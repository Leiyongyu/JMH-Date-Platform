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

// ===== 按契约字段造的 mock：新接口这会儿还调不通 =====
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
      ebay_available: 880, out_of_stock_listed: 0, site_oversell_sku_count: 3, unmatched_count: 4
    }
  ]
}
const MOCK_DETAIL = {
  stat_date: '2026-11-10',
  refreshed_at: '2026-11-10 04:41:02',
  total: 1,
  rows: [{
    seller_account: 'aplus-shop', site: 'DE', site_name: '德国', item_id: '1001', sku: 'TYT-90245-0772',
    title: 'Brake pad', currency: 'EUR', current_price: 52.9, price_usd: 58.2, ebay_quantity_available: 36,
    overseas_sellable: 20, chengdu_sellable: 5, overseas_in_transit: 0, site_store_count: 3,
    site_ebay_available_total: 58, site_price_usd_min: 51.75, site_price_usd_max: 64.1,
    price_vs_site_min_pct: 0.1246, site_oversell: 1, status: '超卖风险'
  }]
}
const MOCK_SUMMARY = {
  stat_date: '2026-11-10',
  refreshed_at: '2026-11-10 04:41:02',
  total: 1,
  rows: [{
    site: 'DE', site_name: '德国', sku: 'TYT-90245-0772', store_count: 3, ebay_quantity_available: 58,
    overseas_sellable: 20, chengdu_sellable: 5, price_usd_min: 51.75, price_usd_max: 64.1,
    site_oversell: true, statuses: '超卖风险,健康'
  }]
}
const MOCK_SKU_LISTINGS = {
  sku: 'TYT-90245-0772',
  title: 'Brake pad',
  image_url: 'https://example.invalid/a.jpg',
  stat_date: '2026-11-10',
  refreshed_at: '2026-11-10 04:41:02',
  listings: [
    { seller_account: 'cshop', site: 'DE', site_name: '德国', item_id: '1003', price_usd: null, ebay_quantity_available: 2 },
    { seller_account: 'bparts', site: 'DE', site_name: '德国', item_id: '1002', price_usd: 51.75, ebay_quantity_available: 10 },
    { seller_account: 'aplus-shop', site: 'DE', site_name: '德国', item_id: '1001', price_usd: 58.2, ebay_quantity_available: 36 },
    { seller_account: 'aplus-shop', site: 'UK', site_name: '英国', item_id: '2001', price_usd: 60, ebay_quantity_available: 4 }
  ],
  sites: [
    { site: 'DE', site_name: '德国', overseas_sellable: 20, chengdu_sellable: 5, ebay_available_total: 48, store_count: 3, site_oversell: true },
    { site: 'UK', site_name: '英国', overseas_sellable: 30, chengdu_sellable: 0, ebay_available_total: 4, store_count: 1, site_oversell: false }
  ]
}

const PAGE_FUNCTIONS = [
  'displayValue', 'integer', 'decimal', 'percent', 'pctClass', 'isTrue', 'statusTagType', 'cellText',
  'cellClass', 'oversellTip', 'toArray', 'csv', 'flag', 'storeKey', 'skuRowKey', 'listingKey',
  'lowestListingKeys', 'buildFilterParams', 'buildStoreParams', 'buildStoreDetailParams', 'buildSkuParams',
  'buildExportParams', 'applySnapshot', 'rememberAccounts', 'filterVersion', 'storesSeq', 'detailSeq',
  'skuSeq', 'loadStores', 'loadStoreDetail', 'loadSkuRows', 'loadActiveTab', 'clearSkuListings',
  'resetPages', 'handleQuery', 'handleListFilter', 'resetQuery', 'handleTabChange', 'selectStore',
  'focusStore', 'sortState', 'handleDetailSort', 'handleSkuSort', 'storeRowClass', 'oversellRowClass',
  'compareSiteRowClass', 'compareListingRowClass', 'STATUS_TAG_TYPE', 'EMPTY_LISTING', 'skuListing',
  'ensureSkuListings', 'openCompare', 'handleSkuExpand', 'handleExport'
]

function createHarness(api = {}) {
  const state = {
    query: reactive({
      sites: [], accounts: [], status: undefined, keyword: undefined,
      onlySiteOversell: false, onlyOutOfStockListed: false
    }),
    detailPage: reactive({ pageNum: 3, pageSize: 50, sortBy: undefined, sortOrder: undefined }),
    skuPage: reactive({ pageNum: 2, pageSize: 50, sortBy: undefined, sortOrder: undefined }),
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
    loadedVersion: { store: -1, sku: -1 }
  }
  const calls = { stores: [], detail: [], skuListings: [], exported: [], warned: 0 }
  const context = vm.createContext({
    ...state,
    checkPermi: api.checkPermi || (() => true),
    ElMessage: { warning: () => { calls.warned += 1 } },
    listEbayPriceAnalysisStores: params => {
      calls.stores.push(plain(params))
      return Promise.resolve(api.stores ? api.stores(params) : { data: MOCK_STORES })
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
  // 用户要的是表格，不要图表；图表库也不再引入。
  assert.doesNotMatch(setupSource, /echarts|chart\.js|highcharts|vue-echarts|\bd3\b/)
  assert.doesNotMatch(pageSource, /kpi|chart-box|scatter|stock_gap_top|risks|storeChart|renderCharts/i)
  assert.doesNotMatch(pageSource, /Overview|overview/)
  assert.doesNotMatch(apiSource, /overview/i)
})

test('body is two tabs: store dimension and sku dimension', () => {
  assert.match(templateSource, /<el-tabs v-model="activeTab"[^>]*@tab-change="handleTabChange"/)
  assert.match(templateSource, /<el-tab-pane label="店铺维度" name="store">/)
  assert.match(templateSource, /<el-tab-pane label="SKU 维度" name="sku">/)
  // 店铺汇总点一行选店铺，明细每行有「其他店铺」打开抽屉。
  assert.match(templateSource, /:data="stores"[^]*?@row-click="selectStore"/)
  assert.match(templateSource, /@click="openCompare\(row\)">其他店铺</)
  assert.match(templateSource, /<el-drawer\s+v-model="compareDrawer\.visible"/)
  // SKU 维度展开行拉这个 SKU 在所有店铺的刊登。
  assert.match(templateSource, /<el-table-column type="expand"/)
  assert.match(templateSource, /@expand-change="handleSkuExpand"/)
})

test('store detail shows every column the brief asks for', () => {
  const defs = declaration('columnDefs')
  for (const key of [
    'image_url', 'sku', 'title', 'current_price', 'price_usd', 'ebay_quantity_available',
    'overseas_sellable', 'chengdu_sellable', 'overseas_in_transit', 'site_store_count',
    'site_ebay_available_total', 'site_price_usd_min', 'site_price_usd_max', 'price_vs_site_min_pct',
    'site_oversell', 'out_of_stock_listed', 'status'
  ]) {
    assert.ok(defs.includes(`'${key}'`), `missing store detail column: ${key}`)
  }
  // 新表换了列配置 key，旧看板存的列顺序不会套上来。
  assert.match(setupSource, /useColumnConfig\(\s*'operations:ebay:priceAnalysis:store'/)
})

test('sku dimension shows store count, price range and the oversell flag', () => {
  const defs = declaration('skuColumns')
  for (const key of ['site_name', 'sku', 'store_count', 'ebay_quantity_available', 'overseas_sellable',
    'chengdu_sellable', 'price_usd_min', 'price_usd_max', 'site_oversell', 'out_of_stock_listed', 'statuses']) {
    assert.ok(defs.includes(`'${key}'`), `missing sku column: ${key}`)
  }
})

test('header has a single refresh button that reloads the page with the jmh-refresh icon', () => {
  const head = templateSource.match(/<div class="head-acts">[^]*?<\/el-tooltip>/)[0]
  assert.equal((head.match(/刷新/g) || []).length, 1)
  assert.match(head, /<el-button :disabled="loading" @click="handleQuery">\s*<svg-icon icon-class="jmh-refresh" class="report-icon" :class="\{ spinning: loading \}" \/>刷新/)
  assert.match(head, /icon-class="jmh-export"/)
  // 导出按钮沿用全站 warning plain 的橙色约定。
  assert.match(head, /<el-button\s+type="warning"\s+plain[^>]*@click="handleExport"/)
  assert.doesNotMatch(head, /\sicon="/)
  assert.doesNotMatch(pageSource, /刷新数据源|handleRefreshSource|operations:ebayPriceAnalysis:refresh/)
  assert.match(styleSource, /\.report-icon\.spinning \{\s*animation: report-icon-spin/)
  // 带文字的按钮里图标跟随文字色（currentColor），不写死颜色。
  const iconRule = styleSource.match(/\.report-icon \{[^}]*\}/)[0]
  assert.doesNotMatch(iconRule, /color:/)
})

test('two "only show" filters exist and are sent as boolean flags', () => {
  assert.match(templateSource, /v-model="query\.onlySiteOversell"[^>]*>只看多店超卖</)
  assert.match(templateSource, /v-model="query\.onlyOutOfStockListed"[^>]*>只看断货在售</)
  const { query, page } = createHarness()
  assert.equal(plain(page.buildFilterParams()).siteOversell, undefined)
  assert.equal(plain(page.buildFilterParams()).outOfStockListed, undefined)
  query.onlySiteOversell = true
  query.onlyOutOfStockListed = true
  assert.equal(page.buildFilterParams().siteOversell, 'true')
  assert.equal(page.buildFilterParams().outOfStockListed, 'true')
})

test('multi-store oversell stands out and the price gap shows as a percentage', () => {
  assert.match(templateSource, /<el-tag type="danger" effect="dark" class="oversell-tag">多店超卖<\/el-tag>/)
  assert.match(styleSource, /\.el-table__row\.is-oversell > td\.el-table__cell\) \{\s*background: #fef0f0;/)
  const { page } = createHarness()
  assert.equal(page.percent(0.1246), '+12.5%')
  assert.equal(page.percent(0), '最低价')
  assert.equal(page.percent(null), '—')
  assert.equal(page.pctClass(0.25), 'price-high')
  assert.equal(page.pctClass(0.05), 'price-above')
  assert.equal(page.pctClass(0), 'price-lowest')
  // 布尔列经过 Python / Java 转发后可能是 1 / '1' / true。
  for (const value of [true, 1, '1', 'true']) assert.equal(page.isTrue(value), true)
  for (const value of [false, 0, '0', null, undefined]) assert.equal(page.isTrue(value), false)
  assert.equal(page.oversellRowClass({ row: MOCK_DETAIL.rows[0] }), 'is-oversell')
  assert.equal(page.oversellRowClass({ row: { site_oversell: 0 } }), '')
  const tip = page.oversellTip(MOCK_DETAIL.rows[0])
  assert.match(tip, /同站点 3 个店铺 eBay 可售合计 58/)
  assert.match(tip, /谷仓可售 20 \+ 成都可售 5/)
})

test('cells render response values without recomputing them', () => {
  const { page } = createHarness()
  const row = MOCK_DETAIL.rows[0]
  assert.equal(page.cellText(row, { key: 'current_price', format: 'price' }), '52.90 EUR')
  assert.equal(
    page.cellText(row, { key: 'site_price_range', format: 'range', minKey: 'site_price_usd_min', maxKey: 'site_price_usd_max' }),
    '51.75 ~ 64.10'
  )
  assert.equal(page.cellText({ a: 5, b: 5 }, { key: 'r', format: 'range', minKey: 'a', maxKey: 'b' }), '5.00')
  assert.equal(page.cellText(row, { key: 'price_vs_site_min_pct', format: 'pct' }), '+12.5%')
  // 多店超卖、断货在售、跨店比价、库存一律取接口值，页面不许自己加减。
  assert.doesNotMatch(setupSource, /(overseas_sellable|chengdu_sellable|ebay_quantity_available)\s*[-+*/]\s*\w/)
  assert.doesNotMatch(setupSource, /site_price_usd_min\s*[-/]|price_usd\s*-\s*\w/)
  assert.doesNotMatch(setupSource, /Math\.(min|max)\(/)
})

test('a listing can be out of stock and multi-store oversold at once, and both marks show', () => {
  // 仓里 0 件、eBay 还挂着：同时满足两个口径，后端确认两个标记都要显示。
  const both = { ...MOCK_DETAIL.rows[0], overseas_sellable: 0, chengdu_sellable: 0, site_oversell: 1, out_of_stock_listed: 1 }
  const { page } = createHarness()
  assert.equal(page.oversellRowClass({ row: both }), 'is-oversell is-out-of-stock')
  assert.equal(page.cellText(both, { key: 'site_oversell', format: 'oversell' }), '多店超卖')
  assert.equal(page.cellText(both, { key: 'out_of_stock_listed', format: 'outOfStock' }), '断货在售')
  // 两个标记是两列、两个独立的分支，不是同一个格子里二选一。
  for (const defs of [declaration('columnDefs'), declaration('skuColumns')]) {
    assert.match(defs, /key: 'site_oversell'[^}]*format: 'oversell'/)
    assert.match(defs, /key: 'out_of_stock_listed'[^}]*format: 'outOfStock'/)
  }
  assert.equal((templateSource.match(/col\.format === 'outOfStock' && isTrue\(row\[col\.key\]\)/g) || []).length, 2)
  assert.match(templateSource, />断货在售<\/el-tag>/)
})

test('cross-store listing tables show the out-of-stock mark and tolerate the field missing', async () => {
  // 抽屉和展开行的刊登表各有一个独立分支，样式和明细表一致（实心橙色）。
  const branch = /<el-tag\s+v-else-if="col\.format === 'outOfStock' && isTrue\(scope\.row\[col\.key\]\)"\s+type="warning"\s+effect="dark"[^>]*>断货在售<\/el-tag>/g
  assert.equal((templateSource.match(branch) || []).length, 2)
  assert.match(declaration('compareListingColumns'), /key: 'out_of_stock_listed'[^}]*format: 'outOfStock'/)

  const listings = [
    { seller_account: 'aplus-shop', site: 'DE', item_id: '1001', price_usd: 58.2, ebay_quantity_available: 36, out_of_stock_listed: true },
    { seller_account: 'bparts', site: 'DE', item_id: '1002', price_usd: 51.75, ebay_quantity_available: 10, out_of_stock_listed: false },
    { seller_account: 'cshop', site: 'DE', item_id: '1003', price_usd: 60, ebay_quantity_available: 2 }
  ]
  const { page } = createHarness({
    skuListings: () => Promise.resolve({ data: { ...MOCK_SKU_LISTINGS, listings } })
  })
  await page.ensureSkuListings('TYT-90245-0772')
  const rows = page.skuListing('TYT-90245-0772').data.listings
  const col = { key: 'out_of_stock_listed', format: 'outOfStock' }
  assert.equal(page.isTrue(rows[0][col.key]), true)
  assert.equal(page.cellText(rows[0], col), '断货在售')
  // 明确为 false 或缺字段（后端上线前）：不显示标记，不报错，格子里是「—」。
  for (const row of [rows[1], rows[2]]) {
    assert.equal(page.isTrue(row[col.key]), false)
    assert.equal(page.cellText(row, col), '—')
  }
  // 原来 mock 里的 listings 一条都没有这个字段，也照常渲染。
  for (const row of MOCK_SKU_LISTINGS.listings) assert.equal(page.cellText(row, col), '—')
})

test('drawer listing table fits the drawer without sideways scrolling', () => {
  // 抽屉 820px，内边距左右各 20px；列宽合计超过约 780px 就会出横向滚动条，留 10px 余量。
  assert.match(templateSource, /<el-drawer[^>]*size="820px"/)
  const defs = declaration('compareListingColumns')
  const widths = [...defs.matchAll(/(?:minWidth|width): (\d+)/g)].map(match => Number(match[1]))
  assert.equal(widths.length, 8)
  assert.ok(widths.reduce((sum, value) => sum + value, 0) <= 770, `listing columns too wide: ${widths}`)
  assert.match(defs, /key: 'price_usd', label: '售价\(USD\)', width: 130/)
  // 价格和「最低」标签不折行，标签写短，免得把列撑回去。
  assert.match(templateSource, />最低<\/el-tag>/)
  assert.doesNotMatch(templateSource, /站点最低<\/el-tag>/)
  assert.match(styleSource, /\.sku-compare-drawer \.usd-cell \{\s*display: inline-flex;\s*white-space: nowrap;/)
})

test('lowest-price marker follows the backend order and skips missing prices', () => {
  const { page } = createHarness()
  const keys = [...page.lowestListingKeys(MOCK_SKU_LISTINGS.listings)]
  assert.deepEqual(keys, ['bparts|DE|1002', 'aplus-shop|UK|2001'])
  assert.equal(page.lowestListingKeys(undefined).size, 0)
})

// ===== 数据加载 =====
test('header snapshot comes from the list responses, not from overview', async () => {
  const { snapshot, page } = createHarness()
  await page.loadStores()
  assert.equal(snapshot.stat_date, '2026-11-10')
  assert.equal(snapshot.refreshed_at, '2026-11-10 04:41:02')
  assert.match(templateSource, /displayValue\(snapshot\.stat_date\)/)
  assert.match(templateSource, /displayValue\(snapshot\.refreshed_at\)/)
  // 一个响应没带快照字段时，不把已有的值清空。
  page.applySnapshot({ rows: [] })
  assert.equal(snapshot.stat_date, '2026-11-10')
})

test('store summary only sends site and account filters', async () => {
  const { query, calls, page } = createHarness()
  query.sites = ['DE']
  query.accounts = [' aplus-shop ', '']
  query.status = '断货'
  query.keyword = 'TYT'
  query.onlySiteOversell = true
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
  query.status = '超卖风险'
  query.onlyOutOfStockListed = true
  await page.selectStore(MOCK_STORES.rows[1])
  assert.equal(calls.detail.length, 1)
  const params = calls.detail[0]
  assert.equal(params.accounts, 'bparts')
  assert.equal(params.sites, 'DE')
  assert.equal(params.mode, 'detail')
  assert.equal(params.status, '超卖风险')
  assert.equal(params.outOfStockListed, 'true')
  assert.equal(params.siteOversell, undefined)
  assert.equal(params.pageNum, 1)
  assert.equal(detailRows.value.length, 1)
  assert.equal(detailTotal.value, 1)
})

test('clicking a count in the store summary turns on the matching filter', async () => {
  const { query, selectedStore, calls, page } = createHarness()
  await page.focusStore(MOCK_STORES.rows[0], 'oversell')
  assert.equal(query.onlySiteOversell, true)
  assert.equal(selectedStore.value.seller_account, 'aplus-shop')
  assert.equal(calls.detail.at(-1).siteOversell, 'true')

  await page.focusStore(MOCK_STORES.rows[0], 'outOfStock')
  assert.equal(query.onlyOutOfStockListed, true)
  assert.equal(calls.detail.at(-1).outOfStockListed, 'true')
})

test('sku dimension loads the summary mode with the shared filters', async () => {
  const { query, calls, skuRows, activeTab, page } = createHarness()
  activeTab.value = 'sku'
  query.keyword = '  TYT-90245  '
  query.onlySiteOversell = true
  await page.handleListFilter()
  const params = calls.detail.at(-1)
  assert.equal(params.mode, 'summary')
  assert.equal(params.keyword, 'TYT-90245')
  assert.equal(params.siteOversell, 'true')
  assert.equal(params.pageNum, 1)
  assert.equal(Object.hasOwn(params, 'accounts'), false)
  assert.equal(skuRows.value[0].store_count, 3)
})

test('list filters reload only the active tab and stale tabs reload on switch', async () => {
  const { calls, activeTab, page } = createHarness()
  await page.handleQuery()
  assert.equal(calls.stores.length, 1)
  assert.deepEqual(calls.detail.map(item => item.mode), ['detail'])

  // 没改筛选，切到 SKU 页签要拉一次；再切回店铺页签不重拉。
  activeTab.value = 'sku'
  await page.handleTabChange()
  activeTab.value = 'store'
  await page.handleTabChange()
  assert.deepEqual(calls.detail.map(item => item.mode), ['detail', 'summary'])

  // 在店铺页签改了「只看」，SKU 页签就过期了，切过去要重拉；店铺汇总不受影响。
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
  assert.equal(state.data.listings.length, 4)
  assert.equal(state.data.sites.length, 2)

  // 收起行不发请求；展开同一个 SKU（前后带空格也算）直接用缓存。
  const collapsed = { sku: 'OTHER-SKU' }
  assert.equal(page.handleSkuExpand(collapsed, []), undefined)
  await page.handleSkuExpand(MOCK_SUMMARY.rows[0], [MOCK_SUMMARY.rows[0]])
  await page.ensureSkuListings(' TYT-90245-0772 ')
  assert.deepEqual(calls.skuListings, ['TYT-90245-0772'])

  // 「刷新」清掉缓存，下次重新拉。
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
  // 空 SKU 不发请求。
  assert.equal(await page.ensureSkuListings('  '), undefined)
})

test('drawer and expand rows highlight the store or site they were opened from', () => {
  const { page } = createHarness()
  const row = { seller_account: 'aplus-shop', site: 'DE' }
  assert.equal(page.compareListingRowClass({ row }, { seller_account: 'aplus-shop', site: 'DE' }), 'is-origin')
  assert.equal(page.compareListingRowClass({ row }, { seller_account: 'bparts', site: 'DE' }), '')
  assert.equal(page.compareListingRowClass({ row }, { site: 'DE' }), 'is-origin')
  assert.equal(page.compareSiteRowClass({ row: MOCK_SKU_LISTINGS.sites[0] }, 'DE'), 'is-origin is-oversell')
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
  query.status = '超卖风险'
  query.accounts = ['aplus-shop']
  await page.handleExport()
  activeTab.value = 'sku'
  await page.handleExport()
  assert.equal(calls.exported.length, 2)
  assert.equal(calls.exported[0].mode, 'detail')
  assert.equal(calls.exported[1].mode, 'summary')
  for (const params of calls.exported) {
    assert.equal(params.siteOversell, undefined)
    assert.equal(params.outOfStockListed, undefined)
    assert.equal(params.status, '超卖风险')
    assert.equal(params.accounts, 'aplus-shop')
    assert.equal(Object.hasOwn(params, 'pageNum'), false)
    assert.equal(Object.hasOwn(params, 'pageSize'), false)
  }
})

test('export carries the two "only show" filters so it matches what is on screen', async () => {
  const { query, activeTab, calls, page } = createHarness()
  query.onlySiteOversell = true
  query.onlyOutOfStockListed = true
  await page.handleExport()
  activeTab.value = 'sku'
  await page.handleExport()
  for (const params of calls.exported) {
    assert.equal(params.siteOversell, 'true')
    assert.equal(params.outOfStockListed, 'true')
  }
  query.onlyOutOfStockListed = false
  await page.handleExport()
  assert.equal(calls.exported.at(-1).siteOversell, 'true')
  assert.equal(Object.hasOwn(calls.exported.at(-1), 'outOfStockListed'), false)
})

test('reset clears every filter, the selection and sorting', async () => {
  const { query, detailPage, calls, page } = createHarness()
  query.sites = ['DE']
  query.status = '断货'
  query.onlySiteOversell = true
  detailPage.sortBy = 'price_usd'
  await page.resetQuery()
  assert.deepEqual([...query.sites], [])
  assert.equal(query.status, undefined)
  assert.equal(query.onlySiteOversell, false)
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
    '售价按站点币种和领星月度企业汇率折算 USD；当月汇率未出时，沿用该币种最近一个已出月份的汇率；完全没有汇率时不折算',
    '采购成本取订单文件中的真实采购成本，未参与售价估算'
  ]) {
    assert.ok(pageSource.includes(line), `missing data-definition line: ${line}`)
  }
  assert.match(pageSource, /快照日期/)
  assert.match(pageSource, /不是实时库存/)
})

test('shared inventory warning sits in the footer and next to every cross-store view', () => {
  const line = '谷仓、成都库存按站点共享，同一站点多个店铺显示的是同一份库存，不能相加'
  // 口径说明里放第一条并加重；抽屉和展开行里也各放一次，三个店铺显示同一个库存时最容易被误加。
  assert.match(templateSource, new RegExp(`<li class="note-key">${line}</li>`))
  assert.equal(templateSource.split(line).length - 1, 3)
  assert.match(setupSource, /SHARED_STOCK_TIP = '按站点共享：同一站点多个店铺显示的是同一份库存，不能相加。'/)
})

test('data-definition wording follows the weekly goodcang snapshot', () => {
  for (const phrase of ['谷仓区域仓接口每周快照', '每周一更新', '美国两仓合计', '捷克 CZ 暂不纳入', '成都中转仓库存仍为领星周快照', '去掉 SKU 第一段']) {
    assert.ok(pageSource.includes(phrase), `missing weekly wording: ${phrase}`)
  }
  assert.doesNotMatch(pageSource, /wid 1870[0-2]|wid 18699|领星周快照的海外仓/)
  assert.doesNotMatch(pageSource, /每天|每日/)
})

// ===== 布局与接口 =====
test('layout holds together at phone width without sideways scrolling', () => {
  assert.match(styleSource, /@media \(max-width: 768px\)/)
  assert.match(styleSource, /\.filter-control,\s*\n\s*\.filter-control--status \{\s*width: 100%;/)
  // 抽屉在手机上不能超出屏幕。
  assert.match(styleSource, /\.sku-compare-drawer \{\s*max-width: 100vw;/)
  // 手机 375px 减掉 app-container 的左右内边距只剩 335px 左右，固定宽度不许超过这个值。
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
  assert.equal((apiSource.match(/^export function /gm) || []).length, 4)
})
