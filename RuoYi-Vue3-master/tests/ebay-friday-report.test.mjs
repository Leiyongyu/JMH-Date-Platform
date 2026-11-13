import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'
import { sheetRules, sourceInfo } from '../src/views/operations/ebay/fridayReport/help.js'

const page = fs.readFileSync(new URL('../src/views/operations/ebay/fridayReport/index.vue', import.meta.url), 'utf8')
const api = fs.readFileSync(new URL('../src/api/operations/ebay/fridayReport.js', import.meta.url), 'utf8')

test('api calls the ERP friday report routes', () => {
  assert.match(api, /const base = '\/operations\/ebay\/friday-report'/)
  for (const path of ['/overview', '/listings', '/stocks', '/generate', '/stores', '/export']) {
    assert.ok(api.includes(`\${base}${path}`), path)
  }
  assert.match(api, /responseType: 'blob'/)
})

test('two sheets switch with chips, like the other report pages', () => {
  assert.ok(page.includes("{ value: 'listing', label: '有货无货' }"))
  assert.ok(page.includes("{ value: 'stock', label: '海外仓库存' }"))
  assert.ok(page.includes('class="chips" role="tablist"'))
  assert.ok(page.includes('class="filter-bar"') && page.includes('class="table-card"'), '页面骨架沿用固定风格')
})

test('toolbar uses semantic icon buttons and follows the three permissions', () => {
  assert.ok(!page.includes('<icon-btn icon="refresh"'), '只留一个「重新生成」，不再另放刷新按钮')
  assert.equal(page.match(/<icon-btn icon="resync"/g)?.length, 1)
  assert.ok(page.includes('<icon-btn icon="export"'))
  assert.ok(page.includes("v-hasPermi=\"['operations:ebayFridayReport:edit']\""))
  assert.ok(page.includes("v-hasPermi=\"['operations:ebayFridayReport:export']\""))
  assert.equal(page.match(/<el-button type="primary"/g)?.length, 3, '实心主按钮：查询（前两张表）、上传订单（订单售出统计，那时不显示筛选）、弹窗保存')
  assert.ok(page.includes(`<div v-if="view !== 'orders'" class="filters">`), '订单售出统计不显示筛选区，同一视图只有一个主按钮')
})

test('judge and status use pills; store columns grouped by main site with wrong-site items highlighted', () => {
  assert.ok(page.includes('jb-pill jb-pill--ok">T') && page.includes('jb-pill jb-pill--danger">F'))
  assert.ok(page.includes('jb-pill jb-pill--danger">无链接'))
  assert.ok(page.includes('v-for="group in storeGroups"'))
  assert.ok(page.includes("'store-item--wrong': item.includes(':')"))
})

test('help covers both sheets and the data sources', () => {
  assert.ok(sourceInfo.some(item => item.value.includes('get_product_inventory')))
  const titles = sheetRules.map(sheet => sheet.title)
  assert.ok(titles[0].startsWith('有货无货') && titles[1].startsWith('海外仓库存'))
  assert.ok(sheetRules[0].rows.some(row => row.note.includes('中间码 + 站点 + 是否二手')))
})

test('only the latest issue is shown: no history date picker', () => {
  assert.ok(!page.includes('v-model="reportDate"'), '不再提供期次下拉')
  assert.ok(page.includes('class="period-tag"'))
  assert.ok(sourceInfo.some(item => item.value.includes('只保留最新一期')))
})

test('switching sheets rebuilds the table and never renders one sheet with the other sheet rows', () => {
  assert.ok(page.includes('key="listing-table"') && page.includes('key="stock-table"'), '两张表各自独立，不复用同一个表格实例')
  assert.ok(page.includes('function changeView(value) {') && page.includes('    rows.value = []'), '切换前先清空数据')
  assert.ok(page.includes('row.store_items?.[store.key]'), '店铺列读取加空值保护')
  assert.ok(page.includes('if (request !== rowsRequest) return'), '慢回来的旧请求不覆盖当前表')
})

test('order sales tab: upload the ERP order export and show the pivot per owner', () => {
  assert.ok(page.includes("{ value: 'orders', label: '订单售出统计' }"))
  assert.ok(page.includes('key="orders-block"'))
  assert.ok(page.includes(':http-request="handleOrderUpload"') && page.includes('accept=".xlsx"'))
  assert.ok(page.includes("v-hasPermi=\"['operations:ebayFridayReport:edit']\" :show-file-list=\"false\""), '上传沿用维护权限')
  for (const label of ['非重复计数项:中间码+站点', '求和项:美金收入', '求和项:购买数量']) assert.ok(page.includes(label), label)
  assert.ok(page.includes('{ ...orderSales.value.total, isTotal: true }'), '最下面是总计行')
  assert.ok(api.includes('/order-sales/import') && api.includes("data.append('file', file)"))
  assert.ok(sheetRules.some(sheet => sheet.title.startsWith('订单售出统计')))
})
