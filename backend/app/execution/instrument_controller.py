"""仪器控制占位（协议分析/报文捕获）。

后续接入协议分析仪、网损仪等设备的启停与配置。
"""

from __future__ import annotations


def start_capture(device_config: dict | None = None) -> dict:
    """启动报文捕获。占位返回 ok。"""
    return {"ok": True, "message": "未实现"}


def stop_capture(capture_id: str | None = None) -> dict:
    """停止报文捕获。占位返回 ok。"""
    return {"ok": True, "message": "未实现"}
