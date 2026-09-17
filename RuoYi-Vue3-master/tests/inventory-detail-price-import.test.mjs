import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'
import vm from 'node:vm'
import { computed, ref } from 'vue'
import { parse, compileScript, compileTemplate } from '@vue/compiler-sfc'

const filename = new URL('../src/views/operations/ebay/inventoryDetail/index.vue', import.meta.url)
const source = fs.readFileSync(filename, 'utf8')
const parsed = parse(source, { filename: filename.pathname })
assert.deepEqual(parsed.errors, [])
const script = compileScript(parsed.descriptor, { id: 'inventory-price-import-test' })
const setupSource = parsed.descriptor.scriptSetup.content
const stateNames = ['importDialogVisible', 'importing', 'importMode', 'importFile', 'uploadRef',
  'importResultVisible', 'importResultMode', 'importResult', 'importWarnings', 'importModes',
  'activeImportConfig', 'importResultSummary', 'loading', 'exporting', 'recalculating', 'unmounted']
const functionNames = ['openImportDialog', 'handleImportFileChange', 'handleImportFileRemove',
  'handleFileExceed', 'handleImport']

function declaration(name, isFunction = false) {
  const node = script.scriptSetupAst.find(item => isFunction
    ? item.type === 'FunctionDeclaration' && item.id?.name === name
    : item.type === 'VariableDeclaration' && item.declarations.some(entry => entry.id.name === name))
  assert.ok(node, 'production declaration: ' + name)
  return setupSource.slice(node.start, node.end)
}

function harness(options = {}) {
  const calls = [], successes = [], warnings = [], queries = [], cleared = []
  const context = vm.createContext({
    computed, ref, checkPermi: () => options.allowed !== false,
    query: {},
    importEbayInventoryHistory: async file => { calls.push(['history', file]); return options.response || { data: {} } },
    importEbayInventoryGrades: async file => { calls.push(['grades', file]); return options.response || { data: {} } },
    importEbayInventoryPrices: async file => {
      calls.push(['prices', file])
      if (options.request) return options.request()
      return options.response || { data: {} }
    },
    handleQuery: async () => { queries.push('read-existing-snapshot') },
    ElMessage: { success: message => successes.push(message), warning: message => warnings.push(message) }
  })
  for (const name of stateNames) vm.runInContext(declaration(name), context)
  for (const name of functionNames) vm.runInContext(declaration(name, true), context)
  vm.runInContext('globalThis.api = { ' + [...stateNames, ...functionNames].join(', ') + ' }', context)
  const api = context.api
  api.uploadRef.value = { clearFiles: () => cleared.push(true) }
  return { api, calls, successes, warnings, queries, cleared,
    unmount: () => vm.runInContext('unmounted = true', context) }
}

const file = { name: '产品单价明细表.xlsx', size: 200 }

test('history import accepts original 27MB file and reads uploaded date without recalculation', async () => {
  const view = harness({ response: { data: { imported_rows: 75590, imported_dates: 46,
    duplicate_rows_preserved: 48, missing_sku_rows: 8, latest_import_date: '2026-09-07' } } })
  view.api.openImportDialog('history')
  view.api.handleImportFileChange({ raw: { name: 'history.xlsx', size: 28246589 } })
  assert.ok(view.api.importFile.value)
  await view.api.handleImport()
  assert.equal(view.calls[0][0], 'history')
  assert.equal(view.queries.length, 1)
  assert.match(view.api.importResultSummary.value, /75590 行、46 个日期/)
  assert.match(view.successes[0], /无需重算/)
  view.api.openImportDialog('prices')
  view.api.handleImportFileChange({ raw: { name: 'history.xlsx', size: 28246589 } })
  assert.equal(view.api.importFile.value, null)
  view.api.openImportDialog('history')
  view.api.handleImportFileChange({ raw: { name: 'history.xlsx', size: 50 * 1024 * 1024 + 1 } })
  assert.equal(view.api.importFile.value, null)
})

test('price and grade imports compile and expose safe update rules with explicit refresh', () => {
  const result = compileTemplate({ source: parsed.descriptor.template.content,
    filename: filename.pathname, id: 'inventory-price-import-test',
    compilerOptions: { bindingMetadata: script.bindings } })
  assert.deepEqual(result.errors, [])
  assert.match(source, /command="prices".*导入产品单价/)
  assert.match(source, /command="grades".*导入产品等级/)
  assert.match(source, /产品代码/)
  assert.match(source, /单价\(默认采购价\)/)
  assert.match(source, /第二段纯数字/)
  assert.match(source, /未涉及 SKU 保留/)
  assert.match(source, /非数字中间段仍保存并提示/)
  assert.match(source, /允许零价/)
  assert.match(source, /历史日期保持不变/)
  assert.match(source, /importWarnings\.length \? 'warning'/)
  assert.doesNotMatch(declaration('handleImport', true), /recalculateEbayInventorySnapshot|handleRefresh/)
})

test('opening another import mode clears the selected file and preserves result mode', () => {
  const view = harness()
  view.api.openImportDialog('prices')
  assert.equal(view.api.importMode.value, 'prices')
  assert.equal(view.api.activeImportConfig.value.label, '产品单价')
  view.api.handleImportFileChange({ raw: file })
  assert.equal(view.api.importFile.value.name, file.name)
  view.api.importResultMode.value = 'prices'
  view.api.openImportDialog('grades')
  assert.equal(view.api.importFile.value, null)
  assert.equal(view.api.importResultMode.value, 'prices')
  assert.equal(view.api.activeImportConfig.value.label, '产品等级')
})

test('price import dispatches once and displays dedup counts and unmatched-middle warnings', async () => {
  const view = harness({ response: { data: { imported_rows: 4, duplicate_rows: 2, sku_count: 3,
    middle_code_count: 1, unmatched_middle_rows: 1, skipped_rows: 0, warnings: ['非数字中间段已保存'] } } })
  view.api.openImportDialog('prices')
  view.api.handleImportFileChange({ raw: file })
  await view.api.handleImport()
  assert.equal(view.calls.length, 1)
  assert.equal(view.calls[0][0], 'prices')
  assert.equal(view.api.importResultMode.value, 'prices')
  assert.equal(view.api.importResultVisible.value, true)
  assert.equal(view.api.importDialogVisible.value, false)
  assert.equal(view.api.importFile.value, null)
  assert.equal(view.api.importing.value, false)
  assert.match(view.api.importResultSummary.value, /4 条 SKU＋单价.*2 条.*3 个 SKU.*1 个中间码.*1 条无数字中间码/)
  assert.equal(view.api.importWarnings.value[0], '非数字中间段已保存')
  assert.equal(view.queries.length, 1)
  assert.match(view.successes[0], /产品单价已导入.*刷新/)
})

test('grade import retains its own route, warning summary and valid-row behavior', async () => {
  const view = harness({ response: { data: { imported_rows: 2, duplicate_rows: 1, skipped_rows: 3 } } })
  view.api.openImportDialog('grades')
  view.api.handleImportFileChange({ raw: file })
  await view.api.handleImport()
  assert.equal(view.calls[0][0], 'grades')
  assert.match(view.api.importResultSummary.value, /更新 2 条.*重复 1 条.*无效 3 条/)
  assert.match(view.successes[0], /产品等级已导入/)
})

test('invalid files only warn and never report an import success', () => {
  for (const raw of [null, { name: 'prices.csv', size: 20 }, { name: 'prices.xlsx', size: 10 * 1024 * 1024 + 1 }]) {
    const view = harness()
    view.api.handleImportFileChange({ raw })
    assert.equal(view.api.importFile.value, null)
    assert.equal(view.warnings.length, 1)
    assert.equal(view.successes.length, 0)
    assert.equal(view.calls.length, 0)
  }
})

test('import guards reject missing permission and concurrent import export load or recalculation', async () => {
  for (const busy of ['loading', 'exporting', 'recalculating', 'importing', 'denied']) {
    const view = harness({ allowed: busy !== 'denied' })
    if (busy !== 'denied') view.api[busy].value = true
    view.api.openImportDialog('prices')
    assert.equal(view.api.importDialogVisible.value, false)
    view.api.importMode.value = 'prices'
    view.api.importFile.value = file
    await view.api.handleImport()
    assert.equal(view.calls.length, 0)
  }
})

test('pending import coalesces submissions and failed import keeps file without success or snapshot query', async () => {
  let reject
  const pending = new Promise((resolve, fail) => { reject = fail })
  const view = harness({ request: () => pending })
  view.api.openImportDialog('prices')
  view.api.handleImportFileChange({ raw: file })
  const work = view.api.handleImport()
  await view.api.handleImport()
  assert.equal(view.calls.length, 1)
  reject(new Error('invalid price'))
  await work
  assert.equal(view.api.importing.value, false)
  assert.equal(view.api.importDialogVisible.value, true)
  assert.equal(view.api.importFile.value.name, file.name)
  assert.equal(view.api.importResultVisible.value, false)
  assert.equal(view.successes.length, 0)
  assert.equal(view.queries.length, 0)
})

test('unmounted view does not display a late successful import or read another snapshot', async () => {
  let resolve
  const pending = new Promise(success => { resolve = success })
  const view = harness({ request: () => pending })
  view.api.openImportDialog('prices')
  view.api.handleImportFileChange({ raw: file })
  const work = view.api.handleImport()
  view.unmount()
  resolve({ data: {} })
  await work
  assert.equal(view.api.importResultVisible.value, false)
  assert.equal(view.successes.length, 0)
  assert.equal(view.queries.length, 0)
})

test('API sends both import types as multipart without client date or operator', async () => {
  const apiSource = fs.readFileSync(new URL('../src/api/operations/ebay/inventoryDetail.js', import.meta.url), 'utf8')
    .replace(/^import .*\n/gm, '').replace(/^export /gm, '')
  const sent = []
  const context = vm.createContext({ FormData, request: payload => { sent.push(payload); return Promise.resolve({}) } })
  vm.runInContext(apiSource + '\nglobalThis.api = { importEbayInventoryPrices, importEbayInventoryGrades }', context)
  const workbook = new Blob(['test-data'])
  await context.api.importEbayInventoryPrices(workbook)
  await context.api.importEbayInventoryGrades(workbook)
  assert.deepEqual(sent.map(item => item.url), ['/finance/ebay-inventory-detail/prices/import', '/finance/ebay-inventory-detail/grades/import'])
  for (const item of sent) {
    assert.equal(item.method, 'post')
    assert.deepEqual([...item.data.keys()], ['file'])
    assert.equal(await item.data.get('file').text(), 'test-data')
    assert.equal(item.headers.repeatSubmit, false)
    assert.equal(item.headers['Content-Type'], 'multipart/form-data')
    assert.equal(item.timeout, 120000)
  }
})
