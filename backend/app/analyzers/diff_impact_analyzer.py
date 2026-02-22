"""差异影响分析器（增强版）。

分析代码变更（diff），通过调用图映射影响传播，
识别传递性回归风险区域并推荐回归测试。
增强: 智能深度替代硬编码 depth=2，双向追踪(callers+callees)，
结合数据流识别变更的返回值经N层调用被用于关键判断。
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

# Default max depth (now much deeper than the old hardcoded 2)
DEFAULT_MAX_DEPTH = 12
DEFAULT_BASE_DEPTH = 3


def _compute_smart_depth(
    fn: str, cg: CallGraph, risk_scores: dict[str, float], max_depth: int,
) -> int:
    """根据函数风险和调用频率动态决定追踪深度。"""
    base = DEFAULT_BASE_DEPTH
    fi = cg.fan_in(fn)
    fo = cg.fan_out(fn)
    risk = risk_scores.get(fn, 0.0)

    if risk > 0.7:
        base += 4
    elif risk > 0.4:
        base += 2

    if fi > 5:
        base += 2
    elif fi > 2:
        base += 1

    if fo > 5:
        base += 1

    return min(base, max_depth)


def _parse_unified_diff(diff_text: str) -> list[dict]:
    """Parse a unified diff into structured changed-file records."""
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
    """Run diff impact analysis (enhanced with smart depth & bidirectional tracing)."""
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
    max_depth = options.get("callgraph_depth", DEFAULT_MAX_DEPTH)

    # ── 从上游提取数据流信息 ──────────────────────────────────────
    data_flow_chains = _extract_data_flow_chains(upstream)
    upstream_risk_scores = _extract_risk_scores(upstream)

    # Step 1: Get diff
    diff_text = _get_git_diff(workspace, base_commit, head_commit)

    if not diff_text:
        warnings.append(
            f"git diff failed or empty ({base_commit}..{head_commit}); "
            "falling back to full directory analysis"
        )
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
    changed_functions: dict[str, list[str]] = {}
    all_changed_symbols: set[str] = set()

    for df in diff_files:
        all_lines = df["added_lines"] + df["removed_lines"]
        if all_lines:
            fns = _map_lines_to_functions(workspace, df["file"], all_lines)
        else:
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

    # Step 3: Build call graph
    target_path = Path(workspace) / target.get("path", "")
    cg_obj, cg_warns = build_callgraph(workspace, target_path)
    cg = cg_obj
    warnings.extend(cg_warns)

    # Step 4: Smart depth + bidirectional propagation
    impacted_symbols: dict[str, dict] = {}

    for sym in all_changed_symbols:
        # 计算智能深度
        smart_depth = _compute_smart_depth(sym, cg, upstream_risk_scores, max_depth)

        # Direct impact
        impacted_symbols[sym] = {
            "depth": 0,
            "changed_by": sym,
            "type": "direct",
            "direction": "self",
        }

        # ── 向上追踪: 谁调用了变更函数 (callers) ─────────────────
        for d in range(1, smart_depth + 1):
            callers_at_d = cg.get_callers(sym, depth=d) - cg.get_callers(sym, depth=d - 1) if d > 1 else cg.get_callers(sym, depth=1)
            for caller in callers_at_d:
                if caller not in impacted_symbols or impacted_symbols[caller].get("depth", 999) > d:
                    impacted_symbols[caller] = {
                        "depth": d,
                        "changed_by": sym,
                        "type": f"caller_{d}hop",
                        "direction": "upstream",
                    }

        # ── 向下追踪: 变更函数调用了谁 (callees) ─────────────────
        # 变更函数内部逻辑改变，它调用的函数可能收到不同的参数
        for d in range(1, min(smart_depth, 4) + 1):  # 下游追踪深度略小
            callees_at_d = cg.get_callees(sym, depth=d) - (cg.get_callees(sym, depth=d - 1) if d > 1 else set())
            for callee in callees_at_d:
                key = callee
                if key not in impacted_symbols or impacted_symbols[key].get("depth", 999) > d:
                    impacted_symbols[key] = {
                        "depth": d,
                        "changed_by": sym,
                        "type": f"callee_{d}hop",
                        "direction": "downstream",
                    }

    # Step 5: Generate findings
    for file_path, fns in changed_functions.items():
        for fn in fns:
            fid += 1
            smart_depth = _compute_smart_depth(fn, cg, upstream_risk_scores, max_depth)
            callers = sorted(cg.get_callers(fn, depth=smart_depth))
            callees = sorted(cg.get_callees(fn, depth=2))

            # 检查是否有数据流传播链穿过这个变更函数
            affected_chains = _find_chains_through_function(fn, data_flow_chains)

            evidence: dict[str, Any] = {
                "changed_files": [file_path],
                "changed_symbols": [fn],
                "impacted_callers": callers[:20],
                "impacted_callees": callees[:10],
                "depth": smart_depth,
                "direction": "bidirectional",
                "related_functions": [fn] + callers[:5] + callees[:5],
                "expected_failure": "变更导致行为或契约变化，调用者未适配",
                "unacceptable_outcomes": ["功能回归", "崩溃", "错误返回值"],
            }

            if affected_chains:
                evidence["affected_data_flow_chains"] = affected_chains[:5]

            description = (
                f"文件 {file_path} 中的函数 {fn}() 发生了代码变更。"
                f"向上影响 {len(callers)} 个调用者"
                + (f"（{', '.join(callers[:5])}）" if callers else "")
                + f"，向下影响 {len(callees)} 个被调函数"
                + (f"（{', '.join(callees[:3])}）" if callees else "")
                + "。"
            )
            if affected_chains:
                description += (
                    f"\n有 {len(affected_chains)} 条数据流传播链经过此函数，"
                    f"变更可能导致整条传播链上的值域/语义发生变化。"
                )

            findings.append({
                "finding_id": f"DI-F{fid:04d}",
                "module_id": MODULE_ID,
                "risk_type": "changed_core_path",
                "severity": "S1" if len(callers) >= 5 or affected_chains else ("S2" if len(callers) >= 3 else "S3"),
                "risk_score": min(0.5 + len(callers) * 0.03 + len(callees) * 0.02 + len(affected_chains) * 0.05, 0.95),
                "title": f"变更函数: {fn}()（影响 {len(callers)} 上游 + {len(callees)} 下游）",
                "description": description,
                "file_path": file_path,
                "symbol_name": fn,
                "line_start": 0,
                "line_end": 0,
                "evidence": evidence,
            })

    # Transitive impact findings
    for sym, info in impacted_symbols.items():
        if info["type"] == "direct":
            continue

        fid += 1
        direction_label = "上游（调用者）" if info["direction"] == "upstream" else "下游（被调者）"

        # 检查该受影响函数是否有数据流链
        sym_chains = _find_chains_through_function(sym, data_flow_chains)

        description = (
            f"函数 {sym}() 通过{direction_label}调用链间接受到变更函数 {info['changed_by']}() 的影响，"
            f"影响传播距离为 {info['depth']} 跳。"
        )

        if info["direction"] == "downstream":
            description += (
                f"由于 {info['changed_by']}() 内部逻辑改变，传递给 {sym}() 的参数"
                f"可能发生变化，需要验证 {sym}() 在新参数下的行为。"
            )
        else:
            description += (
                f"虽然 {sym}() 自身代码未变更，但其依赖的上游函数行为可能已改变。"
            )

        if sym_chains:
            description += (
                f"\n此外，有 {len(sym_chains)} 条数据流传播链经过 {sym}()，"
                f"变更的影响可能沿这些链进一步扩散。"
            )

        findings.append({
            "finding_id": f"DI-F{fid:04d}",
            "module_id": MODULE_ID,
            "risk_type": "transitive_impact",
            "severity": "S2" if info["depth"] <= 2 else "S3",
            "risk_score": max(0.7 - info["depth"] * 0.08, 0.2),
            "title": (
                f"{sym}() 受到{direction_label}传递性影响"
                f"（距变更函数 {info['changed_by']}() {info['depth']} 跳）"
            ),
            "description": description,
            "file_path": cg.function_files.get(sym, ""),
            "symbol_name": sym,
            "line_start": 0,
            "line_end": 0,
            "evidence": {
                "impact_type": info["type"],
                "depth": info["depth"],
                "direction": info["direction"],
                "changed_by": info["changed_by"],
                "data_flow_chains_affected": len(sym_chains),
                "related_functions": [sym, info.get("changed_by", "")],
                "expected_failure": "传递性影响导致间接依赖行为变化",
                "unacceptable_outcomes": ["回归", "契约违反"],
            },
        })

    return _result(
        findings, warnings,
        len(diff_files), len(all_changed_symbols),
        len(impacted_symbols), len(cg.nodes) if cg else 0
    )


def _extract_data_flow_chains(upstream: dict[str, dict]) -> list[dict]:
    """从上游 data_flow 提取传播链。"""
    df_data = upstream.get("data_flow", {})
    chains = []
    for finding in df_data.get("findings", []):
        ev = finding.get("evidence", {})
        chain = ev.get("propagation_chain")
        if chain:
            chains.append({
                "path": chain,
                "entry_function": ev.get("entry_function", ""),
            })
    return chains


def _extract_risk_scores(upstream: dict[str, dict]) -> dict[str, float]:
    """从上游所有模块提取函数级风险评分。"""
    scores: dict[str, float] = {}
    for mod_id, mod_data in upstream.items():
        for finding in mod_data.get("findings", []):
            sym = finding.get("symbol_name", "")
            risk = finding.get("risk_score", 0.0)
            if sym and risk > scores.get(sym, 0.0):
                scores[sym] = risk
    return scores


def _find_chains_through_function(fn: str, chains: list[dict]) -> list[dict]:
    """查找经过指定函数的数据流传播链。"""
    result = []
    for chain in chains:
        path = chain.get("path", [])
        for step in path:
            if step.get("function") == fn:
                result.append(chain)
                break
    return result


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
