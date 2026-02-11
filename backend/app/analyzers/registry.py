"""分析器模块注册表。

集中管理所有分析器模块的元信息，包括内部标识、中文显示名称、描述等。
所有模块引用应通过此注册表获取模块信息，避免硬编码。
"""

from __future__ import annotations

from typing import Any


# ── 模块注册表 ──────────────────────────────────────────────────────────
# 每个模块的内部 ID 使用描述性英文标识（而非 M01/M02 等缩写）

MODULE_REGISTRY: dict[str, dict[str, Any]] = {
    "branch_path": {
        "display_name": "分支路径分析",
        "description": "识别代码中的条件分支（if/else/switch/goto），分类为错误/清理/边界/正常路径，发现未覆盖的分支",
        "category": "静态分析",
    },
    "boundary_value": {
        "display_name": "边界值分析",
        "description": "提取比较表达式和数组访问，推导边界测试候选值（边界值、等价类划分）",
        "category": "静态分析",
    },
    "error_path": {
        "display_name": "错误路径分析",
        "description": "识别资源分配/释放模式、goto清理路径、错误返回值一致性，发现资源泄漏和错误处理缺陷",
        "category": "静态分析",
    },
    "call_graph": {
        "display_name": "调用图构建",
        "description": "构建函数级有向调用图，识别高扇出/扇入函数，分析函数间依赖关系",
        "category": "静态分析",
    },
    "concurrency": {
        "display_name": "并发风险分析",
        "description": "检测共享变量无锁写入、锁序反转死锁风险、未释放的锁等并发安全问题",
        "category": "静态分析",
    },
    "diff_impact": {
        "display_name": "差异影响分析",
        "description": "解析 git diff 输出，映射变更到函数，利用调用图传播影响，识别回归风险区域",
        "category": "变更分析",
    },
    "coverage_map": {
        "display_name": "覆盖率映射",
        "description": "加载代码覆盖率数据（LCOV/JSON），叠加上游风险发现，标记「高风险低覆盖」区域",
        "category": "覆盖分析",
    },
    "postmortem": {
        "display_name": "事后分析",
        "description": "分析逃逸缺陷元数据，关联上游分析发现，推断根因链，生成预防性测试建议",
        "category": "反馈闭环",
    },
    "knowledge_pattern": {
        "display_name": "缺陷知识库",
        "description": "从事后分析结果中提取可复用的缺陷模式，归一化存储，支持相似度匹配",
        "category": "反馈闭环",
    },
}

# ── 分析任务支持的模块集合（不含事后分析模块） ──────────────────────────
ANALYSIS_MODULES = [
    "branch_path", "boundary_value", "error_path", "call_graph",
    "concurrency", "diff_impact", "coverage_map",
]

# ── 事后分析模块 ──────────────────────────────────────────────────────
POSTMORTEM_MODULES = ["postmortem", "knowledge_pattern"]

# ── 所有模块 ──────────────────────────────────────────────────────────
ALL_MODULES = ANALYSIS_MODULES + POSTMORTEM_MODULES


def get_display_name(module_id: str) -> str:
    """获取模块的中文显示名称。"""
    info = MODULE_REGISTRY.get(module_id)
    return info["display_name"] if info else module_id


def get_description(module_id: str) -> str:
    """获取模块的描述信息。"""
    info = MODULE_REGISTRY.get(module_id)
    return info["description"] if info else ""


def get_all_display_names() -> dict[str, str]:
    """返回所有模块的 {module_id: display_name} 映射。"""
    return {mid: info["display_name"] for mid, info in MODULE_REGISTRY.items()}
