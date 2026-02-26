"""测试运行：一次批量执行（多个用例）的聚合记录。"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class TestRun(Base):
    """一次测试运行：选择若干用例、在指定环境下执行，汇总通过/失败/覆盖率。"""
    __tablename__ = "test_runs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(
        String(36), unique=True, nullable=False,
        default=lambda: str(uuid.uuid4()),
    )
    task_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("analysis_tasks.id"), nullable=True,
    )
    project_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("projects.id"), nullable=True,
    )
    status: Mapped[str] = mapped_column(
        String(24), nullable=False, default="pending",
        server_default="pending",
    )  # pending / running / paused / cancelled / success / failed
    environment: Mapped[str] = mapped_column(
        String(32), nullable=False, default="docker",
        server_default="docker",
    )  # docker / ssh
    total: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    passed: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    failed: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    skipped: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    coverage_delta_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
        nullable=False,
    )
    name: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    docker_image: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)

    __table_args__ = (
        Index("ix_test_run_task", "task_id"),
        Index("ix_test_run_project", "project_id"),
        Index("ix_test_run_status", "status"),
    )


# Optional: relationship from TestRun to TestExecution is defined on TestExecution side
