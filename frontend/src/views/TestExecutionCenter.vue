<template>
  <div class="gs-page">
    <div class="gs-page-header">
      <h1 class="gs-page-title">测试执行</h1>
      <p class="gs-page-desc">创建运行、查看执行结果与通过率。工作流：生成脚本 → 审核/编辑 → 创建运行 → 执行。</p>
    </div>

    <div class="gs-toolbar gs-section">
      <div class="gs-toolbar-left">
        <el-select v-model="filterStatus" placeholder="状态" clearable size="default" style="width: 120px;">
          <el-option label="待执行" value="pending" />
          <el-option label="运行中" value="running" />
          <el-option label="已暂停" value="paused" />
          <el-option label="已取消" value="cancelled" />
          <el-option label="成功" value="success" />
          <el-option label="失败" value="failed" />
        </el-select>
        <el-button @click="loadRuns" :loading="loading" size="default">
          <el-icon><Refresh /></el-icon> 刷新
        </el-button>
      </div>
      <div class="gs-toolbar-right">
        <span class="gs-result-count">{{ runs.length }} 次运行</span>
        <el-button type="primary" size="default" @click="openCreateDialog">
          <el-icon><Plus /></el-icon> 新建运行
        </el-button>
      </div>
    </div>

    <!-- 新建运行弹窗：按 项目 → 风险类型 → 风险级别 树状选用例 -->
    <el-dialog
      v-model="showCreate"
      title="新建测试运行"
      width="640"
      destroy-on-close
      @open="loadCaseTree"
      @close="createForm = getDefaultForm()"
    >
      <el-form :model="createForm" label-width="100px">
        <el-form-item label="运行名称">
          <el-input v-model="createForm.name" placeholder="可选，便于区分本次运行" clearable style="width: 320px;" />
        </el-form-item>
        <el-form-item label="环境">
          <el-select v-model="createForm.environment" placeholder="docker" style="width: 200px;">
            <el-option label="Docker" value="docker" />
            <el-option label="SSH" value="ssh" />
          </el-select>
        </el-form-item>
        <el-form-item v-if="createForm.environment === 'docker'" label="Docker 镜像">
          <el-select
            v-model="createForm.docker_image"
            placeholder="可选，不选则使用默认镜像"
            clearable
            filterable
            style="width: 320px;"
            :loading="imagesLoading"
          >
            <el-option
              v-for="img in envImages"
              :key="(img.repository || '') + ':' + (img.tag || 'latest')"
              :label="(img.repository || '') + (img.tag ? ':' + img.tag : '')"
              :value="(img.repository || '') + (img.tag ? ':' + img.tag : '')"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="选择用例">
          <div class="gs-case-tree-wrap">
            <el-tree
              ref="caseTreeRef"
              :data="caseTreeData"
              show-checkbox
              node-key="id"
              :default-expand-all="false"
              :props="{ label: 'label', children: 'children' }"
            >
              <template #default="{ node, data }">
                <span class="gs-tree-node">
                  <el-icon v-if="data.nodeType === 'project'" class="gs-tree-icon"><Folder /></el-icon>
                  <el-icon v-else-if="data.nodeType === 'riskType'" class="gs-tree-icon"><Warning /></el-icon>
                  <el-icon v-else-if="data.nodeType === 'priority'" class="gs-tree-icon"><Flag /></el-icon>
                  <el-icon v-else class="gs-tree-icon"><Document /></el-icon>
                  <span>{{ node.label }}</span>
                  <span v-if="data.nodeType === 'case'" class="gs-tree-case-title">{{ data.title }}</span>
                </span>
              </template>
            </el-tree>
            <div v-if="caseTreeLoading" class="gs-tree-loading">
              <el-icon class="is-loading"><Loading /></el-icon> 加载用例中…
            </div>
            <el-empty v-else-if="!caseTreeData.length" description="暂无已持久化的测试用例，请先在测试设计中生成并保存用例" :image-size="48" />
          </div>
        </el-form-item>
      </el-form>
      <template #footer>
        <span class="gs-dialog-footer-hint">已选 {{ selectedCaseCount }} 条用例</span>
        <el-button @click="showCreate = false">取消</el-button>
        <el-button type="primary" :loading="creating" :disabled="selectedCaseCount === 0" @click="doCreateRun">
          创建
        </el-button>
      </template>
    </el-dialog>

    <div class="gs-card">
      <el-table :data="filteredRuns" size="small" class="gs-table">
        <el-table-column label="运行" width="280">
          <template #default="{ row }">
            <a href="#" class="gs-mono-link" @click.prevent="$router.push(`/test-execution/${row.run_id}`)">
              {{ row.name || row.run_id }}
            </a>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <span class="gs-status-dot" :class="'gs-status-dot--' + row.status"></span>
            {{ runStatusLabel(row.status) }}
          </template>
        </el-table-column>
        <el-table-column label="环境" width="90" prop="environment" />
        <el-table-column label="通过/失败/跳过" width="140">
          <template #default="{ row }">
            <span v-if="row.total > 0">
              <el-tag type="success" size="small">{{ row.passed }}</el-tag>
              <el-tag type="danger" size="small">{{ row.failed }}</el-tag>
              <el-tag type="info" size="small">{{ row.skipped }}</el-tag>
              / {{ row.total }}
            </span>
            <span v-else class="gs-text-muted">-</span>
          </template>
        </el-table-column>
        <el-table-column label="创建时间" width="170">
          <template #default="{ row }">{{ formatDate(row.created_at) }}</template>
        </el-table-column>
        <el-table-column label="操作" fixed="right" width="320">
          <template #default="{ row }">
            <el-button text size="small" type="primary" @click="$router.push(`/test-execution/${row.run_id}`)">
              详情
            </el-button>
            <el-button
              v-if="row.status === 'pending' || row.status === 'paused'"
              text size="small"
              type="success"
              @click="triggerExecute(row)"
            >
              {{ row.status === 'paused' ? '恢复' : '执行' }}
            </el-button>
            <el-button
              v-if="row.status === 'running'"
              text size="small"
              @click="pauseRun(row)"
            >
              暂停
            </el-button>
            <el-button
              v-if="row.status === 'running' || row.status === 'paused'"
              text size="small"
              type="danger"
              @click="cancelRun(row)"
            >
              强制停止
            </el-button>
            <el-button
              text size="small"
              type="danger"
              @click="deleteRun(row)"
            >
              删除
            </el-button>
          </template>
        </el-table-column>
      </el-table>
      <el-empty v-if="!loading && !filteredRuns.length" description="暂无测试运行" :image-size="60" />
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useFormatDate } from '../composables/useFormatDate.js'
import { useAppStore } from '../stores/app.js'
import api from '../api.js'

const props = defineProps({
  projectId: { type: [String, Number], default: null },
})

const route = useRoute()
const appStore = useAppStore()
const projectId = computed(() => props.projectId || route.params.projectId || null)
const { formatDate } = useFormatDate()

const loading = ref(false)
const runs = ref([])
const filterStatus = ref(null)
const showCreate = ref(false)
const creating = ref(false)
const caseTreeRef = ref(null)
const caseTreeData = ref([])
const caseTreeLoading = ref(false)

const riskTypeLabel = {
  boundary_miss: '边界值遗漏',
  missing_cleanup: '资源清理遗漏',
  lock_order_inversion: '锁序反转',
  race_condition: '竞态条件',
  invalid_input_gap: '非法输入缺口',
  branch_high_complexity: '高复杂度分支',
  diff_impact: '变更影响',
  high_risk_low_coverage: '高风险低覆盖',
}

function getDefaultForm() {
  return { environment: 'docker', name: '', docker_image: '' }
}

const createForm = ref(getDefaultForm())
const envImages = ref([])
const imagesLoading = ref(false)

const selectedCaseCount = computed(() => {
  if (!caseTreeRef.value) return 0
  const nodes = caseTreeRef.value.getCheckedNodes()
  return nodes.filter(n => n.nodeType === 'case').length
})

const filteredRuns = computed(() => {
  let list = [...runs.value]
  if (filterStatus.value) list = list.filter(r => r.status === filterStatus.value)
  return list.sort((a, b) => new Date(b.created_at) - new Date(a.created_at))
})

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

function buildCaseTree(cases) {
  const byProject = {}
  for (const c of cases) {
    const pid = c.project_id ?? 0
    if (!byProject[pid]) byProject[pid] = {}
    const cat = c.category || c.risk_type || 'other'
    if (!byProject[pid][cat]) byProject[pid][cat] = {}
    const pri = (c.priority || 'P3').split('-')[0].trim()
    if (!byProject[pid][cat][pri]) byProject[pid][cat][pri] = []
    byProject[pid][cat][pri].push(c)
  }
  const tree = []
  for (const [pidStr, byCat] of Object.entries(byProject)) {
    const pid = Number(pidStr)
    const projName = appStore.getProjectById(pid)?.name || `项目 #${pid}`
    const projectNodeId = `p-${pid}`
    const projectNode = { id: projectNodeId, label: projName, nodeType: 'project', children: [] }
    for (const [cat, byPri] of Object.entries(byCat)) {
      const catLabel = riskTypeLabel[cat] || cat
      const catNodeId = `${projectNodeId}-${cat}`
      const catNode = { id: catNodeId, label: catLabel, nodeType: 'riskType', children: [] }
      for (const [pri, items] of Object.entries(byPri)) {
        const priNodeId = `${catNodeId}-${pri}`
        const priNode = {
          id: priNodeId,
          label: `优先级 ${pri}`,
          nodeType: 'priority',
          children: items.map(tc => ({
            id: `case-${tc.id}`,
            label: tc.test_case_id || tc.case_id || `TC-${tc.id}`,
            nodeType: 'case',
            testCaseId: tc.id,
            title: tc.title,
          })),
        }
        catNode.children.push(priNode)
      }
      projectNode.children.push(catNode)
    }
    tree.push(projectNode)
  }
  return tree
}

async function loadCaseTree() {
  caseTreeData.value = []
  caseTreeLoading.value = true
  envImages.value = []
  imagesLoading.value = true
  try {
    const [casesPromise, imagesPromise] = [
      (async () => {
        let allCases = []
        if (projectId.value) {
          const data = await api.getProjectTestCases(Number(projectId.value), { persisted: true, page_size: 200 })
          allCases = (data?.test_cases || []).map(c => ({ ...c, project_id: projectId.value }))
        } else {
          await appStore.fetchProjects()
          const projects = appStore.projects || []
          for (const p of projects) {
            const pid = p.id ?? p.project_id
            if (!pid) continue
            try {
              const data = await api.getProjectTestCases(pid, { persisted: true, page_size: 200 })
              allCases = allCases.concat((data?.test_cases || []).map(c => ({ ...c, project_id: pid })))
            } catch (err) {
              console.warn('加载项目用例失败:', pid, err)
            }
          }
        }
        return allCases
      })(),
      api.listEnvImages().then(data => data?.images || []).catch(() => []),
    ]
    const [allCases, images] = await Promise.all([casesPromise, imagesPromise])
    caseTreeData.value = buildCaseTree(allCases)
    envImages.value = images
  } catch (e) {
    ElMessage.error('加载用例树失败: ' + (e.message || e))
  } finally {
    caseTreeLoading.value = false
    imagesLoading.value = false
  }
}

function openCreateDialog() {
  showCreate.value = true
}

async function loadRuns() {
  loading.value = true
  try {
    const params = { page: 1, page_size: 100 }
    if (projectId.value) params.project_id = Number(projectId.value)
    const data = await api.listTestRuns(params)
    runs.value = data?.test_runs || data?.items || data || []
  } catch {
    runs.value = []
  } finally {
    loading.value = false
  }
}

async function triggerExecute(row) {
  try {
    await api.executeTestRun(row.run_id)
    ElMessage.success(row.status === 'paused' ? '已加入队列，将恢复执行' : '已加入执行队列')
    await loadRuns()
  } catch (e) {
    ElMessage.error('触发执行失败: ' + (e.message || e))
  }
}

async function pauseRun(row) {
  try {
    await api.pauseTestRun(row.run_id)
    ElMessage.success('已暂停')
    await loadRuns()
  } catch (e) {
    ElMessage.error('暂停失败: ' + (e.message || e))
  }
}

async function cancelRun(row) {
  try {
    await api.cancelTestRun(row.run_id)
    ElMessage.success('已强制停止')
    await loadRuns()
  } catch (e) {
    ElMessage.error('停止失败: ' + (e.message || e))
  }
}

async function deleteRun(row) {
  try {
    await ElMessageBox.confirm(`确定删除运行 ${row.run_id}？删除后不可恢复。`, '删除运行', {
      confirmButtonText: '删除',
      cancelButtonText: '取消',
      type: 'warning',
    })
  } catch {
    return
  }
  try {
    await api.deleteTestRun(row.run_id)
    ElMessage.success('已删除')
    await loadRuns()
  } catch (e) {
    ElMessage.error('删除失败: ' + (e.message || e))
  }
}

async function doCreateRun() {
  const tree = caseTreeRef.value
  if (!tree) return
  const nodes = tree.getCheckedNodes()
  const ids = nodes.filter(n => n.nodeType === 'case' && n.testCaseId).map(n => n.testCaseId)
  if (!ids.length) {
    ElMessage.warning('请至少选择一条测试用例')
    return
  }
  const body = { environment: createForm.value.environment || 'docker', test_case_ids: ids }
  if (projectId.value) body.project_id = Number(projectId.value)
  if (createForm.value.name?.trim()) body.name = createForm.value.name.trim()
  if (createForm.value.docker_image?.trim()) body.docker_image = createForm.value.docker_image.trim()
  creating.value = true
  try {
    await api.createTestRun(body)
    ElMessage.success('运行已创建')
    showCreate.value = false
    createForm.value = getDefaultForm()
    await loadRuns()
  } catch (e) {
    ElMessage.error('创建失败: ' + (e.message || e))
  } finally {
    creating.value = false
  }
}

onMounted(loadRuns)
watch(projectId, loadRuns)
</script>

<style scoped>
.gs-toolbar { display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: var(--gs-space-md); }
.gs-toolbar-left, .gs-toolbar-right { display: flex; align-items: center; gap: var(--gs-space-sm); }
.gs-result-count { font-size: var(--gs-font-sm); color: var(--gs-text-muted); }
.gs-mono-link { font-family: var(--gs-font-mono); font-size: 12px; }

.gs-case-tree-wrap { position: relative; max-height: 400px; overflow-y: auto; border: 1px solid var(--gs-border); border-radius: 6px; padding: 12px; background: var(--gs-surface); }
.gs-tree-loading { padding: 24px; text-align: center; color: var(--gs-text-muted); }
.gs-tree-node { display: inline-flex; align-items: center; gap: 6px; }
.gs-tree-icon { margin-right: 4px; color: var(--gs-text-muted); }
.gs-tree-case-title { margin-left: 6px; font-size: 12px; color: var(--gs-text-secondary); max-width: 240px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.gs-dialog-footer-hint { font-size: 12px; color: var(--gs-text-muted); margin-right: 12px; }
</style>
