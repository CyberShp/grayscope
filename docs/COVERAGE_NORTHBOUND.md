# 覆盖率北向接口设计

## 1. 背景与目标

- **需求**：内网已有覆盖率系统，能统计「哪些黑盒测试用例覆盖了哪些代码分支」。该数据涉密，无法直接给 GrayScope；需要由外部系统**主动推送**到 GrayScope。
- **目标**：提供**北向接口**（API + 数据格式），让内网覆盖率系统（或其它数据源）把「已覆盖的路径/分支/函数」写入 GrayScope；GrayScope 据此做：
  - 与风险发现叠加（coverage_map）：标记「高风险低覆盖」、过滤已覆盖发现等；
  - 统计：如「已覆盖分支占比」「哪些用例覆盖了该分支」（若上游提供用例–分支映射）。

## 2. 接口约定

### 2.1 写入覆盖率数据

**POST** `/api/v1/analysis/tasks/{task_id}/coverage`

- **路径参数**：`task_id` — 已存在的分析任务 ID（逻辑 ID，如 UUID）。
- **请求体**：JSON，见下文「数据格式」。
- **响应**：
  - 200：成功，返回 `{ "code": "OK", "data": { "import_id": 1, "task_id": "...", "format": "summary", "source_system": "..." } }`。
  - 404：任务不存在。
  - 400：body 格式错误或校验失败。

**说明**：同一任务可多次推送；每次覆盖该任务当前使用的「最新一次导入」。coverage_map 分析时使用该任务**最近一次**成功导入的覆盖率数据（与 `coverage_path` 文件合并，若存在）。

### 2.2 查询已导入的覆盖率元数据（可选）

**GET** `/api/v1/analysis/tasks/{task_id}/coverage`

- **响应 200**：`{ "code": "OK", "data": { "latest": { "import_id", "source_system", "revision", "format", "created_at" } | null, "has_data": true|false } }`  
  若无导入记录则 `latest` 为 null、`has_data` 为 false。

## 3. 数据格式

请求体根字段：

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| source_system | string | 否 | 来源系统标识，如 "internal_coverage_platform" |
| revision | string | 否 | 版本/构建标识，如 commit、build_id |
| format | string | 是 | `summary` 或 `granular` |
| (format 对应 payload) | object | 是 | 见下 |

### 3.1 format: summary（文件级汇总）

与当前 LCOV/JSON 文件语义一致，便于现有覆盖率系统直接生成。用于 coverage_map 与风险叠加。

```json
{
  "source_system": "internal_coverage_platform",
  "revision": "abc123",
  "format": "summary",
  "files": {
    "src/storage/volume.c": {
      "lines_total": 100,
      "lines_hit": 65,
      "branches_total": 20,
      "branches_hit": 12,
      "functions": {
        "open_volume": true,
        "close_volume": false
      }
    }
  }
}
```

- `files`: 键为文件路径（相对仓库根或绝对，与 GrayScope 分析目标中的 path 可匹配即可）。
- 每个文件：`lines_total` / `lines_hit`、`branches_total` / `branches_hit`、`functions`（函数名 → 是否被覆盖）。

### 3.2 format: granular（细粒度：分支/行 + 可选用例映射）

用于「哪些黑盒测试用例覆盖了该分支」的统计与后续分析。外部系统可按自身能力提供「覆盖项」列表，以及可选的「用例 → 覆盖项」映射。

**covered** — 全局已覆盖项列表（不去重也可，存储时按需聚合）：

```json
{
  "source_system": "internal_coverage_platform",
  "revision": "abc123",
  "format": "granular",
  "covered": [
    { "file": "src/storage/volume.c", "symbol": "open_volume", "line": 45, "branch_id": "b0" },
    { "file": "src/storage/volume.c", "symbol": "open_volume", "line": 50 }
  ],
  "tests": [
    {
      "test_id": "T001",
      "name": "test_open_normal",
      "covered": [
        { "file": "src/storage/volume.c", "symbol": "open_volume", "line": 45, "branch_id": "b0" }
      ]
    }
  ]
}
```

- **covered**：数组，每项可选字段：`file`（必填）、`symbol`、`line`、`branch_id`。表示该文件/函数/行/分支已被至少一个用例覆盖。
- **tests**（可选）：数组，每项 `test_id`、`name`（可选）、`covered`：该用例覆盖的项列表。GrayScope 可据此统计「该分支被哪些 test_id 覆盖」。

**使用方式**：  
- 存储时原样落库（如 JSON）。  
- coverage_map 使用前，将 granular 聚合成文件级汇总（按 file 聚合 lines_hit、branches 等），再与 `summary` 或 `coverage_path` 一致参与叠加。  
- 后续可在前端/导出中展示「该发现已被用例 T001、T003 覆盖」等（需与 risk_findings 做匹配规则，见实现）。

## 4. 与 coverage_map 的配合

- **数据源优先级**（在 coverage_map 分析时）：  
  1. 该任务**最近一次**通过北向接口导入的覆盖率（summary 或 granular 聚合结果）；  
  2. 若任务 options 中配置了 `coverage_path` 且文件存在，则与 1 合并（如按文件 merge，以导入数据为主或按策略合并）。  
- **无北向数据且无 coverage_path**：行为与现有一致（仅基于上游风险给出「建议运行插桩」等）。

## 5. 安全与实现注意

- 北向接口当前无鉴权，依赖内网与部署边界。  
- 请求体大小可做上限（如 5MB），避免误传超大 payload。  
- 存储：建议独立表 `coverage_imports`（task_id, source_system, revision, format, payload_json, created_at），按 task_id 查询「最新一条」即可；无需保留全量历史（若需可再扩展）。

---

**变更记录**

- 初版：北向接口约定、summary/granular 双格式、与 coverage_map 的配合方式。
