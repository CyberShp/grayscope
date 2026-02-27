/**
 * Tests for FunctionDictionary component
 */

import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import FunctionDictionary from '../../../src/components/analysis/FunctionDictionary.vue'

describe('FunctionDictionary', () => {
  const mockDictionary = {
    'init_connection': {
      business_description: '初始化网络连接，建立与服务器的 TCP 通道',
      inputs: ['host', 'port', 'timeout'],
      outputs: 'connection_handle',
      side_effects: ['创建套接字', '修改全局状态'],
      confidence: 0.85,
    },
    'process_data': {
      business_description: '处理输入数据并返回处理结果',
      inputs: ['data', 'length'],
      outputs: 'processed_result',
      side_effects: [],
      confidence: 0.92,
    },
    'cleanup_resources': {
      business_description: '清理已分配的资源',
      inputs: ['handle'],
      outputs: 'status_code',
      side_effects: ['释放内存', '关闭文件'],
      confidence: 0.45,
    },
  }

  // ═══════════════════════════════════════════════════════════════════
  // 1. RENDERING
  // ═══════════════════════════════════════════════════════════════════

  describe('rendering', () => {
    it('renders without crashing', () => {
      const wrapper = mount(FunctionDictionary, {
        props: { dictionary: mockDictionary },
      })
      
      expect(wrapper.exists()).toBe(true)
    })

    it('renders empty state when no dictionary', () => {
      const wrapper = mount(FunctionDictionary, {
        props: { dictionary: {} },
      })
      
      expect(wrapper.find('.gs-empty').exists()).toBe(true)
    })

    it('displays function count in tag', () => {
      const wrapper = mount(FunctionDictionary, {
        props: { dictionary: mockDictionary },
      })
      
      const html = wrapper.html()
      expect(html).toContain('3')
      expect(html).toContain('个函数')
    })

    it('renders search input', () => {
      const wrapper = mount(FunctionDictionary, {
        props: { dictionary: mockDictionary },
      })
      
      expect(wrapper.find('.gs-fd-toolbar').exists()).toBe(true)
    })
  })

  // ═══════════════════════════════════════════════════════════════════
  // 2. DATA TRANSFORMATION
  // ═══════════════════════════════════════════════════════════════════

  describe('data transformation', () => {
    it('transforms dictionary to list format', () => {
      const wrapper = mount(FunctionDictionary, {
        props: { dictionary: mockDictionary },
      })
      
      const dictList = wrapper.vm.dictList
      expect(dictList.length).toBe(3)
      
      const initConn = dictList.find(d => d.function_name === 'init_connection')
      expect(initConn).toBeDefined()
      expect(initConn.business_description).toContain('网络连接')
    })

    it('includes function_name from object key', () => {
      const wrapper = mount(FunctionDictionary, {
        props: { dictionary: mockDictionary },
      })
      
      const dictList = wrapper.vm.dictList
      expect(dictList.every(d => d.function_name)).toBe(true)
    })
  })

  // ═══════════════════════════════════════════════════════════════════
  // 3. FILTERING
  // ═══════════════════════════════════════════════════════════════════

  describe('filtering', () => {
    it('shows all items when no search term', () => {
      const wrapper = mount(FunctionDictionary, {
        props: { dictionary: mockDictionary },
      })
      
      expect(wrapper.vm.filteredList.length).toBe(3)
    })

    it('filters by function name', async () => {
      const wrapper = mount(FunctionDictionary, {
        props: { dictionary: mockDictionary },
      })
      
      wrapper.vm.searchTerm = 'init'
      await wrapper.vm.$nextTick()
      
      expect(wrapper.vm.filteredList.length).toBe(1)
      expect(wrapper.vm.filteredList[0].function_name).toBe('init_connection')
    })

    it('filters by business description', async () => {
      const wrapper = mount(FunctionDictionary, {
        props: { dictionary: mockDictionary },
      })
      
      wrapper.vm.searchTerm = '资源'
      await wrapper.vm.$nextTick()
      
      expect(wrapper.vm.filteredList.length).toBe(1)
      expect(wrapper.vm.filteredList[0].function_name).toBe('cleanup_resources')
    })

    it('filters are case insensitive', async () => {
      const wrapper = mount(FunctionDictionary, {
        props: { dictionary: mockDictionary },
      })
      
      wrapper.vm.searchTerm = 'INIT'
      await wrapper.vm.$nextTick()
      
      expect(wrapper.vm.filteredList.length).toBe(1)
    })

    it('returns empty array for no matches', async () => {
      const wrapper = mount(FunctionDictionary, {
        props: { dictionary: mockDictionary },
      })
      
      wrapper.vm.searchTerm = 'nonexistent_function'
      await wrapper.vm.$nextTick()
      
      expect(wrapper.vm.filteredList.length).toBe(0)
    })
  })

  // ═══════════════════════════════════════════════════════════════════
  // 4. CONFIDENCE COLOR
  // ═══════════════════════════════════════════════════════════════════

  describe('confidenceColor helper', () => {
    it('returns green for high confidence (>= 0.8)', () => {
      const wrapper = mount(FunctionDictionary, {
        props: { dictionary: {} },
      })
      
      expect(wrapper.vm.confidenceColor(0.8)).toBe('#67C23A')
      expect(wrapper.vm.confidenceColor(0.95)).toBe('#67C23A')
      expect(wrapper.vm.confidenceColor(1.0)).toBe('#67C23A')
    })

    it('returns orange for medium confidence (0.5-0.8)', () => {
      const wrapper = mount(FunctionDictionary, {
        props: { dictionary: {} },
      })
      
      expect(wrapper.vm.confidenceColor(0.5)).toBe('#E6A23C')
      expect(wrapper.vm.confidenceColor(0.65)).toBe('#E6A23C')
      expect(wrapper.vm.confidenceColor(0.79)).toBe('#E6A23C')
    })

    it('returns red for low confidence (< 0.5)', () => {
      const wrapper = mount(FunctionDictionary, {
        props: { dictionary: {} },
      })
      
      expect(wrapper.vm.confidenceColor(0.0)).toBe('#F56C6C')
      expect(wrapper.vm.confidenceColor(0.3)).toBe('#F56C6C')
      expect(wrapper.vm.confidenceColor(0.49)).toBe('#F56C6C')
    })

    it('handles undefined confidence', () => {
      const wrapper = mount(FunctionDictionary, {
        props: { dictionary: {} },
      })
      
      expect(wrapper.vm.confidenceColor(undefined)).toBe('#F56C6C')
    })
  })

  // ═══════════════════════════════════════════════════════════════════
  // 5. EDGE CASES
  // ═══════════════════════════════════════════════════════════════════

  describe('edge cases', () => {
    it('handles null dictionary', () => {
      const wrapper = mount(FunctionDictionary, {
        props: { dictionary: null },
      })
      
      expect(wrapper.vm.dictList.length).toBe(0)
      expect(wrapper.vm.filteredList.length).toBe(0)
    })

    it('handles function without business_description', () => {
      const partialDict = {
        'no_desc_func': {
          inputs: ['x'],
          outputs: 'y',
        }
      }
      
      const wrapper = mount(FunctionDictionary, {
        props: { dictionary: partialDict },
      })
      
      expect(wrapper.vm.dictList.length).toBe(1)
      
      // Search by name should still work
      wrapper.vm.searchTerm = 'no_desc'
      expect(wrapper.vm.filteredList.length).toBe(1)
    })

    it('handles function without inputs', () => {
      const noInputsDict = {
        'getter_func': {
          business_description: 'Gets a value',
          outputs: 'value',
        }
      }
      
      const wrapper = mount(FunctionDictionary, {
        props: { dictionary: noInputsDict },
      })
      
      expect(wrapper.vm.dictList.length).toBe(1)
    })
  })
})
