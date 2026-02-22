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

        exp = c.get("expected_result")
        expected_json_val = json.dumps(exp, ensure_ascii=False) if not isinstance(exp, str) else exp
        tc = TestCase(
            task_id=task.id,
            case_id=case_id,
            title=c.get("title", ""),
            risk_type=c.get("category", ""),
            priority=c.get("priority", "P3-低")[:8],
            preconditions_json=json.dumps(c.get("preconditions", []), ensure_ascii=False),
            steps_json=json.dumps(c.get("test_steps", []), ensure_ascii=False),
            expected_json=expected_json_val,
            source_finding_ids_json=json.dumps([c.get("source_finding_id", "")]),
            status="pending",
            risk_score=c.get("risk_score"),
            module_id=c.get("module_id"),
            file_path=c.get("target_file"),
            symbol_name=c.get("target_function"),
            objective=c.get("objective"),
            expected=exp if isinstance(exp, str) else None,
            execution_hint=c.get("execution_hint"),
            example_input=c.get("example_input"),
            expected_failure=c.get("expected_failure"),
            unacceptable_outcomes_json=json.dumps(c.get("unacceptable_outcomes", []), ensure_ascii=False) if c.get("unacceptable_outcomes") else None,
            related_functions_json=json.dumps(c.get("related_functions", []), ensure_ascii=False) if c.get("related_functions") else None,
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


def get_by_id(db: Session, test_case_id: int) -> Optional[TestCase]:
    """按主键获取一条测试用例。"""
    return db.query(TestCase).filter(TestCase.id == test_case_id).first()


def update_test_case_status(db: Session, test_case_id: int, new_status: str) -> Optional[TestCase]:
    """更新测试用例状态（采纳/忽略/已执行）。"""
    tc = db.query(TestCase).filter(TestCase.id == test_case_id).first()
    if tc and new_status in ("pending", "adopted", "ignored", "executed"):
        tc.status = new_status
        db.commit()
    return tc


def update_test_case(
    db: Session,
    test_case_id: int,
    *,
    title: Optional[str] = None,
    priority: Optional[str] = None,
    preconditions: Optional[list] = None,
    test_steps: Optional[list] = None,
    expected_result: Optional[str] = None,
    objective: Optional[str] = None,
    execution_hint: Optional[str] = None,
    example_input: Optional[str] = None,
    expected_failure: Optional[str] = None,
    unacceptable_outcomes: Optional[list] = None,
    related_functions: Optional[list] = None,
) -> Optional[TestCase]:
    """更新测试用例可编辑字段（步骤、预期、优先级等）。"""
    tc = db.query(TestCase).filter(TestCase.id == test_case_id).first()
    if not tc:
        return None
    if title is not None:
        tc.title = title[:256]
    if priority is not None:
        tc.priority = priority[:8]
    if preconditions is not None:
        tc.preconditions_json = json.dumps(preconditions, ensure_ascii=False)
    if test_steps is not None:
        tc.steps_json = json.dumps(test_steps, ensure_ascii=False)
    if expected_result is not None:
        tc.expected_json = expected_result if isinstance(expected_result, str) else json.dumps(expected_result, ensure_ascii=False)
        tc.expected = expected_result if isinstance(expected_result, str) else None
    if objective is not None:
        tc.objective = objective
    if execution_hint is not None:
        tc.execution_hint = execution_hint
    if example_input is not None:
        tc.example_input = example_input
    if expected_failure is not None:
        tc.expected_failure = expected_failure
    if unacceptable_outcomes is not None:
        tc.unacceptable_outcomes_json = json.dumps(unacceptable_outcomes, ensure_ascii=False)
    if related_functions is not None:
        tc.related_functions_json = json.dumps(related_functions, ensure_ascii=False)
    db.commit()
    db.refresh(tc)
    return tc
