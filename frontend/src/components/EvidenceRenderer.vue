<template>
  <div class="gs-evidence-renderer">
    <!-- boundary_value 模块: 候选值矩阵 -->
    <template v-if="moduleId === 'boundary_value'">
      <div class="gs-ev-boundary">
        <div v-if="evidence.constraint_expr" class="gs-ev-row">
          <span class="gs-ev-label">约束表达式</span>
          <code class="gs-ev-code">{{ evidence.constraint_expr }}</code>
        </div>
        <div v-if="evidence.derived_bounds" class="gs-ev-row">
          <span class="gs-ev-label">推导区间</span>
          <span class="gs-ev-range">
            [{{ evidence.derived_bounds.min }} , {{ evidence.derived_bounds.max }}]
          </span>
        </div>
        <div v-if="evidence.candidates?.length" class="gs-ev-candidates">
          <span class="gs-ev-label">测试候选值</span>
          <div class="gs-ev-candidate-grid">
            <span
              v-for="(c, i) in evidence.candidates"
              :key="i"
              class="gs-ev-candidate-chip"
              :class="candidateClass(c, evidence)"
              :title="candidateHint(c, evidence)"
            >{{ c }}</span>
          </div>
        </div>
      </div>
    </template>

    <!-- error_path 模块: 资源清理检查表 -->
    <template v-else-if="moduleId === 'error_path'">
      <div class="gs-ev-errorpath">
        <div v-if="evidence.error_trigger" class="gs-ev-row">
          <span class="gs-ev-label">错误触发条件</span>
          <code class="gs-ev-code">{{ evidence.error_trigger }}</code>
        </div>
        <div v-if="evidence.return_mapping" class="gs-ev-row">
          <span class="gs-ev-label">返回码映射</span>
          <span class="gs-ev-mapping">
            预期 <code>{{ evidence.return_mapping.expected }}</code>
            → 实际 <code class="gs-ev-mismatch">{{ evidence.return_mapping.actual }}</code>
          </span>
        </div>
        <div v-if="evidence.propagation" class="gs-ev-row">
          <span class="gs-ev-label">错误传播</span>
          <el-tag :type="evidence.propagation === 'swallowed' ? 'danger' : 'success'" size="small">
            {{ evidence.propagation === 'swallowed' ? '被静默吞没' : evidence.propagation }}
          </el-tag>
        </div>
        <div v-if="evidence.cleanup_resources_expected?.length" class="gs-ev-cleanup-table">
          <span class="gs-ev-label">资源清理检查</span>
          <table class="gs-ev-table">
            <thead>
              <tr><th>资源</th><th>预期释放</th><th>实际释放</th><th>状态</th></tr>
            </thead>
            <tbody>
              <tr v-for="res in evidence.cleanup_resources_expected" :key="res">
                <td><code>{{ res }}</code></td>
                <td class="gs-ev-check">&#10003;</td>
                <td :class="evidence.cleanup_resources_observed?.includes(res) ? 'gs-ev-check' : 'gs-ev-miss'">
                  {{ evidence.cleanup_resources_observed?.includes(res) ? '&#10003;' : '&#10007;' }}
                </td>
                <td>
                  <el-tag
                    :type="evidence.cleanup_resources_observed?.includes(res) ? 'success' : 'danger'"
                    size="small"
                  >{{ evidence.cleanup_resources_observed?.includes(res) ? '已释放' : '泄漏' }}</el-tag>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </template>

    <!-- concurrency 模块: 竞态场景表 -->
    <template v-else-if="moduleId === 'concurrency'">
      <div class="gs-ev-concurrency">
        <div v-if="evidence.shared_symbol" class="gs-ev-row">
          <span class="gs-ev-label">共享变量</span>
          <code class="gs-ev-code gs-ev-highlight">{{ evidence.shared_symbol }}</code>
        </div>
        <div v-if="evidence.access_sites?.length" class="gs-ev-access-table">
          <span class="gs-ev-label">访问点分析</span>
          <table class="gs-ev-table">
            <thead>
              <tr><th>行号</th><th>操作</th><th>锁保护</th><th>安全</th></tr>
            </thead>
            <tbody>
              <tr v-for="(site, i) in evidence.access_sites" :key="i">
                <td><code>L{{ site.line }}</code></td>
                <td>
                  <el-tag :type="site.access === 'write' ? 'danger' : 'info'" size="small">{{ site.access === 'write' ? '写' : '读' }}</el-tag>
                </td>
                <td>
                  <code v-if="site.lock">{{ site.lock }}</code>
                  <span v-else class="gs-ev-miss">无锁</span>
                </td>
                <td>
                  <el-tag :type="site.lock ? 'success' : 'danger'" size="small">
                    {{ site.lock ? '安全' : '危险' }}
                  </el-tag>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
        <div v-if="evidence.lock_order?.length" class="gs-ev-row">
          <span class="gs-ev-label">预期锁顺序</span>
          <div class="gs-ev-chain">
            <span v-for="(l, i) in evidence.lock_order" :key="i" class="gs-ev-chain-item">
              <code>{{ l }}</code>
              <span v-if="i < evidence.lock_order.length - 1" class="gs-ev-chain-arrow">→</span>
            </span>
          </div>
        </div>
        <div v-if="evidence.conflict_order?.length" class="gs-ev-row">
          <span class="gs-ev-label">冲突锁顺序</span>
          <div class="gs-ev-chain gs-ev-chain-danger">
            <span v-for="(l, i) in evidence.conflict_order" :key="i" class="gs-ev-chain-item">
              <code>{{ l }}</code>
              <span v-if="i < evidence.conflict_order.length - 1" class="gs-ev-chain-arrow">→</span>
            </span>
          </div>
        </div>
        <div v-if="evidence.operations?.length" class="gs-ev-row">
          <span class="gs-ev-label">非原子操作序列</span>
          <div class="gs-ev-chain gs-ev-chain-warn">
            <span v-for="(op, i) in evidence.operations" :key="i" class="gs-ev-chain-item">
              <code>{{ op }}</code>
              <span v-if="i < evidence.operations.length - 1" class="gs-ev-chain-arrow gs-ev-gap-arrow">⚡</span>
            </span>
          </div>
          <el-tag v-if="evidence.gap_between" type="warning" size="small" style="margin-top:4px">存在原子性缺口</el-tag>
        </div>
      </div>
    </template>

    <!-- call_graph 模块: 调用链 + 可视化 -->
    <template v-else-if="moduleId === 'call_graph'">
      <div class="gs-ev-callgraph">
        <div v-if="evidence.callee_count" class="gs-ev-row">
          <span class="gs-ev-label">被调用者数量</span>
          <span class="gs-ev-big-num" :class="{ danger: evidence.callee_count > 15 }">{{ evidence.callee_count }}</span>
        </div>
        <div v-if="evidence.callees?.length" class="gs-ev-row">
          <span class="gs-ev-label">调用目标</span>
          <div class="gs-ev-chip-list">
            <code v-for="c in evidence.callees" :key="c" class="gs-ev-func-chip">{{ c }}()</code>
          </div>
        </div>
        <div v-if="evidence.depth" class="gs-ev-row">
          <span class="gs-ev-label">调用链深度</span>
          <span class="gs-ev-big-num">{{ evidence.depth }} 层</span>
        </div>
        <div v-if="evidence.chain?.length" class="gs-ev-row">
          <span class="gs-ev-label">调用链路径</span>
          <div class="gs-ev-chain">
            <span v-for="(fn, i) in evidence.chain" :key="i" class="gs-ev-chain-item">
              <code>{{ fn }}()</code>
              <span v-if="i < evidence.chain.length - 1" class="gs-ev-chain-arrow">→</span>
            </span>
          </div>
        </div>
        <!-- 交互式调用图 -->
        <CallGraph :evidence="evidence" :finding="finding" module-id="call_graph" style="margin-top: 8px;" />
      </div>
    </template>

    <!-- diff_impact 模块: 变更影响链 + 可视化 -->
    <template v-else-if="moduleId === 'diff_impact'">
      <div class="gs-ev-diffimpact">
        <div v-if="evidence.changed_symbols?.length" class="gs-ev-row">
          <span class="gs-ev-label">变更函数</span>
          <div class="gs-ev-chip-list">
            <code v-for="s in evidence.changed_symbols" :key="s" class="gs-ev-func-chip gs-ev-changed">{{ s }}()</code>
          </div>
        </div>
        <div v-if="evidence.impacted_symbols?.length" class="gs-ev-row">
          <span class="gs-ev-label">受影响函数</span>
          <div class="gs-ev-chip-list">
            <code v-for="s in evidence.impacted_symbols" :key="s" class="gs-ev-func-chip gs-ev-impacted">{{ s }}()</code>
          </div>
        </div>
        <div v-if="evidence.depth" class="gs-ev-row">
          <span class="gs-ev-label">影响传播深度</span>
          <span class="gs-ev-big-num">{{ evidence.depth }} 层</span>
        </div>
        <!-- 变更影响图 -->
        <CallGraph :evidence="evidence" :finding="finding" module-id="diff_impact" style="margin-top: 8px;" />
      </div>
    </template>

    <!-- coverage_map 模块: 覆盖率条 -->
    <template v-else-if="moduleId === 'coverage_map'">
      <div class="gs-ev-coverage">
        <div class="gs-ev-coverage-bars">
          <div class="gs-ev-cov-item">
            <span class="gs-ev-label">行覆盖率</span>
            <div class="gs-ev-cov-bar-wrap">
              <div class="gs-ev-cov-bar" :style="{ width: (evidence.line_coverage || 0) * 100 + '%' }" :class="covClass(evidence.line_coverage)"></div>
            </div>
            <span class="gs-ev-cov-pct">{{ ((evidence.line_coverage || 0) * 100).toFixed(0) }}%</span>
          </div>
          <div class="gs-ev-cov-item">
            <span class="gs-ev-label">分支覆盖率</span>
            <div class="gs-ev-cov-bar-wrap">
              <div class="gs-ev-cov-bar" :style="{ width: (evidence.branch_coverage || 0) * 100 + '%' }" :class="covClass(evidence.branch_coverage)"></div>
            </div>
            <span class="gs-ev-cov-pct">{{ ((evidence.branch_coverage || 0) * 100).toFixed(0) }}%</span>
          </div>
        </div>
        <div v-if="evidence.related_finding_ids?.length" class="gs-ev-row">
          <span class="gs-ev-label">关联发现</span>
          <div class="gs-ev-chip-list">
            <code v-for="id in evidence.related_finding_ids" :key="id" class="gs-ev-func-chip">{{ id }}</code>
          </div>
        </div>
      </div>
    </template>

    <!-- branch_path 模块: 分支信息 + CFG 可视化 -->
    <template v-else-if="moduleId === 'branch_path'">
      <div class="gs-ev-branch">
        <div v-if="evidence.branch_id" class="gs-ev-row">
          <span class="gs-ev-label">分支 ID</span>
          <code class="gs-ev-code">{{ evidence.branch_id }}</code>
        </div>
        <div v-if="evidence.condition_expr" class="gs-ev-row">
          <span class="gs-ev-label">条件表达式</span>
          <code class="gs-ev-code gs-ev-highlight">{{ evidence.condition_expr }}</code>
        </div>
        <div v-if="evidence.path_type" class="gs-ev-row">
          <span class="gs-ev-label">路径类型</span>
          <el-tag :type="pathTypeTag(evidence.path_type)" size="small">{{ pathTypeLabel(evidence.path_type) }}</el-tag>
        </div>
        <!-- CFG 可视化 -->
        <CfgGraph :evidence="evidence" :finding="finding" style="margin-top: 8px;" />
      </div>
    </template>

    <!-- 通用 fallback: 格式化 JSON -->
    <template v-else>
      <pre class="gs-ev-json">{{ JSON.stringify(evidence, null, 2) }}</pre>
    </template>
  </div>
</template>

<script setup>
import CfgGraph from './CfgGraph.vue'
import CallGraph from './CallGraph.vue'

const props = defineProps({
  moduleId: { type: String, default: '' },
  riskType: { type: String, default: '' },
  evidence: { type: Object, default: () => ({}) },
  finding: { type: Object, default: () => ({}) },
})

function candidateClass(val, ev) {
  if (!ev.derived_bounds) return ''
  const { min, max } = ev.derived_bounds
  if (val < min || val > max) return 'gs-ev-candidate-invalid'
  if (val === min || val === max) return 'gs-ev-candidate-boundary'
  if (val === min - 1 || val === max + 1) return 'gs-ev-candidate-edge'
  return 'gs-ev-candidate-normal'
}

function candidateHint(val, ev) {
  if (!ev.derived_bounds) return String(val)
  const { min, max } = ev.derived_bounds
  if (val < min) return `越界 (< min=${min})`
  if (val > max) return `越界 (> max=${max})`
  if (val === min) return `下界 (min=${min})`
  if (val === max) return `上界 (max=${max})`
  return `区间内 [${min}, ${max}]`
}

function covClass(val) {
  if (!val || val === 0) return 'cov-zero'
  if (val < 0.3) return 'cov-low'
  if (val < 0.7) return 'cov-medium'
  return 'cov-high'
}

function pathTypeTag(pt) {
  if (pt === 'error') return 'danger'
  if (pt === 'cleanup') return 'warning'
  return 'info'
}

function pathTypeLabel(pt) {
  const map = { error: '错误路径', cleanup: '清理路径', normal: '正常路径' }
  return map[pt] || pt
}
</script>

<style scoped>
.gs-evidence-renderer {
  font-size: 13px;
}

/* ── 通用行 ─────────────────────────── */
.gs-ev-row {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  margin-bottom: 10px;
}
.gs-ev-label {
  display: inline-block;
  min-width: 100px;
  font-size: 12px;
  font-weight: 600;
  color: var(--gs-text-muted);
  flex-shrink: 0;
  padding-top: 2px;
}
.gs-ev-code {
  font-family: var(--gs-font-mono);
  font-size: 12px;
  background: rgba(75, 159, 213, 0.08);
  padding: 2px 8px;
  border-radius: 4px;
  color: var(--gs-text-primary);
}
.gs-ev-highlight {
  background: rgba(229, 127, 0, 0.1);
  color: var(--gs-risk-medium);
  font-weight: 600;
}

/* ── 边界值候选 ─────────────────────── */
.gs-ev-range {
  font-family: var(--gs-font-mono);
  font-size: 13px;
  color: var(--gs-text-primary);
}
.gs-ev-candidates {
  margin-top: 4px;
}
.gs-ev-candidate-grid {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 6px;
}
.gs-ev-candidate-chip {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 48px;
  height: 32px;
  padding: 0 10px;
  border-radius: 6px;
  font-family: var(--gs-font-mono);
  font-size: 13px;
  font-weight: 600;
  border: 1px solid var(--gs-border);
  background: var(--gs-surface);
  cursor: help;
  transition: all 0.15s;
}
.gs-ev-candidate-chip:hover { transform: scale(1.05); }
.gs-ev-candidate-boundary {
  background: rgba(229, 127, 0, 0.12);
  border-color: var(--gs-risk-medium);
  color: var(--gs-risk-medium);
}
.gs-ev-candidate-edge {
  background: rgba(213, 0, 0, 0.08);
  border-color: var(--gs-risk-high);
  color: var(--gs-risk-high);
}
.gs-ev-candidate-invalid {
  background: rgba(213, 0, 0, 0.12);
  border-color: var(--gs-risk-critical);
  color: var(--gs-risk-critical);
}
.gs-ev-candidate-normal {
  background: rgba(0, 170, 0, 0.06);
  border-color: var(--gs-success);
  color: var(--gs-success);
}

/* ── 错误码映射 ─────────────────────── */
.gs-ev-mapping code { margin: 0 4px; }
.gs-ev-mismatch { color: var(--gs-danger) !important; font-weight: 700; }
.gs-ev-miss { color: var(--gs-danger); font-weight: 600; font-size: 12px; }
.gs-ev-check { color: var(--gs-success); }

/* ── 表格 ───────────────────────────── */
.gs-ev-table {
  width: 100%;
  border-collapse: collapse;
  margin-top: 6px;
  font-size: 12px;
}
.gs-ev-table th {
  background: var(--gs-bg);
  padding: 6px 10px;
  text-align: left;
  font-weight: 600;
  color: var(--gs-text-muted);
  border-bottom: 1px solid var(--gs-border);
}
.gs-ev-table td {
  padding: 6px 10px;
  border-bottom: 1px solid var(--gs-border);
  color: var(--gs-text-secondary);
}

/* ── 调用链 ─────────────────────────── */
.gs-ev-chain {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 4px;
}
.gs-ev-chain-item { display: flex; align-items: center; gap: 4px; }
.gs-ev-chain-arrow { color: var(--gs-text-muted); font-size: 14px; }
.gs-ev-chain-danger .gs-ev-chain-arrow { color: var(--gs-danger); }
.gs-ev-chain-danger code { color: var(--gs-danger); }
.gs-ev-chain-warn .gs-ev-chain-arrow { color: var(--gs-warning); }
.gs-ev-gap-arrow { color: var(--gs-danger) !important; font-weight: bold; }

/* ── 函数标签 ───────────────────────── */
.gs-ev-chip-list { display: flex; flex-wrap: wrap; gap: 4px; }
.gs-ev-func-chip {
  display: inline-block;
  padding: 2px 8px;
  background: rgba(75, 159, 213, 0.08);
  border-radius: 4px;
  font-family: var(--gs-font-mono);
  font-size: 12px;
  color: var(--gs-text-primary);
}
.gs-ev-changed {
  background: rgba(213, 0, 0, 0.1);
  color: var(--gs-risk-high);
}
.gs-ev-impacted {
  background: rgba(229, 127, 0, 0.1);
  color: var(--gs-risk-medium);
}

/* ── 大数字 ─────────────────────────── */
.gs-ev-big-num {
  font-size: 18px;
  font-weight: 700;
  font-family: var(--gs-font-mono);
  color: var(--gs-text-primary);
}
.gs-ev-big-num.danger { color: var(--gs-risk-high); }

/* ── 覆盖率条 ───────────────────────── */
.gs-ev-coverage-bars {
  display: flex;
  flex-direction: column;
  gap: 10px;
  margin-bottom: 12px;
}
.gs-ev-cov-item {
  display: flex;
  align-items: center;
  gap: 10px;
}
.gs-ev-cov-bar-wrap {
  flex: 1;
  height: 10px;
  background: var(--gs-border);
  border-radius: 5px;
  overflow: hidden;
}
.gs-ev-cov-bar {
  height: 100%;
  border-radius: 5px;
  transition: width 0.3s;
}
.gs-ev-cov-bar.cov-zero { background: var(--gs-danger); width: 2px !important; min-width: 2px; }
.gs-ev-cov-bar.cov-low { background: var(--gs-risk-high); }
.gs-ev-cov-bar.cov-medium { background: var(--gs-risk-medium); }
.gs-ev-cov-bar.cov-high { background: var(--gs-success); }
.gs-ev-cov-pct {
  min-width: 40px;
  text-align: right;
  font-family: var(--gs-font-mono);
  font-size: 12px;
  font-weight: 600;
}

/* ── JSON fallback ──────────────────── */
.gs-ev-json {
  margin: 0;
  padding: 10px;
  background: var(--gs-bg);
  border-radius: var(--gs-radius-sm);
  font-family: var(--gs-font-mono);
  font-size: 12px;
  color: var(--gs-text-secondary);
  line-height: 1.5;
  overflow-x: auto;
  white-space: pre-wrap;
  word-break: break-word;
}
</style>
