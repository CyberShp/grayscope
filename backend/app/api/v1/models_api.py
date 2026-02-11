"""Model provider management and testing endpoints."""

from __future__ import annotations

import asyncio
import time

from fastapi import APIRouter

from app.ai.provider_registry import SUPPORTED_PROVIDERS, get_provider
from app.core.response import error, ok
from app.schemas.model_config import ModelListOut, ModelTestOut, ModelTestRequest, ProviderModels

router = APIRouter()


@router.get("/models")
def list_models() -> dict:
    providers = [
        ProviderModels(provider=p, models=["default"])
        for p in sorted(SUPPORTED_PROVIDERS)
    ]
    return ok(ModelListOut(providers=providers).model_dump())


@router.post("/models/test")
def test_model(req: ModelTestRequest) -> dict:
    if req.provider not in SUPPORTED_PROVIDERS:
        return error("INVALID_REQUEST", f"unknown provider: {req.provider}")

    provider = get_provider(req.provider, model=req.model)
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
