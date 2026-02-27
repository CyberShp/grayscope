const BASE = '/api/v1'

async function request(method, path, body = null) {
  const opts = {
    method,
    headers: { 'Content-Type': 'application/json' },
  }
  if (body) opts.body = JSON.stringify(body)
  const res = await fetch(`${BASE}${path}`, opts)
  let data
  const contentType = res.headers.get('content-type') || ''
  try {
    data = contentType.includes('application/json') ? await res.json() : {}
  } catch {
    data = { message: res.statusText || '网络错误', detail: '响应非 JSON' }
  }
  if (!res.ok) {
    const msg = data.detail || data.message || (Array.isArray(data.detail) ? data.detail.map(d => d.msg || d).join('; ') : res.statusText)
    throw new Error(msg)
  }
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
  getProjectFileTree: (projectId, source) => {
    const qs = source ? `?source=${encodeURIComponent(source)}` : ''
    return request('GET', `/projects/${projectId}/file-tree${qs}`)
  },
  getFileSource: (projectId, filePath) =>
    request('GET', `/projects/${projectId}/source?path=${encodeURIComponent(filePath)}`),

  // ── 仓库 ──────────────────────────────
  listRepos: (projectId) => request('GET', `/projects/${projectId}/repos`),
  createRepo: (projectId, body) => request('POST', `/projects/${projectId}/repos`, body),
  uploadRepo: async (projectId, file, name = null) => {
    const form = new FormData()
    form.append('file', file)
    const url = `${BASE}/projects/${projectId}/repos/upload${name ? `?name=${encodeURIComponent(name)}` : ''}`
    const res = await fetch(url, { method: 'POST', body: form })
    const data = await res.json()
    if (!res.ok) throw new Error(data.message || res.statusText)
    return data.data !== undefined ? data.data : data
  },
  updateRepo: (projectId, repoId, body) => request('PATCH', `/projects/${projectId}/repos/${repoId}`, body),
  syncRepo: (repoId, body = {}) => request('POST', `/repos/${repoId}/sync`, {
    revision: { branch: body.branch || 'main', tag: body.tag || null, commit: body.commit || null },
    depth: body.depth ?? 1,
  }),

  // ── 分析任务 ──────────────────────────
  createTask: (body) => request('POST', '/analysis/tasks', body),
  getTaskStatus: (taskId) => request('GET', `/analysis/tasks/${taskId}`),
  getTaskResults: (taskId) => request('GET', `/analysis/tasks/${taskId}/results`),
  updateTaskMr: (taskId, body) => request('PATCH', `/analysis/tasks/${taskId}/mr`, body),
  exportUrl: (taskId, fmt = 'json') => `${BASE}/analysis/tasks/${taskId}/export?fmt=${fmt}`,
  deleteTask: (taskId) => request('DELETE', `/analysis/tasks/${taskId}`),
  deletePreview: (taskIds) => request('POST', '/analysis/tasks/delete-preview', { task_ids: taskIds }),
  batchDeleteTasks: (taskIds) => request('POST', '/analysis/tasks/batch-delete', { task_ids: taskIds }),
  generateSfmea: (taskId) => request('POST', `/analysis/tasks/${taskId}/sfmea`, {}),
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
  generateProjectTestCases: (projectId) =>
    request('POST', `/projects/${projectId}/test-cases/generate`, {}),
  getAllTestCases: (params = {}) => {
    const qs = new URLSearchParams(params).toString()
    return request('GET', `/test-cases${qs ? '?' + qs : ''}`)
  },
  getTestCase: (id) => request('GET', `/test-cases/${id}`),
  getTestCaseScript: (id, format = 'cpp') => {
    const q = format ? `?format=${encodeURIComponent(format)}` : ''
    return request('GET', `/test-cases/${id}/script${q}`)
  },
  updateTestCase: (id, body) => request('PATCH', `/test-cases/${id}`, body),
  getTestCaseTemplate: () => request('GET', '/test-cases/template'),
  getFindingTestSuggestion: (findingId) =>
    request('GET', `/findings/${encodeURIComponent(findingId)}/test-suggestion`),

  // ── 测试执行 ──────────────────────────
  createTestRun: (body) => request('POST', '/test-runs', body),
  listTestRuns: (params = {}) => {
    const qs = new URLSearchParams(params).toString()
    return request('GET', `/test-runs${qs ? '?' + qs : ''}`)
  },
  getTestRun: (runId) => request('GET', `/test-runs/${runId}`),
  executeTestRun: (runId) => request('POST', `/test-runs/${runId}/execute`, {}),
  rerunTestRun: (runId) => request('POST', `/test-runs/${runId}/rerun`, {}),
  pauseTestRun: (runId) => request('POST', `/test-runs/${runId}/pause`, {}),
  cancelTestRun: (runId) => request('POST', `/test-runs/${runId}/cancel`, {}),
  deleteTestRun: (runId) => request('DELETE', `/test-runs/${runId}`),
  getTestCaseExecutions: (testCaseId) => request('GET', `/test-cases/${testCaseId}/executions`),

  // ── 执行环境（Docker 镜像/容器）────────────────────────────────────
  listEnvImages: () => request('GET', '/execution-env/images'),
  pullEnvImage: (image) => request('POST', '/execution-env/images/pull', { image }),
  loadEnvImage: async (file) => {
    const form = new FormData()
    form.append('file', file)
    const res = await fetch(`${BASE}/execution-env/images/load`, { method: 'POST', body: form })
    const data = await res.json()
    if (!res.ok) throw new Error(data.detail || data.message || res.statusText)
    return data.data !== undefined ? data.data : data
  },
  listEnvContainers: (all = true) => request('GET', `/execution-env/containers?all=${all}`),
  createEnvContainer: (body) => request('POST', '/execution-env/containers', body),
  startEnvContainer: (id) => request('POST', `/execution-env/containers/${id}/start`, {}),
  stopEnvContainer: (id) => request('POST', `/execution-env/containers/${id}/stop`, {}),
  removeEnvContainer: (id, force = false) => request('DELETE', `/execution-env/containers/${id}?force=${force}`),
  getEnvContainer: (id) => request('GET', `/execution-env/containers/${id}`),

  // ── 代码分析流水线（新） ──────────────
  startCodeAnalysis: (body) => request('POST', '/code-analysis/start', body),
  getCodeAnalysisStatus: (analysisId) => request('GET', `/code-analysis/${analysisId}/status`),
  getCodeAnalysisResults: (analysisId) => request('GET', `/code-analysis/${analysisId}/results`),
  getCodeAnalysisCallGraph: (analysisId) => request('GET', `/code-analysis/${analysisId}/call-graph`),
  getCodeAnalysisRisks: (analysisId, params = {}) => {
    const qs = new URLSearchParams(params).toString()
    return request('GET', `/code-analysis/${analysisId}/risks${qs ? '?' + qs : ''}`)
  },
  getCodeAnalysisNarratives: (analysisId) => request('GET', `/code-analysis/${analysisId}/narratives`),
  getCodeAnalysisFunctionDict: (analysisId) => request('GET', `/code-analysis/${analysisId}/function-dictionary`),
  getCodeAnalysisRiskCards: (analysisId) => request('GET', `/code-analysis/${analysisId}/risk-cards`),
  getCodeAnalysisWhatIf: (analysisId) => request('GET', `/code-analysis/${analysisId}/what-if`),
  getCodeAnalysisTestMatrix: (analysisId) => request('GET', `/code-analysis/${analysisId}/test-matrix`),
  getCodeAnalysisProtocolSM: (analysisId) => request('GET', `/code-analysis/${analysisId}/protocol-state-machine`),
  exportCodeAnalysis: (analysisId, fmt = 'json') => `${BASE}/code-analysis/${analysisId}/export?fmt=${fmt}`,
  listCodeAnalyses: (params = {}) => {
    const qs = new URLSearchParams(params).toString()
    return request('GET', `/code-analysis${qs ? '?' + qs : ''}`)
  },
  deleteCodeAnalysis: (analysisId) => request('DELETE', `/code-analysis/${analysisId}`),
}
