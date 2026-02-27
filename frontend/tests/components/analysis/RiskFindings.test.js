/**
 * Tests for RiskFindings component
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import RiskFindings from '../../../src/components/analysis/RiskFindings.vue'

describe('RiskFindings', () => {
  const mockFindings = [
    {
      finding_id: 'RF-001',
      risk_type: 'deadlock_potential',
      severity: 'critical',
      description: 'Potential deadlock detected',
      call_chain: ['main', 'process', 'lock_handler'],
      risk_score: 0.95,
    },
    {
      finding_id: 'RF-002',
      risk_type: 'resource_leak',
      severity: 'high',
      description: 'Memory leak in error path',
      call_chain: ['init', 'allocate', 'cleanup'],
      risk_score: 0.75,
    },
    {
      finding_id: 'RF-003',
      risk_type: 'boundary_miss',
      severity: 'medium',
      description: 'Missing boundary check',
      call_chain: ['validate', 'process'],
      risk_score: 0.5,
    },
    {
      finding_id: 'RF-004',
      risk_type: 'protocol_error',
      severity: 'low',
      description: 'Protocol state not verified',
      call_chain: ['handle_message'],
      risk_score: 0.25,
    },
  ]

  const mockSummary = {
    total_findings: 4,
    severity_distribution: {
      critical: 1,
      high: 1,
      medium: 1,
      low: 1,
    },
  }

  // ═══════════════════════════════════════════════════════════════════
  // 1. RENDERING
  // ═══════════════════════════════════════════════════════════════════

  describe('rendering', () => {
    it('renders without crashing', () => {
      const wrapper = mount(RiskFindings, {
        props: { findings: mockFindings, summary: mockSummary },
      })
      
      expect(wrapper.exists()).toBe(true)
    })

    it('renders empty state when no findings', () => {
      const wrapper = mount(RiskFindings, {
        props: { findings: [], summary: {} },
      })
      
      expect(wrapper.exists()).toBe(true)
    })

    it('renders summary statistics', () => {
      const wrapper = mount(RiskFindings, {
        props: { findings: mockFindings, summary: mockSummary },
      })
      
      const html = wrapper.html()
      expect(html).toContain('总风险数')
    })

    it('renders filters section', () => {
      const wrapper = mount(RiskFindings, {
        props: { findings: mockFindings, summary: mockSummary },
      })
      
      expect(wrapper.find('.gs-rf-filters').exists()).toBe(true)
    })
  })

  // ═══════════════════════════════════════════════════════════════════
  // 2. FILTERING
  // ═══════════════════════════════════════════════════════════════════

  describe('filtering', () => {
    it('computes risk types from findings', async () => {
      const wrapper = mount(RiskFindings, {
        props: { findings: mockFindings, summary: mockSummary },
      })
      
      // Access computed via vm
      const riskTypes = wrapper.vm.riskTypes
      expect(riskTypes).toContain('deadlock_potential')
      expect(riskTypes).toContain('resource_leak')
      expect(riskTypes).toContain('boundary_miss')
    })

    it('filters by severity', async () => {
      const wrapper = mount(RiskFindings, {
        props: { findings: mockFindings, summary: mockSummary },
      })
      
      // Initially all findings shown
      expect(wrapper.vm.filteredFindings.length).toBe(4)
      
      // Set filter
      wrapper.vm.filterSeverity = 'critical'
      await wrapper.vm.$nextTick()
      
      expect(wrapper.vm.filteredFindings.length).toBe(1)
      expect(wrapper.vm.filteredFindings[0].severity).toBe('critical')
    })

    it('filters by risk type', async () => {
      const wrapper = mount(RiskFindings, {
        props: { findings: mockFindings, summary: mockSummary },
      })
      
      wrapper.vm.filterType = 'resource_leak'
      await wrapper.vm.$nextTick()
      
      expect(wrapper.vm.filteredFindings.length).toBe(1)
      expect(wrapper.vm.filteredFindings[0].risk_type).toBe('resource_leak')
    })

    it('filters by search keyword in description', async () => {
      const wrapper = mount(RiskFindings, {
        props: { findings: mockFindings, summary: mockSummary },
      })
      
      wrapper.vm.searchKeyword = 'deadlock'
      await wrapper.vm.$nextTick()
      
      expect(wrapper.vm.filteredFindings.length).toBe(1)
      expect(wrapper.vm.filteredFindings[0].finding_id).toBe('RF-001')
    })

    it('filters by search keyword in finding_id', async () => {
      const wrapper = mount(RiskFindings, {
        props: { findings: mockFindings, summary: mockSummary },
      })
      
      wrapper.vm.searchKeyword = 'RF-002'
      await wrapper.vm.$nextTick()
      
      expect(wrapper.vm.filteredFindings.length).toBe(1)
    })

    it('filters by search keyword in call chain', async () => {
      const wrapper = mount(RiskFindings, {
        props: { findings: mockFindings, summary: mockSummary },
      })
      
      wrapper.vm.searchKeyword = 'allocate'
      await wrapper.vm.$nextTick()
      
      expect(wrapper.vm.filteredFindings.length).toBe(1)
      expect(wrapper.vm.filteredFindings[0].finding_id).toBe('RF-002')
    })

    it('combines multiple filters', async () => {
      const wrapper = mount(RiskFindings, {
        props: { findings: mockFindings, summary: mockSummary },
      })
      
      wrapper.vm.filterSeverity = 'high'
      wrapper.vm.filterType = 'resource_leak'
      await wrapper.vm.$nextTick()
      
      expect(wrapper.vm.filteredFindings.length).toBe(1)
    })
  })

  // ═══════════════════════════════════════════════════════════════════
  // 3. SEVERITY TAG HELPER
  // ═══════════════════════════════════════════════════════════════════

  describe('severityTag helper', () => {
    it('returns danger for critical', () => {
      const wrapper = mount(RiskFindings, {
        props: { findings: [], summary: {} },
      })
      
      expect(wrapper.vm.severityTag('critical')).toBe('danger')
    })

    it('returns warning for high', () => {
      const wrapper = mount(RiskFindings, {
        props: { findings: [], summary: {} },
      })
      
      expect(wrapper.vm.severityTag('high')).toBe('warning')
    })

    it('returns empty string for medium', () => {
      const wrapper = mount(RiskFindings, {
        props: { findings: [], summary: {} },
      })
      
      expect(wrapper.vm.severityTag('medium')).toBe('')
    })

    it('returns info for low', () => {
      const wrapper = mount(RiskFindings, {
        props: { findings: [], summary: {} },
      })
      
      expect(wrapper.vm.severityTag('low')).toBe('info')
    })
  })

  // ═══════════════════════════════════════════════════════════════════
  // 4. RISK TYPE TAG HELPER
  // ═══════════════════════════════════════════════════════════════════

  describe('riskTypeTag helper', () => {
    it('returns danger for deadlock types', () => {
      const wrapper = mount(RiskFindings, {
        props: { findings: [], summary: {} },
      })
      
      expect(wrapper.vm.riskTypeTag('deadlock_potential')).toBe('danger')
      expect(wrapper.vm.riskTypeTag('cross_function_deadlock')).toBe('danger')
    })

    it('returns danger for race types', () => {
      const wrapper = mount(RiskFindings, {
        props: { findings: [], summary: {} },
      })
      
      expect(wrapper.vm.riskTypeTag('race_condition')).toBe('danger')
    })

    it('returns warning for leak/resource types', () => {
      const wrapper = mount(RiskFindings, {
        props: { findings: [], summary: {} },
      })
      
      expect(wrapper.vm.riskTypeTag('resource_leak')).toBe('warning')
      expect(wrapper.vm.riskTypeTag('memory_leak')).toBe('warning')
    })

    it('returns primary for protocol types', () => {
      const wrapper = mount(RiskFindings, {
        props: { findings: [], summary: {} },
      })
      
      expect(wrapper.vm.riskTypeTag('protocol_error')).toBe('primary')
    })

    it('returns empty string for other types', () => {
      const wrapper = mount(RiskFindings, {
        props: { findings: [], summary: {} },
      })
      
      expect(wrapper.vm.riskTypeTag('boundary_miss')).toBe('')
    })
  })

  // ═══════════════════════════════════════════════════════════════════
  // 5. DETAIL DIALOG
  // ═══════════════════════════════════════════════════════════════════

  describe('detail dialog', () => {
    it('opens dialog on showDetail', async () => {
      const wrapper = mount(RiskFindings, {
        props: { findings: mockFindings, summary: mockSummary },
      })
      
      expect(wrapper.vm.dialogVisible).toBe(false)
      
      wrapper.vm.showDetail(mockFindings[0])
      
      expect(wrapper.vm.dialogVisible).toBe(true)
      expect(wrapper.vm.selectedFinding).toEqual(mockFindings[0])
    })

    it('sets selected finding correctly', () => {
      const wrapper = mount(RiskFindings, {
        props: { findings: mockFindings, summary: mockSummary },
      })
      
      const finding = mockFindings[1]
      wrapper.vm.showDetail(finding)
      
      expect(wrapper.vm.selectedFinding.finding_id).toBe('RF-002')
      expect(wrapper.vm.selectedFinding.risk_type).toBe('resource_leak')
    })
  })

  // ═══════════════════════════════════════════════════════════════════
  // 6. EDGE CASES
  // ═══════════════════════════════════════════════════════════════════

  describe('edge cases', () => {
    it('handles null findings prop', () => {
      const wrapper = mount(RiskFindings, {
        props: { findings: null, summary: {} },
      })
      
      expect(wrapper.vm.filteredFindings).toEqual([])
    })

    it('handles findings without call_chain', () => {
      const findingsNoChain = [
        { finding_id: 'RF-X', risk_type: 'test', severity: 'low', description: 'No chain' }
      ]
      
      const wrapper = mount(RiskFindings, {
        props: { findings: findingsNoChain, summary: {} },
      })
      
      // Should not crash when filtering by call chain keyword
      wrapper.vm.searchKeyword = 'something'
      expect(wrapper.vm.filteredFindings).toEqual([])
    })

    it('handles findings without description', () => {
      const findingsNoDesc = [
        { finding_id: 'RF-Y', risk_type: 'test', severity: 'low' }
      ]
      
      const wrapper = mount(RiskFindings, {
        props: { findings: findingsNoDesc, summary: {} },
      })
      
      wrapper.vm.searchKeyword = 'test'
      expect(wrapper.vm.filteredFindings).toEqual([])
    })
  })
})
