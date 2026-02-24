"""测试执行引擎（V2）。"""

from app.execution.ssh_manager import SSHManager
from app.execution.scheduler import schedule_test_run

__all__ = ["SSHManager", "schedule_test_run"]
