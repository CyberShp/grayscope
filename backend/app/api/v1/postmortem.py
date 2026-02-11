"""事后分析和知识库 API 端点。"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from starlette.status import HTTP_201_CREATED

from app.core.database import get_db
from app.core.response import ok
from app.schemas.analysis import PostmortemRequest
from app.services import knowledge_service, postmortem_service

router = APIRouter()


# ── 事后分析 ──────────────────────────────────────────────────────────


@router.post("/postmortem", status_code=HTTP_201_CREATED, tags=["事后分析"])
def create_postmortem(
    req: PostmortemRequest, db: Session = Depends(get_db)
) -> dict:
    """执行逃逸缺陷的事后分析。

    创建事后分析 + 缺陷知识库分析任务，产出根因分析、
    预防性测试建议，并将缺陷模式持久化到知识库。
    """
    result = postmortem_service.run_postmortem(db, req)
    return ok(result, message="事后分析已完成")


# ── 知识库 ──────────────────────────────────────────────────────────


@router.get("/knowledge/patterns", tags=["知识库"])
def list_patterns(
    project_id: int,
    risk_type: str = "",
    keyword: str = "",
    db: Session = Depends(get_db),
) -> dict:
    """搜索缺陷模式知识库。

    筛选条件：
    - keyword：按名称/键/风险类型子串搜索
    - risk_type：按精确风险类型分类筛选
    """
    patterns = knowledge_service.search_patterns(
        db, project_id, keyword=keyword, risk_type=risk_type
    )
    return ok({
        "project_id": project_id,
        "total": len(patterns),
        "patterns": patterns,
    })


@router.post("/knowledge/match", tags=["知识库"])
def match_knowledge(
    project_id: int = Query(...),
    task_id: str = Query(...),
    threshold: float = Query(default=0.4, ge=0.0, le=1.0),
    db: Session = Depends(get_db),
) -> dict:
    """将分析发现与知识库中的已知缺陷模式进行匹配。

    返回包含相似度评分和推荐测试模板的匹配结果。
    """
    import json
    from app.repositories import task_repo

    task = task_repo.get_task_by_id(db, task_id)
    if task is None:
        from app.core.exceptions import NotFoundError
        raise NotFoundError(f"任务 {task_id} 未找到")

    results = task_repo.get_module_results(db, task.id)
    all_findings = []
    for r in results:
        if r.findings_json:
            all_findings.extend(json.loads(r.findings_json))

    matches = knowledge_service.match_findings_against_knowledge(
        db, project_id, all_findings, threshold=threshold
    )

    return ok({
        "task_id": task_id,
        "project_id": project_id,
        "threshold": threshold,
        "total_findings": len(all_findings),
        "total_matches": len(matches),
        "matches": matches[:50],
    })
