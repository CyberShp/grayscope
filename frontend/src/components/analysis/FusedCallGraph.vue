<template>
  <div class="gs-fused-callgraph">
    <div class="gs-cg-toolbar">
      <el-input v-model="searchTerm" placeholder="搜索函数..." clearable style="width:200px" size="small" />
      <el-checkbox-group v-model="filters" size="small">
        <el-checkbox-button value="entry">入口点</el-checkbox-button>
        <el-checkbox-button value="branches">有分支</el-checkbox-button>
        <el-checkbox-button value="locks">有锁操作</el-checkbox-button>
        <el-checkbox-button value="risks">有风险</el-checkbox-button>
      </el-checkbox-group>
    </div>
    <div class="gs-cg-legend">
      <span class="gs-cg-legend-item"><span class="gs-cg-dot" style="background:#D50000"></span>入口点</span>
      <span class="gs-cg-legend-item"><span class="gs-cg-dot" style="background:#4B9FD5"></span>普通函数</span>
      <span class="gs-cg-legend-item"><span class="gs-cg-dot" style="background:#E57F00"></span>有风险</span>
      <span class="gs-cg-legend-item"><span class="gs-cg-dot" style="background:#9C27B0"></span>有锁操作</span>
    </div>
    <el-empty v-if="filteredNodes.length === 0" description="没有符合筛选条件的函数" style="height:300px" />
    <v-chart v-else :option="chartOption" style="height:500px;width:100%" autoresize ref="chartRef" />
    <div class="gs-cg-stats">
      <el-tag type="info">函数: {{ data.nodes?.length || 0 }}</el-tag>
      <el-tag type="info">调用关系: {{ data.edges?.length || 0 }}</el-tag>
      <el-tag type="success">入口点: {{ entryCount }}</el-tag>
    </div>
  </div>
</template>

<script setup>
import { computed, ref } from 'vue'
import { use } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import { GraphChart } from 'echarts/charts'
import { TooltipComponent, LegendComponent } from 'echarts/components'
import VChart from 'vue-echarts'

use([CanvasRenderer, GraphChart, TooltipComponent, LegendComponent])

const props = defineProps({
  data: { type: Object, default: () => ({ nodes: [], edges: [] }) },
})

const searchTerm = ref('')
const filters = ref([])
const chartRef = ref(null)

const entryCount = computed(() => 
  (props.data.nodes || []).filter(n => n.isEntryPoint).length
)

const initialLayout = computed(() => 
  (props.data.nodes?.length || 0) > 30 ? 'circular' : 'force'
)

const filteredNodes = computed(() => {
  let nodes = props.data.nodes || []
  if (searchTerm.value) {
    const term = searchTerm.value.toLowerCase()
    nodes = nodes.filter(n => n.label.toLowerCase().includes(term))
  }
  if (filters.value.includes('entry')) {
    nodes = nodes.filter(n => n.isEntryPoint)
  }
  if (filters.value.includes('branches')) {
    nodes = nodes.filter(n => n.hasBranches)
  }
  if (filters.value.includes('locks')) {
    nodes = nodes.filter(n => n.hasLocks)
  }
  if (filters.value.includes('risks')) {
    nodes = nodes.filter(n => n.riskCount > 0)
  }
  return nodes
})

const filteredEdges = computed(() => {
  const nodeIds = new Set(filteredNodes.value.map(n => n.id))
  return (props.data.edges || []).filter(
    e => nodeIds.has(e.source) && nodeIds.has(e.target)
  )
})

function getNodeColor(node) {
  if (node.isEntryPoint) return '#D50000'
  if (node.riskCount > 0) return '#E57F00'
  if (node.hasLocks) return '#9C27B0'
  return '#4B9FD5'
}

function getNodeSize(node) {
  if (node.isEntryPoint) return 45
  if (node.riskCount > 0) return 35
  return 25
}

const chartOption = computed(() => {
  const nodes = filteredNodes.value.map(n => ({
    name: n.label,
    id: n.id,
    symbolSize: getNodeSize(n),
    itemStyle: { color: getNodeColor(n) },
    label: {
      show: filteredNodes.value.length < 50,
      fontSize: 10,
      formatter: (p) => {
        const name = p.data.name
        return name.length > 20 ? name.slice(0, 18) + '…' : name
      },
    },
    _raw: n,
  }))

  const links = filteredEdges.value.map(e => ({
    source: e.source,
    target: e.target,
    lineStyle: {
      color: e.branchContext ? '#E57F00' : '#999',
      width: e.locksHeld?.length ? 2 : 1,
      type: e.branchContext ? 'dashed' : 'solid',
    },
  }))

  return {
    tooltip: {
      trigger: 'item',
      formatter: (params) => {
        if (params.dataType === 'node') {
          const n = params.data._raw
          let html = `<b>${n.label}</b><br/>`
          html += `文件: ${n.file || '-'}<br/>`
          if (n.isEntryPoint) html += `入口类型: ${n.entryType || '-'}<br/>`
          if (n.riskCount > 0) html += `<span style="color:#E57F00">风险数: ${n.riskCount}</span><br/>`
          if (n.hasBranches) html += '有分支逻辑<br/>'
          if (n.hasLocks) html += '<span style="color:#9C27B0">有锁操作</span><br/>'
          if (n.hasProtocol) html += '有协议操作<br/>'
          return html
        }
        return ''
      },
    },
    series: [{
      type: 'graph',
      layout: initialLayout.value,
      roam: true,
      draggable: true,
      force: { repulsion: 400, gravity: 0.1, edgeLength: [100, 200] },
      circular: { rotateLabel: false },
      edgeSymbol: ['none', 'arrow'],
      edgeSymbolSize: 8,
      lineStyle: { curveness: 0.2 },
      data: nodes,
      links: links,
      animation: true,
      animationDuration: 500,
    }],
  }
})
</script>

<style scoped>
.gs-fused-callgraph {
  background: var(--gs-surface, #fff);
  border-radius: var(--gs-radius-md, 8px);
  padding: 16px;
}
.gs-cg-toolbar {
  display: flex;
  gap: 16px;
  align-items: center;
  margin-bottom: 12px;
  flex-wrap: wrap;
}
.gs-cg-legend {
  display: flex;
  gap: 16px;
  margin-bottom: 8px;
}
.gs-cg-legend-item {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.gs-cg-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
}
.gs-cg-stats {
  display: flex;
  gap: 8px;
  margin-top: 12px;
}
</style>
