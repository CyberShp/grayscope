from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class ProjectCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=64)
    description: Optional[str] = Field(default=None, max_length=512)


class ProjectOut(BaseModel):
    project_id: int
    name: str
    description: Optional[str] = None
    status: str = "active"
    created_at: datetime

    model_config = {"from_attributes": True}

    @classmethod
    def from_orm_obj(cls, obj) -> "ProjectOut":
        return cls(
            project_id=obj.id,
            name=obj.name,
            description=obj.description,
            status=obj.status,
            created_at=obj.created_at,
        )
