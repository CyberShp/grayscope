"""任务生命周期管理，包含状态机强制约束。"""

from __future__ import annotations

import json
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.analyzers.registry import get_display_name
from app.core.exceptions import (
    InvalidRequestError,
    NotFoundError,
    TaskNotFoundError,
    TaskStateInvalidError,
)
from app.models.analysis_task import AnalysisTask
from app.models.module_result import AnalysisModuleResult
from app.repositories import task_repo
from app.schemas.analysis import (
    SUPPORTED_MODULES,
    ModuleResultSummary,
    RetryRequest,
    TaskCreateOut,
    TaskCreateRequest,
    TaskProgress,
    TaskResultsOut,
    TaskStatusOut,
)
from app.utils.id_gen import task_id as gen_task_id


# ── 创建任务 ──────────────────────────────────────────────────────────


def create_task(db: Session, req: TaskCreateRequest) -> TaskCreateOut:
    """创建新的分析任务。"""
    # 幂等性保护
    if req.idempotency_key:
        existing = task_repo.get_task_by_idempotency_key(db, req.idempotency_key)
        if existing:
            return TaskCreateOut(
                task_id=existing.task_id,
                status=existing.status,
                created_at=existing.created_at,
            )

    # 验证分析器模块
    invalid = set(req.analyzers) - SUPPORTED_MODULES
    if invalid:
        raise InvalidRequestError(f"不支持的分析器模块: {invalid}")

    # 差异分析验证
    if req.task_type == "diff":
        if not req.revision.base_commit or not req.revision.head_commit:
            raise InvalidRequestError(
                "差异分析任务需要同时指定 base_commit 和 head_commit"
            )

    tid = gen_task_id()
    options_dict = req.options.model_dump()
    pillar = getattr(req.options, "pillar", None) or options_dict.get("pillar")
    task = task_repo.create_task(
        db,
        task_id=tid,
        project_id=req.project_id,
        repo_id=req.repo_id,
        task_type=req.task_type,
        target=req.target.model_dump(),
        revision=req.revision.model_dump(),
        analyzers=req.analyzers,
        ai=req.ai.model_dump(),
        options=options_dict,
        idempotency_key=req.idempotency_key,
        pillar=pillar,
    )

    # 预创建模块结果记录（初始状态为 pending）
    for mod in req.analyzers:
        task_repo.create_module_result(db, task_pk=task.id, module_id=mod)

    return TaskCreateOut(
        task_id=task.task_id,
        status=task.status,
        created_at=task.created_at,
    )


# ── 查询 ──────────────────────────────────────────────────────────────


def get_task_status(db: Session, task_id: str) -> TaskStatusOut:
    """查询任务当前状态。"""
    task = task_repo.get_task_by_id(db, task_id)
    if task is None:
        raise TaskNotFoundError(f"任务 {task_id} 未找到")

    results = task_repo.get_module_results(db, task.id)
    module_status = {r.module_id: r.status for r in results}
    finished = sum(1 for r in results if r.status in ("success", "failed", "skipped"))
    failed = sum(1 for r in results if r.status == "failed")

    options_dict = None
    if task.options_json:
        try:
            options_dict = json.loads(task.options_json)
        except (TypeError, json.JSONDecodeError):
            pass

    return TaskStatusOut(
        task_id=task.task_id,
        project_id=task.project_id,
        repo_id=task.repo_id,
        task_type=task.task_type,
        status=task.status,
        progress=TaskProgress(
            total_modules=len(results),
            finished_modules=finished,
            failed_modules=failed,
        ),
        module_status=module_status,
        created_at=task.created_at,
        updated_at=task.updated_at,
        error_json=task.error_json,
        options=options_dict,
        pillar=getattr(task, "pillar", None),
    )


def get_task_results(db: Session, task_id: str) -> TaskResultsOut:
    """查询任务的详细分析结果。"""
    task = task_repo.get_task_by_id(db, task_id)
    if task is None:
        raise TaskNotFoundError(f"任务 {task_id} 未找到")

    results = task_repo.get_module_results(db, task.id)
    modules = []
    for r in results:
        findings = json.loads(r.findings_json) if r.findings_json else []
        artifacts = json.loads(r.artifacts_json) if r.artifacts_json else []
        modules.append(
            ModuleResultSummary(
                module=r.module_id,
                display_name=get_display_name(r.module_id),
                status=r.status,
                risk_score=r.risk_score,
                finding_count=len(findings),
                artifact_paths=[a.get("path", "") for a in artifacts]
                if isinstance(artifacts, list)
                else [],
            )
        )

    return TaskResultsOut(
        task_id=task.task_id,
        project_id=task.project_id,
        repo_id=task.repo_id,
        status=task.status,
        aggregate_risk_score=task.aggregate_risk_score,
        modules=modules,
    )


# ── 状态转换 ──────────────────────────────────────────────────────────


def retry_task(db: Session, task_id: str, req: RetryRequest) -> TaskStatusOut:
    """重试失败的分析模块。"""
    task = task_repo.get_task_by_id(db, task_id)
    if task is None:
        raise TaskNotFoundError(f"任务 {task_id} 未找到")
    if task.status not in AnalysisTask.RETRYABLE_STATUSES:
        raise TaskStateInvalidError(
            f"任务状态 '{task.status}' 不允许重试"
        )

    results = task_repo.get_module_results(db, task.id)
    targets = req.modules if req.modules else [r.module_id for r in results if r.status == "failed"]
    for r in results:
        if r.module_id in targets:
            task_repo.update_module_result(db, r.id, status="pending")

    task_repo.update_task_status(db, task_id, "running")
    return get_task_status(db, task_id)


def cancel_task(db: Session, task_id: str) -> TaskStatusOut:
    """取消分析任务。"""
    task = task_repo.get_task_by_id(db, task_id)
    if task is None:
        raise TaskNotFoundError(f"任务 {task_id} 未找到")
    if task.status not in AnalysisTask.CANCELLABLE_STATUSES:
        raise TaskStateInvalidError(
            f"任务状态 '{task.status}' 不允许取消"
        )
    task_repo.update_task_status(db, task_id, "cancelled")
    return get_task_status(db, task_id)
