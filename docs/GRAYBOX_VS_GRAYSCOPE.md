# graybox 与 GrayScope 对比与改进说明

本文对比 Claude Code 生成的 **graybox** 项目（`/Volumes/Media/ClaudeCoding/graybox`）与当前 **GrayScope** 在分支路径分析、分层设计、结果数量上的差异，并说明 GrayScope 已采纳的改进与后续可选项。

---

## 一、核心问题：为什么 GrayScope 会产出 800+ 风险/用例？

- **branch_path**：对每个函数的**每个 CFG 分支节点**都产出一条 finding（if/switch/goto 等），一个中等项目动辄数百个分支 → 数百条发现。
- **1 finding → 1 测试用例**：导出时每条发现生成一条用例，所以发现数直接等于用例数。
- **多模块叠加**：branch_path + boundary_value + error_path + call_graph + … 合计很容易超过 800，测试人员难以筛选。

---

## 二、graybox 的做法（优点）

### 2.1 规则驱动、只报“高价值”风险

- **L2 风险**来自**规则**，不是“每个分支一条”：
  - 例如 **UncoveredBranchRule**：只报 (1) **switch 缺少 default**，(2) **圈复杂度 ≥ 10**（每个函数至多 1 条）。
- 结果：同一文件可能只有几条到十几条风险，而不是上百条。

### 2.2 四层流水线（L1→L2→L3→L4）

- **L1**：解析（函数、CFG、调用图）— 只做结构，不产风险。
- **L2**：规则评估 → **RiskItem**（数量少、语义明确）。
- **L3**：风险 → **FaultMapping**（注入点、方法、时机）。
- **L4**：风险 + 故障映射 → **TestCaseItem**（步骤、预期、检测方式）。

分层清晰，测试用例从“风险”派生，而不是从“每条 AST 节点”派生，数量自然可控。

### 2.3 用例结构适合执行

- **fault_window**：after/before/method，便于测试人员知道在哪注入、怎么注入。
- **detection**：列出推荐检测方式（覆盖率、断言、Valgrind 等）。
- **tags**：便于筛选（如 branch_coverage、gray_box）。

### 2.4 按文件分析

- 任务指定 **target_files**，按文件跑分析器，便于小范围、增量分析。

---

## 三、graybox 的不足或差异

- **规则较少**：branch_path 仅 2 类（switch_no_default、high_complexity），未覆盖“错误路径缺清理”“边界分支”等 GrayScope 已有的类型。
- **按文件**：100 个文件 = 100 次分析器调用；GrayScope 按目录 + max_files 一次扫，适合全仓扫描。
- **依赖与运维**：graybox 有 Celery、SSE 等，GrayScope 当前为同步编排，部署更简单。

---

## 四、GrayScope 已采纳的改进

### 4.1 编排器层：发现数量上限（max_findings_per_module）

- 在 **options** 中增加 **max_findings_per_module**（默认 150）。
- 每个分析器返回的 findings 若超过该值，按 **risk_score 降序**截断，只保留前 N 条再落库。
- 效果：单模块最多 150 条，总发现数可控（例如 8 模块 × 150 = 1200 上限，典型任务远低于此）。

### 4.2 branch_path：减量模式（branch_path_reduce）

- 当 **options.branch_path_reduce = true**（默认 true）时：
  - **只产出 error、cleanup 两类分支**的 finding，**不产出** boundary、state、normal 的逐条发现。
  - 若某函数分支数 ≥ **branch_path_complexity_threshold**（默认 10），额外产出一条 **high_complexity** 汇总发现（该函数有 N 个分支需关注），不再为每个分支各出一条。
- 效果：branch_path 从“每个分支一条”变为“只报高价值错误/清理路径 + 高复杂度汇总”，发现数可降一个数量级。

### 4.3 与 graybox 的对应关系

| graybox 做法           | GrayScope 对应                         |
|------------------------|----------------------------------------|
| 规则只报 switch/default、高复杂度 | branch_path_reduce：只报 error/cleanup + 高复杂度汇总 |
| 风险数量少             | max_findings_per_module 硬上限         |
| L2→L4 分层             | 保留现有“发现→导出用例”链路，在发现侧减量 |

---

## 五、后续可选项（已实现）

- **规则引擎**：已抽成 Rule 注册表（`app/analyzers/rules/`），branch_path 使用 `HighComplexityRule`、`ErrorCleanupOnlyRule`、`SwitchNoDefaultRule`、`GotoCleanupRule`，由规则决定是否产出某类风险，便于扩展。
- **L3 fault_window**：导出 JSON/用例结构中已增加 `fault_window`（after/before/method），便于测试人员确定注入时机与方式。
- **按文件分析**：任务 target 支持 `target_files` 列表；编排器按文件调用分析器并合并发现，适合大仓只分析变更文件。

---

## 六、小结

- **问题**：GrayScope 因“每分支一条发现”和多模块叠加，易产出 800+ 风险/用例，测试人员难以筛选。
- **graybox 优点**：规则驱动、只报高价值风险、四层分层、用例带 fault_window/detection，数量少、可执行性强。
- **GrayScope 改进**：  
  - 编排器层对单模块发现数做**上限截断**；  
  - branch_path 提供**减量模式**（只报 error/cleanup + 高复杂度汇总）。  
- 在不改整体架构的前提下，先通过“减量 + 上限”把发现和用例数压到可接受范围；后续如需再逐步引入规则引擎、L3 故障窗口等 graybox 思路。
