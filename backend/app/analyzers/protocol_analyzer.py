"""协议/报文分析器（V2 支柱三占位）。

占位实现：后续接入 pcap 解析、报文序列与仪器控制。
"""

from __future__ import annotations

import logging
from pathlib import Path

from app.analyzers.base import AnalyzeContext, ModuleResult

logger = logging.getLogger(__name__)

MODULE_ID = "protocol"


def analyze(ctx: AnalyzeContext) -> ModuleResult:
    """占位：返回空发现，协议分析待接入 pcap/仪器。"""
    workspace = ctx.get("workspace_path", "")
    target = ctx.get("target", {})
    target_path = Path(workspace) / target.get("path", "")
    if not target_path.exists():
        return {
            "module_id": MODULE_ID,
            "status": "success",
            "risk_score": 0.0,
            "findings": [],
            "metrics": {"files_scanned": 0, "protocol_placeholder": True},
            "artifacts": [],
            "warnings": ["协议分析器为占位实现，尚未接入 pcap/仪器"],
        }
    return {
        "module_id": MODULE_ID,
        "status": "success",
        "risk_score": 0.0,
        "findings": [],
        "metrics": {"protocol_placeholder": True},
        "artifacts": [],
        "warnings": [],
    }
