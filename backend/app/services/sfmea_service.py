"""SFMEA 生成服务：从分析发现生成 SFMEA 条目。"""

from __future__ import annotations

import json
import logging
from typing import Any

from sqlalchemy.orm import Session

from app.models.sfmea_entry import SfmeaEntry

logger = logging.getLogger(__name__)


def _rpn(severity: int, occurrence: int, detection: int) -> float:
    if severity is None or occurrence is None or detection is None:
        return 0.0
    return float(severity * occurrence * detection)


def generate_from_task(db: Session, task_id: str) -> int:
    """根据任务的模块结果与风险发现生成 SFMEA 条目，返回生成数量。"""
    from app.repositories import task_repo
    task = task_repo.get_task_by_id(db, task_id)
    if not task:
        return 0
    # 删除该任务已有 SFMEA 条目
    db.query(SfmeaEntry).filter(SfmeaEntry.task_id == task.id).delete()
    count = 0
    for mr in task.module_results or []:
        try:
            findings = json.loads(mr.findings_json) if mr.findings_json else []
        except (TypeError, json.JSONDecodeError):
            findings = []
        for f in findings:
            title = f.get("title") or "未命名风险"
            failure_mode = (f.get("description") or title)[:512]
            severity = _severity_from_finding(f)
            occurrence = 5  # 默认中等
            detection = 5
            rpn_val = _rpn(severity, occurrence, detection)
            entry = SfmeaEntry(
                task_id=task.id,
                failure_mode=failure_mode,
                severity=severity,
                occurrence=occurrence,
                detection=detection,
                rpn=rpn_val,
                file_path=f.get("file_path"),
                symbol_name=f.get("symbol_name"),
            )
            db.add(entry)
            count += 1
    db.commit()
    return count


def _severity_from_finding(f: dict[str, Any]) -> int:
    sev = (f.get("severity") or "S3").upper()
    if sev == "S0":
        return 10
    if sev == "S1":
        return 8
    if sev == "S2":
        return 5
    return 3
