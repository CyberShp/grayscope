"""GrayScope 灰盒测试分析平台后端入口。"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse

from app.api.v1.aggregation import router as aggregation_router
from app.api.v1.analysis import router as analysis_router
from app.api.v1.code_analysis_api import router as code_analysis_router
from app.api.v1.health import router as health_router
from app.api.v1.models_api import router as models_router
from app.api.v1.postmortem import router as postmortem_router
from app.api.v1.projects import router as projects_router
from app.api.v1.repos import router as repos_router
from app.api.v1.test_runs import router as test_runs_router
from app.api.v1.execution_env import router as execution_env_router
from app.core.database import engine
from app.core.exceptions import GrayScopeError
from app.core.response import error
from app.models import Base

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def _migrate_repo_auth_columns():
    """Add auth_type, auth_secret_ref to repositories if missing (e.g. existing DBs)."""
    from sqlalchemy import text
    for col, typ in (("auth_type", "VARCHAR(32)"), ("auth_secret_ref", "VARCHAR(256)")):
        try:
            with engine.connect() as conn:
                conn.execute(text(f"ALTER TABLE repositories ADD COLUMN {col} {typ}"))
                conn.commit()
            logger.info("repositories: added column %s", col)
        except Exception as e:
            if "duplicate" in str(e).lower() or "already exists" in str(e).lower():
                pass
            else:
                logger.warning("repositories migration %s: %s", col, e)


def _migrate_test_case_hint_columns():
    """Add execution_hint, example_input, expected_failure, unacceptable_outcomes_json, related_functions_json to test_cases if missing."""
    from sqlalchemy import text
    for col in ("execution_hint", "example_input", "expected_failure", "unacceptable_outcomes_json", "related_functions_json"):
        try:
            with engine.connect() as conn:
                conn.execute(text(f"ALTER TABLE test_cases ADD COLUMN {col} TEXT"))
                conn.commit()
            logger.info("test_cases: added column %s", col)
        except Exception as e:
            if "duplicate" in str(e).lower() or "already exists" in str(e).lower():
                pass
            else:
                logger.warning("test_cases migration %s: %s", col, e)


def _migrate_v2_columns():
    """V2: 分析支柱、传播链、用例执行字段及新表。"""
    from sqlalchemy import text
    migrations = [
        ("analysis_tasks", "pillar", "TEXT"),
        ("risk_findings", "pillar", "TEXT"),
        ("risk_findings", "call_chain_json", "TEXT"),
        ("test_cases", "execution_type", "TEXT"),
        ("test_cases", "target_device_json", "TEXT"),
        ("test_cases", "instruments_json", "TEXT"),
        ("test_cases", "script_content", "TEXT"),
        ("test_cases", "expected_protocol_json", "TEXT"),
    ]
    for table, col, typ in migrations:
        try:
            with engine.connect() as conn:
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {col} {typ}"))
                conn.commit()
            logger.info("v2 migration: %s.%s", table, col)
        except Exception as e:
            if "duplicate" in str(e).lower() or "already exists" in str(e).lower():
                pass
            else:
                logger.warning("v2 migration %s.%s: %s", table, col, e)


def _migrate_test_run_and_execution():
    """TestRun 表由 create_all 创建；TestExecution 扩展列 test_run_id, execution_status。"""
    from sqlalchemy import text
    for table, col, typ in [
        ("test_executions", "test_run_id", "BIGINT"),
        ("test_executions", "execution_status", "VARCHAR(24)"),
    ]:
        try:
            with engine.connect() as conn:
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {col} {typ}"))
                conn.commit()
            logger.info("test_run migration: %s.%s", table, col)
        except Exception as e:
            if "duplicate" in str(e).lower() or "already exists" in str(e).lower():
                pass
            else:
                logger.warning("test_run migration %s.%s: %s", table, col, e)


def _migrate_test_run_name_docker():
    """TestRun 增加 name、docker_image 列。"""
    from sqlalchemy import text
    for col, typ in (("name", "VARCHAR(256)"), ("docker_image", "VARCHAR(512)")):
        try:
            with engine.connect() as conn:
                conn.execute(text(f"ALTER TABLE test_runs ADD COLUMN {col} {typ}"))
                conn.commit()
            logger.info("test_runs: added column %s", col)
        except Exception as e:
            if "duplicate" in str(e).lower() or "already exists" in str(e).lower():
                pass
            else:
                logger.warning("test_runs migration %s: %s", col, e)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动：创建数据库表（开发便利；生产环境使用 Alembic）
    Base.metadata.create_all(bind=engine)
    _migrate_repo_auth_columns()
    _migrate_test_case_hint_columns()
    _migrate_v2_columns()
    _migrate_test_run_and_execution()
    _migrate_test_run_name_docker()
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
app.include_router(code_analysis_router, prefix="/api/v1", tags=["代码分析流水线"])
app.include_router(postmortem_router, prefix="/api/v1", tags=["事后分析", "知识库"])
app.include_router(models_router, prefix="/api/v1", tags=["AI模型"])
app.include_router(aggregation_router, prefix="/api/v1", tags=["聚合数据"])
app.include_router(test_runs_router, prefix="/api/v1", tags=["测试执行"])
app.include_router(execution_env_router, prefix="/api/v1", tags=["执行环境"])


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
