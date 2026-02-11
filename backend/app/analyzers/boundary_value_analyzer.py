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

# AST node types that represent comparisons
_COMPARISON_OPS = {"<", "<=", ">", ">=", "==", "!="}

# Patterns for extracting numeric constraints
_NUMERIC_RE = re.compile(r"\b(\d+)\b")
_SIZE_COMPARE_RE = re.compile(
    r"(size|len|length|count|num|idx|index|offset|capacity)\s*([<>=!]+)\s*(\w+)",
    re.IGNORECASE,
)
_ARRAY_ACCESS_RE = re.compile(r"(\w+)\s*\[([^\]]+)\]")


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
                    "title": f"Boundary condition in {sym.name}: {comp['expr']}",
                    "description": (
                        f"Constraint: {comp['expr']}. "
                        f"Test candidates: {candidates}"
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
                    "title": f"Array access in {sym.name}: {aa['expr']}",
                    "description": (
                        f"Array '{aa['array']}' accessed with index '{aa['index']}'. "
                        "Test with: 0, max-1, max, max+1, negative"
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
    """Extract comparison expressions from function source."""
    results = []
    for i, line in enumerate(source.split("\n")):
        # Named-variable comparisons
        for m in _SIZE_COMPARE_RE.finditer(line):
            results.append({
                "expr": m.group(0).strip(),
                "var": m.group(1),
                "op": m.group(2),
                "bound": m.group(3),
                "rel_line": i,
            })
        # Generic comparisons: look for if/while conditions with operators
        if re.search(r"\b(if|while|for)\s*\(", line):
            for op in _COMPARISON_OPS:
                if op in line:
                    expr = line.strip().lstrip("if").lstrip("while").strip("(){")
                    results.append({
                        "expr": expr.strip()[:80],
                        "var": "",
                        "op": op,
                        "bound": "",
                        "rel_line": i,
                    })
                    break  # one per line
    # deduplicate by (rel_line)
    seen = set()
    unique = []
    for r in results:
        key = r["rel_line"]
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
