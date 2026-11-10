<template>
  <div class="app-container ebay-price-analysis">
    <!-- ===== 页头 ===== -->
    <el-card shadow="never" class="head-card">
      <div class="head-top">
        <div class="head-title">
          <h2>价格分析</h2>
          <p class="head-meta">
            <span class="meta-item">
              快照日期
              <strong>{{ displayValue(overview.stat_date) }}</strong>
            </span>
            <span class="meta-sep">·</span>
            <span class="meta-item">
              刷新时间
              <strong>{{ displayValue(overview.refreshed_at) }}</strong>
            </span>
            <span class="meta-sep">·</span>
            <span class="meta-item">eBay 在售刊登 × 谷仓海外仓库存</span>
          </p>
        </div>
        <div class="head-acts">
          <!-- 只重新读看板表；生产数据由 ERP 定时任务负责，页面不触发同步 -->
          <el-button :disabled="loading" @click="handleQuery">
            <svg-icon icon-class="jmh-refresh" class="report-icon" :class="{ spinning: loading }" />刷新
          </el-button>
          <el-tooltip
            content="导出当前筛选下全部记录，仅包含角色授权的导出字段；不受分页或页面隐藏列限制"
            placement="top"
          >
            <el-button
              type="warning"
              plain
              :loading="exporting"
              :disabled="loading"
              v-hasPermi="['operations:ebayPriceAnalysis:export']"
              @click="handleExport"
            >
              <svg-icon v-if="!exporting" icon-class="jmh-export" class="report-icon" />导出明细
            </el-button>
          </el-tooltip>
        </div>
      </div>

      <el-alert type="info" :closable="false" show-icon class="snapshot-alert">
        <template #title>
          看板展示 {{ displayValue(overview.stat_date) }} 的快照：eBay 侧为在售刊登快照，
          谷仓侧为领星周快照的海外仓可售量，均<strong>不是实时库存</strong>。
        </template>
      </el-alert>

      <el-form :model="query" inline class="filter-form" label-width="56px">
        <el-form-item label="站点">
          <el-select
            v-model="query.sites"
            multiple
            collapse-tags
            collapse-tags-tooltip
            clearable
            placeholder="全部站点"
            class="filter-control"
            @change="handleQuery"
          >
            <el-option v-for="site in siteOptions" :key="site" :label="site" :value="site" />
          </el-select>
        </el-form-item>
        <el-form-item label="店铺">
          <el-select
            v-model="query.accounts"
            multiple
            filterable
            collapse-tags
            collapse-tags-tooltip
            clearable
            placeholder="全部店铺"
            class="filter-control"
            @change="handleQuery"
          >
            <el-option v-for="account in accountOptions" :key="account" :label="account" :value="account" />
          </el-select>
        </el-form-item>
        <el-form-item label="状态">
          <el-select
            v-model="query.status"
            clearable
            placeholder="全部状态"
            class="filter-control filter-control--status"
            @change="handleQuery"
          >
            <el-option v-for="status in statusOptions" :key="status" :label="status" :value="status" />
          </el-select>
        </el-form-item>
        <el-form-item label="关键词">
          <el-input
            v-model="query.keyword"
            clearable
            placeholder="SKU / 标题 / Item ID"
            class="filter-control"
            @clear="handleQuery"
            @keyup.enter="handleQuery"
          />
        </el-form-item>
        <el-form-item label-width="0">
          <el-button type="primary" icon="Search" @click="handleQuery">搜索</el-button>
          <el-button icon="Refresh" @click="resetQuery">重置</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <!-- ===== KPI 行 ===== -->
    <div v-loading="loading" class="kpi-grid">
      <div
        v-for="kpi in kpiCards"
        :key="kpi.key"
        class="kpi-card"
        :class="[`kpi-card--${kpiTone(kpi)}`, { 'is-clickable': kpiStatus(kpi), 'is-active': kpiStatus(kpi) && query.status === kpiStatus(kpi) }]"
        @click="handleKpiClick(kpi)"
      >
        <span class="kpi-label">{{ kpi.label }}</span>
        <strong class="kpi-value">{{ kpiText(kpi) }}</strong>
        <span class="kpi-unit">{{ kpi.unit || '' }}</span>
      </div>
      <el-empty v-if="!kpiCards.length" description="暂无指标数据" class="kpi-empty" />
    </div>

    <!-- ===== 主图区 ===== -->
    <div class="chart-grid">
      <el-card shadow="never" class="chart-card">
        <template #header>
          <div class="card-head">
            <div class="card-head__text">
              <span class="card-title">店铺库存对比</span>
              <small>eBay 可售 vs 谷仓可售；点击柱体按该店铺筛选，再点一次取消</small>
            </div>
            <el-tag type="info" effect="plain">{{ storeCompare.length }} 组</el-tag>
          </div>
        </template>
        <div ref="storeChartRef" class="chart-box"></div>
        <el-empty v-if="!storeCompare.length && !loading" description="暂无店铺数据" :image-size="60" />
      </el-card>

      <el-card shadow="never" class="chart-card">
        <template #header>
          <div class="card-head">
            <div class="card-head__text">
              <span class="card-title">价格 × 库存象限</span>
              <small>气泡越大 = eBay 可售越多；虚线为售价与谷仓库存中位数</small>
            </div>
            <div class="card-head__acts">
              <el-tooltip
                v-if="overview.scatter_sampled"
                content="点数超过 2000，后端已抽样，图上不是全量数据；明细表仍是全量"
                placement="top"
              >
                <el-tag type="warning" effect="dark">已抽样</el-tag>
              </el-tooltip>
              <el-select v-model="query.dimension" class="dimension-select" @change="handleDimensionChange">
                <el-option label="按完整 SKU" value="sku" />
                <el-option label="按品牌＋中间码" value="mid" />
              </el-select>
            </div>
          </div>
        </template>
        <div ref="scatterChartRef" class="chart-box"></div>
        <div class="chart-foot">
          <span v-if="scatterSkipped > 0" class="chart-foot__note">
            {{ scatterSkipped }} 个点缺少 USD 售价或谷仓库存，未画入图中（汇率缺失不折算）
          </span>
        </div>
        <el-empty v-if="!scatterPoints.length && !loading" description="暂无散点数据" :image-size="60" />
      </el-card>
    </div>

    <!-- ===== 次图区 ===== -->
    <div class="chart-grid">
      <el-card shadow="never" class="chart-card">
        <template #header>
          <div class="card-head">
            <div class="card-head__text">
              <span class="card-title">库存缺口 Top 10</span>
              <small>谷仓可售 − eBay 可售：向右是可补上架的空间，向左是超卖风险</small>
            </div>
          </div>
        </template>
        <div ref="gapChartRef" class="chart-box"></div>
        <el-empty v-if="!stockGapTop.length && !loading" description="暂无缺口数据" :image-size="60" />
      </el-card>

      <el-card shadow="never" class="chart-card risk-card">
        <template #header>
          <div class="card-head">
            <div class="card-head__text">
              <span class="card-title">待处理事项</span>
              <small>按影响面排序，点击带上该项筛选跳到明细</small>
            </div>
            <el-tag v-if="risks.length" type="danger" effect="plain">{{ risks.length }} 项</el-tag>
          </div>
        </template>
        <ul class="risk-list">
          <li
            v-for="risk in risks"
            :key="risk.key"
            class="risk-item"
            :class="{ 'is-active': activeRiskKey === risk.key }"
            @click="applyRiskFilter(risk)"
          >
            <span class="risk-dot" :style="{ backgroundColor: statusColor(risk.label) }"></span>
            <span class="risk-text">
              <strong>{{ risk.label }}</strong>
              <small>{{ displayValue(risk.hint) }}</small>
            </span>
            <span class="risk-count">{{ integer(risk.count) }}</span>
          </li>
        </ul>
        <el-empty v-if="!risks.length && !loading" description="没有待处理事项" :image-size="60" />
      </el-card>
    </div>

    <!-- ===== 明细表 ===== -->
    <div ref="detailAnchorRef"></div>
    <el-card shadow="never" class="table-card">
      <template #header>
        <div class="table-head">
          <el-radio-group v-model="query.mode" @change="handleModeChange">
            <el-radio-button value="detail">按店铺明细</el-radio-button>
            <el-radio-button value="summary">按 SKU 汇总</el-radio-button>
          </el-radio-group>
          <div class="table-tools">
            <el-input
              v-model="query.keyword"
              clearable
              placeholder="搜索 SKU 或产品名"
              prefix-icon="Search"
              class="table-search"
              @clear="handleQuery"
              @keyup.enter="handleQuery"
            />
            <el-select
              v-model="query.status"
              clearable
              placeholder="全部状态"
              class="table-status"
              @change="handleQuery"
            >
              <el-option v-for="status in statusOptions" :key="status" :label="status" :value="status" />
            </el-select>
            <el-button :type="dense ? 'primary' : 'default'" plain @click="dense = !dense">紧凑</el-button>
            <el-button icon="Setting" @click="openColumnConfig">自定义列</el-button>
          </div>
        </div>
      </template>

      <div v-if="accountOptions.length" class="store-chips">
        <el-check-tag
          v-for="account in accountOptions"
          :key="account"
          :checked="query.accounts.includes(account)"
          class="store-chip"
          @change="toggleAccount(account)"
        >{{ account }}</el-check-tag>
      </div>

      <el-table
        v-if="columnConfigLoaded"
        :key="columnTableKey"
        v-loading="detailLoading"
        :data="rows"
        :size="dense ? 'small' : 'default'"
        border
        stripe
        height="560"
        empty-text="没有符合条件的记录，换个站点、店铺、状态或关键词试试"
        @sort-change="handleSortChange"
      >
        <el-table-column
          v-for="col in tableColumns"
          :key="col.key"
          :prop="col.key"
          :label="col.label"
          :width="col.width"
          :min-width="col.minWidth"
          :align="col.align"
          :fixed="col.fixed || false"
          :sortable="col.sortable ? 'custom' : false"
          :show-overflow-tooltip="col.tooltip"
        >
          <template v-if="col.tip" #header>
            <span class="column-header">
              <span>{{ col.label }}</span>
              <el-tooltip :content="col.tip" placement="top">
                <el-icon class="column-tip"><QuestionFilled /></el-icon>
              </el-tooltip>
            </span>
          </template>
          <template #default="scope">
            <template v-if="col.format === 'image'">
              <el-image
                v-if="scope.row.image_url"
                :src="scope.row.image_url"
                fit="cover"
                class="row-image"
                :preview-src-list="[scope.row.image_url]"
                preview-teleported
              />
              <span v-else class="muted">—</span>
            </template>
            <template v-else-if="col.format === 'skuLink'">
              <el-link
                v-if="scope.row.view_item_url"
                :href="scope.row.view_item_url"
                target="_blank"
                type="primary"
                :underline="false"
                class="sku-link"
              >{{ displayValue(scope.row.sku) }}</el-link>
              <span v-else>{{ displayValue(scope.row.sku) }}</span>
            </template>
            <template v-else-if="col.format === 'status'">
              <el-tag :type="statusTagType(scope.row.status)" effect="light">
                {{ displayValue(scope.row.status) }}
              </el-tag>
            </template>
            <template v-else-if="col.format === 'integer'">{{ integer(scope.row[col.key]) }}</template>
            <template v-else-if="col.format === 'gap'">
              <span :class="gapClass(scope.row[col.key])">{{ integer(scope.row[col.key]) }}</span>
            </template>
            <template v-else-if="col.format === 'decimal'">{{ decimal(scope.row[col.key]) }}</template>
            <template v-else>{{ displayValue(scope.row[col.key]) }}</template>
          </template>
        </el-table-column>
      </el-table>

      <pagination
        v-show="total > 0"
        :total="total"
        v-model:page="query.pageNum"
        v-model:limit="query.pageSize"
        @pagination="loadDetail"
      />
    </el-card>

    <!-- ===== 口径说明 ===== -->
    <el-card shadow="never" class="note-card">
      <template #header>
        <span class="card-title">口径说明</span>
      </template>
      <ul class="note-list">
        <li>eBay 售价与库存为在售刊登快照，快照日期见页头</li>
        <li>谷仓库存为领星周快照的海外仓可售件数（wid 18699/18700/18701/18702），<strong>不是实时库存</strong></li>
        <li>覆盖天数 = 谷仓可售 ÷ 近 7 日日均销量；近 7 日无销量时不计算，显示「—」</li>
        <li>售价按站点币种和领星月度汇率折算 USD，汇率缺失时不折算</li>
        <li>采购成本取订单文件中的真实采购成本，未参与售价估算</li>
        <li>未关联到库存的 listing 计入「未匹配」，不计入库存缺口与超卖判断</li>
      </ul>
    </el-card>

    <ColumnConfigDrawer
      v-model="showColumnDrawer"
      :columns="columnDefs"
      :fixed-keys="fixedColumnKeys"
      :required-keys="requiredColumnKeys"
      :visible-keys="visibleKeys"
      @apply="applyColumnConfig"
    />
  </div>
</template>

<script setup name="EbayPriceAnalysis">
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import * as echarts from 'echarts'
import { ElMessage } from 'element-plus'
import {
  exportEbayPriceAnalysis,
  getEbayPriceAnalysisOverview,
  listEbayPriceAnalysisDetail
} from '@/api/operations/ebayPriceAnalysis'
import ColumnConfigDrawer from '@/components/ColumnConfigDrawer/index.vue'
import { useColumnConfig } from '@/composables/useColumnConfig'
import { checkPermi } from '@/utils/permission'


// 状态由后端落库算好，前端只按它渲染和筛选，不自己推导。
const statusOptions = ['未匹配', '超卖风险', '断货', '待补货', '滞销', '健康']
const STATUS_COLOR = {
  未匹配: '#909399',
  超卖风险: '#F56C6C',
  断货: '#FF7A00',
  待补货: '#E6A23C',
  滞销: '#409EFF',
  健康: '#67C23A'
}
const STATUS_TAG_TYPE = {
  未匹配: 'info',
  超卖风险: 'danger',
  断货: 'danger',
  待补货: 'warning',
  滞销: 'primary',
  健康: 'success'
}
// KPI 卡只做跳筛选用的静态映射，数值一律取接口返回值。
const KPI_STATUS = { oversell_count: '超卖风险', unmatched_count: '未匹配' }
const KPI_TONE = { stock_gap: 'info', oversell_count: 'danger', unmatched_count: 'warning' }
const SITE_OPTIONS = ['DE', 'UK', 'US', 'FR']
const EBAY_COLOR = '#409EFF'
const WAREHOUSE_COLOR = '#67C23A'

const loading = ref(false)
const detailLoading = ref(false)
const exporting = ref(false)
const dense = ref(false)
const overview = ref({})
const rows = ref([])
const total = ref(0)
const activeRiskKey = ref('')
const storeChartRef = ref()
const scatterChartRef = ref()
const gapChartRef = ref()
const detailAnchorRef = ref()
let storeChart
let scatterChart
let gapChart

const query = reactive({
  statDate: undefined,
  sites: [],
  accounts: [],
  status: undefined,
  keyword: undefined,
  dimension: 'sku',
  mode: 'detail',
  pageNum: 1,
  pageSize: 50,
  sortBy: undefined,
  sortOrder: undefined
})

const fixedColumnKeys = ['image_url', 'seller_account', 'site_name', 'sku']
const requiredColumnKeys = ['sku']
const columnDefs = [
  { key: 'image_url', label: '图片', width: 76, fixed: true, align: 'center', format: 'image' },
  { key: 'seller_account', label: '店铺', width: 150, fixed: true, detailOnly: true, tooltip: true },
  { key: 'site_name', label: '站点', width: 80, fixed: true, align: 'center' },
  { key: 'sku', label: 'SKU', minWidth: 170, fixed: true, format: 'skuLink' },
  { key: 'title', label: '产品名称', minWidth: 230, tooltip: true },
  { key: 'status', label: '状态', width: 108, align: 'center', format: 'status' },
  { key: 'currency', label: '币种', width: 80, align: 'center' },
  { key: 'current_price', label: '原币售价', width: 110, align: 'right', format: 'decimal' },
  {
    key: 'price_usd', label: '售价(USD)', width: 115, align: 'right', format: 'decimal', sortable: true,
    tip: '按站点币种和领星月度汇率折算；汇率缺失时不折算，显示「—」。'
  },
  { key: 'ebay_quantity_available', label: 'eBay可售', width: 110, align: 'right', format: 'integer', sortable: true },
  {
    key: 'overseas_sellable', label: '谷仓可售', width: 110, align: 'right', format: 'integer', sortable: true,
    tip: '领星周快照的海外仓可售件数，不是实时库存。'
  },
  { key: 'overseas_in_transit', label: '海外在途', width: 110, align: 'right', format: 'integer' },
  { key: 'chengdu_sellable', label: '成都可售', width: 110, align: 'right', format: 'integer' },
  { key: 'pending_outbound', label: '待出库', width: 100, align: 'right', format: 'integer' },
  { key: 'sales_qty_7d', label: '近7日销量', width: 110, align: 'right', format: 'integer' },
  { key: 'sales_qty_30d', label: '近30日销量', width: 115, align: 'right', format: 'integer' },
  {
    key: 'cover_days', label: '覆盖天数', width: 110, align: 'right', format: 'decimal', sortable: true,
    tip: '谷仓可售 ÷ 近 7 日日均销量；近 7 日无销量时不计算，显示「—」。'
  },
  {
    key: 'stock_gap', label: '库存缺口', width: 110, align: 'right', format: 'gap', sortable: true,
    tip: '谷仓可售 − eBay 可售：为正是可补上架的空间，为负是超卖风险。'
  },
  { key: 'purchase_cost_cny', label: '采购成本(¥)', width: 125, align: 'right', format: 'decimal' }
]
const {
  showColumnDrawer,
  columnConfigLoaded,
  columnTableKey,
  visibleKeys,
  visibleColumns,
  openColumnConfig,
  initColumnConfig,
  applyColumnConfig
} = useColumnConfig(
  'operations:ebay:priceAnalysis',
  columnDefs,
  fixedColumnKeys,
  requiredColumnKeys
)

const kpiCards = computed(() => (Array.isArray(overview.value.kpis) ? overview.value.kpis : []))
const storeCompare = computed(() => (Array.isArray(overview.value.store_compare) ? overview.value.store_compare : []))
const stockGapTop = computed(() => (Array.isArray(overview.value.stock_gap_top) ? overview.value.stock_gap_top : []))
const risks = computed(() => (Array.isArray(overview.value.risks) ? overview.value.risks : []))
const scatterRaw = computed(() => (Array.isArray(overview.value.scatter) ? overview.value.scatter : []))
const scatterPoints = computed(() => scatterRaw.value.filter(point =>
  Number.isFinite(Number(point?.price_usd)) && point?.price_usd !== null
  && Number.isFinite(Number(point?.overseas_sellable)) && point?.overseas_sellable !== null))
const scatterSkipped = computed(() => scatterRaw.value.length - scatterPoints.value.length)
const siteOptions = computed(() => {
  const fromData = storeCompare.value.map(item => item.site).filter(Boolean)
  return [...new Set([...SITE_OPTIONS, ...fromData])]
})
const accountOptions = computed(() => {
  const fromData = storeCompare.value.map(item => item.seller_account).filter(Boolean)
  return [...new Set([...fromData, ...query.accounts])]
})
// 汇总视图没有店铺维度，店铺列留着只会是一片空值。
const tableColumns = computed(() => visibleColumns.value.filter(col => !(col.detailOnly && query.mode === 'summary')))

function displayValue(value) {
  return value === null || value === undefined || value === '' ? '—' : value
}
function integer(value) {
  if (value === null || value === undefined || String(value).trim() === '') return '—'
  const numeric = Number(value)
  return Number.isFinite(numeric) ? numeric.toLocaleString('zh-CN', { maximumFractionDigits: 0 }) : '—'
}
function decimal(value) {
  if (value === null || value === undefined || String(value).trim() === '') return '—'
  const numeric = Number(value)
  return Number.isFinite(numeric)
    ? numeric.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
    : '—'
}
function kpiText(kpi) {
  const value = kpi?.value
  if (value === null || value === undefined || value === '') return '—'
  const numeric = Number(value)
  if (!Number.isFinite(numeric)) return String(value)
  const fraction = Number.isInteger(numeric) ? 0 : 2
  return numeric.toLocaleString('zh-CN', { minimumFractionDigits: fraction, maximumFractionDigits: fraction })
}
function kpiTone(kpi) {
  return KPI_TONE[kpi?.key] || 'normal'
}
function kpiStatus(kpi) {
  return KPI_STATUS[kpi?.key] || ''
}
function statusColor(status) {
  return STATUS_COLOR[status] || '#909399'
}
function statusTagType(status) {
  return STATUS_TAG_TYPE[status] || 'info'
}
function gapClass(value) {
  const numeric = Number(value)
  if (!Number.isFinite(numeric)) return 'muted'
  return numeric < 0 ? 'gap-negative' : 'gap-positive'
}
function escapeText(value) {
  return String(value === null || value === undefined ? '' : value)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;').replace(/'/g, '&#39;')
}
function toArray(value) {
  if (Array.isArray(value)) return value.map(item => String(item).trim()).filter(Boolean)
  const text = String(value === null || value === undefined ? '' : value).trim()
  return text ? text.split(',').map(item => item.trim()).filter(Boolean) : []
}
function csv(value) {
  if (Array.isArray(value)) {
    const items = value.map(item => String(item === null || item === undefined ? '' : item).trim()).filter(Boolean)
    return items.length ? items.join(',') : undefined
  }
  const text = String(value === null || value === undefined ? '' : value).trim()
  return text || undefined
}

function buildFilterParams() {
  return {
    statDate: csv(query.statDate),
    sites: csv(query.sites),
    accounts: csv(query.accounts),
    status: csv(query.status),
    keyword: csv(query.keyword)
  }
}
function buildOverviewParams() {
  return { ...buildFilterParams(), dimension: query.dimension }
}
function buildDetailParams() {
  return {
    ...buildFilterParams(),
    mode: query.mode,
    sortBy: csv(query.sortBy),
    sortOrder: csv(query.sortOrder),
    pageNum: query.pageNum,
    pageSize: query.pageSize
  }
}

async function loadOverview() {
  loading.value = true
  try {
    const response = await getEbayPriceAnalysisOverview(buildOverviewParams())
    overview.value = response.data || {}
    await nextTick()
    renderCharts()
  } finally {
    loading.value = false
  }
}
async function loadDetail() {
  detailLoading.value = true
  try {
    const response = await listEbayPriceAnalysisDetail(buildDetailParams())
    const data = response.data || {}
    rows.value = Array.isArray(data.rows) ? data.rows : []
    total.value = Number(data.total || 0)
  } finally {
    detailLoading.value = false
  }
}
async function handleQuery() {
  query.pageNum = 1
  await Promise.all([loadOverview(), loadDetail()])
}
function resetQuery() {
  query.statDate = undefined
  query.sites = []
  query.accounts = []
  query.status = undefined
  query.keyword = undefined
  query.dimension = 'sku'
  query.mode = 'detail'
  query.sortBy = undefined
  query.sortOrder = undefined
  activeRiskKey.value = ''
  return handleQuery()
}
function handleModeChange() {
  query.pageNum = 1
  return loadDetail()
}
function handleDimensionChange() {
  return loadOverview()
}
function handleSortChange({ prop, order }) {
  query.sortBy = order ? prop : undefined
  query.sortOrder = order === 'ascending' ? 'asc' : (order === 'descending' ? 'desc' : undefined)
  query.pageNum = 1
  return loadDetail()
}
function toggleAccount(account) {
  const index = query.accounts.indexOf(account)
  if (index >= 0) query.accounts.splice(index, 1)
  else query.accounts.push(account)
  return handleQuery()
}
function applyStatusFilter(status) {
  query.status = query.status === status ? undefined : status
  return handleQuery()
}
function handleKpiClick(kpi) {
  const status = kpiStatus(kpi)
  if (!status) return undefined
  return applyStatusFilter(status)
}
// 事项的 filter 由后端给，前端只认识自己的筛选字段，不猜别的键。
function applyRiskFilter(risk) {
  const filter = risk && typeof risk.filter === 'object' && risk.filter ? risk.filter : null
  if (!filter) return undefined
  if ('status' in filter) query.status = filter.status || undefined
  if ('sites' in filter) query.sites = toArray(filter.sites)
  if ('accounts' in filter) query.accounts = toArray(filter.accounts)
  if ('keyword' in filter) query.keyword = filter.keyword || undefined
  activeRiskKey.value = risk.key || ''
  return Promise.resolve(handleQuery()).then(scrollToDetail)
}
function scrollToDetail() {
  const anchor = detailAnchorRef.value
  if (anchor && typeof anchor.scrollIntoView === 'function') {
    anchor.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }
}
async function handleExport() {
  if (!checkPermi(['operations:ebayPriceAnalysis:export'])) {
    ElMessage.warning('没有价格分析导出权限，请联系管理员授权')
    return
  }
  if (exporting.value || loading.value) return
  exporting.value = true
  try {
    const { pageNum, pageSize, ...params } = buildDetailParams()
    await exportEbayPriceAnalysis(params)
  } finally {
    exporting.value = false
  }
}

function renderCharts() {
  renderStoreChart()
  renderScatterChart()
  renderGapChart()
}
function renderStoreChart() {
  if (!storeChartRef.value) return
  storeChart ||= echarts.init(storeChartRef.value)
  const items = storeCompare.value
  const categories = items.map(item => [item.seller_account, item.site].filter(Boolean).join(' · '))
  storeChart.setOption({
    grid: { left: 8, right: 16, top: 34, bottom: 8, containLabel: true },
    legend: { top: 0, data: ['eBay 可售', '谷仓可售'] },
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'shadow' },
      formatter: params => {
        const index = params?.[0]?.dataIndex
        const item = items[index] || {}
        const lines = [`<b>${escapeText(categories[index])}</b>`]
        params.forEach(entry => {
          lines.push(`${entry.marker}${escapeText(entry.seriesName)}：${integer(entry.value)}`)
        })
        lines.push(`刊登数：${integer(item.listing_count)}`)
        return lines.join('<br/>')
      }
    },
    xAxis: { type: 'category', data: categories, axisLabel: { rotate: 32, interval: 0, width: 92, overflow: 'truncate' } },
    yAxis: { type: 'value', axisLabel: { formatter: value => integer(value) } },
    series: [
      {
        name: 'eBay 可售', type: 'bar', barMaxWidth: 22,
        itemStyle: { color: EBAY_COLOR, borderRadius: [4, 4, 0, 0] },
        data: items.map(item => item.ebay_available)
      },
      {
        name: '谷仓可售', type: 'bar', barMaxWidth: 22,
        itemStyle: { color: WAREHOUSE_COLOR, borderRadius: [4, 4, 0, 0] },
        data: items.map(item => item.overseas_sellable)
      }
    ]
  }, true)
  storeChart.off('click')
  storeChart.on('click', params => {
    const item = items[params?.dataIndex]
    if (item?.seller_account) toggleAccount(item.seller_account)
  })
}
function renderScatterChart() {
  if (!scatterChartRef.value) return
  scatterChart ||= echarts.init(scatterChartRef.value)
  const grouped = new Map()
  scatterPoints.value.forEach(point => {
    const status = point.status || '未匹配'
    if (!grouped.has(status)) grouped.set(status, [])
    grouped.get(status).push([
      Number(point.price_usd),
      Number(point.overseas_sellable),
      Number(point.ebay_available || 0),
      point.sku || point.mid_code || '',
      status
    ])
  })
  const median = overview.value.scatter_median || {}
  const medianPrice = Number(median.price_usd)
  const medianStock = Number(median.overseas_sellable)
  const series = statusOptions.filter(status => grouped.has(status)).map(status => ({
    name: status,
    type: 'scatter',
    symbolSize: item => {
      const size = 6 + Math.sqrt(Math.max(Number(item[2]) || 0, 0)) * 1.5
      return Math.max(6, Math.min(size, 32))
    },
    itemStyle: { color: STATUS_COLOR[status], opacity: 0.68, borderColor: '#fff', borderWidth: 1 },
    data: grouped.get(status)
  }))
  if (series.length && Number.isFinite(medianPrice) && Number.isFinite(medianStock)) {
    series[0].markLine = {
      silent: true,
      symbol: 'none',
      lineStyle: { type: 'dashed', color: '#c0c4cc' },
      label: { formatter: params => params.name, color: '#909399', fontSize: 11 },
      data: [
        { xAxis: medianPrice, name: `售价中位数 $${decimal(medianPrice)}` },
        { yAxis: medianStock, name: `库存中位数 ${integer(medianStock)}` }
      ]
    }
    series[0].markArea = {
      silent: true,
      itemStyle: { color: 'transparent' },
      label: { color: '#a8abb2', fontSize: 11 },
      data: [
        [{ xAxis: 'min', yAxis: medianStock, label: { position: 'insideTopLeft', formatter: '低价 · 高库存（占资金）' } },
          { xAxis: medianPrice, yAxis: 'max' }],
        [{ xAxis: medianPrice, yAxis: medianStock, label: { position: 'insideTopRight', formatter: '高价 · 高库存' } },
          { xAxis: 'max', yAxis: 'max' }],
        [{ xAxis: 'min', yAxis: 'min', label: { position: 'insideBottomLeft', formatter: '低价 · 低库存' } },
          { xAxis: medianPrice, yAxis: medianStock }],
        [{ xAxis: medianPrice, yAxis: 'min', label: { position: 'insideBottomRight', formatter: '高价 · 低库存（补货优先）' } },
          { xAxis: 'max', yAxis: medianStock }]
      ]
    }
  }
  scatterChart.setOption({
    grid: { left: 8, right: 18, top: 34, bottom: 8, containLabel: true },
    legend: { top: 0, data: series.map(item => item.name) },
    tooltip: {
      trigger: 'item',
      formatter: params => {
        const [price, stock, ebay, label, status] = params.value
        return [
          `<b>${escapeText(label)}</b>`,
          `售价：$${decimal(price)}`,
          `谷仓可售：${integer(stock)}`,
          `eBay 可售：${integer(ebay)}`,
          `状态：${escapeText(status)}`
        ].join('<br/>')
      }
    },
    xAxis: { type: 'value', name: '售价 (USD)', nameLocation: 'end', nameTextStyle: { color: '#909399' }, axisLabel: { formatter: value => `$${value}` } },
    yAxis: { type: 'value', name: '谷仓可售', nameTextStyle: { color: '#909399' }, axisLabel: { formatter: value => integer(value) } },
    series
  }, true)
}
function renderGapChart() {
  if (!gapChartRef.value) return
  gapChart ||= echarts.init(gapChartRef.value)
  const items = stockGapTop.value
  const labels = items.map(item => item.sku || item.mid_code || '')
  gapChart.setOption({
    grid: { left: 8, right: 24, top: 16, bottom: 8, containLabel: true },
    tooltip: {
      trigger: 'item',
      formatter: params => {
        const item = items[params.dataIndex] || {}
        return [
          `<b>${escapeText(labels[params.dataIndex])}</b>`,
          `库存缺口：${integer(item.stock_gap)}`,
          `谷仓可售：${integer(item.overseas_sellable)}`,
          `eBay 可售：${integer(item.ebay_available)}`
        ].join('<br/>')
      }
    },
    xAxis: { type: 'value', axisLabel: { formatter: value => integer(value) }, splitLine: { lineStyle: { type: 'dashed' } } },
    yAxis: { type: 'category', inverse: true, data: labels, axisLabel: { width: 118, overflow: 'truncate' } },
    series: [{
      type: 'bar',
      barMaxWidth: 18,
      data: items.map((item, index) => {
        const value = Number(item.stock_gap)
        const negative = Number.isFinite(value) && value < 0
        return {
          value: item.stock_gap,
          itemStyle: {
            color: negative ? STATUS_COLOR['超卖风险'] : WAREHOUSE_COLOR,
            borderRadius: negative ? [4, 0, 0, 4] : [0, 4, 4, 0]
          },
          label: {
            show: true,
            position: negative ? 'left' : 'right',
            color: '#606266',
            fontSize: 11,
            formatter: () => integer(items[index]?.stock_gap)
          }
        }
      })
    }]
  }, true)
}
function resizeCharts() {
  storeChart?.resize()
  scatterChart?.resize()
  gapChart?.resize()
}

onMounted(async () => {
  await initColumnConfig()
  await Promise.all([loadOverview(), loadDetail()])
  window.addEventListener('resize', resizeCharts)
})
onBeforeUnmount(() => {
  window.removeEventListener('resize', resizeCharts)
  storeChart?.dispose()
  scatterChart?.dispose()
  gapChart?.dispose()
})
</script>

<style scoped>
.ebay-price-analysis {
  background: #f5f7fa;
  min-height: calc(100vh - 84px);
}
.ebay-price-analysis :deep(.el-card) {
  border: 0;
  border-radius: 10px;
}
.head-card,
.chart-card,
.table-card,
.note-card {
  margin-bottom: 14px;
}
.head-top {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}
.head-title h2 {
  margin: 0;
  font-size: 20px;
  color: #303133;
}
.head-meta {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
  margin: 6px 0 0;
  font-size: 13px;
  color: #909399;
}
.head-meta strong {
  color: #303133;
  font-weight: 600;
}
.meta-sep {
  color: #dcdfe6;
}
.head-acts {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
/* 自有图标库 jmh-refresh / jmh-export。按钮带文字，图标不设 color，
   用 currentColor 跟随按钮文字色（导出按钮即 warning 橙色）；loading 时刷新图标旋转 */
.report-icon {
  margin-right: 6px;
  font-size: 16px;
}
.report-icon.spinning {
  animation: report-icon-spin 1s linear infinite;
}
@keyframes report-icon-spin {
  to {
    transform: rotate(360deg);
  }
}
.snapshot-alert {
  margin: 12px 0 4px;
}
.filter-form {
  margin-top: 8px;
}
.filter-form :deep(.el-form-item) {
  margin-bottom: 10px;
}
.filter-control {
  width: 220px;
}
.filter-control--status {
  width: 150px;
}
.kpi-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
  gap: 12px;
  margin-bottom: 14px;
}
.kpi-card {
  background: #fff;
  border-radius: 10px;
  padding: 14px 16px;
  border-left: 4px solid #409eff;
}
.kpi-card--danger {
  border-left-color: #f56c6c;
}
.kpi-card--warning {
  border-left-color: #e6a23c;
}
.kpi-card--info {
  border-left-color: #909399;
}
.kpi-card.is-clickable {
  cursor: pointer;
}
.kpi-card.is-active {
  box-shadow: 0 0 0 1px #409eff inset;
}
.kpi-label {
  display: block;
  font-size: 13px;
  color: #909399;
}
.kpi-value {
  display: block;
  margin-top: 6px;
  font-size: 22px;
  line-height: 1.2;
  color: #303133;
  word-break: break-all;
}
.kpi-unit {
  font-size: 12px;
  color: #a8abb2;
}
.kpi-empty {
  grid-column: 1 / -1;
  background: #fff;
  border-radius: 10px;
}
.chart-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
  gap: 14px;
}
.chart-grid > .chart-card {
  min-width: 0;
}
.card-head {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}
.card-head__text {
  display: flex;
  flex-direction: column;
  min-width: 0;
}
.card-head__acts {
  display: flex;
  align-items: center;
  gap: 8px;
}
.card-title {
  font-weight: 600;
  color: #303133;
}
.card-head__text small {
  margin-top: 2px;
  font-size: 12px;
  color: #909399;
}
.dimension-select {
  width: 160px;
}
.chart-box {
  height: 330px;
}
.chart-foot {
  min-height: 18px;
}
.chart-foot__note {
  font-size: 12px;
  color: #e6a23c;
}
.risk-list {
  margin: 0;
  padding: 0;
  list-style: none;
  max-height: 330px;
  overflow-y: auto;
}
.risk-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 8px;
  border-radius: 8px;
  cursor: pointer;
  border-bottom: 1px solid #f2f6fc;
}
.risk-item:hover {
  background: #f5f7fa;
}
.risk-item.is-active {
  background: #ecf5ff;
}
.risk-dot {
  flex: 0 0 auto;
  width: 8px;
  height: 8px;
  border-radius: 50%;
}
.risk-text {
  display: flex;
  flex-direction: column;
  min-width: 0;
  flex: 1 1 auto;
}
.risk-text strong {
  font-size: 14px;
  color: #303133;
}
.risk-text small {
  font-size: 12px;
  color: #909399;
}
.risk-count {
  flex: 0 0 auto;
  font-size: 18px;
  font-weight: 600;
  color: #303133;
}
.table-head {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}
.table-tools {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
}
.table-search {
  width: 220px;
}
.table-status {
  width: 140px;
}
.store-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-bottom: 10px;
}
.store-chip {
  cursor: pointer;
}
.column-header {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  white-space: nowrap;
}
.column-tip {
  color: #909399;
  cursor: help;
}
.row-image {
  width: 46px;
  height: 46px;
  border-radius: 6px;
}
.sku-link {
  font-weight: 600;
}
.muted {
  color: #c0c4cc;
}
.gap-positive {
  color: #67c23a;
}
.gap-negative {
  color: #f56c6c;
}
.note-list {
  margin: 0;
  padding-left: 18px;
  color: #606266;
  font-size: 13px;
  line-height: 2;
}
@media (max-width: 992px) {
  .kpi-grid {
    grid-template-columns: repeat(auto-fit, minmax(130px, 1fr));
  }
  .chart-grid {
    grid-template-columns: 1fr;
  }
}
@media (max-width: 768px) {
  .head-acts,
  .table-tools {
    width: 100%;
  }
  .filter-control,
  .filter-control--status,
  .table-search,
  .table-status,
  .dimension-select {
    width: 100%;
  }
  .filter-form :deep(.el-form-item) {
    display: block;
    margin-right: 0;
  }
  .chart-box {
    height: 280px;
  }
}
</style>
