"""并发分析器。

通过分析检测 C/C++ 代码中的并发风险：
- 共享变量访问模式（全局/静态）
- 锁获取/释放配对与顺序
- 线程入口函数
- 竞态条件候选（无锁写入）
"""

from __future__ import annotations

import logging
import re
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
    """运行并发分析。"""
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
        return _result(findings, warnings, 0, 0, 0, 0, len(files) if target_path.is_dir() else 0)

    # Phase 1: Collect global/static variables across files
    global_vars: set[str] = set()
    all_functions: list[tuple[Symbol, Path]] = []

    for fpath in files:
        try:
            source = fpath.read_text(errors="replace")
        except Exception:
            continue
        # Extract global variable names from file scope
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

    # Phase 2: Per-function analysis
    lock_sites: list[LockSite] = []
    shared_accesses: list[SharedAccess] = []
    func_lock_order: dict[str, list[str]] = {}  # func -> [lock names in order]

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

        # Detect shared variable writes
        # Build set of locks currently held (simplified: any lock acquired in function)
        held_locks = set(func_locks)

        for gv in global_vars:
            # Check if this variable is referenced in the function
            write_pattern = re.compile(
                rf"\b{re.escape(gv)}\s*(?:=(?!=)|[+\-*/&|^]=|\+\+|--)"
            )
            read_pattern = re.compile(rf"\b{re.escape(gv)}\b")

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
        findings.append({
            "finding_id": f"CC-F{fid:04d}",
            "module_id": MODULE_ID,
            "risk_type": "race_write_without_lock",
            "severity": "S1",
            "risk_score": 0.85,
            "title": f"Unprotected write to '{sa.var_name}' in {sa.func_name}",
            "description": (
                f"Global/shared variable '{sa.var_name}' is written without "
                f"holding any lock in function {sa.func_name}."
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
            },
        })

    # 3b. Lock ordering analysis (detect potential inversions)
    # Collect all distinct lock orderings across functions
    all_orders: list[tuple[str, list[str]]] = [
        (fn, locks) for fn, locks in func_lock_order.items() if len(locks) >= 2
    ]

    for i, (fn_a, locks_a) in enumerate(all_orders):
        for fn_b, locks_b in all_orders[i + 1:]:
            # Check if any pair of locks is acquired in opposite order
            for la_idx, la in enumerate(locks_a):
                for lb_idx, lb in enumerate(locks_a[la_idx + 1:], la_idx + 1):
                    # la before lb in fn_a, check if lb before la in fn_b
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
                                "title": f"Lock order inversion: {la}/{lb} between {fn_a} and {fn_b}",
                                "description": (
                                    f"{fn_a} acquires {la} then {lb}, "
                                    f"but {fn_b} acquires {lb} then {la}. "
                                    "Potential deadlock."
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

    # 3c. Lock acquire without matching release in same function
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
                "title": f"Lock not released in {sym.name}: {unreleased}",
                "description": (
                    f"Locks {unreleased} acquired but not released in {sym.name}. "
                    "May cause deadlock on error paths."
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

    # 3d. Thread creation sites
    thread_creates = 0
    for sym, fpath in all_functions:
        if _THREAD_CREATE_RE.search(sym.source):
            thread_creates += 1

    return _result(
        findings, warnings, total_functions,
        len(global_vars), len(lock_sites), thread_creates, len(files)
    )


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
        },
        "artifacts": [],
        "warnings": warnings,
    }
