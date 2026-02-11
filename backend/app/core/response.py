"""Standard response envelope used across all API endpoints."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class ApiResponse(BaseModel):
    code: str = "OK"
    message: str = "success"
    data: Any = None


def ok(data: Any = None, message: str = "success") -> dict:
    return ApiResponse(code="OK", message=message, data=data).model_dump()


def error(code: str, message: str, data: Any = None) -> dict:
    return ApiResponse(code=code, message=message, data=data).model_dump()
