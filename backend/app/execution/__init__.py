"""测试执行引擎（V2）。"""

from app.execution.ssh_manager import SSHManager
from app.execution.scheduler import schedule_test_run
from app.execution.docker_executor import build_and_run, parse_junit_xml
from app.execution.ssh_executor import run_via_ssh

__all__ = [
    "SSHManager",
    "schedule_test_run",
    "build_and_run",
    "parse_junit_xml",
    "run_via_ssh",
]
