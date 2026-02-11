<template>
  <div class="gs-page">
    <!-- 质量门禁 Banner -->
    <div class="gs-section">
      <div class="gs-quality-gate" :class="gatePass ? 'gs-quality-gate--pass' : 'gs-quality-gate--fail'">
        <span class="gs-quality-gate-icon">{{ gatePass ? '✓' : '✗' }}</span>
        <div>
          <div style="font-size: 15px;">质量门禁：{{ gatePass ? '通过' : '未通过' }}</div>
          <div v-if="!gatePass && gateReasons.length" style="font-size: 12px; font-weight: 400; margin-top: 4px;">
            {{ gateReasons.join('；') }}
          </div>
        </div>
      </div>
    </div>

    <!-- 风险指标卡片组 -->
    <div class="gs-stat-row gs-section">
      <div class="gs-stat-card" v-for="s in statCards" :key="s.label">
        <div class="gs-stat-label">{{ s.label }}</div>
        <div class="gs-stat-value" :style="{ color: s.color }">{{ s.value }}</div>
        <div v-if="s.sub" class="gs-stat-sub">{{ s.sub }}</div>
      </div>
    </div>

    <el-row :gutter="20">
      <!-- 模块风险概要 -->
      <el-col :span="14">
        <div class="gs-card gs-section">
          <div class="gs-card-header">
            <span class="gs-card-title">模块分析概要</span>
          </div>
          <el-table :data="moduleResults" size="small" class="gs-table">
            <el-table-column label="分析模块" min-width="160">
              <template #default="{ row }">
                <span style="font-weight: 500;">{{ getDisplayName(row.module || row.module_id) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="状态" width="90" align="center">
              <template #default="{ row }">
                <span class="gs-status-dot" :class="'gs-status-dot--' + row.status"></span>
                {{ statusLabel(row.status) }}
              </template>
            </el-table-column>
            <el-table-column label="风险评分" width="140">
              <template #default="{ row }">
                <div v-if="row.risk_score != null" style="display: flex; align-items: center; gap: 8px;">
                  <div class="gs-risk-bar">
                    <div class="gs-risk-bar-fill" :style="{ width: (row.risk_score * 100) + '%', background: riskColor(row.risk_score) }"></div>
                  </div>
                  <span style="font-size: 12px; font-weight: 600; min-width: 32px;">{{ (row.risk_score * 100).toFixed(0) }}%</span>
                </div>
                <span v-else style="color: var(--gs-text-muted);">-</span>
              </template>
            </el-table-column>
            <el-table-column label="发现数" width="70" align="center">
              <template #default="{ row }">{{ row.finding_count ?? '-' }}</template>
            </el-table-column>
          </el-table>
        </div>
      </el-col>

      <!-- 风险趋势图 -->
      <el-col :span="10">
        <div class="gs-card gs-section">
          <div class="gs-card-header">
            <span class="gs-card-title">风险趋势</span>
          </div>
          <v-chart v-if="trendOption" :option="trendOption" autoresize style="height: 280px;" />
          <el-empty v-else description="暂无趋势数据" :image-size="80" />
        </div>
      </el-col>
    </el-row>

    <!-- 最近任务 -->
    <div class="gs-card">
      <div class="gs-card-header">
        <span class="gs-card-title">最近分析任务</span>
        <router-link :to="`/projects/${projectId}/tasks`" style="font-size: 13px;">查看全部 &rarr;</router-link>
      </div>
      <el-table :data="recentTasks" size="small" class="gs-table">
        <el-table-column label="任务ID" width="160">
          <template #default="{ row }">
            <router-link :to="`/tasks/${row.task_id}`" style="font-weight: 500;">
              {{ (row.task_id || '').slice(0, 16) }}
            </router-link>
          </template>
        </el-table-column>
        <el-table-column prop="task_type" label="类型" width="90" />
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <span class="gs-status-dot" :class="'gs-status-dot--' + row.status"></span>
            {{ statusLabel(row.status) }}
          </template>
        </el-table-column>
        <el-table-column label="风险评分" width="100">
          <template #default="{ row }">
            <span v-if="row.aggregate_risk_score != null" :style="{ color: riskColor(row.aggregate_risk_score), fontWeight: 600 }">
              {{ (row.aggregate_risk_score * 100).toFixed(0) }}%
            </span>
            <span v-else style="color: var(--gs-text-muted);">-</span>
          </template>
        </el-table-column>
        <el-table-column label="时间" width="160">
          <template #default="{ row }">{{ formatDate(row.created_at) }}</template>
        </el-table-column>
      </el-table>
      <el-empty v-if="!recentTasks.length" description="暂无分析任务" :image-size="60" />
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { use } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import { LineChart } from 'echarts/charts'
import { GridComponent, TooltipComponent } from 'echarts/components'
import VChart from 'vue-echarts'
import { useRiskColor } from '../../composables/useRiskColor.js'
import { useModuleNames } from '../../composables/useModuleNames.js'
import api from '../../api.js'

use([CanvasRenderer, LineChart, GridComponent, TooltipComponent])

const props = defineProps({
  projectId: [String, Number],
  project: Object,
})

const { riskColor, statusLabel } = useRiskColor()
const { getDisplayName } = useModuleNames()

const summary = ref({})
const moduleResults = ref([])
const recentTasks = ref([])
const trendData = ref([])
const testCaseStats = ref({ total: 0, high_priority: 0 })

const gatePass = computed(() => {
  const s = summary.value
  if (!s.avg_risk_score && s.avg_risk_score !== 0) return true
  return (s.avg_risk_score || 0) < 0.6 && (s.s0_count || 0) === 0 && (s.s1_count || 0) <= 3
})

const gateReasons = computed(() => {
  const reasons = []
  const s = summary.value
  if ((s.avg_risk_score || 0) >= 0.6) reasons.push(`平均风险评分 ${(s.avg_risk_score * 100).toFixed(0)}% ≥ 60%`)
  if ((s.s0_count || 0) > 0) reasons.push(`存在 ${s.s0_count} 个 S0 紧急问题`)
  if ((s.s1_count || 0) > 3) reasons.push(`S1 高危问题 ${s.s1_count} 个 > 3`)
  if (testCaseStats.value.high_priority > 5) reasons.push(`${testCaseStats.value.high_priority} 个高优先级测试待执行`)
  return reasons
})

const statCards = computed(() => {
  const s = summary.value
  const tc = testCaseStats.value
  return [
    { label: '总发现数', value: s.finding_count ?? '-', color: s.finding_count > 0 ? '#D4333F' : '#1D1D1D', sub: s.finding_count > 0 ? `S0:${s.s0_count || 0} S1:${s.s1_count || 0}` : null },
    { label: '风险评分', value: s.avg_risk_score != null ? (s.avg_risk_score * 100).toFixed(0) + '%' : '-', color: riskColor(s.avg_risk_score || 0) },
    { label: '测试用例', value: tc.total || '-', color: '#4B9FD5', sub: tc.high_priority > 0 ? `${tc.high_priority} 项高优先级` : null },
    { label: '分析任务', value: s.task_count ?? '-', color: '#1D1D1D', sub: moduleResults.value.filter(m => m.status === 'success').length + ' 个模块成功' },
  ]
})

const trendOption = computed(() => {
  if (!trendData.value.length) return null
  return {
    tooltip: { trigger: 'axis' },
    grid: { left: 40, right: 16, top: 16, bottom: 30 },
    xAxis: {
      type: 'category',
      data: trendData.value.map(t => t.label),
      axisLabel: { fontSize: 11 },
    },
    yAxis: { type: 'value', min: 0, max: 1, axisLabel: { formatter: v => (v * 100) + '%', fontSize: 11 } },
    series: [{
      type: 'line',
      data: trendData.value.map(t => t.risk_score),
      smooth: true,
      lineStyle: { color: '#4B9FD5', width: 2 },
      itemStyle: { color: '#4B9FD5' },
      areaStyle: { color: { type: 'linear', x: 0, y: 0, x2: 0, y2: 1, colorStops: [{ offset: 0, color: 'rgba(75,159,213,0.3)' }, { offset: 1, color: 'rgba(75,159,213,0.02)' }] } },
    }],
  }
})

function formatDate(d) {
  if (!d) return '-'
  return new Date(d).toLocaleString('zh-CN', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
}

async function loadData() {
  try {
    const [data, tcData] = await Promise.all([
      api.getProjectSummary(props.projectId),
      api.getProjectTestCases(props.projectId, { page: 1, page_size: 1 }).catch(() => null),
    ])
    summary.value = data || {}
    moduleResults.value = data?.modules || []
    recentTasks.value = data?.recent_tasks || []
    trendData.value = data?.trends || []

    // 加载测试用例统计
    if (tcData) {
      const total = tcData.total || 0
      const highP = (tcData.stats?.by_priority?.P0 || 0) + (tcData.stats?.by_priority?.P1 || 0)
      testCaseStats.value = { total, high_priority: highP }
    }
  } catch {
    // fallback
  }
}

onMounted(loadData)
</script>

<style scoped>
.gs-stat-row {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: var(--gs-space-md);
}

.gs-stat-sub {
  font-size: var(--gs-font-xs);
  color: var(--gs-text-muted);
}

.gs-risk-bar {
  flex: 1;
  height: 6px;
  background: var(--gs-border-light);
  border-radius: 3px;
  overflow: hidden;
}
.gs-risk-bar-fill {
  height: 100%;
  border-radius: 3px;
  transition: width var(--gs-transition);
}
</style>
