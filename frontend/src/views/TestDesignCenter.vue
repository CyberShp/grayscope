<template>
  <div class="gs-page gs-test-design-global">
    <!-- 页头 -->
    <div class="gs-page-header">
      <div>
        <h1 class="gs-page-title">测试设计中心</h1>
        <p class="gs-page-desc">跨项目查看所有灰盒分析生成的测试用例建议——从风险发现到测试设计的桥梁。</p>
      </div>
      <el-button v-if="filters.project_id" type="primary" size="small" :loading="generating" @click="generateAndPersist">
        <el-icon><Plus /></el-icon> 生成并持久化用例
      </el-button>
      <el-button size="small" @click="downloadTemplate">下载灰盒用例模板</el-button>
    </div>

    <!-- 筛选栏 -->
    <div class="gs-filter-bar">
      <el-radio-group v-model="viewMode" size="default" @change="loadData">
        <el-radio-button value="suggested">建议用例</el-radio-button>
        <el-radio-button value="persisted">已持久化用例</el-radio-button>
      </el-radio-group>
      <el-select v-model="filters.project_id" placeholder="选择项目" clearable size="default" @change="loadData">
        <el-option v-for="p in projects" :key="p.project_id" :label="p.name" :value="p.project_id" />
      </el-select>
      <el-select v-model="filters.priority" placeholder="优先级" clearable size="default" @change="loadData">
        <el-option label="P0 紧急" value="P0" />
        <el-option label="P1 高优" value="P1" />
        <el-option label="P2 中" value="P2" />
        <el-option label="P3 低" value="P3" />
      </el-select>
      <el-select v-model="filters.module_id" placeholder="分析模块" clearable size="default" @change="loadData">
        <el-option v-for="m in moduleOptions" :key="m.id" :label="m.name" :value="m.id" />
      </el-select>
      <el-button @click="resetFilters" :icon="RefreshRight">重置</el-button>
      <div style="flex:1"></div>
      <span class="gs-result-count">共 {{ total }} 条用例</span>
    </div>

    <!-- 用例列表 -->
    <div class="gs-testcase-list" v-loading="loading">
      <div v-if="!loading && testCases.length === 0" class="gs-empty">
        <el-empty
          :description="viewMode === 'persisted' && !filters.project_id ? '请选择项目以查看已持久化用例' : '暂无测试用例，请先运行分析任务'"
        />
      </div>

      <div
        v-for="tc in testCases"
        :key="tc.id ?? tc.test_case_id"
        class="gs-testcase-card"
        @click="openDetail(tc)"
      >
        <div class="gs-tc-header">
          <div class="gs-tc-header-left">
            <span class="gs-tc-priority" :class="priorityClass(tc.priority)">
              {{ tc.priority.split('-')[0] }}
            </span>
            <span class="gs-tc-id">{{ tc.case_id || tc.test_case_id }}</span>
            <span class="gs-tc-module-tag">{{ tc.module_display_name }}</span>
            <span v-if="tc.project_id" class="gs-tc-project-tag">
              {{ getProjectName(tc.project_id) }}
            </span>
          </div>
          <div class="gs-tc-header-right">
            <span class="gs-tc-risk">
              <span class="gs-risk-dot" :style="{ background: riskColor(tc.risk_score) }"></span>
              {{ (tc.risk_score * 100).toFixed(0) }}%
            </span>
            <el-icon class="gs-tc-open-icon"><ArrowRight /></el-icon>
          </div>
        </div>

        <div class="gs-tc-title">{{ tc.title }}</div>
        <div class="gs-tc-objective">
          <el-icon><Aim /></el-icon>
          <span>{{ tc.objective }}</span>
        </div>
        <div class="gs-tc-location">
          <code>{{ tc.target_file }}</code>
          <span v-if="tc.target_function">→ <code>{{ tc.target_function }}()</code></span>
          <span v-if="tc.line_start" class="gs-tc-lines">L{{ tc.line_start }}–{{ tc.line_end }}</span>
        </div>
      </div>
    </div>

    <!-- 分页 -->
    <div class="gs-pagination" v-if="total > pageSize">
      <el-pagination
        v-model:current-page="page"
        :page-size="pageSize"
        :total="total"
        layout="prev, pager, next, total"
        @current-change="loadData"
      />
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted, computed, toRaw } from 'vue'
import { useRouter } from 'vue-router'
import { ArrowRight, Aim, RefreshRight, Plus } from '@element-plus/icons-vue'
import api from '../api.js'
import { useAppStore } from '../stores/app.js'
import { ElMessage } from 'element-plus'
import { useModuleNames } from '../composables/useModuleNames.js'
import { useRiskColor } from '../composables/useRiskColor.js'

const appStore = useAppStore()
const { moduleList } = useModuleNames()
const { riskColor } = useRiskColor()

async function downloadTemplate() {
  try {
    const data = await api.getTestCaseTemplate()
    const md = data?.markdown || ''
    const blob = new Blob([md], { type: 'text/markdown' })
    const a = document.createElement('a')
    a.href = URL.createObjectURL(blob)
    a.download = 'grayscope_灰盒测试用例模板.md'
    a.click()
    URL.revokeObjectURL(a.href)
  } catch (e) {
    console.error(e)
  }
}

const router = useRouter()

const loading = ref(false)
const generating = ref(false)
const testCases = ref([])
const total = ref(0)
const page = ref(1)
const pageSize = 30
const filters = reactive({ project_id: '', priority: '', module_id: '' })
const viewMode = ref('suggested')

const projects = computed(() => appStore.projects || [])
const moduleOptions = moduleList.map(m => ({ id: m.id, name: m.name }))

function getProjectName(pid) {
  const p = appStore.getProjectById(pid)
  return p?.name || `项目#${pid}`
}

function priorityClass(p) {
  return `priority-${p.split('-')[0].toLowerCase()}`
}

function openDetail(tc) {
  const plainTc = JSON.parse(JSON.stringify(toRaw(tc)))
  const id = tc.id != null ? tc.id : tc.test_case_id
  router.push({
    name: 'TestCaseDetail',
    params: { testCaseId: String(id) },
    state: { tc: plainTc },
  })
}

function resetFilters() {
  filters.project_id = ''
  filters.priority = ''
  filters.module_id = ''
  page.value = 1
  loadData()
}

async function loadData() {
  loading.value = true
  try {
    if (viewMode.value === 'persisted') {
      if (!filters.project_id) {
        testCases.value = []
        total.value = 0
        loading.value = false
        return
      }
      const params = { page: page.value, page_size: pageSize, persisted: true }
      if (filters.priority) params.priority = filters.priority
      if (filters.module_id) params.module_id = filters.module_id
      const data = await api.getProjectTestCases(filters.project_id, params)
      testCases.value = data.test_cases || []
      total.value = data.total || 0
      return
    }
    const params = { page: page.value, page_size: pageSize }
    if (filters.project_id) params.project_id = filters.project_id
    if (filters.priority) params.priority = filters.priority
    if (filters.module_id) params.module_id = filters.module_id

    const data = await api.getAllTestCases(params)
    testCases.value = data.test_cases || []
    total.value = data.total || 0
  } catch (e) {
    console.error('加载测试用例失败:', e)
  } finally {
    loading.value = false
  }
}

async function generateAndPersist() {
  if (!filters.project_id) {
    ElMessage.warning('请先选择项目')
    return
  }
  generating.value = true
  try {
    const res = await api.generateProjectTestCases(Number(filters.project_id))
    const n = res?.generated ?? 0
    ElMessage.success(`已持久化 ${n} 条用例`)
    viewMode.value = 'persisted'
    page.value = 1
    await loadData()
  } catch (e) {
    ElMessage.error('生成并持久化失败: ' + (e?.message || e))
  } finally {
    generating.value = false
  }
}

onMounted(() => {
  appStore.fetchProjects()
  loadData()
})
</script>

<style scoped>
/* 复用 ProjectTestDesign 的样式 */
.gs-filter-bar {
  display: flex; align-items: center; gap: 10px; margin-bottom: 16px; flex-wrap: wrap;
}
.gs-result-count { font-size: 13px; color: var(--gs-text-muted); white-space: nowrap; }

.gs-testcase-list { display: flex; flex-direction: column; gap: 8px; min-height: 200px; }
.gs-testcase-card {
  background: var(--gs-surface); border: 1px solid var(--gs-border);
  border-radius: var(--gs-radius-md); padding: 16px 20px;
  cursor: pointer; transition: all var(--gs-transition);
}
.gs-testcase-card:hover { border-color: var(--gs-primary); box-shadow: var(--gs-shadow-sm); transform: translateY(-1px); }

.gs-tc-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
.gs-tc-header-left { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.gs-tc-header-right { display: flex; align-items: center; gap: 10px; }

.gs-tc-priority {
  display: inline-flex; align-items: center; justify-content: center;
  min-width: 28px; height: 22px; padding: 0 6px;
  border-radius: 4px; font-size: 11px; font-weight: 700; color: #fff;
}
.gs-tc-priority.priority-p0 { background: var(--gs-risk-critical); }
.gs-tc-priority.priority-p1 { background: var(--gs-risk-high); }
.gs-tc-priority.priority-p2 { background: var(--gs-risk-medium); }
.gs-tc-priority.priority-p3 { background: var(--gs-risk-low); }

.gs-tc-id { font-size: 12px; font-family: var(--gs-font-mono); color: var(--gs-text-muted); }
.gs-tc-module-tag {
  font-size: 11px; padding: 2px 8px;
  background: rgba(75, 159, 213, 0.1); color: var(--gs-primary); border-radius: 10px;
}
.gs-tc-project-tag {
  font-size: 11px; padding: 2px 8px;
  background: rgba(0, 170, 0, 0.08); color: var(--gs-success); border-radius: 10px;
}

.gs-tc-risk { display: flex; align-items: center; gap: 4px; font-size: 12px; color: var(--gs-text-secondary); font-family: var(--gs-font-mono); }
.gs-risk-dot { width: 8px; height: 8px; border-radius: 50%; }
.gs-tc-open-icon { color: var(--gs-text-muted); transition: transform 0.2s; }
.gs-testcase-card:hover .gs-tc-open-icon { color: var(--gs-primary); transform: translateX(2px); }

.gs-tc-title { font-size: 15px; font-weight: 600; color: var(--gs-text-primary); margin-bottom: 6px; line-height: 1.4; }
.gs-tc-objective { display: flex; align-items: flex-start; gap: 6px; font-size: 13px; color: var(--gs-text-secondary); line-height: 1.5; margin-bottom: 6px; }
.gs-tc-objective .el-icon { margin-top: 2px; color: var(--gs-primary); flex-shrink: 0; }

.gs-tc-location { font-size: 12px; color: var(--gs-text-muted); }
.gs-tc-location code { background: rgba(75, 159, 213, 0.08); padding: 1px 5px; border-radius: 3px; font-size: 11px; }
.gs-tc-lines { margin-left: 6px; }

.gs-pagination { display: flex; justify-content: center; margin-top: 20px; padding-bottom: 20px; }
.gs-empty { padding: 60px 0; text-align: center; }
</style>
