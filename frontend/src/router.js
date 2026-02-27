import { createRouter, createWebHistory } from 'vue-router'

const routes = [
  // 根路径重定向到项目列表
  { path: '/', redirect: '/projects' },

  // ── 全局页面 ──────────────────────────
  {
    path: '/projects',
    name: 'ProjectList',
    component: () => import('./views/ProjectList.vue'),
    meta: { title: '项目' },
  },
  {
    path: '/issues',
    name: 'GlobalIssues',
    component: () => import('./views/GlobalIssues.vue'),
    meta: { title: '发现' },
  },
  {
    path: '/tasks',
    name: 'TaskCenter',
    component: () => import('./views/TaskCenter.vue'),
    meta: { title: '任务中心' },
  },
  {
    path: '/tasks/:taskId',
    name: 'TaskDetail',
    component: () => import('./views/TaskDetail.vue'),
    props: true,
    meta: { title: '任务详情' },
  },
  {
    path: '/analyze',
    name: 'AnalysisCreate',
    component: () => import('./views/AnalysisCreate.vue'),
    meta: { title: '新建分析' },
  },
  {
    path: '/code-analysis',
    name: 'CodeAnalysis',
    component: () => import('./views/CodeAnalysis.vue'),
    meta: { title: '代码分析流水线' },
  },
  {
    path: '/postmortem',
    name: 'Postmortem',
    component: () => import('./views/Postmortem.vue'),
    meta: { title: '事后分析' },
  },
  {
    path: '/knowledge',
    name: 'KnowledgeBase',
    component: () => import('./views/KnowledgeBase.vue'),
    meta: { title: '知识库' },
  },
  {
    path: '/test-design',
    name: 'TestDesignCenter',
    component: () => import('./views/TestDesignCenter.vue'),
    meta: { title: '测试设计' },
  },
  {
    path: '/test-design/:testCaseId',
    name: 'TestCaseDetail',
    component: () => import('./views/TestCaseDetail.vue'),
    props: true,
    meta: { title: '测试用例详情' },
  },
  {
    path: '/test-execution',
    name: 'TestExecutionCenter',
    component: () => import('./views/TestExecutionCenter.vue'),
    meta: { title: '测试执行' },
  },
  {
    path: '/test-execution/:runId',
    name: 'TestRunDetail',
    component: () => import('./views/TestRunDetail.vue'),
    props: true,
    meta: { title: '测试运行详情' },
  },
  {
    path: '/execution-env',
    name: 'ExecutionEnv',
    component: () => import('./views/ExecutionEnv.vue'),
    meta: { title: '执行环境' },
  },
  {
    path: '/settings',
    name: 'Settings',
    component: () => import('./views/Settings.vue'),
    meta: { title: '设置' },
  },

  // ── 项目级页面（嵌套路由）──────────────
  {
    path: '/projects/:projectId',
    component: () => import('./layouts/ProjectLayout.vue'),
    props: true,
    children: [
      {
        path: '',
        redirect: to => ({ name: 'ProjectOverview', params: { projectId: to.params.projectId } }),
      },
      {
        path: 'overview',
        name: 'ProjectOverview',
        component: () => import('./views/project/ProjectOverview.vue'),
        props: true,
        meta: { title: '项目概览' },
      },
      {
        path: 'repos',
        name: 'ProjectRepos',
        component: () => import('./views/project/ProjectRepos.vue'),
        props: true,
        meta: { title: '项目仓库' },
      },
      {
        path: 'issues',
        name: 'ProjectIssues',
        component: () => import('./views/project/ProjectIssues.vue'),
        props: true,
        meta: { title: '项目发现' },
      },
      {
        path: 'measures',
        name: 'ProjectMeasures',
        component: () => import('./views/project/ProjectMeasures.vue'),
        props: true,
        meta: { title: '项目度量' },
      },
      {
        path: 'code',
        name: 'ProjectCode',
        component: () => import('./views/project/ProjectCode.vue'),
        props: true,
        meta: { title: '项目代码' },
      },
      {
        path: 'tasks',
        name: 'ProjectTasks',
        component: () => import('./views/project/ProjectTasks.vue'),
        props: true,
        meta: { title: '项目任务' },
      },
      {
        path: 'test-design',
        name: 'ProjectTestDesign',
        component: () => import('./views/project/ProjectTestDesign.vue'),
        props: true,
        meta: { title: '测试设计' },
      },
      {
        path: 'test-execution',
        name: 'ProjectTestExecution',
        component: () => import('./views/TestExecutionCenter.vue'),
        props: true,
        meta: { title: '测试执行' },
      },
    ],
  },

  // 兼容旧路由
  { path: '/task/:taskId', redirect: to => `/tasks/${to.params.taskId}` },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

router.afterEach((to) => {
  document.title = `${to.meta.title || 'GrayScope'} - GrayScope`
})

export default router
