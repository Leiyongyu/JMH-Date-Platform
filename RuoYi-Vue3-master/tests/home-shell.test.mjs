import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'
import * as Vue from 'vue'
import { renderToString } from '@vue/server-renderer'
import { parse, compileScript, compileTemplate } from '@vue/compiler-sfc'
import { compile } from '@vue/compiler-dom'

const file = new URL('../src/views/index.vue', import.meta.url)
const source = fs.readFileSync(file, 'utf8')
const { descriptor, errors } = parse(source)
const navSource = fs.readFileSync(new URL('../src/components/HomeDashboardNav/index.vue', import.meta.url), 'utf8')
const navTemplate = parse(navSource).descriptor.template.content
const navRender = new Function('Vue', compile(navTemplate, { mode: 'function', prefixIdentifiers: true }).code)(Vue)
const HomeDashboardNav = { props: ['active', 'salesVisible'], render: navRender }
const RouterLink = { props: ['to'], setup: (props, { slots }) => () => Vue.h('a', { href: props.to }, slots.default?.()) }
function registerNavigation(app) {
  app.component('HomeDashboardNav', HomeDashboardNav)
  app.component('router-link', RouterLink)
}

test('home compiles and gates the new dashboard by existing AMZ permission', () => {
  assert.deepEqual(errors, [])
  const script = compileScript(descriptor, { id: 'home-shell' })
  assert.match(script.content, /name: 'Index'/)
  const template = compileTemplate({ source: descriptor.template.content, filename: file.pathname,
    id: 'home-shell', compilerOptions: { bindingMetadata: script.bindings } })
  assert.deepEqual(template.errors, [])
  assert.match(source, /operations:amzReplenishment:list/)
  assert.match(source, /operations:ebayReplenishmentV2:list/)
  assert.match(source, /filter\(platform => checkPermi\(\[platform.permission\]\)\)/)
  assert.match(source, /v-for="platform in availablePlatforms" :key="platform.value" :platform="platform.value"/)
  assert.doesNotMatch(source, /activePlatform|el-radio|platform-switch/)
  assert.match(source, /grid-template-columns: repeat\(4, minmax\(0, 1fr\)\)/)
  assert.doesNotMatch(source, /:only-child/)
  assert.doesNotMatch(source, /InventoryCostTrendChart|loadTrend/)
})

test('unauthorized home does not render the chart or fetch its data', async () => {
  const { code } = compile(descriptor.template.content, { mode: 'function', prefixIdentifiers: true })
  const render = new Function('Vue', code)(Vue)
  const app = Vue.createSSRApp({ name: 'Index', setup: () => ({ availablePlatforms: [], canViewSales: false }), render })
  registerNavigation(app)
  app.component('SalesDashboard', { setup: () => () => { throw new Error('Unauthorized sales chart mounted') } })
  app.component('AmzOwnerSkuChart', { setup: () => () => { throw new Error('Unauthorized chart mounted') } })
  app.component('el-empty', { setup: () => () => Vue.h('aside', '暂无可查看的首页看板') })
  const html = await renderToString(app)
  assert.match(html, /class="app-container home"/)
  assert.match(html, /aria-label="首页"/)
  assert.doesNotMatch(html, /amz-owner-sku-chart|月度库存|el-select|el-card/)
})

test('all authorized platforms mount simultaneously; one permission mounts only its own chart', async () => {
  const { code } = compile(descriptor.template.content, { mode: 'function', prefixIdentifiers: true })
  const render = new Function('Vue', code)(Vue)
  for (const platforms of [['amz', 'ebay'], ['amz'], ['ebay']]) {
    const mounted = []
    const app = Vue.createSSRApp({ render, setup: () => ({ availablePlatforms: platforms.map(value => ({ value })), canViewSales: false }) })
    registerNavigation(app)
    app.component('SalesDashboard', { setup: () => () => Vue.h('section') })
    app.component('AmzOwnerSkuChart', { props: ['platform'], setup: props => {
      mounted.push(props.platform)
      return () => Vue.h('section', { 'data-platform': props.platform }, props.platform)
    } })
    app.component('el-empty', { setup: () => () => Vue.h('aside') })
    await renderToString(app)
    assert.deepEqual(mounted, platforms)
  }
})

test('pinned home route and monthly inventory business APIs remain', () => {
  const router = fs.readFileSync(new URL('../src/router/index.js', import.meta.url), 'utf8')
  assert.match(router, /path: '\/index'[\s\S]*?name: 'Index'[\s\S]*?affix: true/)
  const api = fs.readFileSync(new URL('../src/api/finance/monthlyInventoryReport.js', import.meta.url), 'utf8')
  for (const name of ['getMonthlyInventorySummary', 'getMonthlyInventoryDimensionSummary',
    'exportMonthlyInventoryReport', 'rebuildMonthlyInventoryReport']) {
    assert.ok(api.includes(`export function ${name}(`))
  }
  assert.doesNotMatch(api, /getMonthlyInventoryCostTrend|cost-trend/)
})

test('home groups existing reports as product analysis and provides a sales page switch, not a BI card', async () => {
  const { code } = compile(descriptor.template.content, { mode: 'function', prefixIdentifiers: true })
  const render = new Function('Vue', code)(Vue)
  const app = Vue.createSSRApp({ render, setup: () => ({ availablePlatforms: [], canViewSales: true }) })
  registerNavigation(app)
  app.component('SalesDashboard', { setup: () => { throw new Error('Home must not mount sales BI') } })
  for (const name of ['AmzOwnerSkuChart', 'ListingPriceTierChart', 'ProductNatureChart', 'el-empty']) {
    app.component(name, { render: () => null })
  }
  const html = await renderToString(app)
  assert.match(html, /href="\/sales-dashboard\/index"/)
  assert.match(html, /aria-current="page">商品分析/)
  assert.match(html, />销售看板<\/a>/)
  assert.doesNotMatch(html, /sales-entry|进入看板/)
  assert.match(source, /section v-if="availablePlatforms.length" aria-label="商品分析"/)
})

test('sales page highlights sales and keeps the product analysis return button; permission hides sales button', async () => {
  for (const allowed of [true, false]) {
    const app = Vue.createSSRApp({ render: () => Vue.h(HomeDashboardNav, { active: 'sales', salesVisible: allowed }) })
    registerNavigation(app)
    const html = await renderToString(app)
    assert.match(html, /href="\/index"/)
    if (allowed) assert.match(html, /aria-current="page">销售看板/)
    else assert.doesNotMatch(html, /sales-dashboard\/index/)
  }
})

test('unused chart and Java trend-query chain are removed, report endpoints remain', () => {
  for (const path of [
    '../src/components/InventoryCostTrendChart/index.vue',
    '../../RuoYi-Vue-springboot3/ruoyi-system/src/main/java/com/ruoyi/system/service/finance/MonthlyInventoryDashboardService.java',
    '../../RuoYi-Vue-springboot3/ruoyi-system/src/main/java/com/ruoyi/system/mapper/finance/MonthlyInventoryDashboardMapper.java',
    '../../RuoYi-Vue-springboot3/ruoyi-system/src/main/resources/mapper/finance/MonthlyInventoryDashboardMapper.xml'
  ]) assert.equal(fs.existsSync(new URL(path, import.meta.url)), false)
  const controller = fs.readFileSync(new URL('../../RuoYi-Vue-springboot3/ruoyi-admin/src/main/java/com/ruoyi/web/controller/finance/MonthlyInventoryReportController.java', import.meta.url), 'utf8')
  assert.doesNotMatch(controller, /MonthlyInventoryDashboardService|dashboardService|cost-trend/)
  for (const route of ['/summary', '/dimension-summary', '/export', '/months']) {
    assert.ok(controller.includes(`@GetMapping("${route}")`))
  }
})
