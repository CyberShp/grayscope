<template>
  <div class="gs-risk-findings">
    <div class="gs-rf-summary">
      <el-statistic title="总风险数" :value="summary.total_findings || 0" />
      <el-statistic title="严重" :value="summary.severity_distribution?.critical || 0" value-style="color: #D50000" />
      <el-statistic title="高" :value="summary.severity_distribution?.high || 0" value-style="color: #E57F00" />
      <el-statistic title="中" :value="summary.severity_distribution?.medium || 0" value-style="color: #FFC107" />
      <el-statistic title="低" :value="summary.severity_distribution?.low || 0" />
    </div>

    <el-divider />

    <div class="gs-rf-filters">
      <el-select v-model="filterSeverity" placeholder="严重程度" clearable size="small" style="width:120px">
        <el-option value="critical" label="严重" />
        <el-option value="high" label="高" />
        <el-option value="medium" label="中" />
        <el-option value="low" label="低" />
      </el-select>
      <el-select v-model="filterType" placeholder="风险类型" clearable size="small" style="width:160px">
        <el-option v-for="t in riskTypes" :key="t" :value="t" :label="t" />
      </el-select>
      <el-input v-model="searchKeyword" placeholder="搜索..." clearable size="small" style="width:180px" />
    </div>

    <el-table :data="filteredFindings" stripe style="width:100%" max-height="500">
      <el-table-column prop="finding_id" label="ID" width="100" />
      <el-table-column prop="risk_type" label="类型" width="140">
        <template #default="{ row }">
          <el-tag size="small" :type="riskTypeTag(row.risk_type)">{{ row.risk_type }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="severity" label="严重程度" width="100">
        <template #default="{ row }">
          <el-tag :type="severityTag(row.severity)" size="small">{{ row.severity }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="description" label="描述" min-width="250" show-overflow-tooltip />
      <el-table-column prop="call_chain" label="调用链" min-width="200">
        <template #default="{ row }">
          <span class="gs-chain">{{ (row.call_chain || []).slice(0, 3).join(' → ') }}{{ row.call_chain?.length > 3 ? '...' : '' }}</span>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="80" fixed="right">
        <template #default="{ row }">
          <el-button link type="primary" @click="showDetail(row)">详情</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog v-model="dialogVisible" :title="'风险详情: ' + (selectedFinding?.finding_id || '')" width="700px">
      <el-descriptions :column="2" border v-if="selectedFinding">
        <el-descriptions-item label="类型">{{ selectedFinding.risk_type }}</el-descriptions-item>
        <el-descriptions-item label="严重程度">
          <el-tag :type="severityTag(selectedFinding.severity)">{{ selectedFinding.severity }}</el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="风险评分">{{ selectedFinding.risk_score }}</el-descriptions-item>
        <el-descriptions-item label="分支上下文">{{ selectedFinding.branch_context || '-' }}</el-descriptions-item>
        <el-descriptions-item label="描述" :span="2">{{ selectedFinding.description }}</el-descriptions-item>
        <el-descriptions-item label="调用链" :span="2">
          <div class="gs-chain-full">{{ (selectedFinding.call_chain || []).join(' → ') }}</div>
        </el-descriptions-item>
        <el-descriptions-item label="预期结果" :span="2">{{ selectedFinding.expected_outcome }}</el-descriptions-item>
        <el-descriptions-item label="不可接受结果" :span="2">
          <ul class="gs-list">
            <li v-for="(item, i) in selectedFinding.unacceptable_outcomes" :key="i">{{ item }}</li>
          </ul>
        </el-descriptions-item>
        <el-descriptions-item label="测试建议" :span="2">{{ selectedFinding.test_suggestion }}</el-descriptions-item>
        <el-descriptions-item label="代码证据" :span="2">
          <pre class="gs-code">{{ selectedFinding.code_evidence }}</pre>
        </el-descriptions-item>
      </el-descriptions>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'

const props = defineProps({
  findings: { type: Array, default: () => [] },
  summary: { type: Object, default: () => ({}) },
})

const filterSeverity = ref('')
const filterType = ref('')
const searchKeyword = ref('')
const dialogVisible = ref(false)
const selectedFinding = ref(null)

const riskTypes = computed(() => {
  const types = new Set((props.findings || []).map(f => f.risk_type))
  return Array.from(types).sort()
})

const filteredFindings = computed(() => {
  let list = props.findings || []
  if (filterSeverity.value) {
    list = list.filter(f => f.severity === filterSeverity.value)
  }
  if (filterType.value) {
    list = list.filter(f => f.risk_type === filterType.value)
  }
  if (searchKeyword.value) {
    const kw = searchKeyword.value.toLowerCase()
    list = list.filter(f => 
      f.description?.toLowerCase().includes(kw) ||
      f.finding_id?.toLowerCase().includes(kw) ||
      f.call_chain?.some(c => c.toLowerCase().includes(kw))
    )
  }
  return list
})

function severityTag(severity) {
  const map = { critical: 'danger', high: 'warning', medium: '', low: 'info' }
  return map[severity] || 'info'
}

function riskTypeTag(type) {
  if (type?.includes('deadlock') || type?.includes('race')) return 'danger'
  if (type?.includes('leak') || type?.includes('resource')) return 'warning'
  if (type?.includes('protocol')) return 'primary'
  return ''
}

function showDetail(finding) {
  selectedFinding.value = finding
  dialogVisible.value = true
}
</script>

<style scoped>
.gs-rf-summary {
  display: flex;
  gap: 32px;
  flex-wrap: wrap;
}
.gs-rf-filters {
  display: flex;
  gap: 12px;
  margin-bottom: 16px;
  flex-wrap: wrap;
}
.gs-chain {
  font-family: monospace;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.gs-chain-full {
  font-family: monospace;
  font-size: 13px;
  word-break: break-all;
}
.gs-list {
  margin: 0;
  padding-left: 20px;
}
.gs-code {
  background: #f5f5f5;
  padding: 8px;
  border-radius: 4px;
  font-size: 12px;
  overflow-x: auto;
  max-height: 200px;
}
</style>
