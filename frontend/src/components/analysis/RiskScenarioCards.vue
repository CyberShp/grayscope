<template>
  <div class="gs-risk-cards">
    <div v-if="!cards.length" class="gs-empty">
      <el-empty description="暂无风险场景卡片" />
    </div>
    <div class="gs-cards-grid">
      <el-card v-for="card in cards" :key="card.card_id" shadow="hover" class="gs-risk-card">
        <template #header>
          <div class="gs-card-header">
            <span class="gs-card-id">{{ card.card_id }}</span>
            <el-tag :type="priorityTag(card.priority)" size="small">{{ card.priority }}</el-tag>
            <el-tag :type="severityTag(card.severity)" size="small">{{ card.severity }}</el-tag>
          </div>
          <div class="gs-card-title">{{ card.title }}</div>
        </template>

        <div class="gs-card-section">
          <div class="gs-section-label">业务背景</div>
          <p>{{ card.business_context }}</p>
        </div>

        <div class="gs-card-section">
          <div class="gs-section-label">风险说明</div>
          <p>{{ card.risk_explanation }}</p>
        </div>

        <div class="gs-card-section">
          <div class="gs-section-label">触发条件</div>
          <ul>
            <li v-for="(cond, i) in card.trigger_conditions" :key="i">{{ cond }}</li>
          </ul>
        </div>

        <el-divider />

        <div class="gs-card-section">
          <div class="gs-section-label gs-success">预期行为</div>
          <p>{{ card.expected_behavior }}</p>
        </div>

        <div class="gs-card-section">
          <div class="gs-section-label gs-danger">不可接受行为</div>
          <ul class="gs-danger-list">
            <li v-for="(item, i) in card.unacceptable_behaviors" :key="i">{{ item }}</li>
          </ul>
        </div>

        <el-divider />

        <div class="gs-card-section">
          <div class="gs-section-label">测试步骤</div>
          <ol>
            <li v-for="(step, i) in card.test_steps" :key="i">{{ step }}</li>
          </ol>
        </div>

        <div class="gs-card-section">
          <div class="gs-section-label">验证点</div>
          <el-tag v-for="(vp, i) in card.verification_points" :key="i" size="small" style="margin:2px">
            {{ vp }}
          </el-tag>
        </div>
      </el-card>
    </div>
  </div>
</template>

<script setup>
defineProps({
  cards: { type: Array, default: () => [] },
})

function severityTag(severity) {
  const map = { critical: 'danger', high: 'warning', medium: '', low: 'info' }
  return map[severity] || 'info'
}

function priorityTag(priority) {
  const map = { P0: 'danger', P1: 'warning', P2: '', P3: 'info' }
  return map[priority] || 'info'
}
</script>

<style scoped>
.gs-risk-cards {
  padding: 8px;
}
.gs-cards-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(400px, 1fr));
  gap: 16px;
}
.gs-risk-card {
  border-left: 4px solid var(--el-color-warning);
}
.gs-card-header {
  display: flex;
  gap: 8px;
  align-items: center;
  margin-bottom: 4px;
}
.gs-card-id {
  font-family: monospace;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.gs-card-title {
  font-weight: 600;
  font-size: 15px;
}
.gs-card-section {
  margin-bottom: 12px;
}
.gs-section-label {
  font-weight: 600;
  font-size: 13px;
  color: var(--el-text-color-regular);
  margin-bottom: 4px;
}
.gs-section-label.gs-success {
  color: var(--el-color-success);
}
.gs-section-label.gs-danger {
  color: var(--el-color-danger);
}
.gs-card-section p {
  margin: 0;
  font-size: 13px;
  line-height: 1.6;
}
.gs-card-section ul, .gs-card-section ol {
  margin: 0;
  padding-left: 20px;
  font-size: 13px;
}
.gs-danger-list li {
  color: var(--el-color-danger);
}
.gs-empty {
  padding: 40px;
}
</style>
