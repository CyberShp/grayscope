/**
 * Tests for Settings view
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { setActivePinia, createPinia } from 'pinia'
import Settings from '../../src/views/Settings.vue'
import api from '../../src/api.js'

// Mock API module
vi.mock('../../src/api.js', () => ({
  default: {
    listModels: vi.fn(),
    getSettings: vi.fn(),
    testModel: vi.fn(),
  },
}))

// Mock localStorage
const localStorageMock = {
  store: {},
  getItem: vi.fn((key) => localStorageMock.store[key] || null),
  setItem: vi.fn((key, value) => { localStorageMock.store[key] = value }),
  removeItem: vi.fn((key) => { delete localStorageMock.store[key] }),
  clear: vi.fn(() => { localStorageMock.store = {} }),
}
Object.defineProperty(global, 'localStorage', { value: localStorageMock })

// Mock fetch for saveApiKey
global.fetch = vi.fn(() => 
  Promise.resolve({
    json: () => Promise.resolve({ code: 'OK', message: 'Success' })
  })
)

describe('Settings', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
    localStorageMock.clear()
    
    // Default mock implementations
    api.listModels.mockResolvedValue({
      providers: [
        {
          provider_id: 'deepseek',
          display_name: 'DeepSeek',
          provider_type: 'cloud',
          models: ['deepseek-coder', 'deepseek-chat'],
          base_url: 'https://api.deepseek.com',
        },
        {
          provider_id: 'custom',
          display_name: '自定义接口',
          provider_type: 'custom',
          models: ['default'],
          base_url: '',
        },
      ]
    })
    api.getSettings.mockResolvedValue({
      quality_gate: { max_risk_score: 60, max_s0_count: 0, max_s1_count: 3 }
    })
  })

  // ═══════════════════════════════════════════════════════════════════
  // 1. RENDERING
  // ═══════════════════════════════════════════════════════════════════

  describe('rendering', () => {
    it('renders without crashing', async () => {
      const wrapper = mount(Settings)
      await flushPromises()
      
      expect(wrapper.exists()).toBe(true)
    })

    it('renders page title', async () => {
      const wrapper = mount(Settings)
      await flushPromises()
      
      expect(wrapper.text()).toContain('系统设置')
    })

    it('renders tabs for models, quality-gate, and system', async () => {
      const wrapper = mount(Settings)
      await flushPromises()
      
      expect(wrapper.text()).toContain('AI 模型管理')
      expect(wrapper.text()).toContain('质量门禁')
      expect(wrapper.text()).toContain('系统信息')
    })
  })

  // ═══════════════════════════════════════════════════════════════════
  // 2. PROVIDER DISPLAY
  // ═══════════════════════════════════════════════════════════════════

  describe('provider display', () => {
    it('only shows DeepSeek and Custom providers', async () => {
      const wrapper = mount(Settings)
      await flushPromises()
      
      expect(wrapper.text()).toContain('DeepSeek')
      expect(wrapper.text()).toContain('自定义接口')
      
      // Should NOT show old providers
      expect(wrapper.text()).not.toContain('Ollama')
      expect(wrapper.text()).not.toContain('Qwen')
      expect(wrapper.text()).not.toContain('OpenAI Compatible')
    })

    it('loads models on mount', async () => {
      mount(Settings)
      await flushPromises()
      
      expect(api.listModels).toHaveBeenCalled()
    })

    it('loads settings on mount', async () => {
      mount(Settings)
      await flushPromises()
      
      expect(api.getSettings).toHaveBeenCalled()
    })
  })

  // ═══════════════════════════════════════════════════════════════════
  // 3. PROVIDER HELPERS
  // ═══════════════════════════════════════════════════════════════════

  describe('providerTypeTag helper', () => {
    it('returns success for local', async () => {
      const wrapper = mount(Settings)
      await flushPromises()
      
      expect(wrapper.vm.providerTypeTag('local')).toBe('success')
    })

    it('returns primary for cloud', async () => {
      const wrapper = mount(Settings)
      await flushPromises()
      
      expect(wrapper.vm.providerTypeTag('cloud')).toBe('primary')
    })

    it('returns info for other types', async () => {
      const wrapper = mount(Settings)
      await flushPromises()
      
      expect(wrapper.vm.providerTypeTag('custom')).toBe('info')
      expect(wrapper.vm.providerTypeTag('unknown')).toBe('info')
    })
  })

  describe('providerTypeLabel helper', () => {
    it('returns Chinese labels', async () => {
      const wrapper = mount(Settings)
      await flushPromises()
      
      expect(wrapper.vm.providerTypeLabel('local')).toBe('本地部署')
      expect(wrapper.vm.providerTypeLabel('cloud')).toBe('云端 API')
      expect(wrapper.vm.providerTypeLabel('custom')).toBe('自定义')
    })

    it('returns original type for unknown', async () => {
      const wrapper = mount(Settings)
      await flushPromises()
      
      expect(wrapper.vm.providerTypeLabel('something')).toBe('something')
    })

    it('returns 未知 for empty type', async () => {
      const wrapper = mount(Settings)
      await flushPromises()
      
      expect(wrapper.vm.providerTypeLabel('')).toBe('未知')
      expect(wrapper.vm.providerTypeLabel(null)).toBe('未知')
    })
  })

  // ═══════════════════════════════════════════════════════════════════
  // 4. TEST CONNECTION
  // ═══════════════════════════════════════════════════════════════════

  describe('testProvider', () => {
    it('calls api.testModel with correct payload', async () => {
      api.testModel.mockResolvedValueOnce({})
      
      const wrapper = mount(Settings)
      await flushPromises()
      
      const provider = wrapper.vm.models[0]
      await wrapper.vm.testProvider(provider)
      
      expect(api.testModel).toHaveBeenCalledWith(
        expect.objectContaining({
          provider: 'deepseek',
        })
      )
    })

    it('sets healthy to true on success', async () => {
      api.testModel.mockResolvedValueOnce({})
      
      const wrapper = mount(Settings)
      await flushPromises()
      
      const provider = wrapper.vm.models[0]
      await wrapper.vm.testProvider(provider)
      
      expect(provider.healthy).toBe(true)
    })

    it('sets healthy to false on failure', async () => {
      api.testModel.mockRejectedValueOnce(new Error('Connection failed'))
      
      const wrapper = mount(Settings)
      await flushPromises()
      
      const provider = wrapper.vm.models[0]
      await wrapper.vm.testProvider(provider)
      
      expect(provider.healthy).toBe(false)
    })
  })

  // ═══════════════════════════════════════════════════════════════════
  // 5. DEFAULT MODEL
  // ═══════════════════════════════════════════════════════════════════

  describe('default model configuration', () => {
    it('computes currentProviderModels correctly', async () => {
      const wrapper = mount(Settings)
      await flushPromises()
      
      wrapper.vm.defaultProvider = 'deepseek'
      await wrapper.vm.$nextTick()
      
      expect(wrapper.vm.currentProviderModels).toContain('deepseek-coder')
    })

    it('saveDefaultModel stores in localStorage', async () => {
      const wrapper = mount(Settings)
      await flushPromises()
      
      wrapper.vm.defaultProvider = 'deepseek'
      wrapper.vm.defaultModel = 'deepseek-coder'
      wrapper.vm.saveDefaultModel()
      
      expect(localStorageMock.setItem).toHaveBeenCalledWith('gs_default_provider', 'deepseek')
      expect(localStorageMock.setItem).toHaveBeenCalledWith('gs_default_model', 'deepseek-coder')
    })

    it('restores saved defaults on mount', async () => {
      localStorageMock.store['gs_default_provider'] = 'custom'
      localStorageMock.store['gs_default_model'] = 'llama3'
      
      const wrapper = mount(Settings)
      await flushPromises()
      
      expect(wrapper.vm.defaultProvider).toBe('custom')
      expect(wrapper.vm.defaultModel).toBe('llama3')
    })
  })

  // ═══════════════════════════════════════════════════════════════════
  // 6. QUALITY GATE
  // ═══════════════════════════════════════════════════════════════════

  describe('quality gate', () => {
    it('loads quality gate from settings', async () => {
      api.getSettings.mockResolvedValueOnce({
        quality_gate: { max_risk_score: 70, max_s0_count: 1, max_s1_count: 5 }
      })
      
      const wrapper = mount(Settings)
      await flushPromises()
      
      expect(wrapper.vm.qualityGate.max_risk_score).toBe(70)
      expect(wrapper.vm.qualityGate.max_s0_count).toBe(1)
      expect(wrapper.vm.qualityGate.max_s1_count).toBe(5)
    })

    it('resets to defaults', async () => {
      const wrapper = mount(Settings)
      await flushPromises()
      
      wrapper.vm.qualityGate.max_risk_score = 90
      wrapper.vm.qualityGate.max_s0_count = 10
      
      wrapper.vm.resetQualityGate()
      
      expect(wrapper.vm.qualityGate.max_risk_score).toBe(60)
      expect(wrapper.vm.qualityGate.max_s0_count).toBe(0)
      expect(wrapper.vm.qualityGate.max_s1_count).toBe(3)
    })
  })

  // ═══════════════════════════════════════════════════════════════════
  // 7. SET DEFAULT PROVIDER
  // ═══════════════════════════════════════════════════════════════════

  describe('setDefault', () => {
    it('sets default provider and model', async () => {
      const wrapper = mount(Settings)
      await flushPromises()
      
      const provider = {
        provider_id: 'custom',
        display_name: 'Custom',
        models: ['my-model']
      }
      
      wrapper.vm.setDefault(provider)
      
      expect(wrapper.vm.defaultProvider).toBe('custom')
      expect(wrapper.vm.defaultModel).toBe('my-model')
    })
  })
})
