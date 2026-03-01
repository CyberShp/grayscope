"""Application configuration via environment variables and .env file."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict

_PROJECT_ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(_PROJECT_ROOT / ".env"),
        env_file_encoding="utf-8",
        env_prefix="GS_",
        case_sensitive=False,
    )

    # --- General ---
    app_name: str = "GrayScope"
    debug: bool = False

    # --- Database ---
    database_url: str = f"sqlite:///{_PROJECT_ROOT / 'grayscope.db'}"

    # --- Repository workspace ---
    repo_workspace: str = str(_PROJECT_ROOT / "workspaces")

    # --- Artifact storage ---
    artifact_dir: str = str(_PROJECT_ROOT / "artifacts")

    # --- AI defaults ---
    default_provider: str = "deepseek"
    default_model: str = "deepseek-coder"

    # --- Provider endpoints ---
    # DeepSeek (can use custom base_url for internal mirrors)
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_api_key: Optional[str] = None
    # Custom provider (any OpenAI-compatible API)
    custom_base_url: str = "http://localhost:8000"
    custom_api_key: Optional[str] = None
    custom_model: str = "default"

    # --- AI Proxy (for internal network environments) ---
    # Supports HTTP/HTTPS/SOCKS5 proxy, e.g. "http://proxy:8080" or "socks5://proxy:1080"
    ai_proxy: Optional[str] = None

    # --- Prompt ---
    prompt_template_dir: str = str(
        Path(__file__).resolve().parent / "ai" / "prompt_templates"
    )

    # --- Task ---
    max_concurrent_tasks: int = 10

    # --- 显示时间（部署环境时区，用于前端时间展示）---
    display_timezone: str = "Asia/Shanghai"


settings = Settings()
