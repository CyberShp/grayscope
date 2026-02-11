<template>
  <div class="gs-callgraph">
    <div class="gs-cg-header">
      <span class="gs-cg-title">{{ title }}</span>
      <span class="gs-cg-legend">
        <span class="gs-cg-legend-item"><span class="gs-cg-dot" style="background:#D50000"></span>{{ isImpact ? '变更函数' : '中心函数' }}</span>
        <span class="gs-cg-legend-item"><span class="gs-cg-dot" style="background:#E57F00"></span>{{ isImpact ? '受影响函数' : '被调用函数' }}</span>
        <span v-if="!isImpact" class="gs-cg-legend-item"><span class="gs-cg-dot" style="background:#4B9FD5"></span>间接调用</span>
      </span>
    </div>
    <v-chart :option="chartOption" :style="{ height: '320px', width: '100%' }" autoresize />
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

const chartOption = computed(() => {
  const nodes = []
  const links = []
  const centerFn = props.finding.symbol_name || '中心函数'

  if (isImpact.value) {
    // diff_impact: changed → impacted
    const changed = props.evidence.changed_symbols || [centerFn]
    const impacted = props.evidence.impacted_symbols || []

    changed.forEach((fn, i) => {
      nodes.push({
        name: fn + '()',
        symbolSize: 45,
        itemStyle: { color: '#D50000' },
        label: { fontSize: 12, fontWeight: 'bold' },
      })
    })

    impacted.forEach((fn, i) => {
      nodes.push({
        name: fn + '()',
        symbolSize: 32,
        itemStyle: { color: '#E57F00' },
      })
      // 连接到最近的 changed 函数
      const src = changed[0] || centerFn
      links.push({
        source: src + '()',
        target: fn + '()',
        lineStyle: { color: '#E57F00', width: 2 },
      })
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
      // 展示调用链
      chain.forEach((fn, i) => {
        if (i === 0) return // 已经是 center
        nodes.push({
          name: fn + '()',
          symbolSize: Math.max(25, 40 - i * 5),
          itemStyle: { color: i === 1 ? '#E57F00' : '#4B9FD5' },
        })
        const src = chain[i - 1] + '()'
        links.push({
          source: src,
          target: fn + '()',
          lineStyle: { color: i === 1 ? '#E57F00' : '#4B9FD5', width: 2 },
        })
      })
    } else if (callees.length) {
      // 展示扇出
      callees.forEach((fn, i) => {
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

  return {
    tooltip: { trigger: 'item' },
    series: [{
      type: 'graph',
      layout: 'force',
      roam: true,
      draggable: true,
      force: {
        repulsion: 300,
        gravity: 0.1,
        edgeLength: [80, 160],
      },
      label: {
        show: true,
        fontSize: 11,
        color: '#333',
      },
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
