<template>
  <div class="gs-measures-layout">
    <!-- 左侧度量分类 -->
    <aside class="gs-measures-nav">
      <div class="gs-facet-title" style="padding: 12px 16px 8px;">度量分类</div>
      <div
        v-for="cat in categories"
        :key="cat.id"
        class="gs-facet-item"
        :class="{ active: selectedCategory === cat.id }"
        @click="selectedCategory = cat.id"
        style="padding: 8px 16px;"
      >
        <span>{{ cat.label }}</span>
        <span class="gs-facet-count">{{ cat.count }}</span>
      </div>
    </aside>

    <!-- 主区域 -->
    <div class="gs-measures-main">
      <!-- 度量概要 -->
      <div class="gs-stat-row gs-section">
        <div class="gs-stat-card" v-for="s in summaryStats" :key="s.label">
          <div class="gs-stat-label">{{ s.label }}</div>
          <div class="gs-stat-value" :style="{ color: s.color }">{{ s.value }}</div>
        </div>
      </div>

      <!-- 视图切换 -->
      <div class="gs-measures-toolbar gs-section">
        <el-radio-group v-model="viewMode" size="small">
          <el-radio-button value="treemap">Treemap</el-radio-button>
          <el-radio-button value="list">列表</el-radio-button>
        </el-radio-group>
        <span class="gs-result-count">{{ filteredFiles.length }} 个文件</span>
      </div>

      <!-- Treemap 视图 -->
      <div v-if="viewMode === 'treemap'" class="gs-card gs-section">
        <v-chart v-if="treemapOption" :option="treemapOption" autoresize style="height: 500px;" @click="onTreemapClick" />
        <el-empty v-else description="暂无 Treemap 数据" :image-size="80" />
      </div>

      <!-- 列表视图 -->
      <div v-if="viewMode === 'list'" class="gs-card gs-section">
        <el-table :data="filteredFiles" size="small" class="gs-table" :default-sort="{ prop: 'risk_score', order: 'descending' }">
          <el-table-column label="文件路径" min-width="300">
            <template #default="{ row }">
              <router-link
                :to="`/projects/${projectId}/code?path=${encodeURIComponent(row.file_path)}`"
                style="font-family: var(--gs-font-mono); font-size: 12px;"
              >{{ row.file_path }}</router-link>
            </template>
          </el-table-column>
          <el-table-column label="风险评分" width="140" prop="risk_score" sortable>
            <template #default="{ row }">
              <div style="display: flex; align-items: center; gap: 8px;">
                <div class="gs-risk-bar" style="flex: 1;">
                  <div class="gs-risk-bar-fill" :style="{ width: (row.risk_score * 100) + '%', background: riskColor(row.risk_score) }"></div>
                </div>
                <span style="font-size: 12px; font-weight: 600; min-width: 32px;">{{ (row.risk_score * 100).toFixed(0) }}%</span>
              </div>
            </template>
          </el-table-column>
          <el-table-column label="发现数" width="80" prop="finding_count" sortable align="center" />
          <el-table-column label="函数数" width="80" prop="function_count" align="center" />
          <el-table-column label="代码行" width="80" prop="lines" align="center" />
          <el-table-column label="测试建议" width="100" align="center">
            <template #default="{ row }">
              <el-tag v-if="row.risk_score >= 0.7" type="danger" size="small">需测试</el-tag>
              <el-tag v-else-if="row.risk_score >= 0.4" type="warning" size="small">建议测试</el-tag>
              <el-tag v-else type="success" size="small">低风险</el-tag>
            </template>
          </el-table-column>
        </el-table>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import { useRouter } from 'vue-router'
import { use } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import { TreemapChart } from 'echarts/charts'
import { TooltipComponent } from 'echarts/components'
import VChart from 'vue-echarts'
import { useRiskColor } from '../../composables/useRiskColor.js'
import { useModuleNames } from '../../composables/useModuleNames.js'
import api from '../../api.js'

use([CanvasRenderer, TreemapChart, TooltipComponent])

const props = defineProps({
  projectId: [String, Number],
})

const router = useRouter()
const { riskColor } = useRiskColor()
const { getDisplayName } = useModuleNames()

const viewMode = ref('treemap')
const selectedCategory = ref('all')
const filesData = ref([])

const categories = computed(() => {
  const all = { id: 'all', label: '全部', count: filesData.value.length }
  const moduleMap = {}
  filesData.value.forEach(f => {
    (f.modules || []).forEach(m => {
      moduleMap[m] = (moduleMap[m] || 0) + 1
    })
  })
  const mods = Object.entries(moduleMap).map(([id, count]) => ({ id, label: getDisplayName(id), count }))
  return [all, ...mods]
})

const summaryStats = computed(() => {
  const files = filesData.value
  const totalFindings = files.reduce((s, f) => s + (f.finding_count || 0), 0)
  const avgRisk = files.length ? files.reduce((s, f) => s + (f.risk_score || 0), 0) / files.length : 0
  const highRisk = files.filter(f => (f.risk_score || 0) >= 0.7).length
  return [
    { label: '分析文件数', value: files.length, color: '#1D1D1D' },
    { label: '总发现数', value: totalFindings, color: totalFindings > 0 ? '#D4333F' : '#1D1D1D' },
    { label: '平均风险', value: (avgRisk * 100).toFixed(0) + '%', color: riskColor(avgRisk) },
    { label: '高风险文件', value: highRisk, color: highRisk > 0 ? '#D4333F' : '#00AA00' },
  ]
})

const filteredFiles = computed(() => {
  if (selectedCategory.value === 'all') return filesData.value
  return filesData.value.filter(f => (f.modules || []).includes(selectedCategory.value))
})

const treemapOption = computed(() => {
  if (!filteredFiles.value.length) return null
  const data = filteredFiles.value.map(f => ({
    name: f.file_path.split('/').pop(),
    value: f.lines || f.function_count || 1,
    risk_score: f.risk_score || 0,
    file_path: f.file_path,
    finding_count: f.finding_count || 0,
    itemStyle: {
      color: riskColor(f.risk_score || 0),
    },
  }))
  return {
    tooltip: {
      formatter: p => {
        const d = p.data
        return `<b>${d.file_path}</b><br/>风险: ${(d.risk_score * 100).toFixed(0)}%<br/>发现: ${d.finding_count}<br/>行数: ${d.value}`
      },
    },
    series: [{
      type: 'treemap',
      data,
      width: '100%',
      height: '100%',
      roam: false,
      nodeClick: false,
      breadcrumb: { show: false },
      label: {
        show: true,
        formatter: '{b}',
        fontSize: 11,
        color: '#fff',
      },
      itemStyle: {
        borderColor: '#fff',
        borderWidth: 2,
        gapWidth: 2,
      },
      levels: [{
        itemStyle: { borderColor: '#fff', borderWidth: 2, gapWidth: 2 },
      }],
    }],
  }
})

function onTreemapClick(params) {
  if (params.data?.file_path) {
    router.push(`/projects/${props.projectId}/code?path=${encodeURIComponent(params.data.file_path)}`)
  }
}

async function loadData() {
  try {
    const data = await api.getProjectMeasures(props.projectId)
    filesData.value = data?.files || []
  } catch {
    filesData.value = []
  }
}

onMounted(loadData)
watch(() => props.projectId, loadData)
</script>

<style scoped>
.gs-measures-layout {
  display: flex;
  height: 100%;
}

.gs-measures-nav {
  width: 220px;
  flex-shrink: 0;
  border-right: 1px solid var(--gs-border);
  background: var(--gs-surface);
  overflow-y: auto;
}

.gs-measures-main {
  flex: 1;
  padding: var(--gs-space-lg);
  overflow-y: auto;
}

.gs-stat-row {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: var(--gs-space-md);
}

.gs-measures-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.gs-result-count {
  font-size: var(--gs-font-sm);
  color: var(--gs-text-muted);
}

.gs-risk-bar {
  height: 6px;
  background: var(--gs-border-light);
  border-radius: 3px;
  overflow: hidden;
}
.gs-risk-bar-fill {
  height: 100%;
  border-radius: 3px;
}
</style>
