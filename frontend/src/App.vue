<template>
  <div class="gs-app">
    <!-- ══ 顶部全局导航栏 ══ -->
    <header class="gs-topnav">
      <div class="gs-topnav-left">
        <!-- Logo -->
        <router-link to="/projects" class="gs-topnav-brand">
          <svg class="gs-logo-icon" viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" stroke-width="2">
            <circle cx="12" cy="12" r="10"/>
            <path d="M12 2a10 10 0 0 1 0 20"/>
            <circle cx="12" cy="12" r="4"/>
          </svg>
          <span class="gs-logo-text">GrayScope</span>
        </router-link>

        <!-- 全局导航链接 -->
        <nav class="gs-topnav-links">
          <router-link
            v-for="item in navItems"
            :key="item.path"
            :to="item.path"
            class="gs-topnav-link"
            :class="{ active: isNavActive(item) }"
          >
            {{ item.label }}
          </router-link>
        </nav>
      </div>

      <div class="gs-topnav-right">
        <div class="gs-system-status" :class="{ healthy: systemHealthy }">
          <span class="gs-status-indicator"></span>
          <span class="gs-status-text">{{ systemHealthy ? '运行中' : '离线' }}</span>
        </div>
        <router-link to="/settings" class="gs-topnav-icon" title="设置">
          <el-icon :size="18"><Setting /></el-icon>
        </router-link>
      </div>
    </header>

    <!-- ══ 主内容区 ══ -->
    <main class="gs-main">
      <router-view />
    </main>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { Setting } from '@element-plus/icons-vue'
import { useAppStore } from './stores/app.js'

const route = useRoute()
const appStore = useAppStore()
const systemHealthy = computed(() => appStore.systemHealthy)

const navItems = [
  { path: '/projects', label: '项目', match: ['/projects'] },
  { path: '/code-analysis', label: '代码分析', match: ['/code-analysis'] },
  { path: '/test-design', label: '测试设计', match: ['/test-design'] },
  { path: '/test-execution', label: '测试执行', match: ['/test-execution'] },
  { path: '/execution-env', label: '执行环境', match: ['/execution-env'] },
  { path: '/issues', label: '风险发现', match: ['/issues'] },
  { path: '/tasks', label: '任务中心', match: ['/tasks', '/task'] },
  { path: '/postmortem', label: '事后分析', match: ['/postmortem'] },
  { path: '/knowledge', label: '知识库', match: ['/knowledge'] },
]

function isNavActive(item) {
  const path = route.path
  return item.match.some(m => path === m || path.startsWith(m + '/'))
}

onMounted(() => {
  appStore.fetchSettings() // 部署环境时区，用于时间展示
  appStore.checkHealth()
  appStore.fetchProjects()
})
</script>

<style>
@import './styles/global.css';

/* ══ App 根容器 ══════════════════════════ */
.gs-app {
  height: 100vh;
  display: flex;
  flex-direction: column;
}

/* ══ 顶部导航栏 ══════════════════════════ */
.gs-topnav {
  height: var(--gs-nav-height);
  background: var(--gs-nav-bg);
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 var(--gs-space-lg);
  flex-shrink: 0;
  z-index: 1000;
}

.gs-topnav-left {
  display: flex;
  align-items: center;
  gap: var(--gs-space-xl);
}

.gs-topnav-brand {
  display: flex;
  align-items: center;
  gap: var(--gs-space-sm);
  text-decoration: none;
  color: var(--gs-nav-active);
  font-weight: 700;
  font-size: var(--gs-font-lg);
  letter-spacing: 0.5px;
}
.gs-topnav-brand:hover { text-decoration: none; }

.gs-logo-icon {
  color: var(--gs-primary);
}

.gs-topnav-links {
  display: flex;
  align-items: center;
  gap: 2px;
}

.gs-topnav-link {
  padding: 6px 14px;
  border-radius: var(--gs-radius-sm);
  font-size: var(--gs-font-base);
  color: var(--gs-nav-text);
  text-decoration: none;
  transition: all var(--gs-transition);
  white-space: nowrap;
}
.gs-topnav-link:hover {
  background: var(--gs-nav-hover-bg);
  color: var(--gs-nav-active);
  text-decoration: none;
}
.gs-topnav-link.active {
  background: rgba(75, 159, 213, 0.2);
  color: var(--gs-nav-active);
  font-weight: 500;
}

.gs-topnav-right {
  display: flex;
  align-items: center;
  gap: var(--gs-space-md);
}

.gs-system-status {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: var(--gs-font-sm);
  color: var(--gs-nav-text);
}

.gs-status-indicator {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--gs-danger);
}
.gs-system-status.healthy .gs-status-indicator {
  background: var(--gs-success);
}

.gs-topnav-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  border-radius: var(--gs-radius-sm);
  color: var(--gs-nav-text);
  text-decoration: none;
  transition: all var(--gs-transition);
}
.gs-topnav-icon:hover {
  background: var(--gs-nav-hover-bg);
  color: var(--gs-nav-active);
  text-decoration: none;
}

/* ══ 主内容区 ════════════════════════════ */
.gs-main {
  flex: 1;
  overflow-y: auto;
  background: var(--gs-bg);
}
</style>
