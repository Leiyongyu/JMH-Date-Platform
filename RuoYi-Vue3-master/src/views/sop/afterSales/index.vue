<template>
  <div class="app-container after-sales-page">
    <section class="page-head">
      <div>
        <div class="eyebrow">SOP / AMZ AFTER-SALES</div>
        <h2>售后数据</h2>
        <p>订单利润与售后订单按周更新，自动完成去重、翻译、分类及售后率汇总。</p>
      </div>
      <div class="head-actions">
        <el-dropdown
          v-hasPermi="['sop:afterSales:export']"
          trigger="click"
          :disabled="!query.startDate || !query.endDate || loading || rangeBuilding || exporting"
          @command="handleExportCommand"
        >
          <el-button type="primary" plain :loading="exporting">
            <el-icon><Download /></el-icon>
            导出数据
            <el-icon class="el-icon--right"><ArrowDown /></el-icon>
          </el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="data">导出售后数据</el-dropdown-item>
              <el-dropdown-item command="categories" divided>导出十类售后表</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
      </div>
    </section>

    <section class="summary-grid">
      <div class="summary-card accent-blue">
        <span>统计周期</span>
        <strong>{{ query.startDate || '--' }}</strong>
        <small>至 {{ query.endDate || '--' }}</small>
      </div>
      <div class="summary-card accent-indigo">
        <span>SKU 数量</span>
        <strong>{{ number(summary.sku_count) }}</strong>
        <small>当前筛选结果</small>
      </div>
      <div class="summary-card accent-green">
        <span>售后数量</span>
        <strong>{{ number(summary.after_quantity) }}</strong>
        <small>按数量降序排列</small>
      </div>
      <div class="summary-card accent-orange">
        <span>售后订单数</span>
        <strong>{{ number(summary.order_count) }}</strong>
        <small>按订单号去重</small>
      </div>
    </section>

    <el-card shadow="never" class="content-card">
      <div class="filters">
        <el-date-picker
          v-model="dateRange"
          type="daterange"
          class="period-picker"
          unlink-panels
          range-separator="至"
          start-placeholder="开始日期"
          end-placeholder="结束日期"
          format="YYYY-MM-DD"
          value-format="YYYY-MM-DD"
          :shortcuts="dateShortcuts"
          :disabled-date="disableUnavailableDate"
          @change="handleDateChange"
        />
        <el-input v-model="query.sku" clearable placeholder="搜索 SKU" @keyup.enter="handleQuery" />
        <el-input v-model="query.smallCategory" clearable placeholder="搜索售后小类" @keyup.enter="handleQuery" />
        <el-button type="primary" plain :loading="loading" @click="handleQuery">
          <el-icon><Search /></el-icon>查询
        </el-button>
        <el-button @click="resetQuery">重置</el-button>
      </div>

      <div class="range-hint">
        可选数据范围：{{ coverageStart || '--' }} 至 {{ coverageEnd || '--' }}；新日期段首次查询会在后台生成并缓存。
      </div>
      <el-alert
        v-if="rangeBuilding"
        class="range-alert"
        type="info"
        show-icon
        :closable="false"
        :title="rangeMessage"
        description="可以离开当前页面，后台任务会继续运行；本页面将自动刷新结果。"
      />

      <div class="category-tabs">
        <button
          v-for="item in categoryOptions"
          :key="item.value"
          type="button"
          :class="['category-pill', { active: query.bigCategory === item.value }]"
          @click="selectCategory(item.value)"
        >
          {{ item.label }}
        </button>
      </div>

      <div v-if="selectedRows.length" class="selection-tip">
        已选择 <b>{{ selectedRows.length }}</b> 个 SKU，导出售后数据时将只导出这些 SKU
        <el-button link type="primary" @click="clearSelection">取消选择</el-button>
      </div>

      <el-table
        ref="tableRef"
        v-loading="loading"
        :data="rows"
        row-key="id"
        class="result-table"
        stripe
        element-loading-text="正在计算所选日期段的售后率..."
        @selection-change="handleSelectionChange"
      >
        <el-table-column type="selection" width="48" align="center" reserve-selection />
        <el-table-column type="expand" width="48">
          <template #default="{ row }">
            <div class="detail-panel">
              <div class="detail-title">
                <strong>{{ row.business_sku }}</strong>
                <span>共 {{ row.detail_count }} 个售后分类，分类售后率均使用主行共享销量计算</span>
              </div>
              <el-table :data="row.children || []" size="small" border class="detail-table">
                <el-table-column prop="big_category" label="售后原因（大）" min-width="150">
                  <template #default="{ row: detail }">
                    <el-tag effect="plain" round>{{ detail.big_category }}</el-tag>
                  </template>
                </el-table-column>
                <el-table-column prop="small_category" label="售后原因（小）" min-width="170" />
                <el-table-column prop="after_quantity" label="售后数量" width="110" align="right">
                  <template #default="{ row: detail }">{{ number(detail.after_quantity) }}</template>
                </el-table-column>
                <el-table-column prop="order_count" label="订单数" width="90" align="right" />
                <el-table-column label="订单号" min-width="190">
                  <template #default="{ row: detail }">
                    <el-popover placement="top" :width="420" trigger="click">
                      <template #reference>
                        <el-button link type="primary">查看 {{ detail.order_count }} 个订单</el-button>
                      </template>
                      <div class="order-list">{{ detail.order_numbers || '--' }}</div>
                    </el-popover>
                  </template>
                </el-table-column>
                <el-table-column prop="source_after_quantity_text" label="数据来源及售后数量" min-width="190" />
                <el-table-column prop="after_sales_rate" label="分类售后率" width="112" align="right">
                  <template #default="{ row: detail }">
                    {{ detail.sales_volume ? percent(detail.after_sales_rate) : '--' }}
                  </template>
                </el-table-column>
              </el-table>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="#" width="58" align="center">
          <template #default="{ $index }">{{ (query.pageNum - 1) * query.pageSize + $index + 1 }}</template>
        </el-table-column>
        <el-table-column prop="business_sku" label="SKU" min-width="190" show-overflow-tooltip>
          <template #default="{ row }"><b class="sku-text">{{ row.business_sku }}</b></template>
        </el-table-column>
        <el-table-column prop="after_quantity" label="售后数量" width="112" align="right">
          <template #default="{ row }"><b>{{ number(row.after_quantity) }}</b></template>
        </el-table-column>
        <el-table-column prop="order_count" label="订单数" width="92" align="right" />
        <el-table-column label="订单号" min-width="230">
          <template #default="{ row }">
            <el-popover placement="top" :width="420" trigger="click">
              <template #reference>
                <el-button link type="primary">查看 {{ row.order_count }} 个订单</el-button>
              </template>
              <div class="order-list">{{ row.order_numbers || '--' }}</div>
            </el-popover>
          </template>
        </el-table-column>
        <el-table-column prop="source_after_quantity_text" label="数据来源及售后数量" min-width="210" />
        <el-table-column prop="source_sales_volume_text" label="数据来源及销量" min-width="210" />
        <el-table-column prop="sales_volume" label="销量" width="110" align="right">
          <template #default="{ row }">{{ number(row.sales_volume) }}</template>
        </el-table-column>
        <el-table-column prop="after_sales_rate" label="售后率" width="110" align="right">
          <template #default="{ row }">
            <b class="rate-text">{{ row.sales_volume ? percent(row.after_sales_rate) : '--' }}</b>
          </template>
        </el-table-column>
      </el-table>

      <pagination
        v-show="total > 0"
        :total="total"
        v-model:page="query.pageNum"
        v-model:limit="query.pageSize"
        @pagination="loadData"
      />
    </el-card>

  </div>
</template>

<script setup name="SopAfterSales">
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import {
  exportAfterSales,
  exportAfterSalesData,
  getAfterSalesCategories,
  listAfterSales,
  listAfterSalesPeriods
} from '@/api/sop/afterSales'

const loading = ref(false)
const exporting = ref(false)
const rangeBuilding = ref(false)
const rangeMessage = ref('')
const dateRange = ref([])
const coverageStart = ref('')
const coverageEnd = ref('')
const tableRef = ref()
const selectedRows = ref([])
const rows = ref([])
const total = ref(0)
const bigCategories = ref([])
const summary = reactive({})
let rangePollTimer
let loadSequence = 0
const query = reactive({
  pageNum: 1,
  pageSize: 20,
  startDate: undefined,
  endDate: undefined,
  bigCategory: '',
  smallCategory: '',
  sku: ''
})

const categoryOptions = computed(() => [
  { label: '全部', value: '' },
  ...bigCategories.value.map(item => ({ label: item, value: item }))
])

const dateShortcuts = [
  { text: '最近7天', value: () => recentDays(7) },
  { text: '最近30天', value: () => recentDays(30) },
  {
    text: '本月',
    value: () => {
      const end = availableEndDate()
      return [new Date(end.getFullYear(), end.getMonth(), 1), end]
    }
  },
  {
    text: '本年度',
    value: () => {
      const end = availableEndDate()
      return [new Date(end.getFullYear(), 0, 1), end]
    }
  }
]

function recentDays(days) {
  const end = availableEndDate()
  const start = new Date(end)
  start.setDate(start.getDate() - days + 1)
  return [start, end]
}

function availableEndDate() {
  return coverageEnd.value
    ? new Date(`${coverageEnd.value}T00:00:00`)
    : new Date()
}

function disableUnavailableDate(time) {
  const value = time.getTime()
  const min = coverageStart.value
    ? new Date(`${coverageStart.value}T00:00:00`).getTime()
    : undefined
  const max = availableEndDate().getTime()
  return (min !== undefined && value < min) || value > max
}

function number(value) {
  return Number(value || 0).toLocaleString('zh-CN', { maximumFractionDigits: 2 })
}

function percent(value) {
  return `${(Number(value || 0) * 100).toFixed(2)}%`
}

async function loadMetadata() {
  const [categoryResponse, periodResponse] = await Promise.all([
    getAfterSalesCategories(),
    listAfterSalesPeriods()
  ])
  bigCategories.value = categoryResponse.data?.big_categories || []
  const periods = periodResponse.data || []
  coverageStart.value = periods.reduce(
    (value, item) => !value || item.period_start < value ? item.period_start : value,
    ''
  )
  coverageEnd.value = periods.reduce(
    (value, item) => !value || item.period_end > value ? item.period_end : value,
    ''
  )
  if (!dateRange.value.length && periods.length) {
    const latest = periods[0]
    dateRange.value = [latest.period_start, latest.period_end]
    query.startDate = latest.period_start
    query.endDate = latest.period_end
  }
}

async function loadData(isPolling = false) {
  const sequence = ++loadSequence
  const requestedStartDate = query.startDate
  const requestedEndDate = query.endDate
  if (!isPolling) loading.value = true
  try {
    const response = await listAfterSales(query)
    if (
      sequence !== loadSequence ||
      requestedStartDate !== query.startDate ||
      requestedEndDate !== query.endDate
    ) return
    if (response.rangeStatus === 'building') {
      rows.value = []
      total.value = 0
      Object.keys(summary).forEach(key => delete summary[key])
      rangeBuilding.value = true
      rangeMessage.value = response.rangeMessage || '正在后台生成所选日期段的售后率'
      scheduleRangePoll()
      return
    }
    stopRangePoll()
    rows.value = response.rows || []
    total.value = Number(response.total || 0)
    Object.keys(summary).forEach(key => delete summary[key])
    Object.assign(summary, response.summary || {})
    if (!query.startDate && response.periodStart) {
      query.startDate = response.periodStart
      query.endDate = response.periodEnd
      dateRange.value = [response.periodStart, response.periodEnd]
    }
  } catch (error) {
    if (sequence === loadSequence) stopRangePoll()
  } finally {
    if (sequence === loadSequence) loading.value = false
  }
}

function scheduleRangePoll() {
  clearTimeout(rangePollTimer)
  rangePollTimer = setTimeout(() => loadData(true), 5000)
}

function stopRangePoll() {
  clearTimeout(rangePollTimer)
  rangePollTimer = undefined
  rangeBuilding.value = false
  rangeMessage.value = ''
}

function handleDateChange(value) {
  const [startDate, endDate] = value || []
  query.startDate = startDate || undefined
  query.endDate = endDate || undefined
  query.pageNum = 1
  stopRangePoll()
  clearSelection()
  loadData()
}

function selectCategory(value) {
  query.bigCategory = value
  query.pageNum = 1
  clearSelection()
  loadData()
}

function handleQuery() {
  if (!query.startDate || !query.endDate) return
  query.pageNum = 1
  stopRangePoll()
  clearSelection()
  loadData()
}

function resetQuery() {
  query.bigCategory = ''
  query.smallCategory = ''
  query.sku = ''
  query.pageNum = 1
  clearSelection()
  loadData()
}

function handleSelectionChange(selection) {
  selectedRows.value = selection
}

function clearSelection() {
  tableRef.value?.clearSelection()
  selectedRows.value = []
}

async function handleExportCommand(command) {
  exporting.value = true
  try {
    if (command === 'data') {
      const selectedSkus = selectedRows.value.map(item => item.business_sku)
      const data = await exportAfterSalesData(query, selectedSkus)
      const selectedSuffix = selectedSkus.length ? `-已选${selectedSkus.length}个SKU` : ''
      downloadBlob(data, `AMZ-SOP售后数据-${query.startDate}-${query.endDate}${selectedSuffix}`)
    } else if (command === 'categories') {
      const data = await exportAfterSales(query.startDate, query.endDate)
      downloadBlob(data, `AMZ-SOP十类售后表-${query.startDate}-${query.endDate}`)
    }
  } finally {
    exporting.value = false
  }
}

function downloadBlob(data, filenamePrefix) {
  const blob = data instanceof Blob ? data : new Blob([data])
  const timestamp = new Date().toISOString().replace(/[-:T.Z]/g, '').slice(0, 14)
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = `${filenamePrefix}-${timestamp}.xlsx`
  document.body.appendChild(link)
  link.click()
  link.remove()
  URL.revokeObjectURL(url)
}

onMounted(async () => {
  await loadMetadata()
  await loadData()
})

onBeforeUnmount(stopRangePoll)
</script>

<style scoped>
.after-sales-page {
  min-height: calc(100vh - 84px);
  background: #f5f7fb;
}
.page-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 24px;
  margin-bottom: 16px;
  padding: 22px 24px;
  border: 1px solid #e5eaf2;
  border-radius: 12px;
  background: #fff;
}
.page-head h2 { margin: 5px 0 7px; color: #172033; font-size: 25px; }
.page-head p { margin: 0; color: #64748b; }
.eyebrow { color: #2563eb; font-size: 12px; font-weight: 700; letter-spacing: 1px; }
.head-actions { display: flex; flex-shrink: 0; gap: 8px; }
.summary-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(180px, 1fr));
  gap: 12px;
  margin-bottom: 16px;
}
.summary-card {
  min-height: 96px;
  padding: 15px 17px;
  border: 1px solid #e6eaf1;
  border-top-width: 3px;
  border-radius: 10px;
  background: #fff;
}
.summary-card span { color: #64748b; font-size: 12px; }
.summary-card strong { display: block; margin-top: 7px; color: #172033; font-size: 22px; }
.summary-card small { color: #94a3b8; }
.accent-blue { border-top-color: #3b82f6; }
.accent-indigo { border-top-color: #6366f1; }
.accent-green { border-top-color: #10b981; }
.accent-orange { border-top-color: #f59e0b; }
.content-card { border-radius: 12px; }
.filters {
  display: grid;
  grid-template-columns: minmax(260px, 1.3fr) minmax(180px, .8fr) minmax(180px, .8fr) auto auto;
  gap: 10px;
  margin-bottom: 14px;
}
.period-picker { width: 100% !important; }
.range-hint {
  margin: -2px 0 14px;
  color: #64748b;
  font-size: 12px;
}
.range-alert { margin-bottom: 14px; }
.category-tabs { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 16px; }
.selection-tip {
  display: flex;
  align-items: center;
  gap: 5px;
  margin: -4px 0 12px;
  padding: 9px 12px;
  border: 1px solid #bfdbfe;
  border-radius: 8px;
  color: #1e40af;
  background: #eff6ff;
  font-size: 13px;
}
.category-pill {
  padding: 7px 13px;
  border: 1px solid #dfe5ee;
  border-radius: 18px;
  color: #475569;
  background: #fff;
  cursor: pointer;
  transition: .18s ease;
}
.category-pill:hover { border-color: #93c5fd; color: #2563eb; }
.category-pill.active { border-color: #2563eb; color: #fff; background: #2563eb; }
.result-table :deep(.el-table__header th) { color: #475569; background: #f8fafc; }
.sku-text { color: #1e293b; }
.rate-text { color: #2563eb; }
.detail-panel {
  margin: 0 18px 14px 68px;
  padding: 14px;
  border: 1px solid #dbe7f5;
  border-radius: 10px;
  background: #f8fbff;
}
.detail-title {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 11px;
  color: #1e293b;
}
.detail-title span { color: #64748b; font-size: 12px; }
.detail-table { border-radius: 8px; overflow: hidden; }
.order-list { max-height: 240px; overflow-y: auto; color: #475569; line-height: 1.75; word-break: break-all; }
@media (max-width: 1100px) {
  .summary-grid { grid-template-columns: repeat(2, 1fr); }
  .filters { grid-template-columns: 1fr 1fr; }
}
@media (max-width: 720px) {
  .page-head { align-items: flex-start; flex-direction: column; }
  .summary-grid { grid-template-columns: 1fr; }
  .filters { grid-template-columns: 1fr; }
  .detail-panel { margin-left: 8px; }
}
</style>
