"""Code Analysis Pipeline API endpoints.

Provides endpoints for the new end-to-end code analysis pipeline:
- Start analysis
- Get analysis status/progress
- Get results (fused graph, risks, narratives)
- Export in various formats (CSV, JSON, Excel)

Tasks are persisted to the database so they survive server restarts.
Running analysis service references are kept in-memory for live
progress tracking, but results are saved to DB on completion.
"""

from __future__ import annotations

import asyncio
import json
import os
import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from starlette.status import HTTP_202_ACCEPTED, HTTP_404_NOT_FOUND

from app.config import settings
from app.core.database import get_db, SessionLocal
from app.core.response import ok, error
from app.repositories import repository_repo
from app.repositories import code_analysis_repo
from app.services.code_analysis_service import (
    AnalysisResult,
    CodeAnalysisService,
)
from app.services.code_analysis_sync_service import (
    sync_code_analysis_to_project,
    delete_synced_data,
)

router = APIRouter(prefix="/code-analysis", tags=["Code Analysis"])

# In-memory map: analysis_id -> running CodeAnalysisService
# Only holds entries while the analysis is actively running.
# After completion the result is persisted to DB and the entry removed.
_running_services: dict[str, CodeAnalysisService] = {}


class AnalysisRequest(BaseModel):
    """Request to start code analysis."""

    workspace_path: str | None = Field(
        default=None, description="Path to the code workspace (auto-resolved from repo_id if not provided)"
    )
    project_id: int | None = Field(
        default=None, description="Associated project ID"
    )
    repo_id: int | None = Field(
        default=None, description="Associated repository ID (used to auto-resolve workspace_path)"
    )
    sub_path: str | None = Field(
        default=None, description="Sub-path within the repository (e.g. 'src/')"
    )
    enable_ai: bool = Field(
        default=True, description="Enable AI narrative generation"
    )
    max_files: int = Field(
        default=500, description="Maximum number of files to analyze"
    )
    ai_provider: str | None = Field(
        default=None, description="AI provider (uses default from settings if not provided)"
    )
    ai_model: str | None = Field(
        default=None, description="AI model (uses default from settings if not provided)"
    )
    ai_api_key: str | None = Field(
        default=None, description="API key (uses settings if not provided)"
    )
    ai_base_url: str | None = Field(
        default=None, description="Base URL (uses settings if not provided)"
    )


class AnalysisStatusResponse(BaseModel):
    """Response for analysis status query."""

    analysis_id: str
    status: str
    progress: dict[str, Any]
    started_at: str
    completed_at: str | None = None
    error: str | None = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_task_or_404(db: Session, analysis_id: str):
    """Fetch a CodeAnalysisTask from DB or raise 404."""
    task = code_analysis_repo.get_by_analysis_id(db, analysis_id)
    if not task:
        raise HTTPException(HTTP_404_NOT_FOUND, detail="分析任务不存在")
    return task


def _load_result_from_json(result_json: str | None) -> AnalysisResult | None:
    """Deserialize AnalysisResult from JSON string."""
    if not result_json:
        return None
    try:
        data = json.loads(result_json)
        result = AnalysisResult()
        result.risk_findings = data.get("risk_findings", [])
        result.comment_issues = data.get("comment_issues", [])
        result.risk_summary = data.get("risk_summary", {})
        result.narratives = data.get("narratives", {})
        result.protocol_state_machine = data.get("protocol_state_machine", {})
        result.semantic_index = data.get("semantic_index", {})
        # fused_graph is stored as serialized dict; keep as-is for read paths
        result._serialized_fused_graph = data.get("fused_graph")

        # Reconstruct deep_analysis if present
        deep = data.get("deep_analysis")
        if deep and isinstance(deep, dict):
            result.deep_analysis = deep

        # Compute risk_summary on-the-fly if stored value is empty
        if not result.risk_summary and result.risk_findings:
            result.risk_summary = _compute_risk_summary(result.risk_findings)

        return result
    except Exception:
        return None


_SEVERITY_NORMALIZE = {
    "S0": "critical", "s0": "critical",
    "S1": "high", "s1": "high",
    "S2": "medium", "s2": "medium",
    "S3": "low", "s3": "low",
    "critical": "critical", "high": "high", "medium": "medium", "low": "low",
}


def _compute_risk_summary(findings: list[dict]) -> dict[str, Any]:
    """Compute risk summary statistics from findings list."""
    severity_dist: dict[str, int] = {"critical": 0, "high": 0, "medium": 0, "low": 0}
    type_dist: dict[str, int] = {}

    for f in findings:
        sev = f.get("severity", "unknown")
        normalized = _SEVERITY_NORMALIZE.get(sev, sev)
        severity_dist[normalized] = severity_dist.get(normalized, 0) + 1
        rt = f.get("risk_type", "unknown")
        type_dist[rt] = type_dist.get(rt, 0) + 1

    return {
        "total_findings": len(findings),
        "severity_distribution": severity_dist,
        "type_distribution": type_dist,
    }


# ---------------------------------------------------------------------------
# Start / Background
# ---------------------------------------------------------------------------

@router.post("/start", status_code=HTTP_202_ACCEPTED)
async def start_analysis(
    req: AnalysisRequest,
    background_tasks: BackgroundTasks,
) -> dict:
    """Start a new code analysis task."""
    workspace_path = req.workspace_path

    # Auto-resolve from repo_id
    if not workspace_path and req.repo_id:
        with SessionLocal() as db:
            repo = repository_repo.get_by_id(db, req.repo_id)
            if not repo:
                raise HTTPException(400, detail=f"Repository {req.repo_id} not found")
            if not repo.local_mirror_path:
                raise HTTPException(400, detail=f"Repository {req.repo_id} has no local mirror path")
            workspace_path = repo.local_mirror_path

    if not workspace_path:
        raise HTTPException(400, detail="workspace_path is required (or provide repo_id with local mirror)")

    if req.sub_path:
        workspace_path = os.path.join(workspace_path, req.sub_path.strip("/"))

    if not os.path.isdir(workspace_path):
        raise HTTPException(400, detail=f"Invalid workspace path: {workspace_path}")

    analysis_id = str(uuid.uuid4())

    ai_provider = req.ai_provider or settings.default_provider
    ai_model = req.ai_model or settings.default_model
    ai_config = {
        "provider": ai_provider,
        "model": ai_model,
        "api_key": req.ai_api_key or getattr(settings, f"{ai_provider}_api_key", None),
        "base_url": req.ai_base_url or getattr(settings, f"{ai_provider}_base_url", None),
    }

    # Persist task to DB
    with SessionLocal() as db:
        code_analysis_repo.create(
            db,
            analysis_id=analysis_id,
            status="running",
            workspace_path=workspace_path,
            project_id=req.project_id,
            repo_id=req.repo_id,
            enable_ai=req.enable_ai,
            started_at=datetime.now().isoformat(),
        )

    # Create service and keep in-memory for live progress
    service = CodeAnalysisService(workspace_path, ai_config)
    _running_services[analysis_id] = service

    background_tasks.add_task(
        _run_analysis_background,
        analysis_id,
        service,
        req.enable_ai,
        req.max_files,
    )

    return ok({
        "analysis_id": analysis_id,
        "status": "running",
        "message": "分析任务已启动，请使用 analysis_id 查询进度",
    })


async def _run_analysis_background(
    analysis_id: str,
    service: CodeAnalysisService,
    enable_ai: bool,
    max_files: int,
) -> None:
    """Background task to run analysis and persist result to DB."""
    try:
        result = await service.run_full_analysis(enable_ai, max_files)
        result_dict = result.to_dict()
        progress_dict = result.progress.to_dict()

        with SessionLocal() as db:
            code_analysis_repo.update(
                db,
                analysis_id,
                status="completed" if not result.progress.error else "failed",
                completed_at=datetime.now().isoformat(),
                error=result.progress.error,
                result_json=json.dumps(result_dict, ensure_ascii=False, default=str),
                progress_json=json.dumps(progress_dict, ensure_ascii=False, default=str),
            )
            
            # Sync to project-level risk/test system if successful and has project_id
            if not result.progress.error:
                task = code_analysis_repo.get_by_analysis_id(db, analysis_id)
                if task and task.project_id and task.repo_id:
                    sync_code_analysis_to_project(
                        db,
                        analysis_id,
                        result_dict,
                        task.project_id,
                        task.repo_id,
                    )

    except Exception as e:
        with SessionLocal() as db:
            code_analysis_repo.update(
                db,
                analysis_id,
                status="failed",
                completed_at=datetime.now().isoformat(),
                error=str(e),
            )
    finally:
        _running_services.pop(analysis_id, None)


# ---------------------------------------------------------------------------
# Status / Progress
# ---------------------------------------------------------------------------

@router.get("/{analysis_id}/status")
async def get_analysis_status(analysis_id: str) -> dict:
    """Get analysis task status and progress."""
    # If still running in this process, return live progress
    service = _running_services.get(analysis_id)
    if service:
        progress = service.result.progress.to_dict()
        return ok({
            "analysis_id": analysis_id,
            "status": "running",
            "progress": progress,
            "started_at": progress.get("started_at"),
            "completed_at": None,
            "error": None,
        })

    # Otherwise load from DB
    with SessionLocal() as db:
        task = _get_task_or_404(db, analysis_id)
        progress = {}
        if task.progress_json:
            try:
                progress = json.loads(task.progress_json)
            except Exception:
                pass

        return ok({
            "analysis_id": analysis_id,
            "status": task.status,
            "progress": progress,
            "started_at": task.started_at,
            "completed_at": task.completed_at,
            "error": task.error,
        })


# ---------------------------------------------------------------------------
# Results (various views)
# ---------------------------------------------------------------------------

def _get_completed_result(analysis_id: str) -> tuple[AnalysisResult, str]:
    """Return (result, workspace_path) or raise 404."""
    # Try live service first
    service = _running_services.get(analysis_id)
    if service and service.result.fused_graph:
        with SessionLocal() as db:
            task = _get_task_or_404(db, analysis_id)
            workspace_path = task.workspace_path
        return service.result, workspace_path

    # Extract all needed values within session context
    with SessionLocal() as db:
        task = _get_task_or_404(db, analysis_id)
        status = task.status
        result_json = task.result_json
        workspace_path = task.workspace_path

    if status == "running":
        raise HTTPException(HTTP_404_NOT_FOUND, detail="分析任务仍在运行中")

    result = _load_result_from_json(result_json)
    if not result:
        raise HTTPException(HTTP_404_NOT_FOUND, detail="分析结果不存在或无法加载")
    return result, workspace_path


@router.get("/{analysis_id}/results")
async def get_analysis_results(analysis_id: str) -> dict:
    """Get complete analysis results."""
    # If running, return running state
    service = _running_services.get(analysis_id)
    if service:
        return ok({
            "status": "running",
            "message": "分析任务仍在运行中",
            "progress": service.result.progress.to_dict(),
        })

    # Extract all needed values within session context
    with SessionLocal() as db:
        task = _get_task_or_404(db, analysis_id)
        status = task.status
        error = task.error
        result_json = task.result_json

    if status == "running":
        return ok({"status": "running", "message": "分析任务仍在运行中"})
    if status == "failed":
        return ok({"status": "failed", "error": error})

    result = _load_result_from_json(result_json)
    if not result:
        raise HTTPException(HTTP_404_NOT_FOUND, detail="分析结果不存在")

    # For full results, use the serialized fused graph if available
    out = {
        "fused_graph": getattr(result, "_serialized_fused_graph", None),
        "risk_findings": result.risk_findings,
        "comment_issues": result.comment_issues,
        "risk_summary": result.risk_summary,
        "narratives": result.narratives,
        "protocol_state_machine": result.protocol_state_machine,
    }
    return ok(out)


def _convert_fused_graph_for_visualization(fg: dict[str, Any], risk_findings: list | None = None) -> dict[str, Any]:
    """Convert serialized fused graph data to visualization format.
    
    The serialized format stores nodes as a dict {name: {node_data}},
    but the frontend expects an array of nodes with specific fields.
    """
    if not fg:
        return {"nodes": [], "edges": [], "call_chains": []}
    
    nodes_raw = fg.get("nodes", {})
    edges_raw = fg.get("edges", [])
    risk_findings = risk_findings or []
    
    # Convert nodes dict to array with visualization fields
    if isinstance(nodes_raw, dict):
        nodes = []
        for name, node_data in nodes_raw.items():
            if not isinstance(node_data, dict):
                continue
            nodes.append({
                "id": name,
                "label": node_data.get("name", name),
                "file": node_data.get("file_path", ""),
                "line": node_data.get("line_start", 0),
                "isEntryPoint": node_data.get("is_entry_point", False),
                "entryType": node_data.get("entry_point_type", "none"),
                "hasBranches": len(node_data.get("branches", [])) > 0,
                "hasLocks": len(node_data.get("lock_ops", [])) > 0,
                "hasProtocol": len(node_data.get("protocol_ops", [])) > 0,
                "riskCount": sum(
                    1 for r in risk_findings
                    if name in r.get("related_functions", [])
                ),
            })
    elif isinstance(nodes_raw, list):
        # Already in array format (from live service)
        nodes = nodes_raw
    else:
        nodes = []
    
    # Convert edges to visualization format
    edges = []
    for edge in edges_raw:
        if isinstance(edge, dict):
            edges.append({
                "source": edge.get("caller", ""),
                "target": edge.get("callee", ""),
                "line": edge.get("call_site_line", 0),
                "branchContext": edge.get("branch_context", ""),
                "locksHeld": edge.get("lock_held", []),
            })
    
    return {"nodes": nodes, "edges": edges, "call_chains": fg.get("call_chains", [])}


@router.get("/{analysis_id}/call-graph")
async def get_call_graph(analysis_id: str) -> dict:
    """Get call graph data for visualization."""
    result, workspace_path = _get_completed_result(analysis_id)

    # If we have the live service with actual FusedGraph objects
    service_live = _running_services.get(analysis_id)
    if service_live and service_live.result.fused_graph:
        return ok(service_live.get_call_graph_for_visualization())

    # Otherwise use serialized data from DB - convert to visualization format
    fg = getattr(result, "_serialized_fused_graph", None)
    if not fg:
        return ok({"nodes": [], "edges": [], "call_chains": []})
    
    # Convert dict-based nodes to array format for frontend
    return ok(_convert_fused_graph_for_visualization(fg, result.risk_findings))


@router.get("/{analysis_id}/risks")
async def get_risk_findings(
    analysis_id: str,
    severity: str | None = Query(None, description="Filter by severity"),
    risk_type: str | None = Query(None, description="Filter by risk type"),
) -> dict:
    """Get risk findings from analysis."""
    result, _ = _get_completed_result(analysis_id)
    findings = result.risk_findings

    if severity:
        findings = [f for f in findings if f.get("severity") == severity]
    if risk_type:
        findings = [f for f in findings if f.get("risk_type") == risk_type]

    return ok({
        "findings": findings,
        "total": len(findings),
        "summary": result.risk_summary,
    })


@router.get("/{analysis_id}/narratives")
async def get_narratives(analysis_id: str) -> dict:
    """Get AI-generated narratives."""
    result, _ = _get_completed_result(analysis_id)
    return ok(result.narratives)


@router.get("/{analysis_id}/function-dictionary")
async def get_function_dictionary(analysis_id: str) -> dict:
    """Get function dictionary with business descriptions."""
    result, _ = _get_completed_result(analysis_id)
    return ok(result.narratives.get("function_dictionary", {}))


@router.get("/{analysis_id}/risk-cards")
async def get_risk_cards(analysis_id: str) -> dict:
    """Get risk scenario cards."""
    result, _ = _get_completed_result(analysis_id)
    return ok({"cards": result.narratives.get("risk_cards", [])})


@router.get("/{analysis_id}/what-if")
async def get_what_if_scenarios(analysis_id: str) -> dict:
    """Get What-If test scenarios."""
    result, _ = _get_completed_result(analysis_id)
    return ok({"scenarios": result.narratives.get("what_if_scenarios", [])})


@router.get("/{analysis_id}/test-matrix")
async def get_test_matrix(analysis_id: str) -> dict:
    """Get test design matrix."""
    result, _ = _get_completed_result(analysis_id)
    return ok(result.narratives.get("test_matrix", {}))


@router.get("/{analysis_id}/protocol-state-machine")
async def get_protocol_state_machine(analysis_id: str) -> dict:
    """Get protocol state machine for visualization."""
    result, workspace_path = _get_completed_result(analysis_id)

    service_live = _running_services.get(analysis_id)
    if service_live and service_live.result.fused_graph:
        return ok(service_live.get_protocol_state_machine_for_visualization())

    return ok(result.protocol_state_machine)


@router.get("/{analysis_id}/deep-analysis")
async def get_deep_analysis_findings(analysis_id: str) -> dict:
    """Get deep analysis findings (P0-P3 cross-function semantic analysis).
    
    Returns findings from the DeepAnalysisEngine that include:
    - Resource leaks at function exit points
    - Callback context constraint violations
    - Ownership transfer errors
    - Initialization/destruction asymmetry
    """
    result, _ = _get_completed_result(analysis_id)
    
    # Get deep analysis results
    deep_analysis = getattr(result, "deep_analysis", None)
    if deep_analysis:
        return ok(deep_analysis.to_dict() if hasattr(deep_analysis, "to_dict") else deep_analysis)
    
    # Check if findings are embedded in risk_findings with is_deep_finding flag
    deep_findings = [
        f for f in result.risk_findings
        if f.get("is_deep_finding") or f.get("source") == "deep_analysis"
    ]
    
    return ok({
        "findings": deep_findings,
        "total": len(deep_findings),
    })


@router.get("/{analysis_id}/semantic-index")
async def get_semantic_index(analysis_id: str) -> dict:
    """Get semantic index built from FusedGraph.
    
    The semantic index provides higher-level semantic structures:
    - Paired operations (acquire/release matching)
    - Unpaired resources (potential leaks)
    - Exit resource states per function
    - Callback contexts and constraints
    - Ownership transfers
    - Init/exit symmetry pairs
    """
    result, _ = _get_completed_result(analysis_id)
    
    semantic_index = getattr(result, "semantic_index", None)
    if semantic_index:
        return ok(semantic_index)
    
    return ok({
        "paired_operations": [],
        "unpaired_resources": [],
        "exit_resource_states": [],
        "callback_contexts": [],
        "ownership_transfers": [],
        "init_exit_pairs": [],
        "function_callers": {},
        "function_callees": {},
    })


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------

@router.get("/{analysis_id}/export")
async def export_results(
    analysis_id: str,
    fmt: str = Query(
        "json",
        pattern="^(json|csv|test-matrix-csv|risk-cards|function-dict)$",
        description="Export format",
    ),
) -> PlainTextResponse:
    """Export analysis results in various formats."""
    result, workspace_path = _get_completed_result(analysis_id)

    service = CodeAnalysisService(workspace_path)
    service.result = result

    if fmt in ("csv", "test-matrix-csv"):
        content = service.export_test_matrix_csv()
        return PlainTextResponse(
            content,
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="test_matrix_{analysis_id}.csv"'},
        )
    elif fmt == "risk-cards":
        content = service.export_risk_cards_json()
        return PlainTextResponse(
            content,
            media_type="application/json; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="risk_cards_{analysis_id}.json"'},
        )
    elif fmt == "function-dict":
        content = service.export_function_dictionary_json()
        return PlainTextResponse(
            content,
            media_type="application/json; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="function_dict_{analysis_id}.json"'},
        )
    else:
        content = service.export_full_report_json()
        return PlainTextResponse(
            content,
            media_type="application/json; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="analysis_report_{analysis_id}.json"'},
        )


# ---------------------------------------------------------------------------
# Delete / List
# ---------------------------------------------------------------------------

@router.delete("/{analysis_id}")
async def delete_analysis(analysis_id: str) -> dict:
    """Delete analysis task and results, including synced project data."""
    _running_services.pop(analysis_id, None)
    with SessionLocal() as db:
        # Delete synced project data (bridge AnalysisTask, RiskFindings, TestCases)
        delete_synced_data(db, analysis_id)
        # Delete the code analysis task itself
        deleted = code_analysis_repo.delete(db, analysis_id)
    if not deleted:
        raise HTTPException(HTTP_404_NOT_FOUND, detail="分析任务不存在")
    return ok({"message": "分析任务已删除"})


@router.get("/")
async def list_analyses(
    status: str | None = Query(None, description="Filter by status"),
    project_id: int | None = Query(None, description="Filter by project ID"),
    repo_id: int | None = Query(None, description="Filter by repository ID"),
    limit: int = Query(20, ge=1, le=100),
) -> dict:
    """List all analysis tasks."""
    with SessionLocal() as db:
        tasks = code_analysis_repo.list_tasks(
            db, status=status, project_id=project_id, repo_id=repo_id, limit=limit,
        )
        total = code_analysis_repo.count_tasks(
            db, status=status, project_id=project_id, repo_id=repo_id,
        )
        items = [
            {
                "analysis_id": t.analysis_id,
                "status": t.status,
                "workspace_path": t.workspace_path,
                "project_id": t.project_id,
                "repo_id": t.repo_id,
                "started_at": t.started_at,
                "completed_at": t.completed_at,
            }
            for t in tasks
        ]

    # Overlay running services that might have been lost from DB perspective
    running_ids = {t["analysis_id"] for t in items}
    extra_running = 0
    for aid in _running_services:
        if aid not in running_ids:
            items.insert(0, {
                "analysis_id": aid,
                "status": "running",
                "workspace_path": "",
                "started_at": "",
            })
            extra_running += 1

    return ok({"analyses": items[:limit], "total": total + extra_running})
