<template>
  <div class="gs-code-layout">
    <!-- 左侧文件树 -->
    <aside class="gs-file-tree">
      <div class="gs-file-tree-header">
        <el-input v-model="fileSearch" placeholder="搜索文件..." size="small" clearable :prefix-icon="SearchIcon" />
      </div>
      <div class="gs-file-tree-content">
        <div
          v-for="node in filteredTree"
          :key="node.path"
          class="gs-tree-item"
          :class="{ active: selectedFile === node.path }"
          :style="{ paddingLeft: (node.depth * 16 + 12) + 'px' }"
          @click="selectFile(node)"
        >
          <el-icon :size="14" style="margin-right: 6px; flex-shrink: 0;">
            <component :is="node.type === 'dir' ? 'FolderOpened' : 'Document'" />
          </el-icon>
          <span class="gs-tree-name">{{ node.name }}</span>
          <span v-if="node.finding_count" class="gs-tree-badge">{{ node.finding_count }}</span>
        </div>
        <el-empty v-if="!filteredTree.length" description="暂无文件" :image-size="40" />
      </div>
    </aside>

    <!-- 右侧源码查看器 -->
    <div class="gs-source-viewer">
      <template v-if="selectedFile && sourceContent">
        <!-- 文件头 -->
        <div class="gs-source-header">
          <div class="gs-source-path">
            <el-icon><Document /></el-icon>
            <span>{{ selectedFile }}</span>
          </div>
          <div class="gs-source-stats">
            <span v-if="fileFindings.length" class="gs-source-finding-count">
              {{ fileFindings.length }} 条发现
            </span>
          </div>
        </div>

        <!-- 源码 -->
        <div class="gs-source-code">
          <table class="gs-code-table">
            <tbody>
              <tr
                v-for="(line, idx) in sourceLines"
                :key="idx"
                class="gs-code-line"
                :class="{
                  'gs-code-line--issue': lineHasIssue(idx + 1),
                  'gs-code-line--selected': selectedIssueLine === idx + 1,
                  'gs-code-line--covered': lineCoverage(idx + 1) === 'covered',
                  'gs-code-line--uncovered': lineCoverage(idx + 1) === 'uncovered',
                }"
              >
                <td class="gs-line-number" @click="onLineClick(idx + 1)">{{ idx + 1 }}</td>
                <td class="gs-line-cov-indicator">
                  <span v-if="lineCoverage(idx + 1) === 'covered'" class="gs-cov-mark gs-cov-mark--hit" title="已覆盖">▌</span>
                  <span v-else-if="lineCoverage(idx + 1) === 'uncovered'" class="gs-cov-mark gs-cov-mark--miss" title="未覆盖">▌</span>
                </td>
                <td class="gs-line-markers">
                  <span
                    v-if="lineHasIssue(idx + 1)"
                    class="gs-line-issue-marker"
                    :class="'gs-severity-' + getLineMaxSeverity(idx + 1).toLowerCase()"
                    :title="getLineIssueTitle(idx + 1)"
                  >●</span>
                </td>
                <td class="gs-line-content"><pre>{{ line }}</pre></td>
              </tr>
            </tbody>
          </table>
        </div>

        <!-- 当前行的发现 -->
        <div v-if="selectedLineFindings.length" class="gs-line-findings">
          <div class="gs-line-findings-header">
            行 {{ selectedIssueLine }} 的发现 ({{ selectedLineFindings.length }})
          </div>
          <div v-for="f in selectedLineFindings" :key="f.finding_id" class="gs-line-finding-item">
            <span class="gs-severity-tag" :class="'gs-severity-' + (f.severity || 's3').toLowerCase()">{{ f.severity }}</span>
            <div>
              <div style="font-weight: 500;">{{ f.title }}</div>
              <div style="font-size: 12px; color: var(--gs-text-muted);">{{ f.risk_type }} · {{ f.description?.slice(0, 100) }}</div>
            </div>
          </div>
        </div>
      </template>

      <el-empty v-else description="选择左侧文件查看源码" :image-size="80" />
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import { useRoute } from 'vue-router'
import { Search as SearchIcon } from '@element-plus/icons-vue'
import api from '../../api.js'

const props = defineProps({
  projectId: [String, Number],
})

const route = useRoute()
const fileTree = ref([])
const selectedFile = ref(null)
const sourceContent = ref('')
const fileFindings = ref([])
const selectedIssueLine = ref(null)
const fileSearch = ref('')

const sourceLines = computed(() => sourceContent.value ? sourceContent.value.split('\n') : [])

const filteredTree = computed(() => {
  if (!fileSearch.value) return fileTree.value
  const q = fileSearch.value.toLowerCase()
  return fileTree.value.filter(n => n.name.toLowerCase().includes(q) || n.path.toLowerCase().includes(q))
})

const selectedLineFindings = computed(() => {
  if (!selectedIssueLine.value) return []
  return fileFindings.value.filter(f =>
    f.line_start <= selectedIssueLine.value && (f.line_end || f.line_start) >= selectedIssueLine.value
  )
})

function lineHasIssue(lineNum) {
  return fileFindings.value.some(f => f.line_start <= lineNum && (f.line_end || f.line_start) >= lineNum)
}

function getLineMaxSeverity(lineNum) {
  const issues = fileFindings.value.filter(f => f.line_start <= lineNum && (f.line_end || f.line_start) >= lineNum)
  const order = ['S0', 'S1', 'S2', 'S3']
  for (const s of order) {
    if (issues.some(i => i.severity === s)) return s
  }
  return 'S3'
}

function getLineIssueTitle(lineNum) {
  const issues = fileFindings.value.filter(f => f.line_start <= lineNum && (f.line_end || f.line_start) >= lineNum)
  return issues.map(i => `[${i.severity}] ${i.title}`).join('\n')
}

function onLineClick(lineNum) {
  selectedIssueLine.value = selectedIssueLine.value === lineNum ? null : lineNum
}

// 覆盖率着色：从 coverage_map 模块的发现中提取行覆盖信息
function lineCoverage(lineNum) {
  // 检查是否有 coverage_map 类型的发现覆盖此行
  const covFindings = fileFindings.value.filter(f =>
    f.module_id === 'coverage_map' && f.line_start <= lineNum && (f.line_end || f.line_start) >= lineNum
  )
  if (covFindings.length > 0) {
    // 有 coverage_map 发现的行 = 高风险低覆盖 = 未覆盖
    return 'uncovered'
  }
  // 如果发现列表中有 coverage_map 类型发现但不在此行范围 = 其余行视为已覆盖
  const hasCovModule = fileFindings.value.some(f => f.module_id === 'coverage_map')
  if (hasCovModule && lineHasIssue(lineNum)) {
    return '' // 有其他问题但不是覆盖率问题
  }
  return '' // 无覆盖率信息时不显示
}

async function selectFile(node) {
  if (node.type === 'dir') return
  selectedFile.value = node.path
  selectedIssueLine.value = null
  try {
    const data = await api.getFileSource(props.projectId, node.path)
    sourceContent.value = data?.content || '// 无法加载源码'
    fileFindings.value = data?.findings || []
  } catch {
    sourceContent.value = '// 加载失败'
    fileFindings.value = []
  }
}

async function loadTree() {
  try {
    const data = await api.getProjectFileTree(props.projectId)
    fileTree.value = data?.files || []
  } catch {
    fileTree.value = []
  }
  // 如果 URL 有 path 参数，自动选中
  if (route.query.path) {
    const node = fileTree.value.find(n => n.path === route.query.path)
    if (node) selectFile(node)
  }
}

onMounted(loadTree)
watch(() => props.projectId, loadTree)
</script>

<style scoped>
.gs-code-layout {
  display: flex;
  height: 100%;
}

/* ── 文件树 ─────────────────────────── */
.gs-file-tree {
  width: 280px;
  flex-shrink: 0;
  border-right: 1px solid var(--gs-border);
  background: var(--gs-surface);
  display: flex;
  flex-direction: column;
}

.gs-file-tree-header {
  padding: var(--gs-space-sm);
  border-bottom: 1px solid var(--gs-border-light);
}

.gs-file-tree-content {
  flex: 1;
  overflow-y: auto;
  padding: var(--gs-space-xs) 0;
}

.gs-tree-item {
  display: flex;
  align-items: center;
  padding: 5px 12px;
  cursor: pointer;
  font-size: var(--gs-font-sm);
  color: var(--gs-text-primary);
  transition: background var(--gs-transition);
}
.gs-tree-item:hover { background: var(--gs-surface-alt); }
.gs-tree-item.active { background: #E8F4FD; font-weight: 500; }

.gs-tree-name {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.gs-tree-badge {
  font-size: 10px;
  font-weight: 700;
  background: var(--gs-danger);
  color: #fff;
  padding: 1px 5px;
  border-radius: 8px;
  min-width: 16px;
  text-align: center;
}

/* ── 源码查看器 ─────────────────────── */
.gs-source-viewer {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.gs-source-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: var(--gs-space-sm) var(--gs-space-md);
  background: var(--gs-surface);
  border-bottom: 1px solid var(--gs-border);
}

.gs-source-path {
  display: flex;
  align-items: center;
  gap: 6px;
  font-family: var(--gs-font-mono);
  font-size: var(--gs-font-sm);
  color: var(--gs-text-primary);
}

.gs-source-finding-count {
  font-size: var(--gs-font-xs);
  color: var(--gs-danger);
  font-weight: 600;
}

.gs-source-code {
  flex: 1;
  overflow: auto;
  background: #FAFAFA;
}

.gs-code-table {
  border-collapse: collapse;
  width: 100%;
  font-family: var(--gs-font-mono);
  font-size: 12px;
  line-height: 1.6;
}

.gs-code-line { transition: background 0.1s; }
.gs-code-line:hover { background: #F0F0F0; }
.gs-code-line--issue { background: #FFF8E1; }
.gs-code-line--issue:hover { background: #FFF3CD; }
.gs-code-line--selected { background: #E8F4FD !important; }

.gs-line-number {
  width: 50px;
  text-align: right;
  padding: 0 12px 0 8px;
  color: var(--gs-text-muted);
  user-select: none;
  cursor: pointer;
  border-right: 1px solid var(--gs-border-light);
}

.gs-line-markers {
  width: 20px;
  text-align: center;
  padding: 0 2px;
}

.gs-line-issue-marker { font-size: 10px; }

.gs-line-content {
  padding: 0 16px;
  white-space: pre;
}
.gs-line-content pre {
  margin: 0;
  font-family: inherit;
  font-size: inherit;
}

/* ── 行级发现 ─────────────────────────── */
.gs-line-findings {
  border-top: 1px solid var(--gs-border);
  background: var(--gs-surface);
  max-height: 200px;
  overflow-y: auto;
}

.gs-line-findings-header {
  padding: var(--gs-space-sm) var(--gs-space-md);
  font-size: var(--gs-font-sm);
  font-weight: 600;
  color: var(--gs-text-secondary);
  border-bottom: 1px solid var(--gs-border-light);
}

.gs-line-finding-item {
  display: flex;
  align-items: flex-start;
  gap: var(--gs-space-sm);
  padding: var(--gs-space-sm) var(--gs-space-md);
  border-bottom: 1px solid var(--gs-border-light);
}

/* ── 覆盖率着色 ─────────────────────── */
.gs-line-cov-indicator {
  width: 6px;
  padding: 0 1px;
  text-align: center;
  font-size: 10px;
  line-height: 1;
  user-select: none;
}
.gs-cov-mark { font-size: 12px; line-height: 1; }
.gs-cov-mark--hit { color: #00AA00; }
.gs-cov-mark--miss { color: #D50000; }

.gs-code-line--covered {
  background: rgba(0, 170, 0, 0.04);
}
.gs-code-line--uncovered {
  background: rgba(213, 0, 0, 0.06);
}
</style>
