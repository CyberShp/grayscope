"""分析任务 API 端点。"""

from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session
from starlette.status import HTTP_201_CREATED, HTTP_202_ACCEPTED, HTTP_400_BAD_REQUEST, HTTP_404_NOT_FOUND

from app.core.database import get_db
from app.core.response import ok
from app.repositories import task_repo
from app.repositories.coverage_import_repo import create as coverage_import_create, get_latest_by_task_id
from app.schemas.analysis import CoverageImportRequest, RetryRequest, TaskCreateRequest, TaskMrUpdate
from app.services import analysis_orchestrator, export_service, task_service, sfmea_service


class BatchDeleteRequest(BaseModel):
    task_ids: List[str]

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
    fmt: str = Query(
        "json",
        pattern="^(json|csv|markdown|findings|critical|html|sfmea)$",
    ),
    db: Session = Depends(get_db),
):
    """导出分析结果为结构化测试用例。

    格式选项：
    - json：结构化测试用例建议（含多函数交汇临界点 + 用例）
    - csv：测试用例表（先交汇临界点再用例，可导入测试管理工具）
    - markdown：灰盒测试用例清单（含步骤、预期、如何执行）
    - findings：原始发现及 AI 增强数据（JSON）
    - critical：仅多函数交汇临界点（JSON，便于快速粘贴）
    - html：单页 HTML 报告（便于分享与归档）
    - sfmea：SFMEA 条目 CSV（RPN、严重度等）
    """
    if fmt == "sfmea":
        content = export_service.export_sfmea_csv(db, task_id)
        return PlainTextResponse(
            content,
            media_type="text/csv",
            headers={
                "Content-Disposition": f'attachment; filename="grayscope_{task_id}_sfmea.csv"'
            },
        )
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
    elif fmt == "critical":
        content = export_service.export_critical_only(db, task_id)
        return PlainTextResponse(
            content,
            media_type="application/json",
            headers={
                "Content-Disposition": f'attachment; filename="grayscope_{task_id}_critical.json"'
            },
        )
    elif fmt == "html":
        content = export_service.export_html(db, task_id)
        return PlainTextResponse(
            content,
            media_type="text/html",
            headers={
                "Content-Disposition": f'inline; filename="grayscope_{task_id}_report.html"'
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


@router.patch("/analysis/tasks/{task_id}/mr")
def update_task_mr(
    task_id: str, req: TaskMrUpdate, db: Session = Depends(get_db)
) -> dict:
    """更新任务关联的 MR/PR 链接与代码变更，供前端「MR 代码变更」板块展示。"""
    task = task_repo.update_task_mr(
        db, task_id, mr_url=req.mr_url, mr_diff=req.mr_diff
    )
    if not task:
        raise HTTPException(HTTP_404_NOT_FOUND, detail="任务不存在")
    out = task_service.get_task_status(db, task_id)
    return ok(out.model_dump(), message="MR 信息已更新")


@router.delete("/analysis/tasks/{task_id}")
def delete_task(task_id: str, db: Session = Depends(get_db)) -> dict:
    """删除分析任务及所有关联的风险发现、测试用例、模块结果等。"""
    task = task_repo.get_task_by_id(db, task_id)
    if not task:
        raise HTTPException(HTTP_404_NOT_FOUND, detail="任务不存在")
    counts = task_repo.delete_task_cascade(db, task.id)
    return ok(counts, message="任务已删除")


@router.post("/analysis/tasks/delete-preview")
def delete_preview(req: BatchDeleteRequest, db: Session = Depends(get_db)) -> dict:
    """预览删除影响：返回将被删除的风险发现、测试用例等数量。"""
    task_pks = []
    for tid in req.task_ids:
        task = task_repo.get_task_by_id(db, tid)
        if task:
            task_pks.append(task.id)
    counts = task_repo.delete_preview(db, task_pks)
    return ok(counts)


@router.post("/analysis/tasks/batch-delete")
def batch_delete_tasks(req: BatchDeleteRequest, db: Session = Depends(get_db)) -> dict:
    """批量删除分析任务及所有关联数据。"""
    task_pks = []
    for tid in req.task_ids:
        task = task_repo.get_task_by_id(db, tid)
        if task:
            task_pks.append(task.id)
    if not task_pks:
        raise HTTPException(HTTP_404_NOT_FOUND, detail="未找到任何有效任务")
    counts = task_repo.delete_tasks_batch(db, task_pks)
    return ok(counts, message=f"已删除 {counts['task_count']} 个任务")


@router.post("/analysis/tasks/{task_id}/sfmea")
def generate_sfmea(task_id: str, db: Session = Depends(get_db)) -> dict:
    """根据任务分析结果生成 SFMEA 条目。"""
    task = task_repo.get_task_by_id(db, task_id)
    if not task:
        raise HTTPException(HTTP_404_NOT_FOUND, detail="任务不存在")
    count = sfmea_service.generate_from_task(db, task_id)
    return ok({"generated": count}, message=f"已生成 {count} 条 SFMEA 条目")


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
