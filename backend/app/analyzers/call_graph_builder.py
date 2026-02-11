"""调用图构建器。

从 C/C++ 源码构建函数级有向调用图，
提供调用者/被调者查询助手，识别高扇出或深影响函数。
"""

from __future__ import annotations

import json
import logging
import re
from collections import defaultdict
from pathlib import Path
from typing import Any

from app.analyzers.base import AnalyzeContext, ModuleResult
from app.analyzers.code_parser import CodeParser

logger = logging.getLogger(__name__)

MODULE_ID = "call_graph"

# Regex to extract function calls from source code
_CALL_RE = re.compile(r"\b([a-zA-Z_]\w*)\s*\(")
# C keywords and common macros to ignore
_IGNORE = {
    "if", "else", "while", "for", "switch", "case", "return", "sizeof",
    "typeof", "defined", "do", "goto", "break", "continue", "struct",
    "union", "enum", "typedef", "static", "extern", "inline", "const",
    "volatile", "register", "auto", "void", "int", "char", "short",
    "long", "float", "double", "unsigned", "signed", "bool",
    "printf", "fprintf", "sprintf", "snprintf", "assert",
    "NULL", "TRUE", "FALSE", "true", "false",
}


class CallGraph:
    """Directed call graph with query helpers."""

    def __init__(self) -> None:
        self.edges: dict[str, set[str]] = defaultdict(set)  # caller -> callees
        self.reverse: dict[str, set[str]] = defaultdict(set)  # callee -> callers
        self.nodes: set[str] = set()  # all known function symbols

    def add_edge(self, caller: str, callee: str) -> None:
        self.edges[caller].add(callee)
        self.reverse[callee].add(caller)
        self.nodes.add(caller)
        self.nodes.add(callee)

    def get_callees(self, fn: str, depth: int = 1) -> set[str]:
        result: set[str] = set()
        frontier = {fn}
        for _ in range(depth):
            next_frontier: set[str] = set()
            for f in frontier:
                for callee in self.edges.get(f, set()):
                    if callee not in result and callee != fn:
                        result.add(callee)
                        next_frontier.add(callee)
            frontier = next_frontier
        return result

    def get_callers(self, fn: str, depth: int = 1) -> set[str]:
        result: set[str] = set()
        frontier = {fn}
        for _ in range(depth):
            next_frontier: set[str] = set()
            for f in frontier:
                for caller in self.reverse.get(f, set()):
                    if caller not in result and caller != fn:
                        result.add(caller)
                        next_frontier.add(caller)
            frontier = next_frontier
        return result

    def fan_out(self, fn: str) -> int:
        return len(self.edges.get(fn, set()))

    def fan_in(self, fn: str) -> int:
        return len(self.reverse.get(fn, set()))

    def to_dict(self) -> dict:
        return {
            "nodes": [{"symbol": n} for n in sorted(self.nodes)],
            "edges": [
                {"src": caller, "dst": callee}
                for caller, callees in sorted(self.edges.items())
                for callee in sorted(callees)
            ],
        }


def build_callgraph(workspace: str, target_path: Path, max_files: int = 500) -> tuple[CallGraph, list[str]]:
    """Build call graph from source files, return (graph, warnings)."""
    parser = CodeParser()
    cg = CallGraph()
    warnings: list[str] = []

    if target_path.is_file():
        files = [target_path]
    elif target_path.is_dir():
        exts = {".c", ".h", ".cpp", ".cc", ".cxx", ".hpp"}
        files = sorted(
            [p for p in target_path.rglob("*") if p.suffix in exts and p.is_file()]
        )[:max_files]
    else:
        warnings.append(f"target path not found: {target_path}")
        return cg, warnings

    # Pass 1: collect defined functions
    defined_functions: set[str] = set()
    function_sources: list[tuple[str, str]] = []  # (name, source)

    for fpath in files:
        try:
            symbols = parser.parse_file(fpath)
        except Exception as exc:
            warnings.append(f"parse error {fpath}: {exc}")
            continue
        for sym in symbols:
            if sym.kind == "function":
                defined_functions.add(sym.name)
                function_sources.append((sym.name, sym.source))

    # Pass 2: extract call edges
    for fn_name, fn_source in function_sources:
        calls = _extract_calls(fn_source)
        for callee in calls:
            if callee != fn_name and callee in defined_functions:
                cg.add_edge(fn_name, callee)

    return cg, warnings


def _extract_calls(source: str) -> set[str]:
    """Extract function call names from source code."""
    calls = set()
    for m in _CALL_RE.finditer(source):
        name = m.group(1)
        if name not in _IGNORE and not name.isupper():  # skip macros
            calls.add(name)
    return calls


def analyze(ctx: AnalyzeContext) -> ModuleResult:
    """运行调用图分析。"""
    workspace = ctx["workspace_path"]
    target = ctx["target"]
    options = ctx["options"]
    target_path = Path(workspace) / target.get("path", "")
    max_files = options.get("max_files", 500)

    cg, warnings = build_callgraph(workspace, target_path, max_files)

    findings: list[dict[str, Any]] = []
    fid = 0

    # Find high fan-out functions (potential impact hubs)
    for fn in sorted(cg.nodes):
        fo = cg.fan_out(fn)
        fi = cg.fan_in(fn)

        if fo >= 8:
            fid += 1
            findings.append({
                "finding_id": f"CG-F{fid:04d}",
                "module_id": MODULE_ID,
                "risk_type": "high_fan_out",
                "severity": "S2",
                "risk_score": min(0.5 + fo * 0.03, 0.9),
                "title": f"High fan-out: {fn} calls {fo} functions",
                "description": (
                    f"Function {fn} has fan-out={fo}. Changes to callees "
                    "may have wide impact."
                ),
                "file_path": "",
                "symbol_name": fn,
                "line_start": 0,
                "line_end": 0,
                "evidence": {
                    "fan_out": fo,
                    "fan_in": fi,
                    "callees": sorted(cg.edges.get(fn, set()))[:20],
                },
            })

        if fi >= 10:
            fid += 1
            findings.append({
                "finding_id": f"CG-F{fid:04d}",
                "module_id": MODULE_ID,
                "risk_type": "deep_impact_surface",
                "severity": "S2",
                "risk_score": min(0.5 + fi * 0.02, 0.85),
                "title": f"High fan-in: {fn} called by {fi} functions",
                "description": (
                    f"Function {fn} has fan-in={fi}. Changes to this function "
                    "may impact many callers."
                ),
                "file_path": "",
                "symbol_name": fn,
                "line_start": 0,
                "line_end": 0,
                "evidence": {
                    "fan_out": fo,
                    "fan_in": fi,
                    "callers": sorted(cg.reverse.get(fn, set()))[:20],
                },
            })

    graph_dict = cg.to_dict()
    risk = round(sum(f["risk_score"] for f in findings) / len(findings), 4) if findings else 0.0

    return {
        "module_id": MODULE_ID,
        "status": "success",
        "risk_score": risk,
        "findings": findings,
        "metrics": {
            "total_nodes": len(cg.nodes),
            "total_edges": sum(len(v) for v in cg.edges.values()),
            "findings_count": len(findings),
        },
        "artifacts": [
            {"type": "call_graph_json", "data": graph_dict},
        ],
        "warnings": warnings,
    }
