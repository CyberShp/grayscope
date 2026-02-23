"""branch_path 模块的规则：高复杂度、仅报 error/cleanup、switch 缺 default、goto 清理。"""

from __future__ import annotations

import re
from typing import Any

from app.analyzers.branch_path_lib import classify_branch, score_branch
from app.analyzers.rules import register_rule
from app.analyzers.rules.base import BaseRule

MODULE_ID = "branch_path"
_GOTO_RE = re.compile(r"\bgoto\b")

_TYPE_ZH = {"error": "错误处理", "cleanup": "资源清理", "boundary": "边界条件", "state": "状态/模式判断", "normal": "正常"}
_REASON_ZH = {
    "error": "错误处理分支，异常条件下触发；需验证错误路径与资源释放。",
    "cleanup": "资源清理分支，需验证所有退出路径都正确执行清理。",
    "boundary": "边界条件判断，需使用边界值、边界±1 进行测试。",
    "state": "状态/模式判断，需逐一测试每种状态值。",
    "normal": "正常执行路径，需验证输入组合下行为符合预期。",
}


@register_rule(MODULE_ID)
class HighComplexityRule(BaseRule):
    name = "high_complexity"
    description = "函数分支数达到阈值时产出一条汇总发现"
    risk_type = "branch_high_complexity"

    def evaluate(self, **kwargs: Any) -> list[dict[str, Any]]:
        symbol = kwargs.get("symbol")
        branches = kwargs.get("branches", [])
        cfg = kwargs.get("cfg")
        rel_path = kwargs.get("rel_path", "")
        options = kwargs.get("options", {})
        if not symbol or not branches or not cfg:
            return []
        threshold = options.get("branch_path_complexity_threshold", 10)
        if len(branches) < threshold:
            return []
        return [{
            "module_id": MODULE_ID,
            "risk_type": self.risk_type,
            "severity": "S2",
            "risk_score": 0.65,
            "title": f"{symbol.name}() 分支过多需重点覆盖",
            "description": f"函数 {symbol.name}() 共有 {len(branches)} 个分支，圈复杂度较高，常规测试易遗漏深层路径。建议：优先覆盖错误/清理路径，再使用边界组合覆盖关键分支。",
            "file_path": rel_path,
            "symbol_name": symbol.name,
            "line_start": symbol.line_start,
            "line_end": symbol.line_end,
            "evidence": {
                "branch_count": len(branches),
                "cfg_node_count": len(cfg.nodes),
                "cfg_edge_count": len(cfg.edges),
                "expected_failure": "深层路径未覆盖导致逻辑错误或资源问题",
                "unacceptable_outcomes": ["资源泄漏", "状态不一致", "崩溃"],
            },
        }]


@register_rule(MODULE_ID)
class ErrorCleanupOnlyRule(BaseRule):
    """仅对 error/cleanup 分支产出发现（减量模式）。"""
    name = "error_cleanup_only"
    description = "只产出错误处理与清理路径分支发现"
    risk_type = "branch_error"  # 或 branch_cleanup，按 path_type

    def evaluate(self, **kwargs: Any) -> list[dict[str, Any]]:
        symbol = kwargs.get("symbol")
        branches = kwargs.get("branches", [])
        cfg = kwargs.get("cfg")
        rel_path = kwargs.get("rel_path", "")
        options = kwargs.get("options", {})
        if not symbol or not cfg:
            return []
        reduce_mode = options.get("branch_path_reduce", True)
        out: list[dict[str, Any]] = []
        for br in branches:
            path_type = classify_branch(br.label)
            if reduce_mode and path_type not in ("error", "cleanup"):
                continue
            score = score_branch(path_type)
            _cond_text = br.label.replace("if ", "")
            reason = _REASON_ZH.get(path_type, f"分支条件: {br.label}")
            out.append({
                "module_id": MODULE_ID,
                "risk_type": f"branch_{path_type}",
                "severity": "S1" if score >= 0.8 else ("S2" if score >= 0.6 else "S3"),
                "risk_score": round(score, 2),
                "title": f"{symbol.name}() 中的{_TYPE_ZH.get(path_type, path_type)}分支",
                "description": reason,
                "file_path": rel_path,
                "symbol_name": symbol.name,
                "line_start": br.line,
                "line_end": br.line,
                "evidence": {
                    "branch_id": f"{symbol.name}#{br.node_id}",
                    "condition_expr": br.label.replace("if ", ""),
                    "path_type": path_type,
                    "cfg_node_count": len(cfg.nodes),
                    "cfg_edge_count": len(cfg.edges),
                    "expected_failure": {"error": "错误条件成立导致进入错误处理路径", "cleanup": "清理路径执行不完整"}.get(path_type, "分支条件触发异常行为"),
                    "unacceptable_outcomes": {"error": ["资源泄漏", "状态不一致", "崩溃"], "cleanup": ["资源泄漏", "重复释放"]}.get(path_type, ["崩溃", "不可恢复错误"]),
                },
            })
        return out


@register_rule(MODULE_ID)
class SwitchNoDefaultRule(BaseRule):
    """switch 语句缺少 default 分支时产出一条发现。"""
    name = "switch_no_default"
    description = "switch 缺少 default 分支"
    risk_type = "branch_switch_no_default"

    def evaluate(self, **kwargs: Any) -> list[dict[str, Any]]:
        symbol = kwargs.get("symbol")
        branches = kwargs.get("branches", [])
        cfg = kwargs.get("cfg")
        rel_path = kwargs.get("rel_path", "")
        if not symbol or not cfg:
            return []
        out: list[dict[str, Any]] = []
        for n in cfg.nodes:
            if n.kind != "branch" or not n.label.strip().lower().startswith("switch"):
                continue
            edges_from = [e for e in cfg.edges if e.src == n.node_id]
            has_default = any("default" in (e.label or "").lower() for e in edges_from)
            if has_default:
                continue
            cases = [e.label for e in edges_from if e.label]
            out.append({
                "module_id": MODULE_ID,
                "risk_type": self.risk_type,
                "severity": "S1",
                "risk_score": 0.75,
                "title": f"{symbol.name}() switch 缺少 default 分支",
                "description": "switch 语句缺少 default 分支，未预期的输入值可能被静默跳过。",
                "file_path": rel_path,
                "symbol_name": symbol.name,
                "line_start": n.line,
                "line_end": n.line,
                "evidence": {"subtype": "switch_no_default", "cases": cases},
            })
        return out


@register_rule(MODULE_ID)
class GotoCleanupRule(BaseRule):
    """函数源码中存在 goto 时产出一条清理路径发现。"""
    name = "goto_cleanup"
    description = "goto 清理模式需验证所有路径到达清理"
    risk_type = "branch_cleanup"

    def evaluate(self, **kwargs: Any) -> list[dict[str, Any]]:
        symbol = kwargs.get("symbol")
        rel_path = kwargs.get("rel_path", "")
        if not symbol or not getattr(symbol, "source", ""):
            return []
        if not _GOTO_RE.search(symbol.source):
            return []
        return [{
            "module_id": MODULE_ID,
            "risk_type": self.risk_type,
            "severity": "S2",
            "risk_score": 0.7,
            "title": f"{symbol.name}() 中的 goto 清理模式",
            "description": f"函数 {symbol.name}() 使用 goto 跳转到清理标签进行资源释放。需验证：(1) 所有错误路径是否都能到达清理标签；(2) 清理标签处是否释放了所有已分配的资源。",
            "file_path": rel_path,
            "symbol_name": symbol.name,
            "line_start": symbol.line_start,
            "line_end": symbol.line_end,
            "evidence": {
                "pattern": "goto_cleanup",
                "expected_failure": "清理路径执行不完整",
                "unacceptable_outcomes": ["资源泄漏", "重复释放"],
            },
        }]
