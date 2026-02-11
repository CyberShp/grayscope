# GrayScope 分析器契约（V1）

## 1. 目的

本文定义各分析模块的实现契约，便于不同工程师或编码代理独立实现模块并无缝集成。

## 2. 通用契约

### 2.1 分析上下文（AnalyzeContext）

所有分析器的输入均基于统一的上下文字典：

```python
class AnalyzeContext(TypedDict):
    task_id: str
    project_id: int
    repo_id: int
    workspace_path: str
    target: dict
    revision: dict
    options: dict
    upstream_results: dict[str, dict]
```

- `task_id`：任务外部 ID  
- `project_id` / `repo_id`：项目与仓库 ID  
- `workspace_path`：工作区根路径（已拉取代码）  
- `target`：分析范围（path、functions 等）  
- `revision`：分支、base_commit、head_commit  
- `options`：callgraph_depth、max_files、risk_threshold 等  
- `upstream_results`：上游模块结果，key 为 module_id

### 2.2 模块结果（ModuleResult）

所有分析器的输出必须符合以下结构：

```python
class ModuleResult(TypedDict):
    module_id: str
    status: str
    risk_score: float
    findings: list[dict]
    metrics: dict
    artifacts: list[dict]
    warnings: list[str]
```

### 2.3 状态规则

- `success`：模块输出有效且已持久化  
- `failed`：执行失败，须包含错误原因  
- `skipped`：依赖失败或当前不适用  
- `cancelled`：任务被取消  

### 2.4 风险分规则

- 取值范围 `[0, 1]`  
- 模块级：  
  - `0.0`：无风险证据  
  - `0.1–0.4`：低  
  - `0.5–0.7`：中  
  - `0.8–1.0`：高  

### 2.5 发现项统一字段

每条发现（finding）必须包含：

- `finding_id`、`module_id`、`risk_type`、`severity`、`risk_score`  
- `title`、`description`  
- `file_path`、`symbol_name`、`line_start`、`line_end`  
- `evidence`（可选，模块自定义）  

严重程度：`S0` 关键数据安全，`S1` 高功能影响，`S2` 中稳定性影响，`S3` 低影响或可维护性风险。

---

## 3. 各模块契约

### 3.1 branch_path — 分支路径分析

| 项 | 说明 |
|----|------|
| **模块 ID** | `branch_path` |
| **中文名称** | 分支路径分析 |
| **描述** | 基于控制流图（CFG）识别未覆盖分支、错误路径与清理路径，用于补充测试与灰盒用例设计。 |

**输入（AnalyzeContext）**  
- 目标范围内的 AST 符号  
- 各函数的 CFG 节点与边  

**输出（ModuleResult）**  
- `findings`：见下方 risk_type  
- `artifacts`：至少包含 `cfg.json`  

**依赖关系**  
- 依赖解析器核心（AST/CFG），无其他模块依赖  

**发现类型（risk_type）**  

| risk_type | 描述 |
|-----------|------|
| branch_missing_test | 分支缺少对应测试 |
| error_path | 错误返回路径未被覆盖或未测试 |
| cleanup_path | 清理路径（如资源释放）未被覆盖 |

**evidence 示例**  
```json
{
  "branch_id": "meta_create#b12",
  "condition_expr": "rc != 0",
  "path_type": "error",
  "pred_nodes": ["n10"],
  "succ_nodes": ["n13"],
  "reachable_hint": "conditional"
}
```

**评分规则**  
- 未覆盖错误路径/清理路径数量与权重加权，归一化到 [0,1]；关键路径未覆盖时分数偏高。  

---

### 3.2 boundary_value — 边界值分析

| 项 | 说明 |
|----|------|
| **模块 ID** | `boundary_value` |
| **中文名称** | 边界值分析 |
| **描述** | 从表达式与比较、数组访问等推导边界，识别边界缺失与无效输入区间。 |

**输入（AnalyzeContext）**  
- AST 中的表达式与比较  
- 数组/下标访问表达式  

**输出（ModuleResult）**  
- `findings`：risk_type 见下表；候选值放在 `evidence.candidates`  

**依赖关系**  
- 仅依赖解析器核心  

**发现类型（risk_type）**  

| risk_type | 描述 |
|-----------|------|
| boundary_miss | 边界条件未被测试（如 off-by-one） |
| invalid_input_gap | 无效或未覆盖的输入区间 |

**evidence 示例**  
```json
{
  "constraint_expr": "size <= max_size",
  "derived_bounds": { "min": 1, "max": 1048576 },
  "candidates": [0, 1, 2, 1048575, 1048576, 1048577]
}
```

**评分规则**  
- 根据边界缺失数量与关键程度（如 0、max、max+1）加权后归一化到 [0,1]。  

---

### 3.3 error_path — 错误路径分析

| 项 | 说明 |
|----|------|
| **模块 ID** | `error_path` |
| **中文名称** | 错误路径分析 |
| **描述** | 分析函数内错误返回与清理逻辑，发现资源泄漏、错误码不一致、静默吞错等。 |

**输入（AnalyzeContext）**  
- 函数控制流  
- 返回码与清理语句（如 close、free）  

**输出（ModuleResult）**  
- `findings`：risk_type 见下表  

**依赖关系**  
- 依赖解析器核心  

**发现类型（risk_type）**  

| risk_type | 描述 |
|-----------|------|
| missing_cleanup | 错误路径上缺少资源释放/清理 |
| inconsistent_errno_mapping | 返回码与预期（如 -ENOMEM）不一致 |
| silent_error_swallow | 错误被静默忽略未向上传递 |

**evidence 示例**  
```json
{
  "error_trigger": "alloc == NULL",
  "cleanup_resources_expected": ["fd", "buf"],
  "cleanup_resources_observed": ["buf"],
  "return_mapping": { "expected": "-ENOMEM", "actual": "-EIO" }
}
```

**评分规则**  
- 缺失清理、错误码错误、静默吞错按严重程度加权，归一化到 [0,1]；缺失关键清理时分数偏高。  

---

### 3.4 call_graph — 调用图构建

| 项 | 说明 |
|----|------|
| **模块 ID** | `call_graph` |
| **中文名称** | 调用图构建 |
| **描述** | 构建符号级调用图，为下游影响分析、扩散分析提供基础；可附带高扇出、大影响面等发现。 |

**输入（AnalyzeContext）**  
- 符号表  
- 调用表达式  

**输出（ModuleResult）**  
- `artifacts`：至少包含 `call_graph.json`  
- 可选 findings：high_fan_out、deep_impact_surface  

**依赖关系**  
- 独立基础模块，无其他分析器依赖  

**发现类型（risk_type）**  

| risk_type | 描述 |
|-----------|------|
| high_fan_out | 调用者/被调用者过多，变更影响面大 |
| deep_impact_surface | 调用链深或影响面广 |

**artifact 结构示例**  
```json
{
  "nodes": [{"symbol": "meta_create"}],
  "edges": [{"src": "meta_create", "dst": "alloc_meta"}]
}
```

**评分规则**  
- 若无 findings 则 risk_score 可为 0 或低分；有 high_fan_out / deep_impact_surface 时按节点数/深度加权归一化。  

---

### 3.5 concurrency — 并发风险分析

| 项 | 说明 |
|----|------|
| **模块 ID** | `concurrency` |
| **中文名称** | 并发风险分析 |
| **描述** | 分析共享变量访问与锁的获取/释放，识别未加锁写、锁顺序反转、原子性缺口等。 |

**输入（AnalyzeContext）**  
- 共享变量引用  
- 锁获取/释放轨迹  
- 线程入口函数（若可识别）  

**依赖关系**  
- 依赖解析器核心；可选依赖 call_graph  

**发现类型（risk_type）**  

| risk_type | 描述 |
|-----------|------|
| race_write_without_lock | 写共享变量未在锁内 |
| lock_order_inversion | 锁顺序与约定相反，存在死锁风险 |
| atomicity_gap | 本应原子的一组操作之间存在缺口 |

**evidence 示例**  
```json
{
  "shared_symbol": "g_meta_cache",
  "access_sites": [
    {"file": "src/meta/cache.c", "line": 88, "access": "write", "lock": null},
    {"file": "src/meta/cache.c", "line": 150, "access": "read", "lock": "cache_mu"}
  ],
  "lock_order": ["cache_mu", "io_mu"],
  "conflict_order": ["io_mu", "cache_mu"]
}
```

**评分规则**  
- 根据竞态严重程度、锁顺序错误、原子性缺口数量与影响加权，归一化到 [0,1]。  

---

### 3.6 diff_impact — 差异影响分析

| 项 | 说明 |
|----|------|
| **模块 ID** | `diff_impact` |
| **中文名称** | 差异影响分析 |
| **描述** | 结合 base/head 的 diff 与调用图，识别变更波及的核心路径与回归热点。 |

**输入（AnalyzeContext）**  
- 统一 diff（base_commit、head_commit）  
- `upstream_results["call_graph"]`（调用图产物）  

**输出（ModuleResult）**  
- `findings`：risk_type 见下表  

**依赖关系**  
- 依赖 call_graph 输出  

**发现类型（risk_type）**  

| risk_type | 描述 |
|-----------|------|
| changed_core_path | 变更落在核心路径上 |
| transitive_impact | 变更通过调用链产生传递影响 |
| hotspot_regression_risk | 变更涉及历史热点或易回归区域 |

**evidence 示例**  
```json
{
  "changed_files": ["src/meta/meta_txn.c"],
  "changed_symbols": ["txn_commit"],
  "impacted_symbols": ["replica_apply", "journal_flush"],
  "depth": 2
}
```

**评分规则**  
- 按变更影响深度、涉及核心路径与热点数量加权，归一化到 [0,1]。  

---

### 3.7 coverage_map — 覆盖率映射

| 项 | 说明 |
|----|------|
| **模块 ID** | `coverage_map` |
| **中文名称** | 覆盖率映射 |
| **描述** | 将行/分支覆盖率与其它模块的发现结合，识别高风险低覆盖与关键路径未覆盖。 |

**输入（AnalyzeContext）**  
- 覆盖率适配器输出：行覆盖率图、可选分支覆盖率图  
- `upstream_results` 中至少包含 M01/M02/M03/concurrency/diff_impact 之一  

**输出（ModuleResult）**  
- `findings`：risk_type 见下表  

**依赖关系**  
- 依赖 branch_path、boundary_value、error_path、concurrency、diff_impact 中至少一个的发现  

**发现类型（risk_type）**  

| risk_type | 描述 |
|-----------|------|
| high_risk_low_coverage | 高风险发现对应代码覆盖率低 |
| critical_path_uncovered | 关键路径未被覆盖 |

**evidence 示例**  
```json
{
  "line_coverage": 0.31,
  "branch_coverage": 0.0,
  "related_finding_ids": ["branch_path-F0001", "error_path-F0007"],
  "threshold": 0.7
}
```

**评分规则**  
- 根据“高风险 + 低覆盖”的发现数量与严重程度、关键路径未覆盖比例加权，归一化到 [0,1]。  

---

### 3.8 postmortem — 事后分析

| 项 | 说明 |
|----|------|
| **模块 ID** | `postmortem` |
| **中文名称** | 事后分析 |
| **描述** | 对逃逸缺陷做根因分析与预防性测试建议，产出事后分析报告并支撑知识库沉淀。 |

**输入（AnalyzeContext）**  
- 缺陷元数据（标题、严重程度、描述、相关提交、模块路径）  
- 可选：关联任务上下文  

**输出（ModuleResult）**  
- `findings`：risk_type 见下表  
- `artifacts`：如 `postmortem.md`  

**依赖关系**  
- 依赖缺陷输入；可选用 branch_path、error_path、concurrency、diff_impact 等辅助分析  

**发现类型（risk_type）**  

| risk_type | 描述 |
|-----------|------|
| escaped_defect_root_cause | 逃逸缺陷根因链 |
| missing_test_strategy | 缺失的测试策略或用例 |

**evidence 示例**  
```json
{
  "defect_title": "故障切换下元数据陈旧",
  "root_cause_chain": [
    "状态切换未同步",
    "重试路径绕过版本检查"
  ],
  "preventive_tests": ["在重试中注入故障切换并校验 stale epoch"]
}
```

**评分规则**  
- 根据根因明确程度与预防性测试建议的可用性评分，归一化到 [0,1]。  

---

### 3.9 knowledge_pattern — 缺陷知识库

| 项 | 说明 |
|----|------|
| **模块 ID** | `knowledge_pattern` |
| **中文名称** | 缺陷知识库（模式管理） |
| **描述** | 基于事后分析输出与历史缺陷模式，做模式候选提取与相似度计算，并写入 defect_patterns。 |

**输入（AnalyzeContext）**  
- 规范化的事后分析输出  
- 历史缺陷模式（如从 defect_patterns 读取）  

**输出（ModuleResult）**  
- 模式候选及相似度；对知识库的 upsert 由服务层持久化  

**依赖关系**  
- 依赖 postmortem 输出  

**发现类型（risk_type）**  
- 本模块以“模式匹配/推荐”为主，findings 可为空或仅包含推荐模板类信息。  

**evidence 示例**  
```json
{
  "pattern_key": "meta_retry_epoch_gap",
  "similarity": 0.88,
  "recommended_template": "retry_failover_epoch_validation_v1"
}
```

**评分规则**  
- 可按匹配到的模式数量与相似度综合给出 risk_score（例如高相似度匹配多表示当前与历史问题接近，风险偏高）。  

---

## 4. 模块依赖总览

- **call_graph**：独立基础模块  
- **branch_path、boundary_value、error_path**：仅依赖解析器核心  
- **concurrency**：解析器核心，可选 call_graph  
- **diff_impact**：依赖 call_graph  
- **coverage_map**：依赖 branch_path / boundary_value / error_path / concurrency / diff_impact 中至少一个  
- **postmortem**：依赖缺陷输入，可选用 M01/M03/M05/M09  
- **knowledge_pattern**：依赖 postmortem 输出  

---

## 5. 聚合契约

任务级聚合风险分（默认公式）：

```text
task_risk = sum(module_weight[module] * module_risk[module]) / sum(weights)
```

默认权重示例：

| module_id | 权重 |
|-----------|------|
| branch_path | 1.1 |
| boundary_value | 0.9 |
| error_path | 1.1 |
| call_graph | 0.6 |
| concurrency | 1.3 |
| diff_impact | 1.2 |
| coverage_map | 1.2 |
| postmortem | 1.0 |
| knowledge_pattern | 0.7 |

---

## 6. 确定性与可复现

- 相同 revision 与 options 下，分析器输出应具有确定性  
- 在 `metrics` 中提供 `input_fingerprint`：如 repo commit、target 路径哈希、options 哈希  

---

## 7. 最小合法输出示例

```json
{
  "module_id": "error_path",
  "status": "success",
  "risk_score": 0.67,
  "findings": [
    {
      "finding_id": "error_path-F0003",
      "module_id": "error_path",
      "risk_type": "missing_cleanup",
      "severity": "S1",
      "risk_score": 0.72,
      "title": "错误返回路径上文件句柄未关闭",
      "description": "错误路径在 close(fd) 之前返回",
      "file_path": "src/io/open.c",
      "symbol_name": "open_volume",
      "line_start": 91,
      "line_end": 112,
      "evidence": {
        "cleanup_resources_expected": ["fd"],
        "cleanup_resources_observed": []
      }
    }
  ],
  "metrics": {
    "functions_scanned": 123,
    "input_fingerprint": "sha256:abcd..."
  },
  "artifacts": [
    {"type": "json", "path": "artifacts/tsk_xxx/error_path/findings.json"}
  ],
  "warnings": []
}
```
