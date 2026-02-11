"""GrayScope 命令行工具 — 灰盒测试分析平台 CLI。"""

from __future__ import annotations

import json
import sys
from typing import Optional

import httpx
import typer
from rich.console import Console
from rich.table import Table

# ── 模块名称映射 ──────────────────────────────────────────────────────
MODULE_NAMES = {
    "branch_path": "分支路径分析",
    "boundary_value": "边界值分析",
    "error_path": "错误路径分析",
    "call_graph": "调用图构建",
    "concurrency": "并发风险分析",
    "diff_impact": "差异影响分析",
    "coverage_map": "覆盖率映射",
    "postmortem": "事后分析",
    "knowledge_pattern": "缺陷知识库",
}

ANALYSIS_MODULES = "branch_path,boundary_value,error_path,call_graph,concurrency,diff_impact,coverage_map"


def _display_name(mod_id: str) -> str:
    return MODULE_NAMES.get(mod_id, mod_id)


app = typer.Typer(
    name="grayscope",
    help="GrayScope 灰盒测试分析平台命令行工具",
)
console = Console()

BASE_URL = "http://127.0.0.1:18080/api/v1"


def _url(path: str) -> str:
    return f"{BASE_URL}{path}"


def _get(path: str) -> dict:
    r = httpx.get(_url(path), timeout=30)
    r.raise_for_status()
    return r.json()


def _post(path: str, data: dict | None = None) -> dict:
    r = httpx.post(_url(path), json=data, timeout=120)
    r.raise_for_status()
    return r.json()


# ── 健康检查 ──────────────────────────────────────────────────────────


@app.command()
def health(
    json_output: bool = typer.Option(False, "--json", "-j", help="输出原始 JSON"),
):
    """检查后端服务健康状态。"""
    try:
        data = _get("/health")
        if json_output:
            console.print_json(json.dumps(data))
        else:
            d = data.get("data", {})
            console.print(f"[green]✓[/green] 服务: {d.get('service', '?')}")
            console.print(f"  状态: {d.get('status', '?')}")
            console.print(f"  解析器: {'可用' if d.get('parser_available') else '不可用'}")
    except Exception as e:
        console.print(f"[red]✗[/red] 健康检查失败: {e}")
        raise typer.Exit(1)


# ── 分析任务 ──────────────────────────────────────────────────────────

analyze_app = typer.Typer(help="分析任务管理命令")
app.add_typer(analyze_app, name="analyze")


@analyze_app.command("create")
def analyze_create(
    project_id: int = typer.Option(..., "--project", "-p", help="项目 ID"),
    repo_id: int = typer.Option(..., "--repo", "-r", help="仓库 ID"),
    task_type: str = typer.Option("full", "--type", "-t", help="full|file|function|diff"),
    target_path: str = typer.Option(".", "--target", help="分析目标路径"),
    analyzers: str = typer.Option(
        ANALYSIS_MODULES,
        "--analyzers", "-a",
        help="逗号分隔的分析器模块（如 branch_path,boundary_value）",
    ),
    provider: str = typer.Option("ollama", "--provider", help="AI 提供者"),
    model: str = typer.Option("qwen2.5-coder", "--model", help="AI 模型名称"),
    branch: str = typer.Option("main", "--branch", help="Git 分支"),
    base_commit: Optional[str] = typer.Option(None, "--base", help="基准提交（差异分析用）"),
    head_commit: Optional[str] = typer.Option(None, "--head", help="目标提交（差异分析用）"),
    json_output: bool = typer.Option(False, "--json", "-j", help="输出原始 JSON"),
):
    """创建并运行分析任务。"""
    payload = {
        "project_id": project_id,
        "repo_id": repo_id,
        "task_type": task_type,
        "target": {"path": target_path},
        "revision": {
            "branch": branch,
            "base_commit": base_commit,
            "head_commit": head_commit,
        },
        "analyzers": [m.strip() for m in analyzers.split(",")],
        "ai": {"provider": provider, "model": model},
        "options": {"max_files": 500},
    }

    try:
        with console.status("[bold]正在执行分析..."):
            data = _post("/analysis/tasks", payload)
        result = data.get("data", {})

        if json_output:
            console.print_json(json.dumps(data))
        else:
            console.print(f"\n[green]✓[/green] 任务已创建: [bold]{result.get('task_id')}[/bold]")
            console.print(f"  状态: {result.get('status')}")
            progress = result.get("progress", {})
            console.print(
                f"  模块: {progress.get('finished_modules', 0)}/{progress.get('total_modules', 0)} "
                f"(失败: {progress.get('failed_modules', 0)})"
            )
            ms = result.get("module_status", {})
            for mod, st in sorted(ms.items()):
                icon = "✓" if st == "success" else ("✗" if st == "failed" else "◌")
                color = "green" if st == "success" else ("red" if st == "failed" else "yellow")
                console.print(f"    [{color}]{icon}[/{color}] {_display_name(mod)}: {st}")
    except Exception as e:
        console.print(f"[red]✗[/red] 错误: {e}")
        raise typer.Exit(1)


@analyze_app.command("status")
def analyze_status(
    task_id: str = typer.Argument(..., help="任务 ID"),
    json_output: bool = typer.Option(False, "--json", "-j", help="输出原始 JSON"),
):
    """查询分析任务状态。"""
    try:
        data = _get(f"/analysis/tasks/{task_id}")
        if json_output:
            console.print_json(json.dumps(data))
        else:
            d = data.get("data", {})
            console.print(f"任务: [bold]{d.get('task_id')}[/bold]")
            console.print(f"类型: {d.get('task_type')}")
            console.print(f"状态: {d.get('status')}")
            progress = d.get("progress", {})
            console.print(
                f"进度: {progress.get('finished_modules', 0)}/{progress.get('total_modules', 0)}"
            )
            ms = d.get("module_status", {})
            for mod, st in sorted(ms.items()):
                icon = "✓" if st == "success" else ("✗" if st == "failed" else "◌")
                color = "green" if st == "success" else ("red" if st == "failed" else "yellow")
                console.print(f"  [{color}]{icon}[/{color}] {_display_name(mod)}: {st}")
    except Exception as e:
        console.print(f"[red]✗[/red] 错误: {e}")
        raise typer.Exit(1)


@analyze_app.command("results")
def analyze_results(
    task_id: str = typer.Argument(..., help="任务 ID"),
    json_output: bool = typer.Option(False, "--json", "-j", help="输出原始 JSON"),
):
    """查看分析结果摘要。"""
    try:
        data = _get(f"/analysis/tasks/{task_id}/results")
        if json_output:
            console.print_json(json.dumps(data))
        else:
            d = data.get("data", {})
            console.print(f"任务: [bold]{d.get('task_id')}[/bold]  状态: {d.get('status')}")
            risk = d.get("aggregate_risk_score")
            console.print(f"聚合风险评分: [bold]{risk * 100:.1f}%[/bold]" if risk else "聚合风险评分: —")
            console.print()

            table = Table(title="模块分析结果")
            table.add_column("模块名称", style="bold")
            table.add_column("状态")
            table.add_column("风险评分", justify="right")
            table.add_column("发现数", justify="right")

            for m in d.get("modules", []):
                rs = m.get("risk_score")
                risk_str = f"{rs * 100:.1f}%" if rs is not None else "—"
                color = "green" if m["status"] == "success" else "red"
                display = m.get("display_name") or _display_name(m["module"])
                table.add_row(
                    display,
                    f"[{color}]{m['status']}[/{color}]",
                    risk_str,
                    str(m.get("finding_count", 0)),
                )
            console.print(table)
    except Exception as e:
        console.print(f"[red]✗[/red] 错误: {e}")
        raise typer.Exit(1)


# ── 导出 ──────────────────────────────────────────────────────────────


@app.command("export")
def export_task(
    task_id: str = typer.Argument(..., help="要导出的任务 ID"),
    fmt: str = typer.Option("json", "--format", "-f", help="json|csv|findings"),
    output: Optional[str] = typer.Option(None, "--output", "-o", help="输出文件路径"),
):
    """导出分析结果为 JSON、CSV 或原始发现。"""
    try:
        url = _url(f"/analysis/tasks/{task_id}/export?fmt={fmt}")
        r = httpx.get(url, timeout=30)
        r.raise_for_status()
        content = r.text

        if output:
            with open(output, "w", encoding="utf-8") as f:
                f.write(content)
            console.print(f"[green]✓[/green] 已导出到 {output}")
        else:
            console.print(content)
    except Exception as e:
        console.print(f"[red]✗[/red] 导出失败: {e}")
        raise typer.Exit(1)


# ── 事后分析 ──────────────────────────────────────────────────────────


@app.command("postmortem")
def postmortem(
    project_id: int = typer.Option(..., "--project", "-p", help="项目 ID"),
    repo_id: int = typer.Option(..., "--repo", "-r", help="仓库 ID"),
    title: str = typer.Option(..., "--title", help="缺陷标题"),
    severity: str = typer.Option("S1", "--severity", "-s", help="S0|S1|S2|S3"),
    description: str = typer.Option("", "--desc", help="缺陷描述"),
    module_path: str = typer.Option("", "--path", help="相关模块路径"),
    json_output: bool = typer.Option(False, "--json", "-j", help="输出原始 JSON"),
):
    """对逃逸缺陷执行事后分析。"""
    payload = {
        "project_id": project_id,
        "repo_id": repo_id,
        "defect": {
            "title": title,
            "severity": severity,
            "description": description,
            "module_path": module_path,
            "related_commit": "HEAD",
        },
        "ai": {"provider": "ollama", "model": "qwen2.5-coder"},
    }

    try:
        with console.status("[bold]正在执行事后分析..."):
            data = _post("/postmortem", payload)
        result = data.get("data", {})

        if json_output:
            console.print_json(json.dumps(data))
        else:
            console.print(f"\n[green]✓[/green] 事后分析完成: [bold]{result.get('task_id')}[/bold]")
            console.print(f"\n[bold]根因分析:[/bold]")
            for rc in result.get("root_causes", []):
                console.print(
                    f"  • {rc['category']} "
                    f"（置信度: {rc['confidence'] * 100:.0f}%）"
                )

            tests = result.get("preventive_tests", [])
            seen = set()
            unique = [t for t in tests if t["description"] not in seen and not seen.add(t["description"])]
            console.print(f"\n[bold]预防性测试建议（{len(unique)}条）:[/bold]")
            for t in unique[:10]:
                console.print(f"  [{t['priority']}] {t['description']}")

            patterns = result.get("patterns_extracted", [])
            console.print(f"\n[bold]已创建知识库模式: {len(patterns)} 条[/bold]")
    except Exception as e:
        console.print(f"[red]✗[/red] 错误: {e}")
        raise typer.Exit(1)


# ── 知识库 ──────────────────────────────────────────────────────────

knowledge_app = typer.Typer(help="缺陷知识库管理命令")
app.add_typer(knowledge_app, name="knowledge")


@knowledge_app.command("search")
def knowledge_search(
    project_id: int = typer.Option(1, "--project", "-p", help="项目 ID"),
    keyword: str = typer.Option("", "--keyword", "-k", help="搜索关键词"),
    json_output: bool = typer.Option(False, "--json", "-j", help="输出原始 JSON"),
):
    """搜索缺陷知识库中的模式。"""
    try:
        data = _get(f"/knowledge/patterns?project_id={project_id}&keyword={keyword}")
        if json_output:
            console.print_json(json.dumps(data))
        else:
            patterns = data.get("data", {}).get("patterns", [])
            if not patterns:
                console.print("未找到匹配的缺陷模式。")
                return

            table = Table(title=f"缺陷知识库（共 {len(patterns)} 条模式）")
            table.add_column("风险类型", style="bold")
            table.add_column("模式名称")
            table.add_column("命中次数", justify="right")
            table.add_column("置信度", justify="right")

            for p in patterns:
                conf = p.get("trigger_shape", {}).get("confidence", 0)
                table.add_row(
                    p["risk_type"],
                    p["name"][:50],
                    str(p["hit_count"]),
                    f"{conf * 100:.0f}%",
                )
            console.print(table)
    except Exception as e:
        console.print(f"[red]✗[/red] 错误: {e}")
        raise typer.Exit(1)


# ── 入口 ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    app()
