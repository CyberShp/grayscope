<template>
  <div class="gs-flow-narratives">
    <div v-if="!narratives.length" class="gs-empty">
      <el-empty description="暂无业务流程叙事" />
    </div>
    <el-collapse v-model="activeNames">
      <el-collapse-item v-for="(item, idx) in narratives" :key="idx" :name="idx">
        <template #title>
          <div class="gs-narrative-title">
            <el-icon><Guide /></el-icon>
            <span>{{ item.entry_point || '调用链 ' + (idx + 1) }}</span>
            <el-tag size="small" type="info">{{ (item.call_chain || []).length }} 个函数</el-tag>
          </div>
        </template>

        <div class="gs-narrative-content">
          <!-- 业务故事 -->
          <div class="gs-narrative-section">
            <h4><el-icon><Notebook /></el-icon> 业务流程故事</h4>
            <div class="gs-story-box">{{ item.narrative || '暂无' }}</div>
          </div>

          <!-- 调用链 -->
          <div class="gs-narrative-section">
            <h4><el-icon><Connection /></el-icon> 调用链</h4>
            <div class="gs-chain">
              <span v-for="(fn, i) in item.call_chain" :key="i" class="gs-chain-item">
                <span class="gs-fn-name">{{ fn }}</span>
                <el-icon v-if="i < item.call_chain.length - 1"><ArrowRight /></el-icon>
              </span>
            </div>
          </div>

          <!-- 关键步骤 -->
          <div class="gs-narrative-section" v-if="item.key_steps?.length">
            <h4><el-icon><List /></el-icon> 关键步骤（业务含义）</h4>
            <ol class="gs-steps-list">
              <li v-for="(step, i) in item.key_steps" :key="i">{{ step }}</li>
            </ol>
          </div>

          <!-- 决策点 -->
          <div class="gs-narrative-section" v-if="item.decision_points?.length">
            <h4><el-icon><SwitchFilled /></el-icon> 决策点</h4>
            <div class="gs-decision-points">
              <el-tag v-for="(dp, i) in item.decision_points" :key="i" type="warning" effect="plain">
                {{ dp }}
              </el-tag>
            </div>
          </div>

          <!-- 数据流 -->
          <div class="gs-narrative-section" v-if="item.data_flow_summary">
            <h4><el-icon><DataLine /></el-icon> 数据流向</h4>
            <p>{{ item.data_flow_summary }}</p>
          </div>

          <!-- 潜在风险 -->
          <div class="gs-narrative-section" v-if="item.potential_risks?.length">
            <h4><el-icon><Warning /></el-icon> 潜在风险</h4>
            <ul class="gs-risks-list">
              <li v-for="(risk, i) in item.potential_risks" :key="i">{{ risk }}</li>
            </ul>
          </div>
        </div>
      </el-collapse-item>
    </el-collapse>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { Guide, Notebook, Connection, ArrowRight, List, SwitchFilled, DataLine, Warning } from '@element-plus/icons-vue'

defineProps({
  narratives: { type: Array, default: () => [] },
})

const activeNames = ref([0])
</script>

<style scoped>
.gs-flow-narratives {
  padding: 8px;
}
.gs-narrative-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-weight: 500;
}
.gs-narrative-content {
  padding: 8px 16px;
}
.gs-narrative-section {
  margin-bottom: 20px;
}
.gs-narrative-section h4 {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 14px;
  color: var(--el-text-color-primary);
  margin-bottom: 8px;
}
.gs-story-box {
  background: linear-gradient(135deg, #f5f7fa 0%, #e4e7eb 100%);
  border-left: 4px solid var(--el-color-primary);
  padding: 16px;
  border-radius: 4px;
  font-size: 14px;
  line-height: 1.8;
}
.gs-chain {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 4px;
}
.gs-chain-item {
  display: flex;
  align-items: center;
  gap: 4px;
}
.gs-fn-name {
  font-family: monospace;
  background: var(--el-fill-color);
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 12px;
}
.gs-steps-list {
  margin: 0;
  padding-left: 24px;
  line-height: 1.8;
}
.gs-decision-points {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.gs-risks-list {
  margin: 0;
  padding-left: 20px;
  color: var(--el-color-warning);
}
.gs-empty {
  padding: 40px;
}
</style>
