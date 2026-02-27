"""Mock/Stub 生成器：从 call_graph 产出 gmock 头或 C 桩函数声明，供函数级 DT 链接。"""

from __future__ import annotations

import re
from typing import Any


def _safe_cpp_id(s: str) -> str:
    """生成合法 C++ 标识符。"""
    if not s:
        return "unknown"
    out = re.sub(r"[^a-zA-Z0-9_]", "_", s)
    if out and out[0].isdigit():
        out = "_" + out
    return out[:64] if len(out) > 64 else out


def generate_mock_header(
    symbol_under_test: str,
    callees: list[str],
    call_graph_artifact: dict[str, Any] | None = None,
    style: str = "stub",
) -> str:
    """
    根据被调函数列表生成 gmock 头或 C 桩声明。

    :param symbol_under_test: 被测函数名（用于注释）
    :param callees: 需要 mock 的被调函数名列表（来自 call_graph evidence.callees）
    :param call_graph_artifact: 可选 call_graph 产物，用于补充签名信息
    :param style: "stub" -> extern "C" 桩声明；"gmock" -> gmock 类（需 C++ 接口）
    :return: 头文件内容
    """
    lines = [
        "// Mock/Stub 由 GrayScope 从 call_graph 自动生成",
        f"// 被测函数: {symbol_under_test}",
        "// 以下被调函数需在链接时替换为此桩或 mock 实现",
        "",
    ]
    seen: set[str] = set()
    for callee in callees:
        name = (callee or "").strip()
        if not name or name in seen:
            continue
        seen.add(name)
        safe = _safe_cpp_id(name)
        if style == "gmock":
            lines.append(f"// Mock 类: {name}（请根据实际签名补充 MOCK_METHOD）")
            lines.append(f"class Mock{safe} {{")
            lines.append(" public:")
            lines.append(f"  MOCK_METHOD(int, {safe}, ());  // 占位：请按实际签名修改")
            lines.append("};")
        else:
            lines.append(f"// 桩: {name}（占位实现，请按实际签名修改）")
            lines.append(f'extern "C" int {safe}(void);  // 或带参版本")
        lines.append("")
    if not seen:
        lines.append("// 无 callees，无需 mock。")
        lines.append("")
    return "\n".join(lines).strip()


def generate_stub_from_finding(finding: dict[str, Any]) -> str:
    """
    从单条 finding 的 evidence.callees 生成该用例所需的 stub 头内容。
    """
    ev = finding.get("evidence") or {}
    callees = ev.get("callees") or []
    if isinstance(callees, str):
        callees = [s.strip() for s in callees.split(",") if s.strip()]
    symbol = finding.get("symbol_name") or finding.get("target_function") or "target"
    return generate_mock_header(symbol, list(callees), style="stub")


def generate_gmock_from_call_graph_artifact(
    symbol_under_test: str,
    call_graph_artifact: dict[str, Any],
) -> str:
    """
    从 call_graph 产物的 simple_edges 中取 symbol_under_test 的 callees，生成 gmock 头。
    """
    callees = []
    for e in call_graph_artifact.get("simple_edges") or call_graph_artifact.get("edges") or []:
        if isinstance(e, dict) and e.get("src") == symbol_under_test:
            dst = e.get("dst") or e.get("callee")
            if dst:
                callees.append(dst)
    if not callees and call_graph_artifact.get("edges"):
        for e in call_graph_artifact["edges"]:
            if isinstance(e, dict) and e.get("src") == symbol_under_test:
                dst = e.get("dst") or e.get("callee")
                if dst:
                    callees.append(dst)
    return generate_mock_header(
        symbol_under_test,
        callees,
        call_graph_artifact=call_graph_artifact,
        style="gmock",
    )
