from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class ModelTestRequest(BaseModel):
    provider: str
    model: str
    timeout_sec: int = Field(default=20, ge=1, le=120)
    api_key: Optional[str] = None
    base_url: Optional[str] = None


class ModelTestOut(BaseModel):
    provider: str
    model: str
    latency_ms: int


class ProviderModels(BaseModel):
    provider: str
    models: list[str]


class ModelListOut(BaseModel):
    providers: list[ProviderModels]
