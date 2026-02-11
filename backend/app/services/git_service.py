"""Git workspace management: clone, fetch, checkout."""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path

from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError, RepoSyncFailedError
from app.repositories import repository_repo
from app.utils.id_gen import sync_id

logger = logging.getLogger(__name__)


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

    try:
        repository_repo.update_sync_status(db, repo_id, "running")

        if not (mirror / ".git").exists():
            mirror.mkdir(parents=True, exist_ok=True)
            _run(
                ["git", "clone"]
                + (["--depth", str(depth)] if depth > 0 else [])
                + ["--branch", branch or repo.default_branch, repo.git_url, str(mirror)]
            )
        else:
            _run(["git", "fetch", "--all"], cwd=mirror)
            _run(["git", "checkout", revision], cwd=mirror)

        repository_repo.update_sync_status(db, repo_id, "success")
        return {"sync_id": sid, "repo_id": repo_id, "status": "success"}
    except Exception as exc:
        logger.exception("sync failed for repo %s", repo_id)
        repository_repo.update_sync_status(db, repo_id, "failed")
        raise RepoSyncFailedError(str(exc)) from exc


def _run(cmd: list[str], cwd: Path | None = None) -> str:
    result = subprocess.run(
        cmd,
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f"git command failed: {result.stderr.strip()}")
    return result.stdout
