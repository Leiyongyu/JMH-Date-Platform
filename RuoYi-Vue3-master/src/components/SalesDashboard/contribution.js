import { formatMetric } from './chart.js'

export function rankedItems(report, key, dimension, mode, kind) {
  const rows = mode === 'delta' ? report?.contributions?.[key]?.[kind]?.[dimension]?.items || []
    : (report?.breakdown?.[dimension] || []).filter(r => r.metrics[key]?.value != null).map(r => ({ name: r.name, current: r.metrics[key].value }))
  return [...rows].sort((a, b) => mode === 'delta'
    ? Math.abs(Number(b.difference)) - Math.abs(Number(a.difference)) : Number(b.current) - Number(a.current))
}

export function platformBars(report, key) {
  const metric = report?.metrics?.[key]
  return {
    color: ['#4a9fe8', '#9a85df'], legend: { bottom: 0 },
    tooltip: { trigger: 'axis', confine: true, renderMode: 'richText', valueFormatter: v => formatMetric(v) },
    grid: { left: 18, right: 24, top: 35, bottom: 48, containLabel: true },
    xAxis: { type: 'category', data: report?.months || [], axisTick: { show: false } },
    yAxis: { type: 'value', name: '人民币（元）', splitLine: { lineStyle: { type: 'dashed', color: '#e8edf5' } }, axisLabel: { formatter: v => Math.abs(v) >= 10000 ? `${Number((v / 10000).toFixed(1))}万` : v } },
    series: (metric?.platform_series || []).map(s => ({ name: s.name, type: 'bar', stack: 'platforms', stackStrategy: 'samesign', barMaxWidth: 40, data: s.values.map(v => v == null ? null : Number(v)) }))
  }
}

export function contributionBars(items, mode) {
  return {
    grid: { left: 10, right: 35, top: 20, bottom: items.length > 10 ? 45 : 25, containLabel: true },
    tooltip: { trigger: 'axis', confine: true, renderMode: 'richText', formatter: values => {
      const entry = (Array.isArray(values) ? values : [values])[0]
      const item = items[entry?.dataIndex]
      return item ? `${item.name}\n本期金额：${formatMetric(item.current)}${mode === 'delta' ? `\n对比期金额：${formatMetric(item.baseline)}\n增减金额：${formatMetric(item.difference)}` : ''}` : ''
    } },
    xAxis: { type: 'value', splitLine: { lineStyle: { type: 'dashed', color: '#e8edf5' } }, axisLabel: { formatter: v => Math.abs(v) >= 10000 ? `${Number((v / 10000).toFixed(1))}万` : v } },
    yAxis: { type: 'category', inverse: true, data: items.map(r => r.name), axisLabel: { width: 125, overflow: 'truncate' }, axisTick: { show: false } },
    ...(items.length > 10 ? { dataZoom: [{ type: 'slider', yAxisIndex: 0, right: 0, startValue: 0, endValue: 9, filterMode: 'empty' }] } : {}),
    series: [{ type: 'bar', barMaxWidth: 26, data: items.map(r => {
      const value = Number(mode === 'delta' ? r.difference : r.current)
      return { value, itemStyle: { color: value < 0 ? '#bd8ba0' : '#6f98ca' } }
    }) }]
  }
}
