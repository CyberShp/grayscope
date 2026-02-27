<template>
  <div class="gs-page">
    <div class="gs-section" style="display:flex;justify-content:space-between;align-items:center">
      <div>
        <h2 style="margin:0;font-size:16px;font-weight:600;">代码仓库</h2>
        <p style="margin:4px 0 0;font-size:13px;color:var(--gs-text-muted);">管理本项目关联的代码仓库</p>
      </div>
      <div style="display:flex;gap:8px;">
        <el-button type="primary" @click="showAdd = true">
          <el-icon><Plus /></el-icon> 添加仓库
        </el-button>
        <el-button @click="showUpload = true">
          <el-icon><Upload /></el-icon> 上传代码压缩包
        </el-button>
      </div>
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
            {{ row.last_sync_at ? formatDateShort(row.last_sync_at) : '-' }}
          </template>
        </el-table-column>
        <el-table-column label="鉴权" width="90" align="center">
          <template #default="{ row }">
            <el-tag v-if="row.auth_configured" size="small" type="success">{{ row.auth_type || '已配置' }}</el-tag>
            <span v-else class="gs-text-muted">-</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="260" align="center" fixed="right">
          <template #default="{ row }">
            <el-button
              size="small"
              :icon="EditPen"
              @click="openEdit(row)"
            >编辑</el-button>
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
    <el-dialog v-model="showAdd" title="添加代码仓库" width="560px" :close-on-click-modal="false" @closed="resetForm">
      <el-form :model="newRepo" label-width="120px">
        <el-form-item label="仓库名称" required>
          <el-input v-model="newRepo.name" placeholder="例如: my-project" maxlength="128" />
        </el-form-item>
        <el-form-item label="Git URL" required>
          <el-input v-model="newRepo.git_url" placeholder="https://github.com/org/repo.git 或 git@..." />
        </el-form-item>
        <el-form-item label="默认分支">
          <el-input v-model="newRepo.default_branch" placeholder="main" />
        </el-form-item>
        <el-form-item label="鉴权方式">
          <el-select v-model="newRepo.auth_type" placeholder="无（公开仓）" clearable style="width:100%">
            <el-option label="无（公开仓）" value="" />
            <el-option label="HTTPS Token" value="https_token" />
            <el-option label="SSH 私钥" value="ssh_key" />
          </el-select>
        </el-form-item>
        <el-form-item v-if="newRepo.auth_type === 'https_token'" label="Token 环境变量名">
          <el-input v-model="newRepo.auth_secret_ref" placeholder="例如: GIT_TOKEN_REPO_1" maxlength="256" />
          <div class="gs-form-hint">在服务器上设置该环境变量为 Git Token，切勿填写 token 本身</div>
        </el-form-item>
        <el-form-item v-if="newRepo.auth_type === 'ssh_key'" label="SSH 私钥路径">
          <el-input v-model="newRepo.auth_secret_ref" placeholder="例如: ~/.ssh/id_rsa 或 /root/.ssh/id_rsa" maxlength="256" />
          <div class="gs-form-hint">直接填写私钥文件路径（支持 ~ 展开），或填写环境变量名</div>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showAdd = false">取消</el-button>
        <el-button type="primary" @click="addRepo" :loading="adding" :disabled="!newRepo.name.trim() || !newRepo.git_url.trim()">添加</el-button>
      </template>
    </el-dialog>

    <!-- 上传代码压缩包对话框 -->
    <el-dialog v-model="showUpload" title="上传代码压缩包" width="480px" :close-on-click-modal="false" @closed="resetUploadForm">
      <el-form :model="uploadForm" label-width="100px">
        <el-form-item label="仓库名称" required>
          <el-input v-model="uploadForm.name" placeholder="例如: my-project" maxlength="128" />
        </el-form-item>
        <el-form-item label="压缩包" required>
          <el-upload
            ref="uploadRef"
            :auto-upload="false"
            :limit="1"
            accept=".zip,.tar,.tar.gz,.tgz"
            :on-change="onUploadFileChange"
            :on-remove="onUploadFileRemove"
          >
            <el-button type="primary" plain>选择文件</el-button>
            <template #tip>
              <div class="gs-form-hint">支持 .zip、.tar、.tar.gz，将解压为仓库根目录</div>
            </template>
          </el-upload>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showUpload = false">取消</el-button>
        <el-button type="primary" @click="submitUpload" :loading="uploading" :disabled="!uploadForm.name.trim() || !uploadFile">上传</el-button>
      </template>
    </el-dialog>

    <!-- 编辑仓库（鉴权）对话框 -->
    <el-dialog v-model="showEdit" title="编辑仓库" width="560px" :close-on-click-modal="false" @closed="resetEditForm">
      <el-form :model="editRepo" label-width="120px">
        <el-form-item label="Git URL">
          <el-input v-model="editRepo.git_url" placeholder="https://..." />
        </el-form-item>
        <el-form-item label="默认分支">
          <el-input v-model="editRepo.default_branch" placeholder="main" />
        </el-form-item>
        <el-form-item label="鉴权方式">
          <el-select v-model="editRepo.auth_type" placeholder="无" clearable style="width:100%">
            <el-option label="无（公开仓）" value="" />
            <el-option label="HTTPS Token" value="https_token" />
            <el-option label="SSH 私钥" value="ssh_key" />
          </el-select>
        </el-form-item>
        <el-form-item v-if="editRepo.auth_type === 'https_token'" label="Token 环境变量名">
          <el-input v-model="editRepo.auth_secret_ref" placeholder="例如: GIT_TOKEN_REPO_1" maxlength="256" />
        </el-form-item>
        <el-form-item v-if="editRepo.auth_type === 'ssh_key'" label="SSH 私钥路径">
          <el-input v-model="editRepo.auth_secret_ref" placeholder="例如: ~/.ssh/id_rsa 或 /root/.ssh/id_rsa" maxlength="256" />
          <div class="gs-form-hint">直接填写私钥文件路径（支持 ~ 展开），或填写环境变量名</div>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showEdit = false">取消</el-button>
        <el-button type="primary" @click="saveEdit" :loading="saving">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Refresh, Delete, EditPen, Upload } from '@element-plus/icons-vue'
import { useFormatDate } from '../../composables/useFormatDate.js'
import api from '../../api.js'

const props = defineProps({
  projectId: [String, Number],
  project: Object,
})

const loading = ref(false)
const repos = ref([])
const showAdd = ref(false)
const adding = ref(false)
const showUpload = ref(false)
const uploading = ref(false)
const uploadForm = ref({ name: '' })
const uploadFile = ref(null)
const uploadRef = ref(null)
const syncingId = ref(null)
const newRepo = ref({ name: '', git_url: '', default_branch: 'main', auth_type: '', auth_secret_ref: '' })
const showEdit = ref(false)
const saving = ref(false)
const editRepo = ref({ repo_id: null, git_url: '', default_branch: 'main', auth_type: '', auth_secret_ref: '' })

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

const { formatDate } = useFormatDate()
function formatDateShort(d) {
  return formatDate(d, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
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
      auth_type: newRepo.value.auth_type || undefined,
      auth_secret_ref: newRepo.value.auth_secret_ref?.trim() || undefined,
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

function onUploadFileChange(file) {
  uploadFile.value = file?.raw || null
}

function onUploadFileRemove() {
  uploadFile.value = null
}

function resetUploadForm() {
  uploadForm.value = { name: '' }
  uploadFile.value = null
  uploadRef.value?.clearFiles?.()
}

async function submitUpload() {
  if (!uploadForm.value.name.trim() || !uploadFile.value) return
  uploading.value = true
  try {
    await api.uploadRepo(props.projectId, uploadFile.value, uploadForm.value.name.trim())
    ElMessage.success('上传成功，仓库已添加')
    showUpload.value = false
    resetUploadForm()
    await loadRepos()
  } catch (e) {
    ElMessage.error('上传失败: ' + (e.message || e))
  } finally {
    uploading.value = false
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
  newRepo.value = { name: '', git_url: '', default_branch: 'main', auth_type: '', auth_secret_ref: '' }
}

function openEdit(row) {
  editRepo.value = {
    repo_id: row.repo_id,
    git_url: row.git_url,
    default_branch: row.default_branch,
    auth_type: row.auth_type || '',
    auth_secret_ref: '', // never send existing secret ref to client; user re-enters env var name if needed
  }
  showEdit.value = true
}

function resetEditForm() {
  editRepo.value = { repo_id: null, git_url: '', default_branch: 'main', auth_type: '', auth_secret_ref: '' }
}

async function saveEdit() {
  if (!editRepo.value.repo_id) return
  saving.value = true
  try {
    const body = {}
    if (editRepo.value.git_url) body.git_url = editRepo.value.git_url.trim()
    if (editRepo.value.default_branch) body.default_branch = editRepo.value.default_branch.trim()
    body.auth_type = editRepo.value.auth_type || null
    body.auth_secret_ref = editRepo.value.auth_secret_ref?.trim() || null
    await api.updateRepo(props.projectId, editRepo.value.repo_id, body)
    ElMessage.success('仓库已更新')
    showEdit.value = false
    await loadRepos()
  } catch (e) {
    ElMessage.error('更新失败: ' + e.message)
  } finally {
    saving.value = false
  }
}

onMounted(loadRepos)
</script>

<style scoped>
.gs-form-hint {
  font-size: 12px;
  color: var(--gs-text-muted);
  margin-top: 4px;
}
.gs-text-muted { color: var(--gs-text-muted); }
</style>
