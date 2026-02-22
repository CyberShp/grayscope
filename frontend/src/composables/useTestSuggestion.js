/**
 * 前端侧的测试建议生成 — 基于发现的 evidence 数据
 * 生成具体、可操作的中文测试建议。
 */

const SEV_PRIORITY = { S0: 'P0-紧急', S1: 'P1-高', S2: 'P2-中', S3: 'P3-低' }

function _buildChainPath(chain) {
  if (!chain || !chain.length) return ''
  return chain.map(s => `${s.function}(${s.param})`).join(' → ')
}

function getTestObjective(finding) {
  const sym = finding.symbol_name || '目标函数'
  const rt = finding.risk_type || ''
  const ev = finding.evidence || {}

  // 如果有传播链，生成端到端测试目标
  if (ev.propagation_chain && ev.propagation_chain.length > 1) {
    const chain = ev.propagation_chain
    const entry = chain[0]
    const target = chain[chain.length - 1]
    const depth = chain.length
    const isExternal = ev.is_external_input

    if (rt === 'boundary_miss' || rt === 'invalid_input_gap') {
      return `从入口函数 ${entry.function}(${entry.param}) 开始，经过 ${depth} 层调用链到达 ${sym}() 处的${rt === 'boundary_miss' ? '边界条件' : '数组访问'}。${isExternal ? '入口参数来自外部输入，' : ''}构造使整条调用链端到端触发边界行为的测试值`
    }
    if (rt === 'deep_param_propagation') {
      return `验证参数 '${ev.entry_param}' 从 ${ev.entry_function}() 经 ${depth} 层调用传播后的端到端行为：${ev.sensitive_ops?.length ? `到达敏感操作（${ev.sensitive_ops.join('、')}），` : ''}确认传播链上的值域变换不会导致意外风险`
    }
    if (rt === 'external_to_sensitive') {
      return `验证外部输入参数 '${ev.entry_param}' 在 ${ev.entry_function}() 中到达敏感操作（${(ev.sensitive_ops || []).join('、')}）前是否经过充分验证`
    }
    if (rt === 'value_transform_risk') {
      const transforms = ev.transforms || []
      return `验证参数 '${ev.entry_param}' 经过 ${transforms.length} 次算术变换（${transforms.map(t => t.type).join('、')}）后不会溢出或丢失精度`
    }
  }

  const mapping = {
    branch_missing_test: `验证 ${sym}() 中未被测试覆盖的分支路径在各种输入下的行为`,
    branch_error: `验证 ${sym}() 中的错误处理分支：当条件「${ev.condition_expr || '错误条件'}」触发时，确认错误处理逻辑完整、资源无泄漏`,
    branch_cleanup: `验证 ${sym}() 中的资源清理路径：确认所有分配的资源在异常退出时被正确释放`,
    branch_boundary: `验证 ${sym}() 中边界条件「${ev.condition_expr || ''}」附近的行为：确认边界值、边界±1均被正确处理`,
    branch_normal: `验证 ${sym}() 的正常执行路径在典型输入下的行为符合预期`,
    error_path: `验证 ${sym}() 中的错误返回路径：确认函数在失败时返回正确的错误码`,
    cleanup_path: `验证 ${sym}() 在异常退出时正确释放所有资源（${(ev.cleanup_resources_expected || []).join('、') || '内存/文件/锁'}）`,
    boundary_miss: `使用边界值测试 ${sym}() 中的约束条件「${ev.constraint_expr || ''}」：包括边界值本身、边界±1、零值和负数`,
    invalid_input_gap: `验证 ${sym}() 对非法输入的处理：数组「${ev.array_name || ''}」的越界访问应被检测和拒绝`,
    missing_cleanup: `验证 ${sym}() 在错误路径上正确释放所有已分配资源（需要释放: ${(ev.cleanup_resources_expected || []).join('、') || '相关资源'}）`,
    inconsistent_errno_mapping: `验证 ${sym}() 中每条错误路径返回的错误码与预期一致（发现 ${(ev.error_codes || []).length || '多种'} 种不同错误码）`,
    silent_error_swallow: `验证 ${sym}() 中的错误不被静默忽略：确认所有错误都传播给调用者`,
    race_write_without_lock: `验证 ${sym}() 中对共享变量「${ev.shared_symbol || ''}」的并发写入安全性：使用多线程压力测试`,
    lock_order_inversion: `验证涉及 ${sym} 的锁获取顺序：确认不会产生 ABBA 死锁`,
    atomicity_gap: `验证 ${sym}() 中锁的获取/释放配对完整性：确认所有退出路径都释放了锁`,
    changed_core_path: `对修改后的 ${sym}() 进行回归测试：确认功能行为不变、接口契约稳定`,
    transitive_impact: `对受上游变更影响的 ${sym}() 进行回归测试：验证其依赖的函数行为未意外改变`,
    high_risk_low_coverage: `为高风险函数 ${sym}() 增加测试覆盖率：重点关注行覆盖率 ${((ev.line_coverage || 0) * 100).toFixed(0)}% 需提升的区域`,
    critical_path_uncovered: `为零覆盖的关键函数 ${sym}() 编写测试用例，确保基本功能被验证`,
    high_fan_out: `为高扇出枢纽函数 ${sym}()（调用 ${ev.fan_out || '多个'} 个函数）建立集成测试`,
    deep_impact_surface: `为被 ${ev.fan_in || '多个'} 个函数调用的关键函数 ${sym}() 建立接口契约测试`,
    hotspot_regression_risk: `对历史热点函数 ${sym}() 进行全面回归测试`,
    deep_param_propagation: `验证参数 '${ev.entry_param || ''}' 从 ${ev.entry_function || '入口'}() 经 ${ev.max_depth || '多'} 层调用传播后的端到端行为`,
    external_to_sensitive: `验证外部输入到敏感操作的路径安全性: ${ev.entry_function || sym}(${ev.entry_param || ''})`,
    value_transform_risk: `验证参数经多次算术变换后不会溢出: ${ev.entry_function || sym}(${ev.entry_param || ''})`,
    cross_function_resource_leak: `验证 ${sym}() 在调用 ${ev.callee_function || '子函数'}() 失败时正确释放已分配资源`,
    cross_function_deadlock_risk: `验证跨函数调用链上的锁获取顺序不会导致 ABBA 死锁`,
    cross_function_race: `验证调用链上的共享变量 '${ev.shared_symbol || ''}' 并发安全性`,
  }
  return mapping[rt] || `验证 ${sym}() 中与「${rt}」相关的行为是否符合预期`
}

function getTestSteps(finding) {
  const ev = finding.evidence || {}
  const sym = finding.symbol_name || '目标函数'
  const rt = finding.risk_type || ''

  // 端到端传播链测试步骤
  if (ev.propagation_chain && ev.propagation_chain.length > 1) {
    const chain = ev.propagation_chain
    const entry = chain[0]
    const steps = [
      `1. 定位入口函数 ${entry.function}()，参数 '${entry.param}'`,
      `2. 追踪完整调用链: ${_buildChainPath(chain)}`,
    ]
    const transforms = chain.filter(s => s.transform && s.transform !== 'none')
    if (transforms.length) {
      steps.push(`3. 分析调用链上的值变换: ${transforms.map(t => `${t.function}()中${t.transform}(${t.transform_expr || ''})`).join('、')}`)
      steps.push(`4. 反向推导：计算什么样的入口值经过这些变换后恰好触发 ${sym}() 处的风险条件`)
    } else {
      steps.push(`3. 参数在调用链上直接传递（无变换），入口值即为终端值`)
    }
    if (ev.attack_scenario) {
      steps.push(`${transforms.length ? 5 : 4}. 执行攻击场景: ${ev.attack_scenario}`)
    }
    steps.push(`${steps.length + 1}. 使用计算出的边界值从 ${entry.function}() 入口注入，验证整条调用链的端到端行为`)
    if (ev.is_external_input) {
      steps.push(`${steps.length + 1}. 特别注意：入口参数来自外部输入，需要测试畸形/恶意输入值`)
    }
    return steps
  }

  // 跨函数资源泄漏测试
  if (rt === 'cross_function_resource_leak') {
    const caller = ev.caller_function || sym
    const callee = ev.callee_function || '子函数'
    return [
      `1. 在 ${caller}() 中定位资源分配点（${(ev.caller_resources || []).join('、')}）`,
      `2. 使 ${callee}() 返回错误（注入失败条件）`,
      `3. 检查 ${caller}() 在 ${callee}() 失败后是否释放了已分配资源`,
      `4. 使用 Valgrind/AddressSanitizer 验证无内存泄漏`,
      `5. 检查所有错误路径：${caller}() 的每个 return 前是否都有完整清理`,
    ]
  }

  // 跨函数死锁测试
  if (rt === 'cross_function_deadlock_risk') {
    const chainA = ev.chain_a || {}
    const chainB = ev.chain_b || {}
    return [
      `1. 识别两条冲突的锁获取路径:`,
      `   路径A: ${chainA.path || '路径A'} 锁顺序 ${(chainA.locks || []).join(' → ')}`,
      `   路径B: ${chainB.path || '路径B'} 锁顺序 ${(chainB.locks || []).join(' → ')}`,
      `2. 编写多线程测试：线程1执行路径A，线程2执行路径B`,
      `3. 使用高并发压力（>100次迭代）检测死锁`,
      `4. 使用 ThreadSanitizer 检测 lock-order-inversion`,
      `5. 确认全局锁获取顺序文档并修复顺序不一致`,
    ]
  }

  if (rt.includes('boundary') || rt === 'invalid_input_gap') {
    const candidates = ev.candidates || []
    const expr = ev.constraint_expr || ev.array_name || ''
    const steps = []
    if (expr) steps.push(`1. 定位约束条件「${expr}」所在的代码行`)
    else steps.push(`1. 定位 ${sym}() 中的边界检查条件`)
    if (candidates.length) {
      steps.push(`2. 准备以下测试输入值: ${candidates.map(c => `「${c}」`).join('、')}`)
    } else {
      steps.push('2. 准备测试值：下限值、下限-1、上限值、上限+1、0、-1')
    }
    steps.push(`3. 依次使用每个测试值调用 ${sym}()，记录返回值和程序行为`)
    steps.push('4. 验证：(a) 合法值返回正确结果；(b) 非法值被拒绝且不会崩溃；(c) 边界值处行为符合文档定义')
    return steps
  }

  if (rt.includes('cleanup') || rt === 'missing_cleanup') {
    const expected = ev.cleanup_resources_expected || []
    const observed = ev.cleanup_resources_observed || []
    const missing = expected.filter(r => !observed.includes(r))
    return [
      `1. 在 ${sym}() 的资源分配点设置断点或跟踪：${expected.join('、') || '内存/文件/锁'}`,
      '2. 构造触发错误路径的输入（例如：传入 NULL 指针、使 malloc 返回 NULL、模拟 IO 失败）',
      `3. 执行 ${sym}() 并让其走入错误返回路径`,
      `4. 检查以下资源是否被释放: ${expected.join('、')}` + (missing.length ? `（当前缺失: ${missing.join('、')}）` : ''),
      '5. 使用 Valgrind/AddressSanitizer 验证无内存泄漏',
    ]
  }

  if (rt.includes('race') || rt.includes('lock') || rt === 'atomicity_gap') {
    const shared = ev.shared_symbol || ''
    const locks = ev.acquired_locks || ev.conflicting_locks || []
    return [
      `1. 编写多线程测试：启动 2-4 个线程并发调用涉及 ${shared || sym}() 的代码`,
      '2. 在线程中交叉执行读写操作，确保足够的并发压力',
      `3. 使用 ThreadSanitizer (TSan) 编译运行：gcc -fsanitize=thread -g ${sym}.c -o test`,
      `4. 检查 TSan 报告中是否有 "data race" 或 "lock-order-inversion" 警告`,
      locks.length ? `5. 确认锁（${locks.join('、')}）在所有路径上都被正确获取和释放` : '5. 确认共享数据的访问都有适当的同步保护',
    ]
  }

  if (rt.includes('changed') || rt.includes('transitive') || rt.includes('hotspot')) {
    const impacted = (ev.impacted_symbols || []).slice(0, 5)
    const steps = [
      `1. 查看 ${sym}() 的代码变更内容（git diff），理解修改了什么`,
      `2. 运行 ${sym}() 已有的单元测试，确认全部通过`,
      `3. 使用修改前后的典型输入调用 ${sym}()，对比输出是否一致`,
    ]
    if (impacted.length) {
      steps.push(`4. 对以下受影响的调用者运行回归测试: ${impacted.map(s => s + '()').join('、')}`)
    }
    steps.push(`${impacted.length ? 5 : 4}. 确认函数的返回值类型、错误码语义、副作用均未改变`)
    return steps
  }

  if (rt === 'inconsistent_errno_mapping') {
    const codes = ev.error_codes || []
    return [
      `1. 列出 ${sym}() 的所有错误返回路径及其返回值${codes.length ? `（当前发现: ${codes.join('、')}）` : ''}`,
      '2. 对照头文件或文档，确认每个错误码的含义是否正确',
      `3. 逐个注入错误条件（使内部调用失败），调用 ${sym}()`,
      '4. 验证：每种错误场景返回预期的错误码，无混用或遗漏',
    ]
  }

  if (rt === 'silent_error_swallow') {
    return [
      `1. 在 ${sym}() 的内部调用点注入失败（例如：让文件操作返回错误）`,
      `2. 调用 ${sym}() 并检查其返回值是否反映了内部错误`,
      '3. 检查调用者是否能收到正确的错误信息（不是被静默忽略的 0 或 void）',
      '4. 检查是否有日志记录了该错误信息（生产环境需要可追溯性）',
    ]
  }

  if (rt === 'high_fan_out' || rt === 'deep_impact_surface') {
    const callees = (ev.callees || []).slice(0, 5)
    const callers = (ev.callers || []).slice(0, 5)
    return [
      `1. 审查 ${sym}() 的接口契约：参数类型、返回值含义、前置/后置条件`,
      callees.length
        ? `2. 验证 ${sym}() 对以下被调用函数的调用是否正确: ${callees.map(c => c + '()').join('、')}`
        : `2. 验证 ${sym}() 与其依赖函数之间的交互是否正确`,
      callers.length
        ? `3. 模拟修改 ${sym}() 的返回值，验证调用者 ${callers.map(c => c + '()').join('、')} 是否能正确适应`
        : `3. 编写集成测试覆盖 ${sym}() 的主要调用场景`,
      `4. 运行端到端测试验证整条调用链的功能正确性`,
    ]
  }

  if (rt.includes('coverage')) {
    const lineCov = ev.line_coverage ? `${(ev.line_coverage * 100).toFixed(0)}%` : '未知'
    return [
      `1. 运行覆盖率工具（gcov/lcov）查看 ${sym}() 的未覆盖行（当前行覆盖率: ${lineCov}）`,
      '2. 分析未覆盖行所属的分支条件，设计能触发这些分支的输入',
      `3. 编写测试用例覆盖 ${sym}() 中的关键路径`,
      '4. 重新运行覆盖率工具，确认覆盖率有明显提升',
    ]
  }

  // 通用
  return [
    `1. 分析 ${sym}() 的输入参数和前置条件`,
    `2. 使用正常值、边界值、非法值分别调用 ${sym}()`,
    '3. 检查返回值是否正确，是否有内存泄漏或资源未释放',
    '4. 检查边界情况（空指针、零长度、最大值）下的行为',
  ]
}

function getTestExpected(finding) {
  const rt = finding.risk_type || ''
  const sym = finding.symbol_name || '目标函数'
  const ev = finding.evidence || {}
  const mapping = {
    boundary_miss: `${sym}() 在所有边界值处行为正确：合法值返回正确结果，非法值被拒绝，无崩溃或数据损坏`,
    invalid_input_gap: `非法下标被检测并拒绝，不产生缓冲区溢出或段错误，函数返回明确的错误状态`,
    missing_cleanup: `在每条错误退出路径上，所有已分配资源（${(ev.cleanup_resources_expected || []).join('、') || '内存/文件/锁'}）均已正确释放`,
    inconsistent_errno_mapping: `每条错误路径返回正确的、与文档一致的错误码，无混用`,
    silent_error_swallow: `所有内部错误均正确传播给调用者，调用者能区分成功和各类失败`,
    race_write_without_lock: `ThreadSanitizer 检测无数据竞态报告，并发写入${ev.shared_symbol ? ` '${ev.shared_symbol}'` : ''} 有正确的同步保护`,
    lock_order_inversion: `所有锁的获取顺序一致，多线程压力测试下无死锁发生`,
    atomicity_gap: `所有退出路径（含错误路径）都正确释放了锁，无死锁风险`,
    changed_core_path: `修改后的 ${sym}() 行为与修改前一致（除非是有意的行为变更），所有调用者不受影响`,
    transitive_impact: `上游函数变更后 ${sym}() 的行为不变，返回值和副作用与变更前一致`,
    branch_missing_test: `所有关键分支路径都有测试覆盖，无遗漏的未测试代码路径`,
    branch_error: `错误分支正确执行：返回正确错误码、释放已分配资源、不产生副作用`,
    branch_cleanup: `清理路径释放所有已分配资源，无遗漏`,
    error_path: `错误路径返回正确的错误码，资源完整释放`,
    cleanup_path: `清理路径完整执行，所有资源正确释放`,
    high_risk_low_coverage: `高风险区域的测试覆盖率显著提升，关键路径被充分验证`,
    critical_path_uncovered: `关键路径从零覆盖提升到有效覆盖，基本功能被验证`,
    high_fan_out: `${sym}() 的接口变更或被调用者变更不破坏端到端功能`,
    deep_impact_surface: `${sym}() 的接口契约稳定，修改不影响所有 ${ev.fan_in || ''} 个调用者`,
    deep_param_propagation: `参数从入口到终端的整条传播链行为正确，无溢出、越界或意外值域变换`,
    external_to_sensitive: `外部输入在到达敏感操作前被充分验证，畸形输入被正确拒绝，无缓冲区溢出`,
    value_transform_risk: `参数经过所有算术变换后值域正确，无整数溢出或精度丢失`,
    cross_function_resource_leak: `${sym}() 在子函数失败时正确释放所有已分配资源，Valgrind 无泄漏报告`,
    cross_function_deadlock_risk: `多线程压力测试下无死锁发生，锁获取顺序全局一致`,
    cross_function_race: `跨函数访问共享变量 '${ev.shared_symbol || ''}' 时 ThreadSanitizer 无数据竞态报告`,
  }
  return mapping[rt] || `${sym}() 在所有测试场景下行为正确，无崩溃、泄漏或意外行为`
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
