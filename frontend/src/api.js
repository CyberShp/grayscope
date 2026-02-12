const BASE = '/api/v1'

async function request(method, path, body = null) {
  const opts = {
    method,
    headers: { 'Content-Type': 'application/json' },
  }
  if (body) opts.body = JSON.stringify(body)
  const res = await fetch(`${BASE}${path}`, opts)
  const data = await res.json()
  if (!res.ok) throw new Error(data.message || res.statusText)
  return data.data !== undefined ? data.data : data
}

export default {
  // ── 健康检查 ──────────────────────────
  health: () => request('GET', '/health'),

  // ── 项目 ──────────────────────────────
  listProjects: () => request('GET', '/projects'),
  createProject: (body) => request('POST', '/projects', body),
  getProject: (id) => request('GET', `/projects/${id}`),

  // 项目聚合数据（新增 API）
  getProjectSummary: (projectId) => request('GET', `/projects/${projectId}/summary`),
  getProjectTrends: (projectId) => request('GET', `/projects/${projectId}/trends`),
  getProjectQualityGate: (projectId) => request('GET', `/projects/${projectId}/quality-gate`),
  getProjectMeasures: (projectId) => request('GET', `/projects/${projectId}/measures`),
  getProjectFindings: (projectId) => request('GET', `/projects/${projectId}/findings`),
  getProjectTasks: (projectId) => request('GET', `/projects/${projectId}/tasks`),
  getProjectFileTree: (projectId) => request('GET', `/projects/${projectId}/file-tree`),
  getFileSource: (projectId, filePath) =>
    request('GET', `/projects/${projectId}/source?path=${encodeURIComponent(filePath)}`),

  // ── 仓库 ──────────────────────────────
  listRepos: (projectId) => request('GET', `/projects/${projectId}/repos`),
  createRepo: (projectId, body) => request('POST', `/projects/${projectId}/repos`, body),
  syncRepo: (repoId, body = {}) => request('POST', `/repos/${repoId}/sync`, {
    revision: { branch: body.branch || 'main', tag: body.tag || null, commit: body.commit || null },
    depth: body.depth ?? 1,
  }),

  // ── 分析任务 ──────────────────────────
  createTask: (body) => request('POST', '/analysis/tasks', body),
  getTaskStatus: (taskId) => request('GET', `/analysis/tasks/${taskId}`),
  getTaskResults: (taskId) => request('GET', `/analysis/tasks/${taskId}/results`),
  exportUrl: (taskId, fmt = 'json') => `${BASE}/analysis/tasks/${taskId}/export?fmt=${fmt}`,
  retryTask: (taskId, body) => request('POST', `/analysis/tasks/${taskId}/retry`, body),
  cancelTask: (taskId) => request('POST', `/analysis/tasks/${taskId}/cancel`, {}),

  // 全局任务列表（新增 API）
  getAllTasks: (params = {}) => {
    const qs = new URLSearchParams(params).toString()
    return request('GET', `/analysis/tasks${qs ? '?' + qs : ''}`)
  },

  // ── 全局发现（新增 API）──────────────
  getAllFindings: (params = {}) => {
    const qs = new URLSearchParams(params).toString()
    return request('GET', `/findings${qs ? '?' + qs : ''}`)
  },

  // ── 事后分析 ──────────────────────────
  createPostmortem: (body) => request('POST', '/postmortem', body),

  // ── 知识库 ──────────────────────────
  searchPatterns: (projectId, keyword = '', riskType = '') =>
    request('GET', `/knowledge/patterns?project_id=${projectId}&keyword=${keyword}&risk_type=${riskType}`),
  matchKnowledge: (projectId, taskId, threshold = 0.4) =>
    request('POST', `/knowledge/match?project_id=${projectId}&task_id=${taskId}&threshold=${threshold}`, {}),

  // ── AI 模型 ──────────────────────────
  listModels: () => request('GET', '/models'),
  testModel: (body) => request('POST', '/models/test', body),

  // ── 设置 ────────────────────────────
  getSettings: () => request('GET', '/settings'),
  updateSettings: (body) => request('PUT', '/settings', body),

  // ── 测试设计 ──────────────────────────
  getProjectTestCases: (projectId, params = {}) => {
    const qs = new URLSearchParams(params).toString()
    return request('GET', `/projects/${projectId}/test-cases${qs ? '?' + qs : ''}`)
  },
  getAllTestCases: (params = {}) => {
    const qs = new URLSearchParams(params).toString()
    return request('GET', `/test-cases${qs ? '?' + qs : ''}`)
  },
  getFindingTestSuggestion: (findingId) =>
    request('GET', `/findings/${encodeURIComponent(findingId)}/test-suggestion`),
}
