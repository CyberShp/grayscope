<template>
  <div>
    <h2 class="page-title">仪表盘</h2>

    <!-- 统计卡片 -->
    <el-row :gutter="20" class="page-section">
      <el-col :span="6" v-for="s in statCards" :key="s.label">
        <el-card shadow="hover">
          <div style="display:flex;align-items:center;gap:16px">
            <el-icon :size="40" :color="s.color"><component :is="s.icon" /></el-icon>
            <div>
              <div style="font-size:28px;font-weight:700;color:#303133">{{ s.value }}</div>
              <div style="font-size:13px;color:#909399;margin-top:4px">{{ s.label }}</div>
            </div>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <!-- 图表 -->
    <el-row :gutter="20" class="page-section">
      <el-col :span="12">
        <el-card shadow="hover">
          <template #header><span style="font-weight:600">风险分布</span></template>
          <v-chart :option="pieOption" autoresize style="height:300px" />
        </el-card>
      </el-col>
      <el-col :span="12">
        <el-card shadow="hover">
          <template #header><span style="font-weight:600">分析器发现数</span></template>
          <v-chart :option="barOption" autoresize style="height:300px" />
        </el-card>
      </el-col>
    </el-row>

    <!-- 项目列表 -->
    <el-card shadow="hover" class="page-section">
      <template #header>
        <div style="display:flex;justify-content:space-between;align-items:center">
          <span style="font-weight:600">项目列表</span>
          <el-button type="primary" size="small" @click="showNewProject = true">
            <el-icon><Plus /></el-icon> 新建项目
          </el-button>
        </div>
      </template>
      <el-table :data="projects" stripe>
        <el-table-column label="ID" width="80">
          <template #default="{ row }">{{ row.id ?? row.project_id }}</template>
        </el-table-column>
        <el-table-column prop="name" label="项目名称" />
        <el-table-column prop="description" label="描述" />
        <el-table-column label="创建时间" width="180">
          <template #default="{ row }">{{ formatDate(row.created_at) }}</template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 最近任务 -->
    <el-card shadow="hover" class="page-section">
      <template #header><span style="font-weight:600">最近分析任务</span></template>
      <el-table :data="recentTasks" stripe>
        <el-table-column prop="task_id" label="任务ID" width="160">
          <template #default="{ row }">
            <el-link type="primary" @click="$router.push(`/task/${row.task_id}`)">{{ row.task_id.slice(0, 12) }}...</el-link>
          </template>
        </el-table-column>
        <el-table-column prop="task_type" label="类型" width="100" />
        <el-table-column label="状态" width="120">
          <template #default="{ row }">
            <el-tag :type="statusType(row.status)" size="small">{{ statusLabel(row.status) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="风险评分" width="180">
          <template #default="{ row }">
            <el-progress
              :percentage="Math.round((row.aggregate_risk_score || 0) * 100)"
              :color="riskColor(row.aggregate_risk_score || 0)"
              :stroke-width="14"
              :text-inside="true"
            />
          </template>
        </el-table-column>
        <el-table-column label="模块数" width="100">
          <template #default="{ row }">{{ Object.keys(row.module_status || {}).length }}</template>
        </el-table-column>
        <el-table-column label="时间" width="160">
          <template #default="{ row }">{{ formatDate(row.created_at) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="100">
          <template #default="{ row }">
            <el-button type="primary" size="small" text @click="$router.push(`/task/${row.task_id}`)">查看</el-button>
          </template>
        </el-table-column>
      </el-table>
      <el-empty v-if="!recentTasks.length" description="暂无分析任务" />
    </el-card>

    <!-- 新建项目对话框 -->
    <el-dialog v-model="showNewProject" title="新建项目" width="480px">
      <el-form :model="newProject" label-width="80px">
        <el-form-item label="名称">
          <el-input v-model="newProject.name" placeholder="请输入项目名称" />
        </el-form-item>
        <el-form-item label="描述">
          <el-input v-model="newProject.description" type="textarea" :rows="3" placeholder="项目描述（可选）" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showNewProject = false">取消</el-button>
        <el-button type="primary" @click="createProject" :loading="creating">创建</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script>
import { use } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import { PieChart, BarChart } from 'echarts/charts'
import { TitleComponent, TooltipComponent, LegendComponent, GridComponent } from 'echarts/components'
import VChart from 'vue-echarts'
import { Plus, FolderOpened, DataAnalysis, Warning, TrendCharts } from '@element-plus/icons-vue'
import api from '../api.js'
import { useRiskColor } from '../composables/useRiskColor.js'
import { useModuleNames } from '../composables/useModuleNames.js'
import { useFormatDate } from '../composables/useFormatDate.js'

use([CanvasRenderer, PieChart, BarChart, TitleComponent, TooltipComponent, LegendComponent, GridComponent])

export default {
  name: 'Dashboard',
  components: { VChart, Plus, FolderOpened, DataAnalysis, Warning, TrendCharts },
  setup() {
    const { riskColor, statusType, statusLabel } = useRiskColor()
    const { getDisplayName } = useModuleNames()
    const { formatDate } = useFormatDate()
    return { riskColor, statusType, statusLabel, getDisplayName, formatDate }
  },
  data() {
    return {
      projects: [],
      recentTasks: [],
      stats: { projects: 0, tasks: 0, findings: 0, avgRisk: 0 },
      showNewProject: false,
      newProject: { name: '', description: '' },
      creating: false,
      severityCounts: { S1: 0, S2: 0, S3: 0 },
      moduleFindingCounts: {},
    }
  },
  computed: {
    statCards() {
      return [
        { label: '项目数', value: this.stats.projects, icon: FolderOpened, color: '#409EFF' },
        { label: '分析任务', value: this.stats.tasks, icon: DataAnalysis, color: '#67C23A' },
        { label: '风险发现', value: this.stats.findings, icon: Warning, color: '#E6A23C' },
        { label: '平均风险评分', value: this.stats.avgRisk.toFixed(2), icon: TrendCharts, color: '#F56C6C' },
      ]
    },
    pieOption() {
      return {
        tooltip: { trigger: 'item' },
        legend: { bottom: 0 },
        series: [{
          type: 'pie', radius: ['40%', '70%'],
          data: [
            { value: this.severityCounts.S1, name: 'S1 高危', itemStyle: { color: '#F56C6C' } },
            { value: this.severityCounts.S2, name: 'S2 中危', itemStyle: { color: '#E6A23C' } },
            { value: this.severityCounts.S3, name: 'S3 低危', itemStyle: { color: '#409EFF' } },
          ],
          label: { formatter: '{b}: {c} ({d}%)' },
        }],
      }
    },
    barOption() {
      const names = Object.keys(this.moduleFindingCounts).map(k => this.getDisplayName(k))
      const values = Object.values(this.moduleFindingCounts)
      return {
        tooltip: { trigger: 'axis' },
        grid: { left: 100, right: 20, bottom: 20, top: 20 },
        xAxis: { type: 'value' },
        yAxis: { type: 'category', data: names },
        series: [{ type: 'bar', data: values, barWidth: 20, itemStyle: { color: '#409EFF', borderRadius: [0, 4, 4, 0] } }],
      }
    },
  },
  async mounted() {
    await this.loadData()
  },
  methods: {
    async loadData() {
      try {
        const data = await api.listProjects()
        this.projects = data.projects || data.items || data || []
        this.stats.projects = this.projects.length
      } catch { this.projects = [] }
    },
    async createProject() {
      if (!this.newProject.name) return
      this.creating = true
      try {
        await api.createProject(this.newProject)
        this.showNewProject = false
        this.newProject = { name: '', description: '' }
        await this.loadData()
        this.$message.success('项目创建成功')
      } catch (e) {
        this.$message.error('创建失败: ' + e.message)
      } finally { this.creating = false }
    },
  },
}
</script>

<style scoped>
.page-title { margin-bottom: 20px; font-size: 20px; font-weight: 600; color: #303133; }
.page-section { margin-bottom: 20px; }
</style>
