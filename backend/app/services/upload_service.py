"""压缩包上传服务：解压到工作区并创建为仓库（代码来源=上传）。"""

from __future__ import annotations

import logging
import re
import tarfile
import zipfile
from pathlib import Path
from typing import BinaryIO
from uuid import uuid4

from sqlalchemy.orm import Session

from app.config import settings
from app.core.exceptions import InvalidRequestError, NotFoundError
from app.repositories import project_repo, repository_repo

logger = logging.getLogger(__name__)

# 允许的压缩格式
ALLOWED_EXTENSIONS = (".zip", ".tar.gz", ".tgz", ".tar")
MAX_UPLOAD_BYTES = 300 * 1024 * 1024  # 300MB
# 解压后单文件完整路径最大长度（避免 Windows MAX_PATH 260 等限制）
MAX_EXTRACT_PATH_LEN = 240
# 上传仓库的 git_url 占位，sync 时跳过 clone
UPLOAD_REPO_GIT_URL = "upload"


def _safe_name(name: str) -> str:
    """只保留安全字符作为目录名."""
    return re.sub(r"[^\w\-.]", "_", name)[:64] or "upload"


def _extract_zip(file: BinaryIO, dest: Path) -> list[str]:
    """解压 zip，禁止路径穿越；跳过路径过长的文件，返回被跳过的路径列表."""
    skipped: list[str] = []
    dest_str = str(dest.resolve())
    with zipfile.ZipFile(file, "r") as zf:
        for info in zf.infolist():
            if info.is_dir():
                continue
            name = info.filename
            if ".." in name or name.startswith("/"):
                raise InvalidRequestError("压缩包包含非法路径，拒绝解压")
            if name.startswith("./"):
                name = name[2:]
            target = dest / name
            full_path = str(target.resolve())
            if len(full_path) > MAX_EXTRACT_PATH_LEN:
                skipped.append(name)
                logger.warning("skip path too long: %s (%d)", name, len(full_path))
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(info) as src:
                target.write_bytes(src.read())
    return skipped


def _extract_tar(file: BinaryIO, dest: Path) -> list[str]:
    """解压 tar/tar.gz，禁止路径穿越；跳过路径过长的文件，返回被跳过的路径列表."""
    skipped: list[str] = []
    file.seek(0)
    with tarfile.open(fileobj=file, mode="r:*") as tf:
        for member in tf.getmembers():
            if member.isdir():
                continue
            name = member.name
            if ".." in name or name.startswith("/"):
                raise InvalidRequestError("压缩包包含非法路径，拒绝解压")
            if name.startswith("./"):
                name = name[2:]
            target = dest / name
            full_path = str(target.resolve())
            if len(full_path) > MAX_EXTRACT_PATH_LEN:
                skipped.append(name)
                logger.warning("skip path too long: %s (%d)", name, len(full_path))
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            try:
                f = tf.extractfile(member)
                if f:
                    target.write_bytes(f.read())
            except Exception as e:
                logger.warning("skip extracting %s: %s", name, e)
    return skipped


def create_repo_from_upload(
    db: Session,
    project_id: int,
    file: BinaryIO,
    filename: str,
    repo_name: str | None = None,
) -> dict:
    """
    上传压缩包，解压到工作区并创建仓库记录。
    返回 RepoOut 兼容的 dict（含 repo_id, name, git_url=upload 等）。
    """
    proj = project_repo.get_by_id(db, project_id)
    if proj is None:
        raise NotFoundError(f"project {project_id} not found")

    base = Path(settings.repo_workspace)
    base.mkdir(parents=True, exist_ok=True)
    upload_dir = base / str(project_id) / "uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)

    ext = Path(filename).suffix.lower()
    if filename.endswith(".tar.gz") or filename.endswith(".tgz"):
        ext = ".tar.gz"
    if ext not in ALLOWED_EXTENSIONS:
        raise InvalidRequestError(
            f"仅支持压缩格式: {', '.join(ALLOWED_EXTENSIONS)}，当前: {filename}"
        )

    # 限制大小（粗略：读入内存解压时控制）
    file.seek(0, 2)
    size = file.tell()
    file.seek(0)
    if size > MAX_UPLOAD_BYTES:
        raise InvalidRequestError(
            f"压缩包大小超过限制（最大 {MAX_UPLOAD_BYTES // (1024*1024)}MB）"
        )

    uid = uuid4().hex[:12]
    safe = _safe_name(Path(filename).stem)
    extract_path = upload_dir / f"{safe}_{uid}"
    extract_path.mkdir(parents=True, exist_ok=True)

    try:
        skipped_zip: list[str] = []
        skipped_tar: list[str] = []
        if ext == ".zip":
            skipped_zip = _extract_zip(file, extract_path)
        else:
            skipped_tar = _extract_tar(file, extract_path)
        skipped = skipped_zip or skipped_tar
        if skipped:
            logger.warning("upload skipped %d paths longer than %d chars", len(skipped), MAX_EXTRACT_PATH_LEN)
    except InvalidRequestError:
        raise
    except zipfile.BadZipFile as e:
        raise InvalidRequestError(f"无效的 zip 文件: {e}") from e
    except tarfile.ReadError as e:
        raise InvalidRequestError(f"无效的 tar 文件: {e}") from e

    name = repo_name or (Path(filename).stem or f"upload_{uid}")
    # 同项目下仓库名唯一
    existing = repository_repo.list_by_project(db, project_id)
    if any(r.name == name for r in existing):
        name = f"{name}_{uid}"

    obj = repository_repo.create(
        db,
        project_id=project_id,
        name=name,
        git_url=UPLOAD_REPO_GIT_URL,
        default_branch="main",
        local_mirror_path=str(extract_path),
    )
    from app.schemas.repository import RepoOut
    return RepoOut.from_orm_obj(obj).model_dump()
