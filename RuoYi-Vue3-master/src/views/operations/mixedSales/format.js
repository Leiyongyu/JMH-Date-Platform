export function quantity(value) {
  if (value === null || value === undefined || value === '') return '--'
  const number = Number(value)
  return Number.isFinite(number) ? number.toLocaleString('zh-CN', { maximumFractionDigits: 0 }) : '--'
}

export function matchHint(matched, total) {
  const expected = Number(total || 0)
  const actual = Number(matched || 0)
  return expected > actual ? `已匹配 ${actual}/${expected} 个MSKU` : ''
}
export function price(value) {
  if (value === null || value === undefined || value === '') return '--'
  const number = Number(value)
  return Number.isFinite(number) ? number.toLocaleString('zh-CN', { maximumFractionDigits: 10 }) : '--'
}
