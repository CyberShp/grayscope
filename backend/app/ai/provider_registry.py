"""Provider registry: create, cache, and select model providers."""

from __future__ import annotations

import logging
from typing import Any

from app.ai.provider_base import ModelProvider
from app.ai.providers.custom_rest import CustomRESTProvider
from app.ai.providers.deepseek import DeepSeekProvider
from app.ai.providers.ollama import OllamaProvider
from app.ai.providers.openai_compat import OpenAICompatProvider
from app.ai.providers.qwen import QwenProvider
from app.config import settings

logger = logging.getLogger(__name__)

# Singleton cache keyed by (provider_name, model)
_cache: dict[str, ModelProvider] = {}


def _build(provider_name: str, **overrides: Any) -> ModelProvider:
    """Construct a provider instance from settings + optional overrides."""
    if provider_name == "ollama":
        return OllamaProvider(
            base_url=overrides.get("base_url", settings.ollama_base_url),
            default_model=overrides.get("model", settings.default_model),
        )
    if provider_name == "deepseek":
        return DeepSeekProvider(
            base_url=overrides.get("base_url", settings.deepseek_base_url),
            api_key=overrides.get("api_key", settings.deepseek_api_key),
            default_model=overrides.get("model", "deepseek-coder"),
        )
    if provider_name == "qwen":
        return QwenProvider(
            base_url=overrides.get("base_url", settings.qwen_base_url),
            api_key=overrides.get("api_key", settings.qwen_api_key),
            default_model=overrides.get("model", "qwen-plus"),
        )
    if provider_name == "openai_compat":
        return OpenAICompatProvider(
            base_url=overrides.get("base_url", settings.openai_compat_base_url),
            api_key=overrides.get("api_key", settings.openai_compat_api_key),
            default_model=overrides.get("model", "default"),
        )
    if provider_name == "custom_rest":
        return CustomRESTProvider(
            base_url=overrides.get("base_url", settings.custom_rest_base_url),
            api_key=overrides.get("api_key", settings.custom_rest_api_key),
            default_model=overrides.get("model", "distill-v1"),
            chat_path=overrides.get("chat_path", "/v1/chat/completions"),
            health_path=overrides.get("health_path", "/health"),
        )
    raise ValueError(f"unknown provider: {provider_name}")


def get_provider(provider_name: str, **overrides: Any) -> ModelProvider:
    """Get or create a cached provider instance."""
    cache_key = f"{provider_name}:{overrides.get('model', 'default')}"
    if cache_key not in _cache:
        _cache[cache_key] = _build(provider_name, **overrides)
    return _cache[cache_key]


def clear_cache() -> None:
    _cache.clear()


SUPPORTED_PROVIDERS = {"ollama", "deepseek", "qwen", "openai_compat", "custom_rest"}
