import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'
import {
  addDays, addMonths, buildDateCells, buildMonthCells, cellClasses, defaultPresets, pickValue,
  resolveRange, shiftMonth, spanLength
} from '../src/components/DateRangePicker/rangeUtils.js'

test('month and day arithmetic crosses year boundaries', () => {
  assert.deepEqual(shiftMonth(2026, 11, 1), { y: 2027, m: 0 })
  assert.deepEqual(shiftMonth(2026, 0, -1), { y: 2025, m: 11 })
  assert.equal(addMonths('2026-01', -2), '2025-11')
  assert.equal(addDays('2026-03-01', -1), '2026-02-28')
  assert.equal(spanLength('2025-11', '2026-02', 'month'), 4)
  assert.equal(spanLength('2026-10-30', '2026-11-02', 'date'), 4)
})

test('calendar grids', () => {
  const nov = buildDateCells(2026, 10) // 2026-11-01 is a Sunday
  assert.equal(nov.length, 42)
  assert.equal(nov[0].value, '2026-11-01')
  assert.equal(nov[0].other, false)
  assert.equal(nov[30].value, '2026-12-01')
  assert.equal(nov[30].other, true)
  const months = buildMonthCells(2026)
  assert.deepEqual([months[0].value, months[11].value, months[6].label], ['2026-01', '2026-12', '7月'])
})

test('two clicks make a range in either order', () => {
  let state = pickValue({ start: null, end: null }, '2026-09')
  assert.deepEqual(state, { start: '2026-09', end: null })
  assert.deepEqual(pickValue(state, '2026-07'), { start: '2026-07', end: '2026-09' })
  assert.deepEqual(pickValue({ start: '2026-07', end: '2026-09' }, '2026-03'), { start: '2026-03', end: null })
})

test('hover previews the range with a hollow end and solid picked start', () => {
  const range = resolveRange('2026-07', null, '2026-09')
  assert.deepEqual(cellClasses('2026-07', range), ['in-range', 'range-start', 'is-start'])
  assert.deepEqual(cellClasses('2026-08', range), ['in-range'])
  assert.deepEqual(cellClasses('2026-09', range), ['in-range', 'range-end', 'is-preview'])
  assert.deepEqual(cellClasses('2026-10', range), [])
  const single = resolveRange('2026-07', '2026-07', null)
  assert.deepEqual(cellClasses('2026-07', single), ['in-range', 'range-start', 'range-end', 'is-start', 'is-end'])
})

test('default presets end on the right day or month', () => {
  const today = new Date(2026, 10, 5)
  const month = Object.fromEntries(defaultPresets('month', today).map(p => [p.key, p.range]))
  assert.deepEqual(month.lastMonth, ['2026-10', '2026-10'])
  assert.deepEqual(month.last3, ['2026-08', '2026-10'])
  assert.deepEqual(month.lastYear, ['2025-01', '2025-12'])
  const date = Object.fromEntries(defaultPresets('date', today).map(p => [p.key, p.range]))
  assert.deepEqual(date.last7, ['2026-10-30', '2026-11-05'])
  assert.deepEqual(date.lastMonth, ['2026-10-01', '2026-10-31'])
})

test('component exposes v-model range, both modes and confirm/clear', () => {
  const source = fs.readFileSync(new URL('../src/components/DateRangePicker/index.vue', import.meta.url), 'utf8')
  assert.ok(source.includes("validator: value => ['date', 'month'].includes(value)"))
  assert.ok(source.includes("emit('update:modelValue', value)"))
  assert.ok(source.includes('[draft.start, draft.end || draft.start]'))
  assert.ok(source.includes('>清空</button>') && source.includes('>确定</button>'))
})
