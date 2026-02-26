"""执行环境配置：本机 Docker / 远程容器，持久化到 JSON 文件。"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from app.config import settings

DEFAULT_EXECUTION = {
    "target": "local_docker",  # local_docker | remote
    "docker_image": "",  # 空则使用内置 Dockerfile 的默认镜像；可填如 ubuntu:22.04
    "remote_host": "",
    "remote_port": 22,
    "remote_user": "",
    "remote_key_path": "",
    "remote_workdir": "/tmp/grayscope_run",
}


def _settings_path() -> Path:
    p = Path(settings.artifact_dir)
    p.mkdir(parents=True, exist_ok=True)
    return p / "execution_settings.json"


def get_execution_config() -> dict[str, Any]:
    """读取执行环境配置，缺省返回 DEFAULT_EXECUTION。"""
    path = _settings_path()
    if not path.exists():
        return dict(DEFAULT_EXECUTION)
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        out = dict(DEFAULT_EXECUTION)
        out.update(data)
        return out
    except (json.JSONDecodeError, OSError):
        return dict(DEFAULT_EXECUTION)


def save_execution_config(config: dict[str, Any]) -> None:
    """保存执行环境配置（只写 execution 相关字段）。"""
    path = _settings_path()
    current = get_execution_config()
    for k in DEFAULT_EXECUTION:
        if k in config:
            current[k] = config[k]
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(current, f, ensure_ascii=False, indent=2)
