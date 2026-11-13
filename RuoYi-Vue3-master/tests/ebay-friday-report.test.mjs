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
  assert.equal(page.match(/<el-button type="primary"/g)?.length, 2, '实心主按钮只有查询和弹窗里的保存')
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
