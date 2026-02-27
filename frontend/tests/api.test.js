/**
 * API Layer Tests
 * 
 * Tests for the frontend API module:
 * - Request function behavior
 * - Response unwrapping
 * - Error handling
 * - All API method existence
 * - Export URL generation
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import api from '../src/api.js'

// Mock the global fetch
const mockFetch = vi.fn()
global.fetch = mockFetch

describe('API Module', () => {
  beforeEach(() => {
    mockFetch.mockClear()
  })

  // ═══════════════════════════════════════════════════════════════════
  // 1. REQUEST FUNCTION TESTS
  // ═══════════════════════════════════════════════════════════════════

  describe('request function behavior', () => {
    it('unwraps data from successful response', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        headers: new Headers({ 'content-type': 'application/json' }),
        json: async () => ({ code: 200, data: { id: 1, name: 'Test' }, message: 'ok' }),
      })

      const result = await api.health()
      
      expect(result).toEqual({ id: 1, name: 'Test' })
    })

    it('returns full response when data field is undefined', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        headers: new Headers({ 'content-type': 'application/json' }),
        json: async () => ({ status: 'healthy' }),
      })

      const result = await api.health()
      
      expect(result).toEqual({ status: 'healthy' })
    })

    it('throws Error on non-ok response', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: false,
        status: 404,
        statusText: 'Not Found',
        headers: new Headers({ 'content-type': 'application/json' }),
        json: async () => ({ detail: 'Resource not found' }),
      })

      await expect(api.getProject(999)).rejects.toThrow('Resource not found')
    })

    it('handles non-JSON response without crashing', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        headers: new Headers({ 'content-type': 'text/html' }),
        json: async () => { throw new Error('not json') },
      })

      const result = await api.health()
      
      expect(result).toEqual({})
    })

    it('extracts message from detail array', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: false,
        status: 422,
        statusText: 'Unprocessable Entity',
        headers: new Headers({ 'content-type': 'application/json' }),
        json: async () => ({
          detail: [
            { loc: ['body', 'name'], msg: 'field required' },
            { loc: ['body', 'path'], msg: 'invalid path' },
          ],
        }),
      })

      await expect(api.createProject({})).rejects.toThrow('field required; invalid path')
    })

    it('falls back to statusText when no message', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: false,
        status: 500,
        statusText: 'Internal Server Error',
        headers: new Headers({ 'content-type': 'application/json' }),
        json: async () => ({}),
      })

      await expect(api.health()).rejects.toThrow('Internal Server Error')
    })
  })

  // ═══════════════════════════════════════════════════════════════════
  // 2. API METHODS EXISTENCE
  // ═══════════════════════════════════════════════════════════════════

  describe('all API methods exist', () => {
    const expectedMethods = [
      // Health
      'health',
      // Projects
      'listProjects', 'createProject', 'getProject',
      'getProjectSummary', 'getProjectTrends', 'getProjectQualityGate',
      'getProjectMeasures', 'getProjectFindings', 'getProjectTasks',
      'getProjectFileTree', 'getFileSource',
      // Repos
      'listRepos', 'createRepo', 'uploadRepo', 'updateRepo', 'syncRepo',
      // Analysis Tasks
      'createTask', 'getTaskStatus', 'getTaskResults', 'updateTaskMr',
      'exportUrl', 'deleteTask', 'deletePreview', 'batchDeleteTasks',
      'generateSfmea', 'retryTask', 'cancelTask', 'getAllTasks',
      // Findings
      'getAllFindings',
      // Postmortem
      'createPostmortem',
      // Knowledge
      'searchPatterns', 'matchKnowledge',
      // AI Models
      'listModels', 'testModel',
      // Settings
      'getSettings', 'updateSettings',
      // Test Design
      'getProjectTestCases', 'generateProjectTestCases', 'getAllTestCases',
      'getTestCase', 'getTestCaseScript', 'updateTestCase', 'getTestCaseTemplate',
      'getFindingTestSuggestion',
      // Test Runs
      'createTestRun', 'listTestRuns', 'getTestRun', 'executeTestRun',
      'rerunTestRun', 'pauseTestRun', 'cancelTestRun', 'deleteTestRun',
      'getTestCaseExecutions',
      // Execution Environment
      'listEnvImages', 'pullEnvImage', 'loadEnvImage', 'listEnvContainers',
      'createEnvContainer', 'startEnvContainer', 'stopEnvContainer',
      'removeEnvContainer', 'getEnvContainer',
      // Code Analysis (New Pipeline)
      'startCodeAnalysis', 'getCodeAnalysisStatus', 'getCodeAnalysisResults',
      'getCodeAnalysisCallGraph', 'getCodeAnalysisRisks', 'getCodeAnalysisNarratives',
      'getCodeAnalysisFunctionDict', 'getCodeAnalysisRiskCards',
      'getCodeAnalysisWhatIf', 'getCodeAnalysisTestMatrix',
      'getCodeAnalysisProtocolSM', 'exportCodeAnalysis',
      'listCodeAnalyses', 'deleteCodeAnalysis',
    ]

    expectedMethods.forEach(method => {
      it(`has method: ${method}`, () => {
        expect(typeof api[method]).toBe('function')
      })
    })
  })

  // ═══════════════════════════════════════════════════════════════════
  // 3. EXPORT URL TESTS
  // ═══════════════════════════════════════════════════════════════════

  describe('export URL generation', () => {
    it('exportUrl returns correct string', () => {
      const url = api.exportUrl(123, 'csv')
      
      expect(url).toBe('/api/v1/analysis/tasks/123/export?fmt=csv')
    })

    it('exportUrl defaults to json format', () => {
      const url = api.exportUrl(456)
      
      expect(url).toBe('/api/v1/analysis/tasks/456/export?fmt=json')
    })

    it('exportCodeAnalysis returns correct string', () => {
      const url = api.exportCodeAnalysis('abc-123', 'csv')
      
      expect(url).toBe('/api/v1/code-analysis/abc-123/export?fmt=csv')
    })

    it('exportCodeAnalysis defaults to json format', () => {
      const url = api.exportCodeAnalysis('xyz-789')
      
      expect(url).toBe('/api/v1/code-analysis/xyz-789/export?fmt=json')
    })
  })

  // ═══════════════════════════════════════════════════════════════════
  // 4. SPECIFIC API CALL TESTS
  // ═══════════════════════════════════════════════════════════════════

  describe('specific API calls', () => {
    beforeEach(() => {
      mockFetch.mockResolvedValue({
        ok: true,
        headers: new Headers({ 'content-type': 'application/json' }),
        json: async () => ({ code: 200, data: {}, message: 'ok' }),
      })
    })

    it('health calls correct endpoint', async () => {
      await api.health()
      
      expect(mockFetch).toHaveBeenCalledWith(
        '/api/v1/health',
        expect.objectContaining({ method: 'GET' })
      )
    })

    it('listProjects calls correct endpoint', async () => {
      await api.listProjects()
      
      expect(mockFetch).toHaveBeenCalledWith(
        '/api/v1/projects',
        expect.objectContaining({ method: 'GET' })
      )
    })

    it('createProject sends body correctly', async () => {
      const body = { name: 'Test Project', description: 'A test' }
      await api.createProject(body)
      
      expect(mockFetch).toHaveBeenCalledWith(
        '/api/v1/projects',
        expect.objectContaining({
          method: 'POST',
          body: JSON.stringify(body),
        })
      )
    })

    it('getProject includes id in path', async () => {
      await api.getProject(42)
      
      expect(mockFetch).toHaveBeenCalledWith(
        '/api/v1/projects/42',
        expect.objectContaining({ method: 'GET' })
      )
    })

    it('getProjectFileTree adds source query param', async () => {
      await api.getProjectFileTree(1, 'repo')
      
      expect(mockFetch).toHaveBeenCalledWith(
        '/api/v1/projects/1/file-tree?source=repo',
        expect.any(Object)
      )
    })

    it('getProjectFileTree works without source', async () => {
      await api.getProjectFileTree(1)
      
      expect(mockFetch).toHaveBeenCalledWith(
        '/api/v1/projects/1/file-tree',
        expect.any(Object)
      )
    })

    it('syncRepo sends correct revision structure', async () => {
      await api.syncRepo(5, { branch: 'develop', tag: 'v1.0', commit: 'abc123' })
      
      expect(mockFetch).toHaveBeenCalledWith(
        '/api/v1/repos/5/sync',
        expect.objectContaining({
          method: 'POST',
          body: JSON.stringify({
            revision: { branch: 'develop', tag: 'v1.0', commit: 'abc123' },
            depth: 1,
          }),
        })
      )
    })

    it('getCodeAnalysisRisks adds filter params', async () => {
      await api.getCodeAnalysisRisks('abc', { severity: 'high', risk_type: 'deadlock' })
      
      expect(mockFetch).toHaveBeenCalledWith(
        '/api/v1/code-analysis/abc/risks?severity=high&risk_type=deadlock',
        expect.any(Object)
      )
    })

    it('startCodeAnalysis sends workspace_path', async () => {
      await api.startCodeAnalysis({ workspace_path: '/path/to/code' })
      
      expect(mockFetch).toHaveBeenCalledWith(
        '/api/v1/code-analysis/start',
        expect.objectContaining({
          method: 'POST',
          body: JSON.stringify({ workspace_path: '/path/to/code' }),
        })
      )
    })

    it('testModel sends provider config', async () => {
      const config = { provider: 'deepseek', api_key: 'key123' }
      await api.testModel(config)
      
      expect(mockFetch).toHaveBeenCalledWith(
        '/api/v1/models/test',
        expect.objectContaining({
          method: 'POST',
          body: JSON.stringify(config),
        })
      )
    })
  })

  // ═══════════════════════════════════════════════════════════════════
  // 5. UPLOAD FUNCTIONS (FormData)
  // ═══════════════════════════════════════════════════════════════════

  describe('upload functions', () => {
    it('uploadRepo sends FormData without JSON header', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => ({ code: 200, data: { id: 1 }, message: 'ok' }),
      })

      const file = new File(['content'], 'test.zip', { type: 'application/zip' })
      await api.uploadRepo(1, file, 'MyRepo')
      
      expect(mockFetch).toHaveBeenCalledWith(
        '/api/v1/projects/1/repos/upload?name=MyRepo',
        expect.objectContaining({ method: 'POST' })
      )
      
      const call = mockFetch.mock.calls[0]
      expect(call[1].body).toBeInstanceOf(FormData)
    })

    it('loadEnvImage sends FormData', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => ({ code: 200, data: {}, message: 'ok' }),
      })

      const file = new File(['content'], 'image.tar', { type: 'application/x-tar' })
      await api.loadEnvImage(file)
      
      expect(mockFetch).toHaveBeenCalledWith(
        '/api/v1/execution-env/images/load',
        expect.objectContaining({ method: 'POST' })
      )
      
      const call = mockFetch.mock.calls[0]
      expect(call[1].body).toBeInstanceOf(FormData)
    })
  })

  // ═══════════════════════════════════════════════════════════════════
  // 6. QUERY STRING CONSTRUCTION
  // ═══════════════════════════════════════════════════════════════════

  describe('query string construction', () => {
    beforeEach(() => {
      mockFetch.mockResolvedValue({
        ok: true,
        headers: new Headers({ 'content-type': 'application/json' }),
        json: async () => ({ code: 200, data: [], message: 'ok' }),
      })
    })

    it('getAllTasks builds query string from params', async () => {
      await api.getAllTasks({ status: 'completed', limit: 10 })
      
      expect(mockFetch).toHaveBeenCalledWith(
        '/api/v1/analysis/tasks?status=completed&limit=10',
        expect.any(Object)
      )
    })

    it('getAllFindings builds query string from params', async () => {
      await api.getAllFindings({ project_id: 1, severity: 'critical' })
      
      expect(mockFetch).toHaveBeenCalledWith(
        '/api/v1/findings?project_id=1&severity=critical',
        expect.any(Object)
      )
    })

    it('listCodeAnalyses builds query string from params', async () => {
      await api.listCodeAnalyses({ status: 'running', limit: 5 })
      
      expect(mockFetch).toHaveBeenCalledWith(
        '/api/v1/code-analysis?status=running&limit=5',
        expect.any(Object)
      )
    })

    it('getTestCaseScript adds format query param', async () => {
      await api.getTestCaseScript(42, 'python')
      
      expect(mockFetch).toHaveBeenCalledWith(
        '/api/v1/test-cases/42/script?format=python',
        expect.any(Object)
      )
    })
  })
})
