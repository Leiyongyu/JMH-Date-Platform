import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'
import vm from 'node:vm'
import { amzProfitColumnHelp } from '../src/views/finance/amzProfitReport/columnHelp.js'

const source = fs.readFileSync(new URL('../src/views/finance/amzProfitReport/index.vue', import.meta.url), 'utf8')
const columnsSource = source.slice(source.indexOf('const columns = ['), source.indexOf('].map(column =>'))
const columnKeys = Array.from(columnsSource.matchAll(/\{ key: '([^']+)', label:/g), match => match[1])

test('every report column has source API, table, rule and empty handling', () => {
  assert.equal(columnKeys.length, 13)
  assert.deepEqual(Object.keys(amzProfitColumnHelp).sort(), [...columnKeys].sort())
  for (const key of columnKeys) {
    for (const field of ['sourceApi', 'sourceTable', 'formula', 'emptyHandling']) {
      assert.ok(String(amzProfitColumnHelp[key][field] || '').trim(), `${key}.${field}`)
    }
  }
  assert.ok(source.includes('help: amzProfitColumnHelp[column.key]'))
})

test('only order profit columns come from OrderProfit; the rest from settlement', () => {
  for (const key of columnKeys) {
    const api = amzProfitColumnHelp[key].sourceApi
    if (key.startsWith('order_')) assert.match(api, /OrderProfit/)
    else if (key !== 'target_usd') assert.match(api, /profit\/statistics/)
  }
  assert.match(amzProfitColumnHelp.target_usd.sourceTable, /monthly_inventory_report_view_snapshot/)
  assert.match(amzProfitColumnHelp.order_gross_margin.formula, /amount/)
})

test('trend uses the supplied up/down icons with the change shown inline', () => {
  for (const name of ['trend-up', 'trend-down']) {
    const svg = fs.readFileSync(new URL(`../src/assets/icons/svg/jmh/${name}.svg`, import.meta.url), 'utf8')
    assert.doesNotMatch(svg, /fill=/, `${name} inherits currentColor`)
  }
  assert.ok(source.includes("'jmh-trend-up' : 'jmh-trend-down'"))
  assert.ok(source.includes('{{ changeLabel(column, row) }}'))
  assert.doesNotMatch(source, /changeText/)
  assert.doesNotMatch(source, /[↑↓]/)
})

test('page uses the reusable month-range picker and export follows the page period', () => {
  assert.ok(source.includes("import DateRangePicker from '@/components/DateRangePicker/index.vue'"))
  assert.equal((source.match(/<DateRangePicker v-model="period" mode="month"/g) || []).length, 1)
  assert.doesNotMatch(source, /exportRange/)
  assert.ok(source.includes('const [startMonth, endMonth] = period.value'))
  assert.ok(source.includes('exportDimensions.value = [dimension.value]'))
  assert.doesNotMatch(source, /statMonth|target_stat_month|report\.previous_month/)
  const api = fs.readFileSync(new URL('../src/api/finance/amzProfitReport.js', import.meta.url), 'utf8')
  assert.ok(api.includes('params: { startMonth, endMonth, dimension, currency }'))
  assert.ok(api.includes('params: { startMonth, endMonth, dimensions, currency }'))
})

test('currency defaults to CNY and drives display, query and export', () => {
  assert.ok(source.includes("const currency = ref('CNY')"))
  assert.ok(source.includes('getAmzProfitReport(startMonth, endMonth, dimension.value, currency.value)'))
  assert.ok(source.includes("exportDimensions.value.join(','), currency.value)"))
  assert.ok(source.includes("report.value?.currency_code === 'USD' ? '$' : '¥'"))
  assert.match(amzProfitColumnHelp.sales_amount.formula, /我的汇率/)
  assert.ok(source.includes('缺少 USD 我的汇率，按人民币无法对比，可切换美元查看'))
  assert.ok(source.indexOf('data.previous_missing_rate') < source.indexOf('数据未完整拉取，环比和涨跌图标不显示'))
  assert.match(amzProfitColumnHelp.sales_amount.formula, /不用官方汇率/)
})

test('export is a permission-gated month-range dialog', () => {
  assert.ok(source.includes("v-hasPermi=\"['finance:amzProfitReport:export']\""))
  assert.doesNotMatch(source, /type="monthrange"/)
  assert.ok(source.includes('icon-class="jmh-export"'))
  assert.ok(source.includes('icon-class="jmh-refresh"'))
  assert.doesNotMatch(source, />刷新<\/el-button>/)
  assert.ok(source.includes('exportAmzProfitReport(startMonth, endMonth'))
})

test('inline change: percent for amounts, percentage points for rates, none when undefined', () => {
  const pick = name => {
    const start = source.indexOf(`function ${name}(`)
    return source.slice(start, source.indexOf('\n}\n', start) + 2)
  }
  const ctx = vm.createContext({})
  vm.runInContext(`${pick('numberOrNull')}\n${pick('changeLabel')}`, ctx)
  const label = (column, current, previous) => ctx.changeLabel(column, { v: current, previous: { v: previous } })
  assert.equal(label({ key: 'v', format: 'money', trend: true }, '972883.77', '987798.60'), '1.51%')
  assert.equal(label({ key: 'v', format: 'qty', trend: true }, '120', '100'), '20.00%')
  assert.equal(label({ key: 'v', format: 'rate', trend: true }, '0.1225', '0.1176'), '0.49pp')
  assert.equal(label({ key: 'v', format: 'money', trend: true }, '10', '0'), '')
  assert.equal(label({ key: 'v', format: 'money', trend: true }, '10', null), '')
  assert.equal(label({ key: 'v', format: 'rate', trend: 'sign' }, '0.1', '0.2'), '')
})
