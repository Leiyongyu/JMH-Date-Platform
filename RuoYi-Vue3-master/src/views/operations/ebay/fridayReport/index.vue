<template>
  <div class="app-container friday-report">
    <!-- 数据时点：只保留最新一期，不留历史 -->
    <div class="filter-bar">
      <span class="f-label">当期</span>
      <span class="period-tag">{{ reportDate || '未生成' }}</span>
      <span class="f-hint">
        <template v-if="run">
          eBay 刊登拉取于 {{ run.listing_pulled_at || '--' }} · 谷仓库存拉取于 {{ run.goodcang_pulled_at || '--' }}
          · 负责人规则 {{ run.owner_rule_month || '--' }} · 生成于 {{ run.generated_at }}
        </template>
        <template v-else>每周五 06:00 自动拉取 eBay 在售刊登与谷仓库存并生成，只保留最新一期；还没有生成过时可点「重新生成」</template>
      </span>
      <el-tooltip content="页面逻辑与数据来源" placement="left">
        <button type="button" class="icon-btn help-btn" aria-label="页面逻辑与数据来源" @click="helpVisible = true">
          <app-icon name="help" :size="15" />
        </button>
      </el-tooltip>
    </div>

    <!-- 指标：点击直接筛出对应的行 -->
    <div v-if="summary" class="kpis">
      <button v-for="kpi in kpis" :key="kpi.key" type="button" class="kpi" :class="{ active: isKpiActive(kpi) }"
        @click="applyKpi(kpi)">
        <span class="kpi-lb">{{ kpi.label }}</span>
        <span class="kpi-vl" :class="kpi.tone">{{ formatNumber(kpi.value) }}<small>{{ kpi.unit }}</small></span>
        <span class="kpi-dt">{{ kpi.note }}</span>
      </button>
    </div>

    <div class="table-card">
      <div class="tc-head">
        <div>
          <div class="tc-title">周五数据<template v-if="reportDate"> · {{ reportDate }}</template></div>
          <div class="tc-sub">{{ subtitle }}</div>
        </div>
        <div class="tc-actions">
          <div class="chips" role="tablist" aria-label="报表">
            <button v-for="item in views" :key="item.value" type="button" class="chip"
              :class="{ active: view === item.value }" role="tab" :aria-selected="view === item.value"
              @click="switchView(item.value)">{{ item.label }}</button>
          </div>
          <span v-hasPermi="['operations:ebayFridayReport:edit']" class="action-entry">
            <icon-btn icon="store" tooltip="店铺主站点" size="md" @click="openStores" />
            <icon-btn icon="resync" tooltip="用当前 eBay 刊登与谷仓快照重新生成今天这一期" size="md"
              :loading="generating" @click="handleGenerate" />
          </span>
          <span v-hasPermi="['operations:ebayFridayReport:export']" class="action-entry">
            <icon-btn icon="export" tooltip="导出 Excel（有货无货、海外仓库存；已上传订单时附订单售出统计）" size="md"
              :loading="exporting" :disabled="!reportDate" @click="handleExport" />
          </span>
        </div>
      </div>

      <!-- 字段网格筛选（订单售出统计没有筛选） -->
      <div v-if="view !== 'orders'" class="filters">
        <div class="field wide">
          <label>{{ view === 'listing' ? 'SKU / Item Number' : 'SKU / 谷仓商品编码' }}</label>
          <el-input v-model="query.keyword" clearable placeholder="模糊搜索" @keyup.enter="search" @clear="search" />
        </div>
        <div class="field">
          <label>站点</label>
          <el-select v-model="query.site" clearable placeholder="全部站点" @change="search">
            <el-option v-for="site in sites" :key="site" :label="site" :value="site" />
          </el-select>
        </div>
        <div v-if="view === 'listing'" class="field">
          <label>eBay 账号</label>
          <el-select v-model="query.storeName" clearable filterable placeholder="全部账号" @change="search">
            <el-option v-for="name in options.stores || []" :key="name" :label="name" :value="name" />
          </el-select>
        </div>
        <div v-else class="field">
          <label>品牌</label>
          <el-select v-model="query.brand" clearable filterable placeholder="全部品牌" @change="search">
            <el-option v-for="name in options.brands || []" :key="name" :label="name" :value="name" />
          </el-select>
        </div>
        <div class="field">
          <label>负责人</label>
          <el-select v-model="query.principalName" clearable filterable placeholder="全部负责人" @change="search">
            <el-option v-for="name in options.principals || []" :key="name" :label="name" :value="name" />
          </el-select>
        </div>
        <div class="field">
          <label>标记</label>
          <el-select v-model="query.flag" clearable placeholder="全部" @change="search">
            <el-option v-for="item in flagOptions" :key="item.value" :label="item.label" :value="item.value" />
          </el-select>
        </div>
        <div class="filter-actions">
          <el-button text @click="resetQuery">重置</el-button>
          <el-button type="primary" @click="search">查询</el-button>
        </div>
      </div>

      <!-- 有货无货 -->
      <!-- 两张表各带固定 key：切换时重新创建，避免复用同一个 el-table 实例残留上一张表的列与高度。 -->
      <el-table v-if="view === 'listing'" key="listing-table" v-loading="loading" class="report-table" :data="rows" max-height="620"
        empty-text="暂无数据" @sort-change="handleSort">
        <el-table-column label="Item Number" prop="item_id" min-width="128" fixed="left" />
        <el-table-column label="SKU" prop="sku" min-width="170" fixed="left" sortable="custom" show-overflow-tooltip>
          <template #default="{ row }"><span class="sku">{{ row.sku || '--' }}</span></template>
        </el-table-column>
        <el-table-column label="eBay账号" prop="store_name" min-width="150" sortable="custom" show-overflow-tooltip />
        <el-table-column label="在线库存" prop="online_qty" width="96" align="right" sortable="custom">
          <template #default="{ row }"><span class="v">{{ formatNumber(row.online_qty) }}</span></template>
        </el-table-column>
        <el-table-column label="历史售出" prop="sold_qty" width="96" align="right" sortable="custom">
          <template #default="{ row }"><span class="v">{{ formatNumber(row.sold_qty) }}</span></template>
        </el-table-column>
        <el-table-column label="eBay站点" prop="listing_site" width="86" />
        <el-table-column label="上架时间" prop="start_time" width="162" sortable="custom" />
        <el-table-column label="品牌" prop="brand" width="70" />
        <el-table-column label="中间码" prop="mid_code" width="84" />
        <el-table-column label="站点" width="72">
          <template #default="{ row }"><span class="site-tag">{{ row.site }}</span></template>
        </el-table-column>
        <el-table-column label="负责人" prop="principal_name" width="90" />
        <el-table-column label="二手" width="72">
          <template #default="{ row }"><span v-if="row.is_used" class="jb-pill jb-pill--warn">是</span><span v-else class="muted">否</span></template>
        </el-table-column>
        <el-table-column label="海外仓实际库存" prop="overseas_stock" width="128" align="right" sortable="custom">
          <template #default="{ row }">
            <span class="v" :class="{ neg: row.online_qty > 0 && row.overseas_stock <= 0 }">{{ formatNumber(row.overseas_stock) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="规划站点" width="84">
          <template #default="{ row }">{{ row.plan_site || '--' }}</template>
        </el-table-column>
        <el-table-column label="判断" width="76" fixed="right">
          <template #default="{ row }">
            <span v-if="row.judge === 'T'" class="jb-pill jb-pill--ok">T</span>
            <span v-else-if="row.judge === 'F'" class="jb-pill jb-pill--danger">F</span>
            <span v-else class="jb-pill jb-pill--info">未配置</span>
          </template>
        </el-table-column>
      </el-table>

      <!-- 海外仓库存 -->
      <el-table v-else-if="view === 'stock'" key="stock-table" v-loading="loading" class="report-table" :data="rows" max-height="620" empty-text="暂无数据"
        @sort-change="handleSort">
        <el-table-column label="商品编码" prop="product_sku" min-width="160" fixed="left" show-overflow-tooltip />
        <el-table-column label="SKU" prop="sku" min-width="160" fixed="left" sortable="custom" show-overflow-tooltip>
          <template #default="{ row }"><span class="sku">{{ row.sku }}</span></template>
        </el-table-column>
        <el-table-column label="品牌" prop="brand" width="70">
          <template #default="{ row }">{{ row.brand || '--' }}</template>
        </el-table-column>
        <el-table-column label="中间码" prop="mid_code" width="84" />
        <el-table-column label="站点" width="72">
          <template #default="{ row }"><span class="site-tag">{{ row.site }}</span></template>
        </el-table-column>
        <el-table-column label="仓库" prop="warehouse_desc" width="90" sortable="custom" />
        <el-table-column v-for="col in stockNumberColumns" :key="col.key" :label="col.label" :prop="col.key"
          :width="col.width" align="right" :sortable="col.sortable ? 'custom' : false">
          <template #default="{ row }"><span class="v">{{ formatNumber(row[col.key]) }}</span></template>
        </el-table-column>
        <el-table-column label="是否二手" width="86">
          <template #default="{ row }"><span v-if="row.is_used" class="jb-pill jb-pill--warn">是</span><span v-else class="muted">否</span></template>
        </el-table-column>
        <el-table-column label="海外仓有货无在线链接" width="160">
          <template #default="{ row }"><span v-if="row.no_link" class="jb-pill jb-pill--danger">无链接</span></template>
        </el-table-column>
        <el-table-column label="负责人" prop="principal_name" width="90">
          <template #default="{ row }">{{ row.principal_name || '--' }}</template>
        </el-table-column>
        <el-table-column label="商品中文名称" prop="product_title" min-width="150" show-overflow-tooltip />
        <el-table-column v-for="group in storeGroups" :key="group.site" :label="`${group.site} 店铺`" align="center">
          <el-table-column v-for="store in group.stores" :key="store.key" :label="store.name" min-width="150">
            <template #default="{ row }">
              <span v-if="row.store_items?.[store.key]" class="store-items">
                <span v-for="item in splitItems(row.store_items[store.key])" :key="item"
                  :class="{ 'store-item--wrong': item.includes(':') }"
                  :title="item.includes(':') ? '这条链接所在店铺的主站点与站点不一致，冒号后为历史售出' : ''">{{ item }}</span>
              </span>
            </template>
          </el-table-column>
        </el-table-column>
      </el-table>

      <!-- 订单售出统计：手动上传数字酋长订单导出，只看透视 -->
      <div v-else key="orders-block" v-loading="ordersLoading" class="orders-block">
        <div class="orders-bar">
          <div class="orders-meta">
            <template v-if="orderSales?.upload">
              <span><b>{{ orderSales.upload.file_name }}</b></span>
              <span>付款时间 {{ shortTime(orderSales.upload.pay_time_from) }} ~ {{ shortTime(orderSales.upload.pay_time_to) }}</span>
              <span>eBay 订单行 {{ formatNumber(orderSales.upload.used_rows) }} / 文件 {{ formatNumber(orderSales.upload.source_rows) }}</span>
              <span v-if="excludedText">已排除 {{ excludedText }}</span>
              <span>{{ orderSales.upload.uploaded_by || '--' }} 上传于 {{ orderSales.upload.uploaded_at }}</span>
            </template>
            <span v-else class="muted">还没有上传订单；上传数字酋长「Order-交易级别」导出后按负责人出透视</span>
          </div>
          <el-upload v-hasPermi="['operations:ebayFridayReport:edit']" :show-file-list="false" accept=".xlsx"
            :http-request="handleOrderUpload" :disabled="uploading">
            <el-button type="primary" :loading="uploading">
              <app-icon name="upload" :size="15" class="btn-icon" />{{ orderSales?.upload ? '重新上传' : '上传订单' }}
            </el-button>
          </el-upload>
        </div>
        <el-table v-if="orderSales?.upload" class="report-table orders-table" :data="orderRows"
          :row-class-name="orderRowClass" empty-text="暂无数据">
          <el-table-column label="负责人" prop="principal_name" min-width="140">
            <template #default="{ row }"><span :class="row.isTotal ? 'sum-label' : 'sku'">{{ row.principal_name }}</span></template>
          </el-table-column>
          <el-table-column label="非重复计数项:中间码+站点" min-width="200" align="right">
            <template #default="{ row }"><span class="v">{{ formatNumber(row.distinct_mid_site) }}</span></template>
          </el-table-column>
          <el-table-column label="求和项:美金收入" min-width="180" align="right">
            <template #default="{ row }"><span class="v">{{ formatMoney(row.usd_income) }}</span></template>
          </el-table-column>
          <el-table-column label="求和项:购买数量" min-width="160" align="right">
            <template #default="{ row }"><span class="v">{{ formatNumber(row.quantity) }}</span></template>
          </el-table-column>
        </el-table>
      </div>

      <div class="tc-foot">
        <span>{{ footNote }}</span>
        <pagination v-if="view !== 'orders'" v-show="total > 0" :total="total" v-model:page="query.pageNum"
          v-model:limit="query.pageSize" @pagination="loadRows" />
      </div>
    </div>

    <!-- 店铺主站点 -->
    <el-dialog v-model="storeVisible" title="eBay 店铺主站点" width="820px" append-to-body>
      <div class="dialog-note">
        「有货无货」的规划站点、「海外仓库存」的店铺列都取这里；店铺名不区分大小写和符号匹配（autoteilefastship = autoteile-fast-ship）。
        修改后点「重新生成」或等下周五自动生成才会生效。
      </div>
      <el-table :data="stores" size="small" max-height="360" class="report-table">
        <el-table-column label="店铺" prop="store_name" min-width="160" />
        <el-table-column label="主站点" prop="main_site" width="80" />
        <el-table-column label="第二站点" width="86">
          <template #default="{ row }">{{ row.second_site || '--' }}</template>
        </el-table-column>
        <el-table-column label="备注" prop="note" min-width="170" show-overflow-tooltip />
        <el-table-column label="维护人" width="90">
          <template #default="{ row }">{{ row.updated_by || '--' }}</template>
        </el-table-column>
        <el-table-column label="操作" width="110" align="center">
          <template #default="{ row }">
            <el-button link type="primary" @click="editStore(row)">修改</el-button>
            <el-button link type="danger" @click="removeStore(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
      <el-form ref="storeFormRef" :model="storeForm" :rules="storeRules" label-width="76px" class="store-form" @submit.prevent>
        <div class="store-form__title">{{ storeForm.originalKey ? '修改店铺' : '新增店铺' }}</div>
        <el-row :gutter="12">
          <el-col :span="9">
            <el-form-item label="店铺名" prop="storeName"><el-input v-model="storeForm.storeName" placeholder="与 eBay 账号一致" /></el-form-item>
          </el-col>
          <el-col :span="5">
            <el-form-item label="主站点" prop="mainSite">
              <el-select v-model="storeForm.mainSite"><el-option v-for="site in sites" :key="site" :label="site" :value="site" /></el-select>
            </el-form-item>
          </el-col>
          <el-col :span="5">
            <el-form-item label="第二站点">
              <el-select v-model="storeForm.secondSite" clearable><el-option v-for="site in sites" :key="site" :label="site" :value="site" /></el-select>
            </el-form-item>
          </el-col>
          <el-col :span="5">
            <el-form-item label="排序"><el-input-number v-model="storeForm.sortOrder" :min="0" :controls="false" class="full" /></el-form-item>
          </el-col>
        </el-row>
        <el-form-item label="备注"><el-input v-model="storeForm.note" maxlength="255" placeholder="如：关店、后续不上英国链接" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button v-if="storeForm.originalKey" text @click="resetStoreForm">取消修改</el-button>
        <el-button type="primary" :loading="storeSaving" @click="submitStore">{{ storeForm.originalKey ? '保存修改' : '新增' }}</el-button>
      </template>
    </el-dialog>

    <!-- 页面逻辑与数据来源 -->
    <el-drawer v-model="helpVisible" title="周五数据 · 逻辑与数据来源" size="640px" append-to-body>
      <div class="help">
        <section class="help-sec">
          <div class="help-h">数据来源</div>
          <div class="help-kv">
            <div v-for="item in sourceInfo" :key="item.label"><span>{{ item.label }}</span><b>{{ item.value }}</b></div>
          </div>
        </section>
        <section v-for="sheet in sheetRules" :key="sheet.title" class="help-sec">
          <div class="help-h">{{ sheet.title }}</div>
          <el-table :data="sheet.rows" size="small" class="help-table">
            <el-table-column label="列" prop="label" width="130" />
            <el-table-column label="口径" prop="note" min-width="320" />
          </el-table>
        </section>
      </div>
    </el-drawer>
  </div>
</template>

<script setup name="EbayFridayReport">
import { computed, getCurrentInstance, onMounted, reactive, ref } from 'vue'
import { sheetRules, sourceInfo } from './help'
import {
  deleteFridayReportStore, exportFridayReport, generateFridayReport, getFridayOrderSales, getFridayReportOverview,
  importFridayOrderSales, listFridayReportListings, listFridayReportStocks, saveFridayReportStore
} from '@/api/operations/ebay/fridayReport'

const { proxy } = getCurrentInstance()
const sites = ['DE', 'UK', 'US']
const views = [
  { value: 'listing', label: '有货无货' },
  { value: 'stock', label: '海外仓库存' },
  { value: 'orders', label: '订单售出统计' }
]
const FLAGS = {
  listing: [
    { value: 'mismatch', label: '站点不符（F）' },
    { value: 'no_stock', label: '在线有货 · 海外仓无货' },
    { value: 'no_plan', label: '店铺未配置主站点' },
    { value: 'used', label: '二手 SKU' }
  ],
  stock: [
    { value: 'no_link', label: '有货无在线链接' },
    { value: 'no_brand', label: '品牌未匹配' },
    { value: 'used', label: '二手 SKU' }
  ]
}
const stockNumberColumns = [
  { key: 'sellable', label: '良品可售', width: 96, sortable: true },
  { key: 'onway', label: '海外在途', width: 96, sortable: true },
  { key: 'total_onway', label: '总在途', width: 84 },
  { key: 'transfer_onway', label: '中转在途', width: 90 },
  { key: 'reserved', label: '待出库/预占', width: 104 },
  { key: 'shipped', label: '良品已出库', width: 100 },
  { key: 'freeze', label: '冻结', width: 70 }
]

const reportDate = ref('')
const overview = ref(null)
const view = ref('listing')
const rows = ref([])
const total = ref(0)
const loading = ref(false)
const exporting = ref(false)
const generating = ref(false)
const helpVisible = ref(false)
const query = reactive(emptyQuery())

function emptyQuery() {
  return { keyword: '', site: '', storeName: '', brand: '', principalName: '', flag: '', sortField: '', sortOrder: '', pageNum: 1, pageSize: 50 }
}

const run = computed(() => overview.value?.run || null)
const summary = computed(() => overview.value?.summary || null)
const options = computed(() => overview.value?.options || {})
const stores = computed(() => overview.value?.stores || [])
const flagOptions = computed(() => FLAGS[view.value])
const storeGroups = computed(() => sites
  .map(site => ({ site, stores: (overview.value?.store_columns || []).filter(store => store.main_site === site) }))
  .filter(group => group.stores.length))

const kpis = computed(() => {
  const s = summary.value || {}
  return [
    { key: 'listing', view: 'listing', flag: '', label: '在线 listing', value: s.listing_count, unit: '条', note: `${(overview.value?.store_columns || []).length} 个店铺`, tone: '' },
    { key: 'mismatch', view: 'listing', flag: 'mismatch', label: '站点不符（F）', value: s.site_mismatch, unit: '条', note: '店铺主站点 ≠ listing 站点', tone: 'danger' },
    { key: 'no_stock', view: 'listing', flag: 'no_stock', label: '在线有货 · 海外仓无货', value: s.online_without_stock, unit: '条', note: '在线库存 > 0 且海外仓实际库存为 0', tone: 'warn' },
    { key: 'no_link', view: 'stock', flag: 'no_link', label: '海外仓有货无链接', value: s.stock_no_link, unit: '行', note: `海外仓库存共 ${formatNumber(s.stock_rows)} 行`, tone: 'warn' }
  ]
})

const subtitle = computed(() => {
  if (view.value === 'orders') return '按负责人汇总上传的 eBay 订单：中间码 + 站点去重个数、美金收入、购买数量；只保留最新一次上传'
  if (!reportDate.value) return '还没有生成过周五数据'
  return view.value === 'listing'
    ? '每条在线 listing 一行：站点、负责人、海外仓实际库存（中间码 + 站点 + 是否二手汇总谷仓良品可售）与规划站点判断'
    : '谷仓良品可售 > 0 的每一行：谷仓库存字段 + 各店铺同站点同 SKU 的链接，「Item:数字」为挂错站点的链接（数字为历史售出）'
})
const footNote = computed(() => view.value === 'orders'
  ? '美金收入 = 收入 × 订单汇率 ÷ 领星当月美元汇率' + usdRateText.value + '；负责人按当月飞书负责人规则；作废、退款订单照原表一起算'
  : view.value === 'listing'
  ? '判断 T：listing 站点与店铺主站点一致；F：不一致；未配置：店铺还没有维护主站点'
  : '店铺列按店铺主站点分组；没有任何同站点链接的 SKU 标「无链接」')

function formatNumber(value) {
  if (value === null || value === undefined || value === '') return '--'
  return Number(value).toLocaleString('zh-CN')
}

function splitItems(text) {
  return String(text || '').split(/[、,]/).map(item => item.trim()).filter(Boolean)
}

function isKpiActive(kpi) {
  return kpi.flag && view.value === kpi.view && query.flag === kpi.flag
}

// 切换表之前先清空数据：两张表的行结构不同，不能让新表拿旧表的行渲染。
function changeView(value) {
  if (view.value !== value) {
    rows.value = []
    total.value = 0
  }
  view.value = value
}

function applyKpi(kpi) {
  Object.assign(query, emptyQuery(), { flag: kpi.flag })
  changeView(kpi.view)
  loadRows()
}

function switchView(value) {
  if (view.value === value) return
  changeView(value)
  Object.assign(query, emptyQuery())
  if (value === 'orders') loadOrders()
  else loadRows()
}

// ---------------- 订单售出统计
const orderSales = ref(null)
const ordersLoading = ref(false)
const uploading = ref(false)
const orderRows = computed(() => orderSales.value?.upload
  ? [...(orderSales.value.rows || []), { ...orderSales.value.total, isTotal: true }]
  : [])
const excludedText = computed(() => Object.entries(orderSales.value?.upload?.excluded || {})
  .map(([reason, count]) => `${reason} ${count} 行`).join('，'))
const usdRateText = computed(() => {
  const months = Object.entries(orderSales.value?.usd_rate_months || {})
  return months.length ? `（${months.map(([month, info]) => `${month} 用 ${info.rate_month} 的 ${info.rate}`).join('，')}）` : ''
})

function orderRowClass({ row }) {
  return row.isTotal ? 'report-total-row' : ''
}

function formatMoney(value) {
  if (value === null || value === undefined || value === '') return '--'
  return Number(value).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function shortTime(value) {
  return value ? String(value).slice(0, 16) : '--'
}

async function loadOrders() {
  ordersLoading.value = true
  try {
    const response = await getFridayOrderSales()
    orderSales.value = response.data || null
  } finally {
    ordersLoading.value = false
  }
}

async function handleOrderUpload({ file }) {
  uploading.value = true
  try {
    const response = await importFridayOrderSales(file)
    proxy.$modal.msgSuccess(`已上传：eBay 订单行 ${response.data?.used_rows ?? '--'} 条`)
    await loadOrders()
  } finally {
    uploading.value = false
  }
}

function search() {
  query.pageNum = 1
  loadRows()
}

function resetQuery() {
  Object.assign(query, emptyQuery())
  loadRows()
}

function handleSort({ prop, order }) {
  query.sortField = order ? prop : ''
  query.sortOrder = order || ''
  search()
}

async function loadOverview() {
  const response = await getFridayReportOverview()
  overview.value = response.data || null
  reportDate.value = overview.value?.report_date || ''
}

// 只采用最后一次请求的结果：快速切换标签时，慢回来的上一张表数据不能覆盖当前表。
let rowsRequest = 0

async function loadRows() {
  const request = ++rowsRequest
  if (!reportDate.value) {
    rows.value = []
    total.value = 0
    return
  }
  loading.value = true
  try {
    const params = { reportDate: reportDate.value }
    Object.entries(query).forEach(([key, value]) => {
      if (value !== '' && value !== null && value !== undefined) params[key] = value
    })
    if (view.value === 'listing') delete params.brand
    else delete params.storeName
    const response = view.value === 'listing' ? await listFridayReportListings(params) : await listFridayReportStocks(params)
    if (request !== rowsRequest) return
    rows.value = response.data?.items || []
    total.value = Number(response.data?.total || 0)
  } finally {
    if (request === rowsRequest) loading.value = false
  }
}

async function loadAll() {
  Object.assign(query, emptyQuery())
  await loadOverview()
  await loadRows()
}

async function handleGenerate() {
  await proxy.$modal.confirm('用系统当前的 eBay 在售刊登与谷仓库存快照重新生成今天这一期？不会重新拉取接口。')
  generating.value = true
  try {
    const response = await generateFridayReport()
    proxy.$modal.msgSuccess(`已生成 ${response.data?.report_date || ''}`)
    reportDate.value = response.data?.report_date || ''
    await loadAll()
  } finally {
    generating.value = false
  }
}

async function handleExport() {
  exporting.value = true
  try {
    const data = await exportFridayReport(reportDate.value)
    const blob = data instanceof Blob ? data : new Blob([data], { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = `周五数据-${reportDate.value}.xlsx`
    document.body.appendChild(link)
    link.click()
    link.remove()
    URL.revokeObjectURL(url)
    proxy.$modal.msgSuccess('导出成功')
  } catch (error) {
    const responseData = error?.response?.data
    const message = responseData instanceof Blob ? await responseData.text() : String(responseData?.msg || error?.message || '导出失败')
    proxy.$modal.msgError(message || '导出失败')
  } finally {
    exporting.value = false
  }
}

// ---------------- 店铺主站点
const storeVisible = ref(false)
const storeSaving = ref(false)
const storeFormRef = ref()
const storeForm = reactive({ originalKey: '', storeName: '', mainSite: '', secondSite: '', note: '', sortOrder: 0 })
const storeRules = {
  storeName: [{ required: true, message: '请填写店铺名', trigger: 'blur' }],
  mainSite: [{ required: true, message: '请选择主站点', trigger: 'change' }]
}

function resetStoreForm() {
  Object.assign(storeForm, { originalKey: '', storeName: '', mainSite: '', secondSite: '', note: '', sortOrder: 0 })
  storeFormRef.value?.clearValidate()
}

function openStores() {
  resetStoreForm()
  storeVisible.value = true
}

function editStore(row) {
  Object.assign(storeForm, {
    originalKey: row.store_key, storeName: row.store_name, mainSite: row.main_site,
    secondSite: row.second_site || '', note: row.note || '', sortOrder: Number(row.sort_order || 0)
  })
}

async function submitStore() {
  await storeFormRef.value.validate()
  storeSaving.value = true
  try {
    await saveFridayReportStore({ ...storeForm })
    proxy.$modal.msgSuccess('已保存，重新生成后生效')
    resetStoreForm()
    await loadOverview()
  } finally {
    storeSaving.value = false
  }
}

async function removeStore(row) {
  await proxy.$modal.confirm(`确认删除店铺「${row.store_name}」的主站点配置？`)
  await deleteFridayReportStore(row.store_key)
  proxy.$modal.msgSuccess('已删除')
  if (storeForm.originalKey === row.store_key) resetStoreForm()
  await loadOverview()
}

onMounted(loadAll)
</script>

<style scoped>
.friday-report {
  --sky-50: #f4f8ff;
  --sky-100: #e7efff;
  --sky-300: #a9c6f4;
  --sky-600: #1257d6;
  --sky-700: #0e45a8;
  --ink-900: #0b1526;
  --ink-700: #24334a;
  --ink-500: #5a6b85;
  --ink-400: #8a99b0;
  --line: #e3e9f2;
  --radius: 14px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.filter-bar {
  background: #fff;
  border: 1px solid var(--line);
  border-radius: var(--radius);
  padding: 14px 18px;
  display: flex;
  align-items: center;
  gap: 14px;
  flex-wrap: wrap;
  box-shadow: 0 2px 10px rgba(13, 26, 45, .06);
}
.f-label { font-size: 13.5px; color: var(--ink-700); font-weight: 500; }
.f-hint { font-size: 12px; color: var(--ink-400); }
.period-tag { font-size: 13px; font-weight: 600; color: var(--sky-700); background: var(--sky-50); border-radius: 6px; padding: 3px 10px; font-variant-numeric: tabular-nums; }
.help-btn { margin-left: auto; color: #1257d6; }

.kpis { display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; }
.kpi {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 4px;
  padding: 12px 14px 13px;
  background: #fff;
  border: 1px solid var(--line);
  border-radius: 10px;
  font-family: inherit;
  text-align: left;
  cursor: pointer;
  transition: border-color .15s, box-shadow .15s;
}
.kpi:hover { border-color: var(--sky-300); }
.kpi.active { border-color: var(--sky-600); box-shadow: 0 0 0 1px var(--sky-600) inset; }
.kpi-lb { font-size: 11.5px; color: var(--ink-500); }
.kpi-vl { font-size: 21px; font-weight: 600; color: var(--ink-900); letter-spacing: -.4px; line-height: 1.2; font-variant-numeric: tabular-nums; }
.kpi-vl small { font-size: 11px; color: var(--ink-400); font-weight: 500; margin-left: 3px; }
.kpi-vl.danger { color: #dc2626; }
.kpi-vl.warn { color: #d97706; }
.kpi-dt { font-size: 11.5px; color: var(--ink-400); }

.table-card {
  background: #fff;
  border: 1px solid var(--line);
  border-radius: var(--radius);
  box-shadow: 0 2px 10px rgba(13, 26, 45, .06);
  overflow: hidden;
}
.tc-head { display: flex; align-items: center; gap: 16px; padding: 14px 18px; border-bottom: 1px solid var(--line); flex-wrap: wrap; }
.tc-title { font-size: 14.5px; font-weight: 650; color: var(--ink-900); }
.tc-sub { font-size: 12px; color: var(--ink-400); margin-top: 4px; max-width: 760px; }
.tc-actions { margin-left: auto; display: flex; align-items: center; gap: 6px; }
.action-entry { display: inline-flex; gap: 6px; }
.chips { display: inline-flex; align-items: center; gap: 3px; background: #f5f8fd; border: 1px solid var(--line); border-radius: 9px; padding: 3px; margin-right: 4px; }
.chip { font-size: 12.5px; font-weight: 500; font-family: inherit; padding: 5px 14px; border-radius: 7px; border: none; background: transparent; color: var(--ink-500); cursor: pointer; white-space: nowrap; }
.chip:hover { color: var(--sky-600); background: #fff; }
.chip.active { background: #fff; color: var(--sky-700); box-shadow: 0 1px 4px rgba(18, 87, 214, .22); font-weight: 600; }
.icon-btn { width: 34px; height: 34px; border-radius: 9px; display: inline-flex; align-items: center; justify-content: center; border: 1px solid var(--line); background: #fff; cursor: pointer; }
.icon-btn:hover { border-color: var(--sky-300); background: var(--sky-50); }

.filters { display: flex; gap: 10px 14px; flex-wrap: wrap; align-items: flex-end; padding: 14px 18px; border-bottom: 1px solid var(--line); }
.field { display: flex; flex-direction: column; gap: 5px; min-width: 140px; }
.field.wide { min-width: 220px; }
.field label { font-size: 11.5px; color: var(--ink-500); font-weight: 500; }
.filter-actions { margin-left: auto; display: flex; gap: 8px; }

.report-table {
  --el-table-border-color: var(--jb-line, #e3e9f2);
  --el-table-header-bg-color: #f7f9fc;
  --el-table-row-hover-bg-color: #f7faff;
  --el-table-text-color: var(--ink-700);
  --el-table-header-text-color: var(--ink-500);
  font-size: 12.5px;
}
.report-table :deep(th.el-table__cell) { font-size: 11.5px; font-weight: 600; }
.report-table :deep(.el-table__cell) { padding: 9px 0; }
.v { font-variant-numeric: tabular-nums; }
.v.neg { color: #dc2626; font-weight: 600; }
.sku { color: var(--ink-900); font-weight: 500; }
.muted { color: var(--ink-400); }
.site-tag { display: inline-block; padding: 0 7px; line-height: 20px; border-radius: 999px; font-size: 11px; font-weight: 500; color: var(--sky-600); background: var(--sky-50); }
.orders-block { padding: 14px 18px 4px; }
.orders-bar { display: flex; align-items: center; gap: 16px; margin-bottom: 12px; flex-wrap: wrap; }
.orders-meta { display: flex; flex-wrap: wrap; gap: 4px 16px; font-size: 12px; color: var(--ink-500); flex: 1; min-width: 0; }
.orders-meta b { color: var(--ink-900); font-weight: 600; }
.orders-table { max-width: 820px; }
.orders-table :deep(.report-total-row) { background: #eef3fd; font-weight: 600; }
.sum-label { font-weight: 650; color: var(--ink-900); }
.btn-icon { margin-right: 5px; vertical-align: -2px; }
.store-items { display: flex; flex-wrap: wrap; gap: 2px 8px; font-variant-numeric: tabular-nums; }
.store-item--wrong { color: #a85c05; background: #fef4e6; border-radius: 4px; padding: 0 4px; }
.tc-foot { display: flex; justify-content: space-between; align-items: center; gap: 12px; padding: 6px 18px; font-size: 12px; color: var(--ink-400); border-top: 1px solid var(--line); flex-wrap: wrap; }
.tc-foot :deep(.pagination-container) { margin: 0; padding: 6px 0; }

.dialog-note { font-size: 12.5px; color: var(--ink-500); line-height: 1.7; margin-bottom: 10px; }
.store-form { margin-top: 14px; padding-top: 12px; border-top: 1px dashed var(--line); }
.store-form__title { font-size: 13px; font-weight: 600; color: var(--ink-700); margin-bottom: 10px; }
.full { width: 100%; }

/* 说明抽屉挂在 body 下，取不到页面根上的 CSS 变量，颜色直接写值。 */
.help { display: flex; flex-direction: column; gap: 18px; padding: 0 4px 12px; color: #24334a; font-size: 13px; }
.help-h { font-size: 14px; font-weight: 650; color: #0b1526; margin-bottom: 8px; padding-left: 8px; border-left: 3px solid #1257d6; }
.help-kv { display: flex; flex-direction: column; gap: 6px; }
.help-kv > div { display: flex; gap: 12px; line-height: 1.6; }
.help-kv span { flex: 0 0 100px; color: #5a6b85; }
.help-kv b { font-weight: 500; color: #0b1526; }

@media (max-width: 1100px) {
  .kpis { grid-template-columns: repeat(2, 1fr); }
}
</style>
