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
        <!-- 传播链上下文（增强） -->
        <div v-if="evidence.propagation_chain?.length > 1" class="gs-ev-boundary-chain">
          <span class="gs-ev-label">调用链传播</span>
          <div class="gs-ev-chain">
            <span v-for="(step, i) in evidence.propagation_chain" :key="i" class="gs-ev-chain-item">
              <code :class="{ 'gs-ev-changed': i === 0, 'gs-ev-impacted': i === evidence.propagation_chain.length - 1 }">{{ step.function }}({{ step.param }})</code>
              <span v-if="step.transform && step.transform !== 'none'" style="font-size:10px;color:#E57F00;">{{ step.transform }}</span>
              <span v-if="i < evidence.propagation_chain.length - 1" class="gs-ev-chain-arrow">→</span>
            </span>
          </div>
          <el-tag v-if="evidence.is_external_input" type="danger" size="small" style="margin-top:6px;">入口来自外部输入</el-tag>
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
        <!-- 跨函数资源泄漏 -->
        <div v-if="evidence.caller_function && evidence.callee_function" class="gs-ev-row">
          <span class="gs-ev-label">跨函数链</span>
          <div class="gs-ev-chain">
            <span class="gs-ev-chain-item"><code class="gs-ev-changed">{{ evidence.caller_function }}()</code></span>
            <span class="gs-ev-chain-arrow">→ 调用 →</span>
            <span class="gs-ev-chain-item"><code class="gs-ev-impacted">{{ evidence.callee_function }}()</code></span>
          </div>
        </div>
        <div v-if="evidence.caller_resources?.length" class="gs-ev-row">
          <span class="gs-ev-label">已分配资源</span>
          <div class="gs-ev-chip-list">
            <code v-for="r in evidence.caller_resources" :key="r" class="gs-ev-func-chip" style="background:rgba(213,0,0,0.08);color:#D50000;">{{ r }}</code>
          </div>
        </div>
        <div v-if="evidence.return_value_checked !== undefined" class="gs-ev-row">
          <span class="gs-ev-label">返回值检查</span>
          <el-tag :type="evidence.return_value_checked ? 'success' : 'danger'" size="small">
            {{ evidence.return_value_checked ? '已检查' : '未检查' }}
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
        <!-- 跨函数竞态信息 -->
        <div v-if="evidence.other_accessors?.length" class="gs-ev-row">
          <span class="gs-ev-label">其他访问者</span>
          <div class="gs-ev-chip-list">
            <code v-for="fn in evidence.other_accessors" :key="fn" class="gs-ev-func-chip gs-ev-impacted">{{ fn }}()</code>
          </div>
        </div>
        <div v-if="evidence.cross_function_chain" class="gs-ev-row">
          <span class="gs-ev-label">跨函数调用链</span>
          <div class="gs-ev-chain gs-ev-chain-danger">
            <span v-for="(fn, i) in (Array.isArray(evidence.cross_function_chain) ? evidence.cross_function_chain : [evidence.cross_function_chain])" :key="i" class="gs-ev-chain-item">
              <code>{{ fn }}</code>
              <span v-if="i < (Array.isArray(evidence.cross_function_chain) ? evidence.cross_function_chain.length : 1) - 1" class="gs-ev-chain-arrow">→</span>
            </span>
          </div>
        </div>
        <!-- ABBA 死锁 chain_a / chain_b -->
        <div v-if="evidence.chain_a" class="gs-ev-row">
          <span class="gs-ev-label">路径 A 锁顺序</span>
          <div class="gs-ev-chain">
            <span v-for="(l, i) in (evidence.chain_a.locks || [])" :key="'a'+i" class="gs-ev-chain-item">
              <code>{{ l }}</code>
              <span v-if="i < (evidence.chain_a.locks || []).length - 1" class="gs-ev-chain-arrow">→</span>
            </span>
            <span v-if="evidence.chain_a.path" style="font-size:11px;color:var(--gs-text-muted);margin-left:8px;">({{ evidence.chain_a.path }})</span>
          </div>
        </div>
        <div v-if="evidence.chain_b" class="gs-ev-row">
          <span class="gs-ev-label">路径 B 锁顺序</span>
          <div class="gs-ev-chain gs-ev-chain-danger">
            <span v-for="(l, i) in (evidence.chain_b.locks || [])" :key="'b'+i" class="gs-ev-chain-item">
              <code>{{ l }}</code>
              <span v-if="i < (evidence.chain_b.locks || []).length - 1" class="gs-ev-chain-arrow">→</span>
            </span>
            <span v-if="evidence.chain_b.path" style="font-size:11px;color:var(--gs-text-muted);margin-left:8px;">({{ evidence.chain_b.path }})</span>
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

    <!-- data_flow 模块: 参数传播链可视化 -->
    <template v-else-if="moduleId === 'data_flow'">
      <div class="gs-ev-dataflow">
        <div v-if="evidence.entry_function" class="gs-ev-row">
          <span class="gs-ev-label">入口函数</span>
          <code class="gs-ev-code gs-ev-highlight">{{ evidence.entry_function }}({{ evidence.entry_param || '' }})</code>
          <el-tag v-if="evidence.is_external_input" type="danger" size="small" style="margin-left:6px;">外部输入</el-tag>
        </div>
        <div v-if="evidence.chain_depth" class="gs-ev-row">
          <span class="gs-ev-label">传播深度</span>
          <span class="gs-ev-big-num" :class="{ danger: evidence.chain_depth >= 5 }">{{ evidence.chain_depth }} 层</span>
        </div>
        <div v-if="evidence.propagation_chain?.length" class="gs-ev-dataflow-chain">
          <span class="gs-ev-label">传播路径</span>
          <div class="gs-ev-flow-pipeline">
            <div v-for="(step, i) in evidence.propagation_chain" :key="i" class="gs-ev-flow-step"
                 :class="{ 'gs-ev-flow-entry': i === 0, 'gs-ev-flow-sink': i === evidence.propagation_chain.length - 1 }">
              <div class="gs-ev-flow-step-header">
                <span class="gs-ev-flow-step-idx">{{ i + 1 }}</span>
                <code class="gs-ev-func-chip">{{ step.function }}()</code>
              </div>
              <div class="gs-ev-flow-step-detail">
                <span class="gs-ev-flow-param">参数: <code>{{ step.param }}</code></span>
                <span v-if="step.transform && step.transform !== 'none'" class="gs-ev-flow-transform">
                  变换: <code class="gs-ev-flow-transform-code">{{ step.transform }}</code>
                  <span v-if="step.transform_expr" class="gs-ev-flow-transform-expr">{{ step.transform_expr }}</span>
                </span>
              </div>
              <div v-if="i < evidence.propagation_chain.length - 1" class="gs-ev-flow-connector">
                <span class="gs-ev-flow-arrow">▼</span>
              </div>
            </div>
          </div>
        </div>
        <div v-if="evidence.sensitive_operations?.length" class="gs-ev-row">
          <span class="gs-ev-label">敏感操作</span>
          <div class="gs-ev-chip-list">
            <code v-for="op in evidence.sensitive_operations" :key="op" class="gs-ev-func-chip" style="color:#D50000;background:rgba(213,0,0,0.08);">{{ op }}</code>
          </div>
        </div>
        <div v-if="evidence.attack_scenario" class="gs-ev-row" style="flex-direction:column;gap:4px;">
          <span class="gs-ev-label">攻击场景</span>
          <p style="margin:0;font-size:12px;color:var(--gs-text-secondary);line-height:1.5;">{{ evidence.attack_scenario }}</p>
        </div>
        <!-- 交互式数据流图 -->
        <DataFlowGraph
          v-if="evidence.propagation_chain?.length > 1"
          :chain="evidence.propagation_chain"
          :is-external="!!evidence.is_external_input"
          style="margin-top: 8px;"
        />
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
        <div v-if="evidence.caller_chains?.length" class="gs-ev-row" style="flex-direction:column;gap:4px;">
          <span class="gs-ev-label">深层调用链</span>
          <div v-for="(chain, ci) in evidence.caller_chains.slice(0, 5)" :key="ci" class="gs-ev-chain" style="margin-bottom:4px;">
            <span v-for="(fn, i) in chain" :key="i" class="gs-ev-chain-item">
              <code>{{ fn }}()</code>
              <span v-if="i < chain.length - 1" class="gs-ev-chain-arrow">→</span>
            </span>
          </div>
        </div>
        <div v-if="evidence.params?.length" class="gs-ev-row">
          <span class="gs-ev-label">函数参数</span>
          <div class="gs-ev-chip-list">
            <code v-for="p in evidence.params" :key="p" class="gs-ev-func-chip">{{ p }}</code>
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
        <div v-if="evidence.impacted_callers?.length" class="gs-ev-row">
          <span class="gs-ev-label">上游调用者 ({{ evidence.impacted_callers.length }})</span>
          <div class="gs-ev-chip-list">
            <code v-for="s in evidence.impacted_callers.slice(0, 8)" :key="s" class="gs-ev-func-chip gs-ev-impacted">{{ typeof s === 'string' ? s : s.name }}()</code>
            <span v-if="evidence.impacted_callers.length > 8" class="gs-ev-chip-more">还有 {{ evidence.impacted_callers.length - 8 }} 个</span>
          </div>
        </div>
        <div v-if="evidence.impacted_callees?.length" class="gs-ev-row">
          <span class="gs-ev-label">下游被调用 ({{ evidence.impacted_callees.length }})</span>
          <div class="gs-ev-chip-list">
            <code v-for="s in evidence.impacted_callees.slice(0, 8)" :key="s" class="gs-ev-func-chip gs-ev-impacted">{{ typeof s === 'string' ? s : s.name }}()</code>
            <span v-if="evidence.impacted_callees.length > 8" class="gs-ev-chip-more">还有 {{ evidence.impacted_callees.length - 8 }} 个</span>
          </div>
        </div>
        <div v-if="evidence.impacted_symbols?.length" class="gs-ev-row">
          <span class="gs-ev-label">受影响函数</span>
          <div class="gs-ev-chip-list">
            <code v-for="s in evidence.impacted_symbols" :key="s" class="gs-ev-func-chip gs-ev-impacted">{{ typeof s === 'string' ? s : s.name }}()</code>
          </div>
        </div>
        <div v-if="evidence.depth" class="gs-ev-row">
          <span class="gs-ev-label">影响传播深度</span>
          <span class="gs-ev-big-num">{{ evidence.depth }} 层</span>
        </div>
        <div v-if="evidence.affected_data_flow_chains" class="gs-ev-row">
          <span class="gs-ev-label">影响数据流链</span>
          <el-tag type="danger" size="small">{{ typeof evidence.affected_data_flow_chains === 'number' ? evidence.affected_data_flow_chains : Array.isArray(evidence.affected_data_flow_chains) ? evidence.affected_data_flow_chains.length : 1 }} 条传播链受影响</el-tag>
        </div>
        <div v-if="evidence.direction" class="gs-ev-row">
          <span class="gs-ev-label">传播方向</span>
          <el-tag size="small">{{ evidence.direction === 'upstream' ? '上游（调用者）' : evidence.direction === 'downstream' ? '下游（被调用）' : evidence.direction }}</el-tag>
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
import DataFlowGraph from './DataFlowGraph.vue'

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
  if (pt === 'boundary') return 'warning'
  if (pt === 'state') return 'info'
  return 'info'
}

function pathTypeLabel(pt) {
  const map = { error: '错误路径', cleanup: '清理路径', boundary: '边界条件路径', state: '状态判断路径', normal: '正常路径' }
  return map[pt] || pt
}
</script>

<style scoped>
.gs-evidence-renderer {
  font-size: 13px;
  overflow: hidden;
  word-break: break-word;
  overflow-wrap: break-word;
}

/* ── 通用行 ─────────────────────────── */
.gs-ev-row {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  margin-bottom: 10px;
  min-width: 0;
  max-width: 100%;
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
  word-break: break-all;
  overflow-wrap: break-word;
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
  min-width: 0;
  flex: 1;
}
.gs-ev-chain-item { display: flex; align-items: center; gap: 4px; min-width: 0; word-break: break-all; }
.gs-ev-chain-arrow { color: var(--gs-text-muted); font-size: 14px; }
.gs-ev-chain-danger .gs-ev-chain-arrow { color: var(--gs-danger); }
.gs-ev-chain-danger code { color: var(--gs-danger); }
.gs-ev-chain-warn .gs-ev-chain-arrow { color: var(--gs-warning); }
.gs-ev-gap-arrow { color: var(--gs-danger) !important; font-weight: bold; }

/* ── 函数标签 ───────────────────────── */
.gs-ev-chip-list { display: flex; flex-wrap: wrap; gap: 4px; min-width: 0; flex: 1; }
.gs-ev-func-chip {
  display: inline-block;
  padding: 2px 8px;
  background: rgba(75, 159, 213, 0.08);
  border-radius: 4px;
  font-family: var(--gs-font-mono);
  font-size: 12px;
  color: var(--gs-text-primary);
  word-break: break-all;
  overflow-wrap: break-word;
  max-width: 100%;
}
.gs-ev-chip-more {
  display: inline-flex;
  align-items: center;
  padding: 2px 8px;
  font-size: 11px;
  color: var(--gs-text-muted);
  background: rgba(0,0,0,0.04);
  border-radius: 4px;
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

/* ── 数据流传播 ───────────────────── */
.gs-ev-dataflow-chain { margin-top: 8px; }
.gs-ev-flow-pipeline {
  display: flex; flex-direction: column; gap: 0;
  margin-top: 8px; padding-left: 4px;
}
.gs-ev-flow-step {
  position: relative; padding: 8px 12px;
  background: var(--gs-surface); border: 1px solid var(--gs-border); border-radius: 6px;
}
.gs-ev-flow-entry { border-left: 3px solid #00AA00; }
.gs-ev-flow-sink { border-left: 3px solid #D50000; }
.gs-ev-flow-step-header {
  display: flex; align-items: center; gap: 6px;
}
.gs-ev-flow-step-idx {
  min-width: 20px; height: 20px;
  display: flex; align-items: center; justify-content: center;
  border-radius: 50%; font-size: 10px; font-weight: 700;
  background: rgba(75, 159, 213, 0.12); color: var(--gs-primary);
}
.gs-ev-flow-step-detail {
  display: flex; gap: 12px; margin-top: 4px; font-size: 11px;
}
.gs-ev-flow-param { color: var(--gs-text-secondary); }
.gs-ev-flow-param code { font-family: var(--gs-font-mono); font-size: 11px; }
.gs-ev-flow-transform { color: #E57F00; }
.gs-ev-flow-transform-code {
  background: rgba(229, 127, 0, 0.1); padding: 1px 4px; border-radius: 3px;
  font-family: var(--gs-font-mono); font-size: 10px; color: #E57F00;
}
.gs-ev-flow-transform-expr {
  font-size: 10px; color: var(--gs-text-muted);
}
.gs-ev-flow-connector {
  text-align: center; padding: 2px 0; color: var(--gs-text-muted); font-size: 12px;
}
.gs-ev-flow-arrow { color: var(--gs-primary); }

/* ── 边界值传播链 ───────────────────── */
.gs-ev-boundary-chain { margin-top: 8px; }

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
