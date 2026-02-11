#!/usr/bin/env python3
"""
GrayScope 测试数据种子脚本
通过直接操作数据库注入丰富的测试数据，用于前端 UI 测试。
"""

import json
import random
import sys
import os
from datetime import datetime, timedelta, timezone

# 添加项目路径
sys.path.insert(0, os.path.dirname(__file__))

from app.core.database import SessionLocal, engine
from app.models import Base
from app.models.project import Project
from app.models.repository import Repository
from app.models.analysis_task import AnalysisTask
from app.models.module_result import AnalysisModuleResult
from app.models.defect_pattern import DefectPattern

# 确保表存在
Base.metadata.create_all(bind=engine)

db = SessionLocal()

print("=" * 60)
print("GrayScope 数据种子脚本")
print("=" * 60)

# ═══════════════════════════════════════════════════════════
# 1. 创建项目
# ═══════════════════════════════════════════════════════════

projects_data = [
    {"name": "storage-core", "description": "核心存储引擎 — KV/对象/块存储核心模块，支撑所有上层存储服务"},
    {"name": "meta-service", "description": "元数据服务 — 分布式元数据管理，包含 raft 共识、epoch 管理和元数据缓存"},
    {"name": "io-gateway", "description": "IO 网关层 — 负责客户端协议解析、请求路由和 QoS 流量控制"},
]

projects = []
for pd in projects_data:
    existing = db.query(Project).filter(Project.name == pd["name"]).first()
    if existing:
        projects.append(existing)
        print(f"  项目已存在: {pd['name']} (id={existing.id})")
    else:
        p = Project(name=pd["name"], description=pd["description"], status="active")
        db.add(p)
        db.flush()
        projects.append(p)
        print(f"  + 创建项目: {pd['name']} (id={p.id})")

db.commit()
print(f"\n共 {len(projects)} 个项目")

# ═══════════════════════════════════════════════════════════
# 2. 创建仓库
# ═══════════════════════════════════════════════════════════

repos_data = [
    {"project": "storage-core", "name": "storage-engine", "git_url": "ssh://git.internal/storage/engine.git", "branch": "main"},
    {"project": "storage-core", "name": "storage-common", "git_url": "ssh://git.internal/storage/common.git", "branch": "main"},
    {"project": "meta-service", "name": "meta-server", "git_url": "ssh://git.internal/meta/server.git", "branch": "develop"},
    {"project": "io-gateway", "name": "io-proxy", "git_url": "ssh://git.internal/io/proxy.git", "branch": "main"},
]

repos = []
for rd in repos_data:
    proj = next(p for p in projects if p.name == rd["project"])
    existing = db.query(Repository).filter(
        Repository.project_id == proj.id, Repository.name == rd["name"]
    ).first()
    if existing:
        repos.append(existing)
        print(f"  仓库已存在: {rd['name']}")
    else:
        r = Repository(
            project_id=proj.id,
            name=rd["name"],
            git_url=rd["git_url"],
            default_branch=rd["branch"],
            local_mirror_path=f"/data/grayscope/repos/{proj.id}/{rd['name']}",
            last_sync_status="synced",
        )
        db.add(r)
        db.flush()
        repos.append(r)
        print(f"  + 创建仓库: {rd['name']} (id={r.id}, project={proj.name})")

db.commit()
print(f"\n共 {len(repos)} 个仓库")

# ═══════════════════════════════════════════════════════════
# 3. 预定义的发现数据模板
# ═══════════════════════════════════════════════════════════

FINDING_TEMPLATES = {
    "branch_path": [
        {"risk_type": "branch_missing_test", "severity": "S2", "title": "alloc_block() 分支 rc!=0 缺少测试覆盖", "file_path": "src/storage/block_alloc.c", "symbol_name": "alloc_block", "line_start": 45, "line_end": 62, "evidence": {"branch_id": "alloc_block#b3", "condition_expr": "rc != 0", "path_type": "error"}},
        {"risk_type": "error_path", "severity": "S1", "title": "create_volume() 错误路径未释放 fd", "file_path": "src/storage/volume.c", "symbol_name": "create_volume", "line_start": 91, "line_end": 112, "evidence": {"branch_id": "create_volume#b7", "condition_expr": "fd < 0", "path_type": "error"}},
        {"risk_type": "cleanup_path", "severity": "S1", "title": "init_cache() 清理路径上内存未释放", "file_path": "src/cache/cache_init.c", "symbol_name": "init_cache", "line_start": 33, "line_end": 50, "evidence": {"branch_id": "init_cache#b2", "path_type": "cleanup"}},
        {"risk_type": "branch_missing_test", "severity": "S3", "title": "read_extent() 边界条件分支", "file_path": "src/storage/extent.c", "symbol_name": "read_extent", "line_start": 120, "line_end": 135, "evidence": {"branch_id": "read_extent#b5", "condition_expr": "offset >= max_offset", "path_type": "normal"}},
    ],
    "boundary_value": [
        {"risk_type": "boundary_miss", "severity": "S2", "title": "write_block() 块大小上界 off-by-one", "file_path": "src/storage/block_io.c", "symbol_name": "write_block", "line_start": 78, "line_end": 95, "evidence": {"constraint_expr": "size <= MAX_BLOCK_SIZE", "derived_bounds": {"min": 0, "max": 4194304}, "candidates": [0, 1, 4194303, 4194304, 4194305]}},
        {"risk_type": "invalid_input_gap", "severity": "S1", "title": "resize_pool() 负数大小未校验", "file_path": "src/pool/pool_mgr.c", "symbol_name": "resize_pool", "line_start": 55, "line_end": 68, "evidence": {"constraint_expr": "new_size > 0", "candidates": [-1, 0, 1]}},
        {"risk_type": "boundary_miss", "severity": "S2", "title": "get_object() 偏移量边界缺失", "file_path": "src/object/obj_get.c", "symbol_name": "get_object", "line_start": 30, "line_end": 48, "evidence": {"constraint_expr": "offset < obj_size", "candidates": [0, "obj_size-1", "obj_size", "obj_size+1"]}},
    ],
    "error_path": [
        {"risk_type": "missing_cleanup", "severity": "S0", "title": "open_volume() 错误路径文件句柄未关闭", "file_path": "src/storage/volume.c", "symbol_name": "open_volume", "line_start": 91, "line_end": 112, "evidence": {"error_trigger": "alloc == NULL", "cleanup_resources_expected": ["fd", "buf"], "cleanup_resources_observed": ["buf"]}},
        {"risk_type": "inconsistent_errno_mapping", "severity": "S2", "title": "delete_block() 返回码与预期不一致", "file_path": "src/storage/block_alloc.c", "symbol_name": "delete_block", "line_start": 150, "line_end": 175, "evidence": {"return_mapping": {"expected": "-ENOENT", "actual": "-EIO"}}},
        {"risk_type": "silent_error_swallow", "severity": "S1", "title": "flush_journal() 静默忽略写入错误", "file_path": "src/journal/journal_flush.c", "symbol_name": "flush_journal", "line_start": 200, "line_end": 228, "evidence": {"error_trigger": "write() < 0", "propagation": "swallowed"}},
        {"risk_type": "missing_cleanup", "severity": "S1", "title": "batch_insert() 部分失败未回滚", "file_path": "src/storage/batch.c", "symbol_name": "batch_insert", "line_start": 45, "line_end": 88, "evidence": {"cleanup_resources_expected": ["txn", "locks"], "cleanup_resources_observed": []}},
    ],
    "call_graph": [
        {"risk_type": "high_fan_out", "severity": "S3", "title": "process_request() 扇出过高（23 个被调用者）", "file_path": "src/gateway/request_handler.c", "symbol_name": "process_request", "line_start": 10, "line_end": 150, "evidence": {"callee_count": 23, "callees": ["validate_auth", "parse_header", "route_request"]}},
        {"risk_type": "deep_impact_surface", "severity": "S2", "title": "meta_update() 调用链深度达到 6 层", "file_path": "src/meta/meta_update.c", "symbol_name": "meta_update", "line_start": 20, "line_end": 80, "evidence": {"depth": 6, "chain": ["meta_update", "validate_epoch", "acquire_lock", "write_log", "sync_replica", "ack_client"]}},
    ],
    "concurrency": [
        {"risk_type": "race_write_without_lock", "severity": "S0", "title": "g_meta_cache 写操作未在锁保护内", "file_path": "src/meta/cache.c", "symbol_name": "update_cache_entry", "line_start": 88, "line_end": 105, "evidence": {"shared_symbol": "g_meta_cache", "access_sites": [{"line": 88, "access": "write", "lock": None}, {"line": 150, "access": "read", "lock": "cache_mu"}]}},
        {"risk_type": "lock_order_inversion", "severity": "S1", "title": "cache_mu / io_mu 锁顺序反转导致死锁风险", "file_path": "src/meta/cache.c", "symbol_name": "flush_cache", "line_start": 200, "line_end": 240, "evidence": {"lock_order": ["cache_mu", "io_mu"], "conflict_order": ["io_mu", "cache_mu"]}},
        {"risk_type": "atomicity_gap", "severity": "S2", "title": "transfer_ownership() 所有权转移非原子", "file_path": "src/pool/ownership.c", "symbol_name": "transfer_ownership", "line_start": 60, "line_end": 85, "evidence": {"operations": ["remove_from_old", "add_to_new"], "gap_between": True}},
    ],
    "diff_impact": [
        {"risk_type": "changed_core_path", "severity": "S1", "title": "txn_commit() 变更落在事务提交核心路径", "file_path": "src/meta/meta_txn.c", "symbol_name": "txn_commit", "line_start": 100, "line_end": 150, "evidence": {"changed_symbols": ["txn_commit"], "impacted_symbols": ["replica_apply", "journal_flush"], "depth": 2}},
        {"risk_type": "transitive_impact", "severity": "S2", "title": "parse_header() 变更传递影响到 5 个下游函数", "file_path": "src/gateway/parser.c", "symbol_name": "parse_header", "line_start": 15, "line_end": 45, "evidence": {"changed_symbols": ["parse_header"], "impacted_symbols": ["validate_request", "route_msg", "log_access", "rate_limit", "send_response"], "depth": 2}},
    ],
    "coverage_map": [
        {"risk_type": "high_risk_low_coverage", "severity": "S1", "title": "open_volume() 高风险但覆盖率仅 31%", "file_path": "src/storage/volume.c", "symbol_name": "open_volume", "line_start": 91, "line_end": 112, "evidence": {"line_coverage": 0.31, "branch_coverage": 0.0, "related_finding_ids": ["branch_path-F0001", "error_path-F0003"]}},
        {"risk_type": "critical_path_uncovered", "severity": "S1", "title": "flush_journal() 关键路径零覆盖", "file_path": "src/journal/journal_flush.c", "symbol_name": "flush_journal", "line_start": 200, "line_end": 228, "evidence": {"line_coverage": 0.0, "branch_coverage": 0.0}},
        {"risk_type": "high_risk_low_coverage", "severity": "S2", "title": "batch_insert() 覆盖率不足", "file_path": "src/storage/batch.c", "symbol_name": "batch_insert", "line_start": 45, "line_end": 88, "evidence": {"line_coverage": 0.45, "branch_coverage": 0.2}},
    ],
}

MODULE_WEIGHTS = {
    "branch_path": 1.1, "boundary_value": 0.9, "error_path": 1.1, "call_graph": 0.6,
    "concurrency": 1.3, "diff_impact": 1.2, "coverage_map": 1.2,
}

TASK_MODULES_LIST = [
    ["branch_path", "boundary_value", "error_path", "call_graph", "concurrency", "diff_impact", "coverage_map"],
    ["branch_path", "error_path", "call_graph", "concurrency"],
    ["branch_path", "boundary_value", "error_path", "call_graph"],
    ["diff_impact", "call_graph"],
    ["branch_path", "error_path", "concurrency", "coverage_map"],
]


def gen_task_id(idx):
    return f"tsk_20260212_{idx:04d}"


def make_findings(module_id, task_idx):
    """根据模板生成发现，加入随机变化。"""
    templates = FINDING_TEMPLATES.get(module_id, [])
    if not templates:
        return []
    # 每个任务随机选取部分发现
    count = random.randint(1, len(templates))
    selected = random.sample(templates, count)
    findings = []
    for i, t in enumerate(selected):
        f = dict(t)
        f["finding_id"] = f"{module_id}-F{task_idx:03d}{i:02d}"
        f["module_id"] = module_id
        f["risk_score"] = round(random.uniform(0.3, 0.95), 2)
        f["description"] = f"在 {f.get('symbol_name', '未知函数')}() 中发现 {f['risk_type']} 类型的风险项：{f['title']}"
        findings.append(f)
    return findings


# ═══════════════════════════════════════════════════════════
# 4. 创建分析任务和模块结果
# ═══════════════════════════════════════════════════════════

print("\n创建分析任务...")

task_idx = 1
now = datetime.now(timezone.utc)

for proj_idx, proj in enumerate(projects):
    proj_repos = [r for r in repos if r.project_id == proj.id]
    if not proj_repos:
        continue

    # 每个项目创建 3-5 个任务
    num_tasks = random.randint(3, 5)
    for t_idx in range(num_tasks):
        tid = gen_task_id(task_idx)

        # 检查是否已存在
        existing = db.query(AnalysisTask).filter(AnalysisTask.task_id == tid).first()
        if existing:
            print(f"  任务已存在: {tid}")
            task_idx += 1
            continue

        repo = random.choice(proj_repos)
        modules = random.choice(TASK_MODULES_LIST)
        task_type = random.choice(["full", "full", "full", "file", "diff"])
        created_at = now - timedelta(days=num_tasks - t_idx, hours=random.randint(0, 12))

        # 大部分任务成功，少数失败
        if t_idx == num_tasks - 1:
            task_status = "success"  # 最新任务总是成功
        else:
            task_status = random.choice(["success", "success", "success", "partial_failed", "failed"])

        task = AnalysisTask(
            task_id=tid,
            project_id=proj.id,
            repo_id=repo.id,
            task_type=task_type,
            status=task_status,
            target_json=json.dumps({"path": "src/", "functions": []}),
            revision_json=json.dumps({"branch": repo.default_branch, "base_commit": None, "head_commit": None}),
            analyzers_json=json.dumps(modules),
            ai_json=json.dumps({"provider": "ollama", "model": "qwen2.5-coder", "prompt_profile": "default-v1"}),
            options_json=json.dumps({"callgraph_depth": 2, "max_files": 500, "risk_threshold": 0.6}),
            created_at=created_at,
            updated_at=created_at + timedelta(minutes=random.randint(2, 15)),
            finished_at=created_at + timedelta(minutes=random.randint(2, 15)) if task_status != "running" else None,
        )
        db.add(task)
        db.flush()

        # 创建模块结果
        total_risk = 0
        total_weight = 0
        total_findings_count = 0

        for mod_id in modules:
            if task_status == "failed":
                mod_status = "failed"
                findings = []
                risk_score = None
            elif task_status == "partial_failed" and random.random() < 0.3:
                mod_status = "failed"
                findings = []
                risk_score = None
            else:
                mod_status = "success"
                findings = make_findings(mod_id, task_idx)
                risk_score = round(random.uniform(0.2, 0.9), 3) if findings else 0.0

            total_findings_count += len(findings)
            if risk_score is not None:
                w = MODULE_WEIGHTS.get(mod_id, 1.0)
                total_risk += risk_score * w
                total_weight += w

            mr = AnalysisModuleResult(
                task_id=task.id,
                module_id=mod_id,
                status=mod_status,
                risk_score=risk_score,
                findings_json=json.dumps(findings, ensure_ascii=False),
                metrics_json=json.dumps({"functions_scanned": random.randint(20, 200), "input_fingerprint": f"sha256:{random.randbytes(8).hex()}"}),
                artifacts_json=json.dumps([{"type": "json", "path": f"artifacts/{tid}/{mod_id}/findings.json"}]),
                ai_summary_json=json.dumps({"prompt_version": f"{mod_id}-v3", "provider": "ollama", "model": "qwen2.5-coder"}) if mod_status == "success" else None,
                error_json=json.dumps({"error": "模型超时", "retry_count": 2}) if mod_status == "failed" else None,
                started_at=created_at + timedelta(seconds=30),
                finished_at=created_at + timedelta(minutes=random.randint(1, 10)),
            )
            db.add(mr)

        # 计算聚合风险分
        if total_weight > 0:
            task.aggregate_risk_score = round(total_risk / total_weight, 3)

        db.flush()
        print(f"  + 任务 {tid}: {task_type}, {task_status}, {len(modules)} 模块, {total_findings_count} 发现, 风险={task.aggregate_risk_score}")
        task_idx += 1

db.commit()

# ═══════════════════════════════════════════════════════════
# 5. 创建缺陷模式（知识库）
# ═══════════════════════════════════════════════════════════

print("\n创建缺陷模式...")

patterns_data = [
    {
        "pattern_key": "fd_leak_on_error",
        "name": "错误路径文件句柄泄漏",
        "risk_type": "resource_lifecycle_leak",
        "trigger_shape": {"keywords": ["fd", "close", "error", "goto", "cleanup"], "confidence": 0.92},
        "code_signature": {"pattern": "open.*goto.*without close"},
        "test_template": {"test_suggestions": [
            {"description": "在 open() 后注入错误，验证 fd 是否正确关闭", "priority": "P1"},
            {"description": "使用 valgrind 检查文件描述符泄漏", "priority": "P2"},
        ]},
    },
    {
        "pattern_key": "meta_retry_epoch_gap",
        "name": "元数据重试与 epoch 间隙",
        "risk_type": "retry_logic_flaw",
        "trigger_shape": {"keywords": ["epoch", "retry", "stale", "meta", "version"], "confidence": 0.88},
        "code_signature": {"pattern": "retry without epoch check"},
        "test_template": {"test_suggestions": [
            {"description": "在重试路径中注入故障切换，验证 epoch 一致性", "priority": "P1"},
            {"description": "并发重试场景下 epoch 版本校验", "priority": "P1"},
        ]},
    },
    {
        "pattern_key": "race_shared_cache",
        "name": "共享缓存竞态写入",
        "risk_type": "concurrency_race",
        "trigger_shape": {"keywords": ["cache", "mutex", "lock", "write", "shared"], "confidence": 0.85},
        "code_signature": {"pattern": "write shared without lock"},
        "test_template": {"test_suggestions": [
            {"description": "多线程并发更新缓存条目，检测数据一致性", "priority": "P1"},
            {"description": "使用 ThreadSanitizer 检测竞态", "priority": "P2"},
        ]},
    },
    {
        "pattern_key": "boundary_block_size",
        "name": "块大小边界越界",
        "risk_type": "boundary_not_covered",
        "trigger_shape": {"keywords": ["block", "size", "max", "overflow", "boundary"], "confidence": 0.78},
        "code_signature": {"pattern": "size comparison without equal check"},
        "test_template": {"test_suggestions": [
            {"description": "使用 MAX_BLOCK_SIZE, MAX_BLOCK_SIZE+1, 0, -1 作为输入测试", "priority": "P1"},
        ]},
    },
    {
        "pattern_key": "txn_rollback_incomplete",
        "name": "事务回滚不完整",
        "risk_type": "error_path_not_tested",
        "trigger_shape": {"keywords": ["transaction", "rollback", "abort", "partial", "commit"], "confidence": 0.82},
        "code_signature": {"pattern": "txn_abort without full resource release"},
        "test_template": {"test_suggestions": [
            {"description": "在事务中间步骤注入失败，验证完整回滚", "priority": "P1"},
            {"description": "检查回滚后资源状态一致性", "priority": "P1"},
        ]},
    },
    {
        "pattern_key": "lock_order_deadlock",
        "name": "锁顺序死锁",
        "risk_type": "concurrency_race",
        "trigger_shape": {"keywords": ["lock", "order", "deadlock", "mutex", "acquire"], "confidence": 0.91},
        "code_signature": {"pattern": "nested lock acquisition in reverse order"},
        "test_template": {"test_suggestions": [
            {"description": "并发场景模拟双向加锁顺序，检测死锁", "priority": "P1"},
        ]},
    },
]

for pd in patterns_data:
    proj = projects[0]  # 关联到第一个项目
    existing = db.query(DefectPattern).filter(
        DefectPattern.project_id == proj.id,
        DefectPattern.pattern_key == pd["pattern_key"]
    ).first()
    if existing:
        print(f"  模式已存在: {pd['name']}")
        continue

    dp = DefectPattern(
        project_id=proj.id,
        pattern_key=pd["pattern_key"],
        name=pd["name"],
        risk_type=pd["risk_type"],
        trigger_shape_json=json.dumps(pd["trigger_shape"], ensure_ascii=False),
        code_signature_json=json.dumps(pd["code_signature"], ensure_ascii=False),
        test_template_json=json.dumps(pd["test_template"], ensure_ascii=False),
        example_json=json.dumps({}),
        hit_count=random.randint(1, 12),
    )
    db.add(dp)
    print(f"  + 缺陷模式: {pd['name']} ({pd['risk_type']})")

db.commit()

# ═══════════════════════════════════════════════════════════
# 6. 持久化测试用例
# ═══════════════════════════════════════════════════════════

from app.services.testcase_service import persist_test_cases
from app.models.test_case import TestCase

total_tc = 0
for task in db.query(AnalysisTask).filter(AnalysisTask.status == "success").all():
    count = persist_test_cases(db, task)
    total_tc += count
    if count > 0:
        print(f"  + 持久化 {count} 条测试用例 (任务 {task.task_id})")

# ═══════════════════════════════════════════════════════════
# 7. 输出总结
# ═══════════════════════════════════════════════════════════

total_projects = db.query(Project).count()
total_repos = db.query(Repository).count()
total_tasks = db.query(AnalysisTask).count()
total_results = db.query(AnalysisModuleResult).count()
total_patterns = db.query(DefectPattern).count()
total_test_cases = db.query(TestCase).count()

print("\n" + "=" * 60)
print("数据注入完成！")
print("=" * 60)
print(f"  项目:       {total_projects}")
print(f"  仓库:       {total_repos}")
print(f"  分析任务:   {total_tasks}")
print(f"  模块结果:   {total_results}")
print(f"  缺陷模式:   {total_patterns}")
print(f"  测试用例:   {total_test_cases}")
print()
print("现在可以访问前端查看效果:")
print("  http://localhost:15173/projects")
print()

db.close()
