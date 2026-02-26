"""聚合数据 API 端点 — 为新版前端提供项目概览、发现列表、度量、测试设计等聚合数据。"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import List, Optional, Union

from typing import Any, List, Union

from fastapi import APIRouter, Depends, Query, Body
from pydantic import BaseModel, Field
from sqlalchemy import func, desc
from sqlalchemy.orm import Session

from app.config import settings as app_settings
from app.core.database import get_db
from app.core.response import ok
from app.models.analysis_task import AnalysisTask
from app.models.module_result import AnalysisModuleResult
from app.models.project import Project
from app.models.repository import Repository
from app.analyzers.registry import get_display_name
from app.services.export_service import (
    _findings_to_testcases,
    get_diff_impact_affected_symbols,
    _risk_type_to_objective,
    _risk_type_to_preconditions,
    _risk_type_to_steps,
    _risk_type_to_expected,
    _SEV_PRIORITY,
)
from app.models.test_case import TestCase
from app.services.testcase_service import (
    persist_test_cases,
    get_project_test_cases,
    get_by_id as get_test_case_by_id,
    update_test_case_status,
    update_test_case,
)
from app.services.execution_settings import get_execution_config, save_execution_config

router = APIRouter()


class TestCaseUpdateBody(BaseModel):
    """测试用例可编辑字段（部分更新）。"""
    title: Optional[str] = Field(default=None, max_length=256)
    priority: Optional[str] = Field(default=None, max_length=32)
    preconditions: Optional[List[str]] = None
    test_steps: Optional[List[str]] = None
    expected_result: Optional[Union[str, List[str]]] = None
    objective: Optional[str] = None
    execution_hint: Optional[str] = None
    example_input: Optional[str] = None
    expected_failure: Optional[str] = None
    unacceptable_outcomes: Optional[List[str]] = None
    related_functions: Optional[List[str]] = None


# ═══════════════════════════════════════════════════════════════════════
# 项目聚合
# ═══════════════════════════════════════════════════════════════════════


@router.get("/projects/{project_id}/summary")
def project_summary(project_id: int, db: Session = Depends(get_db)) -> dict:
    """项目概览聚合数据：风险评分、发现数、模块概要、最近任务、趋势。"""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        return ok({})

    # 任务统计
    tasks = (
        db.query(AnalysisTask)
        .filter(AnalysisTask.project_id == project_id)
        .order_by(desc(AnalysisTask.created_at))
        .all()
    )
    task_count = len(tasks)

    # 平均风险评分（基于最近一个成功任务）
    latest_success = next(
        (t for t in tasks if t.status == "success" and t.aggregate_risk_score is not None),
        None,
    )

    # 发现统计 — 仅基于最近一个成功任务（避免跨任务累计导致重复膨胀）
    latest_findings = []
    if latest_success:
        for mr in latest_success.module_results:
            try:
                findings = json.loads(mr.findings_json) if mr.findings_json else []
                for f in findings:
                    f["task_id"] = latest_success.task_id
                    f["project_id"] = project_id
                latest_findings.extend(findings)
            except (json.JSONDecodeError, TypeError):
                pass

    finding_count = len(latest_findings)
    s0_count = sum(1 for f in latest_findings if f.get("severity") == "S0")
    s1_count = sum(1 for f in latest_findings if f.get("severity") == "S1")

    avg_risk_score = latest_success.aggregate_risk_score if latest_success else None

    # 模块概要（来自最近一个成功任务）
    modules = []
    if latest_success:
        for mr in latest_success.module_results:
            try:
                findings = json.loads(mr.findings_json) if mr.findings_json else []
            except (json.JSONDecodeError, TypeError):
                findings = []
            modules.append({
                "module_id": mr.module_id,
                "module": mr.module_id,
                "display_name": get_display_name(mr.module_id),
                "status": mr.status,
                "risk_score": mr.risk_score,
                "finding_count": len(findings),
            })

    # 最近任务（最多 5 个）
    recent_tasks = []
    for t in tasks[:5]:
        recent_tasks.append({
            "task_id": t.task_id,
            "task_type": t.task_type,
            "status": t.status,
            "aggregate_risk_score": t.aggregate_risk_score,
            "created_at": t.created_at.isoformat() if t.created_at else None,
        })

    # 趋势（最近 10 个成功任务的风险评分）
    trends = []
    success_tasks = [t for t in tasks if t.status == "success" and t.aggregate_risk_score is not None]
    for t in reversed(success_tasks[:10]):
        trends.append({
            "label": t.created_at.strftime("%m/%d") if t.created_at else "",
            "risk_score": t.aggregate_risk_score,
            "task_id": t.task_id,
        })

    return ok({
        "project_id": project_id,
        "task_count": task_count,
        "finding_count": finding_count,
        "s0_count": s0_count,
        "s1_count": s1_count,
        "avg_risk_score": avg_risk_score,
        "modules": modules,
        "recent_tasks": recent_tasks,
        "trends": trends,
    })


@router.get("/projects/{project_id}/findings")
def project_findings(
    project_id: int,
    severity: Optional[str] = None,
    module_id: Optional[str] = None,
    db: Session = Depends(get_db),
) -> dict:
    """项目发现列表 — 仅显示最近一个成功任务的去重发现，支持筛选。"""
    # 取最近一个成功任务（避免跨任务重复）
    latest = (
        db.query(AnalysisTask)
        .filter(AnalysisTask.project_id == project_id, AnalysisTask.status == "success")
        .order_by(desc(AnalysisTask.created_at))
        .first()
    )

    all_findings = []
    if latest:
        for mr in latest.module_results:
            if module_id and mr.module_id != module_id:
                continue
            try:
                findings = json.loads(mr.findings_json) if mr.findings_json else []
                for f in findings:
                    f["task_id"] = latest.task_id
                    f["project_id"] = project_id
                    if severity and f.get("severity") != severity:
                        continue
                    all_findings.append(f)
            except (json.JSONDecodeError, TypeError):
                pass

    # 按 (file_path, line_start, risk_type, module_id) 去重，保留风险最高的
    seen: dict[tuple, dict] = {}
    for f in all_findings:
        key = (f.get("file_path", ""), f.get("line_start", 0), f.get("risk_type", ""), f.get("module_id", ""))
        if key not in seen or f.get("risk_score", 0) > seen[key].get("risk_score", 0):
            seen[key] = f
    deduped = list(seen.values())

    # 按 risk_score 降序排序
    deduped.sort(key=lambda x: x.get("risk_score", 0), reverse=True)

    return ok({"findings": deduped, "total": len(deduped)})


@router.get("/projects/{project_id}/tasks")
def project_tasks(
    project_id: int,
    status: Optional[str] = None,
    task_type: Optional[str] = None,
    db: Session = Depends(get_db),
) -> dict:
    """项目的分析任务列表。"""
    query = db.query(AnalysisTask).filter(AnalysisTask.project_id == project_id)
    if status:
        query = query.filter(AnalysisTask.status == status)
    if task_type:
        query = query.filter(AnalysisTask.task_type == task_type)

    tasks = query.order_by(desc(AnalysisTask.created_at)).all()

    items = []
    for t in tasks:
        results = t.module_results or []
        finished = sum(1 for r in results if r.status in ("success", "failed", "skipped"))
        items.append({
            "task_id": t.task_id,
            "project_id": t.project_id,
            "task_type": t.task_type,
            "status": t.status,
            "aggregate_risk_score": t.aggregate_risk_score,
            "progress": {
                "total_modules": len(results),
                "finished_modules": finished,
                "failed_modules": sum(1 for r in results if r.status == "failed"),
            },
            "created_at": t.created_at.isoformat() if t.created_at else None,
            "updated_at": t.updated_at.isoformat() if t.updated_at else None,
        })

    return ok({"tasks": items, "total": len(items)})


@router.get("/projects/{project_id}/measures")
def project_measures(project_id: int, db: Session = Depends(get_db)) -> dict:
    """项目度量数据（按文件聚合，用于 Treemap）。"""
    tasks = (
        db.query(AnalysisTask)
        .filter(AnalysisTask.project_id == project_id, AnalysisTask.status == "success")
        .order_by(desc(AnalysisTask.created_at))
        .all()
    )

    # 按文件聚合发现（仅最近一个成功任务，避免重复计数）
    file_map = {}  # file_path -> {risk_scores, findings, modules, functions}
    for task in tasks[:1]:  # 仅最近一个成功任务
        for mr in task.module_results:
            try:
                findings = json.loads(mr.findings_json) if mr.findings_json else []
            except (json.JSONDecodeError, TypeError):
                findings = []
            for f in findings:
                fp = f.get("file_path", "unknown")
                if fp not in file_map:
                    file_map[fp] = {"risk_scores": [], "finding_count": 0, "modules": set(), "functions": set()}
                file_map[fp]["risk_scores"].append(f.get("risk_score", 0))
                file_map[fp]["finding_count"] += 1
                file_map[fp]["modules"].add(mr.module_id)
                if f.get("symbol_name"):
                    file_map[fp]["functions"].add(f["symbol_name"])

    files = []
    for fp, data in file_map.items():
        avg_risk = sum(data["risk_scores"]) / len(data["risk_scores"]) if data["risk_scores"] else 0
        files.append({
            "file_path": fp,
            "risk_score": round(avg_risk, 3),
            "finding_count": data["finding_count"],
            "function_count": len(data["functions"]),
            "lines": max(100, data["finding_count"] * 50),  # 近似值
            "modules": list(data["modules"]),
        })

    files.sort(key=lambda x: x["risk_score"], reverse=True)

    return ok({"files": files, "total": len(files)})


def _file_tree_from_findings(db: Session, project_id: int) -> list[dict]:
    """Build file tree from findings of recent tasks."""
    tasks = (
        db.query(AnalysisTask)
        .filter(AnalysisTask.project_id == project_id)
        .order_by(desc(AnalysisTask.created_at))
        .limit(5)
        .all()
    )
    file_findings: dict[str, int] = {}
    for task in tasks:
        for mr in task.module_results:
            try:
                findings = json.loads(mr.findings_json) if mr.findings_json else []
            except (json.JSONDecodeError, TypeError):
                findings = []
            for f in findings:
                fp = f.get("file_path", "")
                if fp:
                    file_findings[fp] = file_findings.get(fp, 0) + 1
    nodes = []
    dirs_seen: set[str] = set()
    for fp in sorted(file_findings.keys()):
        parts = fp.split("/")
        for i in range(1, len(parts)):
            dir_path = "/".join(parts[:i])
            if dir_path not in dirs_seen:
                dirs_seen.add(dir_path)
                nodes.append({
                    "path": dir_path,
                    "name": parts[i - 1],
                    "type": "dir",
                    "depth": i - 1,
                    "finding_count": 0,
                })
        nodes.append({
            "path": fp,
            "name": parts[-1],
            "type": "file",
            "depth": len(parts) - 1,
            "finding_count": file_findings[fp],
        })
    return nodes


def _file_tree_from_repo(repo_root: str, max_depth: int = 8) -> list[dict]:
    """Build file tree by scanning repo directory. Excludes .git, __pycache__, etc."""
    exclude_dirs = {".git", "__pycache__", "node_modules", ".venv", "venv", ".tox"}
    nodes: list[dict] = []
    root = Path(repo_root)
    if not root.is_dir():
        return nodes

    def walk(parent: Path, depth: int, prefix: str) -> None:
        if depth > max_depth:
            return
        try:
            entries = sorted(parent.iterdir())
        except OSError:
            return
        for entry in entries:
            name = entry.name
            if entry.is_dir():
                if name in exclude_dirs:
                    continue
                path = f"{prefix}{name}" if prefix else name
                nodes.append({"path": path, "name": name, "type": "dir", "depth": depth, "finding_count": 0})
                walk(entry, depth + 1, path + "/")
            else:
                path = f"{prefix}{name}" if prefix else name
                nodes.append({"path": path, "name": name, "type": "file", "depth": depth, "finding_count": 0})

    walk(root, 0, "")
    return nodes


@router.get("/projects/{project_id}/file-tree")
def project_file_tree(
    project_id: int,
    source: Optional[str] = Query(default=None, description="findings | repo | both; default: both with repo fallback"),
    db: Session = Depends(get_db),
) -> dict:
    """项目文件树。source=findings 仅来自发现；source=repo 仅来自仓库目录；未指定或 both 时优先发现，空则用仓库兜底。"""
    nodes: list[dict] = []
    if source == "repo":
        repos = db.query(Repository).filter(Repository.project_id == project_id).all()
        for repo in repos:
            if repo.local_mirror_path and os.path.isdir(repo.local_mirror_path):
                nodes = _file_tree_from_repo(repo.local_mirror_path)
                break
        return ok({"files": nodes})

    findings_nodes = _file_tree_from_findings(db, project_id)
    if source == "findings":
        return ok({"files": findings_nodes})

    if findings_nodes:
        return ok({"files": findings_nodes})
    repos = db.query(Repository).filter(Repository.project_id == project_id).all()
    for repo in repos:
        if repo.local_mirror_path and os.path.isdir(repo.local_mirror_path):
            nodes = _file_tree_from_repo(repo.local_mirror_path)
            break
    return ok({"files": nodes})


@router.get("/projects/{project_id}/source")
def project_source(
    project_id: int,
    path: str = Query(...),
    db: Session = Depends(get_db),
) -> dict:
    """获取源文件内容及其关联的发现标注。"""
    # 尝试从仓库本地镜像读取源文件
    repos = db.query(Repository).filter(Repository.project_id == project_id).all()
    content = None
    for repo in repos:
        if not repo.local_mirror_path:
            continue
        full_path = os.path.join(repo.local_mirror_path, path)
        if os.path.isfile(full_path):
            try:
                with open(full_path, "r", encoding="utf-8", errors="replace") as f:
                    content = f.read()
                break
            except OSError:
                pass

    if content is None:
        content = f"// 文件 {path} 未找到于本地仓库镜像中\n// 请确保仓库已同步"

    # 获取该文件的发现
    tasks = (
        db.query(AnalysisTask)
        .filter(AnalysisTask.project_id == project_id)
        .order_by(desc(AnalysisTask.created_at))
        .limit(3)
        .all()
    )
    file_findings = []
    for task in tasks:
        for mr in task.module_results:
            try:
                findings = json.loads(mr.findings_json) if mr.findings_json else []
            except (json.JSONDecodeError, TypeError):
                findings = []
            for f in findings:
                if f.get("file_path") == path:
                    f["task_id"] = task.task_id
                    file_findings.append(f)

    return ok({"content": content, "findings": file_findings, "path": path})


# ═══════════════════════════════════════════════════════════════════════
# 全局发现
# ═══════════════════════════════════════════════════════════════════════


@router.get("/findings")
def global_findings(
    project_id: Optional[int] = None,
    severity: Optional[str] = None,
    module_id: Optional[str] = None,
    risk_type: Optional[str] = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
) -> dict:
    """全局发现查询 — 每个项目仅取最近成功任务的发现，支持多维筛选。"""
    from sqlalchemy import distinct

    # 每个项目仅取最近一个成功任务
    query = db.query(AnalysisTask).filter(AnalysisTask.status == "success")
    if project_id:
        query = query.filter(AnalysisTask.project_id == project_id)

    tasks_all = query.order_by(desc(AnalysisTask.created_at)).all()

    # 按 project_id 去重，仅保留每个项目的最新任务
    seen_projects: set[int] = set()
    latest_tasks = []
    for t in tasks_all:
        if t.project_id not in seen_projects:
            seen_projects.add(t.project_id)
            latest_tasks.append(t)
        if len(latest_tasks) >= 50:
            break

    all_findings = []
    for task in latest_tasks:
        for mr in task.module_results:
            if module_id and mr.module_id != module_id:
                continue
            try:
                findings = json.loads(mr.findings_json) if mr.findings_json else []
                for f in findings:
                    f["task_id"] = task.task_id
                    f["project_id"] = task.project_id
                    if severity and f.get("severity") != severity:
                        continue
                    if risk_type and f.get("risk_type") != risk_type:
                        continue
                    all_findings.append(f)
            except (json.JSONDecodeError, TypeError):
                pass

    # 按 (project_id, file_path, line_start, risk_type, module_id) 去重
    seen: dict[tuple, dict] = {}
    for f in all_findings:
        key = (f.get("project_id", 0), f.get("file_path", ""), f.get("line_start", 0), f.get("risk_type", ""), f.get("module_id", ""))
        if key not in seen or f.get("risk_score", 0) > seen[key].get("risk_score", 0):
            seen[key] = f
    deduped = list(seen.values())

    deduped.sort(key=lambda x: x.get("risk_score", 0), reverse=True)
    total = len(deduped)
    start = (page - 1) * page_size
    paginated = deduped[start : start + page_size]

    return ok({"findings": paginated, "total": total, "page": page, "page_size": page_size})


# ═══════════════════════════════════════════════════════════════════════
# 全局任务列表（增强原有 analysis/tasks）
# ═══════════════════════════════════════════════════════════════════════


@router.get("/analysis/tasks")
def list_all_tasks(
    project_id: Optional[int] = None,
    status: Optional[str] = None,
    task_type: Optional[str] = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
) -> dict:
    """全局任务列表，支持筛选和分页。"""
    query = db.query(AnalysisTask)
    if project_id:
        query = query.filter(AnalysisTask.project_id == project_id)
    if status:
        query = query.filter(AnalysisTask.status == status)
    if task_type:
        query = query.filter(AnalysisTask.task_type == task_type)

    total = query.count()
    tasks = (
        query.order_by(desc(AnalysisTask.created_at))
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    items = []
    for t in tasks:
        results = t.module_results or []
        finished = sum(1 for r in results if r.status in ("success", "failed", "skipped"))
        module_status = {r.module_id: r.status for r in results}
        items.append({
            "task_id": t.task_id,
            "project_id": t.project_id,
            "repo_id": t.repo_id,
            "task_type": t.task_type,
            "status": t.status,
            "aggregate_risk_score": t.aggregate_risk_score,
            "progress": {
                "total_modules": len(results),
                "finished_modules": finished,
                "failed_modules": sum(1 for r in results if r.status == "failed"),
            },
            "module_status": module_status,
            "created_at": t.created_at.isoformat() if t.created_at else None,
            "updated_at": t.updated_at.isoformat() if t.updated_at else None,
        })

    return ok({"tasks": items, "total": total, "page": page, "page_size": page_size})


# ═══════════════════════════════════════════════════════════════════════
# 设置
# ═══════════════════════════════════════════════════════════════════════


@router.get("/settings")
def get_settings() -> dict:
    """获取系统设置。display_timezone 为部署环境时区，前端据此统一展示时间。execution 为测试执行环境（本机 Docker / 远程）。"""
    execution = get_execution_config()
    return ok({
        "quality_gate": {
            "max_risk_score": 60,
            "max_s0_count": 0,
            "max_s1_count": 3,
        },
        "system": {
            "version": "1.0.0",
            "database": "sqlite",
            "deployment": "intranet",
            "display_timezone": getattr(app_settings, "display_timezone", "Asia/Shanghai"),
        },
        "execution": execution,
    })


@router.put("/settings")
def update_settings(body: dict = Body(default_factory=dict)) -> dict:
    """更新系统设置。body 可含 execution（执行环境）、quality_gate 等。"""
    if "execution" in body:
        save_execution_config(body["execution"])
    return ok({"message": "设置已更新"})


# ═══════════════════════════════════════════════════════════════════════
# 测试设计 — 将发现转化为结构化测试用例
# ═══════════════════════════════════════════════════════════════════════


def _collect_findings_for_project(
    project_id: int, db: Session
) -> tuple[list[dict], dict]:
    """收集项目的所有发现和 AI 数据，返回 (all_findings, ai_data)。"""
    tasks = (
        db.query(AnalysisTask)
        .filter(AnalysisTask.project_id == project_id)
        .order_by(desc(AnalysisTask.created_at))
        .all()
    )
    all_findings: list[dict] = []
    ai_data: dict = {}
    seen_ids: set = set()
    for task in tasks:
        for mr in task.module_results:
            try:
                findings = json.loads(mr.findings_json) if mr.findings_json else []
            except (json.JSONDecodeError, TypeError):
                findings = []
            for f in findings:
                fid = f.get("finding_id", "")
                if fid and fid in seen_ids:
                    continue
                seen_ids.add(fid)
                f["task_id"] = task.task_id
                f["project_id"] = project_id
                all_findings.append(f)
            if mr.ai_summary_json:
                try:
                    ai_data[mr.module_id] = json.loads(mr.ai_summary_json)
                except (json.JSONDecodeError, TypeError):
                    pass
    return all_findings, ai_data


@router.get("/projects/{project_id}/test-cases")
def project_test_cases(
    project_id: int,
    priority: Optional[str] = None,
    module_id: Optional[str] = None,
    risk_type: Optional[str] = None,
    persisted: Optional[bool] = Query(default=False, description="若为 true 则返回已持久化的测试用例（可编辑）"),
    incremental: Optional[bool] = Query(default=False, description="true 时仅返回 diff_impact 影响符号相关用例"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
) -> dict:
    """项目级测试用例列表。persisted=true 时返回已持久化记录（含 id，可编辑）。incremental=true 时仅返回受 diff_impact 影响的符号对应用例。"""
    if persisted:
        items, total = get_project_test_cases(
            db, project_id, priority=priority, module_id=module_id, page=page, page_size=page_size
        )
        cases = [_test_case_to_dict(tc, db) for tc in items]
        stats = {"total": total, "by_priority": {}, "by_module": {}}
        for c in cases:
            p = (c.get("priority") or "P3").split("-")[0]
            stats["by_priority"][p] = stats["by_priority"].get(p, 0) + 1
            m = c.get("module_id") or ""
            stats["by_module"][m] = stats["by_module"].get(m, 0) + 1
        return ok({
            "test_cases": cases,
            "total": total,
            "page": page,
            "page_size": page_size,
            "stats": stats,
        })

    all_findings, ai_data = _collect_findings_for_project(project_id, db)
    task_id_for_tc = f"proj-{project_id:04d}"
    affected_symbols = None
    if incremental:
        latest = (
            db.query(AnalysisTask)
            .filter(AnalysisTask.project_id == project_id, AnalysisTask.status == "success")
            .order_by(desc(AnalysisTask.created_at))
            .first()
        )
        if latest and latest.module_results:
            affected_symbols = get_diff_impact_affected_symbols(latest.module_results)
            if not affected_symbols:
                affected_symbols = None
    cases = _findings_to_testcases(
        task_id_for_tc, all_findings, ai_data, affected_symbols=affected_symbols
    )

    if priority:
        cases = [c for c in cases if c["priority"].startswith(priority)]
    if module_id:
        cases = [c for c in cases if c["module_id"] == module_id]
    if risk_type:
        cases = [c for c in cases if c["category"] == risk_type]

    all_cases_for_stats = _findings_to_testcases(task_id_for_tc, all_findings, ai_data) if (priority or module_id or risk_type) else cases
    stats = {
        "total": len(all_cases_for_stats),
        "by_priority": {},
        "by_module": {},
    }
    for c in all_cases_for_stats:
        p = c["priority"].split("-")[0] if "-" in c["priority"] else c["priority"]
        stats["by_priority"][p] = stats["by_priority"].get(p, 0) + 1
        m = c["module_id"]
        stats["by_module"][m] = stats["by_module"].get(m, 0) + 1

    total = len(cases)
    start = (page - 1) * page_size
    paginated = cases[start : start + page_size]

    return ok({
        "test_cases": paginated,
        "total": total,
        "page": page,
        "page_size": page_size,
        "stats": stats,
    })


@router.get("/test-cases")
def global_test_cases(
    project_id: Optional[int] = None,
    priority: Optional[str] = None,
    module_id: Optional[str] = None,
    risk_type: Optional[str] = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
) -> dict:
    """全局测试用例列表 — 跨项目查看测试设计建议。"""
    if project_id:
        project_ids = [project_id]
    else:
        project_ids = [p.id for p in db.query(Project.id).all()]

    all_cases: list[dict] = []
    for pid in project_ids:
        findings, ai_data = _collect_findings_for_project(pid, db)
        task_id_for_tc = f"proj-{pid:04d}"
        cases = _findings_to_testcases(task_id_for_tc, findings, ai_data)
        for c in cases:
            c["project_id"] = pid
        all_cases.extend(cases)

    # 筛选
    if priority:
        all_cases = [c for c in all_cases if c["priority"].startswith(priority)]
    if module_id:
        all_cases = [c for c in all_cases if c["module_id"] == module_id]
    if risk_type:
        all_cases = [c for c in all_cases if c["category"] == risk_type]

    # 按风险分降序
    all_cases.sort(key=lambda x: x.get("risk_score", 0), reverse=True)

    total = len(all_cases)
    start = (page - 1) * page_size
    paginated = all_cases[start : start + page_size]

    return ok({
        "test_cases": paginated,
        "total": total,
        "page": page,
        "page_size": page_size,
    })


@router.get("/findings/{finding_id}/test-suggestion")
def finding_test_suggestion(
    finding_id: str,
    db: Session = Depends(get_db),
) -> dict:
    """为单条发现生成内联测试建议。"""
    # 查找包含该 finding 的模块结果
    results = db.query(AnalysisModuleResult).all()
    target_finding = None
    for mr in results:
        try:
            findings = json.loads(mr.findings_json) if mr.findings_json else []
        except (json.JSONDecodeError, TypeError):
            continue
        for f in findings:
            if f.get("finding_id") == finding_id:
                target_finding = f
                break
        if target_finding:
            break

    if not target_finding:
        return ok({"suggestion": None})

    risk_type = target_finding.get("risk_type", "")
    return ok({
        "suggestion": {
            "finding_id": finding_id,
            "objective": _risk_type_to_objective(risk_type, target_finding),
            "preconditions": _risk_type_to_preconditions(risk_type, target_finding),
            "test_steps": _risk_type_to_steps(risk_type, target_finding),
            "expected_result": _risk_type_to_expected(risk_type, target_finding),
            "priority": _SEV_PRIORITY.get(target_finding.get("severity", "S3"), "P3-低"),
        }
    })


# ═══════════════════════════════════════════════════════════════════════
# 测试用例持久化与管理
# ═══════════════════════════════════════════════════════════════════════


@router.post("/projects/{project_id}/test-cases/generate")
def generate_project_test_cases(
    project_id: int,
    db: Session = Depends(get_db),
) -> dict:
    """为项目的所有成功任务生成并持久化测试用例。"""
    tasks = (
        db.query(AnalysisTask)
        .filter(
            AnalysisTask.project_id == project_id,
            AnalysisTask.status.in_(["success", "partial_failed"]),
        )
        .all()
    )
    total_generated = 0
    for task in tasks:
        count = persist_test_cases(db, task)
        total_generated += count
    return ok({"generated": total_generated, "tasks_processed": len(tasks)})


def _parse_json_list(raw: Optional[str]) -> list:
    """解析 JSON 数组字符串。"""
    if not raw:
        return []
    try:
        out = json.loads(raw)
        return out if isinstance(out, list) else []
    except (json.JSONDecodeError, TypeError):
        return []


def _test_case_to_dict(tc: TestCase, db: Session) -> dict:
    """将 TestCase ORM 转为前端使用的结构。"""
    preconditions = []
    try:
        preconditions = json.loads(tc.preconditions_json) if tc.preconditions_json else []
    except (json.JSONDecodeError, TypeError):
        pass
    steps = []
    try:
        steps = json.loads(tc.steps_json) if tc.steps_json else []
    except (json.JSONDecodeError, TypeError):
        pass
    expected_raw = tc.expected or tc.expected_json or ""
    try:
        if isinstance(expected_raw, str) and expected_raw.startswith("["):
            expected_result = json.loads(expected_raw)
        else:
            expected_result = expected_raw
    except (json.JSONDecodeError, TypeError):
        expected_result = expected_raw
    project_id = None
    task_row = db.query(AnalysisTask).filter(AnalysisTask.id == tc.task_id).first()
    if task_row:
        project_id = task_row.project_id
    return {
        "id": tc.id,
        "test_case_id": tc.case_id,
        "task_id": tc.task_id,
        "project_id": project_id,
        "title": tc.title,
        "priority": tc.priority,
        "category": tc.risk_type,
        "module_id": tc.module_id,
        "module_display_name": get_display_name(tc.module_id) if tc.module_id else "",
        "preconditions": preconditions,
        "test_steps": steps,
        "expected_result": expected_result,
        "objective": tc.objective,
        "status": tc.status,
        "risk_score": tc.risk_score,
        "target_file": tc.file_path,
        "target_function": tc.symbol_name,
        "evidence": {},
        "execution_hint": getattr(tc, "execution_hint", None),
        "example_input": getattr(tc, "example_input", None),
        "expected_failure": getattr(tc, "expected_failure", None),
        "unacceptable_outcomes": _parse_json_list(getattr(tc, "unacceptable_outcomes_json", None)),
        "related_functions": _parse_json_list(getattr(tc, "related_functions_json", None)),
        "execution_type": getattr(tc, "execution_type", None),
        "script_content": getattr(tc, "script_content", None),
    }


@router.get("/test-cases/{test_case_id}/script")
def get_test_case_script(
    test_case_id: int,
    format: str = Query(default="cpp", description="脚本格式: cpp (GTest) 或 python"),
    db: Session = Depends(get_db),
) -> dict:
    """获取测试用例的生成脚本（若无则按当前用例生成）。format=cpp 为 GTest C++，python 为 Python 占位。"""
    from app.services.script_generator import generate_script
    tc = get_test_case_by_id(db, test_case_id)
    if not tc:
        return ok({"script": None})
    d = _test_case_to_dict(tc, db)
    script = getattr(tc, "script_content", None)
    if not script:
        script = generate_script(d, format=format or "cpp")
    return ok({"script": script})


@router.get("/test-cases/template")
def get_test_case_template() -> dict:
    """获取灰盒测试用例 Markdown 模板，供新手下载后按模板填写。"""
    return ok({"markdown": GRAYBOX_TEMPLATE_MD})


@router.get("/test-cases/{test_case_id}")
def get_test_case(
    test_case_id: int,
    db: Session = Depends(get_db),
) -> dict:
    """获取单条测试用例（持久化记录）。"""
    tc = get_test_case_by_id(db, test_case_id)
    if not tc:
        return ok({"test_case": None})
    return ok({"test_case": _test_case_to_dict(tc, db)})


@router.patch("/test-cases/{test_case_id}")
def patch_test_case(
    test_case_id: int,
    body: TestCaseUpdateBody,
    db: Session = Depends(get_db),
) -> dict:
    """更新测试用例（步骤、预期、优先级等）；仅持久化记录可编辑。"""
    tc = update_test_case(
        db,
        test_case_id,
        title=body.title,
        priority=body.priority,
        preconditions=body.preconditions,
        test_steps=body.test_steps,
        expected_result=body.expected_result,
        objective=body.objective,
        execution_hint=body.execution_hint,
        example_input=body.example_input,
        expected_failure=body.expected_failure,
        unacceptable_outcomes=body.unacceptable_outcomes,
        related_functions=body.related_functions,
    )
    if not tc:
        return ok({"error": "测试用例未找到"})
    return ok({"test_case": _test_case_to_dict(tc, db)})


GRAYBOX_TEMPLATE_MD = """# 灰盒测试用例模板

灰盒核心：**精准找到多个函数（或故障处理分支）交汇的临界点**，一次用例暴露黑盒需 N 次才能撞出的问题。
例如：iSCSI login 叠加端口闪断/网卡下电时，预期失败=建联失败，不可接受=控制器下电/进程崩溃。

按下列结构填写每条用例：

---

## 用例 1

- **用例编号**: TC-001
- **优先级**: P0-紧急 / P1-高 / P2-中 / P3-低
- **关联函数（交汇临界点）**: 函数A、函数B、函数C（多个用逗号分隔）
- **测试目标**: （暴露上述多函数交汇时的何种行为）
- **预期结果（可成功或可接受失败）**: 如：按规格成功完成；或建联失败、返回错误码
- **不可接受结果**: 如：控制器下电；进程崩溃；不可恢复状态
- **性能/时序要求**（可选）: 如：响应时间 < 100ms；IO 延迟 < 5ms

### 前置条件
- 条件 1
- 条件 2

### 测试步骤
1. 步骤一
2. 步骤二
3. 步骤三

### 预期结果
- 预期一
- 预期二

### 如何执行
（在什么环境、用什么方式执行）

### 示例数据
（可选）

### 实际结果
（执行后填写：通过 / 失败，及备注）

---

复制上述区块可继续添加用例 2、3……
"""


@router.put("/test-cases/{test_case_id}/status")
def update_tc_status(
    test_case_id: int,
    status: str = Query(..., description="新状态: pending/adopted/ignored/executed"),
    db: Session = Depends(get_db),
) -> dict:
    """更新测试用例状态。"""
    tc = update_test_case_status(db, test_case_id, status)
    if not tc:
        return ok({"error": "测试用例未找到或状态无效"})
    return ok({"id": tc.id, "case_id": tc.case_id, "status": tc.status})
