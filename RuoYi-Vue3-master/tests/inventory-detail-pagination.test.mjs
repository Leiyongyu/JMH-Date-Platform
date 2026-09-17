import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'
import vm from 'node:vm'
import { computed, nextTick, reactive, ref } from 'vue'
import { parse, compileScript, compileTemplate } from '@vue/compiler-sfc'

const filename = new URL('../src/views/operations/ebay/inventoryDetail/index.vue', import.meta.url)
const source = fs.readFileSync(filename, 'utf8')
const parsed = parse(source, { filename: filename.pathname })
assert.deepEqual(parsed.errors, [])
const script = compileScript(parsed.descriptor, { id: 'inventory-pagination-test' })
const setupSource = parsed.descriptor.scriptSetup.content
const statements = script.scriptSetupAst

const stateNames = [
  'rows', 'total', 'sites', 'brands', 'grades', 'availableDates', 'loading', 'dataReady',
  'recalculating', 'canRecalculate', 'importing',
  'exporting', 'tableRef', 'query', 'appliedFilters', 'filtersDirty',
  'pageQuery', 'pageRange', 'sort', 'selection', 'selectedCount',
  'restoringSelection', 'loadVersion', 'unmounted'
]
const functionNames = [
  'rowKey', 'currentFilters', 'handleSelectionChange', 'clearSelection',
  'restorePageSelection', 'loadRows', 'handlePagination', 'handleQuery', 'disabledStatDate',
  'handleSortChange', 'handleExport', 'handleRefresh'
]

function actualDeclaration(name, functionOnly = false) {
  const node = statements.find(item => functionOnly
    ? item.type === 'FunctionDeclaration' && item.id?.name === name
    : item.type === 'VariableDeclaration'
      && item.declarations.some(entry => entry.id.type === 'Identifier' && entry.id.name === name))
  assert.ok(node, 'production declaration: ' + name)
  return setupSource.slice(node.start, node.end)
}
const plain = value => JSON.parse(JSON.stringify(value))
const settle = () => new Promise(resolve => setImmediate(resolve))

function response(items, { page = 1, size = 50, total = items.length } = {}) {
  return { code: 200, data: {
    items, pagination: { page, page_size: size, total },
    sites: ['德国', '英国'], brands: ['FRD'], grades: ['A'], metadata: { warnings: [] }
  } }
}

function deferred() {
  let resolve
  const promise = new Promise(success => { resolve = success })
  return { promise, resolve }
}

function createHarness(request = async () => response([]), options = {}) {
  const sent = [], exported = [], downloads = [], errors = [], recalculations = [], successes = [], warnings = []
  const renderedSelection = new Map()
  let api
  const context = vm.createContext({
    computed, nextTick, reactive, ref, Blob,
    listEbayInventoryDetail: async params => { sent.push(plain(params)); return request(params) },
    recalculateEbayInventorySnapshot: async (...args) => {
      recalculations.push(args)
      return options.recalculate ? options.recalculate() : { data: { stat_date: '2026-09-16' } }
    },
    exportEbayInventoryDetail: async params => {
      exported.push(plain(params))
      // Only the download envelope is tested, not workbook generation.
      return new Blob([Uint8Array.from([0x50, 0x4b, 0x03, 0x04])],
        { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' })
    },
    checkPermi: () => options.allowed !== false,
    blobValidate: value => value.type !== 'application/json',
    download: { saveAs: (blob, name) => downloads.push({ blob, name }) },
    ElMessage: { error: message => errors.push(message), success: message => successes.push(message), warning: message => warnings.push(message) }
  })
  // Use actual production state and function bodies, not reimplemented logic.
  for (const name of functionNames) vm.runInContext(actualDeclaration(name, true), context)
  for (const name of stateNames) vm.runInContext(actualDeclaration(name), context)
  vm.runInContext('globalThis.pageHarness = { ' + [...stateNames, ...functionNames].join(', ') + ' }', context)
  api = context.pageHarness
  api.markUnmounted = () => vm.runInContext('unmounted = true', context)
  api.tableRef.value = {
    clearSelection() {
      renderedSelection.clear()
      api.handleSelectionChange([])
    },
    toggleRowSelection(row, selected) {
      const key = api.rowKey(row)
      if (selected) renderedSelection.set(key, row)
      else renderedSelection.delete(key)
      api.handleSelectionChange([...renderedSelection.values()])
    }
  }
  api.appliedFilters.value = api.currentFilters()
  return { api, sent, exported, downloads, errors, renderedSelection, recalculations, successes, warnings }
}

test('Pagination compiles to the explicit imported component, never a reactive state object', () => {
  const componentImport = statements.find(node => node.type === 'ImportDeclaration'
    && node.source.value === '@/components/Pagination/index.vue')
  assert.ok(componentImport)
  assert.ok(componentImport.specifiers.some(node => node.type === 'ImportDefaultSpecifier'
    && node.local.name === 'Pagination'))
  assert.equal(script.bindings.pagination, undefined)
  assert.ok(script.bindings.pageQuery)
  const compiled = compileTemplate({
    source: parsed.descriptor.template.content, filename: filename.pathname,
    id: 'inventory-pagination-test', compilerOptions: { bindingMetadata: script.bindings }
  })
  assert.deepEqual(compiled.errors, [])
  assert.match(compiled.code, /_(?:createVNode|createBlock)\(\$setup\["Pagination"\]/)
  assert.doesNotMatch(compiled.code, /_(?:createVNode|createBlock)\(\$setup\["pagination"\]/)
  assert.match(source, /<Pagination\b/)
})

test('original Excel rows with identical or missing SKU keep independent selection keys', async () => {
  const data = [
    { site: '德国', sku: 'DAS-10053-0121', record_key: 'DE:2' },
    { site: '德国', sku: 'DAS-10053-0121', record_key: 'DE:3' },
    { site: '德国', sku: null, record_key: 'DE:4' },
    { site: '德国', sku: null, record_key: 'DE:5' }
  ]
  const view = createHarness(async () => response(data))
  await view.api.loadRows()
  assert.equal(new Set(data.map(view.api.rowKey)).size, 4)
  view.api.handleSelectionChange([data[1], data[2]])
  await view.api.handleExport()
  assert.deepEqual(view.exported[0].selectedKeys, [
    { site: '德国', sku: 'DAS-10053-0121', record_key: 'DE:3' },
    { site: '德国', sku: '', record_key: 'DE:4' }
  ])
})

test('latest date resolves once and date changes clear selection and pin export', async () => {
  const row = { site: '德国', sku: 'MCD-20017-0071' }
  const { api, sent, exported } = createHarness(async params => {
    const day = params.statDate === 'latest' ? '2026-09-16' : params.statDate
    const res = response([{ ...row, stat_date: day }])
    res.data.metadata = { stat_date: day, available_dates: ['2026-09-16', '2026-09-15'] }
    return res
  })
  await api.handleQuery()
  assert.equal(api.query.statDate, '2026-09-16')
  assert.equal(api.appliedFilters.value.statDate, '2026-09-16')
  assert.equal(api.disabledStatDate(new Date(2026, 8, 15)), false)
  assert.equal(api.disabledStatDate(new Date(2026, 8, 14)), true)
  api.handleSelectionChange([row])
  api.query.statDate = '2026-09-15'
  await api.handleQuery()
  assert.equal(api.selectedCount.value, 0)
  assert.equal(sent.at(-1).statDate, '2026-09-15')
  await api.handleExport()
  assert.equal(exported.at(-1).statDate, '2026-09-15')
  assert.match(source, /v-model="query.statDate"/)
})

test('explicit refresh writes once without filters and switches from old date to server today', async () => {
  const { api, sent, recalculations, successes } = createHarness(async params =>
    response([{ site: '德国', sku: 'MCD-20017-0071', stat_date: params.statDate }]))
  api.query.statDate = '2026-09-01'
  api.query.site = '德国'
  await api.handleQuery()
  assert.equal(recalculations.length, 0)
  api.handleSelectionChange(api.rows.value)
  api.pageQuery.pageNum = 3
  await api.handleRefresh()
  assert.deepEqual(recalculations, [[]]) // No selected date, SKU or page reaches the write endpoint.
  assert.equal(api.query.statDate, '2026-09-16')
  assert.equal(sent.at(-1).statDate, '2026-09-16')
  assert.equal(sent.at(-1).pageNum, 1)
  assert.equal(sent.at(-1).site, '德国')
  assert.equal(api.selectedCount.value, 0)
  assert.equal(api.recalculating.value, false)
  assert.equal(api.dataReady.value, true)
  assert.equal(successes.length, 1)
  assert.match(source, /@queryTable="handleRefresh"/)
})

test('refresh coalesces repeated clicks and never turns query or pagination into writes', async () => {
  const pending = deferred()
  const { api, sent, recalculations } = createHarness(undefined, { recalculate: () => pending.promise })
  const first = api.handleRefresh()
  await api.handleRefresh()
  await api.handleQuery()
  await api.handlePagination({ page: 2, limit: 50 })
  assert.equal(recalculations.length, 1)
  assert.equal(sent.length, 0)
  pending.resolve({ data: { stat_date: '2026-09-16' } })
  await first
  await api.handleQuery()
  await api.handlePagination({ page: 2, limit: 50 })
  assert.equal(recalculations.length, 1)
})

test('failed recalculation preserves selected historical date and never reports success', async () => {
  const { api, sent, successes } = createHarness(undefined, {
    recalculate: async () => { throw new Error('server rejected') }
  })
  api.query.statDate = '2026-09-01'
  await api.handleRefresh()
  assert.equal(api.query.statDate, '2026-09-01')
  assert.equal(api.recalculating.value, false)
  assert.equal(api.dataReady.value, false)
  assert.equal(sent.length, 0)
  assert.equal(successes.length, 0)
})

test('read-only permission and active import/export block recalculation', async () => {
  const denied = createHarness(undefined, { allowed: false })
  await denied.api.handleRefresh()
  assert.equal(denied.recalculations.length, 0)
  for (const key of ['importing', 'exporting', 'loading']) {
    const view = createHarness()
    view.api[key].value = true
    await view.api.handleRefresh()
    assert.equal(view.recalculations.length, 0)
  }
})

test('invalid post-write date is visible and never used to load another snapshot', async () => {
  const pending = deferred()
  const view = createHarness(undefined, { recalculate: () => pending.promise })
  const work = view.api.handleRefresh()
  pending.resolve({ data: {} })
  await work
  assert.equal(view.sent.length, 0)
  assert.equal(view.successes.length, 0)
  assert.equal(view.errors.length, 1)
})

test('active import and recalculation prevent concurrent export', async () => {
  for (const key of ['importing', 'recalculating']) {
    const view = createHarness()
    view.api.dataReady.value = true
    view.api[key].value = true
    await view.api.handleExport()
    assert.equal(view.exported.length, 0)
  }
})

test('unmounted view does not query or report success after recalculation returns', async () => {
  const pending = deferred()
  const view = createHarness(undefined, { recalculate: () => pending.promise })
  const work = view.api.handleRefresh()
  view.api.markUnmounted()
  pending.resolve({ data: { stat_date: '2026-09-16' } })
  await work
  assert.equal(view.sent.length, 0)
  assert.equal(view.successes.length, 0)
})

test('footer exposes total, range and page-size/navigation controls', () => {
  assert.match(source, /class="table-pagination"/)
  assert.match(source, /pageRange\.start/)
  assert.match(source, /pageRange\.end/)
  assert.match(source, /layout="total,\s*sizes,\s*prev,\s*pager,\s*next,\s*jumper"/)
  assert.match(source, /:page-sizes="\[10,\s*20,\s*30,\s*50,\s*100,\s*200\]"/)
  assert.match(source, /@pagination="handlePagination"/)
})

test('page and page-size changes send pageNum/pageSize with active filters and sort', async () => {
  const { api, sent, errors } = createHarness(async params => response(
    [{ site: '德国', sku: 'FRD-' + params.pageNum }],
    { page: params.pageNum, size: params.pageSize, total: 237 }
  ))
  assert.deepEqual(plain(api.pageQuery), { pageNum: 1, pageSize: 50 })
  api.query.site = '德国'
  api.appliedFilters.value = api.currentFilters()
  await api.handlePagination({ page: 2, limit: 50 })
  assert.deepEqual(sent[0], {
    statDate: 'latest', site: '德国', pageNum: 2, pageSize: 50,
    sortField: 'sales_qty_30d', sortOrder: 'descending'
  })
  await api.handlePagination({ page: 1, limit: 100 })
  assert.deepEqual(plain(api.pageQuery), { pageNum: 1, pageSize: 100 })
  assert.equal(sent[1].pageNum, 1)
  assert.equal(sent[1].pageSize, 100)
  assert.equal(api.total.value, 237)
  assert.equal(api.loading.value, false)
  assert.equal(api.dataReady.value, true)
  assert.deepEqual(errors, [])
})

test('response page/page_size/total controls the range, including an empty result', async () => {
  const { api } = createHarness(async () => response(
    [{ site: '英国', sku: 'LAST-ROW' }], { page: 2, size: 30, total: 31 }
  ))
  await api.handlePagination({ page: 5, limit: 100 })
  assert.deepEqual(plain(api.pageQuery), { pageNum: 2, pageSize: 30 })
  assert.equal(api.total.value, 31)
  assert.deepEqual(plain(api.pageRange.value), { start: 31, end: 31 })
  const empty = createHarness(async () => response([], { page: 1, size: 50, total: 0 }))
  assert.deepEqual(plain(empty.api.pageRange.value), { start: 0, end: 0 })
  await empty.api.loadRows()
  assert.equal(empty.api.total.value, 0)
  assert.deepEqual(plain(empty.api.pageRange.value), { start: 0, end: 0 })
})

test('cross-page selection survives return to page one and keeps same-SKU different sites distinct', async () => {
  const first = { site: '德国', sku: 'SAME-SKU' }
  const second = { site: '英国', sku: 'SAME-SKU' }
  const { api, renderedSelection } = createHarness(async params => response(
    [params.pageNum === 2 ? second : first],
    { page: params.pageNum, size: params.pageSize, total: 2 }
  ))
  await api.handlePagination({ page: 1, limit: 1 })
  api.handleSelectionChange([first])
  await api.handlePagination({ page: 2, limit: 1 })
  assert.equal(api.selectedCount.value, 1)
  api.handleSelectionChange([second])
  assert.equal(api.selectedCount.value, 2)
  await api.handlePagination({ page: 1, limit: 1 })
  assert.equal(api.selectedCount.value, 2)
  assert.deepEqual([...renderedSelection.keys()], [api.rowKey(first)])
  api.handleSelectionChange([])
  assert.equal(api.selectedCount.value, 1)
  assert.ok(api.selection.has(api.rowKey(second)))
})

test('sorting resets page but preserves selections; a filter query clears selections', async () => {
  const selected = { site: '德国', sku: 'FRD-0001' }
  const { api, sent } = createHarness(async params => response(
    [selected], { page: params.pageNum, size: params.pageSize, total: 180 }
  ))
  await api.handlePagination({ page: 3, limit: 50 })
  api.handleSelectionChange([selected])
  api.handleSortChange({ prop: 'cycle_total_quantity', order: 'ascending' })
  await settle()
  assert.equal(api.pageQuery.pageNum, 1)
  assert.equal(sent.at(-1).pageNum, 1)
  assert.equal(sent.at(-1).sortField, 'cycle_total_quantity')
  assert.equal(sent.at(-1).sortOrder, 'ascending')
  assert.equal(api.selectedCount.value, 1)
  api.query.brand = 'FRD'
  await api.handleQuery()
  assert.equal(api.selectedCount.value, 0)
  assert.equal(api.pageQuery.pageNum, 1)
  assert.equal(sent.at(-1).brand, 'FRD')
})

test('late response cannot overwrite newer page data, total, page size or loading state', async () => {
  const old = deferred(), current = deferred()
  const { api, sent } = createHarness(params => params.pageNum === 2 ? old.promise : current.promise)
  const oldRequest = api.handlePagination({ page: 2, limit: 50 })
  const currentRequest = api.handlePagination({ page: 3, limit: 100 })
  assert.equal(sent.length, 2)
  current.resolve(response([{ site: '英国', sku: 'CURRENT' }], { page: 3, size: 100, total: 250 }))
  await currentRequest
  old.resolve(response([{ site: '德国', sku: 'STALE' }], { page: 2, size: 50, total: 99 }))
  await oldRequest
  assert.deepEqual(plain(api.pageQuery), { pageNum: 3, pageSize: 100 })
  assert.equal(api.total.value, 250)
  assert.equal(api.rows.value[0].sku, 'CURRENT')
  assert.equal(api.loading.value, false)
  assert.equal(api.dataReady.value, true)
})

test('selected and unselected exports retain filter scope but never pagination parameters', async () => {
  const first = { site: '德国', sku: 'SKU-1' }, second = { site: '德国', sku: 'SKU-2' }
  const { api, exported, downloads, errors } = createHarness(async params => response(
    [params.pageNum === 1 ? first : second],
    { page: params.pageNum, size: params.pageSize, total: 2 }
  ))
  api.query.site = '德国'
  api.appliedFilters.value = api.currentFilters()
  await api.handlePagination({ page: 1, limit: 1 })
  api.handleSelectionChange([first])
  await api.handlePagination({ page: 2, limit: 1 })
  api.handleSelectionChange([second])
  await api.handleExport()
  assert.deepEqual(exported[0], {
    statDate: 'latest', site: '德国', sortField: 'sales_qty_30d', sortOrder: 'descending',
    selectedKeys: [first, second]
  })
  for (const key of ['pageNum', 'pageSize', 'page', 'page_size']) {
    assert.equal(Object.hasOwn(exported[0], key), false)
  }
  assert.equal(downloads.length, 1)
  assert.equal(api.exporting.value, false)
  api.clearSelection()
  await api.handleExport()
  assert.deepEqual(exported[1].selectedKeys, [])
  assert.equal(downloads.length, 2)
  assert.deepEqual(errors, [])
})
