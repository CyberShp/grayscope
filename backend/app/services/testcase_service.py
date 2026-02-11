"""测试用例持久化服务 — 将分析发现转化为持久化的测试用例记录。"""

from __future__ import annotations

import json
import logging
from typing import Optional

from sqlalchemy.orm import Session

from app.models.test_case import TestCase
from app.models.analysis_task import AnalysisTask
from app.models.module_result import AnalysisModuleResult
from app.services.export_service import _findings_to_testcases

logger = logging.getLogger(__name__)


def persist_test_cases(db: Session, task: AnalysisTask) -> int:
    """为一个分析任务生成并持久化测试用例。返回写入数量。"""
    if task.status not in ("success", "partial_failed"):
        return 0

    # 收集该任务的所有发现
    all_findings = []
    ai_data = {}
    for mr in task.module_results:
        try:
            findings = json.loads(mr.findings_json) if mr.findings_json else []
            all_findings.extend(findings)
        except (json.JSONDecodeError, TypeError):
            pass
        if mr.ai_summary_json:
            try:
                ai_data[mr.module_id] = json.loads(mr.ai_summary_json)
            except (json.JSONDecodeError, TypeError):
                pass

    if not all_findings:
        return 0

    # 生成测试用例
    cases = _findings_to_testcases(task.task_id, all_findings, ai_data)

    count = 0
    for c in cases:
        case_id = c["test_case_id"]
        # 检查是否已存在（幂等）
        existing = db.query(TestCase).filter(
            TestCase.task_id == task.id,
            TestCase.case_id == case_id,
        ).first()
        if existing:
            continue

        tc = TestCase(
            task_id=task.id,
            case_id=case_id,
            title=c.get("title", ""),
            risk_type=c.get("category", ""),
            priority=c.get("priority", "P3-低")[:8],
            preconditions_json=json.dumps(c.get("preconditions", []), ensure_ascii=False),
            steps_json=json.dumps(c.get("test_steps", []), ensure_ascii=False),
            expected_json=json.dumps(c.get("expected_result", ""), ensure_ascii=False),
            source_finding_ids_json=json.dumps([c.get("source_finding_id", "")]),
            status="pending",
            risk_score=c.get("risk_score"),
            module_id=c.get("module_id"),
            file_path=c.get("target_file"),
            symbol_name=c.get("target_function"),
            objective=c.get("objective"),
            expected=c.get("expected_result"),
        )
        db.add(tc)
        count += 1

    if count > 0:
        db.commit()
        logger.info("为任务 %s 持久化 %d 条测试用例", task.task_id, count)

    return count


def get_project_test_cases(
    db: Session,
    project_id: int,
    status: Optional[str] = None,
    priority: Optional[str] = None,
    module_id: Optional[str] = None,
    page: int = 1,
    page_size: int = 50,
) -> tuple[list[TestCase], int]:
    """查询项目的持久化测试用例。"""
    query = (
        db.query(TestCase)
        .join(AnalysisTask, TestCase.task_id == AnalysisTask.id)
        .filter(AnalysisTask.project_id == project_id)
    )
    if status:
        query = query.filter(TestCase.status == status)
    if priority:
        query = query.filter(TestCase.priority.like(f"{priority}%"))
    if module_id:
        query = query.filter(TestCase.module_id == module_id)

    total = query.count()
    items = (
        query.order_by(TestCase.risk_score.desc().nullslast())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return items, total


def update_test_case_status(db: Session, test_case_id: int, new_status: str) -> Optional[TestCase]:
    """更新测试用例状态（采纳/忽略/已执行）。"""
    tc = db.query(TestCase).filter(TestCase.id == test_case_id).first()
    if tc and new_status in ("pending", "adopted", "ignored", "executed"):
        tc.status = new_status
        db.commit()
    return tc
