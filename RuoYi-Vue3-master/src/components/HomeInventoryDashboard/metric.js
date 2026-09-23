export function changeText(metric, count = false) {
  if (!metric || metric.delta == null) return '较上月 --（无可比数据）'
  if (metric.direction === 'flat') return count ? '较上月持平 · 0 个' : '较上月持平 · 0.00%'
  if (count) return `较上月 ${metric.direction === 'up' ? '↑ +' : '↓ −'}${Math.abs(Number(metric.delta)).toLocaleString()} 个`
  if (metric.change_percent == null) return '较上月 --（上月为0）'
  return `较上月 ${metric.direction === 'up' ? '↑ +' : '↓ −'}${Math.abs(Number(metric.change_percent)).toFixed(2)}%`
}
export function displayValue(value, count = false) {
  if (value == null || value === '' || !Number.isFinite(Number(value))) return '--'
  return count ? Number(value).toLocaleString() : `¥ ${Number(value).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
}
