"""覆盖率导入记录（北向接口写入）。"""

from __future__ import annotations

from sqlalchemy import BigInteger, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class CoverageImport(TimestampMixin, Base):
    """一次覆盖率数据导入，按任务存储；coverage_map 使用该任务最近一次导入。"""

    __tablename__ = "coverage_imports"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    task_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("analysis_tasks.id", ondelete="CASCADE"), nullable=False
    )
    source_system: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    revision: Mapped[str] = mapped_column(String(256), nullable=False, default="")
    format: Mapped[str] = mapped_column(String(32), nullable=False)  # summary | granular
    payload_json: Mapped[str] = mapped_column(Text, nullable=False)

    __table_args__ = (
        Index("ix_coverage_import_task_created", "task_id", "created_at"),
    )
