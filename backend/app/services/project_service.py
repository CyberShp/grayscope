"""Project and repository management service."""

from __future__ import annotations

from pathlib import Path

from sqlalchemy.orm import Session

from app.config import settings
from app.core.exceptions import InvalidRequestError, NotFoundError
from app.models.project import Project
from app.models.repository import Repository
from app.repositories import project_repo, repository_repo
from app.schemas.project import ProjectCreate, ProjectOut
from app.schemas.repository import RepoCreate, RepoOut, RepoUpdate


def create_project(db: Session, req: ProjectCreate) -> ProjectOut:
    existing = project_repo.get_by_name(db, req.name)
    if existing:
        raise InvalidRequestError(f"project name '{req.name}' already exists")
    obj = project_repo.create(db, name=req.name, description=req.description)
    return ProjectOut.from_orm_obj(obj)


def list_projects(
    db: Session, page: int = 1, page_size: int = 20
) -> tuple[list[ProjectOut], int]:
    items, total = project_repo.list_projects(db, page=page, page_size=page_size)
    return [ProjectOut.from_orm_obj(p) for p in items], total


def get_project(db: Session, project_id: int) -> ProjectOut:
    obj = project_repo.get_by_id(db, project_id)
    if obj is None:
        raise NotFoundError(f"project {project_id} not found")
    return ProjectOut.from_orm_obj(obj)


# ---- repos ----


def add_repo(db: Session, project_id: int, req: RepoCreate) -> RepoOut:
    proj = project_repo.get_by_id(db, project_id)
    if proj is None:
        raise NotFoundError(f"project {project_id} not found")

    # Check for duplicate repo name within the same project
    existing_repos = repository_repo.list_by_project(db, project_id)
    if any(r.name == req.name for r in existing_repos):
        raise InvalidRequestError(
            f"repository name '{req.name}' already exists in project {project_id}"
        )

    mirror_path = req.local_mirror_path
    if not mirror_path:
        mirror_path = str(
            Path(settings.repo_workspace) / str(project_id) / req.name
        )

    obj = repository_repo.create(
        db,
        project_id=project_id,
        name=req.name,
        git_url=req.git_url,
        default_branch=req.default_branch,
        local_mirror_path=mirror_path,
        auth_type=req.auth_type,
        auth_secret_ref=req.auth_secret_ref,
    )
    return RepoOut.from_orm_obj(obj)


def list_repos(db: Session, project_id: int) -> list[RepoOut]:
    proj = project_repo.get_by_id(db, project_id)
    if proj is None:
        raise NotFoundError(f"project {project_id} not found")
    repos = repository_repo.list_by_project(db, project_id)
    return [RepoOut.from_orm_obj(r) for r in repos]


def get_repo(db: Session, repo_id: int) -> RepoOut:
    obj = repository_repo.get_by_id(db, repo_id)
    if obj is None:
        raise NotFoundError(f"repo {repo_id} not found")
    return RepoOut.from_orm_obj(obj)


def update_repo(db: Session, repo_id: int, req: RepoUpdate, project_id: int | None = None) -> RepoOut:
    obj = repository_repo.get_by_id(db, repo_id)
    if obj is None:
        raise NotFoundError(f"repo {repo_id} not found")
    if project_id is not None and obj.project_id != project_id:
        raise NotFoundError(f"repo {repo_id} not found in project {project_id}")
    repository_repo.update(
        db,
        repo_id,
        git_url=req.git_url,
        default_branch=req.default_branch,
        auth_type=req.auth_type,
        auth_secret_ref=req.auth_secret_ref,
    )
    obj = repository_repo.get_by_id(db, repo_id)
    return RepoOut.from_orm_obj(obj)
