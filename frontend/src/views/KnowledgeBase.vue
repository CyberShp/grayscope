<template>
  <div class="gs-page">
    <div class="gs-page-header">
      <h1 class="gs-page-title">缺陷知识库</h1>
      <p class="gs-page-desc">浏览和搜索已知的缺陷模式，将分析发现与历史模式进行匹配，复用已验证的测试策略。</p>
    </div>

    <!-- 搜索 -->
    <el-card shadow="hover" class="gs-section">
      <div style="display:flex;gap:12px;align-items:flex-end;flex-wrap:wrap">
        <div>
          <div style="font-size:12px;color:#909399;margin-bottom:4px">项目ID</div>
          <el-input-number v-model="projectId" :min="1" size="default" style="width:120px" />
        </div>
        <div>
          <div style="font-size:12px;color:#909399;margin-bottom:4px">关键词</div>
          <el-input v-model="keyword" placeholder="搜索模式名称..." clearable style="width:220px" />
        </div>
        <div>
          <div style="font-size:12px;color:#909399;margin-bottom:4px">风险类型</div>
          <el-select v-model="riskType" placeholder="全部" clearable style="width:200px">
            <el-option v-for="t in riskTypeOptions" :key="t.id" :label="t.name" :value="t.id" />
          </el-select>
        </div>
        <el-button type="primary" @click="search" :loading="searching">
          <el-icon><Search /></el-icon> 搜索
        </el-button>
      </div>
    </el-card>

    <!-- 模式列表 -->
    <div v-if="searched">
      <el-empty v-if="!patterns.length" description="未找到匹配的缺陷模式" />
      <el-row :gutter="16">
        <el-col :span="12" v-for="p in patterns" :key="p.pattern_id" style="margin-bottom:16px">
          <el-card shadow="hover">
            <template #header>
              <div style="display:flex;justify-content:space-between;align-items:center">
                <span style="font-weight:600;font-size:15px">{{ p.name }}</span>
                <el-tag size="small">{{ getRiskTypeName(p.risk_type) }}</el-tag>
              </div>
            </template>
            <div style="display:flex;gap:20px;margin-bottom:12px">
              <div>
                <span style="color:#909399;font-size:12px">命中次数</span>
                <div style="font-size:20px;font-weight:700;color:#409EFF">{{ p.hit_count }}</div>
              </div>
              <div style="flex:1">
                <span style="color:#909399;font-size:12px">置信度</span>
                <el-progress
                  :percentage="Math.round((p.trigger_shape?.confidence || 0) * 100)"
                  :color="p.trigger_shape?.confidence >= 0.8 ? '#F56C6C' : '#E6A23C'"
                  :stroke-width="12"
                />
              </div>
            </div>
            <div v-if="p.trigger_shape?.keywords?.length" style="margin-bottom:8px">
              <span style="font-size:12px;color:#909399">触发关键词: </span>
              <el-tag v-for="kw in p.trigger_shape.keywords.slice(0, 8)" :key="kw" size="small" type="info" style="margin:2px">{{ kw }}</el-tag>
            </div>
            <div v-if="p.test_template?.test_suggestions?.length">
              <span style="font-size:12px;color:#909399">推荐测试: </span>
              <ul style="margin:4px 0 0 16px;font-size:13px;color:#606266">
                <li v-for="(t, i) in p.test_template.test_suggestions.slice(0, 3)" :key="i">{{ t.description }}</li>
              </ul>
            </div>
          </el-card>
        </el-col>
      </el-row>
    </div>

    <!-- 匹配 -->
    <el-card shadow="hover" class="gs-section" style="margin-top:20px">
      <template #header><span style="font-weight:600">发现匹配</span></template>
      <p style="color:#909399;font-size:13px;margin-bottom:16px">将某次分析任务的发现与知识库中的已知模式进行匹配，找出相似的历史缺陷。</p>
      <div style="display:flex;gap:12px;align-items:flex-end">
        <div>
          <div style="font-size:12px;color:#909399;margin-bottom:4px">任务ID</div>
          <el-input v-model="matchTaskId" placeholder="分析任务ID" style="width:280px" />
        </div>
        <div>
          <div style="font-size:12px;color:#909399;margin-bottom:4px">相似度阈值</div>
          <el-slider v-model="matchThreshold" :min="0" :max="100" :step="5" style="width:200px" />
        </div>
        <el-button type="primary" @click="matchKnowledge" :loading="matching" :disabled="!matchTaskId">匹配</el-button>
      </div>

      <el-table v-if="matches.length" :data="matches" stripe style="margin-top:16px">
        <el-table-column prop="pattern_name" label="模式名称" min-width="200" show-overflow-tooltip />
        <el-table-column prop="finding_id" label="匹配发现" width="160" />
        <el-table-column label="相似度" width="120">
          <template #default="{ row }">
            <el-progress :percentage="Math.round(row.similarity * 100)" :stroke-width="12" :text-inside="true" />
          </template>
        </el-table-column>
        <el-table-column label="推荐测试" min-width="200">
          <template #default="{ row }">
            <span v-if="row.test_template?.test_suggestions?.length">
              {{ row.test_template.test_suggestions[0]?.description || '-' }}
            </span>
            <span v-else>-</span>
          </template>
        </el-table-column>
      </el-table>
    </el-card>
  </div>
</template>

<script>
import api from '../api.js'
import { getRiskTypeName, riskTypeOptions } from '../composables/useRiskTypeNames.js'

export default {
  name: 'KnowledgeBase',
  data() {
    return {
      projectId: 1,
      keyword: '',
      riskType: '',
      patterns: [],
      searched: false,
      searching: false,
      riskTypeOptions,
      matchTaskId: '',
      matchThreshold: 40,
      matches: [],
      matching: false,
    }
  },
  async mounted() {
    await this.search()
  },
  methods: {
    getRiskTypeName,
    async search() {
      this.searching = true
      try {
        const data = await api.searchPatterns(this.projectId, this.keyword, this.riskType)
        this.patterns = data.patterns || []
        this.searched = true
      } catch {
        this.patterns = []
        this.searched = true
      } finally { this.searching = false }
    },
    async matchKnowledge() {
      this.matching = true
      try {
        const data = await api.matchKnowledge(this.projectId, this.matchTaskId, this.matchThreshold / 100)
        this.matches = data.matches || []
      } catch (e) {
        this.$message.error('匹配失败: ' + e.message)
      } finally { this.matching = false }
    },
  },
}
</script>

<style scoped>
.gs-section { margin-bottom: 20px; }
</style>
