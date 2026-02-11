# GrayScope 灰盒测试分析平台 - Makefile
# 常用开发和部署命令

.PHONY: backend frontend cli-health cli-analyze docker-up docker-down docker-prod build-frontend clean help

# ── 本地开发 ──────────────────────────────────────────────────────────

## 启动后端开发服务器（热重载）
backend:
	cd backend && source .venv/bin/activate && uvicorn app.main:app --host 127.0.0.1 --port 18080 --reload

## 启动前端开发服务器
frontend:
	cd frontend && npm run dev

## CLI 健康检查
cli-health:
	cd cli && python -m grayscope_cli.main health

## CLI 创建分析任务
cli-analyze:
	cd cli && python -m grayscope_cli.main analyze create --project 1 --repo 1 --type full --target .

# ── Docker 开发 ──────────────────────────────────────────────────────

## Docker 启动开发环境（含前端热重载）
docker-dev:
	docker-compose --profile dev up -d --build

## Docker 停止所有服务
docker-down:
	docker-compose --profile dev down

# ── 生产部署 ──────────────────────────────────────────────────────────

## 构建前端静态文件
build-frontend:
	cd frontend && npm install && npm run build

## 生产部署（Nginx + 后端）
docker-prod: build-frontend
	docker-compose up -d --build backend frontend

## 仅启动后端（不含前端）
docker-backend:
	docker-compose up -d --build backend

# ── 清理 ──────────────────────────────────────────────────────────────

## 清理所有生成文件和数据库
clean:
	rm -f backend/grayscope.db
	rm -rf backend/.venv
	rm -rf frontend/node_modules
	rm -rf frontend/dist

## 仅清理数据库（重建表结构）
clean-db:
	rm -f backend/grayscope.db

# ── 帮助 ──────────────────────────────────────────────────────────────

## 显示可用命令
help:
	@echo ""
	@echo "GrayScope 灰盒测试分析平台 - 可用命令"
	@echo "────────────────────────────────────────"
	@echo "  make backend        启动后端开发服务器"
	@echo "  make frontend       启动前端开发服务器"
	@echo "  make cli-health     CLI 健康检查"
	@echo "  make cli-analyze    CLI 创建分析任务"
	@echo "  make docker-dev     Docker 开发环境"
	@echo "  make docker-prod    生产部署"
	@echo "  make docker-down    停止 Docker 服务"
	@echo "  make build-frontend 构建前端静态文件"
	@echo "  make clean          清理所有生成文件"
	@echo "  make clean-db       清理数据库"
	@echo ""
