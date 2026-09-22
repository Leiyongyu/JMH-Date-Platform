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

test('empty, not-ready and dirty results block export without blocking imports', () => {
  for (const [field, value] of [['total', 0], ['dataReady', false], ['filtersDirty', true]]) {
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
