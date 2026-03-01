from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class RepoCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    git_url: str = Field(..., min_length=1)
    default_branch: str = Field(default="main", max_length=128)
    local_mirror_path: Optional[str] = None
    auth_type: Optional[str] = Field(default=None, max_length=32)
    auth_secret_ref: Optional[str] = Field(default=None, max_length=256)


class RepoOut(BaseModel):
    repo_id: int
    project_id: int
    name: str
    git_url: str
    default_branch: str
    local_mirror_path: Optional[str] = None
    last_sync_status: str = "never"
    last_sync_at: Optional[datetime] = None
    auth_type: Optional[str] = None
    auth_configured: bool = False

    model_config = {"from_attributes": True}

    @classmethod
    def from_orm_obj(cls, obj) -> "RepoOut":
        return cls(
            repo_id=obj.id,
            project_id=obj.project_id,
            name=obj.name,
            git_url=obj.git_url,
            default_branch=obj.default_branch,
            local_mirror_path=getattr(obj, "local_mirror_path", None),
            last_sync_status=obj.last_sync_status,
            last_sync_at=obj.last_sync_at,
            auth_type=getattr(obj, "auth_type", None),
            auth_configured=bool(getattr(obj, "auth_secret_ref", None)),
        )


class RepoUpdate(BaseModel):
    git_url: Optional[str] = Field(default=None, min_length=1)
    default_branch: Optional[str] = Field(default=None, max_length=128)
    auth_type: Optional[str] = Field(default=None, max_length=32)
    auth_secret_ref: Optional[str] = Field(default=None, max_length=256)


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
