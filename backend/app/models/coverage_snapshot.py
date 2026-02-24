"""覆盖率快照。"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class CoverageSnapshot(Base):
    __tablename__ = "coverage_snapshots"

    id: Mapped[int] = mapped_column(primary_key=True)
    task_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("analysis_tasks.id"), nullable=False
    )
    revision: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    payload_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
        nullable=False,
    )

    __table_args__ = (Index("ix_coverage_snapshot_task", "task_id"),)
