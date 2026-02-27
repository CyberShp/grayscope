# 执行环境板块设计（轻量 Docker 管理）

## 目标

- 单独导航入口「执行环境」，与测试执行解耦。
- 轻量模仿 Docker：镜像管理（拉取/导入）+ 容器管理（创建/启停/删除）。
- 用户可在 Web 上：拉取镜像或上传镜像包（tar）导入、创建并部署容器、管理容器生命周期。

## 范围

- **镜像**：列表、拉取（pull）、从文件导入（load tar）。
- **容器**：列表、创建（选镜像+名称+可选命令）、启动、停止、删除。
- 不包含：网络/卷的独立管理、编排、多主机（仅本机 Docker 或 DOCKER_HOST）。

## 架构

- **后端**：新路由 `/api/v1/execution-env`，使用 Docker SDK for Python 调用本机 Docker 守护进程（或 DOCKER_HOST）。
- **前端**：新路由 `/execution-env`，单页内 Tab「镜像管理」「容器管理」。

## API 设计

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | /execution-env/images | 镜像列表 |
| POST | /execution-env/images/pull | 拉取镜像 body: `{ "image": "ubuntu:22.04" }` |
| POST | /execution-env/images/load | 上传 tar 并 load（multipart） |
| GET | /execution-env/containers | 容器列表 ?all=true |
| POST | /execution-env/containers | 创建容器 body: image, name?, cmd? |
| POST | /execution-env/containers/{id}/start | 启动 |
| POST | /execution-env/containers/{id}/stop | 停止 |
| DELETE | /execution-env/containers/{id} | 删除 |

## 前端结构

- 导航：增加「执行环境」→ `/execution-env`。
- 页面：`ExecutionEnv.vue`，el-tabs：镜像管理 | 容器管理。
- 镜像管理：表格（仓库:标签、ID、大小、创建时间）、拉取镜像（对话框）、导入镜像（上传 tar）。
- 容器管理：表格（名称、镜像、状态、创建时间）、创建容器（选镜像+名称+命令）、启动/停止/删除。

## 安全与依赖

- 依赖：`docker` (Docker SDK for Python)。
- 守护进程：默认本机 socket；可通过环境变量 DOCKER_HOST 指定远程。
- 注意：暴露 Docker 能力需在可信环境使用（如内网）。
