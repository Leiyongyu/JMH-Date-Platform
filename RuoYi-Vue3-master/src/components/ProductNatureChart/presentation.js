// Display only new/old products; retain all backend categories for reconciliation.
export const ALL_NATURE_KEYS = ['NEW', 'OLD', 'UNKNOWN', 'CONFLICT']
export const NATURES = [
  { key: 'NEW', label: '新品', color: '#397bea' },
  { key: 'OLD', label: '老品', color: '#26a69a' }
]

export function currentMonth() {
  const parts = new Intl.DateTimeFormat('en', { timeZone: 'Asia/Shanghai', year: 'numeric', month: '2-digit' }).formatToParts(new Date())
  return `${parts.find(p => p.type === 'year').value}-${parts.find(p => p.type === 'month').value}`
}
export function monthIndex(value) {
  if (!/^20\d{2}-(0[1-9]|1[0-2])$/.test(value || '')) return NaN
  const [y, m] = value.split('-').map(Number)
  return y * 12 + m - 1
}
export function shiftMonth(value, delta) {
  const index = monthIndex(value) + delta
  return `${Math.floor(index / 12)}-${String(index % 12 + 1).padStart(2, '0')}`
}
export function rangeError(range, now = currentMonth()) {
  if (!range || range.length !== 2 || range.some(m => !Number.isFinite(monthIndex(m)))) return '请选择开始年月和结束年月'
  const span = monthIndex(range[1]) - monthIndex(range[0]) + 1
  if (span < 1 || span > 12) return '最多选择连续12个月（含开始和结束月）'
  if (range[1] > now) return '不能选择未来月份'
  return ''
}
export const ready = item => ['READY', 'EMPTY'].includes(item?.state)
export const formatNumber = value => value == null ? '--' : Number(value).toLocaleString('zh-CN')

export function segmentOptions(platform, items) {
  const options = new Map(platform === 'amz' ? [['US', '美国'], ['EU', '欧洲']] : [['德国','德国'], ['美国','美国'], ['英国','英国']])
  items.forEach(item => (item.segments || []).forEach(s => options.set(s.segment_key, s.segment_label)))
  return [...options].map(([value, label]) => ({ value, label }))
}

export function segmentItems(items, key) {
  return items.map(item => {
    if (!ready(item)) return item
    if (!Array.isArray(item.segments)) return { ...item, state: 'NO_SEGMENT_SNAPSHOT', sku_count: null, counts: null, percentages: null, message: '旧快照无区域/站点口径' }
    const segment = item.segments.find(s => s.segment_key === key)
    const zero = { sku_count: 0, counts: Object.fromEntries(ALL_NATURE_KEYS.map(key => [key, 0])), percentages: Object.fromEntries(ALL_NATURE_KEYS.map(key => [key, null])) }
    return { ...item, ...(segment || zero), segment_key: key }
  })
}

// Separate versions into independent series: never join incompatible histories.
export function chartOption(items, mode = 'count') {
  const versions = [...new Set(items.filter(ready).map(i => i.rule_version))]
  return {
    animationDuration: 250,
    color: NATURES.map(n => n.color),
    textStyle: { fontFamily: 'inherit', color: '#8793a5' },
    legend: { data: NATURES.map(n => n.label), top: 0, itemWidth: 12, itemHeight: 7, textStyle: { fontSize: 10, color: '#718096' } },
    tooltip: {
      trigger: 'axis', renderMode: 'richText', confine: true,
      formatter(params) {
        const index = params[0]?.dataIndex
        const item = items[index]
        if (!item) return ''
        const lines = [`${item.stat_month}${item.provisional ? '（当月暂计）' : ''}`]
        if (!ready(item)) return [...lines, item.message || '无历史快照'].join('\n')
        lines.push(`去重SKU ${formatNumber(item.sku_count)}`)
        NATURES.forEach(n => lines.push(`${n.label}：${formatNumber(item.counts?.[n.key])} / ${item.percentages?.[n.key] == null ? '--' : item.percentages[n.key] + '%'}`))
        return lines.join('\n')
      }
    },
    grid: { left: 6, right: 8, top: 34, bottom: 6, containLabel: true },
    xAxis: { type: 'category', boundaryGap: false, data: items.map(i => i.stat_month), axisTick: { show: false }, axisLine: { lineStyle: { color: '#dce3ec' } }, axisLabel: { fontSize: 10, formatter: value => value.slice(2), hideOverlap: true } },
    yAxis: { type: 'value', min: 0, max: mode === 'percent' ? 100 : undefined, minInterval: mode === 'percent' ? undefined : 1, splitNumber: 3, axisLabel: { fontSize: 10, formatter: mode === 'percent' ? '{value}%' : '{value}' }, splitLine: { lineStyle: { color: '#edf1f6', type: 'dashed' } } },
    series: NATURES.flatMap(n => versions.map(version => ({
      name: n.label, type: 'line', smooth: false, connectNulls: false, showSymbol: true, symbolSize: 6,
      lineStyle: { width: 2, color: n.color }, itemStyle: { color: n.color },
      data: items.map(i => ready(i) && i.rule_version === version
        ? (mode === 'percent' ? i.percentages?.[n.key] ?? null : i.counts?.[n.key] ?? null) : null)
    })))
  }
}
