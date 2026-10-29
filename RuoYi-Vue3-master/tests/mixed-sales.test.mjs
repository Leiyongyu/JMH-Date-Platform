import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { parse, compileScript, compileTemplate } from '@vue/compiler-sfc'
import { matchHint, quantity, price } from '../src/views/operations/mixedSales/format.js'
import { ebayDetailQuery, ebayMetrics, ebaySiteMetrics } from '../src/views/operations/mixedSales/ebayMetrics.js'
import vm from 'node:vm'

test('missing source remains blank placeholder while real zero remains zero', () => {
  assert.equal(quantity(null), '--')
  assert.equal(quantity(undefined), '--')
  assert.equal(quantity(0), '0')
  assert.equal(quantity('1200'), '1,200')
  assert.equal(matchHint(2, 3), '已匹配 2/3 个MSKU')
  assert.equal(matchHint(3, 3), '')
  assert.equal(matchHint(0, 0), '')
  assert.equal(price(null), '--')
  assert.equal(price('0'), '0')
  assert.equal(price('11.23456789'), '11.23456789')
})

for (const file of ['index.vue', 'AmzPanel.vue', 'AmzDetail.vue', 'EbayPanel.vue', 'EbayDetail.vue', 'InventoryAgeColumn.vue']) {
  test(`${file}: Vue script and template compile`, () => {
    const source = readFileSync(new URL(`../src/views/operations/mixedSales/${file}`, import.meta.url), 'utf8')
    const { descriptor, errors } = parse(source)
    assert.deepEqual(errors, [])
    const script = compileScript(descriptor, { id: file })
    const template = compileTemplate({source: descriptor.template.content, filename: file, id: file,
      compilerOptions: { bindingMetadata: script.bindings }})
    assert.deepEqual(template.errors, [])
  })
}

test('eBay details pin the displayed version, exact SKU and applied filters', () => {
  const args = ebayDetailQuery({sku: 'FRD-70327-0076'}, {sku: '70327', site: '英国', productName: '产品'}, 'version')
  assert.equal(args.sku, 'FRD-70327-0076')
  assert.equal(args.site, '英国')
  assert.equal(args.productName, '产品')
  assert.equal(args.calculationVersion, 'version')
})

test('common SKUs retain expandable price comparison', () => {
  const source = readFileSync(new URL('../src/views/operations/mixedSales/AmzPanel.vue', import.meta.url), 'utf8')
  assert.ok(!source.includes('no-details'))
  assert.ok(!source.includes('v-if="Number(row.listingCount)"'))
  assert.ok(source.includes('<amz-detail :sku="row.sku"'))
})

test('Amazon store inventory and both platform prices are columns in a single table', () => {
  const source = readFileSync(new URL('../src/views/operations/mixedSales/AmzDetail.vue', import.meta.url), 'utf8')
  assert.equal((source.match(/<el-table\s/g) || []).length, 1)
  assert.ok(!source.includes('<price-comparison'))
  for (const field of ['storeName', '本店近30天销量', 'fbaStock', 'amzMinPrice', 'amzMaxPrice', 'ebayMinPrice', 'ebayMaxPrice'])
    assert.ok(source.includes(field))
})

test('eBay site rows show prices inline and only the 30-day sales metric', () => {
  const source = readFileSync(new URL('../src/views/operations/mixedSales/EbayDetail.vue', import.meta.url), 'utf8')
  const panel = readFileSync(new URL('../src/views/operations/mixedSales/EbayPanel.vue', import.meta.url), 'utf8')
  assert.equal((source.match(/<el-table\s/g) || []).length, 1)
  assert.ok(!source.includes("emit('prices'"))
  assert.ok(!panel.includes('ebay-price-dialog') && !panel.includes('showPrices'))
  for (const field of ['ebayMinPrice', 'ebayMaxPrice', 'amzMinPrice', 'amzMaxPrice'])
    assert.ok(source.includes(field))
  assert.deepEqual(ebayMetrics.filter(c => c.key.startsWith('sales')).map(c => c.key), ['sales30d'])
  assert.deepEqual(ebaySiteMetrics.filter(c => c.key.endsWith('Sales30d')).map(c => c.key), ['ebaySales30d','amzSales30d'])
  const amz = readFileSync(new URL('../src/views/operations/mixedSales/AmzDetail.vue', import.meta.url), 'utf8')
  assert.ok(amz.includes('amzSales30d') && amz.includes('ebaySales30d'))
})

test('late eBay response cannot update a panel after switching platforms', async () => {
  const source = readFileSync(new URL('../src/views/operations/mixedSales/EbayPanel.vue', import.meta.url), 'utf8')
  let respond
  const context = vm.createContext({requestId: 0, query: {}, calculationVersion: {value: 'old'},
    loading: {value: false}, rows: {value: []}, total: {value: 0},
    listEbayMixedSales: () => new Promise(resolve => { respond = resolve })})
  vm.runInContext(source.match(/async function load\([^]*?\n\}/)[0], context)
  const pending = context.load()
  context.requestId += 1 // onBeforeUnmount on platform change
  respond({data: {items: [{sku: 'stale'}]}})
  await pending
  assert.equal(context.rows.value.length, 0)
})
