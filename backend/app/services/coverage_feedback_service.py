"""覆盖率反馈闭环：将 gcovr JSON 转为北向 coverage 格式并写入，供 coverage_map 与前端展示。"""

from __future__ import annotations

import json
import logging
from typing import Any

from sqlalchemy.orm import Session

from app.repositories.coverage_import_repo import create as coverage_import_create
from app.repositories.test_run_repo import get_run_by_id, update_run_status

logger = logging.getLogger(__name__)


def gcovr_json_to_summary(gcovr_json: str | dict) -> dict[str, Any]:
    """
    将 gcovr --json 输出转为北向接口 summary 格式。

    summary 格式: { "files": { filepath: { "lines_total": n, "lines_hit": n, "functions": { fn_name: 0|1 } } } }
    """
    if isinstance(gcovr_json, str):
        try:
            data = json.loads(gcovr_json)
        except json.JSONDecodeError:
            return {"files": {}}
    else:
        data = gcovr_json or {}
    files_in = data.get("files") or []
    if not isinstance(files_in, list):
        return {"files": {}}
    out_files: dict[str, dict[str, Any]] = {}
    for entry in files_in:
        if not isinstance(entry, dict):
            continue
        path = entry.get("file") or entry.get("filename") or ""
        if not path:
            continue
        lines_list = entry.get("lines") or []
        func_list = entry.get("functions") or []
        lines_total = len(lines_list)
        lines_hit = sum(1 for L in lines_list if isinstance(L, dict) and (L.get("count") or 0) > 0)
        functions: dict[str, int] = {}
        for F in func_list:
            if not isinstance(F, dict):
                continue
            name = F.get("name") or F.get("function_name") or ""
            if not name:
                continue
            # 有 execution_count 或通过 lines 推断
            hit = 1 if (F.get("execution_count") or 0) > 0 else 0
            functions[name] = hit
        out_files[path] = {
            "lines_total": lines_total,
            "lines_hit": lines_hit,
            "functions": functions,
        }
    return {"files": out_files}


def upload_coverage_for_run(
    db: Session,
    run_id: str,
    task_primary_id: int | None,
    gcovr_json: str | dict,
    source_system: str = "dt_execution",
    revision: str = "",
) -> tuple[bool, str]:
    """
    将测试运行产生的 gcovr 覆盖率写入北向接口并更新 run 的 coverage_delta_json。

    :param task_primary_id: 关联的 analysis_tasks.id（主键），用于写入 coverage_import
    :return: (success, message)
    """
    summary = gcovr_json_to_summary(gcovr_json)
    if not summary.get("files"):
        return False, "gcovr 解析后无文件数据"
    run = get_run_by_id(db, run_id)
    if run:
        update_run_status(
            db, run_id, run.status,
            coverage_delta_json=json.dumps(summary, ensure_ascii=False),
        )
    if not task_primary_id:
        return True, "已更新 run 覆盖率；未关联 task，未写入北向"
    try:
        coverage_import_create(
            db,
            task_id=task_primary_id,
            source_system=source_system,
            revision=revision or "",
            format="summary",
            payload=summary,
        )
        return True, "覆盖率已写入北向接口，coverage_map 下次分析将使用"
    except Exception as e:
        logger.exception("upload_coverage_for_run: %s", e)
        return False, str(e)
