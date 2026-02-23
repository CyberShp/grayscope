"""规则注册表：按模块注册规则，分析器通过 get_rules(module_id) 获取并执行。"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.analyzers.rules.base import BaseRule

# module_id -> list of rule classes
_RULES: dict[str, list[type[BaseRule]]] = {}


def register_rule(module_id: str):
    """装饰器：将规则注册到指定模块。"""

    def _decorator(cls: type[BaseRule]) -> type[BaseRule]:
        _RULES.setdefault(module_id, []).append(cls)
        return cls

    return _decorator


def get_rules(module_id: str, names: list[str] | None = None) -> list[BaseRule]:
    """获取某模块的规则实例，可选按名称过滤。"""
    classes = _RULES.get(module_id, [])
    if names:
        classes = [c for c in classes if c.name in names]
    return [c() for c in classes]


def list_rules(module_id: str | None = None) -> list[dict[str, str]]:
    """列出已注册规则。若指定 module_id 则只返回该模块的规则。"""
    out: list[dict[str, str]] = []
    for mid, clist in _RULES.items():
        if module_id and mid != module_id:
            continue
        for c in clist:
            out.append({
                "module_id": mid,
                "name": c.name,
                "description": c.description,
                "risk_type": c.risk_type,
            })
    return out
