"""AI 增强分析服务（增强版）。

对静态分析结果进行 AI 增强处理，生成测试建议、风险解释和结构化测试用例。
增强: 支持跨模块上下文、调用链信息、数据流路径传入 AI 提示词。
支持 synthesize_cross_module() 进行全局综合分析。
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
    "data_flow": "data_flow_analysis",
}


async def _call_model_async(
    provider_name: str,
    model: str,
    messages: list[dict[str, str]],
    *,
    api_key: str | None = None,
    base_url: str | None = None,
) -> dict:
    """异步调用 AI 模型并返回解析后的响应。
    
    当显式传入 api_key/base_url 时，会使用这些值而非 settings 中的默认值。
    """
    provider_kwargs: dict[str, Any] = {"model": model}
    if api_key is not None:
        provider_kwargs["api_key"] = api_key
    if base_url is not None:
        provider_kwargs["base_url"] = base_url.rstrip("/")
    
    provider = get_provider(provider_name, **provider_kwargs)
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
    *,
    api_key: str | None = None,
    base_url: str | None = None,
) -> dict:
    """同步调用 AI 模型。"""
    try:
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(
                _call_model_async(
                    provider_name, model, messages,
                    api_key=api_key, base_url=base_url,
                )
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


def _build_cross_context(
    module_id: str,
    findings: list[dict[str, Any]],
    upstream_results: dict[str, dict] | None = None,
) -> dict[str, str]:
    """构建跨模块上下文信息，传入 AI 提示词模板。"""
    context: dict[str, str] = {}

    if not upstream_results:
        return context

    # 调用链上下文
    call_chain_parts = []
    cg_data = upstream_results.get("call_graph", {})
    for finding in cg_data.get("findings", [])[:5]:
        ev = finding.get("evidence", {})
        sym = finding.get("symbol_name", "")
        if ev.get("callees"):
            call_chain_parts.append(f"  {sym}() 调用: {', '.join(ev['callees'][:5])}")
        if ev.get("callers"):
            call_chain_parts.append(f"  {sym}() 被调用: {', '.join(ev['callers'][:5])}")
        if ev.get("caller_chains"):
            for chain in ev["caller_chains"][:2]:
                call_chain_parts.append(f"  调用链: {' → '.join(chain)}")

    if call_chain_parts:
        context["call_chain_context"] = "\n".join(call_chain_parts[:10])

    # 数据流路径
    df_parts = []
    df_data = upstream_results.get("data_flow", {})
    for finding in df_data.get("findings", [])[:5]:
        ev = finding.get("evidence", {})
        chain = ev.get("propagation_chain", [])
        if chain:
            path_str = " → ".join(
                f"{s['function']}({s['param']})" for s in chain[:6]
            )
            external = "外部输入" if ev.get("is_external_input") else "内部"
            df_parts.append(f"  [{external}] {path_str}")
            if ev.get("sensitive_ops"):
                df_parts.append(f"    到达敏感操作: {', '.join(ev['sensitive_ops'])}")

    if df_parts:
        context["data_flow_paths"] = "\n".join(df_parts[:10])

    # 跨模块发现
    cross_parts = []
    for mod_id, mod_data in upstream_results.items():
        if mod_id == module_id:
            continue
        mod_findings = mod_data.get("findings", [])
        high_risk = [f for f in mod_findings if f.get("risk_score", 0) > 0.7]
        if high_risk:
            mod_name = get_display_name(mod_id)
            for f in high_risk[:3]:
                cross_parts.append(
                    f"  [{mod_name}] {f.get('title', '')} (风险={f.get('risk_score', 0):.0%})"
                )

    if cross_parts:
        context["cross_module_findings"] = "\n".join(cross_parts[:10])

    return context


def enrich_module(
    module_id: str,
    findings: list[dict[str, Any]],
    source_snippets: dict[str, str],
    ai_config: dict,
    upstream_results: dict[str, dict] | None = None,
) -> dict:
    """对分析发现进行 AI 增强处理（增强版 —— 含跨模块上下文）。

    参数
    ----------
    module_id : str
        分析器模块标识
    findings : list
        静态分析器产出的原始发现列表
    source_snippets : dict
        {函数名: 源代码} 上下文信息
    ai_config : dict
        {"provider": "...", "model": "...", "prompt_profile": "..."}
    upstream_results : dict, optional
        所有上游模块的分析结果（用于构建跨模块上下文）

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
    api_key = ai_config.get("api_key")
    base_url = ai_config.get("base_url")

    # 从最高风险的发现中构建上下文
    top_findings = findings[:10]
    findings_text = json.dumps(top_findings, indent=2, ensure_ascii=False)

    # 选取代表性的源代码片段
    snippet_text = ""
    for fn_name, src in list(source_snippets.items())[:3]:
        snippet_text += f"\n// --- {fn_name} ---\n{src[:2000]}\n"

    # 构建跨模块上下文
    cross_context = _build_cross_context(module_id, findings, upstream_results)

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
        # 新增: 跨模块上下文变量
        "call_chain_context": cross_context.get("call_chain_context", ""),
        "data_flow_paths": cross_context.get("data_flow_paths", ""),
        "cross_module_findings": cross_context.get("cross_module_findings", ""),
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
            "基于这些发现和上面的调用链/数据流上下文，请提供:\n"
            "1. 风险摘要（特别注意跨函数的风险传播）\n"
            "2. 针对最高风险项的具体端到端测试用例建议（从入口函数开始）\n"
            "3. 静态分析未覆盖的其他风险区域\n"
            "请以 JSON 格式返回。"
        ),
    })

    # 调用 AI 模型
    logger.info("正在调用 AI 模型: %s/%s (消息数=%d)", provider_name, model, len(messages))
    ai_result = _call_model_sync(
        provider_name, model, messages,
        api_key=api_key, base_url=base_url,
    )

    # 解析 AI 响应
    ai_content = ai_result.get("content", "")
    test_suggestions = _extract_test_suggestions(ai_content)

    if not ai_result.get("success"):
        err_msg = ai_result.get("error", "未知错误")
        logger.warning("AI 调用失败 [%s]: %s", display_name, err_msg)
        return {
            "ai_summary": f"{display_name} AI 增强不可用: {err_msg}",
            "test_suggestions": [],
            "enriched_findings": findings,
            "success": False,
            "error": err_msg,
            "usage": ai_result.get("usage", {}),
            "provider": provider_name,
            "model": model,
        }

    logger.info("AI 调用成功 [%s]: 响应长度=%d", display_name, len(ai_content))
    return {
        "ai_summary": ai_content[:5000] if ai_content else f"{display_name} AI 增强不可用",
        "test_suggestions": test_suggestions,
        "enriched_findings": findings,
        "success": True,
        "usage": ai_result.get("usage", {}),
        "provider": provider_name,
        "model": model,
    }


def synthesize_cross_module(
    all_module_results: dict[str, dict],
    source_snippets: dict[str, str],
    ai_config: dict,
    candidate_combinations: list[dict] | None = None,
) -> dict:
    """跨模块综合分析: 结合所有分析器的发现，生成全局视角的测试建议。

    在所有模块完成后调用，提供跨模块关联分析和端到端测试建议。
    若传入 candidate_combinations（静态交汇候选），将纳入提示由 AI 排序/补全，并合并入最终 test_suggestions。
    """
    provider_name = ai_config.get("provider", "ollama")
    model = ai_config.get("model", "qwen2.5-coder")
    api_key = ai_config.get("api_key")
    base_url = ai_config.get("base_url")

    if not provider_name or provider_name.lower() in ("none", "", "skip"):
        return {
            "ai_summary": "未启用 AI 增强",
            "test_suggestions": [],
            "success": False,
            "skipped": True,
        }

    # 汇总所有模块的高风险发现
    all_high_risk: list[dict] = []
    module_summaries: list[str] = []

    for mod_id, mod_data in all_module_results.items():
        mod_findings = mod_data.get("findings", [])
        mod_risk = mod_data.get("risk_score", 0.0)
        high_risk = sorted(
            [f for f in mod_findings if f.get("risk_score", 0) > 0.6],
            key=lambda f: f.get("risk_score", 0),
            reverse=True,
        )[:5]
        all_high_risk.extend(high_risk)

        mod_name = get_display_name(mod_id)
        module_summaries.append(
            f"- {mod_name}: 风险={mod_risk:.0%}, 发现数={len(mod_findings)}, "
            f"高风险={len(high_risk)}"
        )

    # 提取数据流传播链
    df_chains = []
    df_data = all_module_results.get("data_flow", {})
    for finding in df_data.get("findings", [])[:10]:
        ev = finding.get("evidence", {})
        chain = ev.get("propagation_chain", [])
        if chain:
            path_str = " → ".join(f"{s['function']}({s['param']})" for s in chain[:8])
            df_chains.append({
                "path": path_str,
                "external": ev.get("is_external_input", False),
                "sensitive": ev.get("sensitive_ops", []),
            })

    # 构建综合提示（灰盒核心：多函数交汇临界点）
    system_msg = (
        "你是一个灰盒测试分析专家。灰盒测试的核心价值是：**精准找到多个函数（或故障处理分支）交汇的临界点**，"
        "用一次设计好的测试用例暴露黑盒需要 N 次才能撞出的问题。\n"
        "例如：iSCSI login 时若叠加「端口闪断」或「网卡下电」（代码里各有对应处理函数），预期失败是「建联失败」；"
        "但若出现「控制器下电」「进程崩溃」则为不可接受。灰盒要找出 login、端口闪断处理、网卡下电处理 等函数交汇的临界点。\n\n"
        "你需要:\n"
        "1. **多函数交汇临界点**：从调用图+错误路径+数据流中，找出 2 个或 3 个及以上函数/分支交汇的场景，"
        "标明 related_functions、expected_failure（可接受的失败）、unacceptable_outcomes（不可接受结果）\n"
        "2. 关联不同分析器的发现，发现单模块无法看到的组合风险\n"
        "3. 基于数据流传播链，设计从入口到风险点的端到端测试场景\n"
        "4. 输出 JSON，必须包含 critical_combinations: [{ related_functions: [], expected_failure: '', unacceptable_outcomes: [] }]"
    )

    # 按风险排序 top findings
    all_high_risk.sort(key=lambda f: f.get("risk_score", 0), reverse=True)
    top_findings_text = json.dumps(all_high_risk[:15], indent=2, ensure_ascii=False)

    chains_text = "\n".join(
        f"  {'[外部输入]' if c['external'] else '[内部]'} {c['path']}"
        + (f" → 敏感操作: {', '.join(c['sensitive'])}" if c['sensitive'] else "")
        for c in df_chains
    )

    user_msg = (
        f"以下是对一个代码库的多维度静态分析结果综合:\n\n"
        f"**模块分析概要:**\n" + "\n".join(module_summaries) + "\n\n"
        f"**数据流传播链（参数如何跨函数传播）:**\n{chains_text}\n\n"
        f"**所有高风险发现（跨模块汇总，按风险排序）:**\n{top_findings_text[:4000]}\n\n"
    )
    if candidate_combinations:
        candidates_text = json.dumps(
            [{"related_functions": c.get("related_functions"), "finding_ids": c.get("finding_ids", []), "source": c.get("source", "")} for c in candidate_combinations[:30]],
            indent=2,
            ensure_ascii=False,
        )
        user_msg += (
            f"**静态交汇候选（基于调用图与发现图计算，请在此基础上排序、合并、补全 expected_outcome / unacceptable_outcomes / scenario_brief）:**\n{candidates_text[:3000]}\n\n"
        )
    user_msg += "**代码片段:**\n"

    for fn_name, src in list(source_snippets.items())[:3]:
        user_msg += f"\n// --- {fn_name} ---\n{src[:1500]}\n"

    user_msg += (
        "\n\n请以 JSON 格式返回，且必须包含:\n"
        "1. **critical_combinations** (数组): 多函数交汇临界点。每项含:\n"
        "   - related_functions: [\"函数A\", \"函数B\", \"函数C\"] 交汇的 2～3 个函数或故障处理分支\n"
        "   - expected_outcome: 预期结果（可成功或可接受失败）。例如「按规格成功完成」或「建联失败、返回错误码」\n"
        "   - expected_failure: （可选）仅当预期为可接受失败时填写，如「建联失败」\n"
        "   - unacceptable_outcomes: [\"不可接受结果1\", \"不可接受结果2\"] 如「控制器下电」「进程崩溃」\n"
        "   - scenario_brief: 一句话场景描述\n"
        "   - performance_requirement: （可选）性能/时序要求，如「响应时间 < 100ms」「IO 延迟 < 5ms」\n"
        "2. **cross_module_risks**: 跨模块风险关联\n"
        "3. **e2e_test_scenarios**: 端到端测试方案（含输入、路径、预期）\n"
        "4. **methodology_advice**: 灰盒测试改进建议\n\n"
        "返回格式: { critical_combinations, cross_module_risks, e2e_test_scenarios, methodology_advice }"
    )

    messages = [
        {"role": "system", "content": system_msg},
        {"role": "user", "content": user_msg},
    ]

    logger.info("正在执行跨模块 AI 综合分析: %s/%s", provider_name, model)
    ai_result = _call_model_sync(
        provider_name, model, messages,
        api_key=api_key, base_url=base_url,
    )

    ai_content = ai_result.get("content", "")
    test_suggestions = _extract_test_suggestions(ai_content)
    test_suggestions = _merge_static_candidates_into_suggestions(
        test_suggestions, candidate_combinations or []
    )

    if not ai_result.get("success"):
        err_msg = ai_result.get("error", "未知错误")
        return {
            "ai_summary": f"跨模块综合分析失败: {err_msg}",
            "test_suggestions": test_suggestions,
            "success": False,
            "error": err_msg,
            "usage": ai_result.get("usage", {}),
            "provider": provider_name,
            "model": model,
        }

    return {
        "ai_summary": ai_content[:8000] if ai_content else "跨模块综合分析不可用",
        "test_suggestions": test_suggestions,
        "success": True,
        "usage": ai_result.get("usage", {}),
        "provider": provider_name,
        "model": model,
    }


def _merge_static_candidates_into_suggestions(
    test_suggestions: list[dict],
    candidate_combinations: list[dict],
) -> list[dict]:
    """将静态交汇候选合并入 test_suggestions；AI 已返回同 related_functions 的不重复添加。"""
    if not candidate_combinations:
        return test_suggestions
    key_from_suggestion = lambda s: tuple(sorted(s.get("related_functions") or []))
    ai_keys = {key_from_suggestion(s) for s in test_suggestions if key_from_suggestion(s)}
    out = list(test_suggestions)
    for c in candidate_combinations:
        related = c.get("related_functions") or []
        if len(related) < 2:
            continue
        key = tuple(sorted(related))
        if key in ai_keys:
            continue
        ai_keys.add(key)
        out.append({
            "type": "critical_combination",
            "related_functions": related,
            "expected_outcome": c.get("expected_outcome") or "",
            "expected_failure": c.get("expected_failure") or "",
            "unacceptable_outcomes": c.get("unacceptable_outcomes") or [],
            "scenario_brief": c.get("scenario_brief") or "",
            "finding_ids": c.get("finding_ids", []),
            "source": c.get("source", "static"),
        })
    return out


def _extract_test_suggestions(ai_content: str) -> list[dict]:
    """从 AI 响应中提取结构化测试建议，并合并 critical_combinations 为灰盒场景。"""
    if not ai_content:
        return []

    try:
        data = json.loads(ai_content)
        if isinstance(data, list):
            return data
        if not isinstance(data, dict):
            return []

        out: list[dict] = []
        for item in data.get("critical_combinations") or []:
            if isinstance(item, dict) and (item.get("related_functions") or item.get("scenario_brief")):
                out.append({
                    "type": "critical_combination",
                    "related_functions": item.get("related_functions", []),
                    "expected_outcome": item.get("expected_outcome") or item.get("expected_failure", ""),
                    "expected_failure": item.get("expected_failure", ""),
                    "unacceptable_outcomes": item.get("unacceptable_outcomes", []),
                    "scenario_brief": item.get("scenario_brief", ""),
                    **{k: v for k, v in item.items() if k not in ("related_functions", "expected_outcome", "expected_failure", "unacceptable_outcomes", "scenario_brief")},
                })
        _KNOWN_KEYS = ("e2e_test_scenarios", "test_suggestions", "tests",
                       "test_cases", "test_scenarios", "branches", "regression_tests")
        for key in _KNOWN_KEYS:
            if key in data and isinstance(data[key], list):
                for x in data[key]:
                    if isinstance(x, dict) and x not in out:
                        out.append(x)
        if out:
            return out
        return [data]
    except json.JSONDecodeError:
        pass
    return [{"type": "raw_text", "content": ai_content[:3000]}]
