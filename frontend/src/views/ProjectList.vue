<template>
  <div class="gs-page">
    <div class="gs-page-header">
      <div style="display: flex; justify-content: space-between; align-items: flex-start;">
        <div>
          <h1 class="gs-page-title">项目</h1>
          <p class="gs-page-desc">管理和监控您的代码分析项目</p>
        </div>
        <el-button type="primary" @click="showCreate = true">
          <el-icon><Plus /></el-icon> 新建项目
        </el-button>
      </div>
    </div>

    <!-- 搜索 & 排序 & 视图切换 -->
    <div class="gs-toolbar gs-section">
      <div class="gs-toolbar-left">
        <el-input
          v-model="search"
          placeholder="搜索项目名称..."
          :prefix-icon="SearchIcon"
          clearable
          style="width: 280px;"
        />
        <el-select v-model="sortBy" style="width: 160px;" placeholder="排序">
          <el-option label="名称" value="name" />
          <el-option label="最近更新" value="updated" />
          <el-option label="创建时间" value="created" />
        </el-select>
      </div>
      <div class="gs-toolbar-right">
        <el-radio-group v-model="viewMode" size="small">
          <el-radio-button value="card">
            <el-icon><Grid /></el-icon>
          </el-radio-button>
          <el-radio-button value="table">
            <el-icon><List /></el-icon>
          </el-radio-button>
        </el-radio-group>
        <span class="gs-result-count">{{ filteredProjects.length }} 个项目</span>
      </div>
    </div>

    <!-- 卡片视图 -->
    <div v-if="viewMode === 'card'" class="gs-project-grid">
      <div
        v-for="p in filteredProjects"
        :key="p.id ?? p.project_id"
        class="gs-project-card"
        @click="goProject(p)"
      >
        <div class="gs-project-card-top">
          <div class="gs-project-card-name">{{ p.name }}</div>
          <div class="gs-project-card-gate" :class="gateClass(p)">
            {{ gateLabel(p) }}
          </div>
        </div>
        <div v-if="p.description" class="gs-project-card-desc">{{ p.description }}</div>

        <div class="gs-project-card-metrics">
          <div class="gs-metric">
            <span class="gs-metric-value">{{ p.summary?.task_count ?? '-' }}</span>
            <span class="gs-metric-label">任务</span>
          </div>
          <div class="gs-metric">
            <span class="gs-metric-value">{{ p.summary?.finding_count ?? '-' }}</span>
            <span class="gs-metric-label">发现</span>
          </div>
          <div class="gs-metric">
            <span class="gs-metric-value" :style="{ color: riskColor(p.summary?.avg_risk_score ?? 0) }">
              {{ p.summary?.avg_risk_score != null ? (p.summary.avg_risk_score * 100).toFixed(0) + '%' : '-' }}
            </span>
            <span class="gs-metric-label">风险评分</span>
          </div>
        </div>

        <div class="gs-project-card-footer">
          <span class="gs-project-card-time">
            {{ p.summary?.last_analysis_at ? formatDate(p.summary.last_analysis_at) : (p.created_at ? formatDate(p.created_at) : '暂无分析') }}
          </span>
        </div>
      </div>
    </div>

    <!-- 表格视图 -->
    <div v-if="viewMode === 'table'" class="gs-card">
      <el-table :data="filteredProjects" class="gs-table" @row-click="goProject" style="cursor: pointer;">
        <el-table-column label="项目名称" min-width="200">
          <template #default="{ row }">
            <div style="font-weight: 600;">{{ row.name }}</div>
            <div v-if="row.description" style="font-size: 12px; color: var(--gs-text-muted); margin-top: 2px;">{{ row.description }}</div>
          </template>
        </el-table-column>
        <el-table-column label="质量门禁" width="100" align="center">
          <template #default="{ row }">
            <span class="gs-gate-dot" :class="gateClass(row)">{{ gateLabel(row) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="任务数" width="80" align="center">
          <template #default="{ row }">{{ row.summary?.task_count ?? '-' }}</template>
        </el-table-column>
        <el-table-column label="发现数" width="80" align="center">
          <template #default="{ row }">{{ row.summary?.finding_count ?? '-' }}</template>
        </el-table-column>
        <el-table-column label="风险评分" width="100" align="center">
          <template #default="{ row }">
            <span v-if="row.summary?.avg_risk_score != null" :style="{ color: riskColor(row.summary.avg_risk_score), fontWeight: 600 }">
              {{ (row.summary.avg_risk_score * 100).toFixed(0) }}%
            </span>
            <span v-else style="color: var(--gs-text-muted);">-</span>
          </template>
        </el-table-column>
        <el-table-column label="最近分析" width="160">
          <template #default="{ row }">
            {{ row.summary?.last_analysis_at ? formatDate(row.summary.last_analysis_at) : formatDate(row.created_at) }}
          </template>
        </el-table-column>
      </el-table>
    </div>

    <!-- 空状态 -->
    <el-empty v-if="!loading && !filteredProjects.length" description="暂无项目，点击上方按钮创建">
      <el-button type="primary" @click="showCreate = true">新建项目</el-button>
    </el-empty>

    <!-- 新建项目对话框 -->
    <el-dialog v-model="showCreate" title="新建项目" width="480px" :close-on-click-modal="false">
      <el-form :model="newProject" label-width="80px">
        <el-form-item label="名称" required>
          <el-input v-model="newProject.name" placeholder="请输入项目名称" maxlength="64" show-word-limit />
        </el-form-item>
        <el-form-item label="描述">
          <el-input v-model="newProject.description" type="textarea" :rows="3" placeholder="项目描述（可选）" maxlength="512" show-word-limit />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showCreate = false">取消</el-button>
        <el-button type="primary" @click="createProject" :loading="creating" :disabled="!newProject.name.trim()">创建</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { Search as SearchIcon } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { useAppStore } from '../stores/app.js'
import { useRiskColor } from '../composables/useRiskColor.js'
import api from '../api.js'

const router = useRouter()
const appStore = useAppStore()
const { riskColor } = useRiskColor()

const loading = ref(false)
const search = ref('')
const sortBy = ref('updated')
const viewMode = ref('card')
const showCreate = ref(false)
const creating = ref(false)
const newProject = ref({ name: '', description: '' })

const projects = computed(() => appStore.projects)

const filteredProjects = computed(() => {
  let list = [...projects.value]
  if (search.value) {
    const q = search.value.toLowerCase()
    list = list.filter(p => p.name.toLowerCase().includes(q) || (p.description || '').toLowerCase().includes(q))
  }
  if (sortBy.value === 'name') list.sort((a, b) => a.name.localeCompare(b.name))
  else if (sortBy.value === 'created') list.sort((a, b) => new Date(b.created_at) - new Date(a.created_at))
  else list.sort((a, b) => new Date(b.updated_at || b.created_at) - new Date(a.updated_at || a.created_at))
  return list
})

function goProject(p) {
  const id = p.id ?? p.project_id
  router.push(`/projects/${id}/overview`)
}

function gateClass(p) {
  if (!p.summary?.quality_gate_status) return 'gs-gate--none'
  return p.summary.quality_gate_status === 'pass' ? 'gs-gate--pass' : 'gs-gate--fail'
}

function gateLabel(p) {
  if (!p.summary?.quality_gate_status) return '-'
  return p.summary.quality_gate_status === 'pass' ? '通过' : '未通过'
}

function formatDate(d) {
  if (!d) return '-'
  return new Date(d).toLocaleString('zh-CN', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
}

async function createProject() {
  creating.value = true
  try {
    await api.createProject({ name: newProject.value.name.trim(), description: newProject.value.description.trim() })
    showCreate.value = false
    newProject.value = { name: '', description: '' }
    await appStore.fetchProjects()
    ElMessage.success('项目创建成功')
  } catch (e) {
    ElMessage.error('创建失败: ' + e.message)
  } finally {
    creating.value = false
  }
}

onMounted(async () => {
  loading.value = true
  await appStore.fetchProjects()
  loading.value = false
})
</script>

<style scoped>
/* ── 工具栏 ─────────────────────────── */
.gs-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-wrap: wrap;
  gap: var(--gs-space-md);
}
.gs-toolbar-left,
.gs-toolbar-right {
  display: flex;
  align-items: center;
  gap: var(--gs-space-sm);
}
.gs-result-count {
  font-size: var(--gs-font-sm);
  color: var(--gs-text-muted);
  margin-left: var(--gs-space-sm);
}

/* ── 项目卡片网格 ─────────────────────── */
.gs-project-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(340px, 1fr));
  gap: var(--gs-space-md);
}

.gs-project-card {
  background: var(--gs-surface);
  border: 1px solid var(--gs-border);
  border-radius: var(--gs-radius-md);
  padding: var(--gs-space-lg);
  cursor: pointer;
  transition: all var(--gs-transition);
}
.gs-project-card:hover {
  border-color: var(--gs-primary);
  box-shadow: var(--gs-shadow-md);
}

.gs-project-card-top {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: var(--gs-space-sm);
}

.gs-project-card-name {
  font-size: var(--gs-font-lg);
  font-weight: 600;
  color: var(--gs-text-primary);
}

.gs-project-card-gate {
  font-size: var(--gs-font-xs);
  font-weight: 600;
  padding: 2px 8px;
  border-radius: 3px;
}
.gs-gate--pass { background: var(--gs-gate-pass-bg); color: #166534; }
.gs-gate--fail { background: var(--gs-gate-fail-bg); color: #991B1B; }
.gs-gate--none { background: #F5F5F5; color: var(--gs-text-muted); }

.gs-gate-dot {
  font-size: var(--gs-font-xs);
  font-weight: 600;
  padding: 2px 8px;
  border-radius: 3px;
}

.gs-project-card-desc {
  font-size: var(--gs-font-sm);
  color: var(--gs-text-muted);
  margin-bottom: var(--gs-space-md);
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.gs-project-card-metrics {
  display: flex;
  gap: var(--gs-space-xl);
  padding: var(--gs-space-md) 0;
  border-top: 1px solid var(--gs-border-light);
}

.gs-metric {
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.gs-metric-value {
  font-size: var(--gs-font-lg);
  font-weight: 700;
  color: var(--gs-text-primary);
}
.gs-metric-label {
  font-size: var(--gs-font-xs);
  color: var(--gs-text-muted);
  text-transform: uppercase;
  letter-spacing: 0.3px;
}

.gs-project-card-footer {
  margin-top: var(--gs-space-sm);
}
.gs-project-card-time {
  font-size: var(--gs-font-xs);
  color: var(--gs-text-muted);
}
</style>
