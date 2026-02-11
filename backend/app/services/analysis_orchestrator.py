"""分析任务编排器。

按模块依赖顺序执行分析器，完成后进行 AI 增强处理。
支持全部 9 个分析器模块。
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.analyzers import (
    branch_path_analyzer,
    boundary_value_analyzer,
    error_path_analyzer,
    call_graph_builder,
    concurrency_analyzer,
    diff_impact_analyzer,
    coverage_mapper,
    postmortem_analyzer,
    knowledge_pattern_manager,
)
from app.analyzers.base import AnalyzeContext, ModuleResult
from app.analyzers.code_parser import CodeParser
from app.analyzers.registry import get_display_name
from app.repositories import task_repo
from app.services.ai_enrichment import enrich_module

logger = logging.getLogger(__name__)

# ── 模块依赖图 ──────────────────────────────────────────────────────────
MODULE_DEPS: dict[str, list[str]] = {
    "branch_path": [],
    "boundary_value": [],
    "error_path": [],
    "call_graph": [],
    "concurrency": ["call_graph"],
    "diff_impact": ["call_graph"],
    "coverage_map": ["branch_path", "boundary_value", "error_path"],
    "postmortem": [],        # 事后分析可独立运行（依赖缺陷输入，非上游模块）
    "knowledge_pattern": ["postmortem"],
}

# ── 风险评分权重 ──────────────────────────────────────────────────────
MODULE_WEIGHTS: dict[str, float] = {
    "branch_path": 1.1,
    "boundary_value": 0.9,
    "error_path": 1.1,
    "call_graph": 0.6,
    "concurrency": 1.3,
    "diff_impact": 1.2,
    "coverage_map": 1.2,
    "postmortem": 1.0,
    "knowledge_pattern": 0.7,
}

# ── 分析器注册表 ──────────────────────────────────────────────────────
_ANALYZER_REGISTRY: dict[str, Any] = {
    "branch_path": branch_path_analyzer,
    "boundary_value": boundary_value_analyzer,
    "error_path": error_path_analyzer,
    "call_graph": call_graph_builder,
    "concurrency": concurrency_analyzer,
    "diff_impact": diff_impact_analyzer,
    "coverage_map": coverage_mapper,
    "postmortem": postmortem_analyzer,
    "knowledge_pattern": knowledge_pattern_manager,
}


def _topological_order(modules: list[str]) -> list[str]:
    """根据依赖关系对模块进行拓扑排序。"""
    module_set = set(modules)
    visited: set[str] = set()
    order: list[str] = []

    def _visit(m: str) -> None:
        if m in visited:
            return
        visited.add(m)
        for dep in MODULE_DEPS.get(m, []):
            if dep in module_set:
                _visit(dep)
        order.append(m)

    for m in modules:
        _visit(m)
    return order


def _build_context(task, upstream: dict[str, dict]) -> AnalyzeContext:
    """从任务 ORM 对象构建分析上下文。"""
    target = json.loads(task.target_json)
    revision = json.loads(task.revision_json)
    options = json.loads(task.options_json) if task.options_json else {}
    from app.repositories import repository_repo
    from app.core.database import SessionLocal

    # 获取仓库工作空间路径
    with SessionLocal() as db2:
        repo = repository_repo.get_by_id(db2, task.repo_id)
        workspace = repo.local_mirror_path if repo else ""

    return {
        "task_id": task.task_id,
        "project_id": task.project_id,
        "repo_id": task.repo_id,
        "workspace_path": workspace,
        "target": target,
        "revision": revision,
        "options": options,
        "upstream_results": upstream,
    }


def _collect_source_snippets(workspace: str, target: dict) -> dict[str, str]:
    """收集函数源代码片段用于 AI 增强上下文。"""
    snippets: dict[str, str] = {}
    target_path = Path(workspace) / target.get("path", "")
    if not target_path.exists():
        return snippets
    try:
        parser = CodeParser()
        if target_path.is_file():
            symbols = parser.parse_file(target_path)
        else:
            symbols = parser.parse_directory(target_path, max_files=20)
        for sym in symbols:
            if sym.kind == "function" and sym.source:
                snippets[sym.name] = sym.source[:3000]
    except Exception:
        pass
    return snippets


def run_task(db: Session, task_id: str) -> None:
    """执行任务中所有待处理的分析模块。"""
    task = task_repo.get_task_by_id(db, task_id)
    if task is None:
        logger.error("任务 %s 未找到", task_id)
        return

    task_repo.update_task_status(db, task_id, "running")

    analyzers = json.loads(task.analyzers_json)
    ai_config = json.loads(task.ai_json) if task.ai_json else {}
    ordered = _topological_order(analyzers)

    results = task_repo.get_module_results(db, task.id)
    result_map = {r.module_id: r for r in results}

    upstream: dict[str, dict] = {}

    for mod_id in ordered:
        mr = result_map.get(mod_id)
        if mr is None:
            continue
        if mr.status not in ("pending", "failed"):
            # 已完成或已跳过 — 若成功则加载到上游结果中
            if mr.status == "success" and mr.findings_json:
                upstream[mod_id] = {
                    "findings": json.loads(mr.findings_json),
                    "risk_score": mr.risk_score or 0.0,
                }
            continue

        # 检查依赖是否满足
        deps = MODULE_DEPS.get(mod_id, [])
        deps_ok = all(
            result_map.get(d) and result_map[d].status == "success"
            for d in deps
            if d in result_map
        )
        if not deps_ok:
            task_repo.update_module_result(
                db, mr.id,
                status="skipped",
                error_json=json.dumps({"reason": "依赖模块未成功完成"}),
            )
            continue

        task_repo.update_module_result(db, mr.id, status="running")

        try:
            # 构建上下文
            ctx = _build_context(task, upstream)

            # 运行已注册的分析器，否则使用占位实现
            analyzer_mod = _ANALYZER_REGISTRY.get(mod_id)
            if analyzer_mod is not None:
                module_result: ModuleResult = analyzer_mod.analyze(ctx)
            else:
                module_result = _stub_analyze(mod_id, ctx)

            findings = module_result["findings"]
            risk_score = module_result["risk_score"]
            metrics = module_result["metrics"]
            artifacts = module_result["artifacts"]
            warnings = module_result["warnings"]

            # AI 增强分析（尽力而为，不阻塞主流程）
            ai_summary_data: dict[str, Any] = {}
            if findings and ai_config:
                try:
                    snippets = _collect_source_snippets(
                        ctx["workspace_path"], ctx["target"]
                    )
                    ai_summary_data = enrich_module(
                        mod_id, findings, snippets, ai_config
                    )
                except Exception as ai_exc:
                    logger.warning("AI 增强失败 [%s]: %s", get_display_name(mod_id), ai_exc)
                    ai_summary_data = {
                        "ai_summary": f"AI 增强不可用: {ai_exc}",
                        "success": False,
                    }

            task_repo.update_module_result(
                db, mr.id,
                status="success",
                risk_score=risk_score,
                findings_json=json.dumps(findings, ensure_ascii=False),
                metrics_json=json.dumps(metrics),
                artifacts_json=json.dumps(
                    [a for a in artifacts if a.get("type") != "call_graph_json"],
                    default=str,
                ),
                ai_summary_json=json.dumps(ai_summary_data, ensure_ascii=False, default=str)
                if ai_summary_data
                else None,
            )
            upstream[mod_id] = {"findings": findings, "risk_score": risk_score}

        except Exception as exc:
            logger.exception("模块 %s 执行失败", get_display_name(mod_id))
            task_repo.update_module_result(
                db, mr.id,
                status="failed",
                error_json=json.dumps({"error": str(exc)}),
            )

    # 聚合风险评分
    refreshed = task_repo.get_module_results(db, task.id)
    scores = [
        (MODULE_WEIGHTS.get(r.module_id, 1.0), r.risk_score or 0.0)
        for r in refreshed
        if r.status == "success" and r.risk_score is not None
    ]
    if scores:
        agg = sum(w * s for w, s in scores) / sum(w for w, _ in scores)
        task_repo.set_aggregate_score(db, task_id, round(agg, 4))

    # 确定最终任务状态
    statuses = {r.status for r in refreshed}
    if "failed" in statuses:
        final = "partial_failed" if "success" in statuses else "failed"
    else:
        final = "success"
    task_repo.update_task_status(db, task_id, final)


def _stub_analyze(mod_id: str, ctx: AnalyzeContext) -> ModuleResult:
    """尚未实现的模块占位分析器。"""
    display = get_display_name(mod_id)
    return {
        "module_id": mod_id,
        "status": "success",
        "risk_score": 0.1,
        "findings": [{
            "finding_id": f"{mod_id}-STUB-0001",
            "module_id": mod_id,
            "risk_type": "placeholder",
            "severity": "S3",
            "risk_score": 0.1,
            "title": f"占位: {display}尚未实现",
            "description": f"模块 {display} 将在后续阶段实现",
            "file_path": "stub",
            "symbol_name": "",
            "line_start": 0,
            "line_end": 0,
            "evidence": {},
        }],
        "metrics": {"stub": True},
        "artifacts": [],
        "warnings": [f"{display} 为占位实现"],
    }
