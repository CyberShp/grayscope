<template>
  <div class="gs-project-layout">
    <!-- 项目级子导航 -->
    <div class="gs-project-header">
      <div class="gs-project-header-inner">
        <!-- 项目信息 -->
        <div class="gs-project-info">
          <router-link to="/projects" class="gs-project-back">&larr; 所有项目</router-link>
          <div class="gs-project-name-row">
            <h1 class="gs-project-name">{{ project?.name || '加载中...' }}</h1>
            <span v-if="project?.description" class="gs-project-desc">{{ project.description }}</span>
          </div>
        </div>

        <!-- 子导航 Tab -->
        <nav class="gs-project-tabs">
          <router-link
            v-for="tab in tabs"
            :key="tab.name"
            :to="{ name: tab.name, params: { projectId } }"
            class="gs-project-tab"
            :class="{ active: isTabActive(tab) }"
          >
            <el-icon :size="15" style="margin-right: 5px"><component :is="tab.icon" /></el-icon>
            {{ tab.label }}
          </router-link>
        </nav>
      </div>
    </div>

    <!-- 子路由内容 -->
    <div class="gs-project-content">
      <router-view :project="project" :project-id="projectId" />
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { useAppStore } from '../stores/app.js'
import api from '../api.js'

const props = defineProps({
  projectId: {
    type: [String, Number],
    required: true,
  },
})

const route = useRoute()
const appStore = useAppStore()
const project = ref(null)

const tabs = [
  { name: 'ProjectOverview', label: '概览', icon: 'Odometer', match: 'overview' },
  { name: 'ProjectRepos', label: '仓库', icon: 'FolderOpened', match: 'repos' },
  { name: 'ProjectTestDesign', label: '测试设计', icon: 'EditPen', match: 'test-design' },
  { name: 'ProjectTestExecution', label: '测试执行', icon: 'VideoPlay', match: 'test-execution' },
  { name: 'ProjectIssues', label: '风险发现', icon: 'Warning', match: 'issues' },
  { name: 'ProjectMeasures', label: '度量', icon: 'TrendCharts', match: 'measures' },
  { name: 'ProjectCode', label: '代码', icon: 'Document', match: 'code' },
  { name: 'ProjectTasks', label: '任务', icon: 'List', match: 'tasks' },
]

function isTabActive(tab) {
  return route.name === tab.name
}

async function loadProject() {
  // 先尝试从 store 获取
  const cached = appStore.getProjectById(props.projectId)
  if (cached) {
    project.value = cached
    appStore.setCurrentProject(cached)
    return
  }
  // 否则从 API 加载
  try {
    if (!appStore.projects.length) {
      await appStore.fetchProjects()
    }
    const found = appStore.getProjectById(props.projectId)
    if (found) {
      project.value = found
      appStore.setCurrentProject(found)
    }
  } catch {
    // ignore
  }
}

onMounted(loadProject)
watch(() => props.projectId, loadProject)
</script>

<style scoped>
.gs-project-layout {
  display: flex;
  flex-direction: column;
  height: 100%;
}

/* ── 项目头部 ─────────────────────────── */
.gs-project-header {
  background: var(--gs-surface);
  border-bottom: 1px solid var(--gs-border);
  flex-shrink: 0;
}

.gs-project-header-inner {
  max-width: 1400px;
  margin: 0 auto;
  padding: 0 var(--gs-space-lg);
}

.gs-project-info {
  padding-top: var(--gs-space-md);
}

.gs-project-back {
  font-size: var(--gs-font-sm);
  color: var(--gs-text-link);
  text-decoration: none;
}
.gs-project-back:hover {
  text-decoration: underline;
}

.gs-project-name-row {
  display: flex;
  align-items: baseline;
  gap: var(--gs-space-md);
  margin-top: var(--gs-space-xs);
}

.gs-project-name {
  font-size: var(--gs-font-xl);
  font-weight: 600;
  color: var(--gs-text-primary);
  margin: 0;
}

.gs-project-desc {
  font-size: var(--gs-font-base);
  color: var(--gs-text-muted);
}

/* ── 子导航 Tab ───────────────────────── */
.gs-project-tabs {
  display: flex;
  gap: 0;
  margin-top: var(--gs-space-md);
}

.gs-project-tab {
  display: flex;
  align-items: center;
  padding: 10px 16px;
  font-size: var(--gs-font-base);
  color: var(--gs-text-secondary);
  text-decoration: none;
  border-bottom: 2px solid transparent;
  transition: all var(--gs-transition);
  white-space: nowrap;
}
.gs-project-tab:hover {
  color: var(--gs-text-primary);
  text-decoration: none;
}
.gs-project-tab.active {
  color: var(--gs-primary);
  border-bottom-color: var(--gs-primary);
  font-weight: 500;
}

/* ── 子路由内容 ───────────────────────── */
.gs-project-content {
  flex: 1;
  overflow-y: auto;
  background: var(--gs-bg);
}
</style>
