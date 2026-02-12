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
                  <!-- 风险原因高亮区 -->
                  <div class="gs-risk-detail-block">
                    <div class="gs-risk-detail-title">
                      <el-icon style="color:var(--gs-warning);"><WarningFilled /></el-icon>
                      为什么这里有风险？
                    </div>
                    <p class="gs-risk-detail-desc">{{ row.description || '暂无详细描述' }}</p>
                    <div v-if="row.risk_type" class="gs-risk-detail-type">
                      <span style="color:var(--gs-text-muted);font-size:12px;">风险类型:</span>
                      <el-tag size="small" :type="riskTypeTag(row.risk_type)">{{ riskTypeLabel(row.risk_type) }}</el-tag>
                    </div>
                  </div>

                  <!-- 代码位置（可点击跳转） -->
                  <div v-if="row.file_path" class="gs-risk-location-block">
                    <strong>代码位置:</strong>
                    <router-link v-if="taskProjectId" :to="sourceLink(row)" class="gs-source-link" style="margin-left:8px;">
                      {{ row.file_path }}<span v-if="row.line_start">:{{ row.line_start }}<span v-if="row.line_end">-{{ row.line_end }}</span></span>
                    </router-link>
                    <span v-else style="font-family:var(--gs-font-mono);font-size:12px;margin-left:8px;">
                      {{ row.file_path }}<span v-if="row.line_start">:{{ row.line_start }}</span>
                    </span>
                    <span v-if="row.symbol_name" style="margin-left:12px;">
                      <strong>函数:</strong> <code>{{ row.symbol_name }}()</code>
                    </span>
                  </div>

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
            <el-table-column prop="risk_type" label="风险类型" width="160" show-overflow-tooltip>
              <template #default="{ row }">
                <el-tag size="small" :type="riskTypeTag(row.risk_type)">{{ riskTypeLabel(row.risk_type) }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="title" label="标题" min-width="180" show-overflow-tooltip />
            <el-table-column label="风险原因" min-width="220">
              <template #default="{ row }">
                <div class="gs-risk-reason">
                  <span class="gs-risk-reason-text">{{ row.description || '-' }}</span>
                </div>
              </template>
            </el-table-column>
            <el-table-column label="文件位置" min-width="200">
              <template #default="{ row }">
                <div v-if="row.file_path" class="gs-source-link-wrap">
                  <router-link v-if="taskProjectId"
                    :to="sourceLink(row)"
                    class="gs-source-link"
                    :title="row.file_path">
                    <span class="gs-source-file">{{ shortenPath(row.file_path) }}</span>
                    <span v-if="row.line_start" class="gs-source-line">:{{ row.line_start }}<span v-if="row.line_end && row.line_end !== row.line_start">-{{ row.line_end }}</span></span>
                  </router-link>
                  <span v-else class="gs-source-link" style="cursor:default;">
                    <span class="gs-source-file">{{ shortenPath(row.file_path) }}</span>
                    <span v-if="row.line_start" class="gs-source-line">:{{ row.line_start }}</span>
                  </span>
                  <span v-if="row.symbol_name" class="gs-source-symbol">{{ row.symbol_name }}()</span>
                </div>
                <span v-else style="color:var(--gs-text-muted);">-</span>
              </template>
            </el-table-column>
            <el-table-column prop="risk_score" label="评分" width="80" sortable>
              <template #default="{ row }">
                <div style="display:flex;align-items:center;gap:4px;">
                  <div class="gs-risk-bar" style="width:40px;">
                    <div class="gs-risk-bar-fill" :style="{ width: (row.risk_score || 0) * 100 + '%', background: riskColor(row.risk_score || 0) }"></div>
                  </div>
                  <span :style="{ color: riskColor(row.risk_score || 0), fontWeight: 600, fontSize: '12px' }">
                    {{ row.risk_score != null ? (row.risk_score * 100).toFixed(0) + '%' : '-' }}
                  </span>
                </div>
              </template>
            </el-table-column>
          </el-table>
        </el-tab-pane>

        <!-- 覆盖率 -->
        <el-tab-pane label="覆盖率" name="coverage">
          <div v-if="coverageFindings.length" class="gs-coverage-section">
            <!-- 覆盖率汇总 -->
            <div class="gs-stat-row gs-section" style="grid-template-columns: repeat(3, 1fr);">
              <div class="gs-stat-card">
                <div class="gs-stat-label">平均行覆盖率</div>
                <div class="gs-stat-value" :style="{ color: covColor(avgLineCoverage) }">{{ (avgLineCoverage * 100).toFixed(0) }}%</div>
              </div>
              <div class="gs-stat-card">
                <div class="gs-stat-label">平均分支覆盖率</div>
                <div class="gs-stat-value" :style="{ color: covColor(avgBranchCoverage) }">{{ (avgBranchCoverage * 100).toFixed(0) }}%</div>
              </div>
              <div class="gs-stat-card">
                <div class="gs-stat-label">零覆盖文件</div>
                <div class="gs-stat-value" :style="{ color: zeroCoverageCount > 0 ? '#D4333F' : '#00AA00' }">{{ zeroCoverageCount }}</div>
              </div>
            </div>

            <!-- 文件级覆盖率列表 -->
            <el-table :data="coverageFindings" size="small" class="gs-table" :default-sort="{ prop: 'line_coverage', order: 'ascending' }">
              <el-table-column label="文件路径" min-width="280">
                <template #default="{ row }">
                  <router-link v-if="row.file_path && taskProjectId"
                    :to="`/projects/${taskProjectId}/code?path=${encodeURIComponent(row.file_path)}`"
                    class="gs-file-link">
                    {{ row.file_path }}
                  </router-link>
                  <span v-else class="gs-file-path">{{ row.file_path || '-' }}</span>
                </template>
              </el-table-column>
              <el-table-column label="行覆盖率" width="200" prop="line_coverage" sortable>
                <template #default="{ row }">
                  <div style="display: flex; align-items: center; gap: 8px;">
                    <div class="gs-cov-bar-wrap">
                      <div class="gs-cov-bar" :class="covBarClass(row.line_coverage)" :style="{ width: (row.line_coverage || 0) * 100 + '%' }"></div>
                    </div>
                    <span style="font-size: 12px; font-weight: 600; min-width: 36px;">{{ ((row.line_coverage || 0) * 100).toFixed(0) }}%</span>
                  </div>
                </template>
              </el-table-column>
              <el-table-column label="分支覆盖率" width="200" prop="branch_coverage" sortable>
                <template #default="{ row }">
                  <div style="display: flex; align-items: center; gap: 8px;">
                    <div class="gs-cov-bar-wrap">
                      <div class="gs-cov-bar" :class="covBarClass(row.branch_coverage)" :style="{ width: (row.branch_coverage || 0) * 100 + '%' }"></div>
                    </div>
                    <span style="font-size: 12px; font-weight: 600; min-width: 36px;">{{ ((row.branch_coverage || 0) * 100).toFixed(0) }}%</span>
                  </div>
                </template>
              </el-table-column>
              <el-table-column label="风险" width="100" prop="risk_score" sortable>
                <template #default="{ row }">
                  <span :style="{ color: riskColor(row.risk_score || 0), fontWeight: 600 }">
                    {{ row.risk_score != null ? (row.risk_score * 100).toFixed(0) + '%' : '-' }}
                  </span>
                </template>
              </el-table-column>
              <el-table-column label="风险原因" min-width="200" show-overflow-tooltip>
                <template #default="{ row }">
                  <span style="font-size:12px;color:var(--gs-text-secondary);">{{ row.title || row.description || '-' }}</span>
                </template>
              </el-table-column>
            </el-table>
          </div>
          <el-empty v-else description="暂无覆盖率数据，请确保启用了 coverage_map 分析器" :image-size="80" />
        </el-tab-pane>

        <!-- AI 增强 -->
        <el-tab-pane name="ai">
          <template #label>
            AI 增强
            <el-tag v-if="aiSuccessCount" type="success" size="small" style="margin-left:4px;">{{ aiSuccessCount }}</el-tag>
            <el-tag v-else-if="aiFailCount" type="danger" size="small" style="margin-left:4px;">失败</el-tag>
          </template>

          <div v-if="!aiEnabled" class="gs-ai-empty">
            <el-icon :size="48" color="#ccc"><WarningFilled /></el-icon>
            <p>本次分析未启用 AI 增强，或 AI 模型不可用</p>
            <p style="font-size:12px;color:var(--gs-text-muted);">
              请在"设置 → AI 模型管理"中配置可用的 AI 模型（如 DeepSeek、Ollama 等），<br>
              然后在新建分析时选择 AI 提供商和模型
            </p>
          </div>

          <div v-else class="gs-ai-results">
            <div v-for="(summary, modId) in aiSummaries" :key="modId" class="gs-ai-module-card">
              <div class="gs-ai-module-header">
                <span class="gs-ai-module-name">{{ getDisplayName(modId) }}</span>
                <el-tag :type="summary.success ? 'success' : 'danger'" size="small">
                  {{ summary.success ? 'AI 分析完成' : (summary.skipped ? '已跳过' : 'AI 不可用') }}
                </el-tag>
                <span v-if="summary.provider" style="font-size:11px;color:var(--gs-text-muted);margin-left:auto;">
                  {{ summary.provider }}/{{ summary.model }}
                </span>
              </div>

              <div v-if="summary.success && summary.ai_summary" class="gs-ai-summary-content">
                <div class="gs-ai-section-title">AI 风险分析</div>
                <pre class="gs-ai-text">{{ summary.ai_summary }}</pre>
              </div>

              <div v-if="summary.success && summary.test_suggestions && summary.test_suggestions.length" class="gs-ai-suggestions">
                <div class="gs-ai-section-title">AI 测试建议</div>
                <div v-for="(sug, i) in summary.test_suggestions" :key="i" class="gs-ai-suggestion-item">
                  <template v-if="sug.type === 'raw_text'">
                    <pre class="gs-ai-text">{{ sug.content }}</pre>
                  </template>
                  <template v-else>
                    <div><strong>{{ sug.title || sug.name || `测试用例 ${i+1}` }}</strong></div>
                    <div v-if="sug.description || sug.steps" style="font-size:12px;color:var(--gs-text-secondary);">
                      {{ sug.description || sug.steps }}
                    </div>
                  </template>
                </div>
              </div>

              <div v-if="!summary.success && summary.ai_summary" class="gs-ai-error">
                <el-icon color="#D50000"><WarningFilled /></el-icon>
                <span>{{ summary.ai_summary }}</span>
              </div>

              <div v-if="summary.usage && summary.usage.total_tokens" class="gs-ai-usage">
                Token 用量: {{ summary.usage.prompt_tokens || 0 }} + {{ summary.usage.completion_tokens || 0 }} = {{ summary.usage.total_tokens }}
              </div>
            </div>
          </div>
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
import { WarningFilled } from '@element-plus/icons-vue'
import api from '../api.js'
import { useRiskColor } from '../composables/useRiskColor.js'
import { useModuleNames } from '../composables/useModuleNames.js'
import { useTestSuggestion } from '../composables/useTestSuggestion.js'
import EvidenceRenderer from '../components/EvidenceRenderer.vue'

use([CanvasRenderer, RadarChart, TitleComponent, TooltipComponent, LegendComponent])

export default {
  name: 'TaskDetail',
  components: { VChart, EvidenceRenderer, WarningFilled },
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
      aiSummaries: {},
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
    taskProjectId() {
      return this.task?.project_id || null
    },
    coverageFindings() {
      return this.findings
        .filter(f => f.module_id === 'coverage_map' && f.evidence)
        .map(f => ({
          ...f,
          line_coverage: f.evidence?.line_coverage || 0,
          branch_coverage: f.evidence?.branch_coverage || 0,
        }))
    },
    avgLineCoverage() {
      const covs = this.coverageFindings
      if (!covs.length) return 0
      return covs.reduce((s, f) => s + (f.line_coverage || 0), 0) / covs.length
    },
    avgBranchCoverage() {
      const covs = this.coverageFindings
      if (!covs.length) return 0
      return covs.reduce((s, f) => s + (f.branch_coverage || 0), 0) / covs.length
    },
    zeroCoverageCount() {
      return this.coverageFindings.filter(f => (f.line_coverage || 0) === 0).length
    },
    aiEnabled() {
      return Object.keys(this.aiSummaries).length > 0
    },
    aiSuccessCount() {
      return Object.values(this.aiSummaries).filter(a => a.success).length
    },
    aiFailCount() {
      return Object.values(this.aiSummaries).filter(a => !a.success && !a.skipped).length
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
        const aiSummaries = {}
        for (const mod of (data.modules || [])) {
          allFindings.push(...(mod.findings || []))
          if (mod.ai_summary) {
            aiSummaries[mod.module_id || mod.module] = mod.ai_summary
          }
        }
        this.findings = allFindings
        this.aiSummaries = aiSummaries
      } catch {}
    },
    riskTypeTag(type) {
      if (!type) return 'info'
      if (type.includes('critical') || type.includes('crash') || type.includes('deadlock')) return 'danger'
      if (type.includes('error') || type.includes('cleanup')) return 'danger'
      if (type.includes('race') || type.includes('leak') || type.includes('overflow')) return 'warning'
      if (type.includes('boundary')) return 'warning'
      if (type.includes('state')) return ''
      return ''
    },
    riskTypeLabel(type) {
      const map = {
        branch_error: '错误处理分支',
        branch_cleanup: '资源清理分支',
        branch_boundary: '边界条件分支',
        branch_state: '状态/模式判断',
        branch_normal: '正常分支',
        boundary_miss: '边界值缺失',
        invalid_input_gap: '无效输入风险',
        changed_core_path: '核心路径变更',
        error_path_incomplete: '错误路径不完整',
        error_no_check: '缺少错误检查',
        race_condition: '竞态条件',
        deadlock_risk: '死锁风险',
      }
      return map[type] || type
    },
    shortenPath(path) {
      if (!path) return '-'
      const parts = path.split('/')
      if (parts.length <= 3) return path
      return '.../' + parts.slice(-2).join('/')
    },
    sourceLink(row) {
      if (!this.taskProjectId || !row.file_path) return '#'
      let link = `/projects/${this.taskProjectId}/code?path=${encodeURIComponent(row.file_path)}`
      if (row.line_start) link += `&line=${row.line_start}`
      return link
    },
    covColor(val) {
      if (!val || val === 0) return '#D4333F'
      if (val < 0.3) return '#D4333F'
      if (val < 0.7) return '#E57F00'
      return '#00AA00'
    },
    covBarClass(val) {
      if (!val || val === 0) return 'cov-zero'
      if (val < 0.3) return 'cov-low'
      if (val < 0.7) return 'cov-medium'
      return 'cov-high'
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

/* ── 风险原因 ──────────────────────── */
.gs-risk-reason { max-width: 220px; }
.gs-risk-reason-text {
  font-size: 12px; color: var(--gs-text-secondary); line-height: 1.4;
  display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden;
}

.gs-risk-detail-block {
  background: rgba(234, 179, 8, 0.06); border: 1px solid rgba(234, 179, 8, 0.2);
  border-radius: 8px; padding: 12px 16px; margin-bottom: 12px;
}
.gs-risk-detail-title {
  display: flex; align-items: center; gap: 6px;
  font-size: 14px; font-weight: 600; color: var(--gs-text-primary); margin-bottom: 8px;
}
.gs-risk-detail-desc {
  margin: 0 0 8px; font-size: 13px; color: var(--gs-text-primary); line-height: 1.6;
}
.gs-risk-detail-type { display: flex; align-items: center; gap: 6px; }
.gs-risk-location-block {
  margin-bottom: 12px; font-size: 13px; display: flex; align-items: center; flex-wrap: wrap;
}

/* ── 源码链接 ──────────────────────── */
.gs-source-link-wrap { display: flex; flex-direction: column; gap: 2px; }
.gs-source-link {
  font-family: var(--gs-font-mono); font-size: 11px;
  color: var(--gs-text-link); text-decoration: none;
  display: inline-flex; align-items: baseline;
}
.gs-source-link:hover { text-decoration: underline; }
.gs-source-file { word-break: break-all; }
.gs-source-line { color: var(--gs-primary); font-weight: 600; }
.gs-source-symbol {
  font-family: var(--gs-font-mono); font-size: 11px;
  color: var(--gs-text-muted);
}

/* ── 覆盖率 ────────────────────────── */
.gs-coverage-section { padding: 8px 0; }
.gs-cov-bar-wrap {
  flex: 1; height: 8px; background: var(--gs-border-light); border-radius: 4px; overflow: hidden;
}
.gs-cov-bar { height: 100%; border-radius: 4px; transition: width 0.3s; }
.gs-cov-bar.cov-zero { background: var(--gs-danger); min-width: 2px; }
.gs-cov-bar.cov-low { background: #D4333F; }
.gs-cov-bar.cov-medium { background: #E57F00; }
.gs-cov-bar.cov-high { background: #00AA00; }
.gs-file-link {
  font-family: var(--gs-font-mono); font-size: 12px;
  color: var(--gs-text-link); text-decoration: none;
}
.gs-file-link:hover { text-decoration: underline; }
.gs-file-path { font-family: var(--gs-font-mono); font-size: 12px; }

/* ── AI 增强 ──────────────────────── */
.gs-ai-empty {
  padding: 48px; text-align: center;
}
.gs-ai-empty p { margin: 8px 0; color: var(--gs-text-muted); }
.gs-ai-results { display: flex; flex-direction: column; gap: 16px; padding: 8px 0; }
.gs-ai-module-card {
  border: 1px solid var(--gs-border); border-radius: 8px; padding: 16px;
  background: var(--gs-surface);
}
.gs-ai-module-header {
  display: flex; align-items: center; gap: 8px; margin-bottom: 12px;
}
.gs-ai-module-name { font-weight: 600; font-size: 14px; }
.gs-ai-section-title {
  font-size: 12px; font-weight: 600; color: var(--gs-text-muted);
  margin-bottom: 8px; text-transform: uppercase; letter-spacing: 0.5px;
}
.gs-ai-text {
  background: var(--gs-bg); border-radius: 6px; padding: 12px;
  font-size: 13px; line-height: 1.6; white-space: pre-wrap; word-break: break-word;
  font-family: inherit; max-height: 400px; overflow-y: auto;
}
.gs-ai-summary-content { margin-bottom: 16px; }
.gs-ai-suggestions { margin-bottom: 12px; }
.gs-ai-suggestion-item {
  background: var(--gs-bg); border-radius: 6px; padding: 10px 12px;
  margin-bottom: 8px; font-size: 13px;
}
.gs-ai-error {
  display: flex; align-items: center; gap: 8px;
  padding: 10px 12px; background: rgba(213, 0, 0, 0.05); border-radius: 6px;
  font-size: 13px; color: #D50000;
}
.gs-ai-usage {
  font-size: 11px; color: var(--gs-text-muted); margin-top: 8px;
  padding-top: 8px; border-top: 1px solid var(--gs-border);
}
</style>
