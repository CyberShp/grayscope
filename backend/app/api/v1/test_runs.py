"""测试运行 API：创建运行、列表、详情、触发执行、用例执行历史。"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, Query
from pydantic import BaseModel, Field

from app.core.database import get_db, SessionLocal
from app.core.response import ok
from app.repositories.test_run_repo import (
    create_test_run,
    get_run_by_id,
    list_test_runs,
    list_executions_for_run,
    list_executions_for_case,
    update_run_status,
    delete_test_run,
    reset_run_for_rerun,
)
from app.services.execution_runner import run_test_run_sync
from sqlalchemy.orm import Session

router = APIRouter()


class TestRunCreateBody(BaseModel):
    """创建测试运行请求。"""
    task_id: Optional[int] = Field(default=None, description="关联分析任务 PK (analysis_tasks.id)")
    project_id: Optional[int] = Field(default=None, description="项目 ID")
    environment: str = Field(default="docker", description="执行环境: docker | ssh")
    test_case_ids: Optional[list[int]] = Field(default=None, description="要执行的测试用例 ID 列表")
    name: Optional[str] = Field(default=None, description="自定义运行名称")
    docker_image: Optional[str] = Field(default=None, description="指定 Docker 镜像，如 ubuntu:22.04")


def _run_to_dict(run) -> dict:
    return {
        "id": run.id,
        "run_id": run.run_id,
        "task_id": run.task_id,
        "project_id": run.project_id,
        "status": run.status,
        "environment": run.environment,
        "name": getattr(run, "name", None),
        "docker_image": getattr(run, "docker_image", None),
        "total": run.total,
        "passed": run.passed,
        "failed": run.failed,
        "skipped": run.skipped,
        "coverage_delta": json.loads(run.coverage_delta_json) if run.coverage_delta_json else None,
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "finished_at": run.finished_at.isoformat() if run.finished_at else None,
        "created_at": run.created_at.isoformat() if run.created_at else None,
    }


def _execution_to_dict(ex) -> dict:
    return {
        "id": ex.id,
        "test_run_id": ex.test_run_id,
        "test_case_id": ex.test_case_id,
        "status": ex.status,
        "execution_status": ex.execution_status,
        "result": json.loads(ex.result_json) if ex.result_json else None,
        "started_at": ex.started_at.isoformat() if ex.started_at else None,
        "finished_at": ex.finished_at.isoformat() if ex.finished_at else None,
        "created_at": ex.created_at.isoformat() if ex.created_at else None,
    }


@router.post("/test-runs")
def create_run(
    body: TestRunCreateBody,
    db: Session = Depends(get_db),
) -> dict:
    """创建测试运行（选择用例、执行环境）。"""
    run = create_test_run(
        db,
        task_id=body.task_id,
        project_id=body.project_id,
        environment=body.environment or "docker",
        test_case_ids=body.test_case_ids,
        name=body.name,
        docker_image=body.docker_image,
    )
    return ok(_run_to_dict(run))


@router.get("/test-runs")
def list_runs(
    project_id: Optional[int] = Query(default=None),
    task_id: Optional[int] = Query(default=None),
    status: Optional[str] = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
) -> dict:
    """测试运行列表（含状态、通过率、覆盖率增量）。"""
    offset = (page - 1) * page_size
    runs = list_test_runs(
        db,
        project_id=project_id,
        task_id=task_id,
        status=status,
        limit=page_size,
        offset=offset,
    )
    items = [_run_to_dict(r) for r in runs]
    return ok({
        "test_runs": items,
        "page": page,
        "page_size": page_size,
    })


@router.get("/test-runs/trend")
def test_runs_trend(
    project_id: Optional[int] = Query(default=None),
    limit: int = Query(default=10, ge=1, le=50),
    db: Session = Depends(get_db),
) -> dict:
    """最近测试运行的通过/失败趋势，供前端图表展示。"""
    runs = list_test_runs(
        db, project_id=project_id, limit=limit, offset=0,
    )
    trend = [
        {
            "run_id": r.run_id,
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "passed": r.passed,
            "failed": r.failed,
            "skipped": r.skipped,
            "total": r.total,
            "status": r.status,
        }
        for r in runs
    ]
    return ok({"trend": trend})


@router.get("/test-runs/{run_id}")
def get_run_detail(
    run_id: str,
    db: Session = Depends(get_db),
) -> dict:
    """测试运行详情（每条用例的 pass/fail/error + 输出日志），含用例编号与名称。"""
    from app.models.test_case import TestCase
    run = get_run_by_id(db, run_id)
    if not run:
        return ok({"test_run": None})
    executions = list_executions_for_run(db, run.id)
    out = []
    for e in executions:
        d = _execution_to_dict(e)
        if e.test_case_id:
            tc = db.get(TestCase, e.test_case_id)
            if tc:
                d["case_id"] = getattr(tc, "case_id", None) or f"TC-{e.test_case_id}"
                d["title"] = getattr(tc, "title", None) or ""
        else:
            d["case_id"] = f"TC-{e.test_case_id}"
            d["title"] = ""
        out.append(d)
    return ok({
        "test_run": _run_to_dict(run),
        "executions": out,
    })


@router.post("/test-runs/{run_id}/execute")
def trigger_execute(
    run_id: str,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
) -> dict:
    """触发执行：pending 为启动，paused 为恢复；根据设置调用本机 Docker 或远程容器。"""
    run = get_run_by_id(db, run_id)
    if not run:
        return ok({"ok": False, "message": "运行不存在"})
    if run.status == "running":
        return ok({"ok": False, "message": "已在执行中"})
    if run.status not in ("pending", "paused"):
        return ok({"ok": False, "message": f"当前状态 {run.status} 不可执行"})
    update_run_status(db, run_id, "running")
    run = get_run_by_id(db, run_id)

    def run_in_background():
        db_session = SessionLocal()
        try:
            run_test_run_sync(run_id, db_session)
        finally:
            db_session.close()

    background_tasks.add_task(run_in_background)
    return ok({
        "ok": True,
        "run_id": run_id,
        "status": run.status,
        "message": "已加入执行队列；将根据「设置 - 执行环境」调用本机 Docker 或远程容器",
    })


@router.post("/test-runs/{run_id}/rerun")
def rerun_run(
    run_id: str,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
) -> dict:
    """重新运行：仅当状态为 success / failed / cancelled 时可用；重置为 pending 后立即加入执行队列。"""
    run = reset_run_for_rerun(db, run_id)
    if not run:
        existing = get_run_by_id(db, run_id)
        if not existing:
            return ok({"ok": False, "message": "运行不存在"})
        return ok({"ok": False, "message": f"仅已结束的运行可重新运行，当前状态: {existing.status}"})
    update_run_status(db, run_id, "running")
    run = get_run_by_id(db, run_id)

    def run_in_background():
        db_session = SessionLocal()
        try:
            run_test_run_sync(run_id, db_session)
        finally:
            db_session.close()

    background_tasks.add_task(run_in_background)
    return ok({
        "ok": True,
        "run_id": run_id,
        "status": "running",
        "message": "已重置并加入执行队列",
    })


@router.post("/test-runs/{run_id}/pause")
def pause_run(run_id: str, db: Session = Depends(get_db)) -> dict:
    """暂停运行（仅 running 可暂停）。"""
    run = get_run_by_id(db, run_id)
    if not run:
        return ok({"ok": False, "message": "运行不存在"})
    if run.status != "running":
        return ok({"ok": False, "message": f"仅运行中可暂停，当前状态: {run.status}"})
    update_run_status(db, run_id, "paused")
    return ok({"ok": True, "run_id": run_id, "status": "paused", "message": "已暂停"})


@router.post("/test-runs/{run_id}/cancel")
def cancel_run(run_id: str, db: Session = Depends(get_db)) -> dict:
    """强制停止运行（running 或 paused 可停止）。"""
    run = get_run_by_id(db, run_id)
    if not run:
        return ok({"ok": False, "message": "运行不存在"})
    if run.status not in ("running", "paused"):
        return ok({"ok": False, "message": f"仅运行中/已暂停可停止，当前状态: {run.status}"})
    update_run_status(db, run_id, "cancelled", finished_at=datetime.now(timezone.utc))
    return ok({"ok": True, "run_id": run_id, "status": "cancelled", "message": "已强制停止"})


@router.delete("/test-runs/{run_id}")
def delete_run(run_id: str, db: Session = Depends(get_db)) -> dict:
    """删除测试运行及其所有执行记录。"""
    if not delete_test_run(db, run_id):
        return ok({"ok": False, "message": "运行不存在"})
    return ok({"ok": True, "run_id": run_id, "message": "已删除"})


@router.get("/test-cases/{test_case_id}/executions")
def get_case_executions(
    test_case_id: int,
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
) -> dict:
    """某用例的执行历史。"""
    executions = list_executions_for_case(db, test_case_id, limit=limit)
    return ok({
        "test_case_id": test_case_id,
        "executions": [_execution_to_dict(e) for e in executions],
    })
