import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import api from '../api.js'

export const useAppStore = defineStore('app', () => {
  // ── 全局状态 ──────────────────────────
  const systemHealthy = ref(true)
  const loading = ref(false)

  // ── 项目 ──────────────────────────────
  const projects = ref([])
  const currentProject = ref(null)

  async function fetchProjects() {
    try {
      const data = await api.listProjects()
      projects.value = data.projects || data.items || data || []
    } catch {
      projects.value = []
    }
  }

  function setCurrentProject(project) {
    currentProject.value = project
  }

  // ── 系统状态 ──────────────────────────
  async function checkHealth() {
    try {
      await api.health()
      systemHealthy.value = true
    } catch {
      systemHealthy.value = false
    }
  }

  // ── 项目查找 ──────────────────────────
  function getProjectById(id) {
    const numId = Number(id)
    return projects.value.find(p => (p.id ?? p.project_id) === numId)
  }

  return {
    systemHealthy,
    loading,
    projects,
    currentProject,
    fetchProjects,
    setCurrentProject,
    checkHealth,
    getProjectById,
  }
})
