import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'
import * as Vue from 'vue'
import { renderToString } from '@vue/server-renderer'
import { parse, compileScript, compileTemplate } from '@vue/compiler-sfc'
import { compile } from '@vue/compiler-dom'

const file = new URL('../src/components/AmzOwnerSkuChart/index.vue', import.meta.url)
const source = fs.readFileSync(file, 'utf8')
const { descriptor, errors } = parse(source)
const { code } = compile(descriptor.template.content, { mode: 'function', prefixIdentifiers: true })
const render = new Function('Vue', code)(Vue)

async function html(summary, error = '', platform = 'amz') {
  const app = Vue.createSSRApp({ render, setup: () => ({
    summary, error, platform, loading: false, maxCount: 100, load() {},
    platformLabel: platform === 'ebay' ? 'EBAY' : 'AMAZON',
    statusField: platform === 'ebay' ? 'listing_status' : 'status',
    dedupDescription: platform === 'ebay' ? '按负责人及完整 MSKU 去重，同一MSKU跨店铺只计一次' : '按当月规则匹配负责人，再按负责人及完整 seller_sku 去重，同一负责人跨店铺只计一次；本地SKU仅用于品牌及OTH归属匹配',
    formatCount: value => Number(value).toLocaleString('zh-CN')
  }) })
  app.component('el-button', { setup: (_, { slots }) => () => Vue.h('button', slots.default?.()) })
  app.component('el-alert', { props: ['title'], setup: props => () => Vue.h('aside', props.title) })
  app.component('el-empty', { props: ['description'], setup: props => () => Vue.h('aside', props.description) })
  app.directive('loading', {})
  return renderToString(app)
}

test('chart compiles with explicit refresh and has no external chart dependency', () => {
  assert.deepEqual(errors, [])
  const script = compileScript(descriptor, { id: 'amz-owner-chart' })
  const template = compileTemplate({ source: descriptor.template.content, filename: file.pathname,
    id: 'amz-owner-chart', compilerOptions: { bindingMetadata: script.bindings } })
  assert.deepEqual(template.errors, [])
  assert.match(source, /if \(loading.value\) return/)
  assert.match(source, /summary.value = null/)
  assert.match(source, /onBeforeUnmount/)
  assert.doesNotMatch(source, /echarts|v-html/)
})

test('chart renders actual counts, proportional bars and unassigned color class', async () => {
  const output = await html({ state: 'READY', total: 150, owner_count: 1, rule_month: '2026-09', warnings: [],
    items: [{ principal_name: '负责人A', sku_count: 100 }, { principal_name: '未分配', sku_count: 50, unassigned: true }] })
  assert.match(output, /负责人A/)
  assert.match(output, /width:100%/)
  assert.match(output, /width:50%/)
  assert.match(output, /class="unassigned"/)
  assert.match(output, /SKU 合计/)
  assert.match(output, /完整 seller_sku/)
  assert.match(output, /status=1 且 is_delete=0（未删除）/)
  assert.match(output, /同一负责人跨店铺只计一次/)
  assert.doesNotMatch(output, /店铺 SKU 合计|跨店铺分别计数/)
  assert.match(source, /按负责人及完整 seller_sku 去重/)
  assert.match(output, /150/)
  assert.match(output, /排除PC及任意数字\+PC前缀/)
  assert.match(output, /class="chart-scroll" tabindex="0" role="region"/)
})

test('compact card keeps horizontal bars inside a keyboard accessible vertical scroller', () => {
  assert.match(source, /height: 360px/)
  assert.match(source, /\.chart-scroll \{[^}]*min-height: 0;[^}]*overflow-y: auto/)
  assert.match(source, /grid-template-columns: 48px minmax\(0, 1fr\) 43px/)
  assert.doesNotMatch(source, /class="rank"/)
})

test('missing rules and failed source never render a zero-count chart', async () => {
  for (const state of ['MISSING_RULES', 'SOURCE_NOT_READY']) {
    const output = await html({ state, message: '请检查数据', items: [], total: null })
    assert.match(output, /请检查数据/)
    assert.doesNotMatch(output, /bar-chart|SKU 合计/)
  }
  const output = await html(null, '加载失败')
  assert.match(output, /加载失败/)
  assert.doesNotMatch(output, /bar-chart/)
})

test('empty active listing set has an explicit empty state', async () => {
  assert.match(await html({ state: 'EMPTY', total: 0, owner_count: 0, items: [], warnings: [],
    message: '没有在售数据' }), /没有在售数据/)
})

test('configured zero-count owners render with a visible zero and no colored bar', async () => {
  for (const platform of ['amz', 'ebay']) {
    const output = await html({ state: 'EMPTY', total: 0, owner_count: 1, warnings: [],
      items: [{ principal_name: '张生敏', sku_count: 0, unassigned: false }] }, '', platform)
    assert.match(output, /张生敏/)
    assert.match(output, /class="bar-value">0<\/strong>/)
    assert.doesNotMatch(output, /class="bar"|NaN|Infinity/)
    assert.match(output, /class="bar-track"/)
  }
})

test('eBay mode shows its own source, status field and MSKU grain', async () => {
  const output = await html({ state: 'READY', total: 3, owner_count: 1, warnings: [],
    source_api: '/basicOpen/multiplatform/ebay/list', items: [{ principal_name: '方黎力', sku_count: 3 }] }, '', 'ebay')
  assert.match(output, /EBAY/)
  assert.match(output, /listing_status=1/)
  assert.doesNotMatch(output, /is_delete=0/)
  assert.match(output, /完整 MSKU/)
  assert.match(output, /排除PC及任意数字\+PC前缀/)
  assert.match(output, /同一MSKU跨店铺只计一次/)
  assert.doesNotMatch(output, /店铺 SKU 合计|跨店铺分别计数/)
  assert.match(source, /按负责人及完整 MSKU 去重，同一MSKU跨店铺只计一次/)
  assert.match(output, /basicOpen\/multiplatform\/ebay\/list/)
  assert.doesNotMatch(output, /AMAZON|erp\/sc\/data\/mws/)
  assert.match(source, /props.platform === 'ebay' \? getEbayOwnerSkuSummary\(\) : getAmzOwnerSkuSummary\(\)/)
})

test('Java proxy enforces the same permission and Python client uses protected route', () => {
  const controller = fs.readFileSync(new URL('../../RuoYi-Vue-springboot3/ruoyi-admin/src/main/java/com/ruoyi/web/controller/operation/AmzOwnerSkuController.java', import.meta.url), 'utf8')
  assert.match(controller, /@PreAuthorize\("@ss.hasPermi\('operations:amzReplenishment:list'\)"\)/)
  assert.match(controller, /@GetMapping\("\/summary"\)/)
  assert.doesNotMatch(controller, /@Anonymous/)
  const client = fs.readFileSync(new URL('../../RuoYi-Vue-springboot3/ruoyi-system/src/main/java/com/ruoyi/system/service/finance/PerformancePythonClient.java', import.meta.url), 'utf8')
  assert.match(client, /get\("\/amz-owner-sku\/summary", Map.of\(\), requestId\)/)
})
