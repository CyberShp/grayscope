<template>
  <div class="gs-page">
    <div class="gs-page-header">
      <h1 class="gs-page-title">执行环境</h1>
      <p class="gs-page-desc">轻量 Docker 管理：拉取或导入镜像，创建并管理容器，用于测试执行等场景。</p>
    </div>

    <el-tabs v-model="activeTab" class="gs-env-tabs">
      <!-- 镜像管理 -->
      <el-tab-pane label="镜像管理" name="images">
        <div class="gs-card gs-section">
          <div class="gs-toolbar">
            <div class="gs-toolbar-left">
              <el-button type="primary" size="default" @click="showPullDialog = true">
                <el-icon><Download /></el-icon> 拉取镜像
              </el-button>
              <el-button size="default" @click="fileInputRef?.click()">
                <el-icon><Upload /></el-icon> 导入镜像
              </el-button>
              <input
                ref="fileInputRef"
                type="file"
                accept=".tar,.tar.gz"
                style="display:none"
                @change="onLoadImageFile"
              />
            </div>
            <div class="gs-toolbar-right">
              <el-button :loading="imagesLoading" size="default" @click="loadImages">刷新</el-button>
            </div>
          </div>
          <el-table :data="images" size="small" class="gs-table">
            <el-table-column label="镜像" min-width="200">
              <template #default="{ row }">{{ row.repository }}:{{ row.tag }}</template>
            </el-table-column>
            <el-table-column label="ID" width="140" prop="id" />
            <el-table-column label="大小" width="100">
              <template #default="{ row }">{{ formatSize(row.size) }}</template>
            </el-table-column>
            <el-table-column label="创建时间" width="180">
              <template #default="{ row }">{{ formatDate(row.created) }}</template>
            </el-table-column>
          </el-table>
          <el-empty v-if="!imagesLoading && !images.length" description="暂无镜像，请拉取或导入" />
        </div>
      </el-tab-pane>

      <!-- 容器管理 -->
      <el-tab-pane label="容器管理" name="containers">
        <div class="gs-card gs-section">
          <div class="gs-toolbar">
            <div class="gs-toolbar-left">
              <el-button type="primary" size="default" @click="showCreateContainerDialog = true">
                <el-icon><Plus /></el-icon> 创建容器
              </el-button>
            </div>
            <div class="gs-toolbar-right">
              <el-checkbox v-model="containersIncludeStopped">含已停止</el-checkbox>
              <el-button :loading="containersLoading" size="default" @click="loadContainers">刷新</el-button>
            </div>
          </div>
          <el-table :data="containers" size="small" class="gs-table">
            <el-table-column label="名称" min-width="160" prop="name" />
            <el-table-column label="镜像" min-width="180" prop="image" />
            <el-table-column label="状态" width="100">
              <template #default="{ row }">
                <span class="gs-status-dot" :class="'gs-status-dot--' + containerStatusClass(row.status)"></span>
                {{ row.status }}
              </template>
            </el-table-column>
            <el-table-column label="ID" width="140" prop="id" />
            <el-table-column label="创建时间" width="180">
              <template #default="{ row }">{{ formatDate(row.created) }}</template>
            </el-table-column>
            <el-table-column label="操作" fixed="right" width="220">
              <template #default="{ row }">
                <el-button
                  v-if="row.status !== 'running'"
                  text size="small"
                  type="success"
                  @click="startContainer(row)"
                >
                  启动
                </el-button>
                <el-button
                  v-if="row.status === 'running'"
                  text size="small"
                  @click="stopContainer(row)"
                >
                  停止
                </el-button>
                <el-button text size="small" type="danger" @click="removeContainer(row)">
                  删除
                </el-button>
              </template>
            </el-table-column>
          </el-table>
          <el-empty v-if="!containersLoading && !containers.length" description="暂无容器，请创建" />
        </div>
      </el-tab-pane>
    </el-tabs>

    <!-- 拉取镜像对话框 -->
    <el-dialog v-model="showPullDialog" title="拉取镜像" width="400" @close="pullImageName = ''">
      <el-form label-width="80px">
        <el-form-item label="镜像名">
          <el-input v-model="pullImageName" placeholder="如 ubuntu:22.04 或 nginx:latest" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showPullDialog = false">取消</el-button>
        <el-button type="primary" :loading="pulling" :disabled="!pullImageName.trim()" @click="doPullImage">
          拉取
        </el-button>
      </template>
    </el-dialog>

    <!-- 创建容器对话框 -->
    <el-dialog v-model="showCreateContainerDialog" title="创建容器" width="440" @close="resetCreateForm">
          <el-form :model="createForm" label-width="90px">
        <el-form-item label="镜像">
          <el-select v-model="createForm.image" filterable allow-create placeholder="选择或输入镜像" style="width:100%">
            <el-option v-for="(img, idx) in images" :key="img.id + '-' + (img.tags && img.tags[0]) + '-' + idx" :label="`${img.repository}:${img.tag}`" :value="(img.tags && img.tags[0]) || `${img.repository}:${img.tag}`" />
          </el-select>
        </el-form-item>
        <el-form-item label="容器名称">
          <el-input v-model="createForm.name" placeholder="可选，留空自动生成" />
        </el-form-item>
        <el-form-item label="启动命令">
          <el-input v-model="createForm.cmd" placeholder="可选，如 /bin/bash" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showCreateContainerDialog = false">取消</el-button>
        <el-button type="primary" :loading="creating" :disabled="!createForm.image" @click="doCreateContainer">
          创建
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Download, Upload, Plus } from '@element-plus/icons-vue'
import { useFormatDate } from '../composables/useFormatDate.js'
import api from '../api.js'

const activeTab = ref('images')
const { formatDate } = useFormatDate()

const images = ref([])
const imagesLoading = ref(false)
const showPullDialog = ref(false)
const pullImageName = ref('')
const pulling = ref(false)
const fileInputRef = ref(null)

const containers = ref([])
const containersLoading = ref(false)
const containersIncludeStopped = ref(true)
const showCreateContainerDialog = ref(false)
const creating = ref(false)
const createForm = ref({ image: '', name: '', cmd: '' })

function formatSize(bytes) {
  if (bytes == null || bytes === 0) return '-'
  const k = 1024
  const units = ['B', 'KB', 'MB', 'GB']
  let i = 0
  while (bytes >= k && i < units.length - 1) {
    bytes /= k
    i++
  }
  return `${bytes.toFixed(1)} ${units[i]}`
}

function containerStatusClass(s) {
  if (s === 'running') return 'success'
  if (s === 'exited' || s === 'dead') return 'failed'
  return 'pending'
}

async function loadImages() {
  imagesLoading.value = true
  try {
    const data = await api.listEnvImages()
    images.value = data?.images || []
  } catch (e) {
    ElMessage.error('加载镜像列表失败: ' + (e.message || e))
    images.value = []
  } finally {
    imagesLoading.value = false
  }
}

async function doPullImage() {
  const name = pullImageName.value.trim()
  if (!name) return
  pulling.value = true
  try {
    await api.pullEnvImage(name)
    ElMessage.success('拉取成功')
    showPullDialog.value = false
    pullImageName.value = ''
    await loadImages()
  } catch (e) {
    ElMessage.error('拉取失败: ' + (e.message || e))
  } finally {
    pulling.value = false
  }
}

function onLoadImageFile(ev) {
  const file = ev.target?.files?.[0]
  if (!file) return
  api.loadEnvImage(file).then(() => {
    ElMessage.success('导入成功')
    loadImages()
  }).catch(e => {
    ElMessage.error('导入失败: ' + (e.message || e))
  })
  ev.target.value = ''
}

async function loadContainers() {
  containersLoading.value = true
  try {
    const data = await api.listEnvContainers(containersIncludeStopped.value)
    containers.value = data?.containers || []
  } catch (e) {
    ElMessage.error('加载容器列表失败: ' + (e.message || e))
    containers.value = []
  } finally {
    containersLoading.value = false
  }
}

function resetCreateForm() {
  createForm.value = { image: '', name: '', cmd: '' }
}

async function doCreateContainer() {
  if (!createForm.value.image) return
  creating.value = true
  try {
    await api.createEnvContainer({
      image: createForm.value.image,
      name: createForm.value.name.trim() || undefined,
      cmd: createForm.value.cmd.trim() || undefined,
    })
    ElMessage.success('容器已创建')
    showCreateContainerDialog.value = false
    resetCreateForm()
    await loadContainers()
  } catch (e) {
    ElMessage.error('创建失败: ' + (e.message || e))
  } finally {
    creating.value = false
  }
}

async function startContainer(row) {
  try {
    await api.startEnvContainer(row.id)
    ElMessage.success('已启动')
    await loadContainers()
  } catch (e) {
    ElMessage.error('启动失败: ' + (e.message || e))
  }
}

async function stopContainer(row) {
  try {
    await api.stopEnvContainer(row.id)
    ElMessage.success('已停止')
    await loadContainers()
  } catch (e) {
    ElMessage.error('停止失败: ' + (e.message || e))
  }
}

async function removeContainer(row) {
  try {
    await ElMessageBox.confirm(
      `确定删除容器 ${row.name || row.id}？${row.status === 'running' ? '运行中的容器需强制删除。' : ''}`,
      '删除容器',
      { confirmButtonText: '删除', cancelButtonText: '取消', type: 'warning' }
    )
  } catch {
    return
  }
  try {
    await api.removeEnvContainer(row.id, row.status === 'running')
    ElMessage.success('已删除')
    await loadContainers()
  } catch (e) {
    ElMessage.error('删除失败: ' + (e.message || e))
  }
}

onMounted(() => {
  loadImages()
  loadContainers()
})
watch(containersIncludeStopped, loadContainers)
watch(activeTab, (tab) => {
  if (tab === 'images') loadImages()
  else loadContainers()
})
</script>

<style scoped>
.gs-env-tabs :deep(.el-tabs__header) { margin-bottom: var(--gs-space-md); }
.gs-toolbar { display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: var(--gs-space-md); margin-bottom: var(--gs-space-md); }
</style>
