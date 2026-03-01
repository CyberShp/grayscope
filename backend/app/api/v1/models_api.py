"""Model provider management and testing endpoints."""

from __future__ import annotations

import asyncio
import time

from fastapi import APIRouter

from app.ai.provider_registry import SUPPORTED_PROVIDERS, get_provider, build_provider_uncached
from app.config import settings
from app.core.response import error, ok
from app.schemas.model_config import ModelListOut, ModelTestOut, ModelTestRequest, ProviderModels

router = APIRouter()

# Provider metadata for the frontend
_PROVIDER_META = {
    "deepseek": {
        "display_name": "DeepSeek",
        "provider_type": "cloud",
        "default_models": ["deepseek-coder", "deepseek-chat"],
    },
    "custom": {
        "display_name": "自定义接口",
        "provider_type": "custom",
        "default_models": ["default"],
    },
}

_BASE_URLS = {
    "deepseek": lambda: settings.deepseek_base_url,
    "custom": lambda: settings.custom_base_url,
}


@router.get("/models")
async def list_models() -> dict:
    providers = []
    for p in sorted(SUPPORTED_PROVIDERS):
        meta = _PROVIDER_META.get(p, {})
        base_url_fn = _BASE_URLS.get(p)
        # 快速健康检查（10s 超时）
        healthy = None
        try:
            prov = get_provider(p)
            healthy = await prov.health_check()
        except Exception:
            healthy = False
        providers.append({
            "provider_id": p,
            "display_name": meta.get("display_name", p),
            "provider_type": meta.get("provider_type", "unknown"),
            "base_url": base_url_fn() if base_url_fn else None,
            "models": meta.get("default_models", ["default"]),
            "healthy": healthy,
        })
    return ok({"providers": providers})


def _safe_setattr(obj: object, attr: str, value: object) -> bool:
    """Safely set attribute on a Pydantic Settings object.
    
    Pydantic V2 Settings may be frozen; handle by accessing __dict__ directly
    or using object.__setattr__.
    """
    try:
        setattr(obj, attr, value)
        return True
    except (TypeError, ValueError):
        try:
            object.__setattr__(obj, attr, value)
            return True
        except Exception:
            pass
    try:
        obj.__dict__[attr] = value
        return True
    except Exception:
        return False


@router.get("/models/defaults")
def get_model_defaults() -> dict:
    """获取默认 AI 配置（provider、model、proxy）。"""
    return ok({
        "default_provider": settings.default_provider,
        "default_model": settings.default_model,
        "ai_proxy": settings.ai_proxy,
    })


@router.post("/models/config")
def update_model_config(body: dict) -> dict:
    """更新 AI 模型配置（API key、base_url、proxy、default_provider、default_model 等）。

    仅更新内存中的 settings 对象；持久化需写入 .env 文件。
    """
    provider = body.get("provider")
    api_key = body.get("api_key")
    base_url = body.get("base_url")
    proxy = body.get("proxy")
    default_provider = body.get("default_provider")
    default_model = body.get("default_model")

    if not provider:
        return error("INVALID_REQUEST", "provider 字段必填")

    changed = []
    if api_key is not None:
        attr = f"{provider}_api_key"
        if hasattr(settings, attr):
            if _safe_setattr(settings, attr, api_key):
                changed.append(attr)
        # 清除缓存以使新配置生效
        from app.ai.provider_registry import clear_cache
        clear_cache()
    if base_url is not None:
        attr = f"{provider}_base_url"
        if hasattr(settings, attr):
            if _safe_setattr(settings, attr, base_url):
                changed.append(attr)
        from app.ai.provider_registry import clear_cache
        clear_cache()
    if proxy is not None:
        if _safe_setattr(settings, "ai_proxy", proxy if proxy else None):
            changed.append("ai_proxy")
        from app.ai.provider_registry import clear_cache
        clear_cache()
    if default_provider is not None:
        if _safe_setattr(settings, "default_provider", default_provider):
            changed.append("default_provider")
    if default_model is not None:
        if _safe_setattr(settings, "default_model", default_model):
            changed.append("default_model")

    # 持久化到 .env 文件
    if changed:
        _persist_env(provider, api_key, base_url, proxy, default_provider, default_model)

    return ok({"updated": changed})


def _persist_env(
    provider: str,
    api_key: str | None,
    base_url: str | None,
    proxy: str | None = None,
    default_provider: str | None = None,
    default_model: str | None = None,
) -> None:
    """将 AI 配置追加/更新到 .env 文件。"""
    from pathlib import Path
    # backend/ is 4 levels up from app/api/v1/models_api.py
    env_path = Path(__file__).resolve().parent.parent.parent.parent / ".env"
    lines: list[str] = []
    if env_path.exists():
        lines = env_path.read_text().splitlines()

    def _set(key: str, val: str) -> None:
        for i, ln in enumerate(lines):
            if ln.startswith(f"{key}="):
                lines[i] = f"{key}={val}"
                return
        lines.append(f"{key}={val}")

    prefix = f"GS_{provider.upper()}"
    if api_key is not None:
        _set(f"{prefix}_API_KEY", api_key)
    if base_url is not None:
        _set(f"{prefix}_BASE_URL", base_url)
    if proxy is not None:
        _set("GS_AI_PROXY", proxy)
    if default_provider is not None:
        _set("GS_DEFAULT_PROVIDER", default_provider)
    if default_model is not None:
        _set("GS_DEFAULT_MODEL", default_model)

    env_path.write_text("\n".join(lines) + "\n")


@router.post("/models/test")
def test_model(req: ModelTestRequest) -> dict:
    if req.provider not in SUPPORTED_PROVIDERS:
        return error("INVALID_REQUEST", f"unknown provider: {req.provider}")

    overrides = {"model": req.model}
    if req.api_key is not None:
        overrides["api_key"] = req.api_key
    if req.base_url is not None:
        overrides["base_url"] = req.base_url.rstrip("/")
    # Use fresh provider when caller passes api_key/base_url so sk is sent for this test
    if req.api_key is not None or req.base_url is not None:
        provider = build_provider_uncached(req.provider, **overrides)
    else:
        provider = get_provider(req.provider, **overrides)
    start = time.time()
    try:
        healthy = asyncio.get_event_loop().run_until_complete(provider.health_check())
    except RuntimeError:
        # no running event loop (sync context)
        import asyncio as aio

        healthy = aio.run(provider.health_check())
    elapsed_ms = int((time.time() - start) * 1000)

    if not healthy:
        return error(
            "MODEL_PROVIDER_UNAVAILABLE",
            f"provider {req.provider} is not reachable",
        )
    return ok(
        ModelTestOut(
            provider=req.provider,
            model=req.model,
            latency_ms=elapsed_ms,
        ).model_dump(),
        message="provider healthy",
    )
