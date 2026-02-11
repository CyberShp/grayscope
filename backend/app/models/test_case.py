from __future__ import annotations

from typing import Optional

from datetime import datetime, timezone

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class TestCase(Base):
    __tablename__ = "test_cases"

    id: Mapped[int] = mapped_column(primary_key=True)
    task_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("analysis_tasks.id"), nullable=False
    )
    module_result_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("analysis_module_results.id"), nullable=True
    )
    case_id: Mapped[str] = mapped_column(String(64), nullable=False)
    title: Mapped[str] = mapped_column(String(256), nullable=False)
    risk_type: Mapped[str] = mapped_column(String(32), nullable=False)
    priority: Mapped[str] = mapped_column(String(8), nullable=False)
    preconditions_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    steps_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    expected_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    tags_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    source_finding_ids_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="pending",
        server_default="pending",
    )  # pending / adopted / ignored / executed
    risk_score: Mapped[Optional[float]] = mapped_column(nullable=True)
    module_id: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    file_path: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    symbol_name: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    objective: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    expected: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
        nullable=False,
    )

    __table_args__ = (
        UniqueConstraint("task_id", "case_id", name="uq_testcase_task_case"),
        Index("ix_testcase_task_priority", "task_id", "priority"),
        Index("ix_testcase_task_risk", "task_id", "risk_type"),
    )
