"""测试运行执行器：根据设置调用本机 Docker 或远程 SSH，更新执行结果。"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy.orm import Session

from app.execution.docker_executor import build_and_run
from app.execution.ssh_executor import run_via_ssh
from app.models.test_case import TestCase
from app.repositories.test_run_repo import (
    get_run_by_id,
    list_executions_for_run,
    update_run_status,
    update_execution_result,
)
from app.repositories.repository_repo import list_by_project
from app.services.execution_settings import get_execution_config
from app.services.script_generator import generate_script, ensure_unity_test_groups
from app.services.cmake_generator import generate_cmake_for_run

logger = logging.getLogger(__name__)


def _tc_to_script_dict(tc: TestCase) -> dict:
    """从 TestCase ORM 构建 generate_script 需要的字段。"""
    evidence = {}
    try:
        if getattr(tc, "evidence_json", None):
            evidence = json.loads(tc.evidence_json) if isinstance(tc.evidence_json, str) else (tc.evidence_json or {})
    except (TypeError, json.JSONDecodeError):
        pass
    return {
        "risk_type": getattr(tc, "risk_type", None) or "",
        "category": getattr(tc, "risk_type", None) or "",
        "symbol_name": getattr(tc, "symbol_name", None) or "",
        "target_function": getattr(tc, "symbol_name", None) or "",
        "file_path": getattr(tc, "file_path", None) or "",
        "target_file": getattr(tc, "file_path", None) or "",
        "title": tc.title or "",
        "priority": tc.priority or "P3",
        "evidence": evidence,
        "finding_id": "",
        "source_finding_id": "",
    }


def _resolve_workspace_path(db: Session, run) -> str:
    """解析用于 Docker 构建的工作区根目录：优先使用运行所属项目的仓库本地路径。"""
    if getattr(run, "project_id", None) is not None:
        repos = list_by_project(db, run.project_id)
        for repo in repos:
            path = getattr(repo, "local_mirror_path", None)
            if path and os.path.isdir(path):
                return os.path.abspath(path)
    return os.path.abspath(".")


def _workspace_include_dirs_from_file_path(file_path: str) -> list[str]:
    """
    根据被测文件路径生成通用 include 目录列表（相对 tests/ 的 ../ 前缀），
    使任意仓库结构下 #include 都能找到同目录或父级头文件；
    并为每个路径前缀增加 src/include 兄弟目录（便于 Unity 等框架的 unity.h 在 xxx/src 下）。
    例如 a/b/c/foo.c -> ["..", "../a", "../a/b", "../a/b/c", "../a/src", "../a/include", "../a/b/src", ...]
    """
    dirs = [".."]
    if not file_path:
        return dirs
    fp = file_path.replace("\\", "/").strip("/")
    if not fp:
        return dirs
    parts = fp.split("/")
    # Only directory segments (exclude last segment = filename) to avoid "foo.c/src" style paths
    prefixes = []
    for i in range(1, len(parts)):
        prefix = "/".join(parts[:i])
        if prefix and ("../" + prefix) not in dirs:
            dirs.append("../" + prefix)
            prefixes.append(prefix)
    for prefix in prefixes:
        for sub in ("src", "include"):
            p = f"../{prefix}/{sub}"
            if p not in dirs:
                dirs.append(p)
    return dirs


def _collect_workspace_sources(workspace_path: str, include_tests_unity: bool = False) -> list[str]:
    """
    收集工作区根目录下的 .c/.cpp 相对路径供 CMake 链接。
    - 默认排除 tests/ 下文件（避免重复或冲突）。
    - 若 include_tests_unity=True，则包含 tests/unity/ 下的 .c（Unity/Unity Fixture 实现）。
    - 排除常见带 main() 的文件：test.c, afl.c, *main*.c, fuzzing/ 下文件，避免 multiple definition of main。
    """
    root = Path(workspace_path)
    if not root.is_dir():
        return []
    out = []
    for pattern in ("*.c", "*.cpp"):
        for f in root.rglob(pattern):
            try:
                rel = f.relative_to(root)
                parts = rel.parts
                name = parts[-1] if parts else ""
                if "fuzzing" in parts or name in ("test.c", "afl.c") or "main" in name.lower():
                    continue
                if "tests" in parts:
                    if not include_tests_unity:
                        continue
                    # 只链接 Unity 核心与 Fixture 实现，避免 tests/unity 下其他 sample/mock 等编译失败
                    rel_str = str(rel)
                    if rel_str not in (
                        "tests/unity/src/unity.c",
                        "tests/unity/extras/fixture/src/unity_fixture.c",
                    ):
                        continue
                out.append(str(rel))
            except ValueError:
                continue
    return out


def run_test_run_sync(run_id: str, db: Session) -> None:
    """
    同步执行一次测试运行：按执行配置调用本机 Docker 或远程容器，
    逐条执行 pending 的用例并写回结果。
    """
    run = get_run_by_id(db, run_id)
    if not run:
        logger.warning("run not found: %s", run_id)
        return
    if run.status != "running":
        logger.info("run %s status is %s, skip execution", run_id, run.status)
        return

    config = get_execution_config()
    target = (config.get("target") or "local_docker").strip() or "local_docker"
    executions = list_executions_for_run(db, run.id)
    pending = [e for e in executions if e.status == "pending"]
    if not pending:
        update_run_status(
            db, run_id,
            status="success",
            passed=run.passed or 0,
            failed=run.failed or 0,
            skipped=run.skipped or 0,
            finished_at=datetime.now(timezone.utc),
        )
        return

    started_at = datetime.now(timezone.utc)
    update_run_status(db, run_id, "running", started_at=started_at)

    passed = run.passed or 0
    failed = run.failed or 0
    skipped = run.skipped or 0

    try:
        for ex in pending:
            run = get_run_by_id(db, run_id)
            if not run or run.status != "running":
                # 被暂停或强制停止，不再执行后续用例
                if run and run.status in ("paused", "cancelled"):
                    update_run_status(db, run_id, run.status, finished_at=datetime.now(timezone.utc))
                logger.info("run %s stopped with status %s", run_id, getattr(run, "status", None))
                break

            ex_start = datetime.now(timezone.utc)
            update_execution_result(db, ex.id, status="running", started_at=ex_start)

            tc = db.get(TestCase, ex.test_case_id) if ex.test_case_id else None
            if not tc:
                update_execution_result(
                    db, ex.id,
                    status="failed",
                    execution_status="runtime_error",
                    result_json=json.dumps({"message": "测试用例不存在"}),
                    finished_at=datetime.now(timezone.utc),
                )
                failed += 1
                continue

            script = getattr(tc, "script_content", None)
            if not script:
                d = _tc_to_script_dict(tc)
                script = generate_script(d, format="cpp")
            script = ensure_unity_test_groups(script)

            test_sources = {"test_main.cpp": script}
            workspace_abs = _resolve_workspace_path(db, run)
            include_tests_unity = "unity_fixture.h" in script or "unity.h" in script
            workspace_sources = _collect_workspace_sources(workspace_abs, include_tests_unity=include_tests_unity)
            workspace_include_dirs = _workspace_include_dirs_from_file_path(getattr(tc, "file_path", None) or "")
            cmake_content = generate_cmake_for_run(
                ["test_main.cpp"],
                workspace_include_dirs=workspace_include_dirs,
                workspace_source_files=workspace_sources if workspace_sources else None,
            )

            exec_tag = f"{run_id}-{ex.id}"
            result = None

            if target == "remote" and config.get("remote_host"):
                result = run_via_ssh(
                    exec_tag,
                    host=config.get("remote_host", ""),
                    port=int(config.get("remote_port") or 22),
                    username=config.get("remote_user", ""),
                    key_path=config.get("remote_key_path") or None,
                    remote_workdir=config.get("remote_workdir", "/tmp/grayscope_run"),
                )
            else:
                docker_image = (
                (getattr(run, "docker_image", None) or "").strip()
                or (config.get("docker_image") or "").strip()
            )
                result = build_and_run(
                    exec_tag,
                    workspace_path=workspace_abs,
                    test_sources=test_sources,
                    cmake_content=cmake_content,
                    docker_image_tag=None,
                    docker_base_image=docker_image if docker_image else None,
                )

            if not result:
                update_execution_result(
                    db, ex.id,
                    status="failed",
                    execution_status="runtime_error",
                    result_json=json.dumps({"message": "执行器未返回结果"}),
                    finished_at=datetime.now(timezone.utc),
                )
                failed += 1
                continue

            ex_list = result.get("executions") or []
            first = ex_list[0] if ex_list else {}
            exec_status = first.get("execution_status") or ("passed" if result.get("success") else "runtime_error")
            result_json = first.get("result_json") or json.dumps({"build_log": result.get("build_log", ""), "run_log": result.get("run_log", "")})

            status_map = {"passed": "passed", "assertion_fail": "failed", "runtime_error": "failed", "compile_error": "failed", "skipped": "skipped"}
            ex_status = status_map.get(exec_status, "failed")

            update_execution_result(
                db, ex.id,
                status=ex_status,
                execution_status=exec_status,
                result_json=result_json,
                finished_at=datetime.now(timezone.utc),
            )
            if ex_status == "passed":
                passed += 1
            elif ex_status == "skipped":
                skipped += 1
            else:
                failed += 1

        final_status = "failed" if failed > 0 else "success"
        update_run_status(
            db, run_id,
            status=final_status,
            passed=passed,
            failed=failed,
            skipped=skipped,
            finished_at=datetime.now(timezone.utc),
        )
        logger.info("run %s finished: %s, passed=%s failed=%s skipped=%s", run_id, final_status, passed, failed, skipped)
    except Exception as e:
        logger.exception("run_test_run_sync failed for %s: %s", run_id, e)
        run = get_run_by_id(db, run_id)
        if run and run.status == "running":
            update_run_status(
                db, run_id,
                status="failed",
                passed=passed,
                failed=failed,
                skipped=skipped,
                finished_at=datetime.now(timezone.utc),
            )
            # 把仍为 pending 的用例标为失败并带上错误信息
            for ex in pending:
                ex_refresh = list_executions_for_run(db, run.id)
                ex_row = next((x for x in ex_refresh if x.id == ex.id), None)
                if ex_row and ex_row.status == "pending":
                    update_execution_result(
                        db, ex.id,
                        status="failed",
                        execution_status="runtime_error",
                        result_json=json.dumps({"message": str(e)}),
                        finished_at=datetime.now(timezone.utc),
                    )
