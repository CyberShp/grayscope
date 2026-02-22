<template>
  <div class="gs-page gs-tc-detail-page">
    <!-- 返回导航 -->
    <div class="gs-tc-nav gs-section">
      <router-link to="/test-design" class="gs-back-link">&larr; 返回测试设计中心</router-link>
    </div>

    <!-- 新手指引（可折叠） -->
    <div class="gs-tc-section gs-section">
      <el-collapse>
        <el-collapse-item name="guide">
          <template #title>
            <span class="gs-tc-guide-title"><el-icon><QuestionFilled /></el-icon> 新手指引：如何执行本用例</span>
          </template>
          <div class="gs-tc-guide-body">
            <p><strong>灰盒核心</strong>：一次用例暴露<strong>多函数交汇临界点</strong>，避免黑盒需要 N 次才能撞出的问题（例如：login + 端口闪断处理 + 网卡下电 交汇时，预期失败是建联失败，不可接受是控制器下电/进程崩溃）。</p>
            <p><strong>1. 看关联函数与目标</strong>：「关联函数」即交汇的多个函数/分支；「预期失败」为可接受结果，「不可接受结果」一旦出现即缺陷。</p>
            <p><strong>2. 按步骤执行</strong>：在测试环境中逐条执行步骤，参考「如何执行」和「示例数据」。</p>
            <p><strong>3. 对照预期与不可接受</strong>：结果落在「预期失败」内为通过；若出现「不可接受结果」则需提缺陷。</p>
            <p><strong>4. 导出与对接</strong>：使用任务详情的「导出 → Markdown」可下载含关联函数/预期失败/不可接受的清单。</p>
          </div>
        </el-collapse-item>
      </el-collapse>
    </div>

    <!-- 加载/错误状态 -->
    <div v-if="loading && !tc" class="gs-tc-empty">
      <el-skeleton :rows="5" animated />
    </div>
    <div v-else-if="!tc" class="gs-tc-empty">
      <el-empty description="未找到测试用例数据，请从测试设计中心进入">
        <router-link to="/test-design"><el-button type="primary">前往测试设计中心</el-button></router-link>
      </el-empty>
    </div>

    <template v-else>
      <!-- 头部卡片 -->
      <div class="gs-tc-hero gs-section">
        <div class="gs-tc-hero-top">
          <span class="gs-tc-prio-badge" :class="prioClass">{{ prioLabel }}</span>
          <code class="gs-tc-id-label">{{ tc.test_case_id }}</code>
          <span class="gs-tc-module-badge">{{ tc.module_display_name }}</span>
          <span v-if="projectName" class="gs-tc-project-badge">{{ projectName }}</span>
          <div style="flex:1"></div>
          <el-button v-if="canEdit" size="small" type="primary" @click="showEditDialog = true">编辑</el-button>
          <span class="gs-tc-risk-badge" :style="{ background: riskBg }">
            风险 {{ (tc.risk_score * 100).toFixed(0) }}%
          </span>
        </div>
        <h1 class="gs-tc-hero-title">{{ tc.title || '未命名测试用例' }}</h1>
        <p class="gs-tc-hero-objective">
          <el-icon><Aim /></el-icon>
          {{ tc.objective }}
        </p>
        <div class="gs-tc-hero-location">
          <el-icon><Document /></el-icon>
          <code>{{ tc.target_file }}</code>
          <span v-if="tc.target_function"> → <code>{{ tc.target_function }}()</code></span>
          <span v-if="tc.line_start" class="gs-tc-hero-lines">L{{ tc.line_start }}<span v-if="tc.line_end">–{{ tc.line_end }}</span></span>
        </div>
      </div>

      <!-- 两栏：左=测试设计，右=分析证据 -->
      <div class="gs-tc-body">
        <!-- 左栏：完整测试设计 -->
        <div class="gs-tc-col-left">
          <div class="gs-tc-card">
            <h2 class="gs-tc-card-title"><el-icon><List /></el-icon> 前置条件</h2>
            <ul class="gs-tc-list" v-if="tc.preconditions?.length">
              <li v-for="(p, i) in tc.preconditions" :key="i">{{ p }}</li>
            </ul>
            <p v-else class="gs-tc-muted">无特殊前置条件</p>
          </div>

          <div class="gs-tc-card">
            <h2 class="gs-tc-card-title"><el-icon><Guide /></el-icon> 测试步骤</h2>
            <ol class="gs-tc-steps" v-if="tc.test_steps?.length">
              <li v-for="(s, i) in tc.test_steps" :key="i">
                <span class="gs-tc-step-text">{{ stripNumber(s) }}</span>
              </li>
            </ol>
            <p v-else class="gs-tc-muted">无测试步骤</p>
          </div>

          <div class="gs-tc-card" v-if="tc.related_functions?.length">
            <h2 class="gs-tc-card-title">关联函数（交汇临界点）</h2>
            <p class="gs-tc-related-funcs">{{ (tc.related_functions || []).join(' → ') }}</p>
            <p class="gs-tc-gray-desc">灰盒目标：一次用例暴露多函数交汇时的临界行为</p>
          </div>
          <div class="gs-tc-card gs-tc-card-expected">
            <h2 class="gs-tc-card-title"><el-icon><CircleCheck /></el-icon> 预期结果</h2>
            <div class="gs-tc-expected-body">{{ expectedDisplay }}</div>
          </div>
          <div class="gs-tc-card" v-if="tc.expected_failure">
            <h2 class="gs-tc-card-title">预期失败（可接受）</h2>
            <p class="gs-tc-hint">{{ tc.expected_failure }}</p>
          </div>
          <div class="gs-tc-card" v-if="tc.unacceptable_outcomes?.length">
            <h2 class="gs-tc-card-title">不可接受结果</h2>
            <ul class="gs-tc-list">
              <li v-for="(o, i) in tc.unacceptable_outcomes" :key="i">{{ o }}</li>
            </ul>
          </div>

          <div class="gs-tc-card" v-if="tc.execution_hint">
            <h2 class="gs-tc-card-title"><el-icon><Guide /></el-icon> 如何执行</h2>
            <p class="gs-tc-hint">{{ tc.execution_hint }}</p>
          </div>
          <div class="gs-tc-card" v-if="tc.example_input">
            <h2 class="gs-tc-card-title">示例数据</h2>
            <p class="gs-tc-example">{{ tc.example_input }}</p>
          </div>

          <!-- 风险类型信息 -->
          <div class="gs-tc-card" v-if="tc.category">
            <h2 class="gs-tc-card-title"><el-icon><WarningFilled /></el-icon> 风险分类</h2>
            <div class="gs-tc-risk-info">
              <el-tag size="default">{{ getRiskTypeName(tc.category) }}</el-tag>
              <span class="gs-tc-risk-desc">{{ riskDescription }}</span>
            </div>
          </div>
        </div>

        <!-- 右栏：分析证据 -->
        <div class="gs-tc-col-right">
          <div class="gs-tc-card" v-if="tc.evidence && Object.keys(tc.evidence).length">
            <h2 class="gs-tc-card-title"><el-icon><DataAnalysis /></el-icon> 分析证据</h2>
            <div class="gs-tc-evidence-full">
              <EvidenceRenderer
                :module-id="tc.module_id"
                :risk-type="tc.category"
                :evidence="tc.evidence"
                :finding="tc"
              />
            </div>
          </div>
          <div class="gs-tc-card" v-else>
            <h2 class="gs-tc-card-title"><el-icon><DataAnalysis /></el-icon> 分析证据</h2>
            <p class="gs-tc-muted">此用例无关联的结构化证据</p>
          </div>

          <!-- 来源发现信息 -->
          <div class="gs-tc-card" v-if="tc.source_finding_id">
            <h2 class="gs-tc-card-title"><el-icon><Connection /></el-icon> 来源发现</h2>
            <div class="gs-tc-source">
              <code>{{ tc.source_finding_id }}</code>
            </div>
          </div>
        </div>
      </div>

      <!-- 编辑对话框 -->
      <el-dialog v-model="showEditDialog" title="编辑测试用例" width="560px" :close-on-click-modal="false" @closed="resetEditForm">
        <el-form :model="editForm" label-width="90px">
          <el-form-item label="优先级">
            <el-select v-model="editForm.priority" placeholder="选择优先级" style="width:100%">
              <el-option label="P0-紧急" value="P0-紧急" />
              <el-option label="P1-高" value="P1-高" />
              <el-option label="P2-中" value="P2-中" />
              <el-option label="P3-低" value="P3-低" />
            </el-select>
          </el-form-item>
          <el-form-item label="测试目标">
            <el-input v-model="editForm.objective" type="textarea" :rows="2" />
          </el-form-item>
          <el-form-item label="前置条件">
            <el-input v-model="editForm.preconditionsText" type="textarea" :rows="2" placeholder="每行一条" />
          </el-form-item>
          <el-form-item label="测试步骤">
            <el-input v-model="editForm.testStepsText" type="textarea" :rows="4" placeholder="每行一条" />
          </el-form-item>
          <el-form-item label="预期结果">
            <el-input v-model="editForm.expectedResult" type="textarea" :rows="3" />
          </el-form-item>
          <el-form-item label="如何执行">
            <el-input v-model="editForm.executionHint" type="textarea" :rows="2" placeholder="在什么环境、用什么方式执行" />
          </el-form-item>
          <el-form-item label="示例数据">
            <el-input v-model="editForm.exampleInput" type="textarea" :rows="2" placeholder="便于新手构造的示例输入" />
          </el-form-item>
          <el-form-item label="关联函数">
            <el-input v-model="editForm.relatedFunctionsText" type="textarea" :rows="1" placeholder="多个函数用逗号或空格分隔，如: login, handle_port_flap, handle_card_power_off" />
          </el-form-item>
          <el-form-item label="预期失败（可接受）">
            <el-input v-model="editForm.expectedFailure" placeholder="如: 建联失败" />
          </el-form-item>
          <el-form-item label="不可接受结果">
            <el-input v-model="editForm.unacceptableText" type="textarea" :rows="2" placeholder="每行一条，如: 控制器下电、进程崩溃" />
          </el-form-item>
        </el-form>
        <template #footer>
          <el-button @click="showEditDialog = false">取消</el-button>
          <el-button type="primary" @click="saveEdit" :loading="saving">保存</el-button>
        </template>
      </el-dialog>
    </template>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Aim, Document, List, Guide, CircleCheck, WarningFilled, DataAnalysis, Connection, QuestionFilled } from '@element-plus/icons-vue'
import { useAppStore } from '../stores/app.js'
import { useRiskColor } from '../composables/useRiskColor.js'
import { getRiskTypeName } from '../composables/useRiskTypeNames.js'
import EvidenceRenderer from '../components/EvidenceRenderer.vue'
import api from '../api.js'

const route = useRoute()
const appStore = useAppStore()
const { riskColor } = useRiskColor()

const tc = ref(null)
const loading = ref(true)
const showEditDialog = ref(false)
const saving = ref(false)
const editForm = ref({
  priority: '',
  objective: '',
  preconditionsText: '',
  testStepsText: '',
  expectedResult: '',
  executionHint: '',
  exampleInput: '',
  relatedFunctionsText: '',
  expectedFailure: '',
  unacceptableText: '',
})

const canEdit = computed(() => tc.value && typeof tc.value.id === 'number')
const expectedDisplay = computed(() => {
  const e = tc.value?.expected_result
  if (Array.isArray(e)) return e.join('\n')
  return e != null ? String(e) : ''
})

async function loadById(id) {
  const numId = parseInt(id, 10)
  if (Number.isNaN(numId)) return
  try {
    const data = await api.getTestCase(numId)
    if (data?.test_case) tc.value = data.test_case
  } catch {
    tc.value = null
  }
}

onMounted(async () => {
  if (history.state?.tc) {
    tc.value = history.state.tc
    loading.value = false
  } else if (route.params.testCaseId) {
    await loadById(route.params.testCaseId)
  }
  loading.value = false
  appStore.fetchProjects()
})

watch(() => route.params.testCaseId, async (id) => {
  if (id && !history.state?.tc) {
    loading.value = true
    await loadById(id)
    loading.value = false
  }
})

function openEditForm() {
  const t = tc.value
  if (!t) return
  editForm.value = {
    priority: t.priority || 'P3-低',
    objective: t.objective || '',
    preconditionsText: (t.preconditions || []).join('\n'),
    testStepsText: (t.test_steps || []).map(s => typeof s === 'string' ? s.replace(/^\d+\.\s*/, '') : s).join('\n'),
    expectedResult: Array.isArray(t.expected_result) ? t.expected_result.join('\n') : (t.expected_result || ''),
    executionHint: t.execution_hint || '',
    exampleInput: t.example_input || '',
    relatedFunctionsText: (t.related_functions || []).join(', '),
    expectedFailure: t.expected_failure || '',
    unacceptableText: (t.unacceptable_outcomes || []).join('\n'),
  }
}

watch(showEditDialog, (v) => { if (v) openEditForm() })

function resetEditForm() {
  editForm.value = { priority: '', objective: '', preconditionsText: '', testStepsText: '', expectedResult: '', executionHint: '', exampleInput: '', relatedFunctionsText: '', expectedFailure: '', unacceptableText: '' }
}

async function saveEdit() {
  if (!tc.value?.id) return
  saving.value = true
  try {
    const preconditions = editForm.value.preconditionsText.split('\n').map(s => s.trim()).filter(Boolean)
    const steps = editForm.value.testStepsText.split('\n').map(s => s.trim()).filter(Boolean)
    const body = {
      priority: editForm.value.priority,
      objective: editForm.value.objective || undefined,
      preconditions: preconditions.length ? preconditions : undefined,
      test_steps: steps.length ? steps : undefined,
      expected_result: editForm.value.expectedResult || undefined,
      execution_hint: editForm.value.executionHint || undefined,
      example_input: editForm.value.exampleInput || undefined,
      related_functions: editForm.value.relatedFunctionsText ? editForm.value.relatedFunctionsText.split(/[\s,，]+/).filter(Boolean) : undefined,
      expected_failure: editForm.value.expectedFailure || undefined,
      unacceptable_outcomes: editForm.value.unacceptableText ? editForm.value.unacceptableText.split('\n').map(s => s.trim()).filter(Boolean) : undefined,
    }
    const data = await api.updateTestCase(tc.value.id, body)
    if (data?.test_case) tc.value = data.test_case
    ElMessage.success('已保存')
    showEditDialog.value = false
  } catch (e) {
    ElMessage.error('保存失败: ' + (e.message || '未知错误'))
  } finally {
    saving.value = false
  }
}

const projectName = computed(() => {
  if (!tc.value?.project_id) return ''
  const p = appStore.getProjectById(tc.value.project_id)
  return p?.name || `项目#${tc.value.project_id}`
})

const prioLabel = computed(() => {
  if (!tc.value?.priority) return 'P3'
  return tc.value.priority.split('-')[0]
})

const prioClass = computed(() => {
  return `prio-${prioLabel.value.toLowerCase()}`
})

const riskBg = computed(() => {
  if (!tc.value) return '#999'
  return riskColor(tc.value.risk_score)
})

const riskDescription = computed(() => {
  const map = {
    boundary_miss: '约束条件缺少边界值检查',
    invalid_input_gap: '输入校验不完整，可能导致越界',
    branch_error: '错误处理分支可能未正确触发',
    branch_cleanup: '清理路径可能遗漏资源释放',
    branch_boundary: '边界条件分支处理可能不完整',
    missing_cleanup: '错误路径上可能未释放资源',
    changed_core_path: '变更影响了核心调用路径',
    transitive_impact: '变更通过传递依赖影响下游函数',
    deep_impact_surface: '变更的影响面较深',
    race_write_without_lock: '共享变量写入缺少锁保护',
    deep_param_propagation: '参数通过多层调用链传播',
    external_to_sensitive: '外部输入传播到敏感操作',
    value_transform_risk: '值在传播过程中经历变换',
  }
  return map[tc.value?.category] || '详见分析证据'
})

function stripNumber(s) {
  return s.replace(/^\d+\.\s*/, '')
}
</script>

<style scoped>
.gs-tc-detail-page { max-width: 1200px; margin: 0 auto; }

.gs-tc-nav { margin-bottom: 8px; }
.gs-back-link {
  font-size: 13px; color: var(--gs-primary); text-decoration: none;
  display: inline-flex; align-items: center; gap: 4px;
}
.gs-back-link:hover { text-decoration: underline; }

/* ── 头部 ── */
.gs-tc-hero {
  background: var(--gs-surface); border: 1px solid var(--gs-border);
  border-radius: var(--gs-radius-md); padding: 24px 28px;
  margin-bottom: 16px;
}
.gs-tc-hero-top {
  display: flex; align-items: center; gap: 10px; flex-wrap: wrap; margin-bottom: 12px;
}
.gs-tc-prio-badge {
  display: inline-flex; align-items: center; justify-content: center;
  min-width: 36px; height: 26px; padding: 0 10px;
  border-radius: 6px; font-size: 12px; font-weight: 700; color: #fff;
}
.gs-tc-prio-badge.prio-p0 { background: var(--gs-risk-critical); }
.gs-tc-prio-badge.prio-p1 { background: var(--gs-risk-high); }
.gs-tc-prio-badge.prio-p2 { background: var(--gs-risk-medium); }
.gs-tc-prio-badge.prio-p3 { background: var(--gs-risk-low); }

.gs-tc-id-label {
  font-size: 12px; font-family: var(--gs-font-mono); color: var(--gs-text-muted);
  background: var(--gs-bg); padding: 2px 8px; border-radius: 4px;
}
.gs-tc-module-badge {
  font-size: 11px; padding: 3px 10px;
  background: rgba(75, 159, 213, 0.1); color: var(--gs-primary); border-radius: 12px;
}
.gs-tc-project-badge {
  font-size: 11px; padding: 3px 10px;
  background: rgba(0, 170, 0, 0.08); color: var(--gs-success); border-radius: 12px;
}
.gs-tc-risk-badge {
  padding: 4px 14px; border-radius: 12px;
  font-size: 12px; font-weight: 600; color: #fff;
}
.gs-tc-hero-title {
  font-size: 20px; font-weight: 700; color: var(--gs-text-primary);
  margin: 0 0 10px 0; line-height: 1.4;
}
.gs-tc-hero-objective {
  display: flex; align-items: flex-start; gap: 8px;
  font-size: 14px; color: var(--gs-text-secondary); line-height: 1.6; margin: 0 0 12px 0;
}
.gs-tc-hero-objective .el-icon { margin-top: 3px; color: var(--gs-primary); flex-shrink: 0; }
.gs-tc-hero-location {
  display: flex; align-items: center; gap: 6px;
  font-size: 13px; color: var(--gs-text-muted);
}
.gs-tc-hero-location .el-icon { color: var(--gs-text-muted); }
.gs-tc-hero-location code {
  background: rgba(75, 159, 213, 0.08); padding: 2px 8px; border-radius: 4px;
  font-size: 12px; font-family: var(--gs-font-mono);
}
.gs-tc-hero-lines { margin-left: 6px; font-family: var(--gs-font-mono); font-size: 12px; }

/* ── 两栏布局 ── */
.gs-tc-body {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
  align-items: start;
}
@media (max-width: 900px) {
  .gs-tc-body { grid-template-columns: 1fr; }
}

.gs-tc-card {
  background: var(--gs-surface); border: 1px solid var(--gs-border);
  border-radius: var(--gs-radius-md); padding: 20px 24px;
  margin-bottom: 12px;
  overflow: hidden;
  min-width: 0;
}
.gs-tc-card-title {
  display: flex; align-items: center; gap: 8px;
  font-size: 14px; font-weight: 600; color: var(--gs-text-primary);
  margin: 0 0 14px 0;
}
.gs-tc-card-title .el-icon { color: var(--gs-primary); }

/* ── 列表 ── */
.gs-tc-list, .gs-tc-steps {
  margin: 0; padding-left: 22px;
  font-size: 13px; color: var(--gs-text-secondary); line-height: 2;
}
.gs-tc-steps li::marker { color: var(--gs-primary); font-weight: 600; }
.gs-tc-step-text { display: inline; }
.gs-tc-muted { font-size: 13px; color: var(--gs-text-muted); margin: 0; }
.gs-tc-hint, .gs-tc-example {
  font-size: 13px; color: var(--gs-text-secondary); line-height: 1.6; margin: 0;
  padding: 10px 14px; background: var(--gs-bg); border-radius: var(--gs-radius-sm);
}
.gs-tc-related-funcs {
  font-family: var(--gs-font-mono); font-size: 13px; font-weight: 600; color: var(--gs-primary);
  margin: 0 0 6px 0;
}
.gs-tc-gray-desc { font-size: 12px; color: var(--gs-text-muted); margin: 0; }

/* ── 预期结果 ── */
.gs-tc-card-expected { border-left: 3px solid var(--gs-success); }
.gs-tc-expected-body {
  font-size: 14px; color: var(--gs-success); font-weight: 500;
  line-height: 1.7; padding: 12px 16px;
  background: rgba(0, 170, 0, 0.05); border-radius: var(--gs-radius-sm);
}

/* ── 风险分类 ── */
.gs-tc-risk-info { display: flex; align-items: center; gap: 12px; }
.gs-tc-risk-desc { font-size: 13px; color: var(--gs-text-secondary); }

/* ── 证据区域（全宽展示） ── */
.gs-tc-evidence-full {
  background: var(--gs-bg); border-radius: var(--gs-radius-sm); padding: 16px;
  overflow: hidden;
  min-width: 0;
}

/* ── 来源发现 ── */
.gs-tc-source code {
  font-size: 12px; background: var(--gs-bg); padding: 4px 10px; border-radius: 4px;
  font-family: var(--gs-font-mono);
}

.gs-tc-empty { padding: 80px 0; text-align: center; }

.gs-tc-section .el-collapse-item__header { font-size: 14px; }
.gs-tc-guide-title { display: flex; align-items: center; gap: 8px; color: var(--gs-primary); }
.gs-tc-guide-body {
  padding: 12px 0; font-size: 13px; color: var(--gs-text-secondary); line-height: 1.8;
}
.gs-tc-guide-body p { margin: 0 0 10px 0; }
.gs-tc-guide-body p:last-child { margin-bottom: 0; }
</style>
