import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'
import { parse, compileScript, compileTemplate } from '@vue/compiler-sfc'
import { NATURES, chartOption, rangeError, shiftMonth, formatNumber, segmentOptions, segmentItems } from '../src/components/ProductNatureChart/presentation.js'

test('charts, tooltips and shared table columns display only new and old, even for older snapshots', () => {
  const row = { stat_month: '2026-09', state: 'READY', rule_version: 'v1', sku_count: 10,
    counts: { NEW: 2, OLD: 5, UNKNOWN: 1, CONFLICT: 2 },
    percentages: { NEW: '20.00', OLD: '50.00', UNKNOWN: '10.00', CONFLICT: '20.00' } }
  const before = structuredClone(row)
  assert.deepEqual(NATURES.map(n => n.key), ['NEW', 'OLD'])
  for (const mode of ['count', 'percent']) {
    const option = chartOption([row], mode)
    assert.deepEqual(option.legend.data, ['新品', '老品'])
    assert.deepEqual(option.series.map(s => s.name), ['新品', '老品'])
    assert.doesNotMatch(option.tooltip.formatter([{ dataIndex: 0 }]), /未知|冲突/)
  }
  assert.deepEqual(row, before)
})

test('month range permits one to twelve months including endpoints', () => {
  assert.equal(rangeError(['2025-10','2026-09'],'2026-09'),'')
  assert.equal(rangeError(['2026-09','2026-09'],'2026-09'),'')
  for (const range of [null, ['2025-09','2026-09'], ['2026-09','2026-08'], ['2026-10','2026-10'], ['2026-9','2026-09']]) assert.ok(rangeError(range,'2026-09'))
  assert.equal(shiftMonth('2026-01',-1),'2025-12')
})
test('line chart preserves zero and missing months, splits versions, and keeps percent units', () => {
  const items = [
    {stat_month:'2026-06',state:'READY',rule_version:'v1',counts:{NEW:0},percentages:{NEW:'0.00'}},
    {stat_month:'2026-07',state:'NO_SNAPSHOT'},
    {stat_month:'2026-08',state:'READY',rule_version:'v2',counts:{NEW:3},percentages:{NEW:'12.30'}},
    {stat_month:'2026-09',state:'READY',rule_version:'v2',provisional:true,sku_count:10,counts:{NEW:4},percentages:{NEW:'40.00'}}
  ]
  const option=chartOption(items)
  assert.deepEqual(option.series[0].data,[0,null,null,null])
  assert.deepEqual(option.series[1].data,[null,null,3,4])
  assert.ok(option.series.every(s=>s.connectNulls===false))
  assert.equal(chartOption(items,'percent').series[1].data[3],'40.00')
  assert.match(option.tooltip.formatter([{dataIndex:3}]),/当月暂计/)
  assert.match(option.tooltip.formatter([{dataIndex:1}]),/无历史快照/)
  assert.equal(formatNumber(null),'--'); assert.equal(formatNumber(0),'0')
})
test('Vue chart compiles; homepage puts nature after price row in two columns', () => {
  const source=fs.readFileSync(new URL('../src/components/ProductNatureChart/index.vue',import.meta.url),'utf8')
  const {descriptor,errors}=parse(source); assert.deepEqual(errors,[])
  const script=compileScript(descriptor,{id:'nature'})
  assert.deepEqual(compileTemplate({source:descriptor.template.content,filename:'index.vue',id:'nature',compilerOptions:{bindingMetadata:script.bindings}}).errors,[])
  assert.match(source,/type="monthrange"/); assert.match(source,/value-format="YYYY-MM"/)
  assert.match(source,/version !== requestVersion/); assert.match(source,/observer\?\.disconnect/); assert.match(source,/chart\?\.dispose/)
  const home=fs.readFileSync(new URL('../src/views/index.vue',import.meta.url),'utf8')
  assert.match(home,/AmzOwnerSkuChart[\s\S]*class="price-dashboards"[\s\S]*class="nature-dashboards"[\s\S]*ProductNatureChart/)
  assert.match(home,/\.nature-dashboards \{ display: grid; grid-template-columns: repeat\(2,/)
  assert.match(source,/v-model="segment"/)
  assert.match(home,/repeat\(4, minmax\(0, 1fr\)\)/)
})

test('region/site filter never reuses platform totals or fabricates legacy segment values', () => {
  const rows=[{stat_month:'2026-08',state:'READY',sku_count:20},
    {stat_month:'2026-09',state:'READY',sku_count:20,segments:[{segment_key:'美国',segment_label:'美国',sku_count:7,counts:{NEW:2,OLD:5},percentages:{NEW:'28.57'}}]}]
  assert.equal(segmentItems(rows,'美国')[0].state,'NO_SEGMENT_SNAPSHOT')
  assert.equal(segmentItems(rows,'美国')[0].sku_count,null)
  assert.equal(segmentItems(rows,'美国')[1].sku_count,7)
  assert.equal(segmentItems(rows,'英国')[1].sku_count,0)
  assert.equal(segmentItems(rows,'英国')[1].percentages.NEW,null)
  assert.deepEqual(segmentOptions('amz',[]).map(o=>o.value),['US','EU'])
  assert.ok(segmentOptions('ebay',[{segments:[{segment_key:'法国',segment_label:'法国'}]}]).some(o=>o.value==='法国'))
})
