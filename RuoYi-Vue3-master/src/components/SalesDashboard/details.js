import { formatMetric } from './chart.js'

export function formatDetail(value, unit) {
  if (value == null || value === '') return '--'
  return unit === 'text' ? String(value) : formatMetric(value, unit)
}

// Sort all filtered rows before paging; missing values always come last.
export function sortDetails(rows, sort, columns) {
  if (!sort?.prop || !sort?.order) return rows
  const numeric = columns.some(c => c.key === sort.prop && c.unit !== 'text')
  const direction = sort.order === 'descending' ? -1 : 1
  return [...rows].sort((a, b) => {
    const left = a[sort.prop], right = b[sort.prop]
    const leftEmpty = left == null || left === '', rightEmpty = right == null || right === ''
    if (leftEmpty || rightEmpty) return leftEmpty === rightEmpty ? 0 : leftEmpty ? 1 : -1
    return direction * (numeric ? Number(left) - Number(right) : String(left).localeCompare(String(right), 'zh-CN'))
  })
}

export function detailSummary(columns, details) {
  return columns.map((column, index) => {
    if (index === 0) return '合计'
    const definition = details?.columns?.find(item => item.key === column.property)
    if (!definition) return ''
    return formatDetail(details.summary?.[column.property], definition.unit)
  })
}
