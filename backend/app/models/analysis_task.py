from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import BigInteger, DateTime, Float, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class AnalysisTask(TimestampMixin, Base):
    __tablename__ = "analysis_tasks"

    id: Mapped[int] = mapped_column(primary_key=True)
    task_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    project_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("projects.id"), nullable=False
    )
    repo_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("repositories.id"), nullable=False
    )
    task_type: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    target_json: Mapped[str] = mapped_column(Text, nullable=False)
    revision_json: Mapped[str] = mapped_column(Text, nullable=False)
    analyzers_json: Mapped[str] = mapped_column(Text, nullable=False)
    ai_json: Mapped[str] = mapped_column(Text, nullable=False)
    options_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    aggregate_risk_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    error_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    idempotency_key: Mapped[Optional[str]] = mapped_column(
        String(128), unique=True, nullable=True
    )
    created_by: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    finished_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # V2: 分析支柱 exception/concurrency/protocol/full
    pillar: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)

    # relationships
    module_results = relationship(
        "AnalysisModuleResult", back_populates="task", lazy="selectin"
    )

    __table_args__ = (
        Index("ix_task_project_created", "project_id", "created_at"),
        Index("ix_task_repo_created", "repo_id", "created_at"),
        Index("ix_task_status_updated", "status", "updated_at"),
    )

    # --- Valid states and transitions ---
    VALID_STATUSES = {
        "pending",
        "running",
        "partial_failed",
        "success",
        "failed",
        "cancelled",
    }
    VALID_TASK_TYPES = {"full", "file", "function", "diff", "postmortem", "code_analysis"}
    RETRYABLE_STATUSES = {"failed", "partial_failed", "success"}
    CANCELLABLE_STATUSES = {"pending", "running"}
