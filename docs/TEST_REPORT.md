# GrayScope 测试报告

**日期**: 2026-02-23  
**版本**: v1.1.0 — 灰盒增强 + UI 中文化 + 全分析器灰盒字段  

> **后续迭代**：导出多函数交汇临界点（critical_combinations）、fmt=critical/html、expected_outcome、performance_requirement、覆盖率 covered 标记等，见 [GRAYBOX_RESEARCH_AND_ITERATION.md](GRAYBOX_RESEARCH_AND_ITERATION.md)。

---

## 1. 测试概要

| 维度 | 结果 |
|------|------|
| 后端单元/集成测试 | **337 / 337 通过** |
| 分析器模块测试 | **61 / 61 通过** |
| AI 层测试 | **83 / 83 通过** |
| API 综合测试 | **126 / 126 通过** |
| 测试运行 API 测试 | **17 / 17 通过**（test_test_runs_api.py） |
| 服务层测试 | **67 / 67 通过** |
| 前端构建 | **成功（0 错误）** |
| Lint 检查 | **0 错误** |

---

## 2. 本次迭代改动摘要

### 2.1 UI 中文化
- 新增 `useRiskTypeNames.js` composable，统一 20+ 种 risk_type 的中文映射
- 所有视图引用统一映射：TaskDetail、ProjectIssues、GlobalIssues、KnowledgeBase、TestDesignCenter
- 英文残留修复：`+N more` → `还有 N 个`、`TRUE/FALSE 分支` → `条件成立/不成立分支`、`平均风险分` → `平均风险评分`、`git commit hash` → `Git 提交哈希`
- Token 用量显示增加输入/输出标注

### 2.2 全分析器灰盒字段扩展
所有 5 个核心分析器的 findings 现在均包含 `related_functions`、`expected_failure`、`unacceptable_outcomes`：

| 分析器 | risk_type 数量 | 新增灰盒字段 |
|--------|--------------|-------------|
| concurrency | 5 (race_write_without_lock, lock_order_inversion, atomicity_gap, cross_function_deadlock_risk, cross_function_race) | 全部 3 个 |
| data_flow | 3 (deep_param_propagation, external_to_sensitive, value_transform_risk) | 全部 3 个 |
| boundary_value | 2 (boundary_miss, invalid_input_gap) | expected_failure + unacceptable_outcomes |
| branch_path | 5 (error, cleanup, boundary, state, normal) | expected_failure + unacceptable_outcomes（按 path_type 区分） |
| diff_impact | 2 (changed_core_path, transitive_impact) | 全部 3 个 |
| error_path | 已有 (cross_function_resource_leak) | — 之前已完成 |

### 2.3 AI 层修复
- `_extract_test_suggestions`: 修复 JSON list 输入被错误包装的 bug
- 新增 `"branches"` 和 `"regression_tests"` 到已知 key 列表

### 2.4 API 路由修复
- `/test-cases/template` 路由被 `{test_case_id}` 参数路由遮蔽的 bug 已修复

---

## 3. 后端测试详情

### 3.1 运行测试与数据库

- 后端测试使用 SQLite 文件 `./test_grayscope.db`。若新增了表（如 `test_runs`、`test_executions`），首次或报错时建议删除该文件后重跑：`rm -f ./test_grayscope.db && pytest tests/ -v`。
- `conftest.py` 已显式导入 `TestRun`、`TestExecution`、`TestCase`，确保 `create_all` 时包含所有表。

### 3.2 test_ai_layer.py (83 tests)
- Provider 基类/实例化：10 tests ✅
- Prompt 引擎加载/渲染：14 tests ✅
- AI 增强（提取建议、跨模块、模板映射）：22 tests ✅
- 同步调用/边缘情况：12 tests ✅
- 模板结构验证：3 tests ✅

### 3.2 test_analyzers.py (61 tests)
- CodeParser（AST 解析、CFG 构建）：12 tests ✅
- BranchPathAnalyzer（分类/评分/goto）：12 tests ✅
- BoundaryValueAnalyzer（比较/数组/上游传播）：11 tests ✅
- ErrorPathAnalyzer（清理/goto/跨函数）：5 tests ✅
- CallGraphBuilder（扇出/扇入/调用链）：10 tests ✅
- AnalyzerRegistry：6 tests ✅
- 集成测试（storage_module 完整分析）：5 tests ✅

### 3.3 test_api_comprehensive.py (126 tests)
- Health：2 tests ✅
- Project CRUD & validation：20 tests ✅
- Repo CRUD & isolation：14 tests ✅
- Task CRUD & types：14 tests ✅
- Results & Export：15 tests ✅
- Global endpoints：10 tests ✅
- Settings/Models：5 tests ✅
- Postmortem/Knowledge：4 tests ✅
- Response 信封/边缘情况：16 tests ✅
- 前端契约验证：8 tests ✅
- TestCase 状态更新：2 tests ✅

### 3.4 test_services.py (67 tests)
- ProjectRepo/RepositoryRepo/TaskRepo：15 tests ✅
- DefectPatternRepo：6 tests ✅
- ExportService（testcases/json/csv）：6 tests ✅
- TestcaseService：3 tests ✅
- Schema 验证：11 tests ✅
- 响应信封/错误处理：5 tests ✅
- API 集成补充：14 tests ✅

---

## 4. 前端验证

| 检查项 | 结果 |
|--------|------|
| `npm run build` | ✅ 成功（3.14s） |
| Lint 检查（所有修改文件） | ✅ 0 错误 |
| TaskDetail.vue | ✅ 引入集中式 getRiskTypeName |
| TestCaseDetail.vue | ✅ 风险分类显示中文 |
| EvidenceRenderer.vue | ✅ `还有 N 个` 替换 `+N more` |
| CfgGraph.vue | ✅ `条件成立/不成立` 替换 `TRUE/FALSE` |
| CallGraph.vue | ✅ `还有 N 个` 替换 `+N more` |
| Dashboard.vue | ✅ `平均风险评分` 替换 `平均风险分` |
| Postmortem.vue | ✅ `Git 提交哈希` 替换 `git commit hash` |

---

## 5. 已知限制

1. **大块警告**: `index-BfdUTXqs.js` 超过 500KB，建议未来拆分 Element Plus 按需引入
2. **tree-sitter 语言支持**: 当前仅支持 C/C++，Python/Java/Go 等语言需后续扩展
3. **AI 模型依赖**: AI 增强功能需配置 Ollama/DeepSeek/Qwen 等模型才能使用

---

## 6. 测试命令

```bash
# 运行全部后端测试
cd backend && python3 -m pytest tests/ -v

# 运行特定测试文件
python3 -m pytest tests/test_analyzers.py -v
python3 -m pytest tests/test_ai_layer.py -v
python3 -m pytest tests/test_api_comprehensive.py -v
python3 -m pytest tests/test_services.py -v

# 前端构建验证
cd frontend && npm run build
```
