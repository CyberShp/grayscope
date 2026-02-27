/**
 * Tests for useRiskTypeNames composable
 */

import { describe, it, expect } from 'vitest'
import { getRiskTypeName, riskTypeOptions } from '../../src/composables/useRiskTypeNames.js'

describe('useRiskTypeNames', () => {
  // ═══════════════════════════════════════════════════════════════════
  // 1. getRiskTypeName
  // ═══════════════════════════════════════════════════════════════════

  describe('getRiskTypeName', () => {
    it('returns Chinese name for branch-related risks', () => {
      expect(getRiskTypeName('branch_error')).toBe('分支错误路径')
      expect(getRiskTypeName('branch_cleanup')).toBe('分支清理路径')
      expect(getRiskTypeName('branch_boundary')).toBe('分支边界')
      expect(getRiskTypeName('branch_state')).toBe('分支状态')
      expect(getRiskTypeName('branch_normal')).toBe('分支正常路径')
      expect(getRiskTypeName('branch_missing_test')).toBe('分支缺测')
      expect(getRiskTypeName('branch_high_complexity')).toBe('分支高复杂度')
      expect(getRiskTypeName('branch_switch_no_default')).toBe('switch 缺 default')
    })

    it('returns Chinese name for boundary-related risks', () => {
      expect(getRiskTypeName('boundary_miss')).toBe('边界遗漏')
      expect(getRiskTypeName('invalid_input_gap')).toBe('无效输入缺口')
    })

    it('returns Chinese name for error-path risks', () => {
      expect(getRiskTypeName('missing_cleanup')).toBe('缺少清理')
      expect(getRiskTypeName('inconsistent_errno_mapping')).toBe('错误码映射不一致')
      expect(getRiskTypeName('silent_error_swallow')).toBe('静默吞错')
      expect(getRiskTypeName('cross_function_resource_leak')).toBe('跨函数资源泄漏')
    })

    it('returns Chinese name for call-graph risks', () => {
      expect(getRiskTypeName('high_fan_out')).toBe('高扇出')
      expect(getRiskTypeName('deep_impact_surface')).toBe('影响面深')
      expect(getRiskTypeName('hotspot_regression_risk')).toBe('热点回归风险')
    })

    it('returns Chinese name for data-flow risks', () => {
      expect(getRiskTypeName('deep_param_propagation')).toBe('参数深传播')
      expect(getRiskTypeName('external_to_sensitive')).toBe('外部到敏感')
      expect(getRiskTypeName('value_transform_risk')).toBe('值变换风险')
    })

    it('returns Chinese name for concurrency risks', () => {
      expect(getRiskTypeName('race_write_without_lock')).toBe('无锁竞态写')
      expect(getRiskTypeName('lock_order_inversion')).toBe('锁顺序反转')
      expect(getRiskTypeName('atomicity_gap')).toBe('原子性缺口')
      expect(getRiskTypeName('cross_function_deadlock_risk')).toBe('跨函数死锁风险')
      expect(getRiskTypeName('cross_function_race')).toBe('跨函数竞态')
    })

    it('returns Chinese name for diff-impact risks', () => {
      expect(getRiskTypeName('changed_core_path')).toBe('核心路径变更')
      expect(getRiskTypeName('transitive_impact')).toBe('传递影响')
    })

    it('returns Chinese name for coverage risks', () => {
      expect(getRiskTypeName('high_risk_low_coverage')).toBe('高风险低覆盖')
      expect(getRiskTypeName('critical_path_uncovered')).toBe('关键路径未覆盖')
    })

    it('returns original string for unknown risk type', () => {
      expect(getRiskTypeName('unknown_risk_type')).toBe('unknown_risk_type')
      expect(getRiskTypeName('custom_type')).toBe('custom_type')
    })

    it('returns empty string for empty/null input', () => {
      expect(getRiskTypeName('')).toBe('')
      expect(getRiskTypeName(null)).toBe('')
      expect(getRiskTypeName(undefined)).toBe('')
    })
  })

  // ═══════════════════════════════════════════════════════════════════
  // 2. riskTypeOptions
  // ═══════════════════════════════════════════════════════════════════

  describe('riskTypeOptions', () => {
    it('is an array', () => {
      expect(Array.isArray(riskTypeOptions)).toBe(true)
    })

    it('has expected number of options', () => {
      expect(riskTypeOptions.length).toBeGreaterThanOrEqual(20)
    })

    it('each option has id and name', () => {
      riskTypeOptions.forEach(opt => {
        expect(opt).toHaveProperty('id')
        expect(opt).toHaveProperty('name')
        expect(typeof opt.id).toBe('string')
        expect(typeof opt.name).toBe('string')
      })
    })

    it('includes branch_error option', () => {
      const opt = riskTypeOptions.find(o => o.id === 'branch_error')
      expect(opt).toBeDefined()
      expect(opt.name).toBe('分支错误路径')
    })

    it('includes concurrency options', () => {
      const raceOpt = riskTypeOptions.find(o => o.id === 'race_write_without_lock')
      expect(raceOpt).toBeDefined()
      expect(raceOpt.name).toBe('无锁竞态写')
    })
  })
})
