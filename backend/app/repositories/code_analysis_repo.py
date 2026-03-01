"""Repository layer for code_analysis_tasks table."""

from __future__ import annotations

from typing import Any

from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.models.code_analysis_task import CodeAnalysisTask


def create(db: Session, *, analysis_id: str, **kwargs: Any) -> CodeAnalysisTask:
    task = CodeAnalysisTask(analysis_id=analysis_id, **kwargs)
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


def get_by_analysis_id(db: Session, analysis_id: str) -> CodeAnalysisTask | None:
    return (
        db.query(CodeAnalysisTask)
        .filter(CodeAnalysisTask.analysis_id == analysis_id)
        .first()
    )


def update(db: Session, analysis_id: str, **kwargs: Any) -> CodeAnalysisTask | None:
    task = get_by_analysis_id(db, analysis_id)
    if not task:
        return None
    for key, value in kwargs.items():
        setattr(task, key, value)
    db.commit()
    db.refresh(task)
    return task


def delete(db: Session, analysis_id: str) -> bool:
    task = get_by_analysis_id(db, analysis_id)
    if not task:
        return False
    db.delete(task)
    db.commit()
    return True


def list_tasks(
    db: Session,
    *,
    status: str | None = None,
    project_id: int | None = None,
    repo_id: int | None = None,
    limit: int = 20,
) -> list[CodeAnalysisTask]:
    q = db.query(CodeAnalysisTask)
    if status:
        q = q.filter(CodeAnalysisTask.status == status)
    if project_id is not None:
        q = q.filter(CodeAnalysisTask.project_id == project_id)
    if repo_id is not None:
        q = q.filter(CodeAnalysisTask.repo_id == repo_id)
    return q.order_by(desc(CodeAnalysisTask.created_at)).limit(limit).all()


def count_tasks(
    db: Session,
    *,
    status: str | None = None,
    project_id: int | None = None,
    repo_id: int | None = None,
) -> int:
    """Count total tasks matching the filters (without limit)."""
    q = db.query(CodeAnalysisTask)
    if status:
        q = q.filter(CodeAnalysisTask.status == status)
    if project_id is not None:
        q = q.filter(CodeAnalysisTask.project_id == project_id)
    if repo_id is not None:
        q = q.filter(CodeAnalysisTask.repo_id == repo_id)
    return q.count()
