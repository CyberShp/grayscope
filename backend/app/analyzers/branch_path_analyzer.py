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


def _classify_branch(label: str) -> str:
    """将分支分类为 normal、error、cleanup 或 boundary。"""
    low = label.lower()
    if any(kw in low for kw in ("null", "== 0", "< 0", "!= 0", "err", "fail")):
        return "error"
    if any(kw in low for kw in ("goto", "cleanup", "out:")):
        return "cleanup"
    if any(kw in low for kw in ("<=", ">=", "> max", "< min", "size", "len", "count")):
        return "boundary"
    return "normal"


def _score_branch(path_type: str) -> float:
    """单个分支的风险评分。"""
    return {"error": 0.8, "cleanup": 0.85, "boundary": 0.7, "normal": 0.3}[path_type]


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

                findings.append({
                    "finding_id": f"BP-F{fid:04d}",
                    "module_id": MODULE_ID,
                    "risk_type": f"branch_{path_type}",
                    "severity": "S1" if score >= 0.8 else ("S2" if score >= 0.6 else "S3"),
                    "risk_score": round(score, 2),
                    "title": f"{path_type} branch in {sym.name}",
                    "description": f"Branch condition: {br.label}",
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
                    "title": f"goto cleanup pattern in {sym.name}",
                    "description": "函数使用 goto 进行清理；验证所有路径是否到达清理标签",
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
