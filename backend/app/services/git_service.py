"""Git workspace management: clone, fetch, checkout."""

from __future__ import annotations

import logging
import os
import subprocess
from pathlib import Path
from urllib.parse import urlparse

from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError, RepoSyncFailedError
from app.repositories import repository_repo
from app.services.upload_service import UPLOAD_REPO_GIT_URL
from app.utils.id_gen import sync_id

logger = logging.getLogger(__name__)


def _resolve_secret(auth_secret_ref: str | None) -> str | None:
    """Resolve secret from env var name or direct file path.
    
    If auth_secret_ref looks like a file path (starts with /, ~, or contains path separators),
    it's treated as a direct file path. Otherwise, it's treated as an environment variable name.
    Returns None if unset or empty.
    """
    if not auth_secret_ref:
        return None
    
    ref = auth_secret_ref.strip()
    
    # Detect if it's a direct file path
    if ref.startswith("/") or ref.startswith("~") or ref.startswith("./") or os.sep in ref:
        # Expand ~ to user home directory
        expanded = os.path.expanduser(ref)
        return expanded if expanded else None
    
    # Otherwise treat as environment variable name
    return os.environ.get(ref) or None


def _build_clone_url_with_token(git_url: str, token: str) -> str:
    """Inject token into HTTPS URL for clone/fetch (e.g. https://token@host/path)."""
    from urllib.parse import quote
    parsed = urlparse(git_url)
    if parsed.scheme not in ("http", "https"):
        return git_url
    netloc = parsed.netloc
    if "@" in netloc:
        netloc = netloc.split("@", 1)[1]
    safe_token = quote(token, safe="")
    auth_netloc = f"{safe_token}@{netloc}"
    return parsed._replace(netloc=auth_netloc).geturl()


def sync_repo(
    db: Session,
    repo_id: int,
    branch: str | None = None,
    tag: str | None = None,
    commit: str | None = None,
    depth: int = 1,
) -> dict:
    """Clone or fetch the repository, then checkout the requested revision."""
    repo = repository_repo.get_by_id(db, repo_id)
    if repo is None:
        raise NotFoundError(f"repo {repo_id} not found")

    sid = sync_id()
    mirror = Path(repo.local_mirror_path)
    revision = commit or tag or branch or repo.default_branch

    # 上传压缩包创建的仓库无需 clone，直接视为已就绪
    if repo.git_url == UPLOAD_REPO_GIT_URL:
        if not mirror.exists():
            raise RepoSyncFailedError("上传代码目录不存在")
        repository_repo.update_sync_status(db, repo_id, "success")
        return {"sync_id": sid, "repo_id": repo_id, "status": "success"}

    clone_url = repo.git_url
    env = os.environ.copy()

    if repo.auth_type == "https_token" and repo.auth_secret_ref:
        token = _resolve_secret(repo.auth_secret_ref)
        if token:
            clone_url = _build_clone_url_with_token(repo.git_url, token)
        else:
            logger.warning("repo %s: auth_secret_ref env var not set or empty", repo_id)
    elif repo.auth_type == "ssh_key" and repo.auth_secret_ref:
        key_path = _resolve_secret(repo.auth_secret_ref)
        if key_path and Path(key_path).exists():
            env["GIT_SSH_COMMAND"] = f"ssh -i {key_path} -o StrictHostKeyChecking=accept-new"
        else:
            logger.warning("repo %s: ssh key path from auth_secret_ref not found", repo_id)

    try:
        repository_repo.update_sync_status(db, repo_id, "running")

        if not (mirror / ".git").exists():
            mirror.mkdir(parents=True, exist_ok=True)
            _run(
                ["git", "clone"]
                + (["--depth", str(depth)] if depth > 0 else [])
                + ["--branch", branch or repo.default_branch, clone_url, str(mirror)],
                env=env,
            )
        else:
            _run(["git", "fetch", "--all"], cwd=mirror, env=env)
            _run(["git", "checkout", revision], cwd=mirror)

        repository_repo.update_sync_status(db, repo_id, "success")
        return {"sync_id": sid, "repo_id": repo_id, "status": "success"}
    except Exception as exc:
        logger.exception("sync failed for repo %s", repo_id)
        repository_repo.update_sync_status(db, repo_id, "failed")
        raise RepoSyncFailedError(str(exc)) from exc


def _run(
    cmd: list[str],
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
) -> str:
    env = env or os.environ
    result = subprocess.run(
        cmd,
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
        env=env,
    )
    if result.returncode != 0:
        raise RuntimeError(f"git command failed: {result.stderr.strip()}")
    return result.stdout
