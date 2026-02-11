"""错误路径分析器。

识别 C/C++ 代码中的错误处理模式：goto 清理、
return -errno、NULL 检查，并检测缺失清理或返回值映射不一致。
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
        return _result(findings, warnings, 0, 0)

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

            # 1. Resource allocation vs cleanup analysis
            allocs = _MALLOC_RE.findall(src)
            frees = [m[1] for m in _FREE_RE.findall(src)]
            opens = _OPEN_RE.findall(src)
            closes = [m[1] for m in _CLOSE_RE.findall(src)]
            locks = _LOCK_RE.findall(src)
            unlocks = _UNLOCK_RE.findall(src)

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

            # 2. Error returns
            error_returns = _ERROR_RETURN_RE.findall(src)

            # 3. Goto cleanup patterns
            gotos = _GOTO_RE.findall(src)
            labels = _LABEL_RE.findall(src)

            # --- Generate findings ---

            # Missing cleanup: allocated but not freed on all paths
            missing = set(expected_cleanup) - set(observed_cleanup)
            if missing and error_returns:
                fid += 1
                findings.append({
                    "finding_id": f"EP-F{fid:04d}",
                    "module_id": MODULE_ID,
                    "risk_type": "missing_cleanup",
                    "severity": "S1",
                    "risk_score": 0.85,
                    "title": f"Missing cleanup in {sym.name}: {missing}",
                    "description": (
                        f"Resources allocated ({expected_cleanup}) but cleanup "
                        f"incomplete ({observed_cleanup}). "
                        f"{len(error_returns)} error return paths may leak."
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
                    "title": f"Multiple error codes in {sym.name}",
                    "description": (
                        f"Function uses {len(set(error_returns))} distinct error "
                        f"return values: {sorted(set(error_returns))[:6]}. "
                        "Verify each maps to correct errno."
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
                # No goto cleanup pattern but has error returns and resources
                fid += 1
                findings.append({
                    "finding_id": f"EP-F{fid:04d}",
                    "module_id": MODULE_ID,
                    "risk_type": "silent_error_swallow",
                    "severity": "S1",
                    "risk_score": 0.75,
                    "title": f"Error returns without goto cleanup in {sym.name}",
                    "description": (
                        f"Function holds resources {expected_cleanup} and has "
                        f"{len(error_returns)} error returns but no goto cleanup "
                        "pattern. Each error path must be verified individually."
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
                        "title": f"Goto target missing in {sym.name}",
                        "description": f"Labels {missing_labels} referenced but not defined",
                        "file_path": rel_path,
                        "symbol_name": sym.name,
                        "line_start": sym.line_start,
                        "line_end": sym.line_end,
                        "evidence": {
                            "goto_targets": sorted(goto_targets),
                            "defined_labels": sorted(label_set),
                        },
                    })

    return _result(findings, warnings, total_functions, len(files))


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
        },
        "artifacts": [],
        "warnings": warnings,
    }
