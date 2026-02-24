"""协议抓包元数据及解析结果。"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class ProtocolCapture(Base):
    __tablename__ = "protocol_captures"

    id: Mapped[int] = mapped_column(primary_key=True)
    task_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("analysis_tasks.id"), nullable=True
    )
    project_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("projects.id"), nullable=True
    )
    file_name: Mapped[str] = mapped_column(String(512), nullable=False)
    messages_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
        nullable=False,
    )

    __table_args__ = (Index("ix_protocol_capture_task", "task_id"),)
