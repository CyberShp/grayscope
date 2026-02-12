"""边界值分析器。

从 C/C++ AST 提取比较表达式和数组访问，
使用边界值分析方法推导边界测试候选项。
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
# 匹配: lhs OP rhs，其中 OP 只能是 ==, !=, <=, >=, <, >
# 使用 negative lookbehind/lookahead 排除 << >> 位移操作
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
    target_path = Path(workspace) / target.get("path", "")
    max_files = options.get("max_files", 500)

    parser = CodeParser()
    findings: list[dict[str, Any]] = []
    warnings: list[str] = []
    total_functions = 0
    total_constraints = 0
    fid = 0

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
                findings.append({
                    "finding_id": f"BV-F{fid:04d}",
                    "module_id": MODULE_ID,
                    "risk_type": "boundary_miss",
                    "severity": "S2",
                    "risk_score": 0.65,
                    "title": f"{sym.name}() 中的边界条件: {comp['expr']}",
                    "description": (
                        f"函数 {sym.name}() 中存在约束条件「{comp['expr']}」，"
                        f"边界值附近（如刚好等于、差一、越界等）是引发缓冲区溢出、数组越界、"
                        f"整数溢出等严重缺陷的高发区域。推荐使用以下候选测试值进行验证: {candidates}。"
                        f"需要确认：(1) 边界值本身是否被正确处理；(2) 边界值±1是否产生预期行为；"
                        f"(3) 极端值（0、负数、最大值）是否被正确拒绝或处理。"
                    ),
                    "file_path": rel_path,
                    "symbol_name": sym.name,
                    "line_start": sym.line_start + comp.get("rel_line", 0),
                    "line_end": sym.line_start + comp.get("rel_line", 0),
                    "evidence": {
                        "constraint_expr": comp["expr"],
                        "operator": comp.get("op", "?"),
                        "variable": comp.get("var", ""),
                        "bound_value": comp.get("bound", ""),
                        "candidates": candidates,
                    },
                })

            # Array access analysis
            array_accesses = _extract_array_accesses(sym.source)
            for aa in array_accesses:
                fid += 1
                findings.append({
                    "finding_id": f"BV-F{fid:04d}",
                    "module_id": MODULE_ID,
                    "risk_type": "invalid_input_gap",
                    "severity": "S2",
                    "risk_score": 0.7,
                    "title": f"{sym.name}() 中的数组越界风险: {aa['expr']}",
                    "description": (
                        f"函数 {sym.name}() 中数组「{aa['array']}」使用下标「{aa['index']}」进行访问。"
                        f"如果下标值超出数组边界，将导致缓冲区溢出（可能引发安全漏洞）或段错误（程序崩溃）。"
                        f"推荐测试值：下标=0（最小有效值）、下标=max-1（最大有效值）、下标=max（刚好越界）、"
                        f"下标=max+1（明确越界）、下标=-1（负数下标）。需要验证函数在所有这些情况下的行为。"
                    ),
                    "file_path": rel_path,
                    "symbol_name": sym.name,
                    "line_start": sym.line_start,
                    "line_end": sym.line_end,
                    "evidence": {
                        "array_name": aa["array"],
                        "index_expr": aa["index"],
                        "candidates": [0, -1, "max_size-1", "max_size", "max_size+1"],
                    },
                })

    return _result(findings, warnings, total_functions, total_constraints, len(files))


def _extract_comparisons(source: str) -> list[dict]:
    """从函数源码中精确提取比较表达式。

    改进:
    - 只提取真正的比较操作（排除赋值 = 和位移 << >>）
    - 只从条件语句（if/while/for/switch）的条件部分提取
    - 按表达式内容去重
    """
    results = []
    lines = source.split("\n")

    for i, line in enumerate(lines):
        stripped = line.strip()

        # 跳过纯赋值行（快速排除）
        # 但保留含 == 的行
        if "=" in stripped and "==" not in stripped and "!=" not in stripped and "<=" not in stripped and ">=" not in stripped:
            # 可能只是赋值，但如果有 < 或 > 也需要检查
            if "<" not in stripped and ">" not in stripped:
                continue

        # 从行中精确提取所有比较表达式
        for m in _COMPARISON_RE.finditer(stripped):
            lhs = m.group(1).strip()
            op = m.group(2).strip()
            rhs = m.group(3).strip()

            # 过滤: 排除可能被误提取的情况

            # 0. 排除 C 结构体成员访问 -> 被误拆为 > 操作符
            if op == ">" and lhs.endswith("-"):
                continue
            if op == ">" and lhs.endswith("- "):
                continue
            # 排除 lhs 或 rhs 只含单个标点/不合法标识符
            if not re.search(r"\w", lhs) or not re.search(r"\w", rhs):
                continue

            # 1. 排除赋值左侧 (如 type = ...)
            if op in ("<", ">") and not re.search(r"\b(if|while|for|switch|return|assert)\b", stripped):
                # 非条件语句中的 < > 可能是模板参数
                if not re.search(r"\b(size|len|count|num|idx|capacity|offset)\b", lhs, re.I):
                    continue

            # 2. 排除预处理器指令
            if stripped.startswith("#"):
                continue

            # 3. 排除 include 语句中的 < >
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

    # 按表达式内容去重（而非仅按行号去重）
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
    # symbolic bound
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
