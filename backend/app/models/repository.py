from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class Repository(TimestampMixin, Base):
    __tablename__ = "repositories"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("projects.id"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    git_url: Mapped[str] = mapped_column(Text, nullable=False)
    default_branch: Mapped[str] = mapped_column(String(128), nullable=False)
    local_mirror_path: Mapped[str] = mapped_column(Text, nullable=False)
    last_sync_status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="never"
    )
    last_sync_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # Auth for private repos: none | https_token | ssh_key
    auth_type: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    # Env var name for token (https) or path to SSH key (ssh_key); never exposed in API
    auth_secret_ref: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)

    # relationships
    project = relationship("Project", back_populates="repositories")

    __table_args__ = (
        UniqueConstraint("project_id", "name", name="uq_repo_project_name"),
        Index("ix_repo_project_updated", "project_id", "updated_at"),
    )
