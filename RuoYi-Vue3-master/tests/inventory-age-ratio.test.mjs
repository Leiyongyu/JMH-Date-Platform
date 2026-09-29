import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'
import vm from 'node:vm'
import { computed, ref } from 'vue'
import { parse, compileScript, compileTemplate } from '@vue/compiler-sfc'

const file = new URL('../src/views/operations/ebay/inventoryDetail/InventoryAgeRatio.vue', import.meta.url)
const source = fs.readFileSync(file, 'utf8')
const { descriptor, errors } = parse(source)
assert.deepEqual(errors, [])
const script = compileScript(descriptor, { id: 'age-ratio-test' })
const names = ['report', 'dimension', 'selectedDate', 'dateRange', 'availableDates', 'loading', 'refreshing', 'canRefresh',
  'rows', 'visibleWarnings', 'emptyText', 'buckets', 'version', 'disposed', 'formatMoney', 'formatPercent', 'loadReport', 'refreshReport']
function harness({ allowed = true, read, refresh } = {}) {
  const calls = [], events = [], messages = []
  const context = vm.createContext({
    ref, computed, checkPermi: () => allowed,
    emit: (...args) => events.push(args), ElMessage: { success: message => messages.push(message) },
    getEbayInventoryAgeRatio: async params => { calls.push(['read', params]); return read?.(params) || { data: { owners: [], sites: [], available_dates: [] } } },
    recalculateEbayInventoryAgeRatio: async (...args) => {
      calls.push(['refresh', args]); return refresh?.() || { data: { stat_date: '2026-09-29', owners: [{ name: '张三' }], sites: [{ name: '德国' }] } }
    }
  })
  for (const name of names) {
    const node = script.scriptSetupAst.find(n => n.id?.name === name || n.declarations?.some(d => d.id.name === name))
    assert.ok(node, name)
    vm.runInContext(descriptor.scriptSetup.content.slice(node.start, node.end), context)
  }
  vm.runInContext('globalThis.api = { ' + names.join(',') + ' }', context)
  return { api: context.api, calls, events, messages }
}

test('both eleven-column views compile without verbose help or exclusion details', () => {
  const result = compileTemplate({ source: descriptor.template.content, filename: file.pathname, id: 'age-ratio-test',
    compilerOptions: { bindingMetadata: script.bindings } })
  assert.deepEqual(result.errors, [])
  assert.doesNotMatch(source, /库存数量 ×（采购单价＋头程单价）|库龄分段：|捷克仓归德国站/)
  assert.doesNotMatch(descriptor.template.content, /excluded_details|excluded_rows|row.candidates|缺数/)
  assert.match(source, /core-supplier-max-landed-cost-v4/)
  assert.match(source, /核心码＋供应商编号/)
  assert.match(source, /report.generated_at && report.calculation_version/)
  const h = harness()
  assert.equal(h.api.buckets.length * 2 + 3, 11)
  assert.match(source, /dimension === 'owners' \? '负责人' : '站点'/)
})

test('exclusion warnings are hidden without changing report data or other warnings', () => {
  const h = harness()
  h.api.report.value = {
    warnings: ['2条明细缺成本，未计入货值及占比；当前金额为可计算部分。', '谷仓最新源数据不是当月拉取'],
    excluded_details: [{ sku: 'JMH-60013' }], excluded_rows: 1
  }
  assert.equal(h.api.visibleWarnings.value.length, 1)
  assert.equal(h.api.visibleWarnings.value[0], '谷仓最新源数据不是当月拉取')
  assert.equal(h.api.report.value.excluded_details.length, 1)
  assert.equal(h.api.report.value.warnings.length, 2)
})

test('zero money stays zero but null ratios show unavailable and fractions display as percentages', () => {
  const h = harness()
  assert.equal(h.api.formatMoney('0'), '0.00')
  assert.equal(h.api.formatPercent(null), '--')
  assert.equal(h.api.formatPercent('0.125'), '12.50%')
})

test('read never recalculates and pins returned snapshot date', async () => {
  const h = harness({ read: async () => ({ data: { stat_date: '2026-09-28', owners: [], sites: [], available_dates: ['2026-09-28'] } }) })
  await h.api.loadReport()
  assert.equal(h.calls.length, 1)
  assert.equal(h.calls[0][0], 'read')
  assert.equal(h.api.selectedDate.value, '2026-09-28')
})

test('date range reads daily history for both dimensions and clearing returns latest', async () => {
  const h = harness({ read: async params => ({ data: params.startDate ? {
    start_date: params.startDate, end_date: params.endDate, snapshot_dates: ['2026-09-29', '2026-09-28'],
    owners: [{ stat_date: '2026-09-29', name: '张三' }, { stat_date: '2026-09-28', name: '张三' }],
    sites: [{ stat_date: '2026-09-29', name: '德国' }, { stat_date: '2026-09-28', name: '德国' }]
  } : { stat_date: '2026-09-29', owners: [], sites: [] } }) })
  h.api.dateRange.value = ['2026-09-01', '2026-09-30']
  await h.api.loadReport()
  assert.equal(h.calls[0][1].startDate, '2026-09-01')
  assert.equal(h.calls[0][1].endDate, '2026-09-30')
  assert.equal(h.calls[0][1].statDate, undefined)
  assert.equal(h.api.rows.value.length, 2)
  h.api.dimension.value = 'sites'
  assert.equal(h.api.rows.value.length, 2)
  h.api.dateRange.value = null
  await h.api.loadReport()
  assert.equal(h.calls[1][1].statDate, 'latest')
  assert.equal(h.api.dateRange.value.join(','), '2026-09-29,2026-09-29')
  assert.ok(h.calls.every(([kind]) => kind === 'read'))
})

test('empty date range shows a history-specific empty state', async () => {
  const h = harness({ read: async () => ({ data: { start_date: '2020-01-01', end_date: '2020-02-01',
    snapshot_dates: [], owners: [], sites: [] } }) })
  h.api.dateRange.value = ['2020-01-01', '2020-02-01']
  await h.api.loadReport()
  assert.equal(h.api.emptyText.value, '所选日期范围内没有统计快照')
  assert.equal(h.api.dateRange.value[0], '2020-01-01')
})

test('refresh sends no client date or filters, switches to today and keeps history dates', async () => {
  const h = harness()
  h.api.selectedDate.value = '2026-09-01'
  h.api.availableDates.value = ['2026-09-01']
  await h.api.refreshReport()
  assert.equal(h.calls[0][1].length, 0)
  assert.equal(h.api.selectedDate.value, '2026-09-29')
  assert.equal(h.api.availableDates.value.join(','), '2026-09-29,2026-09-01')
  assert.equal(h.api.rows.value[0].name, '张三')
  h.api.dimension.value = 'sites'
  assert.equal(h.api.rows.value[0].name, '德国')
  assert.equal(h.messages.length, 1)
  assert.deepEqual(h.events, [['busy-change', true], ['busy-change', false]])
})

test('refresh permission and duplicate-click guard preserve read-only behavior', async () => {
  const denied = harness({ allowed: false })
  await denied.api.refreshReport()
  assert.equal(denied.calls.length, 0)
  let complete
  const h = harness({ refresh: () => new Promise(resolve => { complete = resolve }) })
  const running = h.api.refreshReport()
  await h.api.refreshReport()
  assert.equal(h.calls.length, 1)
  complete({ data: { stat_date: '2026-09-29', owners: [], sites: [] } })
  await running
  assert.equal(h.api.refreshing.value, false)
})

test('failed refresh preserves old data and never announces success', async () => {
  const h = harness({ refresh: async () => { throw new Error('missing costs') } })
  h.api.report.value = { stat_date: '2026-09-28', owners: [{ name: 'old' }] }
  h.api.selectedDate.value = '2026-09-28'
  await h.api.refreshReport()
  assert.equal(h.api.report.value.stat_date, '2026-09-28')
  assert.equal(h.api.selectedDate.value, '2026-09-28')
  assert.equal(h.messages.length, 0)
  assert.equal(h.api.refreshing.value, false)
})
