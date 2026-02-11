"""Analyzer base protocol and shared types used by all modules."""

from __future__ import annotations

from typing import Any, Protocol, TypedDict


class AnalyzeContext(TypedDict):
    task_id: str
    project_id: int
    repo_id: int
    workspace_path: str
    target: dict[str, Any]
    revision: dict[str, Any]
    options: dict[str, Any]
    upstream_results: dict[str, dict[str, Any]]


class ModuleResult(TypedDict):
    module_id: str
    status: str
    risk_score: float
    findings: list[dict[str, Any]]
    metrics: dict[str, Any]
    artifacts: list[dict[str, Any]]
    warnings: list[str]


class Analyzer(Protocol):
    """Every analyzer module must satisfy this protocol."""

    module_id: str
    depends_on: list[str]

    def analyze(self, ctx: AnalyzeContext) -> ModuleResult:
        ...
