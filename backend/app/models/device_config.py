"""测试床设备连接配置。"""

from __future__ import annotations

from typing import Optional

from sqlalchemy import BigInteger, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class DeviceConfig(TimestampMixin, Base):
    __tablename__ = "device_configs"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("projects.id"), nullable=True
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    device_type: Mapped[str] = mapped_column(String(32), nullable=False)  # dut / host / instrument
    connection_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # SSH 等

    __table_args__ = (Index("ix_device_config_project", "project_id"),)
