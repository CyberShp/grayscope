<template>
  <div class="gs-protocol-sm">
    <div v-if="!hasData" class="gs-empty">
      <el-empty description="暂无协议状态机数据" />
    </div>

    <template v-else>
      <div class="gs-psm-tabs">
        <el-radio-group v-model="viewMode" size="small">
          <el-radio-button value="diagram">状态图</el-radio-button>
          <el-radio-button value="table">状态表</el-radio-button>
          <el-radio-button value="mermaid">Mermaid 源码</el-radio-button>
        </el-radio-group>
      </div>

      <!-- 状态图视图 -->
      <div v-if="viewMode === 'diagram'" class="gs-psm-diagram">
        <v-chart :option="chartOption" style="height:400px;width:100%" autoresize />
      </div>

      <!-- 状态表视图 -->
      <div v-if="viewMode === 'table'" class="gs-psm-table">
        <h4>状态列表</h4>
        <el-table :data="statesList" stripe size="small" style="margin-bottom:20px">
          <el-table-column prop="name" label="状态名" width="200">
            <template #default="{ row }">
              <span class="gs-state-name">{{ row.name }}</span>
              <el-tag v-if="row.is_initial" type="success" size="small" style="margin-left:4px">初始</el-tag>
              <el-tag v-if="row.is_error" type="danger" size="small" style="margin-left:4px">错误</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="description" label="描述" />
        </el-table>

        <h4>状态转换</h4>
        <el-table :data="data.transitions || []" stripe size="small">
          <el-table-column prop="from" label="源状态" width="150">
            <template #default="{ row }">
              <span class="gs-state-name">{{ row.from }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="to" label="目标状态" width="150">
            <template #default="{ row }">
              <span class="gs-state-name">{{ row.to }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="action" label="触发动作" width="200" />
          <el-table-column prop="condition" label="条件" />
        </el-table>
      </div>

      <!-- Mermaid 源码 -->
      <div v-if="viewMode === 'mermaid'" class="gs-psm-mermaid">
        <el-input
          type="textarea"
          :model-value="data.mermaid || ''"
          :rows="15"
          readonly
          class="gs-mermaid-code"
        />
        <el-button type="primary" plain size="small" @click="copyMermaid" style="margin-top:8px">
          <el-icon><CopyDocument /></el-icon> 复制代码
        </el-button>
        <div class="gs-mermaid-hint">
          可粘贴到 Mermaid Live Editor 或支持 Mermaid 的文档工具中查看
        </div>
      </div>
    </template>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import { CopyDocument } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { use } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import { GraphChart } from 'echarts/charts'
import { TooltipComponent } from 'echarts/components'
import VChart from 'vue-echarts'

use([CanvasRenderer, GraphChart, TooltipComponent])

const props = defineProps({
  data: { type: Object, default: () => ({}) },
})

const viewMode = ref('diagram')

function normalizeStates(raw) {
  if (!raw) return []
  if (Array.isArray(raw)) return raw
  return Object.values(raw)
}

const statesList = computed(() => normalizeStates(props.data.states))

const hasData = computed(() => 
  (statesList.value.length > 0) || (props.data.transitions?.length > 0) || props.data.mermaid
)

const chartOption = computed(() => {
  const states = statesList.value
  const transitions = props.data.transitions || []

  const nodes = states.map(s => ({
    name: s.name,
    symbolSize: s.is_initial ? 50 : (s.is_error ? 40 : 35),
    itemStyle: {
      color: s.is_initial ? '#67C23A' : (s.is_error ? '#F56C6C' : '#409EFF'),
    },
    label: {
      show: true,
      fontSize: 11,
      fontWeight: s.is_initial ? 'bold' : 'normal',
    },
  }))

  const links = transitions.map(t => ({
    source: t.from,
    target: t.to,
    label: {
      show: true,
      formatter: t.action || '',
      fontSize: 9,
      color: '#666',
    },
    lineStyle: {
      color: t.condition ? '#E6A23C' : '#909399',
      width: 1.5,
      type: t.condition ? 'dashed' : 'solid',
    },
  }))

  return {
    tooltip: {
      trigger: 'item',
      formatter: (params) => {
        if (params.dataType === 'node') {
          const state = states.find(s => s.name === params.data.name)
          let html = `<b>${params.data.name}</b>`
          if (state?.is_initial) html += ' (初始状态)'
          if (state?.is_error) html += ' (错误状态)'
          if (state?.description) html += `<br/>${state.description}`
          return html
        }
        if (params.dataType === 'edge') {
          const trans = transitions.find(t => t.from === params.data.source && t.to === params.data.target)
          let html = `${params.data.source} → ${params.data.target}`
          if (trans?.action) html += `<br/>动作: ${trans.action}`
          if (trans?.condition) html += `<br/>条件: ${trans.condition}`
          return html
        }
        return ''
      },
    },
    series: [{
      type: 'graph',
      layout: 'circular',
      roam: true,
      circular: { rotateLabel: false },
      edgeSymbol: ['none', 'arrow'],
      edgeSymbolSize: 10,
      lineStyle: { curveness: 0.2 },
      data: nodes,
      links: links,
      animation: true,
    }],
  }
})

function copyMermaid() {
  navigator.clipboard.writeText(props.data.mermaid || '')
    .then(() => ElMessage.success('已复制到剪贴板'))
    .catch(() => ElMessage.error('复制失败'))
}
</script>

<style scoped>
.gs-protocol-sm {
  padding: 8px;
}
.gs-psm-tabs {
  margin-bottom: 16px;
}
.gs-psm-diagram {
  border: 1px solid var(--el-border-color);
  border-radius: 4px;
  padding: 8px;
}
.gs-psm-table h4 {
  margin: 0 0 8px 0;
  font-size: 14px;
  color: var(--el-text-color-primary);
}
.gs-state-name {
  font-family: monospace;
  font-weight: 500;
}
.gs-mermaid-code {
  font-family: monospace;
}
.gs-mermaid-hint {
  margin-top: 8px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.gs-empty {
  padding: 40px;
}
</style>
