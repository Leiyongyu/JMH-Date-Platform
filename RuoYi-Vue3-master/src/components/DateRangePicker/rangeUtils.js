// Pure helpers for <DateRangePicker>; no Vue or DOM so they can be unit tested.
// Values are ISO strings: 'YYYY-MM-DD' in date mode, 'YYYY-MM' in month mode,
// so plain string comparison orders them correctly.

export const WEEK_LABELS = ['日', '一', '二', '三', '四', '五', '六']

export function pad(n) {
  return n < 10 ? `0${n}` : `${n}`
}

export function formatDate(d) {
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
}

export function formatMonth(y, m) {
  return `${y}-${pad(m + 1)}`
}

export function parseValue(value) {
  const [y, m, d] = String(value).split('-').map(Number)
  return { y, m: m - 1, d: d || 1 }
}

// Month index shift that handles year boundaries: shiftMonth(2026, 11, 1) -> { y: 2027, m: 0 }.
export function shiftMonth(y, m, delta) {
  const index = y * 12 + m + delta
  return { y: Math.floor(index / 12), m: ((index % 12) + 12) % 12 }
}

export function addDays(value, n) {
  const { y, m, d } = parseValue(value)
  return formatDate(new Date(y, m, d + n))
}

export function addMonths(value, n) {
  const { y, m } = parseValue(value)
  const t = shiftMonth(y, m, n)
  return formatMonth(t.y, t.m)
}

// Inclusive length: days in date mode, months in month mode.
export function spanLength(start, end, mode) {
  if (!start || !end) return 0
  if (mode === 'month') {
    const a = parseValue(start)
    const b = parseValue(end)
    return (b.y - a.y) * 12 + (b.m - a.m) + 1
  }
  const a = parseValue(start)
  const b = parseValue(end)
  return Math.round((new Date(b.y, b.m, b.d) - new Date(a.y, a.m, a.d)) / 86400000) + 1
}

// 6 x 7 cells starting on Sunday, with leading / trailing days of the neighbour months.
export function buildDateCells(y, m) {
  const firstWeekday = new Date(y, m, 1).getDay()
  const cells = []
  for (let i = firstWeekday; i > 0; i--) cells.push({ value: formatDate(new Date(y, m, 1 - i)), other: true })
  const days = new Date(y, m + 1, 0).getDate()
  for (let i = 1; i <= days; i++) cells.push({ value: formatDate(new Date(y, m, i)), other: false })
  let next = 1
  while (cells.length < 42) cells.push({ value: formatDate(new Date(y, m + 1, next++)), other: true })
  return cells.map(cell => ({ ...cell, label: Number(cell.value.slice(8)) }))
}

export function buildMonthCells(y) {
  return Array.from({ length: 12 }, (_, m) => ({ value: formatMonth(y, m), other: false, label: `${m + 1}月` }))
}

// The range to highlight; while only the start is picked, the hovered cell previews the end.
export function resolveRange(start, end, hover) {
  if (start && !end && hover) {
    const ends = hover < start ? { a: hover, b: start } : { a: start, b: hover }
    return { ...ends, preview: hover }
  }
  return { a: start, b: end, preview: null }
}

// The hovered (not yet clicked) end gets a hollow ring instead of a solid dot.
export function cellClasses(value, range) {
  const classes = []
  const { a, b, preview } = range
  if (a && b && value >= a && value <= b) classes.push('in-range')
  if (a && value === a) classes.push('range-start')
  if (b && value === b) classes.push('range-end')
  if (preview && value === preview && a !== b) classes.push('is-preview')
  else {
    if (a && value === a) classes.push('is-start')
    if (b && value === b) classes.push('is-end')
  }
  return classes
}

// Second click completes the range; clicking before the start swaps the ends.
export function pickValue(state, value) {
  if (!state.start || state.end) return { start: value, end: null }
  return value < state.start ? { start: value, end: state.start } : { start: state.start, end: value }
}

export function defaultPresets(mode, today = new Date()) {
  const t = formatDate(today)
  const thisMonth = formatMonth(today.getFullYear(), today.getMonth())
  const year = today.getFullYear()
  if (mode === 'month') {
    const last = addMonths(thisMonth, -1)
    return [
      { key: 'thisMonth', label: '本月', range: [thisMonth, thisMonth] },
      { key: 'lastMonth', label: '上月', range: [last, last] },
      { key: 'last3', label: '近 3 个月', range: [addMonths(last, -2), last] },
      { key: 'last6', label: '近 6 个月', range: [addMonths(last, -5), last] },
      { key: 'thisYear', label: '今年', range: [`${year}-01`, thisMonth] },
      { key: 'lastYear', label: '去年', range: [`${year - 1}-01`, `${year - 1}-12`] }
    ]
  }
  const monthStart = `${thisMonth}-01`
  const lastMonthStart = `${addMonths(thisMonth, -1)}-01`
  return [
    { key: 'today', label: '今天', range: [t, t] },
    { key: 'yesterday', label: '昨天', range: [addDays(t, -1), addDays(t, -1)] },
    { key: 'last7', label: '近 7 天', range: [addDays(t, -6), t] },
    { key: 'last30', label: '近 30 天', range: [addDays(t, -29), t] },
    { key: 'thisMonth', label: '本月', range: [monthStart, t] },
    { key: 'lastMonth', label: '上月', range: [lastMonthStart, addDays(monthStart, -1)] },
    { key: 'thisYear', label: '今年', range: [`${year}-01-01`, t] }
  ]
}
