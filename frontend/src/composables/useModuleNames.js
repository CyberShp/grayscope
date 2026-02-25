const MODULE_NAMES = {
  branch_path: '分支路径分析',
  boundary_value: '边界值分析',
  error_path: '错误路径分析',
  call_graph: '调用图构建',
  path_and_resource: '路径与资源',
  exception: '异常分支分析',
  protocol: '协议报文分析',
  data_flow: '数据流分析',
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
  call_graph: '构建函数级调用图（含参数映射），识别高扇出/扇入函数',
  path_and_resource: '合并分支路径与错误路径，一次产出路径分类与资源发现',
  exception: 'V2 支柱一：异常分支、资源生命周期与错误传播',
  protocol: 'V2 支柱三：协议/报文序列（占位，后续接入 pcap/仪器）',
  data_flow: '跨函数参数传播链追踪，值域变换检测，外部输入污点分析',
  concurrency: '检测共享变量无锁写入、跨函数锁链死锁等并发风险',
  diff_impact: '分析代码变更影响，智能深度双向追踪回归风险',
  coverage_map: '叠加覆盖率数据与风险发现，标记高风险低覆盖区域',
  postmortem: '分析逃逸缺陷，推断根因链，生成预防性测试',
  knowledge_pattern: '提取缺陷模式，持久化到知识库',
}

/** 核心分析模块（11 个），与后端 ANALYSIS_MODULES 一致；不含事后分析 postmortem / knowledge_pattern */
const ANALYSIS_MODULES = [
  'branch_path', 'boundary_value', 'error_path', 'call_graph',
  'path_and_resource', 'exception', 'protocol',
  'data_flow', 'concurrency', 'diff_impact', 'coverage_map',
]

export function useModuleNames() {
  const getDisplayName = (moduleId) => MODULE_NAMES[moduleId] || moduleId
  const getDescription = (moduleId) => MODULE_DESCRIPTIONS[moduleId] || ''
  const moduleList = ANALYSIS_MODULES.map(id => ({ id, name: MODULE_NAMES[id] || id }))
  return { MODULE_NAMES, MODULE_DESCRIPTIONS, ANALYSIS_MODULES, moduleList, getDisplayName, getDescription }
}
