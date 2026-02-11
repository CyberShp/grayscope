"""分析任务请求/响应数据模型定义。"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


# ── 请求模型 ──────────────────────────────────────────────────────────


class AnalysisTarget(BaseModel):
    path: str = ""
    functions: list[str] = []


class AnalysisRevision(BaseModel):
    branch: Optional[str] = "main"
    base_commit: Optional[str] = None
    head_commit: Optional[str] = None


class AnalysisAI(BaseModel):
    provider: str = "ollama"
    model: str = "qwen2.5-coder"
    prompt_profile: str = "default-v1"


class AnalysisOptions(BaseModel):
    callgraph_depth: int = Field(default=2, ge=1, le=5)
    max_files: int = Field(default=500, ge=1)
    risk_threshold: float = Field(default=0.6, ge=0.0, le=1.0)


SUPPORTED_MODULES = {
    "branch_path", "boundary_value", "error_path", "call_graph",
    "concurrency", "diff_impact", "coverage_map",
    "postmortem", "knowledge_pattern",
}
SUPPORTED_TASK_TYPES = {"full", "file", "function", "diff", "postmortem"}


class TaskCreateRequest(BaseModel):
    idempotency_key: Optional[str] = None
    project_id: int
    repo_id: int
    task_type: str = Field(..., pattern="^(full|file|function|diff|postmortem)$")
    target: AnalysisTarget = AnalysisTarget()
    revision: AnalysisRevision = AnalysisRevision()
    analyzers: list[str] = Field(..., min_length=1)
    ai: AnalysisAI = AnalysisAI()
    options: AnalysisOptions = AnalysisOptions()


class RetryRequest(BaseModel):
    modules: list[str] = []


# ── 响应模型 ──────────────────────────────────────────────────────────


class TaskCreateOut(BaseModel):
    task_id: str
    status: str
    created_at: datetime


class TaskProgress(BaseModel):
    total_modules: int
    finished_modules: int
    failed_modules: int


class TaskStatusOut(BaseModel):
    task_id: str
    task_type: str
    status: str
    progress: TaskProgress
    module_status: dict[str, str]
    created_at: datetime
    updated_at: datetime


class ModuleResultSummary(BaseModel):
    module: str
    display_name: str = ""
    status: str
    risk_score: Optional[float] = None
    finding_count: int = 0
    artifact_paths: list[str] = []


class TaskResultsOut(BaseModel):
    task_id: str
    status: str
    aggregate_risk_score: Optional[float] = None
    modules: list[ModuleResultSummary] = []


# ── 事后分析模型 ──────────────────────────────────────────────────────


class DefectInfo(BaseModel):
    title: str
    severity: str = "S1"
    description: str = ""
    related_commit: Optional[str] = None
    module_path: Optional[str] = None


class PostmortemRequest(BaseModel):
    project_id: int
    repo_id: int
    defect: DefectInfo
    ai: AnalysisAI = AnalysisAI()
