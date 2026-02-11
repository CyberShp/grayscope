export function useRiskColor() {
  const riskColor = (score) => {
    if (score >= 0.8) return '#F56C6C'
    if (score >= 0.6) return '#E6A23C'
    if (score >= 0.4) return '#409EFF'
    return '#67C23A'
  }

  const riskLevel = (score) => {
    if (score >= 0.8) return '高风险'
    if (score >= 0.6) return '中风险'
    if (score >= 0.4) return '低风险'
    return '安全'
  }

  const riskType = (score) => {
    if (score >= 0.8) return 'danger'
    if (score >= 0.6) return 'warning'
    if (score >= 0.4) return ''
    return 'success'
  }

  const severityType = (sev) => {
    const map = { S0: 'danger', S1: 'danger', S2: 'warning', S3: 'info' }
    return map[sev] || 'info'
  }

  const statusType = (status) => {
    const map = { success: 'success', failed: 'danger', running: 'warning', pending: 'info', skipped: 'info', cancelled: 'info', partial_failed: 'warning' }
    return map[status] || 'info'
  }

  const statusLabel = (status) => {
    const map = { success: '成功', failed: '失败', running: '运行中', pending: '等待中', skipped: '已跳过', cancelled: '已取消', partial_failed: '部分失败' }
    return map[status] || status
  }

  return { riskColor, riskLevel, riskType, severityType, statusType, statusLabel }
}
