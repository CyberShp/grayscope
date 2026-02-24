"""SSH 连接与命令执行（占位，后续实现）。"""

from __future__ import annotations


class SSHManager:
    """管理 SSH 连接池与远程命令执行。"""

    def __init__(self, host: str, port: int = 22, username: str = "", key_path: str | None = None):
        self.host = host
        self.port = port
        self.username = username
        self.key_path = key_path

    def run(self, command: str, timeout: int = 60) -> tuple[int, str, str]:
        """执行远程命令，返回 (exit_code, stdout, stderr)。占位返回 (-1, '', '未实现')。"""
        return (-1, "", "未实现")

    def close(self) -> None:
        """关闭连接。"""
        pass
