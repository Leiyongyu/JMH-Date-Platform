import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'
import vm from 'node:vm'
import { amzProfitColumnHelp } from '../src/views/finance/amzProfitReport/columnHelp.js'

// 页面文件可能是 CRLF（改版时存成了 CRLF），下面按 '\n}\n' 截取函数源码，先统一成 LF。
const source = fs.readFileSync(new URL('../src/views/finance/amzProfitReport/index.vue', import.meta.url), 'utf8')
  .replace(/\r\n/g, '\n')
const registry = fs.readFileSync(new URL('../src/components/AppIcon/registry.js', import.meta.url), 'utf8')
// 把 #rgb / #rrggbb / rgb() / rgba() 解析成 { hue, alpha }，用色相判断「红」「绿」，不绑死具体色值。
function colorInfo(text) {
  const value = String(text).trim()
  let r, g, b, alpha = 1
  const hex = value.match(/^#([0-9a-f]{3}|[0-9a-f]{6})$/i)
  const rgb = value.match(/^rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*(?:,\s*([\d.]+)\s*)?\)$/i)
  if (hex) {
    const full = hex[1].length === 3 ? hex[1].replace(/./g, c => c + c) : hex[1]
    ;[r, g, b] = [0, 2, 4].map(i => parseInt(full.slice(i, i + 2), 16))
  } else if (rgb) {
    ;[r, g, b] = rgb.slice(1, 4).map(Number)
    if (rgb[4] !== undefined) alpha = Number(rgb[4])
  } else {
    assert.fail(`unrecognised color: ${value}`)
  }
  const max = Math.max(r, g, b)
  const min = Math.min(r, g, b)
  let hue = 0
  if (max !== min) {
    const d = max - min
    if (max === r) hue = ((g - b) / d) % 6
    else if (max === g) hue = (b - r) / d + 2
    else hue = (r - g) / d + 4
    hue = (hue * 60 + 360) % 360
  }
  return { hue, alpha, lightness: (max + min) / 2 / 255 }
}
const isRed = color => { const { hue } = colorInfo(color); return hue <= 20 || hue >= 340 }
// 绿到青绿都算「跌」色：改版的跌色是青绿 #12b2a6（色相约 176°），旧的是 #16834a（约 145°）。
const isGreen = color => { const { hue } = colorInfo(color); return hue >= 90 && hue <= 185 }

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

test('trend uses up/down icons, red for up and green for down, with the change shown inline', () => {
  // 改版后涨跌图标走 <app-icon> 的 trendUp / trendDown（Solar 线性图标，颜色跟随 currentColor）。
  assert.ok(source.includes("<app-icon :name=\"trend(column, row) === 'up' ? 'trendUp' : 'trendDown'\""))
  assert.match(registry, /^\s*trendUp: \w+,$/m)
  assert.match(registry, /^\s*trendDown: \w+,$/m)
  const up = source.match(/\.trend-up \{ color: ([^;]+);/)
  const down = source.match(/\.trend-down \{ color: ([^;]+);/)
  assert.ok(up && down, 'trend-up / trend-down set their own color')
  assert.ok(isRed(up[1]), `up should be red, got ${up[1]}`)
  assert.ok(isGreen(down[1]), `down should be green, got ${down[1]}`)
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
  assert.match(source, /v-hasPermi="\['finance:amzProfitReport:export'\]"[^]*?<app-icon name="export"/)
  assert.match(source, /<app-icon name="refresh"[^>]*:spin="loading"/)
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
