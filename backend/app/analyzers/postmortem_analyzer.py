"""事后分析器。

分析逃逸缺陷，将缺陷元数据与代码结构（通过上游分支路径/错误路径分析发现）
和 AI 推理进行关联，产出：
- 根因链
- 缺失的测试策略缺口
- 预防性测试建议
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

from app.analyzers.base import AnalyzeContext, ModuleResult
from app.analyzers.code_parser import CodeParser

logger = logging.getLogger(__name__)

MODULE_ID = "postmortem"

# Common root-cause categories in storage systems
_ROOT_CAUSE_CATEGORIES = [
    "error_path_not_tested",
    "boundary_not_covered",
    "concurrency_race",
    "state_transition_gap",
    "resource_lifecycle_leak",
    "config_parameter_edge",
    "protocol_message_malformed",
    "upgrade_compatibility_miss",
    "hardware_fault_injection_absent",
    "retry_logic_flaw",
]


def analyze(ctx: AnalyzeContext) -> ModuleResult:
    """Run postmortem analysis on an escaped defect."""
    workspace = ctx["workspace_path"]
    target = ctx["target"]
    options = ctx["options"]
    upstream = ctx["upstream_results"]

    findings: list[dict[str, Any]] = []
    warnings: list[str] = []
    fid = 0

    # Extract defect metadata from target
    defect = target.get("defect", {})
    defect_title = defect.get("title", "Unknown defect")
    defect_severity = defect.get("severity", "S1")
    defect_desc = defect.get("description", "")
    related_commit = defect.get("related_commit", "")
    module_path = defect.get("module_path", target.get("path", ""))

    if not defect_title:
        warnings.append("No defect title provided")
        return _result(findings, warnings, 0)

    # Phase 1: Correlate with upstream analysis findings
    upstream_correlations = _correlate_upstream(defect, upstream)

    # Phase 2: Static analysis of related code
    code_findings = _analyze_related_code(workspace, module_path, defect)

    # Phase 3: Generate root cause chain
    root_cause_chain = _infer_root_causes(
        defect, upstream_correlations, code_findings
    )

    # Phase 4: Generate preventive test suggestions
    preventive_tests = _generate_preventive_tests(
        defect, root_cause_chain, upstream_correlations
    )

    # Finding 1: Root cause analysis
    fid += 1
    findings.append({
        "finding_id": f"PM-F{fid:04d}",
        "module_id": MODULE_ID,
        "risk_type": "escaped_defect_root_cause",
        "severity": defect_severity,
        "risk_score": 0.9,
        "title": f"Root cause analysis: {defect_title}",
        "description": (
            f"Escaped defect '{defect_title}' analyzed. "
            f"Identified {len(root_cause_chain)} root cause factors "
            f"and {len(preventive_tests)} preventive test suggestions."
        ),
        "file_path": module_path,
        "symbol_name": "",
        "line_start": 0,
        "line_end": 0,
        "evidence": {
            "defect_title": defect_title,
            "defect_severity": defect_severity,
            "defect_description": defect_desc,
            "root_cause_chain": root_cause_chain,
            "preventive_tests": preventive_tests,
            "upstream_correlations": upstream_correlations[:10],
            "related_commit": related_commit,
        },
    })

    # Finding 2: Missing test strategy
    if preventive_tests:
        fid += 1
        findings.append({
            "finding_id": f"PM-F{fid:04d}",
            "module_id": MODULE_ID,
            "risk_type": "missing_test_strategy",
            "severity": "S1" if defect_severity in ("S0", "S1") else "S2",
            "risk_score": 0.85,
            "title": f"Missing test strategies for: {defect_title}",
            "description": (
                f"{len(preventive_tests)} test strategies identified that "
                "could have prevented this defect."
            ),
            "file_path": module_path,
            "symbol_name": "",
            "line_start": 0,
            "line_end": 0,
            "evidence": {
                "preventive_tests": preventive_tests,
                "gap_categories": [rc["category"] for rc in root_cause_chain],
            },
        })

    # Finding 3: Per-code-finding correlations
    for cf in code_findings[:5]:
        fid += 1
        findings.append({
            "finding_id": f"PM-F{fid:04d}",
            "module_id": MODULE_ID,
            "risk_type": "escaped_defect_root_cause",
            "severity": cf.get("severity", "S2"),
            "risk_score": cf.get("risk_score", 0.7),
            "title": cf["title"],
            "description": cf["description"],
            "file_path": cf.get("file_path", module_path),
            "symbol_name": cf.get("symbol_name", ""),
            "line_start": cf.get("line_start", 0),
            "line_end": cf.get("line_end", 0),
            "evidence": cf.get("evidence", {}),
        })

    return _result(findings, warnings, len(root_cause_chain))


def _correlate_upstream(
    defect: dict, upstream: dict[str, dict]
) -> list[dict]:
    """Find upstream findings that correlate with the defect."""
    correlations = []
    defect_text = (
        defect.get("title", "") + " " + defect.get("description", "")
    ).lower()

    # Keywords from defect
    keywords = set(re.findall(r"\b\w{4,}\b", defect_text))

    for mod_id, mod_data in upstream.items():
        for f in mod_data.get("findings", []):
            finding_text = (
                f.get("title", "") + " " + f.get("description", "")
            ).lower()
            finding_keywords = set(re.findall(r"\b\w{4,}\b", finding_text))
            overlap = keywords & finding_keywords
            if len(overlap) >= 2:
                correlations.append({
                    "finding_id": f.get("finding_id", ""),
                    "module_id": mod_id,
                    "title": f.get("title", ""),
                    "overlap_keywords": sorted(overlap)[:5],
                    "risk_score": f.get("risk_score", 0),
                })

    # Sort by relevance (overlap count)
    correlations.sort(
        key=lambda x: len(x.get("overlap_keywords", [])), reverse=True
    )
    return correlations


def _analyze_related_code(
    workspace: str, module_path: str, defect: dict
) -> list[dict]:
    """Analyze the code at the defect location for patterns."""
    findings = []
    target_path = Path(workspace) / module_path

    if not target_path.exists():
        return findings

    try:
        parser = CodeParser()
        if target_path.is_file():
            symbols = parser.parse_file(target_path)
        else:
            symbols = parser.parse_directory(target_path, max_files=20)
    except Exception:
        return findings

    functions = [s for s in symbols if s.kind == "function"]
    defect_text = (
        defect.get("title", "") + " " + defect.get("description", "")
    ).lower()

    for sym in functions:
        # Check if function is likely related to the defect
        if sym.name.lower() in defect_text or _is_keyword_match(
            sym.name, defect_text
        ):
            src = sym.source

            # Check common patterns
            if re.search(r"\bgoto\b", src) and re.search(r"return\s+-", src):
                findings.append({
                    "title": f"Complex error handling in defect-related function {sym.name}",
                    "description": f"Function {sym.name} uses goto + error returns, a common root cause pattern",
                    "severity": "S2",
                    "risk_score": 0.75,
                    "file_path": str(target_path),
                    "symbol_name": sym.name,
                    "line_start": sym.line_start,
                    "line_end": sym.line_end,
                    "evidence": {"pattern": "goto_error_return"},
                })

            if re.search(r"\b(malloc|calloc|realloc)\b", src):
                frees = len(re.findall(r"\bfree\b", src))
                allocs = len(re.findall(r"\b(malloc|calloc|realloc)\b", src))
                if allocs > frees:
                    findings.append({
                        "title": f"Potential resource leak in {sym.name}",
                        "description": f"{allocs} allocations vs {frees} frees detected",
                        "severity": "S1",
                        "risk_score": 0.8,
                        "file_path": str(target_path),
                        "symbol_name": sym.name,
                        "line_start": sym.line_start,
                        "line_end": sym.line_end,
                        "evidence": {
                            "alloc_count": allocs,
                            "free_count": frees,
                        },
                    })

    return findings


def _is_keyword_match(func_name: str, text: str) -> bool:
    """Check if function name words overlap with defect text."""
    parts = re.findall(r"[a-z]+", func_name.lower())
    return any(p in text and len(p) >= 4 for p in parts)


def _infer_root_causes(
    defect: dict, correlations: list[dict], code_findings: list[dict]
) -> list[dict]:
    """Infer root cause chain from all analysis evidence."""
    causes = []
    defect_text = (
        defect.get("title", "") + " " + defect.get("description", "")
    ).lower()

    # Pattern matching against known categories
    category_keywords = {
        "error_path_not_tested": ["error", "return", "errno", "fail", "exception"],
        "boundary_not_covered": ["boundary", "max", "min", "overflow", "limit", "size", "length"],
        "concurrency_race": ["race", "concurrent", "lock", "mutex", "thread", "parallel", "deadlock"],
        "state_transition_gap": ["state", "transition", "status", "switch", "phase", "failover"],
        "resource_lifecycle_leak": ["leak", "memory", "resource", "handle", "fd", "socket", "alloc"],
        "config_parameter_edge": ["config", "parameter", "setting", "option", "threshold"],
        "protocol_message_malformed": ["protocol", "message", "packet", "format", "parse", "serialize"],
        "upgrade_compatibility_miss": ["upgrade", "version", "compatibility", "migration", "schema"],
        "retry_logic_flaw": ["retry", "timeout", "reconnect", "backoff", "idempotent"],
    }

    for cat, keywords in category_keywords.items():
        if any(kw in defect_text for kw in keywords):
            causes.append({
                "category": cat,
                "confidence": 0.7 + 0.1 * sum(kw in defect_text for kw in keywords),
                "evidence": f"Keywords matched: {[kw for kw in keywords if kw in defect_text]}",
            })

    # Add causes from correlations
    if correlations:
        for corr in correlations[:3]:
            mod = corr["module_id"]
            if mod == "branch_path":
                causes.append({
                    "category": "error_path_not_tested",
                    "confidence": 0.8,
                    "evidence": f"Correlated with {corr['finding_id']}: {corr['title']}",
                })
            elif mod == "error_path":
                causes.append({
                    "category": "resource_lifecycle_leak",
                    "confidence": 0.8,
                    "evidence": f"Correlated with {corr['finding_id']}: {corr['title']}",
                })
            elif mod == "concurrency":
                causes.append({
                    "category": "concurrency_race",
                    "confidence": 0.85,
                    "evidence": f"Correlated with {corr['finding_id']}: {corr['title']}",
                })

    # Add causes from code findings
    for cf in code_findings:
        ev = cf.get("evidence", {})
        pattern = ev.get("pattern", "")
        if pattern == "goto_error_return":
            causes.append({
                "category": "error_path_not_tested",
                "confidence": 0.75,
                "evidence": f"Found goto+error pattern in {cf.get('symbol_name', '?')}",
            })
        if ev.get("alloc_count", 0) > ev.get("free_count", 0):
            causes.append({
                "category": "resource_lifecycle_leak",
                "confidence": 0.8,
                "evidence": f"Allocation imbalance in {cf.get('symbol_name', '?')}",
            })

    # Deduplicate by category, keeping highest confidence
    seen: dict[str, dict] = {}
    for c in causes:
        cat = c["category"]
        if cat not in seen or c["confidence"] > seen[cat]["confidence"]:
            seen[cat] = c
    return sorted(seen.values(), key=lambda x: x["confidence"], reverse=True)


def _generate_preventive_tests(
    defect: dict, root_causes: list[dict], correlations: list[dict]
) -> list[dict]:
    """Generate preventive test suggestions based on root causes."""
    tests = []
    tid = 0

    test_templates = {
        "error_path_not_tested": [
            "Inject error at each allocation/IO point and verify cleanup",
            "Test all error return paths with fault injection",
            "Verify errno propagation through the call chain",
        ],
        "boundary_not_covered": [
            "Test with min, min-1, max, max+1 boundary values",
            "Test with zero-length and maximum-length inputs",
            "Fuzz with values near size/count limits",
        ],
        "concurrency_race": [
            "Run concurrent read/write stress test with TSan",
            "Test lock ordering under concurrent access patterns",
            "Inject delays at critical sections to expose races",
        ],
        "state_transition_gap": [
            "Test all state transitions including re-entrant paths",
            "Inject failures during state transitions",
            "Test recovery from interrupted state changes",
        ],
        "resource_lifecycle_leak": [
            "Track resource allocation/deallocation through valgrind/ASan",
            "Test error paths with resource leak detection enabled",
            "Verify cleanup after abnormal termination",
        ],
        "config_parameter_edge": [
            "Test with minimum and maximum config values",
            "Test with default, zero, and extremely large config values",
            "Test config hot-reload during active operations",
        ],
        "retry_logic_flaw": [
            "Test retry exhaustion with persistent failures",
            "Verify idempotency across retries",
            "Test concurrent retry from multiple callers",
        ],
    }

    for rc in root_causes:
        cat = rc["category"]
        templates = test_templates.get(cat, ["General regression test for this category"])
        for tmpl in templates:
            tid += 1
            tests.append({
                "test_id": f"PT-{tid:03d}",
                "category": cat,
                "description": tmpl,
                "priority": "P1" if rc["confidence"] >= 0.8 else "P2",
                "confidence": round(rc["confidence"], 2),
            })

    return tests


def _result(
    findings: list, warnings: list, root_cause_count: int
) -> ModuleResult:
    risk = round(
        sum(f["risk_score"] for f in findings) / len(findings), 4
    ) if findings else 0.0
    return {
        "module_id": MODULE_ID,
        "status": "success",
        "risk_score": risk,
        "findings": findings,
        "metrics": {
            "root_cause_categories": root_cause_count,
            "findings_count": len(findings),
        },
        "artifacts": [],
        "warnings": warnings,
    }
