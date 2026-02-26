"""执行环境 API：轻量 Docker 管理 — 镜像拉取/导入、容器创建/启停/删除。"""

from __future__ import annotations

import io
import logging
from typing import Optional

from fastapi import APIRouter, File, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field

from app.core.response import ok

logger = logging.getLogger(__name__)

router = APIRouter()


def _docker_client():
    import docker
    try:
        return docker.from_env()
    except Exception as e:
        logger.warning("Docker client init failed: %s", e)
        raise HTTPException(status_code=503, detail=f"Docker 不可用: {e}")


# ── 镜像 ─────────────────────────────────────────────────────────────────────

@router.get("/execution-env/images")
def list_images() -> dict:
    """镜像列表。"""
    client = _docker_client()
    try:
        images = client.images.list()
        items = []
        for img in images:
            tags = img.tags or ["<none>:<none>"]
            for tag in tags:
                repo, _, tag_name = tag.partition(":")
                if not tag_name:
                    tag_name = "latest"
                items.append({
                    "id": img.short_id,
                    "tags": [tag],
                    "repository": repo,
                    "tag": tag_name,
                    "size": img.attrs.get("Size", 0),
                    "created": img.attrs.get("Created", ""),
                })
        return ok({"images": items})
    finally:
        client.close()


class PullImageBody(BaseModel):
    image: str = Field(..., description="镜像名，如 ubuntu:22.04")


@router.post("/execution-env/images/pull")
def pull_image(body: PullImageBody) -> dict:
    """拉取镜像。"""
    client = _docker_client()
    try:
        out = client.images.pull(body.image)
        if isinstance(out, list):
            img = out[-1] if out else None
        else:
            img = out
        id_ = img.id if img else ""
        return ok({"image": body.image, "id": id_, "message": "拉取成功"})
    except Exception as e:
        logger.exception("pull image %s: %s", body.image, e)
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        client.close()


@router.post("/execution-env/images/load")
async def load_image(file: UploadFile = File(...)) -> dict:
    """从 tar 文件导入镜像。"""
    client = _docker_client()
    try:
        data = await file.read()
        if not data:
            raise HTTPException(status_code=400, detail="文件为空")
        stream = io.BytesIO(data)
        result = client.images.load(stream)
        loaded = [{"id": img.short_id, "tags": img.tags} for img in result]
        return ok({"loaded": loaded, "message": "导入成功"})
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("load image: %s", e)
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        client.close()


# ── 容器 ───────────────────────────────────────────────────────────────────

@router.get("/execution-env/containers")
def list_containers(all: bool = Query(True, description="包含已停止的容器")) -> dict:
    """容器列表。all=true 含已停止的。"""
    client = _docker_client()
    try:
        containers = client.containers.list(all=all)
        items = []
        for c in containers:
            attrs = c.attrs
            items.append({
                "id": c.short_id,
                "name": (c.name or "").lstrip("/"),
                "image": attrs.get("Config", {}).get("Image", ""),
                "status": c.status,
                "created": attrs.get("Created", ""),
                "state": attrs.get("State", {}).get("Status", ""),
            })
        return ok({"containers": items})
    finally:
        client.close()


class CreateContainerBody(BaseModel):
    image: str = Field(..., description="镜像名或 ID")
    name: Optional[str] = Field(None, description="容器名称")
    cmd: Optional[str] = Field(None, description="启动命令，如 /bin/bash")
    entrypoint: Optional[str] = None


@router.post("/execution-env/containers")
def create_container(body: CreateContainerBody) -> dict:
    """创建容器（不自动启动）。"""
    client = _docker_client()
    try:
        kwargs = {"image": body.image}
        if body.name:
            kwargs["name"] = body.name
        if body.cmd:
            kwargs["command"] = body.cmd.split()
        if body.entrypoint:
            kwargs["entrypoint"] = body.entrypoint.split()
        container = client.containers.create(**kwargs)
        return ok({
            "id": container.short_id,
            "name": (container.name or "").lstrip("/"),
            "message": "容器已创建，可点击启动",
        })
    except Exception as e:
        logger.exception("create container: %s", e)
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        client.close()


@router.post("/execution-env/containers/{container_id}/start")
def start_container(container_id: str) -> dict:
    """启动容器。"""
    client = _docker_client()
    try:
        c = client.containers.get(container_id)
        c.start()
        return ok({"id": container_id, "message": "已启动"})
    except Exception as e:
        logger.exception("start container %s: %s", container_id, e)
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        client.close()


@router.post("/execution-env/containers/{container_id}/stop")
def stop_container(container_id: str) -> dict:
    """停止容器。"""
    client = _docker_client()
    try:
        c = client.containers.get(container_id)
        c.stop()
        return ok({"id": container_id, "message": "已停止"})
    except Exception as e:
        logger.exception("stop container %s: %s", container_id, e)
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        client.close()


@router.delete("/execution-env/containers/{container_id}")
def remove_container(container_id: str, force: bool = Query(False, description="强制删除运行中的容器")) -> dict:
    """删除容器。force=true 可删除运行中的容器。"""
    client = _docker_client()
    try:
        c = client.containers.get(container_id)
        c.remove(force=force)
        return ok({"id": container_id, "message": "已删除"})
    except Exception as e:
        logger.exception("remove container %s: %s", container_id, e)
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        client.close()


@router.get("/execution-env/containers/{container_id}")
def inspect_container(container_id: str) -> dict:
    """容器详情。"""
    client = _docker_client()
    try:
        c = client.containers.get(container_id)
        return ok({"container": c.attrs})
    except Exception as e:
        logger.exception("inspect container %s: %s", container_id, e)
        raise HTTPException(status_code=404, detail=str(e))
    finally:
        client.close()
