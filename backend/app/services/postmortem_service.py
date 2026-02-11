"""事后分析服务：编排事后分析工作流。

1. 创建类型为 postmortem 的分析任务
2. 运行事后分析器 -> 缺陷知识库管理器
3. 将提取的模式持久化到知识库
"""

from __future__ import annotations

import json
import logging
from typing import Any

from sqlalchemy.orm import Session

from app.repositories import task_repo
from app.schemas.analysis import PostmortemRequest
from app.services import analysis_orchestrator, knowledge_service
from app.utils.id_gen import task_id as gen_task_id

logger = logging.getLogger(__name__)


def run_postmortem(
    db: Session, req: PostmortemRequest
) -> dict[str, Any]:
    """执行完整的事后分析工作流。

    返回包含 task_id、事后分析发现、提取的模式和预防性测试建议的字典。
    """
    tid = gen_task_id()

    # 构建包含缺陷元数据的分析目标
    target = {
        "path": req.defect.module_path or ".",
        "defect": req.defect.model_dump(),
    }

    # 创建任务
    task = task_repo.create_task(
        db,
        task_id=tid,
        project_id=req.project_id,
        repo_id=req.repo_id,
        task_type="postmortem",
        target=target,
        revision={"branch": "main", "commit": req.defect.related_commit or "HEAD"},
        analyzers=["postmortem", "knowledge_pattern"],
        ai=req.ai.model_dump(),
        options={},
    )

    # 预创建模块结果记录
    for mod in ["postmortem", "knowledge_pattern"]:
        task_repo.create_module_result(db, task_pk=task.id, module_id=mod)

    # 执行分析
    analysis_orchestrator.run_task(db, tid)

    # 收集结果
    results = task_repo.get_module_results(db, task.id)
    postmortem_data = {}
    knowledge_data = {}

    for r in results:
        findings = json.loads(r.findings_json) if r.findings_json else []
        if r.module_id == "postmortem":
            postmortem_data = {
                "status": r.status,
                "risk_score": r.risk_score,
                "findings": findings,
            }
        elif r.module_id == "knowledge_pattern":
            knowledge_data = {
                "status": r.status,
                "risk_score": r.risk_score,
                "findings": findings,
            }

    # 将缺陷知识库的发现持久化到知识库
    persisted_patterns = []
    if knowledge_data.get("findings"):
        persisted_patterns = knowledge_service.persist_patterns_from_findings(
            db, req.project_id, knowledge_data["findings"]
        )

    # 构建摘要
    root_causes = []
    preventive_tests = []
    for f in postmortem_data.get("findings", []):
        ev = f.get("evidence", {})
        root_causes.extend(ev.get("root_cause_chain", []))
        preventive_tests.extend(ev.get("preventive_tests", []))

    return {
        "task_id": tid,
        "task_type": "postmortem",
        "status": "success",
        "defect": req.defect.model_dump(),
        "root_causes": root_causes,
        "preventive_tests": preventive_tests,
        "postmortem_findings": postmortem_data.get("findings", []),
        "patterns_extracted": persisted_patterns,
        "knowledge_entries_created": len(persisted_patterns),
    }
