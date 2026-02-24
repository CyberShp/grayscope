"""SFMEA 条目（从分析发现生成）。"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import BigInteger, DateTime, Float, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class SfmeaEntry(Base):
    __tablename__ = "sfmea_entries"

    id: Mapped[int] = mapped_column(primary_key=True)
    task_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("analysis_tasks.id"), nullable=False
    )
    finding_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("risk_findings.id"), nullable=True
    )
    test_case_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("test_cases.id"), nullable=True
    )
    failure_mode: Mapped[str] = mapped_column(String(512), nullable=False)
    severity: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    occurrence: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    detection: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    rpn: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    file_path: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    symbol_name: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
        nullable=False,
    )

    __table_args__ = (Index("ix_sfmea_task", "task_id"),)
