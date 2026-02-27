/**
 * Tests for useModuleNames composable
 */

import { describe, it, expect } from 'vitest'
import { useModuleNames } from '../../src/composables/useModuleNames.js'

describe('useModuleNames', () => {
  const { 
    MODULE_NAMES, 
    MODULE_DESCRIPTIONS, 
    ANALYSIS_MODULES, 
    moduleList, 
    getDisplayName, 
    getDescription 
  } = useModuleNames()

  // ═══════════════════════════════════════════════════════════════════
  // 1. MODULE_NAMES MAP
  // ═══════════════════════════════════════════════════════════════════

  describe('MODULE_NAMES', () => {
    it('contains all expected module names', () => {
      expect(MODULE_NAMES.branch_path).toBe('分支路径分析')
      expect(MODULE_NAMES.boundary_value).toBe('边界值分析')
      expect(MODULE_NAMES.error_path).toBe('错误路径分析')
      expect(MODULE_NAMES.call_graph).toBe('调用图构建')
      expect(MODULE_NAMES.protocol).toBe('协议报文分析')
      expect(MODULE_NAMES.data_flow).toBe('数据流分析')
      expect(MODULE_NAMES.concurrency).toBe('并发风险分析')
    })

    it('has at least 10 modules defined', () => {
      const count = Object.keys(MODULE_NAMES).length
      expect(count).toBeGreaterThanOrEqual(10)
    })
  })

  // ═══════════════════════════════════════════════════════════════════
  // 2. MODULE_DESCRIPTIONS MAP
  // ═══════════════════════════════════════════════════════════════════

  describe('MODULE_DESCRIPTIONS', () => {
    it('has descriptions for all modules', () => {
      Object.keys(MODULE_NAMES).forEach(key => {
        expect(MODULE_DESCRIPTIONS[key]).toBeDefined()
        expect(MODULE_DESCRIPTIONS[key].length).toBeGreaterThan(0)
      })
    })

    it('descriptions are in Chinese', () => {
      expect(MODULE_DESCRIPTIONS.branch_path).toContain('分支')
      expect(MODULE_DESCRIPTIONS.data_flow).toContain('传播')
    })
  })

  // ═══════════════════════════════════════════════════════════════════
  // 3. ANALYSIS_MODULES ARRAY
  // ═══════════════════════════════════════════════════════════════════

  describe('ANALYSIS_MODULES', () => {
    it('is an array of 11 core modules', () => {
      expect(Array.isArray(ANALYSIS_MODULES)).toBe(true)
      expect(ANALYSIS_MODULES.length).toBe(11)
    })

    it('does not include postmortem or knowledge_pattern', () => {
      expect(ANALYSIS_MODULES).not.toContain('postmortem')
      expect(ANALYSIS_MODULES).not.toContain('knowledge_pattern')
    })

    it('includes core analysis modules', () => {
      expect(ANALYSIS_MODULES).toContain('branch_path')
      expect(ANALYSIS_MODULES).toContain('call_graph')
      expect(ANALYSIS_MODULES).toContain('data_flow')
      expect(ANALYSIS_MODULES).toContain('concurrency')
    })
  })

  // ═══════════════════════════════════════════════════════════════════
  // 4. moduleList
  // ═══════════════════════════════════════════════════════════════════

  describe('moduleList', () => {
    it('is an array of { id, name } objects', () => {
      expect(Array.isArray(moduleList)).toBe(true)
      
      moduleList.forEach(item => {
        expect(item).toHaveProperty('id')
        expect(item).toHaveProperty('name')
      })
    })

    it('has correct length matching ANALYSIS_MODULES', () => {
      expect(moduleList.length).toBe(ANALYSIS_MODULES.length)
    })

    it('has Chinese names for each module', () => {
      const branchPath = moduleList.find(m => m.id === 'branch_path')
      expect(branchPath.name).toBe('分支路径分析')
    })
  })

  // ═══════════════════════════════════════════════════════════════════
  // 5. getDisplayName
  // ═══════════════════════════════════════════════════════════════════

  describe('getDisplayName', () => {
    it('returns Chinese name for known module', () => {
      expect(getDisplayName('branch_path')).toBe('分支路径分析')
      expect(getDisplayName('concurrency')).toBe('并发风险分析')
    })

    it('returns original ID for unknown module', () => {
      expect(getDisplayName('unknown_module')).toBe('unknown_module')
    })

    it('handles undefined gracefully', () => {
      expect(getDisplayName(undefined)).toBe(undefined)
    })
  })

  // ═══════════════════════════════════════════════════════════════════
  // 6. getDescription
  // ═══════════════════════════════════════════════════════════════════

  describe('getDescription', () => {
    it('returns description for known module', () => {
      const desc = getDescription('branch_path')
      expect(desc).toContain('分支')
    })

    it('returns empty string for unknown module', () => {
      expect(getDescription('unknown_module')).toBe('')
    })

    it('handles undefined gracefully', () => {
      expect(getDescription(undefined)).toBe('')
    })
  })
})
