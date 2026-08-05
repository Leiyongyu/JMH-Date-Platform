<script setup>
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'

const health = ref(null)
const globalError = ref('')
const customsOptions = ref([])
const customsSearch = ref('')
const exportDateStart = ref('')
const exportDateEnd = ref('')
const selectedCustomsNumbers = ref([])
const currentPage = ref(1)
const pageSize = 50
const inventory = ref({
  items: [],
  page: 1,
  page_size: 50,
  total: 0,
  total_pages: 1,
  summary: { original_quantity: 0, available_quantity: 0 },
})
const inventoryKeyword = ref('')
const inventoryAvailableOnly = ref(false)
const inventoryLoading = ref(false)

const performance = reactive({
  platform: 'combined',
  statMonth: '',
  principalName: '',
  orderBy: 'gross_profit',
  order: 'desc',
  page: 1,
  pageSize: 50,
  loading: false,
  refreshing: false,
  importLoading: false,
  ruleImportLoading: false,
  schedulerLoading: false,
  message: '',
  error: '',
  rankings: {
    platform: 'combined',
    stat_month: null,
    currency: 'CNY',
    partial: false,
    items: [],
    pagination: { page: 1, page_size: 50, total: 0 },
  },
  months: [],
  ruleSummary: null,
  schedulerTasks: [],
  schedulerRuns: [],
})
const ebayProfitInput = ref(null)
const ownerRuleInput = ref(null)
const ownerRulePlatform = ref('amazon')
const ownerRuleRebuild = ref(true)

const customsFolderInput = ref(null)
const purchaseInput = ref(null)
const receiptInput = ref(null)
const loading = reactive({ customs: false, purchase: false, receipt: false })
const messages = reactive({ purchase: '', receipt: '' })
const customsJob = ref(null)
let customsJobTimer = null

const showGenerationModal = ref(false)
const generation = reactive({ declaration_month: '', declaration_batch: '' })
const generationLoading = ref(false)
const generationMessage = ref('')
const generationError = ref('')
const generationErrors = ref([])
const downloadPackage = ref(null)

const importActions = [
  {
    key: 'customs',
    title: '导入报关资料文件夹',
    description: '递归读取文件夹内全部Excel，后台逐个处理',
    input: customsFolderInput,
    primary: true,
  },
  {
    key: 'purchase',
    title: '导入采购发票汇总',
    description: '读取全部年份Sheet并同步完整SKU库存',
    input: purchaseInput,
  },
  {
    key: 'receipt',
    title: '导入外汇回款汇总',
    description: '按合同协议号与报关单号增量更新',
    input: receiptInput,
  },
]

const dashboardCards = computed(() => [
  { label: '报关商品', value: health.value?.counts?.customs_declaration_items || 0 },
  { label: '采购发票商品', value: health.value?.counts?.purchase_invoice_summary || 0 },
  { label: '可用库存批次', value: health.value?.counts?.purchase_invoice_inventory || 0 },
  { label: '外汇回款', value: health.value?.counts?.foreign_exchange_receipts || 0 },
])

async function api(url, options = {}) {
  const response = await fetch(url, options)
  const data = await response.json().catch(() => ({}))
  if (!response.ok) throw new Error(data.message || `请求失败：${response.status}`)
  return data
}

async function apiV1(url, options = {}) {
  const response = await api(url, options)
  if (Object.prototype.hasOwnProperty.call(response, 'code')) {
    if (response.code !== 0) throw new Error(response.message || '业务请求失败')
    return response.data
  }
  return response
}

async function loadHealth() {
  health.value = await api('/api/health')
}

async function loadCustomsOptions() {
  customsOptions.value = await api('/api/customs-declarations/options')
}

async function loadInventory(page = inventory.value.page || 1) {
  inventoryLoading.value = true
  try {
    const query = new URLSearchParams({
      page: String(page),
      page_size: '50',
      keyword: inventoryKeyword.value.trim(),
      available_only: String(inventoryAvailableOnly.value),
    })
    inventory.value = await api(`/api/inventory?${query}`)
  } finally {
    inventoryLoading.value = false
  }
}

async function loadPerformanceRankings(page = performance.page || 1) {
  performance.loading = true
  performance.error = ''
  try {
    const query = new URLSearchParams({
      platform: performance.platform,
      order_by: performance.orderBy,
      order: performance.order,
      page: String(page),
      page_size: String(performance.pageSize),
    })
    if (performance.statMonth.trim()) query.set('stat_month', performance.statMonth.trim())
    if (performance.principalName.trim()) query.set('principal_name', performance.principalName.trim())
    performance.rankings = await apiV1(`/api/v1/finance/performance-rankings?${query}`)
    performance.page = performance.rankings.pagination?.page || page
  } catch (error) {
    performance.error = error.message
  } finally {
    performance.loading = false
  }
}

async function loadPerformanceMonths() {
  try {
    performance.months = await apiV1('/api/v1/finance/performance-months?limit=12')
  } catch (error) {
    performance.error = error.message
  }
}

async function refreshPerformance() {
  if (!performance.statMonth.trim()) {
    performance.error = '请先输入统计月份，例如 2026-06'
    return
  }
  performance.refreshing = true
  performance.error = ''
  performance.message = ''
  try {
    const result = await apiV1('/api/v1/finance/performance-refreshes', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        stat_month: performance.statMonth.trim(),
        platform: performance.platform,
        require_all_platforms: false,
      }),
    })
    performance.message = `刷新完成：综合 ${result.combined_ranking_rows || 0} 行，AMZ ${result.amz_ranking_rows || 0} 行，eBay ${result.ebay_ranking_rows || 0} 行`
    await Promise.all([loadPerformanceRankings(1), loadPerformanceMonths()])
  } catch (error) {
    performance.error = error.message
  } finally {
    performance.refreshing = false
  }
}

async function uploadEbayProfit(event) {
  const file = event.target.files?.[0]
  event.target.value = ''
  if (!file) return
  performance.importLoading = true
  performance.error = ''
  performance.message = ''
  try {
    const formData = new FormData()
    formData.append('file', file)
    const result = await apiV1('/api/v1/finance/ebay-profit-imports?rebuild=true', {
      method: 'POST',
      body: formData,
    })
    performance.statMonth = result.stat_month || performance.statMonth
    performance.message = `eBay利润导入完成：${result.inserted_rows || 0} 行，月份 ${result.stat_month}`
    await Promise.all([loadPerformanceRankings(1), loadPerformanceMonths()])
  } catch (error) {
    performance.error = error.message
  } finally {
    performance.importLoading = false
  }
}

async function uploadOwnerRules(event) {
  const file = event.target.files?.[0]
  event.target.value = ''
  if (!file) return
  performance.ruleImportLoading = true
  performance.error = ''
  performance.message = ''
  try {
    const query = new URLSearchParams({
      platform: ownerRulePlatform.value,
      rebuild: String(ownerRuleRebuild.value),
    })
    if (performance.statMonth.trim()) query.set('stat_month', performance.statMonth.trim())
    const formData = new FormData()
    formData.append('file', file)
    const result = await apiV1(`/api/v1/finance/performance-owner-rule-imports?${query}`, {
      method: 'POST',
      body: formData,
    })
    performance.message = `${ownerRulePlatform.value === 'amazon' ? 'AMZ' : 'eBay'}负责人规则导入完成：${result.imported_rows || 0} 条，覆盖 ${result.month_count || 0} 个月份`
    await Promise.all([loadOwnerRuleSummary(), loadPerformanceRankings(1), loadPerformanceMonths()])
  } catch (error) {
    performance.error = error.message
  } finally {
    performance.ruleImportLoading = false
  }
}

async function loadOwnerRuleSummary() {
  if (!performance.statMonth.trim()) return
  try {
    performance.ruleSummary = await apiV1(`/api/v1/finance/performance-owner-rule-summaries?platform=${ownerRulePlatform.value}&stat_month=${performance.statMonth.trim()}`)
  } catch (error) {
    performance.error = error.message
  }
}

async function loadScheduler() {
  try {
    performance.schedulerTasks = await apiV1('/api/v1/internal/scheduler/tasks')
    const taskCode = performance.schedulerTasks[0]?.task_code
    if (taskCode) {
      performance.schedulerRuns = await apiV1(`/api/v1/internal/scheduler/tasks/${taskCode}/runs?limit=10`)
    }
  } catch (error) {
    performance.error = error.message
  }
}

async function runAmzScheduler() {
  const taskCode = performance.schedulerTasks[0]?.task_code || 'amz_monthly_order_profit_sync'
  performance.schedulerLoading = true
  performance.error = ''
  performance.message = ''
  try {
    const result = await apiV1(`/api/v1/internal/scheduler/tasks/${taskCode}/run`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ stat_month: performance.statMonth.trim() || null }),
    })
    performance.message = `AMZ内部任务完成：${result.result?.stat_month || ''}，写入 ${result.result?.upsert_rows || 0} 行`
    await Promise.all([loadScheduler(), loadPerformanceRankings(1), loadPerformanceMonths()])
  } catch (error) {
    performance.error = error.message
  } finally {
    performance.schedulerLoading = false
  }
}

const performanceTotals = computed(() => {
  const items = performance.rankings.items || []
  return items.reduce((summary, row) => {
    summary.gross += Number(row.grossProfit ?? row.gross_profit ?? 0)
    summary.net += Number(row.netSalesAmount ?? row.net_sales_amount ?? 0)
    return summary
  }, { gross: 0, net: 0 })
})

const grossProfitRanking = computed(() => sortPerformanceRanking('grossProfit'))
const netSalesRanking = computed(() => sortPerformanceRanking('netSalesAmount'))

function sortPerformanceRanking(field) {
  return [...(performance.rankings.items || [])]
    .sort((left, right) => Number(right[field] ?? 0) - Number(left[field] ?? 0))
}

function maxPerformanceValue(items, field) {
  return Math.max(...items.map(item => Math.abs(Number(item[field] ?? 0))), 1)
}

function performanceBarWidth(item, field, items) {
  const value = Math.abs(Number(item[field] ?? 0))
  return `${Math.max(4, (value / maxPerformanceValue(items, field)) * 100)}%`
}

function performanceOwner(row) {
  return row.principalNames || row.principal_name || '未分配'
}

function formatPerformanceMoney(value) {
  return Number(value || 0).toLocaleString('zh-CN', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })
}

function openPicker(action) {
  action.input.value?.click()
}

function clearPollTimer() {
  if (customsJobTimer) {
    window.clearTimeout(customsJobTimer)
    customsJobTimer = null
  }
}

async function pollCustomsJob(jobId) {
  try {
    const job = await api(`/api/import-jobs/${jobId}`)
    customsJob.value = job
    if (['queued', 'running'].includes(job.status)) {
      customsJobTimer = window.setTimeout(() => pollCustomsJob(jobId), 800)
      return
    }
    loading.customs = false
    await Promise.all([loadHealth(), loadCustomsOptions(), loadInventory(1)])
  } catch (error) {
    loading.customs = false
    globalError.value = `报关资料任务：${error.message}`
  }
}

async function uploadCustomsFolder(event) {
  const selectedFiles = Array.from(event.target.files || [])
  event.target.value = ''
  if (!selectedFiles.length) return

  const excelFiles = selectedFiles.filter(file => (
    !file.name.startsWith('~$') && /\.(xlsx|xlsm)$/i.test(file.name)
  ))
  if (!excelFiles.length) {
    globalError.value = '所选文件夹中没有可导入的报关资料Excel'
    return
  }

  loading.customs = true
  customsJob.value = null
  globalError.value = ''
  clearPollTimer()
  try {
    const formData = new FormData()
    excelFiles.forEach(file => {
      formData.append('files', file, file.webkitRelativePath || file.name)
    })
    const job = await api('/api/import-jobs/customs-folder', {
      method: 'POST',
      body: formData,
    })
    customsJob.value = job
    await pollCustomsJob(job.job_id)
  } catch (error) {
    loading.customs = false
    globalError.value = `报关资料文件夹：${error.message}`
  }
}

function formatSingleImport(result) {
  const rows = Number(result.processed_rows || 0).toLocaleString('zh-CN')
  const replaced = Number(result.replaced_rows || 0).toLocaleString('zh-CN')
  const inventory = Number(result.inventory_rows || 0).toLocaleString('zh-CN')
  const ordered = Number(
    result.remark_ordered_sku_rows ?? result.remark_validated_sku_rows ?? 0
  )
  const unresolved = Number(result.unresolved_sku_rows || 0)
  const skuSummary = Object.prototype.hasOwnProperty.call(result, 'remark_ordered_sku_rows')
    || Object.prototype.hasOwnProperty.call(result, 'remark_validated_sku_rows')
    ? `，备注顺序补全SKU ${ordered.toLocaleString('zh-CN')} 行${unresolved ? `，仍有 ${unresolved.toLocaleString('zh-CN')} 行备注无可用SKU` : ''}`
    : ''
  return `处理完成：写入 ${rows} 行，覆盖 ${replaced} 行${Number(result.inventory_rows || 0) ? `，同步库存 ${inventory} 行` : ''}${skuSummary}`
}

async function uploadSingle(kind, event) {
  const file = event.target.files?.[0]
  event.target.value = ''
  if (!file) return

  const config = kind === 'purchase'
    ? { endpoint: '/api/upload/purchase-invoice-summary', label: '采购发票汇总' }
    : { endpoint: '/api/upload/foreign-exchange-receipts', label: '外汇回款汇总' }
  loading[kind] = true
  messages[kind] = ''
  globalError.value = ''
  try {
    const formData = new FormData()
    formData.append('file', file)
    const result = await api(config.endpoint, { method: 'POST', body: formData })
    messages[kind] = formatSingleImport(result)
    await Promise.all([loadHealth(), loadCustomsOptions(), loadInventory(1)])
  } catch (error) {
    globalError.value = `${config.label}：${error.message}`
  } finally {
    loading[kind] = false
  }
}

const customsJobPercent = computed(() => {
  if (!customsJob.value?.total_files) return 0
  return Math.round(customsJob.value.processed_files / customsJob.value.total_files * 100)
})

const customsJobLabel = computed(() => {
  const status = customsJob.value?.status
  if (status === 'queued') return '等待处理'
  if (status === 'running') return '正在处理'
  if (status === 'completed') return '全部完成'
  if (status === 'completed_with_errors') return '完成，部分失败'
  if (status === 'failed') return '任务失败'
  return ''
})

const filteredCustomsOptions = computed(() => {
  const keyword = customsSearch.value.trim().toUpperCase()
  const startDate = exportDateStart.value.trim()
  const endDate = exportDateEnd.value.trim()
  return customsOptions.value.filter(row => (
    (!keyword
      || String(row.customs_declaration_no || '').toUpperCase().includes(keyword)
      || String(row.contract_no || '').toUpperCase().includes(keyword))
    && (!startDate || (row.export_date && String(row.export_date) >= startDate))
    && (!endDate || (row.export_date && String(row.export_date) <= endDate))
  ))
})

const totalPages = computed(() => Math.max(1, Math.ceil(filteredCustomsOptions.value.length / pageSize)))
const paginatedCustomsOptions = computed(() => {
  const start = (currentPage.value - 1) * pageSize
  return filteredCustomsOptions.value.slice(start, start + pageSize)
})

const selectableFilteredCustomsOptions = computed(() => (
  filteredCustomsOptions.value.filter(row => row.selectable)
))

const pageAllSelected = computed({
  get() {
    const selectableRows = paginatedCustomsOptions.value.filter(row => row.selectable)
    return selectableRows.length > 0
      && selectableRows.every(row => selectedCustomsNumbers.value.includes(row.customs_declaration_no))
  },
  set(checked) {
    const pageNumbers = paginatedCustomsOptions.value
      .filter(row => row.selectable)
      .map(row => row.customs_declaration_no)
    if (checked) {
      selectedCustomsNumbers.value = [...new Set([...selectedCustomsNumbers.value, ...pageNumbers])]
    } else {
      selectedCustomsNumbers.value = selectedCustomsNumbers.value.filter(value => !pageNumbers.includes(value))
    }
  },
})

const allFilteredSelected = computed(() => (
  selectableFilteredCustomsOptions.value.length > 0
  && selectedCustomsNumbers.value.length === new Set(
    selectableFilteredCustomsOptions.value.map(row => row.customs_declaration_no).filter(Boolean),
  ).size
  && selectableFilteredCustomsOptions.value.every(
    row => selectedCustomsNumbers.value.includes(row.customs_declaration_no),
  )
))

function selectAllCustoms() {
  selectedCustomsNumbers.value = [
    ...new Set(selectableFilteredCustomsOptions.value.map(
      row => row.customs_declaration_no,
    ).filter(Boolean)),
  ]
}

function clearCustomsSelection() {
  selectedCustomsNumbers.value = []
}

watch(customsSearch, () => { currentPage.value = 1 })
watch([exportDateStart, exportDateEnd], () => {
  currentPage.value = 1
  selectedCustomsNumbers.value = []
})
watch(totalPages, pages => {
  if (currentPage.value > pages) currentPage.value = pages
})

function openGenerationModal() {
  if (!selectedCustomsNumbers.value.length) return
  generation.declaration_month = ''
  generation.declaration_batch = ''
  generationError.value = ''
  generationErrors.value = []
  showGenerationModal.value = true
}

async function generateDetails() {
  generationLoading.value = true
  generationError.value = ''
  generationErrors.value = []
  downloadPackage.value = null
  try {
    const result = await api('/api/customs-declarations/batch-convert-to-export-details', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        customs_declaration_numbers: selectedCustomsNumbers.value,
        declaration_month: generation.declaration_month,
        declaration_batch: generation.declaration_batch,
      }),
    })
    generationErrors.value = result.errors || []
    if (result.successful_customs_declaration_count > 0) {
      const packageResult = await api('/api/export/final-package', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ errors: generationErrors.value }),
      })
      downloadPackage.value = packageResult.download_package || null
    }
    generationMessage.value = `本次选择 ${result.customs_declaration_count} 张，成功 ${result.successful_customs_declaration_count} 张，跳过 ${result.failed_customs_declaration_count} 张；生成出口明细 ${result.processed_rows} 行、FIFO进货 ${result.new_inventory_allocation_rows} 行`
    selectedCustomsNumbers.value = generationErrors.value.map(item => item.customs_declaration_no)
    showGenerationModal.value = false
    await Promise.all([loadHealth(), loadCustomsOptions(), loadInventory(1)])
  } catch (error) {
    generationError.value = error.message
  } finally {
    generationLoading.value = false
  }
}

onMounted(() => {
  Promise.all([
    loadHealth(),
    loadCustomsOptions(),
    loadInventory(1),
    loadPerformanceRankings(1),
    loadPerformanceMonths(),
    loadScheduler(),
  ])
    .catch(error => { globalError.value = error.message })
})
onBeforeUnmount(clearPollTimer)
</script>

<template>
  <div class="erp-layout">
    <aside class="erp-sidebar">
      <div class="erp-logo">
        <span>DP</span>
        <div><strong>Data Project</strong><small>外汇退税管理</small></div>
      </div>
      <nav>
        <a class="active" href="#data-import"><i>01</i>数据导入</a>
        <a href="#declaration-workbench"><i>02</i>申报工作台</a>
        <a href="#inventory-query"><i>03</i>库存查询</a>
        <a href="#performance-ranking"><i>04</i>绩效排名测试</a>
      </nav>
      <div class="sidebar-status">
        <span :class="{ online: health?.ok }"></span>
        <div><strong>{{ health?.ok ? '系统运行正常' : '连接检查中' }}</strong><small>{{ health?.database || 'Date-Project' }}</small></div>
      </div>
    </aside>

    <div class="erp-content">
      <header class="erp-header">
        <div><h1>外汇退税业务工作台</h1><p>数据导入、申报生成与文件下载</p></div>
        <div class="header-meta"><span>MySQL {{ health?.mysql_version || '—' }}</span><strong>管理员</strong></div>
      </header>

      <main class="erp-main">
        <section class="summary-grid">
          <article v-for="item in dashboardCards" :key="item.label">
            <span>{{ item.label }}</span>
            <strong>{{ Number(item.value).toLocaleString('zh-CN') }}</strong>
            <small>当前数据库记录</small>
          </article>
        </section>

        <section id="data-import" class="erp-panel">
          <div class="panel-header">
            <div><h2>数据导入</h2><p>选择数据源后立即上传；重复上传按业务键增量覆盖</p></div>
          </div>

          <div class="action-toolbar">
            <button
              v-for="action in importActions"
              :key="action.key"
              class="import-action"
              :class="{ primary: action.primary }"
              :disabled="loading[action.key]"
              @click="openPicker(action)"
            >
              <span class="action-icon">{{ action.key === 'customs' ? '夹' : '表' }}</span>
              <span><strong>{{ loading[action.key] ? '处理中…' : action.title }}</strong><small>{{ action.description }}</small></span>
            </button>
          </div>

          <input ref="customsFolderInput" class="hidden-input" type="file" webkitdirectory directory multiple @change="uploadCustomsFolder" />
          <input ref="purchaseInput" class="hidden-input" type="file" accept=".xlsx,.xlsm" @change="uploadSingle('purchase', $event)" />
          <input ref="receiptInput" class="hidden-input" type="file" accept=".xlsx,.xlsm" @change="uploadSingle('receipt', $event)" />

          <div v-if="customsJob" class="job-panel" :class="{ warning: customsJob.failed_files, success: customsJob.status === 'completed' }">
            <div class="job-title">
              <div><strong>报关资料文件夹导入</strong><span>{{ customsJobLabel }}</span></div>
              <b>{{ customsJob.processed_files }} / {{ customsJob.total_files }}</b>
            </div>
            <div class="progress-track"><span :style="{ width: `${customsJobPercent}%` }"></span></div>
            <div class="job-metrics">
              <span>成功 {{ customsJob.succeeded_files }}</span>
              <span>失败 {{ customsJob.failed_files }}</span>
              <span>写入商品 {{ Number(customsJob.processed_rows || 0).toLocaleString('zh-CN') }} 行</span>
              <span v-if="customsJob.current_file">当前：{{ customsJob.current_file }}</span>
            </div>
            <details v-if="customsJob.errors?.length">
              <summary>查看失败文件与原因（{{ customsJob.errors.length }}）</summary>
              <p v-for="item in customsJob.errors" :key="item.file_name"><b>{{ item.file_name }}</b>{{ item.error }}</p>
            </details>
          </div>

          <div v-if="messages.purchase || messages.receipt" class="import-messages">
            <p v-if="messages.purchase"><b>采购发票：</b>{{ messages.purchase }}</p>
            <p v-if="messages.receipt"><b>外汇回款：</b>{{ messages.receipt }}</p>
          </div>
          <p v-if="globalError" class="alert-error">{{ globalError }}</p>
        </section>

        <section id="declaration-workbench" class="erp-panel declaration-panel">
          <div class="panel-header declaration-heading">
            <div><h2>申报工作台</h2><p>筛选并多选报关单，统一填写申报年月与批次后生成下载包</p></div>
            <button class="primary-button" :disabled="!selectedCustomsNumbers.length" @click="openGenerationModal">
              生成所选批次（{{ selectedCustomsNumbers.length }}）
            </button>
          </div>

          <div class="filter-bar">
            <label><span>关键词</span><input v-model="customsSearch" placeholder="报关单号 / 合同协议号" /></label>
            <label><span>出口日期从</span><input v-model="exportDateStart" type="date" /></label>
            <label><span>出口日期至</span><input v-model="exportDateEnd" type="date" /></label>
            <div class="filter-result">
              共 {{ filteredCustomsOptions.length }} 条，可生成 {{ selectableFilteredCustomsOptions.length }} 条
            </div>
          </div>

          <div class="data-table-wrap">
            <table class="data-table">
              <thead><tr>
                <th class="check-col"><input v-model="pageAllSelected" type="checkbox" title="选择当前页" /></th>
                <th>报关单号</th><th>合同协议号</th><th>出口日期</th>
                <th>商业发票号</th><th>商品数</th><th>处理状态</th>
              </tr></thead>
              <tbody>
                <tr v-for="row in paginatedCustomsOptions" :key="`${row.customs_declaration_no}-${row.contract_no}`">
                  <td>
                    <input
                      v-model="selectedCustomsNumbers"
                      type="checkbox"
                      :value="row.customs_declaration_no"
                      :disabled="!row.selectable"
                      :title="row.has_customs_data ? (row.ambiguous_contract ? '报关单号对应多个合同，不能生成' : '') : '缺少按合同号和报关总金额唯一匹配的报关Excel'"
                    />
                  </td>
                  <td class="mono">{{ row.customs_declaration_no }}</td>
                  <td>{{ row.contract_no }}</td>
                  <td>{{ row.export_date || '—' }}</td>
                  <td>{{ row.invoice_no || '—' }}</td>
                  <td>{{ row.item_count || '—' }}</td>
                  <td>
                    <span v-if="!row.has_customs_data" class="status-tag missing">报关资料未匹配</span>
                    <span v-else-if="row.ambiguous_contract" class="status-tag blocked">报关单号重复</span>
                    <span v-else class="status-tag" :class="{ done: row.converted }">
                      {{ row.converted ? '已生成' : '待生成' }}
                    </span>
                  </td>
                </tr>
                <tr v-if="!paginatedCustomsOptions.length"><td colspan="7" class="empty-cell">暂无符合条件的数据</td></tr>
              </tbody>
            </table>
          </div>

          <div class="table-footer">
            <div class="selection-actions">
              <span>已选择 {{ selectedCustomsNumbers.length }} 条</span>
              <button :disabled="!selectableFilteredCustomsOptions.length || allFilteredSelected" @click="selectAllCustoms">
                全选可生成（{{ selectableFilteredCustomsOptions.length }}）
              </button>
              <button :disabled="!selectedCustomsNumbers.length" @click="clearCustomsSelection">清空选择</button>
            </div>
            <div class="pagination">
              <button :disabled="currentPage <= 1" @click="currentPage--">上一页</button>
              <span>第 {{ currentPage }} / {{ totalPages }} 页</span>
              <button :disabled="currentPage >= totalPages" @click="currentPage++">下一页</button>
            </div>
          </div>

          <div v-if="generationMessage || downloadPackage || generationErrors.length" class="generation-result">
            <div>
              <span>{{ generationMessage }}</span>
              <details v-if="generationErrors.length" class="generation-errors">
                <summary>查看本次跳过的错误（{{ generationErrors.length }}）</summary>
                <p v-for="(item, index) in generationErrors" :key="`${item.customs_declaration_no}-${index}`">
                  <b>{{ item.customs_declaration_no }}</b>
                  <em v-if="item.contract_no">{{ item.contract_no }}</em>
                  <em v-if="item.item_no">项号 {{ item.item_no }}</em>
                  <em v-if="item.sku">{{ item.sku }}</em>
                  {{ item.error }}
                </p>
              </details>
            </div>
            <a v-if="downloadPackage" :href="downloadPackage.url" download>下载全部生成文件</a>
          </div>
        </section>

        <section id="inventory-query" class="erp-panel inventory-panel">
          <div class="panel-header">
            <div><h2>库存查询</h2><p>采购发票商品库存明细，按开票日期从早到晚展示FIFO批次</p></div>
            <div class="inventory-summary">
              <span>记录数 <b>{{ Number(inventory.total).toLocaleString('zh-CN') }}</b></span>
              <span>原始数量 <b>{{ Number(inventory.summary.original_quantity || 0).toLocaleString('zh-CN') }}</b></span>
              <span>可用数量 <b>{{ Number(inventory.summary.available_quantity || 0).toLocaleString('zh-CN') }}</b></span>
            </div>
          </div>

          <div class="inventory-filter">
            <label><span>库存关键词</span><input v-model.trim="inventoryKeyword" placeholder="SKU / 发票号 / 销售方 / 项目名称" @keyup.enter="loadInventory(1)" /></label>
            <label class="switch-label"><input v-model="inventoryAvailableOnly" type="checkbox" /><span>只看有库存</span></label>
            <button class="primary-button" :disabled="inventoryLoading" @click="loadInventory(1)">{{ inventoryLoading ? '查询中…' : '查询库存' }}</button>
          </div>

          <div class="data-table-wrap">
            <table class="data-table inventory-table">
              <thead><tr>
                <th>库存匹配值</th><th>类型</th><th>项目名称</th><th>单位</th><th>原始数量</th><th>可用数量</th>
                <th>发票号码</th><th>开票日期</th><th>销售方</th><th>纳税人识别号</th>
              </tr></thead>
              <tbody>
                <tr v-for="row in inventory.items" :key="row.id">
                  <td class="mono">{{ row.specification }}</td>
                  <td>{{ row.inventory_match_type === 'PRODUCT_NAME' ? '通用品名' : '精确SKU' }}</td>
                  <td class="project-cell" :title="row.project_name">{{ row.project_name }}</td>
                  <td>{{ row.unit }}</td>
                  <td>{{ Number(row.original_quantity).toLocaleString('zh-CN') }}</td>
                  <td><b :class="{ depleted: Number(row.available_quantity) <= 0 }">{{ Number(row.available_quantity).toLocaleString('zh-CN') }}</b></td>
                  <td class="mono">{{ row.invoice_no }}</td>
                  <td>{{ row.invoice_date }}</td>
                  <td class="seller-cell" :title="row.seller_name">{{ row.seller_name }}</td>
                  <td class="mono">{{ row.seller_tax_id }}</td>
                </tr>
                <tr v-if="!inventoryLoading && !inventory.items.length"><td colspan="10" class="empty-cell">暂无符合条件的库存数据</td></tr>
                <tr v-if="inventoryLoading"><td colspan="10" class="empty-cell">正在读取库存…</td></tr>
              </tbody>
            </table>
          </div>
          <div class="table-footer">
            <span>第 {{ inventory.page }} / {{ inventory.total_pages }} 页，每页 {{ inventory.page_size }} 条</span>
            <div class="pagination">
              <button :disabled="inventoryLoading || inventory.page <= 1" @click="loadInventory(inventory.page - 1)">上一页</button>
              <button :disabled="inventoryLoading || inventory.page >= inventory.total_pages" @click="loadInventory(inventory.page + 1)">下一页</button>
            </div>
          </div>
        </section>

        <section id="performance-ranking" class="erp-panel performance-panel">
          <div class="panel-header">
            <div>
              <h2>财务中心绩效排名测试页</h2>
              <p>直接对接 Python `/api/v1/finance` 与内部定时任务接口，暂不对接 ERP</p>
            </div>
            <div class="performance-badges">
              <span>当前平台 <b>{{ performance.platform }}</b></span>
              <span>月份 <b>{{ performance.rankings.stat_month || '暂无' }}</b></span>
              <span :class="{ warning: performance.rankings.partial }">
                {{ performance.rankings.partial ? '单平台临时结果' : '完整/待确认' }}
              </span>
            </div>
          </div>

          <div class="performance-grid">
            <article>
              <span>本页毛利润合计</span>
              <strong>{{ performanceTotals.gross.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) }}</strong>
              <small>CNY，按当前页数据汇总</small>
            </article>
            <article>
              <span>本页净销售额合计</span>
              <strong>{{ performanceTotals.net.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) }}</strong>
              <small>CNY，按当前页数据汇总</small>
            </article>
            <article>
              <span>排名总数</span>
              <strong>{{ Number(performance.rankings.pagination?.total || 0).toLocaleString('zh-CN') }}</strong>
              <small>当前筛选条件</small>
            </article>
            <article>
              <span>最近月份数</span>
              <strong>{{ performance.months.length }}</strong>
              <small>来源于 performance-months</small>
            </article>
          </div>

          <div class="performance-controls">
            <label>
              <span>平台</span>
              <select v-model="performance.platform" @change="loadPerformanceRankings(1)">
                <option value="combined">综合</option>
                <option value="amazon">Amazon</option>
                <option value="ebay">eBay</option>
              </select>
            </label>
            <label>
              <span>统计月份</span>
              <input v-model.trim="performance.statMonth" placeholder="2026-06" @keyup.enter="loadPerformanceRankings(1)" />
            </label>
            <label>
              <span>负责人</span>
              <input v-model.trim="performance.principalName" placeholder="模糊查询" @keyup.enter="loadPerformanceRankings(1)" />
            </label>
            <label>
              <span>排序字段</span>
              <select v-model="performance.orderBy" @change="loadPerformanceRankings(1)">
                <option value="gross_profit">毛利润</option>
                <option value="net_sales_amount">净销售额</option>
              </select>
            </label>
            <label>
              <span>排序</span>
              <select v-model="performance.order" @change="loadPerformanceRankings(1)">
                <option value="desc">降序</option>
                <option value="asc">升序</option>
              </select>
            </label>
            <button class="primary-button" :disabled="performance.loading" @click="loadPerformanceRankings(1)">
              {{ performance.loading ? '查询中…' : '查询排名' }}
            </button>
            <button class="secondary-button" :disabled="performance.refreshing" @click="refreshPerformance">
              {{ performance.refreshing ? '刷新中…' : '刷新排名' }}
            </button>
          </div>

          <div class="performance-actions">
            <button class="import-action mini" :disabled="performance.importLoading" @click="ebayProfitInput?.click()">
              <span class="action-icon">EB</span>
              <span><strong>{{ performance.importLoading ? '导入中…' : '导入 eBay 利润' }}</strong><small>Excel → ODS/DWD → 自动刷新</small></span>
            </button>
            <div class="rule-import-card">
              <label>
                <span>规则平台</span>
                <select v-model="ownerRulePlatform" @change="loadOwnerRuleSummary">
                  <option value="amazon">Amazon负责人规则</option>
                  <option value="ebay">eBay负责人规则</option>
                </select>
              </label>
              <label class="switch-line">
                <input v-model="ownerRuleRebuild" type="checkbox" />
                <span>导入后自动刷新</span>
              </label>
              <button class="secondary-button" :disabled="performance.ruleImportLoading" @click="ownerRuleInput?.click()">
                {{ performance.ruleImportLoading ? '导入中…' : '导入负责人规则' }}
              </button>
              <button class="secondary-button" @click="loadOwnerRuleSummary">规则摘要</button>
            </div>
            <button class="import-action mini internal" :disabled="performance.schedulerLoading" @click="runAmzScheduler">
              <span class="action-icon">AMZ</span>
              <span><strong>{{ performance.schedulerLoading ? '执行中…' : '执行AMZ内部同步' }}</strong><small>每月4日22:00任务，可手动指定月份</small></span>
            </button>
          </div>

          <input ref="ebayProfitInput" class="hidden-input" type="file" accept=".xlsx,.xls" @change="uploadEbayProfit" />
          <input ref="ownerRuleInput" class="hidden-input" type="file" accept=".xlsx,.xls" @change="uploadOwnerRules" />

          <p v-if="performance.message" class="import-messages"><b>绩效：</b>{{ performance.message }}</p>
          <p v-if="performance.error" class="alert-error">{{ performance.error }}</p>

          <div class="months-strip" v-if="performance.months.length">
            <button
              v-for="month in performance.months"
              :key="month.stat_month"
              :class="{ active: performance.statMonth === month.stat_month, partial: month.partial }"
              @click="performance.statMonth = month.stat_month; loadPerformanceRankings(1)"
            >
              <strong>{{ month.stat_month }}</strong>
              <span>
                AMZ {{ month.amazon_ready ? '✓' : '—' }} /
                eBay {{ month.ebay_ready ? '✓' : '—' }} /
                综合 {{ month.combined_ready ? '✓' : '—' }}
              </span>
            </button>
          </div>

          <div class="performance-chart-grid">
            <article class="performance-chart-card">
              <header>
                <div>
                  <h3>毛利润排名</h3>
                  <p>AMZ 与 eBay 各负责人毛利润合计</p>
                </div>
                <span v-if="grossProfitRanking.length">{{ performanceOwner(grossProfitRanking[0]) }}</span>
              </header>
              <div class="ranking-bars">
                <div v-for="(row, index) in grossProfitRanking" :key="`gross-${row.id || index}-${performanceOwner(row)}`" class="ranking-bar-row">
                  <b>{{ performanceOwner(row) }}</b>
                  <div class="ranking-bar-track">
                    <i class="gross" :style="{ width: performanceBarWidth(row, 'grossProfit', grossProfitRanking) }"></i>
                  </div>
                  <em>{{ formatPerformanceMoney(row.grossProfit) }}</em>
                </div>
                <p v-if="!grossProfitRanking.length" class="empty-cell">暂无毛利润排名数据</p>
              </div>
            </article>

            <article class="performance-chart-card">
              <header>
                <div>
                  <h3>净销售额排名</h3>
                  <p>净销售额 = 销售额 - 退款金额</p>
                </div>
                <span v-if="netSalesRanking.length">{{ performanceOwner(netSalesRanking[0]) }}</span>
              </header>
              <div class="ranking-bars">
                <div v-for="(row, index) in netSalesRanking" :key="`net-${row.id || index}-${performanceOwner(row)}`" class="ranking-bar-row">
                  <b>{{ performanceOwner(row) }}</b>
                  <div class="ranking-bar-track">
                    <i class="net" :style="{ width: performanceBarWidth(row, 'netSalesAmount', netSalesRanking) }"></i>
                  </div>
                  <em>{{ formatPerformanceMoney(row.netSalesAmount) }}</em>
                </div>
                <p v-if="!netSalesRanking.length" class="empty-cell">暂无净销售额排名数据</p>
              </div>
            </article>
          </div>

          <div class="data-table-wrap">
            <table class="data-table performance-table">
              <thead>
                <tr>
                  <th>负责人</th>
                  <th>毛利润</th>
                  <th>净销售额</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="(row, index) in performance.rankings.items" :key="`${index}-${performanceOwner(row)}`">
                  <td>{{ performanceOwner(row) }}</td>
                  <td class="money-cell">{{ formatPerformanceMoney(row.grossProfit ?? row.gross_profit) }}</td>
                  <td class="money-cell">{{ formatPerformanceMoney(row.netSalesAmount ?? row.net_sales_amount) }}</td>
                </tr>
                <tr v-if="!performance.loading && !performance.rankings.items.length">
                  <td colspan="3" class="empty-cell">暂无绩效排名数据，可先导入或刷新指定月份</td>
                </tr>
                <tr v-if="performance.loading">
                  <td colspan="3" class="empty-cell">正在读取绩效排名…</td>
                </tr>
              </tbody>
            </table>
          </div>

          <div class="table-footer">
            <span>
              第 {{ performance.rankings.pagination?.page || 1 }} 页，
              共 {{ Number(performance.rankings.pagination?.total || 0).toLocaleString('zh-CN') }} 条
            </span>
            <div class="pagination">
              <button :disabled="performance.loading || performance.page <= 1" @click="loadPerformanceRankings(performance.page - 1)">上一页</button>
              <button
                :disabled="performance.loading || performance.page * performance.pageSize >= (performance.rankings.pagination?.total || 0)"
                @click="loadPerformanceRankings(performance.page + 1)"
              >下一页</button>
            </div>
          </div>

          <div class="performance-bottom-grid">
            <article>
              <h3>负责人规则摘要</h3>
              <p v-if="!performance.ruleSummary">选择月份和平台后点击“规则摘要”。</p>
              <ul v-else>
                <li v-for="item in performance.ruleSummary.items" :key="`${item.group_code}-${item.rule_type}`">
                  <span>{{ item.group_code || 'eBay' }} / {{ item.rule_type }}</span>
                  <b>{{ item.rule_count }}</b>
                </li>
                <li v-if="!performance.ruleSummary.items.length">当前月份暂无规则</li>
              </ul>
            </article>
            <article>
              <h3>内部AMZ定时任务</h3>
              <p v-if="!performance.schedulerTasks.length">暂无任务定义。</p>
              <ul>
                <li v-for="task in performance.schedulerTasks" :key="task.task_code">
                  <span>{{ task.task_name }} / {{ task.cron_expression }}</span>
                  <b>{{ task.enabled ? '启用' : '停用' }}</b>
                </li>
              </ul>
              <h3>最近运行</h3>
              <ul>
                <li v-for="run in performance.schedulerRuns" :key="run.run_id">
                  <span>{{ run.stat_month || '默认月份' }} / {{ run.started_at || '—' }}</span>
                  <b>{{ run.status }}</b>
                </li>
                <li v-if="!performance.schedulerRuns.length">暂无运行记录</li>
              </ul>
            </article>
          </div>
        </section>
      </main>
    </div>

    <div v-if="showGenerationModal" class="modal-mask" @click.self="showGenerationModal = false">
      <section class="erp-modal">
        <header><h2>生成申报批次</h2><button @click="showGenerationModal = false">×</button></header>
        <p>已选择 {{ selectedCustomsNumbers.length }} 张报关单，出口与进货明细将使用相同申报信息。</p>
        <label><span>申报年月</span><input v-model.trim="generation.declaration_month" maxlength="6" inputmode="numeric" placeholder="例如：202601" /></label>
        <label><span>申报批次</span><input v-model.trim="generation.declaration_batch" maxlength="3" inputmode="numeric" placeholder="例如：001" /></label>
        <p v-if="generationError" class="alert-error">{{ generationError }}</p>
        <footer>
          <button class="secondary-button" :disabled="generationLoading" @click="showGenerationModal = false">取消</button>
          <button class="primary-button" :disabled="generationLoading || !generation.declaration_month || !generation.declaration_batch" @click="generateDetails">
            {{ generationLoading ? '正在生成…' : '生成并打包' }}
          </button>
        </footer>
      </section>
    </div>
  </div>
</template>
