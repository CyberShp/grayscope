"""覆盖率适配器接口与数据类型。"""

from __future__ import annotations

from typing import Any, Protocol


class CoverageData:
    """覆盖率数据（占位）。"""
    def __init__(self, files: dict[str, Any] | None = None):
        self.files = files or {}


class CoverageAdapter(Protocol):
    """覆盖率数据源适配器协议。"""

    def fetch_coverage(self, project_id: int, revision: str) -> CoverageData:
        ...
    def get_call_chains(self, function_name: str) -> list[dict[str, Any]]:
        ...
    def get_test_mapping(self, test_case_id: int) -> list[dict[str, Any]]:
        ...


class StubCoverageAdapter:
    """占位覆盖率适配器：返回空数据，用于 gcov/北向接口未接入时。"""

    def fetch_coverage(self, project_id: int, revision: str) -> CoverageData:
        return CoverageData()

    def get_call_chains(self, function_name: str) -> list[dict[str, Any]]:
        return []

    def get_test_mapping(self, test_case_id: int) -> list[dict[str, Any]]:
        return []
