"""静态交汇临界点计算。

基于 call_graph 与各模块 findings，在跨模块 AI 之前计算候选 critical_combinations，
使多函数交汇可追溯至图与发现，AI 仅做排序与补全。
"""

from __future__ import annotations

import logging
from collections import defaultdict
from typing import Any

logger = logging.getLogger(__name__)


def _build_graph_from_artifact(cg_artifact: dict) -> tuple[dict[str, set[str]], dict[str, set[str]]]:
    """从 call_graph artifact 的 to_dict() 产出构建 edges 与 reverse。"""
    edges: dict[str, set[str]] = defaultdict(set)
    reverse: dict[str, set[str]] = defaultdict(set)
    for e in cg_artifact.get("simple_edges", []) or cg_artifact.get("edges", []):
        src = e.get("src") or e.get("caller")
        dst = e.get("dst") or e.get("callee")
        if src and dst:
            edges[src].add(dst)
            reverse[dst].add(src)
    return dict(edges), dict(reverse)


def _get_related_from_finding(f: dict) -> list[str]:
    """从单条发现的 evidence 提取关联函数列表（去重、有序）。"""
    ev = f.get("evidence", {}) or {}
    out: list[str] = []
    seen: set[str] = set()

    def add(name: str) -> None:
        if name and name not in seen:
            seen.add(name)
            out.append(name)

    for x in ev.get("related_functions") or ev.get("interaction_chain") or ev.get("cross_function_chain") or []:
        if isinstance(x, str):
            add(x.strip())
        elif isinstance(x, dict) and x.get("function"):
            add(x["function"])

    chain = ev.get("propagation_chain") or []
    if isinstance(chain, list):
        for s in chain:
            if isinstance(s, dict) and s.get("function"):
                add(s["function"])

    for c in ev.get("callers") or []:
        if isinstance(c, str):
            add(c)
    sym = f.get("symbol_name") or ""
    if sym:
        add(sym)
    for c in ev.get("callees") or []:
        if isinstance(c, str):
            add(c)

    return out


def _call_neighbors(
    symbol: str,
    edges: dict[str, set[str]],
    reverse: dict[str, set[str]],
    depth: int = 2,
) -> set[str]:
    """取 symbol 的 callers(depth) + symbol + callees(depth)。"""
    result: set[str] = {symbol}
    frontier_caller = {symbol}
    frontier_callee = {symbol}
    for _ in range(depth):
        next_caller: set[str] = set()
        for n in frontier_caller:
            for c in reverse.get(n, set()):
                if c not in result:
                    result.add(c)
                    next_caller.add(c)
        frontier_caller = next_caller
        next_callee: set[str] = set()
        for n in frontier_callee:
            for c in edges.get(n, set()):
                if c not in result:
                    result.add(c)
                    next_callee.add(c)
        frontier_callee = next_callee
    return result


def compute_static_critical_candidates(
    upstream: dict[str, dict],
    call_graph_artifact: dict | None,
) -> list[dict[str, Any]]:
    """从 call_graph 与各模块 findings 计算候选多函数交汇临界点。

    规则：
    1) 同一函数上的多条发现 → 该函数为交汇点；
    2) 同一条调用链/邻居上的发现 → 邻居函数集为候选；
    3) 同一 propagation_chain 上的发现 → 链为候选；
    4) 已有 related_functions (≥2) 的发现 → 直接加入候选。

    返回列表每项含: related_functions, finding_ids, scenario_brief (占位), source。
    """
    candidates: list[dict[str, Any]] = []
    seen_keys: set[tuple[str, ...]] = set()

    def add_candidate(related: list[str], finding_ids: list[str], source: str) -> None:
        if len(related) < 2:
            return
        key = tuple(sorted(related))
        if key in seen_keys:
            return
        seen_keys.add(key)
        candidates.append({
            "related_functions": related,
            "finding_ids": finding_ids,
            "scenario_brief": "",
            "expected_outcome": "",
            "expected_failure": "",
            "unacceptable_outcomes": [],
            "source": source,
        })

    # 收集所有 findings（带 module_id 以生成 finding_id）
    all_findings: list[tuple[str, dict]] = []
    for mod_id, data in upstream.items():
        for f in data.get("findings", []) or []:
            fid = f.get("finding_id") or f"{mod_id}-{f.get('symbol_name', '')}"
            if isinstance(f.get("finding_id"), str):
                fid = f["finding_id"]
            all_findings.append((fid, f))

    edges: dict[str, set[str]] = {}
    reverse: dict[str, set[str]] = {}
    if call_graph_artifact:
        edges, reverse = _build_graph_from_artifact(call_graph_artifact)

    # 1) 同一函数上的多条发现 → 该函数 + 调用邻居为候选（至少 2 个函数）
    by_symbol: dict[str, list[tuple[str, dict]]] = defaultdict(list)
    for fid, f in all_findings:
        sym = (f.get("symbol_name") or "").strip()
        if sym:
            by_symbol[sym].append((fid, f))
    for sym, group in by_symbol.items():
        if len(group) < 2:
            continue
        if edges or reverse:
            related = sorted(_call_neighbors(sym, edges, reverse, depth=1))
        else:
            related = [sym]
        if len(related) >= 2:
            add_candidate(related[:8], [fid for fid, _ in group], "same_function")

    # 2) 调用链邻居：同一邻居集合上的发现合并为候选
    if edges or reverse:
        symbol_to_neighbors: dict[str, set[str]] = {}
        for fid, f in all_findings:
            sym = (f.get("symbol_name") or "").strip()
            if not sym:
                continue
            if sym not in symbol_to_neighbors:
                symbol_to_neighbors[sym] = _call_neighbors(sym, edges, reverse, depth=2)
            neighbors = symbol_to_neighbors[sym]
            if len(neighbors) >= 2:
                add_candidate(
                    sorted(neighbors),
                    [fid],
                    "call_chain_neighbors",
                )

    # 3) 同一 propagation_chain
    for mod_id, data in upstream.items():
        for f in data.get("findings", []) or []:
            ev = f.get("evidence", {}) or {}
            chain = ev.get("propagation_chain") or []
            if not isinstance(chain, list) or len(chain) < 2:
                continue
            funcs = [s.get("function") for s in chain if isinstance(s, dict) and s.get("function")]
            if len(funcs) >= 2:
                fid = f.get("finding_id") or f"{mod_id}-{f.get('symbol_name', '')}"
                add_candidate(funcs[:8], [fid], "propagation_chain")

    # 4) 已有 related_functions (≥2)
    for fid, f in all_findings:
        related = _get_related_from_finding(f)
        if len(related) >= 2:
            add_candidate(related[:8], [fid], "existing_related_functions")

    logger.info("静态交汇候选数: %d", len(candidates))
    return candidates
