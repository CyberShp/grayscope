"""分支路径分析器。

使用 tree-sitter 控制流图识别代码分支，经规则引擎产出风险发现
（高复杂度、error/cleanup 分支、switch 缺 default、goto 清理）。
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import app.analyzers.rules.branch_path_rules  # noqa: F401 — 注册 branch_path 规则
from app.analyzers.base import AnalyzeContext, ModuleResult
from app.analyzers.code_parser import CFG, CodeParser, Symbol
from app.analyzers.rules import get_rules

logger = logging.getLogger(__name__)

MODULE_ID = "branch_path"


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

    rules = get_rules(MODULE_ID)

    for fpath in files:
        try:
            symbols = parser.parse_file(fpath)
        except Exception as exc:
            warnings.append(f"解析错误 {fpath}: {exc}")
            continue

        functions = [s for s in symbols if s.kind == "function"]
        total_functions += len(functions)
        rel_path = str(fpath.relative_to(workspace)) if workspace else str(fpath)

        for sym in functions:
            cfg = parser.build_cfg(fpath, sym.name)
            if cfg is None:
                continue

            branches = [n for n in cfg.nodes if n.kind == "branch"]
            total_branches += len(branches)

            rule_kw: dict[str, Any] = {
                "symbol": sym,
                "branches": branches,
                "cfg": cfg,
                "rel_path": rel_path,
                "workspace": workspace,
                "options": options,
            }
            for rule in rules:
                for f in rule.evaluate(**rule_kw):
                    fid += 1
                    f["finding_id"] = f"BP-F{fid:04d}"
                    findings.append(f)

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
