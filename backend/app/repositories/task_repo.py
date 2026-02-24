"""Data access for analysis_tasks and analysis_module_results."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from sqlalchemy import func, select, delete as sa_delete
from sqlalchemy.orm import Session

from app.models.analysis_task import AnalysisTask
from app.models.module_result import AnalysisModuleResult
from app.models.risk_finding import RiskFinding
from app.models.test_case import TestCase
from app.models.export import Export
from app.models.coverage_import import CoverageImport
from app.models.audit_event import AuditEvent


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
    pillar: str | None = None,
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
        pillar=pillar,
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


def update_task_mr(db: Session, task_id: str, mr_url: str | None = None, mr_diff: list | None = None) -> AnalysisTask | None:
    """更新任务的 MR 链接与代码变更（合并到 options_json）。"""
    obj = get_task_by_id(db, task_id)
    if obj is None:
        return None
    options = {}
    if obj.options_json:
        try:
            options = json.loads(obj.options_json)
        except (TypeError, json.JSONDecodeError):
            pass
    if mr_url is not None:
        options["mr_url"] = mr_url
    if mr_diff is not None:
        options["mr_diff"] = mr_diff
    obj.options_json = json.dumps(options, ensure_ascii=False)
    obj.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(obj)
    return obj


def delete_preview(db: Session, task_pks: list[int]) -> dict:
    """Return counts of related records that will be affected by deleting the given tasks."""
    finding_count = db.query(func.count(RiskFinding.id)).filter(
        RiskFinding.task_id.in_(task_pks)
    ).scalar() or 0
    testcase_count = db.query(func.count(TestCase.id)).filter(
        TestCase.task_id.in_(task_pks)
    ).scalar() or 0
    module_count = db.query(func.count(AnalysisModuleResult.id)).filter(
        AnalysisModuleResult.task_id.in_(task_pks)
    ).scalar() or 0
    export_count = db.query(func.count(Export.id)).filter(
        Export.task_id.in_(task_pks)
    ).scalar() or 0
    return {
        "task_count": len(task_pks),
        "finding_count": finding_count,
        "testcase_count": testcase_count,
        "module_result_count": module_count,
        "export_count": export_count,
    }


def delete_task_cascade(db: Session, task_pk: int) -> dict:
    """Delete a task and all related records. Returns counts of deleted rows."""
    counts = delete_preview(db, [task_pk])
    db.execute(sa_delete(RiskFinding).where(RiskFinding.task_id == task_pk))
    db.execute(sa_delete(TestCase).where(TestCase.task_id == task_pk))
    db.execute(sa_delete(Export).where(Export.task_id == task_pk))
    db.execute(sa_delete(CoverageImport).where(CoverageImport.task_id == task_pk))
    db.execute(sa_delete(AnalysisModuleResult).where(AnalysisModuleResult.task_id == task_pk))
    db.query(AuditEvent).filter(AuditEvent.task_id == task_pk).update(
        {AuditEvent.task_id: None}, synchronize_session=False
    )
    db.execute(sa_delete(AnalysisTask).where(AnalysisTask.id == task_pk))
    db.commit()
    return counts


def delete_tasks_batch(db: Session, task_pks: list[int]) -> dict:
    """Delete multiple tasks and all related records. Returns counts of deleted rows."""
    if not task_pks:
        return {"task_count": 0, "finding_count": 0, "testcase_count": 0,
                "module_result_count": 0, "export_count": 0}
    counts = delete_preview(db, task_pks)
    db.execute(sa_delete(RiskFinding).where(RiskFinding.task_id.in_(task_pks)))
    db.execute(sa_delete(TestCase).where(TestCase.task_id.in_(task_pks)))
    db.execute(sa_delete(Export).where(Export.task_id.in_(task_pks)))
    db.execute(sa_delete(CoverageImport).where(CoverageImport.task_id.in_(task_pks)))
    db.execute(sa_delete(AnalysisModuleResult).where(AnalysisModuleResult.task_id.in_(task_pks)))
    db.query(AuditEvent).filter(AuditEvent.task_id.in_(task_pks)).update(
        {AuditEvent.task_id: None}, synchronize_session=False
    )
    db.execute(sa_delete(AnalysisTask).where(AnalysisTask.id.in_(task_pks)))
    db.commit()
    return counts


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
