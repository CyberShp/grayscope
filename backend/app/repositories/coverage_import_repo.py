"""覆盖率导入记录的数据访问。"""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.models.coverage_import import CoverageImport


def create(
    db: Session,
    *,
    task_id: int,
    source_system: str = "",
    revision: str = "",
    format: str,
    payload: dict[str, Any],
) -> CoverageImport:
    """写入一条覆盖率导入记录。"""
    obj = CoverageImport(
        task_id=task_id,
        source_system=source_system or "",
        revision=revision or "",
        format=format,
        payload_json=json.dumps(payload, ensure_ascii=False),
    )
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


def get_latest_by_task_id(db: Session, task_primary_id: int) -> CoverageImport | None:
    """按任务主键查询最近一次导入记录。"""
    return db.scalars(
        select(CoverageImport)
        .where(CoverageImport.task_id == task_primary_id)
        .order_by(desc(CoverageImport.created_at))
        .limit(1)
    ).first()


def get_latest_payload_by_task_id(
    db: Session, task_primary_id: int
) -> tuple[dict[str, Any], str] | None:
    """返回 (payload_dict, format) 或 None。"""
    row = get_latest_by_task_id(db, task_primary_id)
    if not row:
        return None
    try:
        payload = json.loads(row.payload_json)
    except Exception:
        return None
    return (payload, row.format)
