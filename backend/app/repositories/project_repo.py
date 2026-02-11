"""Data access for projects table."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.project import Project


def create(db: Session, *, name: str, description: str | None = None) -> Project:
    obj = Project(name=name, description=description)
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


def get_by_id(db: Session, project_id: int) -> Project | None:
    return db.get(Project, project_id)


def get_by_name(db: Session, name: str) -> Project | None:
    return db.scalars(select(Project).where(Project.name == name)).first()


def list_projects(
    db: Session, *, page: int = 1, page_size: int = 20
) -> tuple[list[Project], int]:
    total = db.scalar(
        select(func.count()).select_from(Project).where(Project.status == "active")
    ) or 0
    items = list(
        db.scalars(
            select(Project)
            .where(Project.status == "active")
            .order_by(Project.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).all()
    )
    return items, total
