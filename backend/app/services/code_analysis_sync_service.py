"""Code analysis sync service.

Syncs code analysis results to the project-level risk/test system by:
1. Creating a bridge AnalysisTask record
2. Syncing risk_findings to RiskFinding table
3. Syncing test_matrix/risk_cards/what_if to TestCase table

This allows project views (ProjectIssues, ProjectTestDesign, TestExecution)
to display code analysis results without any query changes.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.models.analysis_task import AnalysisTask
from app.models.code_analysis_task import CodeAnalysisTask
from app.models.risk_finding import RiskFinding
from app.models.test_case import TestCase

logger = logging.getLogger(__name__)

# Map S0/S1/S2/S3 from FusedRiskAnalyzer to standard severity names
_S_TO_SEVERITY = {"S0": "critical", "S1": "high", "S2": "medium", "S3": "low"}

# Severity to priority mapping
_SEVERITY_TO_PRIORITY = {
    "critical": "P0-紧急",
    "high": "P1-高",
    "medium": "P2-中",
    "low": "P3-低",
}


def _map_severity(raw_severity: str | None) -> str:
    """Map severity from various formats to standard (critical/high/medium/low)."""
    if not raw_severity:
        return "medium"
    # First try S0/S1/S2/S3 mapping
    severity = _S_TO_SEVERITY.get(raw_severity, raw_severity)
    # Validate result
    if severity not in ("critical", "high", "medium", "low"):
        return "medium"
    return severity


def sync_code_analysis_to_project(
    db: Session,
    analysis_id: str,
    result_dict: dict[str, Any],
    project_id: int,
    repo_id: int,
) -> int | None:
    """Sync code analysis results to project-level risk/test system.
    
    Args:
        db: Database session
        analysis_id: Code analysis task ID
        result_dict: The serialized AnalysisResult (from to_dict())
        project_id: Project ID to associate with
        repo_id: Repository ID to associate with
    
    Returns:
        The bridge AnalysisTask.id if successful, None otherwise
    """
    if not project_id or not repo_id:
        logger.warning(f"Cannot sync {analysis_id}: missing project_id or repo_id")
        return None
    
    try:
        # Step 1: Create or update bridge AnalysisTask
        bridge_task = _create_or_update_bridge_task(
            db, analysis_id, project_id, repo_id, result_dict
        )
        
        # Step 2: Sync risk findings
        risk_findings = result_dict.get("risk_findings", [])
        finding_count = _sync_risk_findings(db, bridge_task.id, risk_findings)
        
        # Step 3: Sync test cases from narratives
        narratives = result_dict.get("narratives", {})
        testcase_count = _sync_test_cases(db, bridge_task.id, narratives, risk_findings)
        
        # Step 4: Update CodeAnalysisTask with bridge reference
        ca_task = (
            db.query(CodeAnalysisTask)
            .filter(CodeAnalysisTask.analysis_id == analysis_id)
            .first()
        )
        if ca_task:
            ca_task.bridge_task_id = bridge_task.id
        
        # Single atomic commit for entire sync operation
        db.commit()
        
        logger.info(
            f"Synced code analysis {analysis_id} to project {project_id}: "
            f"{finding_count} findings, {testcase_count} test cases"
        )
        return bridge_task.id
        
    except Exception as e:
        logger.exception(f"Failed to sync code analysis {analysis_id}: {e}")
        db.rollback()
        return None


def delete_synced_data(db: Session, analysis_id: str) -> bool:
    """Delete synced data when a code analysis task is deleted.
    
    Args:
        db: Database session
        analysis_id: Code analysis task ID
    
    Returns:
        True if deletion was successful
    """
    try:
        # Find the code analysis task
        ca_task = (
            db.query(CodeAnalysisTask)
            .filter(CodeAnalysisTask.analysis_id == analysis_id)
            .first()
        )
        if not ca_task or not ca_task.bridge_task_id:
            return True
        
        bridge_task_id = ca_task.bridge_task_id
        
        # Delete test cases linked to the bridge task
        db.query(TestCase).filter(TestCase.task_id == bridge_task_id).delete()
        
        # Delete risk findings linked to the bridge task
        db.query(RiskFinding).filter(RiskFinding.task_id == bridge_task_id).delete()
        
        # Delete the bridge AnalysisTask
        db.query(AnalysisTask).filter(AnalysisTask.id == bridge_task_id).delete()
        
        # Clear the bridge reference
        ca_task.bridge_task_id = None
        
        db.commit()
        logger.info(f"Deleted synced data for code analysis {analysis_id}")
        return True
        
    except Exception as e:
        logger.exception(f"Failed to delete synced data for {analysis_id}: {e}")
        db.rollback()
        return False


def _create_or_update_bridge_task(
    db: Session,
    analysis_id: str,
    project_id: int,
    repo_id: int,
    result_dict: dict[str, Any],
) -> AnalysisTask:
    """Create or update a bridge AnalysisTask for the code analysis."""
    bridge_task_id = f"CA-{analysis_id}"
    
    # Check if bridge task already exists
    existing = (
        db.query(AnalysisTask)
        .filter(AnalysisTask.task_id == bridge_task_id)
        .first()
    )
    
    # Calculate aggregate risk score
    risk_findings = result_dict.get("risk_findings", [])
    risk_summary = result_dict.get("risk_summary", {})
    aggregate_score = risk_summary.get("aggregate_score")
    if aggregate_score is None and risk_findings:
        scores = [f.get("risk_score", 0) for f in risk_findings if f.get("risk_score")]
        aggregate_score = sum(scores) / len(scores) if scores else 0
    
    if existing:
        # Update existing bridge task
        existing.status = "success"
        existing.aggregate_risk_score = aggregate_score
        existing.finished_at = datetime.now(timezone.utc)
        
        # Clear old synced data before re-syncing (no commit - part of transaction)
        db.query(TestCase).filter(TestCase.task_id == existing.id).delete()
        db.query(RiskFinding).filter(RiskFinding.task_id == existing.id).delete()
        
        return existing
    
    # Create new bridge task
    bridge_task = AnalysisTask(
        task_id=bridge_task_id,
        project_id=project_id,
        repo_id=repo_id,
        task_type="code_analysis",
        status="success",
        target_json=json.dumps({"source": "code_analysis", "analysis_id": analysis_id}),
        revision_json=json.dumps({}),
        analyzers_json=json.dumps(["code_analysis"]),
        ai_json=json.dumps({"enabled": True}),
        aggregate_risk_score=aggregate_score,
        finished_at=datetime.now(timezone.utc),
    )
    db.add(bridge_task)
    db.flush()  # Get the ID without committing (part of transaction)
    
    return bridge_task


def _sync_risk_findings(
    db: Session,
    bridge_task_id: int,
    risk_findings: list[dict[str, Any]],
) -> int:
    """Sync risk findings to RiskFinding table."""
    if not risk_findings:
        return 0
    
    count = 0
    seen_keys: set[tuple] = set()
    
    for finding in risk_findings:
        # Dedup key
        key = (
            finding.get("file_path", ""),
            finding.get("line_start"),
            finding.get("risk_type", ""),
        )
        if key in seen_keys:
            continue
        seen_keys.add(key)
        
        # Map severity (handles S0/S1/S2/S3 from FusedRiskAnalyzer)
        severity = _map_severity(finding.get("severity"))
        
        # Extract call chain for evidence
        call_chain = finding.get("call_chain", [])
        evidence = finding.get("evidence", {})
        
        rf = RiskFinding(
            task_id=bridge_task_id,
            module_id="code_analysis",
            risk_type=finding.get("risk_type", "unknown")[:32],
            severity=severity[:8],
            risk_score=finding.get("risk_score", 0.5),
            file_path=finding.get("file_path", "unknown"),
            symbol_name=finding.get("symbol_name") or finding.get("function_name"),
            line_start=finding.get("line_start"),
            line_end=finding.get("line_end"),
            title=(finding.get("title") or finding.get("description", "风险发现"))[:256],
            description=finding.get("description", ""),
            evidence_json=json.dumps(evidence, ensure_ascii=False) if evidence else None,
            call_chain_json=json.dumps(call_chain, ensure_ascii=False) if call_chain else None,
            pillar=finding.get("pillar"),
        )
        db.add(rf)
        count += 1
    
    # No commit here - part of outer transaction
    return count


def _sync_test_cases(
    db: Session,
    bridge_task_id: int,
    narratives: dict[str, Any],
    risk_findings: list[dict[str, Any]],
) -> int:
    """Sync test cases from narratives to TestCase table.
    
    Sources (in priority order):
    1. test_matrix.test_cases - AI-generated test design matrix
    2. risk_cards - Risk scenario cards with test steps
    3. what_if_scenarios - What-If test scenarios
    """
    if not narratives:
        return 0
    
    count = 0
    case_index = 0
    
    # Source 1: Test design matrix
    test_matrix = narratives.get("test_matrix", {})
    matrix_cases = test_matrix.get("test_cases", [])
    if isinstance(matrix_cases, list):
        for tc in matrix_cases:
            case_id = f"CA-TM-{case_index}"
            if _create_test_case_from_matrix(db, bridge_task_id, case_id, tc):
                count += 1
                case_index += 1
    
    # Source 2: Risk cards
    risk_cards = narratives.get("risk_cards", [])
    if isinstance(risk_cards, list):
        for card in risk_cards:
            case_id = f"CA-RC-{case_index}"
            if _create_test_case_from_risk_card(db, bridge_task_id, case_id, card):
                count += 1
                case_index += 1
    
    # Source 3: What-If scenarios
    what_if_scenarios = narratives.get("what_if_scenarios", [])
    if isinstance(what_if_scenarios, list):
        for scenario_group in what_if_scenarios:
            scenarios = scenario_group.get("scenarios", [])
            if isinstance(scenarios, list):
                for scenario in scenarios:
                    case_id = f"CA-WI-{case_index}"
                    if _create_test_case_from_what_if(db, bridge_task_id, case_id, scenario, scenario_group):
                        count += 1
                        case_index += 1
    
    # No commit here - part of outer transaction
    return count


def _create_test_case_from_matrix(
    db: Session,
    bridge_task_id: int,
    case_id: str,
    tc: dict[str, Any],
) -> bool:
    """Create TestCase from test_matrix entry."""
    if not tc:
        return False
    
    title = tc.get("title") or tc.get("scenario_name") or tc.get("name", "测试用例")
    risk_type = tc.get("risk_type") or tc.get("category", "general")
    severity = _map_severity(tc.get("severity"))
    priority = _SEVERITY_TO_PRIORITY.get(severity, "P2-中")
    
    # Extract test steps
    steps = tc.get("test_steps") or tc.get("steps", [])
    if isinstance(steps, str):
        steps = [steps]
    
    # Extract expected result
    expected = tc.get("expected_result") or tc.get("expected", "")
    
    # Extract preconditions
    preconditions = tc.get("preconditions", [])
    if isinstance(preconditions, str):
        preconditions = [preconditions]
    
    test_case = TestCase(
        task_id=bridge_task_id,
        case_id=case_id,
        title=str(title)[:256],
        risk_type=str(risk_type)[:32],
        priority=priority[:8],
        preconditions_json=json.dumps(preconditions, ensure_ascii=False),
        steps_json=json.dumps(steps, ensure_ascii=False),
        expected_json=json.dumps(expected, ensure_ascii=False) if not isinstance(expected, str) else expected,
        expected=expected if isinstance(expected, str) else None,
        status="pending",
        risk_score=tc.get("risk_score"),
        module_id="code_analysis",
        file_path=tc.get("file_path") or tc.get("target_file"),
        symbol_name=tc.get("function_name") or tc.get("target_function"),
        objective=tc.get("objective") or tc.get("description"),
        execution_hint=tc.get("execution_hint") or tc.get("test_approach"),
        source_finding_ids_json=json.dumps(tc.get("related_risk_ids", [])),
        unacceptable_outcomes_json=json.dumps(tc.get("unacceptable_behaviors", []), ensure_ascii=False) if tc.get("unacceptable_behaviors") else None,
        related_functions_json=json.dumps(tc.get("related_functions", []), ensure_ascii=False) if tc.get("related_functions") else None,
    )
    db.add(test_case)
    return True


def _create_test_case_from_risk_card(
    db: Session,
    bridge_task_id: int,
    case_id: str,
    card: dict[str, Any],
) -> bool:
    """Create TestCase from risk_card entry."""
    if not card:
        return False
    
    title = card.get("title", "风险场景测试")
    severity = _map_severity(card.get("severity"))
    priority = card.get("priority") or _SEVERITY_TO_PRIORITY.get(severity, "P2-中")
    
    # Extract test steps
    steps = card.get("test_steps", [])
    if isinstance(steps, str):
        steps = [steps]
    
    # Extract expected behavior as expected result
    expected = card.get("expected_behavior", "")
    
    # Trigger conditions as preconditions
    preconditions = card.get("trigger_conditions", [])
    if isinstance(preconditions, str):
        preconditions = [preconditions]
    
    test_case = TestCase(
        task_id=bridge_task_id,
        case_id=case_id,
        title=str(title)[:256],
        risk_type=card.get("risk_type", "risk_card")[:32],
        priority=str(priority)[:8],
        preconditions_json=json.dumps(preconditions, ensure_ascii=False),
        steps_json=json.dumps(steps, ensure_ascii=False),
        expected_json=expected if isinstance(expected, str) else json.dumps(expected, ensure_ascii=False),
        expected=expected if isinstance(expected, str) else None,
        status="pending",
        module_id="code_analysis",
        objective=card.get("business_context") or card.get("risk_explanation"),
        execution_hint="; ".join(card.get("verification_points", [])) if card.get("verification_points") else None,
        source_finding_ids_json=json.dumps([card.get("card_id", "")]),
        unacceptable_outcomes_json=json.dumps(card.get("unacceptable_behaviors", []), ensure_ascii=False) if card.get("unacceptable_behaviors") else None,
    )
    db.add(test_case)
    return True


def _create_test_case_from_what_if(
    db: Session,
    bridge_task_id: int,
    case_id: str,
    scenario: dict[str, Any],
    scenario_group: dict[str, Any],
) -> bool:
    """Create TestCase from what_if scenario entry."""
    if not scenario:
        return False
    
    # The what_if question becomes the title
    title = scenario.get("what_if", "What-If 场景测试")
    risk_level = _map_severity(scenario.get("risk_level"))
    priority = _SEVERITY_TO_PRIORITY.get(risk_level, "P2-中")
    
    # Test approach as steps
    test_approach = scenario.get("test_approach", "")
    steps = [test_approach] if test_approach else []
    
    # Potential outcome as expected (what we're testing for)
    expected = scenario.get("potential_outcome", "")
    
    # Related functions for context
    related_functions = scenario.get("related_functions", [])
    
    test_case = TestCase(
        task_id=bridge_task_id,
        case_id=case_id,
        title=str(title)[:256],
        risk_type="what_if",
        priority=priority[:8],
        preconditions_json=json.dumps([f"触发步骤: {scenario.get('trigger_step', '')}"]) if scenario.get("trigger_step") else "[]",
        steps_json=json.dumps(steps, ensure_ascii=False),
        expected_json=expected if isinstance(expected, str) else json.dumps(expected, ensure_ascii=False),
        expected=expected if isinstance(expected, str) else None,
        status="pending",
        module_id="code_analysis",
        objective=scenario_group.get("summary") or scenario.get("what_if"),
        execution_hint=test_approach,
        expected_failure=expected,
        source_finding_ids_json=json.dumps([scenario.get("scenario_id", "")]),
        related_functions_json=json.dumps(related_functions, ensure_ascii=False) if related_functions else None,
    )
    db.add(test_case)
    return True
