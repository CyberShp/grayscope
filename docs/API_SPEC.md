# GrayScope API 规范（V1）

## 1. 约定

- **基础路径**：`/api/v1`
- **内容类型**：`application/json`
- **时间格式**：ISO-8601 UTC 字符串
- **认证**：当前阶段无（仅内网）
- **幂等性**：创建任务时可通过 `idempotency_key` 支持幂等

### 1.1 标准响应信封

```json
{
  "code": "OK",
  "message": "success",
  "data": {}
}
```

### 1.2 错误信封

```json
{
  "code": "TASK_NOT_FOUND",
  "message": "分析任务 tsk_xxx 未找到",
  "data": {
    "request_id": "req_xxx"
  }
}
```

### 1.3 错误码（规范）

- `OK`
- `INVALID_REQUEST`
- `NOT_FOUND`
- `REPO_SYNC_FAILED`
- `TASK_NOT_FOUND`
- `TASK_STATE_INVALID`
- `ANALYZER_FAILED`
- `MODEL_PROVIDER_UNAVAILABLE`
- `MODEL_RESPONSE_INVALID`
- `EXPORT_FAILED`
- `INTERNAL_ERROR`

---

## 2. 健康检查

### GET `/api/v1/health`

**响应 200：**

```json
{
  "code": "OK",
  "message": "success",
  "data": {
    "service": "grayscope-backend",
    "status": "ok"
  }
}
```

---

## 3. 项目管理

### POST `/api/v1/projects` — 创建项目

**请求体：**

```json
{
  "name": "storage-core",
  "description": "核心存储测试项目"
}
```

**校验：**

- `name`：必填，长度 1～64，全局唯一
- `description`：可选，长度 ≤ 512

**响应 201：**

```json
{
  "code": "OK",
  "message": "success",
  "data": {
    "project_id": 1,
    "name": "storage-core",
    "description": "核心存储测试项目",
    "created_at": "2026-02-11T10:00:00Z"
  }
}
```

### GET `/api/v1/projects` — 项目列表

**查询参数：**

- `page`：默认 `1`
- `page_size`：默认 `20`，最大 `100`

**响应 200：**

```json
{
  "code": "OK",
  "message": "success",
  "data": {
    "items": [
      {
        "project_id": 1,
        "name": "storage-core",
        "description": "核心存储测试项目",
        "created_at": "2026-02-11T10:00:00Z"
      }
    ],
    "page": 1,
    "page_size": 20,
    "total": 1
  }
}
```

---

## 4. 仓库管理

### POST `/api/v1/projects/{project_id}/repos` — 创建仓库（绑定到项目）

**路径参数：** `project_id`（项目 ID）

**请求体：**

```json
{
  "name": "storage-engine",
  "git_url": "ssh://git.internal/storage/engine.git",
  "default_branch": "main",
  "local_mirror_path": "/data/grayscope/repos/storage-engine"
}
```

**校验：**

- `name`：必填，1～128
- `git_url`：必填，支持 ssh/http(s) 内网地址
- `default_branch`：必填
- `local_mirror_path`：可选；不填时由系统生成

**响应 201：**

```json
{
  "code": "OK",
  "message": "success",
  "data": {
    "repo_id": 10,
    "project_id": 1,
    "name": "storage-engine",
    "git_url": "ssh://git.internal/storage/engine.git",
    "default_branch": "main",
    "last_sync_status": "never"
  }
}
```

### GET `/api/v1/repos` — 仓库列表

**查询参数：**

- `project_id`（必填）：按项目筛选
- `page`：默认 `1`
- `page_size`：默认 `20`，最大 `100`

**响应 200：**

```json
{
  "code": "OK",
  "message": "success",
  "data": {
    "items": [
      {
        "repo_id": 10,
        "project_id": 1,
        "name": "storage-engine",
        "git_url": "ssh://git.internal/storage/engine.git",
        "default_branch": "main",
        "last_sync_status": "never",
        "last_sync_at": null
      }
    ],
    "page": 1,
    "page_size": 20,
    "total": 1
  }
}
```

---

## 5. 分析任务

### POST `/api/v1/analysis/tasks` — 创建分析任务

**请求体：**

```json
{
  "idempotency_key": "9f6f2e1d-b4f8-4f4f-9801-8d2ec8d5e223",
  "project_id": 1,
  "repo_id": 10,
  "task_type": "full",
  "target": {
    "path": "src/storage/",
    "functions": []
  },
  "revision": {
    "branch": "main",
    "base_commit": null,
    "head_commit": null
  },
  "analyzers": [
    "branch_path",
    "boundary_value",
    "error_path",
    "call_graph",
    "concurrency",
    "diff_impact",
    "coverage_map",
    "postmortem",
    "knowledge_pattern"
  ],
  "ai": {
    "provider": "ollama",
    "model": "qwen2.5-coder",
    "prompt_profile": "default-v1"
  },
  "options": {
    "callgraph_depth": 2,
    "max_files": 500,
    "risk_threshold": 0.6
  }
}
```

**请求字段说明：**

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| idempotency_key | string | 否 | 幂等键，重复请求返回同一任务 |
| project_id | int | 是 | 项目 ID |
| repo_id | int | 是 | 仓库 ID |
| task_type | string | 是 | `full` \| `file` \| `function` \| `diff` \| `postmortem` |
| target | object | 是 | 分析范围：path、functions |
| revision | object | 是 | 分支/基准/头提交 |
| analyzers | string[] | 是 | 模块 ID 列表，见下表 |
| ai | object | 否 | AI 提供商与模型配置 |
| options | object | 否 | 分析选项 |

**支持的模块 ID（analyzers）：**

- `branch_path` — 分支路径分析
- `boundary_value` — 边界值分析
- `error_path` — 错误路径分析
- `call_graph` — 调用图构建
- `concurrency` — 并发风险分析
- `diff_impact` — 差异影响分析
- `coverage_map` — 覆盖率映射
- `postmortem` — 事后分析
- `knowledge_pattern` — 缺陷知识库

**校验规则：**

- `task_type` 取值如上
- `analyzers` 非空，且每个元素均在上述模块集合内
- `diff` 类型时 `revision.base_commit` 与 `revision.head_commit` 必填
- `options.risk_threshold` 在 `[0, 1]`

**响应 201：**

```json
{
  "code": "OK",
  "message": "任务已创建",
  "data": {
    "task_id": "tsk_20260211_001",
    "status": "pending",
    "created_at": "2026-02-11T10:10:00Z"
  }
}
```

### GET `/api/v1/analysis/tasks/{task_id}` — 任务状态

**路径参数：** `task_id`（任务外部 ID，如 `tsk_xxx`）

**响应 200：**

```json
{
  "code": "OK",
  "message": "success",
  "data": {
    "task_id": "tsk_20260211_001",
    "task_type": "full",
    "status": "running",
    "progress": {
      "total_modules": 7,
      "finished_modules": 3,
      "failed_modules": 0
    },
    "module_status": {
      "branch_path": "success",
      "boundary_value": "success",
      "error_path": "running",
      "call_graph": "pending",
      "concurrency": "pending",
      "diff_impact": "pending",
      "coverage_map": "pending"
    },
    "created_at": "2026-02-11T10:10:00Z",
    "updated_at": "2026-02-11T10:11:15Z"
  }
}
```

### GET `/api/v1/analysis/tasks/{task_id}/results` — 分析结果

**响应 200：**

```json
{
  "code": "OK",
  "message": "success",
  "data": {
    "task_id": "tsk_20260211_001",
    "status": "success",
    "aggregate_risk_score": 0.78,
    "modules": [
      {
        "module": "branch_path",
        "display_name": "分支路径分析",
        "status": "success",
        "risk_score": 0.82,
        "finding_count": 17,
        "artifact_paths": ["artifacts/tsk_20260211_001/branch_path/cfg.json"]
      }
    ]
  }
}
```

### GET `/api/v1/analysis/tasks/{task_id}/export` — 导出

**查询参数：**

- `fmt`：`json` \| `csv` \| `findings`（必填或默认 `json`）

**说明：**

- `fmt=json`：结构化测试用例建议，`Content-Type: application/json`，附件下载
- `fmt=csv`：测试用例表（CSV），可导入测试管理工具，`Content-Type: text/csv`
- `fmt=findings`：原始发现及 AI 增强数据，`Content-Type: application/json`

**响应 200：** 直接返回文件流，带 `Content-Disposition` 附件头。

### POST `/api/v1/analysis/tasks/{task_id}/retry` — 重试

**请求体：**

```json
{
  "modules": ["error_path"]
}
```

- `modules` 为空：重试所有失败模块
- 任务须处于 `failed`、`partial_failed` 或 `success`（用于手动重跑指定模块）

**响应 202：** 任务状态变为 `running`，返回当前任务状态。

### POST `/api/v1/analysis/tasks/{task_id}/cancel` — 取消

**响应 202：** 任务被取消。

---

## 6. 事后分析

### POST `/api/v1/postmortem` — 事后分析

**请求体：**

```json
{
  "project_id": 1,
  "repo_id": 10,
  "defect": {
    "title": "竞态导致元数据陈旧",
    "severity": "S1",
    "description": "故障切换下间歇性陈旧读",
    "related_commit": "abc123def",
    "module_path": "src/meta/"
  },
  "ai": {
    "provider": "custom_rest",
    "model": "distill-storage-v1"
  }
}
```

**响应 201：**

```json
{
  "code": "OK",
  "message": "事后分析已完成",
  "data": {
    "task_id": "tsk_20260211_090",
    "status": "success"
  }
}
```

---

## 7. 知识库

### GET `/api/v1/knowledge/patterns` — 知识库搜索

**查询参数：**

- `project_id`（必填）
- `risk_type`：可选，按风险类型筛选
- `keyword`：可选，按名称/键/风险类型子串搜索
- `page`、`page_size`：可选分页

**响应 200：**

```json
{
  "code": "OK",
  "message": "success",
  "data": {
    "project_id": 1,
    "total": 5,
    "patterns": [
      {
        "pattern_key": "meta_retry_epoch_gap",
        "name": "元数据重试与 epoch 间隙",
        "risk_type": "race_write_without_lock",
        "hit_count": 3,
        "created_at": "2026-02-11T09:00:00Z"
      }
    ]
  }
}
```

### POST `/api/v1/knowledge/match` — 知识库匹配

**查询参数：**

- `project_id`（必填）
- `task_id`（必填）：要匹配发现的任务 ID
- `threshold`：相似度阈值，默认 `0.4`，范围 `[0, 1]`

**响应 200：**

```json
{
  "code": "OK",
  "message": "success",
  "data": {
    "task_id": "tsk_20260211_001",
    "project_id": 1,
    "threshold": 0.4,
    "total_findings": 23,
    "total_matches": 5,
    "matches": [
      {
        "finding_id": "branch_path-F0001",
        "pattern_key": "meta_retry_epoch_gap",
        "similarity": 0.88,
        "recommended_template": "retry_failover_epoch_validation_v1"
      }
    ]
  }
}
```

---

## 8. 模块结果最小结构

每个分析模块结果需包含：

```json
{
  "module_id": "branch_path",
  "status": "success",
  "risk_score": 0.82,
  "findings": [],
  "metrics": {},
  "artifacts": []
}
```

---

## 9. 向后兼容规则

- 现有端点仅做加法（新增字段），不删不改已有字段语义
- 枚举值不重新定义用途
- 错误码 `code` 保持稳定
