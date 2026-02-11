# GrayScope 实施计划（PLAN）

## 1. 计划说明

本计划为可执行级，面向工程实施与编码代理。各阶段具备明确交付物、完成定义（DoD）与测试门禁。

## 2. 已完成阶段概述

### Phase 0（已完成）

- **交付物**：PRD、HLD、PLAN 实施级草案；后端/前端/CLI 可运行骨架
- **DoD**：`/api/v1/health` 可用；前端与 CLI 骨架可运行
- **状态**：已达成

### Phase 1 — 核心平台基础（已完成）

- 任务生命周期 API、仓库同步服务
- Parser 核心（tree-sitter C/C++）与缓存管理
- Provider 注册表与多模型适配器（openai_compat、ollama、qwen、deepseek、custom_rest）
- Prompt 模板加载与 JSON Schema 校验
- **DoD**：可创建并跟踪分析任务（不含分析器执行）；至少 2 个 Provider 健康测试通过；Parser 可解析 C/C++ 并返回顶层符号

### Phase 2 — 分析器 MVP（已完成）

- branch_path、boundary_value、error_path、call_graph 四个分析器
- 模块结果独立持久化；编排依赖执行；阶段 A 的 AI 增强
- **DoD**：在示例仓库上单任务输出 M01–M04 对应发现；报告接口包含阶段 A 汇总

### Phase 3 — 风险与变更智能（已完成）

- concurrency、diff_impact、coverage_map 及覆盖率适配器
- 风险评分 v1；结构化用例导出 JSON/CSV
- **DoD**：差异任务能映射变更函数并返回影响列表；覆盖率叠加可识别高风险低覆盖项

### Phase 4 — 事后分析与知识闭环（已完成）

- 事后分析输入与 API；模式持久化与检索 API；知识库推荐融入报告
- **DoD**：事后分析任务可生成可复用模式条目；知识库检索返回相关历史模式

### Phase 5 — 前端/CLI 与运维收尾（进行中/已完成）

- 完善 Web 视图（仪表盘、新建分析、任务详情、事后分析、知识库等）与 CLI 命令
- 可观测性（结构化日志、指标）与部署手册

## 3. 当前重构变更总结

- **模块 ID 统一重命名**：由原 M01–M19 等数字编号改为语义化 ID，与代码与文档一致：
  - **branch_path**：分支路径分析（原 M01）
  - **boundary_value**：边界值分析（原 M02）
  - **error_path**：错误路径分析（原 M03）
  - **call_graph**：调用图构建（原 M04）
  - **concurrency**：并发风险分析（原 M05）
  - **diff_impact**：差异影响分析（原 M09）
  - **coverage_map**：覆盖率映射（原 M10）
  - **postmortem**：事后分析（原 M18）
  - **knowledge_pattern**：缺陷知识库（原 M19）
- **文档中 API、数据契约、编排顺序、前端展示** 均按上述新 ID 表述；PRD/HLD/PLAN/README 已同步为中文并反映新模块名与部署约束（X86 Linux 内网、HTTP/HTTPS、无认证）。
- **技术栈明确**：前端 Vue3 + Element Plus + ECharts；后端 FastAPI + SQLAlchemy + tree-sitter；AI 支持 Ollama/Qwen/DeepSeek/OpenAI 兼容/自定义 REST。

## 4. 跨阶段产物

- API 规范：`docs/API_SPEC.md`（Phase 1 起维护）
- Prompt 目录：`backend/app/ai/prompt_templates/`
- 分析器 Fixture：`backend/tests/fixtures/`

## 5. 并行轨道建议

- 轨道 A：后端平台与编排
- 轨道 B：分析器引擎
- 轨道 C：前端与 CLI 集成
- 轨道 D：AI Provider 与 Prompt 质量

## 6. 风险与缓解

- 模型服务不稳定 → 超时、Fallback 链、健康检查
- 宏过多导致 Parser 质量下降 → 预处理回退与符号级降级
- 覆盖率格式多样 → 可插拔适配器与校验

## 7. V1 出口标准

- 九大分析器均可通过 API 使用
- 至少 2 个模型 Provider 达到生产可用
- 在代表性子库上稳定运行，报告与导出可用
- 事后分析流程与知识库检索可用
