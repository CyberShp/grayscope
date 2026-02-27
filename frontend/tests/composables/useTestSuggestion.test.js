/**
 * Tests for useTestSuggestion composable
 */

import { describe, it, expect } from 'vitest'
import { useTestSuggestion } from '../../src/composables/useTestSuggestion.js'

describe('useTestSuggestion', () => {
  const { getTestObjective, getTestSteps, getTestExpected, getTestPriority } = useTestSuggestion()

  // ═══════════════════════════════════════════════════════════════════
  // 1. getTestPriority
  // ═══════════════════════════════════════════════════════════════════

  describe('getTestPriority', () => {
    it('maps S0 to P0-紧急', () => {
      expect(getTestPriority({ severity: 'S0' })).toBe('P0-紧急')
    })

    it('maps S1 to P1-高', () => {
      expect(getTestPriority({ severity: 'S1' })).toBe('P1-高')
    })

    it('maps S2 to P2-中', () => {
      expect(getTestPriority({ severity: 'S2' })).toBe('P2-中')
    })

    it('maps S3 to P3-低', () => {
      expect(getTestPriority({ severity: 'S3' })).toBe('P3-低')
    })

    it('defaults to P3-低 for missing severity', () => {
      expect(getTestPriority({})).toBe('P3-低')
    })
  })

  // ═══════════════════════════════════════════════════════════════════
  // 2. getTestObjective
  // ═══════════════════════════════════════════════════════════════════

  describe('getTestObjective', () => {
    it('generates objective for boundary_miss', () => {
      const finding = {
        risk_type: 'boundary_miss',
        symbol_name: 'process_buffer',
        evidence: { constraint_expr: 'size > 0 && size < 1024' }
      }
      
      const result = getTestObjective(finding)
      
      expect(result).toContain('process_buffer')
      expect(result).toContain('边界')
    })

    it('generates objective for missing_cleanup', () => {
      const finding = {
        risk_type: 'missing_cleanup',
        symbol_name: 'init_connection',
        evidence: { cleanup_resources_expected: ['socket_fd', 'buffer'] }
      }
      
      const result = getTestObjective(finding)
      
      expect(result).toContain('init_connection')
      expect(result).toContain('释放')
    })

    it('generates objective for race_write_without_lock', () => {
      const finding = {
        risk_type: 'race_write_without_lock',
        symbol_name: 'update_counter',
        evidence: { shared_symbol: 'g_counter' }
      }
      
      const result = getTestObjective(finding)
      
      expect(result).toContain('update_counter')
      expect(result).toContain('g_counter')
    })

    it('generates objective with propagation chain', () => {
      const finding = {
        risk_type: 'boundary_miss',
        symbol_name: 'target_func',
        evidence: {
          propagation_chain: [
            { function: 'entry_func', param: 'input' },
            { function: 'middle_func', param: 'data' },
            { function: 'target_func', param: 'buffer' }
          ],
          is_external_input: true
        }
      }
      
      const result = getTestObjective(finding)
      
      expect(result).toContain('entry_func')
      expect(result).toContain('3 层')
      expect(result).toContain('外部输入')
    })

    it('generates fallback for unknown risk type', () => {
      const finding = {
        risk_type: 'unknown_type',
        symbol_name: 'some_func'
      }
      
      const result = getTestObjective(finding)
      
      expect(result).toContain('some_func')
      expect(result).toContain('unknown_type')
    })
  })

  // ═══════════════════════════════════════════════════════════════════
  // 3. getTestSteps
  // ═══════════════════════════════════════════════════════════════════

  describe('getTestSteps', () => {
    it('generates steps for boundary test', () => {
      const finding = {
        risk_type: 'boundary_miss',
        symbol_name: 'validate_size',
        evidence: {
          constraint_expr: 'size > 0',
          candidates: [0, 1, -1, 1024, 1025]
        }
      }
      
      const steps = getTestSteps(finding)
      
      expect(Array.isArray(steps)).toBe(true)
      expect(steps.length).toBeGreaterThanOrEqual(3)
      expect(steps[0]).toContain('定位')
      expect(steps.some(s => s.includes('测试值') || s.includes('候选'))).toBe(true)
    })

    it('generates steps for cleanup test', () => {
      const finding = {
        risk_type: 'missing_cleanup',
        symbol_name: 'open_file',
        evidence: {
          cleanup_resources_expected: ['file_handle', 'buffer'],
          cleanup_resources_observed: ['file_handle']
        }
      }
      
      const steps = getTestSteps(finding)
      
      expect(steps.some(s => s.includes('资源') || s.includes('释放'))).toBe(true)
      expect(steps.some(s => s.includes('Valgrind') || s.includes('Sanitizer'))).toBe(true)
    })

    it('generates steps for race condition test', () => {
      const finding = {
        risk_type: 'race_write_without_lock',
        symbol_name: 'increment',
        evidence: { shared_symbol: 'counter' }
      }
      
      const steps = getTestSteps(finding)
      
      expect(steps.some(s => s.includes('多线程') || s.includes('并发'))).toBe(true)
      expect(steps.some(s => s.includes('ThreadSanitizer') || s.includes('TSan'))).toBe(true)
    })

    it('generates steps for cross_function_resource_leak', () => {
      const finding = {
        risk_type: 'cross_function_resource_leak',
        symbol_name: 'process_request',
        evidence: {
          caller_function: 'process_request',
          callee_function: 'init_buffer',
          caller_resources: ['conn', 'buffer']
        }
      }
      
      const steps = getTestSteps(finding)
      
      expect(steps.length).toBeGreaterThanOrEqual(4)
      expect(steps.some(s => s.includes('init_buffer'))).toBe(true)
      expect(steps.some(s => s.includes('Valgrind'))).toBe(true)
    })

    it('generates steps for cross_function_deadlock_risk', () => {
      const finding = {
        risk_type: 'cross_function_deadlock_risk',
        symbol_name: 'handler',
        evidence: {
          chain_a: { path: 'path_a', locks: ['lock_a', 'lock_b'] },
          chain_b: { path: 'path_b', locks: ['lock_b', 'lock_a'] }
        }
      }
      
      const steps = getTestSteps(finding)
      
      expect(steps.length).toBeGreaterThanOrEqual(4)
      expect(steps.some(s => s.includes('lock_a'))).toBe(true)
      expect(steps.some(s => s.includes('死锁'))).toBe(true)
    })

    it('generates steps with propagation chain analysis', () => {
      const finding = {
        risk_type: 'deep_param_propagation',
        symbol_name: 'target',
        evidence: {
          propagation_chain: [
            { function: 'entry', param: 'input', transform: 'none' },
            { function: 'middle', param: 'data', transform: 'multiply', transform_expr: 'data*2' },
            { function: 'target', param: 'result', transform: 'none' }
          ]
        }
      }
      
      const steps = getTestSteps(finding)
      
      expect(steps.some(s => s.includes('入口函数'))).toBe(true)
      expect(steps.some(s => s.includes('调用链'))).toBe(true)
    })
  })

  // ═══════════════════════════════════════════════════════════════════
  // 4. getTestExpected
  // ═══════════════════════════════════════════════════════════════════

  describe('getTestExpected', () => {
    it('generates expected result for boundary_miss', () => {
      const finding = { risk_type: 'boundary_miss', symbol_name: 'parse' }
      
      const result = getTestExpected(finding)
      
      expect(result).toContain('parse')
      expect(result).toContain('边界')
    })

    it('generates expected result for missing_cleanup', () => {
      const finding = {
        risk_type: 'missing_cleanup',
        symbol_name: 'init',
        evidence: { cleanup_resources_expected: ['fd', 'buf'] }
      }
      
      const result = getTestExpected(finding)
      
      expect(result).toContain('fd')
      expect(result).toContain('buf')
    })

    it('generates expected result for race_write_without_lock', () => {
      const finding = {
        risk_type: 'race_write_without_lock',
        symbol_name: 'write',
        evidence: { shared_symbol: 'g_data' }
      }
      
      const result = getTestExpected(finding)
      
      expect(result).toContain('ThreadSanitizer')
      expect(result).toContain('g_data')
    })

    it('generates expected result for changed_core_path', () => {
      const finding = { risk_type: 'changed_core_path', symbol_name: 'core_func' }
      
      const result = getTestExpected(finding)
      
      expect(result).toContain('core_func')
      expect(result).toContain('一致')
    })

    it('generates fallback for unknown risk type', () => {
      const finding = { risk_type: 'unknown', symbol_name: 'func' }
      
      const result = getTestExpected(finding)
      
      expect(result).toContain('func')
      expect(result).toContain('正确')
    })
  })

  // ═══════════════════════════════════════════════════════════════════
  // 5. Edge Cases
  // ═══════════════════════════════════════════════════════════════════

  describe('edge cases', () => {
    it('handles finding without symbol_name', () => {
      const finding = { risk_type: 'boundary_miss' }
      
      const objective = getTestObjective(finding)
      const steps = getTestSteps(finding)
      const expected = getTestExpected(finding)
      
      expect(objective).toContain('目标函数')
      expect(steps.length).toBeGreaterThan(0)
      expect(expected).toBeDefined()
    })

    it('handles finding without evidence', () => {
      const finding = { risk_type: 'missing_cleanup', symbol_name: 'func' }
      
      const objective = getTestObjective(finding)
      const steps = getTestSteps(finding)
      
      expect(objective).toBeDefined()
      expect(steps.length).toBeGreaterThan(0)
    })

    it('handles empty evidence', () => {
      const finding = { 
        risk_type: 'boundary_miss', 
        symbol_name: 'func',
        evidence: {} 
      }
      
      const steps = getTestSteps(finding)
      
      expect(steps.length).toBeGreaterThan(0)
    })
  })
})
