<template>
  <div class="gs-function-dict">
    <div class="gs-fd-toolbar">
      <el-input v-model="searchTerm" placeholder="搜索函数名或描述..." clearable style="width:300px" />
      <el-tag type="info">共 {{ Object.keys(dictionary).length }} 个函数</el-tag>
    </div>

    <div v-if="!Object.keys(dictionary).length" class="gs-empty">
      <el-empty description="暂无函数词典数据" />
    </div>

    <el-table :data="filteredList" stripe style="width:100%" max-height="600">
      <el-table-column prop="function_name" label="函数名" width="200">
        <template #default="{ row }">
          <span class="gs-fn-name">{{ row.function_name }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="business_description" label="业务描述" min-width="300">
        <template #default="{ row }">
          <span class="gs-biz-desc">{{ row.business_description }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="inputs" label="输入" width="200">
        <template #default="{ row }">
          <el-tooltip v-if="row.inputs?.length" :content="row.inputs.join(', ')" placement="top">
            <span class="gs-io">{{ row.inputs.slice(0, 2).join(', ') }}{{ row.inputs.length > 2 ? '...' : '' }}</span>
          </el-tooltip>
          <span v-else class="gs-na">-</span>
        </template>
      </el-table-column>
      <el-table-column prop="outputs" label="输出" width="180">
        <template #default="{ row }">
          <span class="gs-io">{{ row.outputs || '-' }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="side_effects" label="副作用" width="150">
        <template #default="{ row }">
          <template v-if="row.side_effects?.length">
            <el-tooltip :content="row.side_effects.join(', ')">
              <el-tag size="small" type="warning">{{ row.side_effects.length }} 个</el-tag>
            </el-tooltip>
          </template>
          <span v-else class="gs-na">无</span>
        </template>
      </el-table-column>
      <el-table-column prop="confidence" label="置信度" width="100">
        <template #default="{ row }">
          <el-progress :percentage="Math.round((row.confidence || 0) * 100)" :stroke-width="6" :color="confidenceColor(row.confidence)" style="width:60px" />
        </template>
      </el-table-column>
    </el-table>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'

const props = defineProps({
  dictionary: { type: Object, default: () => ({}) },
})

const searchTerm = ref('')

const dictList = computed(() => {
  return Object.entries(props.dictionary).map(([name, data]) => ({
    function_name: name,
    ...data,
  }))
})

const filteredList = computed(() => {
  if (!searchTerm.value) return dictList.value
  const term = searchTerm.value.toLowerCase()
  return dictList.value.filter(item => 
    item.function_name?.toLowerCase().includes(term) ||
    item.business_description?.toLowerCase().includes(term)
  )
})

function confidenceColor(val) {
  if (val >= 0.8) return '#67C23A'
  if (val >= 0.5) return '#E6A23C'
  return '#F56C6C'
}
</script>

<style scoped>
.gs-function-dict {
  padding: 8px;
}
.gs-fd-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}
.gs-fn-name {
  font-family: monospace;
  font-weight: 600;
  color: var(--el-color-primary);
}
.gs-biz-desc {
  font-size: 13px;
  line-height: 1.5;
}
.gs-io {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.gs-na {
  color: var(--el-text-color-placeholder);
  font-size: 12px;
}
.gs-empty {
  padding: 40px;
}
</style>
