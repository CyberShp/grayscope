"""分析任务 API 端点。"""

from fastapi import APIRouter, Depends, Query
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session
from starlette.status import HTTP_201_CREATED, HTTP_202_ACCEPTED

from app.core.database import get_db
from app.core.response import ok
from app.schemas.analysis import RetryRequest, TaskCreateRequest
from app.services import analysis_orchestrator, export_service, task_service

router = APIRouter()


@router.post("/analysis/tasks", status_code=HTTP_201_CREATED)
def create_task(req: TaskCreateRequest, db: Session = Depends(get_db)) -> dict:
    """创建并执行分析任务。"""
    out = task_service.create_task(db, req)
    # 同步执行编排（后续可切换为 Celery 异步）
    analysis_orchestrator.run_task(db, out.task_id)
    refreshed = task_service.get_task_status(db, out.task_id)
    return ok(refreshed.model_dump(), message="任务已创建")


@router.get("/analysis/tasks/{task_id}")
def get_task(task_id: str, db: Session = Depends(get_db)) -> dict:
    """查询任务状态。"""
    out = task_service.get_task_status(db, task_id)
    return ok(out.model_dump())


@router.get("/analysis/tasks/{task_id}/results")
def get_results(task_id: str, db: Session = Depends(get_db)) -> dict:
    """查询任务分析结果。"""
    out = task_service.get_task_results(db, task_id)
    return ok(out.model_dump())


@router.get("/analysis/tasks/{task_id}/export")
def export_task(
    task_id: str,
    fmt: str = Query("json", pattern="^(json|csv|findings)$"),
    db: Session = Depends(get_db),
):
    """导出分析结果为结构化测试用例。

    格式选项：
    - json：结构化测试用例建议（JSON）
    - csv：测试用例表（CSV，可导入测试管理工具）
    - findings：原始发现及 AI 增强数据（JSON）
    """
    if fmt == "csv":
        content = export_service.export_csv(db, task_id)
        return PlainTextResponse(
            content,
            media_type="text/csv",
            headers={
                "Content-Disposition": f'attachment; filename="grayscope_{task_id}.csv"'
            },
        )
    elif fmt == "findings":
        content = export_service.export_findings_json(db, task_id)
        return PlainTextResponse(
            content,
            media_type="application/json",
            headers={
                "Content-Disposition": f'attachment; filename="grayscope_{task_id}_findings.json"'
            },
        )
    else:
        content = export_service.export_json(db, task_id)
        return PlainTextResponse(
            content,
            media_type="application/json",
            headers={
                "Content-Disposition": f'attachment; filename="grayscope_{task_id}_testcases.json"'
            },
        )


@router.post("/analysis/tasks/{task_id}/retry", status_code=HTTP_202_ACCEPTED)
def retry_task(
    task_id: str, req: RetryRequest, db: Session = Depends(get_db)
) -> dict:
    """重试失败的分析模块。"""
    out = task_service.retry_task(db, task_id, req)
    return ok(out.model_dump())


@router.post("/analysis/tasks/{task_id}/cancel", status_code=HTTP_202_ACCEPTED)
def cancel_task(task_id: str, db: Session = Depends(get_db)) -> dict:
    """取消分析任务。"""
    out = task_service.cancel_task(db, task_id)
    return ok(out.model_dump())
