import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'
import vm from 'node:vm'

const source = fs.readFileSync(new URL('../src/composables/useColumnConfig.js', import.meta.url), 'utf8')
  .replace(/^import .*$/gm, '').replace('export function useColumnConfig', 'function useColumnConfig')

test('new middle column is inserted after SKU without losing saved order or hidden state', async () => {
  for (const [saved, expected] of [
    [{ visibleKeys: ['site', 'sku', 'brand'], allKeys: ['site', 'sku', 'brand'] }, ['site', 'sku', 'sku_middle_code', 'brand']],
    [['site', 'sku', 'brand'], ['site', 'sku', 'sku_middle_code', 'brand']],
    [{ visibleKeys: ['site', 'sku'], allKeys: ['site', 'sku', 'sku_middle_code', 'brand'] }, ['site', 'sku']],
    [{ visibleKeys: ['site', 'sku', 'brand', 'sku_middle_code'], allKeys: ['site', 'sku', 'sku_middle_code', 'brand'] }, ['site', 'sku', 'brand', 'sku_middle_code']]
  ]) {
    const context = vm.createContext({
      computed: fn => ({ get value() { return fn() } }), ref: value => ({ value }),
      getUserColumnConfig: async () => ({ data: JSON.stringify(saved) }),
      saveUserColumnConfig: async () => {}, localStorage: { setItem() {}, getItem() { return null } }
    })
    vm.runInContext(source, context)
    const config = context.useColumnConfig('inventory-detail',
      ['site', 'sku', 'sku_middle_code', 'brand'].map(key => ({ key })),
      ['site', 'sku'], ['site', 'sku'], {}, { sku_middle_code: 'sku' })
    await config.initColumnConfig()
    assert.deepEqual(Array.from(config.visibleKeys.value), expected)
  }
})
