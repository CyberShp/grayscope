<template>
  <div class="gs-issues-layout">
    <!-- 左侧 Facets 面板 -->
    <aside class="gs-facets">
      <div class="gs-facet-group">
        <div class="gs-facet-title">严重程度</div>
        <div
          v-for="sev in severityFacets"
          :key="sev.value"
          class="gs-facet-item"
          :class="{ active: filters.severity === sev.value }"
          @click="toggleFilter('severity', sev.value)"
        >
          <div style="display: flex; align-items: center; gap: 6px;">
            <span class="gs-severity-tag" :class="'gs-severity-' + sev.value.toLowerCase()">{{ sev.value }}</span>
            <span>{{ sev.label }}</span>
          </div>
          <span class="gs-facet-count">{{ sev.count }}</span>
        </div>
      </div>

      <div class="gs-facet-group">
        <div class="gs-facet-title">分析模块</div>
        <div
          v-for="mod in moduleFacets"
          :key="mod.value"
          class="gs-facet-item"
          :class="{ active: filters.module === mod.value }"
          @click="toggleFilter('module', mod.value)"
        >
          <span>{{ mod.label }}</span>
          <span class="gs-facet-count">{{ mod.count }}</span>
        </div>
      </div>

      <div class="gs-facet-group">
        <div class="gs-facet-title">风险类型</div>
        <div
          v-for="rt in riskTypeFacets"
          :key="rt.value"
          class="gs-facet-item"
          :class="{ active: filters.riskType === rt.value }"
          @click="toggleFilter('riskType', rt.value)"
        >
          <span style="font-size: 12px;">{{ rt.value }}</span>
          <span class="gs-facet-count">{{ rt.count }}</span>
        </div>
      </div>

      <div class="gs-facet-group">
        <div class="gs-facet-title">文件</div>
        <div
          v-for="f in fileFacets"
          :key="f.value"
          class="gs-facet-item"
          :class="{ active: filters.filePath === f.value }"
          @click="toggleFilter('filePath', f.value)"
        >
          <span style="font-size: 12px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 170px;" :title="f.value">{{ f.label }}</span>
          <span class="gs-facet-count">{{ f.count }}</span>
        </div>
      </div>
    </aside>

    <!-- 中间发现列表 -->
    <div class="gs-issues-main">
      <div class="gs-issues-toolbar">
        <span class="gs-issues-count">{{ filteredFindings.length }} 条发现</span>
        <el-select v-model="sortBy" size="small" style="width: 140px;">
          <el-option label="风险评分 ↓" value="risk_score" />
          <el-option label="严重程度 ↓" value="severity" />
        </el-select>
      </div>

      <div class="gs-issues-list">
        <div
          v-for="f in paginatedFindings"
          :key="f.finding_id"
          class="gs-issue-item"
          :class="{ selected: selectedFinding?.finding_id === f.finding_id }"
          @click="selectFinding(f)"
        >
          <div class="gs-issue-item-left">
            <span class="gs-severity-tag" :class="'gs-severity-' + (f.severity || 's3').toLowerCase()">{{ f.severity }}</span>
          </div>
          <div class="gs-issue-item-body">
            <div class="gs-issue-title">{{ f.title }}</div>
            <div class="gs-issue-meta">
              <span class="gs-issue-module">{{ getDisplayName(f.module_id) }}</span>
              <span class="gs-issue-file" :title="f.file_path">{{ shortenPath(f.file_path) }}</span>
              <span v-if="f.line_start" class="gs-issue-line">L{{ f.line_start }}</span>
            </div>
          </div>
          <div class="gs-issue-item-right">
            <span class="gs-issue-score" :style="{ color: riskColor(f.risk_score || 0) }">
              {{ f.risk_score != null ? (f.risk_score * 100).toFixed(0) + '%' : '' }}
            </span>
          </div>
        </div>
      </div>

      <el-pagination
        v-if="filteredFindings.length > pageSize"
        v-model:current-page="page"
        :page-size="pageSize"
        :total="filteredFindings.length"
        layout="prev, pager, next"
        size="small"
        style="margin-top: 16px; justify-content: center;"
      />

      <el-empty v-if="!loading && !filteredFindings.length" description="暂无发现" :image-size="60" />
    </div>

    <!-- 右侧详情面板 -->
    <aside v-if="selectedFinding" class="gs-issue-detail">
      <div class="gs-issue-detail-header">
        <span class="gs-severity-tag" :class="'gs-severity-' + (selectedFinding.severity || 's3').toLowerCase()">{{ selectedFinding.severity }}</span>
        <span style="font-weight: 600;">{{ selectedFinding.title }}</span>
        <el-button text size="small" @click="selectedFinding = null" style="margin-left: auto;">
          <el-icon><Close /></el-icon>
        </el-button>
      </div>

      <div class="gs-issue-detail-body">
        <div class="gs-detail-section">
          <div class="gs-detail-label">描述</div>
          <div class="gs-detail-value">{{ selectedFinding.description }}</div>
        </div>

        <div class="gs-detail-section">
          <div class="gs-detail-label">位置</div>
          <div class="gs-detail-value">
            <code>{{ selectedFinding.file_path }}</code>
            <span v-if="selectedFinding.symbol_name"> &rarr; <code>{{ selectedFinding.symbol_name }}()</code></span>
            <span v-if="selectedFinding.line_start"> (行 {{ selectedFinding.line_start }}-{{ selectedFinding.line_end }})</span>
          </div>
        </div>

        <div class="gs-detail-section">
          <div class="gs-detail-label">风险信息</div>
          <div class="gs-detail-tags">
            <span class="gs-tag">{{ selectedFinding.risk_type }}</span>
            <span class="gs-tag">{{ getDisplayName(selectedFinding.module_id) }}</span>
            <span class="gs-tag" :style="{ color: riskColor(selectedFinding.risk_score || 0) }">
              评分: {{ ((selectedFinding.risk_score || 0) * 100).toFixed(0) }}%
            </span>
          </div>
        </div>

        <!-- 推荐测试设计（内联） -->
        <div class="gs-detail-section gs-test-suggestion-section">
          <div class="gs-detail-label">
            <el-icon style="margin-right:4px"><EditPen /></el-icon>推荐测试设计
          </div>
          <div class="gs-test-suggestion-card">
            <div class="gs-ts-objective">
              <strong>测试目标: </strong>{{ getTestObjective(selectedFinding) }}
            </div>
            <div class="gs-ts-steps">
              <strong>测试步骤: </strong>
              <ol>
                <li v-for="(s, i) in getTestSteps(selectedFinding)" :key="i">{{ s.replace(/^\d+\.\s*/, '') }}</li>
              </ol>
            </div>
            <div class="gs-ts-expected">
              <strong>预期结果: </strong>{{ getTestExpected(selectedFinding) }}
            </div>
          </div>
        </div>

        <!-- 结构化证据 -->
        <div v-if="selectedFinding.evidence && Object.keys(selectedFinding.evidence).length" class="gs-detail-section">
          <div class="gs-detail-label">分析证据</div>
          <EvidenceRenderer
            :module-id="selectedFinding.module_id"
            :risk-type="selectedFinding.risk_type"
            :evidence="selectedFinding.evidence"
            :finding="selectedFinding"
          />
        </div>
      </div>
    </aside>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import { useRiskColor } from '../../composables/useRiskColor.js'
import { useModuleNames } from '../../composables/useModuleNames.js'
import { useTestSuggestion } from '../../composables/useTestSuggestion.js'
import EvidenceRenderer from '../../components/EvidenceRenderer.vue'
import api from '../../api.js'

const props = defineProps({
  projectId: [String, Number],
})

const { riskColor } = useRiskColor()
const { getDisplayName } = useModuleNames()
const { getTestObjective, getTestSteps, getTestExpected } = useTestSuggestion()

const loading = ref(false)
const allFindings = ref([])
const selectedFinding = ref(null)
const page = ref(1)
const pageSize = 30
const sortBy = ref('risk_score')

const filters = ref({
  severity: null,
  module: null,
  riskType: null,
  filePath: null,
})

function toggleFilter(key, value) {
  filters.value[key] = filters.value[key] === value ? null : value
  page.value = 1
}

// Facets 计算
function buildFacets(items, key) {
  const map = {}
  items.forEach(f => {
    const v = f[key]
    if (v) map[v] = (map[v] || 0) + 1
  })
  return Object.entries(map).sort((a, b) => b[1] - a[1]).map(([value, count]) => ({ value, count }))
}

const severityFacets = computed(() =>
  buildFacets(allFindings.value, 'severity').map(f => ({ ...f, label: { S0: '紧急', S1: '高危', S2: '中危', S3: '低危' }[f.value] || f.value }))
)
const moduleFacets = computed(() =>
  buildFacets(allFindings.value, 'module_id').map(f => ({ ...f, label: getDisplayName(f.value) }))
)
const riskTypeFacets = computed(() => buildFacets(allFindings.value, 'risk_type'))
const fileFacets = computed(() =>
  buildFacets(allFindings.value, 'file_path').slice(0, 10).map(f => ({ ...f, label: f.value.split('/').pop() }))
)

const filteredFindings = computed(() => {
  let list = [...allFindings.value]
  if (filters.value.severity) list = list.filter(f => f.severity === filters.value.severity)
  if (filters.value.module) list = list.filter(f => f.module_id === filters.value.module)
  if (filters.value.riskType) list = list.filter(f => f.risk_type === filters.value.riskType)
  if (filters.value.filePath) list = list.filter(f => f.file_path === filters.value.filePath)

  const sevOrder = { S0: 0, S1: 1, S2: 2, S3: 3 }
  if (sortBy.value === 'severity') {
    list.sort((a, b) => (sevOrder[a.severity] ?? 9) - (sevOrder[b.severity] ?? 9))
  } else {
    list.sort((a, b) => (b.risk_score || 0) - (a.risk_score || 0))
  }
  return list
})

const paginatedFindings = computed(() => {
  const start = (page.value - 1) * pageSize
  return filteredFindings.value.slice(start, start + pageSize)
})

function selectFinding(f) {
  selectedFinding.value = selectedFinding.value?.finding_id === f.finding_id ? null : f
}

function shortenPath(p) {
  if (!p) return ''
  const parts = p.split('/')
  return parts.length > 2 ? '.../' + parts.slice(-2).join('/') : p
}

async function loadFindings() {
  loading.value = true
  try {
    const data = await api.getProjectFindings(props.projectId)
    allFindings.value = data?.findings || data || []
  } catch {
    allFindings.value = []
  } finally {
    loading.value = false
  }
}

onMounted(loadFindings)
watch(() => props.projectId, loadFindings)
</script>

<style scoped>
.gs-issues-layout {
  display: flex;
  height: 100%;
}

/* ── 发现列表主区域 ─────────────────── */
.gs-issues-main {
  flex: 1;
  padding: var(--gs-space-md) var(--gs-space-lg);
  overflow-y: auto;
  min-width: 0;
}

.gs-issues-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: var(--gs-space-md);
}
.gs-issues-count {
  font-size: var(--gs-font-sm);
  color: var(--gs-text-secondary);
  font-weight: 600;
}

.gs-issues-list {
  display: flex;
  flex-direction: column;
}

.gs-issue-item {
  display: flex;
  align-items: flex-start;
  gap: var(--gs-space-sm);
  padding: var(--gs-space-sm) var(--gs-space-md);
  border-bottom: 1px solid var(--gs-border-light);
  cursor: pointer;
  transition: background var(--gs-transition);
}
.gs-issue-item:hover { background: var(--gs-surface-alt); }
.gs-issue-item.selected { background: #E8F4FD; border-left: 3px solid var(--gs-primary); }

.gs-issue-item-left { padding-top: 2px; }
.gs-issue-item-body { flex: 1; min-width: 0; }
.gs-issue-item-right { flex-shrink: 0; padding-top: 2px; }

.gs-issue-title {
  font-size: var(--gs-font-base);
  font-weight: 500;
  color: var(--gs-text-primary);
  margin-bottom: 4px;
}

.gs-issue-meta {
  display: flex;
  gap: var(--gs-space-md);
  font-size: var(--gs-font-xs);
  color: var(--gs-text-muted);
}
.gs-issue-module { color: var(--gs-primary-dark); }
.gs-issue-file { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 200px; }

.gs-issue-score { font-size: var(--gs-font-sm); font-weight: 700; }

/* ── 详情面板 ─────────────────────────── */
.gs-issue-detail {
  width: 380px;
  flex-shrink: 0;
  border-left: 1px solid var(--gs-border);
  background: var(--gs-surface);
  overflow-y: auto;
}

.gs-issue-detail-header {
  display: flex;
  align-items: center;
  gap: var(--gs-space-sm);
  padding: var(--gs-space-md);
  border-bottom: 1px solid var(--gs-border-light);
}

.gs-issue-detail-body {
  padding: var(--gs-space-md);
}

.gs-detail-section {
  margin-bottom: var(--gs-space-lg);
}
.gs-detail-label {
  font-size: var(--gs-font-xs);
  font-weight: 600;
  color: var(--gs-text-secondary);
  text-transform: uppercase;
  letter-spacing: 0.3px;
  margin-bottom: var(--gs-space-xs);
}
.gs-detail-value {
  font-size: var(--gs-font-base);
  color: var(--gs-text-primary);
  line-height: 1.5;
}
.gs-detail-value code {
  background: #F5F5F5;
  padding: 2px 4px;
  border-radius: 3px;
  font-family: var(--gs-font-mono);
  font-size: var(--gs-font-sm);
}

.gs-detail-tags {
  display: flex;
  flex-wrap: wrap;
  gap: var(--gs-space-xs);
}
.gs-tag {
  padding: 2px 8px;
  background: #F0F0F0;
  border-radius: 3px;
  font-size: var(--gs-font-xs);
}

.gs-code-block {
  background: #1E1E1E;
  color: #D4D4D4;
  padding: var(--gs-space-md);
  border-radius: var(--gs-radius-md);
  font-family: var(--gs-font-mono);
  font-size: var(--gs-font-sm);
  overflow-x: auto;
  white-space: pre-wrap;
  word-break: break-all;
  max-height: 300px;
  overflow-y: auto;
}

/* ── 测试建议卡片 ───────────────────── */
.gs-test-suggestion-section .gs-detail-label {
  display: flex;
  align-items: center;
  color: var(--gs-primary);
}
.gs-test-suggestion-card {
  background: rgba(75, 159, 213, 0.04);
  border: 1px solid rgba(75, 159, 213, 0.15);
  border-radius: var(--gs-radius-md);
  padding: var(--gs-space-md);
  font-size: var(--gs-font-sm);
  color: var(--gs-text-primary);
  line-height: 1.6;
}
.gs-ts-objective { margin-bottom: 8px; }
.gs-ts-steps ol {
  margin: 4px 0 8px 0;
  padding-left: 18px;
  color: var(--gs-text-secondary);
}
.gs-ts-steps ol li { padding: 2px 0; }
.gs-ts-steps ol li::marker { color: var(--gs-primary); font-weight: 600; }
.gs-ts-expected {
  color: var(--gs-success);
  font-weight: 500;
}
</style>
