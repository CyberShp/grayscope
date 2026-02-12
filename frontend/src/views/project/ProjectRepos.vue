<template>
  <div class="gs-page">
    <div class="gs-section" style="display:flex;justify-content:space-between;align-items:center">
      <div>
        <h2 style="margin:0;font-size:16px;font-weight:600;">代码仓库</h2>
        <p style="margin:4px 0 0;font-size:13px;color:var(--gs-text-muted);">管理本项目关联的代码仓库</p>
      </div>
      <el-button type="primary" @click="showAdd = true">
        <el-icon><Plus /></el-icon> 添加仓库
      </el-button>
    </div>

    <!-- 仓库列表 -->
    <div class="gs-card">
      <el-table :data="repos" class="gs-table" v-loading="loading">
        <el-table-column label="仓库名称" min-width="180">
          <template #default="{ row }">
            <div style="font-weight:600;">{{ row.name }}</div>
          </template>
        </el-table-column>
        <el-table-column label="Git URL" min-width="280">
          <template #default="{ row }">
            <span style="font-size:13px;color:var(--gs-text-secondary);word-break:break-all;">{{ row.git_url }}</span>
          </template>
        </el-table-column>
        <el-table-column label="默认分支" width="120" align="center">
          <template #default="{ row }">
            <el-tag size="small" type="info">{{ row.default_branch }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="同步状态" width="120" align="center">
          <template #default="{ row }">
            <el-tag
              size="small"
              :type="syncTagType(row.last_sync_status)"
            >{{ syncLabel(row.last_sync_status) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="最近同步" width="160">
          <template #default="{ row }">
            {{ row.last_sync_at ? formatDate(row.last_sync_at) : '-' }}
          </template>
        </el-table-column>
        <el-table-column label="操作" width="200" align="center" fixed="right">
          <template #default="{ row }">
            <el-button
              size="small"
              type="primary"
              :icon="Refresh"
              :loading="syncingId === row.repo_id"
              :disabled="row.last_sync_status === 'running'"
              @click="syncRepo(row)"
            >同步</el-button>
            <el-button
              size="small"
              type="danger"
              :icon="Delete"
              @click="confirmDelete(row)"
            >删除</el-button>
          </template>
        </el-table-column>
      </el-table>
      <el-empty v-if="!loading && !repos.length" description="暂无仓库，点击上方按钮添加" />
    </div>

    <!-- 添加仓库对话框 -->
    <el-dialog v-model="showAdd" title="添加代码仓库" width="520px" :close-on-click-modal="false" @closed="resetForm">
      <el-form :model="newRepo" label-width="100px">
        <el-form-item label="仓库名称" required>
          <el-input v-model="newRepo.name" placeholder="例如: my-project" maxlength="128" />
        </el-form-item>
        <el-form-item label="Git URL" required>
          <el-input v-model="newRepo.git_url" placeholder="https://github.com/org/repo.git 或 git@..." />
        </el-form-item>
        <el-form-item label="默认分支">
          <el-input v-model="newRepo.default_branch" placeholder="main" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showAdd = false">取消</el-button>
        <el-button type="primary" @click="addRepo" :loading="adding" :disabled="!newRepo.name.trim() || !newRepo.git_url.trim()">添加</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Refresh, Delete } from '@element-plus/icons-vue'
import api from '../../api.js'

const props = defineProps({
  projectId: [String, Number],
  project: Object,
})

const loading = ref(false)
const repos = ref([])
const showAdd = ref(false)
const adding = ref(false)
const syncingId = ref(null)
const newRepo = ref({ name: '', git_url: '', default_branch: 'main' })

function syncTagType(status) {
  if (status === 'success') return 'success'
  if (status === 'running') return 'warning'
  if (status === 'failed') return 'danger'
  return 'info'
}

function syncLabel(status) {
  const map = { never: '未同步', running: '同步中', success: '已同步', failed: '同步失败' }
  return map[status] || status || '未同步'
}

function formatDate(d) {
  if (!d) return '-'
  return new Date(d).toLocaleString('zh-CN', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
}

async function loadRepos() {
  loading.value = true
  try {
    const data = await api.listRepos(props.projectId)
    repos.value = Array.isArray(data) ? data : (data.repos || data.items || [])
  } catch {
    repos.value = []
  } finally {
    loading.value = false
  }
}

async function addRepo() {
  adding.value = true
  try {
    await api.createRepo(props.projectId, {
      name: newRepo.value.name.trim(),
      git_url: newRepo.value.git_url.trim(),
      default_branch: newRepo.value.default_branch.trim() || 'main',
    })
    ElMessage.success('仓库添加成功')
    showAdd.value = false
    await loadRepos()
  } catch (e) {
    ElMessage.error('添加失败: ' + e.message)
  } finally {
    adding.value = false
  }
}

async function syncRepo(row) {
  syncingId.value = row.repo_id
  try {
    await api.syncRepo(row.repo_id, { branch: row.default_branch })
    ElMessage.success(`仓库 "${row.name}" 同步已启动`)
    // Poll for status updates
    setTimeout(async () => {
      await loadRepos()
    }, 2000)
  } catch (e) {
    ElMessage.error('同步失败: ' + e.message)
  } finally {
    syncingId.value = null
  }
}

async function confirmDelete(row) {
  try {
    await ElMessageBox.confirm(
      `确定要删除仓库 "${row.name}" 吗？此操作不可撤销。`,
      '删除仓库',
      { confirmButtonText: '删除', cancelButtonText: '取消', type: 'warning' }
    )
    // TODO: call delete API when backend supports it
    ElMessage.info('删除功能尚未实现')
  } catch {
    // user cancelled
  }
}

function resetForm() {
  newRepo.value = { name: '', git_url: '', default_branch: 'main' }
}

onMounted(loadRepos)
</script>
