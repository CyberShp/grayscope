from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class RepoCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    git_url: str = Field(..., min_length=1)
    default_branch: str = Field(default="main", max_length=128)
    local_mirror_path: Optional[str] = None


class RepoOut(BaseModel):
    repo_id: int
    project_id: int
    name: str
    git_url: str
    default_branch: str
    last_sync_status: str = "never"
    last_sync_at: Optional[datetime] = None

    model_config = {"from_attributes": True}

    @classmethod
    def from_orm_obj(cls, obj) -> "RepoOut":
        return cls(
            repo_id=obj.id,
            project_id=obj.project_id,
            name=obj.name,
            git_url=obj.git_url,
            default_branch=obj.default_branch,
            last_sync_status=obj.last_sync_status,
            last_sync_at=obj.last_sync_at,
        )


class SyncRequest(BaseModel):
    class Revision(BaseModel):
        branch: Optional[str] = "main"
        tag: Optional[str] = None
        commit: Optional[str] = None

    revision: Revision = Revision()
    depth: int = Field(default=1, ge=0)


class SyncOut(BaseModel):
    sync_id: str
    repo_id: int
    status: str = "running"
