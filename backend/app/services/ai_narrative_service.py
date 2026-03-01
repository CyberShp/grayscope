"""AI Narrative Service for code analysis.

Transforms technical analysis results into business-friendly narratives,
risk scenario cards, function dictionaries, What-If scenarios, and test
design matrices using AI-powered prompt templates.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from collections.abc import Callable
from typing import Any

import httpx

from app.ai.prompt_templates import render_prompt
from app.ai.provider_registry import get_provider

logger = logging.getLogger(__name__)

# 可重试的 HTTP 状态码
_RETRYABLE_STATUS_CODES = {429, 502, 503, 504}

# 全局 AI 调用并发控制 - 避免触发 API 限流
_GLOBAL_AI_SEMAPHORE: asyncio.Semaphore | None = None
_SEMAPHORE_LOOP_ID: int | None = None


def _get_global_semaphore(max_concurrent: int = 8) -> asyncio.Semaphore:
    """获取或创建全局 AI 调用 semaphore.
    
    Note: asyncio.Semaphore is bound to the event loop at creation time.
    If we detect we're in a different loop, we recreate the semaphore.
    """
    global _GLOBAL_AI_SEMAPHORE, _SEMAPHORE_LOOP_ID
    
    try:
        loop = asyncio.get_running_loop()
        current_loop_id = id(loop)
    except RuntimeError:
        # No running loop - return existing or create new
        current_loop_id = None
    
    # Recreate semaphore if loop changed or doesn't exist
    if _GLOBAL_AI_SEMAPHORE is None or (current_loop_id and _SEMAPHORE_LOOP_ID != current_loop_id):
        _GLOBAL_AI_SEMAPHORE = asyncio.Semaphore(max_concurrent)
        _SEMAPHORE_LOOP_ID = current_loop_id
    
    return _GLOBAL_AI_SEMAPHORE


def _flatten_lock_sequence(lock_sequence: list[list[str]] | list[str]) -> list[str]:
    """Flatten lock sequence to unique lock names.
    
    lock_sequence is typically list[list[str]] where each inner list
    represents locks held at each step. This flattens and deduplicates.
    """
    if not lock_sequence:
        return []
    result = []
    seen = set()
    for item in lock_sequence:
        if isinstance(item, list):
            for lock in item:
                if lock and lock not in seen:
                    result.append(str(lock))
                    seen.add(lock)
        elif item and item not in seen:
            result.append(str(item))
            seen.add(item)
    return result


def _extract_json_multilayer(content: str) -> dict[str, Any]:
    """多层 JSON 提取 fallback
    
    层级:
    1. 标准 json.loads()
    2. 提取 ```json ... ``` 代码块
    3. 正则提取最外层 {...} 或 [...]
    4. 去除干扰后再解析
    5. 返回 raw_content
    """
    if not content or not content.strip():
        return {"error": "empty_content", "raw_content": ""}
    
    # Layer 1: 直接解析
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        pass
    
    # Layer 2: 提取 ```json 代码块
    if "```json" in content:
        start = content.find("```json") + 7
        end = content.find("```", start)
        if end > start:
            try:
                return json.loads(content[start:end].strip())
            except json.JSONDecodeError:
                pass
    
    # Layer 2b: 提取 ``` 代码块
    if "```" in content:
        start = content.find("```") + 3
        # 跳过语言标识符行
        newline_pos = content.find("\n", start)
        if newline_pos > start:
            start = newline_pos + 1
        end = content.find("```", start)
        if end > start:
            try:
                return json.loads(content[start:end].strip())
            except json.JSONDecodeError:
                pass
    
    # Layer 3: 正则提取最外层 JSON 对象或数组
    # 匹配 {...} 
    obj_match = re.search(r"\{[\s\S]*\}", content)
    if obj_match:
        try:
            return json.loads(obj_match.group())
        except json.JSONDecodeError:
            pass
    
    # 匹配 [...]
    arr_match = re.search(r"\[[\s\S]*\]", content)
    if arr_match:
        try:
            parsed = json.loads(arr_match.group())
            return {"items": parsed} if isinstance(parsed, list) else parsed
        except json.JSONDecodeError:
            pass
    
    # Layer 4: 清理干扰后再解析
    cleaned = content
    # 去除 BOM
    cleaned = cleaned.lstrip("\ufeff")
    # 去除单行注释
    cleaned = re.sub(r"//[^\n]*", "", cleaned)
    # 去除尾部逗号
    cleaned = re.sub(r",(\s*[}\]])", r"\1", cleaned)
    
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass
    
    # Layer 5: 返回原始内容
    return {"raw_content": content, "parse_error": "all_layers_failed"}


async def _call_ai(
    provider_name: str,
    model: str,
    system_prompt: str,
    user_prompt: str,
    *,
    api_key: str | None = None,
    base_url: str | None = None,
    temperature: float = 0.3,
    max_tokens: int = 4096,
    max_retries: int = 3,
    use_global_semaphore: bool = True,
) -> dict[str, Any]:
    """Call AI model and parse JSON response with retry and fallback.
    
    实现指数退避重试和多层 JSON 解析 fallback。
    使用全局 semaphore 控制并发，避免触发 API 限流。
    """
    semaphore = _get_global_semaphore() if use_global_semaphore else None
    
    async def _do_call() -> dict[str, Any]:
        provider_kwargs: dict[str, Any] = {"model": model}
        if api_key:
            provider_kwargs["api_key"] = api_key
        if base_url:
            provider_kwargs["base_url"] = base_url
        
        provider = get_provider(provider_name, **provider_kwargs)
        
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        
        last_error: str | None = None
        
        for attempt in range(max_retries + 1):
            try:
                result = await provider.chat(
                    messages,
                    model=model,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
                content = result.get("content", "")
                
                # 使用多层 JSON 提取
                return _extract_json_multilayer(content)
                
            except httpx.TimeoutException as e:
                last_error = f"timeout: {e}"
                if attempt < max_retries:
                    wait_time = 2 ** attempt
                    logger.warning(f"AI call timeout (attempt {attempt + 1}/{max_retries + 1}), "
                                 f"retrying in {wait_time}s...")
                    await asyncio.sleep(wait_time)
                    continue
                logger.error(f"AI call failed after {max_retries + 1} attempts: timeout")
                return {"error": "timeout_after_retries"}
                
            except httpx.HTTPStatusError as e:
                status_code = e.response.status_code
                last_error = f"http_{status_code}: {e}"
                if status_code in _RETRYABLE_STATUS_CODES and attempt < max_retries:
                    wait_time = 2 ** attempt
                    logger.warning(f"AI call got {status_code} (attempt {attempt + 1}/{max_retries + 1}), "
                                 f"retrying in {wait_time}s...")
                    await asyncio.sleep(wait_time)
                    continue
                logger.error(f"AI call failed with HTTP {status_code}: {e}")
                return {"error": f"http_{status_code}", "detail": str(e)}
                
            except Exception as e:
                last_error = str(e)
                # 对于其他异常，也尝试重试
                if attempt < max_retries:
                    wait_time = 2 ** attempt
                    logger.warning(f"AI call error (attempt {attempt + 1}/{max_retries + 1}): {e}, "
                                 f"retrying in {wait_time}s...")
                    await asyncio.sleep(wait_time)
                    continue
                logger.error(f"AI call failed: {e}")
                return {"error": str(e)}
        
        return {"error": last_error or "unknown_error"}
    
    # 使用 semaphore 控制并发
    if semaphore:
        async with semaphore:
            return await _do_call()
    else:
        return await _do_call()


def _smart_truncate(
    source: str,
    max_chars: int,
    branches: list[dict[str, Any]] | None = None,
) -> str:
    """智能上下文截断
    
    保留策略:
    1. 保留函数签名（第一行）
    2. 保留分支结构行（if/else/switch/for/while）
    3. 保留锁操作行
    4. 截断中间纯计算行
    5. 根据分支数动态调整保留量
    
    Args:
        source: 源代码
        max_chars: 最大字符数
        branches: 分支信息列表，用于动态调整保留量
    """
    if len(source) <= max_chars:
        return source
    
    lines = source.split("\n")
    if not lines:
        return source[:max_chars]
    
    # 根据分支数动态调整保留比例
    num_branches = len(branches) if branches else 0
    branch_factor = min(1.0 + num_branches * 0.1, 1.5)  # 最多增加 50%
    adjusted_max = int(max_chars * branch_factor)
    
    # 关键行模式
    important_patterns = [
        r"^\s*(if|else|switch|case|for|while|do)\b",  # 分支/循环
        r"\b(pthread_mutex_lock|pthread_mutex_unlock|lock|unlock|acquire|release)\b",  # 锁操作
        r"\b(return|goto|break|continue)\b",  # 控制流
        r"\b(malloc|free|calloc|realloc)\b",  # 内存操作
        r"\b(open|close|read|write|send|recv)\b",  # IO操作
    ]
    
    # 标记每行是否重要
    important_lines: set[int] = {0}  # 第一行（签名）始终保留
    for i, line in enumerate(lines):
        for pattern in important_patterns:
            if re.search(pattern, line):
                important_lines.add(i)
                break
    
    # 构建结果
    result_lines: list[str] = []
    current_len = 0
    omitted_count = 0
    in_omitted_section = False
    
    for i, line in enumerate(lines):
        is_important = i in important_lines
        line_len = len(line) + 1  # +1 for newline
        
        if is_important or current_len + line_len <= adjusted_max:
            if in_omitted_section and omitted_count > 0:
                result_lines.append(f"    // ... {omitted_count} lines omitted ...")
                current_len += 30  # 估算省略行的长度
                omitted_count = 0
                in_omitted_section = False
            
            result_lines.append(line)
            current_len += line_len
        else:
            omitted_count += 1
            in_omitted_section = True
        
        # 超过限制后，只保留重要行
        if current_len > adjusted_max and not is_important:
            continue
    
    # 添加最后的省略提示
    if omitted_count > 0:
        result_lines.append(f"    // ... {omitted_count} lines omitted ...")
    
    return "\n".join(result_lines)


async def generate_flow_narrative(
    call_chain: list[str],
    entry_point: str,
    entry_type: str,
    branch_path: str,
    locks_held: list[list[str]] | list[str],
    protocol_sequence: list[str],
    function_summaries: dict[str, str],
    ai_config: dict[str, Any],
) -> dict[str, Any]:
    """Generate business flow narrative for a call chain."""
    flattened_locks = _flatten_lock_sequence(locks_held)
    system, user = render_prompt(
        "flow_narrative",
        call_chain=" -> ".join(call_chain),
        entry_point=entry_point,
        entry_type=entry_type,
        branch_path=branch_path,
        locks_held=", ".join(flattened_locks) if flattened_locks else "无",
        protocol_sequence=" -> ".join(protocol_sequence) if protocol_sequence else "无",
        function_summaries="\n".join(
            f"- {name}: {desc}" for name, desc in function_summaries.items()
        ),
    )
    
    return await _call_ai(
        ai_config.get("provider", "deepseek"),
        ai_config.get("model", "deepseek-coder"),
        system,
        user,
        api_key=ai_config.get("api_key"),
        base_url=ai_config.get("base_url"),
    )


async def generate_function_dictionary(
    function_name: str,
    params: list[str],
    comments: str,
    source_snippet: str,
    callers: list[str],
    callees: list[str],
    ai_config: dict[str, Any],
    branches: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Generate business-language function dictionary entry."""
    # 使用智能截断而非简单截断
    truncated_source = _smart_truncate(source_snippet, 2000, branches)
    
    system, user = render_prompt(
        "function_dictionary",
        function_name=function_name,
        params=", ".join(params) if params else "无参数",
        comments=comments if comments else "无注释",
        source_snippet=truncated_source,
        callers=", ".join(callers) if callers else "无",
        callees=", ".join(callees) if callees else "无",
    )
    
    return await _call_ai(
        ai_config.get("provider", "deepseek"),
        ai_config.get("model", "deepseek-coder"),
        system,
        user,
        api_key=ai_config.get("api_key"),
        base_url=ai_config.get("base_url"),
    )


async def generate_what_if_scenarios(
    call_chain: list[str],
    branch_paths: list[dict[str, Any]],
    lock_operations: list[dict[str, Any]],
    protocol_states: list[str],
    identified_risks: list[dict[str, Any]],
    ai_config: dict[str, Any],
) -> dict[str, Any]:
    """Generate What-If test scenarios for a call chain."""
    system, user = render_prompt(
        "what_if_scenarios",
        call_chain=" -> ".join(call_chain),
        branch_paths=json.dumps(branch_paths, ensure_ascii=False, indent=2),
        lock_operations=json.dumps(lock_operations, ensure_ascii=False, indent=2),
        protocol_states=", ".join(protocol_states) if protocol_states else "无",
        identified_risks=json.dumps(identified_risks, ensure_ascii=False, indent=2),
    )
    
    return await _call_ai(
        ai_config.get("provider", "deepseek"),
        ai_config.get("model", "deepseek-coder"),
        system,
        user,
        api_key=ai_config.get("api_key"),
        base_url=ai_config.get("base_url"),
        max_tokens=6000,
    )


async def generate_risk_scenario_card(
    risk_type: str,
    risk_description: str,
    call_chain: list[str],
    file_path: str,
    line_range: str,
    code_evidence: str,
    branch_context: str,
    risk_id: str,
    ai_config: dict[str, Any],
) -> dict[str, Any]:
    """Generate a risk scenario card for test guidance."""
    system, user = render_prompt(
        "risk_scenario_cards",
        risk_type=risk_type,
        risk_description=risk_description,
        call_chain=" -> ".join(call_chain),
        file_path=file_path,
        line_range=line_range,
        code_evidence=code_evidence[:1500],  # Limit code size
        branch_context=branch_context,
        risk_id=risk_id,
    )
    
    return await _call_ai(
        ai_config.get("provider", "deepseek"),
        ai_config.get("model", "deepseek-coder"),
        system,
        user,
        api_key=ai_config.get("api_key"),
        base_url=ai_config.get("base_url"),
    )


async def generate_test_design_matrix(
    call_chain_summary: str,
    branch_paths: list[dict[str, Any]],
    risks: list[dict[str, Any]],
    what_if_scenarios: list[dict[str, Any]],
    entry_type: str,
    ai_config: dict[str, Any],
) -> dict[str, Any]:
    """Generate structured test design matrix."""
    system, user = render_prompt(
        "test_design_matrix",
        call_chain_summary=call_chain_summary,
        branch_paths=json.dumps(branch_paths, ensure_ascii=False, indent=2),
        risks=json.dumps(risks, ensure_ascii=False, indent=2),
        what_if_scenarios=json.dumps(what_if_scenarios, ensure_ascii=False, indent=2),
        entry_type=entry_type,
    )
    
    return await _call_ai(
        ai_config.get("provider", "deepseek"),
        ai_config.get("model", "deepseek-coder"),
        system,
        user,
        api_key=ai_config.get("api_key"),
        base_url=ai_config.get("base_url"),
        max_tokens=8000,
    )


# =============================================================================
# 批量调用函数 - 使用批量 prompt 模板减少 API 调用次数
# =============================================================================

async def generate_chunked_flow_narratives(
    chains: list[dict[str, Any]],
    ai_config: dict[str, Any],
    batch_size: int = 5,
    on_progress: Callable | None = None,
) -> list[dict[str, Any]]:
    """批量生成调用链叙事，每批 batch_size 个。
    
    将 10 次独立调用减少为 2 次批量调用 (batch_size=5)。
    
    Args:
        chains: 调用链信息列表，每项包含 call_chain, entry_point, entry_type 等
        ai_config: AI 配置
        batch_size: 每批处理的调用链数量
        on_progress: 进度回调 (completed, total)
    
    Returns:
        叙事结果列表，每项包含 chain_index 和生成的叙事字段
    """
    if not chains:
        return []
    
    # 分批
    batches = [chains[i:i + batch_size] for i in range(0, len(chains), batch_size)]
    all_results: list[dict[str, Any]] = []
    completed = 0
    
    async def process_batch(batch: list[dict[str, Any]], batch_idx: int) -> list[dict[str, Any]]:
        # 构建批量输入 JSON
        chains_data = []
        for i, chain in enumerate(batch):
            flattened_locks = _flatten_lock_sequence(chain.get("lock_sequence", []))
            chains_data.append({
                "index": i,
                "call_chain": " -> ".join(chain.get("functions", [])),
                "entry_point": chain.get("entry_point", "unknown"),
                "entry_type": chain.get("entry_type", "unknown"),
                "branch_path": chain.get("branch_coverage", ""),
                "locks_held": ", ".join(flattened_locks) if flattened_locks else "无",
                "protocol_sequence": " -> ".join(chain.get("protocol_sequence", [])) if chain.get("protocol_sequence") else "无",
                "function_summaries": chain.get("function_summaries", {}),
            })
        
        system, user = render_prompt(
            "flow_narrative_batch",
            chain_count=len(batch),
            chains_json=json.dumps(chains_data, ensure_ascii=False, indent=2),
        )
        
        result = await _call_ai(
            ai_config.get("provider", "deepseek"),
            ai_config.get("model", "deepseek-coder"),
            system,
            user,
            api_key=ai_config.get("api_key"),
            base_url=ai_config.get("base_url"),
            max_tokens=8000,
        )
        
        # 解析批量结果
        if "items" in result:
            items = result["items"]
        elif isinstance(result, list):
            items = result
        elif "error" in result:
            logger.error(f"Batch flow narrative failed: {result}")
            return [{**chain, "error": result.get("error")} for chain in batch]
        else:
            # 尝试从返回的对象中提取数组
            items = [result] if result else []
        
        # 映射回原始 chain
        batch_results = []
        for i, chain in enumerate(batch):
            matching = next((item for item in items if item.get("chain_index") == i), None)
            if matching:
                batch_results.append({
                    "call_chain": chain.get("functions", []),
                    "entry_point": chain.get("entry_point"),
                    **{k: v for k, v in matching.items() if k != "chain_index"},
                })
            else:
                # fallback: 使用顺序匹配
                if i < len(items):
                    batch_results.append({
                        "call_chain": chain.get("functions", []),
                        "entry_point": chain.get("entry_point"),
                        **{k: v for k, v in items[i].items() if k != "chain_index"},
                    })
                else:
                    batch_results.append({
                        "call_chain": chain.get("functions", []),
                        "entry_point": chain.get("entry_point"),
                        "error": "missing_result",
                    })
        
        return batch_results
    
    # 并行处理各批次
    tasks = [process_batch(batch, i) for i, batch in enumerate(batches)]
    batch_results = await asyncio.gather(*tasks, return_exceptions=True)
    
    for i, result in enumerate(batch_results):
        if isinstance(result, Exception):
            logger.error(f"Batch {i} failed: {result}")
            # 为该批次的每个 chain 添加错误标记
            for chain in batches[i]:
                all_results.append({
                    "call_chain": chain.get("functions", []),
                    "entry_point": chain.get("entry_point"),
                    "error": str(result),
                })
        else:
            all_results.extend(result)
        
        completed += len(batches[i])
        if on_progress:
            on_progress(completed, len(chains))
    
    return all_results


async def generate_chunked_function_dictionary(
    functions: list[dict[str, Any]],
    ai_config: dict[str, Any],
    batch_size: int = 10,
    on_progress: Callable | None = None,
) -> dict[str, dict[str, Any]]:
    """批量生成函数字典，每批 batch_size 个函数。
    
    将 50 次独立调用减少为 5 次批量调用 (batch_size=10)。
    
    Args:
        functions: 函数信息列表
        ai_config: AI 配置
        batch_size: 每批处理的函数数量
        on_progress: 进度回调 (completed, total)
    
    Returns:
        函数名 -> 字典条目的映射
    """
    if not functions:
        return {}
    
    batches = [functions[i:i + batch_size] for i in range(0, len(functions), batch_size)]
    dictionary: dict[str, dict[str, Any]] = {}
    completed = 0
    
    async def process_batch(batch: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
        # 构建批量输入
        funcs_data = []
        for func in batch:
            truncated_source = _smart_truncate(
                func.get("source", ""), 500, func.get("branches")
            )
            funcs_data.append({
                "name": func["name"],
                "params": ", ".join(func.get("params", [])) if func.get("params") else "无参数",
                "comments": func.get("comments", "") or "无注释",
                "source_snippet": truncated_source,
                "callers": ", ".join(func.get("callers", [])[:5]) if func.get("callers") else "无",
                "callees": ", ".join(func.get("callees", [])[:5]) if func.get("callees") else "无",
            })
        
        system, user = render_prompt(
            "function_dictionary_batch",
            function_count=len(batch),
            functions_json=json.dumps(funcs_data, ensure_ascii=False, indent=2),
        )
        
        result = await _call_ai(
            ai_config.get("provider", "deepseek"),
            ai_config.get("model", "deepseek-coder"),
            system,
            user,
            api_key=ai_config.get("api_key"),
            base_url=ai_config.get("base_url"),
            max_tokens=6000,
        )
        
        # 解析: 期望返回 {函数名: {...}}
        if "error" in result:
            logger.error(f"Batch function dictionary failed: {result}")
            return {func["name"]: {"error": result.get("error")} for func in batch}
        
        # 结果可能是字典或包含 items 的对象
        if isinstance(result, dict) and "items" not in result and "error" not in result:
            return result
        elif "items" in result and isinstance(result["items"], dict):
            return result["items"]
        else:
            # fallback: 尝试作为字典返回
            return {func["name"]: result.get(func["name"], {"error": "missing"}) for func in batch}
    
    # 并行处理各批次
    tasks = [process_batch(batch) for batch in batches]
    batch_results = await asyncio.gather(*tasks, return_exceptions=True)
    
    for i, result in enumerate(batch_results):
        if isinstance(result, Exception):
            logger.error(f"Function dictionary batch {i} failed: {result}")
            for func in batches[i]:
                dictionary[func["name"]] = {"error": str(result)}
        else:
            dictionary.update(result)
        
        completed += len(batches[i])
        if on_progress:
            on_progress(completed, len(functions))
    
    return dictionary


async def generate_chunked_risk_cards(
    risks: list[dict[str, Any]],
    ai_config: dict[str, Any],
    batch_size: int = 5,
    on_progress: Callable | None = None,
) -> list[dict[str, Any]]:
    """批量生成风险场景卡片，每批 batch_size 个风险。
    
    将 15 次独立调用减少为 3 次批量调用 (batch_size=5)。
    
    Args:
        risks: 风险信息列表
        ai_config: AI 配置
        batch_size: 每批处理的风险数量
        on_progress: 进度回调 (completed, total)
    
    Returns:
        风险卡片列表
    """
    if not risks:
        return []
    
    batches = [risks[i:i + batch_size] for i in range(0, len(risks), batch_size)]
    all_cards: list[dict[str, Any]] = []
    completed = 0
    
    async def process_batch(batch: list[dict[str, Any]], batch_idx: int) -> list[dict[str, Any]]:
        # 构建批量输入
        risks_data = []
        for i, risk in enumerate(batch):
            risks_data.append({
                "index": i,
                "risk_id": risk.get("finding_id", f"R{batch_idx * batch_size + i}"),
                "risk_type": risk.get("risk_type", "unknown"),
                "risk_description": risk.get("description", ""),
                "call_chain": " -> ".join(risk.get("call_chain", [])),
                "file_path": risk.get("file_path", "unknown"),
                "line_range": risk.get("line_range", ""),
                "code_evidence": (risk.get("code_evidence", "") or "")[:1000],
                "branch_context": risk.get("branch_context", ""),
            })
        
        system, user = render_prompt(
            "risk_scenario_cards_batch",
            risk_count=len(batch),
            risks_json=json.dumps(risks_data, ensure_ascii=False, indent=2),
        )
        
        result = await _call_ai(
            ai_config.get("provider", "deepseek"),
            ai_config.get("model", "deepseek-coder"),
            system,
            user,
            api_key=ai_config.get("api_key"),
            base_url=ai_config.get("base_url"),
            max_tokens=8000,
        )
        
        # 解析批量结果
        if "items" in result:
            items = result["items"]
        elif isinstance(result, list):
            items = result
        elif "error" in result:
            logger.error(f"Batch risk cards failed: {result}")
            return [{"risk_id": r.get("finding_id"), "error": result.get("error")} for r in batch]
        else:
            items = [result] if result else []
        
        # 按 risk_index 排序并返回
        cards = []
        for i, risk in enumerate(batch):
            matching = next((item for item in items if item.get("risk_index") == i), None)
            if matching:
                cards.append({k: v for k, v in matching.items() if k != "risk_index"})
            elif i < len(items):
                cards.append({k: v for k, v in items[i].items() if k != "risk_index"})
            else:
                cards.append({"risk_id": risk.get("finding_id"), "error": "missing_result"})
        
        return cards
    
    # 并行处理各批次
    tasks = [process_batch(batch, i) for i, batch in enumerate(batches)]
    batch_results = await asyncio.gather(*tasks, return_exceptions=True)
    
    for i, result in enumerate(batch_results):
        if isinstance(result, Exception):
            logger.error(f"Risk cards batch {i} failed: {result}")
            for risk in batches[i]:
                all_cards.append({"risk_id": risk.get("finding_id"), "error": str(result)})
        else:
            all_cards.extend(result)
        
        completed += len(batches[i])
        if on_progress:
            on_progress(completed, len(risks))
    
    return all_cards


async def generate_chunked_what_if_scenarios(
    chains: list[dict[str, Any]],
    ai_config: dict[str, Any],
    on_progress: Callable | None = None,
) -> list[dict[str, Any]]:
    """批量生成 What-If 场景，所有调用链合并为 1 次调用。
    
    将 5 次独立调用减少为 1 次批量调用。
    
    Args:
        chains: 调用链信息列表，每项包含 call_chain, branch_paths, lock_operations 等
        ai_config: AI 配置
        on_progress: 进度回调 (completed, total)
    
    Returns:
        What-If 场景结果列表
    """
    if not chains:
        return []
    
    # 所有 chains 合并为一次调用
    chains_data = []
    for i, chain in enumerate(chains):
        chains_data.append({
            "index": i,
            "call_chain": chain.get("functions", []),
            "branch_paths": chain.get("branch_paths", [])[:10],
            "lock_operations": chain.get("lock_operations", [])[:10],
            "protocol_states": chain.get("protocol_sequence", []),
            "identified_risks": chain.get("identified_risks", [])[:5],
        })
    
    system, user = render_prompt(
        "what_if_scenarios_batch",
        chain_count=len(chains),
        chains_json=json.dumps(chains_data, ensure_ascii=False, indent=2),
    )
    
    result = await _call_ai(
        ai_config.get("provider", "deepseek"),
        ai_config.get("model", "deepseek-coder"),
        system,
        user,
        api_key=ai_config.get("api_key"),
        base_url=ai_config.get("base_url"),
        max_tokens=10000,
    )
    
    if on_progress:
        on_progress(len(chains), len(chains))
    
    # 解析批量结果
    if "items" in result:
        items = result["items"]
    elif isinstance(result, list):
        items = result
    elif "error" in result:
        logger.error(f"Batch what-if scenarios failed: {result}")
        return [{"call_chain": c.get("functions", []), "error": result.get("error")} for c in chains]
    else:
        items = [result] if result else []
    
    # 映射回原始 chain
    scenarios = []
    for i, chain in enumerate(chains):
        matching = next((item for item in items if item.get("chain_index") == i), None)
        if matching:
            scenarios.append({
                "call_chain": chain.get("functions", []),
                **{k: v for k, v in matching.items() if k != "chain_index"},
            })
        elif i < len(items):
            scenarios.append({
                "call_chain": chain.get("functions", []),
                **{k: v for k, v in items[i].items() if k != "chain_index"},
            })
        else:
            scenarios.append({
                "call_chain": chain.get("functions", []),
                "scenarios": [],
                "summary": "生成失败",
            })
    
    return scenarios


# =============================================================================
# 旧版批量函数 (保留用于向后兼容，但不再推荐使用)
# =============================================================================

async def generate_batch_function_dictionary(
    functions: list[dict[str, Any]],
    ai_config: dict[str, Any],
    max_concurrent: int = 5,
) -> dict[str, dict[str, Any]]:
    """Generate function dictionary for multiple functions in parallel.
    
    [DEPRECATED] 建议使用 generate_chunked_function_dictionary 以减少 API 调用次数。
    """
    # 不再使用本地 semaphore，依赖全局 semaphore 控制
    async def process_func(func: dict[str, Any]) -> tuple[str, dict[str, Any]]:
        result = await generate_function_dictionary(
            function_name=func["name"],
            params=func.get("params", []),
            comments=func.get("comments", ""),
            source_snippet=func.get("source", ""),
            callers=func.get("callers", []),
            callees=func.get("callees", []),
            ai_config=ai_config,
            branches=func.get("branches"),
        )
        return func["name"], result
    
    tasks = [process_func(f) for f in functions]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    dictionary = {}
    for result in results:
        if isinstance(result, Exception):
            logger.error(f"Function dictionary generation failed: {result}")
        else:
            name, entry = result
            dictionary[name] = entry
    
    return dictionary


async def generate_batch_risk_cards(
    risks: list[dict[str, Any]],
    ai_config: dict[str, Any],
    max_concurrent: int = 3,
) -> list[dict[str, Any]]:
    """Generate risk scenario cards for multiple risks in parallel.
    
    [DEPRECATED] 建议使用 generate_chunked_risk_cards 以减少 API 调用次数。
    """
    # 不再使用本地 semaphore，依赖全局 semaphore 控制
    async def process_risk(risk: dict[str, Any]) -> dict[str, Any]:
        return await generate_risk_scenario_card(
            risk_type=risk.get("risk_type", "unknown"),
            risk_description=risk.get("description", ""),
            call_chain=risk.get("call_chain", []),
            file_path=risk.get("file_path", "unknown"),
            line_range=risk.get("line_range", ""),
            code_evidence=risk.get("code_evidence", ""),
            branch_context=risk.get("branch_context", ""),
            risk_id=risk.get("finding_id", ""),
            ai_config=ai_config,
        )
    
    tasks = [process_risk(r) for r in risks]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    cards = []
    for result in results:
        if isinstance(result, Exception):
            logger.error(f"Risk card generation failed: {result}")
        else:
            cards.append(result)
    
    return cards


class AINarrativeService:
    """High-level service for generating AI narratives from analysis results.
    
    优化版本特性:
    - 使用批量 prompt 减少 API 调用次数 (~81 -> ~12)
    - 四路并行执行无依赖任务
    - 支持进度回调
    """
    
    def __init__(self, ai_config: dict[str, Any]) -> None:
        self.ai_config = ai_config
    
    async def generate_full_narrative(
        self,
        fused_graph: Any,  # FusedGraph
        risk_findings: list[dict[str, Any]],
        on_progress: Callable | None = None,
    ) -> dict[str, Any]:
        """Generate complete narrative package from analysis results.
        
        采用两阶段并行执行:
        - Phase 1: flow_narratives, function_dictionary, risk_cards, what_if_scenarios 并行
        - Phase 2: test_matrix (依赖 what_if 结果)
        
        Args:
            fused_graph: 融合图分析结果
            risk_findings: 风险发现列表
            on_progress: 进度回调函数 (step_name: str, completed: int, total: int)
        
        Returns dict containing:
        - flow_narratives: List of call chain narratives
        - function_dictionary: Function name -> business description mapping
        - risk_cards: List of risk scenario cards
        - what_if_scenarios: List of What-If scenarios per call chain
        - test_matrix: Structured test design matrix
        """
        results: dict[str, Any] = {
            "flow_narratives": [],
            "function_dictionary": {},
            "risk_cards": [],
            "what_if_scenarios": [],
            "test_matrix": None,
        }
        
        # 准备数据
        chains_for_flow = self._prepare_chains_for_flow(fused_graph)
        functions_for_dict = self._prepare_functions_for_dict(fused_graph)
        high_priority_risks = [
            r for r in risk_findings
            if r.get("severity") in ("critical", "high")
        ][:15]
        chains_for_whatif = self._prepare_chains_for_whatif(fused_graph, risk_findings)
        
        # 进度追踪
        def make_progress_cb(step_name: str):
            def cb(completed: int, total: int):
                if on_progress:
                    on_progress(step_name, completed, total)
            return cb
        
        # =====================================================================
        # Phase 1: 四路并行执行 (无依赖)
        # =====================================================================
        logger.info("AI Narrative Phase 1: Starting 4 parallel tasks")
        
        flow_task = generate_chunked_flow_narratives(
            chains_for_flow,
            self.ai_config,
            batch_size=5,
            on_progress=make_progress_cb("flow_narratives"),
        )
        
        dict_task = generate_chunked_function_dictionary(
            functions_for_dict,
            self.ai_config,
            batch_size=10,
            on_progress=make_progress_cb("function_dictionary"),
        )
        
        risk_task = generate_chunked_risk_cards(
            high_priority_risks,
            self.ai_config,
            batch_size=5,
            on_progress=make_progress_cb("risk_cards"),
        )
        
        whatif_task = generate_chunked_what_if_scenarios(
            chains_for_whatif,
            self.ai_config,
            on_progress=make_progress_cb("what_if_scenarios"),
        )
        
        # 并行执行
        phase1_results = await asyncio.gather(
            flow_task, dict_task, risk_task, whatif_task,
            return_exceptions=True
        )
        
        # 处理 Phase 1 结果
        if isinstance(phase1_results[0], Exception):
            logger.error(f"Flow narratives failed: {phase1_results[0]}")
            results["flow_narratives"] = []
        else:
            results["flow_narratives"] = phase1_results[0]
        
        if isinstance(phase1_results[1], Exception):
            logger.error(f"Function dictionary failed: {phase1_results[1]}")
            results["function_dictionary"] = {}
        else:
            results["function_dictionary"] = phase1_results[1]
        
        if isinstance(phase1_results[2], Exception):
            logger.error(f"Risk cards failed: {phase1_results[2]}")
            results["risk_cards"] = []
        else:
            results["risk_cards"] = phase1_results[2]
        
        if isinstance(phase1_results[3], Exception):
            logger.error(f"What-if scenarios failed: {phase1_results[3]}")
            results["what_if_scenarios"] = []
        else:
            results["what_if_scenarios"] = phase1_results[3]
        
        logger.info("AI Narrative Phase 1: Complete")
        
        # =====================================================================
        # Phase 2: test_matrix (依赖 what_if 结果)
        # =====================================================================
        logger.info("AI Narrative Phase 2: Generating test matrix")
        
        if on_progress:
            on_progress("test_matrix", 0, 1)
        
        results["test_matrix"] = await generate_test_design_matrix(
            call_chain_summary="\n".join(
                f"- {' -> '.join(c.functions[:5])}..."
                for c in fused_graph.call_chains[:10]
            ),
            branch_paths=[
                {"function": node.name, "branches": len(node.branches)}
                for node in list(fused_graph.nodes.values())[:20]
                if node.branches
            ],
            risks=[
                {"id": r.get("finding_id"), "type": r.get("risk_type"), "severity": r.get("severity")}
                for r in risk_findings[:15]
            ],
            what_if_scenarios=[
                s.get("scenarios", [])[:2]
                for s in results["what_if_scenarios"]
            ],
            entry_type="mixed" if len(fused_graph.call_chains) > 1 else (
                fused_graph.call_chains[0].entry_type if fused_graph.call_chains else "unknown"
            ),
            ai_config=self.ai_config,
        )
        
        if on_progress:
            on_progress("test_matrix", 1, 1)
        
        logger.info("AI Narrative Phase 2: Complete")
        
        return results
    
    def _prepare_chains_for_flow(self, fused_graph: Any) -> list[dict[str, Any]]:
        """准备调用链数据用于 flow narrative 批量生成."""
        chains = []
        for chain in fused_graph.call_chains[:10]:
            chains.append({
                "functions": chain.functions,
                "entry_point": chain.entry_point,
                "entry_type": chain.entry_type,
                "branch_coverage": chain.branch_coverage,
                "lock_sequence": chain.lock_sequence,
                "protocol_sequence": chain.protocol_sequence,
                "function_summaries": {
                    f: fused_graph.nodes[f].comments[0].text
                    if f in fused_graph.nodes and fused_graph.nodes[f].comments
                    else ""
                    for f in chain.functions
                    if f in fused_graph.nodes
                },
            })
        return chains
    
    def _prepare_functions_for_dict(self, fused_graph: Any) -> list[dict[str, Any]]:
        """准备函数数据用于 function dictionary 批量生成."""
        # Pre-build adjacency maps for O(1) caller/callee lookup (vs O(E) per node)
        callers_map: dict[str, list[str]] = {}
        callees_map: dict[str, list[str]] = {}
        for edge in fused_graph.edges:
            callees_map.setdefault(edge.caller, []).append(edge.callee)
            callers_map.setdefault(edge.callee, []).append(edge.caller)
        
        functions = []
        for node in list(fused_graph.nodes.values())[:50]:
            functions.append({
                "name": node.name,
                "params": node.params,
                "comments": "\n".join(c.text for c in node.comments),
                "source": node.source or "",
                "branches": [{"type": b.branch_type, "condition": b.condition} for b in node.branches],
                "callers": callers_map.get(node.name, [])[:5],
                "callees": callees_map.get(node.name, [])[:5],
            })
        return functions
    
    def _prepare_chains_for_whatif(
        self, fused_graph: Any, risk_findings: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """准备调用链数据用于 what-if 批量生成."""
        chains = []
        for chain in fused_graph.call_chains[:5]:
            chains.append({
                "functions": chain.functions,
                "protocol_sequence": chain.protocol_sequence,
                "branch_paths": [
                    {"condition": b.condition, "type": b.branch_type}
                    for f in chain.functions
                    if f in fused_graph.nodes
                    for b in fused_graph.nodes[f].branches
                ][:10],
                "lock_operations": [
                    {"op": l.op_type, "lock": l.lock_name}
                    for f in chain.functions
                    if f in fused_graph.nodes
                    for l in fused_graph.nodes[f].lock_ops
                ][:10],
                "identified_risks": [
                    {"type": r.get("risk_type"), "desc": r.get("description", "")}
                    for r in risk_findings
                    if any(f in r.get("call_chain", []) for f in chain.functions)
                ][:5],
            })
        return chains
