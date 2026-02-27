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
    chain: list[str]  # 函数名序列
    entry_point: str
    branch_path: list[str]  # 每一步的分支条件
    locks_held: list[list[str]]  # 每一步持有的锁
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
                    "chain": c.chain,
                    "entry_point": c.entry_point,
                    "branch_path": c.branch_path,
                    "locks_held": c.locks_held,
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


class FusedGraphBuilder:
    """融合图构建器"""

    def __init__(self) -> None:
        if not is_available():
            raise RuntimeError("tree-sitter grammars not available")
        self._parser = CodeParser()
        self._graph: FusedGraph | None = None

    def build(self, workspace_path: str, max_files: int = 500) -> FusedGraph:
        """构建融合图"""
        workspace = Path(workspace_path)
        
        self._graph = FusedGraph(
            nodes={},
            edges=[],
            call_chains=[],
            global_vars=set(),
            protocol_state_machine={},
        )

        exts = {".c", ".h", ".cpp", ".cc", ".cxx", ".hpp"}
        files = sorted(
            [p for p in workspace.rglob("*") if p.suffix in exts and p.is_file()]
        )[:max_files]

        # Pass 1: 收集全局变量和所有函数定义
        function_sources: list[tuple[str, str, str, int, int]] = []
        defined_functions: set[str] = set()

        for fpath in files:
            try:
                source_text = fpath.read_text(errors="replace")
                # 收集全局变量
                for m in _GLOBAL_VAR_RE.finditer(source_text):
                    self._graph.global_vars.add(m.group(1))

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

        return ops

    def _extract_shared_var_access(
        self,
        source: str,
        line_start: int,
        lock_state_by_line: dict[int, list[str]],
    ) -> list[SharedAccess]:
        """提取共享变量访问"""
        accesses: list[SharedAccess] = []
        
        if not self._graph:
            return accesses

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

            for gv in self._graph.global_vars:
                # 写访问
                if re.search(rf"\b{re.escape(gv)}\s*(?:=(?!=)|[+\-*/&|^]=|\+\+|--)", line):
                    accesses.append(SharedAccess(
                        var_name=gv,
                        access="write",
                        line=actual_line,
                        lock_held=list(held_locks),
                    ))
                # 读访问
                elif re.search(rf"\b{re.escape(gv)}\b", line):
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

    def _check_entry_point(self, fn_name: str) -> tuple[bool, str]:
        """检查函数是否为入口点"""
        for pattern, entry_type in _ENTRY_POINT_PATTERNS:
            if pattern.search(fn_name):
                return True, entry_type
        return False, "none"

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

            for m in _CALL_RE.finditer(line):
                callee = m.group(1)
                if callee in _IGNORE_CALLS or callee.isupper():
                    continue
                if callee == fn_name or callee not in defined_functions:
                    continue

                # 提取参数
                raw_args = m.group(2).strip()
                arg_exprs = self._parse_args(raw_args)

                # 构建参数映射
                callee_node = self._graph.nodes.get(callee) if self._graph else None
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
                data_flow_tags = []
                if any("input" in expr.lower() or "buf" in expr.lower() for expr in arg_exprs):
                    data_flow_tags.append("potential_external_input")

                edges.append(FusedEdge(
                    caller=fn_name,
                    callee=callee,
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
        """识别入口点（基于入度为0或命名模式）"""
        if not self._graph:
            return

        # 计算入度
        callee_set: set[str] = set()
        for edge in self._graph.edges:
            callee_set.add(edge.callee)

        # 入度为0的函数可能是入口点
        for name, node in self._graph.nodes.items():
            if not node.is_entry_point and name not in callee_set:
                # 检查是否被 main 或线程创建函数引用
                for edge in self._graph.edges:
                    if edge.callee == name:
                        caller_node = self._graph.nodes.get(edge.caller)
                        if caller_node and caller_node.entry_point_type == "main":
                            node.is_entry_point = True
                            node.entry_point_type = "called_from_main"
                            break

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

        for entry in entry_points:
            chains = self._dfs_call_chains(entry, adj, max_depth=10)
            self._graph.call_chains.extend(chains)

    def _dfs_call_chains(
        self,
        start: str,
        adj: dict[str, list[FusedEdge]],
        max_depth: int,
    ) -> list[CallChain]:
        """DFS 构建调用链"""
        chains: list[CallChain] = []

        def dfs(
            current: str,
            path: list[str],
            branch_path: list[str],
            locks_path: list[list[str]],
            protocol_seq: list[str],
            visited: set[str],
        ) -> None:
            if len(path) > max_depth:
                return

            edges = adj.get(current, [])
            if not edges or len(path) >= max_depth:
                if len(path) > 1:
                    chains.append(CallChain(
                        chain=list(path),
                        entry_point=start,
                        branch_path=list(branch_path),
                        locks_held=list(locks_path),
                        protocol_sequence=list(protocol_seq),
                    ))
                return

            for edge in edges:
                if edge.callee in visited:
                    continue
                
                callee_node = self._graph.nodes.get(edge.callee) if self._graph else None
                proto_ops = []
                if callee_node:
                    proto_ops = [p.op_type for p in callee_node.protocol_ops]

                visited.add(edge.callee)
                path.append(edge.callee)
                branch_path.append(edge.branch_context)
                locks_path.append(edge.lock_held)
                protocol_seq.extend(proto_ops)

                dfs(edge.callee, path, branch_path, locks_path, protocol_seq, visited)

                path.pop()
                branch_path.pop()
                locks_path.pop()
                for _ in proto_ops:
                    protocol_seq.pop()
                visited.discard(edge.callee)

        dfs(start, [start], [], [], [], {start})
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

        for state in state_order:
            states[state] = {"name": state, "functions": []}

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
