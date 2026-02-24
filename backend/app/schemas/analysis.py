"""分析任务请求/响应数据模型定义。"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


# ── 请求模型 ──────────────────────────────────────────────────────────


class AnalysisTarget(BaseModel):
    path: str = ""
    functions: list[str] = []
    target_files: list[str] = []  # 可选：仅分析这些文件（大仓增量/变更文件）


class AnalysisRevision(BaseModel):
    branch: Optional[str] = "main"
    base_commit: Optional[str] = None
    head_commit: Optional[str] = None


class AnalysisAI(BaseModel):
    provider: str = "ollama"
    model: str = "qwen2.5-coder"
    prompt_profile: str = "default-v1"


class MrDiffFile(BaseModel):
    """MR/PR 单文件变更：修改前与修改后内容，供「代码变更」板块展示。"""
    path: str = ""
    old_content: Optional[str] = None
    new_content: Optional[str] = None
    unified_diff: Optional[str] = None  # 可选：直接存 unified diff 文本


class AnalysisOptions(BaseModel):
    callgraph_depth: int = Field(default=12, ge=1, le=20)
    max_files: int = Field(default=500, ge=1)
    risk_threshold: float = Field(default=0.6, ge=0.0, le=1.0)
    enable_data_flow: bool = True
    enable_cross_module_ai: bool = True
    # MR/PR 代码变更（可选）：链接与修改前/后内容，供前端「MR 代码变更」板块展示
    mr_url: Optional[str] = Field(default=None, max_length=2048)
    mr_diff: Optional[list[dict[str, Any]]] = None  # [{ path, old_content?, new_content?, unified_diff? }]
    # V2: 任务来源 repo=仅仓库 / mr=仅MR / mr_repo=MR+关联仓库（推荐）
    task_source: Optional[str] = Field(default="repo", max_length=16)
    # V2: 分析支柱 exception/concurrency/protocol/full
    pillar: Optional[str] = Field(default="full", max_length=32)


SUPPORTED_MODULES = {
    "branch_path", "boundary_value", "error_path", "call_graph",
    "path_and_resource", "exception", "protocol",
    "data_flow", "concurrency", "diff_impact", "coverage_map",
    "postmortem", "knowledge_pattern",
}
SUPPORTED_TASK_TYPES = {"full", "file", "function", "diff", "postmortem"}
PILLAR_VALUES = {"exception", "concurrency", "protocol", "full"}
TASK_SOURCE_VALUES = {"repo", "mr", "mr_repo"}


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


class TaskMrUpdate(BaseModel):
    """更新任务关联的 MR/PR 链接与代码变更（供「MR 代码变更」板块展示）。"""
    mr_url: Optional[str] = Field(default=None, max_length=2048)
    mr_diff: Optional[list[dict[str, Any]]] = None  # [{ path, old_content?, new_content?, unified_diff? }]


class CoverageImportRequest(BaseModel):
    """北向接口：写入覆盖率数据。format=summary 时需提供 files；format=granular 时需提供 covered 或 tests。"""
    source_system: Optional[str] = Field(default="", max_length=128)
    revision: Optional[str] = Field(default="", max_length=256)
    format: str = Field(..., pattern="^(summary|granular)$")
    files: Optional[dict[str, Any]] = None
    covered: Optional[list[dict[str, Any]]] = None
    tests: Optional[list[dict[str, Any]]] = None


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
    project_id: int = 0
    repo_id: int = 0
    task_type: str
    status: str
    progress: TaskProgress
    module_status: dict[str, str]
    created_at: datetime
    updated_at: datetime
    error_json: Optional[str] = None  # 含 cross_module_ai 等扩展，供前端展示多函数交汇临界点
    options: Optional[dict[str, Any]] = None  # 含 mr_url、mr_diff、task_source 等
    pillar: Optional[str] = None  # V2 分析支柱


class ModuleResultSummary(BaseModel):
    module: str
    display_name: str = ""
    status: str
    risk_score: Optional[float] = None
    finding_count: int = 0
    artifact_paths: list[str] = []


class TaskResultsOut(BaseModel):
    task_id: str
    project_id: int = 0
    repo_id: int = 0
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
