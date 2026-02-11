"""Qwen (通义千问) provider via DashScope compatible-mode endpoint."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from app.ai.provider_base import ModelProvider

logger = logging.getLogger(__name__)


class QwenProvider(ModelProvider):
    """DashScope provides an OpenAI-compatible endpoint at
    ``https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions``.
    """

    def __init__(
        self,
        base_url: str = "https://dashscope.aliyuncs.com/compatible-mode",
        api_key: str | None = None,
        default_model: str = "qwen-plus",
        timeout: float = 120,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key or ""
        self._default_model = default_model
        self._timeout = timeout

    def name(self) -> str:
        return "qwen"

    async def health_check(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    f"{self._base_url}/v1/models",
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
                f"{self._base_url}/v1/chat/completions",
                json=payload,
                headers=self._headers(),
            )
            resp.raise_for_status()
            data = resp.json()

        choice = data.get("choices", [{}])[0]
        return {
            "content": choice.get("message", {}).get("content", ""),
            "usage": data.get("usage", {}),
            "raw": data,
        }

    def _headers(self) -> dict[str, str]:
        h: dict[str, str] = {"Content-Type": "application/json"}
        if self._api_key:
            h["Authorization"] = f"Bearer {self._api_key}"
        return h
