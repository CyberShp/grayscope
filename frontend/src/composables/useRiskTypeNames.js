/**
 * Maps risk_type (analyzer output) to Chinese display names.
 * Used in facets, dropdowns, and finding detail views.
 */

const RISK_TYPE_NAMES = {
  // branch_path
  branch_error: '分支错误路径',
  branch_cleanup: '分支清理路径',
  branch_boundary: '分支边界',
  branch_state: '分支状态',
  branch_normal: '分支正常路径',
  branch_missing_test: '分支缺测',
  branch_high_complexity: '分支高复杂度',
  branch_switch_no_default: 'switch 缺 default',

  // boundary_value
  boundary_miss: '边界遗漏',
  invalid_input_gap: '无效输入缺口',

  // error_path
  missing_cleanup: '缺少清理',
  inconsistent_errno_mapping: '错误码映射不一致',
  silent_error_swallow: '静默吞错',
  cross_function_resource_leak: '跨函数资源泄漏',

  // call_graph
  high_fan_out: '高扇出',
  deep_impact_surface: '影响面深',
  hotspot_regression_risk: '热点回归风险',

  // data_flow
  deep_param_propagation: '参数深传播',
  external_to_sensitive: '外部到敏感',
  value_transform_risk: '值变换风险',

  // concurrency
  race_write_without_lock: '无锁竞态写',
  lock_order_inversion: '锁顺序反转',
  atomicity_gap: '原子性缺口',
  cross_function_deadlock_risk: '跨函数死锁风险',
  cross_function_race: '跨函数竞态',

  // diff_impact
  changed_core_path: '核心路径变更',
  transitive_impact: '传递影响',

  // coverage_map
  high_risk_low_coverage: '高风险低覆盖',
  critical_path_uncovered: '关键路径未覆盖',
}

const RISK_TYPE_IDS = Object.keys(RISK_TYPE_NAMES)

/**
 * @param {string} riskType - Raw risk_type string from API
 * @returns {string} Chinese display name, or original string if unknown
 */
export function getRiskTypeName(riskType) {
  if (!riskType) return ''
  return RISK_TYPE_NAMES[riskType] ?? riskType
}

/**
 * Options for risk type select dropdowns: { id, name }.
 * Reactive not required (static list); export as array for consistency with useModuleNames moduleList shape.
 */
export const riskTypeOptions = RISK_TYPE_IDS.map((id) => ({
  id,
  name: RISK_TYPE_NAMES[id],
}))
