# GrayScope 产品使用指南

本文档面向测试工程师与项目负责人，说明如何通过 Web 与 CLI 使用 GrayScope 完成灰盒分析与测试设计、执行。

## 1. 核心流程概览

1. **创建项目** → **添加仓库**（关联 Git 代码库）
2. **新建分析任务**（选择模块、目标路径、可选 AI）
3. **查看任务结果**（风险发现、测试用例建议）
4. **测试设计中心**（浏览/筛选用例建议，持久化为正式用例）
5. **测试执行**（创建运行、选择用例、Docker/SSH 执行，查看通过/失败）
6. **导出与复盘**（导出用例/发现、事后分析、知识库）

## 2. 项目与仓库

- **项目**：对应一个产品或子系统，用于聚合仓库与分析任务。
- **仓库**：绑定项目的 Git 仓库，需配置本地路径或可拉取的远程地址；分析时基于该仓库的代码与可选 Git 差异。

操作入口：**项目** 列表 → 进入某项目 → **仓库** 管理。

## 3. 新建分析

- 入口：**新建分析**。
- 必选：项目、仓库、任务类型（如 full / file / diff）。
- 可选：分析目标路径、分支/提交、启用的分析模块（branch_path、boundary_value、error_path、call_graph、concurrency、diff_impact、coverage_map、postmortem、knowledge_pattern）、AI 提供商与模型。
- 提交后任务进入 **任务中心**，可查看状态与结果。

## 4. 任务结果与发现

- **任务中心**：查看所有任务状态（pending / running / success / partial_failed / failed）。
- **任务详情**：查看各模块结果、风险发现列表、调用图/数据流等可视化。
- **风险发现**：全局或项目级查看发现项，包含 risk_type、优先级、证据（evidence）、关联函数等；可据此筛选并进入测试设计。

## 5. 测试设计中心

- **建议用例**：基于灰盒分析生成的测试用例建议（未持久化），可按项目、优先级、分析模块筛选。
- **已持久化用例**：已保存为正式测试用例的条目，可编辑标题、步骤、预期、优先级等。
- 从建议用例可 **持久化** 为正式用例，并进入 **测试用例详情** 查看/编辑脚本（Python 占位或 C++ GTest/Unity DT 脚本）、生成脚本、查看关联发现与证据。

## 6. DT 测试脚本说明（定向测试）

GrayScope 生成的 C++ 测试脚本采用 **定向测试（DT）** 思路，借鉴成熟实践：

- **边界值（boundary_miss）**：按 BVA 法生成 min / min+1 / nominal / max-1 / max 等边界用例，脚本中含 `EXPECT_*` 断言占位，需根据实际接口补全调用与预期值。
- **错误路径（missing_cleanup / error_path）**：针对 malloc 失败等场景，脚本中说明可通过 malloc wrapper 或 LD_PRELOAD 注入失败，并断言返回值（如 -ENOMEM）与无资源泄漏；Unity Fixture 版本含 TEST_GROUP / TEST_SETUP / TEAR_DOWN 与 main。
- **并发（race / lock）**：双线程调用 + join + 对共享状态的断言模板，可按需补全具体调用与断言。

脚本头部注释中会标明 risk_type、目标函数与约束；按注释补全调用与断言后即可在项目测试环境中编译运行。

## 7. 测试执行

- 入口：**测试执行**。
- **新建运行**：选择项目、环境（Docker / SSH）、可选 Docker 镜像，在树状列表中选择要执行的用例（按项目 → 风险类型 → 优先级展开勾选）。
- **执行**：创建运行后，在运行详情页点击「执行」，系统会生成脚本、构建并运行（Docker 或 SSH），并汇总通过/失败/跳过。
- **查看结果**：运行详情中可查看每条执行的构建日志、运行输出、通过状态；失败时可依据日志修正脚本或环境后重新运行。

## 8. 导出

- **任务导出**：在任务详情中可导出任务结果为 JSON / CSV / findings 等格式，用于归档或外部系统对接。
- **覆盖率北向**：若配置了覆盖率接口，可将执行结果与覆盖率数据上报，详见 [COVERAGE_NORTHBOUND.md](COVERAGE_NORTHBOUND.md)。

## 9. 事后分析与知识库

- **事后分析**：针对已逃逸缺陷，提交描述与严重程度，系统结合仓库与发现生成根因链与预防性测试建议。
- **知识库**：缺陷模式可持久化为知识库条目，支持检索与匹配，用于后续分析时的风险提示与用例建议。

## 10. CLI 快速参考

```bash
cd cli && pip install -r requirements.txt
python -m grayscope_cli.main health
python -m grayscope_cli.main analyze create --project 1 --repo 1 --type full --target .
python -m grayscope_cli.main analyze results <task_id>
python -m grayscope_cli.main export <task_id> --format json -o results.json
python -m grayscope_cli.main postmortem --project 1 --repo 1 --title "标题" --severity S1 --desc "描述"
python -m grayscope_cli.main knowledge search --project 1 --keyword leak
```

更多子命令与参数见 `python -m grayscope_cli.main --help`。
