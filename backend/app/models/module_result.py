"""分析模块执行结果数据模型。"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import BigInteger, DateTime, Float, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class AnalysisModuleResult(TimestampMixin, Base):
    """分析模块执行结果表，记录每个模块的分析状态、发现和指标。"""

    __tablename__ = "analysis_module_results"

    id: Mapped[int] = mapped_column(primary_key=True)
    task_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("analysis_tasks.id"), nullable=False
    )
    module_id: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    risk_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    findings_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    metrics_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    artifacts_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    ai_summary_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    error_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    started_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    finished_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # 关联关系
    task = relationship("AnalysisTask", back_populates="module_results")

    __table_args__ = (
        UniqueConstraint("task_id", "module_id", name="uq_module_result_task_module"),
        Index("ix_module_result_task_status", "task_id", "status"),
        Index("ix_module_result_module_status", "module_id", "status"),
    )

    VALID_STATUSES = {"success", "failed", "skipped", "cancelled", "running", "pending"}
    VALID_MODULES = {
        "branch_path", "boundary_value", "error_path", "call_graph",
        "data_flow", "concurrency", "diff_impact", "coverage_map",
        "postmortem", "knowledge_pattern",
    }
