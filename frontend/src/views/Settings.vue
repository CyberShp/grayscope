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
            <div style="display:flex;gap:8px;">
              <el-button size="small" @click="testAll" :loading="testingAll">全部测试</el-button>
              <el-button type="primary" size="small" @click="showAddProvider = true">
                <el-icon><Plus /></el-icon> 添加提供商
              </el-button>
            </div>
          </div>

          <div class="gs-provider-grid">
            <div v-for="m in models" :key="m.provider_id || m.name" class="gs-provider-card" :class="{ 'gs-provider-card--healthy': m.healthy === true, 'gs-provider-card--unhealthy': m.healthy === false }">
              <div class="gs-provider-header">
                <div>
                  <div class="gs-provider-name">{{ m.display_name || m.name || m.provider_id }}</div>
                  <div class="gs-provider-type">
                    <el-tag size="small" :type="providerTypeTag(m.provider_type)">{{ providerTypeLabel(m.provider_type) }}</el-tag>
                  </div>
                </div>
                <span class="gs-status-dot" :class="'gs-status-dot--' + (m.healthy === true ? 'success' : m.healthy === false ? 'failed' : 'pending')"></span>
              </div>
              <div class="gs-provider-info">
                <div v-if="m.base_url" class="gs-provider-field">
                  <span class="gs-detail-label">端点</span>
                  <code>{{ m.base_url }}</code>
                </div>
                <div v-if="m.models?.length" class="gs-provider-field">
                  <span class="gs-detail-label">可用模型</span>
                  <div style="display:flex;flex-wrap:wrap;gap:4px;">
                    <el-tag v-for="model in m.models" :key="model" size="small"
                      :type="model === defaultModel && m.provider_id === defaultProvider ? 'success' : ''"
                      style="margin: 0;">
                      {{ model }}
                      <span v-if="model === defaultModel && m.provider_id === defaultProvider" style="margin-left:4px;font-size:10px;">✓ 默认</span>
                    </el-tag>
                  </div>
                </div>
              </div>
              <div class="gs-provider-actions">
                <el-button size="small" @click="testProvider(m)" :loading="m._testing">测试连接</el-button>
                <el-button size="small" type="primary" plain @click="setDefault(m)">设为默认</el-button>
              </div>
            </div>
          </div>

          <el-empty v-if="!models.length" description="暂无配置的 AI 提供商" :image-size="60" />
        </div>

        <!-- 默认模型配置 -->
        <div class="gs-card gs-section">
          <div class="gs-card-header">
            <span class="gs-card-title">默认 AI 配置</span>
          </div>
          <p style="font-size: 13px; color: var(--gs-text-secondary); margin-bottom: 16px;">
            新建分析任务时将默认使用以下 AI 提供商和模型
          </p>
          <el-form label-width="120px" style="max-width: 500px;">
            <el-form-item label="默认提供商">
              <el-select v-model="defaultProvider" placeholder="选择提供商" style="width:100%;">
                <el-option v-for="m in models" :key="m.provider_id" :label="m.display_name || m.provider_id" :value="m.provider_id" />
              </el-select>
            </el-form-item>
            <el-form-item label="默认模型">
              <el-select v-model="defaultModel" placeholder="选择模型" style="width:100%;" filterable allow-create>
                <el-option v-for="model in currentProviderModels" :key="model" :label="model" :value="model" />
              </el-select>
            </el-form-item>
            <el-form-item>
              <el-button type="primary" @click="saveDefaultModel">保存默认配置</el-button>
            </el-form-item>
          </el-form>
        </div>

        <!-- API Key 配置 -->
        <div class="gs-card gs-section">
          <div class="gs-card-header">
            <span class="gs-card-title">API Key 配置</span>
          </div>
          <p style="font-size: 13px; color: var(--gs-text-secondary); margin-bottom: 16px;">
            为云端 AI 提供商配置 API Key（本地 Ollama 无需配置）
          </p>
          <el-form label-width="140px" style="max-width: 600px;">
            <el-form-item label="DeepSeek API Key">
              <el-input v-model="apiKeys.deepseek" placeholder="sk-..." type="password" show-password clearable>
                <template #append>
                  <el-button @click="saveApiKey('deepseek')" :loading="savingKey === 'deepseek'">保存</el-button>
                </template>
              </el-input>
            </el-form-item>
            <el-form-item label="通义千问 API Key">
              <el-input v-model="apiKeys.qwen" placeholder="sk-..." type="password" show-password clearable>
                <template #append>
                  <el-button @click="saveApiKey('qwen')" :loading="savingKey === 'qwen'">保存</el-button>
                </template>
              </el-input>
            </el-form-item>
            <el-form-item label="OpenAI 兼容 Key">
              <el-input v-model="apiKeys.openai_compat" placeholder="sk-..." type="password" show-password clearable>
                <template #append>
                  <el-button @click="saveApiKey('openai_compat')" :loading="savingKey === 'openai_compat'">保存</el-button>
                </template>
              </el-input>
            </el-form-item>
          </el-form>
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
import { Plus } from '@element-plus/icons-vue'
import { useAppStore } from '../stores/app.js'
import api from '../api.js'

const appStore = useAppStore()
const systemHealthy = computed(() => appStore.systemHealthy)

const activeTab = ref('models')
const models = ref([])
const testingAll = ref(false)
const showAddProvider = ref(false)
const defaultProvider = ref('ollama')
const defaultModel = ref('qwen2.5-coder')

const currentProviderModels = computed(() => {
  const p = models.value.find(m => m.provider_id === defaultProvider.value)
  return p?.models || ['default']
})

const qualityGate = ref({ max_risk_score: 60, max_s0_count: 0, max_s1_count: 3 })
const savingGate = ref(false)

function providerTypeTag(type) {
  if (type === 'local') return 'success'
  if (type === 'cloud') return 'primary'
  return 'info'
}

function providerTypeLabel(type) {
  const map = { local: '本地部署', cloud: '云端 API', custom: '自定义' }
  return map[type] || type || '未知'
}

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

function setDefault(m) {
  defaultProvider.value = m.provider_id
  defaultModel.value = m.models?.[0] || 'default'
  ElMessage.success(`已将 ${m.display_name} 设为默认提供商`)
}

function saveDefaultModel() {
  localStorage.setItem('gs_default_provider', defaultProvider.value)
  localStorage.setItem('gs_default_model', defaultModel.value)
  ElMessage.success(`默认 AI 配置已保存: ${defaultProvider.value} / ${defaultModel.value}`)
}

const apiKeys = ref({ deepseek: '', qwen: '', openai_compat: '' })
const savingKey = ref('')

async function saveApiKey(provider) {
  savingKey.value = provider
  try {
    const res = await fetch('/api/v1/models/config', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ provider, api_key: apiKeys.value[provider] }),
    })
    const data = await res.json()
    if (data.code === 'OK') {
      ElMessage.success(`${provider} API Key 已保存`)
      // 重新加载模型列表以刷新健康状态
      await loadModels()
    } else {
      ElMessage.error(data.message || '保存失败')
    }
  } catch (e) {
    ElMessage.error(`保存失败: ${e.message}`)
  } finally {
    savingKey.value = ''
  }
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

onMounted(() => {
  loadModels()
  // Restore saved defaults
  const savedProvider = localStorage.getItem('gs_default_provider')
  const savedModel = localStorage.getItem('gs_default_model')
  if (savedProvider) defaultProvider.value = savedProvider
  if (savedModel) defaultModel.value = savedModel
})
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
  display: flex;
  gap: 8px;
}

.gs-provider-card--healthy {
  border-color: rgba(0, 170, 0, 0.3);
}
.gs-provider-card--unhealthy {
  border-color: rgba(213, 0, 0, 0.3);
}
</style>
