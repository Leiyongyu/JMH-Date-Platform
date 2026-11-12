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
const templateSource = descriptor.template.content

// vm 里造出来的对象原型不是本进程的 Object，比较前先转成普通 JSON。
const plain = value => JSON.parse(JSON.stringify(value))

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
function columnKeys(name) {
  return [...declaration(name).matchAll(/key: '([a-z_]+)'/g)].map(match => match[1])
}

// ===== 按契约字段造的 mock：未匹配原因这会儿后端还没有 =====
// 后端这一轮不删字段，site_oversell / out_of_stock_listed / status 等照常返回，页面不用它们。
const MOCK_STORES = {
  stat_date: '2026-11-10',
  refreshed_at: '2026-11-10 04:41:02',
  rows: [
    {
      seller_account: 'aplus-shop', site: 'DE', site_name: '德国', listing_count: 981, sku_count: 960,
      ebay_available: 2140, out_of_stock_listed: 37, site_oversell_sku_count: 12, unmatched_count: 21
    },
    {
      seller_account: 'bparts', site: 'DE', site_name: '德国', listing_count: 410, sku_count: 402,
      ebay_available: 880, out_of_stock_listed: 0, site_oversell_sku_count: 3, unmatched_count: 0
    }
  ]
}
const MOCK_DETAIL = {
  stat_date: '2026-11-10',
  refreshed_at: '2026-11-10 04:41:02',
  total: 2,
  rows: [
    {
      seller_account: 'aplus-shop', site: 'DE', site_name: '德国', item_id: '1001', sku: 'TYT-90245-0772',
      title: 'Brake pad', currency: 'EUR', current_price: 52.9, price_usd: 58.2, ebay_quantity_available: 36,
      overseas_sellable: 20, chengdu_sellable: 5, overseas_in_transit: 0, site_store_count: 3,
      site_ebay_available_total: 58, inventory_matched: 1, unmatched_reason: null, unmatched_reason_text: null,
      site_oversell: 1, out_of_stock_listed: 0, status: '超卖风险'
    },
    {
      seller_account: 'aplus-shop', site: 'DE', site_name: '德国', item_id: '1009', sku: 'TYT-90245-0772-SY',
      title: 'Brake pad', currency: 'EUR', current_price: 49.9, price_usd: 54.9, ebay_quantity_available: 3,
      overseas_sellable: null, chengdu_sellable: null, inventory_matched: 0, unmatched_reason: 'SKU_SUFFIX',
      unmatched_reason_text: 'SKU 带后缀「-SY」，去掉后谷仓 DE 有此商品', status: '未匹配'
    }
  ]
}
const MOCK_SUMMARY = {
  stat_date: '2026-11-10',
  refreshed_at: '2026-11-10 04:41:02',
  total: 1,
  rows: [{
    site: 'DE', site_name: '德国', sku: 'TYT-90245-0772', store_count: 3, ebay_quantity_available: 58,
    overseas_sellable: 20, chengdu_sellable: 5, price_usd_min: 51.75, price_usd_max: 64.1,
    site_oversell: true, statuses: '超卖风险,健康', unmatched_reason_text: null
  }]
}
const MOCK_OWNERS = {
  stat_date: '2026-11-10',
  refreshed_at: '2026-11-10 04:41:02',
  rows: [
    {
      owner_name: '方黎力', sku_count: 722, listing_count: 5101, store_count: 37, ebay_available: 109316,
      inventory_qty: 10742, inventory_value_cny: 960394.47, value_missing_sku_count: 119, unmatched_sku_count: 168,
      sales_qty_7d: 0, sales_qty_30d: 0
    },
    {
      owner_name: '杨萍', sku_count: 605, listing_count: 5820, store_count: 36, ebay_available: 73800,
      inventory_qty: 6335, inventory_value_cny: 852731.17, value_missing_sku_count: 0, unmatched_sku_count: 0,
      sales_qty_7d: 3, sales_qty_30d: 12
    }
  ]
}
const MOCK_SKU_LISTINGS = {
  sku: 'TYT-90245-0772',
  title: 'Brake pad',
  image_url: 'https://example.invalid/a.jpg',
  stat_date: '2026-11-10',
  refreshed_at: '2026-11-10 04:41:02',
  listings: [
    { seller_account: 'bparts', site: 'DE', site_name: '德国', item_id: '1002', price_usd: 51.75, ebay_quantity_available: 10 },
    { seller_account: 'aplus-shop', site: 'DE', site_name: '德国', item_id: '1001', price_usd: 58.2, ebay_quantity_available: 36 },
    {
      seller_account: 'aplus-shop', site: 'FR', site_name: '法国', item_id: '3001', price_usd: 61, ebay_quantity_available: 1,
      unmatched_reason: 'SITE_UNMAPPED', unmatched_reason_text: 'FR 站没有对应仓库'
    }
  ],
  sites: [
    { site: 'DE', site_name: '德国', overseas_sellable: 20, chengdu_sellable: 5, ebay_available_total: 46, store_count: 2, site_oversell: true },
    { site: 'FR', site_name: '法国', overseas_sellable: null, chengdu_sellable: null, ebay_available_total: 1, store_count: 1 }
  ]
}

const PAGE_FUNCTIONS = [
  'displayValue', 'integer', 'decimal', 'isTrue', 'unmatchedReason', 'cellText', 'cellClass', 'csv', 'flag',
  'storeKey', 'skuRowKey', 'buildFilterParams', 'buildStoreParams', 'buildStoreDetailParams', 'buildSkuParams',
  'buildExportParams', 'applySnapshot', 'rememberAccounts', 'filterVersion', 'storesSeq', 'detailSeq',
  'skuSeq', 'loadStores', 'loadStoreDetail', 'loadSkuRows', 'loadActiveTab', 'clearSkuListings',
  'resetPages', 'handleQuery', 'handleListFilter', 'resetQuery', 'handleTabChange', 'selectStore',
  'focusStore', 'sortState', 'handleDetailSort', 'handleSkuSort', 'storeRowClass', 'compareSiteRowClass',
  'compareListingRowClass', 'EMPTY_LISTING', 'skuListing', 'ensureSkuListings', 'openCompare',
  'handleSkuExpand', 'handleExport', 'OWNER_SKU_SORT', 'ownersSeq', 'ownerSkuSeq', 'buildOwnerSkuParams',
  'loadOwners', 'loadOwnerSkus', 'selectOwner', 'focusOwner', 'handleOwnerSkuSort', 'ownerRowClass'
]

function createHarness(api = {}) {
  const state = {
    query: reactive({ sites: [], accounts: [], keyword: undefined, onlyUnmatched: false }),
    detailPage: reactive({ pageNum: 3, pageSize: 50, sortBy: undefined, sortOrder: undefined }),
    skuPage: reactive({ pageNum: 2, pageSize: 50, sortBy: undefined, sortOrder: undefined }),
    ownerSkuPage: reactive({ pageNum: 4, pageSize: 50, sortBy: 'inventory_value_cny', sortOrder: 'desc' }),
    ownerRows: ref([]),
    selectedOwner: ref(null),
    ownerSkuRows: ref([]),
    ownerSkuTotal: ref(0),
    ownersLoading: ref(false),
    ownerSkuLoading: ref(false),
    snapshot: reactive({ stat_date: undefined, refreshed_at: undefined }),
    stores: ref([]),
    selectedStore: ref(null),
    detailRows: ref([]),
    detailTotal: ref(0),
    skuRows: ref([]),
    skuTotal: ref(0),
    knownAccounts: ref([]),
    skuListings: reactive({}),
    compareDrawer: reactive({ visible: false, sku: '', origin: null }),
    activeTab: ref('store'),
    storesLoading: ref(false),
    detailLoading: ref(false),
    skuLoading: ref(false),
    exporting: ref(false),
    loading: ref(false),
    loadedVersion: { store: -1, sku: -1, owner: -1 }
  }
  const calls = { stores: [], owners: [], detail: [], skuListings: [], exported: [], warned: 0 }
  const context = vm.createContext({
    ...state,
    checkPermi: api.checkPermi || (() => true),
    ElMessage: { warning: () => { calls.warned += 1 } },
    listEbayPriceAnalysisStores: params => {
      calls.stores.push(plain(params))
      return Promise.resolve(api.stores ? api.stores(params) : { data: MOCK_STORES })
    },
    listEbayPriceAnalysisOwners: params => {
      calls.owners.push(plain(params))
      return Promise.resolve(api.owners ? api.owners(params) : { data: MOCK_OWNERS })
    },
    listEbayPriceAnalysisDetail: params => {
      calls.detail.push(plain(params))
      const fallback = params.mode === 'summary' ? MOCK_SUMMARY : MOCK_DETAIL
      return Promise.resolve(api.detail ? api.detail(params) : { data: fallback })
    },
    getEbayPriceAnalysisSkuListings: sku => {
      calls.skuListings.push(sku)
      return api.skuListings ? api.skuListings(sku) : Promise.resolve({ data: MOCK_SKU_LISTINGS })
    },
    exportEbayPriceAnalysis: params => {
      calls.exported.push(plain(params))
      return Promise.resolve()
    }
  })
  vm.runInContext(PAGE_FUNCTIONS.map(declaration).join('\n'), context)
  return { ...state, calls, page: context }
}

// ===== 页面结构 =====
test('page and its template compile', () => {
  assert.equal(script.scriptSetupAst.length > 0, true)
  const template = compileTemplate({
    source: templateSource,
    filename: pageFile.pathname,
    id: 'ebay-price-analysis',
    compilerOptions: { bindingMetadata: script.bindings }
  })
  assert.deepEqual(template.errors, [])
})

test('page never injects raw html', () => {
  assert.doesNotMatch(pageSource, /v-html/)
})

test('charts, kpi cards and the overview call are gone', () => {
  assert.doesNotMatch(setupSource, /echarts|chart\.js|highcharts|vue-echarts|\bd3\b/)
  assert.doesNotMatch(pageSource, /kpi|chart-box|scatter|stock_gap_top|risks|storeChart|renderCharts/i)
  assert.doesNotMatch(pageSource, /Overview|overview/)
  assert.doesNotMatch(apiSource, /overview/i)
})

test('body is three tabs: store, sku and owner dimension', () => {
  assert.match(templateSource, /<el-tabs v-model="activeTab"[^>]*@tab-change="handleTabChange"/)
  assert.match(templateSource, /<el-tab-pane label="店铺维度" name="store">/)
  assert.match(templateSource, /<el-tab-pane label="SKU 维度" name="sku">/)
  assert.match(templateSource, /<el-tab-pane label="个人维度" name="owner">/)
  assert.equal((templateSource.match(/<el-tab-pane /g) || []).length, 3)
  assert.match(templateSource, /:data="stores"[^]*?@row-click="selectStore"/)
  assert.match(templateSource, /@click="openCompare\(row\)">其他店铺</)
  assert.match(templateSource, /<el-drawer\s+v-model="compareDrawer\.visible"/)
  assert.match(templateSource, /<el-table-column type="expand"/)
  assert.match(templateSource, /@expand-change="handleSkuExpand"/)
})

test('dropped fields are gone from both tabs, the drawer and the expand rows', () => {
  // 用户不要的字段：同站点最低 / 最高价、比最低价高出、多店超卖、断货在售、状态，店铺汇总的两列，
  // 以及连带的两个「只看」、状态下拉、整行红底、「最低」标签。后端字段照常返回，页面一处都不用。
  for (const pattern of [
    /site_price_usd_m(in|ax)|price_usd_m(in|ax)|price_vs_site_min_pct/,
    /site_oversell|out_of_stock_listed|site_oversell_sku_count|statuses/,
    /多店超卖|断货在售|比最低价|>最低</,
    /onlySiteOversell|onlyOutOfStockListed|siteOversell|outOfStockListed/,
    /query\.status|statusOptions|statusTagType|STATUS_TAG_TYPE|format: 'status'/,
    /is-oversell|oversell-tag|oversellTip|oversellRowClass|lowestListingKeys|usd-cell|price-(lowest|above|high)/
  ]) {
    assert.doesNotMatch(pageSource, pattern)
  }
  assert.doesNotMatch(templateSource, /label="状态"/)
  assert.doesNotMatch(setupSource, /label: '状态'/)
})

test('store detail keeps the listed columns and adds the unmatched reason', () => {
  assert.deepEqual(columnKeys('columnDefs'), [
    'image_url', 'sku', 'title', 'owner_name', 'listing_start_time', 'current_price', 'price_usd', 'ebay_quantity_available',
    'overseas_sellable', 'chengdu_sellable', 'overseas_in_transit', 'site_store_count',
    'site_ebay_available_total', 'unmatched_reason_text'
  ])
  assert.match(declaration('columnDefs'), /key: 'unmatched_reason_text', label: '未匹配原因'[^}]*format: 'reason'/)
  assert.match(setupSource, /useColumnConfig\(\s*'operations:ebay:priceAnalysis:store'/)
})

test('sku dimension keeps store count and stock and adds the unmatched reason', () => {
  assert.deepEqual(columnKeys('skuColumns'), [
    'image_url', 'site_name', 'sku', 'title', 'owner_name', 'store_count', 'ebay_quantity_available',
    'overseas_sellable', 'chengdu_sellable', 'overseas_in_transit', 'unmatched_reason_text'
  ])
})

test('drawer and expand rows: site stock table and listing table keep only the needed columns', () => {
  assert.deepEqual(columnKeys('compareSiteColumns'), [
    'site_name', 'overseas_sellable', 'chengdu_sellable', 'overseas_in_transit', 'pending_outbound',
    'store_count', 'ebay_available_total'
  ])
  assert.deepEqual(columnKeys('compareListingColumns'), [
    'seller_account', 'site_name', 'item_id', 'current_price', 'price_usd', 'ebay_quantity_available',
    'listing_start_time', 'unmatched_reason_text'
  ])
})

test('store summary keeps six columns and the unmatched count is clickable', () => {
  const summary = templateSource.match(/:data="stores"[^]*?<\/el-table>/)[0]
  const props = [...summary.matchAll(/<el-table-column prop="([a-z_]+)"/g)].map(match => match[1])
  assert.deepEqual(props, ['seller_account', 'site_name', 'listing_count', 'sku_count', 'ebay_available', 'unmatched_count'])
  assert.match(summary, /v-if="Number\(row\.unmatched_count\) > 0"[^]*?@click\.stop="focusStore\(row\)"/)
})

test('header has a single refresh button that reloads the page with the refresh icon', () => {
  const head = templateSource.match(/<div class="head-acts">[^]*?<\/el-tooltip>/)[0]
  assert.equal((head.match(/刷新/g) || []).length, 1)
  // 改版后图标走 <app-icon>，加载中旋转由组件的 spin 属性负责，不再靠页面自己的 .spinning 动画。
  assert.match(head, /<el-button :disabled="loading" @click="handleQuery">\s*<app-icon name="refresh"[^>]*class="report-icon"[^>]*:spin="loading"[^>]*\/>刷新/)
  assert.match(head, /<app-icon v-if="!exporting" name="export"[^>]*\/>导出明细/)
  // 改版把导出按钮统一成 primary plain（原来是 warning plain 橙色）。
  assert.match(head, /<el-button\s+type="primary"\s+plain[^>]*@click="handleExport"/)
  assert.doesNotMatch(head, /\sicon="|svg-icon|icon-class=/)
  assert.doesNotMatch(pageSource, /刷新数据源|handleRefreshSource|operations:ebayPriceAnalysis:refresh/)
  // 带文字的按钮里图标跟随文字色（currentColor），不写死颜色。
  const iconRule = styleSource.match(/\.report-icon \{[^}]*\}/)[0]
  assert.doesNotMatch(iconRule, /color:/)
})

// ===== 未匹配原因 =====
test('"only unmatched" is the one remaining checkbox and is sent as unmatched=true', () => {
  assert.match(templateSource, /<el-checkbox v-model="query\.onlyUnmatched" @change="handleListFilter">只看未匹配<\/el-checkbox>/)
  assert.equal((templateSource.match(/<el-checkbox /g) || []).length, 1)
  const { query, page } = createHarness()
  assert.equal(Object.hasOwn(plain(page.buildFilterParams()), 'unmatched'), false)
  query.onlyUnmatched = true
  assert.equal(page.buildFilterParams().unmatched, 'true')
  assert.equal(Object.hasOwn(plain(page.buildFilterParams()), 'status'), false)
})

test('unmatched reason shows only for unmatched listings', () => {
  const { page } = createHarness()
  const [matched, unmatched] = MOCK_DETAIL.rows
  const col = { key: 'unmatched_reason_text', format: 'reason' }
  assert.equal(page.cellText(matched, col), '')
  assert.equal(page.cellText(unmatched, col), 'SKU 带后缀「-SY」，去掉后谷仓 DE 有此商品')
  // 已匹配就算带了文案也留空；没有 inventory_matched 的行（汇总、跨店刊登）只看有没有文案。
  assert.equal(page.unmatchedReason({ inventory_matched: 1, unmatched_reason_text: '旧数据' }), '')
  assert.equal(page.unmatchedReason({ inventory_matched: '1' }), '')
  assert.equal(page.unmatchedReason(MOCK_SUMMARY.rows[0]), '')
  assert.equal(page.unmatchedReason(MOCK_SKU_LISTINGS.listings[2]), 'FR 站没有对应仓库')
  assert.equal(page.unmatchedReason({ unmatched_reason_text: '   ' }), '')
  // 后端上线前：明细里明确未匹配但还没有原因字段，先显示「未匹配」，不留一整列空白。
  assert.equal(page.unmatchedReason({ inventory_matched: 0 }), '未匹配')
  assert.equal(page.unmatchedReason({ inventory_matched: '0', unmatched_reason_text: null }), '未匹配')
  assert.equal(page.cellClass(matched, col), '')
})

test('every table renders the unmatched reason through the same branch', () => {
  // 店铺维度明细、SKU 维度、个人维度 SKU 表、展开行刊登表、抽屉刊登表，五处都有。
  const branches = templateSource.match(/v-else-if="col\.format === 'reason'" class="unmatched-reason">\{\{ unmatchedReason\((row|scope\.row)\) \}\}/g) || []
  assert.equal(branches.length, 5)
  assert.match(styleSource, /\.unmatched-reason \{\s*color: #b88230;/)
  assert.match(styleSource, /\.sku-compare-drawer \.unmatched-reason \{\s*color: #b88230;/)
})

test('clicking the unmatched count selects the store and turns on the filter', async () => {
  const { query, selectedStore, calls, page } = createHarness()
  await page.focusStore(MOCK_STORES.rows[0])
  assert.equal(query.onlyUnmatched, true)
  assert.equal(selectedStore.value.seller_account, 'aplus-shop')
  const params = calls.detail.at(-1)
  assert.equal(params.unmatched, 'true')
  assert.equal(params.accounts, 'aplus-shop')
  assert.equal(params.sites, 'DE')
})

test('cells render response values without recomputing them', () => {
  const { page } = createHarness()
  const row = MOCK_DETAIL.rows[0]
  assert.equal(page.cellText(row, { key: 'current_price', format: 'price' }), '52.90 EUR')
  assert.equal(page.cellText(row, { key: 'price_usd', format: 'decimal' }), '58.20')
  assert.equal(page.cellText(row, { key: 'site_ebay_available_total', format: 'integer' }), '58')
  assert.equal(page.cellText({}, { key: 'overseas_sellable', format: 'integer' }), '—')
  assert.equal(page.cellClass({}, { key: 'overseas_sellable', format: 'integer' }), 'muted')
  assert.doesNotMatch(setupSource, /(overseas_sellable|chengdu_sellable|ebay_quantity_available)\s*[-+*/]\s*\w/)
  assert.doesNotMatch(setupSource, /Math\.(min|max)\(/)
})

// ===== 数据加载 =====
test('header snapshot comes from the list responses, not from overview', async () => {
  const { snapshot, page } = createHarness()
  await page.loadStores()
  assert.equal(snapshot.stat_date, '2026-11-10')
  assert.equal(snapshot.refreshed_at, '2026-11-10 04:41:02')
  assert.match(templateSource, /displayValue\(snapshot\.stat_date\)/)
  assert.match(templateSource, /displayValue\(snapshot\.refreshed_at\)/)
  page.applySnapshot({ rows: [] })
  assert.equal(snapshot.stat_date, '2026-11-10')
})

test('store summary only sends site and account filters', async () => {
  const { query, calls, page } = createHarness()
  query.sites = ['DE']
  query.accounts = [' aplus-shop ', '']
  query.keyword = 'TYT'
  query.onlyUnmatched = true
  await page.loadStores()
  assert.deepEqual(calls.stores, [{ sites: 'DE', accounts: 'aplus-shop' }])
})

test('loading stores selects the first store and keeps the selection when it is still listed', async () => {
  const { stores, selectedStore, knownAccounts, page } = createHarness()
  await page.loadStores()
  assert.equal(stores.value.length, 2)
  assert.equal(selectedStore.value.seller_account, 'aplus-shop')

  page.selectStore(MOCK_STORES.rows[1])
  await page.loadStores()
  assert.equal(selectedStore.value.seller_account, 'bparts')
  assert.deepEqual([...knownAccounts.value], ['aplus-shop', 'bparts'])

  const empty = createHarness({ stores: () => ({ data: { rows: [] } }) })
  await empty.page.loadStores()
  assert.equal(empty.selectedStore.value, null)
  await empty.page.loadStoreDetail()
  assert.equal(empty.calls.detail.length, 0)
})

test('store detail asks for exactly the selected store and site', async () => {
  const { query, calls, detailRows, detailTotal, page } = createHarness()
  query.sites = ['DE', 'UK']
  query.accounts = ['aplus-shop', 'bparts']
  query.keyword = ' TYT '
  query.onlyUnmatched = true
  await page.selectStore(MOCK_STORES.rows[1])
  assert.equal(calls.detail.length, 1)
  const params = calls.detail[0]
  assert.equal(params.accounts, 'bparts')
  assert.equal(params.sites, 'DE')
  assert.equal(params.mode, 'detail')
  assert.equal(params.keyword, 'TYT')
  assert.equal(params.unmatched, 'true')
  assert.equal(params.pageNum, 1)
  assert.equal(detailRows.value.length, 2)
  assert.equal(detailTotal.value, 2)
})

test('sku dimension loads the summary mode with the shared filters', async () => {
  const { query, calls, skuRows, activeTab, page } = createHarness()
  activeTab.value = 'sku'
  query.keyword = '  TYT-90245  '
  query.onlyUnmatched = true
  await page.handleListFilter()
  const params = calls.detail.at(-1)
  assert.equal(params.mode, 'summary')
  assert.equal(params.keyword, 'TYT-90245')
  assert.equal(params.unmatched, 'true')
  assert.equal(params.pageNum, 1)
  assert.equal(Object.hasOwn(params, 'accounts'), false)
  assert.equal(skuRows.value[0].store_count, 3)
})

test('list filters reload only the active tab and stale tabs reload on switch', async () => {
  const { calls, activeTab, page } = createHarness()
  await page.handleQuery()
  assert.equal(calls.stores.length, 1)
  assert.deepEqual(calls.detail.map(item => item.mode), ['detail'])

  activeTab.value = 'sku'
  await page.handleTabChange()
  activeTab.value = 'store'
  await page.handleTabChange()
  assert.deepEqual(calls.detail.map(item => item.mode), ['detail', 'summary'])

  await page.handleListFilter()
  activeTab.value = 'sku'
  await page.handleTabChange()
  assert.deepEqual(calls.detail.map(item => item.mode), ['detail', 'summary', 'detail', 'summary'])
  assert.equal(calls.stores.length, 1)
})

test('sorting maps element-plus order to the api and restarts paging', async () => {
  const { detailPage, skuPage, calls, page } = createHarness()
  await page.loadStores()
  await page.handleDetailSort({ prop: 'price_usd', order: 'ascending' })
  assert.equal(detailPage.sortBy, 'price_usd')
  assert.equal(detailPage.sortOrder, 'asc')
  assert.equal(calls.detail.at(-1).pageNum, 1)
  await page.handleSkuSort({ prop: 'store_count', order: 'descending' })
  assert.equal(skuPage.sortOrder, 'desc')
  assert.equal(calls.detail.at(-1).sortBy, 'store_count')
  await page.handleSkuSort({ prop: 'store_count', order: null })
  assert.equal(skuPage.sortBy, undefined)
})

test('sku listings are fetched once per sku and shared by the drawer and expand rows', async () => {
  const { compareDrawer, calls, page } = createHarness()
  await page.openCompare(MOCK_DETAIL.rows[0])
  assert.equal(compareDrawer.visible, true)
  assert.equal(compareDrawer.sku, 'TYT-90245-0772')
  assert.deepEqual(plain(compareDrawer.origin), { seller_account: 'aplus-shop', site: 'DE' })
  const state = page.skuListing('TYT-90245-0772')
  assert.equal(state.loading, false)
  assert.equal(state.data.listings.length, 3)
  assert.equal(state.data.sites.length, 2)

  const collapsed = { sku: 'OTHER-SKU' }
  assert.equal(page.handleSkuExpand(collapsed, []), undefined)
  await page.handleSkuExpand(MOCK_SUMMARY.rows[0], [MOCK_SUMMARY.rows[0]])
  await page.ensureSkuListings(' TYT-90245-0772 ')
  assert.deepEqual(calls.skuListings, ['TYT-90245-0772'])

  await page.handleQuery()
  await page.openCompare(MOCK_DETAIL.rows[0])
  assert.deepEqual(calls.skuListings, ['TYT-90245-0772', 'TYT-90245-0772'])
})

test('a failed sku listing request is not cached so the next open retries', async () => {
  let attempts = 0
  const { page } = createHarness({
    skuListings: () => {
      attempts += 1
      return attempts === 1 ? Promise.reject(new Error('502')) : Promise.resolve({ data: { sku: 'A', listings: null } })
    }
  })
  await page.ensureSkuListings('A')
  assert.equal(page.skuListing('A').error, true)
  await page.ensureSkuListings('A')
  assert.equal(page.skuListing('A').error, false)
  assert.deepEqual(plain(page.skuListing('A').data.listings), [])
  assert.deepEqual(plain(page.skuListing('A').data.sites), [])
  assert.equal(attempts, 2)
  assert.equal(await page.ensureSkuListings('  '), undefined)
})

test('drawer and expand rows highlight the store or site they were opened from', () => {
  const { page } = createHarness()
  const row = { seller_account: 'aplus-shop', site: 'DE' }
  assert.equal(page.compareListingRowClass({ row }, { seller_account: 'aplus-shop', site: 'DE' }), 'is-origin')
  assert.equal(page.compareListingRowClass({ row }, { seller_account: 'bparts', site: 'DE' }), '')
  assert.equal(page.compareListingRowClass({ row }, { site: 'DE' }), 'is-origin')
  // 站点库存表只剩来源站点高亮，backend 照常返回的 site_oversell 不再挂任何样式。
  assert.equal(page.compareSiteRowClass({ row: MOCK_SKU_LISTINGS.sites[0] }, 'DE'), 'is-origin')
  assert.equal(page.compareSiteRowClass({ row: MOCK_SKU_LISTINGS.sites[1] }, 'DE'), '')
})

// ===== 导出 =====
test('export button is gated by permission twice', () => {
  assert.match(pageSource, /v-hasPermi="\['operations:ebayPriceAnalysis:export'\]"/)
  assert.match(setupSource, /checkPermi\(\['operations:ebayPriceAnalysis:export'\]\)/)
})

test('export without permission warns and sends nothing', async () => {
  const { calls, page } = createHarness({ checkPermi: () => false })
  await page.handleExport()
  assert.equal(calls.warned, 1)
  assert.equal(calls.exported.length, 0)
})

test('export follows the active tab and covers the whole filtered set', async () => {
  const { query, activeTab, calls, page } = createHarness()
  query.keyword = 'TYT'
  query.accounts = ['aplus-shop']
  await page.handleExport()
  activeTab.value = 'sku'
  await page.handleExport()
  assert.equal(calls.exported.length, 2)
  assert.equal(calls.exported[0].mode, 'detail')
  assert.equal(calls.exported[1].mode, 'summary')
  for (const params of calls.exported) {
    assert.equal(params.keyword, 'TYT')
    assert.equal(params.accounts, 'aplus-shop')
    assert.equal(Object.hasOwn(params, 'unmatched'), false)
    assert.equal(Object.hasOwn(params, 'pageNum'), false)
    assert.equal(Object.hasOwn(params, 'pageSize'), false)
  }
})

test('export carries "only unmatched" so it matches what is on screen', async () => {
  const { query, activeTab, calls, page } = createHarness()
  query.onlyUnmatched = true
  await page.handleExport()
  activeTab.value = 'sku'
  await page.handleExport()
  for (const params of calls.exported) assert.equal(params.unmatched, 'true')
  query.onlyUnmatched = false
  await page.handleExport()
  assert.equal(Object.hasOwn(calls.exported.at(-1), 'unmatched'), false)
})

test('reset clears every filter, the selection and sorting', async () => {
  const { query, detailPage, calls, page } = createHarness()
  query.sites = ['DE']
  query.keyword = 'TYT'
  query.onlyUnmatched = true
  detailPage.sortBy = 'price_usd'
  await page.resetQuery()
  assert.deepEqual([...query.sites], [])
  assert.equal(query.keyword, undefined)
  assert.equal(query.onlyUnmatched, false)
  assert.equal(detailPage.sortBy, undefined)
  assert.deepEqual(calls.stores.at(-1), {})
})

// ===== 口径说明 =====
test('page keeps the fixed wording of the data-definition footer', () => {
  for (const line of [
    '谷仓、成都库存按站点共享，同一站点多个店铺显示的是同一份库存，不能相加',
    'eBay 售价与可售量为在售刊登每周快照（每周一更新），快照日期见页头',
    '海外仓库存为谷仓区域仓接口每周快照（DE / UK / 美东 USEA / 美西 USWE，美国两仓合计；捷克 CZ 暂不纳入）',
    '成都中转仓库存仍为领星周快照',
    '海外仓按「站点 + 去掉 SKU 第一段（品牌前缀，谷仓侧为 JMH）」匹配',
    '未匹配：这条刊登在所在站点的谷仓和成都仓都找不到对应 SKU，原因见『未匹配原因』列',
    '售价按站点币种和领星月度企业汇率折算 USD；当月汇率未出时，沿用该币种最近一个已出月份的汇率；完全没有汇率时不折算',
    '采购成本优先取订单文件中最近一笔真实采购成本，没有订单时用领星商品资料的采购价；未参与售价估算',
    '货值 = 实际库存（谷仓可售 + 成都可售）× 单价（含税，取 eBay 库存明细导入的产品单价，按中间码取最低价），同一站点 + SKU 只算一份，不用 eBay 可售（多店挂同一份货会重复）；没有单价的留空'
  ]) {
    assert.ok(pageSource.includes(line), `missing data-definition line: ${line}`)
  }
  assert.match(pageSource, /快照日期/)
  assert.match(pageSource, /不是实时库存/)
  // 多店超卖、断货在售、比最低价高出三条定义一起删掉。
  const notes = templateSource.match(/<ul class="note-list">[^]*?<\/ul>/)[0]
  assert.equal((notes.match(/<li/g) || []).length, 9)
})

test('shared inventory warning sits in the footer and next to every cross-store view', () => {
  const line = '谷仓、成都库存按站点共享，同一站点多个店铺显示的是同一份库存，不能相加'
  assert.match(templateSource, new RegExp(`<li class="note-key">${line}</li>`))
  assert.equal(templateSource.split(line).length - 1, 3)
  assert.match(setupSource, /SHARED_STOCK_TIP = '按站点共享：同一站点多个店铺显示的是同一份库存，不能相加。'/)
})

test('data-definition wording follows the weekly goodcang snapshot', () => {
  for (const phrase of ['谷仓区域仓接口每周快照', '每周一更新', '美国两仓合计', '捷克 CZ 暂不纳入', '成都中转仓库存仍为领星周快照', '去掉 SKU 第一段']) {
    assert.ok(pageSource.includes(phrase), `missing weekly wording: ${phrase}`)
  }
  assert.doesNotMatch(pageSource, /wid 1870[0-2]|wid 18699|领星周快照的海外仓/)
  assert.doesNotMatch(pageSource, /每天|每日|汇率缺失/)
})

// ===== 布局与接口 =====
test('drawer listing table fits the drawer without sideways scrolling', () => {
  // 抽屉 920px，内边距左右各 20px；列宽合计超过约 880px 就会出横向滚动条，留 10px 余量。
  assert.match(templateSource, /<el-drawer[^>]*size="920px"/)
  const widths = [...declaration('compareListingColumns').matchAll(/(?:minWidth|width): (\d+)/g)].map(match => Number(match[1]))
  assert.equal(widths.length, 8)
  assert.ok(widths.reduce((sum, value) => sum + value, 0) <= 870, `listing columns too wide: ${widths}`)
  // 长原因句子不撑宽列：超出部分悬停看全文。
  assert.match(declaration('compareListingColumns'), /key: 'unmatched_reason_text'[^}]*tooltip: true/)
})

test('layout holds together at phone width without sideways scrolling', () => {
  assert.match(styleSource, /@media \(max-width: 768px\)[^]*?\.filter-control \{\s*width: 100%;/)
  assert.match(styleSource, /\.sku-compare-drawer \{\s*max-width: 100vw;/)
  const wide = []
  for (const match of styleSource.matchAll(/(?:minmax\(|min-width:\s*|[^-]width:\s*)(\d+)px/g)) {
    if (Number(match[1]) > 335) wide.push(match[0])
  }
  assert.deepEqual(wide, [])
})

test('api calls the erp proxy routes with a timeout fit for the aggregation', () => {
  assert.match(apiSource, /const base = '\/operations\/ebay\/price-analysis'/)
  assert.match(apiSource, /export function listEbayPriceAnalysisStores[^]*?\$\{base\}\/stores`, method: 'get'/)
  assert.match(apiSource, /export function listEbayPriceAnalysisDetail[^]*?\$\{base\}\/detail`, method: 'get'/)
  assert.match(apiSource, /export function getEbayPriceAnalysisSkuListings\(sku\)[^]*?\$\{base\}\/sku-listings`, method: 'get', params: \{ sku \}/)
  assert.match(apiSource, /export function exportEbayPriceAnalysis[^]*?download\(`\$\{base\}\/export`/)
  assert.match(apiSource, /LONG_TIMEOUT = 120000/)
  assert.doesNotMatch(apiSource, /refreshEbayPriceAnalysis|\/refresh`/)
  assert.match(apiSource, /export function listEbayPriceAnalysisOwners[^]*?\$\{base\}\/owners`, method: 'get'/)
  assert.equal((apiSource.match(/^export function /gm) || []).length, 5)
})


test('owner and listing start time columns are shown; start time is not called a price change', () => {
  const store = declaration('columnDefs')
  assert.match(store, /key: 'owner_name', label: '负责人'/)
  assert.match(store, /key: 'listing_start_time', label: '上架时间'[^}]*不是最近调价时间/)
  assert.match(declaration('skuColumns'), /key: 'owner_name', label: '负责人'/)
  assert.match(declaration('compareListingColumns'), /key: 'listing_start_time', label: '上架日期', width: 100, format: 'date'/)
  // 已保存过列配置的用户：新列插在产品名称后面，而不是追加到最后
  assert.match(pageSource, /\{ owner_name: 'title', listing_start_time: 'owner_name' \}/)
  assert.match(pageSource, /case 'date':\s*return value \? String\(value\)\.slice\(0, 10\) : '—'/)
  assert.doesNotMatch(pageSource, /调价时间'/)
})

test('store summary table is width-capped so the store column does not swallow the card', () => {
  const table = templateSource.match(/<el-table[^>]*class="store-table"[^>]*>/s)?.[0] || ''
  assert.match(table, /max-width:\s*760px/)
  const flexible = [...templateSource.split('class="store-table"')[1].split('</el-table>')[0]
    .matchAll(/<el-table-column[^>]*min-width="(\d+)"/g)].map(m => Number(m[1]))
  // 店铺是唯一弹性列；200 + 其余 5 个固定列 500 = 700，留 60px 给店铺列伸展
  assert.deepEqual(flexible, [200])
})

// ===== 个人维度 =====
test('owner summary shows stock and value per owner without any status columns', () => {
  // columnKeys 只认小写字母和下划线，这两张表有 sales_qty_7d 这类带数字的 key，单独取
  const keys = name => [...declaration(name).matchAll(/key: '([a-z0-9_]+)'/g)].map(match => match[1])
  assert.deepEqual(keys('ownerColumns'), [
    'owner_name', 'sku_count', 'listing_count', 'store_count', 'ebay_available', 'inventory_qty',
    'inventory_value_cny', 'sales_qty_7d', 'sales_qty_30d', 'unmatched_sku_count'
  ])
  assert.deepEqual(keys('ownerSkuColumns'), [
    'image_url', 'site_name', 'sku', 'title', 'store_count', 'ebay_quantity_available', 'overseas_sellable',
    'chengdu_sellable', 'inventory_qty', 'purchase_cost_cny', 'unit_price_tax', 'inventory_value_cny', 'sales_qty_7d',
    'sales_qty_30d', 'cover_days', 'unmatched_reason_text'
  ])
  // 状态列按需求下线，个人维度也不放回来；货值的提示写明不用 eBay 可售
  assert.doesNotMatch(declaration('ownerColumns') + declaration('ownerSkuColumns'), /status|超卖|断货|滞销|待补货/)
  assert.match(setupSource, /VALUE_TIP = '实际库存（谷仓可售 \+ 成都可售）× 单价（含税），同一站点 \+ SKU 只算一份；没有单价的留空/)
  const owner = templateSource.match(/:data="ownerRows"[^]*?<\/el-table>/)[0]
  assert.match(owner, /@row-click="selectOwner"/)
  assert.match(owner, /v-if="Number\(row\.unmatched_sku_count\) > 0"[^]*?@click\.stop="focusOwner\(row\)"/)
  assert.match(owner, /v-if="Number\(row\.value_missing_sku_count\) > 0"/)
  const table = templateSource.match(/<el-table[^>]*class="store-table owner-table"[^>]*>/s)?.[0] || ''
  assert.match(table, /max-width:\s*1040px/)
  const widths = [...declaration('ownerColumns').matchAll(/(?:minWidth|width): (\d+)/g)].map(match => Number(match[1]))
  assert.ok(widths.reduce((sum, value) => sum + value, 0) <= 1040, `owner columns wider than the cap: ${widths}`)
})

test('owner tab loads owners with site and account only, then the owner skus by value', async () => {
  const { query, activeTab, selectedOwner, ownerRows, ownerSkuRows, calls, page } = createHarness()
  query.sites = ['DE']
  query.accounts = ['aplus-shop']
  query.keyword = 'brake'
  query.onlyUnmatched = true
  activeTab.value = 'owner'
  await page.loadActiveTab()
  assert.deepEqual(calls.owners, [{ sites: 'DE', accounts: 'aplus-shop' }])
  assert.equal(ownerRows.value.length, 2)
  assert.equal(selectedOwner.value, '方黎力', '默认选第一位')
  assert.deepEqual(calls.detail.at(-1), {
    sites: 'DE', accounts: 'aplus-shop', keyword: 'brake', unmatched: 'true', owners: '方黎力',
    mode: 'summary', sortBy: 'inventory_value_cny', sortOrder: 'desc', pageNum: 4, pageSize: 50
  })
  assert.equal(ownerSkuRows.value.length, 1)
  assert.equal(calls.stores.length, 0, '个人维度不拉店铺汇总')
})

test('picking an owner keeps the selection across reloads and the unmatched count turns the filter on', async () => {
  const { query, activeTab, selectedOwner, ownerSkuPage, calls, page } = createHarness()
  activeTab.value = 'owner'
  await page.loadActiveTab()
  await page.selectOwner(MOCK_OWNERS.rows[1])
  assert.equal(selectedOwner.value, '杨萍')
  assert.equal(ownerSkuPage.pageNum, 1)
  assert.equal(calls.detail.at(-1).owners, '杨萍')
  await page.loadOwners()
  assert.equal(selectedOwner.value, '杨萍', '筛选后人还在就保持选中')
  assert.equal(page.ownerRowClass({ row: MOCK_OWNERS.rows[1] }), 'is-selected')
  await page.focusOwner(MOCK_OWNERS.rows[0])
  assert.equal(query.onlyUnmatched, true)
  assert.equal(selectedOwner.value, '方黎力')
  assert.equal(calls.detail.at(-1).unmatched, 'true')
  await page.handleOwnerSkuSort({ prop: 'purchase_cost_cny', order: 'ascending' })
  assert.deepEqual([calls.detail.at(-1).sortBy, calls.detail.at(-1).sortOrder], ['purchase_cost_cny', 'asc'])
})

test('no owner means no sku request, and export on the owner tab sends that owner in summary mode', async () => {
  const { activeTab, selectedOwner, ownerSkuRows, calls, page } = createHarness({ owners: () => ({ data: { rows: [] } }) })
  activeTab.value = 'owner'
  await page.loadActiveTab()
  assert.equal(selectedOwner.value, null)
  assert.equal(calls.detail.length, 0)
  assert.deepEqual(plain(ownerSkuRows.value), [])
  selectedOwner.value = '杨萍'
  await page.handleExport()
  assert.deepEqual(calls.exported.at(-1), {
    owners: '杨萍', mode: 'summary', sortBy: 'inventory_value_cny', sortOrder: 'desc'
  })
})

test('owner value cell shows the yuan amount and reset restores the value sort', async () => {
  const { selectedOwner, ownerSkuPage, page } = createHarness()
  assert.equal(page.cellText(MOCK_OWNERS.rows[0], { key: 'inventory_value_cny', format: 'value' }), '960,394.47')
  assert.equal(page.cellText({ inventory_value_cny: null }, { key: 'inventory_value_cny', format: 'value' }), '—')
  selectedOwner.value = '杨萍'
  Object.assign(ownerSkuPage, { sortBy: 'cover_days', sortOrder: 'asc', pageNum: 3 })
  await page.resetQuery()
  assert.equal(selectedOwner.value, null)
  assert.deepEqual([ownerSkuPage.sortBy, ownerSkuPage.sortOrder, ownerSkuPage.pageNum], ['inventory_value_cny', 'desc', 1])
})
