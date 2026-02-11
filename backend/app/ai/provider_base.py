"""Abstract base class for all AI model providers."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class ModelProvider(ABC):
    """Every provider must implement chat, health_check, and name."""

    @abstractmethod
    async def chat(
        self,
        messages: list[dict[str, str]],
        *,
        model: str | None = None,
        temperature: float = 0.3,
        max_tokens: int = 4096,
        **kwargs: Any,
    ) -> dict:
        """Send messages and return structured response dict.

        The response must contain at least:
        - ``content``: the model's reply text
        - ``usage``: token usage dict (prompt_tokens, completion_tokens)
        """
        ...

    @abstractmethod
    async def health_check(self) -> bool:
        """Return True if the provider endpoint is reachable."""
        ...

    @abstractmethod
    def name(self) -> str:
        """Provider identifier string."""
        ...
