"""Data access for repositories table."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.repository import Repository


def create(
    db: Session,
    *,
    project_id: int,
    name: str,
    git_url: str,
    default_branch: str,
    local_mirror_path: str,
) -> Repository:
    obj = Repository(
        project_id=project_id,
        name=name,
        git_url=git_url,
        default_branch=default_branch,
        local_mirror_path=local_mirror_path,
    )
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


def get_by_id(db: Session, repo_id: int) -> Repository | None:
    return db.get(Repository, repo_id)


def list_by_project(db: Session, project_id: int) -> list[Repository]:
    return list(
        db.scalars(
            select(Repository)
            .where(Repository.project_id == project_id)
            .order_by(Repository.updated_at.desc())
        ).all()
    )


def update_sync_status(
    db: Session, repo_id: int, status: str
) -> Repository | None:
    obj = db.get(Repository, repo_id)
    if obj is None:
        return None
    obj.last_sync_status = status
    if status == "success":
        obj.last_sync_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(obj)
    return obj
