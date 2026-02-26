<template>
  <div class="gs-page">
    <router-link to="/test-execution" class="gs-back-link">&larr; 返回测试执行</router-link>

    <div v-if="run" class="gs-page-header">
      <h1 class="gs-page-title">测试运行详情</h1>
      <p class="gs-page-desc">{{ run.name || '运行 ID: ' + run.run_id }}</p>
      <div class="gs-run-meta">
        <span class="gs-status-dot" :class="'gs-status-dot--' + run.status"></span>
        {{ runStatusLabel(run.status) }}
        <span class="gs-meta-sep">|</span>
        环境: {{ run.environment }}
        <span class="gs-meta-sep">|</span>
        通过 {{ run.passed }} / 失败 {{ run.failed }} / 跳过 {{ run.skipped }} / 共 {{ run.total }}
        <span v-if="run.started_at" class="gs-meta-sep">|</span>
        <span v-if="run.started_at">开始: {{ formatDate(run.started_at) }}</span>
        <span v-if="run.finished_at"> 结束: {{ formatDate(run.finished_at) }}</span>
      </div>
      <div class="gs-run-actions">
        <el-button
          v-if="run.status === 'pending' || run.status === 'paused'"
          type="primary"
          size="default"
          @click="triggerExecute"
        >
          {{ run.status === 'paused' ? '恢复执行' : '触发执行' }}
        </el-button>
        <el-button
          v-if="['success', 'failed', 'cancelled'].includes(run.status)"
          type="primary"
          size="default"
          @click="rerunRun"
        >
          重新运行
        </el-button>
        <el-button v-if="run.status === 'running'" size="default" @click="pauseRun">暂停</el-button>
        <el-button
          v-if="run.status === 'running' || run.status === 'paused'"
          type="danger"
          size="default"
          @click="cancelRun"
        >
          强制停止
        </el-button>
        <el-button type="danger" plain size="default" @click="deleteRun">删除运行</el-button>
      </div>
    </div>

    <div v-if="run" class="gs-card gs-section">
      <div class="gs-section-head">
        <h3 class="gs-section-title">用例执行结果</h3>
        <div class="gs-filter-actions">
          <el-radio-group v-model="statusFilter" size="small" class="gs-status-filter">
            <el-radio-button label="all">全部 ({{ executions.length }})</el-radio-button>
            <el-radio-button label="passed">成功 ({{ executionGroupCounts.passed }})</el-radio-button>
            <el-radio-button label="failed">失败 ({{ executionGroupCounts.failed }})</el-radio-button>
            <el-radio-button label="skipped">跳过 ({{ executionGroupCounts.skipped }})</el-radio-button>
            <el-radio-button label="pending">待执行 ({{ executionGroupCounts.pending }})</el-radio-button>
          </el-radio-group>
          <el-button
            v-if="executionGroupCounts.failed > 0 && ['success', 'failed', 'cancelled'].includes(run.status)"
            type="primary"
            size="small"
            @click="openRetestDialog"
          >
            补测失败用例
          </el-button>
        </div>
      </div>
      <el-table :data="filteredExecutions" size="small" class="gs-table">
        <el-table-column label="用例编号" width="120">
          <template #default="{ row }">{{ row.case_id || 'TC-' + row.test_case_id }}</template>
        </el-table-column>
        <el-table-column label="名称" min-width="180">
          <template #default="{ row }">{{ row.title || '-' }}</template>
        </el-table-column>
        <el-table-column label="状态" width="120">
          <template #default="{ row }">
            <span class="gs-status-dot" :class="'gs-status-dot--' + (row.execution_status || row.status)"></span>
            {{ executionStatusLabel(row.execution_status || row.status) }}
          </template>
        </el-table-column>
        <el-table-column label="开始/结束">
          <template #default="{ row }">
            <span v-if="row.started_at">{{ formatDate(row.started_at) }}</span>
            <span v-else class="gs-text-muted">-</span>
            <span v-if="row.finished_at"> → {{ formatDate(row.finished_at) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="输出/日志" min-width="280">
          <template #default="{ row }">
            <div v-if="logText(row.result)" class="gs-log-cell">
              <pre class="gs-log-pre">{{ logText(row.result) }}</pre>
              <el-button text type="primary" size="small" class="gs-log-copy" @click="copyLog(logText(row.result))">
                复制
              </el-button>
            </div>
            <span v-else class="gs-text-muted">-</span>
          </template>
        </el-table-column>
      </el-table>
      <el-empty v-if="!loading && !filteredExecutions.length" :description="statusFilter === 'all' ? '暂无执行记录' : '当前筛选无结果'" />

      <!-- 补测弹窗 -->
      <el-dialog
        v-model="showRetestDialog"
        title="生成补测任务"
        width="440"
        destroy-on-close
        @close="onCloseRetestDialog"
      >
        <p class="gs-retest-hint">将使用当前运行的失败用例创建新运行，继承环境与镜像。</p>
        <el-form :model="retestForm" label-width="80px">
          <el-form-item label="运行名称">
            <el-input v-model="retestForm.name" placeholder="不填则使用 补测-原运行ID" clearable />
          </el-form-item>
        </el-form>
        <template #footer>
          <el-button @click="showRetestDialog = false">取消</el-button>
          <el-button type="primary" :loading="creatingRetest" @click="createRetestRun">
            创建并跳转
          </el-button>
        </template>
      </el-dialog>
    </div>

    <div v-else-if="!loading" class="gs-card">
      <el-empty description="未找到该运行记录" />
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useFormatDate } from '../composables/useFormatDate.js'
import api from '../api.js'

const props = defineProps({
  runId: { type: String, required: true },
})

const route = useRoute()
const router = useRouter()
const runId = props.runId || route.params.runId
const { formatDate } = useFormatDate()

const loading = ref(true)
const run = ref(null)
const executions = ref([])
const statusFilter = ref('all')
const showRetestDialog = ref(false)
const retestForm = ref({ name: '' })
const creatingRetest = ref(false)
let pollTimer = null

/** 将 execution_status 归为：passed / failed / skipped / pending */
function executionGroup(execution_status) {
  const s = execution_status || ''
  if (s === 'passed') return 'passed'
  if (['assertion_fail', 'runtime_error', 'compile_error'].includes(s) || s === 'failed') return 'failed'
  if (s === 'skipped') return 'skipped'
  return 'pending'
}

const executionGroupCounts = computed(() => {
  const counts = { passed: 0, failed: 0, skipped: 0, pending: 0 }
  for (const row of executions.value) {
    const g = executionGroup(row.execution_status || row.status)
    counts[g]++
  }
  return counts
})

const filteredExecutions = computed(() => {
  if (statusFilter.value === 'all') return executions.value
  return executions.value.filter(row => executionGroup(row.execution_status || row.status) === statusFilter.value)
})

const failedCaseIds = computed(() => {
  return executions.value
    .filter(row => executionGroup(row.execution_status || row.status) === 'failed')
    .map(row => row.test_case_id)
    .filter(Boolean)
})

function startPolling() {
  if (pollTimer) return
  pollTimer = setInterval(() => {
    if (run.value && run.value.status === 'running') loadDetail(true)
  }, 1000)
}

function stopPolling() {
  if (pollTimer) {
    clearInterval(pollTimer)
    pollTimer = null
  }
}

function runStatusLabel(s) {
  const map = {
    pending: '待执行',
    running: '运行中',
    paused: '已暂停',
    cancelled: '已取消',
    success: '成功',
    failed: '失败',
  }
  return map[s] || s
}

function executionStatusLabel(s) {
  const map = {
    passed: '通过',
    assertion_fail: '断言失败',
    runtime_error: '运行时错误',
    compile_error: '编译错误',
    pending: '待执行',
    skipped: '跳过',
  }
  return map[s] || s || '-'
}

function logText(result) {
  if (!result) return ''
  const parts = []
  if (result.build_log) parts.push('[构建] ' + result.build_log)
  if (result.run_log) parts.push('[运行] ' + result.run_log)
  if (result.stdout) parts.push(result.stdout)
  if (result.stderr) parts.push(result.stderr)
  if (result.message) parts.push(result.message)
  return parts.join('\n\n') || ''
}

async function copyLog(text) {
  try {
    await navigator.clipboard.writeText(text)
    ElMessage.success('已复制到剪贴板')
  } catch {
    ElMessage.error('复制失败')
  }
}

async function loadDetail(silent = false) {
  if (!runId) return
  if (!silent) loading.value = true
  try {
    const data = await api.getTestRun(runId)
    run.value = data?.test_run || null
    executions.value = data?.executions || []
    if (run.value?.status === 'running') startPolling()
    else stopPolling()
  } catch {
    run.value = null
    executions.value = []
  } finally {
    if (!silent) loading.value = false
  }
}

async function triggerExecute() {
  try {
    await api.executeTestRun(runId)
    ElMessage.success(run.value?.status === 'paused' ? '已加入队列，将恢复执行' : '已加入执行队列')
    await loadDetail()
  } catch (e) {
    ElMessage.error('触发执行失败: ' + (e.message || e))
  }
}

async function rerunRun() {
  try {
    const data = await api.rerunTestRun(runId)
    if (data && data.ok === false) {
      ElMessage.error(data.message || '重新运行失败')
      return
    }
    ElMessage.success('已重置并加入执行队列')
    await loadDetail()
  } catch (e) {
    ElMessage.error('重新运行失败: ' + (e.message || e))
  }
}

async function pauseRun() {
  try {
    await api.pauseTestRun(runId)
    ElMessage.success('已暂停')
    await loadDetail()
  } catch (e) {
    ElMessage.error('暂停失败: ' + (e.message || e))
  }
}

async function cancelRun() {
  try {
    await api.cancelTestRun(runId)
    ElMessage.success('已强制停止')
    await loadDetail()
  } catch (e) {
    ElMessage.error('停止失败: ' + (e.message || e))
  }
}

async function deleteRun() {
  try {
    await ElMessageBox.confirm(`确定删除运行 ${runId}？删除后不可恢复。`, '删除运行', {
      confirmButtonText: '删除',
      cancelButtonText: '取消',
      type: 'warning',
    })
  } catch {
    return
  }
  try {
    await api.deleteTestRun(runId)
    ElMessage.success('已删除')
    router.push('/test-execution')
  } catch (e) {
    ElMessage.error('删除失败: ' + (e.message || e))
  }
}

function openRetestDialog() {
  retestForm.value.name = run.value?.run_id ? `补测-${run.value.run_id}` : '补测'
  showRetestDialog.value = true
}

function onCloseRetestDialog() {
  retestForm.value.name = ''
}

async function createRetestRun() {
  const ids = failedCaseIds.value
  if (!ids.length || !run.value) return
  const name = (retestForm.value.name && retestForm.value.name.trim()) || `补测-${run.value.run_id}`
  const body = {
    environment: run.value.environment || 'docker',
    test_case_ids: ids,
    name,
  }
  if (run.value.project_id != null) body.project_id = run.value.project_id
  if (run.value.docker_image) body.docker_image = run.value.docker_image
  creatingRetest.value = true
  try {
    const data = await api.createTestRun(body)
    const newRunId = data?.run_id || data?.id
    showRetestDialog.value = false
    ElMessage.success('补测任务已创建')
    if (newRunId) {
      router.push(`/test-execution/${newRunId}`)
    } else {
      loadDetail()
    }
  } catch (e) {
    ElMessage.error('创建补测任务失败: ' + (e.message || e))
  } finally {
    creatingRetest.value = false
  }
}

onMounted(loadDetail)
onUnmounted(stopPolling)
watch(() => props.runId || route.params.runId, () => { stopPolling(); loadDetail() })
</script>

<style scoped>
.gs-back-link { display: inline-block; margin-bottom: var(--gs-space-md); font-size: var(--gs-font-sm); color: var(--gs-text-link); text-decoration: none; }
.gs-back-link:hover { text-decoration: underline; }
.gs-run-meta { margin-top: var(--gs-space-sm); font-size: var(--gs-font-sm); color: var(--gs-text-secondary); }
.gs-meta-sep { margin: 0 8px; color: var(--gs-text-muted); }
.gs-run-actions { margin-top: var(--gs-space-md); }
.gs-section-title { margin: 0 0 var(--gs-space-md); font-size: var(--gs-font-base); font-weight: 600; }
.gs-section-head { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: var(--gs-space-md); margin-bottom: var(--gs-space-md); }
.gs-section-head .gs-section-title { margin: 0; }
.gs-filter-actions { display: flex; align-items: center; gap: var(--gs-space-sm); flex-wrap: wrap; }
.gs-status-filter { margin-right: var(--gs-space-sm); }
.gs-retest-hint { font-size: var(--gs-font-sm); color: var(--gs-text-secondary); margin: 0 0 var(--gs-space-md); }
.gs-log-cell { position: relative; }
.gs-log-pre { margin: 0; font-size: 11px; background: var(--gs-surface); padding: 8px; border-radius: 4px; max-height: 200px; overflow: auto; white-space: pre-wrap; word-break: break-all; }
.gs-log-copy { position: absolute; top: 4px; right: 4px; }
</style>
