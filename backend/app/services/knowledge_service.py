"""知识库服务：模式持久化与相似度匹配。

连接缺陷知识库管理器的输出与 defect_patterns 数据库表。
"""

from __future__ import annotations

import json
import logging
from typing import Any

from sqlalchemy.orm import Session

from app.analyzers.knowledge_pattern_manager import match_patterns
from app.repositories import defect_pattern_repo

logger = logging.getLogger(__name__)


def persist_patterns_from_findings(
    db: Session,
    project_id: int,
    knowledge_findings: list[dict[str, Any]],
) -> list[dict]:
    """将缺陷知识库的模式发现持久化到 defect_patterns 表。

    返回已写入/更新的模式摘要列表。
    """
    results = []

    for f in knowledge_findings:
        if f.get("risk_type") != "pattern_extracted":
            continue
        evidence = f.get("evidence", {})

        pattern_key = evidence.get("pattern_key", "")
        trigger_shape = evidence.get("trigger_shape", {})
        code_signature = evidence.get("code_signature", {})
        test_template = evidence.get("test_template", {})

        if not pattern_key:
            continue

        category = trigger_shape.get("category", "unknown")
        name = f.get("title", pattern_key).replace("Pattern extracted: ", "")

        dp = defect_pattern_repo.upsert(
            db,
            project_id=project_id,
            pattern_key=pattern_key,
            name=name,
            risk_type=category,
            trigger_shape=trigger_shape,
            code_signature=code_signature,
            test_template=test_template,
            example={"source_finding": f.get("finding_id", "")},
        )

        results.append({
            "pattern_id": dp.id,
            "pattern_key": dp.pattern_key,
            "name": dp.name,
            "risk_type": dp.risk_type,
            "hit_count": dp.hit_count,
            "is_new": dp.hit_count == 1,
        })

    return results


def search_patterns(
    db: Session,
    project_id: int,
    keyword: str = "",
    risk_type: str = "",
) -> list[dict]:
    """搜索知识库中的缺陷模式。"""
    if keyword:
        patterns = defect_pattern_repo.search(db, project_id, keyword)
    else:
        patterns = defect_pattern_repo.get_by_project(db, project_id, risk_type or None)

    return [_pattern_to_dict(p) for p in patterns]


def match_findings_against_knowledge(
    db: Session,
    project_id: int,
    findings: list[dict],
    threshold: float = 0.4,
) -> list[dict]:
    """将分析发现与已知缺陷模式进行匹配。

    返回包含相似度评分和测试模板的匹配记录列表。
    """
    patterns = defect_pattern_repo.get_by_project(db, project_id)
    if not patterns:
        return []

    known = [_pattern_to_match_dict(p) for p in patterns]
    matches = match_patterns(findings, known, threshold=threshold)

    # 为匹配到的模式增加命中计数
    matched_keys = set()
    for m in matches:
        pk = m.get("pattern_key", "")
        if pk and pk not in matched_keys:
            matched_keys.add(pk)
            dp = defect_pattern_repo.get_by_key(db, project_id, pk)
            if dp:
                defect_pattern_repo.increment_hit(db, dp.id)

    return matches


def _pattern_to_dict(p) -> dict:
    """将 ORM 模式对象转换为 API 返回字典。"""
    return {
        "pattern_id": p.id,
        "project_id": p.project_id,
        "pattern_key": p.pattern_key,
        "name": p.name,
        "risk_type": p.risk_type,
        "trigger_shape": json.loads(p.trigger_shape_json),
        "code_signature": json.loads(p.code_signature_json),
        "test_template": json.loads(p.test_template_json),
        "example": json.loads(p.example_json) if p.example_json else None,
        "hit_count": p.hit_count,
        "created_at": p.created_at.isoformat() if p.created_at else None,
        "updated_at": p.updated_at.isoformat() if p.updated_at else None,
    }


def _pattern_to_match_dict(p) -> dict:
    """将 ORM 模式对象转换为 match_patterns() 所需的格式。"""
    return {
        "pattern_key": p.pattern_key,
        "name": p.name,
        "risk_type": p.risk_type,
        "trigger_shape": json.loads(p.trigger_shape_json),
        "code_signature": json.loads(p.code_signature_json),
        "test_template": json.loads(p.test_template_json),
    }
