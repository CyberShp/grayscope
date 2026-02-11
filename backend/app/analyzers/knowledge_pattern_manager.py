"""缺陷知识库管理器。

将事后分析输出归一化为可复用的缺陷模式，
持久化到知识库，并提供相似度匹配功能。
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from difflib import SequenceMatcher
from typing import Any

from app.analyzers.base import AnalyzeContext, ModuleResult

logger = logging.getLogger(__name__)

MODULE_ID = "knowledge_pattern"


def analyze(ctx: AnalyzeContext) -> ModuleResult:
    """Run knowledge pattern extraction and matching.

    Consumes postmortem output to create/update defect patterns.
    """
    upstream = ctx["upstream_results"]

    findings: list[dict[str, Any]] = []
    warnings: list[str] = []
    fid = 0

    m18_data = upstream.get("postmortem", {})
    m18_findings = m18_data.get("findings", [])

    if not m18_findings:
        warnings.append("无事后分析发现可用")
        return _result(findings, warnings, 0, 0)

    # Extract patterns from postmortem findings
    patterns_extracted = 0
    for f in m18_findings:
        if f.get("risk_type") != "escaped_defect_root_cause":
            continue

        evidence = f.get("evidence", {})
        root_causes = evidence.get("root_cause_chain", [])
        preventive_tests = evidence.get("preventive_tests", [])
        defect_title = evidence.get("defect_title", "")

        for rc in root_causes:
            category = rc.get("category", "unknown")
            confidence = rc.get("confidence", 0.5)

            # Generate pattern key
            pattern_key = _generate_pattern_key(category, defect_title)

            # Build pattern record
            trigger_shape = {
                "category": category,
                "keywords": _extract_keywords(defect_title + " " + evidence.get("defect_description", "")),
                "confidence": confidence,
            }

            code_signature = {
                "file_pattern": f.get("file_path", ""),
                "symbol_pattern": f.get("symbol_name", ""),
                "related_risk_types": [
                    corr.get("module_id", "") + ":" + corr.get("finding_id", "")
                    for corr in evidence.get("upstream_correlations", [])[:5]
                ],
            }

            # Filter relevant preventive tests
            relevant_tests = [
                t for t in preventive_tests
                if t.get("category") == category
            ]
            test_template = {
                "test_suggestions": relevant_tests[:5],
                "auto_generated": True,
            }

            fid += 1
            patterns_extracted += 1
            findings.append({
                "finding_id": f"KP-F{fid:04d}",
                "module_id": MODULE_ID,
                "risk_type": "pattern_extracted",
                "severity": "S3",
                "risk_score": round(confidence * 0.5, 2),
                "title": f"Pattern extracted: {pattern_key}",
                "description": (
                    f"Defect pattern '{category}' extracted from postmortem "
                    f"of '{defect_title}'. Confidence: {confidence:.0%}."
                ),
                "file_path": f.get("file_path", ""),
                "symbol_name": "",
                "line_start": 0,
                "line_end": 0,
                "evidence": {
                    "pattern_key": pattern_key,
                    "trigger_shape": trigger_shape,
                    "code_signature": code_signature,
                    "test_template": test_template,
                    "source_finding_id": f.get("finding_id", ""),
                },
            })

    return _result(findings, warnings, patterns_extracted, len(m18_findings))


def _generate_pattern_key(category: str, defect_title: str) -> str:
    """Generate a deterministic pattern key."""
    normalized = re.sub(r"[^a-z0-9]+", "_", defect_title.lower().strip())[:60]
    hash_suffix = hashlib.md5(
        (category + ":" + defect_title).encode()
    ).hexdigest()[:8]
    return f"{category}__{normalized}__{hash_suffix}"


def _extract_keywords(text: str) -> list[str]:
    """Extract meaningful keywords from text."""
    words = re.findall(r"\b[a-z]{4,}\b", text.lower())
    # Remove very common words
    stopwords = {
        "this", "that", "with", "from", "have", "been", "were",
        "will", "would", "could", "should", "their", "there",
        "than", "then", "when", "what", "which", "where",
        "about", "after", "before", "under", "over",
    }
    return sorted(set(w for w in words if w not in stopwords))[:20]


def match_patterns(
    findings: list[dict],
    known_patterns: list[dict],
    threshold: float = 0.4,
) -> list[dict]:
    """Match new findings against known defect patterns.

    Parameters
    ----------
    findings : list
        Current analysis findings to match against
    known_patterns : list
        Historical defect patterns from database
    threshold : float
        Minimum similarity score to include

    Returns
    -------
    list of match records with similarity scores
    """
    matches = []

    for pattern in known_patterns:
        trigger = pattern.get("trigger_shape", {})
        pattern_keywords = set(trigger.get("keywords", []))
        pattern_category = trigger.get("category", "")

        for f in findings:
            finding_text = (
                f.get("title", "") + " " +
                f.get("description", "") + " " +
                f.get("risk_type", "")
            ).lower()
            finding_keywords = set(re.findall(r"\b[a-z]{4,}\b", finding_text))

            # Keyword overlap similarity
            if pattern_keywords and finding_keywords:
                overlap = pattern_keywords & finding_keywords
                keyword_sim = len(overlap) / max(
                    len(pattern_keywords | finding_keywords), 1
                )
            else:
                keyword_sim = 0.0

            # Category match bonus
            category_bonus = 0.3 if pattern_category == f.get("risk_type", "") else 0.0

            # Text similarity
            text_sim = SequenceMatcher(
                None,
                pattern.get("name", "").lower(),
                f.get("title", "").lower(),
            ).ratio()

            similarity = round(
                keyword_sim * 0.4 + text_sim * 0.3 + category_bonus, 4
            )

            if similarity >= threshold:
                matches.append({
                    "pattern_key": pattern.get("pattern_key", ""),
                    "pattern_name": pattern.get("name", ""),
                    "finding_id": f.get("finding_id", ""),
                    "similarity": similarity,
                    "test_template": pattern.get("test_template", {}),
                })

    matches.sort(key=lambda x: x["similarity"], reverse=True)
    return matches


def _result(
    findings: list, warnings: list,
    patterns_extracted: int, postmortem_findings: int,
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
            "patterns_extracted": patterns_extracted,
            "postmortem_findings_evaluated": postmortem_findings,
            "findings_count": len(findings),
        },
        "artifacts": [],
        "warnings": warnings,
    }
