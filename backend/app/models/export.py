from __future__ import annotations

from typing import Optional

from sqlalchemy import BigInteger, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class Export(TimestampMixin, Base):
    __tablename__ = "exports"

    id: Mapped[int] = mapped_column(primary_key=True)
    export_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    task_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("analysis_tasks.id"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    format: Mapped[str] = mapped_column(String(16), nullable=False)
    content_type: Mapped[str] = mapped_column(String(32), nullable=False)
    artifact_path: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    error_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    __table_args__ = (
        Index("ix_export_task_created", "task_id", "created_at"),
        Index("ix_export_status_updated", "status", "updated_at"),
    )
