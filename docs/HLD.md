# GrayScope 高层设计（HLD）

## 1. 设计目标

- 提供可直接落地的架构与契约
- 解耦分析器、编排与 AI 提供商
- 保证部分结果可用与增量演进（单模块失败不拖垮整任务）

## 2. 系统架构：三层架构

```
┌─────────────────────────────────────────────────────────────────┐
│  前端：Vue3 + Element Plus + ECharts（端口 15173）               │
│  视图：仪表盘、新建分析、任务详情、差异影响、事后分析、知识库     │
└───────────────────────────┬─────────────────────────────────────┘
                            │ HTTP/HTTPS
┌───────────────────────────▼─────────────────────────────────────┐
│  后端：FastAPI（端口 18080）                                      │
│  API 网关 → 任务/项目/仓库/结果/事后/知识库 路由                   │
│  服务层：TaskService、AnalysisOrchestrator、ResultService、       │
│          GitService、ExportService、PostmortemService、Knowledge  │
│  分析器：branch_path / boundary_value / error_path / call_graph / │
│          concurrency / diff_impact / coverage_map / postmortem / │
│          knowledge_pattern                                        │
│  AI 层：Provider 抽象、Prompt Engine、多 Provider 实现            │
└───────────────────────────┬─────────────────────────────────────┘
                            │
┌───────────────────────────▼─────────────────────────────────────┐
│  数据与外部：SQLite / PostgreSQL；可选 Redis；Git；tree-sitter   │
│  模型服务：Ollama / Qwen / DeepSeek / OpenAI 兼容 / 自定义 REST   │
└─────────────────────────────────────────────────────────────────┘
```

- **前端**：Vue3 + Element Plus + ECharts，负责任务创建、进度、报告与导出
- **后端**：FastAPI + SQLAlchemy，负责 API、编排、分析器执行、AI 调用与持久化
- **数据**：SQLite（开发/小规模）或 PostgreSQL（生产），可选 Redis 做任务队列

## 3. 模块设计：九大分析器

所有分析器实现统一契约：

```python
class Analyzer(Protocol):
    module_id: str
    depends_on: list[str]
    def analyze(self, ctx: AnalyzeContext) -> ModuleResult: ...
```

**ModuleResult** 必含：`module_id`、`status`、`findings`、`risk_score`（0..1）、`artifacts`、`metrics`。

| 模块 | 输入 | 输出要点 |
|------|------|----------|
| branch_path | AST + 函数 CFG | 分支 ID、条件表达式、路径类型（normal/error/cleanup）、未达提示 |
| boundary_value | AST | 比较与约束、边界候选（min-1, min, mid, max, max+1, invalid-null） |
| error_path | AST | goto cleanup、return -errno、缺失清理、返回值不一致 |
| call_graph | AST | 函数级有向图；get_callers(fn,depth)、get_callees(fn,depth) |
| concurrency | AST + 调用图 | 共享状态、锁区域、锁顺序反转候选、未同步写 |
| diff_impact | 统一 diff + 调用图 | 变更函数映射、深度默认 2 的传递影响 |
| coverage_map | 覆盖率数据 + 发现 | 行/分支覆盖与发现叠加、高风险低覆盖清单 |
| postmortem | 缺陷元数据 + 版本范围 | 遗漏路径链、预防性测试 |
| knowledge_pattern | 缺陷模式 | 触发形态、代码坏味签名、推荐测试模板；持久化与检索 |

**编排依赖顺序**：

- 阶段 A：branch_path、boundary_value、error_path、call_graph
- 阶段 B：concurrency、diff_impact、coverage_map（依赖 A）
- 阶段 C：postmortem、knowledge_pattern（依赖 A/B 及用户缺陷上下文）

## 4. AI 集成设计

### 4.1 Provider 抽象层

```python
class ModelProvider(ABC):
    @abstractmethod
    async def chat(self, messages: list[dict], **kwargs) -> dict: ...
    @abstractmethod
    async def health_check(self) -> bool: ...
    @abstractmethod
    def name(self) -> str: ...
```

- 注册键：`provider_id`
- 项目级默认 Provider + 模型；任务级可覆盖
- Fallback 链示例：`custom_internal → ollama → openai_compat`

### 4.2 Prompt Engine

- 模板目录：`backend/app/ai/prompt_templates/`
- 每模板含：`template_id`、`version`、`input_schema`、`output_schema`、`system_prompt`、`user_prompt`
- AI 输出经 JSON Schema 校验；非法输出可重试一次（含修复用 prompt）

## 5. 数据流

1. **任务创建**：前端/CLI → `POST /api/v1/analysis/tasks` → TaskService 创建任务并触发 Orchestrator
2. **编排执行**：加载任务与版本 → 准备工作区与 parser 缓存 → 按依赖顺序执行分析器 → 每模块结果独立落库 → 按模块或策略触发 AI 增强 → 汇总风险并更新任务状态
3. **结果消费**：`GET results` / `GET report` / `POST export` 从 DB 与制品库读取
4. **事后分析**：提交缺陷元数据 → postmortem 分析器 + AI → 根因链与模式写入知识库

## 6. 任务状态机

```
[*] → pending → running → success
                 running → partial_failed → (retry_failed) → running
                 running → failed
pending/running → cancelled
partial_failed → success（部分模块重试后全部成功时）
```

## 7. 持久化模型（核心表）

- `projects`、`repositories`
- `analysis_tasks`、`analysis_module_results`、`risk_findings`
- `test_cases`、`defect_patterns`、`model_configs`

关键索引：`analysis_tasks(project_id, created_at)`；`analysis_module_results(task_id, module_id)` 唯一；`risk_findings(task_id, risk_type, severity)`。

## 8. 部署架构

- **内网 X86 Linux**：单机或多机部署
- **HTTP/HTTPS**：反向代理（如 Nginx）可置于前端/后端前
- **无认证**：当前无 RBAC/SSO；密钥仅通过环境变量注入
- **可选**：Celery/RQ 异步任务；制品存储为本地 FS 或对象存储（适配器抽象）

## 9. API 核心（V1）

- 项目/仓库：`POST/GET /api/v1/projects`；`POST /api/v1/projects/{id}/repos`；`POST /api/v1/repos/{id}/sync`
- 分析：`POST /api/v1/analysis/tasks`；`GET /api/v1/analysis/tasks/{id}`；`POST retry/cancel`
- 结果与导出：`GET /api/v1/analysis/tasks/{id}/results`、`report.md`；`POST export`
- 模型：`GET /api/v1/models`；`POST /api/v1/models/test`

## 10. 前端与 CLI

- **前端**：dashboard、new-analysis、task-detail、diff-impact、postmortem、knowledge-base；任务详情需展示模块状态矩阵、风险汇总、发现表（含文件/函数链接）、导出操作
- **CLI**：`grayscope health`；`grayscope analyze create/status`；`grayscope export`；支持机器可读 JSON 输出

## 11. 可观测与可靠性

- 结构化日志含 `task_id`、`module_id`、`provider`
- 每模块耗时与 token 用量
- 分析器瞬时错误：最多 2 次重试；模型超时：指数退避 3 次；按 Provider 的熔断

## 12. 安全与合规（当前阶段）

- 仅内网部署；敏感信息仅通过环境变量配置
- 不向公网模型端点发送源码；AI 调用可记录元数据（哈希与大小）用于审计
