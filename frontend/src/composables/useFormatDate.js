/**
 * 基于部署环境时区的时间格式化。
 * 时区由后端 GET /settings 的 system.display_timezone 下发，保证展示与部署环境一致。
 */
import { storeToRefs } from 'pinia'
import { useAppStore } from '../stores/app.js'

/**
 * @param {string} [d] - ISO 日期字符串或可被 Date 解析的值
 * @param {Intl.DateTimeFormatOptions} [options] - 传给 toLocaleString 的选项（会与 timeZone 合并）
 * @returns {string}
 */
export function useFormatDate() {
  const appStore = useAppStore()
  const { displayTimezone } = storeToRefs(appStore)

  async function ensureSettings() {
    await appStore.fetchSettings()
  }

  function formatDate(d, options = {}) {
    if (d == null || d === '') return '-'
    const date = new Date(d)
    if (Number.isNaN(date.getTime())) return '-'
    const tz = displayTimezone.value || 'Asia/Shanghai'
    return date.toLocaleString('zh-CN', {
      timeZone: tz,
      ...options,
    })
  }

  return { formatDate, ensureSettings, displayTimezone }
}
