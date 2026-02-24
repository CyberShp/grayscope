"""风险发现数据模型。"""

from __future__ import annotations

from typing import Optional

from datetime import datetime, timezone

from sqlalchemy import BigInteger, DateTime, Float, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class RiskFinding(Base):
    """风险发现表，记录分析器产出的每一条风险发现。"""

    __tablename__ = "risk_findings"

    id: Mapped[int] = mapped_column(primary_key=True)
    task_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("analysis_tasks.id"), nullable=False
    )
    module_result_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("analysis_module_results.id"), nullable=True
    )
    module_id: Mapped[str] = mapped_column(String(32), nullable=False)
    risk_type: Mapped[str] = mapped_column(String(32), nullable=False)
    severity: Mapped[str] = mapped_column(String(8), nullable=False)
    risk_score: Mapped[float] = mapped_column(Float, nullable=False)
    file_path: Mapped[str] = mapped_column(Text, nullable=False)
    symbol_name: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    line_start: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    line_end: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    title: Mapped[str] = mapped_column(String(256), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # V2: 支柱；错误传播链等
    pillar: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    call_chain_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
        nullable=False,
    )

    __table_args__ = (
        Index("ix_finding_task_type_sev", "task_id", "risk_type", "severity"),
        Index("ix_finding_task_score", "task_id", "risk_score"),
        Index("ix_finding_file", "file_path", "line_start"),
    )
