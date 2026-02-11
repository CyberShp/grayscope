"""Prompt template engine with versioning and Jinja2 rendering."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml
from jinja2 import BaseLoader, Environment

from app.config import settings

logger = logging.getLogger(__name__)

_env = Environment(loader=BaseLoader(), autoescape=False)

# Cache: template_id -> parsed YAML dict
_template_cache: dict[str, dict] = {}


def _load_all() -> None:
    """Scan prompt_templates directory and cache all YAML files."""
    tpl_dir = Path(settings.prompt_template_dir)
    if not tpl_dir.exists():
        logger.warning("prompt template dir not found: %s", tpl_dir)
        return
    for path in sorted(tpl_dir.glob("*.yaml")):
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
            tid = data.get("template_id", path.stem)
            _template_cache[tid] = data
        except Exception:
            logger.exception("failed to load prompt template: %s", path)


def get_template(template_id: str) -> dict | None:
    """Return raw template dict by ID."""
    if not _template_cache:
        _load_all()
    return _template_cache.get(template_id)


def list_templates() -> list[dict]:
    if not _template_cache:
        _load_all()
    return [
        {"template_id": k, "version": v.get("version", "unknown")}
        for k, v in _template_cache.items()
    ]


def render(template_id: str, variables: dict[str, Any]) -> list[dict[str, str]]:
    """Render a prompt template into a list of chat messages.

    Each template YAML must define ``system_prompt`` and ``user_prompt``
    fields which are Jinja2 strings.
    """
    tpl = get_template(template_id)
    if tpl is None:
        raise ValueError(f"prompt template '{template_id}' not found")

    sys_raw = tpl.get("system_prompt", "")
    usr_raw = tpl.get("user_prompt", "")

    sys_rendered = _env.from_string(sys_raw).render(**variables)
    usr_rendered = _env.from_string(usr_raw).render(**variables)

    messages: list[dict[str, str]] = []
    if sys_rendered.strip():
        messages.append({"role": "system", "content": sys_rendered})
    messages.append({"role": "user", "content": usr_rendered})
    return messages


def reload() -> None:
    """Force reload all templates from disk."""
    _template_cache.clear()
    _load_all()
