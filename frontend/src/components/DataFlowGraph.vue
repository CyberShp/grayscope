<template>
  <div class="gs-dfg" v-if="chainData && chainData.length > 1">
    <div class="gs-dfg-header">
      <span class="gs-dfg-title">数据流传播图</span>
      <span class="gs-dfg-legend">
        <span class="gs-dfg-legend-item"><span class="gs-dfg-dot" style="background:#00AA00;"></span>入口</span>
        <span class="gs-dfg-legend-item"><span class="gs-dfg-dot" style="background:#E57F00;"></span>变换</span>
        <span class="gs-dfg-legend-item"><span class="gs-dfg-dot" style="background:#D50000;"></span>风险点</span>
        <span class="gs-dfg-legend-item"><span class="gs-dfg-dot" style="background:#4B9FD5;"></span>传递</span>
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
  /** 传播链数组: [{ function, param, transform, transform_expr }, ...] */
  chain: { type: Array, default: () => [] },
  /** 是否来自外部输入 */
  isExternal: { type: Boolean, default: false },
  /** 高亮风险的节点索引 (默认最后一个) */
  sinkIndex: { type: Number, default: -1 },
})

const chainData = computed(() => props.chain || [])

const chartHeight = computed(() => {
  const n = chainData.value.length
  return Math.max(200, Math.min(n * 80 + 60, 600))
})

const chartOption = computed(() => {
  const chain = chainData.value
  if (!chain.length) return {}

  const nodes = []
  const links = []
  const n = chain.length
  const sinkIdx = props.sinkIndex >= 0 ? props.sinkIndex : n - 1
  const centerX = 200
  const yStart = 40
  const yGap = 70

  chain.forEach((step, i) => {
    const isEntry = i === 0
    const isSink = i === sinkIdx
    const hasTransform = step.transform && step.transform !== 'none'

    let color = '#4B9FD5'
    let size = 32
    if (isEntry) { color = '#00AA00'; size = 40; }
    else if (isSink) { color = '#D50000'; size = 40; }
    else if (hasTransform) { color = '#E57F00'; size = 36; }

    const label = `${step.function}(${step.param})`

    nodes.push({
      name: label,
      x: centerX,
      y: yStart + i * yGap,
      symbolSize: size,
      symbol: isSink ? 'diamond' : isEntry ? 'roundRect' : 'circle',
      itemStyle: {
        color,
        borderColor: isEntry && props.isExternal ? '#D50000' : 'transparent',
        borderWidth: isEntry && props.isExternal ? 3 : 0,
      },
      label: {
        show: true,
        fontSize: 11,
        color: '#333',
        fontWeight: isEntry || isSink ? 'bold' : 'normal',
        position: i % 2 === 0 ? 'right' : 'left',
      },
      tooltip: {
        formatter: () => {
          let tip = `<strong>${step.function}()</strong><br/>参数: ${step.param}`
          if (hasTransform) {
            tip += `<br/>变换: <span style="color:#E57F00">${step.transform}</span>`
            if (step.transform_expr) tip += ` (${step.transform_expr})`
          }
          if (isEntry && props.isExternal) tip += '<br/><span style="color:#D50000">⚠ 外部输入</span>'
          return tip
        },
      },
    })

    if (i > 0) {
      const prevStep = chain[i - 1]
      const prevLabel = `${prevStep.function}(${prevStep.param})`
      const hasEdgeTransform = step.transform && step.transform !== 'none'
      links.push({
        source: prevLabel,
        target: label,
        lineStyle: {
          color: hasEdgeTransform ? '#E57F00' : '#4B9FD5',
          width: hasEdgeTransform ? 3 : 2,
          type: hasEdgeTransform ? 'solid' : 'solid',
        },
        label: hasEdgeTransform ? {
          show: true,
          formatter: step.transform + (step.transform_expr ? `(${step.transform_expr})` : ''),
          fontSize: 10,
          color: '#E57F00',
        } : undefined,
      })
    }
  })

  return {
    tooltip: {
      trigger: 'item',
      confine: true,
    },
    series: [{
      type: 'graph',
      layout: 'none',
      roam: false,
      label: { show: true },
      edgeSymbol: ['none', 'arrow'],
      edgeSymbolSize: 8,
      edgeLabel: { fontSize: 10 },
      lineStyle: { curveness: 0, width: 2 },
      data: nodes,
      links: links,
      animation: true,
      animationDuration: 300,
    }],
  }
})
</script>

<style scoped>
.gs-dfg {
  background: var(--gs-surface);
  border: 1px solid var(--gs-border);
  border-radius: var(--gs-radius-md);
  padding: 12px;
}
.gs-dfg-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}
.gs-dfg-title {
  font-size: 12px;
  font-weight: 600;
  color: var(--gs-text-muted);
}
.gs-dfg-legend {
  display: flex;
  gap: 12px;
}
.gs-dfg-legend-item {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 11px;
  color: var(--gs-text-muted);
}
.gs-dfg-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
}
</style>
