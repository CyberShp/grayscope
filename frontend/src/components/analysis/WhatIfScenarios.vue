<template>
  <div class="gs-whatif">
    <div v-if="!scenarios.length" class="gs-empty">
      <el-empty description="暂无 What-If 场景" />
    </div>

    <el-collapse v-model="activeNames">
      <el-collapse-item v-for="(group, idx) in scenarios" :key="idx" :name="idx">
        <template #title>
          <div class="gs-group-title">
            <el-icon><QuestionFilled /></el-icon>
            <span>调用链 {{ idx + 1 }}</span>
            <el-tag size="small" type="info">{{ group.scenarios?.length || 0 }} 个场景</el-tag>
          </div>
        </template>

        <div class="gs-group-summary" v-if="group.summary">
          <el-icon><InfoFilled /></el-icon>
          <span>{{ group.summary }}</span>
        </div>

        <div class="gs-scenarios-list">
          <el-card v-for="sc in group.scenarios" :key="sc.scenario_id" shadow="hover" class="gs-scenario-card">
            <template #header>
              <div class="gs-sc-header">
                <span class="gs-sc-id">{{ sc.scenario_id }}</span>
                <el-tag :type="riskLevelTag(sc.risk_level)" size="small">{{ sc.risk_level }}</el-tag>
              </div>
            </template>

            <div class="gs-sc-section">
              <div class="gs-sc-label">触发步骤</div>
              <span class="gs-fn-name">{{ sc.trigger_step }}</span>
            </div>

            <div class="gs-sc-section gs-whatif-question">
              <div class="gs-sc-label">What-If 问题</div>
              <p class="gs-question">{{ sc.what_if }}</p>
            </div>

            <div class="gs-sc-section">
              <div class="gs-sc-label">可能结果</div>
              <p>{{ sc.potential_outcome }}</p>
            </div>

            <div class="gs-sc-section">
              <div class="gs-sc-label">测试方法</div>
              <p class="gs-test-approach">{{ sc.test_approach }}</p>
            </div>

            <div class="gs-sc-section" v-if="sc.related_functions?.length">
              <div class="gs-sc-label">相关函数</div>
              <div class="gs-related-fns">
                <el-tag v-for="fn in sc.related_functions" :key="fn" size="small" type="info">{{ fn }}</el-tag>
              </div>
            </div>
          </el-card>
        </div>
      </el-collapse-item>
    </el-collapse>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { QuestionFilled, InfoFilled } from '@element-plus/icons-vue'

defineProps({
  scenarios: { type: Array, default: () => [] },
})

const activeNames = ref([0])

function riskLevelTag(level) {
  const map = { high: 'danger', medium: 'warning', low: 'info' }
  return map[level] || 'info'
}
</script>

<style scoped>
.gs-whatif {
  padding: 8px;
}
.gs-group-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-weight: 500;
}
.gs-group-summary {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  padding: 12px;
  background: var(--el-fill-color-light);
  border-radius: 4px;
  margin-bottom: 16px;
  font-size: 13px;
  line-height: 1.6;
}
.gs-scenarios-list {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(350px, 1fr));
  gap: 12px;
}
.gs-scenario-card {
  border-left: 4px solid var(--el-color-info);
}
.gs-scenario-card:has(.gs-question) {
  border-left-color: var(--el-color-warning);
}
.gs-sc-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.gs-sc-id {
  font-family: monospace;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.gs-sc-section {
  margin-bottom: 12px;
}
.gs-sc-label {
  font-weight: 600;
  font-size: 12px;
  color: var(--el-text-color-secondary);
  margin-bottom: 4px;
}
.gs-fn-name {
  font-family: monospace;
  background: var(--el-fill-color);
  padding: 2px 6px;
  border-radius: 4px;
  font-size: 12px;
}
.gs-question {
  font-weight: 500;
  font-size: 14px;
  color: var(--el-color-warning-dark-2);
  margin: 0;
  line-height: 1.5;
}
.gs-test-approach {
  font-size: 13px;
  background: #f0f9eb;
  padding: 8px;
  border-radius: 4px;
  margin: 0;
}
.gs-related-fns {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}
.gs-empty {
  padding: 40px;
}
</style>
