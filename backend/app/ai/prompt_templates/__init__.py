"""AI prompt templates for code analysis narrative generation.

This module provides prompt templates for transforming technical analysis
results into business-friendly narratives and test guidance.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

_TEMPLATE_DIR = Path(__file__).parent
_template_cache: dict[str, dict[str, Any]] = {}


def _load_template(template_id: str) -> dict[str, Any]:
    """Load a prompt template from YAML file."""
    if template_id in _template_cache:
        return _template_cache[template_id]
    
    template_path = _TEMPLATE_DIR / f"{template_id}.yaml"
    if not template_path.exists():
        raise FileNotFoundError(f"Template not found: {template_id}")
    
    with open(template_path, encoding="utf-8") as f:
        template = yaml.safe_load(f)
    
    _template_cache[template_id] = template
    return template


def get_system_prompt(template_id: str) -> str:
    """Get the system prompt from a template."""
    template = _load_template(template_id)
    return template.get("system", "")


def get_user_prompt(template_id: str) -> str:
    """Get the user prompt template string."""
    template = _load_template(template_id)
    return template.get("user", "")


def render_prompt(template_id: str, **kwargs: Any) -> tuple[str, str]:
    """Render a prompt template with given variables.
    
    Returns:
        Tuple of (system_prompt, user_prompt)
    """
    template = _load_template(template_id)
    system = template.get("system", "")
    user_template = template.get("user", "")
    
    # Format the user prompt with provided variables
    try:
        user = user_template.format(**kwargs)
    except KeyError as e:
        logger.warning(f"Missing template variable: {e}")
        user = user_template
    
    return system, user


def list_templates() -> list[dict[str, str]]:
    """List all available prompt templates."""
    templates = []
    for yaml_file in _TEMPLATE_DIR.glob("*.yaml"):
        try:
            template = _load_template(yaml_file.stem)
            templates.append({
                "id": template.get("id", yaml_file.stem),
                "name": template.get("name", ""),
                "description": template.get("description", ""),
            })
        except Exception as e:
            logger.warning(f"Failed to load template {yaml_file}: {e}")
    return templates


__all__ = [
    "get_system_prompt",
    "get_user_prompt",
    "render_prompt",
    "list_templates",
]
