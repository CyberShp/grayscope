"""审计事件数据模型。"""

from __future__ import annotations

from typing import Optional

from datetime import datetime, timezone

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class AuditEvent(Base):
    """审计事件表，记录系统中的关键操作事件。"""

    __tablename__ = "audit_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    request_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    task_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("analysis_tasks.id"), nullable=True
    )
    module_id: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    event_type: Mapped[str] = mapped_column(String(32), nullable=False)
    actor: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    payload_hash: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    payload_size: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    meta_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
        nullable=False,
    )

    __table_args__ = (
        Index("ix_audit_task_created", "task_id", "created_at"),
        Index("ix_audit_type_created", "event_type", "created_at"),
    )
