"""Code Analysis Pipeline API endpoints.

Provides endpoints for the new end-to-end code analysis pipeline:
- Start analysis
- Get analysis status/progress
- Get results (fused graph, risks, narratives)
- Export in various formats (CSV, JSON, Excel)
"""

from __future__ import annotations

import asyncio
import os
import tempfile
import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from fastapi.responses import PlainTextResponse, StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from starlette.status import HTTP_202_ACCEPTED, HTTP_404_NOT_FOUND

from app.config import settings
from app.core.database import get_db
from app.core.response import ok
from app.services.code_analysis_service import (
    AnalysisResult,
    CodeAnalysisService,
)

router = APIRouter(prefix="/code-analysis", tags=["Code Analysis"])

# In-memory storage for analysis tasks (for MVP; production would use DB/Redis)
_analysis_tasks: dict[str, dict[str, Any]] = {}


class AnalysisRequest(BaseModel):
    """Request to start code analysis."""
    
    workspace_path: str = Field(
        ..., description="Path to the code workspace to analyze"
    )
    project_id: int | None = Field(
        default=None, description="Associated project ID"
    )
    repo_id: int | None = Field(
        default=None, description="Associated repository ID"
    )
    enable_ai: bool = Field(
        default=True, description="Enable AI narrative generation"
    )
    max_files: int = Field(
        default=500, description="Maximum number of files to analyze"
    )
    ai_provider: str = Field(
        default="deepseek", description="AI provider (deepseek or custom)"
    )
    ai_model: str = Field(
        default="deepseek-coder", description="AI model to use"
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


@router.post("/start", status_code=HTTP_202_ACCEPTED)
async def start_analysis(
    req: AnalysisRequest,
    background_tasks: BackgroundTasks,
) -> dict:
    """Start a new code analysis task.
    
    The analysis runs in the background. Use the returned analysis_id
    to poll for status and retrieve results.
    """
    # Validate workspace path
    if not os.path.isdir(req.workspace_path):
        raise HTTPException(400, detail=f"Invalid workspace path: {req.workspace_path}")
    
    analysis_id = str(uuid.uuid4())
    
    # Build AI config
    ai_config = {
        "provider": req.ai_provider,
        "model": req.ai_model,
        "api_key": req.ai_api_key or getattr(settings, f"{req.ai_provider}_api_key", None),
        "base_url": req.ai_base_url or getattr(settings, f"{req.ai_provider}_base_url", None),
    }
    
    # Initialize task state
    _analysis_tasks[analysis_id] = {
        "status": "running",
        "started_at": datetime.now().isoformat(),
        "completed_at": None,
        "result": None,
        "error": None,
        "workspace_path": req.workspace_path,
        "project_id": req.project_id,
        "repo_id": req.repo_id,
    }
    
    # Start background task
    background_tasks.add_task(
        _run_analysis_background,
        analysis_id,
        req.workspace_path,
        ai_config,
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
    workspace_path: str,
    ai_config: dict[str, Any],
    enable_ai: bool,
    max_files: int,
) -> None:
    """Background task to run analysis."""
    try:
        service = CodeAnalysisService(workspace_path, ai_config)
        result = await service.run_full_analysis(enable_ai, max_files)
        
        _analysis_tasks[analysis_id]["result"] = result
        _analysis_tasks[analysis_id]["status"] = (
            "completed" if not result.progress.error else "failed"
        )
        _analysis_tasks[analysis_id]["completed_at"] = datetime.now().isoformat()
        _analysis_tasks[analysis_id]["error"] = result.progress.error
        
    except Exception as e:
        _analysis_tasks[analysis_id]["status"] = "failed"
        _analysis_tasks[analysis_id]["error"] = str(e)
        _analysis_tasks[analysis_id]["completed_at"] = datetime.now().isoformat()


@router.get("/{analysis_id}/status")
async def get_analysis_status(analysis_id: str) -> dict:
    """Get analysis task status and progress."""
    task = _analysis_tasks.get(analysis_id)
    if not task:
        raise HTTPException(HTTP_404_NOT_FOUND, detail="分析任务不存在")
    
    progress = {}
    if task.get("result"):
        progress = task["result"].progress.to_dict()
    
    return ok({
        "analysis_id": analysis_id,
        "status": task["status"],
        "progress": progress,
        "started_at": task["started_at"],
        "completed_at": task.get("completed_at"),
        "error": task.get("error"),
    })


@router.get("/{analysis_id}/results")
async def get_analysis_results(analysis_id: str) -> dict:
    """Get complete analysis results."""
    task = _analysis_tasks.get(analysis_id)
    if not task:
        raise HTTPException(HTTP_404_NOT_FOUND, detail="分析任务不存在")
    
    if task["status"] == "running":
        return ok({
            "status": "running",
            "message": "分析任务仍在运行中",
            "progress": task.get("result", {}).progress.to_dict() if task.get("result") else {},
        })
    
    if task["status"] == "failed":
        return ok({
            "status": "failed",
            "error": task.get("error"),
        })
    
    result: AnalysisResult = task["result"]
    return ok(result.to_dict())


@router.get("/{analysis_id}/call-graph")
async def get_call_graph(analysis_id: str) -> dict:
    """Get call graph data for visualization."""
    task = _analysis_tasks.get(analysis_id)
    if not task or not task.get("result"):
        raise HTTPException(HTTP_404_NOT_FOUND, detail="分析结果不存在")
    
    result: AnalysisResult = task["result"]
    service = CodeAnalysisService(task["workspace_path"])
    service.result = result
    
    return ok(service.get_call_graph_for_visualization())


@router.get("/{analysis_id}/risks")
async def get_risk_findings(
    analysis_id: str,
    severity: str | None = Query(None, description="Filter by severity"),
    risk_type: str | None = Query(None, description="Filter by risk type"),
) -> dict:
    """Get risk findings from analysis."""
    task = _analysis_tasks.get(analysis_id)
    if not task or not task.get("result"):
        raise HTTPException(HTTP_404_NOT_FOUND, detail="分析结果不存在")
    
    result: AnalysisResult = task["result"]
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
    task = _analysis_tasks.get(analysis_id)
    if not task or not task.get("result"):
        raise HTTPException(HTTP_404_NOT_FOUND, detail="分析结果不存在")
    
    result: AnalysisResult = task["result"]
    return ok(result.narratives)


@router.get("/{analysis_id}/function-dictionary")
async def get_function_dictionary(analysis_id: str) -> dict:
    """Get function dictionary with business descriptions."""
    task = _analysis_tasks.get(analysis_id)
    if not task or not task.get("result"):
        raise HTTPException(HTTP_404_NOT_FOUND, detail="分析结果不存在")
    
    result: AnalysisResult = task["result"]
    return ok(result.narratives.get("function_dictionary", {}))


@router.get("/{analysis_id}/risk-cards")
async def get_risk_cards(analysis_id: str) -> dict:
    """Get risk scenario cards."""
    task = _analysis_tasks.get(analysis_id)
    if not task or not task.get("result"):
        raise HTTPException(HTTP_404_NOT_FOUND, detail="分析结果不存在")
    
    result: AnalysisResult = task["result"]
    return ok({
        "cards": result.narratives.get("risk_cards", []),
    })


@router.get("/{analysis_id}/what-if")
async def get_what_if_scenarios(analysis_id: str) -> dict:
    """Get What-If test scenarios."""
    task = _analysis_tasks.get(analysis_id)
    if not task or not task.get("result"):
        raise HTTPException(HTTP_404_NOT_FOUND, detail="分析结果不存在")
    
    result: AnalysisResult = task["result"]
    return ok({
        "scenarios": result.narratives.get("what_if_scenarios", []),
    })


@router.get("/{analysis_id}/test-matrix")
async def get_test_matrix(analysis_id: str) -> dict:
    """Get test design matrix."""
    task = _analysis_tasks.get(analysis_id)
    if not task or not task.get("result"):
        raise HTTPException(HTTP_404_NOT_FOUND, detail="分析结果不存在")
    
    result: AnalysisResult = task["result"]
    return ok(result.narratives.get("test_matrix", {}))


@router.get("/{analysis_id}/protocol-state-machine")
async def get_protocol_state_machine(analysis_id: str) -> dict:
    """Get protocol state machine for visualization."""
    task = _analysis_tasks.get(analysis_id)
    if not task or not task.get("result"):
        raise HTTPException(HTTP_404_NOT_FOUND, detail="分析结果不存在")
    
    result: AnalysisResult = task["result"]
    service = CodeAnalysisService(task["workspace_path"])
    service.result = result
    
    return ok(service.get_protocol_state_machine_for_visualization())


@router.get("/{analysis_id}/export")
async def export_results(
    analysis_id: str,
    fmt: str = Query(
        "json",
        pattern="^(json|csv|test-matrix-csv|risk-cards|function-dict)$",
        description="Export format",
    ),
) -> PlainTextResponse:
    """Export analysis results in various formats.
    
    Formats:
    - json: Complete analysis report (JSON)
    - csv: Test design matrix (CSV, for Excel import)
    - test-matrix-csv: Same as csv
    - risk-cards: Risk scenario cards (JSON)
    - function-dict: Function dictionary (JSON)
    """
    task = _analysis_tasks.get(analysis_id)
    if not task or not task.get("result"):
        raise HTTPException(HTTP_404_NOT_FOUND, detail="分析结果不存在")
    
    result: AnalysisResult = task["result"]
    service = CodeAnalysisService(task["workspace_path"])
    service.result = result
    
    if fmt == "csv" or fmt == "test-matrix-csv":
        content = service.export_test_matrix_csv()
        return PlainTextResponse(
            content,
            media_type="text/csv; charset=utf-8",
            headers={
                "Content-Disposition": f'attachment; filename="test_matrix_{analysis_id}.csv"',
            },
        )
    elif fmt == "risk-cards":
        content = service.export_risk_cards_json()
        return PlainTextResponse(
            content,
            media_type="application/json; charset=utf-8",
            headers={
                "Content-Disposition": f'attachment; filename="risk_cards_{analysis_id}.json"',
            },
        )
    elif fmt == "function-dict":
        content = service.export_function_dictionary_json()
        return PlainTextResponse(
            content,
            media_type="application/json; charset=utf-8",
            headers={
                "Content-Disposition": f'attachment; filename="function_dict_{analysis_id}.json"',
            },
        )
    else:
        content = service.export_full_report_json()
        return PlainTextResponse(
            content,
            media_type="application/json; charset=utf-8",
            headers={
                "Content-Disposition": f'attachment; filename="analysis_report_{analysis_id}.json"',
            },
        )


@router.delete("/{analysis_id}")
async def delete_analysis(analysis_id: str) -> dict:
    """Delete analysis task and results."""
    if analysis_id not in _analysis_tasks:
        raise HTTPException(HTTP_404_NOT_FOUND, detail="分析任务不存在")
    
    del _analysis_tasks[analysis_id]
    return ok({"message": "分析任务已删除"})


@router.get("/")
async def list_analyses(
    status: str | None = Query(None, description="Filter by status"),
    project_id: int | None = Query(None, description="Filter by project ID"),
    repo_id: int | None = Query(None, description="Filter by repository ID"),
    limit: int = Query(20, ge=1, le=100),
) -> dict:
    """List all analysis tasks."""
    tasks = []
    for aid, task in _analysis_tasks.items():
        if status and task["status"] != status:
            continue
        if project_id is not None and task.get("project_id") != project_id:
            continue
        if repo_id is not None and task.get("repo_id") != repo_id:
            continue
        tasks.append({
            "analysis_id": aid,
            "status": task["status"],
            "workspace_path": task["workspace_path"],
            "project_id": task.get("project_id"),
            "repo_id": task.get("repo_id"),
            "started_at": task["started_at"],
            "completed_at": task.get("completed_at"),
        })
    
    # Sort by started_at desc
    tasks.sort(key=lambda x: x["started_at"], reverse=True)
    
    return ok({
        "analyses": tasks[:limit],
        "total": len(tasks),
    })
