"""调用图构建器（增强版）。

从 C/C++ 源码构建函数级有向调用图，
支持参数映射（caller 实参 → callee 形参）、调用行号、函数形参提取。
提供调用者/被调者查询助手，识别高扇出或深影响函数。
"""

from __future__ import annotations

import json
import logging
import re
from collections import defaultdict
from dataclasses import dataclass, field
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

# ── 调用点提取的更精准正则 ─────────────────────────────────────────
# 匹配: func_name( arg1, arg2, ... ) — 同时提取函数名和参数列表
_CALL_DETAIL_RE = re.compile(
    r"\b([a-zA-Z_]\w*)\s*\(([^)]*)\)"
)

# ── 函数声明/定义中提取形参 ────────────────────────────────────────
# 粗略匹配 C 形参: "type name" or "type *name" or "const type *name"
_PARAM_RE = re.compile(
    r"(?:const\s+)?(?:struct\s+)?(?:unsigned\s+|signed\s+)?"
    r"(?:\w+)\s*\*?\s*(\w+)\s*(?:,|\))"
)


@dataclass
class CallSite:
    """一个调用点的详细信息。"""
    caller: str
    callee: str
    line: int  # 调用所在行号（相对文件）
    arg_expressions: list[str] = field(default_factory=list)  # 实参表达式列表
    arg_mapping: list[dict[str, Any]] = field(default_factory=list)  # 实参→形参映射


class CallGraph:
    """Directed call graph with query helpers and enriched edge data."""

    def __init__(self) -> None:
        self.edges: dict[str, set[str]] = defaultdict(set)  # caller -> callees
        self.reverse: dict[str, set[str]] = defaultdict(set)  # callee -> callers
        self.nodes: set[str] = set()  # all known function symbols
        self.call_sites: list[CallSite] = []  # 全部调用点详情
        self.function_params: dict[str, list[str]] = {}  # function name -> param names
        self.function_files: dict[str, str] = {}  # function name -> file path
        self.function_lines: dict[str, tuple[int, int]] = {}  # function name -> (start, end)

    def add_edge(self, caller: str, callee: str) -> None:
        self.edges[caller].add(callee)
        self.reverse[callee].add(caller)
        self.nodes.add(caller)
        self.nodes.add(callee)

    def add_call_site(self, site: CallSite) -> None:
        """记录一个带参数映射的调用点。"""
        self.call_sites.append(site)
        self.add_edge(site.caller, site.callee)

    def get_call_sites(self, caller: str = "", callee: str = "") -> list[CallSite]:
        """按 caller/callee 筛选调用点。"""
        result = self.call_sites
        if caller:
            result = [s for s in result if s.caller == caller]
        if callee:
            result = [s for s in result if s.callee == callee]
        return result

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

    def get_call_chains(self, fn: str, direction: str = "callers", max_depth: int = 10) -> list[list[str]]:
        """获取从 fn 出发的所有调用链路径。

        direction: "callers" 向上追踪调用者 | "callees" 向下追踪被调者
        返回: [[fn, caller1, caller2, ...], ...] 每条路径
        """
        graph = self.reverse if direction == "callers" else self.edges
        chains: list[list[str]] = []

        def _dfs(current: str, path: list[str], visited: set[str]) -> None:
            neighbors = graph.get(current, set())
            if not neighbors or len(path) >= max_depth:
                if len(path) > 1:
                    chains.append(list(path))
                return
            extended = False
            for neighbor in neighbors:
                if neighbor not in visited:
                    visited.add(neighbor)
                    path.append(neighbor)
                    _dfs(neighbor, path, visited)
                    path.pop()
                    visited.discard(neighbor)
                    extended = True
            if not extended and len(path) > 1:
                chains.append(list(path))

        _dfs(fn, [fn], {fn})
        return chains

    def fan_out(self, fn: str) -> int:
        return len(self.edges.get(fn, set()))

    def fan_in(self, fn: str) -> int:
        return len(self.reverse.get(fn, set()))

    def to_dict(self) -> dict:
        return {
            "nodes": [
                {
                    "symbol": n,
                    "file_path": self.function_files.get(n, ""),
                    "params": self.function_params.get(n, []),
                }
                for n in sorted(self.nodes)
            ],
            "edges": [
                {
                    "src": site.caller,
                    "dst": site.callee,
                    "call_site_line": site.line,
                    "arg_mapping": site.arg_mapping,
                }
                for site in self.call_sites
            ],
            # 保留简单边集合用于向后兼容
            "simple_edges": [
                {"src": caller, "dst": callee}
                for caller, callees in sorted(self.edges.items())
                for callee in sorted(callees)
            ],
        }


def _extract_function_params(source: str, func_name: str) -> list[str]:
    """从函数定义源码中提取形参名称列表。"""
    # 尝试找到形参列表: 函数名后的第一对括号内
    pattern = re.compile(
        rf"\b{re.escape(func_name)}\s*\(([^)]*)\)",
        re.DOTALL,
    )
    m = pattern.search(source)
    if not m:
        return []

    param_str = m.group(1).strip()
    if not param_str or param_str == "void":
        return []

    # 分割参数（按逗号）
    params = []
    for part in param_str.split(","):
        part = part.strip()
        if not part:
            continue
        # 取最后一个标识符作为参数名
        tokens = re.findall(r"[a-zA-Z_]\w*", part)
        if tokens:
            # 排除类型关键字
            name = tokens[-1]
            type_keywords = {
                "int", "char", "void", "short", "long", "float", "double",
                "unsigned", "signed", "const", "volatile", "struct", "union",
                "enum", "static", "extern", "inline", "bool", "size_t",
            }
            if name not in type_keywords:
                params.append(name)
            elif len(tokens) > 1:
                # 可能是 "int" 作为最后 token 的边缘情况
                params.append(tokens[-2] if tokens[-2] not in type_keywords else name)
    return params


def _extract_call_sites_detailed(
    fn_name: str,
    fn_source: str,
    fn_line_start: int,
    defined_functions: set[str],
    function_params: dict[str, list[str]],
) -> list[CallSite]:
    """从函数源码中提取详细的调用点信息，包括参数映射。"""
    sites: list[CallSite] = []
    lines = fn_source.split("\n")

    for line_idx, line in enumerate(lines):
        for m in _CALL_DETAIL_RE.finditer(line):
            callee_name = m.group(1)
            if callee_name in _IGNORE or callee_name.isupper():
                continue
            if callee_name == fn_name or callee_name not in defined_functions:
                continue

            # 提取实参表达式
            raw_args = m.group(2).strip()
            arg_exprs = []
            if raw_args:
                # 简单逗号分割（不处理嵌套括号的复杂情况）
                depth = 0
                current = ""
                for ch in raw_args:
                    if ch in "([{":
                        depth += 1
                        current += ch
                    elif ch in ")]}":
                        depth -= 1
                        current += ch
                    elif ch == "," and depth == 0:
                        arg_exprs.append(current.strip())
                        current = ""
                    else:
                        current += ch
                if current.strip():
                    arg_exprs.append(current.strip())

            # 构建参数映射
            callee_params = function_params.get(callee_name, [])
            arg_mapping = []
            for idx, expr in enumerate(arg_exprs):
                mapping: dict[str, Any] = {
                    "caller_expr": expr,
                    "param_idx": idx,
                }
                if idx < len(callee_params):
                    mapping["callee_param"] = callee_params[idx]
                arg_mapping.append(mapping)

            site = CallSite(
                caller=fn_name,
                callee=callee_name,
                line=fn_line_start + line_idx,
                arg_expressions=arg_exprs,
                arg_mapping=arg_mapping,
            )
            sites.append(site)

    return sites


def build_callgraph(workspace: str, target_path: Path, max_files: int = 500) -> tuple[CallGraph, list[str]]:
    """Build enriched call graph from source files, return (graph, warnings)."""
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

    # Pass 1: collect defined functions, their params, and sources
    defined_functions: set[str] = set()
    function_sources: list[tuple[str, str, str, int, int]] = []  # (name, source, file_path, line_start, line_end)

    for fpath in files:
        try:
            symbols = parser.parse_file(fpath)
        except Exception as exc:
            warnings.append(f"parse error {fpath}: {exc}")
            continue

        rel_path = str(fpath.relative_to(workspace)) if workspace else str(fpath)

        for sym in symbols:
            if sym.kind == "function":
                defined_functions.add(sym.name)
                function_sources.append((sym.name, sym.source, rel_path, sym.line_start, sym.line_end))
                # 提取形参列表
                params = _extract_function_params(sym.source, sym.name)
                cg.function_params[sym.name] = params
                cg.function_files[sym.name] = rel_path
                cg.function_lines[sym.name] = (sym.line_start, sym.line_end)

    # Pass 2: extract detailed call sites with arg mapping
    seen_edges: set[tuple[str, str]] = set()  # 避免重复添加简单边

    for fn_name, fn_source, file_path, line_start, line_end in function_sources:
        sites = _extract_call_sites_detailed(
            fn_name, fn_source, line_start,
            defined_functions, cg.function_params,
        )
        for site in sites:
            cg.add_call_site(site)
            seen_edges.add((site.caller, site.callee))

        # 补充正则提取（捕获 detail regex 可能遗漏的调用）
        calls = _extract_calls(fn_source)
        for callee in calls:
            if callee != fn_name and callee in defined_functions:
                if (fn_name, callee) not in seen_edges:
                    cg.add_edge(fn_name, callee)
                    seen_edges.add((fn_name, callee))

    return cg, warnings


def _extract_calls(source: str) -> set[str]:
    """Extract function call names from source code (fallback simple regex)."""
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
                "title": f"高扇出枢纽函数: {fn}() 调用了 {fo} 个函数",
                "description": (
                    f"函数 {fn}() 的调用扇出度为 {fo}，意味着它直接依赖 {fo} 个其他函数。"
                    f"这使得 {fn}() 成为一个关键的集成枢纽，任何被调用函数的接口变更或行为改变"
                    f"都可能影响 {fn}() 的正确性。需要：(1) 为 {fn}() 建立集成测试覆盖所有调用路径；"
                    f"(2) 当任一被调用函数变更时对 {fn}() 进行回归测试。"
                ),
                "file_path": cg.function_files.get(fn, ""),
                "symbol_name": fn,
                "line_start": cg.function_lines.get(fn, (0, 0))[0],
                "line_end": cg.function_lines.get(fn, (0, 0))[1],
                "evidence": {
                    "fan_out": fo,
                    "fan_in": fi,
                    "callees": sorted(cg.edges.get(fn, set()))[:20],
                    "params": cg.function_params.get(fn, []),
                },
            })

        if fi >= 10:
            fid += 1
            # 获取调用链信息
            caller_chains = cg.get_call_chains(fn, direction="callers", max_depth=6)
            longest_chain = max(caller_chains, key=len) if caller_chains else []

            findings.append({
                "finding_id": f"CG-F{fid:04d}",
                "module_id": MODULE_ID,
                "risk_type": "deep_impact_surface",
                "severity": "S2",
                "risk_score": min(0.5 + fi * 0.02, 0.85),
                "title": f"高扇入关键函数: {fn}() 被 {fi} 个函数调用",
                "description": (
                    f"函数 {fn}() 的调用扇入度为 {fi}，意味着有 {fi} 个不同的函数依赖于它。"
                    f"对 {fn}() 的任何修改（参数变更、返回值语义变化、新增错误路径）都可能"
                    f"影响所有 {fi} 个调用者的正确性。"
                    + (f"最长调用链: {' → '.join(longest_chain)}。" if longest_chain else "")
                    + f"需要：(1) 对 {fn}() 的接口契约进行严格测试；"
                    f"(2) 修改前评估对所有调用者的影响；(3) 变更后运行全量回归测试。"
                ),
                "file_path": cg.function_files.get(fn, ""),
                "symbol_name": fn,
                "line_start": cg.function_lines.get(fn, (0, 0))[0],
                "line_end": cg.function_lines.get(fn, (0, 0))[1],
                "evidence": {
                    "fan_out": fo,
                    "fan_in": fi,
                    "callers": sorted(cg.reverse.get(fn, set()))[:20],
                    "caller_chains": [c[:8] for c in caller_chains[:5]],  # 最多5条链，每条最多8层
                    "params": cg.function_params.get(fn, []),
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
            "total_call_sites": len(cg.call_sites),
            "functions_with_params": sum(1 for v in cg.function_params.values() if v),
            "findings_count": len(findings),
        },
        "artifacts": [
            {"type": "call_graph_json", "data": graph_dict},
        ],
        "warnings": warnings,
    }
