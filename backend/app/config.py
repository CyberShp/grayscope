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
    default_provider: str = "ollama"
    default_model: str = "qwen2.5-coder"

    # --- Provider endpoints ---
    ollama_base_url: str = "http://localhost:11434"
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_api_key: Optional[str] = None
    qwen_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode"
    qwen_api_key: Optional[str] = None
    openai_compat_base_url: str = "http://localhost:8000"
    openai_compat_api_key: Optional[str] = None
    custom_rest_base_url: str = "http://localhost:9000"
    custom_rest_api_key: Optional[str] = None

    # --- Prompt ---
    prompt_template_dir: str = str(
        Path(__file__).resolve().parent / "ai" / "prompt_templates"
    )

    # --- Task ---
    max_concurrent_tasks: int = 10


settings = Settings()
