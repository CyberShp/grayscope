"""End-to-end code analysis service.

Orchestrates the complete analysis pipeline:
1. Upload/sync code repository
2. Build fused graph (call graph + branches + locks + data flow + protocol ops)
3. Run cross-dimensional risk analysis
4. Generate AI narratives (flow stories, function dictionary, risk cards)
5. Generate test design matrix
6. Export results in various formats
"""

from __future__ import annotations

import asyncio
import csv
import io
import json
import logging
from dataclasses import asdict
from datetime import datetime
from typing import Any

from app.analyzers.fused_graph_builder import FusedGraph, FusedGraphBuilder
from app.analyzers.fused_risk_analyzer import FusedRiskAnalyzer
from app.services.ai_narrative_service import AINarrativeService

logger = logging.getLogger(__name__)


class AnalysisProgress:
    """Tracks analysis progress for UI updates."""
    
    def __init__(self) -> None:
        self.steps: list[dict[str, Any]] = []
        self.current_step: str = ""
        self.progress_percent: int = 0
        self.started_at: datetime = datetime.now()
        self.completed_at: datetime | None = None
        self.error: str | None = None
    
    def start_step(self, step_name: str, weight: int = 10) -> None:
        self.current_step = step_name
        self.steps.append({
            "name": step_name,
            "status": "running",
            "started_at": datetime.now().isoformat(),
            "weight": weight,
        })
        logger.info(f"Analysis step started: {step_name}")
    
    def complete_step(self, step_name: str) -> None:
        for step in self.steps:
            if step["name"] == step_name:
                step["status"] = "completed"
                step["completed_at"] = datetime.now().isoformat()
                break
        completed_weight = sum(
            s["weight"] for s in self.steps if s["status"] == "completed"
        )
        total_weight = sum(s["weight"] for s in self.steps)
        if total_weight > 0:
            self.progress_percent = int((completed_weight / total_weight) * 100)
        logger.info(f"Analysis step completed: {step_name} ({self.progress_percent}%)")
    
    def fail_step(self, step_name: str, error: str) -> None:
        for step in self.steps:
            if step["name"] == step_name:
                step["status"] = "failed"
                step["error"] = error
                break
        self.error = error
        logger.error(f"Analysis step failed: {step_name} - {error}")
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "steps": self.steps,
            "current_step": self.current_step,
            "progress_percent": self.progress_percent,
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "error": self.error,
        }


class AnalysisResult:
    """Container for complete analysis results."""
    
    def __init__(self) -> None:
        self.fused_graph: FusedGraph | None = None
        self.risk_findings: list[dict[str, Any]] = []
        self.comment_issues: list[dict[str, Any]] = []
        self.risk_summary: dict[str, Any] = {}
        self.narratives: dict[str, Any] = {}
        self.protocol_state_machine: dict[str, Any] = {}
        self.progress: AnalysisProgress = AnalysisProgress()
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "fused_graph": self._serialize_fused_graph(),
            "risk_findings": self.risk_findings,
            "comment_issues": self.comment_issues,
            "risk_summary": self.risk_summary,
            "narratives": self.narratives,
            "protocol_state_machine": self.protocol_state_machine,
            "progress": self.progress.to_dict(),
        }
    
    def _serialize_fused_graph(self) -> dict[str, Any] | None:
        if not self.fused_graph:
            return None
        return {
            "nodes": {
                name: {
                    "name": node.name,
                    "file_path": node.file_path,
                    "start_line": node.line_start,
                    "end_line": node.line_end,
                    "params": node.params,
                    "comments": [asdict(c) for c in node.comments],
                    "branches": [asdict(b) for b in node.branches],
                    "lock_ops": [asdict(l) for l in node.lock_ops],
                    "shared_var_access": [asdict(s) for s in node.shared_var_access],
                    "protocol_ops": [asdict(p) for p in node.protocol_ops],
                    "is_entry_point": node.is_entry_point,
                    "entry_point_type": node.entry_point_type,
                }
                for name, node in self.fused_graph.nodes.items()
            },
            "edges": [asdict(e) for e in self.fused_graph.edges],
            "call_chains": [
                {
                    "entry_point": c.entry_point,
                    "entry_type": c.entry_type,
                    "functions": c.functions,
                    "depth": c.depth,
                    "branch_coverage": c.branch_coverage,
                    "lock_sequence": c.lock_sequence,
                    "protocol_sequence": c.protocol_sequence,
                }
                for c in self.fused_graph.call_chains
            ],
            "global_vars": list(self.fused_graph.global_vars),
            "protocol_state_machine": self.fused_graph.protocol_state_machine,
            "stats": {
                "total_functions": len(self.fused_graph.nodes),
                "total_edges": len(self.fused_graph.edges),
                "total_call_chains": len(self.fused_graph.call_chains),
                "entry_points": sum(
                    1 for n in self.fused_graph.nodes.values() if n.is_entry_point
                ),
                "functions_with_branches": sum(
                    1 for n in self.fused_graph.nodes.values() if n.branches
                ),
                "functions_with_locks": sum(
                    1 for n in self.fused_graph.nodes.values() if n.lock_ops
                ),
                "functions_with_protocol_ops": sum(
                    1 for n in self.fused_graph.nodes.values() if n.protocol_ops
                ),
            },
        }


class CodeAnalysisService:
    """End-to-end code analysis orchestration service."""
    
    def __init__(
        self,
        workspace_path: str,
        ai_config: dict[str, Any] | None = None,
    ) -> None:
        self.workspace_path = workspace_path
        self.ai_config = ai_config or {}
        self.result = AnalysisResult()
    
    async def run_full_analysis(
        self,
        enable_ai: bool = True,
        max_files: int = 500,
    ) -> AnalysisResult:
        """Run complete analysis pipeline."""
        try:
            # Step 1: Build fused graph
            self.result.progress.start_step("构建融合图", weight=30)
            await self._build_fused_graph(max_files)
            self.result.progress.complete_step("构建融合图")
            
            # Step 2: Risk analysis
            self.result.progress.start_step("跨维度风险分析", weight=20)
            await self._analyze_risks()
            self.result.progress.complete_step("跨维度风险分析")
            
            # Step 3: AI narratives (if enabled)
            if enable_ai and self.ai_config:
                self.result.progress.start_step("AI 叙事生成", weight=40)
                await self._generate_narratives()
                self.result.progress.complete_step("AI 叙事生成")
            
            # Step 4: Extract protocol state machine
            self.result.progress.start_step("协议状态机提取", weight=10)
            await self._extract_protocol_state_machine()
            self.result.progress.complete_step("协议状态机提取")
            
            self.result.progress.completed_at = datetime.now()
            self.result.progress.progress_percent = 100
            
        except Exception as e:
            self.result.progress.fail_step(self.result.progress.current_step, str(e))
            logger.exception("Analysis pipeline failed")
        
        return self.result
    
    async def _build_fused_graph(self, max_files: int) -> None:
        """Build the fused graph from source code."""
        builder = FusedGraphBuilder()
        loop = asyncio.get_event_loop()
        self.result.fused_graph = await loop.run_in_executor(
            None, builder.build, self.workspace_path, max_files
        )
    
    async def _analyze_risks(self) -> None:
        """Run risk analysis on the fused graph."""
        if not self.result.fused_graph:
            return
        
        analyzer = FusedRiskAnalyzer(self.result.fused_graph)
        loop = asyncio.get_event_loop()
        analysis_result = await loop.run_in_executor(None, analyzer.analyze)
        
        self.result.risk_findings = analysis_result.get("findings", [])
        self.result.comment_issues = analysis_result.get("comment_issues", [])
        self.result.risk_summary = analysis_result.get("summary", {})
    
    async def _generate_narratives(self) -> None:
        """Generate AI narratives from analysis results."""
        if not self.result.fused_graph:
            return
        
        narrative_service = AINarrativeService(self.ai_config)
        self.result.narratives = await narrative_service.generate_full_narrative(
            self.result.fused_graph,
            self.result.risk_findings,
        )
    
    async def _extract_protocol_state_machine(self) -> None:
        """Extract and format protocol state machine."""
        if not self.result.fused_graph:
            return
        
        self.result.protocol_state_machine = (
            self.result.fused_graph.protocol_state_machine
        )
    
    def export_test_matrix_csv(self) -> str:
        """Export test design matrix as CSV."""
        output = io.StringIO()
        writer = csv.writer(output)
        
        # Header
        writer.writerow([
            "用例ID", "分类", "场景名称", "前置条件", "测试步骤",
            "预期结果", "风险结果", "检查点", "优先级", "关联风险"
        ])
        
        matrix = self.result.narratives.get("test_matrix", {})
        cases = matrix.get("matrix", [])
        
        for case in cases:
            writer.writerow([
                case.get("case_id", ""),
                case.get("category", ""),
                case.get("scenario_name", ""),
                "; ".join(case.get("preconditions", [])),
                "; ".join(case.get("test_steps", [])),
                case.get("expected_result", ""),
                case.get("risk_result", ""),
                "; ".join(case.get("checkpoints", [])),
                case.get("priority", ""),
                ", ".join(case.get("risk_ids", [])),
            ])
        
        return output.getvalue()
    
    def export_risk_cards_json(self) -> str:
        """Export risk scenario cards as JSON."""
        return json.dumps(
            self.result.narratives.get("risk_cards", []),
            ensure_ascii=False,
            indent=2,
        )
    
    def export_function_dictionary_json(self) -> str:
        """Export function dictionary as JSON."""
        return json.dumps(
            self.result.narratives.get("function_dictionary", {}),
            ensure_ascii=False,
            indent=2,
        )
    
    def export_full_report_json(self) -> str:
        """Export complete analysis report as JSON."""
        return json.dumps(
            self.result.to_dict(),
            ensure_ascii=False,
            indent=2,
            default=str,
        )
    
    def get_call_graph_for_visualization(self) -> dict[str, Any]:
        """Get call graph data formatted for frontend visualization."""
        if not self.result.fused_graph:
            return {"nodes": [], "edges": []}
        
        nodes = []
        for name, node in self.result.fused_graph.nodes.items():
            nodes.append({
                "id": name,
                "label": name,
                "file": node.file_path,
                "line": node.line_start,
                "isEntryPoint": node.is_entry_point,
                "entryType": node.entry_point_type,
                "hasBranches": len(node.branches) > 0,
                "hasLocks": len(node.lock_ops) > 0,
                "hasProtocol": len(node.protocol_ops) > 0,
                "riskCount": sum(
                    1 for r in self.result.risk_findings
                    if name in r.get("related_functions", [])
                ),
            })
        
        edges = []
        for edge in self.result.fused_graph.edges:
            edges.append({
                "source": edge.caller,
                "target": edge.callee,
                "line": edge.call_site_line,
                "branchContext": edge.branch_context,
                "locksHeld": edge.lock_held,
            })
        
        return {"nodes": nodes, "edges": edges}
    
    def get_protocol_state_machine_for_visualization(self) -> dict[str, Any]:
        """Get protocol state machine formatted for Mermaid diagram."""
        if not self.result.protocol_state_machine:
            return {"states": [], "transitions": [], "mermaid": ""}
        
        psm = self.result.protocol_state_machine
        states_raw = psm.get("states", {})
        # Handle both dict and list formats for states
        states_list = (
            list(states_raw.values())
            if isinstance(states_raw, dict)
            else states_raw
        )
        transitions = psm.get("transitions", [])
        
        # Generate Mermaid state diagram
        mermaid_lines = ["stateDiagram-v2"]
        for state in states_list:
            if state.get("is_initial"):
                mermaid_lines.append(f"    [*] --> {state['name']}")
            if state.get("is_error"):
                mermaid_lines.append(f"    {state['name']} --> [*]: error")
        
        for trans in transitions:
            label = trans.get("action", "")
            if trans.get("condition"):
                label += f" [{trans['condition']}]"
            mermaid_lines.append(
                f"    {trans['from']} --> {trans['to']}: {label}"
            )
        
        return {
            "states": states_list,
            "transitions": transitions,
            "mermaid": "\n".join(mermaid_lines),
        }


def run_analysis_sync(
    workspace_path: str,
    ai_config: dict[str, Any] | None = None,
    enable_ai: bool = True,
    max_files: int = 500,
) -> AnalysisResult:
    """Synchronous wrapper for running analysis."""
    service = CodeAnalysisService(workspace_path, ai_config)
    return asyncio.run(service.run_full_analysis(enable_ai, max_files))
