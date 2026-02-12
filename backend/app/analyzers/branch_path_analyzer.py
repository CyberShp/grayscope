"""分支路径分析器。

使用 tree-sitter 控制流图识别代码分支，分类路径类型
（正常/错误/清理/边界），为每个函数产生风险发现。
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

from app.analyzers.base import AnalyzeContext, ModuleResult
from app.analyzers.code_parser import CFG, CodeParser, Symbol

logger = logging.getLogger(__name__)

MODULE_ID = "branch_path"

# 表示错误处理路径的模式
_ERROR_RETURN_RE = re.compile(
    r"return\s+(-\s*\w+|NULL|false|errno|(-1))", re.IGNORECASE
)
_GOTO_RE = re.compile(r"\bgoto\b")
_CLEANUP_LABEL_RE = re.compile(r"^(err|fail|cleanup|out|error|bail)", re.IGNORECASE)


_NULL_CHECK_RE = re.compile(
    r"""
    (?:^|\b)               # 边界
    (\w+)                  # 变量名
    \s*(==|!=)\s*          # 操作符
    (NULL|nullptr|0)\b     # 空值/零值
    """,
    re.VERBOSE | re.IGNORECASE,
)

_NEG_RETURN_RE = re.compile(r"<\s*0|==\s*-1|!=\s*0")

_CONSTANT_CMP_RE = re.compile(
    r"""
    (\w+)\s*(==|!=)\s*     # 变量 == / !=
    ([A-Z_][A-Z0-9_]+)    # 全大写命名常量（如 SDS_NOINIT, O_RDONLY）
    """,
    re.VERBOSE,
)

_BOUNDARY_RE = re.compile(
    r"""
    (\w+)\s*(<=|>=|<|>)\s*  # 变量 比较
    (\w+|\d+)               # 阈值
    """,
    re.VERBOSE,
)


def _classify_branch(label: str) -> str:
    """将分支分类为 error、cleanup、boundary、state 或 normal。

    分类策略：
    1. error   — NULL 检查、负返回值检查、变量名含 err/fail
    2. cleanup — goto 跳转至清理标签
    3. boundary — 数值大小比较 (< > <= >=)
    4. state   — 与命名常量进行等值比较 (== MACRO_CONST)
    5. normal  — 其余
    """
    # 去掉 "if " 前缀和外层括号
    text = label
    if text.startswith("if "):
        text = text[3:]
    text = text.strip()
    if text.startswith("(") and text.endswith(")"):
        text = text[1:-1].strip()

    low = text.lower()

    # --- goto / 清理 ---
    if re.search(r"\bgoto\b", low) or any(kw in low for kw in ("cleanup", "out:", "bail")):
        return "cleanup"

    # --- 拆解复合条件: 对 && 取最严格，对 || 取最宽松 ---
    if "&&" in text or "||" in text:
        op = "&&" if "&&" in text else "||"
        parts = [p.strip() for p in text.split(op)]
        sub_types = [_classify_single_condition(p) for p in parts]
        _PRIORITY = {"error": 0, "cleanup": 1, "boundary": 2, "state": 3, "normal": 4}
        if op == "&&":
            # 取优先级最高（数值最小）的分类
            return min(sub_types, key=lambda t: _PRIORITY.get(t, 4))
        else:
            # 任一子条件最严格即可
            return min(sub_types, key=lambda t: _PRIORITY.get(t, 4))
    return _classify_single_condition(text)


_SIZE_VAR_RE = re.compile(
    r"\b(size|len|length|count|num|idx|index|offset|capacity|initlen|buflen|"
    r"maxlen|minlen|nread|nwrite|nelem|total|avail|remain)\b",
    re.IGNORECASE,
)


def _classify_single_condition(text: str) -> str:
    """分类单个（非复合）条件表达式。"""
    low = text.lower().strip()

    # 变量名本身含 err/fail → error
    if re.search(r"\b(err|error|fail|failure|rc|ret)\b", low):
        return "error"

    # 负返回值检查 → error
    if _NEG_RETURN_RE.search(text):
        return "error"

    # NULL / nullptr 检查 → error（但排除 size 变量 == 0 的情况）
    null_m = _NULL_CHECK_RE.search(text)
    if null_m:
        var_name = null_m.group(1)
        rhs_val = null_m.group(3)
        # 如果是 size/len 类变量 == 0，归为 boundary 而非 error
        if rhs_val == "0" and _SIZE_VAR_RE.search(var_name):
            return "boundary"
        return "error"

    # !ptr 形式（单变量取反）→ error
    if re.match(r"^!\s*\w+$", text.strip()):
        return "error"

    # 边界比较 (含数值或 size 变量) → boundary
    if _BOUNDARY_RE.search(text):
        return "boundary"

    # size/len 类变量在任何比较中 → boundary
    if _SIZE_VAR_RE.search(text) and re.search(r"[<>=!]", text):
        return "boundary"

    # 命名常量等值比较 → state
    if _CONSTANT_CMP_RE.search(text):
        return "state"

    return "normal"


def _score_branch(path_type: str) -> float:
    """单个分支的风险评分。"""
    return {"error": 0.8, "cleanup": 0.85, "boundary": 0.7, "state": 0.5, "normal": 0.3}.get(path_type, 0.3)


def analyze(ctx: AnalyzeContext) -> ModuleResult:
    """对目标范围内所有函数运行分支路径分析。"""
    workspace = ctx["workspace_path"]
    target = ctx["target"]
    options = ctx["options"]
    target_path = Path(workspace) / target.get("path", "")
    max_files = options.get("max_files", 500)

    parser = CodeParser()
    findings: list[dict[str, Any]] = []
    warnings: list[str] = []
    total_functions = 0
    total_branches = 0
    fid = 0

    # 收集源文件
    if target_path.is_file():
        files = [target_path]
    elif target_path.is_dir():
        exts = {".c", ".h", ".cpp", ".cc", ".cxx", ".hpp"}
        files = sorted(
            [p for p in target_path.rglob("*") if p.suffix in exts and p.is_file()]
        )[:max_files]
    else:
        warnings.append(f"目标路径不存在: {target_path}")
        return _result(findings, warnings, 0, 0, 0)

    for fpath in files:
        try:
            symbols = parser.parse_file(fpath)
        except Exception as exc:
            warnings.append(f"解析错误 {fpath}: {exc}")
            continue

        functions = [s for s in symbols if s.kind == "function"]
        total_functions += len(functions)

        for sym in functions:
            cfg = parser.build_cfg(fpath, sym.name)
            if cfg is None:
                continue

            branches = [n for n in cfg.nodes if n.kind == "branch"]
            total_branches += len(branches)

            for br in branches:
                path_type = _classify_branch(br.label)
                score = _score_branch(path_type)
                fid += 1
                rel_path = str(fpath.relative_to(workspace)) if workspace else str(fpath)

                _cond_text = br.label.replace("if ", "")
                _type_zh = {"error": "错误处理", "cleanup": "资源清理", "boundary": "边界条件", "state": "状态/模式判断", "normal": "正常"}
                _reason_zh = {
                    "error": f"函数 {sym.name}() 中存在错误处理分支 {_cond_text}，该分支在异常条件下被触发。如果错误处理逻辑不完善，可能导致资源泄漏、状态不一致或程序崩溃。需要设计覆盖该错误路径的测试用例，验证异常情况下的正确行为。",
                    "cleanup": f"函数 {sym.name}() 中存在资源清理分支 {_cond_text}，该分支负责在退出前释放已分配的资源（如内存、文件句柄、锁）。如果清理路径被跳过或不完整，将导致资源泄漏。需要验证所有退出路径都正确执行了清理操作。",
                    "boundary": f"函数 {sym.name}() 中存在边界条件判断 {_cond_text}，边界值附近（如 off-by-one）是常见的缺陷来源。需要使用边界值、边界±1 和极端值进行测试，确保函数在边界条件处行为正确。",
                    "state": f"函数 {sym.name}() 中的分支 {_cond_text} 是一个状态/模式判断。不同的状态值（如特殊标志、枚举常量）会导致不同的执行路径。需要逐一测试每种状态值下的行为是否正确，特别关注状态切换时的边界情况和默认值处理。",
                    "normal": f"函数 {sym.name}() 中的分支 {_cond_text} 为正常执行路径，但仍需验证该路径在各种输入组合下的行为是否符合预期。",
                }
                findings.append({
                    "finding_id": f"BP-F{fid:04d}",
                    "module_id": MODULE_ID,
                    "risk_type": f"branch_{path_type}",
                    "severity": "S1" if score >= 0.8 else ("S2" if score >= 0.6 else "S3"),
                    "risk_score": round(score, 2),
                    "title": f"{sym.name}() 中的{_type_zh.get(path_type, path_type)}分支",
                    "description": _reason_zh.get(path_type, f"分支条件: {br.label}"),
                    "file_path": rel_path,
                    "symbol_name": sym.name,
                    "line_start": br.line,
                    "line_end": br.line,
                    "evidence": {
                        "branch_id": f"{sym.name}#{br.node_id}",
                        "condition_expr": br.label.replace("if ", ""),
                        "path_type": path_type,
                        "cfg_node_count": len(cfg.nodes),
                        "cfg_edge_count": len(cfg.edges),
                    },
                })

            # 检查源码中的 goto 清理模式
            if _GOTO_RE.search(sym.source):
                fid += 1
                findings.append({
                    "finding_id": f"BP-F{fid:04d}",
                    "module_id": MODULE_ID,
                    "risk_type": "branch_cleanup",
                    "severity": "S2",
                    "risk_score": 0.7,
                    "title": f"{sym.name}() 中的 goto 清理模式",
                    "description": f"函数 {sym.name}() 使用 goto 语句跳转到清理标签进行资源释放。这是 C 语言中常见的错误处理模式，但如果某些错误路径绕过了 goto 跳转，将导致资源泄漏。需要验证：(1) 所有错误路径是否都能到达清理标签；(2) 清理标签处是否释放了所有已分配的资源；(3) 释放顺序是否正确。",
                    "file_path": str(fpath.relative_to(workspace)) if workspace else str(fpath),
                    "symbol_name": sym.name,
                    "line_start": sym.line_start,
                    "line_end": sym.line_end,
                    "evidence": {"pattern": "goto_cleanup"},
                })

    return _result(findings, warnings, total_functions, total_branches, len(files))


def _result(
    findings: list, warnings: list, funcs: int, branches: int, files: int
) -> ModuleResult:
    if not findings:
        risk = 0.0
    else:
        risk = round(sum(f["risk_score"] for f in findings) / len(findings), 4)
    return {
        "module_id": MODULE_ID,
        "status": "success",
        "risk_score": risk,
        "findings": findings,
        "metrics": {
            "files_scanned": files,
            "functions_scanned": funcs,
            "branches_found": branches,
            "findings_count": len(findings),
        },
        "artifacts": [],
        "warnings": warnings,
    }
