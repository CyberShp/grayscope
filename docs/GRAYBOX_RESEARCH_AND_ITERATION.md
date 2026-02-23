# 灰盒测试调研与 GrayScope 迭代建议

本文档基于联网检索的灰盒测试概念、原理、工具与开源实现，整理可借鉴的功能性、可用性、可读性与易用性，并给出对当前项目的迭代建议。可随时根据你的反馈调整优先级或补充问题。

---

## 一、灰盒测试概念与原理（业界共识）

### 1.1 定义（NIST / Wikipedia）

- **灰盒测试**：结合白盒与黑盒，测试者拥有**部分**内部结构知识（如文档中的数据结构、算法、架构），而非完全不可见或完全可见。
- **目标**：用黑盒的简洁执行方式，结合**针对代码/结构**的测试设计，发现「结构不当」或「使用不当」导致的缺陷。
- **设计依据**：高层与详细文档、架构、设计文档、API 规格，用于定义测试用例；常用技术包括**边界值分析、判定表、状态迁移**。
- **用例来源**：基于**算法**评估内部状态、程序行为与架构知识生成用例，而非完全人工从零设计。

### 1.2 与 GrayScope 的对应

| 业界表述 | GrayScope 现状 |
|----------|----------------|
| 部分内部知识 | 调用图、CFG、错误路径、数据流、并发访问 — 已具备 |
| 边界值 / 判定 / 状态 | boundary_value、branch_path、error_path 等 — 已具备 |
| 基于算法/结构生成用例 | 静态分析 → findings → 导出用例 — 已具备 |
| 预期结果 vs 不可接受 | expected_outcome（可成功或可接受失败）/ unacceptable_outcomes — 已具备并通用化 |

---

## 二、开源工具与实现逻辑

### 2.1 EvoMaster（REST/GraphQL/RPC API 灰盒/白盒）

- **定位**：首个开源的、AI 驱动的**系统级**测试生成（fuzzing），面向 Web/企业应用，支持黑盒与白盒。
- **核心机制**：  
  - **进化算法** + **动态程序分析**：以**代码覆盖率**和**故障发现**为反馈，进化测试用例。  
  - 白盒模式：分析 JVM 字节码，**可测试性变换**、**污点分析**，生成更有效的输入。  
  - REST 感知：利用 OpenAPI/Swagger，理解资源与依赖，生成「先建资源再测端点」的用例。
- **输出**：  
  - 可执行测试（JUnit 4/5 Java/Kotlin、Python、JavaScript 等）。  
  - **交互式 Web 报告**（index.html）汇总结果。  
  - 故障检测：500、schema 不匹配、访问策略违反等；**通过用例名/注释指出可能故障，用例仍为通过**（避免 flaky）。
- **可借鉴**：  
  - **覆盖率/故障双目标**的反馈驱动；  
  - **多格式输出**（多种语言 + Web 报告）；  
  - **自包含测试**（白盒时自动启停应用）；  
  - 明确区分「发现故障」与「用例通过」的展示方式。

### 2.2 GrayC（C 编译器/分析器灰盒 Fuzzing）

- **定位**：面向 C 编译器与代码分析器的**覆盖引导、变异式**灰盒 fuzzing（基于 LibFuzzer）。
- **核心逻辑**：  
  - **专用变异**：针对常见 C 结构做变异，使生成程序**可编译**、有**有意义的输出**。  
  - **差分测试**作为 **test oracle**：多编译器/分析器结果对比。  
  - 将 fuzzer 生成的程序**贡献回回归测试套件**（如 Clang/LLVM）。
- **可借鉴**：  
  - **领域专用变异/构造**（我们对应：按 path_type/risk_type 的步骤与注入方式）；  
  - **可集成到回归**的用例形态；  
  - **Oracle 明确**：预期失败 vs 不可接受，我们已区分，可再强化展示。

### 2.3 灰盒 + 故障注入（文献）

- **软件故障注入 + 灰盒**：结合故障相关需求与结构分析，在**目标位置**注入故障，提高覆盖与缺陷发现。  
- **基于模型的故障注入**：在模型层面注入，可 mock 组件，用于「对故障容忍」的验证。  
- **可借鉴**：我们的 **fault_window**（after/before/method）就是在标定「注入窗口」，可继续强化与用例步骤、执行建议的联动。

### 2.4 基于搜索的测试生成（SBST）

- **思路**：用遗传算法等，以**适应度函数**（如分支覆盖、变异分数）驱动生成测试。  
- **适应度**：常含 **approach level**（到目标路径的距离）、**branch distance**（到满足某分支条件的距离）。  
- **可借鉴**：我们当前是**静态分析 → 发现 → 导出**，没有运行时反馈；若未来做「一次执行 + 覆盖率反馈」的闭环，可引入类似目标与距离概念；短期可先做「发现优先级/排序」与「与覆盖率北向数据结合」的排序。

---

## 三、用例可读性、结构与易用性（最佳实践）

- **建议的用例结构**（与现有导出对齐）：  
  - 用例 ID、名称、**目标（Objective）**  
  - **前置条件**、**步骤**、**预期结果**、**测试数据/示例输入**  
  - **预期失败（可接受）**、**不可接受结果**（我们已有）  
  - **执行环境/建议**（我们已有 execution_hint、fault_window）  
- **可读性**：  
  - 用户界面驱动、同时验证内部行为，避免过于依赖实现细节而变脆。  
  - 文档中**显式区分**「对外行为验证」与「借助部分架构知识验证的内容」。

---

## 四、GrayScope 迭代建议（按优先级）

### P0：强化「多函数交汇临界点」的可见性与可执行性

1. **导出中把 critical_combinations 当一等公民**  
   - 跨模块 AI 产出的 `critical_combinations` 当前只在「AI 增强」里展示；建议在**导出 JSON/CSV/Markdown** 中单独一节「多函数交汇临界点」，每条含 related_functions、expected_failure、unacceptable_outcomes、scenario_brief，并生成对应**推荐步骤**与 **fault_window**，便于直接转成用例或导入测试管理工具。
2. **交汇临界点 → 可执行步骤**  
   - 为每条 critical_combination 生成「建议步骤」与「注入时机」（fault_window），即使不跑自动化，测试人员也能按步骤执行；若已有 fault_window，在导出中与步骤并列展示。

### P1：可读性与易用性

3. **统一用例字段与模板**  
   - 导出与前端展示统一包含：Test Case ID、Title、Objective、Preconditions、Steps、Expected Result、**Expected Outcome**（预期结果：可成功或可接受失败）、**Unacceptable Outcomes**、Related Functions、Fault Window、Execution Hint、Example Input；Markdown 导出增加简短「使用说明」。
4. **Web 报告或单页汇总**  
   - 借鉴 EvoMaster：在导出时生成一份 **index.html**（或内嵌到前端的「导出预览」），汇总：模块风险、发现数、多函数交汇临界点列表、每条发现的 one-line 摘要与跳转，提升「打开即懂」的体验。
5. **Oracle 的通用化（不做单一固定句）**  
   - 灰盒场景既可能是「预期失败（可接受） vs 不可接受」，也可能是「预期成功 vs 不可接受」。在用例模板与 UI 中固定展示 **Expected Outcome**（预期结果：可成功或可接受失败）与 **Unacceptable Outcomes**，由分析/AI 按场景填写，不写死一句「通过条件」。

### P2：功能扩展（可选）

6. **与覆盖率北向数据联动**  
   - 已有北向接口；在展示或排序时：若某条发现对应的 file/symbol/line 已被覆盖，可标记「已覆盖」或降权，优先展示未覆盖的交汇临界点。
7. **优先级/排序**  
   - 按 risk_score、related_functions 数量、是否在关键路径等做排序或标签，便于「先做哪几条」；可与 coverage 结合做「高价值未覆盖」列表。
8. **回归与可重复执行**  
   - 导出用例时提供「可复制」的步骤与预期，便于加入回归套件；若未来支持脚本/自动化，可考虑「自包含」的用例格式（如含环境假设与启停说明）。

### P3：中长期

9. **反馈闭环**  
   - 若有执行结果或覆盖率回传，可根据「是否覆盖该发现」「是否触发不可接受结果」调整发现权重或推荐顺序。  
10. **领域专用**  
    - 类似 GrayC 的领域变异：针对存储/控制面场景，预置更多「故障类型」与「注入点」模板，便于生成更贴业务的用例。

---

## 五、已拍板与实施说明

1. **优先级**：**全部做**（P0～P3）。  
2. **导出形态（推荐）**：以**测试人员易用性**为准，采用 **单文件导出 + 醒目「多函数交汇临界点」区块**：JSON/CSV/Markdown 均在**同一文件内**先列出「多函数交汇临界点」再列按发现生成的用例，测试人员一份文件即可看到重点与全量；另提供 **fmt=critical** 仅导出交汇临界点（便于快速粘贴到测试管理系统）。  
3. **Web 报告**：**两者兼顾**——前端任务详情/导出区增加「导出预览」式单页汇总（易用性优先）；同时支持 **fmt=html** 下载独立 **index.html** 报告，便于分享与归档。  
4. **Oracle**：**不**加单一固定句。多函数交汇既有「预期失败（可接受） vs 不可接受」，也有「预期成功 vs 不可接受」。统一用 **Expected Outcome**（预期结果：可成功或可接受失败）+ **Unacceptable Outcomes**，由分析器/AI 按场景填写。  
5. **目标系统**：当前项目**仅做 C/C++ 存储系统**，不扩展 REST/多语言；领域专用（P3）针对存储/控制面。

---

## 六、实施状态

- P0：导出中 critical_combinations 一等公民 + 建议步骤与 fault_window → 已实现/进行中  
- P1：统一字段与 expected_outcome、Web/HTML 报告 → 已实现/进行中  
- P2：覆盖率联动、优先级排序、回归友好导出 → 已实现/进行中  
- P3：**反馈闭环**：若有执行结果或覆盖率回传，可根据「是否覆盖该发现」「是否触发不可接受结果」调整发现权重或推荐顺序（当前覆盖率北向已支持导入，导出中已标「已覆盖」）。**领域专用**：针对 C/C++ 存储系统，预置更多「故障类型」与「注入点」模板（如端口闪断、网卡下电、IO 失败注入），便于生成更贴业务的用例；见各分析器 `_risk_type_to_fault_window` 与提示词模板。

---

## 七、继续调研（第二轮）

### 7.1 灰盒四合一定义与十步法（Cleanscape / Lockheed Martin）

- **灰盒 = 黑盒 + 白盒 + 回归 + 变异**（Coulter99）。同一用例可同时验证功能、结构（覆盖）与性能（时序）。
- **十步法**：识别输入 → 识别输出 → 识别主要路径 → 对每个子功能：设计输入/输出、执行用例、验证结果 → 对其它子功能重复 → 回归中再执行 7&8。
- **实时扩展**：在预期结果上增加**时间维度**（Object Level Timing）；用仿真生成带时间戳的预期数据，在目标系统上采集时间戳输出并比对，从而在**同一用例格式**下验证性能/时序需求。
- **与 GrayScope 的对应**：我们的「主要路径」= critical_combinations + 各分析器的路径/分支；子功能 = 按 symbol/发现；输入/输出/步骤/预期 = 导出中的 test_steps、expected_result、expected_outcome；回归 = 导出说明「可复制加入回归套件」。可选增加**性能/时序要求**字段，便于存储与实时场景。

### 7.2 测试充分性与 Oracle 缺口

- **充分性准则**：测试集是否「足够好」由**覆盖域**衡量——白盒为程序结构（控制流/数据流），黑盒为需求。满足覆盖域内所有元素即称充分。
- **Oracle 缺口（Oracle Gap）**：**覆盖率与变异分数之差**。高覆盖率并不代表断言/预言足够强；变异测试更能反映「能否发现注入缺陷」，用于识别「被执行但预言薄弱」的代码，指导补强断言。
- **Mu2**：用变异测试引导灰盒 fuzzing，生成高变异分数的回归用例，而非仅追求覆盖率。
- **对 GrayScope**：当前以静态发现与覆盖率北向为主；后续若有执行/变异反馈，可引入「预言强度」或 adequacy_notes；文档中明确：我们的导出可作为**静态目标**，供动态/concolic 或变异测试使用。

### 7.3 静态引导动态与 Concolic

- **静态引导动态测试生成**：用静态分析识别**目标**（脆弱点、关键路径），再用动态/符号执行生成到达目标的测试输入，缓解状态空间爆炸。
- **Concolic**：结合具体执行与符号执行，沿路径收集约束、取反分支以探索新路径，用求解器生成新输入；对 C 中难以求解的运算可用具体值替代。
- **LLM + 静态**：用静态分析提供**精简上下文**（签名、CFG、关键路径）给 LLM，生成更精准的测试代码或用例描述。
- **对 GrayScope**：我们的**发现、交汇临界点、fault_window、target_file/symbol/line** 即「静态目标」；可在导出或文档中说明：上述输出可用于驱动 concolic/符号执行或外部 fuzzer 的种子与目标列表。

### 7.4 C/C++ 嵌入式与存储相关

- **AUTS（2024）**：C/C++ 嵌入式项目的自动化测试数据与桩生成，concolic、多路径策略、自动桩，适用于不完整源码。
- **IPEA**：In-Vivo 探针 + Ex-Vivo 分析，设备侧轻量采集、工作站侧重分析；灰盒 fuzzer + sanitizer，降低内存开销。
- **嵌入式测试库**：针对无文件系统/标准输出的环境，测试中断与硬件相关代码；GrayScope 的 execution_hint、fault_window 可与「在什么时机注入、在什么环境执行」对齐。
- **存储/实时**：性能要求可写为定量、可观测（如「在事件 X 后 T ms 内完成」）；用例中可选**性能/时序要求**字段便于后续对接仿真或时间戳比对。

---

## 八、第二轮迭代（基于继续调研）

1. **文档**  
   - 在 GRAYBOX_ANALYSIS 或本文档中补充：灰盒十步法与 GrayScope 步骤映射；测试充分性与 Oracle 缺口简述；**静态输出可引导动态/concolic/fuzzer** 的用法说明（导出中的目标与路径可作为下游工具的输入）。
2. **可选字段：performance_requirement**  
   - 为用例与多函数交汇临界点增加可选 **performance_requirement**（如「响应时间 &lt; 100ms」「IO 延迟 &lt; 5ms」），便于存储/实时场景在导出或测试管理中填写；分析器/AI 可在 evidence 或 critical_combination 中产出，导出 JSON/CSV/Markdown 时带空字符串占位或实际值。
3. **模板与 API**  
   - 灰盒用例模板与聚合 API 的测试用例结构支持可选 **performance_requirement**，与「预期结果」「不可接受结果」并列，不写死为必填。

4. **静态输出引导动态/Concolic**  
   - 在导出或使用说明中注明：导出的 **target_file / target_function / line_start** 及 **critical_combinations** 中的路径与函数列表，可作为下游**动态测试**、**Concolic 执行**或 **Fuzzer** 的目标与种子输入，实现「静态引导动态」的闭环。

### 8.1 灰盒十步法检查清单（与 GrayScope 对应）

| 十步法步骤 | GrayScope 对应 |
|------------|----------------|
| 1. 识别输入 | 导出的 example_input、test_steps 中的输入描述；target/revision 限定范围 |
| 2. 识别输出 | expected_result、expected_outcome、unacceptable_outcomes |
| 3. 识别主要路径 | critical_combinations、各分析器 path_type / 调用链 |
| 4–8. 按子功能设计/执行/验证 | 按 finding（symbol/文件）生成的用例；fault_window、execution_hint |
| 9. 其它子功能重复 | 多模块 findings 合并；按 risk_score/related_functions 排序 |
| 10. 回归再执行 7&8 | 导出说明「可复制加入回归套件」；covered 标记与覆盖率北向 |
| （可选）性能/时序 | performance_requirement 字段；存储/实时场景可填「响应时间 &lt; Xms」 |

---

## 九、第三轮调研：底层分析逻辑重构（以多函数交互为锚点）

本节基于前两轮调研与对当前实现的最新梳理，**不囿于「九大模块」**，以**底层分析逻辑的优化与深化**为主线，对分析层进行推翻、合并与重构建议。**唯一不动摇的核心**：**多函数交互（交汇临界点）**——灰盒价值在于用少量精准用例暴露多函数/多分支在同一场景下的不可接受结果，其余均可围绕此目标重组。

### 9.1 原则

- **多函数交互**：保留并加强。包括 (1) 发现中的 **related_functions**（谁参与这条风险链）；(2) 跨模块产出的 **critical_combinations**（多函数交汇临界点）；(3) 预期失败 vs 不可接受结果的灰盒三要素。
- **其他**：九大功能、模块边界、编排顺序、发现形态均可**推翻、合并、重构**，以「是否服务于多函数交汇」与「分析深度」为评判标准。

### 9.2 现状诊断

| 维度 | 现状 |
|------|------|
| **原生产出 related_functions 的分析器** | **error_path**（cross_function_resource_leak）、**concurrency**（cross_function_race、cross_function_deadlock_risk）、**data_flow**（propagation_chain）、**diff_impact**（impacted_callers/callees）。这四类在 evidence 中显式写出关联函数。 |
| **依赖导出层推导 related_functions** | **branch_path**、**boundary_value**、**call_graph** 的发现本身多为单符号；导出时 `_get_related_functions()` 从 evidence 的 callers/callees 或 data_flow 的 propagation_chain 推导，属于「事后补全」而非分析器内建的多函数视角。 |
| **critical_combinations 来源** | 目前**仅由跨模块 AI**（synthesize_cross_module）产出，无基于调用图/发现图的**静态交汇计算**，可追溯性与确定性不足。 |
| **编排与数量** | 已通过 max_findings_per_module、branch_path_reduce 控量；模块间通过 upstream 传递 call_graph/data_flow 等，但「多函数」视角仍集中在少数分析器与 AI 综合。 |

结论：**真正支撑多函数交汇的底层能力**来自 (1) 调用图与数据流基础设施；(2) 在**调用链/传播链/并发访问/变更影响**上显式建模的分析器；(3) 将「发现对」或「路径交汇」显式计算的步骤（当前缺失）。单函数维度的分支/边界/错误路径分析可合并或降为「结构子层」，避免与「交汇」并列成同等权重模块。

### 9.3 分层重构建议

#### 第一层：结构基础（Infrastructure + 路径与资源）

- **call_graph**  
  - **定位**：纯基础设施，产出 **call_graph.json** 供下游使用；节点、边、callers/callees、call_sites。  
  - **建议**：**不再产出** high_fan_out / deep_impact_surface 等「发现」（或迁至单独的「影响面」视图），避免与 diff_impact、data_flow 的「影响/传播」重复，并减少与多函数交汇无关的噪音。

- **branch_path + error_path → 合并为「路径与资源」分析器（path_and_resource 或保留双名内部统一流水线）**  
  - **理由**：二者均基于 CFG/控制流；branch_path 做分支分类（error/cleanup/boundary/state），error_path 做资源分配/释放、错误返回、**跨函数资源泄漏**。合并后可：  
    - 一次遍历 CFG 同时产出「未覆盖错误/清理路径」「缺失清理」「错误码不一致」「静默吞错」与「跨函数资源泄漏」；  
    - **related_functions** 仅在跨函数资源泄漏等真正多函数处写入，其余为单函数路径发现；  
  - 对外可仍暴露为两个模块 ID（兼容）或统一为一个「路径与资源」模块，编排上视为同一阶段。

#### 第二层：跨函数风险（核心分析）

- **data_flow**  
  - **保留并深化**：跨函数参数传播、外部输入→敏感操作、值域变换风险已直接贡献 related_functions（propagation_chain）。  
  - **深化方向**：  
    - 与 **call_graph** 结合，标注传播链上的**调用点**（call site）而不仅是函数名；  
    - 与 **路径条件**（来自合并后的 path 分析）结合，区分「在何种分支条件下」该传播可达，便于生成更精准的用例与交汇描述。

- **concurrency**  
  - **保留**：已原生产出跨函数竞态、跨函数死锁风险，related_functions 明确。  
  - **可选深化**：若有解析能力，补充线程拓扑（谁创建线程、哪些函数在何线程中执行），使交汇描述更具体。

- **diff_impact**  
  - **保留**：依赖 call_graph，产出变更函数与 impacted_callers/callees，天然多函数。  
  - 与 call_graph 的职责划分：call_graph 只提供图；diff_impact 只做「变更 + 影响传播」，不重复「高扇出/深影响面」类发现。

- **boundary_value**  
  - **方案 A（推荐）**：**并入 data_flow**，作为「数据流 + 约束」子能力。边界本质是「值从哪来（传播）+ 在何处被约束（比较/数组访问）」；合并后 data_flow 同时产出 propagation_chain 与 boundary_miss / invalid_input_gap 类发现，related_functions 统一从传播链来。  
  - **方案 B**：保留独立模块，但**仅产出与约束/边界相关的发现**，related_functions 由导出层从 data_flow 的 propagation_chain 按 symbol 关联补全，不单独维护一套边界「模块权重」。

#### 第三层：叠加与反馈

- **coverage_map**  
  - **保留**：作为发现与覆盖率北向的叠加层，标记高风险低覆盖、关键路径未覆盖等，不改变底层分析逻辑。

- **postmortem / knowledge_pattern**  
  - **保留**：反馈闭环与知识沉淀，依赖缺陷元数据与上游发现，不参与「九大」结构重组。

### 9.4 交汇临界点的静态化（关键新增）

- **问题**：当前 critical_combinations 完全由 AI 从各模块发现文本中「归纳」，无基于图结构的确定性步骤。  
- **建议**：增加 **静态交汇步骤**（在跨模块 AI 之前或与之并行）：  
  1. 输入：call_graph 产物 + 所有模块的 findings（含 symbol_name、evidence.callers/callees、evidence.related_functions、evidence.propagation_chain 等）。  
  2. 计算：  
     - 同一函数上的多条发现 → 该函数为交汇点；  
     - 同一条调用链上的发现 → 链上函数集为候选交汇；  
     - 同一 propagation_chain 上的发现 → 链为候选交汇；  
     - 已有 related_functions 的发现 → 直接加入候选。  
  3. 输出：**候选 critical_combinations**（related_functions、涉及 finding_id 列表、可选 scenario_brief 占位）。  
  4. AI 角色：对候选进行**排序、合并、补全预期失败/不可接受结果与自然语言描述**，而非从零发明。  
- 这样「多函数交汇」先有**可追溯的图源与发现源**，再有人工智能增强，符合灰盒可解释性。

### 9.5 模块视图的收敛（对外不必再强调「九大」）

- **结构层**：call_graph（仅基础设施），path_and_resource（branch_path + error_path 合并）。  
- **跨函数风险层**：data_flow（可选合并 boundary_value），concurrency，diff_impact。  
- **叠加层**：coverage_map。  
- **反馈层**：postmortem，knowledge_pattern。  

对外可表述为「**以多函数交汇为核心的分析管线**」：结构 → 跨函数风险 → 静态交汇候选 → AI 综合 → 用例与导出；模块数量与命名可按实现阶段逐步迁移，无需一步到位。

### 9.6 实施优先级建议

| 优先级 | 内容 |
|--------|------|
| P0 | **静态交汇步骤**：在编排器中增加「从 call_graph + findings 生成候选 critical_combinations」的步骤，AI 仅做排序与补全。 |
| P1 | **call_graph 发现裁剪**：high_fan_out / deep_impact_surface 改为可选或移除，或迁至「影响面」聚合视图，减少噪音。 |
| P2 | **path_and_resource 合并**：将 branch_path 与 error_path 合并为单一分析流水线（内部可仍保留两个 module_id 兼容），统一 CFG 与资源/错误路径分析。 |
| P3 | **data_flow 深化**：传播链与 call_graph 调用点、路径条件结合；boundary_value 并入 data_flow（方案 A）或明确其仅产出约束发现并由 data_flow 补全 related_functions（方案 B）。 |

以上为基于底层分析逻辑的持续调研与迭代方向，**多函数交互**为唯一不变锚点，其余均可围绕其推翻、合并与重构。
