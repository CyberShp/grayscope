<template>
  <div class="gs-callgraph">
    <div class="gs-cg-header">
      <span class="gs-cg-title">{{ title }}</span>
      <span class="gs-cg-legend">
        <span class="gs-cg-legend-item"><span class="gs-cg-dot" style="background:#D50000"></span>{{ isImpact ? '变更函数' : '中心函数' }}</span>
        <span v-if="isImpact" class="gs-cg-legend-item"><span class="gs-cg-dot" style="background:#4B9FD5"></span>上游调用者</span>
        <span class="gs-cg-legend-item"><span class="gs-cg-dot" style="background:#E57F00"></span>{{ isImpact ? '下游被调用' : '被调用函数' }}</span>
        <span v-if="!isImpact" class="gs-cg-legend-item"><span class="gs-cg-dot" style="background:#4B9FD5"></span>间接调用</span>
      </span>
    </div>
    <v-chart :option="chartOption" :style="{ height: chartHeight + 'px', width: '100%' }" autoresize />
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { use } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import { GraphChart } from 'echarts/charts'
import { TooltipComponent } from 'echarts/components'
import VChart from 'vue-echarts'

use([CanvasRenderer, GraphChart, TooltipComponent])

const props = defineProps({
  evidence: { type: Object, default: () => ({}) },
  finding: { type: Object, default: () => ({}) },
  moduleId: { type: String, default: '' },
})

const isImpact = computed(() => props.moduleId === 'diff_impact')

const title = computed(() =>
  isImpact.value ? '变更影响图' : '调用关系图'
)

// 图内最多显示的上游/下游节点数
const MAX_GRAPH_NODES = 12

const totalCallers = computed(() => (props.evidence.impacted_callers || []).length)
const totalCallees = computed(() => (props.evidence.impacted_callees || []).length)

// 动态高度：节点少时紧凑，多时适当增高
const chartHeight = computed(() => {
  if (!isImpact.value) return 320
  const n = Math.min(totalCallers.value, MAX_GRAPH_NODES) + Math.min(totalCallees.value, MAX_GRAPH_NODES) + 1
  if (n <= 6) return 280
  if (n <= 12) return 340
  return 400
})

const chartOption = computed(() => {
  const nodes = []
  const links = []
  const centerFn = props.finding.symbol_name || '中心函数'

  if (isImpact.value) {
    const changed = props.evidence.changed_symbols || [centerFn]
    const allCallers = (props.evidence.impacted_callers || []).map(c => typeof c === 'string' ? c : c.name || c)
    const allCallees = (props.evidence.impacted_callees || []).map(c => typeof c === 'string' ? c : c.name || c)
    const fallbackImpacted = (!allCallers.length && !allCallees.length) ? (props.evidence.impacted_symbols || []) : []

    const callers = allCallers.slice(0, MAX_GRAPH_NODES)
    const callees = allCallees.slice(0, MAX_GRAPH_NODES)
    const callerOverflow = allCallers.length - callers.length
    const calleeOverflow = allCallees.length - callees.length

    const addedNames = new Set()
    const srcName = (changed[0] || centerFn) + '()'

    // 变更函数节点（红色，中心）
    changed.forEach((fn) => {
      const name = fn + '()'
      if (!addedNames.has(name)) {
        addedNames.add(name)
        nodes.push({
          name,
          symbolSize: 42,
          itemStyle: { color: '#D50000', borderColor: '#fff', borderWidth: 2 },
          label: { fontSize: 12, fontWeight: 'bold', color: '#D50000' },
        })
      }
    })

    // 上游调用者（蓝色）
    callers.forEach((fn) => {
      const name = fn + '()'
      if (!addedNames.has(name)) {
        addedNames.add(name)
        nodes.push({ name, symbolSize: 24, itemStyle: { color: '#4B9FD5' } })
      }
      links.push({
        source: name, target: srcName,
        lineStyle: { color: '#4B9FD5', width: 1.5 },
        label: { show: false },
      })
    })

    if (callerOverflow > 0) {
      const overName = `还有 ${callerOverflow} 个`
      nodes.push({
        name: overName, symbolSize: 18,
        itemStyle: { color: '#B0BEC5' },
        label: { fontSize: 10, color: '#999' },
      })
      links.push({
        source: overName, target: srcName,
        lineStyle: { color: '#B0BEC5', width: 1, type: 'dashed' },
        label: { show: false },
      })
    }

    // 下游被调用（橙色）
    callees.forEach((fn) => {
      const name = fn + '()'
      if (!addedNames.has(name)) {
        addedNames.add(name)
        nodes.push({ name, symbolSize: 24, itemStyle: { color: '#E57F00' } })
      }
      links.push({
        source: srcName, target: name,
        lineStyle: { color: '#E57F00', width: 1.5 },
        label: { show: false },
      })
    })

    if (calleeOverflow > 0) {
      const overName = `还有 ${calleeOverflow} 个 ↓`
      nodes.push({
        name: overName, symbolSize: 18,
        itemStyle: { color: '#B0BEC5' },
        label: { fontSize: 10, color: '#999' },
      })
      links.push({
        source: srcName, target: overName,
        lineStyle: { color: '#B0BEC5', width: 1, type: 'dashed' },
        label: { show: false },
      })
    }

    // 旧格式 fallback
    fallbackImpacted.slice(0, MAX_GRAPH_NODES).forEach((fn) => {
      const name = (typeof fn === 'string' ? fn : fn.name || fn) + '()'
      if (!addedNames.has(name)) {
        addedNames.add(name)
        nodes.push({ name, symbolSize: 24, itemStyle: { color: '#E57F00' } })
        links.push({
          source: srcName, target: name,
          lineStyle: { color: '#E57F00', width: 1.5 },
        })
      }
    })
  } else {
    // call_graph: center → callees
    nodes.push({
      name: centerFn + '()',
      symbolSize: 50,
      itemStyle: { color: '#D50000' },
      label: { fontSize: 13, fontWeight: 'bold' },
    })

    const callees = props.evidence.callees || []
    const chain = props.evidence.chain || []

    if (chain.length > 1) {
      chain.forEach((fn, i) => {
        if (i === 0) return
        nodes.push({
          name: fn + '()',
          symbolSize: Math.max(25, 40 - i * 5),
          itemStyle: { color: i === 1 ? '#E57F00' : '#4B9FD5' },
        })
        links.push({
          source: chain[i - 1] + '()',
          target: fn + '()',
          lineStyle: { color: i === 1 ? '#E57F00' : '#4B9FD5', width: 2 },
        })
      })
    } else if (callees.length) {
      callees.forEach((fn) => {
        nodes.push({
          name: fn + '()',
          symbolSize: 30,
          itemStyle: { color: '#E57F00' },
        })
        links.push({
          source: centerFn + '()',
          target: fn + '()',
          lineStyle: { color: '#E57F00', width: 1.5 },
        })
      })
    }
  }

  // diff_impact: 使用 circular 布局（确定性、自适应容器宽度）
  if (isImpact.value) {
    return {
      tooltip: { trigger: 'item', confine: true },
      series: [{
        type: 'graph',
        layout: 'circular',
        circular: { rotateLabel: false },
        roam: false,
        label: { show: true, fontSize: 10, color: '#333', formatter: (p) => {
          const n = p.data.name
          return n.length > 16 ? n.slice(0, 14) + '…' : n
        }},
        edgeSymbol: ['none', 'arrow'],
        edgeSymbolSize: 8,
        lineStyle: { width: 1.5, curveness: 0.25, opacity: 0.7 },
        data: nodes,
        links: links,
        animation: true,
        animationDuration: 400,
      }],
    }
  }

  // call_graph: 使用 force 布局（节点少，效果好）
  return {
    tooltip: { trigger: 'item' },
    series: [{
      type: 'graph',
      layout: 'force',
      roam: true,
      draggable: true,
      force: { repulsion: 300, gravity: 0.1, edgeLength: [80, 160] },
      label: { show: true, fontSize: 11, color: '#333' },
      edgeSymbol: ['none', 'arrow'],
      edgeSymbolSize: 8,
      lineStyle: { width: 1.5, curveness: 0.15 },
      data: nodes,
      links: links,
    }],
  }
})
</script>

<style scoped>
.gs-callgraph {
  background: var(--gs-surface);
  border: 1px solid var(--gs-border);
  border-radius: var(--gs-radius-md);
  padding: 12px;
  overflow: hidden;
}
.gs-cg-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 4px;
}
.gs-cg-title {
  font-size: 12px;
  font-weight: 600;
  color: var(--gs-text-muted);
}
.gs-cg-legend {
  display: flex;
  gap: 12px;
}
.gs-cg-legend-item {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 11px;
  color: var(--gs-text-muted);
}
.gs-cg-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
}
</style>
