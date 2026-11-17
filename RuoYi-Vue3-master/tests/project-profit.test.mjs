import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'
import { checkSteps, logicSteps, sourceInfo } from '../src/views/finance/projectProfit/help.js'

const page = fs.readFileSync(new URL('../src/views/finance/projectProfit/index.vue', import.meta.url), 'utf8')
const api = fs.readFileSync(new URL('../src/api/finance/projectProfit.js', import.meta.url), 'utf8')

test('api calls the ERP finance routes with statMonth', () => {
  assert.match(api, /const base = '\/finance\/project-profit'/)
  for (const path of ['/months', '/report', '/items', '/ebay/import', '/amz/import', '/export']) {
    assert.ok(api.includes(`\${base}${path}`), path)
  }
  assert.match(api, /method: 'put'/)
  assert.match(api, /responseType: 'blob'/)
})

test('eBay and LingXing uploads are sent as multipart (request.js defaults to JSON)', () => {
  for (const name of ['importProjectProfitEbay', 'importProjectProfitAmz']) {
    const start = api.indexOf(`export const ${name}`)
    const upload = api.slice(start, api.indexOf('\n}\n', start))
    assert.ok(upload.includes("headers: { 'Content-Type': 'multipart/form-data'"), `${name} 缺这一行 Java 会报 Current request is not a multipart request`)
    assert.ok(upload.includes('timeout: 300000'), `${name} 大文件读取要几十秒`)
  }
})

test('page shows both statements and guards edit / export by permission', () => {
  assert.ok(page.includes("{ value: 'group', label: '小组项目利润表' }"))
  assert.ok(page.includes("{ value: 'store', label: '店铺维度利润表' }"))
  assert.ok(page.includes('key="group-table"') && page.includes('key="store-table"'), 'v-if/v-else 两张表要有不同 key')
  assert.equal((page.match(/v-hasPermi="\['finance:projectProfit:edit'\]"/g) || []).length, 3, '领星上传、eBay 上传、录入手工项')
  assert.ok(page.includes("v-hasPermi=\"['finance:projectProfit:export']\""))
  assert.equal((page.match(/type="primary"/g) || []).length, 2, '页面主按钮 1 个 + 弹窗保存 1 个')
})

test('editor converts rate inputs between percent and decimal and only sends changed cells', () => {
  assert.ok(page.includes("row.unit === 'rate' ? String(Number(text) / 100) : text"))
  assert.ok(page.includes('(Number(value) * 100).toFixed(4)'))
  assert.ok(page.includes("if (text === String(original[group.code][row.code] ?? '').trim()) continue"))
})

test('help drawer content is filled', () => {
  assert.ok(sourceInfo.length >= 3 && logicSteps.length >= 4 && checkSteps.length >= 2)
})
