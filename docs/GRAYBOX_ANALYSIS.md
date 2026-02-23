# GrayScope 灰盒测试分析原理与设计文档

本文档阐述 GrayScope 的**灰盒测试分析原理**与**设计思路**，面向测试架构师与开发人员，说明平台如何从代码结构出发识别多函数交汇临界点、生成可执行的灰盒测试用例。

---

## 一、灰盒测试的定义与定位

### 1.1 黑盒、白盒与灰盒

| 维度 | 黑盒 | 白盒 | 灰盒（GrayScope 定位） |
|------|------|------|------------------------|
| **可见性** | 仅接口与行为 | 源码、分支、覆盖率全可见 | 接口 + 有限结构（调用关系、关键路径、多函数交汇点） |
| **测试设计依据** | 需求/规格 | 语句、分支、路径覆盖 | **多函数/多分支交汇场景** + 预期失败 vs 不可接受结果 |
| **典型问题** | 不知道「谁和谁在何时交汇」，需 N 次随机撞 | 用例与实现强耦合，维护成本高 | 用**少量精准用例**暴露交汇临界点的异常行为 |
| **目标** | 功能正确性 | 覆盖度与代码质量 | **一次用例暴露多函数交汇时的不可接受结果** |

灰盒测试的核心诉求：在**不完全依赖代码实现细节**的前提下，利用**有限的结构信息**（调用图、错误路径、数据流传播）找到**多个函数或故障处理分支在同一场景下交汇**的临界点，并明确「什么是可接受的失败」「什么是不可接受的结果」，从而设计高价值的测试用例。

### 1.2 为什么需要灰盒

- **黑盒**：例如 iSCSI login 时叠加端口闪断或网卡下电，预期失败是「建联失败」，不可接受是「控制器下电、进程崩溃」。黑盒不知道代码里哪些函数/分支会交汇，只能靠大量组合测试撞出问题。
- **白盒**：关注行/分支覆盖，容易产生大量与「多函数交汇临界行为」无关的用例，且维护成本高。
- **灰盒**：显式识别「login + handle_port_flap + handle_card_power_off」等交汇点，设计**一次**针对性用例（在 login 过程中注入端口闪断/网卡下电），验证仅出现「建联失败」而不出现「控制器下电/进程崩溃」。

---

## 二、核心分析原理

### 2.1 多函数交汇临界点

**交汇临界点**：两个或多个函数（或同一函数内的不同分支）在**同一执行场景下**共同影响系统行为的位置。典型形态包括：

- **调用链上的资源与错误**：调用者分配资源 → 被调用者失败 → 调用者是否正确释放（error_path 的 cross_function_resource_leak）。
- **并发下的共享状态**：多个函数在不同线程中访问同一共享变量，无锁写或锁顺序不一致（concurrency 的 race、lock_order_inversion、cross_function_deadlock_risk）。
- **数据流传播链**：外部输入经多级函数传播后到达敏感操作或边界判断（data_flow 的 external_to_sensitive、deep_param_propagation）。
- **变更影响链**：某函数变更后，其调用者/被调用者行为未适配（diff_impact 的 changed_core_path、transitive_impact）。

分析器通过**调用图、数据流、错误路径、并发访问、差异影响**等维度，为每个发现标注「谁参与了这条风险链」，即 **related_functions**（关联函数列表）。

### 2.2 预期失败与不可接受结果

每条灰盒发现需要区分两类结果，便于测试人员判断用例是否通过：

| 概念 | 含义 | 示例 |
|------|------|------|
| **预期失败（可接受）** | 在该风险场景下，系统**允许**出现的结果 | 建联失败、连接超时、返回 -ETIMEDOUT |
| **不可接受结果** | 一旦出现即视为**缺陷**的结果 | 控制器下电、进程崩溃、不可恢复状态、数据损坏 |

设计目标：灰盒用例应能**复现预期失败**（验证系统按设计降级），并**不出现不可接受结果**（否则提缺陷）。各分析器在 evidence 中提供 **expected_failure** 与 **unacceptable_outcomes**，用于生成和展示测试用例。

### 2.3 从发现到测试用例的映射

```
代码/版本
    ↓
静态分析（AST、CFG、调用图、数据流、并发、diff）
    ↓
findings（含 risk_type、evidence、related_functions、expected_failure、unacceptable_outcomes）
    ↓
导出服务 + AI 增强
    ↓
结构化测试用例（目标、前置条件、步骤、预期结果、关联函数、预期失败、不可接受结果、执行提示、示例数据）
    ↓
持久化 / 导出（JSON、CSV、Markdown）
```

### 2.4 与业界灰盒方法的对应

- **灰盒四合一定义**（Cleanscape/Coulter）：灰盒 = 黑盒 + 白盒 + 回归 + 变异。GrayScope 的静态分析提供「白盒」结构信息，导出用例支持「回归」与可复制步骤；若有覆盖率/执行反馈可进一步与「变异/预言质量」结合。
- **十步法对应**：识别输入/输出 → 对应导出的 test_steps、expected_result、example_input；识别主要路径 → 对应 **critical_combinations** 与各分析器路径；按子功能设计并验证 → 对应按 finding/symbol 生成的用例；回归 → 导出说明「可复制加入回归套件」。
- **静态引导动态**：导出的 **target_file、target_function、line_start** 及 **critical_combinations** 中的路径与函数列表，可作为下游**动态测试**、**Concolic 执行**或 **Fuzzer** 的目标与种子输入，实现「静态分析指明目标、动态/符号执行生成输入」的闭环。

---

## 三、GrayScope 实现原理概览

### 3.1 分层架构

1. **解析层**：tree-sitter 解析 C/C++，产出 AST、符号表、控制流图（CFG）；为所有分析器提供统一输入。
2. **分析器层**：多个独立分析器（branch_path、boundary_value、error_path、call_graph、data_flow、concurrency、diff_impact、coverage_map），按依赖顺序执行，每个模块输出 **ModuleResult**（findings + risk_score + artifacts）。
3. **证据与灰盒字段**：每个 finding 的 **evidence** 可包含模块特有数据；为支撑灰盒，统一扩展 **related_functions**、**expected_failure**、**unacceptable_outcomes**（由分析器直接写入或由导出服务从 callers/callees、propagation_chain 等推导）。
4. **AI 增强层**：对单模块发现做摘要与测试建议；跨模块综合分析时，要求 AI 输出 **critical_combinations**（多函数交汇临界点），包含上述三项，用于补全灰盒场景。
5. **导出与展示层**：将 findings 转为测试用例（含关联函数、预期失败、不可接受结果），持久化到 test_cases 表，并支持 JSON/CSV/Markdown 导出；前端在测试用例详情中突出展示灰盒相关字段。

### 3.2 灰盒证据的三种来源

| 来源 | 说明 | 示例 |
|------|------|------|
| **分析器直接写入** | 分析器在生成 finding 时即写入 related_functions、expected_failure、unacceptable_outcomes | error_path 的 cross_function_resource_leak；concurrency 的 cross_function_race / cross_function_deadlock_risk；data_flow 的传播链；diff_impact 的 impacted_callers/callees |
| **导出服务推导** | evidence 中无显式三项时，从 callers/callees、propagation_chain 等推导 | _get_related_functions() 从 call_graph 的 callers/callees 或 data_flow 的 propagation_chain 提取函数列表 |
| **AI 综合补全** | 跨模块分析时，AI 输出 critical_combinations，经 _extract_test_suggestions 解析后写入测试建议 | 提示词要求输出 related_functions、expected_failure、unacceptable_outcomes、scenario_brief |

---

## 四、各分析器与灰盒证据设计

以下说明各分析器如何贡献「多函数交汇」与「预期失败/不可接受结果」信息。

### 4.1 branch_path（分支路径分析）

- **产出**：基于 CFG 的分支分类（error/cleanup/boundary/state/normal）、未覆盖路径。
- **灰盒扩展**：evidence 中按 path_type 写入 **expected_failure**、**unacceptable_outcomes**（如错误路径：预期失败「错误条件成立导致进入错误处理路径」，不可接受「资源泄漏、状态不一致、崩溃」）。
- **关联函数**：当前以单函数为主；若后续接入 call_graph，可从调用者扩展 related_functions。

### 4.2 boundary_value（边界值分析）

- **产出**：比较/数组访问的约束表达式、推导区间、测试候选值；可选传播链（与 data_flow 上游结合）。
- **灰盒扩展**：evidence 写入 **expected_failure**（如「边界值或边界±1 触发错误分支或越界」）、**unacceptable_outcomes**（如「越界、溢出、错误逻辑」）；传播链存在时，related_functions 可由导出服务从 propagation_chain 推导。

### 4.3 error_path（错误路径分析）

- **产出**：缺失清理、错误码不一致、静默吞错、**跨函数资源泄漏**（caller 分配资源，callee 失败后 caller 未释放）。
- **灰盒扩展**：cross_function_resource_leak 类发现显式写入 **related_functions**（caller/callee）、**expected_failure**、**unacceptable_outcomes**，直接支撑「多函数交汇」用例。

### 4.4 call_graph（调用图构建）

- **产出**：函数级有向图、扇入/扇出、调用链；findings 如 high_fan_out、deep_impact_surface。
- **灰盒扩展**：evidence 中的 callers/callees/chain 被导出服务用于推导 **related_functions**；本模块不直接写 expected_failure/unacceptable_outcomes，由下游或 AI 补全。

### 4.5 data_flow（数据流分析）

- **产出**：跨函数参数传播链、入口→敏感操作、值域变换风险（deep_param_propagation、external_to_sensitive、value_transform_risk）。
- **灰盒扩展**：evidence 写入 **related_functions**（传播链上的函数列表）、**expected_failure**、**unacceptable_outcomes**（如「未校验外部输入直达敏感操作」→ 不可接受「缓冲区溢出、注入、崩溃」）。

### 4.6 concurrency（并发风险分析）

- **产出**：无锁写、锁顺序反转、原子性缺口、**跨函数死锁风险**、**跨函数竞态**。
- **灰盒扩展**：所有 risk_type 的 evidence 均写入 **related_functions**、**expected_failure**、**unacceptable_outcomes**（如跨函数竞态：预期失败「数据竞态」，不可接受「未定义行为、崩溃」）。

### 4.7 diff_impact（差异影响分析）

- **产出**：变更函数、上游调用者/下游被调用者、传递影响深度。
- **灰盒扩展**：evidence 写入 **related_functions**（变更函数 + impacted_callers/callees）、**expected_failure**（如「变更导致行为或契约变化，调用者未适配」）、**unacceptable_outcomes**（如「功能回归、崩溃、错误返回值」）。

### 4.8 coverage_map（覆盖率映射）

- **产出**：行/分支覆盖率与发现的叠加、高风险低覆盖清单。
- **灰盒扩展**：本模块主要做覆盖与风险叠加；related_functions 等可由关联的发现继承或由导出服务从上游发现推导。

---

## 五、数据流与编排设计

### 5.1 分析编排顺序

- **阶段 A**（无分析器间依赖）：branch_path、boundary_value、error_path、call_graph。
- **阶段 B**（依赖阶段 A）：data_flow（依赖 call_graph）、concurrency（可选 call_graph）、diff_impact（依赖 call_graph）、coverage_map（依赖其他模块发现）。
- **阶段 C**（可选）：postmortem、knowledge_pattern，依赖用户缺陷上下文及既有发现。

每个模块独立执行并落库；单模块失败不拖垮整任务，支持仅重试失败模块。

### 5.2 从发现到测试用例的流水线

1. **任务执行完毕**：所有启用模块的 ModuleResult 持久化到 analysis_module_results、risk_findings（若有统一表）或结果 JSON。
2. **导出/聚合**：ExportService._findings_to_testcases() 遍历所有发现，对每条发现：
   - 用 _get_related_functions()、_get_expected_failure()、_get_unacceptable_outcomes() 从 evidence 或默认映射取灰盒三要素；
   - 用 _format_objective_with_related() 将关联函数写入测试目标；
   - 用 _append_expected_vs_unacceptable() 将预期失败与不可接受结果并入预期结果文案；
   - 生成 execution_hint、example_input 等，输出结构化 case 字典。
3. **持久化**：用户可将导出的用例批量持久化到 test_cases 表（TestCase 模型含 related_functions_json、expected_failure、unacceptable_outcomes_json 等）。
4. **AI 综合**：若启用跨模块 AI，synthesize_cross_module() 会请求 AI 输出 critical_combinations，经 _extract_test_suggestions() 解析后并入测试建议，同样具备 related_functions、expected_failure、unacceptable_outcomes。

### 5.3 前端展示与可读性

- **测试用例详情页**：突出展示「关联函数（交汇临界点）」「预期失败（可接受）」「不可接受结果」；新手指引说明如何根据这三项执行用例与判通过/失败。
- **任务详情发现列表**：风险类型使用中文映射（useRiskTypeNames）；展开行展示推荐测试设计与证据（EvidenceRenderer）。
- **导出**：CSV/Markdown 均含关联函数、预期失败、不可接受结果列或区块；Markdown 模板可供新手按灰盒结构填写新用例。

---

## 六、测试用例生成与可读性设计

### 6.1 结构化字段（与灰盒强相关）

| 字段 | 用途 |
|------|------|
| objective | 测试目标；可前缀「关联函数: A, B, C。灰盒目标: …」 |
| preconditions | 前置条件（列表） |
| test_steps | 步骤（列表） |
| expected_result | 预期结果（含预期失败与不可接受结果的说明） |
| related_functions | 关联函数列表（交汇临界点） |
| expected_failure | 可接受的失败描述 |
| unacceptable_outcomes | 不可接受结果列表 |
| execution_hint | 如何执行（环境、工具、注意点） |
| example_input | 示例输入，便于新手构造数据 |

### 6.2 优先级与严重程度映射

- 发现严重程度 S0/S1/S2/S3 映射为测试优先级 P0/P1/P2/P3，保证高严重度发现对应高优先级用例。

### 6.3 模板与导出

- **灰盒用例 Markdown 模板**：通过 GET /api/v1/test-cases/template 获取，内含关联函数、预期失败、不可接受结果的占位与说明，便于手工补充或评审。
- **导出格式**：JSON（机器可读）、CSV（表格）、Markdown（人类可读清单），均包含灰盒相关列或区块。

---

## 七、与现有文档的关系

| 文档 | 关系 |
|------|------|
| [PRD](PRD.md) | 产品需求与九大模块定义；本设计文档是 PRD 中「灰盒分析」的展开与实现说明。 |
| [HLD](HLD.md) | 系统架构、编排顺序、数据流；本设计文档在 HLD 基础上细化灰盒证据与用例生成链路。 |
| [ANALYZER_CONTRACTS](ANALYZER_CONTRACTS.md) | 各分析器输入输出契约；本设计文档说明各模块如何扩展 evidence 以支撑 related_functions、expected_failure、unacceptable_outcomes。 |
| [GRAYBOX_VALUE](GRAYBOX_VALUE.md) | 灰盒核心价值与示例（如 iSCSI login）；本设计文档从原理与设计层面系统化阐述，与 GRAYBOX_VALUE 互为补充。 |
| [API_SPEC](API_SPEC.md) / [DB_SCHEMA](DB_SCHEMA.md) | API 与表结构；测试用例的 CRUD、导出、模板接口及 test_cases 表字段与本文的「测试用例生成与可读性」一致。 |

---

## 八、小结

- **灰盒测试**：利用有限结构信息（调用图、错误路径、数据流、并发、变更影响）识别**多函数交汇临界点**，并区分**预期失败**与**不可接受结果**，用少量精准用例暴露问题。
- **GrayScope 原理**：静态分析器产出带 evidence 的 findings，evidence 中显式或可推导出 related_functions、expected_failure、unacceptable_outcomes；导出服务与 AI 综合将发现转为结构化测试用例并持久化；前端与导出格式突出灰盒三要素，提升可读性与可执行性。
- **设计要点**：分析器契约统一、灰盒三要素贯穿发现→用例→展示→导出；AI 通过 critical_combinations 补全跨模块交汇场景；测试用例模型与 API 支持灰盒字段的读写与模板下载。

---

## 九、与第三轮调研（底层分析重构）的关系

[GRAYBOX_RESEARCH_AND_ITERATION.md](GRAYBOX_RESEARCH_AND_ITERATION.md) 第九节提出：**以多函数交互为唯一锚点**，对分析层进行推翻、合并与重构。要点包括：(1) 将 branch_path 与 error_path 合并为「路径与资源」分析；(2) call_graph 仅作基础设施，不再产出高扇出/深影响面类发现；(3) boundary_value 可选并入 data_flow，形成「数据流 + 约束」；(4) **新增静态交汇步骤**：基于 call_graph 与 findings 先计算候选 critical_combinations，再由 AI 排序与补全。本文档第四、五节所述各分析器与灰盒证据设计，在实施第三轮重构时将按上述分层（结构层 / 跨函数风险层 / 叠加与反馈层）演进，**多函数交汇**始终为灰盒分析的核心目标。
