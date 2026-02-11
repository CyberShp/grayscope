"""差异影响分析器。

分析代码变更（diff），通过调用图映射影响传播，
识别传递性回归风险区域并推荐回归测试。
"""

from __future__ import annotations

import logging
import re
import subprocess
from pathlib import Path
from typing import Any

from app.analyzers.base import AnalyzeContext, ModuleResult
from app.analyzers.code_parser import CodeParser
from app.analyzers.call_graph_builder import CallGraph, build_callgraph

logger = logging.getLogger(__name__)

MODULE_ID = "diff_impact"

# Max depth for transitive impact propagation
DEFAULT_IMPACT_DEPTH = 2


def _parse_unified_diff(diff_text: str) -> list[dict]:
    """Parse a unified diff into structured changed-file records.

    Returns list of:
      {"file": str, "added_lines": [int], "removed_lines": [int]}
    """
    results: list[dict] = []
    current: dict | None = None
    line_no = 0

    for line in diff_text.split("\n"):
        if line.startswith("+++ b/"):
            file_path = line[6:]
            current = {"file": file_path, "added_lines": [], "removed_lines": []}
            results.append(current)
        elif line.startswith("--- a/"):
            continue
        elif line.startswith("@@ "):
            # Parse hunk header: @@ -old_start,old_count +new_start,new_count @@
            m = re.search(r"\+(\d+)", line)
            line_no = int(m.group(1)) if m else 0
        elif current is not None:
            if line.startswith("+") and not line.startswith("+++"):
                current["added_lines"].append(line_no)
                line_no += 1
            elif line.startswith("-") and not line.startswith("---"):
                current["removed_lines"].append(line_no)
            else:
                line_no += 1

    return results


def _get_git_diff(workspace: str, base: str, head: str) -> str:
    """Run git diff between two commits."""
    try:
        result = subprocess.run(
            ["git", "diff", base, head, "--unified=3"],
            capture_output=True, text=True, cwd=workspace,
            timeout=30,
        )
        return result.stdout
    except Exception as exc:
        logger.warning("git diff failed: %s", exc)
        return ""


def _map_lines_to_functions(
    workspace: str, file_path: str, lines: list[int]
) -> list[str]:
    """Map changed line numbers to function names using parser."""
    abs_path = Path(workspace) / file_path
    if not abs_path.exists() or abs_path.suffix not in {".c", ".h", ".cpp", ".cc", ".cxx", ".hpp"}:
        return []

    try:
        parser = CodeParser()
        symbols = parser.parse_file(abs_path)
    except Exception:
        return []

    affected = set()
    for sym in symbols:
        if sym.kind == "function":
            for ln in lines:
                if sym.line_start <= ln <= sym.line_end:
                    affected.add(sym.name)
    return sorted(affected)


def analyze(ctx: AnalyzeContext) -> ModuleResult:
    """Run diff impact analysis."""
    workspace = ctx["workspace_path"]
    target = ctx["target"]
    options = ctx["options"]
    upstream = ctx["upstream_results"]
    revision = ctx.get("revision", {})

    findings: list[dict[str, Any]] = []
    warnings: list[str] = []
    fid = 0

    base_commit = revision.get("base_commit", revision.get("base", "HEAD~1"))
    head_commit = revision.get("commit", revision.get("head", "HEAD"))
    impact_depth = options.get("impact_depth", DEFAULT_IMPACT_DEPTH)

    # Step 1: Get diff
    diff_text = _get_git_diff(workspace, base_commit, head_commit)

    if not diff_text:
        # No git diff available — try to analyze all files as "changed"
        warnings.append(
            f"git diff failed or empty ({base_commit}..{head_commit}); "
            "falling back to full directory analysis"
        )
        # Fallback: treat all C files as changed
        target_path = Path(workspace) / target.get("path", "")
        if target_path.is_dir():
            exts = {".c", ".h", ".cpp", ".cc", ".cxx", ".hpp"}
            c_files = sorted(
                [p for p in target_path.rglob("*") if p.suffix in exts and p.is_file()]
            )[:50]
            diff_files = []
            for fpath in c_files:
                rel = str(fpath.relative_to(workspace))
                diff_files.append({"file": rel, "added_lines": [], "removed_lines": []})
        else:
            return _result(findings, warnings, 0, 0, 0, 0)
    else:
        diff_files = _parse_unified_diff(diff_text)

    # Step 2: Map changed lines to functions
    changed_functions: dict[str, list[str]] = {}  # file -> [function names]
    all_changed_symbols: set[str] = set()

    for df in diff_files:
        all_lines = df["added_lines"] + df["removed_lines"]
        if all_lines:
            fns = _map_lines_to_functions(workspace, df["file"], all_lines)
        else:
            # File appears in diff but no line mapping available — parse all functions
            abs_path = Path(workspace) / df["file"]
            if abs_path.exists() and abs_path.suffix in {".c", ".h", ".cpp", ".cc", ".cxx", ".hpp"}:
                try:
                    parser = CodeParser()
                    syms = parser.parse_file(abs_path)
                    fns = [s.name for s in syms if s.kind == "function"]
                except Exception:
                    fns = []
            else:
                fns = []
        changed_functions[df["file"]] = fns
        all_changed_symbols.update(fns)

    # Step 3: Build call graph and propagate impact
    target_path = Path(workspace) / target.get("path", "")

    # Try to reuse upstream call graph, else build fresh
    m04_data = upstream.get("call_graph", {})
    cg: CallGraph | None = None

    if not m04_data:
        cg_obj, cg_warns = build_callgraph(workspace, target_path)
        cg = cg_obj
        warnings.extend(cg_warns)
    else:
        # Rebuild from upstream (simplified — always rebuild for accuracy)
        cg_obj, cg_warns = build_callgraph(workspace, target_path)
        cg = cg_obj
        warnings.extend(cg_warns)

    # Propagate through call graph
    impacted_symbols: dict[str, dict] = {}  # symbol -> {depth, changed_by}
    for sym in all_changed_symbols:
        # Direct impact
        impacted_symbols[sym] = {"depth": 0, "changed_by": sym, "type": "direct"}
        # Transitive callers
        callers = cg.get_callers(sym, depth=impact_depth)
        for caller in callers:
            if caller not in impacted_symbols or impacted_symbols[caller]["depth"] > 1:
                depth = 1  # simplified: mark depth based on get_callers depth param
                for d in range(1, impact_depth + 1):
                    if caller in cg.get_callers(sym, depth=d):
                        depth = d
                        break
                impacted_symbols[caller] = {
                    "depth": depth,
                    "changed_by": sym,
                    "type": f"transitive_{depth}hop",
                }

    # Step 4: Generate findings
    for file_path, fns in changed_functions.items():
        for fn in fns:
            fid += 1
            callers = sorted(cg.get_callers(fn, depth=impact_depth))
            findings.append({
                "finding_id": f"DI-F{fid:04d}",
                "module_id": MODULE_ID,
                "risk_type": "changed_core_path",
                "severity": "S2" if len(callers) >= 3 else "S3",
                "risk_score": min(0.5 + len(callers) * 0.05, 0.9),
                "title": f"Changed function: {fn}",
                "description": (
                    f"Function {fn} in {file_path} was modified. "
                    f"Impacts {len(callers)} callers."
                ),
                "file_path": file_path,
                "symbol_name": fn,
                "line_start": 0,
                "line_end": 0,
                "evidence": {
                    "changed_files": [file_path],
                    "changed_symbols": [fn],
                    "impacted_symbols": callers[:20],
                    "depth": impact_depth,
                },
            })

    # Transitive impact findings
    for sym, info in impacted_symbols.items():
        if info["type"] != "direct":
            fid += 1
            findings.append({
                "finding_id": f"DI-F{fid:04d}",
                "module_id": MODULE_ID,
                "risk_type": "transitive_impact",
                "severity": "S2" if info["depth"] == 1 else "S3",
                "risk_score": max(0.7 - info["depth"] * 0.15, 0.3),
                "title": f"Transitive impact on {sym} ({info['depth']}hop from {info['changed_by']})",
                "description": (
                    f"{sym} is a {info['type']} dependency of changed "
                    f"function {info['changed_by']}."
                ),
                "file_path": "",
                "symbol_name": sym,
                "line_start": 0,
                "line_end": 0,
                "evidence": {
                    "impact_type": info["type"],
                    "depth": info["depth"],
                    "changed_by": info["changed_by"],
                },
            })

    return _result(
        findings, warnings,
        len(diff_files), len(all_changed_symbols),
        len(impacted_symbols), len(cg.nodes) if cg else 0
    )


def _result(
    findings: list, warnings: list,
    files_changed: int, symbols_changed: int,
    symbols_impacted: int, callgraph_nodes: int,
) -> ModuleResult:
    risk = round(sum(f["risk_score"] for f in findings) / len(findings), 4) if findings else 0.0
    return {
        "module_id": MODULE_ID,
        "status": "success",
        "risk_score": risk,
        "findings": findings,
        "metrics": {
            "files_changed": files_changed,
            "symbols_changed": symbols_changed,
            "symbols_impacted": symbols_impacted,
            "callgraph_nodes": callgraph_nodes,
            "findings_count": len(findings),
        },
        "artifacts": [],
        "warnings": warnings,
    }
