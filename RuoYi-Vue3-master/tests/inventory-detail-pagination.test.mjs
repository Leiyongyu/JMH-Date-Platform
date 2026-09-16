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
  'rows', 'total', 'sites', 'brands', 'grades', 'metadata', 'loading', 'dataReady',
  'exporting', 'tableRef', 'query', 'appliedFilters', 'filtersDirty',
  'pageQuery', 'pageRange', 'sort', 'selection', 'selectedCount',
  'restoringSelection', 'loadVersion', 'unmounted'
]
const functionNames = [
  'rowKey', 'currentFilters', 'handleSelectionChange', 'clearSelection',
  'restorePageSelection', 'loadRows', 'handlePagination', 'handleQuery',
  'handleSortChange', 'handleExport'
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

function createHarness(request = async () => response([])) {
  const sent = [], exported = [], downloads = [], errors = []
  const renderedSelection = new Map()
  let api
  const context = vm.createContext({
    computed, nextTick, reactive, ref, Blob,
    listEbayInventoryDetail: async params => { sent.push(plain(params)); return request(params) },
    exportEbayInventoryDetail: async params => {
      exported.push(plain(params))
      // Only the download envelope is tested, not workbook generation.
      return new Blob([Uint8Array.from([0x50, 0x4b, 0x03, 0x04])],
        { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' })
    },
    checkPermi: () => true,
    blobValidate: value => value.type !== 'application/json',
    download: { saveAs: (blob, name) => downloads.push({ blob, name }) },
    ElMessage: { error: message => errors.push(message), success() {}, warning() {} }
  })
  // Use actual production state and function bodies, not reimplemented logic.
  for (const name of functionNames) vm.runInContext(actualDeclaration(name, true), context)
  for (const name of stateNames) vm.runInContext(actualDeclaration(name), context)
  vm.runInContext('globalThis.pageHarness = { ' + [...stateNames, ...functionNames].join(', ') + ' }', context)
  api = context.pageHarness
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
  return { api, sent, exported, downloads, errors, renderedSelection }
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
    site: '德国', pageNum: 2, pageSize: 50,
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
    site: '德国', sortField: 'sales_qty_30d', sortOrder: 'descending',
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
