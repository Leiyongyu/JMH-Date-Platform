export const trendColors = { up: '#d93025', down: '#16834a' }

export function trendDirection(value) {
  if (value == null || value === '' || !Number.isFinite(Number(value))) return ''
  return Number(value) > 0 ? 'up' : Number(value) < 0 ? 'down' : ''
}

export function comparisonDirection(comparison) {
  return comparison?.reason ? '' : trendDirection(comparison?.value)
}
