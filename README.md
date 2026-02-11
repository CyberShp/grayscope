# GrayScope 灰盒测试分析平台

面向数据存储软件的 AI 驱动灰盒/白盒测试分析系统。

GrayScope 帮助测试团队从黑盒测试转向智能灰盒/白盒分析，通过静态代码分析（tree-sitter）与 AI 推理相结合，识别：

- **分支路径分析** (branch_path)：控制流分支分类与覆盖缺口
- **边界值分析** (boundary_value)：比较/数组访问边界候选推导
- **错误路径分析** (error_path)：资源生命周期、清理与 errno 一致性
- **调用图构建** (call_graph)：函数依赖图与扇入/扇出分析
- **并发风险分析** (concurrency)：共享变量竞态与锁顺序分析
- **差异影响分析** (diff_impact)：Git diff → 函数映射 → 传递影响
- **覆盖率映射** (coverage_map)：覆盖率与风险发现叠加
- **事后分析** (postmortem)：逃逸缺陷根因链与预防性测试
- **缺陷知识库** (knowledge_pattern)：缺陷模式提取、持久化与匹配

## 技术栈

| 层级 | 技术 |
|------|------|
| 前端 | Vue 3 + Element Plus + ECharts |
| 后端 | FastAPI + SQLAlchemy + tree-sitter |
| AI | Ollama / Qwen / DeepSeek / OpenAI 兼容 / 自定义 REST |
| 部署 | X86 Linux 内网，HTTP/HTTPS，无认证 |

## 快速开始

### Docker 一键部署

```bash
docker-compose up -d
```

后端 API：`http://<host>:18080`，前端：`http://<host>:15173`。

### 本地开发

**后端：**

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --host 127.0.0.1 --port 18080 --reload
```

API 文档：http://127.0.0.1:18080/docs

**前端：**

```bash
cd frontend
npm install
npm run dev
```

访问：http://localhost:15173

## 项目结构

```
grayscope/
├── backend/                 # FastAPI 后端
│   └── app/
│       ├── api/v1/          # REST 路由
│       ├── analyzers/       # 9 个分析器模块
│       ├── ai/              # Provider 抽象、Prompt 引擎
│       ├── core/            # 数据库、异常、响应
│       ├── models/          # SQLAlchemy 模型
│       ├── repositories/     # 数据访问层
│       ├── schemas/         # Pydantic 校验
│       ├── services/        # 编排、Git、导出等
│       └── utils/
├── frontend/                # Vue3 + Element Plus
│   └── src/
│       ├── views/           # 仪表盘、新建分析、任务详情等
│       ├── components/
│       ├── api/
│       └── composables/
├── cli/                     # Typer CLI
│   └── grayscope_cli/
├── docs/                    # PRD、HLD、PLAN、API、DB、分析器契约
├── docker-compose.yml
└── README.md
```

## API 概览

| 接口 | 说明 |
|------|------|
| `GET /api/v1/health` | 服务健康检查 |
| `POST /api/v1/projects` | 创建项目 |
| `POST /api/v1/projects/{id}/repos` | 添加仓库 |
| `POST /api/v1/analysis/tasks` | 创建并执行分析任务 |
| `GET /api/v1/analysis/tasks/{id}` | 任务状态 |
| `GET /api/v1/analysis/tasks/{id}/results` | 任务结果 |
| `GET /api/v1/analysis/tasks/{id}/export` | 导出（json/csv/findings） |
| `POST /api/v1/postmortem` | 事后分析 |
| `GET /api/v1/knowledge/patterns` | 知识库模式检索 |
| `POST /api/v1/knowledge/match` | 发现与知识库匹配 |

## CLI 使用

```bash
cd cli
pip install -r requirements.txt
```

**健康检查：**

```bash
python -m grayscope_cli.main health
```

**创建分析：**

```bash
python -m grayscope_cli.main analyze create \
  --project 1 --repo 1 --type full --target .
```

**查看结果：**

```bash
python -m grayscope_cli.main analyze results <task_id>
```

**导出：**

```bash
python -m grayscope_cli.main export <task_id> --format json -o results.json
```

**事后分析：**

```bash
python -m grayscope_cli.main postmortem \
  --project 1 --repo 1 \
  --title "alloc_entry 内存泄漏" \
  --severity S1 \
  --desc "malloc 失败但 entry 未释放"
```

**知识库检索：**

```bash
python -m grayscope_cli.main knowledge search --project 1 --keyword leak
```

## 分析器模块

| 模块 ID | 名称 | 说明 |
|---------|------|------|
| branch_path | 分支路径分析 | 基于 CFG 的分支分类与缺口检测 |
| boundary_value | 边界值分析 | 比较/数组访问边界候选推导 |
| error_path | 错误路径分析 | 资源生命周期、清理、errno 一致性 |
| call_graph | 调用图构建 | 函数依赖图与扇入/扇出分析 |
| concurrency | 并发风险分析 | 共享变量竞态、锁顺序分析 |
| diff_impact | 差异影响分析 | Git diff → 函数映射 → 传递影响 |
| coverage_map | 覆盖率映射 | 覆盖率与风险发现叠加 |
| postmortem | 事后分析 | 逃逸缺陷根因链与预防性测试 |
| knowledge_pattern | 缺陷知识库 | 缺陷模式提取、持久化与匹配 |

## AI 提供商

- **Ollama**（本地模型）
- **Qwen**（阿里云）
- **DeepSeek**
- **OpenAI 兼容**（任意兼容端点）
- **自定义 REST**（内网蒸馏模型等）

## 文档

- [PRD](docs/PRD.md) — 产品需求
- [HLD](docs/HLD.md) — 高层设计
- [PLAN](docs/PLAN.md) — 实施计划
- [API_SPEC](docs/API_SPEC.md) — API 规范
- [DB_SCHEMA](docs/DB_SCHEMA.md) — 数据库 schema
- [ANALYZER_CONTRACTS](docs/ANALYZER_CONTRACTS.md) — 分析器契约

## 许可证

仅供内部使用。
