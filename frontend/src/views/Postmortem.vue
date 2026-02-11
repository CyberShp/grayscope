<template>
  <div class="gs-page">
    <div class="gs-page-header">
      <h1 class="gs-page-title">事后分析</h1>
      <p class="gs-page-desc">对逃逸到下游的缺陷进行事后分析，自动推断根因链并生成预防性测试建议。</p>
    </div>

    <el-row :gutter="20">
      <el-col :span="result ? 10 : 24">
        <el-card shadow="hover">
          <template #header><span style="font-weight:600">缺陷信息</span></template>
          <el-form :model="form" label-width="100px">
            <el-form-item label="项目">
              <el-select v-model="form.project_id" placeholder="选择项目" style="width:100%" @change="onProjectChange">
                <el-option v-for="p in projects" :key="p.id" :label="p.name" :value="p.id" />
              </el-select>
            </el-form-item>
            <el-form-item label="代码仓库">
              <el-select v-model="form.repo_id" placeholder="选择仓库" style="width:100%">
                <el-option v-for="r in repos" :key="r.id" :label="r.name || r.clone_url" :value="r.id" />
              </el-select>
            </el-form-item>
            <el-divider />
            <el-form-item label="缺陷标题">
              <el-input v-model="form.defect.title" placeholder="例如: pool_insert 在并发场景下出现内存泄漏" />
            </el-form-item>
            <el-form-item label="严重程度">
              <el-select v-model="form.defect.severity" style="width:100%">
                <el-option label="S0 - 紧急" value="S0" />
                <el-option label="S1 - 高" value="S1" />
                <el-option label="S2 - 中" value="S2" />
                <el-option label="S3 - 低" value="S3" />
              </el-select>
            </el-form-item>
            <el-form-item label="模块路径">
              <el-input v-model="form.defect.module_path" placeholder="例如: test_samples/storage_module.c" />
            </el-form-item>
            <el-form-item label="缺陷描述">
              <el-input v-model="form.defect.description" type="textarea" :rows="4" placeholder="详细描述缺陷现象和影响" />
            </el-form-item>
            <el-form-item label="关联提交">
              <el-input v-model="form.defect.related_commit" placeholder="git commit hash（可选）" />
            </el-form-item>
            <el-form-item>
              <el-button type="primary" @click="submit" :loading="submitting" :disabled="!form.defect.title">
                <el-icon><Search /></el-icon> 开始分析
              </el-button>
            </el-form-item>
          </el-form>
        </el-card>
      </el-col>

      <el-col :span="14" v-if="result">
        <!-- 根因链 -->
        <el-card shadow="hover" class="gs-section">
          <template #header><span style="font-weight:600">根因分析</span></template>
          <el-timeline>
            <el-timeline-item
              v-for="(rc, i) in result.root_causes"
              :key="i"
              :type="rc.confidence >= 0.8 ? 'danger' : 'warning'"
              :timestamp="`置信度: ${(rc.confidence * 100).toFixed(0)}%`"
              placement="top"
            >
              <el-card shadow="never">
                <div style="font-weight:600;margin-bottom:4px">{{ rc.category }}</div>
                <div style="font-size:13px;color:#606266">{{ rc.evidence }}</div>
              </el-card>
            </el-timeline-item>
          </el-timeline>
          <el-empty v-if="!result.root_causes?.length" description="未发现根因" />
        </el-card>

        <!-- 预防性测试 -->
        <el-card shadow="hover" class="gs-section">
          <template #header><span style="font-weight:600">预防性测试建议</span></template>
          <el-table :data="result.preventive_tests || []" stripe>
            <el-table-column prop="test_id" label="ID" width="80" />
            <el-table-column prop="category" label="类别" width="180" />
            <el-table-column prop="description" label="测试建议" />
            <el-table-column label="优先级" width="80">
              <template #default="{ row }">
                <el-tag :type="row.priority === 'P1' ? 'danger' : 'warning'" size="small">{{ row.priority }}</el-tag>
              </template>
            </el-table-column>
          </el-table>
        </el-card>

        <!-- 知识库模式 -->
        <el-card shadow="hover" v-if="result.patterns_extracted?.length">
          <template #header><span style="font-weight:600">提取的缺陷模式</span></template>
          <el-tag v-for="p in result.patterns_extracted" :key="p.pattern_key" style="margin:4px" :type="p.is_new ? 'success' : ''">
            {{ p.name }} (命中: {{ p.hit_count }})
          </el-tag>
        </el-card>
      </el-col>
    </el-row>

    <el-alert v-if="error" :title="error" type="error" show-icon closable @close="error=''" style="margin-top:16px" />
  </div>
</template>

<script>
import api from '../api.js'

export default {
  name: 'Postmortem',
  data() {
    return {
      projects: [],
      repos: [],
      form: {
        project_id: null,
        repo_id: null,
        defect: { title: '', severity: 'S1', description: '', module_path: '', related_commit: '' },
        ai: { provider: 'ollama', model: 'qwen2.5-coder', prompt_profile: 'default-v1' },
      },
      submitting: false,
      result: null,
      error: '',
    }
  },
  async mounted() {
    try {
      const data = await api.listProjects()
      this.projects = data.projects || data || []
    } catch {}
  },
  methods: {
    async onProjectChange() {
      this.form.repo_id = null
      this.repos = []
      if (!this.form.project_id) return
      try {
        const data = await api.listRepos(this.form.project_id)
        this.repos = data.repos || data || []
      } catch {}
    },
    async submit() {
      this.submitting = true
      this.error = ''
      this.result = null
      try {
        this.result = await api.createPostmortem(this.form)
      } catch (e) {
        this.error = '分析失败: ' + e.message
      } finally { this.submitting = false }
    },
  },
}
</script>

<style scoped>
.gs-section { margin-bottom: 20px; }
</style>
