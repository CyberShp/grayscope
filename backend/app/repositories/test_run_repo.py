"""TestRun 与 TestExecution 数据访问。"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.test_execution import TestExecution
from app.models.test_run import TestRun
from app.models.test_case import TestCase


def create_test_run(
    db: Session,
    *,
    task_id: int | None = None,
    project_id: int | None = None,
    environment: str = "docker",
    test_case_ids: list[int] | None = None,
    name: str | None = None,
    docker_image: str | None = None,
) -> TestRun:
    run = TestRun(
        task_id=task_id,
        project_id=project_id,
        status="pending",
        environment=environment,
        total=len(test_case_ids) if test_case_ids else 0,
        name=name,
        docker_image=docker_image,
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    if test_case_ids:
        for tc_id in test_case_ids:
            tc = db.get(TestCase, tc_id)
            task_id_val = (tc.task_id if tc else None) or run.task_id or 0
            ex = TestExecution(
                test_run_id=run.id,
                task_id=task_id_val,
                test_case_id=tc_id,
                status="pending",
            )
            db.add(ex)
        db.commit()
        db.refresh(run)
    return run


def get_run_by_id(db: Session, run_id: str) -> TestRun | None:
    return db.scalars(
        select(TestRun).where(TestRun.run_id == run_id)
    ).first()


def get_run_by_pk(db: Session, pk: int) -> TestRun | None:
    return db.get(TestRun, pk)


def list_test_runs(
    db: Session,
    project_id: int | None = None,
    task_id: int | None = None,
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[TestRun]:
    q = select(TestRun).order_by(TestRun.created_at.desc())
    if project_id is not None:
        q = q.where(TestRun.project_id == project_id)
    if task_id is not None:
        q = q.where(TestRun.task_id == task_id)
    if status:
        q = q.where(TestRun.status == status)
    q = q.offset(offset).limit(limit)
    return list(db.scalars(q).all())


def list_executions_for_run(db: Session, test_run_id: int) -> list[TestExecution]:
    return list(
        db.scalars(
            select(TestExecution)
            .where(TestExecution.test_run_id == test_run_id)
            .order_by(TestExecution.id)
        ).all()
    )


def list_executions_for_case(db: Session, test_case_id: int, limit: int = 20) -> list[TestExecution]:
    return list(
        db.scalars(
            select(TestExecution)
            .where(TestExecution.test_case_id == test_case_id)
            .order_by(TestExecution.created_at.desc())
            .limit(limit)
        ).all()
    )


def update_run_status(
    db: Session,
    run_id: str,
    status: str,
    *,
    total: int | None = None,
    passed: int | None = None,
    failed: int | None = None,
    skipped: int | None = None,
    coverage_delta_json: str | None = None,
    started_at: datetime | None = None,
    finished_at: datetime | None = None,
) -> TestRun | None:
    run = get_run_by_id(db, run_id)
    if not run:
        return None
    run.status = status
    if total is not None:
        run.total = total
    if passed is not None:
        run.passed = passed
    if failed is not None:
        run.failed = failed
    if skipped is not None:
        run.skipped = skipped
    if coverage_delta_json is not None:
        run.coverage_delta_json = coverage_delta_json
    if started_at is not None:
        run.started_at = started_at
    if finished_at is not None:
        run.finished_at = finished_at
    db.commit()
    db.refresh(run)
    return run


def delete_test_run(db: Session, run_id: str) -> bool:
    """删除测试运行及其所有执行记录。"""
    run = get_run_by_id(db, run_id)
    if not run:
        return False
    for ex in list_executions_for_run(db, run.id):
        db.delete(ex)
    db.delete(run)
    db.commit()
    return True


def update_execution_result(
    db: Session,
    execution_id: int,
    *,
    status: str,
    execution_status: str | None = None,
    result_json: str | None = None,
    started_at: datetime | None = None,
    finished_at: datetime | None = None,
) -> TestExecution | None:
    ex = db.get(TestExecution, execution_id)
    if not ex:
        return None
    ex.status = status
    if execution_status is not None:
        ex.execution_status = execution_status
    if result_json is not None:
        ex.result_json = result_json
    if started_at is not None:
        ex.started_at = started_at
    if finished_at is not None:
        ex.finished_at = finished_at
    db.commit()
    db.refresh(ex)
    return ex


def reset_run_for_rerun(db: Session, run_id: str) -> TestRun | None:
    """将已结束的运行重置为 pending，清空统计与每条执行结果，便于重新运行。"""
    run = get_run_by_id(db, run_id)
    if not run:
        return None
    if run.status not in ("success", "failed", "cancelled"):
        return None
    run.status = "pending"
    run.passed = 0
    run.failed = 0
    run.skipped = 0
    run.started_at = None
    run.finished_at = None
    for ex in list_executions_for_run(db, run.id):
        ex.status = "pending"
        ex.execution_status = None
        ex.result_json = None
        ex.started_at = None
        ex.finished_at = None
    db.commit()
    db.refresh(run)
    return run
