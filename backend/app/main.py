"""GrayScope 灰盒测试分析平台后端入口。"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse

from app.api.v1.aggregation import router as aggregation_router
from app.api.v1.analysis import router as analysis_router
from app.api.v1.health import router as health_router
from app.api.v1.models_api import router as models_router
from app.api.v1.postmortem import router as postmortem_router
from app.api.v1.projects import router as projects_router
from app.api.v1.repos import router as repos_router
from app.core.database import engine
from app.core.exceptions import GrayScopeError
from app.core.response import error
from app.models import Base

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动：创建数据库表（开发便利；生产环境使用 Alembic）
    Base.metadata.create_all(bind=engine)
    logger.info("数据库表已就绪")
    yield
    # 关闭
    logger.info("正在关闭服务")


app = FastAPI(
    title="GrayScope 灰盒测试分析平台",
    description="基于静态分析和 AI 增强的灰盒测试设计分析系统",
    version="1.0.0",
    lifespan=lifespan,
)

# 跨域配置（允许前端开发服务器访问）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── 注册路由 ──────────────────────────────────────────────────────────

app.include_router(health_router, prefix="/api/v1", tags=["健康检查"])
app.include_router(projects_router, prefix="/api/v1", tags=["项目管理"])
app.include_router(repos_router, prefix="/api/v1", tags=["仓库管理"])
app.include_router(analysis_router, prefix="/api/v1", tags=["分析任务"])
app.include_router(postmortem_router, prefix="/api/v1", tags=["事后分析", "知识库"])
app.include_router(models_router, prefix="/api/v1", tags=["AI模型"])
app.include_router(aggregation_router, prefix="/api/v1", tags=["聚合数据"])


# ── 根路径重定向 ──────────────────────────────────────────────────────


@app.get("/", include_in_schema=False)
async def root():
    """重定向根路径到 Swagger 文档。"""
    return RedirectResponse(url="/docs")


# ── 全局异常处理 ──────────────────────────────────────────────────────


@app.exception_handler(GrayScopeError)
async def grayscope_error_handler(request: Request, exc: GrayScopeError):
    return JSONResponse(
        status_code=exc.status_code,
        content=error(exc.code, exc.message),
    )


@app.exception_handler(Exception)
async def generic_error_handler(request: Request, exc: Exception):
    logger.exception("未处理的异常")
    return JSONResponse(
        status_code=500,
        content=error("INTERNAL_ERROR", f"服务器内部错误: {exc}"),
    )
