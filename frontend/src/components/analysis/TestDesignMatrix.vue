<template>
  <div class="gs-test-matrix">
    <div class="gs-tm-toolbar">
      <el-select v-model="filterCategory" placeholder="分类" clearable size="small" style="width:140px">
        <el-option v-for="cat in categories" :key="cat" :value="cat" :label="cat" />
      </el-select>
      <el-select v-model="filterPriority" placeholder="优先级" clearable size="small" style="width:100px">
        <el-option value="P0" label="P0" />
        <el-option value="P1" label="P1" />
        <el-option value="P2" label="P2" />
        <el-option value="P3" label="P3" />
      </el-select>
      <el-input v-model="searchKeyword" placeholder="搜索..." clearable size="small" style="width:180px" />
      <div class="gs-tm-stats">
        <el-tag type="info">总计: {{ matrix.matrix?.length || 0 }}</el-tag>
        <el-tag type="danger">P0: {{ summary.by_priority?.P0 || 0 }}</el-tag>
        <el-tag type="warning">P1: {{ summary.by_priority?.P1 || 0 }}</el-tag>
      </div>
    </div>

    <div v-if="!matrix.matrix?.length" class="gs-empty">
      <el-empty description="暂无测试用例矩阵" />
    </div>

    <el-table v-else :data="filteredCases" stripe style="width:100%" max-height="600">
      <el-table-column prop="case_id" label="用例ID" width="90" fixed />
      <el-table-column prop="category" label="分类" width="100">
        <template #default="{ row }">
          <el-tag :type="categoryTag(row.category)" size="small">{{ row.category }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="scenario_name" label="场景名称" min-width="200" show-overflow-tooltip />
      <el-table-column prop="preconditions" label="前置条件" min-width="180">
        <template #default="{ row }">
          <ul class="gs-mini-list">
            <li v-for="(p, i) in row.preconditions?.slice(0, 2)" :key="i">{{ p }}</li>
            <li v-if="row.preconditions?.length > 2">...</li>
          </ul>
        </template>
      </el-table-column>
      <el-table-column prop="test_steps" label="测试步骤" min-width="200">
        <template #default="{ row }">
          <ol class="gs-mini-list">
            <li v-for="(s, i) in row.test_steps?.slice(0, 3)" :key="i">{{ s }}</li>
            <li v-if="row.test_steps?.length > 3">...</li>
          </ol>
        </template>
      </el-table-column>
      <el-table-column prop="expected_result" label="预期结果" min-width="160" show-overflow-tooltip />
      <el-table-column prop="risk_result" label="风险结果" min-width="160">
        <template #default="{ row }">
          <span class="gs-risk-result">{{ row.risk_result || '-' }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="priority" label="优先级" width="80">
        <template #default="{ row }">
          <el-tag :type="priorityTag(row.priority)" size="small">{{ row.priority }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="80" fixed="right">
        <template #default="{ row }">
          <el-button link type="primary" @click="showDetail(row)">详情</el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- 详情对话框 -->
    <el-dialog v-model="dialogVisible" :title="'测试用例: ' + (selectedCase?.case_id || '')" width="700px">
      <el-descriptions :column="2" border v-if="selectedCase">
        <el-descriptions-item label="用例ID">{{ selectedCase.case_id }}</el-descriptions-item>
        <el-descriptions-item label="分类">
          <el-tag :type="categoryTag(selectedCase.category)">{{ selectedCase.category }}</el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="优先级">
          <el-tag :type="priorityTag(selectedCase.priority)">{{ selectedCase.priority }}</el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="关联风险">
          <el-tag v-for="rid in selectedCase.risk_ids" :key="rid" size="small" style="margin:2px">{{ rid }}</el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="场景名称" :span="2">{{ selectedCase.scenario_name }}</el-descriptions-item>
        <el-descriptions-item label="前置条件" :span="2">
          <ul class="gs-list">
            <li v-for="(p, i) in selectedCase.preconditions" :key="i">{{ p }}</li>
          </ul>
        </el-descriptions-item>
        <el-descriptions-item label="测试步骤" :span="2">
          <ol class="gs-list">
            <li v-for="(s, i) in selectedCase.test_steps" :key="i">{{ s }}</li>
          </ol>
        </el-descriptions-item>
        <el-descriptions-item label="预期结果" :span="2">{{ selectedCase.expected_result }}</el-descriptions-item>
        <el-descriptions-item label="风险结果" :span="2">
          <span class="gs-risk-result-full">{{ selectedCase.risk_result || '-' }}</span>
        </el-descriptions-item>
        <el-descriptions-item label="检查点" :span="2">
          <el-tag v-for="(cp, i) in selectedCase.checkpoints" :key="i" size="small" style="margin:2px">
            {{ cp }}
          </el-tag>
        </el-descriptions-item>
      </el-descriptions>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'

const props = defineProps({
  matrix: { type: Object, default: () => ({}) },
})

const filterCategory = ref('')
const filterPriority = ref('')
const searchKeyword = ref('')
const dialogVisible = ref(false)
const selectedCase = ref(null)

const summary = computed(() => props.matrix.coverage_summary || {})

const categories = computed(() => {
  const cats = new Set((props.matrix.matrix || []).map(c => c.category))
  return Array.from(cats).sort()
})

const filteredCases = computed(() => {
  let list = props.matrix.matrix || []
  if (filterCategory.value) {
    list = list.filter(c => c.category === filterCategory.value)
  }
  if (filterPriority.value) {
    list = list.filter(c => c.priority === filterPriority.value)
  }
  if (searchKeyword.value) {
    const kw = searchKeyword.value.toLowerCase()
    list = list.filter(c =>
      c.scenario_name?.toLowerCase().includes(kw) ||
      c.case_id?.toLowerCase().includes(kw) ||
      c.expected_result?.toLowerCase().includes(kw)
    )
  }
  return list
})

function categoryTag(cat) {
  const map = {
    '正常流程': 'success',
    '边界条件': 'warning',
    '异常场景': 'danger',
    '风险验证': 'danger',
    '并发测试': 'info',
    '协议测试': 'primary',
  }
  return map[cat] || ''
}

function priorityTag(priority) {
  const map = { P0: 'danger', P1: 'warning', P2: '', P3: 'info' }
  return map[priority] || 'info'
}

function showDetail(testCase) {
  selectedCase.value = testCase
  dialogVisible.value = true
}
</script>

<style scoped>
.gs-test-matrix {
  padding: 8px;
}
.gs-tm-toolbar {
  display: flex;
  gap: 12px;
  align-items: center;
  margin-bottom: 16px;
  flex-wrap: wrap;
}
.gs-tm-stats {
  display: flex;
  gap: 8px;
  margin-left: auto;
}
.gs-mini-list {
  margin: 0;
  padding-left: 16px;
  font-size: 12px;
  line-height: 1.5;
}
.gs-risk-result {
  color: var(--el-color-danger);
  font-size: 12px;
}
.gs-risk-result-full {
  color: var(--el-color-danger);
}
.gs-list {
  margin: 0;
  padding-left: 20px;
}
.gs-empty {
  padding: 40px;
}
</style>
