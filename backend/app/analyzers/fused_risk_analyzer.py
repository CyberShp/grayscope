"""融合风险分析器 — 在 FusedGraph 上运行跨维度风险检测。

检测类型:
- 分支+调用链: error/cleanup 分支中的资源泄漏
- 并发+分支: 锁持有状态在不同分支下的不一致性
- 并发+调用链: 跨函数的 ABBA 死锁
- 协议+分支+并发: 协议状态转换中的竞态条件
- 数据流+分支: 外部输入在特定分支下到达敏感操作
- 注释-代码一致性: 注释意图 vs 实际行为的矛盾
"""

from __future__ import annotations

import logging
import re
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from app.analyzers.fused_graph_builder import FusedGraph, FusedNode, FusedEdge

logger = logging.getLogger(__name__)

# 整数溢出检测正则
_ARITH_OVERFLOW_RE = re.compile(r"(\w+)\s*([*+])\s*(\w+)")
_MALLOC_MULTIPLY_RE = re.compile(r"(?:malloc|realloc)\s*\(\s*(\w+)\s*\*\s*(\w+)\s*\)")
_RANGE_CHECK_RE = re.compile(r"if\s*\(\s*(\w+)\s*[<>]=?\s*\w+.*\)")

# 缓冲区溢出检测正则
_UNSAFE_STR_FUNCS = {"strcpy", "strcat", "sprintf", "gets", "scanf"}
_UNSAFE_CALL_RE = re.compile(r"\b(strcpy|strcat|sprintf|gets)\s*\(([^)]+)\)")
_SCANF_RE = re.compile(r"\bscanf\s*\(\s*\"[^\"]*%s[^\"]*\"")

# 格式化字符串检测正则  
_FORMAT_FUNCS = {"printf", "fprintf", "sprintf", "snprintf", "syslog"}
_FORMAT_CALL_RE = re.compile(r"\b(printf|fprintf|sprintf|snprintf|syslog)\s*\(([^)]+)\)")

# TOCTOU 检测正则
_CHECK_FUNCS = {"access", "stat", "lstat", "fstat"}
_USE_FUNCS = {"open", "unlink", "rename", "remove", "chmod", "chown"}
_CHECK_RE = re.compile(r"\b(access|stat|lstat)\s*\(\s*([^,)]+)")
_USE_RE = re.compile(r"\b(open|unlink|rename|remove|chmod|chown)\s*\(\s*([^,)]+)")


@dataclass
class RiskFinding:
    """风险发现"""
    finding_id: str
    risk_type: str
    severity: str  # S0, S1, S2, S3
    risk_score: float
    title: str
    description: str
    file_path: str
    symbol_name: str
    line_start: int
    line_end: int
    evidence: dict[str, Any]
    call_chain: list[str] = field(default_factory=list)
    branch_context: str = ""
    related_functions: list[str] = field(default_factory=list)
    expected_outcome: str = ""
    unacceptable_outcomes: list[str] = field(default_factory=list)
    test_suggestion: str = ""


@dataclass
class CommentIssue:
    """注释-代码不一致问题"""
    function_name: str
    file_path: str
    line: int
    comment_text: str
    actual_behavior: str
    inconsistency_type: str  # missing_cleanup, thread_safety_claim, return_value, etc.
    severity: str


class FusedRiskAnalyzer:
    """融合风险分析器"""

    def __init__(self, graph: FusedGraph) -> None:
        self._graph = graph
        self._findings: list[RiskFinding] = []
        self._comment_issues: list[CommentIssue] = []
        self._fid = 0

    def analyze(self) -> dict[str, Any]:
        """运行所有风险分析"""
        self._analyze_branch_call_chain_risks()
        self._analyze_concurrency_branch_risks()
        self._analyze_cross_function_deadlock()
        self._analyze_protocol_risks()
        self._analyze_data_flow_branch_risks()
        self._analyze_comment_consistency()
        # 新增的安全风险分析
        self._analyze_integer_overflow_risks()
        self._analyze_buffer_overflow_risks()
        self._analyze_format_string_risks()
        self._analyze_toctou_risks()

        return {
            "findings": [self._finding_to_dict(f) for f in self._findings],
            "comment_issues": [self._issue_to_dict(i) for i in self._comment_issues],
            "risk_summary": self._compute_summary(),
        }

    def _new_finding_id(self) -> str:
        self._fid += 1
        return f"FR-{self._fid:04d}"

    def _analyze_branch_call_chain_risks(self) -> None:
        """分析分支+调用链风险: error/cleanup 路径中的资源泄漏"""
        for chain in self._graph.call_chains:
            # 检查调用链中是否有 error/cleanup 分支
            for i, branch_ctx in enumerate(chain.branch_coverage):
                if not branch_ctx:
                    continue
                
                is_error_branch = any(
                    kw in branch_ctx.lower()
                    for kw in ["error", "err", "fail", "ret < 0", "ret != 0", "!= 0", "< 0", "null", "cleanup"]
                )
                
                if not is_error_branch:
                    continue

                # 检查该分支后的函数是否有资源释放
                callee = chain.functions[i + 1] if i + 1 < len(chain.functions) else None
                if not callee:
                    continue

                callee_node = self._graph.nodes.get(callee)
                if not callee_node:
                    continue

                # 检查是否有锁获取但未释放
                acquires = {op.lock_name for op in callee_node.lock_ops if op.op == "acquire"}
                releases = {op.lock_name for op in callee_node.lock_ops if op.op == "release"}
                unreleased = acquires - releases

                if unreleased:
                    self._findings.append(RiskFinding(
                        finding_id=self._new_finding_id(),
                        risk_type="error_path_resource_leak",
                        severity="S1",
                        risk_score=0.85,
                        title=f"错误路径资源泄漏: {callee}() 在 error 分支下锁未释放",
                        description=(
                            f"在调用链 {' → '.join(chain.functions[:i+2])} 的错误分支 "
                            f"({branch_ctx}) 中，函数 {callee}() 获取了锁 {unreleased}，"
                            f"但未释放。当执行流进入此错误分支时，锁将永久持有，"
                            f"导致其他线程死等。"
                        ),
                        file_path=callee_node.file_path,
                        symbol_name=callee,
                        line_start=callee_node.line_start,
                        line_end=callee_node.line_end,
                        evidence={
                            "call_chain": chain.functions[:i+2],
                            "branch_context": branch_ctx,
                            "unreleased_locks": sorted(unreleased),
                            "acquired_locks": sorted(acquires),
                        },
                        call_chain=chain.functions[:i+2],
                        branch_context=branch_ctx,
                        related_functions=chain.functions[:i+2],
                        expected_outcome="错误路径正确释放所有资源",
                        unacceptable_outcomes=["锁泄漏", "死锁", "资源耗尽"],
                        test_suggestion="注入错误条件触发 error 分支，检查锁是否正确释放",
                    ))

    def _analyze_concurrency_branch_risks(self) -> None:
        """分析并发+分支风险: 锁持有状态在不同分支下的不一致性"""
        for name, node in self._graph.nodes.items():
            # 检查不同分支下的锁操作模式
            if len(node.branches) < 2 or not node.lock_ops:
                continue

            # 按分支分组锁操作
            branch_lines = sorted([b.line for b in node.branches if b.branch_type in ("if", "else")])
            
            for i in range(len(branch_lines) - 1):
                branch_start = branch_lines[i]
                branch_end = branch_lines[i + 1]
                
                # 该分支内的锁操作
                branch_lock_ops = [
                    op for op in node.lock_ops
                    if branch_start <= op.line < branch_end
                ]
                
                acquires_in_branch = {op.lock_name for op in branch_lock_ops if op.op == "acquire"}
                releases_in_branch = {op.lock_name for op in branch_lock_ops if op.op == "release"}
                
                # 检查是否有锁在某些分支获取但不释放
                if acquires_in_branch and not releases_in_branch:
                    branch = next(
                        (b for b in node.branches if b.line == branch_start),
                        None
                    )
                    branch_ctx = f"{branch.branch_type} ({branch.condition})" if branch else ""
                    
                    self._findings.append(RiskFinding(
                        finding_id=self._new_finding_id(),
                        risk_type="branch_lock_inconsistency",
                        severity="S1",
                        risk_score=0.8,
                        title=f"分支锁不一致: {name}() 在 {branch_ctx} 分支获取锁但未释放",
                        description=(
                            f"函数 {name}() 在条件分支 {branch_ctx} 中获取了锁 "
                            f"{acquires_in_branch}，但在该分支内未释放。"
                            f"这可能导致：(1) 如果分支结束后释放，则分支外也持有锁，"
                            f"语义可能不符预期；(2) 如果分支提前 return，锁将泄漏。"
                        ),
                        file_path=node.file_path,
                        symbol_name=name,
                        line_start=branch_start,
                        line_end=branch_end,
                        evidence={
                            "branch": branch_ctx,
                            "acquired_in_branch": sorted(acquires_in_branch),
                            "released_in_branch": sorted(releases_in_branch),
                        },
                        branch_context=branch_ctx,
                        related_functions=[name],
                        expected_outcome="锁在获取它的同一分支内释放",
                        unacceptable_outcomes=["锁泄漏", "死锁"],
                    ))

    def _analyze_cross_function_deadlock(self) -> None:
        """分析跨函数 ABBA 死锁风险"""
        # 为每个函数计算其持有的锁序列（考虑调用链）
        func_lock_order: dict[str, list[str]] = {}
        
        for chain in self._graph.call_chains:
            # 累积调用链中的锁获取顺序
            accumulated_locks: list[str] = []
            for i, fn in enumerate(chain.functions):
                node = self._graph.nodes.get(fn)
                if not node:
                    continue
                for op in sorted(node.lock_ops, key=lambda x: x.line):
                    if op.op == "acquire" and op.lock_name not in accumulated_locks:
                        accumulated_locks.append(op.lock_name)
            
            if len(accumulated_locks) >= 2:
                chain_key = "→".join(chain.functions[:3])
                func_lock_order[chain_key] = accumulated_locks

        # 检查锁顺序冲突
        items = list(func_lock_order.items())
        for i, (chain_a, locks_a) in enumerate(items):
            if len(locks_a) < 2:
                continue
            for chain_b, locks_b in items[i + 1:]:
                if len(locks_b) < 2:
                    continue
                
                # 检查 ABBA 模式
                for a_idx, la in enumerate(locks_a):
                    for lb in locks_a[a_idx + 1:]:
                        if lb in locks_b and la in locks_b:
                            b_pos_lb = locks_b.index(lb)
                            b_pos_la = locks_b.index(la)
                            if b_pos_lb < b_pos_la:
                                self._findings.append(RiskFinding(
                                    finding_id=self._new_finding_id(),
                                    risk_type="cross_function_deadlock",
                                    severity="S0",
                                    risk_score=0.95,
                                    title=f"跨函数死锁: {chain_a} 与 {chain_b} 存在 {la}/{lb} ABBA",
                                    description=(
                                        f"通过调用链分析发现潜在死锁:\n"
                                        f"路径1 ({chain_a}): 锁顺序 {' → '.join(locks_a)}\n"
                                        f"路径2 ({chain_b}): 锁顺序 {' → '.join(locks_b)}\n"
                                        f"锁 {la} 和 {lb} 在两条路径中以相反顺序获取。"
                                    ),
                                    file_path="",
                                    symbol_name=f"{chain_a} vs {chain_b}",
                                    line_start=0,
                                    line_end=0,
                                    evidence={
                                        "chain_a": {"path": chain_a, "locks": locks_a},
                                        "chain_b": {"path": chain_b, "locks": locks_b},
                                        "conflicting_locks": [la, lb],
                                    },
                                    related_functions=chain_a.split("→") + chain_b.split("→"),
                                    expected_outcome="统一锁获取顺序",
                                    unacceptable_outcomes=["死锁", "系统挂起"],
                                    test_suggestion="并发测试两条路径，使用锁依赖检测工具",
                                ))

    def _analyze_protocol_risks(self) -> None:
        """分析协议+分支+并发风险"""
        for chain in self._graph.call_chains:
            if not chain.protocol_sequence:
                continue

            # 检查协议操作序列中的异常
            for i, (fn, branch_ctx, locks) in enumerate(
                zip(chain.functions, chain.branch_coverage, chain.lock_sequence)
            ):
                node = self._graph.nodes.get(fn)
                if not node:
                    continue

                for proto_op in node.protocol_ops:
                    # 检查: 在 error 分支下的协议操作但没有清理
                    is_error_branch = branch_ctx and any(
                        kw in branch_ctx.lower()
                        for kw in ["error", "err", "fail", "< 0", "null"]
                    )
                    
                    if is_error_branch and proto_op.op_type in ("send", "recv"):
                        # error 分支下仍在做 IO 操作
                        has_close = any(
                            p.op_type == "close"
                            for n in self._graph.nodes.values()
                            for p in n.protocol_ops
                            if p.line > proto_op.line
                        )
                        
                        if not has_close:
                            self._findings.append(RiskFinding(
                                finding_id=self._new_finding_id(),
                                risk_type="protocol_error_no_cleanup",
                                severity="S1",
                                risk_score=0.8,
                                title=f"协议错误路径缺少清理: {fn}() 在 error 分支执行 {proto_op.op_type}",
                                description=(
                                    f"在错误分支 ({branch_ctx}) 中，函数 {fn}() "
                                    f"执行了协议操作 {proto_op.op_type}，但后续未找到 close 操作。"
                                    f"这可能导致：(1) 连接泄漏；(2) 对端资源挂起；"
                                    f"(3) 文件描述符耗尽。"
                                ),
                                file_path=node.file_path,
                                symbol_name=fn,
                                line_start=proto_op.line,
                                line_end=proto_op.line,
                                evidence={
                                    "protocol_op": proto_op.op_type,
                                    "branch_context": branch_ctx,
                                    "call_chain": chain.functions[:i+1],
                                },
                                call_chain=chain.functions[:i+1],
                                branch_context=branch_ctx,
                                related_functions=chain.functions[:i+1],
                                expected_outcome="错误路径关闭连接/释放资源",
                                unacceptable_outcomes=["连接泄漏", "FD 耗尽", "资源挂起"],
                            ))

                    # 检查: 协议操作时持有锁可能导致死锁
                    if proto_op.op_type in ("recv", "accept") and locks:
                        self._findings.append(RiskFinding(
                            finding_id=self._new_finding_id(),
                            risk_type="protocol_lock_holding",
                            severity="S2",
                            risk_score=0.7,
                            title=f"协议操作持锁: {fn}() 在持有锁 {locks} 时执行阻塞 {proto_op.op_type}",
                            description=(
                                f"函数 {fn}() 在持有锁 {locks} 的情况下执行了可能阻塞的 "
                                f"协议操作 {proto_op.op_type}。如果该操作阻塞，其他需要这些锁的 "
                                f"线程将被阻塞，可能导致整体性能下降或死锁。"
                            ),
                            file_path=node.file_path,
                            symbol_name=fn,
                            line_start=proto_op.line,
                            line_end=proto_op.line,
                            evidence={
                                "protocol_op": proto_op.op_type,
                                "locks_held": locks,
                            },
                            related_functions=[fn],
                            expected_outcome="不在持锁期间执行阻塞操作",
                            unacceptable_outcomes=["死锁", "性能严重下降"],
                        ))

    def _analyze_data_flow_branch_risks(self) -> None:
        """分析数据流+分支风险: 外部输入在特定分支到达敏感操作"""
        sensitive_ops = {"memcpy", "strcpy", "sprintf", "system", "exec", "popen"}
        
        for edge in self._graph.edges:
            if not edge.data_flow_tags:
                continue
            
            # 检查外部输入是否到达敏感操作
            if "potential_external_input" in edge.data_flow_tags:
                callee_node = self._graph.nodes.get(edge.callee)
                if not callee_node:
                    continue

                # 检查 callee 中是否有敏感操作
                for op in sensitive_ops:
                    if op in callee_node.source:
                        self._findings.append(RiskFinding(
                            finding_id=self._new_finding_id(),
                            risk_type="external_input_sensitive_op",
                            severity="S1",
                            risk_score=0.85,
                            title=f"外部输入到敏感操作: {edge.caller}() → {edge.callee}() 含 {op}",
                            description=(
                                f"函数 {edge.caller}() 将可能来自外部的输入传递给 "
                                f"{edge.callee}()，该函数中包含敏感操作 {op}。"
                                f"在分支 '{edge.branch_context}' 下，如果输入未经验证，"
                                f"可能导致缓冲区溢出或命令注入。"
                            ),
                            file_path=callee_node.file_path,
                            symbol_name=edge.callee,
                            line_start=edge.call_site_line,
                            line_end=edge.call_site_line,
                            evidence={
                                "caller": edge.caller,
                                "callee": edge.callee,
                                "sensitive_op": op,
                                "branch_context": edge.branch_context,
                                "data_flow_tags": edge.data_flow_tags,
                            },
                            branch_context=edge.branch_context,
                            related_functions=[edge.caller, edge.callee],
                            expected_outcome="输入经过长度/格式验证",
                            unacceptable_outcomes=["缓冲区溢出", "命令注入", "崩溃"],
                            test_suggestion="构造超长/恶意输入测试边界",
                        ))
                        break

    def _analyze_comment_consistency(self) -> None:
        """分析注释-代码一致性"""
        cleanup_keywords = ["释放", "release", "free", "cleanup", "清理", "deallocate"]
        thread_safe_keywords = ["线程安全", "thread safe", "thread-safe", "threadsafe", "锁保护"]
        return_keywords = ["返回", "return", "returns"]

        for name, node in self._graph.nodes.items():
            for comment in node.comments:
                comment_lower = comment.text.lower()

                # 检查: 注释声称释放资源，但代码没有
                if any(kw in comment_lower for kw in cleanup_keywords):
                    # 检查是否真的有释放操作
                    has_release = any(op.op == "release" for op in node.lock_ops)
                    has_free = "free(" in node.source or "delete " in node.source
                    
                    if not has_release and not has_free:
                        self._comment_issues.append(CommentIssue(
                            function_name=name,
                            file_path=node.file_path,
                            line=comment.line,
                            comment_text=comment.text[:200],
                            actual_behavior="未找到资源释放操作",
                            inconsistency_type="missing_cleanup",
                            severity="S1",
                        ))

                # 检查: 注释声称线程安全，但没有锁操作
                if any(kw in comment_lower for kw in thread_safe_keywords):
                    has_lock = len(node.lock_ops) > 0
                    has_atomic = "atomic" in node.source.lower()
                    
                    if not has_lock and not has_atomic:
                        self._comment_issues.append(CommentIssue(
                            function_name=name,
                            file_path=node.file_path,
                            line=comment.line,
                            comment_text=comment.text[:200],
                            actual_behavior="未找到锁操作或原子操作",
                            inconsistency_type="thread_safety_claim",
                            severity="S0",
                        ))

                # 检查: 注释提到特定返回值，但代码中没有该返回
                return_match = re.search(r"返回\s*(-?\d+|NULL|0|错误码)", comment.text)
                if return_match:
                    expected_return = return_match.group(1)
                    if expected_return not in node.source:
                        self._comment_issues.append(CommentIssue(
                            function_name=name,
                            file_path=node.file_path,
                            line=comment.line,
                            comment_text=comment.text[:200],
                            actual_behavior=f"代码中未找到返回 {expected_return}",
                            inconsistency_type="return_value",
                            severity="S2",
                        ))

    def _analyze_integer_overflow_risks(self) -> None:
        """检测整数溢出风险
        
        识别:
        - malloc(a * b) 中的乘法溢出
        - 无范围校验的算术运算
        """
        for name, node in self._graph.nodes.items():
            source = node.source
            lines = source.split("\n")
            
            # 检测 malloc 乘法
            for m in _MALLOC_MULTIPLY_RE.finditer(source):
                var1, var2 = m.group(1), m.group(2)
                line_offset = source[:m.start()].count("\n")
                actual_line = node.line_start + line_offset
                
                # 检查是否有前置范围校验
                has_check = False
                for i, line in enumerate(lines[:line_offset]):
                    if _RANGE_CHECK_RE.search(line):
                        if var1 in line or var2 in line:
                            has_check = True
                            break
                
                if not has_check:
                    self._findings.append(RiskFinding(
                        finding_id=self._new_finding_id(),
                        risk_type="integer_overflow",
                        severity="S1",
                        risk_score=0.75,
                        title=f"潜在整数溢出: malloc({var1} * {var2})",
                        description=f"在 malloc 调用中对 {var1} 和 {var2} 进行乘法运算，"
                                   f"如果这两个变量来源于外部输入，可能导致整数溢出和堆溢出",
                        file_path=node.file_path,
                        symbol_name=name,
                        line_start=actual_line,
                        line_end=actual_line,
                        evidence={
                            "operand1": var1,
                            "operand2": var2,
                            "operation": "multiplication in malloc",
                            "has_range_check": False,
                        },
                        expected_outcome="分配的内存大小正确",
                        unacceptable_outcomes=["整数溢出导致分配过小的缓冲区", "堆溢出"],
                        test_suggestion=f"测试 {var1} 和 {var2} 接近 SIZE_MAX/2 时的行为",
                    ))
            
            # 检测通用算术溢出（针对敏感变量）
            for m in _ARITH_OVERFLOW_RE.finditer(source):
                var1, op, var2 = m.group(1), m.group(2), m.group(3)
                
                # 只关注涉及 size/len/count 等敏感命名的变量
                if not any(kw in var1.lower() or kw in var2.lower() 
                          for kw in ("size", "len", "count", "num", "idx")):
                    continue
                
                line_offset = source[:m.start()].count("\n")
                actual_line = node.line_start + line_offset
                
                # 检查前置范围校验
                has_check = False
                for i, line in enumerate(lines[:line_offset]):
                    if _RANGE_CHECK_RE.search(line) and (var1 in line or var2 in line):
                        has_check = True
                        break
                
                if not has_check:
                    self._findings.append(RiskFinding(
                        finding_id=self._new_finding_id(),
                        risk_type="integer_overflow",
                        severity="S2",
                        risk_score=0.5,
                        title=f"潜在整数溢出: {var1} {op} {var2}",
                        description=f"对敏感变量进行算术运算，缺少范围校验",
                        file_path=node.file_path,
                        symbol_name=name,
                        line_start=actual_line,
                        line_end=actual_line,
                        evidence={
                            "operand1": var1,
                            "operand2": var2,
                            "operation": op,
                            "has_range_check": False,
                        },
                        expected_outcome="算术运算结果在有效范围内",
                        unacceptable_outcomes=["整数溢出", "下溢"],
                        test_suggestion=f"测试边界值时 {var1} {op} {var2} 的行为",
                    ))

    def _analyze_buffer_overflow_risks(self) -> None:
        """检测缓冲区溢出风险
        
        识别不安全函数调用: strcpy, strcat, sprintf, gets
        """
        for name, node in self._graph.nodes.items():
            source = node.source
            
            for m in _UNSAFE_CALL_RE.finditer(source):
                func_name = m.group(1)
                args_str = m.group(2)
                line_offset = source[:m.start()].count("\n")
                actual_line = node.line_start + line_offset
                
                # 检查数据流标签是否包含外部输入
                has_external_input = False
                for edge in self._graph.edges:
                    if edge.caller == name and "potential_external_input" in edge.data_flow_tags:
                        has_external_input = True
                        break
                
                severity = "S0" if has_external_input else "S1"
                risk_score = 0.9 if has_external_input else 0.7
                
                safe_alt = {
                    "strcpy": "strncpy",
                    "strcat": "strncat",
                    "sprintf": "snprintf",
                    "gets": "fgets",
                }.get(func_name, "N/A")
                
                self._findings.append(RiskFinding(
                    finding_id=self._new_finding_id(),
                    risk_type="buffer_overflow",
                    severity=severity,
                    risk_score=risk_score,
                    title=f"不安全函数调用: {func_name}()",
                    description=f"使用不安全的字符串函数 {func_name}，应替换为 {safe_alt}",
                    file_path=node.file_path,
                    symbol_name=name,
                    line_start=actual_line,
                    line_end=actual_line,
                    evidence={
                        "unsafe_function": func_name,
                        "safe_alternative": safe_alt,
                        "args": args_str[:100],
                        "has_external_input": has_external_input,
                    },
                    expected_outcome="字符串操作不超出缓冲区边界",
                    unacceptable_outcomes=["缓冲区溢出", "内存损坏", "代码执行"],
                    test_suggestion=f"测试当输入超过目标缓冲区大小时的行为",
                ))
            
            # 检测 scanf %s
            if _SCANF_RE.search(source):
                line_offset = source.find("scanf")
                if line_offset >= 0:
                    actual_line = node.line_start + source[:line_offset].count("\n")
                    self._findings.append(RiskFinding(
                        finding_id=self._new_finding_id(),
                        risk_type="buffer_overflow",
                        severity="S0",
                        risk_score=0.9,
                        title="不安全的 scanf %s 使用",
                        description="scanf 使用 %s 格式化符而没有长度限制，可能导致缓冲区溢出",
                        file_path=node.file_path,
                        symbol_name=name,
                        line_start=actual_line,
                        line_end=actual_line,
                        evidence={"pattern": "scanf with %s"},
                        expected_outcome="输入被正确截断",
                        unacceptable_outcomes=["缓冲区溢出"],
                        test_suggestion="测试超长输入时的行为，应使用 %Ns 指定长度",
                    ))

    def _analyze_format_string_risks(self) -> None:
        """检测格式化字符串漏洞
        
        识别 printf 等函数的 format 参数不是字面字符串的情况
        """
        for name, node in self._graph.nodes.items():
            source = node.source
            
            for m in _FORMAT_CALL_RE.finditer(source):
                func_name = m.group(1)
                args_str = m.group(2).strip()
                line_offset = source[:m.start()].count("\n")
                actual_line = node.line_start + line_offset
                
                # 解析第一个参数（format string 位置）
                # fprintf 第一个参数是 FILE*，format 是第二个
                args = [a.strip() for a in args_str.split(",")]
                if not args:
                    continue
                
                if func_name == "fprintf" or func_name == "syslog":
                    format_arg = args[1] if len(args) > 1 else ""
                else:
                    format_arg = args[0]
                
                # 检查 format 参数是否是字面字符串
                if format_arg.startswith('"') and format_arg.endswith('"'):
                    continue  # 字面字符串，安全
                
                # 不是字面字符串，可能是变量
                if not format_arg:
                    continue
                
                # 检查该变量是否来自函数参数或外部输入
                is_from_param = format_arg in node.params
                
                severity = "S0" if is_from_param else "S1"
                risk_score = 0.85 if is_from_param else 0.65
                
                self._findings.append(RiskFinding(
                    finding_id=self._new_finding_id(),
                    risk_type="format_string",
                    severity=severity,
                    risk_score=risk_score,
                    title=f"格式化字符串漏洞: {func_name}({format_arg})",
                    description=f"{func_name} 的格式化参数不是字面字符串，可能导致格式化字符串攻击",
                    file_path=node.file_path,
                    symbol_name=name,
                    line_start=actual_line,
                    line_end=actual_line,
                    evidence={
                        "function": func_name,
                        "format_arg": format_arg[:50],
                        "is_from_param": is_from_param,
                    },
                    expected_outcome="格式化字符串是静态定义的",
                    unacceptable_outcomes=["任意内存读取", "任意内存写入", "信息泄露"],
                    test_suggestion=f"测试当 {format_arg} 包含 %n, %x 等格式符时的行为",
                ))

    def _analyze_toctou_risks(self) -> None:
        """检测 TOCTOU (Time-of-check Time-of-use) 竞态条件
        
        识别 access()/stat() 后接 open()/unlink() 的模式
        """
        for name, node in self._graph.nodes.items():
            source = node.source
            lines = source.split("\n")
            
            # 收集所有检查操作
            checks: list[tuple[int, str, str]] = []  # (line_offset, func, path)
            for m in _CHECK_RE.finditer(source):
                line_offset = source[:m.start()].count("\n")
                func = m.group(1)
                path_arg = m.group(2).strip()
                checks.append((line_offset, func, path_arg))
            
            # 收集所有使用操作
            uses: list[tuple[int, str, str]] = []
            for m in _USE_RE.finditer(source):
                line_offset = source[:m.start()].count("\n")
                func = m.group(1)
                path_arg = m.group(2).strip()
                uses.append((line_offset, func, path_arg))
            
            # 检测检查-使用对
            for check_line, check_func, check_path in checks:
                for use_line, use_func, use_path in uses:
                    # 使用操作必须在检查之后
                    if use_line <= check_line:
                        continue
                    
                    # 检查路径是否匹配（简化：变量名相同）
                    check_var = check_path.strip('"').strip()
                    use_var = use_path.strip('"').strip()
                    if check_var != use_var:
                        continue
                    
                    # 检查两个操作之间是否有锁保护
                    has_lock = False
                    for lop in node.lock_ops:
                        lock_line = lop.line - node.line_start
                        if check_line < lock_line < use_line and lop.op == "acquire":
                            has_lock = True
                            break
                    
                    if has_lock:
                        continue
                    
                    actual_line = node.line_start + check_line
                    
                    self._findings.append(RiskFinding(
                        finding_id=self._new_finding_id(),
                        risk_type="toctou",
                        severity="S1",
                        risk_score=0.7,
                        title=f"TOCTOU 竞态: {check_func}() -> {use_func}()",
                        description=f"在 {check_func}({check_path}) 检查后调用 {use_func}()，"
                                   f"攻击者可能在检查和使用之间修改文件状态",
                        file_path=node.file_path,
                        symbol_name=name,
                        line_start=actual_line,
                        line_end=node.line_start + use_line,
                        evidence={
                            "check_func": check_func,
                            "use_func": use_func,
                            "path": check_path[:50],
                            "check_line": actual_line,
                            "use_line": node.line_start + use_line,
                            "has_lock": False,
                        },
                        expected_outcome="文件操作是原子性的或有适当的同步",
                        unacceptable_outcomes=["权限绕过", "符号链接攻击", "文件替换攻击"],
                        test_suggestion="测试在检查和使用之间修改文件或替换为符号链接的场景",
                    ))

    def _finding_to_dict(self, f: RiskFinding) -> dict:
        return {
            "finding_id": f.finding_id,
            "risk_type": f.risk_type,
            "severity": f.severity,
            "risk_score": f.risk_score,
            "title": f.title,
            "description": f.description,
            "file_path": f.file_path,
            "symbol_name": f.symbol_name,
            "line_start": f.line_start,
            "line_end": f.line_end,
            "evidence": f.evidence,
            "call_chain": f.call_chain,
            "branch_context": f.branch_context,
            "related_functions": f.related_functions,
            "expected_outcome": f.expected_outcome,
            "unacceptable_outcomes": f.unacceptable_outcomes,
            "test_suggestion": f.test_suggestion,
        }

    def _issue_to_dict(self, i: CommentIssue) -> dict:
        return {
            "function_name": i.function_name,
            "file_path": i.file_path,
            "line": i.line,
            "comment_text": i.comment_text,
            "actual_behavior": i.actual_behavior,
            "inconsistency_type": i.inconsistency_type,
            "severity": i.severity,
        }

    def _compute_summary(self) -> dict:
        """计算风险摘要"""
        severity_counts = defaultdict(int)
        type_counts = defaultdict(int)
        
        for f in self._findings:
            severity_counts[f.severity] += 1
            type_counts[f.risk_type] += 1

        avg_score = (
            sum(f.risk_score for f in self._findings) / len(self._findings)
            if self._findings else 0.0
        )

        return {
            "total_findings": len(self._findings),
            "total_comment_issues": len(self._comment_issues),
            "severity_distribution": dict(severity_counts),
            "type_distribution": dict(type_counts),
            "average_risk_score": round(avg_score, 4),
            "critical_count": severity_counts.get("S0", 0),
            "high_count": severity_counts.get("S1", 0),
        }


def analyze_fused_risks(graph: FusedGraph) -> dict[str, Any]:
    """分析融合图风险的便捷函数"""
    analyzer = FusedRiskAnalyzer(graph)
    return analyzer.analyze()
