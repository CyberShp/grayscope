<template>
  <div class="gs-page">
    <div class="gs-page-header">
      <h1 class="gs-page-title">代码分析流水线</h1>
      <p class="gs-page-desc">端到端分析：调用链 → 风险识别 → AI叙事 → 测试指导</p>
    </div>

    <!-- 分析列表视图 (默认) -->
    <el-card v-if="mode === 'list'" shadow="hover" class="gs-section">
      <template #header>
        <div class="gs-header-row">
          <span class="gs-card-title">分析管理</span>
          <el-button type="primary" @click="switchToCreate">
            <el-icon><Plus /></el-icon> 新建分析
          </el-button>
        </div>
      </template>
      <el-table :data="analysesList" v-loading="loadingList" stripe style="width:100%">
        <el-table-column prop="analysis_id" label="分析ID" width="300">
          <template #default="{ row }">
            <span class="gs-mono">{{ row.analysis_id }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="workspace_path" label="代码路径" min-width="200" show-overflow-tooltip />
        <el-table-column prop="status" label="状态" width="120">
          <template #default="{ row }">
            <el-tag :type="statusType(row.status)" size="small">{{ statusLabel(row.status) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="started_at" label="启动时间" width="180">
          <template #default="{ row }">
            {{ formatTime(row.started_at) }}
          </template>
        </el-table-column>
        <el-table-column label="操作" width="160" fixed="right">
          <template #default="{ row }">
            <el-button v-if="row.status === 'completed'" type="primary" link @click="viewAnalysis(row)">查看</el-button>
            <el-button v-else-if="row.status === 'running'" type="warning" link @click="viewRunning(row)">进度</el-button>
            <el-popconfirm title="确认删除此分析记录？" @confirm="deleteAnalysis(row.analysis_id)">
              <template #reference>
                <el-button type="danger" link>删除</el-button>
              </template>
            </el-popconfirm>
          </template>
        </el-table-column>
      </el-table>
      <div v-if="analysesList.length === 0 && !loadingList" class="gs-empty">
        <el-empty description="暂无分析记录">
          <el-button type="primary" @click="switchToCreate">创建第一个分析</el-button>
        </el-empty>
      </div>
    </el-card>

    <!-- 创建分析表单 -->
    <el-card v-if="mode === 'create'" shadow="hover" class="gs-section">
      <template #header>
        <div class="gs-header-row">
          <span class="gs-card-title">启动新分析</span>
          <el-button @click="mode = 'list'" :icon="Back">返回列表</el-button>
        </div>
      </template>
      <el-form :model="form" label-width="120px" style="max-width:700px">
        <el-divider content-position="left">代码来源</el-divider>
        <el-form-item label="项目" required>
          <el-select v-model="form.project_id" placeholder="请选择项目" style="width:100%" @change="onProjectChange" filterable>
            <el-option v-for="p in projects" :key="p.id ?? p.project_id" :label="p.name" :value="p.id ?? p.project_id" />
          </el-select>
        </el-form-item>
        <el-form-item label="仓库" required>
          <el-select v-model="form.repo_id" placeholder="请先选择项目" :disabled="!form.project_id" style="width:100%" filterable>
            <el-option v-for="r in repos" :key="r.repo_id" :label="repoLabel(r)" :value="r.repo_id" />
          </el-select>
          <div v-if="selectedRepo?.local_mirror_path" class="gs-form-hint">
            本地路径: {{ selectedRepo.local_mirror_path }}
          </div>
          <div v-else-if="form.repo_id" class="gs-form-hint gs-warn">
            ⚠ 仓库未同步，请先在仓库管理中同步代码
          </div>
        </el-form-item>
        <el-form-item label="子目录">
          <el-input v-model="form.sub_path" placeholder="可选，如 src/" style="width:100%">
            <template #prepend>/</template>
          </el-input>
          <div class="gs-form-hint">指定仓库内的子目录进行分析（留空则分析整个仓库）</div>
        </el-form-item>

        <el-divider content-position="left">分析配置</el-divider>
        <el-form-item label="最大文件数">
          <el-slider v-model="form.max_files" :min="50" :max="1000" :step="50" show-input style="max-width:400px" />
        </el-form-item>
        <el-form-item label="AI 增强">
          <el-switch v-model="form.enable_ai" active-text="启用" inactive-text="关闭" />
          <div class="gs-form-hint">生成业务流程叙事、风险卡片、What-If 场景、测试矩阵</div>
        </el-form-item>

        <template v-if="form.enable_ai">
          <el-divider content-position="left">AI 配置</el-divider>
          <el-form-item label="AI 提供者">
            <el-select v-model="form.ai_provider" placeholder="选择 AI 提供商" style="width:100%" @change="onProviderChange">
              <el-option v-for="p in aiProviders" :key="p.provider_id" :value="p.provider_id">
                <div class="gs-provider-option">
                  <span class="gs-provider-dot" :class="{ 'gs-healthy': p.healthy, 'gs-unhealthy': p.healthy === false }"></span>
                  <span class="gs-provider-name">{{ p.display_name || p.provider_id }}</span>
                  <el-tag size="small" :type="p.provider_type === 'local' ? 'success' : p.provider_type === 'cloud' ? 'primary' : 'info'">
                    {{ p.provider_type === 'local' ? '本地' : p.provider_type === 'cloud' ? '云端' : '自定义' }}
                  </el-tag>
                </div>
              </el-option>
            </el-select>
            <div v-if="selectedProviderHealthy === false" class="gs-form-hint gs-warn">
              ⚠ 当前提供商不可用，请先在"设置"中配置 API Key 或启动本地服务
            </div>
          </el-form-item>
          <el-form-item label="AI 模型">
            <el-select v-model="form.ai_model" placeholder="选择模型" style="width:100%" filterable allow-create>
              <el-option v-for="m in currentModels" :key="m" :label="m" :value="m" />
            </el-select>
          </el-form-item>
        </template>

        <el-form-item style="margin-top:24px">
          <el-button type="primary" @click="startAnalysis" :loading="starting" size="large" :disabled="!canStart">
            <el-icon><VideoPlay /></el-icon> 开始分析
          </el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <!-- 分析进度 -->
    <el-card v-if="mode === 'running'" shadow="hover" class="gs-section">
      <template #header>
        <div class="gs-header-row">
          <span class="gs-card-title">分析进行中</span>
          <el-tag type="warning" size="small">{{ progress.current_step || '准备中...' }}</el-tag>
        </div>
      </template>
      <el-progress :percentage="progress.progress_percent || 0" :stroke-width="20" striped striped-flow />
      <div class="gs-progress-meta">
        <span class="gs-elapsed">
          <el-icon><Timer /></el-icon>
          已用时: {{ formatDuration(liveElapsed) }}
        </span>
        <span v-if="progress.estimated_remaining" class="gs-remaining">
          <el-icon><Clock /></el-icon>
          预计剩余: {{ formatDuration(progress.estimated_remaining) }}
        </span>
      </div>
      <div class="gs-progress-steps">
        <div 
          v-for="step in progress.steps" 
          :key="step.name" 
          class="gs-progress-step" 
          :class="{ 
            'gs-step-active': step.status === 'running',
            'gs-step-sub': step.is_sub_step 
          }"
        >
          <el-icon v-if="step.status === 'completed'" class="gs-step-icon gs-step-done"><CircleCheck /></el-icon>
          <el-icon v-else-if="step.status === 'running'" class="gs-step-icon gs-step-running"><Loading /></el-icon>
          <el-icon v-else-if="step.status === 'failed'" class="gs-step-icon gs-step-failed"><CircleClose /></el-icon>
          <el-icon v-else class="gs-step-icon gs-step-pending"><Clock /></el-icon>
          <span class="gs-step-name">{{ step.name }}</span>
          <!-- 子进度显示 -->
          <span v-if="step.sub_progress && step.status === 'running'" class="gs-step-sub-progress">
            ({{ step.sub_progress.completed }}/{{ step.sub_progress.total }})
          </span>
          <!-- 已完成耗时 -->
          <span v-if="step.duration_ms" class="gs-step-duration">
            {{ (step.duration_ms / 1000).toFixed(1) }}s
          </span>
          <!-- 正在运行的实时计时 -->
          <span v-else-if="step.status === 'running' && step.started_at" class="gs-step-duration gs-step-live">
            {{ getStepLiveTime(step) }}s
          </span>
        </div>
      </div>
      <div style="margin-top:16px">
        <el-button @click="backToList">返回列表</el-button>
      </div>
    </el-card>

    <!-- 分析失败 -->
    <el-alert v-if="mode === 'failed'" type="error" :title="'分析失败: ' + (error || '未知错误')" show-icon class="gs-section">
      <div style="margin-top:8px">
        <el-button @click="switchToCreate" size="small">重新创建</el-button>
        <el-button @click="mode = 'list'" size="small">返回列表</el-button>
      </div>
    </el-alert>

    <!-- 分析结果 Tabs -->
    <el-card v-if="mode === 'result'" shadow="hover" class="gs-section">
      <template #header>
        <div class="gs-result-header">
          <span class="gs-card-title">分析结果</span>
          <div class="gs-result-actions">
            <el-dropdown @command="exportResults">
              <el-button type="primary" plain>
                <el-icon><Download /></el-icon> 导出
              </el-button>
              <template #dropdown>
                <el-dropdown-menu>
                  <el-dropdown-item command="json">完整报告 (JSON)</el-dropdown-item>
                  <el-dropdown-item command="csv">测试矩阵 (CSV)</el-dropdown-item>
                  <el-dropdown-item command="risk-cards">风险卡片 (JSON)</el-dropdown-item>
                  <el-dropdown-item command="function-dict">函数词典 (JSON)</el-dropdown-item>
                </el-dropdown-menu>
              </template>
            </el-dropdown>
            <el-button @click="switchToCreate">新建分析</el-button>
            <el-button @click="mode = 'list'">返回列表</el-button>
          </div>
        </div>
      </template>

      <el-tabs v-model="activeTab" type="border-card">
        <el-tab-pane name="callgraph">
          <template #label>
            调用图
            <el-badge v-if="callGraph.nodes?.length" :value="callGraph.nodes.length" class="gs-tab-badge" type="info" />
          </template>
          <FusedCallGraph :data="callGraph" />
        </el-tab-pane>

        <el-tab-pane name="risks">
          <template #label>
            风险发现
            <el-badge v-if="risks.findings?.length" :value="risks.findings.length" class="gs-tab-badge" :type="risks.summary?.severity_distribution?.critical ? 'danger' : 'warning'" />
          </template>
          <RiskFindings :findings="risks.findings" :summary="risks.summary" />
        </el-tab-pane>

        <el-tab-pane name="deep-analysis">
          <template #label>
            深度分析
            <el-badge v-if="deepAnalysis.findings?.length" :value="deepAnalysis.findings.length" class="gs-tab-badge" type="danger" />
          </template>
          <DeepAnalysisFindings :findings="deepAnalysis.findings" :semantic-index="semanticIndex" />
        </el-tab-pane>

        <el-tab-pane name="risk-cards">
          <template #label>
            风险卡片
            <el-badge v-if="riskCards?.length" :value="riskCards.length" class="gs-tab-badge" type="warning" />
          </template>
          <RiskScenarioCards :cards="riskCards" />
        </el-tab-pane>

        <el-tab-pane name="narratives">
          <template #label>
            流程叙事
            <el-badge v-if="narratives.flow_narratives?.length" :value="narratives.flow_narratives.length" class="gs-tab-badge" type="primary" />
          </template>
          <FlowNarratives :narratives="narratives.flow_narratives" />
        </el-tab-pane>

        <el-tab-pane name="function-dict">
          <template #label>
            函数词典
            <el-badge v-if="Object.keys(functionDict || {}).length" :value="Object.keys(functionDict).length" class="gs-tab-badge" type="info" />
          </template>
          <FunctionDictionary :dictionary="functionDict" />
        </el-tab-pane>

        <el-tab-pane name="what-if">
          <template #label>
            What-If
            <el-badge v-if="whatIfScenarios?.length" :value="whatIfScenarios.length" class="gs-tab-badge" type="primary" />
          </template>
          <WhatIfScenarios :scenarios="whatIfScenarios" />
        </el-tab-pane>

        <el-tab-pane name="test-matrix">
          <template #label>
            测试矩阵
            <el-badge v-if="testMatrix.test_cases?.length" :value="testMatrix.test_cases.length" class="gs-tab-badge" type="success" />
          </template>
          <TestDesignMatrix :matrix="testMatrix" />
        </el-tab-pane>

        <el-tab-pane name="protocol-sm">
          <template #label>
            协议状态机
            <el-badge v-if="protocolSmStateCount" :value="protocolSmStateCount" class="gs-tab-badge" type="info" />
          </template>
          <ProtocolStateMachine :data="protocolSM" />
        </el-tab-pane>
      </el-tabs>
    </el-card>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import { VideoPlay, Download, CircleCheck, CircleClose, Loading, Clock, Plus, Back, Timer } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import api from '../api.js'

import FusedCallGraph from '../components/analysis/FusedCallGraph.vue'
import RiskFindings from '../components/analysis/RiskFindings.vue'
import RiskScenarioCards from '../components/analysis/RiskScenarioCards.vue'
import FlowNarratives from '../components/analysis/FlowNarratives.vue'
import FunctionDictionary from '../components/analysis/FunctionDictionary.vue'
import WhatIfScenarios from '../components/analysis/WhatIfScenarios.vue'
import TestDesignMatrix from '../components/analysis/TestDesignMatrix.vue'
import ProtocolStateMachine from '../components/analysis/ProtocolStateMachine.vue'
import DeepAnalysisFindings from '../components/analysis/DeepAnalysisFindings.vue'

const mode = ref('list')

const loadingList = ref(false)
const analysesList = ref([])

const projects = ref([])
const repos = ref([])
const aiProviders = ref([])

const form = ref({
  project_id: null,
  repo_id: null,
  sub_path: '',
  enable_ai: true,
  max_files: 500,
  ai_provider: '',
  ai_model: '',
})

const starting = ref(false)
const analysisId = ref(null)
const progress = ref({})
const error = ref('')
const activeTab = ref('callgraph')

const callGraph = ref({ nodes: [], edges: [] })
const risks = ref({ findings: [], summary: {} })
const riskCards = ref([])
const narratives = ref({})
const functionDict = ref({})
const whatIfScenarios = ref([])
const testMatrix = ref({})
const protocolSM = ref({})
const deepAnalysis = ref({ findings: [] })
const semanticIndex = ref({})

let pollTimer = null
let liveTimer = null
const nowTimestamp = ref(Date.now())

const selectedRepo = computed(() => repos.value.find(r => r.repo_id === form.value.repo_id))

const protocolSmStateCount = computed(() => {
  const s = protocolSM.value?.states
  if (!s) return 0
  if (Array.isArray(s)) return s.length
  return Object.keys(s).length
})

// 实时计算已用时间（秒）
const liveElapsed = computed(() => {
  if (progress.value.started_at) {
    const started = new Date(progress.value.started_at).getTime()
    return Math.floor((nowTimestamp.value - started) / 1000)
  }
  return progress.value.elapsed_seconds || 0
})

// 计算正在运行步骤的实时耗时
function getStepLiveTime(step) {
  if (!step.started_at) return '0.0'
  const started = new Date(step.started_at).getTime()
  const elapsed = (nowTimestamp.value - started) / 1000
  return elapsed.toFixed(1)
}

// 启动实时计时器
function startLiveTimer() {
  if (liveTimer) return
  liveTimer = setInterval(() => {
    nowTimestamp.value = Date.now()
  }, 100) // 每100ms更新一次，显示更流畅
}

// 停止实时计时器
function stopLiveTimer() {
  if (liveTimer) {
    clearInterval(liveTimer)
    liveTimer = null
  }
}

const currentModels = computed(() => {
  const p = aiProviders.value.find(m => m.provider_id === form.value.ai_provider)
  return p?.models || ['default']
})

const selectedProviderHealthy = computed(() => {
  const p = aiProviders.value.find(m => m.provider_id === form.value.ai_provider)
  return p?.healthy ?? null
})

const canStart = computed(() => {
  if (!form.value.repo_id) return false
  if (!selectedRepo.value?.local_mirror_path) return false
  return true
})

async function loadAnalysesList() {
  loadingList.value = true
  try {
    const data = await api.listCodeAnalyses()
    analysesList.value = data?.analyses || data?.items || (Array.isArray(data) ? data : [])
  } catch (e) {
    ElMessage.error('加载分析列表失败: ' + e.message)
  } finally {
    loadingList.value = false
  }
}

async function loadProjects() {
  try {
    const data = await api.listProjects()
    projects.value = data?.items || data?.projects || (Array.isArray(data) ? data : [])
  } catch {}
}

async function loadAIProviders() {
  try {
    const data = await api.listModels()
    aiProviders.value = data?.providers || (Array.isArray(data) ? data : [])
    const savedProvider = localStorage.getItem('gs_default_provider')
    if (savedProvider && aiProviders.value.some(p => p.provider_id === savedProvider)) {
      form.value.ai_provider = savedProvider
      const p = aiProviders.value.find(m => m.provider_id === savedProvider)
      form.value.ai_model = p?.models?.[0] || 'default'
    } else if (aiProviders.value.length > 0) {
      form.value.ai_provider = aiProviders.value[0].provider_id
      form.value.ai_model = aiProviders.value[0].models?.[0] || 'default'
    }
  } catch {}
}

async function onProjectChange() {
  form.value.repo_id = null
  repos.value = []
  if (!form.value.project_id) return
  try {
    const data = await api.listRepos(form.value.project_id)
    repos.value = Array.isArray(data) ? data : (data?.repos || data?.items || [])
  } catch {}
}

function onProviderChange() {
  const p = aiProviders.value.find(m => m.provider_id === form.value.ai_provider)
  form.value.ai_model = p?.models?.[0] || 'default'
}

function switchToCreate() {
  mode.value = 'create'
}

function backToList() {
  stopPolling()
  mode.value = 'list'
  loadAnalysesList()
}

function repoLabel(r) {
  const name = r.name || r.git_url || ''
  const hasLocal = !!r.local_mirror_path
  return hasLocal ? name : `${name} (未同步)`
}

async function startAnalysis() {
  if (!form.value.repo_id || !selectedRepo.value?.local_mirror_path) {
    ElMessage.warning('请选择一个已同步的仓库')
    return
  }
  starting.value = true
  try {
    const payload = {
      project_id: form.value.project_id,
      repo_id: form.value.repo_id,
      sub_path: form.value.sub_path || undefined,
      enable_ai: form.value.enable_ai,
      max_files: form.value.max_files,
      ai_provider: form.value.ai_provider || undefined,
      ai_model: form.value.ai_model || undefined,
    }
    const res = await api.startCodeAnalysis(payload)
    analysisId.value = res.analysis_id
    mode.value = 'running'
    startPolling()
    ElMessage.success('分析任务已启动')
  } catch (e) {
    ElMessage.error('启动失败: ' + e.message)
  } finally {
    starting.value = false
  }
}

async function pollProgress() {
  try {
    const res = await api.getCodeAnalysisStatus(analysisId.value)
    progress.value = res.progress || {}

    if (res.status === 'completed') {
      stopPolling()
      await loadResults()
      mode.value = 'result'
    } else if (res.status === 'failed') {
      stopPolling()
      error.value = res.error || '未知错误'
      mode.value = 'failed'
    }
  } catch (e) {
    console.error('Polling error:', e)
  }
}

function startPolling() {
  startLiveTimer()
  pollTimer = setInterval(pollProgress, 2000)
}

function stopPolling() {
  stopLiveTimer()
  if (pollTimer) {
    clearInterval(pollTimer)
    pollTimer = null
  }
}

async function loadResults() {
  const results = await Promise.allSettled([
    api.getCodeAnalysisCallGraph(analysisId.value),
    api.getCodeAnalysisRisks(analysisId.value),
    api.getCodeAnalysisRiskCards(analysisId.value),
    api.getCodeAnalysisNarratives(analysisId.value),
    api.getCodeAnalysisFunctionDict(analysisId.value),
    api.getCodeAnalysisWhatIf(analysisId.value),
    api.getCodeAnalysisTestMatrix(analysisId.value),
    api.getCodeAnalysisProtocolSM(analysisId.value),
    api.getCodeAnalysisDeepFindings(analysisId.value),
    api.getCodeAnalysisSemanticIndex(analysisId.value),
  ])
  
  // Helper to extract value from settled result
  const getValue = (r, fallback = null) => r.status === 'fulfilled' ? r.value : fallback
  
  callGraph.value = getValue(results[0])
  risks.value = getValue(results[1])
  riskCards.value = getValue(results[2])?.cards || []
  narratives.value = getValue(results[3])
  functionDict.value = getValue(results[4])
  whatIfScenarios.value = getValue(results[5])?.scenarios || []
  testMatrix.value = getValue(results[6])
  protocolSM.value = getValue(results[7])
  deepAnalysis.value = getValue(results[8]) || { findings: [] }
  semanticIndex.value = getValue(results[9]) || {}
  
  // Warn about any failures without blocking other results
  const failures = results.filter(r => r.status === 'rejected')
  if (failures.length > 0) {
    console.warn('Some result APIs failed:', failures.map(f => f.reason))
  }
}

async function viewAnalysis(row) {
  analysisId.value = row.analysis_id
  await loadResults()
  mode.value = 'result'
}

async function viewRunning(row) {
  analysisId.value = row.analysis_id
  mode.value = 'running'
  await pollProgress()  // Immediate first fetch to avoid 2s delay
  startPolling()
}

async function deleteAnalysis(id) {
  try {
    await api.deleteCodeAnalysis(id)
    ElMessage.success('删除成功')
    loadAnalysesList()
  } catch (e) {
    ElMessage.error('删除失败: ' + e.message)
  }
}

function exportResults(fmt) {
  window.open(api.exportCodeAnalysis(analysisId.value, fmt), '_blank')
}

function formatDuration(seconds) {
  if (!seconds || seconds < 0) return '--'
  if (seconds < 60) return `${seconds.toFixed(0)}秒`
  const mins = Math.floor(seconds / 60)
  const secs = Math.round(seconds % 60)
  return secs > 0 ? `${mins}分${secs}秒` : `${mins}分`
}

function formatTime(isoStr) {
  if (!isoStr) return '--'
  try {
    return new Date(isoStr).toLocaleString('zh-CN')
  } catch {
    return isoStr
  }
}

function statusType(s) {
  if (s === 'completed') return 'success'
  if (s === 'running') return 'warning'
  if (s === 'failed') return 'danger'
  return 'info'
}

function statusLabel(s) {
  const map = { completed: '已完成', running: '运行中', failed: '失败', pending: '等待中' }
  return map[s] || s
}

onMounted(async () => {
  await Promise.all([loadAnalysesList(), loadProjects(), loadAIProviders()])
})

onUnmounted(() => {
  stopPolling()
  stopLiveTimer()
})
</script>

<style scoped>
.gs-section {
  margin-bottom: 20px;
}
.gs-card-title {
  font-weight: 600;
  font-size: 16px;
}
.gs-form-hint {
  color: var(--el-text-color-secondary);
  font-size: 12px;
  margin-top: 4px;
}
.gs-form-hint.gs-warn {
  color: var(--el-color-warning);
}
.gs-header-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.gs-mono {
  font-family: 'Monaco', 'Menlo', monospace;
  font-size: 12px;
}
.gs-empty {
  padding: 40px 0;
}
.gs-provider-option {
  display: flex;
  align-items: center;
  gap: 8px;
}
.gs-provider-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #999;
}
.gs-provider-dot.gs-healthy {
  background: #00AA00;
}
.gs-provider-dot.gs-unhealthy {
  background: #D50000;
}
.gs-provider-name {
  font-weight: 500;
  flex: 1;
}
.gs-progress-steps {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-top: 16px;
}
.gs-progress-step {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  padding: 4px 8px;
  border-radius: 4px;
  transition: background-color 0.2s;
}
.gs-progress-step:hover {
  background: var(--el-fill-color-light);
}
.gs-step-sub {
  margin-left: 24px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.gs-step-icon {
  font-size: 16px;
  color: var(--el-text-color-secondary);
  flex-shrink: 0;
}
.gs-step-pending {
  opacity: 0.5;
}
.gs-step-done {
  color: var(--el-color-success);
}
.gs-step-running {
  color: var(--el-color-warning);
  animation: spin 1s linear infinite;
}
.gs-step-failed {
  color: var(--el-color-danger);
}
.gs-step-name {
  flex: 1;
}
.gs-step-sub-progress {
  font-size: 11px;
  color: var(--el-color-primary);
  font-weight: 500;
  margin-left: 4px;
}
@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}
.gs-result-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.gs-result-actions {
  display: flex;
  gap: 8px;
}
.gs-progress-meta {
  display: flex;
  gap: 24px;
  margin-top: 12px;
  font-size: 13px;
  color: var(--el-text-color-secondary);
}
.gs-progress-meta span {
  display: flex;
  align-items: center;
  gap: 4px;
}
.gs-elapsed {
  color: var(--el-color-primary);
  font-weight: 500;
}
.gs-remaining {
  color: var(--el-color-warning);
}
.gs-step-duration {
  font-size: 11px;
  color: var(--el-text-color-placeholder);
  margin-left: auto;
  font-family: 'Monaco', 'Menlo', monospace;
}
.gs-step-live {
  color: var(--el-color-warning);
  animation: pulse 1s ease-in-out infinite;
}
@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.6; }
}
.gs-step-active {
  font-weight: 500;
  color: var(--el-color-primary);
  background: var(--el-color-primary-light-9);
}
.gs-tab-badge {
  margin-left: 6px;
}
.gs-tab-badge :deep(.el-badge__content) {
  font-size: 11px;
}
</style>
