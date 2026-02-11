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

        prev = entry
        for child in body.children:
            if child.type in ("{", "}"):
                continue
            line = child.start_point[0] + 1
            text = source[child.start_byte : child.end_byte].decode(errors="replace")[:80]

            if child.type == "if_statement":
                cond = child.child_by_field_name("condition")
                cond_text = source[cond.start_byte : cond.end_byte].decode(errors="replace") if cond else "?"
                branch = _new("branch", f"if {cond_text}", line)
                cfg.edges.append(CFGEdge(prev, branch))
                true_n = _new("statement", "then", line)
                cfg.edges.append(CFGEdge(branch, true_n, "true"))
                false_n = _new("statement", "else", line)
                cfg.edges.append(CFGEdge(branch, false_n, "false"))
                merge = _new("statement", "merge", line)
                cfg.edges.append(CFGEdge(true_n, merge))
                cfg.edges.append(CFGEdge(false_n, merge))
                prev = merge
            elif child.type == "return_statement":
                ret = _new("statement", text.strip(), line)
                cfg.edges.append(CFGEdge(prev, ret))
                cfg.edges.append(CFGEdge(ret, exit_n))
                prev = _new("statement", "unreachable", line)
            else:
                stmt = _new("statement", text.strip()[:60], line)
                cfg.edges.append(CFGEdge(prev, stmt))
                prev = stmt

        cfg.edges.append(CFGEdge(prev, exit_n))
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
