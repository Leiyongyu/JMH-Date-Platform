import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'
import { parse, compileScript, compileTemplate } from '@vue/compiler-sfc'
import { checkSteps, columnHelp, logicSteps, sourceInfo } from '../src/views/finance/ebayMonthlyProfit/help.js'

const pageFile = new URL('../src/views/finance/ebayMonthlyProfit/index.vue', import.meta.url)
const page = fs.readFileSync(pageFile, 'utf8')
const api = fs.readFileSync(new URL('../src/api/finance/ebayMonthlyProfit.js', import.meta.url), 'utf8')
const service = fs.readFileSync(new URL('../../Date-Project/backend/services/ebay_monthly_profit_service.py', import.meta.url), 'utf8')

test('page compiles', () => {
  const parsed = parse(page, { filename: pageFile.pathname })
  assert.deepEqual(parsed.errors, [])
  const script = compileScript(parsed.descriptor, { id: 'ebay-monthly-profit' })
  const template = compileTemplate({
    source: parsed.descriptor.template.content, filename: pageFile.pathname, id: 'ebay-monthly-profit',
    compilerOptions: { bindingMetadata: script.bindings }
  })
  assert.deepEqual(template.errors, [])
})

test('api calls the ERP finance routes with statMonth', () => {
  assert.match(api, /const base = '\/finance\/ebay-monthly-profit'/)
  for (const path of ['/months', '/report', '/rates', '/adjustments', '/export']) {
    assert.ok(api.includes(`\${base}${path}`), path)
  }
  assert.match(api, /responseType: 'blob'/)
  assert.match(api, /saveEbayMonthlyProfitRates[^]*?method: 'put'/)
})

test('three statements come from backend column definitions', () => {
  for (const [value, label] of [['site', '站点汇总'], ['owner', '个人利润'], ['store', '店铺利润']]) {
    assert.ok(page.includes(`{ value: '${value}', label: '${label}' }`), label)
  }
  assert.ok(page.includes('report.value[`${view.value}_columns`]'), '列定义来自后端，不在前端重算')
  assert.ok(page.includes("const SITE_CHILDREN = ['DE', 'UK']"), 'EU 下的 DE / UK 缩进显示')
  for (const key of ['site_columns', 'owner_columns', 'store_columns']) assert.ok(service.includes(`report["${key}"]`), key)
})

test('buttons follow the three permissions and rates can be entered before the report loads', () => {
  assert.equal((page.match(/v-hasPermi="\['finance:ebayMonthlyProfit:edit'\]"/g) || []).length, 2)
  assert.match(page, /v-hasPermi="\['finance:ebayMonthlyProfit:export'\]"[^]*?<app-icon name="export"/)
  assert.match(page, /<app-icon name="refresh"[^>]*:spin="loading"/)
  // 没录汇率时报表取不到：「中行汇率」按钮只看是否选了月份，不看报表
  assert.match(page, /:disabled="!statMonth" @click="openRates"/)
  assert.ok(page.includes("const RATE_CURRENCIES = ['USD', 'EUR', 'GBP']"))
  assert.ok(page.includes('至少填写 USD 汇率'))
  assert.ok(page.includes('reportError'))
})

test('supplementary fee rows depend on the scopes the backend allows', () => {
  assert.ok(page.includes("item.scopes.includes('ALL')"))
  assert.ok(page.includes("item.scopes.includes('SITE')"))
  assert.ok(page.includes("item.scopes.includes('OWNER')"))
  assert.ok(page.includes("report.value?.owners"))
  assert.match(page, /Promise\.all\(\[loadAdjustments\(\), loadReport\(\)\]\)/)
  assert.ok(page.includes('请填写非 0 金额'))
  for (const key of ['store_operation', 'gu_destruction', 'points', 'purchase_freight', 'first_leg_duty', 'loan_clear',
    'ctu_discount', 'packaging', 'brushing', 'supplement']) {
    assert.ok(service.includes(`("${key}",`), key)
  }
})

test('help describes every data source and the schedule', () => {
  const text = JSON.stringify([sourceInfo, logicSteps, checkSteps])
  for (const word of ['Finances', '太平洋时间', 'SKU分析', 'ACG1064502', '中行折算价', '05:00', '05:30', '06:00']) {
    assert.ok(text.includes(word), word)
  }
  for (const key of ['platform_income', 'platform_net', 'capital_cost', 'tax_risk', 'gross_profit', 'storage_fee']) {
    assert.ok(columnHelp[key], key)
  }
})
