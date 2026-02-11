from fastapi import APIRouter

from app.analyzers.code_parser import is_available as parser_available
from app.core.response import ok

router = APIRouter()


@router.get("/health")
def health() -> dict:
    return ok(
        {
            "service": "grayscope-backend",
            "status": "ok",
            "parser_available": parser_available(),
        }
    )
