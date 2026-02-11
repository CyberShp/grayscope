<template>
  <div class="gs-page">
    <!-- 返回导航 -->
    <div class="gs-task-nav gs-section">
      <router-link to="/tasks" class="gs-back-link">&larr; 返回任务中心</router-link>
    </div>

    <!-- 任务头部 -->
    <div class="gs-task-header gs-section">
      <div class="gs-task-header-left">
        <h1 class="gs-page-title" style="margin-bottom: 4px;">任务详情</h1>
        <code class="gs-task-id">{{ task.task_id }}</code>
      </div>
      <div class="gs-task-header-right">
        <el-button v-if="['failed','partial_failed'].includes(task.status)" type="primary" size="small" @click="doRetry">
          <el-icon><RefreshRight /></el-icon> 重试
        </el-button>
        <el-button v-if="['pending','running'].includes(task.status)" type="danger" size="small" plain @click="doCancel">取消</el-button>
        <el-dropdown trigger="click">
          <el-button size="small"><el-icon><Download /></el-icon> 导出</el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item @click="doExport('json')">JSON 测试用例</el-dropdown-item>
              <el-dropdown-item @click="doExport('csv')">CSV 表格</el-dropdown-item>
              <el-dropdown-item @click="doExport('findings')">原始发现</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
      </div>
    </div>

    <!-- 状态卡片组 -->
    <div class="gs-stat-row gs-section">
      <div class="gs-stat-card">
        <div class="gs-stat-label">状态</div>
        <div style="display: flex; align-items: center; gap: 6px;">
          <span class="gs-status-dot" :class="'gs-status-dot--' + task.status"></span>
          <span class="gs-stat-value" style="font-size: 16px;">{{ statusLabel(task.status) }}</span>
        </div>
      </div>
      <div class="gs-stat-card">
        <div class="gs-stat-label">风险评分</div>
        <div class="gs-stat-value" :style="{ color: riskColor(results.aggregate_risk_score || 0) }">
          {{ results.aggregate_risk_score != null ? (results.aggregate_risk_score * 100).toFixed(0) + '%' : '-' }}
        </div>
        <div class="gs-stat-sub">{{ riskLevel(results.aggregate_risk_score || 0) }}</div>
      </div>
      <div class="gs-stat-card">
        <div class="gs-stat-label">模块进度</div>
        <div class="gs-stat-value" style="font-size: 16px;">
          {{ task.progress?.finished_modules || 0 }} / {{ task.progress?.total_modules || 0 }}
        </div>
        <div class="gs-stat-sub">{{ task.task_type || '-' }}</div>
      </div>
      <div class="gs-stat-card">
        <div class="gs-stat-label">创建时间</div>
        <div style="font-size: 13px; color: var(--gs-text-primary);">{{ formatDate(task.created_at) }}</div>
        <div class="gs-stat-sub">更新: {{ formatDate(task.updated_at) }}</div>
      </div>
    </div>

    <!-- Tabs -->
    <div class="gs-card">
      <el-tabs v-model="activeTab">
        <!-- 模块概览 -->
        <el-tab-pane label="模块概览" name="modules">
          <el-row :gutter="20">
            <el-col :span="14">
              <el-table :data="modules" size="small" class="gs-table">
                <el-table-column label="模块名称" min-width="160">
                  <template #default="{ row }">
                    <span style="font-weight: 500;">{{ row.display_name || getDisplayName(row.module) }}</span>
                  </template>
                </el-table-column>
                <el-table-column label="状态" width="100">
                  <template #default="{ row }">
                    <span class="gs-status-dot" :class="'gs-status-dot--' + row.status"></span>
                    {{ statusLabel(row.status) }}
                  </template>
                </el-table-column>
                <el-table-column label="风险评分" width="160">
                  <template #default="{ row }">
                    <div v-if="row.risk_score != null" style="display: flex; align-items: center; gap: 8px;">
                      <div class="gs-risk-bar" style="flex: 1;">
                        <div class="gs-risk-bar-fill" :style="{ width: (row.risk_score * 100) + '%', background: riskColor(row.risk_score) }"></div>
                      </div>
                      <span style="font-size: 12px; font-weight: 600;">{{ (row.risk_score * 100).toFixed(0) }}%</span>
                    </div>
                    <span v-else style="color: var(--gs-text-muted);">-</span>
                  </template>
                </el-table-column>
                <el-table-column prop="finding_count" label="发现数" width="70" align="center" />
              </el-table>
            </el-col>
            <el-col :span="10">
              <v-chart v-if="Object.keys(radarOption).length" :option="radarOption" autoresize style="height: 320px;" />
              <el-empty v-else description="暂无雷达图数据" :image-size="60" />
            </el-col>
          </el-row>
        </el-tab-pane>

        <!-- 发现列表 -->
        <el-tab-pane label="发现列表" name="findings">
          <div class="gs-toolbar" style="margin-bottom: 12px;">
            <div class="gs-toolbar-left">
              <el-select v-model="filterSeverity" placeholder="严重程度" clearable size="small" style="width: 120px;">
                <el-option label="S0 紧急" value="S0" />
                <el-option label="S1 高危" value="S1" />
                <el-option label="S2 中危" value="S2" />
                <el-option label="S3 低危" value="S3" />
              </el-select>
              <el-select v-model="filterModule" placeholder="分析模块" clearable size="small" style="width: 160px;">
                <el-option v-for="m in modules" :key="m.module" :label="getDisplayName(m.module)" :value="m.module" />
              </el-select>
            </div>
            <span class="gs-result-count">{{ filteredFindings.length }} 条发现</span>
          </div>
          <el-table :data="filteredFindings" size="small" class="gs-table" row-key="finding_id" :default-sort="{ prop: 'risk_score', order: 'descending' }">
            <el-table-column type="expand">
              <template #default="{ row }">
                <div style="padding: 12px 24px;">
                  <p style="margin-bottom: 8px;"><strong>描述:</strong> {{ row.description }}</p>
                  <p v-if="row.symbol_name" style="margin-bottom: 8px;"><strong>函数:</strong> <code>{{ row.symbol_name }}()</code></p>
                  <p v-if="row.line_start" style="margin-bottom: 8px;"><strong>行号:</strong> {{ row.line_start }} - {{ row.line_end }}</p>

                  <!-- 推荐测试设计 -->
                  <div class="gs-inline-test-suggestion">
                    <div class="gs-inline-ts-title"><el-icon><EditPen /></el-icon> 推荐测试设计</div>
                    <div class="gs-inline-ts-body">
                      <p><strong>测试目标:</strong> {{ getTestObjective(row) }}</p>
                      <p><strong>测试步骤:</strong></p>
                      <ol class="gs-inline-ts-steps">
                        <li v-for="(s, i) in getTestSteps(row)" :key="i">{{ s.replace(/^\d+\.\s*/, '') }}</li>
                      </ol>
                      <p class="gs-inline-ts-expected"><strong>预期结果:</strong> {{ getTestExpected(row) }}</p>
                    </div>
                  </div>

                  <!-- 结构化证据 -->
                  <div v-if="row.evidence && Object.keys(row.evidence).length" style="margin-top: 12px;">
                    <strong>分析证据:</strong>
                    <div style="margin-top: 8px;">
                      <EvidenceRenderer :module-id="row.module_id" :risk-type="row.risk_type" :evidence="row.evidence" :finding="row" />
                    </div>
                  </div>
                </div>
              </template>
            </el-table-column>
            <el-table-column label="严重度" width="80" sortable prop="severity">
              <template #default="{ row }">
                <span class="gs-severity-tag" :class="'gs-severity-' + (row.severity || 's3').toLowerCase()">{{ row.severity }}</span>
              </template>
            </el-table-column>
            <el-table-column label="模块" width="130">
              <template #default="{ row }">{{ getDisplayName(row.module_id) }}</template>
            </el-table-column>
            <el-table-column prop="risk_type" label="风险类型" width="180" show-overflow-tooltip />
            <el-table-column prop="title" label="标题" min-width="200" show-overflow-tooltip />
            <el-table-column prop="file_path" label="文件" min-width="160" show-overflow-tooltip>
              <template #default="{ row }">
                <span style="font-family: var(--gs-font-mono); font-size: 11px;">{{ row.file_path }}</span>
              </template>
            </el-table-column>
            <el-table-column prop="risk_score" label="评分" width="70" sortable>
              <template #default="{ row }">
                <span :style="{ color: riskColor(row.risk_score || 0), fontWeight: 600 }">
                  {{ row.risk_score != null ? (row.risk_score * 100).toFixed(0) + '%' : '-' }}
                </span>
              </template>
            </el-table-column>
          </el-table>
        </el-tab-pane>

        <!-- 导出 -->
        <el-tab-pane label="导出" name="export">
          <div style="padding: 48px; text-align: center;">
            <p style="color: var(--gs-text-muted); margin-bottom: 24px;">选择导出格式下载分析结果</p>
            <div style="display: flex; gap: 16px; justify-content: center;">
              <div class="gs-export-card" @click="doExport('json')">
                <el-icon :size="32" color="#4B9FD5"><Document /></el-icon>
                <div class="gs-export-label">JSON 测试用例</div>
                <div class="gs-export-desc">结构化测试用例建议</div>
              </div>
              <div class="gs-export-card" @click="doExport('csv')">
                <el-icon :size="32" color="#00AA00"><Grid /></el-icon>
                <div class="gs-export-label">CSV 表格</div>
                <div class="gs-export-desc">可导入测试管理工具</div>
              </div>
              <div class="gs-export-card" @click="doExport('findings')">
                <el-icon :size="32" color="#EAB308"><DataLine /></el-icon>
                <div class="gs-export-label">原始发现</div>
                <div class="gs-export-desc">完整发现及 AI 增强数据</div>
              </div>
            </div>
          </div>
        </el-tab-pane>
      </el-tabs>
    </div>
  </div>
</template>

<script>
import { use } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import { RadarChart } from 'echarts/charts'
import { TitleComponent, TooltipComponent, LegendComponent } from 'echarts/components'
import VChart from 'vue-echarts'
import { ElMessage } from 'element-plus'
import api from '../api.js'
import { useRiskColor } from '../composables/useRiskColor.js'
import { useModuleNames } from '../composables/useModuleNames.js'
import { useTestSuggestion } from '../composables/useTestSuggestion.js'
import EvidenceRenderer from '../components/EvidenceRenderer.vue'

use([CanvasRenderer, RadarChart, TitleComponent, TooltipComponent, LegendComponent])

export default {
  name: 'TaskDetail',
  components: { VChart, EvidenceRenderer },
  props: { taskId: String },
  setup() {
    const { riskColor, riskLevel, severityType, statusType, statusLabel } = useRiskColor()
    const { getDisplayName } = useModuleNames()
    const { getTestObjective, getTestSteps, getTestExpected } = useTestSuggestion()
    return { riskColor, riskLevel, severityType, statusType, statusLabel, getDisplayName, getTestObjective, getTestSteps, getTestExpected }
  },
  data() {
    return {
      task: {},
      results: {},
      modules: [],
      findings: [],
      activeTab: 'modules',
      filterSeverity: '',
      filterModule: '',
    }
  },
  computed: {
    filteredFindings() {
      let list = this.findings
      if (this.filterSeverity) list = list.filter(f => f.severity === this.filterSeverity)
      if (this.filterModule) list = list.filter(f => f.module_id === this.filterModule)
      return list
    },
    radarOption() {
      const mods = this.modules.filter(m => m.status === 'success' && m.risk_score != null)
      if (!mods.length) return {}
      return {
        tooltip: {},
        radar: {
          indicator: mods.map(m => ({ name: this.getDisplayName(m.module), max: 1 })),
        },
        series: [{
          type: 'radar',
          data: [{ value: mods.map(m => m.risk_score || 0), name: '风险评分' }],
          lineStyle: { color: '#4B9FD5' },
          itemStyle: { color: '#4B9FD5' },
          areaStyle: { opacity: 0.2, color: '#4B9FD5' },
        }],
      }
    },
  },
  async mounted() {
    await this.loadAll()
  },
  methods: {
    async loadAll() {
      try {
        this.task = await api.getTaskStatus(this.taskId)
        this.results = await api.getTaskResults(this.taskId)
        this.modules = this.results.modules || []
      } catch {}
      try {
        const url = api.exportUrl(this.taskId, 'findings')
        const res = await fetch(url)
        const data = await res.json()
        const allFindings = []
        for (const mod of (data.modules || [])) {
          allFindings.push(...(mod.findings || []))
        }
        this.findings = allFindings
      } catch {}
    },
    doExport(fmt) {
      window.open(api.exportUrl(this.taskId, fmt), '_blank')
    },
    async doRetry() {
      try { await api.retryTask(this.taskId, {}); ElMessage.success('重试已提交'); await this.loadAll() }
      catch (e) { ElMessage.error('重试失败: ' + e.message) }
    },
    async doCancel() {
      try { await api.cancelTask(this.taskId); ElMessage.success('已取消'); await this.loadAll() }
      catch (e) { ElMessage.error('取消失败: ' + e.message) }
    },
    formatDate(d) {
      if (!d) return '-'
      return new Date(d).toLocaleString('zh-CN')
    },
  },
}
</script>

<style scoped>
.gs-task-nav { margin-bottom: var(--gs-space-sm); }
.gs-back-link { font-size: var(--gs-font-sm); color: var(--gs-text-link); text-decoration: none; }
.gs-back-link:hover { text-decoration: underline; }

.gs-task-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
}
.gs-task-header-right { display: flex; gap: var(--gs-space-sm); }
.gs-task-id {
  font-family: var(--gs-font-mono);
  font-size: var(--gs-font-sm);
  background: #F5F5F5;
  padding: 2px 8px;
  border-radius: 3px;
}

.gs-stat-row {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: var(--gs-space-md);
}
.gs-stat-sub {
  font-size: var(--gs-font-xs);
  color: var(--gs-text-muted);
}

.gs-toolbar { display: flex; justify-content: space-between; align-items: center; }
.gs-toolbar-left { display: flex; gap: var(--gs-space-sm); }
.gs-result-count { font-size: var(--gs-font-sm); color: var(--gs-text-muted); }

.gs-risk-bar { height: 6px; background: var(--gs-border-light); border-radius: 3px; overflow: hidden; }
.gs-risk-bar-fill { height: 100%; border-radius: 3px; }

.gs-code-block {
  background: #1E1E1E;
  color: #D4D4D4;
  padding: 12px;
  border-radius: 6px;
  font-family: var(--gs-font-mono);
  font-size: 12px;
  overflow-x: auto;
  white-space: pre-wrap;
}

.gs-export-card {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  padding: 24px 32px;
  border: 1px solid var(--gs-border);
  border-radius: var(--gs-radius-lg);
  cursor: pointer;
  transition: all var(--gs-transition);
  min-width: 160px;
}
.gs-export-card:hover {
  border-color: var(--gs-primary);
  box-shadow: var(--gs-shadow-md);
}
.gs-export-label { font-weight: 600; font-size: 14px; }
.gs-export-desc { font-size: 12px; color: var(--gs-text-muted); }

/* ── 内联测试建议 ──────────────────── */
.gs-inline-test-suggestion {
  margin-top: 12px;
  background: rgba(75, 159, 213, 0.04);
  border: 1px solid rgba(75, 159, 213, 0.15);
  border-radius: 8px;
  overflow: hidden;
}
.gs-inline-ts-title {
  display: flex; align-items: center; gap: 6px;
  padding: 8px 14px;
  background: rgba(75, 159, 213, 0.08);
  font-size: 13px; font-weight: 600; color: var(--gs-primary);
}
.gs-inline-ts-body {
  padding: 12px 14px;
  font-size: 13px; color: var(--gs-text-primary); line-height: 1.6;
}
.gs-inline-ts-body p { margin: 0 0 6px 0; }
.gs-inline-ts-steps {
  margin: 4px 0 8px 0; padding-left: 18px;
  color: var(--gs-text-secondary);
}
.gs-inline-ts-steps li { padding: 2px 0; }
.gs-inline-ts-steps li::marker { color: var(--gs-primary); font-weight: 600; }
.gs-inline-ts-expected { color: var(--gs-success) !important; font-weight: 500; }
</style>
