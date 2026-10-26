import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'
import vm from 'node:vm'
import { parse, compileScript, compileTemplate } from '@vue/compiler-sfc'

const page = readFileSync(new URL('../src/views/operations/ebay/priceTracking/index.vue', import.meta.url), 'utf8')
const handleImport = page.match(/function handleImport\(command\) \{[^]*?\n\}/)[0]

test('tracking imports preserve files and dispatch all original and migrated formats to their endpoint', async () => {
  for (const [command, suffix, label] of [
    ['lowestPrice', 'import-lowest-price', '最低价'], ['productPrice', 'import-product-price', '商品单价'],
    ['sales', 'import-sales', '销量'], ['profitRate', 'import-profit-rate', '利润率'], ['returnRate', 'import-return-rate', '退货率']
  ]) {
    let input, sent, shown, refreshed = 0
    const file = { name: 'history.xlsx' }
    class FormData { fields = []; append(...field) { this.fields.push(field) } }
    const importing = { value: false }
    const context = vm.createContext({
      importing, FormData, IMPORT_TIMEOUT: 600000,
      document: { createElement: () => (input = { click() {} }) },
      request: async request => { sent = request; return { data: { status: 'SUCCESS' } } },
      showImportResult: (...args) => { shown = args }, getList: async () => { refreshed++ },
      proxy: { $modal: { msgError: message => assert.fail(message) } }
    })
    vm.runInContext(handleImport, context)
    context.handleImport(command)
    await input.onchange({ target: { files: [file] } })
    assert.equal(sent.url, `/operations/ebay/price-tracking/${suffix}`)
    assert.equal(sent.data.fields[0][0], 'file')
    assert.equal(sent.data.fields[0][1], file)
    assert.equal(shown[0], label)
    assert.equal(refreshed, 1)
    assert.equal(importing.value, false)
  }
})

test('tracking page with migrated import controls compiles', () => {
  const { descriptor, errors } = parse(page)
  assert.deepEqual(errors, [])
  const script = compileScript(descriptor, { id: 'tracking' })
  assert.deepEqual(compileTemplate({ source: descriptor.template.content, filename: 'index.vue', id: 'tracking',
    compilerOptions: { bindingMetadata: script.bindings } }).errors, [])
})
