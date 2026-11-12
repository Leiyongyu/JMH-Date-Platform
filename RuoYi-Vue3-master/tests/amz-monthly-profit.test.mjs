import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'
import { checkSteps, columnHelp, logicSteps, sourceInfo } from '../src/views/finance/amzMonthlyProfit/help.js'

const page = fs.readFileSync(new URL('../src/views/finance/amzMonthlyProfit/index.vue', import.meta.url), 'utf8')
const api = fs.readFileSync(new URL('../src/api/finance/amzMonthlyProfit.js', import.meta.url), 'utf8')
const service = fs.readFileSync(new URL('../../Date-Project/backend/services/amz_monthly_profit_service.py', import.meta.url), 'utf8')

test('api calls the ERP finance routes with statMonth', () => {
  assert.match(api, /const base = '\/finance\/amz-monthly-profit'/)
  for (const path of ['/months', '/report', '/adjustments', '/export']) {
    assert.ok(api.includes(`\${base}${path}`), path)
  }
  assert.match(api, /responseType: 'blob'/)
  assert.match(api, /method: 'put'/)
  assert.match(api, /method: 'delete'/)
})

test('page renders store and group statements from backend column definitions', () => {
  assert.ok(page.includes("{ value: 'store', label: '店铺利润' }"))
  assert.ok(page.includes("{ value: 'group', label: '小组利润' }"))
  assert.ok(page.includes('report.value.store_columns : report.value.group_columns'), '列定义来自后端，不在前端重算')
  assert.ok(page.includes("row.row_type === 'SUBTEAM'"), 'US3 下的 MJ / ZXY 小组行单独标识')
})

test('buttons follow the three permissions', () => {
  assert.ok(page.includes("v-hasPermi=\"['finance:amzMonthlyProfit:edit']\""))
  assert.ok(page.includes("v-hasPermi=\"['finance:amzMonthlyProfit:export']\""))
  // 改版后图标统一走 <app-icon>：刷新带 :spin 加载态，导出在导出权限的包裹里。
  assert.match(page, /<app-icon name="refresh"[^>]*:spin="loading"/)
  assert.match(page, /v-hasPermi="\['finance:amzMonthlyProfit:export'\]"[^]*?<app-icon name="export"/)
})

test('supplementary fees go to leaf rows only and refresh the report after changes', () => {
  assert.ok(page.includes('report?.leaf_codes'))
  assert.ok(page.includes('report?.adjustment_items'))
  assert.match(page, /Promise\.all\(\[loadAdjustments\(\), loadReport\(\)\]\)/)
  assert.ok(page.includes('请填写非 0 金额'))
})

test('empty values show -- instead of 0', () => {
  assert.match(page, /if \(value === null \|\| value === undefined \|\| value === ''\) return '--'/)
})

test('logic and data source live behind the top-right question button, not an always-on notice', () => {
  assert.match(page, /aria-label="页面逻辑与数据来源"[^>]*>\s*<app-icon name="help"/)
  assert.ok(page.includes('<el-drawer v-model="helpVisible"'))
  assert.doesNotMatch(page, /数据口径说明/, '原来常驻的口径说明块已移入问号按钮')
  assert.ok(logicSteps.some(step => step.text.includes('最终毛利 = 毛利润 − FBA途损抵扣 + 手工补充费用')))
  assert.ok(sourceInfo.some(item => item.value.includes('/bd/profit/report/open/report/msku/list')))
  assert.ok(checkSteps.length >= 4)
})

test('every statement column from the backend has a source and a note in the help', () => {
  const keys = new Set()
  for (const match of service.matchAll(/\("([a-z_0-9]+)", "[^"]+", "(?:money|qty|rate)"\)/g)) keys.add(match[1])
  for (const match of service.matchAll(/\("([a-z_]+_fee)", "[^"]+"\)/g)) keys.add(match[1])
  assert.ok(keys.size >= 35, `parsed ${keys.size} keys`)
  for (const key of keys) {
    assert.ok(columnHelp[key]?.source && columnHelp[key]?.note, key)
  }
})
