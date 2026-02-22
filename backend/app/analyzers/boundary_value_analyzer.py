"""边界值分析器（增强版）。

从 C/C++ AST 提取比较表达式和数组访问，
使用边界值分析方法推导边界测试候选项。
增强: 读取 data_flow 上游结果，为边界条件添加完整调用链上下文和攻击场景。
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

from app.analyzers.base import AnalyzeContext, ModuleResult
from app.analyzers.code_parser import CodeParser

logger = logging.getLogger(__name__)

MODULE_ID = "boundary_value"

_NUMERIC_RE = re.compile(r"\b(\d+)\b")
_ARRAY_ACCESS_RE = re.compile(r"(\w+)\s*\[([^\]]+)\]")

# ---- 基于正则精准提取比较表达式 ----
_COMPARISON_RE = re.compile(
    r"""
    ([\w.\->]+(?:\([^)]*\))?)\s*    # LHS: 变量/成员/函数调用
    (==|!=|<=|>=|(?<!<)<(?!<)|(?<!>)>(?!>))  # 操作符 (排除 << >>)
    \s*([\w.\->]+(?:\([^)]*\))?)    # RHS: 变量/常量/函数调用
    """,
    re.VERBOSE,
)


def analyze(ctx: AnalyzeContext) -> ModuleResult:
    workspace = ctx["workspace_path"]
    target = ctx["target"]
    options = ctx["options"]
    upstream = ctx["upstream_results"]
    target_path = Path(workspace) / target.get("path", "")
    max_files = options.get("max_files", 500)

    parser = CodeParser()
    findings: list[dict[str, Any]] = []
    warnings: list[str] = []
    total_functions = 0
    total_constraints = 0
    fid = 0

    # ── 从上游数据流结果提取传播链信息 ─────────────────────────────
    data_flow_chains = _extract_data_flow_chains(upstream)
    call_graph_data = _extract_call_graph_callers(upstream)

    if target_path.is_file():
        files = [target_path]
    elif target_path.is_dir():
        exts = {".c", ".h", ".cpp", ".cc", ".cxx", ".hpp"}
        files = sorted(
            [p for p in target_path.rglob("*") if p.suffix in exts and p.is_file()]
        )[:max_files]
    else:
        warnings.append(f"target path not found: {target_path}")
        return _result(findings, warnings, 0, 0, 0)

    for fpath in files:
        try:
            symbols = parser.parse_file(fpath)
        except Exception as exc:
            warnings.append(f"parse error {fpath}: {exc}")
            continue

        functions = [s for s in symbols if s.kind == "function"]
        total_functions += len(functions)

        for sym in functions:
            rel_path = str(fpath.relative_to(workspace)) if workspace else str(fpath)

            # Extract comparisons from source
            comparisons = _extract_comparisons(sym.source)
            total_constraints += len(comparisons)

            for comp in comparisons:
                fid += 1
                candidates = _derive_candidates(comp)

                # ── 增强: 查找涉及此变量的传播链 ──────────────────
                var_name = comp.get("var", "")
                propagation_context = _find_propagation_context(
                    sym.name, var_name, data_flow_chains
                )
                callers_context = call_graph_data.get(sym.name, [])

                # 构建增强的 evidence
                evidence: dict[str, Any] = {
                    "constraint_expr": comp["expr"],
                    "operator": comp.get("op", "?"),
                    "variable": var_name,
                    "bound_value": comp.get("bound", ""),
                    "candidates": candidates,
                    "expected_failure": "边界值或边界±1触发错误分支或越界",
                    "unacceptable_outcomes": ["越界", "溢出", "错误逻辑"],
                }

                # 添加传播链上下文
                if propagation_context:
                    chain = propagation_context
                    evidence["propagation_chain"] = chain["propagation_path"]
                    evidence["entry_function"] = chain.get("entry_function", "")
                    evidence["entry_param"] = chain.get("entry_param", "")
                    evidence["is_external_input"] = chain.get("is_external_input", False)
                    evidence["chain_depth"] = len(chain.get("propagation_path", []))

                    # 构建攻击场景描述
                    attack_scenario = _build_attack_scenario(
                        chain, comp, sym.name, candidates,
                    )
                    if attack_scenario:
                        evidence["attack_scenario"] = attack_scenario

                # 添加调用者上下文
                if callers_context:
                    evidence["callers"] = callers_context[:10]

                # 根据传播链调整风险评分和严重度
                base_risk = 0.65
                severity = "S2"
                title_suffix = ""

                if propagation_context:
                    chain_depth = len(propagation_context.get("propagation_path", []))
                    if chain_depth > 1:
                        base_risk += min(chain_depth * 0.03, 0.15)
                        title_suffix = f" (经{chain_depth}层调用传入)"
                    if propagation_context.get("is_external_input"):
                        base_risk += 0.1
                        severity = "S1"
                        title_suffix = f" (外部输入经{chain_depth}层调用传入)"

                base_risk = min(base_risk, 0.95)

                findings.append({
                    "finding_id": f"BV-F{fid:04d}",
                    "module_id": MODULE_ID,
                    "risk_type": "boundary_miss",
                    "severity": severity,
                    "risk_score": round(base_risk, 4),
                    "title": f"{sym.name}() 中的边界条件: {comp['expr']}{title_suffix}",
                    "description": _build_description(
                        sym.name, comp, candidates, propagation_context,
                    ),
                    "file_path": rel_path,
                    "symbol_name": sym.name,
                    "line_start": sym.line_start + comp.get("rel_line", 0),
                    "line_end": sym.line_start + comp.get("rel_line", 0),
                    "evidence": evidence,
                })

            # Array access analysis
            array_accesses = _extract_array_accesses(sym.source)
            for aa in array_accesses:
                fid += 1

                # 检查数组下标是否有传播链
                index_name = aa["index"].strip()
                propagation_context = _find_propagation_context(
                    sym.name, index_name, data_flow_chains
                )

                evidence_aa: dict[str, Any] = {
                    "array_name": aa["array"],
                    "index_expr": aa["index"],
                    "candidates": [0, -1, "max_size-1", "max_size", "max_size+1"],
                    "expected_failure": "非法下标经调用链传入导致越界",
                    "unacceptable_outcomes": ["缓冲区溢出", "段错误", "崩溃"],
                }

                if propagation_context:
                    evidence_aa["propagation_chain"] = propagation_context.get("propagation_path", [])
                    evidence_aa["entry_function"] = propagation_context.get("entry_function", "")
                    evidence_aa["entry_param"] = propagation_context.get("entry_param", "")
                    evidence_aa["is_external_input"] = propagation_context.get("is_external_input", False)

                base_risk = 0.7
                severity = "S2"
                if propagation_context and propagation_context.get("is_external_input"):
                    base_risk = 0.85
                    severity = "S1"

                findings.append({
                    "finding_id": f"BV-F{fid:04d}",
                    "module_id": MODULE_ID,
                    "risk_type": "invalid_input_gap",
                    "severity": severity,
                    "risk_score": round(base_risk, 4),
                    "title": f"{sym.name}() 中的数组越界风险: {aa['expr']}",
                    "description": (
                        f"函数 {sym.name}() 中数组「{aa['array']}」使用下标「{aa['index']}」进行访问。"
                        f"如果下标值超出数组边界，将导致缓冲区溢出或段错误。"
                        + (f"该下标来自外部输入（经过 {len(propagation_context.get('propagation_path', []))} 层调用），"
                           f"攻击者可以通过精心构造的输入触发越界访问。"
                           if propagation_context and propagation_context.get("is_external_input")
                           else "")
                        + f"推荐测试值：下标=0、max-1、max、max+1、-1。"
                    ),
                    "file_path": rel_path,
                    "symbol_name": sym.name,
                    "line_start": sym.line_start,
                    "line_end": sym.line_end,
                    "evidence": evidence_aa,
                })

    # ── 去重: 同一文件+行号+risk_type 仅保留风险最高的 finding ─────
    seen_keys: dict[tuple, int] = {}
    for idx, f in enumerate(findings):
        key = (f.get("file_path", ""), f.get("line_start", 0), f.get("risk_type", ""))
        if key not in seen_keys or f["risk_score"] > findings[seen_keys[key]]["risk_score"]:
            seen_keys[key] = idx
    findings = [findings[i] for i in sorted(seen_keys.values())]

    return _result(findings, warnings, total_functions, total_constraints, len(files))


def _build_description(
    func_name: str,
    comp: dict,
    candidates: list,
    propagation_context: dict | None,
) -> str:
    """构建增强的风险描述，包含调用链上下文。"""
    base = (
        f"函数 {func_name}() 中存在约束条件「{comp['expr']}」，"
        f"边界值附近是引发缓冲区溢出、数组越界、整数溢出等严重缺陷的高发区域。"
    )

    if propagation_context:
        chain = propagation_context.get("propagation_path", [])
        entry_fn = propagation_context.get("entry_function", "")
        entry_param = propagation_context.get("entry_param", "")
        is_external = propagation_context.get("is_external_input", False)

        if chain and len(chain) > 1:
            path_str = " → ".join(
                f"{s['function']}({s['param']})" for s in chain
            )
            base += (
                f"\n\n【调用链上下文】变量 '{comp.get('var', '')}' 的值来自 "
                f"{len(chain)} 层调用链: {path_str}。"
            )
            if is_external:
                base += f"入口参数 '{entry_param}' 来自外部输入，攻击者可控制。"

            # 标识变换
            transforms = [s for s in chain if s.get("transform", "none") != "none"]
            if transforms:
                base += f"经过的变换: " + ", ".join(
                    f"{t['function']}()中{t['transform']}({t.get('transform_expr', '')})"
                    for t in transforms[:3]
                ) + "。"

    base += (
        f"\n推荐使用以下候选测试值进行验证: {candidates}。"
        f"需要确认：(1) 边界值本身是否被正确处理；"
        f"(2) 边界值±1是否产生预期行为；"
        f"(3) 极端值（0、负数、最大值）是否被正确拒绝或处理。"
    )

    if propagation_context and len(propagation_context.get("propagation_path", [])) > 1:
        entry_fn = propagation_context.get("entry_function", "")
        base += (
            f"\n【端到端测试建议】从入口函数 {entry_fn}() 开始构造测试用例，"
            f"使入口参数经过整条调用链的变换后恰好触发此边界条件。"
        )

    return base


def _build_attack_scenario(
    chain: dict, comp: dict, func_name: str, candidates: list,
) -> str:
    """构建具体的攻击场景描述。"""
    path = chain.get("propagation_path", [])
    if len(path) < 2:
        return ""

    entry = path[0]
    transforms = [s for s in path if s.get("transform", "none") != "none"]

    scenario = (
        f"{entry['function']}({entry['param']}=<边界相关值>) 调用开始"
    )
    for step in path[1:]:
        if step.get("transform", "none") != "none":
            scenario += (
                f" → {step['function']}() 将 {step.get('transform_expr', step['param'])} "
                f"通过 {step['transform']} 变换"
            )
        else:
            scenario += f" → {step['function']}() 直接传递"

    scenario += f" → {func_name}() 处触发条件 {comp['expr']}"

    if candidates:
        bound_val = comp.get("bound", "")
        scenario += f"。需要反向推导使 {func_name}() 处 {comp.get('var', '')} 恰好等于 {bound_val} 时，入口参数的值"

    return scenario


def _extract_data_flow_chains(upstream: dict[str, dict]) -> list[dict]:
    """从上游 data_flow 结果中提取传播链。"""
    df_data = upstream.get("data_flow", {})
    findings = df_data.get("findings", [])

    chains = []
    for finding in findings:
        evidence = finding.get("evidence", {})
        chain = evidence.get("propagation_chain")
        if chain:
            chains.append({
                "propagation_path": chain,
                "entry_function": evidence.get("entry_function", ""),
                "entry_param": evidence.get("entry_param", ""),
                "is_external_input": evidence.get("is_external_input", False),
            })
    return chains


def _extract_call_graph_callers(upstream: dict[str, dict]) -> dict[str, list[str]]:
    """从上游 call_graph 结果中提取每个函数的调用者。"""
    cg_data = upstream.get("call_graph", {})
    callers_map: dict[str, list[str]] = {}
    for finding in cg_data.get("findings", []):
        ev = finding.get("evidence", {})
        sym = finding.get("symbol_name", "")
        if sym and ev.get("callers"):
            callers_map[sym] = ev["callers"]
    return callers_map


def _find_propagation_context(
    func_name: str, var_name: str, chains: list[dict],
) -> dict | None:
    """在传播链中查找涉及指定函数和变量的链。"""
    if not var_name or not chains:
        return None

    best_match = None
    best_depth = 0

    for chain in chains:
        path = chain.get("propagation_path", [])
        for step in path:
            if step.get("function") == func_name and step.get("param") == var_name:
                depth = len(path)
                if depth > best_depth:
                    best_match = chain
                    best_depth = depth
                break

    return best_match


def _extract_comparisons(source: str) -> list[dict]:
    """从函数源码中精确提取比较表达式。"""
    results = []
    lines = source.split("\n")

    for i, line in enumerate(lines):
        stripped = line.strip()

        if "=" in stripped and "==" not in stripped and "!=" not in stripped and "<=" not in stripped and ">=" not in stripped:
            if "<" not in stripped and ">" not in stripped:
                continue

        for m in _COMPARISON_RE.finditer(stripped):
            lhs = m.group(1).strip()
            op = m.group(2).strip()
            rhs = m.group(3).strip()

            if op == ">" and lhs.endswith("-"):
                continue
            if op == ">" and lhs.endswith("- "):
                continue
            if not re.search(r"\w", lhs) or not re.search(r"\w", rhs):
                continue

            if op in ("<", ">") and not re.search(r"\b(if|while|for|switch|return|assert)\b", stripped):
                if not re.search(r"\b(size|len|count|num|idx|capacity|offset)\b", lhs, re.I):
                    continue

            if stripped.startswith("#"):
                continue
            if "include" in stripped:
                continue

            expr = f"{lhs} {op} {rhs}"
            results.append({
                "expr": expr,
                "var": lhs,
                "op": op,
                "bound": rhs,
                "rel_line": i,
            })

    seen = set()
    unique = []
    for r in results:
        key = r["expr"]
        if key not in seen:
            seen.add(key)
            unique.append(r)
    return unique


def _extract_array_accesses(source: str) -> list[dict]:
    """Extract array index accesses."""
    results = []
    seen = set()
    for m in _ARRAY_ACCESS_RE.finditer(source):
        key = (m.group(1), m.group(2).strip())
        if key not in seen:
            seen.add(key)
            results.append({
                "expr": m.group(0),
                "array": m.group(1),
                "index": m.group(2).strip(),
            })
    return results


def _derive_candidates(comp: dict) -> list:
    """Derive boundary test candidate values from a comparison."""
    bound_str = comp.get("bound", "")
    nums = _NUMERIC_RE.findall(bound_str)
    if nums:
        val = int(nums[0])
        return [val - 1, val, val + 1, 0, -1]
    return [0, 1, -1, f"{bound_str}-1", bound_str, f"{bound_str}+1"]


def _result(
    findings: list, warnings: list, funcs: int, constraints: int, files: int
) -> ModuleResult:
    risk = round(sum(f["risk_score"] for f in findings) / len(findings), 4) if findings else 0.0
    return {
        "module_id": MODULE_ID,
        "status": "success",
        "risk_score": risk,
        "findings": findings,
        "metrics": {
            "files_scanned": files,
            "functions_scanned": funcs,
            "constraints_found": constraints,
            "findings_count": len(findings),
        },
        "artifacts": [],
        "warnings": warnings,
    }
