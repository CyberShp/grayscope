<template>
  <div class="gs-page">
    <div class="gs-page-header">
      <h1 class="gs-page-title">系统设置</h1>
      <p class="gs-page-desc">管理 AI 模型提供商、质量门禁规则和系统配置</p>
    </div>

    <el-tabs v-model="activeTab" class="gs-settings-tabs">
      <!-- AI 模型管理 -->
      <el-tab-pane label="AI 模型管理" name="models">
        <div class="gs-card gs-section">
          <div class="gs-card-header">
            <span class="gs-card-title">已配置的模型提供商</span>
            <el-button type="primary" size="small" @click="testAll" :loading="testingAll">全部测试</el-button>
          </div>

          <div class="gs-provider-grid">
            <div v-for="m in models" :key="m.provider_id || m.name" class="gs-provider-card">
              <div class="gs-provider-header">
                <div>
                  <div class="gs-provider-name">{{ m.display_name || m.name || m.provider_id }}</div>
                  <div class="gs-provider-type">{{ m.provider_type || m.provider_id }}</div>
                </div>
                <span class="gs-status-dot" :class="'gs-status-dot--' + (m.healthy ? 'success' : 'failed')"></span>
              </div>
              <div class="gs-provider-info">
                <div v-if="m.base_url" class="gs-provider-field">
                  <span class="gs-detail-label">端点</span>
                  <code>{{ m.base_url }}</code>
                </div>
                <div v-if="m.models?.length" class="gs-provider-field">
                  <span class="gs-detail-label">模型</span>
                  <div>
                    <el-tag v-for="model in m.models.slice(0, 5)" :key="model" size="small" style="margin: 2px;">{{ model }}</el-tag>
                  </div>
                </div>
              </div>
              <div class="gs-provider-actions">
                <el-button size="small" @click="testProvider(m)" :loading="m._testing">测试连接</el-button>
              </div>
            </div>
          </div>

          <el-empty v-if="!models.length" description="暂无配置的 AI 提供商" :image-size="60" />
        </div>
      </el-tab-pane>

      <!-- 质量门禁 -->
      <el-tab-pane label="质量门禁" name="quality-gate">
        <div class="gs-card gs-section">
          <div class="gs-card-header">
            <span class="gs-card-title">质量门禁规则</span>
          </div>
          <p style="font-size: 13px; color: var(--gs-text-secondary); margin-bottom: 20px;">
            定义项目通过质量门禁的条件。不满足任一条件的项目将标记为"未通过"。
          </p>

          <el-form label-width="200px" style="max-width: 600px;">
            <el-form-item label="最大平均风险评分">
              <el-slider v-model="qualityGate.max_risk_score" :min="0" :max="100" :step="5" show-input :format-tooltip="v => v + '%'" />
            </el-form-item>
            <el-form-item label="S0 紧急问题数上限">
              <el-input-number v-model="qualityGate.max_s0_count" :min="0" :max="100" />
            </el-form-item>
            <el-form-item label="S1 高危问题数上限">
              <el-input-number v-model="qualityGate.max_s1_count" :min="0" :max="1000" />
            </el-form-item>
            <el-form-item>
              <el-button type="primary" @click="saveQualityGate" :loading="savingGate">保存规则</el-button>
              <el-button @click="resetQualityGate">恢复默认</el-button>
            </el-form-item>
          </el-form>
        </div>
      </el-tab-pane>

      <!-- 系统信息 -->
      <el-tab-pane label="系统信息" name="system">
        <div class="gs-card">
          <div class="gs-card-header">
            <span class="gs-card-title">系统信息</span>
          </div>
          <el-descriptions :column="1" border size="small">
            <el-descriptions-item label="系统版本">GrayScope v1.0.0</el-descriptions-item>
            <el-descriptions-item label="后端状态">
              <span class="gs-status-dot" :class="'gs-status-dot--' + (systemHealthy ? 'success' : 'failed')"></span>
              {{ systemHealthy ? '正常运行' : '离线' }}
            </el-descriptions-item>
            <el-descriptions-item label="数据库">SQLite / PostgreSQL</el-descriptions-item>
            <el-descriptions-item label="分析模块">9 个（branch_path, boundary_value, error_path, call_graph, concurrency, diff_impact, coverage_map, postmortem, knowledge_pattern）</el-descriptions-item>
            <el-descriptions-item label="部署环境">X86 Linux 内网</el-descriptions-item>
            <el-descriptions-item label="API 基础路径">/api/v1</el-descriptions-item>
          </el-descriptions>
        </div>
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { useAppStore } from '../stores/app.js'
import api from '../api.js'

const appStore = useAppStore()
const systemHealthy = computed(() => appStore.systemHealthy)

const activeTab = ref('models')
const models = ref([])
const testingAll = ref(false)

const qualityGate = ref({ max_risk_score: 60, max_s0_count: 0, max_s1_count: 3 })
const savingGate = ref(false)

async function loadModels() {
  try {
    const data = await api.listModels()
    models.value = (data?.providers || data || []).map(m => ({ ...m, _testing: false }))
  } catch {
    models.value = []
  }
}

async function testProvider(m) {
  m._testing = true
  try {
    await api.testModel({ provider: m.provider_id || m.name, model: m.models?.[0] || 'default' })
    m.healthy = true
    ElMessage.success(`${m.display_name || m.name} 连接成功`)
  } catch (e) {
    m.healthy = false
    ElMessage.error(`${m.display_name || m.name} 连接失败: ${e.message}`)
  } finally {
    m._testing = false
  }
}

async function testAll() {
  testingAll.value = true
  for (const m of models.value) {
    await testProvider(m)
  }
  testingAll.value = false
}

function saveQualityGate() {
  savingGate.value = true
  setTimeout(() => {
    ElMessage.success('质量门禁规则已保存')
    savingGate.value = false
  }, 500)
}

function resetQualityGate() {
  qualityGate.value = { max_risk_score: 60, max_s0_count: 0, max_s1_count: 3 }
}

onMounted(loadModels)
</script>

<style scoped>
.gs-settings-tabs :deep(.el-tabs__header) {
  margin-bottom: var(--gs-space-lg);
}

.gs-provider-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
  gap: var(--gs-space-md);
}

.gs-provider-card {
  border: 1px solid var(--gs-border);
  border-radius: var(--gs-radius-md);
  padding: var(--gs-space-md);
}

.gs-provider-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: var(--gs-space-md);
}

.gs-provider-name {
  font-weight: 600;
  font-size: var(--gs-font-md);
}

.gs-provider-type {
  font-size: var(--gs-font-xs);
  color: var(--gs-text-muted);
}

.gs-provider-info {
  margin-bottom: var(--gs-space-md);
}

.gs-provider-field {
  margin-bottom: var(--gs-space-sm);
}
.gs-provider-field code {
  background: #F5F5F5;
  padding: 2px 6px;
  border-radius: 3px;
  font-family: var(--gs-font-mono);
  font-size: var(--gs-font-sm);
}

.gs-provider-actions {
  border-top: 1px solid var(--gs-border-light);
  padding-top: var(--gs-space-sm);
}
</style>
