import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'
import vm from 'node:vm'
import { parse, compileScript, compileTemplate } from '@vue/compiler-sfc'

for (const region of ['eu', 'us']) {
  const filename = new URL(`../src/views/operations/amz/replenishment/${region}/index.vue`, import.meta.url)
  const source = fs.readFileSync(filename, 'utf8')
  test(`${region}: gross profit columns are last, still monetary and sortable`, () => {
    const block = source.match(/const columnDefs = (\[[\s\S]*?\n\])/)?.[1]
    const columns = vm.runInNewContext(`(${block})`)
    assert.deepEqual(Array.from(columns.slice(-2), col => col.key), ['grossProfit30d', 'grossProfit90d'])
    assert.equal(columns.filter(col => col.key.startsWith('grossProfit')).length, 2)
    for (const col of columns.slice(-2)) {
      assert.equal(col.format, 'money')
      assert.equal(col.sortable, true)
    }
    assert.match(source, /columns: exportColumns.value/)
  })
  test(`${region}: saved layouts move only visible gross profit columns, preserve other order`, async () => {
    const fn = source.match(/async function initColumnConfig\(\) \{[\s\S]*?\n\}/)?.[0]
    assert.ok(fn)
    for (const [saved, expected] of [
      [['storeName', 'grossProfit90d', 'remark', 'grossProfit30d', 'sellerSku'],
        ['storeName', 'remark', 'sellerSku', 'grossProfit30d', 'grossProfit90d']],
      [['storeName', 'grossProfit90d', 'remark'], ['storeName', 'remark', 'grossProfit90d']],
      [['storeName', 'remark'], ['storeName', 'remark']],
      [['storeName', 'grossProfit30d', 'grossProfit90d'], ['storeName', 'grossProfit30d', 'grossProfit90d']]
    ]) {
      const visibleKeys = { value: [] }
      const context = vm.createContext({ visibleKeys, loadColumnConfig: async () => { visibleKeys.value = saved } })
      vm.runInContext(fn, context)
      await context.initColumnConfig()
      assert.deepEqual(Array.from(visibleKeys.value), expected)
    }
  })
  test(`${region}: Vue script/template compile with restored-column wrapper`, () => {
    const { descriptor, errors } = parse(source, { filename: filename.pathname })
    assert.deepEqual(errors, [])
    const script = compileScript(descriptor, { id: `amz-${region}` })
    const template = compileTemplate({ source: descriptor.template.content, filename: filename.pathname,
      id: `amz-${region}`, compilerOptions: { bindingMetadata: script.bindings } })
    assert.deepEqual(template.errors, [])
  })
}
