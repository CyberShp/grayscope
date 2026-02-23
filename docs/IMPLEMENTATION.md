# GrayScope 核心功能代码实现说明

本文从**设计到代码**说明 GrayScope 核心功能是如何在代码中实现的：从 API 入口、任务创建、分析编排、各分析器执行，到发现持久化、导出为测试用例的完整数据流与关键实现点。

---

## 一、整体调用链概览

```
前端/CLI
    │
    ▼ POST /api/v1/analysis/tasks
app.api.v1.analysis.create_task()
    │
    ├─► task_service.create_task()        # 写 analysis_tasks + 预写 analysis_module_results (pending)
    │
    └─► analysis_orchestrator.run_task()  # 同步执行所有模块
            │
            ├─► 按拓扑序遍历模块 (branch_path → boundary_value → error_path → call_graph → data_flow → …)
            ├─► 每模块: _build_context() → analyzer.analyze(ctx) → AI 增强 → task_repo.update_module_result()
            └─► 跨模块 AI 综合 → 聚合风险分 → 更新任务状态

GET /api/v1/analysis/tasks/{id}/export?fmt=json|csv|markdown|findings|critical|html
    │
    └─► export_service.export_*()
            │
            └─► task_repo.get_module_results() → 合并 findings + critical_combinations（来自 task.error_json）
                 → _findings_to_testcases()（含 expected_outcome、performance_requirement、covered）
                 → 返回/写文件
```

---

## 二、入口与任务创建

### 2.1 API 入口

**文件**: `backend/app/api/v1/analysis.py`

- **POST `/analysis/tasks`**  
  - 调用 `task_service.create_task(db, req)` 创建任务并预创建各模块结果行（状态 `pending`）。  
  - 随后**同步**调用 `analysis_orchestrator.run_task(db, out.task_id)` 执行分析（当前无 Celery 等异步队列）。

- **GET `/analysis/tasks/{task_id}/export?fmt=...`**  
  - `fmt=json` → `export_service.export_json()`（含 critical_combinations、test_cases、covered）  
  - `fmt=csv` → `export_service.export_csv()`（先交汇临界点再用例，含 performance_requirement、covered）  
  - `fmt=markdown` → `export_service.export_markdown()`  
  - `fmt=findings` → `export_service.export_findings_json()`  
  - `fmt=critical` → `export_service.export_critical_only()`  
  - `fmt=html` → `export_service.export_html()`  

### 2.2 任务与模块结果的持久化

**任务创建**（`task_service.create_task` → `task_repo.create_task`）：

- 写入表 **`analysis_tasks`**：  
  `task_id`, `project_id`, `repo_id`, `task_type`, `target_json`, `revision_json`, `analyzers_json`, `ai_json`, `options_json` 等。
- 为请求中的每个 `analyzers` 条目调用 **`task_repo.create_module_result(db, task_pk=task.id, module_id=mod)`**，在 **`analysis_module_results`** 中插入一行，`status='pending'`，`findings_json='[]'`。

因此，编排器跑之前，每个要执行的模块已经有一条“占位”记录，编排器只更新这些记录的 `status`、`findings_json`、`risk_score`、`ai_summary_json` 等。

---

## 三、分析编排器（核心调度）

**文件**: `backend/app/services/analysis_orchestrator.py`

### 3.1 模块依赖与执行顺序

- **MODULE_DEPS**：定义每个模块依赖的上游模块，例如  
  `data_flow` 依赖 `call_graph`，`concurrency` / `diff_impact` 依赖 `call_graph` 和 `data_flow` 等。
- **\_topological_order(analyzers)**：对本次任务启用的 `analyzers` 做拓扑排序，保证依赖模块先执行。

### 3.2 run_task() 主流程

1. **加载任务**  
   `task_repo.get_task_by_id(db, task_id)`，`task_repo.get_module_results(db, task.id)` 得到每个模块的当前结果行。

2. **初始化 upstream**  
   `upstream: dict[str, dict] = {}`。每完成一个模块且状态为 `success` 时，执行  
   `upstream[mod_id] = {"findings": findings, "risk_score": risk_score}`，供后续模块通过 `ctx["upstream_results"]` 使用。

3. **按拓扑序遍历每个模块**  
   - 若该模块结果已是 `success`/`skipped` 等非 pending/failed，则只把其 findings 并入 `upstream`，不重跑。  
   - 若为 `pending` 或 `failed`：  
     - 检查依赖是否均 `success`；不满足则把该模块标为 `skipped`。  
     - 满足则：  
       - `task_repo.update_module_result(..., status="running")`  
       - **ctx = _build_context(task, upstream)**  
       - **module_result = analyzer_mod.analyze(ctx)**（见下节）  
       - 若配置了 AI，则 **enrich_module(...)** 做单模块 AI 增强，结果写入 `ai_summary_data`  
       - **task_repo.update_module_result(..., status="success", risk_score=..., findings_json=..., ai_summary_json=...)**  
       - 更新 `upstream[mod_id]`

4. **跨模块 AI**  
   若启用且 `upstream` 至少 2 个模块，调用 **synthesize_cross_module(upstream, snippets, ai_config)**，结果通过 **task_repo.set_cross_module_ai()** 存到任务的 `error_json` 扩展字段（如 `cross_module_ai`）。

5. **收尾**  
   根据各模块状态聚合风险分（**MODULE_WEIGHTS** 加权），写回任务 `aggregate_risk_score`，并设置任务最终状态（success / partial_failed / failed）。

### 3.3 上下文的构建

**\_build_context(task, upstream)** 返回 **AnalyzeContext**（定义在 `app.analyzers.base`）：

- `task_id`, `project_id`, `repo_id`  
- `workspace_path`：从 `repository_repo.get_by_id(..., task.repo_id)` 取 `repo.local_mirror_path`  
- `target`：来自 `task.target_json`（分析范围，如 path）  
- `revision`：来自 `task.revision_json`（分支、base/head commit）  
- `options`：来自 `task.options_json`，并设默认 `max_files=500`, `max_functions=10000`  
- `upstream_results`：即当前已完成的 `upstream` 字典（key=module_id, value={findings, risk_score}）

---

## 四、分析器契约与统一入口

**文件**: `backend/app/analyzers/base.py`

- **AnalyzeContext**：TypedDict，包含上述字段。  
- **ModuleResult**：TypedDict，包含  
  `module_id`, `status`, `risk_score`, `findings`, `metrics`, `artifacts`, `warnings`。  
- 每个分析器模块对外暴露 **`analyze(ctx: AnalyzeContext) -> ModuleResult`**，由编排器通过 **\_ANALYZER_REGISTRY[mod_id].analyze(ctx)** 调用。

**注册表**（在 `analysis_orchestrator.py`）：  
`branch_path_analyzer`, `boundary_value_analyzer`, `error_path_analyzer`, `call_graph_builder`, `data_flow_analyzer`, `concurrency_analyzer`, `diff_impact_analyzer`, `coverage_mapper`, `postmortem_analyzer`, `knowledge_pattern_manager` 等。

---

## 五、解析层：CodeParser（所有分析器的基础）

**文件**: `backend/app/analyzers/code_parser.py`

- 基于 **tree-sitter**（C/C++ 语法）解析源码，得到：
  - **Symbol**：name, kind（function/struct/…）, file_path, line_start/end, source  
  - **CFG**：nodes（entry/exit/branch/statement）、edges（true/false/fallthrough）
- 主要接口：
  - **parse_file(path)** / **parse_directory(path, max_files)**：返回 `list[Symbol]`  
  - **build_cfg(path, function_name)**：返回该函数的 **CFG**（用于 branch_path、部分 error_path 等）

各分析器在 `analyze(ctx)` 内根据 `ctx["workspace_path"]` 和 `ctx["target"]` 解析目标文件或目录，再按各自逻辑遍历符号/CFG 生成 findings。

---

## 六、单分析器实现示例（两条链路）

### 6.1 branch_path：基于 CFG 的分支分类

**文件**: `backend/app/analyzers/branch_path_analyzer.py`

- **analyze(ctx)** 流程：  
  1. 从 `ctx["workspace_path"]`、`ctx["target"]`、`ctx["options"]` 得到目标路径和 `max_files`。  
  2. 用 **CodeParser** 遍历目标下 C/C++ 文件，对每个函数调用 **parser.build_cfg(fpath, sym.name)** 得到 CFG。  
  3. 对每个 CFG 中 `kind="branch"` 的节点，用 **_classify_branch(br.label)** 得到 path_type（error/cleanup/boundary/state/normal），用 **_score_branch(path_type)** 得到风险分。  
  4. 每条发现写入 **findings**，每条带 **evidence**：  
     `branch_id`, `condition_expr`, `path_type`, `cfg_node_count`, `cfg_edge_count`,  
     以及灰盒扩展字段 **expected_failure**、**unacceptable_outcomes**（按 path_type 映射中文描述）。  
  5. 返回 **ModuleResult**：`findings`, `risk_score`（由 findings 聚合）, `metrics`, `artifacts`, `warnings`。

### 6.2 error_path：资源/错误路径 + 跨函数链

**文件**: `backend/app/analyzers/error_path_analyzer.py`

- **analyze(ctx)** 流程：  
  1. 同样解析目标路径下文件，用 **CodeParser** 得到符号与源码。  
  2. **Pass 1**：对每个函数用正则（如 `_MALLOC_RE`, `_FREE_RE`, `_OPEN_RE` 等）收集“分配/释放/加锁/解锁/错误返回”等模式，得到 **function_resource_info**；并从 **ctx["upstream_results"]** 取 **data_flow** / **call_graph** 信息（**_extract_data_flow_chains**, **_extract_call_graph_info**）用于跨函数分析。  
  3. **Pass 2**：  
     - 单函数：检测缺失清理、goto 清理、错误码不一致、静默吞错等，生成 findings，evidence 含 `cleanup_resources_expected/observed`、`return_mapping` 等。  
     - 跨函数：若 A 分配资源后调用 B，B 可能失败，则检查 A 在 B 失败后是否释放资源；若否，生成 **cross_function_resource_leak** 类发现，evidence 中显式写 **related_functions**（caller/callee）、**expected_failure**、**unacceptable_outcomes**。  
  4. 返回 **ModuleResult**，结构同上。

### 6.3 data_flow：调用图 + 传播链

**文件**: `backend/app/analyzers/data_flow_analyzer.py`

- **analyze(ctx)** 流程：  
  1. 可从 **ctx["upstream_results"].get("call_graph")** 读取上游，但当前实现会再调 **build_callgraph(workspace, target_path, max_files)** 得到完整调用图与参数映射。  
  2. 用 **CodeParser** 收集各函数源码到 **function_sources**。  
  3. **_build_risk_scores(upstream)**：根据上游模块 findings 给函数打风险分，用于传播链排序。  
  4. **_build_propagation_chains(...)**：沿调用图构建“入口参数 → 多级调用 → 敏感操作/边界”的传播链。  
  5. 对每条链根据“深度、是否外部输入、是否到达敏感操作、值域变换”等生成 findings（如 **deep_param_propagation**, **external_to_sensitive**, **value_transform_risk**），evidence 中含 **propagation_chain**、**related_functions**、**expected_failure**、**unacceptable_outcomes**。  
  6. 返回 **ModuleResult**。

其他模块（concurrency、diff_impact、boundary_value、call_graph、coverage_map 等）同样实现 **analyze(ctx) -> ModuleResult**，有的读 **upstream_results**（如 diff_impact 读 call_graph），有的只读 workspace/target/options。灰盒三要素（related_functions、expected_failure、unacceptable_outcomes）或在 evidence 里直接写，或由导出服务从 callers/callees、propagation_chain 等推导。

---

## 七、发现的持久化

- 编排器在每模块 **analyze()** 返回后，将 **findings** 序列化为 JSON，通过 **task_repo.update_module_result(db, mr.id, findings_json=json.dumps(findings), ...)** 写入 **analysis_module_results.findings_json**。  
- 同一条记录还写入 **risk_score**、**metrics_json**、**artifacts_json**、**ai_summary_json**（单模块 AI 增强结果）。  
- 因此“核心功能”的静态分析产出，最终都落在 **analysis_tasks** 与 **analysis_module_results** 两张表；导出与测试用例生成只读这些表，不再调分析器。

---

## 八、从发现到测试用例（导出服务）

**文件**: `backend/app/services/export_service.py`

### 8.1 导出入口如何取发现

- **export_json** / **export_csv** / **export_markdown** 统一逻辑：  
  1. **task_repo.get_task_by_id(db, task_id)** 取任务；  
  2. **task_repo.get_module_results(db, task.id)** 取该任务下所有 **AnalysisModuleResult**；  
  3. 遍历每个 result，若 **findings_json** 非空则 **json.loads(r.findings_json)** 并入 **all_findings**；  
  4. 若存在 **ai_summary_json** 则并入 **ai_data[module_id]**；  
  5. 调用 **\_findings_to_testcases(task_id, all_findings, ai_data)** 得到结构化测试用例列表。

### 8.2 _findings_to_testcases()：发现 → 用例字典

- 对 **all_findings** 中每条 finding：  
  - 用 **\_get_related_functions(f)**、**_get_expected_failure(risk_type, f)**、**_get_unacceptable_outcomes(risk_type, f)** 从 **evidence** 或默认映射取灰盒三要素；  
  - 用 **\_risk_type_to_objective**、**_risk_type_to_preconditions**、**_risk_type_to_steps**、**_risk_type_to_expected** 等生成 objective、preconditions、test_steps、expected_result；  
  - **\_risk_type_to_execution_hint**、**_risk_type_to_example_input** 生成 execution_hint、example_input；  
  - 若存在 related_functions，用 **_format_objective_with_related()** 在 objective 前加“关联函数: …”；  
  - 用 **_append_expected_vs_unacceptable()** 把 expected_failure / unacceptable_outcomes 并入预期结果文案；  
  - 组装成一条 case 字典（含 test_case_id、priority、module_id、title、objective、preconditions、test_steps、expected_result、related_functions、expected_failure、unacceptable_outcomes、execution_hint、example_input、target_file、target_function、risk_score、evidence 等）。  
- 返回 **list[dict]**，再由各 export 函数输出为 JSON 字符串、CSV 或 Markdown。

### 8.3 灰盒三要素的来源（代码层面）

- **分析器直接写**：如 error_path 的 cross_function_resource_leak、concurrency 的 cross_function_race、data_flow 的各类 risk_type，在构造 finding 时就在 **evidence** 里写入 **related_functions**、**expected_failure**、**unacceptable_outcomes**。  
- **导出服务推导**：**_get_related_functions(f)** 若 evidence 中无显式 related_functions，则从 **evidence 的 callers/callees**（call_graph 产出）或 **propagation_chain**（data_flow 产出）推导函数列表。  
- **AI 补全**：跨模块 **synthesize_cross_module** 会要求模型输出 **critical_combinations**，经 **ai_enrichment._extract_test_suggestions()** 解析后得到带 related_functions/expected_failure/unacceptable_outcomes 的建议，可用于展示或后续写入用例（当前跨模块结果存 task 的 error_json，导出时通过 ai_data 间接影响展示，持久化用例则通过“测试用例生成/采纳”流程写入 **test_cases** 表）。

---

## 九、AI 增强在代码中的位置

- **单模块**：在 **analysis_orchestrator.run_task()** 内，每个模块 **analyze()** 成功后，若配置了 AI，则调用 **ai_enrichment.enrich_module(mod_id, findings, snippets, ai_config, upstream_results=upstream)**；返回的 **ai_summary_data**（含 test_suggestions、ai_summary 等）写入 **analysis_module_results.ai_summary_json**。  
- **跨模块**：所有模块跑完后，若启用跨模块 AI，调用 **ai_enrichment.synthesize_cross_module(upstream, snippets, ai_config)**，结果通过 **task_repo.set_cross_module_ai(db, task_id, json.dumps(cross_result))** 存到 **analysis_tasks.error_json** 的扩展字段（如 `cross_module_ai`）。  
- 提示词与模板在 **app.ai.prompt_engine** 与 **app.ai.prompt_templates/*.yaml** 中；模型调用通过 **app.ai.provider_registry.get_provider()** 拿到具体 Provider（Ollama/DeepSeek/Qwen/OpenAI 兼容等）执行。

---

## 十、关键文件与职责小结

| 层级 | 文件 | 职责 |
|------|------|------|
| API | `api/v1/analysis.py` | 创建任务、查状态/结果、导出（json/csv/markdown/findings） |
| 服务 | `services/task_service.py` | 任务创建、状态/结果查询；预创建 module_result 行 |
| 服务 | `services/analysis_orchestrator.py` | 拓扑排序、_build_context、按序调用 analyzer.analyze、AI 增强、写回 module_result、跨模块 AI、聚合风险分 |
| 服务 | `services/export_service.py` | 从 module_results 合并 findings，_findings_to_testcases，输出 JSON/CSV/Markdown |
| 服务 | `services/ai_enrichment.py` | enrich_module、synthesize_cross_module、_extract_test_suggestions |
| 分析器基座 | `analyzers/base.py` | AnalyzeContext、ModuleResult、Analyzer 协议 |
| 分析器基座 | `analyzers/code_parser.py` | tree-sitter 解析、parse_file/parse_directory、build_cfg |
| 分析器 | `analyzers/branch_path_analyzer.py` 等 | analyze(ctx) → ModuleResult，产出 findings（含 evidence 与灰盒字段） |
| 持久化 | `repositories/task_repo.py` | analysis_tasks / analysis_module_results 的 CRUD |
| 模型 | `models/analysis_task.py`, `models/module_result.py` | 任务与模块结果表结构 |

整体上，**设计层面的“分析编排 → 多模块 findings → 灰盒证据 → 测试用例”** 在代码中对应为：**analysis_orchestrator.run_task()** 驱动各 **analyzer.analyze(ctx)**，结果写入 **analysis_module_results**；**export_service** 读取这些结果，通过 **_findings_to_testcases()** 转为带灰盒字段的测试用例并导出。
