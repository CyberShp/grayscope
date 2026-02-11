"""AI 增强分析服务。

对静态分析结果进行 AI 增强处理，生成测试建议、风险解释和结构化测试用例。
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from app.ai import prompt_engine
from app.ai.provider_registry import get_provider
from app.analyzers.registry import get_display_name

logger = logging.getLogger(__name__)

# ── 模块 → 提示词模板映射 ──────────────────────────────────────────────
_MODULE_TEMPLATES: dict[str, str] = {
    "branch_path": "branch_path_analysis",
    "boundary_value": "boundary_value_analysis",
    "error_path": "error_path_analysis",
    "concurrency": "concurrency_analysis",
    "diff_impact": "diff_impact_analysis",
}


async def _call_model_async(
    provider_name: str,
    model: str,
    messages: list[dict[str, str]],
) -> dict:
    """异步调用 AI 模型并返回解析后的响应。"""
    provider = get_provider(provider_name, model=model)
    try:
        result = await provider.chat(messages, model=model)
        return {
            "content": result.get("content", ""),
            "usage": result.get("usage", {}),
            "success": True,
        }
    except Exception as exc:
        logger.warning("AI 调用失败 (%s/%s): %s", provider_name, model, exc)
        return {
            "content": "",
            "usage": {},
            "success": False,
            "error": str(exc),
        }


def _call_model_sync(
    provider_name: str,
    model: str,
    messages: list[dict[str, str]],
) -> dict:
    """同步调用 AI 模型（适用于工作线程中无事件循环的场景）。

    创建新的事件循环，因为 FastAPI 工作线程没有运行中的事件循环。
    """
    try:
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(
                _call_model_async(provider_name, model, messages)
            )
        finally:
            loop.close()
    except Exception as exc:
        logger.warning("AI 同步调用失败 (%s/%s): %s", provider_name, model, exc)
        return {
            "content": "",
            "usage": {},
            "success": False,
            "error": str(exc),
        }


def enrich_module(
    module_id: str,
    findings: list[dict[str, Any]],
    source_snippets: dict[str, str],
    ai_config: dict,
) -> dict:
    """对分析发现进行 AI 增强处理。

    参数
    ----------
    module_id : str
        分析器模块标识（如 branch_path、boundary_value 等）
    findings : list
        静态分析器产出的原始发现列表
    source_snippets : dict
        {函数名: 源代码} 上下文信息
    ai_config : dict
        {"provider": "...", "model": "...", "prompt_profile": "..."}

    返回
    -------
    dict，包含: ai_summary, test_suggestions, enriched_findings
    """
    display_name = get_display_name(module_id)
    template_id = _MODULE_TEMPLATES.get(module_id)
    if not template_id:
        return {
            "ai_summary": f"{display_name}暂无对应的提示词模板",
            "test_suggestions": [],
            "enriched_findings": findings,
            "success": False,
        }

    provider_name = ai_config.get("provider", "ollama")
    model = ai_config.get("model", "qwen2.5-coder")

    # 从最高风险的发现中构建上下文（限制数量避免超出 token 限制）
    top_findings = findings[:10]
    findings_text = json.dumps(top_findings, indent=2, ensure_ascii=False)

    # 选取代表性的源代码片段
    snippet_text = ""
    for fn_name, src in list(source_snippets.items())[:3]:
        snippet_text += f"\n// --- {fn_name} ---\n{src[:2000]}\n"

    # 构建提示词变量
    variables: dict[str, Any] = {
        "function_name": top_findings[0].get("symbol_name", "unknown") if top_findings else "unknown",
        "source_code": snippet_text[:4000],
        "cfg_summary": f"静态分析产出 {len(findings)} 条发现",
        "module_path": "",
        "shared_vars": "",
        "lock_usage": "",
        "changed_files": "",
        "changed_symbols": "",
        "diff_text": "",
        "depth": 2,
        "impacted_symbols": "",
    }

    try:
        messages = prompt_engine.render(template_id, variables)
    except Exception as exc:
        logger.warning("提示词渲染失败 [%s]: %s", display_name, exc)
        return {
            "ai_summary": f"提示词渲染失败: {exc}",
            "test_suggestions": [],
            "enriched_findings": findings,
            "success": False,
        }

    # 追加发现上下文作为后续用户消息
    messages.append({
        "role": "user",
        "content": (
            f"静态分析产出 {len(findings)} 条发现:\n"
            f"{findings_text[:3000]}\n\n"
            "基于这些发现，请提供:\n"
            "1. 风险摘要\n"
            "2. 针对最高风险项的具体测试用例建议\n"
            "3. 静态分析未覆盖的其他风险区域\n"
            "请以 JSON 格式返回。"
        ),
    })

    # 调用 AI 模型（同步封装，适用于工作线程）
    ai_result = _call_model_sync(provider_name, model, messages)

    # 解析 AI 响应
    ai_content = ai_result.get("content", "")
    test_suggestions = _extract_test_suggestions(ai_content)

    return {
        "ai_summary": ai_content[:5000] if ai_content else f"{display_name} AI 增强不可用",
        "test_suggestions": test_suggestions,
        "enriched_findings": findings,
        "success": ai_result.get("success", False),
        "usage": ai_result.get("usage", {}),
        "provider": provider_name,
        "model": model,
    }


def _extract_test_suggestions(ai_content: str) -> list[dict]:
    """尝试从 AI 响应中提取结构化的测试建议。"""
    if not ai_content:
        return []

    # 尝试 JSON 解析
    try:
        data = json.loads(ai_content)
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            for key in ("test_suggestions", "tests", "test_cases", "branches"):
                if key in data and isinstance(data[key], list):
                    return data[key]
            return [data]
    except json.JSONDecodeError:
        pass

    # 降级处理：返回原始文本块
    return [{"type": "raw_text", "content": ai_content[:3000]}]
