"""并发分析器（增强版）。

通过分析检测 C/C++ 代码中的并发风险：
- 共享变量访问模式（全局/静态）
- 锁获取/释放配对与顺序
- 线程入口函数
- 竞态条件候选（无锁写入）
增强: 真正使用 call_graph，实现跨函数锁持有链构建和 ABBA 死锁检测。
"""

from __future__ import annotations

import logging
import re
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.analyzers.base import AnalyzeContext, ModuleResult
from app.analyzers.code_parser import CodeParser, Symbol

logger = logging.getLogger(__name__)

MODULE_ID = "concurrency"

# --- Pattern library ---

_LOCK_ACQUIRE_RE = re.compile(
    r"\b(pthread_mutex_lock|pthread_spin_lock|spin_lock|mutex_lock|"
    r"pthread_rwlock_rdlock|pthread_rwlock_wrlock|sem_wait|"
    r"EnterCriticalSection|AcquireSRWLock\w*)\s*\(\s*&?\s*(\w+)"
)
_LOCK_RELEASE_RE = re.compile(
    r"\b(pthread_mutex_unlock|pthread_spin_unlock|spin_unlock|mutex_unlock|"
    r"pthread_rwlock_unlock|sem_post|"
    r"LeaveCriticalSection|ReleaseSRWLock\w*)\s*\(\s*&?\s*(\w+)"
)
_THREAD_CREATE_RE = re.compile(
    r"\b(pthread_create|CreateThread|std::thread)\s*\("
)
_GLOBAL_VAR_RE = re.compile(
    r"^(?:static\s+)?(?:volatile\s+)?(?:(?:int|char|void|unsigned|long|short|"
    r"size_t|uint\d+_t|int\d+_t|bool|float|double|struct\s+\w+|"
    r"\w+_t)\s*\*?\s+)(\w+)\s*(?:=|;|\[)",
    re.MULTILINE,
)
_ATOMIC_RE = re.compile(
    r"\b(atomic_\w+|__sync_\w+|__atomic_\w+|InterlockedIncrement|"
    r"InterlockedDecrement|InterlockedExchange)\s*\("
)
_SHARED_ACCESS_RE = re.compile(r"\b({var})\s*(?:=(?!=)|[+\-*/&|^]=|\+\+|--)")


@dataclass
class LockSite:
    lock_name: str
    op: str  # "acquire" | "release"
    line: int
    func_name: str
    file_path: str


@dataclass
class SharedAccess:
    var_name: str
    access: str  # "read" | "write"
    line: int
    func_name: str
    file_path: str
    lock_held: str  # lock name or "" if none


def analyze(ctx: AnalyzeContext) -> ModuleResult:
    """运行并发分析（增强版 —— 跨函数锁链追踪）。"""
    workspace = ctx["workspace_path"]
    target = ctx["target"]
    options = ctx["options"]
    upstream = ctx["upstream_results"]
    target_path = Path(workspace) / target.get("path", "")
    max_files = options.get("max_files", 500)

    parser = CodeParser()
    findings: list[dict[str, Any]] = []
    warnings: list[str] = []
    fid = 0
    total_functions = 0

    # ── 从上游提取调用图信息 ──────────────────────────────────────
    call_graph_edges = _extract_call_graph_edges(upstream)
    data_flow_info = _extract_data_flow_shared_vars(upstream)

    # Collect files
    if target_path.is_file():
        files = [target_path]
    elif target_path.is_dir():
        exts = {".c", ".h", ".cpp", ".cc", ".cxx", ".hpp"}
        files = sorted(
            [p for p in target_path.rglob("*") if p.suffix in exts and p.is_file()]
        )[:max_files]
    else:
        warnings.append(f"target path not found: {target_path}")
        return _result(findings, warnings, 0, 0, 0, 0, 0)

    # Phase 1: Collect global/static variables across files
    global_vars: set[str] = set()
    all_functions: list[tuple[Symbol, Path]] = []

    for fpath in files:
        try:
            source = fpath.read_text(errors="replace")
        except Exception:
            continue
        for m in _GLOBAL_VAR_RE.finditer(source):
            global_vars.add(m.group(1))

        try:
            symbols = parser.parse_file(fpath)
        except Exception as exc:
            warnings.append(f"parse error {fpath}: {exc}")
            continue
        for sym in symbols:
            if sym.kind == "function":
                all_functions.append((sym, fpath))
        total_functions += len([s for s in symbols if s.kind == "function"])

    # Phase 2: Per-function lock and shared variable analysis
    lock_sites: list[LockSite] = []
    shared_accesses: list[SharedAccess] = []
    func_lock_order: dict[str, list[str]] = {}  # func -> [lock names in order]
    func_held_locks: dict[str, set[str]] = {}  # func -> set of locks acquired

    for sym, fpath in all_functions:
        src = sym.source
        rel_path = str(fpath.relative_to(workspace)) if workspace else str(fpath)

        # Extract lock operations
        func_locks: list[str] = []
        for m in _LOCK_ACQUIRE_RE.finditer(src):
            lock_name = m.group(2)
            line_offset = src[:m.start()].count("\n")
            lock_sites.append(LockSite(
                lock_name=lock_name, op="acquire",
                line=sym.line_start + line_offset,
                func_name=sym.name, file_path=rel_path,
            ))
            func_locks.append(lock_name)

        for m in _LOCK_RELEASE_RE.finditer(src):
            lock_name = m.group(2)
            line_offset = src[:m.start()].count("\n")
            lock_sites.append(LockSite(
                lock_name=lock_name, op="release",
                line=sym.line_start + line_offset,
                func_name=sym.name, file_path=rel_path,
            ))

        if func_locks:
            func_lock_order[sym.name] = func_locks
            func_held_locks[sym.name] = set(func_locks)

        # Detect shared variable writes
        held_locks = set(func_locks)

        for gv in global_vars:
            write_pattern = re.compile(
                rf"\b{re.escape(gv)}\s*(?:=(?!=)|[+\-*/&|^]=|\+\+|--)"
            )

            for wm in write_pattern.finditer(src):
                line_offset = src[:wm.start()].count("\n")
                lock_held = list(held_locks)[0] if held_locks else ""
                shared_accesses.append(SharedAccess(
                    var_name=gv, access="write",
                    line=sym.line_start + line_offset,
                    func_name=sym.name, file_path=rel_path,
                    lock_held=lock_held,
                ))

    # Phase 3: Generate findings

    # 3a. Write to shared variable without lock
    writes_without_lock = [
        sa for sa in shared_accesses
        if sa.access == "write" and not sa.lock_held
    ]
    for sa in writes_without_lock:
        fid += 1
        # 增强: 检查这个变量是否通过调用链被其他函数访问
        other_accessors = [
            a for a in shared_accesses
            if a.var_name == sa.var_name and a.func_name != sa.func_name
        ]
        other_accessor_names = [a.func_name for a in other_accessors]

        findings.append({
            "finding_id": f"CC-F{fid:04d}",
            "module_id": MODULE_ID,
            "risk_type": "race_write_without_lock",
            "severity": "S1",
            "risk_score": 0.85,
            "title": f"{sa.func_name}() 中对共享变量 '{sa.var_name}' 的无锁写入",
            "description": (
                f"函数 {sa.func_name}() 在未持有任何锁的情况下写入全局/共享变量 '{sa.var_name}'。"
                f"在多线程环境中，无锁写入是数据竞态的典型来源。"
                + (f"该变量同时被以下函数访问: {', '.join(other_accessor_names[:5])}，"
                   f"增加了并发冲突的可能性。"
                   if other_accessor_names else "")
                + f"需要：(1) 在写入前获取互斥锁；"
                f"(2) 或使用原子操作替代；"
                f"(3) 使用 ThreadSanitizer 进行运行时检测。"
            ),
            "file_path": sa.file_path,
            "symbol_name": sa.func_name,
            "line_start": sa.line,
            "line_end": sa.line,
            "evidence": {
                "shared_symbol": sa.var_name,
                "access": "write",
                "lock_held": None,
                "function": sa.func_name,
                "other_accessors": other_accessor_names[:10],
                "related_functions": [sa.func_name] + [a for a in other_accessor_names[:5] if a != sa.func_name],
                "expected_failure": "多线程同时写共享变量导致数据竞态",
                "unacceptable_outcomes": ["数据损坏", "未定义行为", "崩溃"],
            },
        })

    # 3b. Lock ordering analysis (within single functions)
    all_orders: list[tuple[str, list[str]]] = [
        (fn, locks) for fn, locks in func_lock_order.items() if len(locks) >= 2
    ]

    for i, (fn_a, locks_a) in enumerate(all_orders):
        for fn_b, locks_b in all_orders[i + 1:]:
            for la_idx, la in enumerate(locks_a):
                for lb_idx, lb in enumerate(locks_a[la_idx + 1:], la_idx + 1):
                    if lb in locks_b and la in locks_b:
                        b_idx_lb = locks_b.index(lb)
                        b_idx_la = locks_b.index(la)
                        if b_idx_lb < b_idx_la:
                            fid += 1
                            findings.append({
                                "finding_id": f"CC-F{fid:04d}",
                                "module_id": MODULE_ID,
                                "risk_type": "lock_order_inversion",
                                "severity": "S0",
                                "risk_score": 0.95,
                                "title": f"锁顺序反转: {fn_a}() 和 {fn_b}() 之间的 {la}/{lb}",
                                "description": (
                                    f"函数 {fn_a}() 先获取锁 {la} 再获取锁 {lb}，"
                                    f"但函数 {fn_b}() 先获取锁 {lb} 再获取锁 {la}。"
                                    f"这是经典的 ABBA 死锁模式。"
                                    f"需要统一锁获取顺序或使用 trylock 超时机制。"
                                ),
                                "file_path": "",
                                "symbol_name": f"{fn_a}/{fn_b}",
                                "line_start": 0,
                                "line_end": 0,
                                "evidence": {
                                    "lock_order_a": {fn_a: locks_a},
                                    "lock_order_b": {fn_b: locks_b},
                                    "conflicting_locks": [la, lb],
                                },
                            })

    # 3c. Lock acquire without matching release
    for sym, fpath in all_functions:
        src = sym.source
        rel_path = str(fpath.relative_to(workspace)) if workspace else str(fpath)

        acquires = {m.group(2) for m in _LOCK_ACQUIRE_RE.finditer(src)}
        releases = {m.group(2) for m in _LOCK_RELEASE_RE.finditer(src)}
        unreleased = acquires - releases

        if unreleased:
            fid += 1
            findings.append({
                "finding_id": f"CC-F{fid:04d}",
                "module_id": MODULE_ID,
                "risk_type": "atomicity_gap",
                "severity": "S1",
                "risk_score": 0.8,
                "title": f"{sym.name}() 中锁未释放: {unreleased}",
                "description": (
                    f"函数 {sym.name}() 获取了锁 {unreleased}，但在函数体内未找到释放操作。"
                    f"注意错误路径：如果函数获取锁后直接 return，锁将永远不会释放。"
                ),
                "file_path": rel_path,
                "symbol_name": sym.name,
                "line_start": sym.line_start,
                "line_end": sym.line_end,
                "evidence": {
                    "acquired_locks": sorted(acquires),
                    "released_locks": sorted(releases),
                    "unreleased": sorted(unreleased),
                },
            })

    # ── 新增 3d: 跨函数锁持有链分析 ─────────────────────────────
    # 如果 A 持有 lock_x 后调用 B，B 又获取 lock_y，
    # 则实际持有链为 A:[lock_x] -> B:[lock_x, lock_y]
    # 如果另一条路径 C:[lock_y] -> D:[lock_y, lock_x]，则存在跨函数 ABBA 死锁
    cross_func_lock_chains: dict[str, list[str]] = {}  # func -> accumulated lock chain

    for fn_name, held_locks_set in func_held_locks.items():
        callees = call_graph_edges.get(fn_name, [])
        for callee in callees:
            callee_locks = func_held_locks.get(callee, set())
            if not callee_locks:
                continue

            # 构建跨函数锁持有链
            chain_key = f"{fn_name}->{callee}"
            accumulated = list(held_locks_set) + [
                lk for lk in func_lock_order.get(callee, []) if lk not in held_locks_set
            ]
            cross_func_lock_chains[chain_key] = accumulated

    # 检查跨函数锁链之间的冲突
    chain_items = list(cross_func_lock_chains.items())
    for i, (chain_a_key, locks_a) in enumerate(chain_items):
        if len(locks_a) < 2:
            continue
        for chain_b_key, locks_b in chain_items[i + 1:]:
            if len(locks_b) < 2:
                continue
            # 检查是否有两个锁在两条链中以相反顺序出现
            for a_idx, la in enumerate(locks_a):
                for lb_idx, lb in enumerate(locks_a[a_idx + 1:], a_idx + 1):
                    if lb in locks_b and la in locks_b:
                        b_pos_lb = locks_b.index(lb)
                        b_pos_la = locks_b.index(la)
                        if b_pos_lb < b_pos_la:
                            fid += 1
                            findings.append({
                                "finding_id": f"CC-F{fid:04d}",
                                "module_id": MODULE_ID,
                                "risk_type": "cross_function_deadlock_risk",
                                "severity": "S0",
                                "risk_score": 0.95,
                                "title": (
                                    f"跨函数死锁风险: 调用链 {chain_a_key} 与 "
                                    f"{chain_b_key} 之间的 {la}/{lb}"
                                ),
                                "description": (
                                    f"通过调用链分析发现潜在的跨函数 ABBA 死锁:\n"
                                    f"路径1: {chain_a_key} 的锁获取顺序为 {' → '.join(locks_a)}\n"
                                    f"路径2: {chain_b_key} 的锁获取顺序为 {' → '.join(locks_b)}\n"
                                    f"锁 {la} 和 {lb} 在两条路径中以相反顺序被获取。"
                                    f"当两个线程分别沿这两条路径执行时，可能产生死锁。"
                                    f"这种跨函数死锁比单函数内的更难发现和调试。"
                                    f"建议：(1) 全局统一锁获取顺序文档；"
                                    f"(2) 使用锁层级（lock hierarchy）约束；"
                                    f"(3) 在持有锁时调用其他函数前审查被调函数的锁行为。"
                                ),
                                "file_path": "",
                                "symbol_name": f"{chain_a_key} vs {chain_b_key}",
                                "line_start": 0,
                                "line_end": 0,
                                "evidence": {
                                    "chain_a": {"path": chain_a_key, "locks": locks_a},
                                    "chain_b": {"path": chain_b_key, "locks": locks_b},
                                    "conflicting_locks": [la, lb],
                                    "cross_function": True,
                                },
                            })

    # ── 新增 3e: 跨函数共享变量竞态追踪 ──────────────────────────
    # 利用调用图找出哪些函数在调用链上共同访问了同一个共享变量
    var_accessors: dict[str, list[dict]] = defaultdict(list)
    for sa in shared_accesses:
        var_accessors[sa.var_name].append({
            "func": sa.func_name,
            "access": sa.access,
            "lock": sa.lock_held,
            "line": sa.line,
            "file": sa.file_path,
        })

    for var_name, accessors in var_accessors.items():
        if len(accessors) < 2:
            continue

        # 检查是否有调用链关系（A 调用 B，两者都访问同一变量）
        writers = [a for a in accessors if a["access"] == "write"]
        for writer in writers:
            for other in accessors:
                if other["func"] == writer["func"]:
                    continue

                # 检查是否存在调用关系
                writer_callees = call_graph_edges.get(writer["func"], [])
                other_callees = call_graph_edges.get(other["func"], [])

                has_call_relation = (
                    other["func"] in writer_callees
                    or writer["func"] in other_callees
                )

                if has_call_relation and not writer["lock"]:
                    fid += 1
                    findings.append({
                        "finding_id": f"CC-F{fid:04d}",
                        "module_id": MODULE_ID,
                        "risk_type": "cross_function_race",
                        "severity": "S1",
                        "risk_score": 0.85,
                        "title": (
                            f"跨函数竞态: {writer['func']}() 和 {other['func']}() "
                            f"在调用链上共享变量 '{var_name}'"
                        ),
                        "description": (
                            f"函数 {writer['func']}() 无锁写入共享变量 '{var_name}'，"
                            f"同时函数 {other['func']}() 也访问该变量，"
                            f"且两个函数存在调用关系。"
                            f"在多线程环境中，如果一个线程正在执行 {writer['func']}() "
                            f"修改 '{var_name}'，另一个线程通过调用 {other['func']}() "
                            f"读取该变量，会导致数据竞态。"
                            f"这种跨函数的竞态条件更难通过代码审查发现。"
                        ),
                        "file_path": writer["file"],
                        "symbol_name": writer["func"],
                        "line_start": writer["line"],
                        "line_end": writer["line"],
                        "evidence": {
                            "shared_symbol": var_name,
                            "writer": {
                                "function": writer["func"],
                                "lock": writer["lock"],
                            },
                            "reader": {
                                "function": other["func"],
                                "lock": other["lock"],
                            },
                            "call_relation": True,
                            "cross_function": True,
                            "related_functions": list(dict.fromkeys([writer["func"], other["func"]])),
                            "expected_failure": "调用链上无锁写与读/写并发",
                            "unacceptable_outcomes": ["数据竞态", "未定义行为"],
                        },
                    })
                    break  # 每个 writer-variable 组合只报一次

    # Count thread creation sites
    thread_creates = sum(
        1 for sym, _ in all_functions if _THREAD_CREATE_RE.search(sym.source)
    )

    return _result(
        findings, warnings, total_functions,
        len(global_vars), len(lock_sites), thread_creates, len(files)
    )


def _extract_call_graph_edges(upstream: dict[str, dict]) -> dict[str, list[str]]:
    """从上游 call_graph 提取调用关系。"""
    cg_data = upstream.get("call_graph", {})
    edges: dict[str, list[str]] = defaultdict(list)

    # 从 findings 的 evidence 中提取 callees
    for finding in cg_data.get("findings", []):
        ev = finding.get("evidence", {})
        sym = finding.get("symbol_name", "")
        if sym and ev.get("callees"):
            edges[sym] = ev["callees"]

    return dict(edges)


def _extract_data_flow_shared_vars(upstream: dict[str, dict]) -> dict:
    """从上游 data_flow 提取与共享变量相关的传播链。"""
    df_data = upstream.get("data_flow", {})
    return df_data  # 简单传递，具体使用在分析中按需提取


def _result(
    findings: list, warnings: list, funcs: int,
    shared_vars: int, lock_ops: int, thread_creates: int, files: int
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
            "shared_variables_found": shared_vars,
            "lock_operations": lock_ops,
            "thread_creation_sites": thread_creates,
            "findings_count": len(findings),
            "cross_function_findings": sum(
                1 for f in findings
                if f["risk_type"] in ("cross_function_deadlock_risk", "cross_function_race")
            ),
        },
        "artifacts": [],
        "warnings": warnings,
    }
