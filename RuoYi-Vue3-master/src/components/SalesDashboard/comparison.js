import { formatMetric } from './chart.js'

const reasons = { missing_current: '本期无数据', missing_baseline: '对比期无数据', incomplete: '对比数据不完整', zero_baseline: '基期为0' }
export function changeText(comparison) {
  if (!comparison || comparison.value == null) return comparison?.reason === 'zero_baseline' ? '基期为0' : '--'
  const value = Number(comparison.value) * 100
  return `${value > 0 ? '+' : ''}${value.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}%`
}
export function changeTip(comparison, current, unit, range) {
  if (!comparison) return '暂无对比数据'
  const missing = [comparison.missing_current_months?.length ? `本期不完整月份：${comparison.missing_current_months.join('、')}` : '',
    comparison.missing_baseline_months?.length ? `对比期不完整月份：${comparison.missing_baseline_months.join('、')}` : ''].filter(Boolean)
  return [`本期：${(range || []).join(' 至 ')}；${formatMetric(current, unit)}`,
    `对比期：${comparison.start} 至 ${comparison.end}；${formatMetric(comparison.baseline, unit)}`,
    `增减：${comparison.unit === 'pp' ? changeText({ ...comparison, value: comparison.difference, reason: null }) : formatMetric(comparison.difference, unit)}`,
    reasons[comparison.reason], ...missing].filter(Boolean).join('；')
}
