"""Provider registry: create, cache, and select model providers."""

from __future__ import annotations

import logging
from typing import Any

from app.ai.provider_base import ModelProvider
from app.ai.providers.custom import CustomProvider
from app.ai.providers.deepseek import DeepSeekProvider
from app.config import settings

logger = logging.getLogger(__name__)

# Singleton cache keyed by (provider_name, model)
_cache: dict[str, ModelProvider] = {}


class ProviderNotSupportedError(ValueError):
    """Raised when an unknown or unsupported provider is requested."""
    def __init__(self, provider_name: str):
        self.provider_name = provider_name
        super().__init__(
            f"不支持的 AI 提供商: {provider_name}。"
            f"支持的提供商: {', '.join(sorted(SUPPORTED_PROVIDERS))}"
        )


def _build(provider_name: str, **overrides: Any) -> ModelProvider:
    """Construct a provider instance from settings + optional overrides."""
    proxy = overrides.get("proxy", settings.ai_proxy)
    if provider_name == "deepseek":
        return DeepSeekProvider(
            base_url=overrides.get("base_url", settings.deepseek_base_url),
            api_key=overrides.get("api_key", settings.deepseek_api_key),
            default_model=overrides.get("model", "deepseek-coder"),
            proxy=proxy,
        )
    if provider_name == "custom":
        return CustomProvider(
            base_url=overrides.get("base_url", settings.custom_base_url),
            api_key=overrides.get("api_key", settings.custom_api_key),
            default_model=overrides.get("model", settings.custom_model),
            chat_path=overrides.get("chat_path", "/v1/chat/completions"),
            health_path=overrides.get("health_path", "/v1/models"),
            proxy=proxy,
        )
    raise ProviderNotSupportedError(provider_name)


def get_provider(provider_name: str, **overrides: Any) -> ModelProvider:
    """Get or create a cached provider instance.
    
    When api_key or base_url is explicitly passed, build uncached to avoid
    using stale cached providers with different credentials.
    """
    if overrides.get("api_key") is not None or overrides.get("base_url") is not None:
        return _build(provider_name, **overrides)
    cache_key = f"{provider_name}:{overrides.get('model', 'default')}"
    if cache_key not in _cache:
        _cache[cache_key] = _build(provider_name, **overrides)
    return _cache[cache_key]


def build_provider_uncached(provider_name: str, **overrides: Any) -> ModelProvider:
    """Build a provider instance without caching (e.g. for test with custom api_key/base_url)."""
    return _build(provider_name, **overrides)


def clear_cache() -> None:
    _cache.clear()


SUPPORTED_PROVIDERS = {"deepseek", "custom"}
