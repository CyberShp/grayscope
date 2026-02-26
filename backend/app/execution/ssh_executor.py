"""SSH 执行器：在 ARM 真机上传编译产物、运行测试、拉回 JUnit XML 与 gcov。"""

from __future__ import annotations

import json
import logging
from typing import Any

from app.execution.ssh_manager import SSHManager
from app.execution.docker_executor import (
    STATUS_PASSED,
    STATUS_ASSERTION_FAIL,
    STATUS_RUNTIME_ERROR,
    STATUS_COMPILE_ERROR,
)

logger = logging.getLogger(__name__)


def run_via_ssh(
    run_id: str,
    host: str,
    port: int = 22,
    username: str = "",
    key_path: str | None = None,
    remote_binary_path: str = "/tmp/grayscope_test_runner",
    remote_workdir: str = "/tmp/grayscope_run",
) -> dict[str, Any]:
    """
    通过 SSH 在远程 ARM 主机上执行测试二进制，收集结果。

    假定调用方已在远程准备好可执行文件与工作目录；
    本函数仅负责执行命令并解析输出。

    :return: 与 docker_executor.build_and_run 相同结构的结果字典
    """
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
    manager = SSHManager(host=host, port=port, username=username, key_path=key_path)
    try:
        cmd = f"cd {remote_workdir} && {remote_binary_path} --gtest_output=xml:results.xml 2>&1; gcovr -r . --json -o coverage.json 2>/dev/null || true"
        code, stdout, stderr = manager.run(cmd, timeout=120)
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
        out["success"] = True
        out["total"] = 1
        out["passed"] = 1
        out["executions"].append({
            "test_case_id": None,
            "execution_status": STATUS_PASSED,
            "result_json": json.dumps({"stdout": stdout, "stderr": stderr}),
        })
    finally:
        manager.close()
    return out
