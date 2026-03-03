"""AI prompt templates for code analysis narrative generation.

This module provides prompt templates for transforming technical analysis
results into business-friendly narratives and test guidance.

Supports both Python format strings and Jinja2 templates.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

_TEMPLATE_DIR = Path(__file__).parent
_template_cache: dict[str, dict[str, Any]] = {}

# Lazy-load jinja2 to avoid import overhead if not needed
_jinja_env = None


def _get_jinja_env():
    """Get or create Jinja2 environment."""
    global _jinja_env
    if _jinja_env is None:
        try:
            from jinja2 import Environment, BaseLoader
            _jinja_env = Environment(loader=BaseLoader())
        except ImportError:
            _jinja_env = False  # Mark as unavailable
    return _jinja_env


def _is_jinja_template(text: str) -> bool:
    """Check if text contains Jinja2 syntax.
    
    Detects {% %} control blocks OR {{ identifier }} variable expressions.
    Python str.format() uses {{ to produce literal '{' — in that case
    the double brace is followed by a newline or quote, not a word char.
    Jinja2 {{ var }} always has a word character after the opening braces.
    """
    return bool(re.search(r"\{%|\{\{\s*\w", text))


def _render_template_string(template_str: str, variables: dict[str, Any]) -> str:
    """Render a template string with variables.
    
    Uses Jinja2 if the template contains Jinja2 syntax, otherwise uses str.format().
    """
    if not template_str:
        return ""
    
    if _is_jinja_template(template_str):
        # Use Jinja2 for complex templates
        jinja_env = _get_jinja_env()
        if jinja_env:
            try:
                template = jinja_env.from_string(template_str)
                return template.render(**variables)
            except Exception as e:
                logger.warning(f"Jinja2 rendering failed: {e}, falling back to raw template")
                return template_str
        else:
            logger.warning("Jinja2 not available, returning raw template")
            return template_str
    else:
        # Use simple Python format for basic templates
        try:
            return template_str.format(**variables)
        except KeyError as e:
            logger.warning(f"Missing template variable: {e}")
            return template_str


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
        (system_prompt, user_prompt) tuple of rendered strings.
    """
    template = _load_template(template_id)
    system_template = template.get("system", "")
    user_template = template.get("user", "")
    
    system = _render_template_string(system_template, kwargs)
    user = _render_template_string(user_template, kwargs)
    
    return system, user


def render_prompt_messages(template_id: str, **kwargs: Any) -> list[dict[str, str]]:
    """Render a prompt template as chat API message dicts.
    
    Returns:
        List of message dicts [{"role": "system", "content": ...}, ...]
    """
    system, user = render_prompt(template_id, **kwargs)
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    if user:
        messages.append({"role": "user", "content": user})
    return messages


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
    "render_prompt_messages",
    "list_templates",
]
