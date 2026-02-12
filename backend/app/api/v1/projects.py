from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from starlette.status import HTTP_201_CREATED

from app.core.database import get_db
from app.core.response import ok
from app.schemas.project import ProjectCreate
from app.schemas.repository import RepoCreate
from app.services import project_service

router = APIRouter()


@router.post("/projects", status_code=HTTP_201_CREATED)
def create_project(req: ProjectCreate, db: Session = Depends(get_db)) -> dict:
    out = project_service.create_project(db, req)
    return ok(out.model_dump())


@router.get("/projects")
def list_projects(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
) -> dict:
    items, total = project_service.list_projects(db, page=page, page_size=page_size)
    return ok(
        {
            "items": [i.model_dump() for i in items],
            "page": page,
            "page_size": page_size,
            "total": total,
        }
    )


@router.get("/projects/{project_id}")
def get_project(project_id: int, db: Session = Depends(get_db)) -> dict:
    out = project_service.get_project(db, project_id)
    return ok(out.model_dump())


# ---- repositories ----


@router.get("/projects/{project_id}/repos")
def list_repos(project_id: int, db: Session = Depends(get_db)) -> dict:
    repos = project_service.list_repos(db, project_id)
    return ok([r.model_dump() for r in repos])


@router.post("/projects/{project_id}/repos", status_code=HTTP_201_CREATED)
def add_repo(
    project_id: int, req: RepoCreate, db: Session = Depends(get_db)
) -> dict:
    out = project_service.add_repo(db, project_id, req)
    return ok(out.model_dump())
