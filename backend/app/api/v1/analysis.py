"""分析任务 API 端点。"""

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session
from starlette.status import HTTP_201_CREATED, HTTP_202_ACCEPTED, HTTP_400_BAD_REQUEST, HTTP_404_NOT_FOUND

from app.core.database import get_db
from app.core.response import ok
from app.repositories import task_repo
from app.repositories.coverage_import_repo import create as coverage_import_create, get_latest_by_task_id
from app.schemas.analysis import CoverageImportRequest, RetryRequest, TaskCreateRequest
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
    fmt: str = Query("json", pattern="^(json|csv|markdown|findings)$"),
    db: Session = Depends(get_db),
):
    """导出分析结果为结构化测试用例。

    格式选项：
    - json：结构化测试用例建议（JSON）
    - csv：测试用例表（CSV，可导入测试管理工具）
    - markdown：灰盒测试用例清单（含步骤、预期、如何执行）
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
    elif fmt == "markdown":
        content = export_service.export_markdown(db, task_id)
        return PlainTextResponse(
            content,
            media_type="text/markdown",
            headers={
                "Content-Disposition": f'attachment; filename="grayscope_{task_id}_testcases.md"'
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


@router.post("/analysis/tasks/{task_id}/coverage")
def import_coverage(
    task_id: str, req: CoverageImportRequest, db: Session = Depends(get_db)
) -> dict:
    """北向接口：写入覆盖率数据。内网覆盖率系统可推送已覆盖路径/分支到此。"""
    task = task_repo.get_task_by_id(db, task_id)
    if not task:
        raise HTTPException(HTTP_404_NOT_FOUND, detail="任务不存在")
    if req.format == "summary":
        if not req.files or not isinstance(req.files, dict):
            raise HTTPException(
                HTTP_400_BAD_REQUEST,
                detail="format=summary 时需提供 files 对象",
            )
        payload = {"files": req.files}
    else:
        covered = req.covered if isinstance(req.covered, list) else []
        tests = req.tests if isinstance(req.tests, list) else []
        if not covered and not tests:
            raise HTTPException(
                HTTP_400_BAD_REQUEST,
                detail="format=granular 时需提供 covered 或 tests",
            )
        payload = {"covered": covered, "tests": tests}
    row = coverage_import_create(
        db,
        task_id=task.id,
        source_system=req.source_system or "",
        revision=req.revision or "",
        format=req.format,
        payload=payload,
    )
    return ok(
        {
            "import_id": row.id,
            "task_id": task_id,
            "format": row.format,
            "source_system": row.source_system,
        },
        message="覆盖率数据已写入",
    )


@router.get("/analysis/tasks/{task_id}/coverage")
def get_coverage_import(task_id: str, db: Session = Depends(get_db)) -> dict:
    """查询该任务最近一次导入的覆盖率元数据。"""
    task = task_repo.get_task_by_id(db, task_id)
    if not task:
        raise HTTPException(HTTP_404_NOT_FOUND, detail="任务不存在")
    row = get_latest_by_task_id(db, task.id)
    if not row:
        return ok({"latest": None, "has_data": False})
    return ok({
        "latest": {
            "import_id": row.id,
            "source_system": row.source_system,
            "revision": row.revision,
            "format": row.format,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        },
        "has_data": True,
    })
