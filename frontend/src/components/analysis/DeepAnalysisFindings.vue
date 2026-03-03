<template>
  <div class="gs-deep-findings">
    <!-- 概览统计 -->
    <div class="gs-df-summary">
      <el-statistic title="深度发现总数" :value="totalFindings" />
      <el-statistic title="资源泄漏" :value="countByType('resource_leak')" value-style="color: #D50000" />
      <el-statistic title="回调约束" :value="countByType('callback_constraint')" value-style="color: #E57F00" />
      <el-statistic title="所有权错误" :value="countByType('ownership_error')" value-style="color: #FFC107" />
      <el-statistic title="初始化不对称" :value="countByType('init_exit_asymmetry')" value-style="color: #409EFF" />
    </div>

    <el-divider />

    <!-- 语义索引概览 -->
    <div v-if="semanticIndex && Object.keys(semanticIndex).length" class="gs-semantic-overview">
      <el-collapse>
        <el-collapse-item title="语义索引概览" name="semantic">
          <div class="gs-semantic-stats">
            <div class="gs-semantic-stat">
              <span class="gs-stat-label">配对操作</span>
              <el-tag type="success" size="small">{{ semanticIndex.paired_operations?.length || 0 }}</el-tag>
            </div>
            <div class="gs-semantic-stat">
              <span class="gs-stat-label">未配对资源</span>
              <el-tag type="danger" size="small">{{ semanticIndex.unpaired_resources?.length || 0 }}</el-tag>
            </div>
            <div class="gs-semantic-stat">
              <span class="gs-stat-label">回调上下文</span>
              <el-tag type="warning" size="small">{{ semanticIndex.callback_contexts?.length || 0 }}</el-tag>
            </div>
            <div class="gs-semantic-stat">
              <span class="gs-stat-label">所有权转移</span>
              <el-tag type="info" size="small">{{ semanticIndex.ownership_transfers?.length || 0 }}</el-tag>
            </div>
            <div class="gs-semantic-stat">
              <span class="gs-stat-label">初始化/退出配对</span>
              <el-tag type="primary" size="small">{{ semanticIndex.init_exit_pairs?.length || 0 }}</el-tag>
            </div>
          </div>
        </el-collapse-item>
      </el-collapse>
    </div>

    <!-- 筛选器 -->
    <div class="gs-df-filters">
      <el-select v-model="filterSeverity" placeholder="严重程度" clearable size="small" style="width:120px">
        <el-option value="critical" label="严重" />
        <el-option value="high" label="高" />
        <el-option value="medium" label="中" />
        <el-option value="low" label="低" />
      </el-select>
      <el-select v-model="filterType" placeholder="发现类型" clearable size="small" style="width:160px">
        <el-option value="resource_leak" label="资源泄漏" />
        <el-option value="callback_constraint" label="回调约束违反" />
        <el-option value="ownership_error" label="所有权错误" />
        <el-option value="init_exit_asymmetry" label="初始化/退出不对称" />
        <el-option value="concurrency" label="并发问题" />
      </el-select>
      <el-select v-model="filterConfidence" placeholder="置信度" clearable size="small" style="width:120px">
        <el-option value="high" label="高置信度" />
        <el-option value="medium" label="中置信度" />
        <el-option value="low" label="低置信度" />
      </el-select>
      <el-input v-model="searchKeyword" placeholder="搜索函数/文件..." clearable size="small" style="width:200px" />
    </div>

    <!-- 无数据提示 -->
    <el-empty v-if="!filteredFindings.length" description="暂无深度分析发现">
      <template #description>
        <p>深度分析未发现问题，或尚未执行深度分析</p>
      </template>
    </el-empty>

    <!-- 发现卡片列表 -->
    <div class="gs-df-list">
      <el-card 
        v-for="finding in filteredFindings" 
        :key="finding.id || finding.title"
        class="gs-df-card"
        :class="'gs-df-' + finding.severity"
        shadow="hover"
      >
        <template #header>
          <div class="gs-df-card-header">
            <div class="gs-df-card-title">
              <el-tag :type="severityTag(finding.severity)" size="small" effect="dark">
                {{ severityLabel(finding.severity) }}
              </el-tag>
              <el-tag :type="typeTag(finding.finding_type)" size="small">
                {{ typeLabel(finding.finding_type) }}
              </el-tag>
              <span class="gs-df-title-text">{{ finding.title }}</span>
            </div>
            <div class="gs-df-card-meta">
              <span class="gs-df-confidence" :class="'gs-conf-' + finding.confidence">
                置信度: {{ confidenceLabel(finding.confidence) }}
              </span>
              <el-button link type="primary" @click="showDetail(finding)">
                查看证据链
              </el-button>
            </div>
          </div>
        </template>

        <div class="gs-df-card-body">
          <p class="gs-df-desc">{{ finding.description }}</p>
          
          <!-- 位置信息 -->
          <div class="gs-df-location">
            <el-icon><Location /></el-icon>
            <span class="gs-df-file">{{ finding.file_path }}</span>
            <span class="gs-df-func">{{ finding.function_name }}</span>
            <span class="gs-df-line">L{{ finding.line }}</span>
          </div>

          <!-- 执行路径预览 -->
          <div v-if="finding.execution_path?.length" class="gs-df-path-preview">
            <span class="gs-df-path-label">执行路径:</span>
            <span class="gs-df-path-chain">
              {{ finding.execution_path.slice(0, 4).join(' → ') }}
              {{ finding.execution_path.length > 4 ? '...' : '' }}
            </span>
          </div>

          <!-- 修复建议预览 -->
          <div v-if="finding.fix_suggestion" class="gs-df-fix-preview">
            <el-icon><Opportunity /></el-icon>
            <span>{{ truncate(finding.fix_suggestion, 100) }}</span>
          </div>
        </div>
      </el-card>
    </div>

    <!-- 详情对话框 -->
    <el-dialog 
      v-model="dialogVisible" 
      :title="'深度分析详情: ' + (selectedFinding?.title || '')" 
      width="800px"
      class="gs-df-dialog"
    >
      <div v-if="selectedFinding" class="gs-df-detail">
        <!-- 基本信息 -->
        <el-descriptions :column="2" border>
          <el-descriptions-item label="类型">
            <el-tag :type="typeTag(selectedFinding.finding_type)">
              {{ typeLabel(selectedFinding.finding_type) }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="严重程度">
            <el-tag :type="severityTag(selectedFinding.severity)" effect="dark">
              {{ severityLabel(selectedFinding.severity) }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="置信度">
            <span :class="'gs-conf-' + selectedFinding.confidence">
              {{ confidenceLabel(selectedFinding.confidence) }}
            </span>
          </el-descriptions-item>
          <el-descriptions-item label="来源">深度AI分析</el-descriptions-item>
          <el-descriptions-item label="文件" :span="2">
            <code>{{ selectedFinding.file_path }}</code>
          </el-descriptions-item>
          <el-descriptions-item label="函数">
            <code>{{ selectedFinding.function_name }}</code>
          </el-descriptions-item>
          <el-descriptions-item label="行号">{{ selectedFinding.line }}</el-descriptions-item>
        </el-descriptions>

        <el-divider content-position="left">问题描述</el-divider>
        <p class="gs-df-desc-full">{{ selectedFinding.description }}</p>

        <!-- 执行路径（证据链） -->
        <el-divider content-position="left">执行路径 / 证据链</el-divider>
        <div v-if="selectedFinding.execution_path?.length" class="gs-df-execution-path">
          <el-timeline>
            <el-timeline-item 
              v-for="(step, idx) in selectedFinding.execution_path" 
              :key="idx"
              :type="idx === 0 ? 'primary' : (idx === selectedFinding.execution_path.length - 1 ? 'danger' : '')"
              :hollow="idx !== 0 && idx !== selectedFinding.execution_path.length - 1"
            >
              <div class="gs-path-step">
                <span class="gs-path-idx">{{ idx + 1 }}</span>
                <code class="gs-path-func">{{ step }}</code>
              </div>
            </el-timeline-item>
          </el-timeline>
        </div>
        <el-empty v-else description="无执行路径信息" :image-size="60" />

        <!-- 代码证据 -->
        <el-divider content-position="left">代码证据</el-divider>
        <div v-if="selectedFinding.evidence" class="gs-df-evidence">
          <pre class="gs-df-code">{{ selectedFinding.evidence }}</pre>
        </div>
        <el-empty v-else description="无代码证据" :image-size="60" />

        <!-- 修复建议 -->
        <el-divider content-position="left">修复建议</el-divider>
        <div v-if="selectedFinding.fix_suggestion" class="gs-df-fix">
          <el-alert type="success" :closable="false" show-icon>
            <template #title>
              <span>{{ selectedFinding.fix_suggestion }}</span>
            </template>
          </el-alert>
        </div>
        <el-empty v-else description="无修复建议" :image-size="60" />
      </div>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import { Location, Opportunity } from '@element-plus/icons-vue'

const props = defineProps({
  findings: { type: Array, default: () => [] },
  semanticIndex: { type: Object, default: () => ({}) },
})

const filterSeverity = ref('')
const filterType = ref('')
const filterConfidence = ref('')
const searchKeyword = ref('')
const dialogVisible = ref(false)
const selectedFinding = ref(null)

const totalFindings = computed(() => props.findings?.length || 0)

function countByType(type) {
  return (props.findings || []).filter(f => f.finding_type === type).length
}

const filteredFindings = computed(() => {
  let list = props.findings || []
  
  if (filterSeverity.value) {
    list = list.filter(f => f.severity === filterSeverity.value)
  }
  if (filterType.value) {
    list = list.filter(f => f.finding_type === filterType.value)
  }
  if (filterConfidence.value) {
    list = list.filter(f => f.confidence === filterConfidence.value)
  }
  if (searchKeyword.value) {
    const kw = searchKeyword.value.toLowerCase()
    list = list.filter(f => 
      f.function_name?.toLowerCase().includes(kw) ||
      f.file_path?.toLowerCase().includes(kw) ||
      f.title?.toLowerCase().includes(kw) ||
      f.description?.toLowerCase().includes(kw)
    )
  }
  
  // Sort by severity (critical first)
  const severityOrder = { critical: 0, high: 1, medium: 2, low: 3 }
  return [...list].sort((a, b) => 
    (severityOrder[a.severity] ?? 4) - (severityOrder[b.severity] ?? 4)
  )
})

function severityTag(severity) {
  const map = { critical: 'danger', high: 'warning', medium: '', low: 'info' }
  return map[severity] || 'info'
}

function severityLabel(severity) {
  const map = { critical: '严重', high: '高', medium: '中', low: '低' }
  return map[severity] || severity
}

function typeTag(type) {
  const map = {
    resource_leak: 'danger',
    callback_constraint: 'warning',
    ownership_error: '',
    init_exit_asymmetry: 'info',
    concurrency: 'danger',
  }
  return map[type] || ''
}

function typeLabel(type) {
  const map = {
    resource_leak: '资源泄漏',
    callback_constraint: '回调约束违反',
    ownership_error: '所有权错误',
    init_exit_asymmetry: '初始化/退出不对称',
    concurrency: '并发问题',
    exit_resource_leak: '退出时资源泄漏',
    unpaired_acquire: '未配对的获取',
  }
  return map[type] || type
}

function confidenceLabel(conf) {
  const map = { high: '高', medium: '中', low: '低' }
  return map[conf] || conf
}

function truncate(str, len) {
  if (!str) return ''
  return str.length > len ? str.slice(0, len) + '...' : str
}

function showDetail(finding) {
  selectedFinding.value = finding
  dialogVisible.value = true
}
</script>

<style scoped>
.gs-df-summary {
  display: flex;
  gap: 32px;
  flex-wrap: wrap;
}

.gs-semantic-overview {
  margin-bottom: 16px;
}

.gs-semantic-stats {
  display: flex;
  gap: 24px;
  flex-wrap: wrap;
}

.gs-semantic-stat {
  display: flex;
  align-items: center;
  gap: 8px;
}

.gs-stat-label {
  color: var(--el-text-color-secondary);
  font-size: 13px;
}

.gs-df-filters {
  display: flex;
  gap: 12px;
  margin-bottom: 16px;
  flex-wrap: wrap;
}

.gs-df-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.gs-df-card {
  border-left: 4px solid var(--el-border-color);
}

.gs-df-critical {
  border-left-color: var(--el-color-danger);
}

.gs-df-high {
  border-left-color: var(--el-color-warning);
}

.gs-df-medium {
  border-left-color: var(--el-color-info);
}

.gs-df-low {
  border-left-color: var(--el-color-success);
}

.gs-df-card-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 12px;
}

.gs-df-card-title {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.gs-df-title-text {
  font-weight: 600;
  font-size: 14px;
}

.gs-df-card-meta {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-shrink: 0;
}

.gs-df-confidence {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.gs-conf-high {
  color: var(--el-color-danger);
  font-weight: 500;
}

.gs-conf-medium {
  color: var(--el-color-warning);
}

.gs-conf-low {
  color: var(--el-text-color-secondary);
}

.gs-df-card-body {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.gs-df-desc {
  margin: 0;
  color: var(--el-text-color-regular);
  font-size: 13px;
  line-height: 1.5;
}

.gs-df-location {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.gs-df-file {
  font-family: monospace;
  background: var(--el-fill-color-light);
  padding: 2px 6px;
  border-radius: 3px;
}

.gs-df-func {
  font-family: monospace;
  color: var(--el-color-primary);
  font-weight: 500;
}

.gs-df-line {
  font-family: monospace;
  color: var(--el-text-color-placeholder);
}

.gs-df-path-preview {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
}

.gs-df-path-label {
  color: var(--el-text-color-secondary);
}

.gs-df-path-chain {
  font-family: monospace;
  color: var(--el-color-primary);
}

.gs-df-fix-preview {
  display: flex;
  align-items: flex-start;
  gap: 6px;
  font-size: 12px;
  color: var(--el-color-success);
  background: var(--el-color-success-light-9);
  padding: 6px 10px;
  border-radius: 4px;
}

.gs-df-detail {
  max-height: 70vh;
  overflow-y: auto;
}

.gs-df-desc-full {
  margin: 0;
  line-height: 1.6;
  color: var(--el-text-color-regular);
}

.gs-df-execution-path {
  padding: 12px 0;
}

.gs-path-step {
  display: flex;
  align-items: center;
  gap: 12px;
}

.gs-path-idx {
  width: 24px;
  height: 24px;
  border-radius: 50%;
  background: var(--el-fill-color);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  font-weight: 600;
  color: var(--el-text-color-secondary);
}

.gs-path-func {
  font-family: monospace;
  font-size: 13px;
  color: var(--el-color-primary);
}

.gs-df-evidence {
  background: var(--el-fill-color-lighter);
  border-radius: 6px;
  overflow: hidden;
}

.gs-df-code {
  margin: 0;
  padding: 12px 16px;
  font-family: 'Monaco', 'Menlo', 'Consolas', monospace;
  font-size: 12px;
  line-height: 1.5;
  overflow-x: auto;
  max-height: 300px;
}

.gs-df-fix {
  margin-top: 8px;
}

.gs-df-dialog :deep(.el-dialog__body) {
  padding-top: 0;
}
</style>
