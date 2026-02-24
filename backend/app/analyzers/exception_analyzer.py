"""异常分支分析器（V2 支柱一）。

统一错误路径与分支路径分析，聚焦 C/C++ 异常分支、资源生命周期、错误传播。
"""

from __future__ import annotations

import logging
from typing import Any

from app.analyzers.base import AnalyzeContext, ModuleResult
from app.analyzers import path_and_resource_analyzer

logger = logging.getLogger(__name__)

MODULE_ID = "exception"


def analyze(ctx: AnalyzeContext) -> ModuleResult:
    """运行路径与资源分析，并为所有发现打上 pillar=exception。"""
    result: ModuleResult = path_and_resource_analyzer.analyze(ctx)
    findings = list(result.get("findings", []) or [])
    out_findings = []
    for f in findings:
        f = dict(f)
        f["pillar"] = "exception"
        if "evidence" in f and isinstance(f["evidence"], dict):
            ev = dict(f["evidence"])
            ev["pillar"] = "exception"
            f["evidence"] = ev
        out_findings.append(f)
    result = dict(result)
    result["findings"] = out_findings
    result["module_id"] = MODULE_ID
    return result
