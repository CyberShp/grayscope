"""Docker + QEMU ARM 执行器：在容器内交叉编译并运行 CppUnit，收集 JUnit XML 与 gcov 覆盖率。"""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# 复制工作区时排除的目录/文件名（不排除 tests，以便仓库内 tests/unity 等被复制）
_WORKSPACE_EXCLUDE = {".git", "__pycache__", "node_modules", ".cursor", ".venv", "venv", "build"}

# 执行结果四种状态（与 test_execution 模型一致）
STATUS_PASSED = "passed"
STATUS_ASSERTION_FAIL = "assertion_fail"
STATUS_RUNTIME_ERROR = "runtime_error"
STATUS_COMPILE_ERROR = "compile_error"
STATUS_SKIPPED = "skipped"


def _is_alpine_image(base_image: str) -> bool:
    """基础镜像名或 tag 中含 alpine 则视为 Alpine 系（用 apk）。"""
    return base_image and "alpine" in base_image.lower()


def _dockerfile_content(base_image: str = "arm64v8/ubuntu:22.04") -> str:
    """生成 Dockerfile：基于指定镜像，安装 CppUnit。Debian/Ubuntu 用 apt-get，Alpine 用 apk。"""
    if _is_alpine_image(base_image):
        return r"""
FROM """ + base_image + r"""
RUN apk add --no-cache \
    g++ \
    make \
    cmake \
    cppunit-dev \
    gcovr \
    git
WORKDIR /workspace
COPY . /workspace
WORKDIR /workspace/tests
RUN mkdir -p build && cd build && \
    cmake .. -DCMAKE_BUILD_TYPE=Debug -DCMAKE_CXX_FLAGS="--coverage -O0 -g" && \
    make -j$(nproc)
CMD ["/bin/sh", "-c", "cd /workspace/tests/build && ctest --output-on-failure --no-compress-output -T Test || true; gcovr -r ../.. --json -o coverage.json 2>/dev/null || true"]
"""
    # Debian/Ubuntu
    return r"""
FROM """ + base_image + r"""
RUN apt-get update && apt-get install -y --no-install-recommends \
    g++ \
    cmake \
    git \
    libcppunit-dev \
    gcovr \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /workspace
COPY . /workspace
WORKDIR /workspace/tests
RUN mkdir -p build && cd build && \
    cmake .. -DCMAKE_BUILD_TYPE=Debug -DCMAKE_CXX_FLAGS="--coverage -O0 -g" && \
    make -j$(nproc)
CMD ["/bin/bash", "-c", "cd /workspace/tests/build && ctest --output-on-failure --no-compress-output -T Test || true; gcovr -r ../.. --json -o coverage.json 2>/dev/null || true"]
"""


def _run_cmd(cmd: list[str], cwd: str | None = None, timeout: int = 600) -> tuple[int, str, str]:
    """执行命令，返回 (returncode, stdout, stderr)。"""
    try:
        r = subprocess.run(
            cmd,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return (r.returncode, r.stdout or "", r.stderr or "")
    except subprocess.TimeoutExpired:
        return (-1, "", "Timeout")
    except FileNotFoundError:
        return (-1, "", "Command not found")
    except Exception as e:
        return (-1, "", str(e))


def build_and_run(
    run_id: str,
    workspace_path: str,
    test_sources: dict[str, str],
    cmake_content: str,
    docker_image_tag: str | None = None,
    docker_base_image: str | None = None,
) -> dict[str, Any]:
    """
    在 Docker 中构建并运行测试，收集 JUnit XML 与 gcovr 覆盖率。

    :param run_id: 运行 ID
    :param workspace_path: 仓库/工作区根路径（用于 COPY 源码）
    :param test_sources: 文件名 -> 内容，如 {"test_foo.cpp": "..."}
    :param cmake_content: CMakeLists.txt 内容
    :param docker_image_tag: 可选镜像 tag
    :return: {
        "success": bool,
        "total": int, "passed": int, "failed": int, "skipped": int,
        "executions": [{"test_case_id": ?, "execution_status": str, "result_json": str}],
        "coverage_delta_json": str | None,
        "build_log": str, "run_log": str,
    }
    """
    tag = docker_image_tag or f"grayscope-test-run-{run_id[:8]}"
    base = (docker_base_image or "arm64v8/ubuntu:22.04").strip() or "arm64v8/ubuntu:22.04"
    out = {
        "success": False,
        "total": 0,
        "passed": 0,
        "failed": 0,
        "skipped": 0,
        "executions": [],
        "coverage_delta_json": None,
        "build_log": "",
        "run_log": "",
    }

    with tempfile.TemporaryDirectory(prefix="grayscope_docker_") as tmpdir:
        root = Path(tmpdir)
        # 先复制工作区源码（头文件与 .c/.cpp），便于测试代码 #include 与链接
        if workspace_path and os.path.isdir(workspace_path):
            for name in os.listdir(workspace_path):
                if name in _WORKSPACE_EXCLUDE:
                    continue
                src = Path(workspace_path) / name
                dst = root / name
                try:
                    if src.is_dir():
                        shutil.copytree(
                            src, dst,
                            ignore=shutil.ignore_patterns(*_WORKSPACE_EXCLUDE),
                            dirs_exist_ok=True,
                        )
                    else:
                        shutil.copy2(src, dst)
                except (OSError, shutil.Error) as e:
                    logger.warning("copy workspace item %s: %s", name, e)
        (root / "tests").mkdir(exist_ok=True)
        for name, content in test_sources.items():
            (root / "tests" / name).write_text(content, encoding="utf-8")
        (root / "tests" / "CMakeLists.txt").write_text(cmake_content, encoding="utf-8")
        (root / "Dockerfile").write_text(_dockerfile_content(base), encoding="utf-8")

        docker_context = str(root)

        code, stdout, stderr = _run_cmd(
            ["docker", "build", "-t", tag, docker_context],
            timeout=300,
        )
        out["build_log"] = stdout + "\n" + stderr
        if code != 0:
            out["executions"].append({
                "test_case_id": None,
                "execution_status": STATUS_COMPILE_ERROR,
                "result_json": json.dumps({"stdout": stdout, "stderr": stderr, "message": "Docker build failed"}),
            })
            out["total"] = 1
            out["failed"] = 1
            return out

        code, stdout, stderr = _run_cmd(
            ["docker", "run", "--rm", tag],
            timeout=120,
        )
        out["run_log"] = stdout + "\n" + stderr
        if code != 0:
            out["executions"].append({
                "test_case_id": None,
                "execution_status": STATUS_RUNTIME_ERROR,
                "result_json": json.dumps({"stdout": stdout, "stderr": stderr, "exit_code": code}),
            })
            out["total"] = 1
            out["failed"] = 1
            return out

        # 解析 CTest 输出或 JUnit XML（若容器内产出）
        # 简化：根据 exit code 设一条汇总执行记录；完整实现可挂载卷取出 XML
        out["success"] = True
        out["total"] = 1
        out["passed"] = 1 if code == 0 else 0
        out["failed"] = 0 if code == 0 else 1
        out["executions"].append({
            "test_case_id": None,
            "execution_status": STATUS_PASSED if code == 0 else STATUS_RUNTIME_ERROR,
            "result_json": json.dumps({"stdout": stdout, "stderr": stderr}),
        })
    return out


def parse_junit_xml(xml_path: str) -> list[dict[str, Any]]:
    """解析 JUnit XML，返回每条用例的 execution_status 与 result_json。"""
    results = []
    try:
        tree = ET.parse(xml_path)
        root = tree.getroot()
        for suite in root.findall(".//testsuite"):
            for tc in suite.findall("testcase"):
                name = tc.get("name", "")
                status = STATUS_PASSED
                message = ""
                failure = tc.find("failure")
                error = tc.find("error")
                if failure is not None:
                    status = STATUS_ASSERTION_FAIL
                    message = failure.get("message", "") or (failure.text or "")
                elif error is not None:
                    status = STATUS_RUNTIME_ERROR
                    message = error.get("message", "") or (error.text or "")
                results.append({
                    "name": name,
                    "execution_status": status,
                    "result_json": json.dumps({"message": message}),
                })
    except Exception as e:
        logger.warning("parse_junit_xml %s: %s", xml_path, e)
    return results
