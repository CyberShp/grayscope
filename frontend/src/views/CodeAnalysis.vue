<template>
  <div class="gs-page">
    <div class="gs-page-header">
      <h1 class="gs-page-title">代码分析流水线</h1>
      <p class="gs-page-desc">端到端分析：调用链 → 风险识别 → AI叙事 → 测试指导</p>
    </div>

    <!-- 启动分析表单 -->
    <el-card v-if="!analysisId" shadow="hover" class="gs-section">
      <template #header>
        <span class="gs-card-title">启动新分析</span>
      </template>
      <el-form :model="form" label-width="120px" style="max-width:700px">
        <el-form-item label="代码路径" required>
          <el-input v-model="form.workspace_path" placeholder="例如: /path/to/your/code" />
          <div class="gs-form-hint">本地代码目录的绝对路径</div>
        </el-form-item>
        <el-form-item label="最大文件数">
          <el-slider v-model="form.max_files" :min="50" :max="1000" :step="50" show-input style="max-width:400px" />
        </el-form-item>
        <el-form-item label="AI 增强">
          <el-switch v-model="form.enable_ai" active-text="启用" inactive-text="关闭" />
          <div class="gs-form-hint">生成业务流程叙事、风险卡片、What-If 场景、测试矩阵</div>
        </el-form-item>
        <template v-if="form.enable_ai">
          <el-form-item label="AI 提供者">
            <el-select v-model="form.ai_provider" style="width:200px">
              <el-option value="deepseek" label="DeepSeek" />
              <el-option value="custom" label="自定义接口" />
            </el-select>
          </el-form-item>
          <el-form-item label="模型">
            <el-input v-model="form.ai_model" placeholder="deepseek-coder" style="width:200px" />
          </el-form-item>
          <el-form-item label="Base URL">
            <el-input v-model="form.ai_base_url" placeholder="使用设置中的配置" />
          </el-form-item>
          <el-form-item label="API Key">
            <el-input v-model="form.ai_api_key" placeholder="使用设置中的配置" type="password" show-password />
          </el-form-item>
        </template>
        <el-form-item>
          <el-button type="primary" @click="startAnalysis" :loading="starting" size="large">
            <el-icon><VideoPlay /></el-icon> 开始分析
          </el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <!-- 分析进度 -->
    <el-card v-if="analysisId && status === 'running'" shadow="hover" class="gs-section">
      <template #header>
        <span class="gs-card-title">分析进行中</span>
        <el-tag type="warning" size="small">{{ progress.current_step || '准备中...' }}</el-tag>
      </template>
      <el-progress :percentage="progress.progress_percent || 0" :stroke-width="20" striped striped-flow />
      <div class="gs-progress-steps">
        <div v-for="step in progress.steps" :key="step.name" class="gs-progress-step">
          <el-icon v-if="step.status === 'completed'" class="gs-step-icon gs-step-done"><CircleCheck /></el-icon>
          <el-icon v-else-if="step.status === 'running'" class="gs-step-icon gs-step-running"><Loading /></el-icon>
          <el-icon v-else-if="step.status === 'failed'" class="gs-step-icon gs-step-failed"><CircleClose /></el-icon>
          <el-icon v-else class="gs-step-icon"><Clock /></el-icon>
          <span>{{ step.name }}</span>
        </div>
      </div>
    </el-card>

    <!-- 分析失败 -->
    <el-alert v-if="status === 'failed'" type="error" :title="'分析失败: ' + (error || '未知错误')" show-icon class="gs-section">
      <el-button @click="resetAnalysis" size="small" style="margin-top:8px">重新开始</el-button>
    </el-alert>

    <!-- 分析结果 Tabs -->
    <el-card v-if="status === 'completed'" shadow="hover" class="gs-section">
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
            <el-button @click="resetAnalysis">新建分析</el-button>
          </div>
        </div>
      </template>

      <el-tabs v-model="activeTab" type="border-card">
        <!-- 调用图 -->
        <el-tab-pane label="调用图" name="callgraph">
          <FusedCallGraph :data="callGraph" />
        </el-tab-pane>

        <!-- 风险发现 -->
        <el-tab-pane label="风险发现" name="risks">
          <RiskFindings :findings="risks.findings" :summary="risks.summary" />
        </el-tab-pane>

        <!-- 风险卡片 -->
        <el-tab-pane label="风险卡片" name="risk-cards">
          <RiskScenarioCards :cards="riskCards" />
        </el-tab-pane>

        <!-- 业务流程叙事 -->
        <el-tab-pane label="流程叙事" name="narratives">
          <FlowNarratives :narratives="narratives.flow_narratives" />
        </el-tab-pane>

        <!-- 函数词典 -->
        <el-tab-pane label="函数词典" name="function-dict">
          <FunctionDictionary :dictionary="functionDict" />
        </el-tab-pane>

        <!-- What-If 场景 -->
        <el-tab-pane label="What-If" name="what-if">
          <WhatIfScenarios :scenarios="whatIfScenarios" />
        </el-tab-pane>

        <!-- 测试矩阵 -->
        <el-tab-pane label="测试矩阵" name="test-matrix">
          <TestDesignMatrix :matrix="testMatrix" />
        </el-tab-pane>

        <!-- 协议状态机 -->
        <el-tab-pane label="协议状态机" name="protocol-sm">
          <ProtocolStateMachine :data="protocolSM" />
        </el-tab-pane>
      </el-tabs>
    </el-card>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import { VideoPlay, Download, CircleCheck, CircleClose, Loading, Clock } from '@element-plus/icons-vue'
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

const form = ref({
  workspace_path: '',
  enable_ai: true,
  max_files: 500,
  ai_provider: 'deepseek',
  ai_model: 'deepseek-coder',
  ai_base_url: '',
  ai_api_key: '',
})

const starting = ref(false)
const analysisId = ref(null)
const status = ref('')
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

let pollTimer = null

async function startAnalysis() {
  if (!form.value.workspace_path) {
    ElMessage.warning('请填写代码路径')
    return
  }
  starting.value = true
  try {
    const res = await api.startCodeAnalysis(form.value)
    analysisId.value = res.analysis_id
    status.value = 'running'
    startPolling()
    ElMessage.success('分析任务已启动')
  } catch (e) {
    ElMessage.error('启动失败: ' + e.message)
  } finally {
    starting.value = false
  }
}

function startPolling() {
  pollTimer = setInterval(async () => {
    try {
      const res = await api.getCodeAnalysisStatus(analysisId.value)
      progress.value = res.progress || {}
      status.value = res.status

      if (res.status === 'completed') {
        stopPolling()
        await loadResults()
      } else if (res.status === 'failed') {
        stopPolling()
        error.value = res.error || '未知错误'
      }
    } catch (e) {
      console.error('Polling error:', e)
    }
  }, 2000)
}

function stopPolling() {
  if (pollTimer) {
    clearInterval(pollTimer)
    pollTimer = null
  }
}

async function loadResults() {
  try {
    const [cg, rk, cards, narr, fd, wi, tm, psm] = await Promise.all([
      api.getCodeAnalysisCallGraph(analysisId.value),
      api.getCodeAnalysisRisks(analysisId.value),
      api.getCodeAnalysisRiskCards(analysisId.value),
      api.getCodeAnalysisNarratives(analysisId.value),
      api.getCodeAnalysisFunctionDict(analysisId.value),
      api.getCodeAnalysisWhatIf(analysisId.value),
      api.getCodeAnalysisTestMatrix(analysisId.value),
      api.getCodeAnalysisProtocolSM(analysisId.value),
    ])
    callGraph.value = cg
    risks.value = rk
    riskCards.value = cards.cards || []
    narratives.value = narr
    functionDict.value = fd
    whatIfScenarios.value = wi.scenarios || []
    testMatrix.value = tm
    protocolSM.value = psm
  } catch (e) {
    ElMessage.error('加载结果失败: ' + e.message)
  }
}

function exportResults(fmt) {
  window.open(api.exportCodeAnalysis(analysisId.value, fmt), '_blank')
}

function resetAnalysis() {
  analysisId.value = null
  status.value = ''
  progress.value = {}
  error.value = ''
  callGraph.value = { nodes: [], edges: [] }
  risks.value = { findings: [], summary: {} }
  riskCards.value = []
  narratives.value = {}
  functionDict.value = {}
  whatIfScenarios.value = []
  testMatrix.value = {}
  protocolSM.value = {}
}

onMounted(() => {
  const saved = localStorage.getItem('gs_default_provider')
  if (saved) form.value.ai_provider = saved === 'custom' ? 'custom' : 'deepseek'
})

onUnmounted(() => {
  stopPolling()
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
.gs-progress-steps {
  display: flex;
  gap: 24px;
  margin-top: 16px;
  flex-wrap: wrap;
}
.gs-progress-step {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
}
.gs-step-icon {
  font-size: 18px;
  color: var(--el-text-color-secondary);
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
</style>
