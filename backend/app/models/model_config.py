from __future__ import annotations

from typing import Optional

from sqlalchemy import BigInteger, Boolean, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class ModelConfig(TimestampMixin, Base):
    __tablename__ = "model_configs"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("projects.id"), nullable=True
    )
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    model: Mapped[str] = mapped_column(String(128), nullable=False)
    base_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    auth_type: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    auth_secret_ref: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    extra_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    __table_args__ = (
        Index("ix_model_cfg_provider", "provider", "model", "is_active"),
        Index("ix_model_cfg_project", "project_id", "is_active"),
    )
