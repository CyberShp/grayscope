"""语义索引器 — 在 FusedGraph 上构建深度分析所需的语义索引。

纯程序化逻辑，不调用 AI。为 DeepAnalysisEngine 提供确定性的索引数据。

索引类型：
- 配对操作注册表：确认哪些 acquire/release 是成对的
- 路径-资源状态矩阵：每个函数的每个退出点持有的资源
- 回调上下文映射：函数指针注册 → 执行上下文约束
- 所有权转移链：alloc → transfer → 最终释放者
- init/exit 对称性模型：初始化/销毁函数的资源操作对称性
"""

from __future__ import annotations

import logging
import re
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from app.analyzers.fused_graph_builder import (
    FusedGraph,
    FusedNode,
    FusedEdge,
    ResourceOp,
    ErrorExit,
    _RESOURCE_PAIRS,
)

logger = logging.getLogger(__name__)


@dataclass
class PairedOperation:
    """已确认的配对操作"""
    acquire_func: str       # 获取操作所在函数
    acquire_line: int       # 获取操作行号
    acquire_api: str        # 获取 API 名
    release_func: str       # 释放操作所在函数（可能与 acquire 不同）
    release_line: int       # 释放操作行号
    release_api: str        # 释放 API 名
    resource_id: str        # 资源标识符
    resource_kind: str      # 资源类型
    is_cross_function: bool # 是否跨函数配对


@dataclass
class UnpairedResource:
    """未配对的资源操作 — 可能是 bug 或需要深度分析"""
    func_name: str
    line: int
    op_type: str            # acquire / release
    api_name: str
    resource_id: str
    resource_kind: str
    reason: str             # why_unpaired: no_match, cross_function, error_path_only


@dataclass
class ExitResourceState:
    """退出点的资源持有状态"""
    func_name: str
    exit_line: int
    exit_type: str          # return, goto
    condition: str          # 触发条件
    resources_held: list[str]  # 持有的资源 ID
    expected_release: list[str]  # 应该释放的资源（基于函数内 acquire）
    missing_release: list[str]  # 缺失的释放（expected - held 中已 release 的）


@dataclass
class CallbackContext:
    """回调函数的执行上下文约束"""
    func_name: str
    registration_api: str   # request_irq, timer_setup, INIT_WORK 等
    execution_context: str  # atomic, process, softirq, workqueue, unknown
    can_sleep: bool         # 是否可以睡眠
    constraints: list[str]  # 约束描述


@dataclass
class OwnershipTransfer:
    """所有权转移记录"""
    func_name: str
    line: int
    resource_id: str
    transfer_api: str       # list_add, return, assign_to_struct 等
    new_owner: str          # 新所有者（函数名/结构体字段/返回值）


@dataclass
class InitExitPair:
    """初始化/销毁函数对"""
    init_func: str
    exit_func: str
    init_resources: list[str]   # init 中获取的资源（按顺序）
    exit_resources: list[str]   # exit 中释放的资源（按顺序）
    is_symmetric: bool          # 是否对称（逆序）
    asymmetry_details: str      # 不对称的具体说明


@dataclass
class SemanticIndex:
    """语义索引汇总"""
    # P0 核心
    paired_operations: list[PairedOperation] = field(default_factory=list)
    unpaired_resources: list[UnpairedResource] = field(default_factory=list)
    exit_resource_states: list[ExitResourceState] = field(default_factory=list)
    
    # P1
    callback_contexts: list[CallbackContext] = field(default_factory=list)
    ownership_transfers: list[OwnershipTransfer] = field(default_factory=list)
    
    # P2
    init_exit_pairs: list[InitExitPair] = field(default_factory=list)
    
    # 辅助数据
    function_callers: dict[str, list[str]] = field(default_factory=dict)  # func -> [callers]
    function_callees: dict[str, list[str]] = field(default_factory=dict)  # func -> [callees]

    def to_dict(self) -> dict[str, Any]:
        """序列化为字典"""
        return {
            "paired_operations": [
                {
                    "acquire_func": p.acquire_func,
                    "acquire_line": p.acquire_line,
                    "acquire_api": p.acquire_api,
                    "release_func": p.release_func,
                    "release_line": p.release_line,
                    "release_api": p.release_api,
                    "resource_id": p.resource_id,
                    "resource_kind": p.resource_kind,
                    "is_cross_function": p.is_cross_function,
                }
                for p in self.paired_operations
            ],
            "unpaired_resources": [
                {
                    "func_name": u.func_name,
                    "line": u.line,
                    "op_type": u.op_type,
                    "api_name": u.api_name,
                    "resource_id": u.resource_id,
                    "resource_kind": u.resource_kind,
                    "reason": u.reason,
                }
                for u in self.unpaired_resources
            ],
            "exit_resource_states": [
                {
                    "func_name": e.func_name,
                    "exit_line": e.exit_line,
                    "exit_type": e.exit_type,
                    "condition": e.condition,
                    "resources_held": e.resources_held,
                    "expected_release": e.expected_release,
                    "missing_release": e.missing_release,
                }
                for e in self.exit_resource_states
            ],
            "callback_contexts": [
                {
                    "func_name": c.func_name,
                    "registration_api": c.registration_api,
                    "execution_context": c.execution_context,
                    "can_sleep": c.can_sleep,
                    "constraints": c.constraints,
                }
                for c in self.callback_contexts
            ],
            "ownership_transfers": [
                {
                    "func_name": o.func_name,
                    "line": o.line,
                    "resource_id": o.resource_id,
                    "transfer_api": o.transfer_api,
                    "new_owner": o.new_owner,
                }
                for o in self.ownership_transfers
            ],
            "init_exit_pairs": [
                {
                    "init_func": i.init_func,
                    "exit_func": i.exit_func,
                    "init_resources": i.init_resources,
                    "exit_resources": i.exit_resources,
                    "is_symmetric": i.is_symmetric,
                    "asymmetry_details": i.asymmetry_details,
                }
                for i in self.init_exit_pairs
            ],
            "function_callers": self.function_callers,
            "function_callees": self.function_callees,
        }


# 回调注册 API → 执行上下文映射
_CALLBACK_CONTEXT_MAP: dict[str, tuple[str, bool]] = {
    # (execution_context, can_sleep)
    "request_irq": ("atomic", False),
    "request_threaded_irq": ("process", True),  # threaded handler 在进程上下文
    "devm_request_irq": ("atomic", False),
    "devm_request_threaded_irq": ("process", True),
    "timer_setup": ("softirq", False),
    "mod_timer": ("softirq", False),
    "add_timer": ("softirq", False),
    "tasklet_init": ("softirq", False),
    "tasklet_setup": ("softirq", False),
    "INIT_WORK": ("process", True),
    "INIT_DELAYED_WORK": ("process", True),
    "queue_work": ("process", True),
    "schedule_work": ("process", True),
    "kthread_create": ("process", True),
    "kthread_run": ("process", True),
    "pthread_create": ("process", True),
}

# 所有权转移 API
_OWNERSHIP_TRANSFER_APIS = {
    "list_add", "list_add_tail", "list_add_rcu",
    "rb_insert_color", "rb_link_node",
    "hash_add", "hash_add_rcu",
    "hlist_add_head", "hlist_add_head_rcu",
    "rcu_assign_pointer",
    "kobject_add", "device_add",
    "platform_device_add", "pci_register_driver",
}


class SemanticIndexer:
    """语义索引构建器 — 在 FusedGraph 上构建深度分析索引"""

    def __init__(self, graph: FusedGraph) -> None:
        self._graph = graph
        self._index = SemanticIndex()

    def build(self) -> SemanticIndex:
        """构建完整的语义索引"""
        # 首先构建调用关系映射
        self._build_call_maps()
        
        # P0 核心
        self._build_paired_operations()
        self._build_exit_resource_states()
        
        # P1
        self._build_callback_context_map()
        self._build_ownership_transfers()
        
        # P2
        self._build_init_exit_symmetry()
        
        return self._index

    def _build_call_maps(self) -> None:
        """构建调用关系映射"""
        for edge in self._graph.edges:
            # caller -> callees
            if edge.caller not in self._index.function_callees:
                self._index.function_callees[edge.caller] = []
            if edge.callee not in self._index.function_callees[edge.caller]:
                self._index.function_callees[edge.caller].append(edge.callee)
            
            # callee -> callers
            if edge.callee not in self._index.function_callers:
                self._index.function_callers[edge.callee] = []
            if edge.caller not in self._index.function_callers[edge.callee]:
                self._index.function_callers[edge.callee].append(edge.caller)

    def _build_paired_operations(self) -> None:
        """构建配对操作注册表（P0 核心）
        
        识别哪些 acquire/release 是成对的，避免 AI 误报。
        支持函数内配对和跨函数配对。
        """
        # 收集所有资源操作
        all_acquires: list[tuple[str, ResourceOp]] = []  # (func_name, op)
        all_releases: list[tuple[str, ResourceOp]] = []
        
        for func_name, node in self._graph.nodes.items():
            for op in node.resource_ops:
                if op.op_type == "acquire":
                    all_acquires.append((func_name, op))
                elif op.op_type == "release":
                    all_releases.append((func_name, op))
        
        # 用于追踪已配对的操作
        paired_acquires: set[tuple[str, int]] = set()  # (func, line)
        paired_releases: set[tuple[str, int]] = set()
        
        # 第一遍：函数内配对
        for func_name, node in self._graph.nodes.items():
            acquires = [op for op in node.resource_ops if op.op_type == "acquire"]
            releases = [op for op in node.resource_ops if op.op_type == "release"]
            
            for acq in acquires:
                # 查找匹配的 release
                expected_release_api = None
                if acq.api_name in _RESOURCE_PAIRS:
                    _, expected_release_api = _RESOURCE_PAIRS[acq.api_name]
                
                for rel in releases:
                    # 匹配条件：
                    # 1. release API 匹配（标准配对）
                    # 2. 或者 resource_id 匹配（自定义配对）
                    api_match = expected_release_api and rel.api_name == expected_release_api
                    id_match = acq.resource_id and acq.resource_id == rel.resource_id
                    
                    if (api_match or id_match) and rel.line > acq.line:
                        self._index.paired_operations.append(PairedOperation(
                            acquire_func=func_name,
                            acquire_line=acq.line,
                            acquire_api=acq.api_name,
                            release_func=func_name,
                            release_line=rel.line,
                            release_api=rel.api_name,
                            resource_id=acq.resource_id,
                            resource_kind=acq.resource_kind,
                            is_cross_function=False,
                        ))
                        paired_acquires.add((func_name, acq.line))
                        paired_releases.add((func_name, rel.line))
                        break
        
        # 第二遍：跨函数配对（通过调用关系）
        for func_name, acq in all_acquires:
            if (func_name, acq.line) in paired_acquires:
                continue
            
            # 查找调用者中的 release
            callers = self._index.function_callers.get(func_name, [])
            for caller in callers:
                caller_node = self._graph.nodes.get(caller)
                if not caller_node:
                    continue
                
                for rel in caller_node.resource_ops:
                    if rel.op_type != "release":
                        continue
                    
                    # 检查是否为对应的 release
                    expected_release_api = None
                    if acq.api_name in _RESOURCE_PAIRS:
                        _, expected_release_api = _RESOURCE_PAIRS[acq.api_name]
                    
                    api_match = expected_release_api and rel.api_name == expected_release_api
                    
                    if api_match:
                        self._index.paired_operations.append(PairedOperation(
                            acquire_func=func_name,
                            acquire_line=acq.line,
                            acquire_api=acq.api_name,
                            release_func=caller,
                            release_line=rel.line,
                            release_api=rel.api_name,
                            resource_id=acq.resource_id,
                            resource_kind=acq.resource_kind,
                            is_cross_function=True,
                        ))
                        paired_acquires.add((func_name, acq.line))
                        paired_releases.add((caller, rel.line))
                        break
        
        # 记录未配对的操作
        for func_name, acq in all_acquires:
            if (func_name, acq.line) not in paired_acquires:
                # 检查是否为 devm_* 系列（自动释放）
                if acq.api_name.startswith("devm_"):
                    continue
                
                self._index.unpaired_resources.append(UnpairedResource(
                    func_name=func_name,
                    line=acq.line,
                    op_type="acquire",
                    api_name=acq.api_name,
                    resource_id=acq.resource_id,
                    resource_kind=acq.resource_kind,
                    reason="no_matching_release",
                ))
        
        for func_name, rel in all_releases:
            if (func_name, rel.line) not in paired_releases:
                self._index.unpaired_resources.append(UnpairedResource(
                    func_name=func_name,
                    line=rel.line,
                    op_type="release",
                    api_name=rel.api_name,
                    resource_id=rel.resource_id,
                    resource_kind=rel.resource_kind,
                    reason="no_matching_acquire",
                ))

    def _build_exit_resource_states(self) -> None:
        """构建路径-资源状态矩阵（P0 核心）
        
        对每个函数的每个退出点，计算该点持有的资源，
        以及应该释放但未释放的资源。
        """
        for func_name, node in self._graph.nodes.items():
            # 收集函数内的 acquire 操作
            acquires_in_func = [
                op for op in node.resource_ops 
                if op.op_type == "acquire" and not op.api_name.startswith("devm_")
            ]
            
            for exit_point in node.error_exits:
                # 计算该退出点时应该已经 release 的资源
                # （在 exit_point.line 之前的 release）
                released_before_exit = set()
                for op in node.resource_ops:
                    if op.op_type == "release" and op.line < exit_point.line:
                        released_before_exit.add(op.resource_id)
                
                # 计算应该释放的资源（函数内 acquire 且在 exit_point 之前）
                expected_release = [
                    op.resource_id for op in acquires_in_func
                    if op.line < exit_point.line
                ]
                
                # 计算缺失的释放
                missing_release = [
                    rid for rid in expected_release
                    if rid and rid not in released_before_exit and rid in exit_point.resources_held
                ]
                
                if missing_release or exit_point.resources_held:
                    self._index.exit_resource_states.append(ExitResourceState(
                        func_name=func_name,
                        exit_line=exit_point.line,
                        exit_type=exit_point.exit_type,
                        condition=exit_point.condition,
                        resources_held=exit_point.resources_held,
                        expected_release=expected_release,
                        missing_release=missing_release,
                    ))

    def _build_callback_context_map(self) -> None:
        """构建回调上下文映射（P1）
        
        从函数指针赋值和注册 API 推断执行上下文约束。
        """
        for func_name, node in self._graph.nodes.items():
            for ptr_assign in node.func_ptr_assignments:
                target_func = ptr_assign.target_func
                
                # 检查是否为已知的回调注册
                for api, (context, can_sleep) in _CALLBACK_CONTEXT_MAP.items():
                    if api.lower() in ptr_assign.ptr_name.lower() or api.lower() in node.source.lower():
                        constraints = []
                        if not can_sleep:
                            constraints.append("不能调用可睡眠函数（mutex_lock, GFP_KERNEL, copy_from_user, msleep等）")
                        
                        # 检查目标函数是否存在
                        if target_func in self._graph.nodes:
                            self._index.callback_contexts.append(CallbackContext(
                                func_name=target_func,
                                registration_api=api,
                                execution_context=context,
                                can_sleep=can_sleep,
                                constraints=constraints,
                            ))
                        break
            
            # 检查函数内的回调注册调用
            for edge in self._graph.edges:
                if edge.caller != func_name:
                    continue
                
                callee = edge.callee
                if callee in _CALLBACK_CONTEXT_MAP:
                    context, can_sleep = _CALLBACK_CONTEXT_MAP[callee]
                    # 尝试从参数中提取回调函数名
                    for arg in edge.arg_mapping:
                        arg_value = arg.get("value", "")
                        if arg_value in self._graph.nodes:
                            constraints = []
                            if not can_sleep:
                                constraints.append("不能调用可睡眠函数")
                            
                            self._index.callback_contexts.append(CallbackContext(
                                func_name=arg_value,
                                registration_api=callee,
                                execution_context=context,
                                can_sleep=can_sleep,
                                constraints=constraints,
                            ))

    def _build_ownership_transfers(self) -> None:
        """构建所有权转移链（P1）
        
        识别 list_add、返回值、赋值给结构体等所有权转移模式。
        """
        for func_name, node in self._graph.nodes.items():
            source = node.source
            lines = source.split("\n")
            
            for line_idx, line in enumerate(lines):
                actual_line = node.line_start + line_idx
                
                # 检查所有权转移 API 调用
                for api in _OWNERSHIP_TRANSFER_APIS:
                    pattern = rf"\b{re.escape(api)}\s*\(\s*&?\s*(\w+)"
                    for m in re.finditer(pattern, line):
                        resource_id = m.group(1)
                        self._index.ownership_transfers.append(OwnershipTransfer(
                            func_name=func_name,
                            line=actual_line,
                            resource_id=resource_id,
                            transfer_api=api,
                            new_owner=f"container_via_{api}",
                        ))
                
                # 检查 return 语句（通过返回值转移所有权）
                ret_match = re.search(r"\breturn\s+(\w+)\s*;", line)
                if ret_match:
                    ret_val = ret_match.group(1)
                    # 检查是否为资源变量
                    for op in node.resource_ops:
                        if op.op_type == "acquire" and op.resource_id == ret_val:
                            self._index.ownership_transfers.append(OwnershipTransfer(
                                func_name=func_name,
                                line=actual_line,
                                resource_id=ret_val,
                                transfer_api="return",
                                new_owner="caller",
                            ))
                            break
                
                # 检查赋值给结构体字段
                assign_match = re.search(r"(\w+)->(\w+)\s*=\s*(\w+)", line)
                if assign_match:
                    struct_var, field_name, value = assign_match.groups()
                    for op in node.resource_ops:
                        if op.op_type == "acquire" and op.resource_id == value:
                            self._index.ownership_transfers.append(OwnershipTransfer(
                                func_name=func_name,
                                line=actual_line,
                                resource_id=value,
                                transfer_api="assign_to_struct",
                                new_owner=f"{struct_var}->{field_name}",
                            ))
                            break

    def _build_init_exit_symmetry(self) -> None:
        """构建初始化/销毁对称性模型（P2）
        
        识别 init/exit 函数对，验证资源操作的逆序对称性。
        """
        # 识别 init/exit 函数对
        init_funcs: dict[str, str] = {}  # prefix -> full_name
        exit_funcs: dict[str, str] = {}
        
        init_patterns = ["_init", "_probe", "_setup", "_create", "_start", "_open"]
        exit_patterns = ["_exit", "_remove", "_cleanup", "_destroy", "_stop", "_close", "_deinit", "_fini"]
        
        for func_name in self._graph.nodes:
            for pattern in init_patterns:
                if func_name.endswith(pattern):
                    prefix = func_name[:-len(pattern)]
                    init_funcs[prefix] = func_name
                    break
            
            for pattern in exit_patterns:
                if func_name.endswith(pattern):
                    prefix = func_name[:-len(pattern)]
                    if not prefix:
                        # 处理类似 cleanup_xxx 的命名
                        prefix = func_name.replace(pattern.lstrip("_"), "").rstrip("_")
                    exit_funcs[prefix] = func_name
                    break
        
        # 匹配 init/exit 对
        for prefix, init_func in init_funcs.items():
            exit_func = exit_funcs.get(prefix)
            if not exit_func:
                # 尝试其他命名惯例
                for ep in exit_patterns:
                    candidate = prefix + ep
                    if candidate in self._graph.nodes:
                        exit_func = candidate
                        break
            
            if not exit_func:
                continue
            
            init_node = self._graph.nodes.get(init_func)
            exit_node = self._graph.nodes.get(exit_func)
            
            if not init_node or not exit_node:
                continue
            
            # 提取资源操作序列
            init_acquires = [
                op.api_name for op in init_node.resource_ops 
                if op.op_type == "acquire" and not op.in_error_path
            ]
            exit_releases = [
                op.api_name for op in exit_node.resource_ops 
                if op.op_type == "release"
            ]
            
            # 检查逆序对称性
            expected_exit_order = list(reversed(init_acquires))
            is_symmetric = self._check_sequence_match(expected_exit_order, exit_releases)
            
            asymmetry_details = ""
            if not is_symmetric:
                missing_in_exit = [api for api in init_acquires if api not in exit_releases]
                extra_in_exit = [api for api in exit_releases if api not in [
                    _RESOURCE_PAIRS.get(a, (None, None))[1] for a in init_acquires
                ] and api not in init_acquires]
                
                if missing_in_exit:
                    asymmetry_details += f"exit 缺少: {', '.join(missing_in_exit[:5])}; "
                if expected_exit_order != exit_releases[:len(expected_exit_order)]:
                    asymmetry_details += "释放顺序不是逆序"
            
            self._index.init_exit_pairs.append(InitExitPair(
                init_func=init_func,
                exit_func=exit_func,
                init_resources=init_acquires[:20],
                exit_resources=exit_releases[:20],
                is_symmetric=is_symmetric,
                asymmetry_details=asymmetry_details[:200],
            ))

    def _check_sequence_match(self, expected: list[str], actual: list[str]) -> bool:
        """检查释放序列是否与预期（逆序 acquire）匹配"""
        if not expected:
            return True
        
        # 将 acquire API 映射到对应的 release API
        expected_releases = []
        for api in expected:
            if api in _RESOURCE_PAIRS:
                _, release_api = _RESOURCE_PAIRS[api]
                if release_api:
                    expected_releases.append(release_api)
        
        # 检查 actual 是否包含所有预期的 release（顺序可以有额外的）
        actual_idx = 0
        for exp in expected_releases:
            found = False
            while actual_idx < len(actual):
                if actual[actual_idx] == exp:
                    found = True
                    actual_idx += 1
                    break
                actual_idx += 1
            if not found:
                return False
        
        return True
