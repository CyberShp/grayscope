"""规则基类：由规则决定是否产出某类风险，便于扩展。"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class BaseRule(ABC):
    """Layer 2 风险规则基类。evaluate 返回 0 或多个 finding 片段（dict）。"""

    name: str = "base_rule"
    description: str = ""
    risk_type: str = ""

    @abstractmethod
    def evaluate(self, **kwargs: Any) -> list[dict[str, Any]]:
        """根据上下文返回 finding 列表（每项为完整 finding 的 dict）。"""
        ...
