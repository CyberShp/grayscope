"""DeepSeek API provider."""

from __future__ import annotations

import logging
from typing import Any
from urllib.parse import urlparse

import httpx

from app.ai.provider_base import ModelProvider

logger = logging.getLogger(__name__)

# Hosts that should bypass proxy (internal/local endpoints)
_NO_PROXY_HOSTS = {"localhost", "127.0.0.1", "::1"}


def _should_bypass_proxy(url: str) -> bool:
    """Check if the URL should bypass proxy (localhost, 127.0.0.1, etc.)."""
    try:
        parsed = urlparse(url)
        host = parsed.hostname or ""
        return host.lower() in _NO_PROXY_HOSTS or host.startswith("192.168.") or host.startswith("10.")
    except Exception:
        return False


class DeepSeekProvider(ModelProvider):
    """DeepSeek uses an OpenAI-compatible chat completions endpoint."""

    def __init__(
        self,
        base_url: str = "https://api.deepseek.com",
        api_key: str | None = None,
        default_model: str = "deepseek-coder",
        timeout: float = 120,
        proxy: str | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key or ""
        self._default_model = default_model
        self._timeout = timeout
        # Bypass proxy for localhost/internal IPs to avoid 504/407 errors
        self._proxy = None if _should_bypass_proxy(self._base_url) else proxy

    def name(self) -> str:
        return "deepseek"

    async def health_check(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=10, proxy=self._proxy) as client:
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
        async with httpx.AsyncClient(timeout=self._timeout, proxy=self._proxy) as client:
            resp = await client.post(
                f"{self._base_url}/v1/chat/completions",
                json=payload,
                headers=self._headers(),
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

    def _headers(self) -> dict[str, str]:
        h: dict[str, str] = {"Content-Type": "application/json"}
        if self._api_key:
            h["Authorization"] = f"Bearer {self._api_key}"
        return h
