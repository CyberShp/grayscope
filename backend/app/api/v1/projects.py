from typing import Optional

from fastapi import APIRouter, Depends, File, Query, UploadFile
from sqlalchemy.orm import Session
from starlette.status import HTTP_201_CREATED

from app.core.database import get_db
from app.core.exceptions import InvalidRequestError
from app.core.response import ok
from app.schemas.project import ProjectCreate
from app.schemas.repository import RepoCreate, RepoUpdate
from app.services import project_service
from app.services.upload_service import create_repo_from_upload

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


@router.post("/projects/{project_id}/repos/upload", status_code=HTTP_201_CREATED)
def upload_repo(
    project_id: int,
    file: UploadFile = File(..., description="压缩包：.zip / .tar.gz / .tar"),
    name: Optional[str] = Query(default=None, description="仓库显示名称，默认用文件名"),
    db: Session = Depends(get_db),
) -> dict:
    """上传代码压缩包，解压后创建为仓库（代码来源=上传），可直接用于新建分析任务。"""
    if not file.filename:
        raise InvalidRequestError("请选择压缩包文件")
    content = file.file.read()
    import io
    out = create_repo_from_upload(
        db,
        project_id=project_id,
        file=io.BytesIO(content),
        filename=file.filename,
        repo_name=name,
    )
    return ok(out, message="上传解压成功，已创建仓库")


@router.patch("/projects/{project_id}/repos/{repo_id}")
def update_repo(
    project_id: int,
    repo_id: int,
    req: RepoUpdate,
    db: Session = Depends(get_db),
) -> dict:
    out = project_service.update_repo(db, repo_id, req, project_id=project_id)
    return ok(out.model_dump())
