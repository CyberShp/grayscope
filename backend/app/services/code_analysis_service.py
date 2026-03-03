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
from app.analyzers.semantic_indexer import SemanticIndexer
from app.analyzers.deep_analysis_engine import DeepAnalysisEngine, DeepAnalysisResult
from app.services.ai_narrative_service import AINarrativeService
from app.utils.data import flatten_list as _flatten_list

logger = logging.getLogger(__name__)


class AnalysisProgress:
    """Tracks analysis progress for UI updates.
    
    增强版本特性:
    - elapsed_seconds: 已用时间
    - estimated_remaining: 基于已完成步骤耗时估算剩余时间
    - duration_ms: 每个步骤的实际耗时
    - sub_progress: 子步骤级别的进度追踪
    """
    
    def __init__(self) -> None:
        self.steps: list[dict[str, Any]] = []
        self.current_step: str = ""
        self.progress_percent: int = 0
        self.started_at: datetime = datetime.now()
        self.completed_at: datetime | None = None
        self.error: str | None = None
        self._sub_progress: dict[str, dict[str, int]] = {}  # step_name -> {completed, total}
    
    def start_step(self, step_name: str, weight: int = 10, is_sub_step: bool = False, parent_step: str | None = None) -> None:
        """开始一个步骤.
        
        Args:
            step_name: 步骤名称
            weight: 权重（用于计算总进度百分比）
            is_sub_step: 是否为子步骤
            parent_step: 父步骤名称（仅子步骤需要）
        """
        self.current_step = step_name
        step_data = {
            "name": step_name,
            "status": "running",
            "started_at": datetime.now().isoformat(),
            "weight": weight,
            "is_sub_step": is_sub_step,
        }
        if parent_step:
            step_data["parent_step"] = parent_step
        self.steps.append(step_data)
        logger.info(f"Analysis step started: {step_name}")
    
    def complete_step(self, step_name: str) -> None:
        """完成一个步骤."""
        now = datetime.now()
        for step in self.steps:
            if step["name"] == step_name:
                step["status"] = "completed"
                step["completed_at"] = now.isoformat()
                # 计算 duration_ms
                try:
                    started = datetime.fromisoformat(step["started_at"])
                    step["duration_ms"] = int((now - started).total_seconds() * 1000)
                except (KeyError, ValueError):
                    step["duration_ms"] = 0
                break
        
        self._update_progress_percent()
        logger.info(f"Analysis step completed: {step_name} ({self.progress_percent}%)")
    
    def fail_step(self, step_name: str, error: str) -> None:
        """标记步骤失败."""
        now = datetime.now()
        for step in self.steps:
            if step["name"] == step_name:
                step["status"] = "failed"
                step["error"] = error
                step["completed_at"] = now.isoformat()
                try:
                    started = datetime.fromisoformat(step["started_at"])
                    step["duration_ms"] = int((now - started).total_seconds() * 1000)
                except (KeyError, ValueError):
                    step["duration_ms"] = 0
                break
        self.error = error
        logger.error(f"Analysis step failed: {step_name} - {error}")
    
    def update_sub_progress(self, step_name: str, completed: int, total: int) -> None:
        """更新步骤的子进度.
        
        用于追踪批量操作的进度，如 "函数字典 3/5 批次"。
        """
        self._sub_progress[step_name] = {"completed": completed, "total": total}
        
        # 更新对应步骤的 sub_progress 字段
        for step in self.steps:
            if step["name"] == step_name:
                step["sub_progress"] = {"completed": completed, "total": total}
                break
        
        # 重新计算总进度
        self._update_progress_percent()
    
    def _update_progress_percent(self) -> None:
        """重新计算总进度百分比.
        
        考虑:
        1. 已完成步骤的完整权重
        2. 正在运行步骤的部分权重（基于 sub_progress）
        """
        completed_weight = 0.0
        total_weight = sum(s["weight"] for s in self.steps)
        
        for step in self.steps:
            if step["status"] == "completed":
                completed_weight += step["weight"]
            elif step["status"] == "running":
                # 如果有子进度，按比例计算部分权重
                sub = step.get("sub_progress")
                if sub and sub["total"] > 0:
                    ratio = sub["completed"] / sub["total"]
                    completed_weight += step["weight"] * ratio
        
        if total_weight > 0:
            self.progress_percent = int((completed_weight / total_weight) * 100)
    
    @property
    def elapsed_seconds(self) -> float:
        """已用时间（秒）."""
        if self.completed_at:
            return (self.completed_at - self.started_at).total_seconds()
        return (datetime.now() - self.started_at).total_seconds()
    
    @property
    def estimated_remaining(self) -> float | None:
        """估算剩余时间（秒）.
        
        基于已完成步骤的加权平均耗时推算。
        """
        completed_steps = [s for s in self.steps if s["status"] == "completed" and s.get("duration_ms")]
        if not completed_steps:
            return None
        
        # 计算加权平均耗时
        total_duration_ms = sum(s["duration_ms"] for s in completed_steps)
        total_completed_weight = sum(s["weight"] for s in completed_steps)
        
        if total_completed_weight == 0:
            return None
        
        avg_ms_per_weight = total_duration_ms / total_completed_weight
        
        # 计算剩余权重
        remaining_weight = 0
        for step in self.steps:
            if step["status"] == "pending":
                remaining_weight += step["weight"]
            elif step["status"] == "running":
                # 正在运行的步骤，考虑子进度
                sub = step.get("sub_progress")
                if sub and sub["total"] > 0:
                    remaining_ratio = 1 - (sub["completed"] / sub["total"])
                    remaining_weight += step["weight"] * remaining_ratio
                else:
                    remaining_weight += step["weight"]
        
        return (avg_ms_per_weight * remaining_weight) / 1000
    
    def to_dict(self) -> dict[str, Any]:
        """转换为字典用于 API 响应."""
        return {
            "steps": self.steps,
            "current_step": self.current_step,
            "progress_percent": self.progress_percent,
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "error": self.error,
            "elapsed_seconds": round(self.elapsed_seconds, 1),
            "estimated_remaining": round(self.estimated_remaining, 1) if self.estimated_remaining else None,
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
        # 深度分析结果（P0-P3）
        self.deep_analysis: DeepAnalysisResult | None = None
        self.semantic_index: dict[str, Any] = {}
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "fused_graph": self._serialize_fused_graph(),
            "risk_findings": self.risk_findings,
            "comment_issues": self.comment_issues,
            "risk_summary": self.risk_summary,
            "narratives": self.narratives,
            "protocol_state_machine": self.protocol_state_machine,
            "progress": self.progress.to_dict(),
            "deep_analysis": self.deep_analysis.to_dict() if self.deep_analysis else None,
            "semantic_index": self.semantic_index,
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
        enable_deep_analysis: bool = True,
        max_files: int = 500,
    ) -> AnalysisResult:
        """Run complete analysis pipeline.
        
        步骤权重分配:
        - 构建融合图: 20
        - 构建语义索引: 10
        - 跨维度风险分析: 15
        - 深度 AI 分析 (新增): 15
        - AI 叙事生成 (5 个子步骤): 30
          - AI: 调用链叙事: 8
          - AI: 函数字典: 8
          - AI: 风险卡片: 6
          - AI: What-If场景: 4
          - AI: 测试矩阵: 4
        - 协议状态机提取: 10
        """
        try:
            # Step 1: Build fused graph
            self.result.progress.start_step("构建融合图", weight=20)
            await self._build_fused_graph(max_files)
            self.result.progress.complete_step("构建融合图")
            
            # Step 2: Build semantic index (P0 core)
            self.result.progress.start_step("构建语义索引", weight=10)
            await self._build_semantic_index()
            self.result.progress.complete_step("构建语义索引")
            
            # Step 3: Risk analysis
            self.result.progress.start_step("跨维度风险分析", weight=15)
            await self._analyze_risks()
            self.result.progress.complete_step("跨维度风险分析")
            
            # Step 4: Deep AI analysis (if enabled) - parallel with narratives
            deep_analysis_task = None
            if enable_deep_analysis and enable_ai and self.ai_config:
                self.result.progress.start_step("深度 AI 分析", weight=15)
                deep_analysis_task = asyncio.create_task(self._run_deep_analysis())
            
            # Step 5: AI narratives (if enabled) - 拆分为 5 个子步骤
            if enable_ai and self.ai_config:
                await self._generate_narratives_with_substeps()
            
            # Wait for deep analysis to complete
            if deep_analysis_task:
                await deep_analysis_task
                self.result.progress.complete_step("深度 AI 分析")
            
            # Step 6: Extract protocol state machine
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
        self.result.fused_graph = await asyncio.to_thread(
            builder.build, self.workspace_path, max_files
        )
    
    async def _analyze_risks(self) -> None:
        """Run risk analysis on the fused graph."""
        if not self.result.fused_graph:
            return
        
        analyzer = FusedRiskAnalyzer(self.result.fused_graph)
        analysis_result = await asyncio.to_thread(analyzer.analyze)
        
        self.result.risk_findings = analysis_result.get("findings", [])
        self.result.comment_issues = analysis_result.get("comment_issues", [])
        self.result.risk_summary = analysis_result.get("summary", {})
    
    async def _build_semantic_index(self) -> None:
        """Build semantic index from fused graph (P0 core).
        
        语义索引器是纯程序化的后处理，将 FusedGraph 中的原始数据
        提升为更高层次的语义结构:
        - 配对操作 (acquire/release 匹配)
        - 未配对资源 (潜在泄漏/多余释放)
        - 出口资源状态
        - 回调上下文映射
        - 所有权转移
        - 初始化/退出对称性
        """
        if not self.result.fused_graph:
            return
        
        try:
            indexer = SemanticIndexer(self.result.fused_graph)
            semantic_index = await asyncio.to_thread(indexer.build)
            self.result.semantic_index = semantic_index.to_dict()
            logger.info(
                "Semantic index built: paired=%d, unpaired=%d, callbacks=%d, ownership=%d",
                len(semantic_index.paired_operations),
                len(semantic_index.unpaired_resources),
                len(semantic_index.callback_contexts),
                len(semantic_index.ownership_transfers),
            )
        except Exception as e:
            logger.warning("Semantic index build failed: %s", e)
            self.result.semantic_index = {}
    
    async def _run_deep_analysis(self) -> None:
        """Run deep AI analysis using semantic index (P0-P3).
        
        深度分析引擎使用语义索引的结构化上下文，
        组装 AI 提示进行跨函数语义分析:
        - 资源泄漏检测 (P0)
        - 回调约束违反 (P1)
        - 所有权错误 (P1)
        - 初始化/退出不对称 (P2)
        """
        if not self.result.fused_graph:
            return
        
        try:
            # 从已构建的语义索引重建 SemanticIndex 对象
            indexer = SemanticIndexer(self.result.fused_graph)
            semantic_index = indexer.build()
            
            # 运行深度分析
            engine = DeepAnalysisEngine(
                graph=self.result.fused_graph,
                semantic_index=semantic_index,
                ai_config=self.ai_config,
            )
            
            deep_result = await engine.analyze(
                existing_risk_findings=self.result.risk_findings,
                max_targets=50,  # 限制分析目标数量
            )
            
            self.result.deep_analysis = deep_result
            
            # 将深度分析发现合并到 risk_findings
            if deep_result.findings:
                merged_findings = self._merge_deep_findings(deep_result.findings)
                self.result.risk_findings.extend(merged_findings)
                logger.info("Deep analysis completed: %d new findings", len(merged_findings))
            else:
                logger.info("Deep analysis completed: no new findings")
                
        except Exception as e:
            logger.warning("Deep analysis failed: %s", e)
            self.result.deep_analysis = None
    
    def _merge_deep_findings(
        self, deep_findings: list
    ) -> list[dict[str, Any]]:
        """Convert deep analysis findings to standard risk finding format."""
        merged = []
        
        for finding in deep_findings:
            # 转换为标准风险发现格式
            risk_finding = {
                "id": f"deep_{finding.finding_type}_{finding.file_path}_{finding.line_start}",
                "type": finding.finding_type,
                "severity": finding.severity,
                "confidence": finding.confidence,
                "title": finding.title,
                "description": finding.description,
                "file_path": finding.file_path,
                "function_name": finding.function_name,
                "line_start": finding.line_start,
                "line_end": finding.line_end,
                "execution_path": finding.execution_path,
                "evidence": finding.evidence,
                "fix_suggestion": finding.fix_suggestion,
                "source": "deep_analysis",
                "is_deep_finding": True,
            }
            merged.append(risk_finding)
        
        return merged
    
    async def _generate_narratives(self) -> None:
        """Generate AI narratives from analysis results (without sub-step tracking)."""
        if not self.result.fused_graph:
            return
        
        narrative_service = AINarrativeService(self.ai_config)
        self.result.narratives = await narrative_service.generate_full_narrative(
            self.result.fused_graph,
            self.result.risk_findings,
        )
    
    async def _generate_narratives_with_substeps(self) -> None:
        """Generate AI narratives with detailed sub-step progress tracking.
        
        将 AI 叙事生成拆分为 5 个子步骤:
        1. AI: 调用链叙事 (weight=10)
        2. AI: 函数字典 (weight=10)
        3. AI: 风险卡片 (weight=8)
        4. AI: What-If场景 (weight=6)
        5. AI: 测试矩阵 (weight=6)
        """
        if not self.result.fused_graph:
            return
        
        # 子步骤配置
        substeps = [
            ("AI: 调用链叙事", 10, "flow_narratives"),
            ("AI: 函数字典", 10, "function_dictionary"),
            ("AI: 风险卡片", 8, "risk_cards"),
            ("AI: What-If场景", 6, "what_if_scenarios"),
            ("AI: 测试矩阵", 6, "test_matrix"),
        ]
        
        # 注册所有子步骤（状态为 pending）
        for step_name, weight, _ in substeps:
            self.result.progress.steps.append({
                "name": step_name,
                "status": "pending",
                "weight": weight,
                "is_sub_step": True,
                "parent_step": "AI 叙事生成",
            })
        
        # 追踪当前完成的子步骤
        completed_substeps: set[str] = set()
        
        def on_progress(step_key: str, completed: int, total: int) -> None:
            """进度回调: 由 AINarrativeService 调用."""
            # 映射 step_key 到子步骤名称
            step_mapping = {
                "flow_narratives": "AI: 调用链叙事",
                "function_dictionary": "AI: 函数字典",
                "risk_cards": "AI: 风险卡片",
                "what_if_scenarios": "AI: What-If场景",
                "test_matrix": "AI: 测试矩阵",
            }
            step_name = step_mapping.get(step_key)
            if not step_name:
                return
            
            # 更新步骤状态
            for step in self.result.progress.steps:
                if step["name"] == step_name:
                    if step["status"] == "pending":
                        # 首次进度更新 -> running
                        step["status"] = "running"
                        step["started_at"] = datetime.now().isoformat()
                        self.result.progress.current_step = step_name
                        logger.info(f"AI sub-step started: {step_name}")
                    
                    # 更新子进度
                    step["sub_progress"] = {"completed": completed, "total": total}
                    
                    # 如果完成了
                    if completed >= total and step_name not in completed_substeps:
                        step["status"] = "completed"
                        step["completed_at"] = datetime.now().isoformat()
                        try:
                            started = datetime.fromisoformat(step["started_at"])
                            step["duration_ms"] = int((datetime.now() - started).total_seconds() * 1000)
                        except (KeyError, ValueError):
                            step["duration_ms"] = 0
                        completed_substeps.add(step_name)
                        logger.info(f"AI sub-step completed: {step_name}")
                    break
            
            # 重新计算总进度
            self.result.progress._update_progress_percent()
        
        # 执行 AI 叙事生成（带进度回调）
        narrative_service = AINarrativeService(self.ai_config)
        self.result.narratives = await narrative_service.generate_full_narrative(
            self.result.fused_graph,
            self.result.risk_findings,
            on_progress=on_progress,
        )
        
        # 确保所有子步骤都标记为完成
        for step_name, _, _ in substeps:
            for step in self.result.progress.steps:
                if step["name"] == step_name and step["status"] != "completed":
                    step["status"] = "completed"
                    if "completed_at" not in step:
                        step["completed_at"] = datetime.now().isoformat()
                    break
    
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
                "; ".join(_flatten_list(case.get("preconditions", []))),
                "; ".join(_flatten_list(case.get("test_steps", []))),
                case.get("expected_result", ""),
                case.get("risk_result", ""),
                "; ".join(_flatten_list(case.get("checkpoints", []))),
                case.get("priority", ""),
                ", ".join(_flatten_list(case.get("risk_ids", []))),
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
