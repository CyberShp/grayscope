"""错误路径分析器（增强版）。

识别 C/C++ 代码中的错误处理模式：goto 清理、return -errno、NULL 检查，
并检测缺失清理或返回值映射不一致。
增强: 跨函数资源泄漏链追踪 —— 如果 A 分配资源后调用 B，B 出错返回，A 是否释放了资源？
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

from app.analyzers.base import AnalyzeContext, ModuleResult
from app.analyzers.code_parser import CodeParser

logger = logging.getLogger(__name__)

MODULE_ID = "error_path"

# Pattern library for error handling idioms
_ERROR_RETURN_RE = re.compile(
    r"return\s+(-\s*E\w+|-1|NULL|false|0)", re.IGNORECASE
)
_GOTO_RE = re.compile(r"\bgoto\s+(\w+)")
_LABEL_RE = re.compile(r"^(\w+)\s*:", re.MULTILINE)
_MALLOC_RE = re.compile(r"\b(malloc|calloc|realloc|strdup|mmap)\s*\(")
_FREE_RE = re.compile(r"\b(free|munmap)\s*\(\s*(\w+)")
_OPEN_RE = re.compile(r"\b(open|fopen|socket|accept|creat)\s*\(")
_CLOSE_RE = re.compile(r"\b(close|fclose)\s*\(\s*(\w+)")
_LOCK_RE = re.compile(r"\b(pthread_mutex_lock|spin_lock|mutex_lock)\s*\(")
_UNLOCK_RE = re.compile(r"\b(pthread_mutex_unlock|spin_unlock|mutex_unlock)\s*\(")
_ERRNO_ASSIGN_RE = re.compile(r"errno\s*=")

# 用于跨函数分析的模式
_CALL_AND_CHECK_RE = re.compile(
    r"(?:ret|rc|err|status|result)\s*=\s*(\w+)\s*\([^)]*\).*?"
    r"(?:if\s*\(\s*(?:ret|rc|err|status|result)\s*[<!=])",
    re.DOTALL,
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
    fid = 0

    # ── 从上游提取数据流和调用图信息 ──────────────────────────────
    data_flow_chains = _extract_data_flow_chains(upstream)
    call_graph_info = _extract_call_graph_info(upstream)

    if target_path.is_file():
        files = [target_path]
    elif target_path.is_dir():
        exts = {".c", ".h", ".cpp", ".cc", ".cxx", ".hpp"}
        files = sorted(
            [p for p in target_path.rglob("*") if p.suffix in exts and p.is_file()]
        )[:max_files]
    else:
        warnings.append(f"target path not found: {target_path}")
        return _result(findings, warnings, 0, 0)

    # Pass 1: 收集每个函数的资源操作信息（用于跨函数分析）
    function_resource_info: dict[str, dict] = {}  # func_name -> resource info
    all_function_data: list[tuple[Any, Path, str]] = []

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
            src = sym.source
            all_function_data.append((sym, fpath, rel_path))

            # 收集资源操作
            allocs = _MALLOC_RE.findall(src)
            frees = [m[1] for m in _FREE_RE.findall(src)]
            opens = _OPEN_RE.findall(src)
            closes = [m[1] for m in _CLOSE_RE.findall(src)]
            locks = _LOCK_RE.findall(src)
            unlocks = _UNLOCK_RE.findall(src)
            error_returns = _ERROR_RETURN_RE.findall(src)

            function_resource_info[sym.name] = {
                "allocs": allocs,
                "frees": frees,
                "opens": opens,
                "closes": closes,
                "locks": locks,
                "unlocks": unlocks,
                "error_returns": error_returns,
                "file_path": rel_path,
                "line_start": sym.line_start,
                "line_end": sym.line_end,
            }

    # Pass 2: 单函数分析（原有逻辑）+ 跨函数分析（新增）
    for sym, fpath, rel_path in all_function_data:
        src = sym.source
        info = function_resource_info.get(sym.name, {})

        allocs = info.get("allocs", [])
        frees = info.get("frees", [])
        opens = info.get("opens", [])
        closes = info.get("closes", [])
        locks = info.get("locks", [])
        unlocks = info.get("unlocks", [])
        error_returns = info.get("error_returns", [])

        gotos = _GOTO_RE.findall(src)
        labels = _LABEL_RE.findall(src)

        expected_cleanup = []
        observed_cleanup = []
        if allocs:
            expected_cleanup.append("free")
            if frees:
                observed_cleanup.append("free")
        if opens:
            expected_cleanup.append("close")
            if closes:
                observed_cleanup.append("close")
        if locks:
            expected_cleanup.append("unlock")
            if unlocks:
                observed_cleanup.append("unlock")

        # --- Generate findings ---

        # Missing cleanup
        missing = set(expected_cleanup) - set(observed_cleanup)
        if missing and error_returns:
            fid += 1
            findings.append({
                "finding_id": f"EP-F{fid:04d}",
                "module_id": MODULE_ID,
                "risk_type": "missing_cleanup",
                "severity": "S1",
                "risk_score": 0.85,
                "title": f"{sym.name}() 中缺少资源清理: {missing}",
                "description": (
                    f"函数 {sym.name}() 分配了资源（{', '.join(expected_cleanup)}），但清理操作不完整"
                    f"（仅执行了 {', '.join(observed_cleanup) if observed_cleanup else '无'}）。"
                    f"该函数有 {len(error_returns)} 条错误返回路径，这些路径在异常退出时可能跳过资源释放，"
                    f"导致内存泄漏、文件句柄泄漏或锁未释放等问题。"
                    f"需要验证每条错误路径是否都执行了完整的资源释放操作。"
                ),
                "file_path": rel_path,
                "symbol_name": sym.name,
                "line_start": sym.line_start,
                "line_end": sym.line_end,
                "evidence": {
                    "cleanup_resources_expected": expected_cleanup,
                    "cleanup_resources_observed": observed_cleanup,
                    "error_returns": error_returns[:5],
                },
            })

        # Multiple error returns with different codes
        if len(set(error_returns)) > 2:
            fid += 1
            findings.append({
                "finding_id": f"EP-F{fid:04d}",
                "module_id": MODULE_ID,
                "risk_type": "inconsistent_errno_mapping",
                "severity": "S2",
                "risk_score": 0.6,
                "title": f"{sym.name}() 中存在多种错误返回码",
                "description": (
                    f"函数 {sym.name}() 使用了 {len(set(error_returns))} 种不同的错误返回值: "
                    f"{', '.join(sorted(set(error_returns))[:6])}。"
                    f"多种错误返回码增加了调用者正确处理每种错误的难度。"
                    f"需要验证：(1) 每种错误码是否对应正确的错误场景；"
                    f"(2) 调用者是否区分处理了不同的错误码；"
                    f"(3) 文档中是否记录了所有可能的错误返回值。"
                ),
                "file_path": rel_path,
                "symbol_name": sym.name,
                "line_start": sym.line_start,
                "line_end": sym.line_end,
                "evidence": {
                    "error_codes": sorted(set(error_returns)),
                },
            })

        # Error returns without cleanup when resources are held
        if error_returns and expected_cleanup and not gotos:
            fid += 1
            findings.append({
                "finding_id": f"EP-F{fid:04d}",
                "module_id": MODULE_ID,
                "risk_type": "silent_error_swallow",
                "severity": "S1",
                "risk_score": 0.75,
                "title": f"{sym.name}() 中错误返回路径缺少统一清理",
                "description": (
                    f"函数 {sym.name}() 持有资源（{', '.join(expected_cleanup)}）并且有 "
                    f"{len(error_returns)} 条错误返回路径，但未使用 goto 集中清理模式。"
                    f"这意味着每条错误返回路径都需要独立处理资源释放，容易遗漏。"
                    f"如果某条路径忘记释放资源，将导致泄漏。建议：(1) 逐条检查每个 return 前是否释放了所有资源；"
                    f"(2) 考虑重构为 goto 集中清理模式以降低遗漏风险。"
                ),
                "file_path": rel_path,
                "symbol_name": sym.name,
                "line_start": sym.line_start,
                "line_end": sym.line_end,
                "evidence": {
                    "resources_held": expected_cleanup,
                    "error_return_count": len(error_returns),
                    "has_goto_cleanup": False,
                },
            })

        # Goto target label mismatch
        if gotos:
            goto_targets = set(gotos)
            label_set = set(labels)
            missing_labels = goto_targets - label_set
            if missing_labels:
                fid += 1
                findings.append({
                    "finding_id": f"EP-F{fid:04d}",
                    "module_id": MODULE_ID,
                    "risk_type": "missing_cleanup",
                    "severity": "S0",
                    "risk_score": 0.95,
                    "title": f"{sym.name}() 中 goto 目标标签缺失",
                    "description": (
                        f"函数 {sym.name}() 中引用了标签 {missing_labels}，但这些标签在函数体内未定义。"
                        f"这将导致编译错误或运行时跳转到未定义位置，是严重的代码缺陷。"
                        f"需要立即检查并修复缺失的标签定义。"
                    ),
                    "file_path": rel_path,
                    "symbol_name": sym.name,
                    "line_start": sym.line_start,
                    "line_end": sym.line_end,
                    "evidence": {
                        "goto_targets": sorted(goto_targets),
                        "defined_labels": sorted(label_set),
                    },
                })

        # ── 新增: 跨函数资源泄漏链分析 ──────────────────────────
        # 如果本函数分配了资源，然后调用了其他函数
        # 被调函数可能返回错误，本函数是否在该错误路径上释放了已分配的资源？
        if expected_cleanup:
            callees = call_graph_info.get(sym.name, [])
            for callee_name in callees:
                callee_info = function_resource_info.get(callee_name, {})
                callee_errors = callee_info.get("error_returns", [])

                if not callee_errors:
                    continue

                # 检查本函数在调用 callee 后是否检查了返回值
                call_and_check = re.search(
                    rf"(?:ret|rc|err|status|result)\s*=\s*{re.escape(callee_name)}\s*\(",
                    src,
                )
                if not call_and_check:
                    # 未检查返回值 — 被调函数出错时本函数不知道，资源可能泄漏
                    fid += 1
                    findings.append({
                        "finding_id": f"EP-F{fid:04d}",
                        "module_id": MODULE_ID,
                        "risk_type": "cross_function_resource_leak",
                        "severity": "S1",
                        "risk_score": 0.8,
                        "title": (
                            f"{sym.name}() 调用 {callee_name}() 后未检查错误返回值，"
                            f"已分配资源可能泄漏"
                        ),
                        "description": (
                            f"函数 {sym.name}() 持有资源（{', '.join(expected_cleanup)}）并调用了 "
                            f"{callee_name}()。{callee_name}() 有 {len(callee_errors)} 条错误返回路径，"
                            f"但 {sym.name}() 未检查 {callee_name}() 的返回值。"
                            f"如果 {callee_name}() 执行失败，{sym.name}() 不知道发生了错误，"
                            f"后续逻辑可能在错误状态下继续执行，且已分配的资源在异常路径上可能不会被释放。"
                            f"需要：(1) 检查 {callee_name}() 的返回值；"
                            f"(2) 在错误路径上释放 {sym.name}() 已分配的所有资源。"
                        ),
                        "file_path": rel_path,
                        "symbol_name": sym.name,
                        "line_start": sym.line_start,
                        "line_end": sym.line_end,
                        "evidence": {
                            "caller_function": sym.name,
                            "callee_function": callee_name,
                            "caller_resources": expected_cleanup,
                            "callee_error_returns": callee_errors[:5],
                            "return_value_checked": False,
                            "cross_function_chain": [sym.name, callee_name],
                            "related_functions": [sym.name, callee_name],
                            "expected_failure": "被调函数返回错误、调用方返回错误码",
                            "unacceptable_outcomes": ["资源泄漏", "进程崩溃", "不可恢复状态"],
                        },
                    })
                else:
                    # 检查了返回值，但错误处理路径是否释放了资源？
                    # 简化检查：在错误检查和 return 之间是否有 free/close/unlock
                    error_block_start = call_and_check.end()
                    next_200_chars = src[error_block_start:error_block_start + 500]

                    has_cleanup_in_error = any(
                        re.search(pattern, next_200_chars)
                        for pattern in [
                            r"\bfree\s*\(",
                            r"\bclose\s*\(",
                            r"\bfclose\s*\(",
                            r"\bunlock\s*\(",
                            r"\bgoto\s+\w+",
                        ]
                    )

                    if not has_cleanup_in_error and missing:
                        fid += 1
                        findings.append({
                            "finding_id": f"EP-F{fid:04d}",
                            "module_id": MODULE_ID,
                            "risk_type": "cross_function_resource_leak",
                            "severity": "S1",
                            "risk_score": 0.75,
                            "title": (
                                f"{sym.name}() 在 {callee_name}() 失败路径上"
                                f"可能遗漏资源释放"
                            ),
                            "description": (
                                f"函数 {sym.name}() 持有资源（{', '.join(expected_cleanup)}），"
                                f"调用 {callee_name}() 并检查了返回值。"
                                f"但在 {callee_name}() 的错误处理路径上，"
                                f"未发现对已分配资源的释放操作（缺失: {', '.join(missing)}）。"
                                f"这可能导致在 {callee_name}() 失败时资源泄漏。"
                                f"建议检查错误处理分支是否包含完整的资源清理。"
                            ),
                            "file_path": rel_path,
                            "symbol_name": sym.name,
                            "line_start": sym.line_start,
                            "line_end": sym.line_end,
                            "evidence": {
                                "caller_function": sym.name,
                                "callee_function": callee_name,
                                "caller_resources": expected_cleanup,
                                "missing_cleanup": list(missing),
                                "return_value_checked": True,
                                "error_cleanup_found": False,
                                "cross_function_chain": [sym.name, callee_name],
                                "related_functions": [sym.name, callee_name],
                                "expected_failure": "被调函数失败后调用方返回错误",
                                "unacceptable_outcomes": ["资源泄漏", "进程崩溃"],
                            },
                        })

    return _result(findings, warnings, total_functions, len(files))


def _extract_data_flow_chains(upstream: dict[str, dict]) -> list[dict]:
    """从上游 data_flow 结果中提取传播链。"""
    df_data = upstream.get("data_flow", {})
    chains = []
    for finding in df_data.get("findings", []):
        ev = finding.get("evidence", {})
        chain = ev.get("propagation_chain")
        if chain:
            chains.append({
                "propagation_path": chain,
                "entry_function": ev.get("entry_function", ""),
            })
    return chains


def _extract_call_graph_info(upstream: dict[str, dict]) -> dict[str, list[str]]:
    """从上游 call_graph 提取每个函数调用了谁。"""
    cg_data = upstream.get("call_graph", {})
    callees_map: dict[str, list[str]] = {}
    for finding in cg_data.get("findings", []):
        ev = finding.get("evidence", {})
        sym = finding.get("symbol_name", "")
        if sym and ev.get("callees"):
            callees_map[sym] = ev["callees"]
    return callees_map


def _result(
    findings: list, warnings: list, funcs: int, files: int
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
            "findings_count": len(findings),
            "cross_function_findings": sum(
                1 for f in findings if f["risk_type"] == "cross_function_resource_leak"
            ),
        },
        "artifacts": [],
        "warnings": warnings,
    }
