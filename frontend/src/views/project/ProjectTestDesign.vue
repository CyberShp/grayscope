<template>
  <div class="gs-page gs-test-design">
    <!-- 页头 -->
    <div class="gs-page-header">
      <div>
        <h1 class="gs-page-title">测试设计中心</h1>
        <p class="gs-page-desc">基于灰盒分析发现，自动生成结构化测试用例建议——这是分析的最终产出物。</p>
      </div>
      <div class="gs-header-actions">
        <el-button type="primary" @click="exportAll('json')">
          <el-icon><Download /></el-icon> 导出全部用例
        </el-button>
      </div>
    </div>

    <!-- 统计面板 -->
    <div class="gs-stats-row" v-if="stats">
      <div class="gs-stat-card gs-stat-total">
        <div class="gs-stat-value">{{ stats.total }}</div>
        <div class="gs-stat-label">测试用例总数</div>
      </div>
      <div class="gs-stat-card gs-stat-p0" @click="setFilter('priority', 'P0')">
        <div class="gs-stat-value">{{ stats.by_priority?.P0 || 0 }}</div>
        <div class="gs-stat-label">P0 紧急</div>
      </div>
      <div class="gs-stat-card gs-stat-p1" @click="setFilter('priority', 'P1')">
        <div class="gs-stat-value">{{ stats.by_priority?.P1 || 0 }}</div>
        <div class="gs-stat-label">P1 高优</div>
      </div>
      <div class="gs-stat-card gs-stat-p2" @click="setFilter('priority', 'P2')">
        <div class="gs-stat-value">{{ stats.by_priority?.P2 || 0 }}</div>
        <div class="gs-stat-label">P2 中</div>
      </div>
      <div class="gs-stat-card gs-stat-p3" @click="setFilter('priority', 'P3')">
        <div class="gs-stat-value">{{ stats.by_priority?.P3 || 0 }}</div>
        <div class="gs-stat-label">P3 低</div>
      </div>
    </div>

    <!-- 优先级矩阵 -->
    <PriorityMatrix v-if="testCases.length > 0" :test-cases="allTestCasesForMatrix" style="margin-bottom: 20px;" />

    <!-- 筛选栏 -->
    <div class="gs-filter-bar">
      <el-select v-model="filters.priority" placeholder="优先级" clearable size="default" @change="loadData">
        <el-option label="P0 紧急" value="P0" />
        <el-option label="P1 高优" value="P1" />
        <el-option label="P2 中" value="P2" />
        <el-option label="P3 低" value="P3" />
      </el-select>
      <el-select v-model="filters.module_id" placeholder="分析模块" clearable size="default" @change="loadData">
        <el-option v-for="m in moduleOptions" :key="m.id" :label="m.name" :value="m.id" />
      </el-select>
      <el-select v-model="filters.risk_type" placeholder="风险类型" clearable size="default" @change="loadData">
        <el-option v-for="rt in riskTypeOptions" :key="rt" :label="rt" :value="rt" />
      </el-select>
      <el-button @click="resetFilters" :icon="RefreshRight">重置</el-button>
      <div class="gs-filter-spacer"></div>
      <span class="gs-result-count">共 {{ total }} 条用例</span>
    </div>

    <!-- 测试用例卡片列表 -->
    <div class="gs-testcase-list" v-loading="loading">
      <div v-if="!loading && testCases.length === 0" class="gs-empty">
        <el-empty description="暂无测试用例" />
      </div>

      <div
        v-for="tc in testCases"
        :key="tc.test_case_id"
        class="gs-testcase-card"
        :class="{ expanded: expandedId === tc.test_case_id }"
        @click="toggleExpand(tc.test_case_id)"
      >
        <!-- 卡片头部 -->
        <div class="gs-tc-header">
          <div class="gs-tc-header-left">
            <span class="gs-tc-priority" :class="priorityClass(tc.priority)">
              {{ tc.priority.split('-')[0] }}
            </span>
            <span class="gs-tc-id">{{ tc.test_case_id }}</span>
            <span class="gs-tc-module-tag">{{ tc.module_display_name }}</span>
          </div>
          <div class="gs-tc-header-right">
            <span class="gs-tc-risk" :title="`风险分: ${tc.risk_score}`">
              <span class="gs-risk-dot" :style="{ background: riskColor(tc.risk_score) }"></span>
              {{ (tc.risk_score * 100).toFixed(0) }}%
            </span>
            <el-icon class="gs-tc-expand-icon" :class="{ rotated: expandedId === tc.test_case_id }"><ArrowDown /></el-icon>
          </div>
        </div>

        <!-- 用例标题和目标 -->
        <div class="gs-tc-title">{{ tc.title }}</div>
        <div class="gs-tc-objective">
          <el-icon><Aim /></el-icon>
          <span>{{ tc.objective }}</span>
        </div>

        <!-- 目标位置 -->
        <div class="gs-tc-location">
          <code>{{ tc.target_file }}</code>
          <span v-if="tc.target_function">→ <code>{{ tc.target_function }}()</code></span>
          <span v-if="tc.line_start" class="gs-tc-lines">L{{ tc.line_start }}–{{ tc.line_end }}</span>
        </div>

        <!-- 展开的详细内容 -->
        <div v-if="expandedId === tc.test_case_id" class="gs-tc-detail" @click.stop>
          <!-- 前置条件 -->
          <div class="gs-tc-section">
            <div class="gs-tc-section-title">
              <el-icon><List /></el-icon> 前置条件
            </div>
            <ul class="gs-tc-preconditions">
              <li v-for="(p, i) in tc.preconditions" :key="i">{{ p }}</li>
            </ul>
          </div>

          <!-- 测试步骤 -->
          <div class="gs-tc-section">
            <div class="gs-tc-section-title">
              <el-icon><Guide /></el-icon> 测试步骤
            </div>
            <ol class="gs-tc-steps">
              <li v-for="(s, i) in tc.test_steps" :key="i">{{ stripNumber(s) }}</li>
            </ol>
          </div>

          <!-- 预期结果 -->
          <div class="gs-tc-section">
            <div class="gs-tc-section-title">
              <el-icon><CircleCheck /></el-icon> 预期结果
            </div>
            <div class="gs-tc-expected">{{ tc.expected_result }}</div>
          </div>

          <!-- 关联证据 -->
          <div v-if="tc.evidence && Object.keys(tc.evidence).length" class="gs-tc-section">
            <div class="gs-tc-section-title">
              <el-icon><Document /></el-icon> 分析证据
            </div>
            <div class="gs-tc-evidence">
              <EvidenceRenderer :module-id="tc.module_id" :risk-type="tc.category" :evidence="tc.evidence" :finding="tc" />
            </div>
          </div>

          <!-- 操作按钮 -->
          <div class="gs-tc-actions">
            <span class="gs-tc-finding-link">
              来源发现: <code>{{ tc.source_finding_id }}</code>
            </span>
          </div>
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
import { ref, reactive, onMounted, markRaw } from 'vue'
import { Download, ArrowDown, Aim, List, Guide, CircleCheck, Document, RefreshRight } from '@element-plus/icons-vue'
import api from '../../api.js'
import { useModuleNames } from '../../composables/useModuleNames.js'
import { useRiskColor } from '../../composables/useRiskColor.js'
import EvidenceRenderer from '../../components/EvidenceRenderer.vue'
import PriorityMatrix from '../../components/PriorityMatrix.vue'

const props = defineProps({
  projectId: { type: [String, Number], required: true },
})

const { moduleList } = useModuleNames()
const { riskColor } = useRiskColor()

const loading = ref(false)
const testCases = ref([])
const allTestCasesForMatrix = ref([])
const total = ref(0)
const page = ref(1)
const pageSize = 30
const stats = ref(null)
const expandedId = ref(null)
const filters = reactive({ priority: '', module_id: '', risk_type: '' })

const moduleOptions = moduleList.map(m => ({ id: m.id, name: m.name }))
const riskTypeOptions = [
  'branch_missing_test', 'error_path', 'cleanup_path',
  'boundary_miss', 'invalid_input_gap',
  'missing_cleanup', 'inconsistent_errno_mapping', 'silent_error_swallow',
  'high_fan_out', 'deep_impact_surface',
  'race_write_without_lock', 'lock_order_inversion', 'atomicity_gap',
  'changed_core_path', 'transitive_impact',
  'high_risk_low_coverage', 'critical_path_uncovered',
]

function priorityClass(p) {
  const lvl = p.split('-')[0]
  return `priority-${lvl.toLowerCase()}`
}

function stripNumber(s) {
  return s.replace(/^\d+\.\s*/, '')
}

function toggleExpand(id) {
  expandedId.value = expandedId.value === id ? null : id
}

function setFilter(key, value) {
  filters[key] = filters[key] === value ? '' : value
  page.value = 1
  loadData()
}

function resetFilters() {
  filters.priority = ''
  filters.module_id = ''
  filters.risk_type = ''
  page.value = 1
  loadData()
}

async function loadData() {
  loading.value = true
  try {
    const params = { page: page.value, page_size: pageSize }
    if (filters.priority) params.priority = filters.priority
    if (filters.module_id) params.module_id = filters.module_id
    if (filters.risk_type) params.risk_type = filters.risk_type

    const data = await api.getProjectTestCases(props.projectId, params)
    testCases.value = data.test_cases || []
    total.value = data.total || 0
    if (data.stats) stats.value = data.stats

    // 加载全部用例用于优先级矩阵（仅首次）
    if (allTestCasesForMatrix.value.length === 0) {
      const allData = await api.getProjectTestCases(props.projectId, { page: 1, page_size: 200 })
      allTestCasesForMatrix.value = allData.test_cases || []
    }
  } catch (e) {
    console.error('加载测试用例失败:', e)
  } finally {
    loading.value = false
  }
}

function exportAll(fmt) {
  // 查找最新任务并导出
  window.open(api.exportUrl(`proj-${String(props.projectId).padStart(4, '0')}`, fmt), '_blank')
}

onMounted(loadData)
</script>

<style scoped>
/* ── 统计面板 ───────────────────────── */
.gs-stats-row {
  display: flex;
  gap: 12px;
  margin-bottom: 20px;
  flex-wrap: wrap;
}
.gs-stat-card {
  flex: 1;
  min-width: 120px;
  background: var(--gs-surface);
  border: 1px solid var(--gs-border);
  border-radius: var(--gs-radius-md);
  padding: 16px;
  text-align: center;
  cursor: pointer;
  transition: all var(--gs-transition);
}
.gs-stat-card:hover { border-color: var(--gs-primary); }
.gs-stat-value { font-size: 28px; font-weight: 700; color: var(--gs-text-primary); }
.gs-stat-label { font-size: 12px; color: var(--gs-text-muted); margin-top: 4px; }
.gs-stat-p0 .gs-stat-value { color: var(--gs-risk-critical); }
.gs-stat-p1 .gs-stat-value { color: var(--gs-risk-high); }
.gs-stat-p2 .gs-stat-value { color: var(--gs-risk-medium); }
.gs-stat-p3 .gs-stat-value { color: var(--gs-risk-low); }

/* ── 筛选栏 ─────────────────────────── */
.gs-filter-bar {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 16px;
  flex-wrap: wrap;
}
.gs-filter-spacer { flex: 1; }
.gs-result-count {
  font-size: 13px;
  color: var(--gs-text-muted);
  white-space: nowrap;
}

/* ── 用例卡片 ─────────────────────────── */
.gs-testcase-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  min-height: 200px;
}

.gs-testcase-card {
  background: var(--gs-surface);
  border: 1px solid var(--gs-border);
  border-radius: var(--gs-radius-md);
  padding: 16px 20px;
  cursor: pointer;
  transition: all var(--gs-transition);
}
.gs-testcase-card:hover {
  border-color: var(--gs-primary);
  box-shadow: var(--gs-shadow-sm);
}
.gs-testcase-card.expanded {
  border-color: var(--gs-primary);
  box-shadow: var(--gs-shadow-md);
}

/* 卡片头部 */
.gs-tc-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}
.gs-tc-header-left {
  display: flex;
  align-items: center;
  gap: 8px;
}
.gs-tc-header-right {
  display: flex;
  align-items: center;
  gap: 10px;
}

.gs-tc-priority {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 28px;
  height: 22px;
  padding: 0 6px;
  border-radius: 4px;
  font-size: 11px;
  font-weight: 700;
  color: #fff;
}
.gs-tc-priority.priority-p0 { background: var(--gs-risk-critical); }
.gs-tc-priority.priority-p1 { background: var(--gs-risk-high); }
.gs-tc-priority.priority-p2 { background: var(--gs-risk-medium); }
.gs-tc-priority.priority-p3 { background: var(--gs-risk-low); }

.gs-tc-id {
  font-size: 12px;
  font-family: var(--gs-font-mono);
  color: var(--gs-text-muted);
}

.gs-tc-module-tag {
  font-size: 11px;
  padding: 2px 8px;
  background: rgba(75, 159, 213, 0.1);
  color: var(--gs-primary);
  border-radius: 10px;
}

.gs-tc-risk {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
  color: var(--gs-text-secondary);
  font-family: var(--gs-font-mono);
}
.gs-risk-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
}

.gs-tc-expand-icon {
  transition: transform 0.2s;
  color: var(--gs-text-muted);
}
.gs-tc-expand-icon.rotated { transform: rotate(180deg); }

/* 用例标题 / 目标 */
.gs-tc-title {
  font-size: 15px;
  font-weight: 600;
  color: var(--gs-text-primary);
  margin-bottom: 6px;
  line-height: 1.4;
}

.gs-tc-objective {
  display: flex;
  align-items: flex-start;
  gap: 6px;
  font-size: 13px;
  color: var(--gs-text-secondary);
  line-height: 1.5;
  margin-bottom: 6px;
}
.gs-tc-objective .el-icon {
  margin-top: 2px;
  color: var(--gs-primary);
  flex-shrink: 0;
}

.gs-tc-location {
  font-size: 12px;
  color: var(--gs-text-muted);
}
.gs-tc-location code {
  background: rgba(75, 159, 213, 0.08);
  padding: 1px 5px;
  border-radius: 3px;
  font-size: 11px;
}
.gs-tc-lines {
  margin-left: 6px;
  color: var(--gs-text-muted);
}

/* ── 展开详情 ───────────────────────── */
.gs-tc-detail {
  margin-top: 16px;
  padding-top: 16px;
  border-top: 1px solid var(--gs-border);
  cursor: default;
}

.gs-tc-section {
  margin-bottom: 16px;
}
.gs-tc-section-title {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  font-weight: 600;
  color: var(--gs-text-primary);
  margin-bottom: 8px;
}
.gs-tc-section-title .el-icon { color: var(--gs-primary); }

.gs-tc-preconditions,
.gs-tc-steps {
  margin: 0;
  padding-left: 20px;
  font-size: 13px;
  color: var(--gs-text-secondary);
  line-height: 1.8;
}
.gs-tc-steps li {
  padding: 2px 0;
}
.gs-tc-steps li::marker {
  color: var(--gs-primary);
  font-weight: 600;
}

.gs-tc-expected {
  font-size: 13px;
  color: var(--gs-success);
  font-weight: 500;
  padding: 10px 14px;
  background: rgba(0, 170, 0, 0.06);
  border-radius: var(--gs-radius-sm);
  border-left: 3px solid var(--gs-success);
}

.gs-tc-evidence {
  background: var(--gs-bg);
  border-radius: var(--gs-radius-sm);
  padding: 12px;
}

.gs-tc-actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-top: 12px;
  padding-top: 12px;
  border-top: 1px dashed var(--gs-border);
}
.gs-tc-finding-link {
  font-size: 12px;
  color: var(--gs-text-muted);
}
.gs-tc-finding-link code {
  font-size: 11px;
  color: var(--gs-primary);
}

/* ── 分页 ───────────────────────────── */
.gs-pagination {
  display: flex;
  justify-content: center;
  margin-top: 20px;
  padding-bottom: 20px;
}

/* ── 空状态 ─────────────────────────── */
.gs-empty {
  padding: 60px 0;
  text-align: center;
}

/* ── 响应式 ─────────────────────────── */
.gs-header-actions {
  flex-shrink: 0;
}
.gs-page-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
}
</style>
