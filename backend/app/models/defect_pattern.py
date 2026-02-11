from __future__ import annotations

from typing import Optional

from sqlalchemy import BigInteger, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class DefectPattern(TimestampMixin, Base):
    __tablename__ = "defect_patterns"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("projects.id"), nullable=False
    )
    pattern_key: Mapped[str] = mapped_column(String(128), nullable=False)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    risk_type: Mapped[str] = mapped_column(String(32), nullable=False)
    trigger_shape_json: Mapped[str] = mapped_column(Text, nullable=False)
    code_signature_json: Mapped[str] = mapped_column(Text, nullable=False)
    test_template_json: Mapped[str] = mapped_column(Text, nullable=False)
    example_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    hit_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    __table_args__ = (
        UniqueConstraint("project_id", "pattern_key", name="uq_pattern_project_key"),
        Index("ix_pattern_project_risk", "project_id", "risk_type", "hit_count"),
    )
