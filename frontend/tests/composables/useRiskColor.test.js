/**
 * Tests for useRiskColor composable
 */

import { describe, it, expect } from 'vitest'
import { useRiskColor } from '../../src/composables/useRiskColor.js'

describe('useRiskColor', () => {
  const { 
    riskColor, 
    riskLevel, 
    riskType, 
    severityType, 
    statusType, 
    statusLabel 
  } = useRiskColor()

  // ═══════════════════════════════════════════════════════════════════
  // 1. riskColor
  // ═══════════════════════════════════════════════════════════════════

  describe('riskColor', () => {
    it('returns red for high risk (>= 0.8)', () => {
      expect(riskColor(0.8)).toBe('#F56C6C')
      expect(riskColor(0.9)).toBe('#F56C6C')
      expect(riskColor(1.0)).toBe('#F56C6C')
    })

    it('returns orange for medium risk (0.6-0.8)', () => {
      expect(riskColor(0.6)).toBe('#E6A23C')
      expect(riskColor(0.7)).toBe('#E6A23C')
      expect(riskColor(0.79)).toBe('#E6A23C')
    })

    it('returns blue for low risk (0.4-0.6)', () => {
      expect(riskColor(0.4)).toBe('#409EFF')
      expect(riskColor(0.5)).toBe('#409EFF')
      expect(riskColor(0.59)).toBe('#409EFF')
    })

    it('returns green for safe (< 0.4)', () => {
      expect(riskColor(0.0)).toBe('#67C23A')
      expect(riskColor(0.2)).toBe('#67C23A')
      expect(riskColor(0.39)).toBe('#67C23A')
    })
  })

  // ═══════════════════════════════════════════════════════════════════
  // 2. riskLevel
  // ═══════════════════════════════════════════════════════════════════

  describe('riskLevel', () => {
    it('returns 高风险 for >= 0.8', () => {
      expect(riskLevel(0.8)).toBe('高风险')
      expect(riskLevel(1.0)).toBe('高风险')
    })

    it('returns 中风险 for 0.6-0.8', () => {
      expect(riskLevel(0.6)).toBe('中风险')
      expect(riskLevel(0.79)).toBe('中风险')
    })

    it('returns 低风险 for 0.4-0.6', () => {
      expect(riskLevel(0.4)).toBe('低风险')
      expect(riskLevel(0.59)).toBe('低风险')
    })

    it('returns 安全 for < 0.4', () => {
      expect(riskLevel(0.0)).toBe('安全')
      expect(riskLevel(0.39)).toBe('安全')
    })
  })

  // ═══════════════════════════════════════════════════════════════════
  // 3. riskType
  // ═══════════════════════════════════════════════════════════════════

  describe('riskType', () => {
    it('returns danger for >= 0.8', () => {
      expect(riskType(0.8)).toBe('danger')
    })

    it('returns warning for 0.6-0.8', () => {
      expect(riskType(0.7)).toBe('warning')
    })

    it('returns empty string for 0.4-0.6', () => {
      expect(riskType(0.5)).toBe('')
    })

    it('returns success for < 0.4', () => {
      expect(riskType(0.3)).toBe('success')
    })
  })

  // ═══════════════════════════════════════════════════════════════════
  // 4. severityType
  // ═══════════════════════════════════════════════════════════════════

  describe('severityType', () => {
    it('maps S0 to danger', () => {
      expect(severityType('S0')).toBe('danger')
    })

    it('maps S1 to danger', () => {
      expect(severityType('S1')).toBe('danger')
    })

    it('maps S2 to warning', () => {
      expect(severityType('S2')).toBe('warning')
    })

    it('maps S3 to info', () => {
      expect(severityType('S3')).toBe('info')
    })

    it('defaults to info for unknown severity', () => {
      expect(severityType('S4')).toBe('info')
      expect(severityType('')).toBe('info')
      expect(severityType(null)).toBe('info')
    })
  })

  // ═══════════════════════════════════════════════════════════════════
  // 5. statusType
  // ═══════════════════════════════════════════════════════════════════

  describe('statusType', () => {
    it('maps success to success', () => {
      expect(statusType('success')).toBe('success')
    })

    it('maps failed to danger', () => {
      expect(statusType('failed')).toBe('danger')
    })

    it('maps running to warning', () => {
      expect(statusType('running')).toBe('warning')
    })

    it('maps pending to info', () => {
      expect(statusType('pending')).toBe('info')
    })

    it('maps skipped to info', () => {
      expect(statusType('skipped')).toBe('info')
    })

    it('maps cancelled to info', () => {
      expect(statusType('cancelled')).toBe('info')
    })

    it('maps partial_failed to warning', () => {
      expect(statusType('partial_failed')).toBe('warning')
    })

    it('defaults to info for unknown status', () => {
      expect(statusType('unknown')).toBe('info')
    })
  })

  // ═══════════════════════════════════════════════════════════════════
  // 6. statusLabel
  // ═══════════════════════════════════════════════════════════════════

  describe('statusLabel', () => {
    it('maps success to 成功', () => {
      expect(statusLabel('success')).toBe('成功')
    })

    it('maps failed to 失败', () => {
      expect(statusLabel('failed')).toBe('失败')
    })

    it('maps running to 运行中', () => {
      expect(statusLabel('running')).toBe('运行中')
    })

    it('maps pending to 等待中', () => {
      expect(statusLabel('pending')).toBe('等待中')
    })

    it('maps skipped to 已跳过', () => {
      expect(statusLabel('skipped')).toBe('已跳过')
    })

    it('maps cancelled to 已取消', () => {
      expect(statusLabel('cancelled')).toBe('已取消')
    })

    it('maps partial_failed to 部分失败', () => {
      expect(statusLabel('partial_failed')).toBe('部分失败')
    })

    it('returns original status for unknown', () => {
      expect(statusLabel('unknown')).toBe('unknown')
    })
  })
})
