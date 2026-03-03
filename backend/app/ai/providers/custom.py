"""Unified custom AI provider supporting OpenAI-compatible APIs.

Combines functionality from OpenAI-compat and Custom-REST providers into
a single unified adapter. Works with any OpenAI-compatible endpoint including
vLLM, TGI, LMStudio, internal deployments, and custom model services.
"""

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


class CustomProvider(ModelProvider):
    """Unified adapter for custom/internal AI model services.
    
    Supports standard OpenAI-compatible API format with configurable paths
    for health check and chat completions.
    """

    def __init__(
        self,
        base_url: str = "http://localhost:8000",
        api_key: str | None = None,
        default_model: str = "default",
        timeout: float = 180,
        chat_path: str = "/v1/chat/completions",
        health_path: str = "/v1/models",
        response_content_key: str = "choices.0.message.content",
        proxy: str | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key or ""
        self._default_model = default_model
        self._timeout = timeout
        self._chat_path = chat_path
        self._health_path = health_path
        self._response_content_key = response_content_key
        # Bypass proxy for localhost/internal IPs to avoid 504/407 errors
        self._proxy = None if _should_bypass_proxy(self._base_url) else proxy

    def name(self) -> str:
        return "custom"

    async def health_check(self) -> bool:
        """Check if the service is reachable."""
        try:
            async with httpx.AsyncClient(timeout=10, proxy=self._proxy) as client:
                resp = await client.get(
                    f"{self._base_url}{self._health_path}",
                    headers=self._headers(),
                )
                return resp.status_code == 200
        except Exception:
            # Fall back to checking the chat endpoint with HEAD
            try:
                async with httpx.AsyncClient(timeout=10, proxy=self._proxy) as client:
                    resp = await client.options(
                        f"{self._base_url}{self._chat_path}",
                        headers=self._headers(),
                    )
                    return resp.status_code in (200, 204, 405)
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
        """Send chat completion request."""
        payload = {
            "model": model or self._default_model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            **kwargs,
        }
        async with httpx.AsyncClient(timeout=self._timeout, proxy=self._proxy) as client:
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

    def _headers(self) -> dict[str, str]:
        h: dict[str, str] = {"Content-Type": "application/json"}
        if self._api_key:
            h["Authorization"] = f"Bearer {self._api_key}"
        return h

    @staticmethod
    def _extract(data: Any, key_path: str) -> str:
        """Navigate data with a dot-separated path like 'choices.0.message.content'."""
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
