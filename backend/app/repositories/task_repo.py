"""Data access for analysis_tasks and analysis_module_results."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.analysis_task import AnalysisTask
from app.models.module_result import AnalysisModuleResult


# ---------- task CRUD ----------


def create_task(
    db: Session,
    *,
    task_id: str,
    project_id: int,
    repo_id: int,
    task_type: str,
    target: dict,
    revision: dict,
    analyzers: list[str],
    ai: dict,
    options: dict | None = None,
    idempotency_key: str | None = None,
) -> AnalysisTask:
    obj = AnalysisTask(
        task_id=task_id,
        project_id=project_id,
        repo_id=repo_id,
        task_type=task_type,
        status="pending",
        target_json=json.dumps(target),
        revision_json=json.dumps(revision),
        analyzers_json=json.dumps(analyzers),
        ai_json=json.dumps(ai),
        options_json=json.dumps(options) if options else None,
        idempotency_key=idempotency_key,
    )
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


def get_task_by_id(db: Session, task_id: str) -> AnalysisTask | None:
    return db.scalars(
        select(AnalysisTask).where(AnalysisTask.task_id == task_id)
    ).first()


def get_task_by_idempotency_key(db: Session, key: str) -> AnalysisTask | None:
    return db.scalars(
        select(AnalysisTask).where(AnalysisTask.idempotency_key == key)
    ).first()


def update_task_status(
    db: Session, task_id: str, status: str, error: dict | None = None
) -> AnalysisTask | None:
    obj = get_task_by_id(db, task_id)
    if obj is None:
        return None
    obj.status = status
    obj.updated_at = datetime.now(timezone.utc)
    if status in ("success", "failed", "cancelled"):
        obj.finished_at = datetime.now(timezone.utc)
    if error is not None:
        obj.error_json = json.dumps(error)
    db.commit()
    db.refresh(obj)
    return obj


def set_aggregate_score(db: Session, task_id: str, score: float) -> None:
    obj = get_task_by_id(db, task_id)
    if obj:
        obj.aggregate_risk_score = score
        db.commit()


def set_cross_module_ai(db: Session, task_id: str, ai_json: str) -> None:
    """保存跨模块 AI 综合分析结果到任务的扩展 JSON 字段。"""
    import json as _json
    obj = get_task_by_id(db, task_id)
    if obj:
        # 存到 error_json 中作为扩展数据（不影响错误语义，用 key 区分）
        existing = {}
        if obj.error_json:
            try:
                existing = _json.loads(obj.error_json)
            except Exception:
                existing = {"_original": obj.error_json}
        existing["cross_module_ai"] = _json.loads(ai_json) if isinstance(ai_json, str) else ai_json
        obj.error_json = _json.dumps(existing, ensure_ascii=False, default=str)
        db.commit()


# ---------- module result CRUD ----------


def create_module_result(
    db: Session,
    *,
    task_pk: int,
    module_id: str,
    status: str = "pending",
) -> AnalysisModuleResult:
    obj = AnalysisModuleResult(
        task_id=task_pk,
        module_id=module_id,
        status=status,
        findings_json="[]",
    )
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


def get_module_results(db: Session, task_pk: int) -> list[AnalysisModuleResult]:
    return list(
        db.scalars(
            select(AnalysisModuleResult)
            .where(AnalysisModuleResult.task_id == task_pk)
            .order_by(AnalysisModuleResult.module_id)
        ).all()
    )


def update_module_result(
    db: Session,
    result_id: int,
    *,
    status: str,
    risk_score: float | None = None,
    findings_json: str | None = None,
    metrics_json: str | None = None,
    artifacts_json: str | None = None,
    ai_summary_json: str | None = None,
    error_json: str | None = None,
) -> AnalysisModuleResult | None:
    obj = db.get(AnalysisModuleResult, result_id)
    if obj is None:
        return None
    obj.status = status
    obj.updated_at = datetime.now(timezone.utc)
    if risk_score is not None:
        obj.risk_score = risk_score
    if findings_json is not None:
        obj.findings_json = findings_json
    if metrics_json is not None:
        obj.metrics_json = metrics_json
    if artifacts_json is not None:
        obj.artifacts_json = artifacts_json
    if ai_summary_json is not None:
        obj.ai_summary_json = ai_summary_json
    if error_json is not None:
        obj.error_json = error_json
    if status in ("success", "failed", "skipped", "cancelled"):
        obj.finished_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(obj)
    return obj
