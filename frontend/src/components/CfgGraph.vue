<template>
  <div class="gs-cfg-graph">
    <div class="gs-cfg-header">
      <span class="gs-cfg-title">控制流图 (CFG)</span>
      <span class="gs-cfg-legend">
        <span class="gs-cfg-legend-item"><span class="gs-cfg-dot gs-cfg-dot-normal"></span>正常路径</span>
        <span class="gs-cfg-legend-item"><span class="gs-cfg-dot gs-cfg-dot-error"></span>错误路径</span>
        <span class="gs-cfg-legend-item"><span class="gs-cfg-dot gs-cfg-dot-cleanup"></span>清理路径</span>
        <span class="gs-cfg-legend-item"><span class="gs-cfg-dot gs-cfg-dot-uncovered"></span>未覆盖</span>
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
})

const pathType = computed(() => props.evidence.path_type || 'normal')
const branchId = computed(() => props.evidence.branch_id || '')
const conditionExpr = computed(() => props.evidence.condition_expr || '')

// 从 evidence 中的 pred/succ 节点和分支信息构建简化 CFG
const graphData = computed(() => {
  const funcName = props.finding.symbol_name || '函数入口'
  const preds = props.evidence.pred_nodes || []
  const succs = props.evidence.succ_nodes || []
  const pt = pathType.value

  // 构建节点
  const nodes = []
  const links = []

  // 入口节点
  nodes.push({
    name: 'entry',
    label: funcName + '()',
    category: 'normal',
    symbolSize: 40,
    x: 200, y: 30,
  })

  // 条件节点
  if (conditionExpr.value) {
    nodes.push({
      name: 'condition',
      label: conditionExpr.value,
      category: 'condition',
      symbolSize: 50,
      x: 200, y: 120,
      symbol: 'diamond',
    })
    links.push({ source: 'entry', target: 'condition' })

    // True 分支（正常路径）
    nodes.push({
      name: 'true_branch',
      label: '正常处理',
      category: 'normal',
      symbolSize: 35,
      x: 100, y: 220,
    })
    links.push({
      source: 'condition',
      target: 'true_branch',
      label: { show: true, formatter: 'true' },
    })

    // False 分支（目标路径 — 取决于 path_type）
    nodes.push({
      name: 'false_branch',
      label: pt === 'error' ? '错误处理' : pt === 'cleanup' ? '资源清理' : '分支路径',
      category: pt === 'error' ? 'error' : pt === 'cleanup' ? 'cleanup' : 'uncovered',
      symbolSize: 35,
      x: 300, y: 220,
    })
    links.push({
      source: 'condition',
      target: 'false_branch',
      label: { show: true, formatter: 'false' },
      lineStyle: { type: 'dashed', color: pt === 'error' ? '#D50000' : '#E57F00' },
    })

    // 后续节点
    if (pt === 'error') {
      nodes.push({
        name: 'error_return',
        label: '错误返回',
        category: 'error',
        symbolSize: 30,
        x: 300, y: 310,
      })
      links.push({ source: 'false_branch', target: 'error_return' })
    } else if (pt === 'cleanup') {
      nodes.push({
        name: 'cleanup_action',
        label: '释放资源',
        category: 'cleanup',
        symbolSize: 30,
        x: 300, y: 310,
      })
      links.push({ source: 'false_branch', target: 'cleanup_action' })
    }

    // 正常出口
    nodes.push({
      name: 'exit',
      label: '返回',
      category: 'normal',
      symbolSize: 30,
      x: 200, y: 380,
    })
    links.push({ source: 'true_branch', target: 'exit' })
    if (pt === 'error') {
      links.push({ source: 'error_return', target: 'exit', lineStyle: { type: 'dotted' } })
    } else if (pt === 'cleanup') {
      links.push({ source: 'cleanup_action', target: 'exit', lineStyle: { type: 'dotted' } })
    } else {
      links.push({ source: 'false_branch', target: 'exit' })
    }
  } else {
    // 无条件表达式时显示简化图
    nodes.push({
      name: 'target',
      label: branchId.value || '目标分支',
      category: pt === 'error' ? 'error' : pt === 'cleanup' ? 'cleanup' : 'uncovered',
      symbolSize: 40,
      x: 200, y: 120,
    })
    links.push({ source: 'entry', target: 'target' })

    nodes.push({
      name: 'exit',
      label: '返回',
      category: 'normal',
      symbolSize: 30,
      x: 200, y: 220,
    })
    links.push({ source: 'target', target: 'exit' })
  }

  return { nodes, links }
})

const chartHeight = computed(() => conditionExpr.value ? 420 : 260)

const categoryColors = {
  normal: '#4B9FD5',
  condition: '#8B5CF6',
  error: '#D50000',
  cleanup: '#E57F00',
  uncovered: '#999',
}

const chartOption = computed(() => ({
  tooltip: {
    trigger: 'item',
    formatter: (params) => {
      if (params.dataType === 'node') return params.data.label
      return ''
    }
  },
  series: [{
    type: 'graph',
    layout: 'none',
    roam: false,
    label: {
      show: true,
      formatter: '{b}',
      fontSize: 11,
      color: '#333',
    },
    edgeLabel: { fontSize: 10, color: '#666' },
    categories: [
      { name: 'normal', itemStyle: { color: categoryColors.normal } },
      { name: 'condition', itemStyle: { color: categoryColors.condition } },
      { name: 'error', itemStyle: { color: categoryColors.error } },
      { name: 'cleanup', itemStyle: { color: categoryColors.cleanup } },
      { name: 'uncovered', itemStyle: { color: categoryColors.uncovered } },
    ],
    data: graphData.value.nodes.map(n => ({
      ...n,
      name: n.label,
      category: ['normal', 'condition', 'error', 'cleanup', 'uncovered'].indexOf(n.category),
      itemStyle: { color: categoryColors[n.category] || '#4B9FD5' },
    })),
    links: graphData.value.links.map(l => ({
      ...l,
      source: graphData.value.nodes.find(n => n.name === l.source)?.label,
      target: graphData.value.nodes.find(n => n.name === l.target)?.label,
      lineStyle: {
        color: '#999',
        curveness: 0,
        ...(l.lineStyle || {}),
      },
    })),
    lineStyle: { color: '#999', width: 2 },
    edgeSymbol: ['none', 'arrow'],
    edgeSymbolSize: 8,
  }],
}))
</script>

<style scoped>
.gs-cfg-graph {
  background: var(--gs-surface);
  border: 1px solid var(--gs-border);
  border-radius: var(--gs-radius-md);
  padding: 12px;
}
.gs-cfg-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}
.gs-cfg-title {
  font-size: 12px;
  font-weight: 600;
  color: var(--gs-text-muted);
}
.gs-cfg-legend {
  display: flex;
  gap: 12px;
}
.gs-cfg-legend-item {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 11px;
  color: var(--gs-text-muted);
}
.gs-cfg-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
}
.gs-cfg-dot-normal { background: #4B9FD5; }
.gs-cfg-dot-error { background: #D50000; }
.gs-cfg-dot-cleanup { background: #E57F00; }
.gs-cfg-dot-uncovered { background: #999; }
</style>
