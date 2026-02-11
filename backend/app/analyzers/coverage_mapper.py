"""覆盖率映射分析器。

将代码覆盖率数据与其他模块的风险发现叠加，
识别需要测试关注的「高风险低覆盖」区域。

支持的覆盖率输入格式：
- LCOV 格式（.info 文件）
- JSON 格式（自定义或 gcov-json）
- 纯文本函数级覆盖率
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.analyzers.base import AnalyzeContext, ModuleResult

logger = logging.getLogger(__name__)

MODULE_ID = "coverage_map"

# 默认阈值
DEFAULT_LINE_COV_THRESHOLD = 0.7
DEFAULT_BRANCH_COV_THRESHOLD = 0.5


@dataclass
class FileCoverage:
    """单个文件的覆盖率数据。"""
    file_path: str
    lines_total: int = 0
    lines_hit: int = 0
    branches_total: int = 0
    branches_hit: int = 0
    function_coverage: dict[str, bool] = field(default_factory=dict)
    line_details: dict[int, int] = field(default_factory=dict)

    @property
    def line_rate(self) -> float:
        return self.lines_hit / self.lines_total if self.lines_total > 0 else 0.0

    @property
    def branch_rate(self) -> float:
        return self.branches_hit / self.branches_total if self.branches_total > 0 else 0.0


def parse_lcov(lcov_path: Path) -> dict[str, FileCoverage]:
    """解析 LCOV info 文件为覆盖率映射。"""
    coverage: dict[str, FileCoverage] = {}
    current: FileCoverage | None = None

    try:
        content = lcov_path.read_text(errors="replace")
    except Exception:
        return coverage

    for line in content.split("\n"):
        line = line.strip()
        if line.startswith("SF:"):
            fpath = line[3:]
            current = FileCoverage(file_path=fpath)
            coverage[fpath] = current
        elif line.startswith("DA:") and current:
            parts = line[3:].split(",")
            if len(parts) >= 2:
                ln = int(parts[0])
                hits = int(parts[1])
                current.line_details[ln] = hits
                current.lines_total += 1
                if hits > 0:
                    current.lines_hit += 1
        elif line.startswith("FN:") and current:
            parts = line[3:].split(",")
            if len(parts) >= 2:
                fn_name = parts[1]
                current.function_coverage[fn_name] = False
        elif line.startswith("FNDA:") and current:
            parts = line[5:].split(",")
            if len(parts) >= 2:
                hits = int(parts[0])
                fn_name = parts[1]
                current.function_coverage[fn_name] = hits > 0
        elif line.startswith("BRDA:") and current:
            parts = line[5:].split(",")
            current.branches_total += 1
            if len(parts) >= 4 and parts[3] != "-" and int(parts[3]) > 0:
                current.branches_hit += 1
        elif line == "end_of_record":
            current = None

    return coverage


def parse_json_coverage(json_path: Path) -> dict[str, FileCoverage]:
    """解析 JSON 覆盖率文件。"""
    coverage: dict[str, FileCoverage] = {}
    try:
        data = json.loads(json_path.read_text(errors="replace"))
    except Exception:
        return coverage

    files = data.get("files", data)
    if isinstance(files, dict):
        for fpath, fdata in files.items():
            if isinstance(fdata, dict):
                cov = FileCoverage(
                    file_path=fpath,
                    lines_total=fdata.get("lines_total", 0),
                    lines_hit=fdata.get("lines_hit", 0),
                    branches_total=fdata.get("branches_total", 0),
                    branches_hit=fdata.get("branches_hit", 0),
                )
                funcs = fdata.get("functions", {})
                if isinstance(funcs, dict):
                    cov.function_coverage = {k: bool(v) for k, v in funcs.items()}
                coverage[fpath] = cov

    return coverage


def load_coverage(options: dict) -> dict[str, FileCoverage]:
    """从配置的来源加载覆盖率数据。"""
    cov_path_str = options.get("coverage_path", "")
    if not cov_path_str:
        return {}

    cov_path = Path(cov_path_str)
    if not cov_path.exists():
        return {}

    if cov_path.suffix == ".info":
        return parse_lcov(cov_path)
    elif cov_path.suffix == ".json":
        return parse_json_coverage(cov_path)
    else:
        result = parse_json_coverage(cov_path)
        if not result:
            result = parse_lcov(cov_path)
        return result


def analyze(ctx: AnalyzeContext) -> ModuleResult:
    """运行覆盖率映射分析。"""
    workspace = ctx["workspace_path"]
    options = ctx["options"]
    upstream = ctx["upstream_results"]

    findings: list[dict[str, Any]] = []
    warnings: list[str] = []
    fid = 0

    line_threshold = options.get("line_coverage_threshold", DEFAULT_LINE_COV_THRESHOLD)
    branch_threshold = options.get("branch_coverage_threshold", DEFAULT_BRANCH_COV_THRESHOLD)

    # 加载覆盖率数据
    coverage = load_coverage(options)

    # 收集上游风险发现
    upstream_findings: list[dict] = []
    for mod_id in ("branch_path", "boundary_value", "error_path", "concurrency", "diff_impact"):
        mod_data = upstream.get(mod_id, {})
        upstream_findings.extend(mod_data.get("findings", []))

    if not coverage and not upstream_findings:
        warnings.append(
            "未提供覆盖率数据且无上游发现。"
            "请在选项中提供 coverage_path 或先运行分支路径/边界值/错误路径分析。"
        )
        return _result(findings, warnings, 0, 0, 0)

    # 情况 1：有覆盖率数据 — 与风险发现叠加
    if coverage:
        for file_path, cov in coverage.items():
            if cov.line_rate < line_threshold:
                related = [
                    f for f in upstream_findings
                    if f.get("file_path", "").endswith(file_path)
                    or file_path.endswith(f.get("file_path", "___none___"))
                ]
                related_ids = [f["finding_id"] for f in related[:10]]

                if related:
                    fid += 1
                    max_risk = max(f.get("risk_score", 0.5) for f in related)
                    findings.append({
                        "finding_id": f"CM-F{fid:04d}",
                        "module_id": MODULE_ID,
                        "risk_type": "high_risk_low_coverage",
                        "severity": "S1" if max_risk >= 0.7 else "S2",
                        "risk_score": round(max_risk * (1 - cov.line_rate), 4),
                        "title": (
                            f"高风险低覆盖: {file_path} "
                            f"（行覆盖率 {cov.line_rate:.0%}）"
                        ),
                        "description": (
                            f"文件有 {len(related)} 条风险发现但行覆盖率仅 "
                            f"{cov.line_rate:.1%}。分支覆盖率: {cov.branch_rate:.1%}。"
                        ),
                        "file_path": file_path,
                        "symbol_name": "",
                        "line_start": 0,
                        "line_end": 0,
                        "evidence": {
                            "line_coverage": round(cov.line_rate, 4),
                            "branch_coverage": round(cov.branch_rate, 4),
                            "threshold": line_threshold,
                            "related_finding_ids": related_ids,
                        },
                    })

            for fn_name, covered in cov.function_coverage.items():
                if not covered:
                    fn_findings = [
                        f for f in upstream_findings
                        if f.get("symbol_name") == fn_name
                    ]
                    if fn_findings:
                        fid += 1
                        max_risk = max(f.get("risk_score", 0.5) for f in fn_findings)
                        findings.append({
                            "finding_id": f"CM-F{fid:04d}",
                            "module_id": MODULE_ID,
                            "risk_type": "critical_path_uncovered",
                            "severity": "S1",
                            "risk_score": round(max_risk, 4),
                            "title": f"高风险函数 {fn_name} 覆盖率为 0%",
                            "description": (
                                f"函数 {fn_name}（{file_path}）有 {len(fn_findings)} "
                                "条风险发现但测试覆盖率为零。"
                            ),
                            "file_path": file_path,
                            "symbol_name": fn_name,
                            "line_start": 0,
                            "line_end": 0,
                            "evidence": {
                                "line_coverage": 0.0,
                                "related_finding_ids": [
                                    f["finding_id"] for f in fn_findings[:10]
                                ],
                            },
                        })

    # 情况 2：无覆盖率数据 — 基于风险生成建议
    if not coverage and upstream_findings:
        file_findings: dict[str, list[dict]] = {}
        for f in upstream_findings:
            fp = f.get("file_path", "unknown")
            file_findings.setdefault(fp, []).append(f)

        for file_path, file_fns in file_findings.items():
            if len(file_fns) >= 3:
                avg_risk = sum(f.get("risk_score", 0.5) for f in file_fns) / len(file_fns)
                fid += 1
                findings.append({
                    "finding_id": f"CM-F{fid:04d}",
                    "module_id": MODULE_ID,
                    "risk_type": "high_risk_low_coverage",
                    "severity": "S2",
                    "risk_score": round(avg_risk, 4),
                    "title": f"高风险文件需要覆盖率数据: {file_path}",
                    "description": (
                        f"文件有 {len(file_fns)} 条风险发现（平均风险 "
                        f"{avg_risk:.2f}）但无覆盖率数据。建议运行插桩测试。"
                    ),
                    "file_path": file_path,
                    "symbol_name": "",
                    "line_start": 0,
                    "line_end": 0,
                    "evidence": {
                        "line_coverage": None,
                        "findings_count": len(file_fns),
                        "avg_risk": round(avg_risk, 4),
                        "related_finding_ids": [
                            f["finding_id"] for f in file_fns[:10]
                        ],
                    },
                })

    files_with_cov = len(coverage)
    total_upstream = len(upstream_findings)
    return _result(findings, warnings, files_with_cov, total_upstream, len(findings))


def _result(
    findings: list, warnings: list,
    files_with_coverage: int, upstream_findings: int,
    findings_count: int,
) -> ModuleResult:
    risk = round(sum(f["risk_score"] for f in findings) / len(findings), 4) if findings else 0.0
    return {
        "module_id": MODULE_ID,
        "status": "success",
        "risk_score": risk,
        "findings": findings,
        "metrics": {
            "files_with_coverage": files_with_coverage,
            "upstream_findings_evaluated": upstream_findings,
            "findings_count": findings_count,
        },
        "artifacts": [],
        "warnings": warnings,
    }
