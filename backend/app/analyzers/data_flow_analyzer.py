"""数据流/污点追踪分析器。

核心基础设施模块：跨函数参数传播链构建、值域收窄/扩张检测、
智能深度追踪、外部输入到敏感操作的污点传播分析。

依赖: call_graph（增强版，含参数映射）
"""

from __future__ import annotations

import logging
import re
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.analyzers.base import AnalyzeContext, ModuleResult
from app.analyzers.code_parser import CodeParser
from app.analyzers.call_graph_builder import CallGraph, build_callgraph, CallSite

logger = logging.getLogger(__name__)

MODULE_ID = "data_flow"

# ── 默认配置 ──────────────────────────────────────────────────────────
DEFAULT_MAX_DEPTH = 12
DEFAULT_BASE_DEPTH = 3

# ── 敏感操作模式 ─────────────────────────────────────────────────────
_SENSITIVE_OPS = {
    "memory_access": re.compile(
        r"\b(memcpy|memmove|memset|strcpy|strncpy|strcat|strncat|"
        r"malloc|calloc|realloc|free)\s*\("
    ),
    "array_index": re.compile(r"\w+\s*\[([^\]]+)\]"),
    "system_call": re.compile(
        r"\b(open|close|read|write|ioctl|mmap|munmap|"
        r"send|recv|socket|connect|bind|listen|accept)\s*\("
    ),
    "lock_operation": re.compile(
        r"\b(pthread_mutex_lock|pthread_mutex_unlock|"
        r"spin_lock|spin_unlock|mutex_lock|mutex_unlock)\s*\("
    ),
    "format_string": re.compile(
        r"\b(printf|fprintf|sprintf|snprintf|syslog)\s*\("
    ),
}

# ── 值变换模式 ────────────────────────────────────────────────────────
_TRANSFORM_PATTERNS = [
    (re.compile(r"(\w+)\s*\+\s*(\w+)"), "add"),
    (re.compile(r"(\w+)\s*-\s*(\w+)"), "sub"),
    (re.compile(r"(\w+)\s*\*\s*(\w+)"), "mul"),
    (re.compile(r"(\w+)\s*/\s*(\w+)"), "div"),
    (re.compile(r"(\w+)\s*>>\s*(\d+)"), "rshift"),
    (re.compile(r"(\w+)\s*<<\s*(\d+)"), "lshift"),
    (re.compile(r"(\w+)\s*&\s*(0x[0-9a-fA-F]+|\w+)"), "mask"),
    (re.compile(r"\(\s*(\w+)\s*\)\s*(\w+)"), "cast"),
]

# ── 外部输入源标记 ────────────────────────────────────────────────────
_EXTERNAL_INPUT_PATTERNS = re.compile(
    r"\b(argv|argc|stdin|getenv|fgets|fread|recv|recvfrom|"
    r"read|getchar|scanf|fscanf|sscanf|gets|"
    r"request|req|input|buf|data|payload|packet|msg)\b",
    re.IGNORECASE,
)


@dataclass
class PropagationStep:
    """传播链的一个步骤。"""
    function: str
    param: str
    param_idx: int
    transform: str  # "none", "add", "sub", "mul", "cast" etc.
    transform_expr: str  # 变换表达式描述
    file_path: str
    line: int


@dataclass
class PropagationChain:
    """一条完整的参数传播链。"""
    chain_id: str
    entry_function: str
    entry_param: str
    steps: list[PropagationStep] = field(default_factory=list)
    terminal_risks: list[dict[str, Any]] = field(default_factory=list)
    is_external_input: bool = False  # 入口参数是否来自外部输入
    sensitive_ops: list[str] = field(default_factory=list)  # 到达的敏感操作
    max_depth: int = 0

    def to_dict(self) -> dict:
        return {
            "chain_id": self.chain_id,
            "entry_function": self.entry_function,
            "entry_param": self.entry_param,
            "is_external_input": self.is_external_input,
            "sensitive_ops": self.sensitive_ops,
            "max_depth": self.max_depth,
            "propagation_path": [
                {
                    "function": s.function,
                    "param": s.param,
                    "param_idx": s.param_idx,
                    "transform": s.transform,
                    "transform_expr": s.transform_expr,
                    "file_path": s.file_path,
                    "line": s.line,
                }
                for s in self.steps
            ],
            "terminal_risks": self.terminal_risks,
        }


def _compute_trace_depth(
    function: str,
    call_graph: CallGraph,
    risk_scores: dict[str, float],
    max_depth: int = DEFAULT_MAX_DEPTH,
) -> int:
    """根据函数风险和调用频率动态决定追踪深度。"""
    base_depth = DEFAULT_BASE_DEPTH
    fan_in = call_graph.fan_in(function)
    fan_out = call_graph.fan_out(function)
    risk = risk_scores.get(function, 0.0)

    # 高风险函数追踪更深
    if risk > 0.7:
        base_depth += 4
    elif risk > 0.4:
        base_depth += 2

    # 高扇入（被很多人调用）= 关键节点，追踪更深
    if fan_in > 5:
        base_depth += 2
    elif fan_in > 2:
        base_depth += 1

    # 高扇出（调用很多人）= 集成枢纽，追踪更深
    if fan_out > 5:
        base_depth += 1

    return min(base_depth, max_depth)


def _detect_transform(caller_source: str, arg_expr: str, param_name: str) -> tuple[str, str]:
    """检测参数在调用前经历了什么变换。

    返回 (transform_type, transform_expression)
    """
    # 检查实参是否包含算术运算
    for pattern, transform_type in _TRANSFORM_PATTERNS:
        if pattern.search(arg_expr):
            return transform_type, arg_expr

    # 检查是否是简单传递
    if re.match(r"^[a-zA-Z_]\w*$", arg_expr.strip()):
        return "none", arg_expr.strip()

    # 检查是否是成员访问
    if "->" in arg_expr or "." in arg_expr:
        return "member_access", arg_expr.strip()

    # 检查是否是取地址/解引用
    if arg_expr.strip().startswith("&"):
        return "address_of", arg_expr.strip()
    if arg_expr.strip().startswith("*"):
        return "dereference", arg_expr.strip()

    return "complex", arg_expr.strip()


def _is_param_used_in_sensitive_op(source: str, param_name: str) -> list[str]:
    """检查参数是否被用于敏感操作。"""
    sensitive = []
    for op_name, pattern in _SENSITIVE_OPS.items():
        # 检查该参数是否出现在敏感函数调用附近
        for m in pattern.finditer(source):
            # 获取敏感调用的上下文（前后100字符）
            start = max(0, m.start() - 20)
            end = min(len(source), m.end() + 100)
            context = source[start:end]
            if re.search(rf"\b{re.escape(param_name)}\b", context):
                sensitive.append(op_name)
                break
    return sensitive


def _is_external_input(entry_function: str, param_name: str, function_source: str) -> bool:
    """判断入口函数的参数是否可能来自外部输入。"""
    # 检查参数名是否匹配外部输入模式
    if _EXTERNAL_INPUT_PATTERNS.search(param_name):
        return True
    # 检查函数名是否是典型的入口点
    entry_patterns = re.compile(
        r"(handle|process|parse|dispatch|on_|do_|cmd_|ioctl_|"
        r"request|handler|callback|main|entry|init|setup)",
        re.IGNORECASE,
    )
    if entry_patterns.search(entry_function):
        return True
    return False


def _build_propagation_chains(
    call_graph: CallGraph,
    function_sources: dict[str, str],
    risk_scores: dict[str, float],
    max_depth: int = DEFAULT_MAX_DEPTH,
) -> list[PropagationChain]:
    """构建所有有意义的参数传播链。

    策略: 从入口函数（高扇入=0 或低扇入的函数）开始，
    沿调用图向下追踪每个参数的传播路径。
    """
    chains: list[PropagationChain] = []
    chain_id = 0

    # 找出入口函数（没有调用者的函数，或者扇入很低的函数）
    entry_functions = set()
    for fn in call_graph.nodes:
        fi = call_graph.fan_in(fn)
        if fi == 0:
            entry_functions.add(fn)
        elif fi <= 2 and fn in function_sources:
            # 低扇入函数也作为入口点
            entry_functions.add(fn)

    # 对每个入口函数的每个参数进行追踪
    for entry_fn in sorted(entry_functions):
        params = call_graph.function_params.get(entry_fn, [])
        if not params:
            continue

        trace_depth = _compute_trace_depth(entry_fn, call_graph, risk_scores, max_depth)

        for param_idx, param_name in enumerate(params):
            chain_id += 1
            chain = PropagationChain(
                chain_id=f"DF-C{chain_id:04d}",
                entry_function=entry_fn,
                entry_param=param_name,
                is_external_input=_is_external_input(
                    entry_fn, param_name,
                    function_sources.get(entry_fn, ""),
                ),
            )

            # 初始步骤
            entry_step = PropagationStep(
                function=entry_fn,
                param=param_name,
                param_idx=param_idx,
                transform="none",
                transform_expr=param_name,
                file_path=call_graph.function_files.get(entry_fn, ""),
                line=call_graph.function_lines.get(entry_fn, (0, 0))[0],
            )
            chain.steps.append(entry_step)

            # 检查入口函数中该参数是否用于敏感操作
            entry_source = function_sources.get(entry_fn, "")
            sensitive = _is_param_used_in_sensitive_op(entry_source, param_name)
            chain.sensitive_ops.extend(sensitive)

            # 沿调用图向下追踪
            _trace_param_forward(
                call_graph, function_sources, risk_scores,
                entry_fn, param_name, param_idx,
                chain, set(), trace_depth, 1,
            )

            chain.max_depth = len(chain.steps) - 1

            # 只保留有意义的链（长度 > 1 或到达敏感操作）
            if len(chain.steps) > 1 or chain.sensitive_ops:
                chains.append(chain)

    return chains


def _trace_param_forward(
    call_graph: CallGraph,
    function_sources: dict[str, str],
    risk_scores: dict[str, float],
    current_fn: str,
    current_param: str,
    current_param_idx: int,
    chain: PropagationChain,
    visited: set[str],
    max_depth: int,
    current_depth: int,
) -> None:
    """递归追踪参数在调用链中的向下传播。"""
    if current_depth > max_depth or current_fn in visited:
        return

    visited.add(current_fn)
    fn_source = function_sources.get(current_fn, "")

    # 获取当前函数的所有调用点
    call_sites = call_graph.get_call_sites(caller=current_fn)

    for site in call_sites:
        # 检查当前被追踪的参数是否出现在调用的实参中
        for mapping in site.arg_mapping:
            caller_expr = mapping.get("caller_expr", "")
            # 检查当前参数是否在实参表达式中被引用
            if not re.search(rf"\b{re.escape(current_param)}\b", caller_expr):
                continue

            callee_param = mapping.get("callee_param", f"arg{mapping['param_idx']}")
            callee_param_idx = mapping["param_idx"]

            # 检测变换
            transform_type, transform_expr = _detect_transform(
                fn_source, caller_expr, current_param,
            )

            step = PropagationStep(
                function=site.callee,
                param=callee_param,
                param_idx=callee_param_idx,
                transform=transform_type,
                transform_expr=transform_expr,
                file_path=call_graph.function_files.get(site.callee, ""),
                line=site.line,
            )
            chain.steps.append(step)

            # 检查 callee 中该参数是否用于敏感操作
            callee_source = function_sources.get(site.callee, "")
            sensitive = _is_param_used_in_sensitive_op(callee_source, callee_param)
            for s in sensitive:
                if s not in chain.sensitive_ops:
                    chain.sensitive_ops.append(s)

            # 继续追踪
            _trace_param_forward(
                call_graph, function_sources, risk_scores,
                site.callee, callee_param, callee_param_idx,
                chain, visited, max_depth, current_depth + 1,
            )

            # 回溯（已经加过了，不需要 pop，因为 chain.steps 是累积的）
            break  # 每个参数在一个调用点只追踪一次最佳匹配

    visited.discard(current_fn)


def _build_risk_scores(upstream: dict[str, dict]) -> dict[str, float]:
    """从上游分析结果中提取每个函数的风险评分。"""
    scores: dict[str, float] = {}
    for mod_id, mod_data in upstream.items():
        for finding in mod_data.get("findings", []):
            sym = finding.get("symbol_name", "")
            risk = finding.get("risk_score", 0.0)
            if sym and risk > scores.get(sym, 0.0):
                scores[sym] = risk
    return scores


def analyze(ctx: AnalyzeContext) -> ModuleResult:
    """运行数据流分析。"""
    workspace = ctx["workspace_path"]
    target = ctx["target"]
    options = ctx["options"]
    upstream = ctx["upstream_results"]
    target_path = Path(workspace) / target.get("path", "")
    max_files = options.get("max_files", 500)
    max_depth = options.get("callgraph_depth", DEFAULT_MAX_DEPTH)

    findings: list[dict[str, Any]] = []
    warnings: list[str] = []
    fid = 0

    # Step 1: 获取或构建调用图
    cg: CallGraph | None = None
    cg_data = upstream.get("call_graph", {})

    # 总是重新构建以获取完整的参数映射
    cg, cg_warns = build_callgraph(workspace, target_path, max_files)
    warnings.extend(cg_warns)

    if not cg or not cg.nodes:
        warnings.append("调用图为空，无法进行数据流分析")
        return _result(findings, warnings, 0, 0, 0, 0)

    # Step 2: 收集函数源码
    parser = CodeParser()
    function_sources: dict[str, str] = {}

    if target_path.is_file():
        files = [target_path]
    elif target_path.is_dir():
        exts = {".c", ".h", ".cpp", ".cc", ".cxx", ".hpp"}
        files = sorted(
            [p for p in target_path.rglob("*") if p.suffix in exts and p.is_file()]
        )[:max_files]
    else:
        files = []

    for fpath in files:
        try:
            symbols = parser.parse_file(fpath)
            for sym in symbols:
                if sym.kind == "function" and sym.source:
                    function_sources[sym.name] = sym.source
        except Exception:
            pass

    # Step 3: 从上游结果构建函数风险评分
    risk_scores = _build_risk_scores(upstream)

    # Step 4: 构建传播链
    chains = _build_propagation_chains(
        cg, function_sources, risk_scores, max_depth,
    )

    # Step 5: 生成发现

    # 5a. 长传播链 —— 参数经过多层调用变换后可能产生意外值
    for chain in chains:
        if chain.max_depth < 2:
            continue

        fid += 1
        has_transform = any(
            s.transform != "none" for s in chain.steps[1:]
        )
        reaches_sensitive = bool(chain.sensitive_ops)

        # 计算风险评分
        risk = 0.4
        if chain.is_external_input:
            risk += 0.2
        if has_transform:
            risk += 0.1
        if reaches_sensitive:
            risk += 0.15
        risk += min(chain.max_depth * 0.03, 0.15)
        risk = min(risk, 0.95)

        severity = "S1" if (chain.is_external_input and reaches_sensitive) else "S2"

        # 构建路径描述
        path_desc = " → ".join(
            f"{s.function}({s.param})"
            for s in chain.steps
        )
        transform_desc = ""
        transforms = [s for s in chain.steps[1:] if s.transform != "none"]
        if transforms:
            transform_desc = "，经过变换: " + "、".join(
                f"{s.function}()中{s.transform}({s.transform_expr})"
                for s in transforms[:3]
            )

        findings.append({
            "finding_id": f"DF-F{fid:04d}",
            "module_id": MODULE_ID,
            "risk_type": "deep_param_propagation",
            "severity": severity,
            "risk_score": round(risk, 4),
            "title": (
                f"参数传播链: {chain.entry_function}({chain.entry_param}) "
                f"经 {chain.max_depth} 层调用到达"
                + (f" {chain.sensitive_ops[0]}" if chain.sensitive_ops else "深层函数")
            ),
            "description": (
                f"参数 '{chain.entry_param}' 从入口函数 {chain.entry_function}() 开始，"
                f"经过 {chain.max_depth} 层函数调用传播{transform_desc}。"
                f"传播路径: {path_desc}。"
                + (f"该参数{'来自外部输入，' if chain.is_external_input else ''}"
                   f"最终到达敏感操作（{', '.join(chain.sensitive_ops)}），"
                   f"看似正常的入口值经过多层变换后可能触发边界条件或安全风险。"
                   if reaches_sensitive
                   else f"虽未直接到达敏感操作，但 {chain.max_depth} 层的传播深度"
                   f"使得入口值的影响难以预测。")
                + f"建议：从入口函数 {chain.entry_function}() 构造边界值测试，"
                f"验证整条调用链的端到端行为。"
            ),
            "file_path": chain.steps[0].file_path if chain.steps else "",
            "symbol_name": chain.entry_function,
            "line_start": chain.steps[0].line if chain.steps else 0,
            "line_end": chain.steps[-1].line if chain.steps else 0,
            "evidence": {
                "propagation_chain": chain.to_dict()["propagation_path"],
                "entry_function": chain.entry_function,
                "entry_param": chain.entry_param,
                "is_external_input": chain.is_external_input,
                "sensitive_ops": chain.sensitive_ops,
                "max_depth": chain.max_depth,
                "has_transform": has_transform,
                "related_functions": [s.function for s in chain.steps][:6],
                "expected_failure": "入口值经多层调用变换后触发敏感操作或边界条件",
                "unacceptable_outcomes": ["越界访问", "溢出", "安全漏洞"],
            },
        })

    # 5b. 外部输入到敏感操作的短链（即使深度 < 2 也很重要）
    for chain in chains:
        if chain.max_depth >= 2:
            continue  # 已在上面处理
        if not (chain.is_external_input and chain.sensitive_ops):
            continue

        fid += 1
        risk = 0.7 if "memory_access" in chain.sensitive_ops else 0.6

        findings.append({
            "finding_id": f"DF-F{fid:04d}",
            "module_id": MODULE_ID,
            "risk_type": "external_to_sensitive",
            "severity": "S1",
            "risk_score": round(risk, 4),
            "title": (
                f"外部输入直达敏感操作: {chain.entry_function}({chain.entry_param}) "
                f"→ {', '.join(chain.sensitive_ops)}"
            ),
            "description": (
                f"外部输入参数 '{chain.entry_param}' 在函数 {chain.entry_function}() 中"
                f"直接或经少量变换用于敏感操作（{', '.join(chain.sensitive_ops)}）。"
                f"这是安全漏洞的典型入口点。需要验证：(1) 输入是否经过充分验证；"
                f"(2) 边界值和畸形输入是否被正确拒绝；(3) 是否有缓冲区溢出风险。"
            ),
            "file_path": chain.steps[0].file_path if chain.steps else "",
            "symbol_name": chain.entry_function,
            "line_start": chain.steps[0].line if chain.steps else 0,
            "line_end": chain.steps[-1].line if chain.steps else 0,
            "evidence": {
                "propagation_chain": chain.to_dict()["propagation_path"],
                "entry_function": chain.entry_function,
                "entry_param": chain.entry_param,
                "is_external_input": True,
                "sensitive_ops": chain.sensitive_ops,
                "max_depth": chain.max_depth,
                "related_functions": [s.function for s in chain.steps][:6],
                "expected_failure": "未校验的外部输入直达敏感操作",
                "unacceptable_outcomes": ["缓冲区溢出", "注入", "崩溃"],
            },
        })

    # 5c. 值域变换风险 —— 参数经过算术变换后可能溢出
    for chain in chains:
        transforms = [s for s in chain.steps if s.transform in ("add", "mul", "lshift", "sub")]
        if not transforms:
            continue

        fid += 1
        risk = 0.55 + len(transforms) * 0.05
        risk = min(risk, 0.85)

        findings.append({
            "finding_id": f"DF-F{fid:04d}",
            "module_id": MODULE_ID,
            "risk_type": "value_transform_risk",
            "severity": "S2",
            "risk_score": round(risk, 4),
            "title": (
                f"值域变换风险: {chain.entry_function}({chain.entry_param}) "
                f"经 {len(transforms)} 次算术变换"
            ),
            "description": (
                f"参数 '{chain.entry_param}' 在调用链中经过 {len(transforms)} 次算术变换"
                f"（{', '.join(t.transform for t in transforms)}），"
                f"每次变换都可能扩大或收窄值域。例如：入口处的正常值 "
                f"经过加法后可能溢出，经过移位后可能丢失精度。"
                f"建议构造刚好触发变换溢出的边界测试值，从入口函数 "
                f"{chain.entry_function}() 注入并验证整条调用链的行为。"
            ),
            "file_path": chain.steps[0].file_path if chain.steps else "",
            "symbol_name": chain.entry_function,
            "line_start": chain.steps[0].line if chain.steps else 0,
            "line_end": 0,
            "evidence": {
                "propagation_chain": chain.to_dict()["propagation_path"],
                "entry_function": chain.entry_function,
                "entry_param": chain.entry_param,
                "transforms": [
                    {"function": t.function, "type": t.transform, "expr": t.transform_expr}
                    for t in transforms
                ],
                "related_functions": [s.function for s in chain.steps if s.transform and s.transform != "none"][:6] or [chain.steps[0].function, chain.steps[-1].function],
                "expected_failure": "算术变换导致溢出或非法值",
                "unacceptable_outcomes": ["整数溢出", "越界", "错误结果"],
            },
        })

    # 构建数据流 artifact
    chains_data = [c.to_dict() for c in chains[:100]]  # 限制大小

    return {
        "module_id": MODULE_ID,
        "status": "success",
        "risk_score": round(
            sum(f["risk_score"] for f in findings) / len(findings), 4
        ) if findings else 0.0,
        "findings": findings,
        "metrics": {
            "total_chains": len(chains),
            "external_input_chains": sum(1 for c in chains if c.is_external_input),
            "chains_reaching_sensitive": sum(1 for c in chains if c.sensitive_ops),
            "max_chain_depth": max((c.max_depth for c in chains), default=0),
            "avg_chain_depth": round(
                sum(c.max_depth for c in chains) / len(chains), 2
            ) if chains else 0,
            "findings_count": len(findings),
        },
        "artifacts": [
            {"type": "data_flow_chains", "data": chains_data},
        ],
        "warnings": warnings,
    }


def _result(
    findings: list, warnings: list,
    chains: int, external: int, sensitive: int, max_depth: int,
) -> ModuleResult:
    risk = round(
        sum(f["risk_score"] for f in findings) / len(findings), 4
    ) if findings else 0.0
    return {
        "module_id": MODULE_ID,
        "status": "success",
        "risk_score": risk,
        "findings": findings,
        "metrics": {
            "total_chains": chains,
            "external_input_chains": external,
            "chains_reaching_sensitive": sensitive,
            "max_chain_depth": max_depth,
            "findings_count": len(findings),
        },
        "artifacts": [],
        "warnings": warnings,
    }
