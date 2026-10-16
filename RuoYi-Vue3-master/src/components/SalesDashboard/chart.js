export const salesMetrics = [
  { key: 'platform_income', label: '平台收入', color: '#23b7a3', icon: 'Coin' },
  { key: 'platform_expense', label: '平台支出', color: '#64748b', icon: 'Wallet' },
  { key: 'gross_profit', label: '毛利润', color: '#38b5ed', icon: 'TrendCharts' },
  { key: 'net_sales', label: '净收款', color: '#f47798', icon: 'Wallet' },
  { key: 'gross_sales', label: '销售总额', color: '#5285da', icon: 'DataAnalysis' },
  { key: 'refund_amount', label: '退款金额', color: '#f2a14a', icon: 'RefreshLeft' },
  { key: 'gross_margin', label: '毛利率', color: '#8b7ce8', icon: 'DataAnalysis', secondary: true },
  { key: 'refund_rate', label: '退款率', color: '#df789b', icon: 'PieChart', secondary: true }
]

export function formatMetric(value, unit = 'CNY', compact = false) {
  if (value == null || !Number.isFinite(Number(value))) return '--'
  const number = Number(value)
  if (unit === 'ratio') return `${(number * 100).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}%`
  const scale = compact && Math.abs(number) >= 100000000 ? 100000000 : compact && Math.abs(number) >= 10000 ? 10000 : 1
  return `¥${(number / scale).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}${scale === 100000000 ? '亿' : scale === 10000 ? '万' : ''}`
}

export function salesChartOption(report, metricKey = 'net_sales', dimension = 'total', showYear = false) {
  const metric = report.metrics?.[metricKey] || (metricKey === 'net_sales' ? report : { total: [], series: [] })
  const definition = salesMetrics.find(item => item.key === metricKey) || { label: metric.label || metricKey, color: '#6479d8' }
  const unit = metric.unit || 'CNY'
  const series = dimension === 'platform' ? (metric.platform_series || []) : dimension === 'group' ? (metric.series || [])
    : [{ name: '筛选合计', values: metric.total, comparisons: metric.point_comparisons },
      ...(showYear ? [{ name: '去年同期', values: metric.year_total, previous: true }] : [])]
  const comparisonText = value => {
    if (!value || value.value == null) return ({ incomplete: '对比数据不完整', zero_baseline: '基期为0', missing_baseline: '对比期无数据', missing_current: '本期无数据' })[value?.reason] || '--'
    const number = Number(value.value) * 100
    return `${number > 0 ? '+' : ''}${number.toFixed(2)}${value.unit === 'pp' ? '个百分点' : '%'}`
  }
  return {
    color: [definition.color, '#409eff', '#f5ad42', '#8b7ce8', '#23b7a3', '#64748b'],
    animationDuration: 350,
    animationDurationUpdate: 300,
    tooltip: {
      trigger: 'axis', renderMode: 'richText', confine: true,
      backgroundColor: '#fff', borderColor: '#e8edf5', padding: [12, 16],
      textStyle: { color: '#334155', fontSize: 12 },
      axisPointer: { type: 'line', lineStyle: { color: '#b8c5d9', type: 'dashed' } },
      valueFormatter: value => value == null ? '无数据' : formatMetric(value, unit),
      formatter: params => {
        const items = Array.isArray(params) ? params : [params]
        return [items[0]?.axisValueLabel || '', ...items.map(item => {
          const comparisons = series[item.seriesIndex]?.comparisons?.[item.dataIndex]
          return [`${item.seriesName}：${formatMetric(item.value, unit)}`, ...['mom', 'yoy'].flatMap(kind => {
            const value = comparisons?.[kind]
            return value ? [`  ${kind === 'mom' ? '环比' : '同比'} ${comparisonText(value)}（${value.start} 至 ${value.end}：${formatMetric(value.baseline, unit)}）`] : []
          })].join('\n')
        })].join('\n')
      }
    },
    legend: { type: 'scroll', bottom: 0, icon: 'roundRect', itemWidth: 14, itemHeight: 4,
      itemGap: 24, textStyle: { color: '#718096', fontSize: 12 } },
    grid: { left: 18, right: 30, top: 40, bottom: 48, containLabel: true },
    xAxis: { type: 'category', boundaryGap: false, data: report.months,
      axisTick: { show: false }, axisLine: { lineStyle: { color: '#e8edf5' } },
      axisLabel: { color: '#8090a8', margin: 16 },
      splitLine: { show: true, lineStyle: { color: '#edf1f8', type: 'dashed' } } },
    yAxis: { type: 'value', name: unit === 'ratio' ? `${definition.label}（%）` : '人民币（元）',
      nameTextStyle: { color: '#8090a8', padding: [0, 12, 8, 0] },
      axisLabel: { color: '#8090a8', formatter: value => unit === 'ratio'
        ? `${Number((Number(value) * 100).toFixed(2))}%`
        : Math.abs(value) >= 10000 ? `${Number((value / 10000).toFixed(2))}万` : Number(value).toLocaleString('zh-CN') },
      splitLine: { lineStyle: { color: '#e8edf5', type: 'dashed' } } },
    series: series.map((item, index) => ({ name: item.name, type: 'line', connectNulls: false,
      smooth: false, showSymbol: (report.months || []).length === 1, symbol: 'circle', symbolSize: 7,
      lineStyle: { width: index === 0 ? 3 : 1.8, opacity: index === 0 ? 1 : 0.8, type: item.previous ? 'dashed' : 'solid' },
      emphasis: { focus: 'series', scale: true },
      ...(index === 0 && unit !== 'ratio' ? { areaStyle: { opacity: 0.07 } } : {}),
      data: (item.values || []).map(v => v == null ? null : Number(v)) }))
  }
}
