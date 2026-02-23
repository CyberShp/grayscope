<template>
  <div class="gs-page">
    <div class="gs-page-header">
      <h2 class="gs-page-title" style="font-size: 16px;">分析任务历史</h2>
    </div>

    <!-- 筛选 -->
    <div class="gs-toolbar gs-section">
      <div class="gs-toolbar-left">
        <el-select v-model="filterStatus" placeholder="状态" clearable size="small" style="width: 120px;">
          <el-option label="成功" value="success" />
          <el-option label="失败" value="failed" />
          <el-option label="运行中" value="running" />
          <el-option label="等待中" value="pending" />
          <el-option label="部分失败" value="partial_failed" />
        </el-select>
        <el-select v-model="filterType" placeholder="类型" clearable size="small" style="width: 120px;">
          <el-option label="全量" value="full" />
          <el-option label="文件" value="file" />
          <el-option label="函数" value="function" />
          <el-option label="差异" value="diff" />
          <el-option label="事后分析" value="postmortem" />
        </el-select>
        <el-button
          v-if="selectedTasks.length"
          type="danger"
          size="small"
          @click="doBatchDelete"
        >
          删除选中 ({{ selectedTasks.length }})
        </el-button>
      </div>
      <span class="gs-result-count">{{ filteredTasks.length }} 个任务</span>
    </div>

    <!-- 任务列表 -->
    <div class="gs-card">
      <el-table
        ref="taskTableRef"
        :data="filteredTasks"
        size="small"
        class="gs-table"
        :default-sort="{ prop: 'created_at', order: 'descending' }"
        @selection-change="onSelectionChange"
      >
        <el-table-column type="selection" width="40" />
        <el-table-column label="任务ID" width="180">
          <template #default="{ row }">
            <router-link :to="`/tasks/${row.task_id}`" style="font-weight: 500; font-family: var(--gs-font-mono); font-size: 12px;">
              {{ (row.task_id || '').slice(0, 20) }}
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
        <el-table-column label="模块进度" width="120">
          <template #default="{ row }">
            <span v-if="row.progress">{{ row.progress.finished_modules }}/{{ row.progress.total_modules }}</span>
            <span v-else>-</span>
          </template>
        </el-table-column>
        <el-table-column label="创建时间" width="160" prop="created_at" sortable>
          <template #default="{ row }">{{ formatDate(row.created_at, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="160">
          <template #default="{ row }">
            <el-button text size="small" type="primary" @click="$router.push(`/tasks/${row.task_id}`)">详情</el-button>
            <el-button v-if="row.status === 'failed' || row.status === 'partial_failed'" text size="small" @click="retryTask(row)">重试</el-button>
            <el-button text size="small" type="danger" @click="doDelete(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
      <el-empty v-if="!filteredTasks.length" description="暂无任务" :image-size="60" />
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useRiskColor } from '../../composables/useRiskColor.js'
import { useFormatDate } from '../../composables/useFormatDate.js'
import api from '../../api.js'

const props = defineProps({
  projectId: [String, Number],
})

const { riskColor, statusLabel } = useRiskColor()
const { formatDate } = useFormatDate()

const tasks = ref([])
const filterStatus = ref(null)
const filterType = ref(null)
const selectedTasks = ref([])
const taskTableRef = ref(null)

const filteredTasks = computed(() => {
  let list = [...tasks.value]
  if (filterStatus.value) list = list.filter(t => t.status === filterStatus.value)
  if (filterType.value) list = list.filter(t => t.task_type === filterType.value)
  return list.sort((a, b) => new Date(b.created_at) - new Date(a.created_at))
})

function typeLabel(type) {
  const map = { full: '全量', file: '文件', function: '函数', diff: '差异', postmortem: '事后' }
  return map[type] || type
}

function onSelectionChange(rows) {
  selectedTasks.value = rows
}

async function retryTask(task) {
  try {
    await api.retryTask(task.task_id, {})
    ElMessage.success('重试已提交')
    await loadTasks()
  } catch (e) {
    ElMessage.error('重试失败: ' + e.message)
  }
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
  try {
    const data = await api.getProjectTasks(props.projectId)
    tasks.value = data?.tasks || data?.items || data || []
  } catch {
    tasks.value = []
  }
}

onMounted(loadTasks)
watch(() => props.projectId, loadTasks)
</script>

<style scoped>
.gs-toolbar { display: flex; justify-content: space-between; align-items: center; }
.gs-toolbar-left { display: flex; gap: var(--gs-space-sm); }
.gs-result-count { font-size: var(--gs-font-sm); color: var(--gs-text-muted); }
.gs-type-tag {
  font-size: var(--gs-font-xs);
  background: #F0F0F0;
  padding: 2px 6px;
  border-radius: 3px;
}
.gs-risk-bar { height: 6px; background: var(--gs-border-light); border-radius: 3px; overflow: hidden; }
.gs-risk-bar-fill { height: 100%; border-radius: 3px; }
</style>
