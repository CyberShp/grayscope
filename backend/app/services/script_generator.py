"""测试脚本生成器：从测试用例生成可执行的 Python 测试脚本。"""

from __future__ import annotations

import json
from typing import Any


def generate_python_script(test_case: dict[str, Any]) -> str:
    """根据用例生成 Python 测试脚本内容（兼容自研框架风格）。"""
    title = test_case.get("title") or "未命名用例"
    steps = test_case.get("test_steps")
    if isinstance(test_case.get("steps_json"), str):
        try:
            steps = json.loads(test_case["steps_json"])
        except (TypeError, json.JSONDecodeError):
            steps = []
    if not steps and isinstance(test_case.get("preconditions"), list):
        steps = []
    if not steps:
        steps = [f"执行与 {title} 相关的测试步骤"]
    expected = test_case.get("expected") or test_case.get("expected_result") or "通过"
    if isinstance(expected, list):
        expected = "\n".join(str(x) for x in expected)
    priority = (test_case.get("priority") or "P3").split("-")[0]
    lines = [
        '"""',
        f"用例: {title}",
        f"优先级: {priority}",
        '"""',
        "",
        "def test_case():",
        "    # 前置条件与步骤",
    ]
    for i, step in enumerate(steps, 1):
        lines.append(f'    # {i}. {step}')
    lines.extend([
        "    # 预期结果",
        f'    # {expected}',
        "    pass  # 请在此实现断言与调用",
        "",
    ])
    return "\n".join(lines)
