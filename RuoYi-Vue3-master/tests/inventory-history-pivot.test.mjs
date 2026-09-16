import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'
import vm from 'node:vm'
import { computed, reactive, ref } from 'vue'
import { parse, compileScript, compileStyle, compileTemplate } from '@vue/compiler-sfc'

const file = new URL('../src/views/operations/ebay/inventoryDetail/InventoryHistoryPivot.vue', import.meta.url)
const source = fs.readFileSync(file, 'utf8')
const parsed = parse(source, { filename: file.pathname })
assert.deepEqual(parsed.errors, [])
const compiledScript = compileScript(parsed.descriptor, { id: 'inventory-history-pivot-test' })
const setupSource = parsed.descriptor.scriptSetup.content
const statements = compiledScript.scriptSetupAst
const stateNames = [
  'rows', 'total', 'loading', 'exporting', 'dataReady', 'metadata', 'tableRef', 'options',
  'query', 'appliedFilters', 'filtersDirty', 'pageQuery', 'sort', 'defaultSort', 'validDates',
  'snapshotCount', 'detailCount', 'onlyOwnerTotals', 'visibleRows', 'pageOwnerTotalCount',
  'pageRange', 'loadVersion', 'unmounted', 'columns'
]
const functionNames = [
  'currentFilters', 'disabledStatDate', 'rowKey', 'isOwnerTotal', 'rowClassName', 'formatValue', 'missingMessage', 'loadRows',
  'handleQuery', 'resetQuery', 'handlePagination', 'handleSortChange', 'handleExport'
]
const plain = value => JSON.parse(JSON.stringify(value))
function declaration(name, functionOnly = false) {
  const node = statements.find(item => functionOnly
    ? item.type === 'FunctionDeclaration' && item.id?.name === name
    : item.type === 'VariableDeclaration'
      && item.declarations.some(entry => entry.id.type === 'Identifier' && entry.id.name === name))
  assert.ok(node, 'production declaration: ' + name)
  return setupSource.slice(node.start, node.end)
}
function response(items = [], overrides = {}) {
  const ownerTotalCount = items.filter(row => row.row_type === 'OWNER_TOTAL').length
  return { data: {
    items, pagination: { page: 1, page_size: 50, total: ownerTotalCount },
    options: { owners: ['李茫茫', '未分配'], sites: ['德国', '英国'], dates: ['2026-09-16', '2026-09-14'] },
    metadata: { snapshot_count: 2, owner_total_count: ownerTotalCount,
      detail_count: items.length - ownerTotalCount, pagination_unit: 'owner_date' }, ...overrides
  } }
}
function deferred() {
  let resolve
  const promise = new Promise(success => { resolve = success })
  return { promise, resolve }
}
function harness(request = async () => response()) {
  const sent = [], exported = [], downloads = [], errors = [], warnings = []
  let permission = true
  let exportResponse = new Blob([Uint8Array.from([0x50, 0x4b, 0x03, 0x04])],
    { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' })
  const context = vm.createContext({
    computed, reactive, ref, Blob, Date,
    listEbayInventoryPivot: async params => { sent.push(plain(params)); return request(params) },
    exportEbayInventoryPivot: async params => { exported.push(plain(params)); return exportResponse },
    checkPermi: () => permission,
    blobValidate: value => value.type !== 'application/json',
    download: { saveAs: (blob, name) => downloads.push({ blob, name }) },
    ElMessage: { warning: message => warnings.push(message), error: message => errors.push(message) }
  })
  for (const name of functionNames) vm.runInContext(declaration(name, true), context)
  for (const name of stateNames) vm.runInContext(declaration(name), context)
  vm.runInContext('globalThis.api = { ' + [...stateNames, ...functionNames].join(', ') + ' }', context)
  const api = context.api
  api.appliedFilters.value = api.currentFilters()
  api.tableRef.value = { sort() {} }
  return {
    api, sent, exported, downloads, errors, warnings, context,
    setPermission: value => { permission = value },
    setExportResponse: value => { exportResponse = value }
  }
}

test('history component compiles with an explicitly imported Pagination and independent state', () => {
  const compiled = compileTemplate({
    source: parsed.descriptor.template.content, filename: file.pathname,
    id: 'inventory-history-pivot-test', compilerOptions: { bindingMetadata: compiledScript.bindings }
  })
  assert.deepEqual(compiled.errors, [])
  assert.ok(compiledScript.bindings.Pagination)
  assert.equal(compiledScript.bindings.pagination, undefined)
  assert.match(source, /v-for="size in \[10, 20, 30, 50, 100, 200\]"/)
  assert.match(source, /:label="size \+ ' 组\/页'"/)
  assert.match(source, /layout="prev, pager, next, jumper"/)
  assert.match(source, /@pagination="handlePagination"/)
  assert.match(source, /operations:ebayInventoryDetail:export/)
})

test('switch keeps detail mounted and its original selection, filters and column config intact', () => {
  const index = fs.readFileSync(new URL('../src/views/operations/ebay/inventoryDetail/index.vue', import.meta.url), 'utf8')
  assert.match(index, /<section v-show="activeView === 'detail'" class="table-panel">/)
  assert.match(index, /<InventoryHistoryPivot v-if="activeView === 'pivot'"\s*\/>/)
  assert.match(index, /const activeView = ref\('detail'\)/)
  assert.match(index, /const selection = reactive\(new Map\(\)\)/)
  assert.match(index, /useColumnConfig\('operations:ebay:inventory-detail'/)
})

test('twelve visible columns follow requested order; month stays a date tooltip', () => {
  const { api } = harness()
  assert.deepEqual(plain(api.columns.map(column => column.key)), [
    'owner', 'site', 'stat_date', 'sku_count', 'overseas_sellable_quantity', 'overseas_total_quantity',
    'sales_qty_30d', 'in_stock_sales_ratio', 'total_stock_sales_ratio',
    'overseas_sellable_value', 'overseas_total_value', 'warehouse_rent_30d_cny'
  ])
  assert.match(source, /统计年月：/)
  assert.match(source, /同日重新生成覆盖当日/)
  assert.match(source, /负责人保留采集时归属/)
})

test('calendar permits only actual snapshot dates using local calendar rather than UTC conversion', async () => {
  const { api, sent } = harness()
  assert.equal(api.disabledStatDate(new Date(2026, 8, 16)), true)
  await api.loadRows()
  assert.equal(api.disabledStatDate(new Date(2026, 8, 16)), false)
  assert.equal(api.disabledStatDate(new Date(2026, 8, 14)), false)
  assert.equal(api.disabledStatDate(new Date(2026, 8, 15)), true)
  assert.equal(api.disabledStatDate(new Date('invalid')), true)
  assert.deepEqual(sent[0], { pageNum: 1, pageSize: 50, sortField: 'stat_date', sortOrder: 'descending' })
  assert.equal(api.snapshotCount.value, 2)
  assert.match(source, /:disabled="!options\.dates\.length"/)
  assert.match(source, /暂无历史快照/)
})

test('date, owner and site filters apply together and reset returns to unfiltered date-descending view', async () => {
  const { api, sent } = harness()
  await api.loadRows()
  api.query.dateRange = ['2026-09-14', '2026-09-16']
  api.query.owner = '李茫茫'
  api.query.site = '德国'
  api.pageQuery.pageNum = 5
  assert.equal(api.filtersDirty.value, true)
  await api.handleQuery()
  assert.deepEqual(sent.at(-1), {
    startDate: '2026-09-14', endDate: '2026-09-16', owner: '李茫茫', site: '德国',
    pageNum: 1, pageSize: 50, sortField: 'stat_date', sortOrder: 'descending'
  })
  assert.equal(api.filtersDirty.value, false)
  await api.resetQuery()
  assert.deepEqual(sent.at(-1), { pageNum: 1, pageSize: 50, sortField: 'stat_date', sortOrder: 'descending' })
})

test('unknown, incomplete or reverse date ranges are rejected without querying', async () => {
  const { api, sent, warnings } = harness()
  await api.loadRows()
  for (const dates of [
    ['2026-09-15', '2026-09-16'], ['2026-09-14'], ['2026-09-16', '2026-09-14']
  ]) {
    api.query.dateRange = dates
    await api.handleQuery()
  }
  assert.equal(sent.length, 1)
  assert.equal(warnings.length, 3)
})

test('pagination and sorting preserve applied filters, and refresh ignores unsubmitted edits', async () => {
  const { api, sent } = harness(async params => response(
    [
      { stat_date: '2026-09-16', owner: '李茫茫', site: '德国', row_type: 'DETAIL' },
      { stat_date: '2026-09-16', owner: '李茫茫', site: '负责人汇总', row_type: 'OWNER_TOTAL', site_count: 1 }
    ],
    { pagination: { page: params.pageNum, page_size: params.pageSize, total: 201 } }
  ))
  await api.loadRows()
  api.query.site = '德国'
  await api.handleQuery()
  await api.handlePagination({ page: 3, limit: 20 })
  assert.equal(sent.at(-1).pageNum, 3)
  assert.equal(sent.at(-1).pageSize, 20)
  assert.deepEqual(plain(api.pageRange.value), { start: 41, end: 41 })
  await api.handleSortChange({ prop: 'sku_count', order: 'descending' })
  assert.equal(sent.at(-1).pageNum, 1)
  assert.equal(sent.at(-1).sortField, 'sku_count')
  api.query.site = '英国'
  await api.loadRows()
  assert.equal(sent.at(-1).site, '德国')
  assert.equal(api.filtersDirty.value, true)
})

test('slow earlier requests and responses after unmount cannot replace newer historical results', async () => {
  const first = deferred(), second = deferred(), third = deferred()
  let calls = 0
  const { api, context } = harness(() => [first, second, third][calls++].promise)
  const load1 = api.loadRows(), load2 = api.loadRows()
  second.resolve(response([{ owner: 'new' }]))
  await load2
  first.resolve(response([{ owner: 'old' }]))
  await load1
  assert.equal(api.rows.value[0].owner, 'new')
  vm.runInContext('unmounted = true', context)
  const load3 = api.loadRows()
  third.resolve(response([{ owner: 'after-unmount' }]))
  await load3
  assert.equal(api.rows.value[0].owner, 'new')
})

test('zero remains visible, percentages scale once, and row keys distinguish historical dates', () => {
  const { api } = harness()
  assert.equal(api.formatValue(null, 'money'), '--')
  assert.equal(api.formatValue(0, 'quantity'), '0')
  assert.equal(api.formatValue('0.125', 'percent'), '12.50%')
  assert.equal(api.formatValue('1234.567', 'money'), '¥1,234.57')
  assert.notEqual(api.rowKey({ stat_date: '2026-09-14', owner: 'A', site: '德国' }),
    api.rowKey({ stat_date: '2026-09-16', owner: 'A', site: '德国' }))
  assert.notEqual(api.rowKey({ stat_date: '2026-09-16', owner: 'A', site: '负责人汇总', row_type: 'DETAIL' }),
    api.rowKey({ stat_date: '2026-09-16', owner: 'A', site: '负责人汇总', row_type: 'OWNER_TOTAL' }))
})

test('owner totals have a red bold row style including date, identity and missing-money cells', () => {
  const { api } = harness()
  assert.equal(api.rowClassName({ row: { row_type: 'DETAIL' } }), '')
  assert.equal(api.rowClassName({ row: { row_type: 'OWNER_TOTAL' } }), 'owner-total-row')
  assert.match(source, /:row-class-name="rowClassName"/)
  const style = compileStyle({ source: parsed.descriptor.styles[0].content,
    filename: file.pathname, id: 'data-v-inventory-history-pivot-test', scoped: true })
  assert.deepEqual(style.errors, [])
  assert.match(style.code, /\.owner-total-row > td\.el-table__cell\s*\{[^}]*color: #c62828; font-weight: 700/)
  assert.match(style.code, /\.owner-total-row \.missing-value\s*\{[^}]*color: #c62828; font-weight: 700/)
  assert.match(api.columns.find(column => column.key === 'sku_count').tip, /跨站点的相同SKU分别计数/)
  assert.match(api.columns.find(column => column.key === 'site').tip, /当前筛选的站点/)
  for (const column of api.columns.filter(item => item.format === 'percent')) {
    assert.match(column.tip, /先加总各站点库存和销量再相除/)
    assert.match(column.tip, /不对SKU行或站点库销比求和或平均/)
  }
})

test('summary-only toggle preserves backend ordering, complete groups, pagination and query state', async () => {
  const items = [
    { stat_date: '2026-09-14', owner: 'A', site: '德国', row_type: 'DETAIL' },
    { stat_date: '2026-09-14', owner: 'A', site: '英国', row_type: 'DETAIL' },
    { stat_date: '2026-09-14', owner: 'A', site: '负责人汇总', row_type: 'OWNER_TOTAL', site_count: 2 },
    { stat_date: '2026-09-07', owner: 'A', site: '德国', row_type: 'DETAIL' },
    { stat_date: '2026-09-07', owner: 'A', site: '负责人汇总', row_type: 'OWNER_TOTAL', site_count: 1 }
  ]
  const { api, sent } = harness(async () => response(items, {
    pagination: { page: 3, page_size: 10, total: 22 },
    metadata: { snapshot_count: 4, detail_count: 68, owner_total_count: 22, pagination_unit: 'owner_date' }
  }))
  await api.loadRows()
  assert.equal(api.total.value, 22)
  assert.equal(api.detailCount.value, 68)
  assert.equal(api.snapshotCount.value, 4)
  assert.equal(api.pageOwnerTotalCount.value, 2)
  assert.deepEqual(plain(api.pageRange.value), { start: 21, end: 22 })
  assert.deepEqual(plain(api.visibleRows.value), items)
  const queriesBeforeToggle = sent.length
  api.onlyOwnerTotals.value = true
  assert.deepEqual(plain(api.visibleRows.value), [items[2], items[4]])
  assert.equal(api.rows.value.length, 5)
  assert.deepEqual(plain(api.pageRange.value), { start: 21, end: 22 })
  assert.equal(api.filtersDirty.value, false)
  assert.equal(sent.length, queriesBeforeToggle)
  api.onlyOwnerTotals.value = false
  assert.deepEqual(plain(api.visibleRows.value), items)
  assert.match(source, /:data="visibleRows"/)
  assert.match(source, /仅隐藏当前页站点明细，不改变分页或排序/)
  assert.match(source, /导出始终包含全部筛选结果的站点明细和负责人汇总/)
})

test('empty pages show zero groups even when the summary-only display is selected', async () => {
  const { api } = harness()
  api.onlyOwnerTotals.value = true
  await api.loadRows()
  assert.deepEqual(plain(api.pageRange.value), { start: 0, end: 0 })
  assert.deepEqual(plain(api.visibleRows.value), [])
})

test('owner total money explains frozen site sums and does not misstate excluded old null amounts', () => {
  const { api } = harness()
  for (const [key, missingField] of [
    ['overseas_sellable_value', 'missing_price_count'],
    ['overseas_total_value', 'missing_price_count'],
    ['warehouse_rent_30d_cny', 'missing_rent_count']
  ]) {
    for (const amount of ['120.00', 0, null]) {
      const row = { row_type: 'OWNER_TOTAL', sku_count: 8, [key]: amount, [missingField]: 2 }
      const message = api.missingMessage(row, key)
      assert.match(message, /当前筛选站点的已冻结金额汇总相加/)
      assert.match(message, /忽略空值，0为有效值/)
      assert.match(message, /未记录的历史金额不追溯重算/)
      assert.match(message, /原快照记录有 2 个SKU/)
      assert.doesNotMatch(message, /已排除/)
      if (amount === null) assert.match(message, /该项站点金额均无有效记录，合计显示--/)
      else assert.doesNotMatch(message, /显示--/)
    }
  }
})

test('amount columns explain available-only aggregation and frozen historical nulls', () => {
  const { api } = harness()
  for (const column of api.columns.filter(item => item.format === 'money')) {
    assert.match(column.tip, /仅汇总有值金额/)
    assert.match(column.tip, /0为有效值/)
    assert.match(column.tip, /该项金额全部缺失才显示--/)
    assert.match(column.tip, /已冻结历史中未记录的金额汇总不追溯重算/)
    assert.doesNotMatch(column.tip, /任一SKU.*整组显示--/)
  }
})

for (const [key, missingField, reason] of [
  ['overseas_sellable_value', 'missing_price_count', /缺少有效采购价/],
  ['overseas_total_value', 'missing_price_count', /缺少有效采购价/],
  ['warehouse_rent_30d_cny', 'missing_rent_count', /仓租无法完整计算/]
]) {
  test(key + ' displays partial sums and reports the excluded SKU count', () => {
    const { api } = harness()
    const row = { sku_count: 5, [missingField]: 2, [key]: '1234.56' }
    assert.equal(api.formatValue(row[key], 'money'), '¥1,234.56')
    const message = api.missingMessage(row, key)
    assert.match(message, /已排除 2 个SKU/)
    assert.match(message, reason)
    assert.match(message, /仅汇总有值金额/)
    assert.doesNotMatch(message, /显示--|全部缺失|未记录金额汇总/)
    assert.equal(api.missingMessage({ ...row, [missingField]: 0 }, key), '')
  })

  test(key + ' displays -- only when this amount has no available values', () => {
    const { api } = harness()
    const row = { sku_count: 3, [missingField]: 3, [key]: null }
    assert.equal(api.formatValue(row[key], 'money'), '--')
    const message = api.missingMessage(row, key)
    assert.match(message, /3 个SKU/)
    assert.match(message, reason)
    assert.match(message, /该项金额全部缺失，合计显示--/)
    assert.doesNotMatch(message, /已排除|仅汇总有值金额|未记录金额汇总/)
  })

  test(key + ' treats numeric and string zero as valid available sums', () => {
    const { api } = harness()
    for (const amount of [0, '0', '0.00']) {
      const row = { sku_count: 4, [missingField]: 2, [key]: amount }
      assert.equal(api.formatValue(row[key], 'money'), '¥0.00')
      const message = api.missingMessage(row, key)
      assert.match(message, /已排除 2 个SKU/)
      assert.match(message, /仅汇总有值金额/)
      assert.doesNotMatch(message, /显示--|全部缺失|未记录金额汇总/)
    }
  })

  test(key + ' preserves old null totals without claiming a partial sum was recorded', () => {
    const { api } = harness()
    for (const missingCount of [0, 2]) {
      const row = { sku_count: 5, [missingField]: missingCount, [key]: null }
      assert.equal(api.formatValue(row[key], 'money'), '--')
      const message = api.missingMessage(row, key)
      assert.match(message, /历史该项未记录金额汇总，显示--/)
      assert.match(message, /已冻结历史不追溯重算/)
      assert.doesNotMatch(message, /已排除|仅汇总有值金额|全部缺失/)
      if (missingCount > 0) {
        assert.match(message, /2 个SKU/)
        assert.match(message, reason)
      }
    }
  })
}

test('export sends only applied historical filters and ordering, not current page or unsaved edits', async () => {
  const { api, exported, downloads } = harness(async () => response([
    { owner: 'A', site: '德国', row_type: 'DETAIL' },
    { owner: 'A', site: '负责人汇总', row_type: 'OWNER_TOTAL' }
  ]))
  await api.loadRows()
  api.query.site = '德国'
  await api.handleQuery()
  api.pageQuery.pageNum = 3
  api.onlyOwnerTotals.value = true
  await api.handleExport()
  assert.deepEqual(exported[0], { site: '德国', sortField: 'stat_date', sortOrder: 'descending' })
  assert.equal(downloads.length, 1)
  assert.match(downloads[0].name, /^Ebay库存历史透视-/)
  api.query.site = '英国'
  await api.handleExport()
  assert.equal(exported.length, 1)
})

test('export enforces permission and rejects JSON error or invalid workbook responses', async () => {
  const state = harness(async () => response([{ owner: 'A', row_type: 'OWNER_TOTAL' }]))
  await state.api.loadRows()
  state.setPermission(false)
  await state.api.handleExport()
  assert.equal(state.exported.length, 0)
  state.setPermission(true)
  state.setExportResponse(new Blob([JSON.stringify({ detail: '历史快照不可用' })], { type: 'application/json' }))
  await state.api.handleExport()
  assert.equal(state.errors[0], '历史快照不可用')
  state.setExportResponse(new Blob(['invalid'], { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' }))
  await state.api.handleExport()
  assert.match(state.errors[1], /有效的 Excel/)
  assert.equal(state.downloads.length, 0)
  assert.equal(state.api.exporting.value, false)
})

test('history API uses authenticated ERP endpoints and binary GET export', () => {
  const apiSource = fs.readFileSync(new URL('../src/api/operations/ebay/inventoryDetail.js', import.meta.url), 'utf8')
  assert.match(apiSource, /const base = '\/finance\/ebay-inventory-detail'/)
  assert.match(apiSource, /export function listEbayInventoryPivot\(params\)/)
  assert.match(apiSource, /export function exportEbayInventoryPivot\(params\)/)
  assert.match(apiSource, /\/pivot\/export.*method: 'get', params/)
  assert.match(apiSource, /responseType: 'blob'/)
})
