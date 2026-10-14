import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'
import vm from 'node:vm'
import { parse, compileScript, compileTemplate } from '@vue/compiler-sfc'

const view = readFileSync(new URL('../src/views/finance/slowMovingClearance/index.vue', import.meta.url), 'utf8')

function setup(fetch, fetchOwners = fetch, extras = {}) {
  const source = view.split('const { proxy } = getCurrentInstance()', 2)[1].split('onMounted(', 1)[0]
  const context = vm.createContext({
    reactive: value => value, ref: value => ({ value }),
    getSlowMovingClearanceDimensions: fetch, getSlowMovingClearanceOwners: fetchOwners,
    ...extras
  })
  vm.runInContext(`${source}\nthis.state = { drilldown, summary, query, loading, rows, openDrilldown, closeDrilldown, drilldownSummary, handleMonthChange, loadData, handleExport, costExporting }`, context)
  return context.state
}

test('page template and script compile with site/store drilldown entry', () => {
  const { descriptor, errors } = parse(view)
  assert.deepEqual(errors, [])
  const script = compileScript(descriptor, { id: 'clearance-test' })
  const template = compileTemplate({ source: descriptor.template.content, filename: 'index.vue', id: 'clearance-test', compilerOptions: { bindingMetadata: script.bindings } })
  assert.deepEqual(template.errors, [])
  assert.match(view, /按站点查看/)
  assert.match(view, /按店铺查看/)
})

test('drilldown uses shared month selector and ignores stale response', async () => {
  const requests = []
  const state = setup((month, group) => new Promise(resolve => requests.push({ month, group, resolve })))
  state.query.pullMonth = '2026-09'
  const first = state.openDrilldown({ pull_month: '2026-09', group_code: 'EBAY-1', group_name: 'eBay' })
  assert.equal(requests[0].month, '2026-09')
  assert.equal(state.drilldown.isEbay, true)
  state.query.pullMonth = '2026-10'
  const second = state.openDrilldown({ pull_month: '2026-10', group_code: 'EU', group_name: 'EU' })
  requests[1].resolve({ data: { items: [{ dimension_key: 'SID:1' }] } })
  await second
  requests[0].resolve({ data: { items: [{ dimension_key: 'US' }] } })
  await first
  assert.equal(state.drilldown.rows[0].dimension_key, 'SID:1')
  assert.equal(state.drilldown.month, '2026-10')
  assert.equal(state.drilldown.isEbay, false)
  assert.equal(state.drilldown.loading, false)
})

test('closing invalidates pending response and failed requests show error', async () => {
  let resolve
  const state = setup(() => new Promise(done => { resolve = done }))
  state.query.pullMonth = '2026-10'
  const pending = state.openDrilldown({ pull_month: '2026-10', group_code: 'EU', group_name: 'EU' })
  state.closeDrilldown()
  resolve({ data: { items: [{ dimension_key: 'stale' }] } })
  await pending
  assert.equal(state.drilldown.rows.length, 0)
  const failed = setup(async () => { throw new Error('offline') })
  failed.query.pullMonth = '2026-10'
  await failed.openDrilldown({ pull_month: '2026-10', group_code: 'EU', group_name: 'EU' })
  assert.match(failed.drilldown.error, /加载失败/)
  assert.equal(failed.drilldown.loading, false)
})

test('summary distinguishes missing previous data from actual zero', () => {
  const state = setup(() => {})
  const totals = state.drilldownSummary({
    columns: [{ property: 'dimension_name' }, { property: 'total_inventory_qty' }, { property: 'total_inventory_cost' }, { property: 'previous_month_91_180_cost' }],
    data: [{ total_inventory_qty: 2, total_inventory_cost: '10.5', previous_month_91_180_cost: null },
      { total_inventory_qty: 3, total_inventory_cost: '0', previous_month_91_180_cost: null }]
  })
  assert.equal(totals[0], '合计')
  assert.equal(totals[1], '5')
  assert.equal(totals[2], '¥10.50')
  assert.equal(totals[3], '--')
})

test('personal entry opens shared dialog for selected month and all sites without brand columns', async () => {
  const calls = []
  const state = setup(() => { throw new Error('must use owners API') }, async (...args) => {
    calls.push(args)
    return { data: { items: [{ dimension_name: '按品牌负责人' }] } }
  })
  state.query.pullMonth = '2026-09'
  await state.openDrilldown({ group_code: 'EBAY-1', group_name: 'eBay', pull_month: '2026-08' }, 'OWNER')
  assert.deepEqual(calls, [['2026-09']])
  assert.equal(state.drilldown.visible, true)
  assert.equal(state.drilldown.dimension, 'OWNER')
  assert.equal(state.drilldown.rows[0].dimension_name, '按品牌负责人')
  assert.match(state.drilldown.title, /全部站点/)
  assert.match(view, /按个人查看/)
  assert.doesNotMatch(view, /本月库存涉及品牌|上月库存涉及品牌|previous_brands|router.push|openOwnerPage/)
  const routes = readFileSync(new URL('../src/router/index.js', import.meta.url), 'utf8')
  assert.doesNotMatch(routes, /ClearanceMonthlyOwners|clearance-owners/)
})

test('month changes close dialog and do not allow earlier group responses to overwrite selected month', async () => {
  const pending = []
  const state = setup(() => {}, undefined, {
    listSlowMovingClearance: query => new Promise(resolve => pending.push({ month: query.pullMonth, resolve })),
    getSlowMovingClearanceSummary: async month => ({ data: { pull_month: month } })
  })
  state.query.pullMonth = '2026-09'
  const first = state.loadData()
  state.drilldown.visible = true
  state.query.pullMonth = '2026-10'
  state.handleMonthChange()
  assert.equal(state.drilldown.visible, false)
  assert.equal(state.loading.value, true)
  await state.openDrilldown({ group_code: 'EBAY-1' }, 'OWNER')
  assert.equal(state.drilldown.visible, false)
  pending[1].resolve({ rows: [{ group_name: '当前月' }] })
  await new Promise(resolve => setImmediate(resolve))
  pending[0].resolve({ rows: [{ group_name: '旧月份' }] })
  await first
  assert.equal(state.rows.value[0].group_name, '当前月')
  assert.equal(state.query.pullMonth, '2026-10')
})

test('both export commands use shared selected month, and JSON failures are not saved as XLSX', async () => {
  const calls = [], downloads = [], errors = []
  const state = setup(() => {}, undefined, {
    Blob, proxy: { $modal: { msgSuccess() {}, msgError: value => errors.push(value) } },
    URL: { createObjectURL: () => 'blob:test', revokeObjectURL() {} },
    document: { body: { appendChild() {} }, createElement: () => ({
      click() { downloads.push(this.download) }, remove() {}
    }) },
    exportClearanceMonthlySummary: async month => {
      calls.push(['summary', month])
      return new Blob(['xlsx'], { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' })
    },
    exportInventoryAgeDetails: async month => {
      calls.push(['detail', month])
      return new Blob(['{"msg":"没有权限"}'], { type: 'application/json' })
    }
  })
  state.query.pullMonth = '2026-09'
  await state.handleExport('summary')
  await state.handleExport('detail')
  assert.deepEqual(calls, [['summary', '2026-09'], ['detail', '2026-09']])
  assert.equal(downloads.length, 1)
  assert.match(downloads[0], /2026-09-滞销清货当月汇总/)
  assert.deepEqual(errors, ['没有权限'])
  assert.equal(state.costExporting.value, false)
})
