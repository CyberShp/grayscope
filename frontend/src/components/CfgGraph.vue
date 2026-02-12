<template>
  <div class="gs-cfg-graph">
    <div class="gs-cfg-header">
      <span class="gs-cfg-title">控制流图 (CFG)</span>
      <span class="gs-cfg-legend">
        <span class="gs-cfg-legend-item"><span class="gs-cfg-dot gs-cfg-dot-normal"></span>正常路径</span>
        <span class="gs-cfg-legend-item"><span class="gs-cfg-dot gs-cfg-dot-error"></span>错误路径</span>
        <span class="gs-cfg-legend-item"><span class="gs-cfg-dot gs-cfg-dot-cleanup"></span>清理路径</span>
        <span class="gs-cfg-legend-item"><span class="gs-cfg-dot" style="background:#0D9488;"></span>状态判断</span>
        <span class="gs-cfg-legend-item"><span class="gs-cfg-dot gs-cfg-dot-uncovered"></span>未覆盖</span>
      </span>
    </div>
    <v-chart :option="chartOption" :style="{ height: chartHeight + 'px', width: '100%' }" autoresize />

    <!-- 分支推荐测试数据区 -->
    <div class="gs-cfg-test-data" v-if="conditionExpr">
      <div class="gs-cfg-test-header">
        <el-icon style="color:var(--gs-primary);"><DataLine /></el-icon>
        <span>分支测试数据推荐</span>
      </div>

      <div class="gs-cfg-branch-cards">
        <!-- True 分支 -->
        <div class="gs-cfg-branch-card gs-cfg-branch-true"
             :class="{ 'gs-cfg-branch-active': highlightBranch === 'true' }"
             @click="selectBranch('true')" style="cursor:pointer;">
          <div class="gs-cfg-branch-label">
            <el-tag type="success" size="small">TRUE 分支</el-tag>
            <span class="gs-cfg-branch-desc">条件成立: <code>{{ conditionExpr }}</code></span>
            <span v-if="highlightBranch === 'true'" class="gs-cfg-highlight-hint">← CFG 已高亮</span>
          </div>
          <div class="gs-cfg-test-values">
            <div class="gs-cfg-test-row" v-for="(val, i) in trueBranchValues" :key="'t'+i">
              <span class="gs-cfg-test-idx">T{{ i+1 }}</span>
              <code class="gs-cfg-test-val">{{ val.input }}</code>
              <span class="gs-cfg-test-expect">→ {{ val.expected }}</span>
            </div>
          </div>
        </div>

        <!-- False 分支 -->
        <div class="gs-cfg-branch-card gs-cfg-branch-false"
             :class="{ 'gs-cfg-branch-active': highlightBranch === 'false' }"
             @click="selectBranch('false')" style="cursor:pointer;">
          <div class="gs-cfg-branch-label">
            <el-tag :type="pathType === 'error' ? 'danger' : 'warning'" size="small">FALSE 分支</el-tag>
            <span class="gs-cfg-branch-desc">条件不成立: <code>{{ negatedCondition }}</code></span>
            <span v-if="highlightBranch === 'false'" class="gs-cfg-highlight-hint">← CFG 已高亮</span>
          </div>
          <div class="gs-cfg-test-values">
            <div class="gs-cfg-test-row" v-for="(val, i) in falseBranchValues" :key="'f'+i">
              <span class="gs-cfg-test-idx">F{{ i+1 }}</span>
              <code class="gs-cfg-test-val">{{ val.input }}</code>
              <span class="gs-cfg-test-expect">→ {{ val.expected }}</span>
            </div>
          </div>
        </div>

        <!-- 边界值 -->
        <div class="gs-cfg-branch-card gs-cfg-branch-boundary" v-if="boundaryValues.length"
             :class="{ 'gs-cfg-branch-active': highlightBranch === 'boundary' }"
             @click="selectBranch('boundary')" style="cursor:pointer;">
          <div class="gs-cfg-branch-label">
            <el-tag type="warning" size="small">边界值</el-tag>
            <span class="gs-cfg-branch-desc">条件翻转临界点</span>
            <span v-if="highlightBranch === 'boundary'" class="gs-cfg-highlight-hint">← CFG 已高亮</span>
          </div>
          <div class="gs-cfg-test-values">
            <div class="gs-cfg-test-row" v-for="(val, i) in boundaryValues" :key="'b'+i">
              <span class="gs-cfg-test-idx">B{{ i+1 }}</span>
              <code class="gs-cfg-test-val">{{ val.input }}</code>
              <span class="gs-cfg-test-expect">→ {{ val.expected }}</span>
            </div>
          </div>
        </div>
      </div>

      <!-- 用户自定义测试数据 -->
      <div class="gs-cfg-custom">
        <div class="gs-cfg-custom-header" @click="showCustom = !showCustom" style="cursor:pointer;">
          <el-icon><Edit /></el-icon>
          <span>自定义测试数据</span>
          <el-icon style="margin-left:auto;"><ArrowDown v-if="!showCustom" /><ArrowUp v-else /></el-icon>
        </div>
        <div v-if="showCustom" class="gs-cfg-custom-body">
          <div v-for="(item, idx) in customInputs" :key="idx" class="gs-cfg-custom-row">
            <el-input v-model="item.input" placeholder="输入值，例如: n=0" size="small" style="flex:2;" />
            <el-input v-model="item.expected" placeholder="预期结果" size="small" style="flex:2;" />
            <el-select v-model="item.branch" placeholder="分支" size="small" style="width:100px;">
              <el-option label="TRUE" value="true" />
              <el-option label="FALSE" value="false" />
              <el-option label="边界" value="boundary" />
            </el-select>
            <el-button size="small" type="danger" plain :icon="Delete" @click="customInputs.splice(idx, 1)" circle />
          </div>
          <el-button size="small" type="primary" plain @click="addCustomInput" style="margin-top:8px;">
            <el-icon><Plus /></el-icon> 添加测试数据
          </el-button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, ref } from 'vue'
import { use } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import { GraphChart } from 'echarts/charts'
import { TooltipComponent } from 'echarts/components'
import VChart from 'vue-echarts'
import { DataLine, Edit, Plus, Delete, ArrowDown, ArrowUp } from '@element-plus/icons-vue'

use([CanvasRenderer, GraphChart, TooltipComponent])

const props = defineProps({
  evidence: { type: Object, default: () => ({}) },
  finding: { type: Object, default: () => ({}) },
})

const showCustom = ref(false)
const customInputs = ref([])
const highlightBranch = ref('')  // 'true' | 'false' | 'boundary' | ''

function addCustomInput() {
  customInputs.value.push({ input: '', expected: '', branch: 'true' })
}

function selectBranch(branch) {
  highlightBranch.value = highlightBranch.value === branch ? '' : branch
}

const pathType = computed(() => props.evidence.path_type || 'normal')
const branchId = computed(() => props.evidence.branch_id || '')
const conditionExpr = computed(() => props.evidence.condition_expr || '')

// 生成条件的否定形式
const negatedCondition = computed(() => {
  const expr = conditionExpr.value
  if (!expr) return ''
  const clean = expr.replace(/^\(|\)$/g, '').trim()
  // 处理各种操作符的否定
  if (clean.includes('==')) return clean.replace('==', '!=')
  if (clean.includes('!=')) return clean.replace('!=', '==')
  if (clean.includes('<=')) return clean.replace('<=', '>')
  if (clean.includes('>=')) return clean.replace('>=', '<')
  // 注意: < 和 > 需要在 <= >= 之后处理
  if (clean.includes(' < ')) return clean.replace(' < ', ' >= ')
  if (clean.includes(' > ')) return clean.replace(' > ', ' <= ')
  // 处理 ! 前缀
  if (clean.startsWith('!')) return clean.substring(1)
  // 处理 && || 复合条件
  if (clean.includes('&&') || clean.includes('||')) return `!(${clean})`
  // 默认加 !
  return `!${clean}`
})

// 推导推荐测试数据
const trueBranchValues = computed(() => {
  const expr = conditionExpr.value
  if (!expr) return []
  return _deriveTrueValues(expr)
})

const falseBranchValues = computed(() => {
  const expr = conditionExpr.value
  if (!expr) return []
  return _deriveFalseValues(expr)
})

const boundaryValues = computed(() => {
  const expr = conditionExpr.value
  if (!expr) return []
  return _deriveBoundaryValues(expr)
})

// ---- 从条件表达式解析结构 ----
function _parseCondition(expr) {
  const clean = expr.replace(/^\(|\)$/g, '').trim()
  // 复合条件: a && b, a || b
  if (clean.includes('&&') || clean.includes('||')) {
    const op = clean.includes('&&') ? '&&' : '||'
    const parts = clean.split(op).map(s => s.trim())
    return { kind: 'compound', op, parts, raw: clean }
  }
  // 比较: lhs OP rhs  (== != <= >= < >)
  const cmpMatch = clean.match(/^(.+?)\s*(==|!=|<=|>=|<|>)\s*(.+)$/)
  if (cmpMatch) {
    const [, lhs, op, rhs] = cmpMatch
    const isNumeric = /^-?\d+$/.test(rhs.trim())
    return { kind: 'compare', lhs: lhs.trim(), op, rhs: rhs.trim(), isNumeric, raw: clean }
  }
  // 取反: !expr
  if (clean.startsWith('!')) {
    return { kind: 'negate', variable: clean.substring(1).trim(), raw: clean }
  }
  // 单变量 (truthy): variable
  return { kind: 'truthy', variable: clean, raw: clean }
}

function _deriveTrueValues(expr) {
  const cond = _parseCondition(expr)

  if (cond.kind === 'compare') {
    const { lhs, op, rhs, isNumeric } = cond
    if (op === '==' && rhs === 'NULL') {
      return [
        { input: `${lhs} = NULL`, expected: '条件为真，进入错误/空值处理' },
      ]
    }
    if (op === '==' && rhs === '0') {
      return [
        { input: `${lhs} = 0`, expected: '条件为真，进入分支' },
      ]
    }
    if (op === '==' && !isNumeric) {
      // 命名常量: init == SDS_NOINIT, type == SDS_TYPE_5
      return [
        { input: `${lhs} = ${rhs}`, expected: `条件为真，执行 ${lhs} == ${rhs} 对应的逻辑` },
      ]
    }
    if (op === '==' && isNumeric) {
      return [
        { input: `${lhs} = ${rhs}`, expected: '精确匹配，条件为真' },
      ]
    }
    if (op === '!=' && rhs === 'NULL') {
      return [
        { input: `${lhs} = 有效指针（非 NULL）`, expected: '指针有效，条件为真' },
      ]
    }
    if (op === '!=' && !isNumeric) {
      return [
        { input: `${lhs} = 任意非 ${rhs} 的值`, expected: `${lhs} 不等于 ${rhs}，条件为真` },
      ]
    }
    if (op === '<' || op === '<=') {
      const numVal = isNumeric ? parseInt(rhs) : null
      if (numVal !== null) {
        const v = op === '<' ? numVal - 1 : numVal
        return [
          { input: `${lhs} = ${v}`, expected: `满足 ${lhs} ${op} ${rhs}` },
          { input: `${lhs} = 0`, expected: '最小典型值' },
        ]
      }
      return [{ input: `${lhs} < ${rhs}（取小于的值）`, expected: '条件为真' }]
    }
    if (op === '>' || op === '>=') {
      const numVal = isNumeric ? parseInt(rhs) : null
      if (numVal !== null) {
        const v = op === '>' ? numVal + 1 : numVal
        return [
          { input: `${lhs} = ${v}`, expected: `满足 ${lhs} ${op} ${rhs}` },
          { input: `${lhs} = ${numVal * 2 || 10}`, expected: '远大于阈值' },
        ]
      }
      return [{ input: `${lhs} > ${rhs}（取大于的值）`, expected: '条件为真' }]
    }
  }

  if (cond.kind === 'negate') {
    // !ptr, !flag
    return [
      { input: `${cond.variable} = NULL / 0 / false`, expected: `!${cond.variable} 为真，进入分支` },
    ]
  }
  if (cond.kind === 'truthy') {
    return [
      { input: `${cond.variable} = 有效非零值`, expected: `${cond.variable} 为真，进入分支` },
    ]
  }
  if (cond.kind === 'compound') {
    const sub = cond.parts.map(p => _parseCondition(p))
    const lines = sub.map(s => {
      if (s.kind === 'compare') return `${s.lhs} ${s.op} ${s.rhs}`
      if (s.kind === 'negate') return `${s.variable} = NULL/0`
      if (s.kind === 'truthy') return `${s.variable} = 非零值`
      return s.raw
    })
    const opDesc = cond.op === '&&' ? '同时满足' : '至少一个满足'
    return [
      { input: lines.join('；'), expected: `${opDesc}，条件为真` },
    ]
  }

  return [{ input: `使 ${expr} 为真`, expected: '进入 true 分支' }]
}

function _deriveFalseValues(expr) {
  const cond = _parseCondition(expr)

  if (cond.kind === 'compare') {
    const { lhs, op, rhs, isNumeric } = cond
    if (op === '==' && rhs === 'NULL') {
      return [
        { input: `${lhs} = 有效指针（非 NULL）`, expected: '条件为假，跳过空值处理' },
      ]
    }
    if (op === '==' && rhs === '0') {
      return [
        { input: `${lhs} = 非零值（如 1, -1）`, expected: '条件为假' },
      ]
    }
    if (op === '==' && !isNumeric) {
      return [
        { input: `${lhs} = 非 ${rhs} 的其他值`, expected: `${lhs} != ${rhs}，跳过该分支` },
        { input: `${lhs} = NULL / 默认值`, expected: `${lhs} != ${rhs}，走 else 路径` },
      ]
    }
    if (op === '==' && isNumeric) {
      const n = parseInt(rhs)
      return [
        { input: `${lhs} = ${n + 1}`, expected: '不等于目标值，条件为假' },
        { input: `${lhs} = ${n - 1}`, expected: '不等于目标值，条件为假' },
      ]
    }
    if (op === '!=' && rhs === 'NULL') {
      return [
        { input: `${lhs} = NULL`, expected: '指针为空，条件为假' },
      ]
    }
    if (op === '!=' && !isNumeric) {
      return [
        { input: `${lhs} = ${rhs}`, expected: `${lhs} 等于 ${rhs}，条件为假` },
      ]
    }
    if (op === '<' || op === '<=') {
      const numVal = isNumeric ? parseInt(rhs) : null
      if (numVal !== null) {
        const v = op === '<' ? numVal : numVal + 1
        return [
          { input: `${lhs} = ${v}`, expected: `不满足 ${lhs} ${op} ${rhs}` },
          { input: `${lhs} = ${numVal + 10}`, expected: '远大于阈值' },
        ]
      }
      return [{ input: `${lhs} >= ${rhs}`, expected: '条件为假' }]
    }
    if (op === '>' || op === '>=') {
      const numVal = isNumeric ? parseInt(rhs) : null
      if (numVal !== null) {
        const v = op === '>' ? numVal : numVal - 1
        return [
          { input: `${lhs} = ${v}`, expected: `不满足 ${lhs} ${op} ${rhs}` },
          { input: `${lhs} = 0`, expected: '远小于阈值' },
        ]
      }
      return [{ input: `${lhs} <= ${rhs}`, expected: '条件为假' }]
    }
  }

  if (cond.kind === 'negate') {
    return [
      { input: `${cond.variable} = 有效非零值 / true`, expected: `!${cond.variable} 为假，跳过分支` },
    ]
  }
  if (cond.kind === 'truthy') {
    return [
      { input: `${cond.variable} = NULL / 0 / false`, expected: `${cond.variable} 为假，跳过分支` },
    ]
  }
  if (cond.kind === 'compound') {
    const sub = cond.parts.map(p => _parseCondition(p))
    if (cond.op === '&&') {
      // 破坏任一子条件即可
      const first = sub[0]
      const hint = first.kind === 'compare'
        ? `${first.lhs} 不满足 ${first.op} ${first.rhs}`
        : first.kind === 'negate' ? `${first.variable} = 非零值` : `${first.raw} 为假`
      return [{ input: hint, expected: '任一子条件为假，整体为假' }]
    } else {
      const lines = sub.map(s => {
        if (s.kind === 'compare') return `${s.lhs} 不满足 ${s.op} ${s.rhs}`
        if (s.kind === 'negate') return `${s.variable} = 非零值`
        return `${s.raw} 为假`
      })
      return [{ input: lines.join('；'), expected: '所有子条件均为假' }]
    }
  }

  return [{ input: `使 ${expr} 为假`, expected: '进入 false 分支' }]
}

function _deriveBoundaryValues(expr) {
  const cond = _parseCondition(expr)

  if (cond.kind === 'compare' && cond.isNumeric) {
    const n = parseInt(cond.rhs)
    if (cond.op === '==' || cond.op === '!=') {
      return [
        { input: `${cond.lhs} = ${n}`, expected: '精确匹配' },
        { input: `${cond.lhs} = ${n - 1}`, expected: '差一 (off-by-one)' },
        { input: `${cond.lhs} = ${n + 1}`, expected: '差一 (off-by-one)' },
      ]
    }
    if (cond.op === '<') {
      return [
        { input: `${cond.lhs} = ${n - 1}`, expected: '刚好满足' },
        { input: `${cond.lhs} = ${n}`, expected: '临界值（不满足）' },
        { input: `${cond.lhs} = ${n + 1}`, expected: '超过临界值' },
      ]
    }
    if (cond.op === '<=') {
      return [
        { input: `${cond.lhs} = ${n - 1}`, expected: '刚好满足' },
        { input: `${cond.lhs} = ${n}`, expected: '恰好在边界上（满足）' },
        { input: `${cond.lhs} = ${n + 1}`, expected: '刚好不满足' },
      ]
    }
    if (cond.op === '>') {
      return [
        { input: `${cond.lhs} = ${n + 1}`, expected: '刚好满足' },
        { input: `${cond.lhs} = ${n}`, expected: '临界值（不满足）' },
        { input: `${cond.lhs} = ${n - 1}`, expected: '低于临界值' },
      ]
    }
    if (cond.op === '>=') {
      return [
        { input: `${cond.lhs} = ${n + 1}`, expected: '刚好满足' },
        { input: `${cond.lhs} = ${n}`, expected: '恰好在边界上（满足）' },
        { input: `${cond.lhs} = ${n - 1}`, expected: '刚好不满足' },
      ]
    }
  }

  // 对于命名常量比较 (== SDS_NOINIT), 无法生成有意义的边界值
  if (cond.kind === 'compare' && !cond.isNumeric && (cond.op === '==' || cond.op === '!=')) {
    return [
      { input: `${cond.lhs} = ${cond.rhs}`, expected: '精确匹配该常量' },
      { input: `${cond.lhs} = NULL`, expected: '空值边界' },
      { input: `${cond.lhs} = 其他有效值`, expected: '非匹配值' },
    ]
  }

  return []
}

// 从 evidence 中的 pred/succ 节点和分支信息构建简化 CFG
const graphData = computed(() => {
  const funcName = props.finding.symbol_name || '函数入口'
  const pt = pathType.value

  const nodes = []
  const links = []

  nodes.push({ name: 'entry', label: funcName + '()', category: 'normal', symbolSize: 40, x: 200, y: 30 })

  if (conditionExpr.value) {
    nodes.push({ name: 'condition', label: conditionExpr.value, category: 'condition', symbolSize: 50, x: 200, y: 120, symbol: 'diamond' })
    links.push({ source: 'entry', target: 'condition' })

    const _trueLabel = pt === 'error' ? '正常路径' : pt === 'state' ? `匹配 (${conditionExpr.value})` : '条件成立'
    const _falseLabel = pt === 'error' ? '错误处理'
      : pt === 'cleanup' ? '资源清理'
      : pt === 'state' ? `不匹配 (${negatedCondition.value})`
      : pt === 'boundary' ? '越界路径'
      : '条件不成立'
    const _falseCat = pt === 'error' ? 'error' : pt === 'cleanup' ? 'cleanup' : pt === 'state' ? 'state' : 'uncovered'

    nodes.push({ name: 'true_branch', label: _trueLabel, category: 'normal', symbolSize: 35, x: 100, y: 220 })
    links.push({ source: 'condition', target: 'true_branch', label: { show: true, formatter: 'true' } })

    nodes.push({
      name: 'false_branch',
      label: _falseLabel,
      category: _falseCat,
      symbolSize: 35, x: 300, y: 220,
    })
    links.push({ source: 'condition', target: 'false_branch', label: { show: true, formatter: 'false' }, lineStyle: { type: 'dashed', color: pt === 'error' ? '#D50000' : '#E57F00' } })

    if (pt === 'error') {
      nodes.push({ name: 'error_return', label: '错误返回', category: 'error', symbolSize: 30, x: 300, y: 310 })
      links.push({ source: 'false_branch', target: 'error_return' })
    } else if (pt === 'cleanup') {
      nodes.push({ name: 'cleanup_action', label: '释放资源', category: 'cleanup', symbolSize: 30, x: 300, y: 310 })
      links.push({ source: 'false_branch', target: 'cleanup_action' })
    }

    nodes.push({ name: 'exit', label: '返回', category: 'normal', symbolSize: 30, x: 200, y: 380 })
    links.push({ source: 'true_branch', target: 'exit' })
    if (pt === 'error') {
      links.push({ source: 'error_return', target: 'exit', lineStyle: { type: 'dotted' } })
    } else if (pt === 'cleanup') {
      links.push({ source: 'cleanup_action', target: 'exit', lineStyle: { type: 'dotted' } })
    } else {
      links.push({ source: 'false_branch', target: 'exit' })
    }
  } else {
    nodes.push({
      name: 'target',
      label: branchId.value || '目标分支',
      category: pt === 'error' ? 'error' : pt === 'cleanup' ? 'cleanup' : 'uncovered',
      symbolSize: 40, x: 200, y: 120,
    })
    links.push({ source: 'entry', target: 'target' })
    nodes.push({ name: 'exit', label: '返回', category: 'normal', symbolSize: 30, x: 200, y: 220 })
    links.push({ source: 'target', target: 'exit' })
  }

  return { nodes, links }
})

const chartHeight = computed(() => conditionExpr.value ? 420 : 260)

const categoryColors = {
  normal: '#4B9FD5',
  condition: '#8B5CF6',
  error: '#D50000',
  cleanup: '#E57F00',
  state: '#0D9488',
  uncovered: '#999',
}

// 高亮路径中的节点名集合
const highlightedNodes = computed(() => {
  const hl = highlightBranch.value
  if (!hl) return new Set()
  if (hl === 'true') return new Set(['entry', 'condition', 'true_branch', 'exit'])
  if (hl === 'false') return new Set(['entry', 'condition', 'false_branch', 'error_return', 'cleanup_action', 'exit'])
  if (hl === 'boundary') return new Set(['entry', 'condition', 'true_branch', 'false_branch', 'exit'])
  return new Set()
})

const highlightedEdgeKeys = computed(() => {
  const hl = highlightBranch.value
  if (!hl) return new Set()
  if (hl === 'true') return new Set(['entry→condition', 'condition→true_branch', 'true_branch→exit'])
  if (hl === 'false') return new Set(['entry→condition', 'condition→false_branch', 'false_branch→error_return', 'false_branch→cleanup_action', 'false_branch→exit', 'error_return→exit', 'cleanup_action→exit'])
  if (hl === 'boundary') return new Set(['entry→condition', 'condition→true_branch', 'condition→false_branch'])
  return new Set()
})

const chartOption = computed(() => {
  const hl = highlightBranch.value
  const hlNodes = highlightedNodes.value
  const hlEdges = highlightedEdgeKeys.value
  const dimOpacity = hl ? 0.15 : 1

  return {
    tooltip: {
      trigger: 'item',
      formatter: (params) => {
        if (params.dataType === 'node') return params.data.label
        return ''
      }
    },
    series: [{
      type: 'graph',
      layout: 'none',
      roam: false,
      label: { show: true, formatter: '{b}', fontSize: 11, color: '#333' },
      edgeLabel: { fontSize: 10, color: '#666' },
      categories: [
        { name: 'normal', itemStyle: { color: categoryColors.normal } },
        { name: 'condition', itemStyle: { color: categoryColors.condition } },
        { name: 'error', itemStyle: { color: categoryColors.error } },
        { name: 'cleanup', itemStyle: { color: categoryColors.cleanup } },
        { name: 'state', itemStyle: { color: categoryColors.state } },
        { name: 'uncovered', itemStyle: { color: categoryColors.uncovered } },
      ],
      data: graphData.value.nodes.map(n => {
        const isHl = !hl || hlNodes.has(n.name)
        const baseColor = categoryColors[n.category] || '#4B9FD5'
        return {
          ...n, name: n.label,
          category: ['normal', 'condition', 'error', 'cleanup', 'state', 'uncovered'].indexOf(n.category),
          symbolSize: isHl && hl ? (n.symbolSize || 35) * 1.2 : n.symbolSize,
          itemStyle: {
            color: baseColor,
            opacity: isHl ? 1 : dimOpacity,
            borderColor: isHl && hl ? '#FFD600' : 'transparent',
            borderWidth: isHl && hl ? 3 : 0,
          },
          label: {
            color: isHl ? '#333' : '#ccc',
            fontWeight: isHl && hl ? 'bold' : 'normal',
          },
        }
      }),
      links: graphData.value.links.map(l => {
        const edgeKey = `${l.source}→${l.target}`
        const isHl = !hl || hlEdges.has(edgeKey)
        return {
          ...l,
          source: graphData.value.nodes.find(n => n.name === l.source)?.label,
          target: graphData.value.nodes.find(n => n.name === l.target)?.label,
          lineStyle: {
            color: isHl && hl ? (hl === 'true' ? '#22C55E' : hl === 'false' ? '#EF4444' : '#F59E0B') : '#999',
            curveness: 0,
            width: isHl && hl ? 4 : 2,
            opacity: isHl ? 1 : dimOpacity,
            ...(l.lineStyle || {}),
            ...(isHl && hl ? { type: 'solid' } : {}),
          },
          label: l.label ? {
            ...l.label,
            color: isHl && hl ? '#000' : '#666',
            fontWeight: isHl && hl ? 'bold' : 'normal',
          } : undefined,
        }
      }),
      lineStyle: { color: '#999', width: 2 },
      edgeSymbol: ['none', 'arrow'],
      edgeSymbolSize: 8,
      animation: true,
      animationDuration: 300,
    }],
  }
})
</script>

<style scoped>
.gs-cfg-graph {
  background: var(--gs-surface);
  border: 1px solid var(--gs-border);
  border-radius: var(--gs-radius-md);
  padding: 12px;
}
.gs-cfg-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
.gs-cfg-title { font-size: 12px; font-weight: 600; color: var(--gs-text-muted); }
.gs-cfg-legend { display: flex; gap: 12px; }
.gs-cfg-legend-item { display: flex; align-items: center; gap: 4px; font-size: 11px; color: var(--gs-text-muted); }
.gs-cfg-dot { width: 8px; height: 8px; border-radius: 50%; }
.gs-cfg-dot-normal { background: #4B9FD5; }
.gs-cfg-dot-error { background: #D50000; }
.gs-cfg-dot-cleanup { background: #E57F00; }
.gs-cfg-dot-uncovered { background: #999; }

/* 测试数据推荐区 */
.gs-cfg-test-data {
  margin-top: 12px;
  border-top: 1px solid var(--gs-border);
  padding-top: 12px;
}
.gs-cfg-test-header {
  display: flex; align-items: center; gap: 6px;
  font-size: 13px; font-weight: 600; color: var(--gs-text-primary);
  margin-bottom: 12px;
}

.gs-cfg-branch-cards {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
  gap: 10px;
  margin-bottom: 12px;
}
.gs-cfg-branch-card {
  border: 1px solid var(--gs-border);
  border-radius: 8px;
  padding: 10px;
}
.gs-cfg-branch-true { border-left: 3px solid #00AA00; transition: all 0.2s; }
.gs-cfg-branch-false { border-left: 3px solid #D50000; transition: all 0.2s; }
.gs-cfg-branch-boundary { border-left: 3px solid #E57F00; transition: all 0.2s; }
.gs-cfg-branch-card:hover { background: rgba(139, 92, 246, 0.04); }
.gs-cfg-branch-active { box-shadow: 0 0 0 2px rgba(139, 92, 246, 0.4); background: rgba(139, 92, 246, 0.06) !important; }
.gs-cfg-highlight-hint { font-size: 11px; color: var(--gs-primary); font-weight: 600; margin-left: auto; }

.gs-cfg-branch-label {
  display: flex; align-items: center; gap: 8px;
  margin-bottom: 8px;
}
.gs-cfg-branch-desc {
  font-size: 12px; color: var(--gs-text-secondary);
}
.gs-cfg-branch-desc code {
  background: rgba(139, 92, 246, 0.1);
  padding: 1px 4px;
  border-radius: 3px;
  font-size: 11px;
}

.gs-cfg-test-values { display: flex; flex-direction: column; gap: 4px; }
.gs-cfg-test-row {
  display: flex; align-items: center; gap: 6px;
  font-size: 12px;
}
.gs-cfg-test-idx {
  min-width: 24px;
  font-weight: 700;
  color: var(--gs-text-muted);
  font-family: var(--gs-font-mono);
  font-size: 11px;
}
.gs-cfg-test-val {
  font-family: var(--gs-font-mono);
  font-size: 11px;
  background: var(--gs-bg);
  padding: 2px 6px;
  border-radius: 3px;
}
.gs-cfg-test-expect {
  font-size: 11px;
  color: var(--gs-text-muted);
}

/* 自定义输入区 */
.gs-cfg-custom {
  background: var(--gs-bg);
  border-radius: 8px;
  overflow: hidden;
}
.gs-cfg-custom-header {
  display: flex; align-items: center; gap: 6px;
  padding: 8px 12px;
  font-size: 12px; font-weight: 600;
  color: var(--gs-text-secondary);
}
.gs-cfg-custom-body {
  padding: 8px 12px 12px;
}
.gs-cfg-custom-row {
  display: flex; align-items: center; gap: 6px;
  margin-bottom: 6px;
}
</style>
