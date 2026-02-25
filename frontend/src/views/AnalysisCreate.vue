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
            <div style="display:flex;gap:8px;width:100%;flex-wrap:wrap">
              <el-select v-model="form.repo_id" placeholder="请选择仓库" style="flex:1;min-width:200px">
                <el-option v-for="r in repos" :key="r.id ?? r.repo_id" :label="repoLabel(r)" :value="r.id ?? r.repo_id" />
              </el-select>
              <el-button type="primary" plain @click="showNewRepo = true" :disabled="!form.project_id">
                <el-icon><Plus /></el-icon> 新建仓库
              </el-button>
              <el-button type="success" plain @click="showUpload = true" :disabled="!form.project_id">
                <el-icon><Upload /></el-icon> 上传压缩包
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
          <el-form-item label="任务来源">
            <el-radio-group v-model="form.options.task_source">
              <el-radio-button value="repo">仅仓库（继承特性）</el-radio-button>
              <el-radio-button value="mr">仅 MR（新增特性）</el-radio-button>
              <el-radio-button value="mr_repo">MR + 关联仓库（推荐）</el-radio-button>
            </el-radio-group>
            <div style="color:#909399;font-size:12px;margin-top:4px">关联仓库时可分析 MR 变更对已有代码的影响</div>
          </el-form-item>
          <el-form-item label="分析支柱">
            <el-radio-group v-model="form.options.pillar">
              <el-radio-button value="full">全量</el-radio-button>
              <el-radio-button value="exception">异常分支</el-radio-button>
              <el-radio-button value="concurrency">并发时序</el-radio-button>
              <el-radio-button value="protocol">协议报文</el-radio-button>
            </el-radio-group>
          </el-form-item>
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
            <div class="gs-module-hint">共 11 个核心分析模块（含 V2 支柱：异常分支、并发时序、协议报文）</div>
            <el-checkbox-group v-model="form.analyzers">
              <div v-for="mod in ANALYSIS_MODULES" :key="mod" class="gs-module-row">
                <el-checkbox :value="mod">
                  <span class="gs-module-name">{{ getDisplayName(mod) }}</span>
                  <span class="gs-module-desc">{{ getDescription(mod) }}</span>
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

          <el-divider>MR/PR 关联（可选）</el-divider>
          <el-form-item label="MR/PR 链接">
            <el-input v-model="form.options.mr_url" placeholder="GitLab MR 或 GitHub PR 链接，任务详情中可补充代码变更" clearable />
          </el-form-item>

          <el-divider>灰盒核心诉求</el-divider>
          <el-form-item label="多函数交汇临界点">
            <el-switch v-model="form.options.enable_cross_module_ai" active-text="启用" inactive-text="关闭" />
            <div style="color:#909399;font-size:12px;margin-top:6px;line-height:1.6">
              精准找到多个函数/分支在同一场景下的交汇点，<strong>一次</strong>灰盒用例即可暴露「不可接受结果」（如控制器下电、进程崩溃），无需 N 次黑盒盲测。启用后分析完成将执行跨模块 AI 综合并产出交汇临界点建议。
            </div>
          </el-form-item>

          <el-divider>AI 增强配置</el-divider>
          <el-form-item label="AI 提供者">
            <el-select v-model="form.ai.provider" placeholder="选择 AI 提供商" style="width:100%;" @change="onProviderChange">
              <el-option v-for="p in aiProviders" :key="p.provider_id" :label="p.display_name || p.provider_id" :value="p.provider_id">
                <div style="display:flex;align-items:center;gap:6px;">
                  <span :style="{ width:'8px', height:'8px', borderRadius:'50%', background: p.healthy === true ? '#00AA00' : p.healthy === false ? '#D50000' : '#999' }"></span>
                  <span style="font-weight:500;">{{ p.display_name || p.provider_id }}</span>
                  <el-tag size="small" :type="p.provider_type === 'local' ? 'success' : p.provider_type === 'cloud' ? 'primary' : 'info'" style="margin-left:auto;">
                    {{ p.provider_type === 'local' ? '本地' : p.provider_type === 'cloud' ? '云端' : '自定义' }}
                  </el-tag>
                </div>
              </el-option>
            </el-select>
            <div v-if="selectedProviderHealth === false" style="color:#D50000;font-size:12px;margin-top:4px;">
              ⚠ 当前提供商不可用，请先在"设置"中配置 API Key 或启动本地服务
            </div>
          </el-form-item>
          <el-form-item label="AI 模型">
            <el-select v-model="form.ai.model" placeholder="选择模型" style="width:100%;" filterable allow-create>
              <el-option v-for="m in currentAiModels" :key="m" :label="m" :value="m" />
            </el-select>
          </el-form-item>

          <el-divider>深度分析配置</el-divider>
          <el-form-item label="调用图深度">
            <el-slider v-model="form.options.callgraph_depth" :min="2" :max="20" :step="1" show-stops show-input style="max-width:400px" />
            <div style="color:#909399;font-size:12px;margin-top:2px">控制调用链追踪层级（建议 8-15）</div>
          </el-form-item>
          <el-form-item label="数据流分析">
            <el-switch v-model="form.options.enable_data_flow" active-text="启用" inactive-text="关闭" />
            <div style="color:#909399;font-size:12px;margin-top:2px">跨函数参数传播 & 污点追踪（依赖调用图）</div>
          </el-form-item>
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
          <el-descriptions-item label="任务来源">{{ form.options.task_source }}</el-descriptions-item>
          <el-descriptions-item label="分析支柱">{{ pillarLabel(form.options.pillar) }}</el-descriptions-item>
          <el-descriptions-item label="目标路径">{{ form.target.path || '（全量）' }}</el-descriptions-item>
          <el-descriptions-item label="分析器模块" :span="2">
            <el-tag v-for="m in form.analyzers" :key="m" size="small" style="margin:2px">{{ getDisplayName(m) }}</el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="多函数交汇临界点">{{ form.options.enable_cross_module_ai ? '启用' : '关闭' }}</el-descriptions-item>
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

    <!-- 上传压缩包对话框 -->
    <el-dialog v-model="showUpload" title="上传代码压缩包" width="480px" @closed="uploadFile = null; uploadName = ''">
      <el-form label-width="100px">
        <el-form-item label="压缩包" required>
          <el-upload
            :auto-upload="false"
            :limit="1"
            accept=".zip,.tar.gz,.tgz,.tar"
            :on-change="(f) => { uploadFile = f?.raw }"
          >
            <el-button type="primary" plain>选择 .zip / .tar.gz / .tar</el-button>
          </el-upload>
          <div style="color:#909399;font-size:12px;margin-top:6px">最大 300MB，解压后将作为代码仓库用于分析</div>
        </el-form-item>
        <el-form-item label="仓库名称">
          <el-input v-model="uploadName" placeholder="可选，默认用文件名" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showUpload = false">取消</el-button>
        <el-button type="primary" @click="doUpload" :loading="uploading">上传并创建仓库</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script>
import { Plus, CaretRight, Upload } from '@element-plus/icons-vue'
import api from '../api.js'
import { useModuleNames } from '../composables/useModuleNames.js'

export default {
  name: 'AnalysisCreate',
  components: { Plus, CaretRight, Upload },
  setup() {
    const { ANALYSIS_MODULES, getDisplayName, getDescription } = useModuleNames()
    return { ANALYSIS_MODULES, getDisplayName, getDescription }
  },
  data() {
    const savedProvider = localStorage.getItem('gs_default_provider') || 'ollama'
    const savedModel = localStorage.getItem('gs_default_model') || 'qwen2.5-coder'
    return {
      step: 0,
      projects: [],
      repos: [],
      aiProviders: [],
      form: {
        project_id: null,
        repo_id: null,
        task_type: 'full',
        target: { path: '' },
        revision: { branch: 'main', base_commit: '', head_commit: '' },
        analyzers: ['branch_path', 'boundary_value', 'error_path', 'call_graph', 'path_and_resource', 'exception', 'protocol', 'data_flow', 'concurrency', 'diff_impact', 'coverage_map'],
        ai: { provider: savedProvider, model: savedModel, prompt_profile: 'default-v1' },
        options: { max_files: 500, risk_threshold: 0.6, callgraph_depth: 12, enable_data_flow: true, enable_cross_module_ai: true, mr_url: '', task_source: 'repo', pillar: 'full' },
      },
      submitting: false,
      result: null,
      error: '',
      showNewRepo: false,
      newRepo: { name: '', git_url: '' },
      creatingRepo: false,
      showUpload: false,
      uploadFile: null,
      uploadName: '',
      uploading: false,
    }
  },
  computed: {
    currentAiModels() {
      const p = this.aiProviders.find(m => m.provider_id === this.form.ai.provider)
      return p?.models || ['default']
    },
    selectedProviderHealth() {
      const p = this.aiProviders.find(m => m.provider_id === this.form.ai.provider)
      return p?.healthy ?? null
    },
  },
  watch: {
    'form.options.pillar'(val) {
      if (!val) return
      const sets = {
        full: ['branch_path', 'boundary_value', 'error_path', 'call_graph', 'path_and_resource', 'exception', 'protocol', 'data_flow', 'concurrency', 'diff_impact', 'coverage_map'],
        exception: ['path_and_resource', 'exception'],
        concurrency: ['call_graph', 'data_flow', 'concurrency'],
        protocol: ['protocol'],
      }
      this.form.analyzers = sets[val] || sets.full
    },
  },
  async mounted() {
    try {
      const data = await api.listProjects()
      this.projects = data.items || data.projects || (Array.isArray(data) ? data : [])
    } catch {}
    try {
      const data = await api.listModels()
      this.aiProviders = data?.providers || data || []
    } catch {}
  },
  methods: {
    onProviderChange() {
      const p = this.aiProviders.find(m => m.provider_id === this.form.ai.provider)
      this.form.ai.model = p?.models?.[0] || 'default'
    },
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
    repoLabel(r) {
      const name = r.name || r.git_url || ''
      return r.git_url === 'upload' ? `📦 ${name}（上传）` : name
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
    async doUpload() {
      if (!this.uploadFile) {
        this.$message.warning('请选择压缩包文件')
        return
      }
      this.uploading = true
      this.error = ''
      try {
        const repo = await api.uploadRepo(this.form.project_id, this.uploadFile, this.uploadName || null)
        this.$message.success('上传解压成功，已创建仓库')
        this.showUpload = false
        this.uploadFile = null
        this.uploadName = ''
        await this.onProjectChange()
        this.form.repo_id = repo.repo_id ?? repo.id
      } catch (e) {
        this.error = '上传失败: ' + e.message
      } finally {
        this.uploading = false
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
    pillarLabel(pillar) {
      const m = { full: '全量', exception: '异常分支', concurrency: '并发时序', protocol: '协议报文' }
      return m[pillar] || pillar || '全量'
    },
  },
}
</script>

<style scoped>
.gs-section { margin-bottom: 20px; }
.gs-module-hint { color: #909399; font-size: 12px; margin-bottom: 8px; }
.gs-module-row { margin-bottom: 8px; }
.gs-module-name { font-weight: 600; }
.gs-module-desc { color: #909399; font-size: 12px; margin-left: 8px; }
</style>
