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
from app.utils.data import flatten_list as _flatten_list

logger = logging.getLogger(__name__)


def _get_covered_set(db: Session, task_primary_id: int) -> set[tuple[str, str]]:
    """从任务最近一次覆盖率导入中得到 (file_path, function_name) 已覆盖集合。"""
    from app.repositories.coverage_import_repo import get_latest_payload_by_task_id

    out: set[tuple[str, str]] = set()
    result = get_latest_payload_by_task_id(db, task_primary_id)
    if not result:
        return out
    payload, fmt = result
    if fmt == "summary":
        for path, data in (payload.get("files") or {}).items():
            funcs = data.get("functions") or {}
            for fn, hit in funcs.items():
                if hit:
                    out.add((path, fn))
    return out


def _get_cross_module_critical_combinations(task) -> list[dict]:
    """从任务的 error_json 扩展中读取跨模块 AI 产出的多函数交汇临界点。"""
    if not task or not task.error_json:
        return []
    try:
        data = json.loads(task.error_json)
        cross = data.get("cross_module_ai") or {}
        suggestions = cross.get("test_suggestions") or []
    except (json.JSONDecodeError, TypeError):
        return []
    out = []
    for s in suggestions:
        if not isinstance(s, dict):
            continue
        if s.get("type") == "critical_combination" or (
            (s.get("related_functions") or s.get("scenario_brief"))
        ):
            out.append(s)
    return out


def _critical_combination_to_export_item(
    cc: dict, index: int, task_id: str
) -> dict:
    """将一条 critical_combination 转为导出结构，含建议步骤与 fault_window。"""
    related = cc.get("related_functions") or []
    scenario = cc.get("scenario_brief") or ""
    expected_outcome = (
        cc.get("expected_outcome")
        or cc.get("expected_failure")
        or "按规格成功完成或可接受失败"
    )
    unacceptable = cc.get("unacceptable_outcomes") or []
    if isinstance(unacceptable, str):
        unacceptable = [s.strip() for s in unacceptable.split(";") if s.strip()]

    # 建议步骤：从关联函数与场景生成
    steps = []
    if related:
        steps.append(f"1. 构造同时涉及以下函数/分支的执行场景: {', '.join(related[:5])}")
    if scenario:
        steps.append(f"2. 场景要点: {scenario}")
    steps.append("3. 按上述场景执行（可结合故障注入或边界输入）")
    steps.append("4. 验证出现预期结果且未出现不可接受结果")

    fault_window = {
        "after": "进入上述关联函数交汇的执行路径",
        "before": "相关调用链/分支执行完毕",
        "method": "在交汇点注入故障或构造边界输入，观察预期结果与不可接受结果",
    }

    return {
        "id": f"CC-{task_id[-8:]}-{index:04d}",
        "related_functions": related,
        "expected_outcome": expected_outcome,
        "unacceptable_outcomes": unacceptable,
        "scenario_brief": scenario,
        "suggested_steps": steps,
        "fault_window": fault_window,
        "performance_requirement": cc.get("performance_requirement") or "",
    }

# 严重程度 → 优先级映射
_SEV_PRIORITY = {"S0": "P0-紧急", "S1": "P1-高", "S2": "P2-中", "S3": "P3-低"}


def get_diff_impact_affected_symbols(module_results: list) -> set[str]:
    """从任务的 diff_impact 模块结果中提取受变更影响的符号集合，供增量测试生成。"""
    out: set[str] = set()
    for mr in module_results or []:
        if getattr(mr, "module_id", None) != "diff_impact" or not getattr(mr, "findings_json", None):
            continue
        try:
            findings = json.loads(mr.findings_json)
        except (TypeError, json.JSONDecodeError):
            continue
        for f in findings:
            sym = f.get("symbol_name", "")
            if sym:
                out.add(sym)
            ev = f.get("evidence", {}) or {}
            for name in ev.get("impacted_callers") or []:
                if name:
                    out.add(name)
            for name in ev.get("impacted_callees") or []:
                if name:
                    out.add(name)
    return out


def _findings_to_testcases(
    task_id: str,
    all_findings: list[dict[str, Any]],
    ai_data: dict[str, Any],
    symbol_to_related: dict[str, list[str]] | None = None,
    affected_symbols: set[str] | None = None,
) -> list[dict[str, Any]]:
    """将发现转换为结构化测试用例建议。symbol_to_related 用于 P3：由 data_flow 为 boundary 等补全 related_functions。
    若提供 affected_symbols（来自 diff_impact），则仅保留 symbol_name 在该集合中的发现（增量测试生成）。"""
    if affected_symbols is not None:
        all_findings = [f for f in all_findings if (f.get("symbol_name") or "") in affected_symbols]
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

        execution_hint = _risk_type_to_execution_hint(risk_type, f)
        example_input = _risk_type_to_example_input(risk_type, f)
        fault_window = _risk_type_to_fault_window(risk_type, f)
        related_functions = _get_related_functions(f, symbol_to_related)
        expected_failure = _get_expected_failure(risk_type, f)
        unacceptable_outcomes = _get_unacceptable_outcomes(risk_type, f)
        performance_requirement = _get_performance_requirement(f)
        ev = f.get("evidence", {})
        expected_outcome = (
            ev.get("expected_outcome")
            or expected_failure
            or "按规格成功完成或可接受失败"
        )
        if related_functions:
            objective = _format_objective_with_related(objective, related_functions)
        expected = _append_expected_vs_unacceptable(expected, expected_failure, unacceptable_outcomes)
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
            "execution_hint": execution_hint,
            "example_input": example_input,
            "fault_window": fault_window,
            "related_functions": related_functions,
            "expected_outcome": expected_outcome,
            "expected_failure": expected_failure,
            "unacceptable_outcomes": unacceptable_outcomes,
            "performance_requirement": performance_requirement,
            "target_file": f.get("file_path", ""),
            "target_function": f.get("symbol_name", ""),
            "line_start": f.get("line_start", 0),
            "line_end": f.get("line_end", 0),
            "risk_score": f.get("risk_score", 0),
            "evidence": f.get("evidence", {}),
        }
        cases.append(case)

    # 按风险分降序、再按关联函数数量降序（高价值优先）
    cases.sort(
        key=lambda c: (
            -float(c.get("risk_score") or 0),
            -len(c.get("related_functions") or []),
        )
    )
    return cases


def _build_symbol_to_related_from_data_flow(module_results: list) -> dict[str, list[str]]:
    """P3: 从 data_flow / path_and_resource 等模块的 propagation_chain 构建 symbol -> related_functions。"""
    out: dict[str, list[str]] = {}
    for r in module_results or []:
        if not r.findings_json:
            continue
        try:
            findings = json.loads(r.findings_json)
        except (json.JSONDecodeError, TypeError):
            continue
        for f in findings:
            ev = f.get("evidence", {}) or {}
            chain = ev.get("propagation_chain") or []
            if not isinstance(chain, list) or len(chain) < 2:
                continue
            funcs = [s.get("function") for s in chain if isinstance(s, dict) and s.get("function")]
            if len(funcs) < 2:
                continue
            for fn in funcs:
                if fn and fn not in (out.get(fn) or []):
                    out.setdefault(fn, []).extend(x for x in funcs if x and x != fn)
    for k in out:
        out[k] = list(dict.fromkeys(out[k]))[:8]
    return out


def _get_related_functions(finding: dict, symbol_to_related: dict[str, list[str]] | None = None) -> list[str]:
    """从 evidence 提取关联函数列表（多函数交汇临界点）。优先显式字段，否则从调用链/数据流推导；P3 可用 symbol_to_related 补全 boundary 等。"""
    ev = finding.get("evidence", {})
    related = ev.get("related_functions") or ev.get("interaction_chain") or ev.get("cross_function_chain")
    if isinstance(related, list):
        out = [str(x) for x in related if x]
        if out:
            return out
    if isinstance(related, str):
        out = [s.strip() for s in related.split(",") if s.strip()]
        if out:
            return out
    sym = finding.get("symbol_name", "")
    # P3: 由 data_flow 传播链补全（如 boundary_value 等单符号发现）
    if symbol_to_related and sym and sym in symbol_to_related:
        cand = symbol_to_related[sym]
        if len(cand) >= 1:
            return [sym] + [x for x in cand if x != sym][:5]
    # 从 call_graph: callers + self + callees
    callers = ev.get("callers") or []
    callees = ev.get("callees") or []
    if isinstance(callers, list) and isinstance(callees, list):
        combined = list(dict.fromkeys([*callers[:3], sym, *callees[:3]]))
        if len(combined) > 1:
            return [x for x in combined if x]
    # 从 data_flow propagation_chain（本发现自身）
    chain = ev.get("propagation_chain") or []
    if isinstance(chain, list) and chain:
        funcs = [s.get("function") for s in chain if isinstance(s, dict) and s.get("function")]
        if len(funcs) > 1:
            return funcs[:6]
    return [sym] if sym else []


def _get_expected_failure(risk_type: str, finding: dict) -> str:
    """预期失败（灰盒：可接受的失败结果）。"""
    ev = finding.get("evidence", {})
    if ev.get("expected_failure"):
        return str(ev["expected_failure"])
    return _risk_type_to_expected_failure_default(risk_type, finding)


def _get_performance_requirement(finding: dict) -> str:
    """可选：性能/时序要求（如 响应时间 < 100ms），供存储/实时场景填写。"""
    ev = finding.get("evidence", {})
    return str(ev.get("performance_requirement", "") or "").strip()


def _get_unacceptable_outcomes(risk_type: str, finding: dict) -> list[str]:
    """不可接受结果（灰盒：一旦出现即缺陷）。"""
    ev = finding.get("evidence", {})
    out = ev.get("unacceptable_outcomes")
    if isinstance(out, list):
        return [str(x) for x in out if x]
    if isinstance(out, str):
        return [s.strip() for s in out.split(";") if s.strip()]
    return _risk_type_to_unacceptable_default(risk_type, finding)


def _risk_type_to_expected_failure_default(risk_type: str, finding: dict) -> str:
    sym = finding.get("symbol_name", "目标函数")
    defaults = {
        "missing_cleanup": "资源泄漏、句柄泄漏",
        "branch_error": "错误分支未正确触发或未返回预期错误码",
        "race_write_without_lock": "数据竞态、结果不确定",
        "lock_order_inversion": "死锁、线程卡死",
        "boundary_miss": "边界值未正确处理导致崩溃或错误结果",
        "invalid_input_gap": "越界访问、崩溃",
        "cross_function_resource_leak": "跨函数调用链上的资源泄漏",
    }
    return defaults.get(risk_type, f"{sym} 执行失败或返回错误码（预期内失败）")


def _risk_type_to_unacceptable_default(risk_type: str, finding: dict) -> list[str]:
    defaults = {
        "missing_cleanup": ["进程崩溃", "控制器异常", "不可恢复状态"],
        "race_write_without_lock": ["数据损坏", "崩溃", "死锁"],
        "lock_order_inversion": ["死锁", "系统挂起"],
        "boundary_miss": ["崩溃", "安全漏洞"],
        "invalid_input_gap": ["崩溃", "越界写"],
        "cross_function_resource_leak": ["进程崩溃", "资源耗尽"],
    }
    return defaults.get(risk_type, ["进程崩溃", "控制器下电", "不可恢复的错误状态"])


def _format_objective_with_related(objective: str, related_functions: list[str]) -> str:
    """在目标前加上关联函数，突出多函数交汇。"""
    funcs = "、".join(related_functions[:5])
    return f"关联函数: {funcs}。灰盒目标: 暴露多函数交汇临界点——{objective}"


def _append_expected_vs_unacceptable(
    expected: str | list,
    expected_failure: str,
    unacceptable_outcomes: list[str],
) -> str | list:
    """在预期结果后追加「预期失败」与「不可接受结果」，提升可读性。"""
    base = expected if isinstance(expected, str) else "；".join(expected) if isinstance(expected, list) else ""
    parts = [base] if base else []
    if expected_failure:
        parts.append(f"预期失败（可接受）: {expected_failure}")
    if unacceptable_outcomes:
        parts.append("不可接受结果: " + "；".join(unacceptable_outcomes))
    if len(parts) <= 1 and base:
        return expected
    return "；".join(parts)


def _risk_type_to_objective(risk_type: str, finding: dict) -> str:
    """根据风险类型生成测试目标。"""
    sym = finding.get("symbol_name", "目标函数")
    mapping = {
        "branch_error": f"验证 {sym} 中的错误处理分支是否正确触发和处理",
        "branch_cleanup": f"验证 {sym} 中的清理路径是否释放所有资源",
        "branch_boundary": f"验证 {sym} 中的边界条件分支是否正确处理边界值",
        "branch_normal": f"验证 {sym} 的正常执行路径",
        "branch_high_complexity": f"验证高分支数函数 {sym} 的深层路径覆盖（优先错误/清理路径，再边界组合）",
        "branch_switch_no_default": f"验证 {sym} 中 switch 对未列出 case 值的处理（缺 default 分支）",
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
    elif risk_type == "branch_high_complexity":
        branch_count = ev.get("branch_count", 0)
        steps.append(f"1. 通过内网覆盖率系统或本地覆盖率工具查看 {sym} 的未覆盖分支（共 {branch_count} 个分支）")
        steps.append("2. 优先为错误处理、资源清理路径补充用例")
        steps.append("3. 再为边界条件、状态判断补充边界组合输入")
        steps.append("4. 用覆盖率系统或工具确认关键路径已覆盖")
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
        "branch_high_complexity": "关键分支（尤其错误/清理路径）被覆盖，深层路径行为符合预期，无资源泄漏",
        "branch_switch_no_default": "switch 对未列出值有明确处理（或补充 default），无静默跳过或未定义行为",
    }
    return mapping.get(risk_type, "函数行为正确且优雅地处理边界情况")


def _risk_type_to_execution_hint(risk_type: str, finding: dict) -> str:
    """灰盒：执行建议（在什么环境、用什么方式执行）。"""
    sym = finding.get("symbol_name", "目标函数")
    hints = {
        "boundary_miss": f"在测试环境通过单元测试或 API 调用传入边界值，观察 {sym} 的返回与副作用。",
        "invalid_input_gap": "使用畸形输入（越界索引、超长字符串）从接口或 CLI 触发，确认被拒绝或安全处理。",
        "branch_error": "在测试环境中注入失败（如 malloc 失败），或构造触发错误分支的输入。",
        "missing_cleanup": "启用内存/句柄检测工具，运行触发错误路径的用例，确认无泄漏。",
        "race_write_without_lock": "多线程压力测试（可配合 TSan）在测试机执行。",
        "lock_order_inversion": "并发执行涉及该锁的多个线程，观察是否出现死锁。",
        "changed_core_path": "在测试环境运行该函数的现有用例及回归用例。",
        "transitive_impact": "运行受影响模块的集成/回归测试。",
        "branch_high_complexity": f"通过覆盖率系统或覆盖率工具查看 {sym} 未覆盖分支，优先补充错误/清理路径用例，再补充边界组合。",
    }
    return hints.get(risk_type, f"在测试环境按上述步骤执行，重点验证 {sym} 的行为与预期一致。")


def _risk_type_to_example_input(risk_type: str, finding: dict) -> str:
    """灰盒：示例输入（便于新手构造测试数据）。"""
    ev = finding.get("evidence", {})
    candidates = ev.get("candidates", [])
    if "boundary" in risk_type and candidates:
        return f"边界候选值: {candidates[:5]}"
    if risk_type == "invalid_input_gap":
        return "示例: 索引 -1、len、len+1；或超长缓冲区。"
    if "race" in risk_type or "lock" in risk_type:
        return "示例: 多线程同时调用同一接口，或交替调用不同接口。"
    return ""


def _risk_type_to_fault_window(risk_type: str, finding: dict) -> dict | None:
    """L3 故障注入窗口：after/before/method，便于测试人员确定注入时机与方式。"""
    sym = finding.get("symbol_name", "目标函数")
    line = finding.get("line_start") or finding.get("line_end") or 0
    loc = f"{finding.get('file_path', '')}:{sym}:L{line}" if line else f"{finding.get('file_path', '')}:{sym}"

    windows = {
        "branch_error": {"after": f"进入 {sym} 函数", "before": "错误分支执行完毕或返回", "method": "注入失败返回值或构造触发错误分支的输入"},
        "branch_cleanup": {"after": f"进入 {sym} 函数", "before": "清理标签执行完毕", "method": "触发错误路径使控制流经 goto 到达清理；或注入资源分配失败"},
        "branch_switch_no_default": {"after": f"进入 {sym} 函数", "before": "switch 语句执行完毕", "method": "向 switch 变量注入未列出的 case 值"},
        "branch_high_complexity": {"after": f"进入 {sym} 函数", "before": "函数返回", "method": "边界组合输入或注入使深层分支被执行"},
        "missing_cleanup": {"after": "资源分配点", "before": "函数返回或跳转清理", "method": "在分配后注入失败，验证清理路径"},
        "race_write_without_lock": {"after": "共享变量可见", "before": "临界区结束", "method": "多线程并发访问同一变量"},
        "lock_order_inversion": {"after": "获取第一把锁", "before": "释放第二把锁", "method": "另一线程以相反顺序获取锁"},
        "boundary_miss": {"after": f"调用 {sym} 前", "before": f"{sym} 返回", "method": "传入边界值、边界±1"},
        "invalid_input_gap": {"after": "输入进入校验逻辑前", "before": "数组/缓冲区访问", "method": "传入越界索引或超长输入"},
    }
    out = windows.get(risk_type)
    if out:
        return out
    if "branch_" in risk_type:
        return {"after": f"进入 {sym} 函数", "before": "该分支执行完毕", "method": "构造触发该分支的输入或注入"}
    return {"after": f"调用 {sym} 前", "before": f"{sym} 返回", "method": "按测试步骤执行"}


def export_json(db: Session, task_id: str) -> str:
    """导出任务发现为结构化 JSON 测试用例；含多函数交汇临界点区块。"""
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

    symbol_to_related = _build_symbol_to_related_from_data_flow(results)
    cases = _findings_to_testcases(task_id, all_findings, ai_data, symbol_to_related)
    critical_list = _get_cross_module_critical_combinations(task)
    critical_export = [
        _critical_combination_to_export_item(cc, i, task_id)
        for i, cc in enumerate(critical_list, 1)
    ]

    covered_set = _get_covered_set(db, task.id)
    for c in cases:
        c["covered"] = (c.get("target_file") or "", c.get("target_function") or "") in covered_set

    export = {
        "export_format": "grayscope_testcases_v1",
        "task_id": task_id,
        "project_id": task.project_id,
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "total_test_cases": len(cases),
        "critical_combinations_count": len(critical_export),
        "aggregate_risk_score": task.aggregate_risk_score,
        "critical_combinations": critical_export,
        "test_cases": cases,
    }
    return json.dumps(export, indent=2, ensure_ascii=False)


def export_csv(db: Session, task_id: str) -> str:
    """导出任务发现为 CSV 测试用例表；先多函数交汇临界点，再按发现生成的用例。"""
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

    symbol_to_related = _build_symbol_to_related_from_data_flow(results)
    cases = _findings_to_testcases(task_id, all_findings, ai_data, symbol_to_related)
    critical_list = _get_cross_module_critical_combinations(task)
    critical_export = [
        _critical_combination_to_export_item(cc, i, task_id)
        for i, cc in enumerate(critical_list, 1)
    ]
    covered_set = _get_covered_set(db, task.id)
    for c in cases:
        c["covered"] = (c.get("target_file") or "", c.get("target_function") or "") in covered_set

    output = io.StringIO()
    fieldnames = [
        "source", "test_case_id", "priority", "module_id", "module_display_name", "category",
        "title", "objective", "target_file", "target_function",
        "line_start", "line_end", "risk_score", "covered",
        "related_functions", "expected_outcome", "expected_failure", "unacceptable_outcomes",
        "performance_requirement",
        "preconditions", "test_steps", "expected_result",
        "execution_hint", "example_input", "scenario_brief",
    ]
    writer = csv.DictWriter(output, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()

    for c in critical_export:
        row = {
            "source": "critical_combination",
            "test_case_id": c.get("id", ""),
            "priority": "",
            "module_id": "",
            "module_display_name": "",
            "category": "",
            "title": c.get("scenario_brief", "多函数交汇临界点"),
            "objective": "验证多函数交汇时的预期结果且不出现不可接受结果",
            "target_file": "",
            "target_function": "",
            "line_start": "",
            "line_end": "",
            "risk_score": "",
            "related_functions": "; ".join(_flatten_list(c.get("related_functions", []))),
            "expected_outcome": c.get("expected_outcome", ""),
            "expected_failure": "",
            "unacceptable_outcomes": "; ".join(_flatten_list(c.get("unacceptable_outcomes", []))),
            "performance_requirement": c.get("performance_requirement", "") or "",
            "preconditions": "",
            "test_steps": "; ".join(_flatten_list(c.get("suggested_steps", []))),
            "expected_result": "",
            "execution_hint": str(c.get("fault_window", "")),
            "example_input": "",
            "scenario_brief": c.get("scenario_brief", ""),
            "covered": "",
        }
        writer.writerow(row)

    for c in cases:
        row = dict(c)
        row["source"] = "finding"
        row["covered"] = "是" if c.get("covered") else "否"
        row["preconditions"] = "; ".join(_flatten_list(c.get("preconditions", [])))
        row["test_steps"] = "; ".join(_flatten_list(c.get("test_steps", [])))
        exp = c.get("expected_result")
        row["expected_result"] = "; ".join(_flatten_list(exp)) if isinstance(exp, list) else (exp or "")
        row["related_functions"] = "; ".join(_flatten_list(c.get("related_functions", [])))
        row["expected_outcome"] = c.get("expected_outcome") or ""
        row["expected_failure"] = c.get("expected_failure") or ""
        row["unacceptable_outcomes"] = "; ".join(_flatten_list(c.get("unacceptable_outcomes", [])))
        row["execution_hint"] = c.get("execution_hint") or ""
        row["example_input"] = c.get("example_input") or ""
        row["scenario_brief"] = ""
        row["performance_requirement"] = c.get("performance_requirement") or ""
        writer.writerow(row)

    return output.getvalue()


def export_markdown(db: Session, task_id: str) -> str:
    """导出任务发现为可读的 Markdown 测试用例清单；先多函数交汇临界点，再按发现生成的用例。"""
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

    symbol_to_related = _build_symbol_to_related_from_data_flow(results)
    cases = _findings_to_testcases(task_id, all_findings, ai_data, symbol_to_related)
    critical_list = _get_cross_module_critical_combinations(task)
    critical_export = [
        _critical_combination_to_export_item(cc, i, task_id)
        for i, cc in enumerate(critical_list, 1)
    ]

    lines = [
        "# GrayScope 灰盒测试用例",
        "",
        f"**任务** {task_id} | **项目** {task.project_id} | **用例数** {len(cases)} | **交汇临界点** {len(critical_export)}",
        "",
        "以下步骤与预期可直接复制加入回归套件。",
        "",
        "---",
        "",
    ]

    if critical_export:
        lines.append("## 多函数交汇临界点")
        lines.append("")
        for i, c in enumerate(critical_export, 1):
            lines.append(f"### 交汇点 {i}")
            lines.append("")
            if c.get("related_functions"):
                lines.append(f"- **关联函数**: {', '.join(c['related_functions'])}")
            lines.append(f"- **预期结果（可成功或可接受失败）**: {c.get('expected_outcome', '')}")
            if c.get("unacceptable_outcomes"):
                lines.append(f"- **不可接受结果**: {'；'.join(c['unacceptable_outcomes'])}")
            if c.get("scenario_brief"):
                lines.append(f"- **场景**: {c['scenario_brief']}")
            if c.get("performance_requirement"):
                lines.append(f"- **性能/时序要求**: {c['performance_requirement']}")
            lines.append("")
            lines.append("#### 建议步骤")
            for s in c.get("suggested_steps", []):
                lines.append(f"- {s}")
            fw = c.get("fault_window", {})
            if fw:
                lines.append("")
                lines.append("#### 故障注入窗口")
                lines.append(f"- 时机 after: {fw.get('after', '')}")
                lines.append(f"- 时机 before: {fw.get('before', '')}")
                lines.append(f"- 方式: {fw.get('method', '')}")
            lines.append("")
            lines.append("---")
            lines.append("")
        lines.append("## 按发现生成的测试用例")
        lines.append("")

    for i, c in enumerate(cases, 1):
        lines.append(f"## {i}. {c.get('title', '未命名')}")
        lines.append("")
        lines.append(f"- **优先级**: {c.get('priority', '')} | **风险类型**: {c.get('category', '')}")
        lines.append(f"- **目标**: {c.get('objective', '')}")
        if c.get("related_functions"):
            lines.append(f"- **关联函数（交汇临界点）**: {', '.join(c['related_functions'])}")
        lines.append(f"- **预期结果（可成功或可接受失败）**: {c.get('expected_outcome', '')}")
        if c.get("expected_failure"):
            lines.append(f"- **预期失败（可接受）**: {c['expected_failure']}")
        if c.get("unacceptable_outcomes"):
            lines.append(f"- **不可接受结果**: {'；'.join(c['unacceptable_outcomes'])}")
        if c.get("performance_requirement"):
            lines.append(f"- **性能/时序要求**: {c['performance_requirement']}")
        lines.append("")
        lines.append("### 前置条件")
        for p in c.get("preconditions", []):
            lines.append(f"- {p}")
        lines.append("")
        lines.append("### 测试步骤")
        for s in c.get("test_steps", []):
            lines.append(f"- {s}")
        lines.append("")
        lines.append("### 预期结果")
        exp = c.get("expected_result")
        if isinstance(exp, list):
            for e in exp:
                lines.append(f"- {e}")
        else:
            lines.append(str(exp or ""))
        if c.get("execution_hint"):
            lines.append("")
            lines.append("### 如何执行")
            lines.append(c["execution_hint"])
        if c.get("example_input"):
            lines.append("")
            lines.append("### 示例数据")
            lines.append(c["example_input"])
        lines.append("")
        lines.append("---")
        lines.append("")
    return "\n".join(lines)


def export_critical_only(db: Session, task_id: str) -> str:
    """仅导出多函数交汇临界点（JSON），便于快速粘贴到测试管理系统。"""
    task = task_repo.get_task_by_id(db, task_id)
    if task is None:
        raise NotFoundError(f"任务 {task_id} 未找到")
    critical_list = _get_cross_module_critical_combinations(task)
    critical_export = [
        _critical_combination_to_export_item(cc, i, task_id)
        for i, cc in enumerate(critical_list, 1)
    ]
    out = {
        "export_format": "grayscope_critical_combinations_v1",
        "task_id": task_id,
        "project_id": task.project_id,
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "count": len(critical_export),
        "critical_combinations": critical_export,
    }
    return json.dumps(out, indent=2, ensure_ascii=False)


def export_html(db: Session, task_id: str) -> str:
    """导出单页 HTML 报告：汇总、多函数交汇临界点、发现数，便于分享与归档。"""
    task = task_repo.get_task_by_id(db, task_id)
    if task is None:
        raise NotFoundError(f"任务 {task_id} 未找到")
    results = task_repo.get_module_results(db, task.id)
    all_findings: list[dict] = []
    for r in results:
        if r.findings_json:
            try:
                all_findings.extend(json.loads(r.findings_json))
            except (json.JSONDecodeError, TypeError):
                pass
    critical_list = _get_cross_module_critical_combinations(task)
    critical_export = [
        _critical_combination_to_export_item(cc, i, task_id)
        for i, cc in enumerate(critical_list, 1)
    ]
    modules_ok = sum(1 for r in results if r.status == "success")
    modules_total = len(results)

    html_parts = [
        "<!DOCTYPE html><html lang='zh-CN'><head><meta charset='UTF-8'><meta name='viewport' content='width=device-width,initial-scale=1'>",
        "<title>GrayScope 报告 - " + _escape(task_id) + "</title>",
        "<style>",
        "body{font-family:system-ui,sans-serif;margin:1rem 2rem;background:#fafafa;}",
        "h1{color:#333;} .meta{color:#666;font-size:0.9rem;}",
        ".card{background:#fff;border-radius:8px;box-shadow:0 1px 3px rgba(0,0,0,0.08);padding:1rem;margin:1rem 0;}",
        ".cc-item{border-left:4px solid #4B9FD5;padding:0.5rem 0 0.5rem 0.75rem;margin:0.5rem 0;}",
        "ul{margin:0.25rem 0;} .tag{display:inline-block;background:#e3f2fd;padding:2px 6px;border-radius:4px;margin:2px;font-size:0.85rem;}",
        "</style></head><body>",
        "<h1>GrayScope 灰盒测试报告</h1>",
        f"<p class='meta'>任务 {_escape(task_id)} | 项目 {task.project_id} | "
        f"模块 {modules_ok}/{modules_total} 成功 | 发现 {len(all_findings)} 条 | 交汇临界点 {len(critical_export)}</p>",
        f"<p class='meta'>聚合风险分: {task.aggregate_risk_score or '-'}</p>",
        "<div class='card'><h2>多函数交汇临界点</h2>",
    ]
    if critical_export:
        for i, c in enumerate(critical_export, 1):
            funcs = ", ".join(_flatten_list(c.get("related_functions", [])))
            outcome = _escape(c.get("expected_outcome", ""))
            unacc = "；".join(_flatten_list(c.get("unacceptable_outcomes", [])))
            brief = _escape(c.get("scenario_brief", ""))
            perf = _escape(c.get("performance_requirement", "") or "")
            html_parts.append(
                f"<div class='cc-item'>"
                f"<strong>交汇点 {i}</strong>"
                f" {(' — ' + brief) if brief else ''}<br>"
                f"<span class='tag'>关联函数: {_escape(funcs)}</span><br>"
                f"预期结果: {outcome} | 不可接受: {_escape(unacc)}"
                f"{(' | 性能/时序: ' + perf) if perf else ''}"
                f"</div>"
            )
    else:
        html_parts.append("<p>暂无 AI 识别的多函数交汇临界点（需启用跨模块 AI 综合并完成分析）。</p>")
    html_parts.append("</div></body></html>")
    return "\n".join(html_parts)


def export_sfmea_csv(db: Session, task_id: str) -> str:
    """导出任务 SFMEA 条目为 CSV（RPN、严重度等）。"""
    from app.models.sfmea_entry import SfmeaEntry

    task = task_repo.get_task_by_id(db, task_id)
    if task is None:
        raise NotFoundError(f"任务 {task_id} 未找到")
    rows = db.query(SfmeaEntry).filter(SfmeaEntry.task_id == task.id).order_by(SfmeaEntry.id).all()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["id", "failure_mode", "severity", "occurrence", "detection", "rpn", "file_path", "symbol_name"])
    for r in rows:
        writer.writerow([
            r.id,
            r.failure_mode or "",
            r.severity if r.severity is not None else "",
            r.occurrence if r.occurrence is not None else "",
            r.detection if r.detection is not None else "",
            f"{r.rpn:.2f}" if r.rpn is not None else "",
            r.file_path or "",
            r.symbol_name or "",
        ])
    return output.getvalue()


def _escape(s: str) -> str:
    if not s:
        return ""
    return (
        str(s)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


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
