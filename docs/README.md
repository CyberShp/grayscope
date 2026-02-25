# GrayScope 文档索引

本目录为 GrayScope 灰盒测试分析平台的文档集合。按用途分类如下。

---

## 产品与设计

| 文档 | 说明 |
|------|------|
| [PRD.md](PRD.md) | 产品需求文档：目标用户、核心模块、AI 增强、部署与验收标准 |
| [HLD.md](HLD.md) | 高层设计：系统架构、九大分析器、AI 集成、数据流与任务状态机 |
| [PLAN.md](PLAN.md) | 实施计划：阶段划分、DoD、模块 ID 与跨阶段产物 |

---

## 灰盒测试原理与价值

| 文档 | 说明 |
|------|------|
| [GRAYBOX_VALUE.md](GRAYBOX_VALUE.md) | 灰盒核心价值：多函数交汇临界点、预期失败 vs 不可接受结果 |
| [GRAYBOX_ANALYSIS.md](GRAYBOX_ANALYSIS.md) | 分析原理与设计：交汇临界点、发现→用例映射、与业界方法对应 |
| [GRAYBOX_VS_GRAYSCOPE.md](GRAYBOX_VS_GRAYSCOPE.md) | 与外部 graybox 项目对比：规则驱动、分层、按文件分析等 |
| [GRAYBOX_RESEARCH_AND_ITERATION.md](GRAYBOX_RESEARCH_AND_ITERATION.md) | 调研与迭代：业界定义、EvoMaster/GrayC、十步法、Oracle 缺口、第二轮迭代（performance_requirement、静态引导动态） |

---

## 接口与实现

| 文档 | 说明 |
|------|------|
| [API_SPEC.md](API_SPEC.md) | API 规范 V1：健康检查、项目/仓库、任务、导出、覆盖率北向、事后分析等 |
| [COVERAGE_NORTHBOUND.md](COVERAGE_NORTHBOUND.md) | 覆盖率北向接口：数据格式、summary/granular、用例映射 |
| [ANALYZER_CONTRACTS.md](ANALYZER_CONTRACTS.md) | 分析器契约：输入输出、risk_type、evidence、灰盒字段约定 |
| [IMPLEMENTATION.md](IMPLEMENTATION.md) | 核心实现说明：调用链、编排器、导出服务、AI 增强与跨模块综合 |
| [DB_SCHEMA.md](DB_SCHEMA.md) | 数据库表结构：projects、repositories、analysis_tasks、module_results 等 |

---

## 部署与使用

| 文档 | 说明 |
|------|------|
| [DEPLOYMENT.md](DEPLOYMENT.md) | **部署文档**：Docker 与本地部署、端口、环境变量、测试执行环境、故障排查 |
| [PRODUCT_GUIDE.md](PRODUCT_GUIDE.md) | **产品使用指南**：项目/仓库、新建分析、任务结果、测试设计、DT 脚本、测试执行、导出、事后分析与知识库、CLI 参考 |

---

## 测试与质量

| 文档 | 说明 |
|------|------|
| [TEST_REPORT.md](TEST_REPORT.md) | 测试报告：后端/前端验证、迭代改动摘要、已知限制与测试命令 |

---

## 使用建议

- **新人**：先读 [GRAYBOX_VALUE.md](GRAYBOX_VALUE.md) 与 [PRD.md](PRD.md)，再根据需要查阅 [API_SPEC.md](API_SPEC.md) 或 [HLD.md](HLD.md)。
- **迭代与调研**：以 [GRAYBOX_RESEARCH_AND_ITERATION.md](GRAYBOX_RESEARCH_AND_ITERATION.md) 为主，配合 [GRAYBOX_ANALYSIS.md](GRAYBOX_ANALYSIS.md)。
- **对接覆盖率/导出**：见 [COVERAGE_NORTHBOUND.md](COVERAGE_NORTHBOUND.md) 与 [API_SPEC.md](API_SPEC.md) 导出与覆盖率小节。
