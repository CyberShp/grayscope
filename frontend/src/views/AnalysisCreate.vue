<template>
  <div class="gs-page">
    <div class="gs-page-header">
      <h1 class="gs-page-title">新建分析任务</h1>
    </div>

    <el-card shadow="hover">
      <el-steps :active="step" align-center class="gs-section">
        <el-step title="选择项目" />
        <el-step title="配置分析" />
        <el-step title="确认执行" />
      </el-steps>

      <!-- Step 1: 选择项目 -->
      <div v-if="step === 0">
        <el-form label-width="100px" style="max-width:600px;margin:24px auto">
          <el-form-item label="项目">
            <el-select v-model="form.project_id" placeholder="请选择项目" style="width:100%" @change="onProjectChange">
              <el-option v-for="p in projects" :key="p.id ?? p.project_id" :label="p.name" :value="p.id ?? p.project_id" />
            </el-select>
          </el-form-item>
          <el-form-item label="代码仓库">
            <div style="display:flex;gap:8px;width:100%">
              <el-select v-model="form.repo_id" placeholder="请选择仓库" style="flex:1">
                <el-option v-for="r in repos" :key="r.id ?? r.repo_id" :label="r.name || r.git_url" :value="r.id ?? r.repo_id" />
              </el-select>
              <el-button type="primary" plain @click="showNewRepo = true" :disabled="!form.project_id">
                <el-icon><Plus /></el-icon> 新建仓库
              </el-button>
            </div>
          </el-form-item>
        </el-form>
        <div style="text-align:center">
          <el-button type="primary" @click="step = 1" :disabled="!form.project_id || !form.repo_id">下一步</el-button>
        </div>
      </div>

      <!-- Step 2: 配置分析 -->
      <div v-if="step === 1">
        <el-form label-width="120px" style="max-width:700px;margin:24px auto">
          <el-form-item label="任务类型">
            <el-radio-group v-model="form.task_type">
              <el-radio-button value="full">全量分析</el-radio-button>
              <el-radio-button value="file">文件分析</el-radio-button>
              <el-radio-button value="function">函数分析</el-radio-button>
              <el-radio-button value="diff">差异分析</el-radio-button>
            </el-radio-group>
          </el-form-item>
          <el-form-item label="目标路径">
            <el-input v-model="form.target.path" placeholder="例如: src/ 或 storage_module.c" />
          </el-form-item>
          <el-form-item label="分析器模块">
            <el-checkbox-group v-model="form.analyzers">
              <div v-for="mod in ANALYSIS_MODULES" :key="mod" style="margin-bottom:8px">
                <el-checkbox :value="mod">
                  <span style="font-weight:600">{{ getDisplayName(mod) }}</span>
                  <span style="color:#909399;font-size:12px;margin-left:8px">{{ getDescription(mod) }}</span>
                </el-checkbox>
              </div>
            </el-checkbox-group>
          </el-form-item>

          <el-divider>差异分析配置</el-divider>
          <template v-if="form.task_type === 'diff'">
            <el-form-item label="基准提交">
              <el-input v-model="form.revision.base_commit" placeholder="HEAD~1" />
            </el-form-item>
            <el-form-item label="目标提交">
              <el-input v-model="form.revision.head_commit" placeholder="HEAD" />
            </el-form-item>
          </template>

          <el-collapse>
            <el-collapse-item title="AI 增强配置">
              <el-form-item label="AI 提供者">
                <el-input v-model="form.ai.provider" placeholder="ollama" />
              </el-form-item>
              <el-form-item label="模型">
                <el-input v-model="form.ai.model" placeholder="qwen2.5-coder" />
              </el-form-item>
            </el-collapse-item>
          </el-collapse>
        </el-form>
        <div style="text-align:center;margin-top:20px">
          <el-button @click="step = 0">上一步</el-button>
          <el-button type="primary" @click="step = 2" :disabled="!form.analyzers.length">下一步</el-button>
        </div>
      </div>

      <!-- Step 3: 确认执行 -->
      <div v-if="step === 2 && !result">
        <el-descriptions title="分析任务配置确认" :column="2" border style="max-width:700px;margin:24px auto">
          <el-descriptions-item label="项目ID">{{ form.project_id }}</el-descriptions-item>
          <el-descriptions-item label="仓库ID">{{ form.repo_id }}</el-descriptions-item>
          <el-descriptions-item label="任务类型">{{ form.task_type }}</el-descriptions-item>
          <el-descriptions-item label="目标路径">{{ form.target.path || '（全量）' }}</el-descriptions-item>
          <el-descriptions-item label="分析器模块" :span="2">
            <el-tag v-for="m in form.analyzers" :key="m" size="small" style="margin:2px">{{ getDisplayName(m) }}</el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="AI 提供者">{{ form.ai.provider }}</el-descriptions-item>
          <el-descriptions-item label="AI 模型">{{ form.ai.model }}</el-descriptions-item>
        </el-descriptions>
        <div style="text-align:center;margin-top:24px">
          <el-button @click="step = 1">上一步</el-button>
          <el-button type="primary" @click="submit" :loading="submitting" size="large">
            <el-icon><CaretRight /></el-icon> 开始分析
          </el-button>
        </div>
      </div>

      <!-- 结果 -->
      <div v-if="result">
        <el-result icon="success" title="分析任务已创建" :sub-title="`任务ID: ${result.task_id}`">
          <template #extra>
            <el-button type="primary" @click="$router.push(`/tasks/${result.task_id}`)">查看结果</el-button>
            <el-button @click="reset">新建另一个任务</el-button>
          </template>
        </el-result>
      </div>

      <!-- 错误 -->
      <el-alert v-if="error" :title="error" type="error" show-icon closable @close="error=''" style="margin-top:16px" />
    </el-card>

    <!-- 新建仓库对话框 -->
    <el-dialog v-model="showNewRepo" title="新建仓库" width="480px" @closed="newRepo = { name: '', git_url: '' }">
      <el-form :model="newRepo" label-width="100px">
        <el-form-item label="名称">
          <el-input v-model="newRepo.name" placeholder="仓库显示名称（可选）" />
        </el-form-item>
        <el-form-item label="克隆地址" required>
          <el-input v-model="newRepo.git_url" placeholder="https://或git@..." />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showNewRepo = false">取消</el-button>
        <el-button type="primary" @click="createRepo" :loading="creatingRepo">创建</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script>
import { Plus, CaretRight } from '@element-plus/icons-vue'
import api from '../api.js'
import { useModuleNames } from '../composables/useModuleNames.js'

export default {
  name: 'AnalysisCreate',
  components: { Plus, CaretRight },
  setup() {
    const { ANALYSIS_MODULES, getDisplayName, getDescription } = useModuleNames()
    return { ANALYSIS_MODULES, getDisplayName, getDescription }
  },
  data() {
    return {
      step: 0,
      projects: [],
      repos: [],
      form: {
        project_id: null,
        repo_id: null,
        task_type: 'full',
        target: { path: '' },
        revision: { branch: 'main', base_commit: '', head_commit: '' },
        analyzers: ['branch_path', 'boundary_value', 'error_path', 'call_graph', 'concurrency', 'diff_impact', 'coverage_map'],
        ai: { provider: 'ollama', model: 'qwen2.5-coder', prompt_profile: 'default-v1' },
        options: { max_files: 500, risk_threshold: 0.6 },
      },
      submitting: false,
      result: null,
      error: '',
      showNewRepo: false,
      newRepo: { name: '', git_url: '' },
      creatingRepo: false,
    }
  },
  async mounted() {
    try {
      const data = await api.listProjects()
      this.projects = data.items || data.projects || (Array.isArray(data) ? data : [])
    } catch {}
  },
  methods: {
    async onProjectChange() {
      this.form.repo_id = null
      this.repos = []
      if (!this.form.project_id) return
      try {
        const data = await api.listRepos(this.form.project_id)
        this.repos = Array.isArray(data) ? data : (data.repos || data.items || [])
      } catch {
      }
    },
    async createRepo() {
      if (!this.newRepo.git_url) {
        this.$message.warning('请填写克隆地址')
        return
      }
      this.creatingRepo = true
      this.error = ''
      try {
        await api.createRepo(this.form.project_id, {
          name: this.newRepo.name || this.newRepo.git_url,
          git_url: this.newRepo.git_url,
        })
        this.$message.success('仓库创建成功')
        this.showNewRepo = false
        await this.onProjectChange()
      } catch (e) {
        this.error = '创建仓库失败: ' + e.message
      } finally {
        this.creatingRepo = false
      }
    },
    async submit() {
      this.submitting = true
      this.error = ''
      try {
        this.result = await api.createTask(this.form)
      } catch (e) {
        this.error = '创建失败: ' + e.message
      } finally { this.submitting = false }
    },
    reset() {
      this.step = 0
      this.result = null
      this.error = ''
    },
  },
}
</script>

<style scoped>
.gs-section { margin-bottom: 20px; }
</style>
