"""路径与资源分析器（P2 合并）。

统一运行 branch_path 与 error_path 分析，一次编排产出路径与资源/错误路径发现，
多函数交汇相关（如 cross_function_resource_leak）由 error_path 贡献。
"""

from __future__ import annotations

import logging
from typing import Any

from app.analyzers.base import AnalyzeContext, ModuleResult
from app.analyzers import branch_path_analyzer, error_path_analyzer

logger = logging.getLogger(__name__)

MODULE_ID = "path_and_resource"


def analyze(ctx: AnalyzeContext) -> ModuleResult:
    """运行分支路径 + 错误路径分析，合并发现与产物。"""
    bp_result: ModuleResult = branch_path_analyzer.analyze(ctx)
    ep_result: ModuleResult = error_path_analyzer.analyze(ctx)

    bp_findings = list(bp_result.get("findings", []) or [])
    ep_findings = list(ep_result.get("findings", []) or [])

    # 重写 finding_id 避免与单模块运行时的 ID 冲突，并标出来源
    for i, f in enumerate(bp_findings):
        f = dict(f)
        fid = f.get("finding_id") or f"PAR-BP-{i + 1:04d}"
        if not str(fid).startswith("PAR-"):
            fid = f"PAR-BP-{i + 1:04d}"
        f["finding_id"] = fid
        f["module_id"] = MODULE_ID
        bp_findings[i] = f

    for i, f in enumerate(ep_findings):
        f = dict(f)
        fid = f.get("finding_id") or f"PAR-EP-{i + 1:04d}"
        if not str(fid).startswith("PAR-"):
            fid = f"PAR-EP-{i + 1:04d}"
        f["finding_id"] = fid
        f["module_id"] = MODULE_ID
        ep_findings[i] = f

    merged_findings = bp_findings + ep_findings
    bp_artifacts = list(bp_result.get("artifacts", []) or [])
    ep_artifacts = list(ep_result.get("artifacts", []) or [])
    merged_artifacts = bp_artifacts + ep_artifacts

    risk_score = 0.0
    if merged_findings:
        risk_score = round(
            sum(f.get("risk_score") or 0 for f in merged_findings) / len(merged_findings),
            4,
        )

    warnings = list(bp_result.get("warnings", []) or []) + list(ep_result.get("warnings", []) or [])

    metrics: dict[str, Any] = {
        "findings_count": len(merged_findings),
        "branch_path_findings": len(bp_findings),
        "error_path_findings": len(ep_findings),
    }
    for k, v in (bp_result.get("metrics") or {}).items():
        if k not in metrics:
            metrics[k] = v
    for k, v in (ep_result.get("metrics") or {}).items():
        if k not in metrics:
            metrics[k] = v

    return {
        "module_id": MODULE_ID,
        "status": "success" if bp_result.get("status") == "success" and ep_result.get("status") == "success" else "failed",
        "risk_score": risk_score,
        "findings": merged_findings,
        "metrics": metrics,
        "artifacts": merged_artifacts,
        "warnings": warnings,
    }
