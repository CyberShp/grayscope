/**
 * App Store Tests
 * 
 * Tests for the main Pinia store:
 * - Initial state
 * - fetchProjects action
 * - checkHealth action
 * - getProjectById getter
 * - setCurrentProject action
 * - fetchSettings action
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useAppStore } from '../../src/stores/app.js'
import api from '../../src/api.js'

// Mock the API module
vi.mock('../../src/api.js', () => ({
  default: {
    listProjects: vi.fn(),
    getSettings: vi.fn(),
    health: vi.fn(),
  },
}))

describe('App Store', () => {
  let store

  beforeEach(() => {
    setActivePinia(createPinia())
    store = useAppStore()
    vi.clearAllMocks()
  })

  // ═══════════════════════════════════════════════════════════════════
  // 1. INITIAL STATE
  // ═══════════════════════════════════════════════════════════════════

  describe('initial state', () => {
    it('has correct default values', () => {
      expect(store.systemHealthy).toBe(true)
      expect(store.loading).toBe(false)
      expect(store.projects).toEqual([])
      expect(store.currentProject).toBeNull()
      expect(store.displayTimezone).toBe('Asia/Shanghai')
    })
  })

  // ═══════════════════════════════════════════════════════════════════
  // 2. FETCH PROJECTS
  // ═══════════════════════════════════════════════════════════════════

  describe('fetchProjects', () => {
    it('fetches and stores projects with .projects array', async () => {
      const mockProjects = [
        { id: 1, name: 'Project A' },
        { id: 2, name: 'Project B' },
      ]
      api.listProjects.mockResolvedValueOnce({ projects: mockProjects })

      await store.fetchProjects()

      expect(api.listProjects).toHaveBeenCalled()
      expect(store.projects).toEqual(mockProjects)
    })

    it('handles .items array format', async () => {
      const mockProjects = [{ id: 1, name: 'Project X' }]
      api.listProjects.mockResolvedValueOnce({ items: mockProjects })

      await store.fetchProjects()

      expect(store.projects).toEqual(mockProjects)
    })

    it('handles direct array response', async () => {
      const mockProjects = [{ id: 1, name: 'Direct' }]
      api.listProjects.mockResolvedValueOnce(mockProjects)

      await store.fetchProjects()

      expect(store.projects).toEqual(mockProjects)
    })

    it('sets empty array on error', async () => {
      api.listProjects.mockRejectedValueOnce(new Error('Network error'))

      await store.fetchProjects()

      expect(store.projects).toEqual([])
    })
  })

  // ═══════════════════════════════════════════════════════════════════
  // 3. CHECK HEALTH
  // ═══════════════════════════════════════════════════════════════════

  describe('checkHealth', () => {
    it('sets systemHealthy to true on success', async () => {
      store.systemHealthy = false
      api.health.mockResolvedValueOnce({ status: 'healthy' })

      await store.checkHealth()

      expect(api.health).toHaveBeenCalled()
      expect(store.systemHealthy).toBe(true)
    })

    it('sets systemHealthy to false on error', async () => {
      api.health.mockRejectedValueOnce(new Error('Server down'))

      await store.checkHealth()

      expect(store.systemHealthy).toBe(false)
    })
  })

  // ═══════════════════════════════════════════════════════════════════
  // 4. GET PROJECT BY ID
  // ═══════════════════════════════════════════════════════════════════

  describe('getProjectById', () => {
    it('finds project by id', () => {
      store.projects = [
        { id: 1, name: 'First' },
        { id: 2, name: 'Second' },
        { id: 3, name: 'Third' },
      ]

      const found = store.getProjectById(2)

      expect(found).toEqual({ id: 2, name: 'Second' })
    })

    it('finds project by string id', () => {
      store.projects = [
        { id: 1, name: 'First' },
        { id: 42, name: 'Found' },
      ]

      const found = store.getProjectById('42')

      expect(found).toEqual({ id: 42, name: 'Found' })
    })

    it('handles project_id field', () => {
      store.projects = [
        { project_id: 10, name: 'Legacy Format' },
      ]

      const found = store.getProjectById(10)

      expect(found).toEqual({ project_id: 10, name: 'Legacy Format' })
    })

    it('returns undefined for non-existent id', () => {
      store.projects = [{ id: 1, name: 'Only One' }]

      const found = store.getProjectById(999)

      expect(found).toBeUndefined()
    })
  })

  // ═══════════════════════════════════════════════════════════════════
  // 5. SET CURRENT PROJECT
  // ═══════════════════════════════════════════════════════════════════

  describe('setCurrentProject', () => {
    it('sets current project', () => {
      const project = { id: 5, name: 'Current' }

      store.setCurrentProject(project)

      expect(store.currentProject).toEqual(project)
    })

    it('can clear current project', () => {
      store.currentProject = { id: 1, name: 'Existing' }

      store.setCurrentProject(null)

      expect(store.currentProject).toBeNull()
    })
  })

  // ═══════════════════════════════════════════════════════════════════
  // 6. FETCH SETTINGS
  // ═══════════════════════════════════════════════════════════════════

  describe('fetchSettings', () => {
    it('fetches and stores display timezone', async () => {
      api.getSettings.mockResolvedValueOnce({
        system: { display_timezone: 'America/New_York' },
      })

      await store.fetchSettings()

      expect(api.getSettings).toHaveBeenCalled()
      expect(store.displayTimezone).toBe('America/New_York')
    })

    it('keeps default timezone on missing data', async () => {
      api.getSettings.mockResolvedValueOnce({})

      await store.fetchSettings()

      expect(store.displayTimezone).toBe('Asia/Shanghai')
    })

    it('only fetches once (caching)', async () => {
      api.getSettings.mockResolvedValueOnce({
        system: { display_timezone: 'UTC' },
      })

      await store.fetchSettings()
      await store.fetchSettings()
      await store.fetchSettings()

      expect(api.getSettings).toHaveBeenCalledTimes(1)
    })

    it('keeps default timezone on error', async () => {
      api.getSettings.mockRejectedValueOnce(new Error('Failed'))

      await store.fetchSettings()

      expect(store.displayTimezone).toBe('Asia/Shanghai')
    })
  })
})
