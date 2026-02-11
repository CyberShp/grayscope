<template>
  <div class="gs-priority-matrix">
    <div class="gs-pm-header">
      <span class="gs-pm-title">测试优先级矩阵</span>
      <span class="gs-pm-hint">右上角 = 最优先测试区域（高风险 + 高严重度）</span>
    </div>
    <v-chart :option="chartOption" style="height: 360px; width: 100%;" autoresize />
    <div class="gs-pm-quadrants">
      <div class="gs-pm-q gs-pm-q1">
        <strong>Q1 立即测试</strong>
        <span>{{ q1Count }} 项</span>
      </div>
      <div class="gs-pm-q gs-pm-q2">
        <strong>Q2 优先安排</strong>
        <span>{{ q2Count }} 项</span>
      </div>
      <div class="gs-pm-q gs-pm-q3">
        <strong>Q3 视情况安排</strong>
        <span>{{ q3Count }} 项</span>
      </div>
      <div class="gs-pm-q gs-pm-q4">
        <strong>Q4 低优先级</strong>
        <span>{{ q4Count }} 项</span>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { use } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import { ScatterChart } from 'echarts/charts'
import { TooltipComponent, GridComponent, MarkAreaComponent } from 'echarts/components'
import VChart from 'vue-echarts'

use([CanvasRenderer, ScatterChart, TooltipComponent, GridComponent, MarkAreaComponent])

const props = defineProps({
  testCases: { type: Array, default: () => [] },
})

const sevScore = { S0: 1.0, S1: 0.8, S2: 0.5, S3: 0.2 }

function parsePriority(p) {
  if (p.startsWith('P0')) return 1.0
  if (p.startsWith('P1')) return 0.8
  if (p.startsWith('P2')) return 0.5
  return 0.2
}

const scatterData = computed(() =>
  props.testCases.map(tc => ({
    x: tc.risk_score || 0,
    y: parsePriority(tc.priority),
    name: tc.title,
    file: tc.target_file,
    fn: tc.target_function,
    priority: tc.priority,
    module: tc.module_display_name,
  }))
)

const q1Count = computed(() => scatterData.value.filter(d => d.x >= 0.5 && d.y >= 0.5).length)
const q2Count = computed(() => scatterData.value.filter(d => d.x < 0.5 && d.y >= 0.5).length)
const q3Count = computed(() => scatterData.value.filter(d => d.x >= 0.5 && d.y < 0.5).length)
const q4Count = computed(() => scatterData.value.filter(d => d.x < 0.5 && d.y < 0.5).length)

const chartOption = computed(() => ({
  tooltip: {
    trigger: 'item',
    formatter: (p) => {
      const d = p.data
      return `<b>${d.name}</b><br/>风险: ${(d.x * 100).toFixed(0)}%<br/>优先级: ${d.priority}<br/>模块: ${d.module}<br/>${d.fn ? d.fn + '()' : d.file}`
    },
  },
  grid: { left: 60, right: 20, top: 20, bottom: 50 },
  xAxis: {
    name: '风险评分',
    nameLocation: 'center',
    nameGap: 30,
    type: 'value',
    min: 0, max: 1,
    axisLabel: { formatter: v => (v * 100).toFixed(0) + '%' },
    splitLine: { lineStyle: { type: 'dashed', color: '#eee' } },
  },
  yAxis: {
    name: '严重度/优先级',
    nameLocation: 'center',
    nameGap: 40,
    type: 'value',
    min: 0, max: 1,
    axisLabel: {
      formatter: v => {
        if (v >= 0.9) return 'P0'
        if (v >= 0.6) return 'P1'
        if (v >= 0.35) return 'P2'
        return 'P3'
      },
    },
    splitLine: { lineStyle: { type: 'dashed', color: '#eee' } },
  },
  series: [{
    type: 'scatter',
    symbolSize: 10,
    data: scatterData.value.map(d => ({
      value: [d.x, d.y],
      ...d,
      itemStyle: {
        color: d.x >= 0.5 && d.y >= 0.5 ? '#D50000'
          : d.x >= 0.5 || d.y >= 0.5 ? '#E57F00'
          : '#4B9FD5',
      },
    })),
    markArea: {
      silent: true,
      data: [
        [{ xAxis: 0.5, yAxis: 0.5, itemStyle: { color: 'rgba(213,0,0,0.04)' } }, { xAxis: 1, yAxis: 1 }],
        [{ xAxis: 0, yAxis: 0.5, itemStyle: { color: 'rgba(229,127,0,0.03)' } }, { xAxis: 0.5, yAxis: 1 }],
        [{ xAxis: 0.5, yAxis: 0, itemStyle: { color: 'rgba(229,127,0,0.02)' } }, { xAxis: 1, yAxis: 0.5 }],
      ],
    },
  }],
}))
</script>

<style scoped>
.gs-priority-matrix {
  background: var(--gs-surface);
  border: 1px solid var(--gs-border);
  border-radius: var(--gs-radius-md);
  padding: 16px;
}
.gs-pm-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}
.gs-pm-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--gs-text-primary);
}
.gs-pm-hint {
  font-size: 11px;
  color: var(--gs-text-muted);
}
.gs-pm-quadrants {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px;
  margin-top: 12px;
}
.gs-pm-q {
  padding: 8px 12px;
  border-radius: var(--gs-radius-sm);
  font-size: 12px;
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.gs-pm-q strong { font-size: 12px; }
.gs-pm-q span { font-family: var(--gs-font-mono); font-weight: 700; }
.gs-pm-q1 { background: rgba(213,0,0,0.06); color: var(--gs-risk-critical); }
.gs-pm-q2 { background: rgba(229,127,0,0.06); color: var(--gs-risk-medium); }
.gs-pm-q3 { background: rgba(229,127,0,0.04); color: var(--gs-risk-medium); }
.gs-pm-q4 { background: rgba(75,159,213,0.06); color: var(--gs-primary); }
</style>
