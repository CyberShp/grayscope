"""Custom internal REST model provider.

This adapter is designed for internal distilled models that may expose
a non-standard REST API.  It can be configured via ``extra_json`` in
model_configs to customize the request/response mapping.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from app.ai.provider_base import ModelProvider

logger = logging.getLogger(__name__)


class CustomRESTProvider(ModelProvider):
    """Flexible adapter for any internal model service.

    Default assumption: the endpoint expects a JSON body with a ``messages``
    field and returns a JSON body with a ``response`` or ``content`` field.
    """

    def __init__(
        self,
        base_url: str = "http://localhost:9000",
        api_key: str | None = None,
        default_model: str = "distill-v1",
        timeout: float = 180,
        chat_path: str = "/v1/chat/completions",
        health_path: str = "/health",
        response_content_key: str = "choices.0.message.content",
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key or ""
        self._default_model = default_model
        self._timeout = timeout
        self._chat_path = chat_path
        self._health_path = health_path
        self._response_content_key = response_content_key

    def name(self) -> str:
        return "custom_rest"

    async def health_check(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    f"{self._base_url}{self._health_path}",
                    headers=self._headers(),
                )
                return resp.status_code == 200
        except Exception:
            return False

    async def chat(
        self,
        messages: list[dict[str, str]],
        *,
        model: str | None = None,
        temperature: float = 0.3,
        max_tokens: int = 4096,
        **kwargs: Any,
    ) -> dict:
        payload = {
            "model": model or self._default_model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            **kwargs,
        }
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.post(
                f"{self._base_url}{self._chat_path}",
                json=payload,
                headers=self._headers(),
            )
            resp.raise_for_status()
            data = resp.json()

        content = self._extract(data, self._response_content_key)
        return {
            "content": content,
            "usage": data.get("usage", {}),
            "raw": data,
        }

    # --- helpers ---

    def _headers(self) -> dict[str, str]:
        h: dict[str, str] = {"Content-Type": "application/json"}
        if self._api_key:
            h["Authorization"] = f"Bearer {self._api_key}"
        return h

    @staticmethod
    def _extract(data: Any, key_path: str) -> str:
        """Navigate ``data`` with a dot-separated path like
        ``choices.0.message.content``.
        """
        current = data
        for part in key_path.split("."):
            if isinstance(current, list):
                try:
                    current = current[int(part)]
                except (IndexError, ValueError):
                    return ""
            elif isinstance(current, dict):
                current = current.get(part, "")
            else:
                return ""
        return str(current) if current else ""
