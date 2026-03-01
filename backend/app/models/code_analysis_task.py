"""Code analysis task persistence model.

Replaces in-memory _analysis_tasks dict with DB-backed storage,
so tasks survive server restarts / hot-reloads.
"""

from __future__ import annotations

from typing import Optional

from sqlalchemy import BigInteger, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class CodeAnalysisTask(TimestampMixin, Base):
    __tablename__ = "code_analysis_tasks"

    id: Mapped[int] = mapped_column(primary_key=True)
    analysis_id: Mapped[str] = mapped_column(
        String(64), unique=True, nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(
        String(24), nullable=False, default="running"
    )
    workspace_path: Mapped[str] = mapped_column(Text, nullable=False)
    project_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("projects.id"), nullable=True
    )
    repo_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("repositories.id"), nullable=True
    )
    enable_ai: Mapped[bool] = mapped_column(default=True)
    started_at: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    completed_at: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # JSON-serialized analysis result (progress + fused_graph + risks + narratives)
    result_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # JSON-serialized progress snapshot (always kept up-to-date even during run)
    progress_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Bridge to AnalysisTask for project-level risk/testcase integration
    bridge_task_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("analysis_tasks.id"), nullable=True
    )

    __table_args__ = (
        Index("ix_code_analysis_task_status", "status"),
        Index("ix_code_analysis_task_project", "project_id"),
    )
