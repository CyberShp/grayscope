from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class ExportRequest(BaseModel):
    format: str = Field(..., pattern="^(json|csv|markdown)$")
    include_modules: list[str] = []
    content: str = Field(..., pattern="^(test_cases|findings|summary)$")


class ExportOut(BaseModel):
    export_id: str
    status: str = "pending"


class ExportStatusOut(BaseModel):
    export_id: str
    status: str
    download_url: Optional[str] = None
