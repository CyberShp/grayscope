<template>
  <div class="gs-page">
    <div class="gs-page-header">
      <h1 class="gs-page-title">任务中心</h1>
      <p class="gs-page-desc">管理和监控所有分析任务</p>
    </div>

    <!-- 筛选栏 -->
    <div class="gs-toolbar gs-section">
      <div class="gs-toolbar-left">
        <el-select v-model="filterProject" placeholder="所有项目" clearable size="default" style="width: 180px;">
          <el-option v-for="p in projects" :key="p.id ?? p.project_id" :label="p.name" :value="p.id ?? p.project_id" />
        </el-select>
        <el-select v-model="filterStatus" placeholder="状态" clearable size="default" style="width: 120px;" multiple collapse-tags>
          <el-option label="成功" value="success" />
          <el-option label="失败" value="failed" />
          <el-option label="运行中" value="running" />
          <el-option label="等待中" value="pending" />
          <el-option label="部分失败" value="partial_failed" />
          <el-option label="已取消" value="cancelled" />
        </el-select>
        <el-select v-model="filterType" placeholder="类型" clearable size="default" style="width: 120px;">
          <el-option label="全量" value="full" />
          <el-option label="文件" value="file" />
          <el-option label="函数" value="function" />
          <el-option label="差异" value="diff" />
          <el-option label="事后分析" value="postmortem" />
        </el-select>
        <el-button @click="loadTasks" :loading="loading" size="default">
          <el-icon><Refresh /></el-icon> 刷新
        </el-button>
        <el-button
          v-if="selectedTasks.length"
          type="danger"
          size="default"
          @click="doBatchDelete"
        >
          删除选中 ({{ selectedTasks.length }})
        </el-button>
      </div>
      <div class="gs-toolbar-right">
        <span class="gs-result-count">{{ filteredTasks.length }} 个任务</span>
        <router-link to="/analyze">
          <el-button type="primary" size="default"><el-icon><Plus /></el-icon> 新建分析</el-button>
        </router-link>
      </div>
    </div>

    <!-- 任务表格 -->
    <div class="gs-card">
      <el-table
        ref="taskTableRef"
        :data="paginatedTasks"
        size="small"
        class="gs-table"
        :default-sort="{ prop: 'created_at', order: 'descending' }"
        @selection-change="onSelectionChange"
      >
        <el-table-column type="selection" width="40" />
        <el-table-column label="任务ID" width="200">
          <template #default="{ row }">
            <router-link :to="`/tasks/${row.task_id}`" style="font-weight: 500; font-family: var(--gs-font-mono); font-size: 12px;">
              {{ (row.task_id || '').slice(0, 24) }}
            </router-link>
          </template>
        </el-table-column>
        <el-table-column label="项目" width="140">
          <template #default="{ row }">
            <router-link v-if="row.project_id" :to="`/projects/${row.project_id}/overview`" style="font-size: 12px;">
              {{ getProjectName(row.project_id) }}
            </router-link>
          </template>
        </el-table-column>
        <el-table-column prop="task_type" label="类型" width="80">
          <template #default="{ row }">
            <span class="gs-type-tag">{{ typeLabel(row.task_type) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <span class="gs-status-dot" :class="'gs-status-dot--' + row.status"></span>
            {{ statusLabel(row.status) }}
          </template>
        </el-table-column>
        <el-table-column label="风险评分" width="140">
          <template #default="{ row }">
            <div v-if="row.aggregate_risk_score != null" style="display: flex; align-items: center; gap: 8px;">
              <div class="gs-risk-bar" style="flex: 1;">
                <div class="gs-risk-bar-fill" :style="{ width: (row.aggregate_risk_score * 100) + '%', background: riskColor(row.aggregate_risk_score) }"></div>
              </div>
              <span style="font-size: 12px; font-weight: 600;">{{ (row.aggregate_risk_score * 100).toFixed(0) }}%</span>
            </div>
            <span v-else style="color: var(--gs-text-muted);">-</span>
          </template>
        </el-table-column>
        <el-table-column label="模块" width="90" align="center">
          <template #default="{ row }">
            <span v-if="row.progress">{{ row.progress.finished_modules }}/{{ row.progress.total_modules }}</span>
          </template>
        </el-table-column>
        <el-table-column label="创建时间" width="160" prop="created_at" sortable>
          <template #default="{ row }">{{ formatDate(row.created_at, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="180" fixed="right">
          <template #default="{ row }">
            <el-button text size="small" type="primary" @click="$router.push(`/tasks/${row.task_id}`)">详情</el-button>
            <el-button v-if="['failed', 'partial_failed'].includes(row.status)" text size="small" @click="doRetry(row)">重试</el-button>
            <el-button v-if="['pending', 'running'].includes(row.status)" text size="small" type="danger" @click="doCancel(row)">取消</el-button>
            <el-button text size="small" type="danger" @click="doDelete(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>

      <el-pagination
        v-if="filteredTasks.length > pageSize"
        v-model:current-page="page"
        :page-size="pageSize"
        :total="filteredTasks.length"
        layout="total, prev, pager, next"
        style="margin-top: 16px; justify-content: center;"
      />

      <el-empty v-if="!loading && !filteredTasks.length" description="暂无任务" :image-size="60" />
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useRiskColor } from '../composables/useRiskColor.js'
import { useFormatDate } from '../composables/useFormatDate.js'
import { useAppStore } from '../stores/app.js'
import api from '../api.js'

const { riskColor, statusLabel } = useRiskColor()
const { formatDate } = useFormatDate()
const appStore = useAppStore()
const projects = computed(() => appStore.projects)

const loading = ref(false)
const tasks = ref([])
const filterProject = ref(null)
const filterStatus = ref([])
const filterType = ref(null)
const page = ref(1)
const pageSize = 20
const selectedTasks = ref([])
const taskTableRef = ref(null)

const filteredTasks = computed(() => {
  let list = [...tasks.value]
  if (filterProject.value) list = list.filter(t => t.project_id === filterProject.value)
  if (filterStatus.value.length) list = list.filter(t => filterStatus.value.includes(t.status))
  if (filterType.value) list = list.filter(t => t.task_type === filterType.value)
  return list.sort((a, b) => new Date(b.created_at) - new Date(a.created_at))
})

const paginatedTasks = computed(() => {
  const start = (page.value - 1) * pageSize
  return filteredTasks.value.slice(start, start + pageSize)
})

function getProjectName(id) {
  const p = appStore.getProjectById(id)
  return p?.name || `#${id}`
}

function typeLabel(type) {
  const map = { full: '全量', file: '文件', function: '函数', diff: '差异', postmortem: '事后' }
  return map[type] || type
}

function onSelectionChange(rows) {
  selectedTasks.value = rows
}

async function doRetry(task) {
  try { await api.retryTask(task.task_id, {}); ElMessage.success('重试已提交'); await loadTasks() }
  catch (e) { ElMessage.error('重试失败: ' + e.message) }
}

async function doCancel(task) {
  try { await api.cancelTask(task.task_id); ElMessage.success('已取消'); await loadTasks() }
  catch (e) { ElMessage.error('取消失败: ' + e.message) }
}

async function doDelete(task) {
  try {
    const preview = await api.deletePreview([task.task_id])
    const msg = `确定要删除该任务吗？此操作不可恢复。\n\n将同时删除：\n` +
      `- 风险发现：${preview.finding_count} 条\n` +
      `- 测试用例：${preview.testcase_count} 条\n` +
      `- 模块结果：${preview.module_result_count} 条\n` +
      `- 导出记录：${preview.export_count} 条`
    await ElMessageBox.confirm(msg, '删除确认', {
      confirmButtonText: '确认删除',
      cancelButtonText: '取消',
      type: 'warning',
      dangerouslyUseHTMLString: false,
    })
    await api.deleteTask(task.task_id)
    ElMessage.success('任务已删除')
    await loadTasks()
  } catch (e) {
    if (e !== 'cancel' && e?.toString() !== 'cancel') {
      ElMessage.error('删除失败: ' + (e.message || e))
    }
  }
}

async function doBatchDelete() {
  const ids = selectedTasks.value.map(t => t.task_id)
  if (!ids.length) return
  try {
    const preview = await api.deletePreview(ids)
    const msg = `确定要删除选中的 ${ids.length} 个任务吗？此操作不可恢复。\n\n将同时删除：\n` +
      `- 风险发现：${preview.finding_count} 条\n` +
      `- 测试用例：${preview.testcase_count} 条\n` +
      `- 模块结果：${preview.module_result_count} 条\n` +
      `- 导出记录：${preview.export_count} 条`
    await ElMessageBox.confirm(msg, '批量删除确认', {
      confirmButtonText: '确认删除',
      cancelButtonText: '取消',
      type: 'warning',
    })
    await api.batchDeleteTasks(ids)
    ElMessage.success(`已删除 ${ids.length} 个任务`)
    selectedTasks.value = []
    await loadTasks()
  } catch (e) {
    if (e !== 'cancel' && e?.toString() !== 'cancel') {
      ElMessage.error('批量删除失败: ' + (e.message || e))
    }
  }
}

async function loadTasks() {
  loading.value = true
  try {
    const data = await api.getAllTasks()
    tasks.value = data?.tasks || data?.items || data || []
  } catch {
    tasks.value = []
  } finally {
    loading.value = false
  }
}

onMounted(loadTasks)
</script>

<style scoped>
.gs-toolbar { display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: var(--gs-space-md); }
.gs-toolbar-left, .gs-toolbar-right { display: flex; align-items: center; gap: var(--gs-space-sm); }
.gs-result-count { font-size: var(--gs-font-sm); color: var(--gs-text-muted); }
.gs-type-tag { font-size: var(--gs-font-xs); background: #F0F0F0; padding: 2px 6px; border-radius: 3px; }
.gs-risk-bar { height: 6px; background: var(--gs-border-light); border-radius: 3px; overflow: hidden; }
.gs-risk-bar-fill { height: 100%; border-radius: 3px; }
</style>
