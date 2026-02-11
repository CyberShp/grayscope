"""聚合数据 API 端点 — 为新版前端提供项目概览、发现列表、度量、测试设计等聚合数据。"""

from __future__ import annotations

import json
import os
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, desc
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.response import ok
from app.models.analysis_task import AnalysisTask
from app.models.module_result import AnalysisModuleResult
from app.models.project import Project
from app.models.repository import Repository
from app.analyzers.registry import get_display_name
from app.services.export_service import (
    _findings_to_testcases,
    _risk_type_to_objective,
    _risk_type_to_preconditions,
    _risk_type_to_steps,
    _risk_type_to_expected,
    _SEV_PRIORITY,
)
from app.services.testcase_service import (
    persist_test_cases,
    get_project_test_cases,
    update_test_case_status,
)

router = APIRouter()


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

    # 所有发现
    all_findings = []
    module_results_all = []
    for task in tasks:
        for mr in task.module_results:
            module_results_all.append(mr)
            try:
                findings = json.loads(mr.findings_json) if mr.findings_json else []
                for f in findings:
                    f["task_id"] = task.task_id
                    f["project_id"] = project_id
                all_findings.extend(findings)
            except (json.JSONDecodeError, TypeError):
                pass

    finding_count = len(all_findings)
    s0_count = sum(1 for f in all_findings if f.get("severity") == "S0")
    s1_count = sum(1 for f in all_findings if f.get("severity") == "S1")

    # 平均风险评分（基于最近一个成功任务）
    latest_success = next(
        (t for t in tasks if t.status == "success" and t.aggregate_risk_score is not None),
        None,
    )
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
    """项目所有发现列表，支持筛选。"""
    tasks = (
        db.query(AnalysisTask)
        .filter(AnalysisTask.project_id == project_id)
        .all()
    )

    all_findings = []
    for task in tasks:
        for mr in task.module_results:
            if module_id and mr.module_id != module_id:
                continue
            try:
                findings = json.loads(mr.findings_json) if mr.findings_json else []
                for f in findings:
                    f["task_id"] = task.task_id
                    f["project_id"] = project_id
                    if severity and f.get("severity") != severity:
                        continue
                    all_findings.append(f)
            except (json.JSONDecodeError, TypeError):
                pass

    # 按 risk_score 降序排序
    all_findings.sort(key=lambda x: x.get("risk_score", 0), reverse=True)

    return ok({"findings": all_findings, "total": len(all_findings)})


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

    # 按文件聚合发现
    file_map = {}  # file_path -> {risk_scores, findings, modules, functions}
    for task in tasks[:3]:  # 最近 3 个成功任务
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


@router.get("/projects/{project_id}/file-tree")
def project_file_tree(project_id: int, db: Session = Depends(get_db)) -> dict:
    """项目文件树（基于分析发现中的文件路径构建）。"""
    tasks = (
        db.query(AnalysisTask)
        .filter(AnalysisTask.project_id == project_id)
        .order_by(desc(AnalysisTask.created_at))
        .limit(5)
        .all()
    )

    file_findings = {}  # file_path -> finding_count
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

    # 构建扁平化文件列表（含目录）
    nodes = []
    dirs_seen = set()
    for fp in sorted(file_findings.keys()):
        parts = fp.split("/")
        # 添加目录节点
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
        # 文件节点
        nodes.append({
            "path": fp,
            "name": parts[-1],
            "type": "file",
            "depth": len(parts) - 1,
            "finding_count": file_findings[fp],
        })

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
    """全局发现查询，支持多维筛选。"""
    query = db.query(AnalysisTask)
    if project_id:
        query = query.filter(AnalysisTask.project_id == project_id)

    tasks = query.order_by(desc(AnalysisTask.created_at)).limit(50).all()

    all_findings = []
    for task in tasks:
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

    all_findings.sort(key=lambda x: x.get("risk_score", 0), reverse=True)
    total = len(all_findings)
    start = (page - 1) * page_size
    paginated = all_findings[start : start + page_size]

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
    """获取系统设置。"""
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
        },
    })


@router.put("/settings")
def update_settings() -> dict:
    """更新系统设置（占位）。"""
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
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
) -> dict:
    """项目级测试用例列表 — 将风险发现转化为结构化测试设计建议。"""
    all_findings, ai_data = _collect_findings_for_project(project_id, db)

    # 使用 export_service 中已有的转换逻辑
    task_id_for_tc = f"proj-{project_id:04d}"
    cases = _findings_to_testcases(task_id_for_tc, all_findings, ai_data)

    # 筛选
    if priority:
        cases = [c for c in cases if c["priority"].startswith(priority)]
    if module_id:
        cases = [c for c in cases if c["module_id"] == module_id]
    if risk_type:
        cases = [c for c in cases if c["category"] == risk_type]

    # 统计
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
