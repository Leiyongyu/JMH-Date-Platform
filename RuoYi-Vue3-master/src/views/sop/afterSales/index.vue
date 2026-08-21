<template>
  <div class="app-container after-sales-page">
    <section class="page-head">
      <div>
        <div class="eyebrow">SOP / {{ activePlatform === 'amz' ? 'AMZ' : 'EBAY' }} AFTER-SALES</div>
        <h2>售后数据</h2>
        <p>{{ platformDescription }}</p>
      </div>
      <div class="head-actions">
        <el-dropdown
          v-if="activePlatform === 'ebay'"
          v-hasPermi="['sop:afterSales:import']"
          trigger="click"
          :disabled="importing"
          @command="chooseImportType"
        >
          <el-button type="success" plain :loading="importing">
            <el-icon><UploadFilled /></el-icon>
            上传 eBay 数据
            <el-icon class="el-icon--right"><ArrowDown /></el-icon>
          </el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="monthly">上传指定月份售后+销量</el-dropdown-item>
              <el-dropdown-item command="history" divided>首次上传历史售后+销量</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
        <input
          ref="fileInput"
          class="hidden-file-input"
          type="file"
          accept=".xlsx,.xlsm"
          @change="handleImportFile"
        />
        <el-button
          v-if="activePlatform === 'amz'"
          v-hasPermi="['sop:afterSales:sync']"
          type="warning"
          plain
          :loading="syncing"
          :disabled="!selectedMonths.length || loading || rangeBuilding"
          @click="handleAmzRefresh"
        >
          <el-icon><Refresh /></el-icon>
          重新拉取区间
        </el-button>
        <el-dropdown
          v-hasPermi="['sop:afterSales:export']"
          trigger="click"
          :disabled="!selectedMonths.length || !query.startDate || !query.endDate || loading || rangeBuilding || exporting"
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

    <section class="platform-switch">
      <button
        v-for="item in platformOptions"
        :key="item.value"
        type="button"
        :class="['platform-card', item.value, { active: activePlatform === item.value }]"
        @click="changePlatform(item.value)"
      >
        <span class="platform-code">{{ item.code }}</span>
        <span class="platform-copy">
          <strong>{{ item.label }}</strong>
          <small>{{ item.description }}</small>
        </span>
        <span class="platform-state">{{ activePlatform === item.value ? '当前展示' : '点击切换' }}</span>
      </button>
    </section>

    <section class="summary-grid">
      <div class="summary-card accent-blue">
        <span>统计月份</span>
        <strong>{{ selectedMonthLabel }}</strong>
        <small>{{ selectedPeriodDescription }}</small>
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
      <div class="summary-card accent-cyan">
        <span>区间全部销量</span>
        <strong>{{ number(summary.range_sales_volume) }}</strong>
        <small>包含没有售后的SKU</small>
      </div>
      <div class="summary-card accent-red">
        <span>区间整体售后率</span>
        <strong>{{ percent(summary.range_after_sales_rate) }}</strong>
        <small>{{ number(summary.range_after_quantity) }} ÷ {{ number(summary.range_sales_volume) }}</small>
      </div>
    </section>

    <el-card shadow="never" class="content-card">
      <div class="filters">
        <el-date-picker
          v-model="selectedMonths"
          type="monthrange"
          class="period-picker"
          unlink-panels
          range-separator="至"
          start-placeholder="开始月份"
          end-placeholder="结束月份"
          format="YYYY年MM月"
          value-format="YYYY-MM"
          :disabled-date="disableUnavailableMonth"
          @change="handleMonthRangeChange"
        />
        <el-input v-model="query.sku" clearable placeholder="搜索 SKU" @keyup.enter="handleQuery" />
        <el-input v-model="query.smallCategory" clearable placeholder="搜索售后小类" @keyup.enter="handleQuery" />
        <el-button type="primary" plain :loading="loading" @click="handleQuery">
          <el-icon><Search /></el-icon>查询
        </el-button>
        <el-button @click="resetQuery">重置</el-button>
      </div>

      <div class="range-hint">
        可选月份：{{ coverageMonthStart || '--' }} 至 {{ coverageMonthEnd || '--' }}；{{ rangeHint }}
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
        element-loading-text="正在计算所选月份的售后率..."
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
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  exportAfterSales,
  exportAfterSalesData,
  getAfterSalesCategories,
  importEbayAfterSalesFile,
  listAfterSales,
  listAfterSalesPeriods,
  syncAmzAfterSales
} from '@/api/sop/afterSales'

const loading = ref(false)
const exporting = ref(false)
const importing = ref(false)
const syncing = ref(false)
const rangeBuilding = ref(false)
const rangeMessage = ref('')
const selectedMonths = ref([])
const coverageStart = ref('')
const coverageEnd = ref('')
const tableRef = ref()
const fileInput = ref()
const pendingImportType = ref('')
const pendingImportMonth = ref('')
const activePlatform = ref('amz')
const selectedRows = ref([])
const rows = ref([])
const total = ref(0)
const bigCategories = ref([])
const summary = reactive({})
let rangePollTimer
let loadSequence = 0
const query = reactive({
  platform: 'amz',
  pageNum: 1,
  pageSize: 20,
  startDate: undefined,
  endDate: undefined,
  bigCategory: '',
  smallCategory: '',
  sku: ''
})

const platformOptions = [
  {
    value: 'amz', code: 'AMZ', label: 'Amazon 售后率',
    description: '领星接口自动拉取销量与售后数据'
  },
  {
    value: 'ebay', code: 'eBay', label: 'eBay 售后率',
    description: '按自然月上传标准售后及销量文件'
  }
]

const platformDescription = computed(() => activePlatform.value === 'amz'
  ? '每周刷新当月；新月份首次任务强制补拉上个完整自然月，并自动完成去重、翻译、分类及售后率汇总。'
  : '首次可导入多月历史数据，后续按自然月整月覆盖；原始层和清洗层均保留可追溯数据。')

const rangeHint = computed(() => activePlatform.value === 'amz'
  ? '支持连续1至12个月；新月份区间首次查询会生成版本缓存，也可手工重新拉取。'
  : '支持连续1至12个月；上传后自动失效旧缓存，首次查询按所选月份重新汇总。')

const coverageMonthStart = computed(() => coverageStart.value?.slice(0, 7) || '')
const coverageMonthEnd = computed(() => coverageEnd.value?.slice(0, 7) || '')

const selectedMonthLabel = computed(() => {
  const [start, end] = selectedMonths.value || []
  if (!start || !end) return '--'
  return start === end ? start : `${start} 至 ${end}`
})

const selectedPeriodDescription = computed(() => {
  if (!query.startDate || !query.endDate) return '请选择月份'
  const endMonth = selectedMonths.value?.[1]
  const naturalEnd = monthEnd(endMonth)
  return query.endDate === naturalEnd
    ? `${query.startDate} 至 ${query.endDate}`
    : `${query.startDate} 至 ${query.endDate}（当月已有数据）`
})

const categoryOptions = computed(() => [
  { label: '全部', value: '' },
  ...bigCategories.value.map(item => ({ label: item, value: item }))
])

function monthStart(value) {
  return /^\d{4}-\d{2}$/.test(value || '') ? `${value}-01` : ''
}

function monthEnd(value) {
  if (!/^\d{4}-\d{2}$/.test(value || '')) return ''
  const [year, month] = value.split('-').map(Number)
  return `${value}-${String(new Date(year, month, 0).getDate()).padStart(2, '0')}`
}

function applyMonthRange(value) {
  const [startMonth, endMonth] = value || []
  if (!startMonth || !endMonth) {
    query.startDate = undefined
    query.endDate = undefined
    return
  }
  const naturalStart = monthStart(startMonth)
  const naturalEnd = monthEnd(endMonth)
  query.startDate = coverageStart.value && coverageStart.value > naturalStart
    ? coverageStart.value : naturalStart
  query.endDate = coverageEnd.value && coverageEnd.value < naturalEnd
    ? coverageEnd.value : naturalEnd
}

function disableUnavailableMonth(time) {
  const value = `${time.getFullYear()}-${String(time.getMonth() + 1).padStart(2, '0')}`
  return Boolean(
    (coverageMonthStart.value && value < coverageMonthStart.value) ||
    (coverageMonthEnd.value && value > coverageMonthEnd.value)
  )
}

function number(value) {
  return Number(value || 0).toLocaleString('zh-CN', { maximumFractionDigits: 2 })
}

function percent(value) {
  return `${(Number(value || 0) * 100).toFixed(2)}%`
}

async function loadMetadata(resetPeriod = false) {
  if (resetPeriod) {
    selectedMonths.value = []
    query.startDate = undefined
    query.endDate = undefined
  }
  const [categoryResponse, periodResponse] = await Promise.all([
    getAfterSalesCategories(activePlatform.value),
    listAfterSalesPeriods(activePlatform.value)
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
  if (!selectedMonths.value.length && periods.length) {
    const latest = periods[0]
    const latestMonth = String(latest.period_end || latest.period_start).slice(0, 7)
    selectedMonths.value = [latestMonth, latestMonth]
    applyMonthRange(selectedMonths.value)
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
      rangeMessage.value = response.rangeMessage || '正在后台生成所选月份区间的售后率'
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
      selectedMonths.value = [
        String(response.periodStart).slice(0, 7),
        String(response.periodEnd).slice(0, 7)
      ]
    }
  } catch (error) {
    if (sequence === loadSequence) stopRangePoll()
  } finally {
    if (sequence === loadSequence) loading.value = false
  }
}

async function changePlatform(platform) {
  if (platform === activePlatform.value || loading.value || importing.value) return
  stopRangePoll()
  loadSequence += 1
  activePlatform.value = platform
  query.platform = platform
  query.bigCategory = ''
  query.smallCategory = ''
  query.sku = ''
  query.pageNum = 1
  rows.value = []
  total.value = 0
  Object.keys(summary).forEach(key => delete summary[key])
  clearSelection()
  loading.value = true
  try {
    await loadMetadata(true)
    await loadData()
  } finally {
    loading.value = false
  }
}

async function chooseImportType(type) {
  if (type === 'monthly') {
    try {
      const { value } = await ElMessageBox.prompt(
        '请输入要整月覆盖的月份（YYYY-MM）。文件必须同时包含“售后数据”和“销量”工作表，且所有数据都属于该月份。',
        '上传 eBay 月度售后及销量',
        {
          confirmButtonText: '继续选择文件', cancelButtonText: '取消',
          inputValue: selectedMonths.value?.[0] || '',
          inputPattern: /^20\d{2}-(0[1-9]|1[0-2])$/,
          inputErrorMessage: '请输入YYYY-MM格式月份'
        }
      )
      pendingImportMonth.value = value
    } catch {
      return
    }
  }
  if (type === 'history') {
    try {
      await ElMessageBox.confirm(
        '仅首次初始化使用：标准文件应同时包含“售后数据”和“销量”工作表，可包含多个自然月。以后每月请使用“上传指定月份售后+销量”。是否继续？',
        '首次上传历史售后及销量',
        { type: 'warning', confirmButtonText: '继续选择文件', cancelButtonText: '取消' }
      )
    } catch {
      return
    }
  }
  pendingImportType.value = type
  if (fileInput.value) {
    fileInput.value.value = ''
    fileInput.value.click()
  }
}

async function handleImportFile(event) {
  const file = event.target.files?.[0]
  const type = pendingImportType.value
  if (!file || !type) return
  if (!/\.(xlsx|xlsm)$/i.test(file.name)) {
    ElMessage.error('只支持 .xlsx 或 .xlsm 文件')
    pendingImportType.value = ''
    pendingImportMonth.value = ''
    if (event.target) event.target.value = ''
    return
  }
  importing.value = true
  try {
    const response = await importEbayAfterSalesFile(type, file, pendingImportMonth.value)
    const result = response.data || {}
    ElMessage.success(
      `${result.message || '导入完成'}：原始层${number(result.raw_rows)}行，清洗层${number(result.dwd_rows)}行，跳过${number(result.skipped_rows)}行`
    )
    await loadMetadata(true)
    await loadData()
  } finally {
    importing.value = false
    pendingImportType.value = ''
    pendingImportMonth.value = ''
    if (event.target) event.target.value = ''
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

function handleMonthRangeChange(value) {
  const [startMonth, endMonth] = value || []
  if (startMonth && endMonth) {
    const [startYear, startValue] = startMonth.split('-').map(Number)
    const [endYear, endValue] = endMonth.split('-').map(Number)
    const monthCount = (endYear - startYear) * 12 + endValue - startValue + 1
    if (monthCount > 12) {
      ElMessage.warning('单次最多查询连续12个月')
      selectedMonths.value = []
      applyMonthRange([])
      return
    }
  }
  applyMonthRange(value)
  query.pageNum = 1
  stopRangePoll()
  clearSelection()
  if (value?.length === 2) {
    loadData()
    return
  }
  rows.value = []
  total.value = 0
  Object.keys(summary).forEach(key => delete summary[key])
}

async function handleAmzRefresh() {
  if (!query.startDate || !query.endDate) return
  try {
    await ElMessageBox.confirm(
      `将重新拉取${query.startDate}至${query.endDate}的领星销量和售后数据，并覆盖该区间汇总。是否继续？`,
      '重新拉取AMZ售后区间',
      { type: 'warning', confirmButtonText: '开始拉取', cancelButtonText: '取消' }
    )
  } catch {
    return
  }
  syncing.value = true
  try {
    await syncAmzAfterSales(query.startDate, query.endDate)
    ElMessage.success('AMZ售后区间重新拉取并计算完成')
    await loadMetadata()
    await loadData()
  } finally {
    syncing.value = false
  }
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
      const data = await exportAfterSalesData(activePlatform.value, query, selectedSkus)
      const selectedSuffix = selectedSkus.length ? `-已选${selectedSkus.length}个SKU` : ''
      downloadBlob(data, `${activePlatform.value === 'amz' ? 'AMZ' : 'eBay'}-SOP售后数据-${query.startDate}-${query.endDate}${selectedSuffix}`)
    } else if (command === 'categories') {
      const data = await exportAfterSales(activePlatform.value, query.startDate, query.endDate)
      downloadBlob(data, `${activePlatform.value === 'amz' ? 'AMZ' : 'eBay'}-SOP十类售后表-${query.startDate}-${query.endDate}`)
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
.hidden-file-input { display: none; }
.platform-switch {
  display: grid;
  grid-template-columns: repeat(2, minmax(280px, 1fr));
  gap: 12px;
  margin-bottom: 16px;
}
.platform-card {
  display: flex;
  align-items: center;
  gap: 13px;
  padding: 15px 17px;
  border: 1px solid #dfe5ee;
  border-radius: 12px;
  color: #334155;
  background: #fff;
  text-align: left;
  cursor: pointer;
  transition: .18s ease;
}
.platform-card:hover { border-color: #93c5fd; transform: translateY(-1px); }
.platform-card.active { border-color: #3b82f6; box-shadow: 0 0 0 2px #dbeafe; }
.platform-card.ebay.active { border-color: #8b5cf6; box-shadow: 0 0 0 2px #ede9fe; }
.platform-code {
  display: grid;
  width: 48px;
  height: 48px;
  flex: 0 0 48px;
  place-items: center;
  border-radius: 11px;
  color: #1d4ed8;
  background: #dbeafe;
  font-weight: 800;
}
.platform-card.ebay .platform-code { color: #6d28d9; background: #ede9fe; }
.platform-copy { display: flex; min-width: 0; flex: 1; flex-direction: column; gap: 4px; }
.platform-copy strong { color: #172033; font-size: 15px; }
.platform-copy small { color: #64748b; }
.platform-state { color: #94a3b8; font-size: 12px; }
.platform-card.active .platform-state { color: #2563eb; font-weight: 600; }
.summary-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(180px, 1fr));
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
.accent-cyan { border-top-color: #06b6d4; }
.accent-red { border-top-color: #ef4444; }
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
  .platform-switch { grid-template-columns: 1fr; }
  .filters { grid-template-columns: 1fr; }
  .detail-panel { margin-left: 8px; }
}
</style>
