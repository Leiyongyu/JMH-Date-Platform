import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import vm from 'node:vm'
import { childQuery, withMoreRow, isSkuRow } from '../src/views/operations/ebay/replenishmentV2/hierarchy.js'

const pageSource = readFileSync(new URL('../src/views/operations/ebay/replenishmentV2/index.vue', import.meta.url), 'utf8')
const functionSource = name => pageSource.match(new RegExp(`(?:async )?function ${name}\\([^]*?\\n\\}`))[0]

function loaderContext(api) {
  const context = vm.createContext({
    rowsRequest: 1, calculationVersion: {value: 'v1'}, appliedFilters: {value: {sku: '70327'}},
    loadingNodes: new Set(), failedNodes: new Set(), childrenByNode: new Map(),
    childQuery, withMoreRow, listEbayReplenishmentHierarchy: api, normalizeRow: value => value,
    initializeLeadTimeSavedValues: (_rows, reset) => assert.equal(reset, false)
  })
  vm.runInContext(functionSource('fetchChildren'), context)
  return context
}

test('expand pins the version, preserves filters and selects exact site/product parent', () => {
  const params = childQuery({nodeKind: 'product', site: '英国', brandCore: 'FRD-70327'},
    {site: undefined, sku: '70327', productLevel: 'A', operationsConfirmed: true, principalName: '任雅婷', sortOrder: 'asc'}, 'version', 2)
  assert.equal(params.site, '英国')
  assert.equal(params.hierarchyLevel, 'sku')
  assert.equal(params.brandCore, 'FRD-70327')
  assert.equal(params.calculationVersion, 'version')
  assert.equal(params.operationsConfirmed, true)
  assert.equal(params.pageNum, 2)
  assert.equal(params.principalName, '任雅婷')
  assert.equal(params.refresh, false)
  const site = childQuery({nodeKind: 'site', site: '德国'}, {}, 'v')
  assert.equal(site.hierarchyLevel, 'product')
  assert.equal(site.brandCore, undefined)
})

test('pagination adds a non-editable load-more row and removes it on last page', () => {
  const parent = {nodeId: 'parent', nodeKind: 'product'}
  const children = [{nodeKind: 'sku'}, {nodeKind: 'sku'}]
  const page = withMoreRow(parent, children, 3, 2)
  assert.equal(page.length, 3)
  assert.equal(page[2].nextPage, 2)
  assert.equal(page[2].parent, parent)
  assert.equal(isSkuRow(page[2]), false)
  assert.equal(isSkuRow(parent), false)
  assert.equal(isSkuRow(children[0]), true)
  assert.equal(withMoreRow(parent, children, 2, 2), children)
})

test('old expand response cannot append rows after a new search or calculation', async () => {
  let respond
  const state = loaderContext(() => new Promise(resolve => { respond = resolve }))
  const pending = state.fetchChildren({nodeId: 'UK', nodeKind: 'site', site: '英国'})
  state.rowsRequest = 2
  respond({data: {items: [{sku: 'OLD'}], pagination: {total: 1}}})
  assert.equal(await pending, null)
  assert.equal(state.childrenByNode.size, 0)
})

test('failed next page retains previously loaded data and retries the same page', async () => {
  let fail = false
  const state = loaderContext(async params => {
    if (fail) throw new Error('network')
    assert.equal(params.calculationVersion, 'v1')
    return {data: {items: [{sku: `SKU${params.pageNum}`}], pagination: {total: 2}}}
  })
  const parent = {nodeId: 'UK', nodeKind: 'site', site: '英国'}
  await state.fetchChildren(parent, 1)
  fail = true
  assert.equal(await state.fetchChildren(parent, 2), null)
  assert.equal(state.childrenByNode.get('UK').length, 1)
  fail = false
  const all = await state.fetchChildren(parent, 2)
  assert.equal(all.length, 2)
  assert.equal(all[1].sku, 'SKU2')
  assert.equal(state.failedNodes.has('UK'), false)
})

test('initial failed lazy load creates a retry child; restored branch uses cached children once', async () => {
  const context = vm.createContext({restoredChildren: new Map(), fetchChildren: async () => null})
  vm.runInContext(functionSource('loadChildren'), context)
  const parent = {nodeId: 'UK', nodeKind: 'site', site: '英国'}
  let resolved
  await context.loadChildren(parent, {}, rows => { resolved = rows })
  assert.equal(resolved.length, 1)
  assert.equal(resolved[0].nodeKind, 'more')
  assert.equal(resolved[0].nextPage, 1)
  const children = [{nodeId: 'child', nodeKind: 'sku'}]
  context.restoredChildren.set('UK', children)
  context.fetchChildren = () => assert.fail('restored data should not be fetched twice')
  await context.loadChildren(parent, {}, rows => { resolved = rows })
  assert.equal(resolved, children)
  assert.equal(context.restoredChildren.size, 0)
})
