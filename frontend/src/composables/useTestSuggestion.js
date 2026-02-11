/**
 * 前端侧的测试建议生成 — 镜像后端 export_service.py 的逻辑，
 * 使得在发现详情中可以不依赖额外 API 直接内联展示测试建议。
 */

const SEV_PRIORITY = { S0: 'P0-紧急', S1: 'P1-高', S2: 'P2-中', S3: 'P3-低' }

function getTestObjective(finding) {
  const sym = finding.symbol_name || '目标函数'
  const rt = finding.risk_type || ''
  const mapping = {
    branch_missing_test: `验证 ${sym}() 中的未覆盖分支是否有对应测试`,
    branch_error: `验证 ${sym}() 中的错误处理分支是否正确触发和处理`,
    branch_cleanup: `验证 ${sym}() 中的清理路径是否释放所有资源`,
    branch_boundary: `验证 ${sym}() 中的边界条件分支是否正确处理边界值`,
    branch_normal: `验证 ${sym}() 的正常执行路径`,
    error_path: `验证 ${sym}() 中的错误返回路径是否正确处理`,
    cleanup_path: `验证 ${sym}() 中的清理路径是否正确释放资源`,
    boundary_miss: `测试 ${sym}() 中约束条件的边界值，包括 off-by-one`,
    invalid_input_gap: `验证 ${sym}() 对非法输入的拒绝与校验`,
    missing_cleanup: `验证 ${sym}() 在错误路径上是否正确释放所有资源`,
    inconsistent_errno_mapping: `验证 ${sym}() 中的错误码映射是否一致`,
    silent_error_swallow: `验证 ${sym}() 中的错误是否被正确传播给调用者`,
    race_write_without_lock: `验证 ${sym}() 中共享变量访问的线程安全性`,
    lock_order_inversion: `验证 ${sym}() 中锁获取是否存在死锁风险`,
    atomicity_gap: `验证 ${sym}() 中的复合操作是否具有原子性`,
    changed_core_path: `对修改的函数 ${sym}() 进行回归测试`,
    transitive_impact: `对受上游变更影响的函数 ${sym}() 进行回归测试`,
    high_risk_low_coverage: `提高高风险函数 ${sym}() 的测试覆盖率`,
    critical_path_uncovered: `为未覆盖的关键函数 ${sym}() 增加测试覆盖`,
    high_fan_out: `对高影响力枢纽函数 ${sym}() 进行集成测试`,
    deep_impact_surface: `验证函数 ${sym}() 的契约稳定性（被多个调用者依赖）`,
    hotspot_regression_risk: `对历史热点函数 ${sym}() 进行回归测试`,
  }
  return mapping[rt] || `验证 ${sym}() 中与 ${rt} 相关的行为`
}

function getTestSteps(finding) {
  const ev = finding.evidence || {}
  const sym = finding.symbol_name || '目标函数'
  const rt = finding.risk_type || ''

  if (rt.includes('boundary') || rt === 'invalid_input_gap') {
    const candidates = ev.candidates || []
    const expr = ev.constraint_expr || ''
    const steps = [`1. 识别约束条件: ${expr}`]
    if (candidates.length) steps.push(`2. 准备边界测试值: ${candidates.join(', ')}`)
    steps.push(`3. 使用每个候选值调用 ${sym}()`)
    steps.push('4. 验证每种情况下的返回值和副作用')
    return steps
  }
  if (rt.includes('cleanup') || rt === 'missing_cleanup') {
    const resources = ev.cleanup_resources_expected || []
    return [
      `1. 设置资源跟踪: ${resources.join(', ') || '相关资源'}`,
      `2. 使用触发错误路径的参数调用 ${sym}()`,
      '3. 在资源分配/IO 点注入失败',
      '4. 验证错误后所有跟踪的资源已正确释放',
    ]
  }
  if (rt.includes('race') || rt.includes('lock') || rt === 'atomicity_gap') {
    const shared = ev.shared_symbol || ''
    return [
      `1. 启动并发线程访问 ${shared || sym}()`,
      '2. 运行交叉操作的压力测试',
      '3. 使用线程检测工具（TSan）或手动竞态检测',
      '4. 验证无数据损坏或死锁',
    ]
  }
  if (rt.includes('changed') || rt.includes('transitive') || rt.includes('hotspot')) {
    const impacted = (ev.impacted_symbols || []).slice(0, 5)
    const steps = [
      `1. 审查 ${sym}() 的变更内容`,
      `2. 运行 ${sym}() 的已有测试`,
    ]
    if (impacted.length) steps.push(`3. 对受影响的调用者运行回归测试: ${impacted.join(', ')}`)
    steps.push('4. 验证功能行为符合规范')
    return steps
  }
  if (rt === 'inconsistent_errno_mapping') {
    return [
      `1. 遍历 ${sym}() 的所有错误返回路径`,
      '2. 在每个错误触发点注入失败条件',
      '3. 比较实际返回码与文档/头文件中定义的预期值',
      '4. 验证每条错误路径返回正确的错误码',
    ]
  }
  if (rt === 'silent_error_swallow') {
    return [
      `1. 在 ${sym}() 的错误路径注入失败条件`,
      '2. 检查调用者是否能收到正确的错误通知',
      '3. 验证日志是否记录了错误信息',
      '4. 确认无静默忽略的错误返回',
    ]
  }
  if (rt === 'high_fan_out' || rt === 'deep_impact_surface') {
    return [
      `1. 审查 ${sym}() 的被调用者列表`,
      `2. 修改 ${sym}() 的接口契约`,
      '3. 检查所有下游调用者是否仍然正常',
      '4. 运行集成测试验证端到端行为',
    ]
  }
  if (rt.includes('coverage')) {
    return [
      `1. 使用覆盖率工具标记 ${sym}() 的未覆盖行`,
      '2. 设计覆盖未执行分支的测试输入',
      '3. 运行新测试并验证覆盖率提升',
      '4. 关注高风险区域的分支覆盖',
    ]
  }
  // 通用
  return [
    `1. 搭建 ${sym}() 的测试环境`,
    `2. 使用代表性输入调用 ${sym}()`,
    '3. 验证预期行为和返回值',
    '4. 检查资源泄漏和错误处理',
  ]
}

function getTestExpected(finding) {
  const rt = finding.risk_type || ''
  const mapping = {
    boundary_miss: '函数正确处理所有边界值，无崩溃或数据损坏',
    invalid_input_gap: '非法输入被拒绝；无缓冲区溢出或越界访问',
    missing_cleanup: '在每条错误路径上所有已分配的资源均已释放',
    inconsistent_errno_mapping: '每条错误路径返回正确的、文档记录的错误码',
    silent_error_swallow: '所有错误均正确传播给调用者，无静默吞没',
    race_write_without_lock: '并发访问下未检测到数据竞态',
    lock_order_inversion: '所有锁序组合下的并发执行无死锁',
    atomicity_gap: '复合操作具有原子性，中断后状态一致',
    changed_core_path: '修改后的函数行为与规范一致',
    transitive_impact: '上游变更后下游调用函数继续正常工作',
    branch_missing_test: '所有关键分支都有对应测试覆盖',
    error_path: '错误路径正确处理并返回预期错误码',
    cleanup_path: '清理路径释放所有已分配资源',
    high_risk_low_coverage: '高风险区域的测试覆盖率达到可接受水平',
    critical_path_uncovered: '关键路径获得充分测试覆盖',
    high_fan_out: '高扇出函数的接口变更不影响下游调用者',
    deep_impact_surface: '深调用链函数的契约保持稳定',
  }
  return mapping[rt] || '函数行为正确且优雅地处理边界情况'
}

function getTestPriority(finding) {
  return SEV_PRIORITY[finding.severity || 'S3'] || 'P3-低'
}

export function useTestSuggestion() {
  return {
    getTestObjective,
    getTestSteps,
    getTestExpected,
    getTestPriority,
  }
}
