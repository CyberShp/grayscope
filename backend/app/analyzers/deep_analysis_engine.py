"""深度分析引擎 — 基于语义索引调用 AI 进行深层代码分析。

核心流程：
1. 从 SemanticIndex 获取待分析目标
2. 为每个目标组装上下文（当前函数 + 调用者/被调用者 + 配对信息 + 路径资源状态）
3. 按方法论第四章结构构建 AI Prompt
4. 解析 AI 返回，构建 DeepFinding 对象
5. 与 FusedRiskAnalyzer 的发现去重
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any

from app.ai.prompt_templates import render_prompt_messages
from app.ai.provider_registry import get_provider
from app.analyzers.fused_graph_builder import FusedGraph, FusedNode
from app.analyzers.semantic_indexer import (
    SemanticIndex,
    SemanticIndexer,
    UnpairedResource,
    ExitResourceState,
    CallbackContext,
)

logger = logging.getLogger(__name__)


@dataclass
class DeepFinding:
    """深度分析发现"""
    finding_id: str
    finding_type: str       # resource_leak, deadlock, callback_violation, etc.
    severity: str           # S0, S1, S2, S3
    confidence: float       # 0.0 - 1.0
    title: str
    description: str
    file_path: str
    function_name: str
    line_start: int
    line_end: int
    evidence: dict[str, Any]
    execution_path: list[str]   # 触发路径
    fix_suggestion: str
    related_functions: list[str]
    is_false_positive_risk: bool  # AI 评估是否可能为误报
    false_positive_reason: str


@dataclass
class DeepAnalysisResult:
    """深度分析结果"""
    findings: list[DeepFinding] = field(default_factory=list)
    analyzed_targets: int = 0
    ai_calls: int = 0
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "findings": [
                {
                    "finding_id": f.finding_id,
                    "finding_type": f.finding_type,
                    "severity": f.severity,
                    "confidence": f.confidence,
                    "title": f.title,
                    "description": f.description,
                    "file_path": f.file_path,
                    "function_name": f.function_name,
                    "line_start": f.line_start,
                    "line_end": f.line_end,
                    "evidence": f.evidence,
                    "execution_path": f.execution_path,
                    "fix_suggestion": f.fix_suggestion,
                    "related_functions": f.related_functions,
                    "is_false_positive_risk": f.is_false_positive_risk,
                    "false_positive_reason": f.false_positive_reason,
                }
                for f in self.findings
            ],
            "analyzed_targets": self.analyzed_targets,
            "ai_calls": self.ai_calls,
            "errors": self.errors,
        }


# AI 并发控制
_DEEP_ANALYSIS_SEMAPHORE: asyncio.Semaphore | None = None


def _get_semaphore(max_concurrent: int = 4) -> asyncio.Semaphore:
    """获取或创建深度分析 semaphore"""
    global _DEEP_ANALYSIS_SEMAPHORE
    if _DEEP_ANALYSIS_SEMAPHORE is None:
        _DEEP_ANALYSIS_SEMAPHORE = asyncio.Semaphore(max_concurrent)
    return _DEEP_ANALYSIS_SEMAPHORE


class DeepAnalysisEngine:
    """深度分析引擎"""

    def __init__(
        self,
        graph: FusedGraph,
        semantic_index: SemanticIndex,
        ai_config: dict[str, Any] | None = None,
    ) -> None:
        self._graph = graph
        self._index = semantic_index
        self._ai_config = ai_config or {}
        self._result = DeepAnalysisResult()
        self._existing_findings: set[str] = set()  # 用于去重

    async def analyze(
        self,
        existing_risk_findings: list[dict] | None = None,
        max_targets: int = 50,
    ) -> DeepAnalysisResult:
        """执行深度分析
        
        Args:
            existing_risk_findings: FusedRiskAnalyzer 的现有发现（用于去重）
            max_targets: 最大分析目标数
        """
        # 初始化去重集合
        if existing_risk_findings:
            for f in existing_risk_findings:
                key = self._make_finding_key(
                    f.get("file_path", ""),
                    f.get("symbol_name", ""),
                    f.get("line_start", 0),
                    f.get("risk_type", ""),
                )
                self._existing_findings.add(key)
        
        # 收集分析目标
        targets = self._collect_analysis_targets(max_targets)
        self._result.analyzed_targets = len(targets)
        
        if not targets:
            return self._result
        
        # 并行分析（控制并发）
        tasks = [self._analyze_target(target) for target in targets]
        await asyncio.gather(*tasks, return_exceptions=True)
        
        return self._result

    def _collect_analysis_targets(self, max_targets: int) -> list[dict[str, Any]]:
        """收集需要深度分析的目标
        
        优先级：
        1. 有资源泄漏风险的退出点
        2. 未配对的资源操作
        3. 回调上下文约束可能违规的函数
        """
        targets: list[dict[str, Any]] = []
        
        # 1. 退出点资源泄漏
        for exit_state in self._index.exit_resource_states:
            if exit_state.missing_release:
                targets.append({
                    "type": "exit_resource_leak",
                    "func_name": exit_state.func_name,
                    "exit_line": exit_state.exit_line,
                    "exit_type": exit_state.exit_type,
                    "condition": exit_state.condition,
                    "missing_release": exit_state.missing_release,
                    "priority": 1,
                })
        
        # 2. 未配对资源
        for unpaired in self._index.unpaired_resources:
            if unpaired.op_type == "acquire":
                targets.append({
                    "type": "unpaired_acquire",
                    "func_name": unpaired.func_name,
                    "line": unpaired.line,
                    "api_name": unpaired.api_name,
                    "resource_id": unpaired.resource_id,
                    "resource_kind": unpaired.resource_kind,
                    "priority": 2,
                })
        
        # 3. 回调约束检查
        for callback in self._index.callback_contexts:
            if not callback.can_sleep:
                targets.append({
                    "type": "callback_constraint",
                    "func_name": callback.func_name,
                    "registration_api": callback.registration_api,
                    "execution_context": callback.execution_context,
                    "constraints": callback.constraints,
                    "priority": 3,
                })
        
        # 按优先级排序并限制数量
        targets.sort(key=lambda x: x["priority"])
        return targets[:max_targets]

    async def _analyze_target(self, target: dict[str, Any]) -> None:
        """分析单个目标"""
        target_type = target.get("type", "")
        
        try:
            if target_type == "exit_resource_leak":
                await self._analyze_exit_resource_leak(target)
            elif target_type == "unpaired_acquire":
                await self._analyze_unpaired_acquire(target)
            elif target_type == "callback_constraint":
                await self._analyze_callback_constraint(target)
        except Exception as e:
            self._result.errors.append(f"分析 {target_type} 失败: {e}")
            logger.warning("深度分析目标失败: %s", e)

    async def _analyze_exit_resource_leak(self, target: dict[str, Any]) -> None:
        """分析退出点资源泄漏"""
        func_name = target["func_name"]
        node = self._graph.nodes.get(func_name)
        if not node:
            return
        
        # 检查是否已存在类似发现
        finding_key = self._make_finding_key(
            node.file_path, func_name, target["exit_line"], "error_path_resource_leak"
        )
        if finding_key in self._existing_findings:
            return
        
        # 组装上下文
        context = self._build_function_context(func_name)
        
        # 构建 AI prompt
        prompt_vars = {
            "function_name": func_name,
            "function_source": node.source[:4000],
            "exit_line": target["exit_line"],
            "exit_type": target["exit_type"],
            "condition": target["condition"],
            "missing_release": target["missing_release"],
            "callers_code": context.get("callers_code", ""),
            "callees_code": context.get("callees_code", ""),
            "paired_operations": context.get("paired_operations", []),
        }
        
        # 调用 AI
        ai_result = await self._call_ai("deep_analysis_resource_leak", prompt_vars)
        if not ai_result:
            return
        
        # 解析结果并创建发现
        findings = self._parse_ai_findings(ai_result, node, target)
        for f in findings:
            if f.finding_id not in self._existing_findings:
                self._result.findings.append(f)
                self._existing_findings.add(f.finding_id)

    async def _analyze_unpaired_acquire(self, target: dict[str, Any]) -> None:
        """分析未配对的资源获取"""
        func_name = target["func_name"]
        node = self._graph.nodes.get(func_name)
        if not node:
            return
        
        # 检查是否有跨函数配对（调用者中的 release）
        callers = self._index.function_callers.get(func_name, [])
        
        # 组装上下文
        context = self._build_function_context(func_name)
        context["callers"] = callers
        context["resource_api"] = target["api_name"]
        context["resource_id"] = target["resource_id"]
        
        # 检查是否通过返回值或参数传递了资源
        # 如果是，可能是所有权转移，不是泄漏
        for transfer in self._index.ownership_transfers:
            if transfer.func_name == func_name and transfer.resource_id == target["resource_id"]:
                # 所有权已转移，跳过
                return
        
        # 构建简化的发现（不调用 AI 以节省成本）
        finding = DeepFinding(
            finding_id=f"deep_unpaired_{func_name}_{target['line']}",
            finding_type="potential_resource_leak",
            severity="S2",
            confidence=0.6,
            title=f"潜在资源泄漏: {target['api_name']}",
            description=f"函数 {func_name} 调用了 {target['api_name']} 获取资源，但未找到对应的释放操作",
            file_path=node.file_path,
            function_name=func_name,
            line_start=target["line"],
            line_end=target["line"],
            evidence={
                "api_name": target["api_name"],
                "resource_id": target["resource_id"],
                "resource_kind": target["resource_kind"],
                "callers": callers[:5],
            },
            execution_path=[func_name],
            fix_suggestion=f"确认资源是否通过返回值传递给调用者释放，或在函数内添加释放操作",
            related_functions=callers[:5],
            is_false_positive_risk=len(callers) > 0,  # 有调用者时可能是跨函数配对
            false_positive_reason="可能是跨函数配对或所有权转移" if callers else "",
        )
        
        finding_key = self._make_finding_key(
            node.file_path, func_name, target["line"], "potential_resource_leak"
        )
        if finding_key not in self._existing_findings:
            self._result.findings.append(finding)
            self._existing_findings.add(finding_key)

    async def _analyze_callback_constraint(self, target: dict[str, Any]) -> None:
        """分析回调上下文约束"""
        func_name = target["func_name"]
        node = self._graph.nodes.get(func_name)
        if not node:
            return
        
        # 检查是否存在违规操作
        sleepable_apis = {
            "mutex_lock", "down", "down_read", "down_write",
            "msleep", "usleep_range", "schedule", "schedule_timeout",
            "wait_event", "wait_for_completion",
            "copy_from_user", "copy_to_user",
            "kmalloc", "kzalloc", "vmalloc",  # 使用 GFP_KERNEL 时
        }
        
        violations = []
        for line_idx, line in enumerate(node.source.split("\n")):
            for api in sleepable_apis:
                if re.search(rf"\b{api}\s*\(", line):
                    # 检查 kmalloc 是否使用 GFP_KERNEL
                    if api in ("kmalloc", "kzalloc") and "GFP_ATOMIC" in line:
                        continue
                    violations.append({
                        "api": api,
                        "line": node.line_start + line_idx,
                        "code": line.strip()[:100],
                    })
        
        if not violations:
            return
        
        finding = DeepFinding(
            finding_id=f"deep_callback_{func_name}_{target['registration_api']}",
            finding_type="callback_context_violation",
            severity="S1",
            confidence=0.8,
            title=f"原子上下文中调用可睡眠函数",
            description=(
                f"函数 {func_name} 被注册为 {target['registration_api']} 回调，"
                f"运行在 {target['execution_context']} 上下文中，不能调用可睡眠函数。"
                f"但发现了 {len(violations)} 处可能违规的调用。"
            ),
            file_path=node.file_path,
            function_name=func_name,
            line_start=violations[0]["line"],
            line_end=violations[-1]["line"],
            evidence={
                "registration_api": target["registration_api"],
                "execution_context": target["execution_context"],
                "violations": violations[:10],
            },
            execution_path=[func_name],
            fix_suggestion="将可睡眠操作移到工作队列中执行，或使用原子上下文安全的替代API",
            related_functions=[],
            is_false_positive_risk=False,
            false_positive_reason="",
        )
        
        finding_key = self._make_finding_key(
            node.file_path, func_name, violations[0]["line"], "callback_context_violation"
        )
        if finding_key not in self._existing_findings:
            self._result.findings.append(finding)
            self._existing_findings.add(finding_key)

    def _build_function_context(self, func_name: str) -> dict[str, Any]:
        """为函数构建分析上下文"""
        context: dict[str, Any] = {}
        
        # 获取调用者代码
        callers = self._index.function_callers.get(func_name, [])
        callers_code = []
        for caller in callers[:3]:
            caller_node = self._graph.nodes.get(caller)
            if caller_node:
                callers_code.append(f"// {caller}\n{caller_node.source[:1000]}")
        context["callers_code"] = "\n\n".join(callers_code)
        
        # 获取被调用者代码
        callees = self._index.function_callees.get(func_name, [])
        callees_code = []
        for callee in callees[:3]:
            callee_node = self._graph.nodes.get(callee)
            if callee_node:
                callees_code.append(f"// {callee}\n{callee_node.source[:1000]}")
        context["callees_code"] = "\n\n".join(callees_code)
        
        # 获取已确认的配对操作
        paired_ops = [
            {
                "acquire": f"{p.acquire_func}:{p.acquire_line} - {p.acquire_api}",
                "release": f"{p.release_func}:{p.release_line} - {p.release_api}",
            }
            for p in self._index.paired_operations
            if p.acquire_func == func_name or p.release_func == func_name
        ]
        context["paired_operations"] = paired_ops
        
        return context

    async def _call_ai(
        self, template_id: str, variables: dict[str, Any]
    ) -> dict[str, Any] | None:
        """调用 AI 模型"""
        if not self._ai_config:
            return None
        
        provider_name = self._ai_config.get("provider", "custom")
        model = self._ai_config.get("model", "default")
        
        try:
            messages = render_prompt_messages(template_id, **variables)
        except Exception as e:
            logger.warning("渲染深度分析 prompt 失败: %s", e)
            return None
        
        sem = _get_semaphore()
        async with sem:
            try:
                provider = get_provider(
                    provider_name,
                    model=model,
                    api_key=self._ai_config.get("api_key"),
                    base_url=self._ai_config.get("base_url"),
                )
                result = await provider.chat(messages, model=model)
                self._result.ai_calls += 1
                return {
                    "content": result.get("content", ""),
                    "success": True,
                }
            except Exception as e:
                logger.warning("深度分析 AI 调用失败: %s", e)
                return None

    def _parse_ai_findings(
        self, ai_result: dict[str, Any], node: FusedNode, target: dict[str, Any]
    ) -> list[DeepFinding]:
        """解析 AI 返回的发现"""
        findings: list[DeepFinding] = []
        content = ai_result.get("content", "")
        
        if not content:
            return findings
        
        # 尝试解析 JSON
        try:
            data = json.loads(content)
            if isinstance(data, dict):
                issues = data.get("issues", data.get("findings", [data]))
            elif isinstance(data, list):
                issues = data
            else:
                issues = []
        except json.JSONDecodeError:
            # 非 JSON 响应，创建单个发现
            issues = [{"description": content[:1000]}]
        
        for idx, issue in enumerate(issues[:5]):
            if not isinstance(issue, dict):
                continue
            
            finding = DeepFinding(
                finding_id=f"deep_{target['type']}_{node.name}_{target.get('exit_line', target.get('line', 0))}_{idx}",
                finding_type=issue.get("type", target["type"]),
                severity=issue.get("severity", "S2"),
                confidence=float(issue.get("confidence", 0.7)),
                title=issue.get("title", f"深度分析发现: {target['type']}"),
                description=issue.get("description", "")[:500],
                file_path=node.file_path,
                function_name=node.name,
                line_start=issue.get("line", target.get("exit_line", target.get("line", node.line_start))),
                line_end=issue.get("line_end", node.line_end),
                evidence=issue.get("evidence", target),
                execution_path=issue.get("execution_path", [node.name]),
                fix_suggestion=issue.get("fix_suggestion", issue.get("fix", ""))[:500],
                related_functions=issue.get("related_functions", [])[:10],
                is_false_positive_risk=issue.get("is_false_positive", False),
                false_positive_reason=issue.get("false_positive_reason", "")[:200],
            )
            findings.append(finding)
        
        return findings

    def _make_finding_key(
        self, file_path: str, func_name: str, line: int, finding_type: str
    ) -> str:
        """生成发现的去重 key"""
        return f"{file_path}:{func_name}:{line}:{finding_type}"


async def run_deep_analysis(
    graph: FusedGraph,
    ai_config: dict[str, Any] | None = None,
    existing_findings: list[dict] | None = None,
    max_targets: int = 50,
) -> DeepAnalysisResult:
    """运行深度分析的便捷函数"""
    # 构建语义索引
    indexer = SemanticIndexer(graph)
    semantic_index = indexer.build()
    
    # 运行深度分析
    engine = DeepAnalysisEngine(graph, semantic_index, ai_config)
    return await engine.analyze(existing_findings, max_targets)
