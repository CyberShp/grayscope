"""Data access for model_configs table."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.model_config import ModelConfig


def list_active(db: Session, project_id: int | None = None) -> list[ModelConfig]:
    stmt = select(ModelConfig).where(ModelConfig.is_active.is_(True))
    if project_id is not None:
        stmt = stmt.where(
            (ModelConfig.project_id == project_id) | (ModelConfig.project_id.is_(None))
        )
    return list(db.scalars(stmt.order_by(ModelConfig.provider, ModelConfig.model)).all())


def create_or_update(
    db: Session,
    *,
    provider: str,
    model: str,
    project_id: int | None = None,
    base_url: str | None = None,
    auth_type: str | None = None,
    auth_secret_ref: str | None = None,
    extra_json: str | None = None,
) -> ModelConfig:
    existing = db.scalars(
        select(ModelConfig).where(
            ModelConfig.provider == provider,
            ModelConfig.model == model,
            ModelConfig.project_id == project_id
            if project_id
            else ModelConfig.project_id.is_(None),
        )
    ).first()
    if existing:
        existing.base_url = base_url or existing.base_url
        existing.auth_type = auth_type or existing.auth_type
        existing.auth_secret_ref = auth_secret_ref or existing.auth_secret_ref
        existing.extra_json = extra_json or existing.extra_json
        existing.is_active = True
        db.commit()
        db.refresh(existing)
        return existing
    obj = ModelConfig(
        project_id=project_id,
        provider=provider,
        model=model,
        base_url=base_url,
        auth_type=auth_type,
        auth_secret_ref=auth_secret_ref,
        extra_json=extra_json,
    )
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj
