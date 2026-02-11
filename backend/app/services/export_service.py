"""导出服务：结构化测试用例和发现的 JSON/CSV 导出。

将分析任务发现转换为结构化测试用例，并以机器可读格式导出。
"""

from __future__ import annotations

import csv
import io
import json
import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.analyzers.registry import get_display_name
from app.core.exceptions import NotFoundError
from app.repositories import task_repo

logger = logging.getLogger(__name__)

# 严重程度 → 优先级映射
_SEV_PRIORITY = {"S0": "P0-紧急", "S1": "P1-高", "S2": "P2-中", "S3": "P3-低"}


def _findings_to_testcases(
    task_id: str,
    all_findings: list[dict[str, Any]],
    ai_data: dict[str, Any],
) -> list[dict[str, Any]]:
    """将发现转换为结构化测试用例建议。"""
    cases: list[dict[str, Any]] = []
    tc_id = 0

    for f in all_findings:
        tc_id += 1
        module = f.get("module_id", "")
        risk_type = f.get("risk_type", "")

        # 基于风险类型生成测试目标
        objective = _risk_type_to_objective(risk_type, f)
        preconditions = _risk_type_to_preconditions(risk_type, f)
        steps = _risk_type_to_steps(risk_type, f)
        expected = _risk_type_to_expected(risk_type, f)

        case = {
            "test_case_id": f"TC-{task_id[-8:]}-{tc_id:04d}",
            "source_finding_id": f.get("finding_id", ""),
            "module_id": module,
            "module_display_name": get_display_name(module),
            "priority": _SEV_PRIORITY.get(f.get("severity", "S3"), "P3-低"),
            "category": risk_type,
            "title": f.get("title", ""),
            "objective": objective,
            "preconditions": preconditions,
            "test_steps": steps,
            "expected_result": expected,
            "target_file": f.get("file_path", ""),
            "target_function": f.get("symbol_name", ""),
            "line_start": f.get("line_start", 0),
            "line_end": f.get("line_end", 0),
            "risk_score": f.get("risk_score", 0),
            "evidence": f.get("evidence", {}),
        }
        cases.append(case)

    return cases


def _risk_type_to_objective(risk_type: str, finding: dict) -> str:
    """根据风险类型生成测试目标。"""
    sym = finding.get("symbol_name", "目标函数")
    mapping = {
        "branch_error": f"验证 {sym} 中的错误处理分支是否正确触发和处理",
        "branch_cleanup": f"验证 {sym} 中的清理路径是否释放所有资源",
        "branch_boundary": f"验证 {sym} 中的边界条件分支是否正确处理边界值",
        "branch_normal": f"验证 {sym} 的正常执行路径",
        "boundary_miss": f"测试 {sym} 中约束条件的边界值",
        "invalid_input_gap": f"验证 {sym} 中数组/缓冲区访问的输入校验",
        "missing_cleanup": f"验证 {sym} 在错误路径上是否正确释放所有资源",
        "inconsistent_errno_mapping": f"验证 {sym} 中的错误码映射是否一致",
        "silent_error_swallow": f"验证 {sym} 中的错误是否被静默吞没",
        "race_write_without_lock": f"验证 {sym} 中共享变量访问的线程安全性",
        "lock_order_inversion": f"验证 {sym} 中锁获取是否存在死锁风险",
        "atomicity_gap": f"验证 {sym} 中的锁是否在所有路径上正确释放",
        "changed_core_path": f"对修改的函数 {sym} 进行回归测试",
        "transitive_impact": f"对受上游变更影响的函数 {sym} 进行回归测试",
        "high_risk_low_coverage": f"提高高风险文件/函数 {sym} 的测试覆盖率",
        "critical_path_uncovered": f"为未覆盖的关键函数 {sym} 增加测试覆盖",
        "high_fan_out": f"对高影响力枢纽函数 {sym} 进行集成测试",
        "deep_impact_surface": f"验证函数 {sym} 的契约稳定性（被多个调用者依赖）",
    }
    return mapping.get(risk_type, f"验证 {sym} 中与 {risk_type} 相关的行为")


def _risk_type_to_preconditions(risk_type: str, finding: dict) -> list[str]:
    """根据风险类型生成前置条件。"""
    preconditions = ["系统处于正常运行状态"]
    ev = finding.get("evidence", {})

    if "cleanup" in risk_type or "missing_cleanup" in risk_type:
        resources = ev.get("cleanup_resources_expected", [])
        if resources:
            preconditions.append(f"需要跟踪的资源: {resources}")
    if "lock" in risk_type or "race" in risk_type:
        preconditions.append("多线程执行环境")
    if "boundary" in risk_type:
        preconditions.append("已准备输入校验边界条件")
    if "diff" in risk_type or "changed" in risk_type or "transitive" in risk_type:
        preconditions.append("有可用的上一版本基线进行比较")

    return preconditions


def _risk_type_to_steps(risk_type: str, finding: dict) -> list[str]:
    """根据风险类型和证据生成测试步骤。"""
    ev = finding.get("evidence", {})
    sym = finding.get("symbol_name", "目标函数")
    steps = []

    if "boundary" in risk_type:
        candidates = ev.get("candidates", [])
        expr = ev.get("constraint_expr", "")
        steps.append(f"1. 识别约束条件: {expr}")
        if candidates:
            steps.append(f"2. 准备边界测试值: {candidates}")
        steps.append(f"3. 使用每个候选值调用 {sym}")
        steps.append("4. 验证每种情况下的返回值和副作用")
    elif "cleanup" in risk_type or "missing_cleanup" in risk_type:
        expected_res = ev.get("cleanup_resources_expected", [])
        steps.append(f"1. 设置资源跟踪: {expected_res}")
        steps.append(f"2. 使用触发错误路径的参数调用 {sym}")
        steps.append("3. 在资源分配/IO 点注入失败")
        steps.append("4. 验证错误后所有跟踪的资源已释放")
    elif "race" in risk_type or "lock" in risk_type:
        shared = ev.get("shared_symbol", "")
        steps.append(f"1. 启动并发线程访问 {shared or sym}")
        steps.append("2. 运行交叉操作的压力测试")
        steps.append("3. 使用线程检测工具（TSan）或手动竞态检测")
        steps.append("4. 验证无数据损坏或死锁")
    elif "changed" in risk_type or "transitive" in risk_type:
        impacted = ev.get("impacted_symbols", [])[:5]
        steps.append(f"1. 审查 {sym} 的变更内容")
        steps.append(f"2. 运行 {sym} 的已有测试")
        if impacted:
            steps.append(f"3. 对受影响的调用者运行回归测试: {impacted}")
        steps.append("4. 验证功能行为符合规范")
    else:
        steps.append(f"1. 搭建 {sym} 的测试环境")
        steps.append(f"2. 使用代表性输入调用 {sym}")
        steps.append("3. 验证预期行为和返回值")
        steps.append("4. 检查资源泄漏和错误处理")

    return steps


def _risk_type_to_expected(risk_type: str, finding: dict) -> str:
    """生成预期结果描述。"""
    mapping = {
        "boundary_miss": "函数正确处理所有边界值，无崩溃或数据损坏",
        "invalid_input_gap": "非法索引被拒绝；无缓冲区溢出或越界访问",
        "missing_cleanup": "在每条错误路径上所有已分配的资源均已释放",
        "inconsistent_errno_mapping": "每条错误路径返回正确的、文档记录的错误码",
        "silent_error_swallow": "所有错误均正确传播给调用者",
        "race_write_without_lock": "并发访问下未检测到数据竞态",
        "lock_order_inversion": "所有锁序组合下的并发执行无死锁",
        "atomicity_gap": "在所有代码路径（包括错误路径）上锁均正确释放",
        "changed_core_path": "修改后的函数行为与规范一致",
        "transitive_impact": "上游变更后调用函数继续正常工作",
    }
    return mapping.get(risk_type, "函数行为正确且优雅地处理边界情况")


def export_json(db: Session, task_id: str) -> str:
    """导出任务发现为结构化 JSON 测试用例。"""
    task = task_repo.get_task_by_id(db, task_id)
    if task is None:
        raise NotFoundError(f"任务 {task_id} 未找到")

    results = task_repo.get_module_results(db, task.id)
    all_findings: list[dict] = []
    ai_data: dict[str, Any] = {}

    for r in results:
        if r.findings_json:
            findings = json.loads(r.findings_json)
            all_findings.extend(findings)
        if r.ai_summary_json:
            ai_data[r.module_id] = json.loads(r.ai_summary_json)

    cases = _findings_to_testcases(task_id, all_findings, ai_data)

    export = {
        "export_format": "grayscope_testcases_v1",
        "task_id": task_id,
        "project_id": task.project_id,
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "total_test_cases": len(cases),
        "aggregate_risk_score": task.aggregate_risk_score,
        "test_cases": cases,
    }
    return json.dumps(export, indent=2, ensure_ascii=False)


def export_csv(db: Session, task_id: str) -> str:
    """导出任务发现为 CSV 测试用例表。"""
    task = task_repo.get_task_by_id(db, task_id)
    if task is None:
        raise NotFoundError(f"任务 {task_id} 未找到")

    results = task_repo.get_module_results(db, task.id)
    all_findings: list[dict] = []
    ai_data: dict[str, Any] = {}

    for r in results:
        if r.findings_json:
            findings = json.loads(r.findings_json)
            all_findings.extend(findings)
        if r.ai_summary_json:
            ai_data[r.module_id] = json.loads(r.ai_summary_json)

    cases = _findings_to_testcases(task_id, all_findings, ai_data)

    output = io.StringIO()
    fieldnames = [
        "test_case_id", "priority", "module_id", "module_display_name", "category",
        "title", "objective", "target_file", "target_function",
        "line_start", "line_end", "risk_score",
        "preconditions", "test_steps", "expected_result",
    ]
    writer = csv.DictWriter(output, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()

    for c in cases:
        row = dict(c)
        # 列表字段展平为文本
        row["preconditions"] = "; ".join(c.get("preconditions", []))
        row["test_steps"] = "; ".join(c.get("test_steps", []))
        writer.writerow(row)

    return output.getvalue()


def export_findings_json(db: Session, task_id: str) -> str:
    """导出所有模块的原始发现 JSON。"""
    task = task_repo.get_task_by_id(db, task_id)
    if task is None:
        raise NotFoundError(f"任务 {task_id} 未找到")

    results = task_repo.get_module_results(db, task.id)
    modules_data = []
    for r in results:
        findings = json.loads(r.findings_json) if r.findings_json else []
        metrics = json.loads(r.metrics_json) if r.metrics_json else {}
        ai_summary = json.loads(r.ai_summary_json) if r.ai_summary_json else {}
        modules_data.append({
            "module_id": r.module_id,
            "display_name": get_display_name(r.module_id),
            "status": r.status,
            "risk_score": r.risk_score,
            "findings": findings,
            "metrics": metrics,
            "ai_summary": ai_summary,
        })

    export = {
        "export_format": "grayscope_findings_v1",
        "task_id": task_id,
        "project_id": task.project_id,
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "aggregate_risk_score": task.aggregate_risk_score,
        "modules": modules_data,
    }
    return json.dumps(export, indent=2, ensure_ascii=False)
