# GrayScope 部署文档

本文档说明 GrayScope 的部署方式、环境要求与常用配置。

## 1. 环境要求

- **操作系统**：推荐 Linux（x86_64），macOS 可用于开发
- **Docker**：若使用 Docker 部署，需 Docker 20.10+ 与 Docker Compose V2
- **Python**：本地部署后端需 Python 3.10+
- **Node.js**：本地构建前端需 Node.js 18+

## 2. Docker 一键部署（推荐）

### 2.1 启动服务

在项目根目录执行：

```bash
docker-compose up -d
```

- **后端 API**：`http://<host>:18080`
- **前端 Web**：`http://<host>:15173`
- API 文档：`http://<host>:18080/docs`

### 2.2 端口说明

| 端口  | 服务   | 说明           |
|-------|--------|----------------|
| 18080 | 后端   | FastAPI 主服务 |
| 15173 | 前端   | Vite 开发/构建后静态服务 |

### 2.3 数据持久化

- 后端使用 SQLite 时，数据文件位于容器内；若需持久化，可在 `docker-compose.yml` 中为后端服务挂载 volume 到数据库文件路径。
- 使用 PostgreSQL 等外部数据库时，需在环境变量中配置 `DATABASE_URL` 并在编排中接入对应服务。

### 2.4 测试执行（Docker 环境）

- 测试运行若选择「Docker」环境，执行器会在宿主机调用 Docker 构建并运行测试镜像。
- 需保证运行 GrayScope 的宿主机可执行 `docker build` / `docker run`（即 Docker-in-Docker 或宿主机 Docker 套接字挂载）。
- 可选镜像：如 `postgres:16-alpine` 等，用于提供 C/C++ 编译与运行环境；镜像需包含 `gcc`/`g++`、`make`、`cmake` 等。

## 3. 本地开发部署

### 3.1 后端

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --host 127.0.0.1 --port 18080 --reload
```

- 健康检查：`GET http://127.0.0.1:18080/api/v1/health`
- OpenAPI：`http://127.0.0.1:18080/docs`

### 3.2 前端

```bash
cd frontend
npm install
npm run dev
```

- 访问：`http://localhost:15173`
- 开发模式下前端会代理 `/api` 到后端（需在 `vite.config` 等配置中指向后端地址，如 `http://127.0.0.1:18080`）。

### 3.3 环境变量（可选）

- 后端：数据库连接、AI Provider 端点等可通过环境变量或 `.env` 配置，参见 `backend` 内配置加载逻辑。
- 前端：构建时可通过 `import.meta.env` 注入 API 基地址等。

## 4. 生产/内网部署要点

- **协议**：内网通常 HTTP 即可；若需 HTTPS，可在前端与后端前增加反向代理（如 Nginx），配置 TLS。
- **认证**：当前版本无用户登录；若需限制访问，可在 Nginx 或网关层做 IP 白名单、Basic Auth 等。
- **资源**：分析任务与测试执行会占用 CPU/内存，建议根据并发任务数适当调大后端与执行器资源限制。

## 5. 故障排查

- **后端无法访问**：检查 18080 是否被占用、防火墙是否放行。
- **前端请求 API 404**：确认前端代理或生产环境中的 API 基地址指向正确后端。
- **测试执行失败**：查看运行详情中的构建/运行日志；确认 Docker 可用且所选镜像包含编译与测试运行时所需工具链。
