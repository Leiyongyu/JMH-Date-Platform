export const trendColors = { up: '#e05252', down: '#12b2a6' }

export function trendDirection(value) {
  if (value == null || value === '' || !Number.isFinite(Number(value))) return ''
  return Number(value) > 0 ? 'up' : Number(value) < 0 ? 'down' : ''
}

export function comparisonDirection(comparison) {
  return comparison?.reason ? '' : trendDirection(comparison?.value)
}
