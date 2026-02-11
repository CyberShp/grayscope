from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from starlette.status import HTTP_202_ACCEPTED

from app.core.database import get_db
from app.core.response import ok
from app.schemas.repository import SyncRequest, SyncOut
from app.services import git_service
from app.utils.id_gen import sync_id

router = APIRouter()


@router.post("/repos/{repo_id}/sync", status_code=HTTP_202_ACCEPTED)
def sync_repo(repo_id: int, req: SyncRequest, db: Session = Depends(get_db)) -> dict:
    result = git_service.sync_repo(
        db,
        repo_id,
        branch=req.revision.branch,
        tag=req.revision.tag,
        commit=req.revision.commit,
        depth=req.depth,
    )
    return ok(SyncOut(**result).model_dump(), message="sync started")
