# GrayScope 产品需求文档（PRD）

## 1. 文档控制

- 版本：v1.0
- 状态：已批准实施
- 受众：测试架构师、后端/前端工程师、AI 平台工程师
- 目的：本文档为实施级文档，与 HLD、PLAN 配合可供编码代理完整构建系统。

## 2. 产品概述

GrayScope 是面向**数据存储系统**的灰盒/白盒测试分析平台，部署于 **X86 Linux 内网**，通过 **HTTP/HTTPS** 提供服务，当前阶段**不提供用户认证**。平台将静态代码分析（tree-sitter）与多模型 AI 推理结合，为测试团队提供代码感知的测试设计与风险发现能力，覆盖 KV/对象/文件/块存储及硬件管理面。

**核心价值**：从黑盒主导的测试模式转向灰盒/白盒驱动的、可解释的测试设计与逃逸缺陷复盘。

## 3. 目标用户

- **测试工程师**（50+ 人存储测试团队）：基于代码风险设计与优化测试策略
- **测试负责人**：审视风险覆盖质量与团队一致性
- **开发人员**（次要）：在代码评审中参考风险报告

## 4. 核心需求：灰盒分析九大模块

| 模块 ID | 名称 | 能力简述 |
|---------|------|----------|
| branch_path | 分支路径分析 | 基于 CFG 的分支分类与未覆盖高风险路径识别 |
| boundary_value | 边界值分析 | 比较、数组访问等约束与边界候选值推导 |
| error_path | 错误路径分析 | 异常/清理路径、资源释放、errno 一致性 |
| call_graph | 调用图构建 | 函数级依赖图，支持调用者/被调用者查询 |
| concurrency | 并发风险分析 | 共享状态、锁顺序、竞态候选识别 |
| diff_impact | 差异影响分析 | Git diff → 变更函数 → 传递影响范围 |
| coverage_map | 覆盖率映射 | 行/分支覆盖率与风险发现叠加，高风险低覆盖清单 |
| postmortem | 事后分析 | 逃逸缺陷根因链与预防性测试建议 |
| knowledge_pattern | 缺陷知识库 | 缺陷模式持久化、检索与发现匹配 |

上述模块需支持通过 Web 与 CLI 创建任务、查看结果、导出报告与用例。

## 5. AI 增强需求

- **统一 Provider 接口**：`chat`、`health_check`、`name` 等，可选 `embed`
- **多 Provider 支持**：Ollama、Qwen、DeepSeek、OpenAI 兼容、自定义 REST
- **按项目/环境选择**：运行时通过配置选择 Provider 与模型
- **Prompt 管理**：版本化、可审计的模板，输出经 JSON Schema 校验后持久化
- **可靠性**：重试与 Fallback 链（如 custom_internal → ollama → openai_compat）

## 6. 部署需求

- **环境**：X86 Linux 内网
- **协议**：HTTP/HTTPS
- **认证**：当前阶段不做 RBAC/SSO，无登录鉴权
- **依赖**：不强制依赖公网；模型为内网 Ollama/内部 API 或允许的云厂商

## 7. 功能需求摘要

- **项目与仓库**：创建/列表/更新/归档项目；绑定多 Git 仓库；按分支/标签/提交同步；记录同步历史与结果
- **分析编排**：任务类型 full/file/function/diff/postmortem；状态 pending/running/partial_failed/success/failed/cancelled；按模块独立持久化结果；支持仅重试失败模块
- **输出**：结构化测试用例（case_id、title、risk_type、preconditions、steps、expected、priority、tags）；导出 JSON/CSV/Markdown；分析报告（风险汇总+文件级引用）；脑图式测试设计数据
- **Web 与 CLI**：Web 支持任务创建、进度查看、报告浏览、导出；CLI 支持无头分析/导出，便于 CI 集成

## 8. 非功能性需求

- **NFR-001**：仅内网部署，无需外网依赖
- **NFR-002**：支持百万级行仓库，具备增量解析与缓存
- **NFR-003**：单文件分析目标在排除 LLM 排队后 &lt; 30s
- **NFR-004**：支持 ≥10 个并发任务
- **NFR-005**：相同输入与分析器集合的任务重跑幂等
- **NFR-006**：所有任务操作与 AI 调用产生结构化日志

## 9. 数据契约（规范）

### 9.1 分析任务请求

```json
{
  "project_id": 1,
  "repo_id": 2,
  "task_type": "full",
  "target": { "path": "src/storage/", "functions": [] },
  "revision": { "branch": "main", "base_commit": null, "head_commit": null },
  "analyzers": ["branch_path", "boundary_value", "error_path", "concurrency", "coverage_map"],
  "ai": { "provider": "ollama", "model": "qwen2.5-coder", "prompt_profile": "default-v1" }
}
```

### 9.2 分析结果信封

```json
{
  "task_id": "tsk_20260211_001",
  "module": "branch_path",
  "status": "success",
  "risk_score": 0.82,
  "artifacts": [{ "type": "cfg_json", "path": "artifacts/tsk_.../branch_path/cfg.json" }],
  "ai_summary": { "prompt_version": "branch_path-v3", "provider": "ollama", "model": "qwen2.5-coder", "output": {} }
}
```

### 9.3 结构化测试用例

```json
{
  "case_id": "GS-branch_path-0001",
  "title": "alloc 失败时错误清理分支",
  "risk_type": "error_path",
  "priority": "P1",
  "preconditions": ["对 malloc 启用故障注入"],
  "steps": ["使用 size=... 调用 create_volume"],
  "expected": ["返回码为 E_NOMEM", "无 fd/内存泄漏"],
  "tags": ["storage", "memory", "cleanup"]
}
```

## 10. 验收标准

- **Phase 0**：PRD/HLD/PLAN 齐备且为实施级；后端骨架提供 `/api/v1/health`；前端开发服务器可运行并渲染占位页；CLI 具备 help 与 health 命令
- **V1**：九大分析器均可通过 API 调用；至少两个 AI Provider 在集成测试中验证；可导出 ≥100 条生成用例（JSON/CSV）；差异分析能映射变更函数到受影响模块

## 11. 风险与约束

- 内网与多环境模型 API 差异 → 通过 Provider 抽象与 Fallback 缓解
- C/C++ 宏较多时 AST 质量下降 → 预处理回退与符号级降级
- 覆盖率工具异构 → 可插拔覆盖率适配层

缓解措施见 HLD 与 PLAN。
