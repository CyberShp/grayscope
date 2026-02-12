"""Tree-sitter based C/C++ code parser.

Provides AST parsing, symbol extraction, and basic CFG construction
as the foundation for all analyzer modules.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ---------- tree-sitter setup ----------

try:
    import tree_sitter_c as _tsc
    import tree_sitter_cpp as _tscpp
    from tree_sitter import Language, Parser

    C_LANGUAGE = Language(_tsc.language())
    CPP_LANGUAGE = Language(_tscpp.language())
    _AVAILABLE = True
except ImportError:
    logger.warning(
        "tree-sitter grammars not installed; code parsing will be unavailable. "
        "Install with: pip install tree-sitter tree-sitter-c tree-sitter-cpp"
    )
    _AVAILABLE = False
    C_LANGUAGE = None  # type: ignore[assignment]
    CPP_LANGUAGE = None  # type: ignore[assignment]


# ---------- data classes ----------


@dataclass
class Symbol:
    name: str
    kind: str  # function, struct, enum, typedef, variable
    file_path: str
    line_start: int
    line_end: int
    source: str = ""


@dataclass
class CFGNode:
    node_id: str
    kind: str  # entry, exit, branch, statement
    label: str = ""
    line: int = 0


@dataclass
class CFGEdge:
    src: str
    dst: str
    label: str = ""  # true, false, fallthrough


@dataclass
class CFG:
    function_name: str
    nodes: list[CFGNode] = field(default_factory=list)
    edges: list[CFGEdge] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "function_name": self.function_name,
            "nodes": [{"id": n.node_id, "kind": n.kind, "label": n.label, "line": n.line} for n in self.nodes],
            "edges": [{"src": e.src, "dst": e.dst, "label": e.label} for e in self.edges],
        }


# ---------- parser ----------


class CodeParser:
    """Parse C/C++ files and extract symbols and control flow."""

    def __init__(self) -> None:
        if not _AVAILABLE:
            raise RuntimeError("tree-sitter grammars not available")
        self._c_parser = Parser(C_LANGUAGE)
        self._cpp_parser = Parser(CPP_LANGUAGE)

    def parse_file(self, path: str | Path) -> list[Symbol]:
        """Parse a single source file and return top-level symbols."""
        p = Path(path)
        source = p.read_bytes()
        parser = self._cpp_parser if p.suffix in (".cpp", ".cc", ".cxx", ".hpp") else self._c_parser
        tree = parser.parse(source)
        return self._extract_symbols(tree.root_node, str(p), source)

    def parse_directory(self, dir_path: str | Path, max_files: int = 500) -> list[Symbol]:
        """Recursively parse C/C++ files in a directory."""
        d = Path(dir_path)
        extensions = {".c", ".h", ".cpp", ".cc", ".cxx", ".hpp"}
        symbols: list[Symbol] = []
        count = 0
        for p in sorted(d.rglob("*")):
            if p.suffix in extensions and p.is_file():
                try:
                    symbols.extend(self.parse_file(p))
                except Exception:
                    logger.warning("failed to parse %s", p)
                count += 1
                if count >= max_files:
                    break
        return symbols

    def build_cfg(self, path: str | Path, function_name: str) -> CFG | None:
        """Build a simple CFG for a specific function."""
        p = Path(path)
        source = p.read_bytes()
        parser = self._cpp_parser if p.suffix in (".cpp", ".cc", ".cxx", ".hpp") else self._c_parser
        tree = parser.parse(source)

        for node in self._walk(tree.root_node):
            if node.type == "function_definition":
                decl = node.child_by_field_name("declarator")
                name = self._get_function_name(decl) if decl else ""
                if name == function_name:
                    return self._build_function_cfg(node, function_name, source)
        return None

    # ---------- internal ----------

    def _extract_symbols(self, root, file_path: str, source: bytes) -> list[Symbol]:
        symbols: list[Symbol] = []
        for node in self._walk(root):
            if node.type == "function_definition":
                decl = node.child_by_field_name("declarator")
                name = self._get_function_name(decl) if decl else "<anonymous>"
                symbols.append(
                    Symbol(
                        name=name,
                        kind="function",
                        file_path=file_path,
                        line_start=node.start_point[0] + 1,
                        line_end=node.end_point[0] + 1,
                        source=source[node.start_byte : node.end_byte].decode(
                            errors="replace"
                        ),
                    )
                )
            elif node.type in ("struct_specifier", "enum_specifier"):
                name_node = node.child_by_field_name("name")
                if name_node:
                    symbols.append(
                        Symbol(
                            name=name_node.text.decode(errors="replace"),
                            kind=node.type.split("_")[0],
                            file_path=file_path,
                            line_start=node.start_point[0] + 1,
                            line_end=node.end_point[0] + 1,
                        )
                    )
        return symbols

    def _build_function_cfg(self, func_node, func_name: str, source: bytes) -> CFG:
        cfg = CFG(function_name=func_name)
        nid = 0

        def _new(kind: str, label: str = "", line: int = 0) -> str:
            nonlocal nid
            n = CFGNode(node_id=f"n{nid}", kind=kind, label=label, line=line)
            cfg.nodes.append(n)
            nid += 1
            return n.node_id

        entry = _new("entry", "ENTRY", func_node.start_point[0] + 1)
        exit_n = _new("exit", "EXIT", func_node.end_point[0] + 1)

        body = func_node.child_by_field_name("body")
        if body is None:
            cfg.edges.append(CFGEdge(entry, exit_n))
            return cfg

        def _src(node) -> str:
            return source[node.start_byte : node.end_byte].decode(errors="replace")

        def _visit_block(stmts, prev_id: str) -> str:
            """递归处理一组语句，返回最后一个节点的 id。"""
            prev = prev_id
            for child in stmts:
                if child.type in ("{", "}", "comment"):
                    continue
                prev = _visit_stmt(child, prev)
            return prev

        def _visit_stmt(node, prev_id: str) -> str:
            """递归处理单条语句，返回最后一个节点 id。"""
            line = node.start_point[0] + 1

            # ---- if / else if / else ----
            if node.type == "if_statement":
                cond = node.child_by_field_name("condition")
                cond_text = _src(cond) if cond else "?"
                branch = _new("branch", f"if {cond_text}", line)
                cfg.edges.append(CFGEdge(prev_id, branch))

                merge = _new("statement", "merge", line)

                # then 分支 (consequence)
                conseq = node.child_by_field_name("consequence")
                if conseq:
                    true_entry = _new("statement", "then", line)
                    cfg.edges.append(CFGEdge(branch, true_entry, "true"))
                    if conseq.type == "compound_statement":
                        true_exit = _visit_block(conseq.children, true_entry)
                    else:
                        true_exit = _visit_stmt(conseq, true_entry)
                    cfg.edges.append(CFGEdge(true_exit, merge))
                else:
                    cfg.edges.append(CFGEdge(branch, merge, "true"))

                # else 分支 (alternative) — 可能是 else-if 或 else {}
                alt = node.child_by_field_name("alternative")
                if alt:
                    if alt.type == "if_statement":
                        # else-if: 递归处理，false 边直接连到下一个 if
                        else_exit = _visit_stmt(alt, branch)
                        # 给 branch → alt 加 "false" 标签
                        # 找到最后添加的 branch→alt 边并标注
                        for e in reversed(cfg.edges):
                            if e.src == branch and e.label == "":
                                e.label = "false"
                                break
                        cfg.edges.append(CFGEdge(else_exit, merge))
                    elif alt.type == "else_clause":
                        false_entry = _new("statement", "else", line)
                        cfg.edges.append(CFGEdge(branch, false_entry, "false"))
                        # else 内部可能是 compound_statement 或单条语句
                        body_node = None
                        for ch in alt.children:
                            if ch.type not in ("else",):
                                body_node = ch
                        if body_node and body_node.type == "compound_statement":
                            false_exit = _visit_block(body_node.children, false_entry)
                        elif body_node:
                            false_exit = _visit_stmt(body_node, false_entry)
                        else:
                            false_exit = false_entry
                        cfg.edges.append(CFGEdge(false_exit, merge))
                    else:
                        # 其他情况 (如直接 compound_statement)
                        false_entry = _new("statement", "else", line)
                        cfg.edges.append(CFGEdge(branch, false_entry, "false"))
                        if alt.type == "compound_statement":
                            false_exit = _visit_block(alt.children, false_entry)
                        else:
                            false_exit = _visit_stmt(alt, false_entry)
                        cfg.edges.append(CFGEdge(false_exit, merge))
                else:
                    cfg.edges.append(CFGEdge(branch, merge, "false"))

                return merge

            # ---- switch/case ----
            if node.type == "switch_statement":
                cond = node.child_by_field_name("condition")
                cond_text = _src(cond) if cond else "?"
                sw = _new("branch", f"switch {cond_text}", line)
                cfg.edges.append(CFGEdge(prev_id, sw))
                merge = _new("statement", "merge", line)
                body_node = node.child_by_field_name("body")
                if body_node:
                    for ch in body_node.children:
                        if ch.type == "case_statement":
                            case_label = _src(ch.children[1]) if len(ch.children) > 1 else "default"
                            case_n = _new("statement", f"case {case_label[:30]}", ch.start_point[0] + 1)
                            cfg.edges.append(CFGEdge(sw, case_n, case_label[:30]))
                            case_end = _visit_block(ch.children[2:], case_n) if len(ch.children) > 2 else case_n
                            cfg.edges.append(CFGEdge(case_end, merge))
                else:
                    cfg.edges.append(CFGEdge(sw, merge))
                return merge

            # ---- for / while / do-while 循环 ----
            if node.type in ("for_statement", "while_statement", "do_statement"):
                cond = node.child_by_field_name("condition")
                cond_text = _src(cond) if cond else "true"
                loop_kind = node.type.split("_")[0]  # for / while / do
                loop_br = _new("branch", f"{loop_kind} {cond_text}", line)
                cfg.edges.append(CFGEdge(prev_id, loop_br))
                # 循环体
                body_node = node.child_by_field_name("body")
                if body_node:
                    loop_entry = _new("statement", f"{loop_kind}_body", line)
                    cfg.edges.append(CFGEdge(loop_br, loop_entry, "true"))
                    if body_node.type == "compound_statement":
                        loop_exit = _visit_block(body_node.children, loop_entry)
                    else:
                        loop_exit = _visit_stmt(body_node, loop_entry)
                    cfg.edges.append(CFGEdge(loop_exit, loop_br, "back"))
                merge = _new("statement", "loop_exit", line)
                cfg.edges.append(CFGEdge(loop_br, merge, "false"))
                return merge

            # ---- return ----
            if node.type == "return_statement":
                text = _src(node)[:80].strip()
                ret = _new("statement", text, line)
                cfg.edges.append(CFGEdge(prev_id, ret))
                cfg.edges.append(CFGEdge(ret, exit_n))
                return _new("statement", "unreachable", line)

            # ---- compound_statement (嵌套块) ----
            if node.type == "compound_statement":
                return _visit_block(node.children, prev_id)

            # ---- 其他语句 ----
            text = _src(node)[:60].strip()
            stmt = _new("statement", text, line)
            cfg.edges.append(CFGEdge(prev_id, stmt))
            return stmt

        last = _visit_block(body.children, entry)
        cfg.edges.append(CFGEdge(last, exit_n))
        return cfg

    @staticmethod
    def _get_function_name(decl_node) -> str:
        if decl_node is None:
            return "<anonymous>"
        if decl_node.type == "function_declarator":
            name_node = decl_node.child_by_field_name("declarator")
            return name_node.text.decode(errors="replace") if name_node else "<anonymous>"
        return decl_node.text.decode(errors="replace") if decl_node.text else "<anonymous>"

    @staticmethod
    def _walk(node):
        yield node
        for child in node.children:
            yield from CodeParser._walk(child)


def is_available() -> bool:
    """Check if tree-sitter grammars are installed."""
    return _AVAILABLE
