import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'
import vm from 'node:vm'
import { reactive, ref } from 'vue'
import { parse, compileScript, compileTemplate } from '@vue/compiler-sfc'

const pageFile = new URL('../src/views/operations/ebay/priceAnalysis/index.vue', import.meta.url)
const pageSource = fs.readFileSync(pageFile, 'utf8')
const apiSource = fs.readFileSync(
  new URL('../src/api/operations/ebayPriceAnalysis.js', import.meta.url),
  'utf8'
)

const parsed = parse(pageSource, { filename: pageFile.pathname })
assert.deepEqual(parsed.errors, [])
const descriptor = parsed.descriptor
const script = compileScript(descriptor, { id: 'ebay-price-analysis' })
const setupSource = descriptor.scriptSetup.content
const statements = script.scriptSetupAst
const styleSource = descriptor.styles.map(style => style.content).join('\n')

// 从真实的 setup 源码里取声明来跑，避免测试自带一份会和页面走偏的副本。
function declaration(name) {
  const node = statements.find(item => (
    (item.type === 'FunctionDeclaration' && item.id?.name === name)
    || (item.type === 'VariableDeclaration'
      && item.declarations.some(entry => entry.id.type === 'Identifier' && entry.id.name === name))
  ))
  assert.ok(node, `missing declaration: ${name}`)
  return setupSource.slice(node.start, node.end)
}

function createHarness() {
  const query = reactive({
    statDate: undefined,
    sites: [],
    accounts: [],
    status: undefined,
    keyword: undefined,
    dimension: 'sku',
    mode: 'detail',
    pageNum: 3,
    pageSize: 50,
    sortBy: undefined,
    sortOrder: undefined
  })
  const calls = { query: 0, detail: 0, scrolled: 0 }
  const context = vm.createContext({
    query,
    activeRiskKey: ref(''),
    loading: ref(false),
    exporting: ref(false),
    handleQuery: () => {
      calls.query += 1
      query.pageNum = 1
      return Promise.resolve()
    },
    loadDetail: () => {
      calls.detail += 1
      return Promise.resolve()
    },
    scrollToDetail: () => {
      calls.scrolled += 1
    },
    checkPermi: () => true,
    ElMessage: { warning: () => {} },
    exportEbayPriceAnalysis: () => Promise.resolve()
  })
  vm.runInContext([
    declaration('KPI_STATUS'),
    declaration('csv'),
    declaration('toArray'),
    declaration('kpiStatus'),
    declaration('buildFilterParams'),
    declaration('buildOverviewParams'),
    declaration('buildDetailParams'),
    declaration('applyStatusFilter'),
    declaration('handleKpiClick'),
    declaration('applyRiskFilter'),
    declaration('toggleAccount'),
    declaration('handleModeChange'),
    declaration('handleSortChange')
  ].join('\n'), context)
  return { query, calls, api: context }
}

test('page and its template compile', () => {
  assert.equal(script.scriptSetupAst.length > 0, true)
  const template = compileTemplate({
    source: descriptor.template.content,
    filename: pageFile.pathname,
    id: 'ebay-price-analysis',
    compilerOptions: { bindingMetadata: script.bindings }
  })
  assert.deepEqual(template.errors, [])
})

test('page never injects raw html', () => {
  assert.doesNotMatch(pageSource, /v-html/)
  // 图表 tooltip 里拼了 HTML，listing 标题和 SKU 是外部数据，必须转义后再拼。
  assert.match(setupSource, /function escapeText/)
  for (const formatter of setupSource.match(/formatter: params => \{[^]*?\n {6}\}/g) || []) {
    if (!formatter.includes('<b>')) continue
    assert.match(formatter, /escapeText\(/)
  }
})

test('export button is gated by permission twice', () => {
  assert.match(pageSource, /v-hasPermi="\['operations:ebayPriceAnalysis:export'\]"/)
  assert.match(setupSource, /checkPermi\(\['operations:ebayPriceAnalysis:export'\]\)/)
})

test('export without permission warns and sends nothing', async () => {
  let sent = 0
  let warned = 0
  const context = vm.createContext({
    loading: ref(false),
    exporting: ref(false),
    checkPermi: () => false,
    ElMessage: { warning: () => { warned += 1 } },
    exportEbayPriceAnalysis: () => { sent += 1 },
    buildDetailParams: () => ({ pageNum: 1, pageSize: 50 })
  })
  vm.runInContext(declaration('handleExport'), context)
  await context.handleExport()
  assert.equal(warned, 1)
  assert.equal(sent, 0)
})

test('export drops pagination so it covers the whole filtered set', async () => {
  const sent = []
  const context = vm.createContext({
    loading: ref(false),
    exporting: ref(false),
    checkPermi: () => true,
    ElMessage: { warning: () => {} },
    exportEbayPriceAnalysis: params => {
      sent.push(params)
      return Promise.resolve()
    },
    buildDetailParams: () => ({ status: '超卖风险', mode: 'detail', pageNum: 2, pageSize: 50 })
  })
  vm.runInContext(declaration('handleExport'), context)
  await context.handleExport()
  assert.equal(sent.length, 1)
  assert.equal(sent[0].status, '超卖风险')
  assert.equal(Object.hasOwn(sent[0], 'pageNum'), false)
  assert.equal(Object.hasOwn(sent[0], 'pageSize'), false)
})

test('filters travel as csv and empty ones are not sent', () => {
  const { query, api } = createHarness()
  query.sites = ['DE', 'UK']
  query.accounts = [' aplus-shop ', '', 'bparts']
  query.status = '未匹配'
  query.keyword = '  TYT-90245  '
  const params = api.buildDetailParams()
  assert.equal(params.sites, 'DE,UK')
  assert.equal(params.accounts, 'aplus-shop,bparts')
  assert.equal(params.status, '未匹配')
  assert.equal(params.keyword, 'TYT-90245')
  assert.equal(params.mode, 'detail')
  assert.equal(params.statDate, undefined)
  assert.equal(params.sortBy, undefined)

  query.sites = []
  query.accounts = []
  query.status = undefined
  query.keyword = ''
  const empty = api.buildDetailParams()
  for (const key of ['sites', 'accounts', 'status', 'keyword']) {
    assert.equal(empty[key], undefined)
  }
  // 象限图的聚合维度只走 overview，明细不带它。
  assert.equal(api.buildOverviewParams().dimension, 'sku')
  assert.equal(Object.hasOwn(api.buildDetailParams(), 'dimension'), false)
})

test('status dropdown offers all six backend statuses, unmatched included', () => {
  const options = declaration('statusOptions')
  for (const status of ['未匹配', '超卖风险', '断货', '待补货', '滞销', '健康']) {
    assert.ok(options.includes(status), `missing status option: ${status}`)
  }
  // US 站约 18% 的 listing 关联不到库存，这部分必须能单独筛出来看。
  assert.match(options, /'未匹配'/)
})

test('status filter toggles and always restarts from the first page', async () => {
  const { query, calls, api } = createHarness()
  await api.applyStatusFilter('超卖风险')
  assert.equal(query.status, '超卖风险')
  assert.equal(query.pageNum, 1)
  assert.equal(calls.query, 1)

  query.pageNum = 4
  await api.applyStatusFilter('超卖风险')
  assert.equal(query.status, undefined)
  assert.equal(query.pageNum, 1)
  assert.equal(calls.query, 2)
})

test('unmatched kpi card filters the detail by that status', async () => {
  const { query, api } = createHarness()
  assert.equal(api.kpiStatus({ key: 'listing_count' }), '')
  assert.equal(api.handleKpiClick({ key: 'listing_count' }), undefined)
  assert.equal(query.status, undefined)

  await api.handleKpiClick({ key: 'unmatched_count' })
  assert.equal(query.status, '未匹配')
  await api.handleKpiClick({ key: 'oversell_count' })
  assert.equal(query.status, '超卖风险')
})

test('risk list applies only the filter keys the page knows', async () => {
  const { query, calls, api } = createHarness()
  await api.applyRiskFilter({
    key: 'oversell',
    label: '超卖风险',
    filter: { status: '超卖风险', accounts: 'aplus-shop, bparts', sites: ['DE'] }
  })
  assert.equal(query.status, '超卖风险')
  assert.deepEqual([...query.accounts], ['aplus-shop', 'bparts'])
  assert.deepEqual([...query.sites], ['DE'])
  assert.equal(query.pageNum, 1)
  assert.equal(calls.query, 1)
  assert.equal(calls.scrolled, 1)

  // 后端给的别的键不认，也不能把已有筛选清掉。
  await api.applyRiskFilter({ key: 'unknown', filter: { mystery: 1 } })
  assert.equal(query.status, '超卖风险')
  assert.equal(api.applyRiskFilter({ key: 'broken' }), undefined)
  assert.equal(calls.query, 2)
})

test('store chips toggle the account filter in both directions', async () => {
  const { query, api } = createHarness()
  await api.toggleAccount('aplus-shop')
  assert.deepEqual([...query.accounts], ['aplus-shop'])
  await api.toggleAccount('bparts')
  assert.deepEqual([...query.accounts], ['aplus-shop', 'bparts'])
  await api.toggleAccount('aplus-shop')
  assert.deepEqual([...query.accounts], ['bparts'])
})

test('view switch and sorting reload only the detail table', async () => {
  const { query, calls, api } = createHarness()
  query.mode = 'summary'
  await api.handleModeChange()
  assert.equal(query.pageNum, 1)
  assert.equal(calls.detail, 1)
  assert.equal(calls.query, 0)

  await api.handleSortChange({ prop: 'stock_gap', order: 'ascending' })
  assert.equal(query.sortBy, 'stock_gap')
  assert.equal(query.sortOrder, 'asc')
  await api.handleSortChange({ prop: 'stock_gap', order: null })
  assert.equal(query.sortBy, undefined)
  assert.equal(query.sortOrder, undefined)
  assert.equal(calls.detail, 3)
})

test('numbers are rendered from the response, never recomputed on the page', () => {
  // 状态、缺口、覆盖天数都由后端落库算好，页面不许再推一遍。
  assert.match(setupSource, /overview\.value = response\.data \|\| \{\}/)
  assert.match(setupSource, /kpiCards = computed\(\(\) => \(Array\.isArray\(overview\.value\.kpis\)/)
  assert.doesNotMatch(setupSource, /cover_days\s*=|stock_gap\s*=[^=]/)
  assert.doesNotMatch(setupSource, /overseas_sellable\s*[-+]\s*\w*ebay/i)
  assert.doesNotMatch(setupSource, /'超卖风险'\s*:\s*\w+\s*>/)
})

test('sampled scatter is labelled so it is not read as the full set', () => {
  assert.match(pageSource, /overview\.scatter_sampled/)
  assert.match(pageSource, /已抽样/)
  assert.match(pageSource, /后端已抽样，图上不是全量数据/)
  // 汇率缺失画不出来的点也要交代清楚，不能静默丢掉。
  assert.match(pageSource, /scatterSkipped/)
  assert.match(setupSource, /scatter_median/)
})

test('page keeps the fixed wording of the data-definition footer', () => {
  for (const line of [
    'eBay 售价与可售量为在售刊登每周快照（每周一更新），快照日期见页头',
    '海外仓库存为谷仓区域仓接口每周快照（DE / UK / 美东 USEA / 美西 USWE，美国两仓合计；捷克 CZ 暂不纳入）',
    '成都中转仓库存仍为领星周快照',
    '海外仓按「站点 + 去掉 SKU 第一段（品牌前缀，谷仓侧为 JMH）」匹配',
    '覆盖天数 = 谷仓可售 ÷ 近 7 日日均销量',
    '售价按站点币种和领星月度汇率折算 USD，汇率缺失时不折算',
    '采购成本取订单文件中的真实采购成本，未参与售价估算',
    '未关联到库存的 listing 计入「未匹配」，不计入库存缺口与超卖判断'
  ]) {
    assert.ok(pageSource.includes(line), `missing data-definition line: ${line}`)
  }
  // 两个数据源都停摆过，快照日期必须明确，不能被当成实时数据。
  assert.match(pageSource, /快照日期/)
  assert.match(pageSource, /不是实时库存/)
})

test('data-definition wording follows the weekly goodcang snapshot', () => {
  // 海外仓改用谷仓区域仓接口、eBay 与谷仓都改为每周一同步，页面不能再写旧口径。
  for (const phrase of ['谷仓区域仓接口每周快照', '每周一更新', '美国两仓合计', '捷克 CZ 暂不纳入', '成都中转仓库存仍为领星周快照', '去掉 SKU 第一段']) {
    assert.ok(pageSource.includes(phrase), `missing weekly wording: ${phrase}`)
  }
  assert.doesNotMatch(pageSource, /wid 1870[0-2]|wid 18699|领星周快照的海外仓/)
  assert.doesNotMatch(pageSource, /每天|每日/)
})

test('columns use the shared column config and drop the store column when summarised', () => {
  assert.match(setupSource, /useColumnConfig\(\s*'operations:ebay:priceAnalysis'/)
  assert.match(setupSource, /const columnDefs = \[/)
  assert.match(setupSource, /tableColumns = computed\(\(\) => visibleColumns\.value\.filter/)
  assert.match(setupSource, /col\.detailOnly && query\.mode === 'summary'/)
  assert.match(setupSource, /key: 'seller_account'[^}]*detailOnly: true/)
  // 导出列由角色权限决定，页面的隐藏列不参与。
  assert.doesNotMatch(pageSource, /exportColumn:/)
})

test('charts reuse the project echarts setup and add no new dependency', () => {
  assert.match(setupSource, /import \* as echarts from 'echarts'/)
  assert.equal((setupSource.match(/^import /gm) || []).every(line => !/chart\.js|d3|highcharts|vue-echarts/.test(line)), true)
  assert.match(setupSource, /storeChart \|\|= echarts\.init/)
  assert.match(setupSource, /scatterChart \|\|= echarts\.init/)
  assert.match(setupSource, /gapChart \|\|= echarts\.init/)
  // 点柱体筛店铺，离开页面要把实例释放掉。
  assert.match(setupSource, /storeChart\.on\('click'/)
  assert.match(setupSource, /onBeforeUnmount\(\(\) => \{/)
  assert.match(setupSource, /storeChart\?\.dispose\(\)/)
})

test('layout holds together at phone width without sideways scrolling', () => {
  assert.match(styleSource, /@media \(max-width: 768px\)/)
  assert.match(styleSource, /grid-template-columns: repeat\(auto-fit, minmax\(150px, 1fr\)\)/)
  assert.match(styleSource, /@media \(max-width: 992px\)[^]*?\.chart-grid \{\s*grid-template-columns: 1fr;/)
  // 固定宽度的筛选控件在窄屏要放开，否则一行撑出横向滚动条。
  assert.match(styleSource, /\.filter-control,\s*\n\s*\.filter-control--status,[^]*?width: 100%;/)
  // 手机 375px 减掉 app-container 的左右内边距只剩 335px 左右，
  // 任何网格轨道或固定宽度都不许超过这个值，否则整页会横向溢出。
  const wideTracks = []
  for (const match of styleSource.matchAll(/(?:minmax\(|min-width:\s*)(\d+)px/g)) {
    if (Number(match[1]) > 335) wideTracks.push(match[0])
  }
  assert.deepEqual(wideTracks, [])
})

test('api calls the erp proxy routes with a timeout fit for the aggregation', () => {
  assert.match(apiSource, /const base = '\/operations\/ebay\/price-analysis'/)
  assert.match(apiSource, /export function getEbayPriceAnalysisOverview[^]*?\$\{base\}\/overview/)
  assert.match(apiSource, /export function listEbayPriceAnalysisDetail[^]*?\$\{base\}\/detail/)
  assert.match(apiSource, /export function exportEbayPriceAnalysis[^]*?download\(`\$\{base\}\/export`/)
  assert.match(apiSource, /LONG_TIMEOUT = 120000/)
})

test('header has a single refresh button that reloads the page with the jmh-refresh icon', () => {
  const head = descriptor.template.content.match(/<div class="head-acts">[^]*?<\/el-tooltip>/)[0]
  assert.equal((head.match(/刷新/g) || []).length, 1)
  assert.match(head, /<el-button :disabled="loading" @click="handleQuery">\s*<svg-icon icon-class="jmh-refresh" class="report-icon" :class="\{ spinning: loading \}" \/>刷新/)
  assert.match(head, /icon-class="jmh-export"/)
  // 导出按钮沿用全站 warning plain 的橙色约定。
  assert.match(head, /<el-button\s+type="warning"\s+plain[^>]*@click="handleExport"/)
  // 不再用 Element 自带图标，也不再有只登记任务、不刷数据的「刷新数据源」。
  assert.doesNotMatch(head, /\sicon="/)
  assert.doesNotMatch(pageSource, /刷新数据源|handleRefreshSource|operations:ebayPriceAnalysis:refresh/)
  assert.doesNotMatch(setupSource, /refreshEbayPriceAnalysis/)
  assert.doesNotMatch(apiSource, /refreshEbayPriceAnalysis|\/refresh`/)
  assert.match(styleSource, /\.report-icon\.spinning \{\s*animation: report-icon-spin/)
  // 带文字的按钮里图标跟随文字色（currentColor），不写死颜色。
  const iconRule = styleSource.match(/\.report-icon \{[^}]*\}/)[0]
  assert.doesNotMatch(iconRule, /color:/)
})
