"""Ollama local model provider."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from app.ai.provider_base import ModelProvider

logger = logging.getLogger(__name__)


class OllamaProvider(ModelProvider):
    """Ollama exposes an OpenAI-compatible /v1/chat/completions endpoint
    as well as its native /api/chat endpoint.  We use the OpenAI-compat
    path so prompt format stays uniform.
    """

    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        default_model: str = "qwen2.5-coder",
        timeout: float = 180,
        proxy: str | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._default_model = default_model
        self._timeout = timeout
        self._proxy = proxy

    def name(self) -> str:
        return "ollama"

    async def health_check(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=10, proxy=self._proxy) as client:
                resp = await client.get(f"{self._base_url}/api/tags")
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
            "stream": False,
            **kwargs,
        }
        async with httpx.AsyncClient(timeout=self._timeout, proxy=self._proxy) as client:
            resp = await client.post(
                f"{self._base_url}/v1/chat/completions",
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()

        choices = data.get("choices") or [{}]
        choice = choices[0] if choices else {}
        return {
            "content": choice.get("message", {}).get("content", ""),
            "usage": data.get("usage", {}),
            "raw": data,
        }
