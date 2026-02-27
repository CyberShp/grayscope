"""AI Narrative Service for code analysis.

Transforms technical analysis results into business-friendly narratives,
risk scenario cards, function dictionaries, What-If scenarios, and test
design matrices using AI-powered prompt templates.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from app.ai.prompt_templates import render_prompt
from app.ai.provider_registry import get_provider

logger = logging.getLogger(__name__)


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
) -> dict[str, Any]:
    """Call AI model and parse JSON response."""
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
    
    try:
        result = await provider.chat(
            messages,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        content = result.get("content", "")
        
        # Try to extract JSON from response
        if "```json" in content:
            start = content.find("```json") + 7
            end = content.find("```", start)
            content = content[start:end].strip()
        elif "```" in content:
            start = content.find("```") + 3
            end = content.find("```", start)
            content = content[start:end].strip()
        
        return json.loads(content)
    except json.JSONDecodeError as e:
        logger.warning(f"Failed to parse AI response as JSON: {e}")
        return {"raw_content": content, "parse_error": str(e)}
    except Exception as e:
        logger.error(f"AI call failed: {e}")
        return {"error": str(e)}


async def generate_flow_narrative(
    call_chain: list[str],
    entry_point: str,
    entry_type: str,
    branch_path: str,
    locks_held: list[str],
    protocol_sequence: list[str],
    function_summaries: dict[str, str],
    ai_config: dict[str, Any],
) -> dict[str, Any]:
    """Generate business flow narrative for a call chain."""
    system, user = render_prompt(
        "flow_narrative",
        call_chain=" -> ".join(call_chain),
        entry_point=entry_point,
        entry_type=entry_type,
        branch_path=branch_path,
        locks_held=", ".join(locks_held) if locks_held else "无",
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
) -> dict[str, Any]:
    """Generate business-language function dictionary entry."""
    system, user = render_prompt(
        "function_dictionary",
        function_name=function_name,
        params=", ".join(params) if params else "无参数",
        comments=comments if comments else "无注释",
        source_snippet=source_snippet[:2000],  # Limit source size
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


async def generate_batch_function_dictionary(
    functions: list[dict[str, Any]],
    ai_config: dict[str, Any],
    max_concurrent: int = 5,
) -> dict[str, dict[str, Any]]:
    """Generate function dictionary for multiple functions in parallel."""
    semaphore = asyncio.Semaphore(max_concurrent)
    
    async def process_func(func: dict[str, Any]) -> tuple[str, dict[str, Any]]:
        async with semaphore:
            result = await generate_function_dictionary(
                function_name=func["name"],
                params=func.get("params", []),
                comments=func.get("comments", ""),
                source_snippet=func.get("source", ""),
                callers=func.get("callers", []),
                callees=func.get("callees", []),
                ai_config=ai_config,
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
    """Generate risk scenario cards for multiple risks in parallel."""
    semaphore = asyncio.Semaphore(max_concurrent)
    
    async def process_risk(risk: dict[str, Any]) -> dict[str, Any]:
        async with semaphore:
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
    """High-level service for generating AI narratives from analysis results."""
    
    def __init__(self, ai_config: dict[str, Any]) -> None:
        self.ai_config = ai_config
    
    async def generate_full_narrative(
        self,
        fused_graph: Any,  # FusedGraph
        risk_findings: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Generate complete narrative package from analysis results.
        
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
        
        # Generate flow narratives for each call chain
        for chain in fused_graph.call_chains[:10]:  # Limit to top 10 chains
            narrative = await generate_flow_narrative(
                call_chain=chain.functions,
                entry_point=chain.entry_point,
                entry_type=chain.entry_type,
                branch_path=chain.branch_coverage,
                locks_held=chain.lock_sequence,
                protocol_sequence=chain.protocol_sequence,
                function_summaries={
                    f: fused_graph.nodes[f].comments[0].text
                    if f in fused_graph.nodes and fused_graph.nodes[f].comments
                    else ""
                    for f in chain.functions
                    if f in fused_graph.nodes
                },
                ai_config=self.ai_config,
            )
            results["flow_narratives"].append({
                "call_chain": chain.functions,
                "entry_point": chain.entry_point,
                **narrative,
            })
        
        # Generate function dictionary
        functions_to_process = [
            {
                "name": node.name,
                "params": node.params,
                "comments": "\n".join(c.text for c in node.comments),
                "source": node.source[:500] if node.source else "",
                "callers": [
                    e.caller for e in fused_graph.edges if e.callee == node.name
                ][:5],
                "callees": [
                    e.callee for e in fused_graph.edges if e.caller == node.name
                ][:5],
            }
            for node in list(fused_graph.nodes.values())[:50]  # Limit nodes
        ]
        results["function_dictionary"] = await generate_batch_function_dictionary(
            functions_to_process,
            self.ai_config,
        )
        
        # Generate risk scenario cards
        high_priority_risks = [
            r for r in risk_findings
            if r.get("severity") in ("critical", "high")
        ][:15]
        results["risk_cards"] = await generate_batch_risk_cards(
            high_priority_risks,
            self.ai_config,
        )
        
        # Generate What-If scenarios for top call chains
        for chain in fused_graph.call_chains[:5]:
            what_if = await generate_what_if_scenarios(
                call_chain=chain.functions,
                branch_paths=[
                    {"condition": b.condition, "type": b.branch_type}
                    for f in chain.functions
                    if f in fused_graph.nodes
                    for b in fused_graph.nodes[f].branches
                ][:10],
                lock_operations=[
                    {"op": l.op_type, "lock": l.lock_name}
                    for f in chain.functions
                    if f in fused_graph.nodes
                    for l in fused_graph.nodes[f].lock_ops
                ][:10],
                protocol_states=chain.protocol_sequence,
                identified_risks=[
                    {"type": r.get("risk_type"), "desc": r.get("description", "")}
                    for r in risk_findings
                    if any(f in r.get("call_chain", []) for f in chain.functions)
                ][:5],
                ai_config=self.ai_config,
            )
            results["what_if_scenarios"].append({
                "call_chain": chain.functions,
                **what_if,
            })
        
        # Generate test design matrix
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
        
        return results
