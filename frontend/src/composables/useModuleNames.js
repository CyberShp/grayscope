const MODULE_NAMES = {
  branch_path: '分支路径分析',
  boundary_value: '边界值分析',
  error_path: '错误路径分析',
  call_graph: '调用图构建',
  concurrency: '并发风险分析',
  diff_impact: '差异影响分析',
  coverage_map: '覆盖率映射',
  postmortem: '事后分析',
  knowledge_pattern: '缺陷知识库',
}

const MODULE_DESCRIPTIONS = {
  branch_path: '识别代码分支，分类错误/清理/边界/正常路径',
  boundary_value: '提取比较表达式和数组访问，推导边界测试候选值',
  error_path: '识别资源分配/释放模式、错误返回值一致性',
  call_graph: '构建函数级调用图，识别高扇出/扇入函数',
  concurrency: '检测共享变量无锁写入、锁序反转等并发风险',
  diff_impact: '分析代码变更影响，通过调用图传播回归风险',
  coverage_map: '叠加覆盖率数据与风险发现，标记高风险低覆盖区域',
  postmortem: '分析逃逸缺陷，推断根因链，生成预防性测试',
  knowledge_pattern: '提取缺陷模式，持久化到知识库',
}

const ANALYSIS_MODULES = [
  'branch_path', 'boundary_value', 'error_path', 'call_graph',
  'concurrency', 'diff_impact', 'coverage_map',
]

export function useModuleNames() {
  const getDisplayName = (moduleId) => MODULE_NAMES[moduleId] || moduleId
  const getDescription = (moduleId) => MODULE_DESCRIPTIONS[moduleId] || ''
  const moduleList = ANALYSIS_MODULES.map(id => ({ id, name: MODULE_NAMES[id] || id }))
  return { MODULE_NAMES, MODULE_DESCRIPTIONS, ANALYSIS_MODULES, moduleList, getDisplayName, getDescription }
}
