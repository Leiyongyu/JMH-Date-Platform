<template>
  <div class="app-container">
    <el-card shadow="never" class="platform-card">
      <div class="platform-switch">
        <div>
          <div class="platform-heading">{{ platformTitle }}绩效排名</div>
          <div class="platform-hint">
            {{ platformHint }}
          </div>
        </div>
        <el-radio-group v-model="query.platform" @change="handlePlatformChange">
          <el-radio-button value="combined">综合</el-radio-button>
          <el-radio-button value="amazon">AMZ</el-radio-button>
          <el-radio-button value="ebay">eBay</el-radio-button>
        </el-radio-group>
      </div>
    </el-card>

    <el-card shadow="never" class="filter-card">
      <el-form ref="queryRef" :model="query" inline label-width="82px">
        <el-form-item label="统计月份" prop="statMonth">
          <el-select
            v-model="query.statMonth"
            placeholder="默认最新月份"
            clearable
            style="width: 260px"
            @change="handleQuery"
          >
            <el-option
              v-for="month in monthOptions"
              :key="month.stat_month"
              :label="monthLabel(month)"
              :value="month.stat_month"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="负责人" prop="principalName">
          <el-input v-model="query.principalName" clearable placeholder="Listing负责人" @keyup.enter="handleQuery" />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" icon="Search" @click="handleQuery">搜索</el-button>
          <el-button icon="Refresh" @click="resetQuery">重置</el-button>
          <el-button
            type="success"
            icon="Refresh"
            :loading="refreshing"
            v-hasPermi="['finance:performanceRanking:edit']"
            @click="handleRefresh"
          >
            重新匹配并汇总
          </el-button>
          <el-button
            type="primary"
            plain
            icon="Upload"
            :loading="profitImporting"
            v-hasPermi="['finance:performanceRanking:edit']"
            @click="openProfitImportDialog"
          >
            导入 eBay 月度利润表
          </el-button>
          <el-button
            type="warning"
            icon="Upload"
            v-hasPermi="['finance:performanceRanking:edit']"
            @click="openOwnerImportDialog('AMZ')"
          >
            导入 AMZ 负责人配置
          </el-button>
          <el-button
            type="warning"
            plain
            icon="Upload"
            v-hasPermi="['finance:performanceRanking:edit']"
            @click="openOwnerImportDialog('EBAY')"
          >
            导入 eBay 负责人配置
          </el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <el-card shadow="never" class="summary-card">
      <template #header>
        <div class="card-header">
          <div>
            <span class="title">月度{{ platformTitle }}绩效排名</span>
            <span class="subtitle">{{ rankingSubtitle }}</span>
          </div>
          <el-tag type="success">{{ displayedMonth || '最新月份' }}</el-tag>
        </div>
      </template>

      <el-alert
        v-if="lastRefreshStats"
        class="result-alert"
        :type="lastRefreshStats.unmatchedRows > 0 ? 'warning' : 'success'"
        :closable="false"
        show-icon
      >
        <template #title>
          {{ lastRefreshStats.statMonth }} 共处理 AMZ {{ lastRefreshStats.amzProfitRows || 0 }} 条、
          eBay {{ lastRefreshStats.ebayProfitRows || 0 }} 条利润数据，未分配
          {{ lastRefreshStats.unmatchedRows || 0 }} 条，生成 {{ lastRefreshStats.rows || 0 }} 条{{ platformTitle }}负责人汇总
        </template>
      </el-alert>
    </el-card>

    <div v-loading="loading" class="ranking-grid">
      <el-card shadow="never" class="ranking-card gross-profit-card">
        <template #header>
          <div class="ranking-header">
            <div>
              <div class="ranking-title">毛利润排名</div>
              <div class="ranking-description">{{ platformTitle }}各负责人毛利润</div>
            </div>
            <el-tag v-if="grossProfitRanking.length" type="success" effect="light">
              {{ grossProfitRanking[0].principalNames }}
            </el-tag>
          </div>
        </template>
        <div ref="grossProfitChartRef" class="ranking-chart"></div>
      </el-card>

      <el-card shadow="never" class="ranking-card net-sales-card">
        <template #header>
          <div class="ranking-header">
            <div>
              <div class="ranking-title">净销售额排名</div>
              <div class="ranking-description">净销售额 = 销售额 - 退款金额</div>
            </div>
            <el-tag v-if="netSalesRanking.length" type="primary" effect="light">
              {{ netSalesRanking[0].principalNames }}
            </el-tag>
          </div>
        </template>
        <div ref="netSalesChartRef" class="ranking-chart"></div>
      </el-card>
    </div>

    <el-dialog
      v-model="profitDialogVisible"
      title="导入 eBay 月度利润表"
      width="560px"
      append-to-body
      :close-on-click-modal="false"
      @closed="resetProfitImportDialog"
    >
      <el-form :model="profitImportForm" label-width="92px">
        <el-form-item label="利润表" required>
          <el-upload
            ref="profitUploadRef"
            class="owner-upload"
            drag
            accept=".xlsx,.xls"
            :auto-upload="false"
            :limit="1"
            :on-change="handleProfitFileChange"
            :on-remove="handleProfitFileRemove"
          >
            <el-icon class="el-icon--upload"><UploadFilled /></el-icon>
            <div class="el-upload__text">拖入文件，或<em>点击选择</em></div>
            <template #tip>
              <div class="el-upload__tip">
                文件名必须包含年月，例如 ebay-202606-利润表.xlsx；读取 sheet1 的
                SKU、利润、商品销售额、应收运费和退款金额；销售额 = 商品销售额 + 应收运费，
                净销售额 = 销售额 - 退款金额。同月再次导入会整月覆盖。
              </div>
            </template>
          </el-upload>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="profitDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="profitImporting" @click="submitEbayProfit">
          导入并重新汇总
        </el-button>
      </template>
    </el-dialog>

    <el-dialog
      v-model="ownerImportDialogVisible"
      :title="`导入${ownerImportPlatform === 'AMZ' ? 'AMZ' : 'eBay'}月度负责人配置`"
      width="560px"
      append-to-body
      :close-on-click-modal="false"
      @closed="resetOwnerImportDialog"
    >
      <el-form :model="importForm" label-width="92px">
        <el-form-item label="Excel文件" required>
          <el-upload
            ref="uploadRef"
            class="owner-upload"
            drag
            accept=".xlsx,.xls"
            :auto-upload="false"
            :limit="1"
            :on-change="handleFileChange"
            :on-remove="handleFileRemove"
          >
            <el-icon class="el-icon--upload"><UploadFilled /></el-icon>
            <div class="el-upload__text">拖入文件，或<em>点击选择</em></div>
            <template #tip>
              <div class="el-upload__tip">
                {{ ownerImportTip }}
              </div>
            </template>
          </el-upload>
        </el-form-item>
        <el-form-item label="后续操作">
          <el-checkbox v-model="importForm.rebuildAfterImport">
            导入成功后立即重新匹配并汇总当前查询月份（未选择时汇总最新利润月份）
          </el-checkbox>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="ownerImportDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="importing" @click="submitOwnerRules">
          开始增量导入
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup name="PerformanceRanking">
import { computed, getCurrentInstance, nextTick, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import * as echarts from 'echarts'
import {
  getPerformanceMonths,
  importEbayPerformanceOwnerRules,
  importEbayPerformanceProfit,
  importPerformanceOwnerRules,
  listPerformanceRanking,
  refreshPerformanceRanking
} from '@/api/finance/performanceRanking'

const { proxy } = getCurrentInstance()
const loading = ref(false)
const rows = ref([])
const monthOptions = ref([])
const actualMonth = ref('')
const refreshing = ref(false)
const importing = ref(false)
const profitImporting = ref(false)
const ownerImportDialogVisible = ref(false)
const profitDialogVisible = ref(false)
const uploadRef = ref()
const profitUploadRef = ref()
const lastRefreshStats = ref()
const ownerImportPlatform = ref('AMZ')
const queryRef = ref()
const grossProfitChartRef = ref()
const netSalesChartRef = ref()
let grossProfitChart
let netSalesChart
const query = reactive({
  pageNum: 1,
  pageSize: 1000,
  platform: 'combined',
  statMonth: undefined,
  principalName: undefined
})
const importForm = reactive({
  file: undefined,
  rebuildAfterImport: true
})
const profitImportForm = reactive({
  file: undefined
})

const displayedMonth = computed(() => actualMonth.value || query.statMonth || '')
const platformTitle = computed(() => ({
  combined: '综合',
  amazon: 'AMZ',
  ebay: 'eBay'
}[query.platform] || '综合'))
const platformHint = computed(() => query.platform === 'combined'
  ? 'AMZ 与 eBay 保持各自负责人匹配规则，最终按月份和负责人合并排名'
  : `查看 Python 绩效服务生成的${platformTitle.value}负责人月度排名`)
const rankingSubtitle = computed(() => query.platform === 'combined'
  ? '同一负责人在 AMZ 与 eBay 的金额合并，金额统一为 CNY'
  : `${platformTitle.value}负责人排名，金额统一为 CNY`)
const ownerImportTip = computed(() => ownerImportPlatform.value === 'AMZ'
  ? '自动读取 EU-品牌、EU-OTH、US1、US2 四个sheet中的全部“YYYYMM负责人”列；相同月份、组别和匹配键覆盖，其余数据保留。'
  : '只读取 Sheet1：第一列为品牌，后续为“YYYYMM负责人”列；相同月份和品牌覆盖，其余数据保留。')
const grossProfitRanking = computed(() => sortRanking('grossProfit'))
const netSalesRanking = computed(() => sortRanking('netSalesAmount'))

function formatMoney(value) {
  return Number(value || 0).toLocaleString('zh-CN', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2
  })
}

function sortRanking(field) {
  return [...rows.value].sort((left, right) => Number(right[field] || 0) - Number(left[field] || 0))
}

function buildChartOption(ranking, field, color, seriesName) {
  const hasData = ranking.length > 0
  const showZoom = ranking.length > 10
  const zoomEnd = Math.min(100, (10 / Math.max(ranking.length, 1)) * 100)
  return {
    color: [color],
    animationDuration: 700,
    grid: {
      left: 24,
      right: showZoom ? 92 : 72,
      top: 28,
      bottom: 54,
      containLabel: true
    },
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'shadow' },
      formatter(params) {
        const item = params?.[0]
        if (!item) return ''
        const owner = ranking[item.dataIndex]?.principalNames || '未分配'
        return `${item.dataIndex + 1}. ${owner}<br/>${seriesName}：¥${formatMoney(item.value)}`
      }
    },
    xAxis: {
      type: 'value',
      name: '金额（CNY）',
      nameLocation: 'middle',
      nameGap: 38,
      nameTextStyle: { color: '#64748b' },
      axisLabel: {
        color: '#64748b',
        formatter(value) {
          const absolute = Math.abs(value)
          if (absolute >= 10000) return `${(value / 10000).toFixed(1)}万`
          return Number(value).toLocaleString('zh-CN')
        }
      },
      splitLine: { lineStyle: { color: '#eef2f7' } }
    },
    yAxis: {
      type: 'category',
      inverse: true,
      data: ranking.map(item => item.principalNames || '未分配'),
      axisTick: { show: false },
      axisLabel: {
        color: '#475569',
        fontSize: 13,
        margin: 12
      },
      axisLine: { lineStyle: { color: '#cbd5e1' } }
    },
    dataZoom: showZoom
      ? [
          {
            type: 'inside',
            yAxisIndex: 0,
            start: 0,
            end: zoomEnd
          },
          {
            type: 'slider',
            yAxisIndex: 0,
            orient: 'vertical',
            width: 16,
            right: 10,
            top: 28,
            bottom: 54,
            start: 0,
            end: zoomEnd,
            brushSelect: false
          }
        ]
      : [],
    series: [
      {
        name: seriesName,
        type: 'bar',
        barMaxWidth: 34,
        data: ranking.map(item => Number(item[field] || 0)),
        itemStyle: {
          borderRadius: [0, 6, 6, 0],
          color: new echarts.graphic.LinearGradient(0, 0, 1, 0, [
            { offset: 0, color },
            { offset: 1, color: `${color}99` }
          ])
        },
        label: {
          show: true,
          position: 'right',
          color: '#334155',
          fontSize: 11,
          formatter: params => formatMoney(params.value)
        }
      }
    ],
    graphic: hasData
      ? []
      : [
          {
            type: 'text',
            left: 'center',
            top: 'middle',
            style: { text: '暂无排名数据', fill: '#94a3b8', fontSize: 14 }
          }
        ]
  }
}

async function renderCharts() {
  await nextTick()
  if (grossProfitChartRef.value) {
    grossProfitChart ||= echarts.init(grossProfitChartRef.value)
    grossProfitChart.setOption(
      buildChartOption(
        grossProfitRanking.value,
        'grossProfit',
        '#16a34a',
        '毛利润'
      ),
      true
    )
  }
  if (netSalesChartRef.value) {
    netSalesChart ||= echarts.init(netSalesChartRef.value)
    netSalesChart.setOption(
      buildChartOption(netSalesRanking.value, 'netSalesAmount', '#2563eb', '净销售额'),
      true
    )
  }
}

async function loadData() {
  loading.value = true
  try {
    const response = await listPerformanceRanking(query)
    rows.value = response.rows || []
    actualMonth.value = response.statMonth || query.statMonth || ''
    await renderCharts()
  } finally {
    loading.value = false
  }
}

async function loadMonths(selectLatest = false) {
  const response = await getPerformanceMonths(60)
  monthOptions.value = response.data || []
  if ((selectLatest || !query.statMonth) && monthOptions.value.length) {
    query.statMonth = monthOptions.value[0].stat_month
  }
}

function monthLabel(month) {
  const ready = [
    `AMZ${month.amazon_ready ? '✓' : '—'}`,
    `eBay${month.ebay_ready ? '✓' : '—'}`,
    `综合${month.combined_ready ? '✓' : '—'}`
  ].join(' / ')
  return `${month.stat_month}（${ready}）`
}

function handleQuery() {
  query.pageNum = 1
  loadData()
}

function handlePlatformChange() {
  query.pageNum = 1
  loadData()
}

function resetQuery() {
  queryRef.value?.resetFields()
  query.pageNum = 1
  if (monthOptions.value.length) query.statMonth = monthOptions.value[0].stat_month
  loadData()
}

async function handleRefresh() {
  if (!query.statMonth) {
    proxy.$modal.msgError('请选择需要刷新的统计月份')
    return
  }
  refreshing.value = true
  try {
    const response = await refreshPerformanceRanking(query.statMonth, query.platform)
    const result = response.data || {}
    lastRefreshStats.value = normalizeRefresh(result)
    if ((lastRefreshStats.value.unmatchedRows || 0) > 0) {
      proxy.$modal.msgWarning(
        `汇总完成，但有${lastRefreshStats.value.unmatchedRows}条利润数据归入未分配，请检查当月负责人配置`
      )
    } else {
      proxy.$modal.msgSuccess(
        `${platformTitle.value}负责人匹配完成，共生成${lastRefreshStats.value.rows || 0}条汇总数据`
      )
    }
    await loadMonths()
    query.pageNum = 1
    await loadData()
  } finally {
    refreshing.value = false
  }
}

function normalizeRefresh(result = {}) {
  const resultPlatform = result.platform || query.platform
  const rankingRows = resultPlatform === 'amazon'
    ? result.amz_ranking_rows
    : resultPlatform === 'ebay'
      ? result.ebay_ranking_rows
      : result.combined_ranking_rows
  return {
    statMonth: result.stat_month || result.statMonth || query.statMonth,
    rows: rankingRows ?? result.rows ?? 0,
    sourceRows: result.source_rows ?? result.sourceRows ?? 0,
    matchedRows: result.matched_rows ?? result.matchedRows ?? 0,
    unmatchedRows: result.unmatched_rows ?? result.unmatchedRows ?? 0,
    amzProfitRows: result.amz_profit_rows ?? result.amzProfitRows ?? 0,
    ebayProfitRows: result.ebay_profit_rows ?? result.ebayProfitRows ?? 0,
    partial: result.partial || false
  }
}

function openOwnerImportDialog(platform) {
  ownerImportPlatform.value = platform
  importForm.file = undefined
  importForm.rebuildAfterImport = true
  ownerImportDialogVisible.value = true
}

function handleFileChange(uploadFile) {
  importForm.file = uploadFile.raw
}

function handleFileRemove() {
  importForm.file = undefined
}

function resetOwnerImportDialog() {
  uploadRef.value?.clearFiles()
  importForm.file = undefined
}

async function submitOwnerRules() {
  if (!importForm.file) {
    proxy.$modal.msgError('请选择负责人划分Excel文件')
    return
  }

  importing.value = true
  try {
    const importApi = ownerImportPlatform.value === 'AMZ'
      ? importPerformanceOwnerRules
      : importEbayPerformanceOwnerRules
    const response = await importApi(
      importForm.file,
      importForm.rebuildAfterImport,
      query.statMonth
    )
    const result = response.data || {}
    const sourceDescription = ownerImportPlatform.value === 'AMZ'
      ? 'AMZ负责人工作簿'
      : `Sheet1`
    proxy.$modal.msgSuccess(`负责人配置导入完成：${sourceDescription}、${result.month_count || 0}个月份，共写入${result.imported_rows || 0}条规则`)
    query.pageNum = 1
    const rebuildAfterImport = importForm.rebuildAfterImport
    ownerImportDialogVisible.value = false
    if (rebuildAfterImport && result.refreshes?.length) {
      lastRefreshStats.value = normalizeRefresh(result.refreshes[0])
    }
    await loadMonths()
    await loadData()
  } finally {
    importing.value = false
  }
}

function openProfitImportDialog() {
  profitImportForm.file = undefined
  profitDialogVisible.value = true
}

function handleProfitFileChange(uploadFile) {
  profitImportForm.file = uploadFile.raw
}

function handleProfitFileRemove() {
  profitImportForm.file = undefined
}

function resetProfitImportDialog() {
  profitUploadRef.value?.clearFiles()
  profitImportForm.file = undefined
}

async function submitEbayProfit() {
  if (!profitImportForm.file) {
    proxy.$modal.msgError('请选择 eBay 月度利润表Excel文件')
    return
  }

  profitImporting.value = true
  try {
    const response = await importEbayPerformanceProfit(profitImportForm.file, true)
    const result = response.data || {}
    query.statMonth = result.stat_month
    query.pageNum = 1
    profitDialogVisible.value = false
    proxy.$modal.msgSuccess(
      `${result.stat_month || ''} eBay利润表导入完成，共${result.inserted_rows || 0}条`
    )
    if (result.refresh) lastRefreshStats.value = normalizeRefresh(result.refresh)
    await loadMonths()
    await loadData()
  } finally {
    profitImporting.value = false
  }
}

function resizeCharts() {
  grossProfitChart?.resize()
  netSalesChart?.resize()
}

onMounted(async () => {
  window.addEventListener('resize', resizeCharts)
  await loadMonths(true)
  await loadData()
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', resizeCharts)
  grossProfitChart?.dispose()
  netSalesChart?.dispose()
})
</script>

<style scoped>
.platform-card { margin-bottom: 16px; border-radius: 10px; }
.platform-switch {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 18px;
}
.platform-heading { color: #1e293b; font-size: 18px; font-weight: 650; }
.platform-hint { margin-top: 5px; color: #64748b; font-size: 12px; }
.filter-card { margin-bottom: 16px; }
.summary-card { margin-bottom: 16px; }
.card-header { display: flex; align-items: center; justify-content: space-between; }
.title { font-size: 16px; font-weight: 600; }
.subtitle { margin-left: 12px; color: var(--el-text-color-secondary); font-size: 13px; }
.result-alert { margin-bottom: 16px; }
.ranking-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
}
.ranking-card {
  min-width: 0;
  border-radius: 10px;
}
.ranking-card :deep(.el-card__body) { padding: 12px 16px 16px; }
.gross-profit-card { border-top: 3px solid #16a34a; }
.net-sales-card { border-top: 3px solid #2563eb; }
.ranking-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}
.ranking-title { color: #1e293b; font-size: 17px; font-weight: 650; }
.ranking-description { margin-top: 5px; color: #64748b; font-size: 12px; }
.ranking-chart { width: 100%; height: 460px; }
.owner-upload { width: 100%; }
.owner-upload :deep(.el-upload),
.owner-upload :deep(.el-upload-dragger) { width: 100%; }

@media (max-width: 1200px) {
  .ranking-grid { grid-template-columns: 1fr; }
}

@media (max-width: 768px) {
  .platform-switch,
  .card-header,
  .ranking-header { align-items: flex-start; flex-direction: column; }
  .subtitle { display: block; margin: 5px 0 0; }
  .ranking-chart { height: 400px; }
}
</style>
