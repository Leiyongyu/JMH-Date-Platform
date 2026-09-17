import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'
import vm from 'node:vm'

const source = fs.readFileSync(new URL('../src/composables/useColumnConfig.js', import.meta.url), 'utf8')
  .replace(/^import .*$/gm, '').replace('export function useColumnConfig', 'function useColumnConfig')
const pageSource = fs.readFileSync(new URL('../src/views/operations/ebay/inventoryDetail/index.vue', import.meta.url), 'utf8')
const placementSource = pageSource.match(/\{ sku_middle_code: 'sku', sku_middle_site_code: \{ before: 'sku_middle_code', after: 'sku' \} \}/)?.[0]
assert.ok(placementSource, 'production placement keeps a before anchor with an after fallback')
const allKeys = ['site', 'sku', 'sku_middle_site_code', 'sku_middle_code', 'brand']

function configHarness(saved, useLocal = false) {
  let persisted = saved == null ? null : JSON.stringify(saved)
  const context = vm.createContext({
    computed: fn => ({ get value() { return fn() } }), ref: value => ({ value }),
    getUserColumnConfig: async () => ({ data: useLocal ? null : persisted }),
    saveUserColumnConfig: async (page, payload) => { persisted = payload },
    localStorage: { setItem(key, value) { persisted = value }, getItem() { return persisted } }
  })
  vm.runInContext(source, context)
  const create = () => context.useColumnConfig('inventory-detail', allKeys.map(key => ({ key })),
    ['site', 'sku'], ['site', 'sku'], {}, vm.runInContext('(' + placementSource + ')', context))
  return { create, persisted: () => JSON.parse(persisted) }
}

test('middle-plus-site defaults before middle code without resetting saved order or hidden columns', async () => {
  const previousKeys = ['site', 'sku', 'sku_middle_code', 'brand']
  for (const [saved, expected] of [
    [null, allKeys],
    [{ visibleKeys: ['site', 'sku', 'brand'], allKeys: ['site', 'sku', 'brand'] }, allKeys],
    [['site', 'sku', 'brand'], allKeys],
    [{ visibleKeys: previousKeys, allKeys: previousKeys }, allKeys],
    [{ visibleKeys: ['site', 'sku', 'brand', 'sku_middle_code'], allKeys: previousKeys },
      ['site', 'sku', 'brand', 'sku_middle_site_code', 'sku_middle_code']],
    [['site', 'sku', 'brand', 'sku_middle_code'], ['site', 'sku', 'brand', 'sku_middle_site_code', 'sku_middle_code']],
    [{ visibleKeys: ['site', 'sku', 'brand'], allKeys: previousKeys }, ['site', 'sku', 'sku_middle_site_code', 'brand']],
    [{ visibleKeys: ['site', 'sku'], allKeys: previousKeys }, ['site', 'sku', 'sku_middle_site_code']],
    [{ visibleKeys: ['site', 'sku', 'brand', 'sku_middle_code'], allKeys }, ['site', 'sku', 'brand', 'sku_middle_code']],
    [{ visibleKeys: ['site', 'sku', 'brand', 'sku_middle_code', 'sku_middle_site_code'], allKeys },
      ['site', 'sku', 'brand', 'sku_middle_code', 'sku_middle_site_code']],
    [['site', 'sku', 'brand', 'sku_middle_code', 'sku_middle_site_code'],
      ['site', 'sku', 'brand', 'sku_middle_code', 'sku_middle_site_code']]
  ]) {
    for (const local of [false, true]) {
      const config = configHarness(saved, local).create()
      await config.initColumnConfig()
      assert.deepEqual(Array.from(config.visibleKeys.value), expected)
    }
  }
})

test('saving a new custom position or hiding the derived column survives future loads', async () => {
  const harness = configHarness(['site', 'sku', 'brand'])
  const initial = harness.create()
  await initial.initColumnConfig()
  assert.deepEqual(Array.from(initial.visibleKeys.value), allKeys)
  for (const custom of [
    ['site', 'sku', 'brand', 'sku_middle_code', 'sku_middle_site_code'],
    ['site', 'sku', 'brand', 'sku_middle_code'],
    ['site', 'sku', 'brand']
  ]) {
    await initial.applyColumnConfig(custom)
    assert.deepEqual(harness.persisted().allKeys, allKeys)
    const reopened = harness.create()
    await reopened.initColumnConfig()
    assert.deepEqual(Array.from(reopened.visibleKeys.value), custom)
  }
})

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
