"""覆盖率北向接口：将已导入的覆盖率转为 coverage_map 可用的 FileCoverage。"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.analyzers.coverage_mapper import (
    _granular_payload_to_file_coverage,
    _summary_payload_to_file_coverage,
)
from app.repositories import task_repo
from app.repositories.coverage_import_repo import get_latest_payload_by_task_id


def get_imported_coverage_for_task(db: Session, task_id: str) -> dict:
    """按任务逻辑 ID 取最近一次导入的覆盖率，转为 FileCoverage 字典供 coverage_map 使用。"""
    task = task_repo.get_task_by_id(db, task_id)
    if not task:
        return {}
    out = get_latest_payload_by_task_id(db, task.id)
    if not out:
        return {}
    payload, fmt = out
    if fmt == "summary":
        return _summary_payload_to_file_coverage(payload)
    if fmt == "granular":
        return _granular_payload_to_file_coverage(payload)
    return {}
