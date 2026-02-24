"""测试执行调度（占位，后续实现）。"""

from __future__ import annotations

import uuid


def schedule_test_run(task_id: str, test_case_ids: list[int]) -> dict:
    """调度一批测试用例执行。占位返回 run_id 供 E2E 编排使用。"""
    run_id = str(uuid.uuid4())[:8]
    return {"run_id": run_id, "scheduled": 0, "message": "未实现"}
