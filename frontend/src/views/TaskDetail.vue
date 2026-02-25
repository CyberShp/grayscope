<template>
  <div class="gs-page">
    <!-- 返回导航 -->
    <div class="gs-task-nav gs-section">
      <router-link to="/tasks" class="gs-back-link">&larr; 返回任务中心</router-link>
    </div>

    <!-- 任务头部 -->
    <div class="gs-task-header gs-section">
      <div class="gs-task-header-left">
        <h1 class="gs-page-title" style="margin-bottom: 4px;">任务详情</h1>
        <code class="gs-task-id">{{ task.task_id }}</code>
      </div>
      <div class="gs-task-header-right">
        <el-button v-if="['failed','partial_failed'].includes(task.status)" type="primary" size="small" @click="doRetry">
          <el-icon><RefreshRight /></el-icon> 重试
        </el-button>
        <el-button v-if="['pending','running'].includes(task.status)" type="danger" size="small" plain @click="doCancel">取消</el-button>
        <el-button v-if="['success','partial_failed'].includes(task.status)" size="small" @click="doGenerateSfmea" :loading="sfmeaLoading">生成 SFMEA</el-button>
        <el-dropdown trigger="click">
          <el-button size="small"><el-icon><Download /></el-icon> 导出</el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item @click="doExport('json')">JSON 测试用例</el-dropdown-item>
              <el-dropdown-item @click="doExport('csv')">CSV 表格</el-dropdown-item>
              <el-dropdown-item @click="doExport('sfmea')">SFMEA 条目 (CSV)</el-dropdown-item>
              <el-dropdown-item @click="doExport('markdown')">Markdown 清单</el-dropdown-item>
              <el-dropdown-item @click="doExport('critical')">仅交汇临界点</el-dropdown-item>
              <el-dropdown-item @click="doExport('html')">HTML 报告</el-dropdown-item>
              <el-dropdown-item @click="doExport('findings')">原始发现</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
      </div>
    </div>

    <!-- 状态卡片组 -->
    <div class="gs-stat-row gs-section">
      <div class="gs-stat-card">
        <div class="gs-stat-label">状态</div>
        <div style="display: flex; align-items: center; gap: 6px;">
          <span class="gs-status-dot" :class="'gs-status-dot--' + task.status"></span>
          <span class="gs-stat-value" style="font-size: 16px;">{{ statusLabel(task.status) }}</span>
        </div>
      </div>
      <div class="gs-stat-card">
        <div class="gs-stat-label">风险评分</div>
        <div class="gs-stat-value" :style="{ color: riskColor(results.aggregate_risk_score || 0) }">
          {{ results.aggregate_risk_score != null ? (results.aggregate_risk_score * 100).toFixed(0) + '%' : '-' }}
        </div>
        <div class="gs-stat-sub">{{ riskLevel(results.aggregate_risk_score || 0) }}</div>
      </div>
      <div class="gs-stat-card">
        <div class="gs-stat-label">模块进度</div>
        <div class="gs-stat-value" style="font-size: 16px;">
          {{ task.progress?.finished_modules || 0 }} / {{ task.progress?.total_modules || 0 }}
        </div>
        <div class="gs-stat-sub">{{ task.task_type || '-' }}</div>
      </div>
      <div class="gs-stat-card">
        <div class="gs-stat-label">创建时间</div>
        <div style="font-size: 13px; color: var(--gs-text-primary);">{{ formatDate(task.created_at) }}</div>
        <div class="gs-stat-sub">更新: {{ formatDate(task.updated_at) }}</div>
      </div>
    </div>

    <!-- Tabs -->
    <div class="gs-card">
      <el-tabs v-model="activeTab">
        <!-- 模块概览 -->
        <el-tab-pane label="模块概览" name="modules">
          <el-row :gutter="20">
            <el-col :span="14">
              <el-table :data="modules" size="small" class="gs-table">
                <el-table-column label="模块名称" min-width="160">
                  <template #default="{ row }">
                    <span style="font-weight: 500;">{{ row.display_name || getDisplayName(row.module) }}</span>
                  </template>
                </el-table-column>
                <el-table-column label="状态" width="100">
                  <template #default="{ row }">
                    <span class="gs-status-dot" :class="'gs-status-dot--' + row.status"></span>
                    {{ statusLabel(row.status) }}
                  </template>
                </el-table-column>
                <el-table-column label="风险评分" width="160">
                  <template #default="{ row }">
                    <div v-if="row.risk_score != null" style="display: flex; align-items: center; gap: 8px;">
                      <div class="gs-risk-bar" style="flex: 1;">
                        <div class="gs-risk-bar-fill" :style="{ width: (row.risk_score * 100) + '%', background: riskColor(row.risk_score) }"></div>
                      </div>
                      <span style="font-size: 12px; font-weight: 600;">{{ (row.risk_score * 100).toFixed(0) }}%</span>
                    </div>
                    <span v-else style="color: var(--gs-text-muted);">-</span>
                  </template>
                </el-table-column>
                <el-table-column prop="finding_count" label="发现数" width="70" align="center" />
              </el-table>
            </el-col>
            <el-col :span="10">
              <v-chart v-if="Object.keys(radarOption).length" :option="radarOption" autoresize style="height: 320px;" />
              <el-empty v-else description="暂无雷达图数据" :image-size="60" />
            </el-col>
          </el-row>
        </el-tab-pane>

        <!-- 发现列表 -->
        <el-tab-pane label="发现列表" name="findings">
          <div class="gs-toolbar" style="margin-bottom: 12px;">
            <div class="gs-toolbar-left">
              <el-select v-model="filterSeverity" placeholder="严重程度" clearable size="small" style="width: 120px;">
                <el-option label="S0 紧急" value="S0" />
                <el-option label="S1 高危" value="S1" />
                <el-option label="S2 中危" value="S2" />
                <el-option label="S3 低危" value="S3" />
              </el-select>
              <el-select v-model="filterModule" placeholder="分析模块" clearable size="small" style="width: 160px;">
                <el-option v-for="m in modules" :key="m.module" :label="getDisplayName(m.module)" :value="m.module" />
              </el-select>
            </div>
            <span class="gs-result-count">{{ filteredFindings.length }} 条发现</span>
          </div>
          <el-table :data="filteredFindings" size="small" class="gs-table" row-key="finding_id" :default-sort="{ prop: 'risk_score', order: 'descending' }">
            <el-table-column type="expand">
              <template #default="{ row }">
                <div style="padding: 12px 24px;">
                  <!-- 风险原因高亮区 -->
                  <div class="gs-risk-detail-block">
                    <div class="gs-risk-detail-title">
                      <el-icon style="color:var(--gs-warning);"><WarningFilled /></el-icon>
                      为什么这里有风险？
                    </div>
                    <p class="gs-risk-detail-desc">{{ row.description || '暂无详细描述' }}</p>
                    <div v-if="row.risk_type" class="gs-risk-detail-type">
                      <span style="color:var(--gs-text-muted);font-size:12px;">风险类型:</span>
                      <el-tag size="small" :type="riskTypeTag(row.risk_type)">{{ riskTypeLabel(row.risk_type) }}</el-tag>
                    </div>
                  </div>

                  <!-- 调用链上下文 -->
                  <div v-if="row.evidence && row.evidence.propagation_chain && row.evidence.propagation_chain.length > 1" class="gs-propagation-block">
                    <div class="gs-propagation-title">
                      <el-icon style="color:#8B5CF6;"><Connection /></el-icon>
                      调用链上下文（{{ row.evidence.propagation_chain.length }} 层传播）
                    </div>
                    <div class="gs-propagation-chain">
                      <div v-for="(step, idx) in row.evidence.propagation_chain" :key="idx" class="gs-propagation-step"
                           :class="{ 'gs-propagation-entry': idx === 0, 'gs-propagation-sink': idx === row.evidence.propagation_chain.length - 1 }">
                        <div class="gs-propagation-step-num">{{ idx + 1 }}</div>
                        <div class="gs-propagation-step-body">
                          <code class="gs-propagation-func">{{ step.function }}({{ step.param }})</code>
                          <span v-if="step.transform && step.transform !== 'none'" class="gs-propagation-transform">
                            变换: <code>{{ step.transform }}{{ step.transform_expr ? '(' + step.transform_expr + ')' : '' }}</code>
                          </span>
                          <span v-else-if="idx < row.evidence.propagation_chain.length - 1" class="gs-propagation-passthrough">直接传递</span>
                        </div>
                        <div v-if="idx < row.evidence.propagation_chain.length - 1" class="gs-propagation-arrow">↓</div>
                      </div>
                    </div>
                    <div v-if="row.evidence.is_external_input" class="gs-propagation-external-warn">
                      <el-icon><WarningFilled /></el-icon>
                      入口参数来自外部输入（攻击者可控）
                    </div>
                    <div v-if="row.evidence.attack_scenario" class="gs-propagation-scenario">
                      <strong>攻击场景:</strong> {{ row.evidence.attack_scenario }}
                    </div>
                  </div>

                  <!-- 代码位置（可点击跳转） -->
                  <div v-if="row.file_path" class="gs-risk-location-block">
                    <strong>代码位置:</strong>
                    <router-link v-if="taskProjectId" :to="sourceLink(row)" class="gs-source-link" style="margin-left:8px;">
                      {{ row.file_path }}<span v-if="row.line_start">:{{ row.line_start }}<span v-if="row.line_end">-{{ row.line_end }}</span></span>
                    </router-link>
                    <span v-else style="font-family:var(--gs-font-mono);font-size:12px;margin-left:8px;">
                      {{ row.file_path }}<span v-if="row.line_start">:{{ row.line_start }}</span>
                    </span>
                    <span v-if="row.symbol_name" style="margin-left:12px;">
                      <strong>函数:</strong> <code>{{ row.symbol_name }}()</code>
                    </span>
                  </div>

                  <!-- 推荐测试设计 -->
                  <div class="gs-inline-test-suggestion">
                    <div class="gs-inline-ts-title"><el-icon><EditPen /></el-icon> 推荐测试设计</div>
                    <div class="gs-inline-ts-body">
                      <p><strong>测试目标:</strong> {{ getTestObjective(row) }}</p>
                      <p><strong>测试步骤:</strong></p>
                      <ol class="gs-inline-ts-steps">
                        <li v-for="(s, i) in getTestSteps(row)" :key="i">{{ s.replace(/^\d+\.\s*/, '') }}</li>
                      </ol>
                      <p class="gs-inline-ts-expected"><strong>预期结果:</strong> {{ getTestExpected(row) }}</p>
                    </div>
                  </div>

                  <!-- 结构化证据 -->
                  <div v-if="row.evidence && Object.keys(row.evidence).length" style="margin-top: 12px;">
                    <strong>分析证据:</strong>
                    <div style="margin-top: 8px;">
                      <EvidenceRenderer :module-id="row.module_id" :risk-type="row.risk_type" :evidence="row.evidence" :finding="row" />
                    </div>
                  </div>
                </div>
              </template>
            </el-table-column>
            <el-table-column label="严重度" width="80" sortable prop="severity">
              <template #default="{ row }">
                <span class="gs-severity-tag" :class="'gs-severity-' + (row.severity || 's3').toLowerCase()">{{ row.severity }}</span>
              </template>
            </el-table-column>
            <el-table-column label="模块" width="130">
              <template #default="{ row }">{{ getDisplayName(row.module_id) }}</template>
            </el-table-column>
            <el-table-column prop="risk_type" label="风险类型" width="160" show-overflow-tooltip>
              <template #default="{ row }">
                <el-tag size="small" :type="riskTypeTag(row.risk_type)">{{ riskTypeLabel(row.risk_type) }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="title" label="标题" min-width="180" show-overflow-tooltip />
            <el-table-column label="风险原因" min-width="220">
              <template #default="{ row }">
                <div class="gs-risk-reason">
                  <span class="gs-risk-reason-text">{{ row.description || '-' }}</span>
                </div>
              </template>
            </el-table-column>
            <el-table-column label="文件位置" min-width="200">
              <template #default="{ row }">
                <div v-if="row.file_path" class="gs-source-link-wrap">
                  <router-link v-if="taskProjectId"
                    :to="sourceLink(row)"
                    class="gs-source-link"
                    :title="row.file_path">
                    <span class="gs-source-file">{{ shortenPath(row.file_path) }}</span>
                    <span v-if="row.line_start" class="gs-source-line">:{{ row.line_start }}<span v-if="row.line_end && row.line_end !== row.line_start">-{{ row.line_end }}</span></span>
                  </router-link>
                  <span v-else class="gs-source-link" style="cursor:default;">
                    <span class="gs-source-file">{{ shortenPath(row.file_path) }}</span>
                    <span v-if="row.line_start" class="gs-source-line">:{{ row.line_start }}</span>
                  </span>
                  <span v-if="row.symbol_name" class="gs-source-symbol">{{ row.symbol_name }}()</span>
                </div>
                <span v-else style="color:var(--gs-text-muted);">-</span>
              </template>
            </el-table-column>
            <el-table-column prop="risk_score" label="评分" width="80" sortable>
              <template #default="{ row }">
                <div style="display:flex;align-items:center;gap:4px;">
                  <div class="gs-risk-bar" style="width:40px;">
                    <div class="gs-risk-bar-fill" :style="{ width: (row.risk_score || 0) * 100 + '%', background: riskColor(row.risk_score || 0) }"></div>
                  </div>
                  <span :style="{ color: riskColor(row.risk_score || 0), fontWeight: 600, fontSize: '12px' }">
                    {{ row.risk_score != null ? (row.risk_score * 100).toFixed(0) + '%' : '-' }}
                  </span>
                </div>
              </template>
            </el-table-column>
          </el-table>
        </el-tab-pane>

        <!-- 覆盖率 -->
        <el-tab-pane label="覆盖率" name="coverage">
          <div v-if="coverageFindings.length" class="gs-coverage-section">
            <!-- 覆盖率汇总 -->
            <div class="gs-stat-row gs-section" style="grid-template-columns: repeat(3, 1fr);">
              <div class="gs-stat-card">
                <div class="gs-stat-label">平均行覆盖率</div>
                <div class="gs-stat-value" :style="{ color: covColor(avgLineCoverage) }">{{ (avgLineCoverage * 100).toFixed(0) }}%</div>
              </div>
              <div class="gs-stat-card">
                <div class="gs-stat-label">平均分支覆盖率</div>
                <div class="gs-stat-value" :style="{ color: covColor(avgBranchCoverage) }">{{ (avgBranchCoverage * 100).toFixed(0) }}%</div>
              </div>
              <div class="gs-stat-card">
                <div class="gs-stat-label">零覆盖文件</div>
                <div class="gs-stat-value" :style="{ color: zeroCoverageCount > 0 ? '#D4333F' : '#00AA00' }">{{ zeroCoverageCount }}</div>
              </div>
            </div>

            <!-- 文件级覆盖率列表 -->
            <el-table :data="coverageFindings" size="small" class="gs-table" :default-sort="{ prop: 'line_coverage', order: 'ascending' }">
              <el-table-column label="文件路径" min-width="280">
                <template #default="{ row }">
                  <router-link v-if="row.file_path && taskProjectId"
                    :to="`/projects/${taskProjectId}/code?path=${encodeURIComponent(row.file_path)}`"
                    class="gs-file-link">
                    {{ row.file_path }}
                  </router-link>
                  <span v-else class="gs-file-path">{{ row.file_path || '-' }}</span>
                </template>
              </el-table-column>
              <el-table-column label="行覆盖率" width="200" prop="line_coverage" sortable>
                <template #default="{ row }">
                  <div style="display: flex; align-items: center; gap: 8px;">
                    <div class="gs-cov-bar-wrap">
                      <div class="gs-cov-bar" :class="covBarClass(row.line_coverage)" :style="{ width: (row.line_coverage || 0) * 100 + '%' }"></div>
                    </div>
                    <span style="font-size: 12px; font-weight: 600; min-width: 36px;">{{ ((row.line_coverage || 0) * 100).toFixed(0) }}%</span>
                  </div>
                </template>
              </el-table-column>
              <el-table-column label="分支覆盖率" width="200" prop="branch_coverage" sortable>
                <template #default="{ row }">
                  <div style="display: flex; align-items: center; gap: 8px;">
                    <div class="gs-cov-bar-wrap">
                      <div class="gs-cov-bar" :class="covBarClass(row.branch_coverage)" :style="{ width: (row.branch_coverage || 0) * 100 + '%' }"></div>
                    </div>
                    <span style="font-size: 12px; font-weight: 600; min-width: 36px;">{{ ((row.branch_coverage || 0) * 100).toFixed(0) }}%</span>
                  </div>
                </template>
              </el-table-column>
              <el-table-column label="风险" width="100" prop="risk_score" sortable>
                <template #default="{ row }">
                  <span :style="{ color: riskColor(row.risk_score || 0), fontWeight: 600 }">
                    {{ row.risk_score != null ? (row.risk_score * 100).toFixed(0) + '%' : '-' }}
                  </span>
                </template>
              </el-table-column>
              <el-table-column label="风险原因" min-width="200" show-overflow-tooltip>
                <template #default="{ row }">
                  <span style="font-size:12px;color:var(--gs-text-secondary);">{{ row.title || row.description || '-' }}</span>
                </template>
              </el-table-column>
            </el-table>
          </div>
          <el-empty v-else description="暂无覆盖率数据，请确保启用了 coverage_map 分析器" :image-size="80" />
        </el-tab-pane>

        <!-- AI 增强 -->
        <el-tab-pane name="ai">
          <template #label>
            AI 增强
            <el-tag v-if="aiSuccessCount" type="success" size="small" style="margin-left:4px;">{{ aiSuccessCount }}</el-tag>
            <el-tag v-else-if="aiFailCount" type="danger" size="small" style="margin-left:4px;">失败</el-tag>
          </template>

          <div v-if="!aiEnabled" class="gs-ai-empty">
            <el-icon :size="48" color="#ccc"><WarningFilled /></el-icon>
            <p>本次分析未启用 AI 增强，或 AI 模型不可用</p>
            <p style="font-size:12px;color:var(--gs-text-muted);">
              请在"设置 → AI 模型管理"中配置可用的 AI 模型（如 DeepSeek、Ollama 等），<br>
              然后在新建分析时选择 AI 提供商和模型；启用「跨模块 AI 综合」后，将在此展示<strong>多函数交汇临界点</strong>（灰盒核心：一次用例暴露不可接受结果）。
            </p>
          </div>

          <div v-else class="gs-ai-results">
            <!-- 无跨模块结果时也展示「多函数交汇临界点」说明，便于用户理解灰盒核心 -->
            <div v-if="!(crossModuleAi && crossModuleAi.success)" class="gs-ai-cross-module-card gs-critical-intersection">
              <div class="gs-ai-section-title"><el-icon color="#8B5CF6"><Connection /></el-icon> 多函数交汇临界点</div>
              <p class="gs-cc-what">
                交汇 = 多个函数/分支在<strong>同一场景</strong>下同时参与（如：login 执行中 + 端口闪断/网卡下电处理被触发），不单指「同一变量」；包含执行路径、调用链、故障注入时机上的交汇。一次灰盒用例针对该交汇点即可暴露不可接受结果。
              </p>
              <p class="gs-cc-empty">需在<strong>新建分析时勾选「启用跨模块 AI 综合」</strong>并完成分析后，下方「跨模块综合分析」卡片会出现在此，并列出 AI 推断的交汇临界点。</p>
            </div>

            <!-- 跨模块 AI 综合分析 -->
            <div v-if="crossModuleAi && crossModuleAi.success" class="gs-ai-cross-module-card">
              <div class="gs-ai-module-header">
                <span class="gs-ai-module-name" style="color:#8B5CF6;">跨模块综合分析</span>
                <el-tag type="success" size="small">全局视角</el-tag>
                <span v-if="crossModuleAi.provider" style="font-size:11px;color:var(--gs-text-muted);margin-left:auto;">
                  {{ crossModuleAi.provider }}/{{ crossModuleAi.model }}
                </span>
              </div>

              <!-- 灰盒核心：多函数交汇临界点 — 一次用例即可暴露黑盒需 N 次才能撞出的不可接受结果 -->
              <div class="gs-ai-cross-section gs-critical-intersection">
                <div class="gs-ai-section-title">
                  <el-icon color="#8B5CF6"><Connection /></el-icon>
                  多函数交汇临界点
                </div>
                <p class="gs-cc-what">
                  交汇 = 多个函数/分支在<strong>同一场景</strong>下同时参与（如：login 执行中 + 端口闪断处理被触发 + 网卡下电处理被触发），
                  不是单指「同一个变量」；同一变量是并发分析里的共享变量竞态。这里指<strong>执行路径、调用链或故障注入时机</strong>上的交汇，
                  一次灰盒用例针对该交汇点即可暴露不可接受结果，无需 N 次黑盒盲测。
                </p>
                <div v-if="criticalCombinations.length">
                  <div v-for="(cc, i) in criticalCombinations" :key="'cc'+i" class="gs-ai-cross-item gs-critical-combo">
                    <div class="gs-ai-cross-item-header">
                      <strong>交汇点 {{ i + 1 }}</strong>
                      <span v-if="cc.scenario_brief" class="gs-cc-brief">{{ cc.scenario_brief }}</span>
                    </div>
                    <div v-if="cc.related_functions && cc.related_functions.length" class="gs-cc-funcs">
                      <span class="gs-cc-label">关联函数/分支：</span>
                      <el-tag v-for="fn in cc.related_functions" :key="fn" size="small" type="primary" effect="plain" style="margin:2px;">{{ fn }}</el-tag>
                    </div>
                    <p v-if="(cc.expected_outcome || cc.expected_failure)" class="gs-cc-expected">
                      <span class="gs-cc-label">预期结果（可成功或可接受失败）：</span>{{ cc.expected_outcome || cc.expected_failure }}
                    </p>
                    <p v-if="cc.unacceptable_outcomes && cc.unacceptable_outcomes.length" class="gs-cc-unacceptable">
                      <span class="gs-cc-label">不可接受结果：</span>
                      <el-tag v-for="(o, j) in cc.unacceptable_outcomes" :key="j" size="small" type="danger" effect="plain" style="margin:2px;">{{ o }}</el-tag>
                    </p>
                    <p v-if="cc.performance_requirement" class="gs-cc-perf">
                      <span class="gs-cc-label">性能/时序要求：</span>{{ cc.performance_requirement }}
                    </p>
                  </div>
                </div>
                <p v-else class="gs-cc-empty">
                  当前暂无 AI 识别的交汇临界点。请确保新建分析时<strong>启用了「跨模块 AI 综合」</strong>且分析已成功完成，AI 会从调用图+错误路径+数据流中推断多函数交汇场景并填入此处。
                </p>
              </div>

              <div v-if="crossModuleAi.cross_module_risks && crossModuleAi.cross_module_risks.length" class="gs-ai-cross-section">
                <div class="gs-ai-section-title">跨模块关联风险</div>
                <div v-for="(risk, i) in crossModuleAi.cross_module_risks" :key="'cmr'+i" class="gs-ai-cross-item gs-ai-cross-risk">
                  <div class="gs-ai-cross-item-header">
                    <el-icon color="#D50000"><WarningFilled /></el-icon>
                    <strong>{{ risk.title || risk.name || `关联风险 ${i+1}` }}</strong>
                    <el-tag v-if="risk.severity" :type="risk.severity === 'high' ? 'danger' : risk.severity === 'medium' ? 'warning' : 'info'" size="small">{{ risk.severity }}</el-tag>
                  </div>
                  <p v-if="risk.description" class="gs-ai-cross-desc">{{ risk.description }}</p>
                  <div v-if="risk.modules && risk.modules.length" class="gs-ai-cross-modules">
                    涉及模块: <el-tag v-for="m in risk.modules" :key="m" size="small" style="margin:2px;">{{ getDisplayName(m) }}</el-tag>
                  </div>
                </div>
              </div>

              <div v-if="crossModuleAi.hidden_risk_paths && crossModuleAi.hidden_risk_paths.length" class="gs-ai-cross-section">
                <div class="gs-ai-section-title">隐藏风险路径</div>
                <div v-for="(path, i) in crossModuleAi.hidden_risk_paths" :key="'hrp'+i" class="gs-ai-cross-item gs-ai-cross-hidden">
                  <div class="gs-ai-cross-item-header">
                    <el-icon color="#E57F00"><WarningFilled /></el-icon>
                    <strong>{{ path.title || `隐藏路径 ${i+1}` }}</strong>
                  </div>
                  <p v-if="path.description" class="gs-ai-cross-desc">{{ path.description }}</p>
                  <div v-if="path.chain" class="gs-ai-cross-chain">
                    路径: <code>{{ Array.isArray(path.chain) ? path.chain.join(' → ') : path.chain }}</code>
                  </div>
                </div>
              </div>

              <div v-if="crossModuleAi.e2e_test_scenarios && crossModuleAi.e2e_test_scenarios.length" class="gs-ai-cross-section">
                <div class="gs-ai-section-title">端到端测试场景</div>
                <div v-for="(scenario, i) in crossModuleAi.e2e_test_scenarios" :key="'e2e'+i" class="gs-ai-cross-item gs-ai-cross-scenario">
                  <div class="gs-ai-cross-item-header">
                    <el-icon color="#4B9FD5"><EditPen /></el-icon>
                    <strong>{{ scenario.title || scenario.name || `场景 ${i+1}` }}</strong>
                    <el-tag v-if="scenario.priority" size="small">{{ scenario.priority }}</el-tag>
                  </div>
                  <p v-if="scenario.description || scenario.steps" class="gs-ai-cross-desc">{{ scenario.description || scenario.steps }}</p>
                  <p v-if="scenario.expected" class="gs-ai-cross-expected"><strong>预期:</strong> {{ scenario.expected }}</p>
                </div>
              </div>

              <div v-if="crossModuleAi.methodology_advice" class="gs-ai-cross-section">
                <div class="gs-ai-section-title">测试方法论建议</div>
                <pre class="gs-ai-text">{{ crossModuleAi.methodology_advice }}</pre>
              </div>

              <div v-if="crossModuleAi.usage && crossModuleAi.usage.total_tokens" class="gs-ai-usage">
                Token 使用量：{{ crossModuleAi.usage.prompt_tokens || 0 }}（输入）+ {{ crossModuleAi.usage.completion_tokens || 0 }}（输出）= {{ crossModuleAi.usage.total_tokens }}
              </div>
            </div>

            <!-- 单模块 AI 分析 -->
            <div v-for="(summary, modId) in aiSummaries" :key="modId" class="gs-ai-module-card">
              <div class="gs-ai-module-header">
                <span class="gs-ai-module-name">{{ getDisplayName(modId) }}</span>
                <el-tag :type="summary.success ? 'success' : 'danger'" size="small">
                  {{ summary.success ? 'AI 分析完成' : (summary.skipped ? '已跳过' : 'AI 不可用') }}
                </el-tag>
                <span v-if="summary.provider" style="font-size:11px;color:var(--gs-text-muted);margin-left:auto;">
                  {{ summary.provider }}/{{ summary.model }}
                </span>
              </div>

              <div v-if="summary.success && summary.ai_summary" class="gs-ai-summary-content">
                <div class="gs-ai-section-title">AI 风险分析</div>
                <pre class="gs-ai-text">{{ summary.ai_summary }}</pre>
              </div>

              <div v-if="summary.success && summary.test_suggestions && summary.test_suggestions.length" class="gs-ai-suggestions">
                <div class="gs-ai-section-title">AI 测试建议</div>
                <div v-for="(sug, i) in summary.test_suggestions" :key="i" class="gs-ai-suggestion-item">
                  <template v-if="sug.type === 'raw_text'">
                    <pre class="gs-ai-text">{{ sug.content }}</pre>
                  </template>
                  <template v-else>
                    <div><strong>{{ sug.title || sug.name || `测试用例 ${i+1}` }}</strong></div>
                    <div v-if="sug.description || sug.steps" style="font-size:12px;color:var(--gs-text-secondary);">
                      {{ sug.description || sug.steps }}
                    </div>
                  </template>
                </div>
              </div>

              <div v-if="!summary.success && summary.ai_summary" class="gs-ai-error">
                <el-icon color="#D50000"><WarningFilled /></el-icon>
                <span>{{ summary.ai_summary }}</span>
              </div>

              <div v-if="summary.usage && summary.usage.total_tokens" class="gs-ai-usage">
                Token 使用量：{{ summary.usage.prompt_tokens || 0 }}（输入）+ {{ summary.usage.completion_tokens || 0 }}（输出）= {{ summary.usage.total_tokens }}
              </div>
            </div>
          </div>
        </el-tab-pane>

        <!-- MR 代码变更（与本次任务分析关联：MR 变更文件即本仓库中的变更，与发现联动） -->
        <el-tab-pane label="MR 代码变更" name="mr">
          <div class="gs-mr-block">
            <div class="gs-mr-intro">
              <p style="font-size:12px;color:var(--gs-text-muted);margin-bottom:12px;">
                MR/PR 中的代码变更通常属于<strong>当前分析任务所在项目/仓库</strong>。下方会关联本次任务的发现：标出「MR 涉及文件」及「与 MR 变更文件相关的发现」，便于针对 MR 做灰盒测试设计。
              </p>
            </div>
            <div v-if="taskOptions?.mr_url || (taskOptions?.mr_diff && taskOptions.mr_diff.length)" class="gs-mr-display">
              <div class="gs-mr-section">
                <div class="gs-ai-section-title">MR/PR 链接</div>
                <p v-if="taskOptions?.mr_url">
                  <a :href="taskOptions.mr_url" target="_blank" rel="noopener" class="gs-mr-link">{{ taskOptions.mr_url }}</a>
                </p>
                <p v-else class="gs-text-muted">未填写</p>
              </div>
              <!-- 与本次分析发现的关联：MR 涉及文件 + 落在这些文件上的发现 -->
              <div v-if="mrDiffPaths.length" class="gs-mr-section gs-mr-linkage">
                <div class="gs-ai-section-title">与本次分析发现的关联</div>
                <p class="gs-mr-linkage-desc">本 MR 涉及 <strong>{{ mrDiffPaths.length }}</strong> 个文件；以下为<strong>本次任务</strong>分析结果中落在这些文件上的发现，便于结合 MR 变更做用例设计。</p>
                <div class="gs-mr-paths">
                  <span class="gs-mr-path-tag" v-for="p in mrDiffPaths" :key="p">{{ p }}</span>
                </div>
                <div v-if="findingsInMrFiles.length" class="gs-mr-findings">
                  <el-table :data="findingsInMrFiles" size="small" class="gs-table" max-height="320">
                    <el-table-column label="文件" min-width="200">
                      <template #default="{ row }">
                        <router-link v-if="taskProjectId && row.file_path" :to="`/projects/${taskProjectId}/code?path=${encodeURIComponent(row.file_path)}&line=${row.line_start || ''}`" class="gs-file-link">{{ shortenPath(row.file_path) }}</router-link>
                        <span v-else>{{ shortenPath(row.file_path) }}</span>
                      </template>
                    </el-table-column>
                    <el-table-column label="位置" width="80">
                      <template #default="{ row }">L{{ row.line_start || '-' }}</template>
                    </el-table-column>
                    <el-table-column label="风险类型" width="140">
                      <template #default="{ row }">{{ riskTypeLabel(row.risk_type) }}</template>
                    </el-table-column>
                    <el-table-column label="标题" min-width="180" show-overflow-tooltip>
                      <template #default="{ row }">{{ row.title || '-' }}</template>
                    </el-table-column>
                  </el-table>
                </div>
                <p v-else class="gs-text-muted" style="margin-top:8px;">本次分析中暂无落在上述 MR 文件上的发现。</p>
              </div>
              <div v-if="taskOptions?.mr_diff && taskOptions.mr_diff.length" class="gs-mr-section">
                <div class="gs-ai-section-title">修改前 / 修改后 代码变更</div>
                <div v-for="(item, idx) in taskOptions.mr_diff" :key="idx" class="gs-mr-diff-file">
                  <div class="gs-mr-diff-path">{{ item.path || `文件 ${idx + 1}` }}</div>
                  <template v-if="item.unified_diff">
                    <pre class="gs-mr-diff-unified">{{ item.unified_diff }}</pre>
                  </template>
                  <template v-else>
                    <div class="gs-mr-diff-cols">
                      <div class="gs-mr-diff-col">
                        <div class="gs-mr-diff-col-title">修改前</div>
                        <pre class="gs-mr-diff-pre">{{ item.old_content || '（无）' }}</pre>
                      </div>
                      <div class="gs-mr-diff-col">
                        <div class="gs-mr-diff-col-title">修改后</div>
                        <pre class="gs-mr-diff-pre">{{ item.new_content || '（无）' }}</pre>
                      </div>
                    </div>
                  </template>
                </div>
              </div>
            </div>
            <div v-else class="gs-mr-empty">
              <p>当前任务未关联 MR/PR 链接或代码变更。</p>
              <p style="font-size:12px;color:var(--gs-text-muted);">可在下方填写 MR 链接或粘贴 unified diff（建议含文件路径，便于与本次分析发现关联）。</p>
            </div>
            <el-divider />
            <div class="gs-mr-form">
              <div class="gs-ai-section-title">填写 / 更新 MR 信息</div>
              <el-form label-width="100px" style="max-width:720px">
                <el-form-item label="MR/PR 链接">
                  <el-input v-model="mrForm.url" placeholder="GitLab MR 或 GitHub PR 链接" clearable />
                </el-form-item>
                <el-form-item label="代码变更">
                  <el-input v-model="mrForm.diffText" type="textarea" :rows="8" placeholder="可选：粘贴 unified diff 或修改前/后内容（多文件可多次保存）" />
                </el-form-item>
                <el-form-item>
                  <el-button type="primary" @click="saveMrInfo" :loading="mrSaving">保存</el-button>
                </el-form-item>
              </el-form>
            </div>
          </div>
        </el-tab-pane>

        <!-- 导出 -->
        <el-tab-pane label="导出" name="export">
          <div style="padding: 48px; text-align: center;">
            <p style="color: var(--gs-text-muted); margin-bottom: 8px;">导出文件均含多函数交汇临界点与按发现生成的用例；步骤与预期可复制加入回归套件。</p>
            <p style="color: var(--gs-text-muted); margin-bottom: 24px;">选择格式下载或打开报告</p>
            <div style="display: flex; flex-wrap: wrap; gap: 16px; justify-content: center;">
              <div class="gs-export-card" @click="doExport('json')">
                <el-icon :size="32" color="#4B9FD5"><Document /></el-icon>
                <div class="gs-export-label">JSON 测试用例</div>
                <div class="gs-export-desc">结构化用例 + 交汇临界点</div>
              </div>
              <div class="gs-export-card" @click="doExport('csv')">
                <el-icon :size="32" color="#00AA00"><Grid /></el-icon>
                <div class="gs-export-label">CSV 表格</div>
                <div class="gs-export-desc">先交汇点再用例，可导入测试管理</div>
              </div>
              <div class="gs-export-card" @click="doExport('sfmea')">
                <el-icon :size="32" color="#7C3AED"><Document /></el-icon>
                <div class="gs-export-label">SFMEA 条目 (CSV)</div>
                <div class="gs-export-desc">RPN、严重度等</div>
              </div>
              <div class="gs-export-card" @click="doExport('markdown')">
                <el-icon :size="32" color="#7C3AED"><Document /></el-icon>
                <div class="gs-export-label">Markdown 清单</div>
                <div class="gs-export-desc">含步骤、预期、如何执行</div>
              </div>
              <div class="gs-export-card" @click="doExport('critical')">
                <el-icon :size="32" color="#D4333F"><Connection /></el-icon>
                <div class="gs-export-label">仅交汇临界点</div>
                <div class="gs-export-desc">JSON，快速粘贴到测试系统</div>
              </div>
              <div class="gs-export-card" @click="doExport('html')">
                <el-icon :size="32" color="#0ea5e9"><Document /></el-icon>
                <div class="gs-export-label">HTML 报告</div>
                <div class="gs-export-desc">单页汇总，分享或归档</div>
              </div>
              <div class="gs-export-card" @click="doExport('findings')">
                <el-icon :size="32" color="#EAB308"><DataLine /></el-icon>
                <div class="gs-export-label">原始发现</div>
                <div class="gs-export-desc">完整发现及 AI 增强数据</div>
              </div>
            </div>
          </div>
        </el-tab-pane>
      </el-tabs>
    </div>
  </div>
</template>

<script>
import { use } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import { RadarChart } from 'echarts/charts'
import { TitleComponent, TooltipComponent, LegendComponent } from 'echarts/components'
import VChart from 'vue-echarts'
import { ElMessage } from 'element-plus'
import { WarningFilled, Connection, EditPen } from '@element-plus/icons-vue'
import api from '../api.js'
import { useRiskColor } from '../composables/useRiskColor.js'
import { useModuleNames } from '../composables/useModuleNames.js'
import { useTestSuggestion } from '../composables/useTestSuggestion.js'
import { getRiskTypeName } from '../composables/useRiskTypeNames.js'
import { useFormatDate } from '../composables/useFormatDate.js'
import EvidenceRenderer from '../components/EvidenceRenderer.vue'

use([CanvasRenderer, RadarChart, TitleComponent, TooltipComponent, LegendComponent])

export default {
  name: 'TaskDetail',
  components: { VChart, EvidenceRenderer, WarningFilled, Connection, EditPen },
  props: { taskId: String },
  setup() {
    const { riskColor, riskLevel, severityType, statusType, statusLabel } = useRiskColor()
    const { getDisplayName } = useModuleNames()
    const { getTestObjective, getTestSteps, getTestExpected } = useTestSuggestion()
    const { formatDate } = useFormatDate()
    return { riskColor, riskLevel, severityType, statusType, statusLabel, getDisplayName, getTestObjective, getTestSteps, getTestExpected, formatDate }
  },
  data() {
    return {
      task: {},
      results: {},
      modules: [],
      findings: [],
      aiSummaries: {},
      crossModuleAi: null,
      activeTab: 'modules',
      filterSeverity: '',
      filterModule: '',
      mrForm: { url: '', diffText: '' },
      mrSaving: false,
      sfmeaLoading: false,
    }
  },
  computed: {
    taskOptions() {
      return this.task?.options || null
    },
    filteredFindings() {
      let list = this.findings
      if (this.filterSeverity) list = list.filter(f => f.severity === this.filterSeverity)
      if (this.filterModule) list = list.filter(f => f.module_id === this.filterModule)
      return list
    },
    taskProjectId() {
      return this.task?.project_id || null
    },
    coverageFindings() {
      return this.findings
        .filter(f => f.module_id === 'coverage_map' && f.evidence)
        .map(f => ({
          ...f,
          line_coverage: f.evidence?.line_coverage || 0,
          branch_coverage: f.evidence?.branch_coverage || 0,
        }))
    },
    avgLineCoverage() {
      const covs = this.coverageFindings
      if (!covs.length) return 0
      return covs.reduce((s, f) => s + (f.line_coverage || 0), 0) / covs.length
    },
    avgBranchCoverage() {
      const covs = this.coverageFindings
      if (!covs.length) return 0
      return covs.reduce((s, f) => s + (f.branch_coverage || 0), 0) / covs.length
    },
    zeroCoverageCount() {
      return this.coverageFindings.filter(f => (f.line_coverage || 0) === 0).length
    },
    /** 灰盒核心：多函数交汇临界点（来自跨模块 AI 的 critical_combinations），一次用例即可暴露不可接受结果 */
    criticalCombinations() {
      const list = this.crossModuleAi?.test_suggestions || []
      return list.filter(s => s && (s.type === 'critical_combination' || (s.related_functions && s.related_functions.length)))
    },
    aiEnabled() {
      return Object.keys(this.aiSummaries).length > 0
    },
    aiSuccessCount() {
      return Object.values(this.aiSummaries).filter(a => a.success).length
    },
    aiFailCount() {
      return Object.values(this.aiSummaries).filter(a => !a.success && !a.skipped).length
    },
    radarOption() {
      const mods = this.modules.filter(m => m.status === 'success' && m.risk_score != null)
      if (!mods.length) return {}
      return {
        tooltip: {},
        radar: {
          indicator: mods.map(m => ({ name: this.getDisplayName(m.module), max: 1 })),
        },
        series: [{
          type: 'radar',
          data: [{ value: mods.map(m => m.risk_score || 0), name: '风险评分' }],
          lineStyle: { color: '#4B9FD5' },
          itemStyle: { color: '#4B9FD5' },
          areaStyle: { opacity: 0.2, color: '#4B9FD5' },
        }],
      }
    },
    /** MR 变更中的文件路径列表（与本次任务分析关联） */
    mrDiffPaths() {
      const diff = this.taskOptions?.mr_diff
      if (!Array.isArray(diff)) return []
      return diff.map(d => (d.path || '').trim()).filter(Boolean)
    },
    /** 本次任务发现中落在 MR 涉及文件上的项（联系起来分析） */
    findingsInMrFiles() {
      const paths = this.mrDiffPaths
      if (!paths.length) return []
      const norm = s => (s || '').replace(/^\/+/, '')
      return this.findings.filter(f => {
        const fp = norm(f.file_path || '')
        if (!fp) return false
        return paths.some(p => {
          const pp = norm(p)
          return fp === pp || fp.endsWith('/' + pp) || pp.endsWith('/' + fp)
        })
      })
    },
  },
  async mounted() {
    await this.loadAll()
  },
  methods: {
    async loadAll() {
      try {
        this.task = await api.getTaskStatus(this.taskId)
        this.mrForm.url = this.task?.options?.mr_url || ''
        this.mrForm.diffText = ''
        this.results = await api.getTaskResults(this.taskId)
        this.modules = this.results.modules || []
        // 尝试读取跨模块 AI 综合结果（存储在 task 的 error_json 中）
        if (this.task.error_json) {
          try {
            const errData = typeof this.task.error_json === 'string' ? JSON.parse(this.task.error_json) : this.task.error_json
            if (errData && errData.cross_module_ai) {
              this.crossModuleAi = errData.cross_module_ai
            }
          } catch {}
        }
      } catch {}
      try {
        const url = api.exportUrl(this.taskId, 'findings')
        const res = await fetch(url)
        const data = await res.json()
        const allFindings = []
        const aiSummaries = {}
        for (const mod of (data.modules || [])) {
          allFindings.push(...(mod.findings || []))
          if (mod.ai_summary) {
            aiSummaries[mod.module_id || mod.module] = mod.ai_summary
          }
        }
        this.findings = allFindings
        this.aiSummaries = aiSummaries
      } catch {}
    },
    riskTypeTag(type) {
      if (!type) return 'info'
      if (type.includes('critical') || type.includes('crash') || type.includes('deadlock')) return 'danger'
      if (type.includes('error') || type.includes('cleanup')) return 'danger'
      if (type.includes('race') || type.includes('leak') || type.includes('overflow')) return 'warning'
      if (type.includes('boundary') || type.includes('transform_risk')) return 'warning'
      if (type.includes('external_to_sensitive') || type.includes('deep_param')) return 'danger'
      if (type.includes('cross_function')) return 'danger'
      if (type.includes('state') || type.includes('impact')) return ''
      return ''
    },
    riskTypeLabel(type) {
      return getRiskTypeName(type)
    },
    shortenPath(path) {
      if (!path) return '-'
      const parts = path.split('/')
      if (parts.length <= 3) return path
      return '.../' + parts.slice(-2).join('/')
    },
    sourceLink(row) {
      if (!this.taskProjectId || !row.file_path) return '#'
      let link = `/projects/${this.taskProjectId}/code?path=${encodeURIComponent(row.file_path)}`
      if (row.line_start) link += `&line=${row.line_start}`
      return link
    },
    covColor(val) {
      if (!val || val === 0) return '#D4333F'
      if (val < 0.3) return '#D4333F'
      if (val < 0.7) return '#E57F00'
      return '#00AA00'
    },
    covBarClass(val) {
      if (!val || val === 0) return 'cov-zero'
      if (val < 0.3) return 'cov-low'
      if (val < 0.7) return 'cov-medium'
      return 'cov-high'
    },
    doExport(fmt) {
      window.open(api.exportUrl(this.taskId, fmt), '_blank')
    },
    async doRetry() {
      try { await api.retryTask(this.taskId, {}); ElMessage.success('重试已提交'); await this.loadAll() }
      catch (e) { ElMessage.error('重试失败: ' + e.message) }
    },
    async doCancel() {
      try { await api.cancelTask(this.taskId); ElMessage.success('已取消'); await this.loadAll() }
      catch (e) { ElMessage.error('取消失败: ' + e.message) }
    },
    async doGenerateSfmea() {
      this.sfmeaLoading = true
      try {
        const data = await api.generateSfmea(this.taskId)
        ElMessage.success(data?.generated != null ? `已生成 ${data.generated} 条 SFMEA 条目` : 'SFMEA 已生成')
      } catch (e) {
        ElMessage.error('生成 SFMEA 失败: ' + e.message)
      } finally {
        this.sfmeaLoading = false
      }
    },
    async saveMrInfo() {
      this.mrSaving = true
      try {
        const payload = { mr_url: this.mrForm.url || null }
        if (this.mrForm.diffText && this.mrForm.diffText.trim()) {
          payload.mr_diff = [{ path: '', unified_diff: this.mrForm.diffText.trim() }]
        }
        await api.updateTaskMr(this.taskId, payload)
        ElMessage.success('MR 信息已更新')
        this.task = await api.getTaskStatus(this.taskId)
      } catch (e) {
        ElMessage.error('保存失败: ' + e.message)
      } finally {
        this.mrSaving = false
      }
    },
  },
}
</script>

<style scoped>
.gs-task-nav { margin-bottom: var(--gs-space-sm); }
.gs-back-link { font-size: var(--gs-font-sm); color: var(--gs-text-link); text-decoration: none; }
.gs-back-link:hover { text-decoration: underline; }

.gs-task-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
}
.gs-task-header-right { display: flex; gap: var(--gs-space-sm); }
.gs-task-id {
  font-family: var(--gs-font-mono);
  font-size: var(--gs-font-sm);
  background: #F5F5F5;
  padding: 2px 8px;
  border-radius: 3px;
}

.gs-stat-row {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: var(--gs-space-md);
}
.gs-stat-sub {
  font-size: var(--gs-font-xs);
  color: var(--gs-text-muted);
}

.gs-toolbar { display: flex; justify-content: space-between; align-items: center; }
.gs-toolbar-left { display: flex; gap: var(--gs-space-sm); }
.gs-result-count { font-size: var(--gs-font-sm); color: var(--gs-text-muted); }

.gs-risk-bar { height: 6px; background: var(--gs-border-light); border-radius: 3px; overflow: hidden; }
.gs-risk-bar-fill { height: 100%; border-radius: 3px; }

.gs-code-block {
  background: #1E1E1E;
  color: #D4D4D4;
  padding: 12px;
  border-radius: 6px;
  font-family: var(--gs-font-mono);
  font-size: 12px;
  overflow-x: auto;
  white-space: pre-wrap;
}

.gs-export-card {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  padding: 24px 32px;
  border: 1px solid var(--gs-border);
  border-radius: var(--gs-radius-lg);
  cursor: pointer;
  transition: all var(--gs-transition);
  min-width: 160px;
}
.gs-export-card:hover {
  border-color: var(--gs-primary);
  box-shadow: var(--gs-shadow-md);
}
.gs-export-label { font-weight: 600; font-size: 14px; }
.gs-export-desc { font-size: 12px; color: var(--gs-text-muted); }

/* ── MR 代码变更 ───────────────────── */
.gs-mr-block { padding: 16px; }
.gs-mr-display { margin-bottom: 20px; }
.gs-mr-section { margin-bottom: 20px; }
.gs-mr-link { color: var(--gs-primary); word-break: break-all; }
.gs-mr-empty { color: var(--gs-text-muted); margin-bottom: 16px; }
.gs-mr-diff-file { margin-bottom: 20px; border: 1px solid var(--gs-border); border-radius: 8px; overflow: hidden; }
.gs-mr-diff-path { padding: 8px 12px; background: #f5f5f5; font-family: var(--gs-font-mono); font-size: 12px; }
.gs-mr-diff-unified, .gs-mr-diff-pre {
  margin: 0; padding: 12px; font-family: var(--gs-font-mono); font-size: 12px;
  background: #1e1e1e; color: #d4d4d4; overflow-x: auto; white-space: pre-wrap; max-height: 400px; overflow-y: auto;
}
.gs-mr-diff-cols { display: grid; grid-template-columns: 1fr 1fr; gap: 0; }
.gs-mr-diff-col { border-right: 1px solid var(--gs-border); }
.gs-mr-diff-col:last-child { border-right: none; }
.gs-mr-diff-col-title { padding: 6px 12px; background: #eee; font-size: 12px; font-weight: 600; }
.gs-mr-diff-col .gs-mr-diff-pre { max-height: 300px; }
.gs-mr-form { margin-top: 16px; }
.gs-mr-intro { margin-bottom: 16px; }
.gs-mr-linkage { background: var(--gs-bg-subtle, #f8f9fa); border-radius: 8px; padding: 12px 16px; }
.gs-mr-linkage-desc { font-size: 13px; color: var(--gs-text-secondary); margin-bottom: 10px; }
.gs-mr-paths { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 12px; }
.gs-mr-path-tag { font-family: var(--gs-font-mono); font-size: 11px; padding: 4px 8px; background: #e8eaed; border-radius: 4px; }
.gs-mr-findings .gs-table { margin-top: 8px; }
.gs-mr-findings .gs-file-link { color: var(--gs-primary); text-decoration: none; }
.gs-mr-findings .gs-file-link:hover { text-decoration: underline; }

/* ── 内联测试建议 ──────────────────── */
.gs-inline-test-suggestion {
  margin-top: 12px;
  background: rgba(75, 159, 213, 0.04);
  border: 1px solid rgba(75, 159, 213, 0.15);
  border-radius: 8px;
  overflow: hidden;
}
.gs-inline-ts-title {
  display: flex; align-items: center; gap: 6px;
  padding: 8px 14px;
  background: rgba(75, 159, 213, 0.08);
  font-size: 13px; font-weight: 600; color: var(--gs-primary);
}
.gs-inline-ts-body {
  padding: 12px 14px;
  font-size: 13px; color: var(--gs-text-primary); line-height: 1.6;
}
.gs-inline-ts-body p { margin: 0 0 6px 0; }
.gs-inline-ts-steps {
  margin: 4px 0 8px 0; padding-left: 18px;
  color: var(--gs-text-secondary);
}
.gs-inline-ts-steps li { padding: 2px 0; }
.gs-inline-ts-steps li::marker { color: var(--gs-primary); font-weight: 600; }
.gs-inline-ts-expected { color: var(--gs-success) !important; font-weight: 500; }

/* ── 风险原因 ──────────────────────── */
.gs-risk-reason { max-width: 220px; }
.gs-risk-reason-text {
  font-size: 12px; color: var(--gs-text-secondary); line-height: 1.4;
  display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden;
}

.gs-risk-detail-block {
  background: rgba(234, 179, 8, 0.06); border: 1px solid rgba(234, 179, 8, 0.2);
  border-radius: 8px; padding: 12px 16px; margin-bottom: 12px;
}
.gs-risk-detail-title {
  display: flex; align-items: center; gap: 6px;
  font-size: 14px; font-weight: 600; color: var(--gs-text-primary); margin-bottom: 8px;
}
.gs-risk-detail-desc {
  margin: 0 0 8px; font-size: 13px; color: var(--gs-text-primary); line-height: 1.6;
}
.gs-risk-detail-type { display: flex; align-items: center; gap: 6px; }
.gs-risk-location-block {
  margin-bottom: 12px; font-size: 13px; display: flex; align-items: center; flex-wrap: wrap;
}

/* ── 源码链接 ──────────────────────── */
.gs-source-link-wrap { display: flex; flex-direction: column; gap: 2px; }
.gs-source-link {
  font-family: var(--gs-font-mono); font-size: 11px;
  color: var(--gs-text-link); text-decoration: none;
  display: inline-flex; align-items: baseline;
}
.gs-source-link:hover { text-decoration: underline; }
.gs-source-file { word-break: break-all; }
.gs-source-line { color: var(--gs-primary); font-weight: 600; }
.gs-source-symbol {
  font-family: var(--gs-font-mono); font-size: 11px;
  color: var(--gs-text-muted);
}

/* ── 覆盖率 ────────────────────────── */
.gs-coverage-section { padding: 8px 0; }
.gs-cov-bar-wrap {
  flex: 1; height: 8px; background: var(--gs-border-light); border-radius: 4px; overflow: hidden;
}
.gs-cov-bar { height: 100%; border-radius: 4px; transition: width 0.3s; }
.gs-cov-bar.cov-zero { background: var(--gs-danger); min-width: 2px; }
.gs-cov-bar.cov-low { background: #D4333F; }
.gs-cov-bar.cov-medium { background: #E57F00; }
.gs-cov-bar.cov-high { background: #00AA00; }
.gs-file-link {
  font-family: var(--gs-font-mono); font-size: 12px;
  color: var(--gs-text-link); text-decoration: none;
}
.gs-file-link:hover { text-decoration: underline; }
.gs-file-path { font-family: var(--gs-font-mono); font-size: 12px; }

/* ── 调用链上下文 ──────────────────── */
.gs-propagation-block {
  background: rgba(139, 92, 246, 0.04);
  border: 1px solid rgba(139, 92, 246, 0.15);
  border-radius: 8px; padding: 12px 16px; margin-bottom: 12px;
}
.gs-propagation-title {
  display: flex; align-items: center; gap: 6px;
  font-size: 14px; font-weight: 600; color: #8B5CF6; margin-bottom: 10px;
}
.gs-propagation-chain {
  display: flex; flex-direction: column; gap: 2px;
  padding-left: 4px;
}
.gs-propagation-step {
  display: flex; align-items: center; gap: 8px;
  position: relative;
}
.gs-propagation-step-num {
  min-width: 24px; height: 24px;
  display: flex; align-items: center; justify-content: center;
  border-radius: 50%; font-size: 11px; font-weight: 700;
  background: rgba(139, 92, 246, 0.1); color: #8B5CF6;
}
.gs-propagation-entry .gs-propagation-step-num {
  background: rgba(0, 170, 0, 0.15); color: #00AA00;
}
.gs-propagation-sink .gs-propagation-step-num {
  background: rgba(213, 0, 0, 0.15); color: #D50000;
}
.gs-propagation-step-body {
  display: flex; align-items: center; gap: 8px; flex: 1;
}
.gs-propagation-func {
  font-family: var(--gs-font-mono); font-size: 12px;
  background: rgba(139, 92, 246, 0.08); padding: 2px 8px; border-radius: 4px;
}
.gs-propagation-transform {
  font-size: 11px; color: #E57F00;
}
.gs-propagation-transform code {
  background: rgba(229, 127, 0, 0.1); padding: 1px 4px; border-radius: 3px;
}
.gs-propagation-passthrough {
  font-size: 11px; color: var(--gs-text-muted);
}
.gs-propagation-arrow {
  color: #8B5CF6; font-size: 14px; font-weight: bold;
  padding-left: 6px;
}
.gs-propagation-external-warn {
  display: flex; align-items: center; gap: 6px;
  margin-top: 8px; padding: 6px 10px;
  background: rgba(213, 0, 0, 0.06); border-radius: 6px;
  font-size: 12px; color: #D50000; font-weight: 600;
}
.gs-propagation-scenario {
  margin-top: 8px; font-size: 12px; color: var(--gs-text-secondary); line-height: 1.5;
}

/* ── AI 增强 ──────────────────────── */
.gs-ai-empty {
  padding: 48px; text-align: center;
}
.gs-ai-empty p { margin: 8px 0; color: var(--gs-text-muted); }
.gs-ai-results { display: flex; flex-direction: column; gap: 16px; padding: 8px 0; }
.gs-ai-module-card {
  border: 1px solid var(--gs-border); border-radius: 8px; padding: 16px;
  background: var(--gs-surface);
}
.gs-ai-module-header {
  display: flex; align-items: center; gap: 8px; margin-bottom: 12px;
}
.gs-ai-module-name { font-weight: 600; font-size: 14px; }
.gs-ai-section-title {
  font-size: 12px; font-weight: 600; color: var(--gs-text-muted);
  margin-bottom: 8px; text-transform: uppercase; letter-spacing: 0.5px;
}
.gs-ai-text {
  background: var(--gs-bg); border-radius: 6px; padding: 12px;
  font-size: 13px; line-height: 1.6; white-space: pre-wrap; word-break: break-word;
  font-family: inherit; max-height: 400px; overflow-y: auto;
}
.gs-ai-summary-content { margin-bottom: 16px; }
.gs-ai-suggestions { margin-bottom: 12px; }
.gs-ai-suggestion-item {
  background: var(--gs-bg); border-radius: 6px; padding: 10px 12px;
  margin-bottom: 8px; font-size: 13px;
}
.gs-ai-error {
  display: flex; align-items: center; gap: 8px;
  padding: 10px 12px; background: rgba(213, 0, 0, 0.05); border-radius: 6px;
  font-size: 13px; color: #D50000;
}
.gs-ai-usage {
  font-size: 11px; color: var(--gs-text-muted); margin-top: 8px;
  padding-top: 8px; border-top: 1px solid var(--gs-border);
}

/* ── 跨模块 AI 综合 ────────────────── */
.gs-ai-cross-module-card {
  border: 2px solid rgba(139, 92, 246, 0.3);
  border-radius: 10px; padding: 16px;
  background: linear-gradient(135deg, rgba(139, 92, 246, 0.03), rgba(75, 159, 213, 0.03));
  margin-bottom: 8px;
}
.gs-ai-cross-section {
  margin-bottom: 16px;
}
.gs-ai-cross-item {
  background: var(--gs-surface); border-radius: 8px; padding: 12px;
  margin-bottom: 8px; border: 1px solid var(--gs-border);
}
.gs-ai-cross-item-header {
  display: flex; align-items: center; gap: 6px; margin-bottom: 6px;
}
.gs-ai-cross-desc {
  margin: 0; font-size: 13px; color: var(--gs-text-secondary); line-height: 1.6;
}
.gs-ai-cross-modules {
  margin-top: 6px; font-size: 12px; color: var(--gs-text-muted);
}
.gs-ai-cross-chain {
  margin-top: 6px; font-size: 12px;
}
.gs-ai-cross-chain code {
  background: rgba(139, 92, 246, 0.08); padding: 2px 6px; border-radius: 4px;
  font-family: var(--gs-font-mono); font-size: 11px;
}
.gs-ai-cross-expected {
  margin: 4px 0 0; font-size: 12px; color: var(--gs-success);
}
.gs-ai-cross-risk { border-left: 3px solid #D50000; }
.gs-ai-cross-hidden { border-left: 3px solid #E57F00; }
.gs-ai-cross-scenario { border-left: 3px solid #4B9FD5; }
.gs-critical-intersection { border: 1px solid rgba(139, 92, 246, 0.25); border-radius: 8px; padding: 12px; background: rgba(139, 92, 246, 0.04); }
.gs-ai-section-title .gs-ai-section-hint { font-size: 11px; font-weight: normal; color: var(--gs-text-muted); margin-left: 8px; }
.gs-critical-combo { border-left: 3px solid #8B5CF6; }
.gs-cc-funcs, .gs-cc-expected, .gs-cc-unacceptable { margin: 6px 0 0; font-size: 12px; }
.gs-cc-label { font-weight: 600; color: var(--gs-text-secondary); margin-right: 6px; }
.gs-cc-brief { font-size: 12px; color: var(--gs-text-muted); margin-left: 8px; font-weight: normal; }
.gs-cc-what { margin: 0 0 12px; font-size: 12px; color: var(--gs-text-secondary); line-height: 1.7; }
.gs-cc-what strong { color: var(--gs-text-primary); }
.gs-cc-empty { margin: 8px 0 0; font-size: 12px; color: var(--gs-text-muted); line-height: 1.6; }
</style>
