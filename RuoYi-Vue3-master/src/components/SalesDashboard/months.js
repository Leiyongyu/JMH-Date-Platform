// Available months come from persisted history for the selected platform.
export function availableMonths(options, platform) {
  const months = platform === 'all' ? ['ebay', 'amz'].flatMap(p => options?.[p]?.months || []) : options?.[platform]?.months || []
  return [...new Set(months)].sort()
}

export function availableQuarters(months) {
  return [...new Set(months.map(m => `${m.slice(0, 4)}-Q${Math.ceil(Number(m.slice(-2)) / 3)}`))].sort()
}

export function quarterRange(range, months) {
  const choices = availableQuarters(months)
  const picked = availableQuarters(range || [])
  if (!choices.length) return []
  return picked.length && picked.every(q => choices.includes(q)) ? [picked[0], picked.at(-1)] : [choices[0], choices.at(-1)]
}

export function quarterMonths(range) {
  if (!Array.isArray(range) || range.length !== 2 || range[0] > range[1] || !range.every(q => /^20\d{2}-Q[1-4]$/.test(q))) return []
  return [0, 1].map(i => `${range[i].slice(0, 4)}-${String(Number(range[i].slice(-1)) * 3 - (i === 0 ? 2 : 0)).padStart(2, '0')}`)
}

export function platformGroups(options, platform) {
  return (platform === 'all' ? ['ebay', 'amz'] : [platform]).flatMap(p =>
    (options?.[p]?.groups || []).map(g => ({ value: `${p}:${g}`, label: `${p === 'ebay' ? 'eBay' : 'AMZ'} / ${g}` })))
}

export function validMonthRange(range, months) {
  return Array.isArray(range) && range.length === 2 && range[0] <= range[1] &&
    range.every(month => months.includes(month))
}

export function fitMonthRange(range, months) {
  if (!months.length) return []
  if (validMonthRange(range, months)) return [...range]
  const covered = range?.length === 2 ? months.filter(m => m >= range[0] && m <= range[1]) : []
  const candidates = covered.length ? covered : months.slice(-12)
  return [candidates[0], candidates.at(-1)]
}

export function disabledMonth(date, months) {
  if (!(date instanceof Date) || Number.isNaN(date.getTime())) return true
  const key = `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}`
  return !months.includes(key)
}
