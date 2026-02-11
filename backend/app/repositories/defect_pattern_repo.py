"""Data access for defect_patterns table."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.defect_pattern import DefectPattern


def upsert(
    db: Session,
    *,
    project_id: int,
    pattern_key: str,
    name: str,
    risk_type: str,
    trigger_shape: dict,
    code_signature: dict,
    test_template: dict,
    example: dict | None = None,
) -> DefectPattern:
    """Insert or update a defect pattern (upsert by project_id + pattern_key)."""
    existing = db.scalars(
        select(DefectPattern).where(
            DefectPattern.project_id == project_id,
            DefectPattern.pattern_key == pattern_key,
        )
    ).first()

    if existing:
        existing.name = name
        existing.risk_type = risk_type
        existing.trigger_shape_json = json.dumps(trigger_shape, ensure_ascii=False)
        existing.code_signature_json = json.dumps(code_signature, ensure_ascii=False)
        existing.test_template_json = json.dumps(test_template, ensure_ascii=False)
        if example is not None:
            existing.example_json = json.dumps(example, ensure_ascii=False)
        existing.hit_count += 1
        existing.updated_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(existing)
        return existing

    obj = DefectPattern(
        project_id=project_id,
        pattern_key=pattern_key,
        name=name,
        risk_type=risk_type,
        trigger_shape_json=json.dumps(trigger_shape, ensure_ascii=False),
        code_signature_json=json.dumps(code_signature, ensure_ascii=False),
        test_template_json=json.dumps(test_template, ensure_ascii=False),
        example_json=json.dumps(example, ensure_ascii=False) if example else None,
        hit_count=1,
    )
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


def get_by_project(
    db: Session, project_id: int, risk_type: str | None = None
) -> list[DefectPattern]:
    """List defect patterns for a project, optionally filtered by risk_type."""
    stmt = select(DefectPattern).where(
        DefectPattern.project_id == project_id
    )
    if risk_type:
        stmt = stmt.where(DefectPattern.risk_type == risk_type)
    stmt = stmt.order_by(DefectPattern.hit_count.desc(), DefectPattern.updated_at.desc())
    return list(db.scalars(stmt).all())


def get_by_key(db: Session, project_id: int, pattern_key: str) -> DefectPattern | None:
    return db.scalars(
        select(DefectPattern).where(
            DefectPattern.project_id == project_id,
            DefectPattern.pattern_key == pattern_key,
        )
    ).first()


def search(
    db: Session, project_id: int, keyword: str, limit: int = 20
) -> list[DefectPattern]:
    """Search patterns by name or pattern_key containing keyword."""
    stmt = (
        select(DefectPattern)
        .where(
            DefectPattern.project_id == project_id,
            (
                DefectPattern.name.ilike(f"%{keyword}%")
                | DefectPattern.pattern_key.ilike(f"%{keyword}%")
                | DefectPattern.risk_type.ilike(f"%{keyword}%")
            ),
        )
        .order_by(DefectPattern.hit_count.desc())
        .limit(limit)
    )
    return list(db.scalars(stmt).all())


def increment_hit(db: Session, pattern_id: int) -> None:
    obj = db.get(DefectPattern, pattern_id)
    if obj:
        obj.hit_count += 1
        obj.updated_at = datetime.now(timezone.utc)
        db.commit()
