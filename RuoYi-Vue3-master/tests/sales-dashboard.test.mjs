import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'
import { parse, compileScript, compileTemplate } from '@vue/compiler-sfc'
import * as Vue from 'vue'
import { compile } from '@vue/compiler-dom'
import { renderToString } from '@vue/server-renderer'
import { trendDirection, comparisonDirection, trendColors } from '../src/components/SalesDashboard/trend.js'
import { salesChartOption, salesMetrics, formatMetric } from '../src/components/SalesDashboard/chart.js'
import { availableMonths, disabledMonth, fitMonthRange, validMonthRange, availableQuarters, quarterRange, quarterMonths, platformGroups } from '../src/components/SalesDashboard/months.js'
import { changeText, changeTip } from '../src/components/SalesDashboard/comparison.js'
import { rankedItems, platformBars, contributionBars } from '../src/components/SalesDashboard/contribution.js'
import { formatDetail, sortDetails, detailSummary } from '../src/components/SalesDashboard/details.js'

test('monthly line preserves zero and missing months', () => {
  const option = salesChartOption({ months: ['2026-01', '2026-02'], total: ['0', null], series: [{ name: 'DE', values: ['0', null] }] })
  assert.deepEqual(option.series[0].data, [0, null])
  assert.equal(option.series[0].connectNulls, false)
  assert.deepEqual(option.xAxis.data, ['2026-01', '2026-02'])
  assert.equal(option.tooltip.renderMode, 'richText')
})

test('six primary and two ratio cards select their own series and units', () => {
  assert.deepEqual(salesMetrics.filter(m => !m.secondary).map(m => m.key), ['platform_income', 'platform_expense', 'gross_profit', 'net_sales', 'gross_sales', 'refund_amount'])
  assert.equal(salesMetrics.filter(m => m.secondary).length, 2)
  const metrics = Object.fromEntries(salesMetrics.map((m, i) => [m.key, {
    unit: ['gross_margin', 'refund_rate'].includes(m.key) ? 'ratio' : 'CNY', total: [String(i / 10)],
    series: [{ name: 'US', values: ['0'] }]
  }]))
  for (const [i, metric] of salesMetrics.entries()) {
    const option = salesChartOption({ months: ['2026-01'], metrics }, metric.key)
    assert.deepEqual(option.series[0].data, [i / 10])
    assert.equal(option.color[0], metric.color)
    assert.equal(option.series[0].showSymbol, true)
    assert.deepEqual(salesChartOption({ months: ['2026-01'], metrics }, metric.key, 'group').series[0].data, [0])
    assert.equal(option.tooltip.valueFormatter(null), '无数据')
  }
  const ratio = salesChartOption({ months: ['2026-01'], metrics }, 'gross_margin')
  assert.equal(ratio.yAxis.axisLabel.formatter(0.2), '20%')
  assert.equal(ratio.tooltip.valueFormatter(-0.125), '-12.50%')
  assert.equal(ratio.series[0].areaStyle, undefined)
  const refund = salesChartOption({ months: ['2026-01'], metrics }, 'refund_rate')
  assert.equal(refund.yAxis.name, '退款率（%）')
  assert.equal(refund.tooltip.valueFormatter(-0.05), '-5.00%')
  assert.equal(refund.series[0].areaStyle, undefined)
})

test('card values distinguish empty and zero and show exact or compact amounts', () => {
  assert.equal(formatMetric(null), '--')
  assert.equal(formatMetric(undefined), '--')
  assert.equal(formatMetric('invalid'), '--')
  assert.equal(formatMetric('0'), '¥0.00')
  assert.equal(formatMetric('123456.78'), '¥123,456.78')
  assert.equal(formatMetric('123456.78', 'CNY', true), '¥12.35万')
  assert.equal(formatMetric('-200000000', 'CNY', true), '¥-2.00亿')
  assert.equal(formatMetric('0.123456', 'ratio'), '12.35%')
})

test('sales dashboard compiles, upload permission and platform group reset exist', () => {
  const filename = new URL('../src/components/SalesDashboard/index.vue', import.meta.url)
  const source = fs.readFileSync(filename, 'utf8')
  const { descriptor, errors } = parse(source)
  assert.deepEqual(errors, [])
  const script = compileScript(descriptor, { id: 'sales-dashboard' })
  const template = compileTemplate({ source: descriptor.template.content, filename: filename.pathname,
    id: 'sales-dashboard', compilerOptions: { bindingMetadata: script.bindings } })
  assert.deepEqual(template.errors, [])
  assert.match(source, /finance:salesDashboard:import/)
  assert.match(source, /function changePlatform\(\) \{\s+groups.value = \[\]\s+range.value = fitMonthRange/)
  assert.match(source, /:disabled-date="isMonthDisabled"/)
  assert.match(source, /:editable="false"/)
  assert.match(source, /:disabled="!monthOptions.length"/)
  assert.match(source, /monthrange/)
  assert.match(source, /class="month-range-filter"/)
  assert.match(source, /\.month-range-filter \{ flex: 0 1 240px;/)
  assert.match(source, /\.month-range-filter :deep\(\.el-date-editor\)[^\n]*flex-grow: 0/)
  assert.match(source, /chosenPreview.sha256/)
  assert.ok(source.indexOf('class="global-filters"') < source.indexOf('class="analysis-panel"'))
  assert.equal((source.match(/type="monthrange"/g) || []).length, 1)
  assert.match(source, /@click="selectMetric\(item.key\)"/)
  assert.match(source, /salesChartOption\(report.value, selectedMetric.value, trendDimension.value, showYear.value\)/)
  const selection = source.match(/function selectMetric\(key\) \{([\s\S]*?)\n\}/)[1]
  const selectedMetric = { value: 'net_sales' }
  let renders = 0
  new Function('selectedMetric', 'renderChart', 'key', selection)(selectedMetric, () => renders++, 'gross_margin')
  assert.equal(selectedMetric.value, 'gross_margin')
  assert.equal(renders, 1)
  const footnote = source.match(/function metricFootnote\(key\) \{([\s\S]*?)\n\}/)[1]
  const footnoteFn = new Function('loading', 'metricData', 'key', footnote)
  const partial = { value: '100', missing_months: ['2026-09'], complete: false, reason: null }
  assert.equal(footnoteFn({ value: false }, () => ({ summary: partial }), 'gross_profit'), '所选时间段已有数据合计')
  assert.equal(footnoteFn({ value: false }, () => ({ summary: { ...partial, value: null } }), 'gross_profit'), '所选范围暂无数据')
  assert.doesNotMatch(source, /区间数据不完整时卡片显示|个月数据不完整/)
  const home = fs.readFileSync(new URL('../src/views/index.vue', import.meta.url), 'utf8')
  assert.doesNotMatch(home, /HomeDashboardNav|sales-dashboard|销售看板/)
  assert.doesNotMatch(home, /import SalesDashboard|<SalesDashboard/)
  assert.doesNotMatch(home, /finance:salesDashboard:list/)
})

test('only months uploaded to the selected platform can be selected, including gaps and year boundaries', () => {
  const options = { ebay: { months: ['2026-03', '2025-12', '2026-01', '2026-01'] }, amz: { months: ['2026-02'] } }
  const months = availableMonths(options, 'ebay')
  assert.deepEqual(months, ['2025-12', '2026-01', '2026-03'])
  assert.equal(disabledMonth(new Date(2026, 0, 31), months), false)
  assert.equal(disabledMonth(new Date(2026, 1, 1), months), true)
  assert.equal(disabledMonth(new Date(2025, 11, 1), months), false)
  assert.equal(disabledMonth(new Date(2026, 0, 1), availableMonths(options, 'amz')), true)
  assert.equal(disabledMonth(new Date(), []), true)
})

test('default, platform change and upload ranges use available months and empty platforms stay empty', () => {
  const months = ['2025-12', '2026-01', '2026-03']
  assert.deepEqual(fitMonthRange([], months), ['2025-12', '2026-03'])
  assert.deepEqual(fitMonthRange(['2025-12', '2026-01'], months), ['2025-12', '2026-01'])
  assert.deepEqual(fitMonthRange(['2026-01', '2026-02'], months), ['2026-01', '2026-01'])
  assert.deepEqual(fitMonthRange(['2025-12', '2026-03'], ['2026-02']), ['2026-02', '2026-02'])
  assert.deepEqual(fitMonthRange(['2026-01', '2026-03'], []), [])
  assert.equal(validMonthRange(['2026-01', '2026-02'], months), false)
  assert.equal(validMonthRange(['2026-03', '2026-01'], months), false)
  assert.equal(validMonthRange(['2026-01', '2026-01'], months), true)
})

test('sales dashboard has a separate permission-gated page and database route', () => {
  const filename = new URL('../src/views/finance/salesDashboard/index.vue', import.meta.url)
  const source = fs.readFileSync(filename, 'utf8')
  const { descriptor, errors } = parse(source)
  assert.deepEqual(errors, [])
  const script = compileScript(descriptor, { id: 'sales-page' })
  assert.deepEqual(compileTemplate({ source: descriptor.template.content, filename: filename.pathname,
    id: 'sales-page', compilerOptions: { bindingMetadata: script.bindings } }).errors, [])
  assert.match(source, /SalesDashboard v-if="canView"/)
  assert.doesNotMatch(source, /HomeDashboardNav/)
  assert.match(source, /finance:salesDashboard:list/)
  const sql = fs.readFileSync(new URL('../../RuoYi-Vue-springboot3/sql/20261030_sales_dashboard_finance_menu.sql', import.meta.url), 'utf8')
  assert.match(sql, /component='finance\/salesDashboard\/index'/)
  assert.match(sql, /route_name='SalesDashboard',menu_type='C'/)
  assert.match(sql, /menu_type='C',visible='0',status='0'/)
})

test('performance detail table compiles and shares global filters with cards', () => {
  const filename = new URL('../src/components/SalesDashboard/PerformanceDetails.vue', import.meta.url)
  const source = fs.readFileSync(filename, 'utf8')
  const { descriptor, errors } = parse(source)
  assert.deepEqual(errors, [])
  const script = compileScript(descriptor, { id: 'sales-details' })
  assert.deepEqual(compileTemplate({ source: descriptor.template.content, filename: filename.pathname,
    id: 'sales-details', compilerOptions: { bindingMetadata: script.bindings } }).errors, [])
  assert.match(source, /业绩详情/)
  assert.match(source, /按组别/)
  assert.match(source, /sortedRows.value.slice/)
  assert.match(source, /watch\(\(\) => props.details/)
  assert.doesNotMatch(source, /v-html|el-date-picker|getSalesReport/)
  const parent = fs.readFileSync(new URL('../src/components/SalesDashboard/index.vue', import.meta.url), 'utf8')
  assert.match(parent, /<PerformanceDetails :details="report\?\.raw_details\?\.\[rawPlatform\]" :loading="loading" :error="error" :scope="scopeCaption"/)
  assert.ok(parent.indexOf('<PerformanceDetails') > parent.indexOf('ref="chartEl"'))
})

test('detail sorting is numeric across pages, stable, and leaves missing values last', () => {
  const rows = [{ value: '10' }, { value: null }, { value: '-2' }, { value: '100' }, { value: '0' }]
  const columns = [{ key: 'value', unit: 'CNY' }]
  assert.deepEqual(sortDetails(rows, { prop: 'value', order: 'ascending' }, columns).map(r => r.value), ['-2', '0', '10', '100', null])
  assert.deepEqual(sortDetails(rows, { prop: 'value', order: 'descending' }, columns).slice(0, 2).map(r => r.value), ['100', '10'])
  assert.deepEqual(rows.map(r => r.value), ['10', null, '-2', '100', '0'])
  assert.equal(sortDetails(rows, {}, columns), rows)
  assert.equal(formatDetail(null, 'CNY'), '--')
  assert.equal(formatDetail('0', 'CNY'), '¥0.00')
  assert.equal(formatDetail('-0.1', 'ratio'), '-10.00%')
  assert.equal(formatDetail('<b>文字</b>', 'text'), '<b>文字</b>')
})

test('detail summary uses full server totals, not the current page or sum of percentages', () => {
  const columns = [{}, { property: 'group_code' }, { property: 'gross_profit' }, { property: 'gross_margin' }]
  const details = { columns: [{ key: 'gross_profit', unit: 'CNY' }, { key: 'gross_margin', unit: 'ratio' }],
    summary: { gross_profit: '1234.56', gross_margin: '0.15' } }
  assert.deepEqual(detailSummary(columns, details), ['合计', '', '¥1,234.56', '15.00%'])
  assert.deepEqual(detailSummary(columns, undefined), ['合计', '', '', ''])
})

test('company filters preserve platform-qualified groups and quarter bounds across years', () => {
  const options = { ebay: { months: ['2025-12', '2026-07'], groups: ['US'] }, amz: { months: ['2026-09'], groups: ['US'] } }
  assert.deepEqual(availableMonths(options, 'all'), ['2025-12', '2026-07', '2026-09'])
  assert.deepEqual(platformGroups(options, 'all').map(g => g.value), ['ebay:US', 'amz:US'])
  assert.deepEqual(availableQuarters(availableMonths(options, 'all')), ['2025-Q4', '2026-Q3'])
  assert.deepEqual(quarterRange(['2026-07', '2026-09'], availableMonths(options, 'all')), ['2026-Q3', '2026-Q3'])
  assert.deepEqual(quarterMonths(['2025-Q4', '2026-Q3']), ['2025-10', '2026-09'])
  assert.deepEqual(quarterMonths(['2026-Q3', '2025-Q4']), [])
})

test('comparison labels use percent suffix for growth and rate differences, preserving incomplete and zero', () => {
  assert.equal(changeText({ value: '0.05', unit: 'ratio' }), '+5.00%')
  assert.equal(changeText({ value: '0.05', unit: 'pp' }), '+5.00%')
  assert.equal(changeText({ value: '0.0079', unit: 'pp' }), '+0.79%')
  assert.equal(changeText({ value: '-0.0079', unit: 'pp' }), '-0.79%')
  assert.equal(changeText({ value: '0', unit: 'pp' }), '0.00%')
  assert.equal(changeText({ value: '-1', unit: 'ratio' }), '-100.00%')
  assert.equal(changeText({ value: null, reason: 'zero_baseline' }), '基期为0')
  assert.equal(changeText({ value: null, reason: 'incomplete' }), '--')
  const tip = changeTip({ start: '2026-04', end: '2026-06', baseline: '100', difference: '-20', reason: 'incomplete', missing_current_months: ['2026-09'] }, '80', 'CNY', ['2026-07', '2026-09'])
  assert.match(tip, /2026-04 至 2026-06/)
  assert.match(tip, /本期不完整月份：2026-09/)
})

test('ratio card and chart tooltips use percent signs without changing rate differences', () => {
  const comparison = { value: '0.0079', unit: 'pp', difference: '0.0079', baseline: '0.0901', start: '2025-08', end: '2025-08' }
  const tip = changeTip(comparison, '0.098', 'ratio', ['2026-08', '2026-08'])
  assert.match(tip, /增减：\+0\.79%/)
  assert.doesNotMatch(tip, /百分点/)
  for (const key of ['gross_margin', 'refund_rate']) {
    const option = salesChartOption({ months: ['2026-08'], metrics: { [key]: {
      unit: 'ratio', total: ['0.098'], point_comparisons: [{ mom: comparison, yoy: comparison }]
    } } }, key)
    const chartTip = option.tooltip.formatter([{ axisValueLabel: '2026-08', seriesName: '筛选合计', value: 0.098, seriesIndex: 0, dataIndex: 0 }])
    assert.match(chartTip, /环比 \{up\|↑ \+0\.79%\}/)
    assert.match(chartTip, /同比 \{up\|↑ \+0\.79%\}/)
    assert.doesNotMatch(chartTip, /百分点/)
  }
})

test('trend arrows follow numeric change, not business meaning, and leave unavailable comparisons neutral', () => {
  assert.equal(trendDirection('0.0079'), 'up')
  assert.equal(trendDirection('-0.0079'), 'down')
  for (const value of [0, '0', '-0', null, undefined, '', 'bad', Infinity]) assert.equal(trendDirection(value), '')
  for (const reason of ['incomplete', 'missing_current', 'missing_baseline', 'zero_baseline']) {
    assert.equal(comparisonDirection({ value: '1', reason }), '')
  }
  assert.equal(comparisonDirection({ value: '-1' }), 'down')
})

test('TrendValue renders red up and green down arrows while zero and missing values have no arrow', async () => {
  const source = fs.readFileSync(new URL('../src/components/SalesDashboard/TrendValue.vue', import.meta.url), 'utf8')
  const template = parse(source).descriptor.template.content
  const render = new Function('Vue', compile(template, { mode: 'function', prefixIdentifiers: true }).code)(Vue)
  for (const [value, direction, arrow, color] of [['1', 'up', '↑', '#d93025'], ['-1', 'down', '↓', '#16834a'], ['0', '', '', ''], [null, '', '', '']]) {
    const app = Vue.createSSRApp({ render, setup: () => ({ direction: trendDirection(value), trendColors }) })
    const html = await renderToString(app)
    if (direction) {
      assert.ok(html.includes(`trend-${direction}`))
      assert.ok(html.includes(arrow))
      assert.ok(html.includes(`color:${color}`))
    } else assert.doesNotMatch(html, /trend-arrow|trend-up|trend-down/)
  }
})

test('platform-specific chart comparisons use the same signed arrows and colors', () => {
  const option = salesChartOption({ months: ['2026-08'], metrics: { commission: {
    unit: 'CNY', total: ['10'], point_comparisons: [{ mom: { value: '-0.2' }, yoy: { value: '0' } }]
  } } }, 'commission')
  const tip = option.tooltip.formatter([{ value: 10, seriesIndex: 0, dataIndex: 0 }])
  assert.match(tip, /环比 \{down\|↓ -20\.00%\}/)
  assert.match(tip, /同比 0\.00%/)
  assert.equal(option.tooltip.textStyle.rich.up.color, '#d93025')
  assert.equal(option.tooltip.textStyle.rich.down.color, '#16834a')
})

for (const name of ['TrendValue', 'ComparisonValue', 'ComparisonTable', 'DashboardChart', 'ContributionPanel', 'PlatformAnalysis']) {
  test(`${name} compiles`, () => {
    const filename = new URL(`../src/components/SalesDashboard/${name}.vue`, import.meta.url)
    const { descriptor, errors } = parse(fs.readFileSync(filename, 'utf8'))
    assert.deepEqual(errors, [])
    const script = compileScript(descriptor, { id: name })
    assert.deepEqual(compileTemplate({ source: descriptor.template.content, filename: filename.pathname, id: name, compilerOptions: { bindingMetadata: script.bindings } }).errors, [])
  })
}

test('company, platform and group trends select separate series and last-year dashed line', () => {
  const report = { months: ['2026 Q3'], metrics: { net_sales: { total: ['300'], year_total: ['200'], platform_series: [{name:'eBay',values:['100']},{name:'AMZ',values:['200']}], series: [{name:'eBay / US',values:['100']}] } } }
  assert.equal(salesChartOption(report, 'net_sales', 'total').series.length, 1)
  assert.deepEqual(salesChartOption(report, 'net_sales', 'platform').series.map(s => s.name), ['eBay', 'AMZ'])
  assert.equal(salesChartOption(report, 'net_sales', 'group').series[0].name, 'eBay / US')
  assert.equal(salesChartOption(report, 'net_sales', 'total', true).series[1].lineStyle.type, 'dashed')
})

test('contribution chart preserves negative amounts, excludes unavailable rows and does not mutate data', () => {
  const items = [{ name: 'US', current: '50', baseline: '0', difference: '50' }, { name: 'DE', current: '-100', baseline: '0', difference: '-100' }]
  const report = { contributions: { gross_profit: { mom: { group: { items, unavailable: [{ name: 'missing', difference: '999' }] } } } },
    breakdown: { group: [{ name: 'US', metrics: { gross_profit: { value: '50' } } }, { name: 'missing', metrics: { gross_profit: { value: null } } }] } }
  const ranked = rankedItems(report, 'gross_profit', 'group', 'delta', 'mom')
  assert.deepEqual(ranked.map(r => r.name), ['DE', 'US'])
  assert.deepEqual(items.map(r => r.name), ['US', 'DE'])
  assert.deepEqual(contributionBars(ranked, 'delta').series[0].data.map(d => d.value), [-100, 50])
  assert.deepEqual(rankedItems(report, 'gross_profit', 'group', 'rank', 'mom').map(r => r.name), ['US'])
  assert.match(contributionBars(ranked, 'delta').tooltip.formatter([{ dataIndex: 0 }]), /增减金额：¥-100.00/)
})

test('platform bars preserve null and zero, and separate signed stacks', () => {
  const option = platformBars({ months: ['2026-08', '2026-09'], metrics: { gross_profit: { platform_series: [{ name: 'eBay', values: ['0', null] }, { name: 'AMZ', values: ['-100', '200'] }] } } }, 'gross_profit')
  assert.deepEqual(option.series[0].data, [0, null])
  assert.deepEqual(option.series[1].data, [-100, 200])
  assert.equal(option.series[0].stackStrategy, 'samesign')
})

test('platform specialty chart uses its own label and summary tables can expand platform fields', () => {
  const option = salesChartOption({ months: ['2026-09'], metrics: { commission: { label: '平台佣金', unit: 'CNY', total: ['-100'], series: [] } } }, 'commission')
  assert.deepEqual(option.series[0].data, [-100])
  const table = fs.readFileSync(new URL('../src/components/SalesDashboard/ComparisonTable.vue', import.meta.url), 'utf8')
  assert.match(table, /展开平台独有字段/)
  assert.match(table, /props.report\?\.platform !== 'all'/)
  const page = fs.readFileSync(new URL('../src/components/SalesDashboard/index.vue', import.meta.url), 'utf8')
  assert.match(page, /<ContributionPanel :report="report" :loading="loading" :scope="scopeCaption"/)
  assert.match(page, /<PlatformAnalysis :report="report" :loading="loading" :scope="scopeCaption"/)
})
