"""测试执行记录。"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class TestExecution(Base):
    __tablename__ = "test_executions"

    id: Mapped[int] = mapped_column(primary_key=True)
    task_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("analysis_tasks.id"), nullable=False
    )
    test_case_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("test_cases.id"), nullable=True
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    result_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    coverage_delta_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
        nullable=False,
    )

    __table_args__ = (Index("ix_test_execution_task", "task_id"),)
