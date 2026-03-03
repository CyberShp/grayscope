"""融合图构建器 — 一次解析提取所有分析维度。

构建 FusedGraph 数据结构，在单次 tree-sitter 遍历中同时提取:
- 函数定义 + 代码注释
- 调用关系 + 所在分支条件
- 锁操作 + 持有状态
- 共享变量访问
- 协议相关操作 (send/recv/connect/accept)
- 入口点标注 (handler/callback/on_/cmd_)
"""

from __future__ import annotations

import logging
import re
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.analyzers.code_parser import CodeParser, is_available

logger = logging.getLogger(__name__)


@dataclass
class Branch:
    """分支信息"""
    condition: str
    line: int
    branch_type: str  # if, else, switch, case, while, for


@dataclass
class LockOp:
    """锁操作"""
    lock_name: str
    op: str  # acquire, release
    line: int


@dataclass
class SharedAccess:
    """共享变量访问"""
    var_name: str
    access: str  # read, write
    line: int
    lock_held: list[str]


@dataclass
class ProtocolOp:
    """协议操作"""
    op_type: str  # send, recv, connect, accept, close, state_change
    target: str  # socket/fd/connection name
    line: int
    args: list[str]


@dataclass
class FunctionComment:
    """函数注释"""
    text: str
    line: int
    comment_type: str  # block, line, doxygen


@dataclass
class FuncPtrAssignment:
    """函数指针赋值"""
    ptr_name: str  # 指针变量名
    target_func: str  # 指向的函数名
    line: int


@dataclass
class CallbackRegistration:
    """回调函数注册 — 用于执行上下文约束检查（P1）"""
    target_func: str          # 被注册的回调函数名
    registration_api: str     # request_irq, timer_setup, INIT_WORK 等
    execution_context: str    # atomic, process, softirq, workqueue, unknown
    can_sleep: bool           # 执行上下文是否可以睡眠
    file_path: str
    line: int
    constraints: list[str] = field(default_factory=list)  # 约束描述


@dataclass
class FieldAccessEntry:
    """结构体字段访问记录 — 用于并发一致性检查（P2）"""
    struct_expr: str      # 结构体表达式 (如 dev, ctx->dev)
    field_name: str       # 字段名 (如 state, flags)
    access_type: str      # read / write
    line: int
    locks_held: list[str] = field(default_factory=list)  # 访问时持有的锁


@dataclass
class ResourceOp:
    """资源操作（配对操作的一侧）— 用于深度分析"""
    op_type: str        # acquire / release
    resource_kind: str  # memory, fd, lock, refcount, dma, clock, irq, timer, custom
    api_name: str       # malloc, free, mutex_lock, etc.
    resource_id: str    # 资源标识符（变量名/表达式）
    line: int
    in_branch: str      # 所在分支条件，空串表示主路径
    in_error_path: bool # 是否在错误处理路径（goto label 后或 if err 块内）


@dataclass
class ErrorExit:
    """错误退出点 — 用于深度分析"""
    line: int
    exit_type: str      # return, goto, break
    target_label: str   # goto 目标 label，非 goto 时为空
    return_value: str   # 返回值表达式
    condition: str      # 触发退出的条件（如 if (ret < 0)）
    resources_held: list[str] = field(default_factory=list)  # 此时持有的资源 ID


@dataclass
class FusedNode:
    """函数节点 — 融合了分支/锁/协议信息"""
    name: str
    file_path: str
    line_start: int
    line_end: int
    source: str
    params: list[str]
    comments: list[FunctionComment]
    branches: list[Branch]
    lock_ops: list[LockOp]
    shared_var_access: list[SharedAccess]
    protocol_ops: list[ProtocolOp]
    is_entry_point: bool
    entry_point_type: str  # handler, callback, cmd, ioctl, main, thread_entry, none
    func_ptr_assignments: list[FuncPtrAssignment] = field(default_factory=list)
    # 深度分析新增字段
    resource_ops: list[ResourceOp] = field(default_factory=list)  # 资源获取/释放操作
    error_exits: list[ErrorExit] = field(default_factory=list)     # 错误退出点
    callback_registrations: list[CallbackRegistration] = field(default_factory=list)  # 回调注册（P1）
    field_accesses: list[FieldAccessEntry] = field(default_factory=list)  # 结构体字段访问（P2）


@dataclass
class FusedEdge:
    """调用边 — 融合了上下文信息"""
    caller: str
    callee: str
    call_site_line: int
    branch_context: str  # 调用所在的分支条件
    lock_held: list[str]  # 调用点持有的锁
    arg_mapping: list[dict[str, Any]]
    data_flow_tags: list[str]  # external_input, tainted, etc.


@dataclass
class CallChain:
    """预计算的调用链"""
    functions: list[str]  # 函数名序列
    entry_point: str
    entry_type: str  # 入口类型 (handler, callback, cmd, ioctl, main, thread_entry, none)
    depth: int  # 调用链深度
    branch_coverage: list[str]  # 每一步的分支条件
    lock_sequence: list[list[str]]  # 每一步持有的锁
    protocol_sequence: list[str]  # 协议操作序列


@dataclass
class FusedGraph:
    """融合分析图"""
    nodes: dict[str, FusedNode]
    edges: list[FusedEdge]
    call_chains: list[CallChain]
    global_vars: set[str]
    protocol_state_machine: dict[str, Any]

    def to_dict(self) -> dict:
        """序列化为字典（用于 JSON 输出）"""
        return {
            "nodes": {
                name: {
                    "name": node.name,
                    "file_path": node.file_path,
                    "line_start": node.line_start,
                    "line_end": node.line_end,
                    "params": node.params,
                    "comments": [
                        {"text": c.text[:500], "line": c.line, "type": c.comment_type}
                        for c in node.comments
                    ],
                    "branches": [
                        {"condition": b.condition, "line": b.line, "type": b.branch_type}
                        for b in node.branches
                    ],
                    "lock_ops": [
                        {"lock": l.lock_name, "op": l.op, "line": l.line}
                        for l in node.lock_ops
                    ],
                    "shared_var_access": [
                        {"var": s.var_name, "access": s.access, "line": s.line, "locks": s.lock_held}
                        for s in node.shared_var_access
                    ],
                    "protocol_ops": [
                        {"op": p.op_type, "target": p.target, "line": p.line, "args": p.args}
                        for p in node.protocol_ops
                    ],
                    "is_entry_point": node.is_entry_point,
                    "entry_point_type": node.entry_point_type,
                    # 深度分析新增字段
                    "resource_ops": [
                        {
                            "op_type": r.op_type,
                            "resource_kind": r.resource_kind,
                            "api_name": r.api_name,
                            "resource_id": r.resource_id,
                            "line": r.line,
                            "in_branch": r.in_branch,
                            "in_error_path": r.in_error_path,
                        }
                        for r in node.resource_ops
                    ],
                    "error_exits": [
                        {
                            "line": e.line,
                            "exit_type": e.exit_type,
                            "target_label": e.target_label,
                            "return_value": e.return_value,
                            "condition": e.condition,
                            "resources_held": e.resources_held,
                        }
                        for e in node.error_exits
                    ],
                    "callback_registrations": [
                        {
                            "target_func": cb.target_func,
                            "registration_api": cb.registration_api,
                            "execution_context": cb.execution_context,
                            "can_sleep": cb.can_sleep,
                            "file_path": cb.file_path,
                            "line": cb.line,
                            "constraints": cb.constraints,
                        }
                        for cb in node.callback_registrations
                    ],
                    "field_accesses": [
                        {
                            "struct_expr": fa.struct_expr,
                            "field_name": fa.field_name,
                            "access_type": fa.access_type,
                            "line": fa.line,
                            "locks_held": fa.locks_held,
                        }
                        for fa in node.field_accesses
                    ],
                }
                for name, node in self.nodes.items()
            },
            "edges": [
                {
                    "caller": e.caller,
                    "callee": e.callee,
                    "line": e.call_site_line,
                    "branch_context": e.branch_context,
                    "lock_held": e.lock_held,
                    "arg_mapping": e.arg_mapping,
                    "data_flow_tags": e.data_flow_tags,
                }
                for e in self.edges
            ],
            "call_chains": [
                {
                    "functions": c.functions,
                    "entry_point": c.entry_point,
                    "entry_type": c.entry_type,
                    "depth": c.depth,
                    "branch_coverage": c.branch_coverage,
                    "lock_sequence": c.lock_sequence,
                    "protocol_sequence": c.protocol_sequence,
                }
                for c in self.call_chains
            ],
            "global_vars": sorted(self.global_vars),
            "protocol_state_machine": self.protocol_state_machine,
        }


# ========== 正则模式 ==========

_CALL_RE = re.compile(r"\b([a-zA-Z_]\w*)\s*\(([^)]*)\)")

_LOCK_ACQUIRE_RE = re.compile(
    r"\b(pthread_mutex_lock|pthread_spin_lock|spin_lock|mutex_lock|"
    r"pthread_rwlock_rdlock|pthread_rwlock_wrlock|sem_wait|"
    r"EnterCriticalSection|AcquireSRWLock\w*)\s*\(\s*&?\s*(\w+)"
)
_LOCK_RELEASE_RE = re.compile(
    r"\b(pthread_mutex_unlock|pthread_spin_unlock|spin_unlock|mutex_unlock|"
    r"pthread_rwlock_unlock|sem_post|"
    r"LeaveCriticalSection|ReleaseSRWLock\w*)\s*\(\s*&?\s*(\w+)"
)

_GLOBAL_VAR_RE = re.compile(
    r"^(?:static\s+)?(?:volatile\s+)?(?:(?:int|char|void|unsigned|long|short|"
    r"size_t|uint\d+_t|int\d+_t|bool|float|double|struct\s+\w+|"
    r"\w+_t)\s*\*?\s+)(\w+)\s*(?:=|;|\[)",
    re.MULTILINE,
)

_PROTOCOL_OPS_RE = re.compile(
    r"\b(send|recv|read|write|connect|accept|close|socket|"
    r"ioctl|fcntl|poll|select|epoll_wait|sendto|recvfrom|"
    r"sendmsg|recvmsg|shutdown)\s*\("
)

_ENTRY_POINT_PATTERNS = [
    (re.compile(r"_handler$|_Handler$|Handler$"), "handler"),
    (re.compile(r"_callback$|_Callback$|Callback$|_cb$"), "callback"),
    (re.compile(r"^on_|^On"), "callback"),
    (re.compile(r"^cmd_|^CMD_|_cmd$"), "cmd"),
    (re.compile(r"^ioctl_|_ioctl$|_IOCTL$"), "ioctl"),
    (re.compile(r"^process_|_process$"), "handler"),
    (re.compile(r"^main$"), "main"),
    (re.compile(r"_thread$|Thread$|_task$|Task$"), "thread_entry"),
]

_IGNORE_CALLS = {
    "if", "else", "while", "for", "switch", "case", "return", "sizeof",
    "typeof", "defined", "do", "goto", "break", "continue", "struct",
    "union", "enum", "typedef", "static", "extern", "inline", "const",
    "volatile", "register", "auto", "void", "int", "char", "short",
    "long", "float", "double", "unsigned", "signed", "bool",
    "printf", "fprintf", "sprintf", "snprintf", "assert",
    "malloc", "free", "calloc", "realloc", "memcpy", "memset", "strlen",
    "strcmp", "strncmp", "strcpy", "strncpy", "strcat",
    "NULL", "TRUE", "FALSE", "true", "false",
}

# 函数指针赋值识别模式
# 匹配: ptr = func_name, ptr = &func_name, struct.member = func_name, array[i] = func_name
# 以及声明式: void (*ptr)(int) = func_name
_FUNC_PTR_ASSIGN_RE = re.compile(
    r"(?:"
    # 声明式: type (*name)(params) = func
    r"\(\s*\*\s*(\w+)\s*\)\s*\([^)]*\)\s*=\s*&?\s*([a-zA-Z_]\w*)"
    r"|"
    # 赋值式: name = func
    r"(\w+(?:\.\w+|\[\w+\])?)\s*=\s*&?\s*([a-zA-Z_]\w*)"
    r")\s*[;,)]"
)

# typedef 识别模式
_TYPEDEF_RE = re.compile(
    r"typedef\s+(?:[\w\s*]+)\s+(\w+)\s*;",
    re.MULTILINE,
)

# typedef 函数指针识别模式: typedef ret_type (*name)(params);
_TYPEDEF_FUNCPTR_RE = re.compile(
    r"typedef\s+[\w\s*]+\s*\(\s*\*\s*(\w+)\s*\)\s*\([^)]*\)\s*;"
)

# 锁宏识别模式
_LOCK_MACRO_RE = re.compile(
    r"\b(LOCK_GUARD|SCOPED_LOCK|WITH_LOCK|MUTEX_LOCK|SPIN_LOCK|"
    r"RW_LOCK_READ|RW_LOCK_WRITE|AUTO_LOCK|GUARD|LOCK)\s*\(\s*&?\s*(\w+)"
)

# 宏定义展开识别: #define MACRO(args) real_func(args)
_MACRO_FUNC_DEF_RE = re.compile(
    r"#define\s+(\w+)\s*\([^)]*\)\s+(\w+)\s*\("
)

# ========== 深度分析：资源操作模式 ==========
# 配对操作表（方法论 2.1）：acquire -> release
_RESOURCE_PAIRS: dict[str, tuple[str, str]] = {
    # 内存分配
    "malloc": ("memory", "free"),
    "calloc": ("memory", "free"),
    "realloc": ("memory", "free"),
    "strdup": ("memory", "free"),
    "strndup": ("memory", "free"),
    "kmalloc": ("memory", "kfree"),
    "kzalloc": ("memory", "kfree"),
    "kcalloc": ("memory", "kfree"),
    "vmalloc": ("memory", "vfree"),
    "vzalloc": ("memory", "vfree"),
    "devm_kmalloc": ("memory", None),  # devm_ 系列由框架自动释放
    "devm_kzalloc": ("memory", None),
    # 文件/套接字
    "open": ("fd", "close"),
    "fopen": ("fd", "fclose"),
    "socket": ("fd", "close"),
    "accept": ("fd", "close"),
    "dup": ("fd", "close"),
    "dup2": ("fd", "close"),
    "pipe": ("fd", "close"),
    "epoll_create": ("fd", "close"),
    "epoll_create1": ("fd", "close"),
    "eventfd": ("fd", "close"),
    "timerfd_create": ("fd", "close"),
    "signalfd": ("fd", "close"),
    "inotify_init": ("fd", "close"),
    "inotify_init1": ("fd", "close"),
    # 锁（这些已经在 lock_ops 中处理，这里记录为配对资源）
    "pthread_mutex_lock": ("lock", "pthread_mutex_unlock"),
    "pthread_spin_lock": ("lock", "pthread_spin_unlock"),
    "pthread_rwlock_rdlock": ("lock", "pthread_rwlock_unlock"),
    "pthread_rwlock_wrlock": ("lock", "pthread_rwlock_unlock"),
    "mutex_lock": ("lock", "mutex_unlock"),
    "spin_lock": ("lock", "spin_unlock"),
    "spin_lock_irq": ("lock", "spin_unlock_irq"),
    "spin_lock_irqsave": ("lock", "spin_unlock_irqrestore"),
    "read_lock": ("lock", "read_unlock"),
    "write_lock": ("lock", "write_unlock"),
    "down": ("lock", "up"),
    "down_read": ("lock", "up_read"),
    "down_write": ("lock", "up_write"),
    "sem_wait": ("lock", "sem_post"),
    "EnterCriticalSection": ("lock", "LeaveCriticalSection"),
    # 引用计数
    "kref_get": ("refcount", "kref_put"),
    "get_device": ("refcount", "put_device"),
    "kobject_get": ("refcount", "kobject_put"),
    "module_get": ("refcount", "module_put"),
    "AddRef": ("refcount", "Release"),
    # DMA/MMIO
    "dma_map_single": ("dma", "dma_unmap_single"),
    "dma_map_page": ("dma", "dma_unmap_page"),
    "dma_map_sg": ("dma", "dma_unmap_sg"),
    "ioremap": ("mmio", "iounmap"),
    "ioremap_nocache": ("mmio", "iounmap"),
    "pci_iomap": ("mmio", "pci_iounmap"),
    # 时钟/电源
    "clk_prepare_enable": ("clock", "clk_disable_unprepare"),
    "clk_enable": ("clock", "clk_disable"),
    "pm_runtime_get_sync": ("power", "pm_runtime_put"),
    "pm_runtime_get": ("power", "pm_runtime_put"),
    # 定时器/工作队列
    "timer_setup": ("timer", "del_timer_sync"),
    "mod_timer": ("timer", "del_timer"),
    "add_timer": ("timer", "del_timer"),
    "queue_work": ("workqueue", "cancel_work_sync"),
    "queue_delayed_work": ("workqueue", "cancel_delayed_work_sync"),
    "schedule_work": ("workqueue", "cancel_work_sync"),
    # 设备/中断注册
    "request_irq": ("irq", "free_irq"),
    "request_threaded_irq": ("irq", "free_irq"),
    "devm_request_irq": ("irq", None),  # devm_ 系列自动释放
    "register_chrdev": ("device", "unregister_chrdev"),
    "register_netdev": ("device", "unregister_netdev"),
    "platform_device_register": ("device", "platform_device_unregister"),
    # 中断/抢占禁用
    "local_irq_disable": ("irq_state", "local_irq_enable"),
    "local_irq_save": ("irq_state", "local_irq_restore"),
    "preempt_disable": ("preempt", "preempt_enable"),
    # RCU
    "rcu_read_lock": ("rcu", "rcu_read_unlock"),
    "rcu_read_lock_bh": ("rcu", "rcu_read_unlock_bh"),
    "rcu_read_lock_sched": ("rcu", "rcu_read_unlock_sched"),
}

# 构建资源获取正则
_RESOURCE_ACQUIRE_APIS = "|".join(re.escape(api) for api in _RESOURCE_PAIRS.keys())
_RESOURCE_ACQUIRE_RE = re.compile(
    rf"\b({_RESOURCE_ACQUIRE_APIS})\s*\(\s*([^,)]*)"
)

# 构建资源释放正则
_RELEASE_APIS: set[str] = set()
for _, (_, release) in _RESOURCE_PAIRS.items():
    if release:
        _RELEASE_APIS.add(release)
_RESOURCE_RELEASE_APIS = "|".join(re.escape(api) for api in _RELEASE_APIS)
_RESOURCE_RELEASE_RE = re.compile(
    rf"\b({_RESOURCE_RELEASE_APIS})\s*\(\s*([^,)]*)"
)

# 错误退出点模式
_ERROR_RETURN_RE = re.compile(
    r"\breturn\s+([^;]+);",
    re.MULTILINE,
)
_GOTO_RE = re.compile(
    r"\bgoto\s+(\w+)\s*;",
)
_LABEL_RE = re.compile(
    r"^(\w+)\s*:",
    re.MULTILINE,
)
# 错误条件检测模式
_ERROR_CONDITION_RE = re.compile(
    r"\bif\s*\(\s*(!?\s*\w+|[^)]+[<>=!]+[^)]+)\s*\)",
)

# ========== 回调注册 API → 执行上下文映射（P1 回调约束检查） ==========
_CALLBACK_REGISTRATION_MAP: dict[str, tuple[str, bool]] = {
    # (execution_context, can_sleep)
    # 中断相关
    "request_irq": ("atomic", False),
    "request_threaded_irq": ("process", True),  # threaded handler 在进程上下文
    "devm_request_irq": ("atomic", False),
    "devm_request_threaded_irq": ("process", True),
    "setup_irq": ("atomic", False),
    # 定时器
    "timer_setup": ("softirq", False),
    "mod_timer": ("softirq", False),
    "add_timer": ("softirq", False),
    "init_timer": ("softirq", False),
    "hrtimer_init": ("softirq", False),
    "hrtimer_start": ("softirq", False),
    # tasklet
    "tasklet_init": ("softirq", False),
    "tasklet_setup": ("softirq", False),
    "tasklet_schedule": ("softirq", False),
    # 工作队列
    "INIT_WORK": ("process", True),
    "INIT_DELAYED_WORK": ("process", True),
    "queue_work": ("process", True),
    "queue_delayed_work": ("process", True),
    "schedule_work": ("process", True),
    "schedule_delayed_work": ("process", True),
    # 内核线程
    "kthread_create": ("process", True),
    "kthread_run": ("process", True),
    "kernel_thread": ("process", True),
    # POSIX 线程
    "pthread_create": ("process", True),
    # notifier
    "register_netdevice_notifier": ("unknown", False),
    "register_reboot_notifier": ("process", True),
    "register_pm_notifier": ("process", True),
    # 其他回调注册
    "register_console": ("atomic", False),
    "register_nmi_handler": ("atomic", False),
}

# 构建回调注册 API 正则
_CALLBACK_APIS = "|".join(re.escape(api) for api in _CALLBACK_REGISTRATION_MAP.keys())
_CALLBACK_REGISTRATION_RE = re.compile(
    rf"\b({_CALLBACK_APIS})\s*\([^)]*[,\s]&?\s*(\w+)\s*[,)]"
)


class FusedGraphBuilder:
    """融合图构建器"""

    def __init__(self) -> None:
        if not is_available():
            raise RuntimeError("tree-sitter grammars not available")
        self._parser = CodeParser()
        self._graph: FusedGraph | None = None
        # 新增: typedef 映射 (new_type -> original_type)
        self._typedefs: dict[str, str] = {}
        # 新增: 函数指针映射 (ptr_name -> func_name), 全局级别
        self._global_func_ptr_map: dict[str, str] = {}
        # 新增: 宏-函数映射 (macro_name -> real_func_name)
        self._macro_expansions: dict[str, str] = {}

    def build(
        self, 
        workspace_path: str, 
        max_files: int = 500,
        parallel_workers: int | None = None,
    ) -> FusedGraph:
        """构建融合图
        
        Args:
            workspace_path: 工作区路径
            max_files: 最大解析文件数
            parallel_workers: 并行工作线程数，默认为 CPU 核心数
        """
        workspace = Path(workspace_path)
        
        self._graph = FusedGraph(
            nodes={},
            edges=[],
            call_chains=[],
            global_vars=set(),
            protocol_state_machine={},
        )

        # 收集待解析文件
        files = self._collect_files(workspace, max_files)
        if not files:
            return self._graph

        # Pass 0: 预扫描收集 typedef 和宏定义（需要先收集这些才能构建动态正则）
        file_contents = self._prescan_files(files)

        # 构建动态全局变量正则（包含 typedef 类型）
        dynamic_global_var_re = self._build_global_var_regex()

        # Pass 1: 并行解析文件，收集全局变量和函数定义
        parse_results = self._parallel_parse_files(
            files, workspace, file_contents, dynamic_global_var_re, parallel_workers
        )

        # 合并解析结果
        function_sources, defined_functions = self._merge_parse_results(parse_results)

        # Pass 2: 为每个函数提取详细信息
        for fn_name, fn_source, file_path, line_start, line_end in function_sources:
            node = self._build_fused_node(
                fn_name, fn_source, file_path, line_start, line_end
            )
            self._graph.nodes[fn_name] = node

            # 提取调用边
            edges = self._extract_fused_edges(
                fn_name, fn_source, line_start, defined_functions, node
            )
            self._graph.edges.extend(edges)

        # Pass 3: 识别入口点
        self._identify_entry_points()

        # Pass 4: 构建调用链
        self._build_call_chains()

        # Pass 5: 提取协议状态机
        self._extract_protocol_state_machine()

        return self._graph

    def _collect_files(self, workspace: Path, max_files: int) -> list[Path]:
        """收集待解析文件"""
        exts = {".c", ".h", ".cpp", ".cc", ".cxx", ".hpp"}
        files = sorted(
            [p for p in workspace.rglob("*") if p.suffix in exts and p.is_file()]
        )[:max_files]
        return files

    def _prescan_files(self, files: list[Path]) -> dict[Path, str]:
        """预扫描文件，收集 typedef 和宏定义"""
        file_contents: dict[Path, str] = {}
        
        for fpath in files:
            try:
                source_text = fpath.read_text(errors="replace")
                file_contents[fpath] = source_text
                
                # 收集 typedef 定义
                for m in _TYPEDEF_RE.finditer(source_text):
                    typedef_name = m.group(1)
                    self._typedefs[typedef_name] = typedef_name
                for m in _TYPEDEF_FUNCPTR_RE.finditer(source_text):
                    self._typedefs[m.group(1)] = "funcptr"
                
                # 收集宏-函数映射
                for m in _MACRO_FUNC_DEF_RE.finditer(source_text):
                    macro_name, real_func = m.group(1), m.group(2)
                    self._macro_expansions[macro_name] = real_func
            except Exception as exc:
                logger.warning("预扫描文件失败 %s: %s", fpath, exc)
        
        return file_contents

    def _parse_single_file(
        self,
        fpath: Path,
        workspace: Path,
        file_contents: dict[Path, str],
        global_var_re: re.Pattern[str],
    ) -> tuple[list[tuple[str, str, str, int, int]], set[str], set[str]]:
        """解析单个文件
        
        Returns:
            (function_sources, defined_functions, global_vars)
        """
        function_sources: list[tuple[str, str, str, int, int]] = []
        defined_functions: set[str] = set()
        global_vars: set[str] = set()
        
        try:
            source_text = file_contents.get(fpath)
            if source_text is None:
                source_text = fpath.read_text(errors="replace")
            
            # 收集全局变量
            for m in global_var_re.finditer(source_text):
                global_vars.add(m.group(1))

            # 解析函数
            symbols = self._parser.parse_file(fpath)
            rel_path = str(fpath.relative_to(workspace)) if workspace else str(fpath)

            for sym in symbols:
                if sym.kind == "function":
                    defined_functions.add(sym.name)
                    function_sources.append((
                        sym.name, sym.source, rel_path,
                        sym.line_start, sym.line_end
                    ))
        except Exception as exc:
            logger.warning("解析文件失败 %s: %s", fpath, exc)
        
        return function_sources, defined_functions, global_vars

    def _parallel_parse_files(
        self,
        files: list[Path],
        workspace: Path,
        file_contents: dict[Path, str],
        global_var_re: re.Pattern[str],
        workers: int | None = None,
    ) -> list[tuple[list[tuple[str, str, str, int, int]], set[str], set[str]]]:
        """并行解析多个文件"""
        import os
        from concurrent.futures import ThreadPoolExecutor
        
        if workers is None:
            workers = min(os.cpu_count() or 4, len(files), 8)
        
        # 对于小文件集，串行处理可能更快
        if len(files) < 4:
            return [
                self._parse_single_file(f, workspace, file_contents, global_var_re)
                for f in files
            ]
        
        results = []
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = [
                executor.submit(
                    self._parse_single_file, f, workspace, file_contents, global_var_re
                )
                for f in files
            ]
            for future in futures:
                try:
                    results.append(future.result())
                except Exception as exc:
                    logger.warning("并行解析任务失败: %s", exc)
                    results.append(([], set(), set()))
        
        return results

    def _merge_parse_results(
        self,
        results: list[tuple[list[tuple[str, str, str, int, int]], set[str], set[str]]],
    ) -> tuple[list[tuple[str, str, str, int, int]], set[str]]:
        """合并解析结果"""
        function_sources: list[tuple[str, str, str, int, int]] = []
        defined_functions: set[str] = set()
        
        for fn_sources, fn_names, global_vars in results:
            function_sources.extend(fn_sources)
            defined_functions.update(fn_names)
            self._graph.global_vars.update(global_vars)
        
        return function_sources, defined_functions

    def _build_fused_node(
        self,
        fn_name: str,
        fn_source: str,
        file_path: str,
        line_start: int,
        line_end: int,
    ) -> FusedNode:
        """构建融合函数节点"""
        # 提取参数
        params = self._extract_params(fn_source, fn_name)

        # 提取注释
        comments = self._extract_comments(fn_source, line_start)

        # 提取分支
        branches = self._extract_branches(fn_source, line_start)

        # 提取锁操作
        lock_ops = self._extract_lock_ops(fn_source, line_start)

        # 计算当前持有的锁（简化：按行号顺序累积）
        held_locks: list[str] = []
        lock_state_by_line: dict[int, list[str]] = {}
        for lop in sorted(lock_ops, key=lambda x: x.line):
            if lop.op == "acquire":
                held_locks.append(lop.lock_name)
            elif lop.op == "release" and lop.lock_name in held_locks:
                held_locks.remove(lop.lock_name)
            lock_state_by_line[lop.line] = list(held_locks)

        # 提取共享变量访问
        shared_var_access = self._extract_shared_var_access(
            fn_source, line_start, lock_state_by_line
        )

        # 提取协议操作
        protocol_ops = self._extract_protocol_ops(fn_source, line_start)

        # 检查是否为入口点
        is_entry, entry_type = self._check_entry_point(fn_name)

        # 提取函数指针赋值
        func_ptr_assignments = self._extract_func_ptr_assignments(fn_source, line_start)

        # 深度分析：提取资源操作（P0 核心）
        resource_ops = self._extract_resource_ops(fn_source, line_start, branches)

        # 深度分析：提取错误退出点（P0 核心）
        error_exits = self._extract_error_exits(fn_source, line_start, resource_ops)

        # 深度分析：提取回调注册（P1 回调约束检查）
        callback_registrations = self._extract_callback_registrations(fn_source, file_path, line_start)

        # 深度分析：提取结构体字段访问（P2 并发一致性检查）
        field_accesses = self._extract_field_accesses(fn_source, line_start, lock_state_by_line)

        return FusedNode(
            name=fn_name,
            file_path=file_path,
            line_start=line_start,
            line_end=line_end,
            source=fn_source,
            params=params,
            comments=comments,
            branches=branches,
            lock_ops=lock_ops,
            shared_var_access=shared_var_access,
            protocol_ops=protocol_ops,
            is_entry_point=is_entry,
            entry_point_type=entry_type,
            func_ptr_assignments=func_ptr_assignments,
            resource_ops=resource_ops,
            error_exits=error_exits,
            callback_registrations=callback_registrations,
            field_accesses=field_accesses,
        )

    def _extract_params(self, source: str, fn_name: str) -> list[str]:
        """提取函数参数"""
        pattern = re.compile(rf"\b{re.escape(fn_name)}\s*\(([^)]*)\)", re.DOTALL)
        m = pattern.search(source)
        if not m:
            return []
        
        param_str = m.group(1).strip()
        if not param_str or param_str == "void":
            return []

        params = []
        for part in param_str.split(","):
            part = part.strip()
            if not part:
                continue
            tokens = re.findall(r"[a-zA-Z_]\w*", part)
            if tokens:
                name = tokens[-1]
                type_keywords = {
                    "int", "char", "void", "short", "long", "float", "double",
                    "unsigned", "signed", "const", "volatile", "struct", "union",
                    "enum", "static", "extern", "inline", "bool", "size_t",
                }
                if name not in type_keywords:
                    params.append(name)
        return params

    def _extract_comments(self, source: str, line_start: int) -> list[FunctionComment]:
        """提取函数内和函数前的注释"""
        comments: list[FunctionComment] = []
        
        # 块注释
        for m in re.finditer(r"/\*[\s\S]*?\*/", source):
            text = m.group(0)
            line_offset = source[:m.start()].count("\n")
            comment_type = "doxygen" if text.startswith("/**") else "block"
            comments.append(FunctionComment(
                text=text.strip(),
                line=line_start + line_offset,
                comment_type=comment_type,
            ))

        # 行注释
        for m in re.finditer(r"//[^\n]*", source):
            text = m.group(0)
            line_offset = source[:m.start()].count("\n")
            comments.append(FunctionComment(
                text=text.strip(),
                line=line_start + line_offset,
                comment_type="line",
            ))

        return comments

    def _extract_branches(self, source: str, line_start: int) -> list[Branch]:
        """提取分支结构"""
        branches: list[Branch] = []
        lines = source.split("\n")

        for line_idx, line in enumerate(lines):
            # if 语句
            m = re.search(r"\bif\s*\(([^)]+)\)", line)
            if m:
                branches.append(Branch(
                    condition=m.group(1).strip(),
                    line=line_start + line_idx,
                    branch_type="if",
                ))

            # else if
            m = re.search(r"\belse\s+if\s*\(([^)]+)\)", line)
            if m:
                branches.append(Branch(
                    condition=m.group(1).strip(),
                    line=line_start + line_idx,
                    branch_type="else_if",
                ))

            # else
            if re.search(r"\belse\s*{", line):
                branches.append(Branch(
                    condition="else",
                    line=line_start + line_idx,
                    branch_type="else",
                ))

            # switch
            m = re.search(r"\bswitch\s*\(([^)]+)\)", line)
            if m:
                branches.append(Branch(
                    condition=m.group(1).strip(),
                    line=line_start + line_idx,
                    branch_type="switch",
                ))

            # case
            m = re.search(r"\bcase\s+([^:]+):", line)
            if m:
                branches.append(Branch(
                    condition=m.group(1).strip(),
                    line=line_start + line_idx,
                    branch_type="case",
                ))

            # while
            m = re.search(r"\bwhile\s*\(([^)]+)\)", line)
            if m:
                branches.append(Branch(
                    condition=m.group(1).strip(),
                    line=line_start + line_idx,
                    branch_type="while",
                ))

            # for
            m = re.search(r"\bfor\s*\(([^)]+)\)", line)
            if m:
                branches.append(Branch(
                    condition=m.group(1).strip(),
                    line=line_start + line_idx,
                    branch_type="for",
                ))

        return branches

    def _extract_lock_ops(self, source: str, line_start: int) -> list[LockOp]:
        """提取锁操作"""
        ops: list[LockOp] = []

        for m in _LOCK_ACQUIRE_RE.finditer(source):
            line_offset = source[:m.start()].count("\n")
            ops.append(LockOp(
                lock_name=m.group(2),
                op="acquire",
                line=line_start + line_offset,
            ))

        for m in _LOCK_RELEASE_RE.finditer(source):
            line_offset = source[:m.start()].count("\n")
            ops.append(LockOp(
                lock_name=m.group(2),
                op="release",
                line=line_start + line_offset,
            ))

        # 识别锁宏 (LOCK_GUARD, SCOPED_LOCK, etc.)
        # 这些宏通常在作用域内自动获取和释放锁
        for m in _LOCK_MACRO_RE.finditer(source):
            line_offset = source[:m.start()].count("\n")
            macro_name = m.group(1)
            lock_name = m.group(2)
            
            # 锁宏视为 acquire (作用域结束自动 release)
            ops.append(LockOp(
                lock_name=lock_name,
                op="acquire",
                line=line_start + line_offset,
            ))
            
            # 对于 SCOPED/GUARD 类型的宏，在函数末尾自动释放
            # 这里简化处理：不添加显式 release，因为作用域自动管理

        return ops

    def _extract_shared_var_access(
        self,
        source: str,
        line_start: int,
        lock_state_by_line: dict[int, list[str]],
    ) -> list[SharedAccess]:
        """提取共享变量访问"""
        accesses: list[SharedAccess] = []
        
        if not self._graph or not self._graph.global_vars:
            return accesses

        # Pre-compile combined regex patterns for all global vars (O(1) per line vs O(N))
        gv_names = "|".join(re.escape(gv) for gv in self._graph.global_vars)
        write_re = re.compile(rf"\b({gv_names})\s*(?:=(?!=)|[+\-*/&|^]=|\+\+|--)")
        read_re = re.compile(rf"\b({gv_names})\b")

        lines = source.split("\n")
        for line_idx, line in enumerate(lines):
            actual_line = line_start + line_idx
            # 找最近的锁状态
            held_locks = []
            for ln in sorted(lock_state_by_line.keys()):
                if ln <= actual_line:
                    held_locks = lock_state_by_line[ln]
                else:
                    break

            # Check for write access
            write_matches = write_re.findall(line)
            for gv in write_matches:
                accesses.append(SharedAccess(
                    var_name=gv,
                    access="write",
                    line=actual_line,
                    lock_held=list(held_locks),
                ))
            
            # Check for read access (excluding already-matched writes)
            written_vars = set(write_matches)
            read_matches = read_re.findall(line)
            for gv in read_matches:
                if gv not in written_vars:
                    accesses.append(SharedAccess(
                        var_name=gv,
                        access="read",
                        line=actual_line,
                        lock_held=list(held_locks),
                    ))

        return accesses

    def _extract_protocol_ops(self, source: str, line_start: int) -> list[ProtocolOp]:
        """提取协议相关操作"""
        ops: list[ProtocolOp] = []
        
        for m in _PROTOCOL_OPS_RE.finditer(source):
            op_name = m.group(1)
            line_offset = source[:m.start()].count("\n")
            
            # 尝试提取参数
            remaining = source[m.end():]
            args_match = re.match(r"([^)]*)\)", remaining)
            args = []
            if args_match:
                args_str = args_match.group(1)
                args = [a.strip() for a in args_str.split(",") if a.strip()]

            op_type = "send" if op_name in ("send", "sendto", "sendmsg", "write") else \
                      "recv" if op_name in ("recv", "recvfrom", "recvmsg", "read") else \
                      "connect" if op_name == "connect" else \
                      "accept" if op_name == "accept" else \
                      "close" if op_name in ("close", "shutdown") else \
                      "io_control"

            target = args[0] if args else ""
            
            ops.append(ProtocolOp(
                op_type=op_type,
                target=target[:50],
                line=line_start + line_offset,
                args=args[:5],
            ))

        return ops

    def _extract_resource_ops(
        self, source: str, line_start: int, branches: list[Branch]
    ) -> list[ResourceOp]:
        """提取资源获取/释放操作（深度分析 P0 核心）
        
        识别标准 C/C++ 配对操作（方法论 2.1）以及项目自定义配对函数。
        """
        ops: list[ResourceOp] = []
        lines = source.split("\n")
        
        # 构建分支条件映射：line -> branch_condition
        branch_conditions: dict[int, str] = {}
        current_branch = ""
        for b in sorted(branches, key=lambda x: x.line):
            branch_conditions[b.line] = b.condition
        
        # 检测 error_out/cleanup label 位置
        error_labels: set[int] = set()
        for m in _LABEL_RE.finditer(source):
            label = m.group(1).lower()
            if any(x in label for x in ("err", "out", "fail", "cleanup", "exit", "error")):
                line_offset = source[:m.start()].count("\n")
                error_labels.add(line_start + line_offset)
        
        for line_idx, line in enumerate(lines):
            actual_line = line_start + line_idx
            
            # 确定当前所在分支
            in_branch = ""
            for bl, cond in branch_conditions.items():
                if bl <= actual_line:
                    in_branch = cond
            
            # 检测是否在错误路径（在 error label 之后）
            in_error_path = any(actual_line > el for el in error_labels)
            
            # 检测资源获取
            for m in _RESOURCE_ACQUIRE_RE.finditer(line):
                api_name = m.group(1)
                resource_id = m.group(2).strip() if m.group(2) else ""
                
                if api_name in _RESOURCE_PAIRS:
                    resource_kind, _ = _RESOURCE_PAIRS[api_name]
                    ops.append(ResourceOp(
                        op_type="acquire",
                        resource_kind=resource_kind,
                        api_name=api_name,
                        resource_id=resource_id[:100],
                        line=actual_line,
                        in_branch=in_branch[:200],
                        in_error_path=in_error_path,
                    ))
            
            # 检测资源释放
            for m in _RESOURCE_RELEASE_RE.finditer(line):
                api_name = m.group(1)
                resource_id = m.group(2).strip() if m.group(2) else ""
                
                # 反向查找对应的 resource_kind
                resource_kind = "unknown"
                for acquire_api, (kind, release_api) in _RESOURCE_PAIRS.items():
                    if release_api == api_name:
                        resource_kind = kind
                        break
                
                ops.append(ResourceOp(
                    op_type="release",
                    resource_kind=resource_kind,
                    api_name=api_name,
                    resource_id=resource_id[:100],
                    line=actual_line,
                    in_branch=in_branch[:200],
                    in_error_path=in_error_path,
                ))
        
        # 识别项目自定义配对函数（命名惯例推断）
        ops.extend(self._extract_custom_resource_ops(source, line_start, branch_conditions, error_labels))
        
        return ops

    def _extract_custom_resource_ops(
        self,
        source: str,
        line_start: int,
        branch_conditions: dict[int, str],
        error_labels: set[int],
    ) -> list[ResourceOp]:
        """识别项目自定义的配对函数（通过命名惯例推断）
        
        惯例：xxx_init/xxx_deinit, xxx_acquire/xxx_release, xxx_open/xxx_close,
              xxx_alloc/xxx_free, xxx_get/xxx_put, xxx_lock/xxx_unlock
        """
        ops: list[ResourceOp] = []
        lines = source.split("\n")
        
        # 配对后缀模式
        acquire_patterns = [
            (r"\b(\w+)_init\s*\(", "_init", "custom"),
            (r"\b(\w+)_acquire\s*\(", "_acquire", "custom"),
            (r"\b(\w+)_open\s*\(", "_open", "custom"),
            (r"\b(\w+)_alloc\s*\(", "_alloc", "custom"),
            (r"\b(\w+)_get\s*\(", "_get", "custom"),
            (r"\b(\w+)_create\s*\(", "_create", "custom"),
            (r"\b(\w+)_start\s*\(", "_start", "custom"),
            (r"\b(\w+)_enable\s*\(", "_enable", "custom"),
        ]
        release_patterns = [
            (r"\b(\w+)_deinit\s*\(", "_deinit", "custom"),
            (r"\b(\w+)_release\s*\(", "_release", "custom"),
            (r"\b(\w+)_close\s*\(", "_close", "custom"),
            (r"\b(\w+)_free\s*\(", "_free", "custom"),
            (r"\b(\w+)_put\s*\(", "_put", "custom"),
            (r"\b(\w+)_destroy\s*\(", "_destroy", "custom"),
            (r"\b(\w+)_stop\s*\(", "_stop", "custom"),
            (r"\b(\w+)_disable\s*\(", "_disable", "custom"),
        ]
        
        for line_idx, line in enumerate(lines):
            actual_line = line_start + line_idx
            
            # 确定当前所在分支
            in_branch = ""
            for bl, cond in branch_conditions.items():
                if bl <= actual_line:
                    in_branch = cond
            
            in_error_path = any(actual_line > el for el in error_labels)
            
            # 检测自定义 acquire
            for pattern, suffix, kind in acquire_patterns:
                for m in re.finditer(pattern, line):
                    prefix = m.group(1)
                    api_name = f"{prefix}{suffix}"
                    # 排除标准库函数（已在主列表中处理）
                    if api_name in _RESOURCE_PAIRS:
                        continue
                    ops.append(ResourceOp(
                        op_type="acquire",
                        resource_kind=kind,
                        api_name=api_name,
                        resource_id=prefix,
                        line=actual_line,
                        in_branch=in_branch[:200],
                        in_error_path=in_error_path,
                    ))
            
            # 检测自定义 release
            for pattern, suffix, kind in release_patterns:
                for m in re.finditer(pattern, line):
                    prefix = m.group(1)
                    api_name = f"{prefix}{suffix}"
                    ops.append(ResourceOp(
                        op_type="release",
                        resource_kind=kind,
                        api_name=api_name,
                        resource_id=prefix,
                        line=actual_line,
                        in_branch=in_branch[:200],
                        in_error_path=in_error_path,
                    ))
        
        return ops

    def _extract_error_exits(
        self, source: str, line_start: int, resource_ops: list[ResourceOp]
    ) -> list[ErrorExit]:
        """提取错误退出点（深度分析 P0 核心）
        
        识别 return, goto, break 等可能导致资源泄漏的退出点，
        并计算每个退出点处持有的资源。
        """
        exits: list[ErrorExit] = []
        lines = source.split("\n")
        
        # 按行号排序资源操作，用于计算每个退出点的资源持有状态
        resource_ops_sorted = sorted(resource_ops, key=lambda x: x.line)
        
        # 收集所有 label 定义
        labels: dict[str, int] = {}
        for m in _LABEL_RE.finditer(source):
            label_name = m.group(1)
            line_offset = source[:m.start()].count("\n")
            labels[label_name] = line_start + line_offset
        
        # 检测错误条件上下文
        current_error_condition = ""
        
        for line_idx, line in enumerate(lines):
            actual_line = line_start + line_idx
            
            # 检测错误条件
            err_cond_match = _ERROR_CONDITION_RE.search(line)
            if err_cond_match:
                cond = err_cond_match.group(1)
                # 检测是否为错误检测条件
                if any(x in cond.lower() for x in ("err", "ret", "rc", "status", "< 0", "!= 0", "== null", "== -1", "fail")):
                    current_error_condition = cond
            
            # 计算此行时持有的资源
            resources_held: list[str] = []
            resource_state: dict[str, int] = {}  # resource_id -> count
            for rop in resource_ops_sorted:
                if rop.line <= actual_line:
                    if rop.op_type == "acquire":
                        resource_state[rop.resource_id] = resource_state.get(rop.resource_id, 0) + 1
                    elif rop.op_type == "release" and rop.resource_id in resource_state:
                        resource_state[rop.resource_id] = max(0, resource_state[rop.resource_id] - 1)
            resources_held = [rid for rid, cnt in resource_state.items() if cnt > 0]
            
            # 检测 return
            ret_match = _ERROR_RETURN_RE.search(line)
            if ret_match:
                return_value = ret_match.group(1).strip()
                # 检测是否为错误返回
                is_error_return = any(x in return_value.lower() for x in 
                    ("-1", "null", "err", "fail", "false", "-e", "einval", "enomem", "enoent"))
                
                # 只记录错误路径返回或持有资源的返回
                if is_error_return or resources_held:
                    exits.append(ErrorExit(
                        line=actual_line,
                        exit_type="return",
                        target_label="",
                        return_value=return_value[:100],
                        condition=current_error_condition[:200],
                        resources_held=resources_held[:20],
                    ))
                    current_error_condition = ""  # 重置条件
            
            # 检测 goto
            goto_match = _GOTO_RE.search(line)
            if goto_match:
                target_label = goto_match.group(1)
                exits.append(ErrorExit(
                    line=actual_line,
                    exit_type="goto",
                    target_label=target_label,
                    return_value="",
                    condition=current_error_condition[:200],
                    resources_held=resources_held[:20],
                ))
                current_error_condition = ""
        
        return exits

    def _extract_callback_registrations(
        self, source: str, file_path: str, line_start: int
    ) -> list[CallbackRegistration]:
        """提取回调注册（深度分析 P1 回调约束检查）
        
        识别 request_irq, timer_setup, INIT_WORK 等回调注册 API，
        并推断回调函数的执行上下文约束。
        """
        registrations: list[CallbackRegistration] = []
        lines = source.split("\n")
        
        for line_idx, line in enumerate(lines):
            actual_line = line_start + line_idx
            
            # 使用正则匹配回调注册 API
            for m in _CALLBACK_REGISTRATION_RE.finditer(line):
                api_name = m.group(1)
                target_func = m.group(2)
                
                if api_name in _CALLBACK_REGISTRATION_MAP:
                    execution_context, can_sleep = _CALLBACK_REGISTRATION_MAP[api_name]
                    
                    # 构建约束描述
                    constraints: list[str] = []
                    if not can_sleep:
                        constraints.append("不能调用可睡眠函数（mutex_lock, GFP_KERNEL, msleep等）")
                    if execution_context == "atomic":
                        constraints.append("不能使用 copy_from_user/copy_to_user")
                    if execution_context == "softirq":
                        constraints.append("可被硬中断打断")
                    
                    registrations.append(CallbackRegistration(
                        target_func=target_func,
                        registration_api=api_name,
                        execution_context=execution_context,
                        can_sleep=can_sleep,
                        file_path=file_path,
                        line=actual_line,
                        constraints=constraints,
                    ))
            
            # 检测 INIT_WORK / INIT_DELAYED_WORK 宏（特殊格式）
            work_match = re.search(r"\b(INIT_WORK|INIT_DELAYED_WORK)\s*\(\s*&?\s*\w+\s*,\s*(\w+)\s*\)", line)
            if work_match:
                api_name = work_match.group(1)
                target_func = work_match.group(2)
                
                registrations.append(CallbackRegistration(
                    target_func=target_func,
                    registration_api=api_name,
                    execution_context="process",
                    can_sleep=True,
                    file_path=file_path,
                    line=actual_line,
                    constraints=[],
                ))
        
        return registrations

    def _extract_field_accesses(
        self, source: str, line_start: int, lock_state_by_line: dict[int, list[str]]
    ) -> list[FieldAccessEntry]:
        """提取结构体字段访问（深度分析 P2 并发一致性检查）
        
        识别对结构体字段的读写访问，记录访问时持有的锁，
        用于跨函数汇聚后检测竞态条件。
        """
        accesses: list[FieldAccessEntry] = []
        lines = source.split("\n")
        
        # 匹配结构体字段访问: expr->field 或 expr.field
        # 写访问: expr->field = ..., expr->field++, expr->field |= ...
        # 读访问: ...expr->field... (非赋值左侧)
        field_access_re = re.compile(r"(\w+(?:\[\w+\])?)\s*(?:->|\.)\s*(\w+)")
        write_pattern_re = re.compile(r"(\w+(?:\[\w+\])?)\s*(?:->|\.)\s*(\w+)\s*(?:=(?!=)|[+\-*/&|^]=|\+\+|--)")
        
        for line_idx, line in enumerate(lines):
            actual_line = line_start + line_idx
            
            # 获取当前行的锁状态
            held_locks: list[str] = []
            for ln in sorted(lock_state_by_line.keys()):
                if ln <= actual_line:
                    held_locks = lock_state_by_line[ln]
                else:
                    break
            
            # 检测写访问
            write_matches = set()
            for m in write_pattern_re.finditer(line):
                struct_expr, field_name = m.group(1), m.group(2)
                write_matches.add((struct_expr, field_name))
                accesses.append(FieldAccessEntry(
                    struct_expr=struct_expr[:50],
                    field_name=field_name,
                    access_type="write",
                    line=actual_line,
                    locks_held=list(held_locks),
                ))
            
            # 检测读访问（排除已记录的写访问）
            for m in field_access_re.finditer(line):
                struct_expr, field_name = m.group(1), m.group(2)
                if (struct_expr, field_name) not in write_matches:
                    # 排除常见的非字段名（如关键字）
                    if field_name not in {"if", "else", "while", "for", "return", "sizeof"}:
                        accesses.append(FieldAccessEntry(
                            struct_expr=struct_expr[:50],
                            field_name=field_name,
                            access_type="read",
                            line=actual_line,
                            locks_held=list(held_locks),
                        ))
        
        return accesses

    def _check_entry_point(self, fn_name: str) -> tuple[bool, str]:
        """检查函数是否为入口点"""
        for pattern, entry_type in _ENTRY_POINT_PATTERNS:
            if pattern.search(fn_name):
                return True, entry_type
        return False, "none"

    def _build_global_var_regex(self) -> re.Pattern[str]:
        """构建动态全局变量正则，包含收集到的 typedef 类型"""
        base_types = (
            r"int|char|void|unsigned|long|short|"
            r"size_t|uint\d+_t|int\d+_t|bool|float|double|struct\s+\w+"
        )
        
        # 添加收集到的 typedef 名作为可识别类型
        if self._typedefs:
            typedef_names = "|".join(re.escape(t) for t in self._typedefs.keys())
            type_pattern = f"(?:{base_types}|{typedef_names})"
        else:
            type_pattern = f"(?:{base_types})"
        
        pattern = (
            rf"^(?:static\s+)?(?:volatile\s+)?(?:{type_pattern}\s*\*?\s+)"
            rf"(\w+)\s*(?:=|;|\[)"
        )
        return re.compile(pattern, re.MULTILINE)

    def _extract_func_ptr_assignments(
        self, source: str, line_start: int
    ) -> list[FuncPtrAssignment]:
        """提取函数指针赋值
        
        识别模式:
        - void (*ptr)(int) = func_name (声明式)
        - ptr = func_name
        - ptr = &func_name
        - struct.member = func_name
        - array[i] = func_name
        """
        assignments: list[FuncPtrAssignment] = []
        lines = source.split("\n")
        
        for line_idx, line in enumerate(lines):
            actual_line = line_start + line_idx
            
            for m in _FUNC_PTR_ASSIGN_RE.finditer(line):
                # 新的正则有4组:
                # - Group 1, 2: 声明式 (*ptr)(params) = func
                # - Group 3, 4: 赋值式 ptr = func
                if m.group(1) and m.group(2):
                    ptr_name = m.group(1)
                    target_func = m.group(2)
                elif m.group(3) and m.group(4):
                    ptr_name = m.group(3)
                    target_func = m.group(4)
                else:
                    continue
                
                # 过滤掉明显不是函数赋值的情况
                if target_func in _IGNORE_CALLS:
                    continue
                # 过滤掉数值赋值
                if target_func.isdigit():
                    continue
                # 过滤掉字符串赋值
                if target_func.startswith('"') or target_func.startswith("'"):
                    continue
                
                assignments.append(FuncPtrAssignment(
                    ptr_name=ptr_name,
                    target_func=target_func,
                    line=actual_line,
                ))
        
        return assignments

    def _extract_fused_edges(
        self,
        fn_name: str,
        fn_source: str,
        line_start: int,
        defined_functions: set[str],
        node: FusedNode,
    ) -> list[FusedEdge]:
        """提取带上下文的调用边"""
        edges: list[FusedEdge] = []
        lines = fn_source.split("\n")

        # 构建行号到分支上下文的映射
        branch_context_by_line: dict[int, str] = {}
        current_branch = ""
        for branch in node.branches:
            if branch.branch_type in ("if", "else_if", "switch"):
                current_branch = f"{branch.branch_type} ({branch.condition})"
            branch_context_by_line[branch.line] = current_branch

        # 构建行号到锁状态的映射
        held_locks: list[str] = []
        lock_state_by_line: dict[int, list[str]] = {}
        for lop in sorted(node.lock_ops, key=lambda x: x.line):
            if lop.op == "acquire":
                held_locks.append(lop.lock_name)
            elif lop.op == "release" and lop.lock_name in held_locks:
                held_locks.remove(lop.lock_name)
            lock_state_by_line[lop.line] = list(held_locks)

        for line_idx, line in enumerate(lines):
            actual_line = line_start + line_idx

            # 找最近的分支上下文
            branch_ctx = ""
            for ln in sorted(branch_context_by_line.keys()):
                if ln <= actual_line:
                    branch_ctx = branch_context_by_line[ln]

            # 找最近的锁状态
            current_locks: list[str] = []
            for ln in sorted(lock_state_by_line.keys()):
                if ln <= actual_line:
                    current_locks = lock_state_by_line[ln]

            # 构建本函数内的函数指针映射
            local_func_ptr_map: dict[str, str] = {}
            for fpa in node.func_ptr_assignments:
                if fpa.line <= actual_line:
                    local_func_ptr_map[fpa.ptr_name] = fpa.target_func

            for m in _CALL_RE.finditer(line):
                callee = m.group(1)
                if callee in _IGNORE_CALLS or callee.isupper():
                    continue
                if callee == fn_name:
                    continue
                
                # 尝试解析间接调用
                resolved_callee = callee
                is_indirect = False
                
                # 1. 检查宏展开
                if callee in self._macro_expansions:
                    resolved_callee = self._macro_expansions[callee]
                    is_indirect = True
                # 2. 检查本函数内的函数指针
                elif callee in local_func_ptr_map:
                    resolved_callee = local_func_ptr_map[callee]
                    is_indirect = True
                # 3. 检查全局函数指针
                elif callee in self._global_func_ptr_map:
                    resolved_callee = self._global_func_ptr_map[callee]
                    is_indirect = True
                
                # 只有解析后的函数在已定义函数集中才记录边
                if resolved_callee not in defined_functions:
                    continue

                # 提取参数
                raw_args = m.group(2).strip()
                arg_exprs = self._parse_args(raw_args)

                # 构建参数映射
                callee_node = self._graph.nodes.get(resolved_callee) if self._graph else None
                callee_params = callee_node.params if callee_node else []
                arg_mapping = []
                for idx, expr in enumerate(arg_exprs):
                    mapping: dict[str, Any] = {
                        "caller_expr": expr,
                        "param_idx": idx,
                    }
                    if idx < len(callee_params):
                        mapping["callee_param"] = callee_params[idx]
                    arg_mapping.append(mapping)

                # 检测数据流标签
                data_flow_tags: list[str] = []
                if any("input" in expr.lower() or "buf" in expr.lower() for expr in arg_exprs):
                    data_flow_tags.append("potential_external_input")
                if is_indirect:
                    data_flow_tags.append("indirect_call")

                edges.append(FusedEdge(
                    caller=fn_name,
                    callee=resolved_callee,
                    call_site_line=actual_line,
                    branch_context=branch_ctx,
                    lock_held=current_locks,
                    arg_mapping=arg_mapping,
                    data_flow_tags=data_flow_tags,
                ))

        return edges

    def _parse_args(self, raw_args: str) -> list[str]:
        """解析参数列表（处理嵌套括号）"""
        if not raw_args:
            return []
        
        args = []
        depth = 0
        current = ""
        for ch in raw_args:
            if ch in "([{":
                depth += 1
                current += ch
            elif ch in ")]}":
                depth -= 1
                current += ch
            elif ch == "," and depth == 0:
                args.append(current.strip())
                current = ""
            else:
                current += ch
        if current.strip():
            args.append(current.strip())
        return args

    def _identify_entry_points(self) -> None:
        """识别入口点（基于入度为0或命名模式）
        
        函数已被 _build_node() 基于命名模式标记为入口点。
        这里只补充识别入度为0的函数作为潜在入口点。
        """
        if not self._graph:
            return

        # 计算入度（被调用的函数集合）
        callee_set: set[str] = set()
        for edge in self._graph.edges:
            callee_set.add(edge.callee)

        # 入度为0的函数可能是入口点（未被任何函数调用）
        for name, node in self._graph.nodes.items():
            if not node.is_entry_point and name not in callee_set:
                # 入度为0且未被标记，可能是外部入口
                node.is_entry_point = True
                node.entry_point_type = "unreferenced"

    def _build_call_chains(self) -> None:
        """构建调用链"""
        if not self._graph:
            return

        # 从每个入口点开始 DFS
        entry_points = [
            name for name, node in self._graph.nodes.items()
            if node.is_entry_point
        ]

        # 构建邻接表
        adj: dict[str, list[FusedEdge]] = defaultdict(list)
        for edge in self._graph.edges:
            adj[edge.caller].append(edge)

        # 计算自适应深度
        max_depth = self._compute_adaptive_depth(adj)
        
        # 检测递归函数 (自调用)
        recursive_funcs: set[str] = set()
        for caller, edges in adj.items():
            for edge in edges:
                if edge.callee == caller:
                    recursive_funcs.add(caller)

        for entry in entry_points:
            chains = self._dfs_call_chains(
                entry, adj, max_depth=max_depth, 
                recursive_funcs=recursive_funcs,
                max_recursive_depth=3
            )
            self._graph.call_chains.extend(chains)

    def _compute_adaptive_depth(self, adj: dict[str, list[FusedEdge]]) -> int:
        """根据图结构计算自适应的最大调用链深度
        
        算法: max_depth = min(max(max_out_degree * 2, 10), 25)
        """
        if not adj:
            return 10
        
        max_out_degree = max(len(edges) for edges in adj.values()) if adj else 1
        adaptive_depth = min(max(max_out_degree * 2, 10), 25)
        
        return adaptive_depth

    def _dfs_call_chains(
        self,
        start: str,
        adj: dict[str, list[FusedEdge]],
        max_depth: int,
        recursive_funcs: set[str] | None = None,
        max_recursive_depth: int = 3,
    ) -> list[CallChain]:
        """DFS 构建调用链
        
        Args:
            start: 起始入口点函数名
            adj: 邻接表
            max_depth: 最大调用链深度
            recursive_funcs: 递归函数集合
            max_recursive_depth: 递归函数的最大递归深度
        """
        chains: list[CallChain] = []
        recursive_funcs = recursive_funcs or set()

        def dfs(
            current: str,
            path: list[str],
            branch_path: list[str],
            locks_path: list[list[str]],
            protocol_seq: list[str],
            visited: set[str],
            recursive_counts: dict[str, int],
        ) -> None:
            if len(path) > max_depth:
                return

            edges = adj.get(current, [])
            if not edges or len(path) >= max_depth:
                if len(path) > 1:
                    entry_node = self._graph.nodes.get(start) if self._graph else None
                    entry_type = entry_node.entry_point_type if entry_node else "none"
                    chains.append(CallChain(
                        functions=list(path),
                        entry_point=start,
                        entry_type=entry_type,
                        depth=len(path),
                        branch_coverage=list(branch_path),
                        lock_sequence=list(locks_path),
                        protocol_sequence=list(protocol_seq),
                    ))
                return

            for edge in edges:
                callee = edge.callee
                
                # 对于递归函数，使用单独的递归深度限制
                if callee in recursive_funcs:
                    current_count = recursive_counts.get(callee, 0)
                    if current_count >= max_recursive_depth:
                        continue
                    recursive_counts[callee] = current_count + 1
                elif callee in visited:
                    continue
                
                callee_node = self._graph.nodes.get(callee) if self._graph else None
                proto_ops = []
                if callee_node:
                    proto_ops = [p.op_type for p in callee_node.protocol_ops]

                visited.add(callee)
                path.append(callee)
                branch_path.append(edge.branch_context)
                locks_path.append(edge.lock_held)
                protocol_seq.extend(proto_ops)

                dfs(callee, path, branch_path, locks_path, protocol_seq, visited, recursive_counts)

                path.pop()
                branch_path.pop()
                locks_path.pop()
                for _ in proto_ops:
                    protocol_seq.pop()
                visited.discard(callee)
                
                # 恢复递归计数
                if callee in recursive_funcs:
                    recursive_counts[callee] = recursive_counts.get(callee, 1) - 1

        dfs(start, [start], [], [], [], {start}, {})
        return chains

    def _extract_protocol_state_machine(self) -> None:
        """从调用链和协议操作提取状态机"""
        if not self._graph:
            return

        states: dict[str, dict] = {}
        transitions: list[dict] = []

        # 从协议操作中推断状态
        proto_sequence: list[tuple[str, str]] = []  # (function, op_type)
        for name, node in self._graph.nodes.items():
            for op in node.protocol_ops:
                proto_sequence.append((name, op.op_type))

        # 构建状态机（简化版：基于操作序列）
        state_order = ["INIT", "CONNECTING", "CONNECTED", "ACTIVE", "CLOSING", "CLOSED"]
        op_to_state = {
            "connect": "CONNECTING",
            "accept": "CONNECTED",
            "send": "ACTIVE",
            "recv": "ACTIVE",
            "close": "CLOSING",
        }

        for i, state in enumerate(state_order):
            states[state] = {
                "name": state,
                "functions": [],
                "is_initial": i == 0,
                "is_error": False,
            }

        for fn_name, op_type in proto_sequence:
            target_state = op_to_state.get(op_type)
            if target_state and target_state in states:
                states[target_state]["functions"].append(fn_name)

        # 构建转换
        for i, state in enumerate(state_order[:-1]):
            transitions.append({
                "from": state,
                "to": state_order[i + 1],
                "trigger": f"协议操作",
            })

        self._graph.protocol_state_machine = {
            "states": states,
            "transitions": transitions,
        }


def build_fused_graph(workspace_path: str, max_files: int = 500) -> FusedGraph:
    """构建融合图的便捷函数"""
    builder = FusedGraphBuilder()
    return builder.build(workspace_path, max_files)
