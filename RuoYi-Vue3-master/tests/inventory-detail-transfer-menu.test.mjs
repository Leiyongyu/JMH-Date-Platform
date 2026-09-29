import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'
import vm from 'node:vm'
import { computed, ref } from 'vue'
import { parse, compileScript, compileTemplate } from '@vue/compiler-sfc'

const file = new URL('../src/views/operations/ebay/inventoryDetail/index.vue', import.meta.url)
const source = fs.readFileSync(file, 'utf8')
const { descriptor, errors } = parse(source)
assert.deepEqual(errors, [])
const script = compileScript(descriptor, { id: 'transfer-menu-test' })

function harness(permissions = ['import', 'export']) {
  const exports = [], imports = []
  const context = vm.createContext({
    computed, ref,
    checkPermi: values => permissions.some(permission => values.includes(`operations:ebayInventoryDetail:${permission}`)),
    handleExport: () => exports.push(true), openImportDialog: mode => imports.push(mode),
    loading: ref(false), importing: ref(false), exporting: ref(false), recalculating: ref(false),
    dataReady: ref(true), filtersDirty: ref(false), total: ref(10)
  })
  const names = ['canImportData', 'canExportData', 'transferBusy', 'exportUnavailable', 'handleTransferCommand']
  for (const name of names) {
    const node = script.scriptSetupAst.find(n => n.id?.name === name || n.declarations?.some(d => d.id.name === name))
    assert.ok(node)
    vm.runInContext(descriptor.scriptSetup.content.slice(node.start, node.end), context)
  }
  vm.runInContext('globalThis.menu = { ' + names.join(',') + ' }', context)
  return { context, api: context.menu, exports, imports }
}

test('single split control compiles, with direct export and three menu actions', () => {
  const result = compileTemplate({ source: descriptor.template.content, filename: file.pathname,
    id: 'transfer-menu-test', compilerOptions: { bindingMetadata: script.bindings } })
  assert.deepEqual(result.errors, [])
  assert.equal((source.match(/class="transfer-actions"/g) || []).length, 1)
  assert.match(source, /class="transfer-primary"[\s\S]*?@click="handleExport"/)
  assert.match(source, /:disabled="exportUnavailable"/)
  assert.match(source, /<el-dropdown trigger="click" :disabled="transferBusy" @command="handleTransferCommand"/)
  for (const name of ['export', 'prices', 'history']) assert.match(source, new RegExp(`command="${name}"`))
  // 等级改为计算字段后，导入产品等级入口已移除。
  assert.doesNotMatch(source, /command="grades"/)
  assert.doesNotMatch(descriptor.template.content, /@click="openImportDialog\(/)
})

test('each command dispatches to the existing action, unknown commands do nothing', () => {
  const h = harness()
  for (const command of ['export', 'grades', 'prices', 'history', 'unknown']) h.api.handleTransferCommand(command)
  assert.deepEqual(h.exports, [true])
  // 'grades' 已下线，应与 'unknown' 一样被忽略，不能再触发导入。
  assert.deepEqual(h.imports, ['prices', 'history'])
})

test('not-ready results block export without blocking imports', () => {
  for (const [field, value] of [['dataReady', false]]) {
    const h = harness()
    h.context[field].value = value
    assert.equal(h.api.exportUnavailable.value, true)
    assert.equal(h.api.transferBusy.value, false)
    h.api.handleTransferCommand('export')
    h.api.handleTransferCommand('history')
    assert.equal(h.exports.length, 0)
    assert.deepEqual(h.imports, ['history'])
  }
})

test('empty filtered results and unapplied row filters do not block full export', () => {
  const h = harness()
  h.context.total.value = 0
  h.context.filtersDirty.value = true
  assert.equal(h.api.exportUnavailable.value, false)
  h.api.handleTransferCommand('export')
  assert.deepEqual(h.exports, [true])
})

test('export sends only inclusive date range and sorting, never filters, selection or pagination', async () => {
  const requests = [], downloads = []
  const context = vm.createContext({
    exportUnavailable: ref(false), exporting: ref(false),
    exportDateRange: ref(['2026-09-01', '2026-09-16']), exportDialogVisible: ref(true),
    appliedFilters: ref({ statDate: '2026-09-16', site: '英国', sku: '00123', brand: 'MCD', grade: 'A' }),
    sort: { sortField: 'sku', sortOrder: 'descending' },
    selection: new Map([['selected', { site: '英国', sku: 'SKU-B' }]]),
    pageQuery: { pageNum: 2, pageSize: 1 },
    exportEbayInventoryDetail: async payload => {
      requests.push(JSON.parse(JSON.stringify(payload)))
      return new Blob([new Uint8Array([0x50, 0x4b, 0x03, 0x04])])
    },
    Blob, Uint8Array, blobValidate: () => true,
    download: { saveAs: (...args) => downloads.push(args) },
    ElMessage: { error: message => assert.fail(message) }
  })
  const node = script.scriptSetupAst.find(n => n.id?.name === 'confirmExport')
  vm.runInContext(descriptor.scriptSetup.content.slice(node.start, node.end), context)
  await context.confirmExport()
  assert.deepEqual(requests, [{ startDate: '2026-09-01', endDate: '2026-09-16', sortField: 'sku', sortOrder: 'descending' }])
  assert.equal(downloads.length, 1)
  assert.equal(context.exporting.value, false)
  assert.equal(context.exportDialogVisible.value, false)
  assert.equal(downloads[0][1], '库存明细持续更新-ebay-2026-09-01_至_2026-09-16.xlsx')
})

test('export opens range picker defaulting to displayed day without sending a request', () => {
  const context = vm.createContext({ exportUnavailable: ref(false),
    appliedFilters: ref({ statDate: '2026-09-16' }), exportDateRange: ref([]), exportDialogVisible: ref(false) })
  const node = script.scriptSetupAst.find(n => n.id?.name === 'handleExport')
  vm.runInContext(descriptor.scriptSetup.content.slice(node.start, node.end), context)
  context.handleExport()
  assert.deepEqual(Array.from(context.exportDateRange.value), ['2026-09-16', '2026-09-16'])
  assert.equal(context.exportDialogVisible.value, true)
  assert.match(source, /v-model="exportDateRange" type="daterange"/)
})

test('incomplete or reversed range never starts export', async () => {
  for (const range of [[], ['2026-09-16'], ['2026-09-16', '2026-09-01']]) {
    const errors = []
    const context = vm.createContext({ exportUnavailable: ref(false), exporting: ref(false),
      exportDateRange: ref(range), ElMessage: { error: message => errors.push(message) },
      exportEbayInventoryDetail: () => assert.fail('must not send request') })
    const node = script.scriptSetupAst.find(n => n.id?.name === 'confirmExport')
    vm.runInContext(descriptor.scriptSetup.content.slice(node.start, node.end), context)
    await context.confirmExport()
    assert.equal(errors.length, 1)
    assert.equal(context.exporting.value, false)
  }
})

test('permissions stay independent for menu visibility and dispatch', () => {
  for (const permissions of [[], ['import'], ['export']]) {
    const h = harness(permissions)
    assert.equal(h.api.canImportData.value, permissions.includes('import'))
    assert.equal(h.api.canExportData.value, permissions.includes('export'))
    h.api.handleTransferCommand('export')
    for (const command of ['prices', 'history']) h.api.handleTransferCommand(command)
    assert.equal(h.exports.length, permissions.includes('export') ? 1 : 0)
    assert.equal(h.imports.length, permissions.includes('import') ? 2 : 0)
  }
})

test('loading, importing, exporting or recalculating disables every menu action', () => {
  for (const field of ['loading', 'importing', 'exporting', 'recalculating']) {
    const h = harness()
    h.context[field].value = true
    for (const command of ['export', 'prices', 'history']) h.api.handleTransferCommand(command)
    assert.equal(h.api.transferBusy.value, true)
    assert.equal(h.exports.length + h.imports.length, 0)
  }
})
