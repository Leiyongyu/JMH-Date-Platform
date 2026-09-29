import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'
import vm from 'node:vm'
import { computed, ref } from 'vue'
import { parse, compileScript, compileTemplate } from '@vue/compiler-sfc'

const file = new URL('../src/views/operations/ebay/inventoryDetail/InventoryAgeRatio.vue', import.meta.url)
const source = fs.readFileSync(file, 'utf8')
const { descriptor, errors } = parse(source)
assert.deepEqual(errors, [])
const script = compileScript(descriptor, { id: 'age-ratio-test' })
const names = ['report', 'loading',
  'visibleWarnings', 'emptyText', 'buckets', 'siteColumns', 'ratioBarWidth', 'version', 'disposed', 'formatQuantity', 'formatMoney', 'formatPercent', 'loadReport']
function harness({ allowed = true, read, refresh } = {}) {
  const calls = [], events = [], messages = []
  const context = vm.createContext({
    props: { dateRange: ['2026-09-01', '2026-09-30'] }, ref, computed, checkPermi: () => allowed,
    emit: (...args) => events.push(args), ElMessage: { success: message => messages.push(message) },
    getEbayInventoryAgeRatio: async params => { calls.push(['read', params]); return read?.(params) || { data: { owners: [], sites: [], available_dates: [] } } },
    recalculateEbayInventoryAgeRatio: async (...args) => {
      calls.push(['refresh', args]); return refresh?.() || { data: { stat_date: '2026-09-29', owners: [{ name: '张三' }], sites: [{ name: '德国' }] } }
    }
  })
  for (const name of names) {
    const node = script.scriptSetupAst.find(n => n.id?.name === name || n.declarations?.some(d => d.id.name === name))
    assert.ok(node, name)
    vm.runInContext(descriptor.scriptSetup.content.slice(node.start, node.end), context)
  }
  vm.runInContext('globalThis.api = { ' + names.join(',') + ' }', context)
  return { api: context.api, props: context.props, calls, events, messages }
}

test('eleven-column owner and eight-column site views compile without verbose help or exclusion details', () => {
  const result = compileTemplate({ source: descriptor.template.content, filename: file.pathname, id: 'age-ratio-test',
    compilerOptions: { bindingMetadata: script.bindings } })
  assert.deepEqual(result.errors, [])
  assert.doesNotMatch(source, /库存数量 ×（采购单价＋头程单价）|库龄分段：|捷克仓归德国站/)
  assert.doesNotMatch(descriptor.template.content, /excluded_details|excluded_rows|row.candidates|缺数/)
  assert.match(source, /core-supplier-max-landed-cost-v4/)
  assert.match(source, /核心码＋供应商编号/)
  assert.match(source, /report.generated_at && report.calculation_version/)
  const h = harness()
  assert.equal(h.api.buckets.length * 2 + 3, 11)
  assert.equal((descriptor.template.content.match(/<el-table :data=/g) || []).length, 2)
  assert.equal(h.api.siteColumns.length + 1, 8)
  assert.equal(h.api.siteColumns.map(c => c.label).join(','), '站点,总库存,>180天库存,库存占比,总货值,>180天货值,货值占比')
  assert.equal(h.api.siteColumns.map(c => c.prop).join(','), 'name,total_quantity,over_180_quantity,over_180_quantity_ratio,total_value,over_180_value,over_180_ratio')
})

test('exclusion warnings are hidden without changing report data or other warnings', () => {
  const h = harness()
  h.api.report.value = {
    warnings: ['2条明细缺成本，未计入货值及占比；当前金额为可计算部分。', '谷仓最新源数据不是当月拉取'],
    excluded_details: [{ sku: 'JMH-60013' }], excluded_rows: 1
  }
  assert.equal(h.api.visibleWarnings.value.length, 1)
  assert.equal(h.api.visibleWarnings.value[0], '谷仓最新源数据不是当月拉取')
  assert.equal(h.api.report.value.excluded_details.length, 1)
  assert.equal(h.api.report.value.warnings.length, 2)
})

test('historical import notes are hidden for single dates and ranges without changing saved data', () => {
  const h = harness()
  const notes = [
    'Excel历史汇总：<90货值及占比按要求补0，总货值保留原表，分段合计及占比不一定等于总货值或100%。',
    '历史分段沿用原Excel公式：90至120含两端、120至180含两端、180及以上；与当前互斥分段口径不同，未按当前规则重算。',
    '原表仅有负责人汇总，无站点数据及SKU明细；站点维度为空。负责人保留原表，不按当前负责人重新匹配。'
  ]
  const warnings = ['', '2026-08-03：', '2026-08-10：', '2026-08-17：', '2026-08-24：', '2026-08-31：', '2026-09-07：']
    .flatMap(prefix => notes.map(note => prefix + note))
  warnings.push('2026-09-29：谷仓最新源数据不是当月拉取')
  h.api.report.value = { warnings, owners: [{ name: '陈丽', total_value: '571847.9906' }], sites: [] }
  const before = JSON.stringify(h.api.report.value)
  assert.equal(h.api.visibleWarnings.value.length, 1)
  assert.equal(h.api.visibleWarnings.value[0], warnings.at(-1))
  assert.equal(JSON.stringify(h.api.report.value), before)
})

test('zero money stays zero but null ratios show unavailable and fractions display as percentages', () => {
  const h = harness()
  assert.equal(h.api.formatMoney('0'), '0.00')
  assert.equal(h.api.formatPercent(null), '--')
  assert.equal(h.api.formatPercent('0.125'), '12.50%')
  assert.equal(h.api.formatQuantity(undefined), '--')
  assert.equal(h.api.formatQuantity(null), '--')
  assert.equal(h.api.formatQuantity('0.000000'), '0')
  assert.equal(h.api.formatQuantity('2751.000000'), '2,751')
})

test('pink data bars use actual percentages against a fixed 100 percent cell width', () => {
  const h = harness()
  h.api.report.value = { owners: [
    { over_180_ratio: '0.2', under_90_ratio: '0.8' },
    { over_180_ratio: '0.1', under_90_ratio: '0.2' }
  ], sites: [] }
  const before = JSON.stringify(h.api.report.value)
  assert.equal(h.api.ratioBarWidth('0.2'), '20%')
  assert.equal(h.api.ratioBarWidth('0.1'), '10%')
  assert.equal(h.api.ratioBarWidth('0.9345'), '93.45%')
  assert.equal(h.api.ratioBarWidth('0.0197'), '1.97%')
  assert.equal(h.api.ratioBarWidth('0.0578'), '5.78%')
  assert.equal(h.api.ratioBarWidth('1'), '100%')
  assert.equal(h.api.ratioBarWidth('1.2'), '100%')
  assert.equal(h.api.formatPercent('0.1'), '10.00%')
  assert.equal(JSON.stringify(h.api.report.value), before)
  assert.equal((descriptor.template.content.match(/class="ratio-data-bar"/g) || []).length, 2)
  assert.match(source, /background: #f5a0ac/)
})

test('site bars keep a fixed scale on report changes; zero and missing values stay empty', () => {
  const h = harness()
  h.api.report.value = { owners: [{ over_180_ratio: '0.8' }], sites: [
    { over_180_ratio: '0.1', over_180_quantity_ratio: '0.2' },
    { over_180_ratio: '0.05', over_180_quantity_ratio: '0.1' }
  ] }
  assert.equal(h.api.ratioBarWidth('0.05'), '5%')
  assert.equal(h.api.ratioBarWidth('0.1'), '10%')
  for (const value of [null, undefined, '', 'invalid', Infinity, -1, 0]) {
    assert.equal(h.api.ratioBarWidth(value), '0%')
  }
  h.api.report.value.sites = [{ over_180_ratio: '0.05' }]
  assert.equal(h.api.ratioBarWidth('0.05'), '5%')
  h.api.report.value.sites = [{ over_180_ratio: '0' }, { over_180_ratio: null }]
  assert.equal(h.api.ratioBarWidth('0'), '0%')
  assert.equal(h.api.formatPercent('0'), '0.00%')
  assert.equal(h.api.formatPercent('invalid'), '--')
})

test('reads only the parent date range for both dimensions without writes', async () => {
  const h = harness({ read: async p => ({ data: { start_date: p.startDate, end_date: p.endDate,
    owners: [{ name: '张三' }], sites: [{ name: '德国' }] } }) })
  Object.assign(h.props, { site: '美国', sku: '10053', brand: ['DAS'], grade: ['--'] })
  await h.api.loadReport()
  assert.deepEqual(JSON.parse(JSON.stringify(h.calls)), [['read', { startDate: '2026-09-01', endDate: '2026-09-30' }]])
  assert.equal(h.api.report.value.owners[0].name, '张三')
  assert.equal(h.api.report.value.sites[0].name, '德国')
  assert.match(source, /:data="report\.owners \|\| \[\]"/)
  assert.match(source, /:data="report\.sites \|\| \[\]"/)
  assert.doesNotMatch(source, /<el-radio|<el-button|<el-form|dimension ===/)
  assert.doesNotMatch(source, /<el-date-picker|refreshReport|recalculateEbayInventoryAgeRatio/)
})
test('no independent latest-date fallback while waiting for parent date resolution', async () => {
  const h = harness()
  h.props.dateRange = []
  await h.api.loadReport()
  assert.equal(h.calls.length, 0)
  assert.equal(h.api.loading.value, false)
})
test('failed read preserves the last successful data without announcing success', async () => {
  const h = harness({ read: async () => { throw new Error('read failed') } })
  h.api.report.value = { owners: [{ name: 'old' }], sites: [] }
  await h.api.loadReport()
  assert.equal(h.api.report.value.owners[0].name, 'old')
  assert.equal(h.messages.length, 0)
})
