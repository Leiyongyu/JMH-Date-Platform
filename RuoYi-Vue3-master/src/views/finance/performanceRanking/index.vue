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
          <el-button type="primary" @click="handleQuery"><app-icon name="search" :size="15" class="btn-icon" />搜索</el-button>
          <el-button @click="resetQuery"><app-icon name="undo" :size="15" class="btn-icon" />重置</el-button>
          <el-button
            type="success"
            :loading="refreshing"
            v-hasPermi="['finance:performanceRanking:edit']"
            @click="handleRefresh"
          >
            <app-icon name="refresh" :size="15" class="btn-icon" />重新匹配并汇总
          </el-button>
          <el-dropdown
            trigger="click"
            popper-class="performance-data-menu"
            :disabled="dataOperationLoading"
            @command="handleDataCommand"
          >
            <el-button
              class="data-action-trigger"
              type="primary"
              plain
              :loading="dataOperationLoading"
            >
              <app-icon name="folder" :size="15" />
              <span>数据导入/导出</span>
              <app-icon name="chevronDown" :size="13" class="el-icon--right" />
            </el-button>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item
                  command="exportAmzSource"
                  v-hasPermi="['finance:performanceRanking:list']"
                >
                  <app-icon name="download" :size="15" class="data-menu-icon export-icon" />
                  <div class="data-menu-copy">
                    <span>导出 AMZ 源数据</span>
                    <small>导出当前月份的绩效明细</small>
                  </div>
                </el-dropdown-item>
                <el-dropdown-item
                  command="importEbayProfit"
                  divided
                  v-hasPermi="['finance:performanceRanking:edit']"
                  class="ebay-profit-import-item"
                >
                  <el-popover
                    trigger="hover"
                    placement="right-start"
                    :width="720"
                    :show-after="250"
                    popper-class="performance-ebay-profit-guide"
                  >
                    <template #reference>
                      <div class="ebay-profit-import-trigger">
                        <app-icon name="upload" :size="15" class="data-menu-icon profit-icon" />
                        <div class="data-menu-copy">
                          <span>导入 eBay 月度利润表</span>
                          <small>覆盖所导入月份的利润数据</small>
                        </div>
                      </div>
                    </template>
                    <div class="ebay-profit-guide">
                      <div class="ebay-profit-guide__title">eBay 月度利润表导出格式</div>
                      <div class="ebay-profit-guide__hint">
                        请按下图所示格式导出月度利润文件，再点击“导入 eBay 月度利润表”上传。
                      </div>
                      <el-image
                        class="ebay-profit-guide__image"
                        :src="ebayMonthlyProfitGuide"
                        :preview-src-list="[ebayMonthlyProfitGuide]"
                        fit="contain"
                        preview-teleported
                      />
                    </div>
                  </el-popover>
                </el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
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

      <div class="unassigned-hint">
        <el-text size="small" type="info">
          排名已排除「未分配」，只比较真实负责人；未匹配的利润明细与原因见右侧。
        </el-text>
        <el-button type="warning" plain size="small" @click="openUnmatched">
          未匹配排查
        </el-button>
      </div>
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
              <div class="ranking-description">净销售额 = 销售额 - 促销折扣 - 退款金额（均按绝对值扣减）</div>
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
      v-model="unmatchedVisible"
      title="未匹配负责人排查"
      width="1040px"
      append-to-body
    >
      <el-alert type="info" :closable="false" show-icon class="unmatched-alert">
        <template #title>
          归属规则来自「负责人划分」Excel，<strong>按月独立生效，不会沿用上个月</strong>。
          Amazon 店铺的匹配键是<strong>去掉 US1/US2 前缀后的店铺主体名</strong>，
          Excel 的「店铺名」列必须只写主体（例如店铺 <code>US1-嘉茂鸿</code> 要写 <code>嘉茂鸿</code>）。
          EU 的归属只按 SKU 品牌码／中间码，<strong>在「EU-店铺」页配负责人不生效</strong>。
        </template>
      </el-alert>

      <div v-if="unmatchedTotals" class="unmatched-summary">
        <el-tag type="warning" effect="plain">
          共 {{ unmatchedTotals.keys || 0 }} 个匹配键 / {{ unmatchedTotals.sourceRows || 0 }} 条利润行
        </el-tag>
        <el-tag
          v-for="bucket in unmatchedTotals.byReason || []"
          :key="bucket.reason"
          :type="reasonTagType(bucket.reason)"
          effect="plain"
        >
          {{ bucket.reasonText }}：{{ bucket.keys }} 个
        </el-tag>
      </div>

      <el-table
        v-loading="unmatchedLoading"
        :data="unmatchedItems"
        size="small"
        border
        max-height="460"
        empty-text="该月没有未匹配的利润数据"
      >
        <el-table-column prop="platform" label="平台" width="76">
          <template #default="scope">
            {{ scope.row.platform === 'amazon' ? 'Amazon' : 'eBay' }}
          </template>
        </el-table-column>
        <el-table-column label="匹配维度" min-width="190" show-overflow-tooltip>
          <template #default="scope">{{ scope.row.dimensionText }}</template>
        </el-table-column>
        <el-table-column label="匹配键" min-width="130" show-overflow-tooltip>
          <template #default="scope">
            <code v-if="scope.row.matchKey">{{ scope.row.matchKey }}</code>
            <el-text v-else size="small" type="danger">（空）</el-text>
          </template>
        </el-table-column>
        <el-table-column label="原因" min-width="270">
          <template #default="scope">
            <el-tag :type="reasonTagType(scope.row.reason)" effect="light" size="small">
              {{ scope.row.reasonText }}
            </el-tag>
            <el-text
              v-if="!scope.row.countsInRanking"
              size="small"
              type="info"
              class="not-counted"
            >
              金额未计入排名
            </el-text>
          </template>
        </el-table-column>
        <el-table-column prop="sourceRows" label="利润行数" width="92" align="right" />
        <el-table-column label="毛利润" width="124" align="right">
          <template #default="scope">{{ scope.row.grossProfit }}</template>
        </el-table-column>
        <el-table-column label="示例" min-width="190" show-overflow-tooltip>
          <template #default="scope">
            <div v-if="scope.row.sampleStore">店铺：{{ scope.row.sampleStore }}</div>
            <div v-if="scope.row.sampleSku">SKU：{{ scope.row.sampleSku }}</div>
          </template>
        </el-table-column>
      </el-table>

      <template #footer>
        <el-button @click="unmatchedVisible = false">关闭</el-button>
      </template>
    </el-dialog>

    <el-dialog
      v-model="profitDialogVisible"
      title="导入 eBay 月度利润表"
      width="560px"
      append-to-body
      :close-on-click-modal="false"
      @closed="resetProfitImportDialog"
    >
      <el-form :model="profitImportForm" label-width="92px">
        <el-form-item label="统计月份" required>
          <el-date-picker
            v-model="profitImportForm.statMonth"
            type="month"
            value-format="YYYY-MM"
            format="YYYY年MM月"
            placeholder="选择利润归属月份"
            style="width: 100%"
          />
          <div class="el-upload__tip">
            统计月份以这里选择的月份为准，不再根据文件下载日期或文件名判断。
          </div>
        </el-form-item>
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
            <app-icon name="upload" :size="40" class="upload-hero" />
            <div class="el-upload__text">拖入文件，或<em>点击选择</em></div>
            <template #tip>
              <div class="el-upload__tip">
                读取 sheet1 的
                SKU、利润、商品销售额、应收运费和退款金额；销售额 = 商品销售额 + 应收运费，
                净销售额 = 销售额 - 退款金额；AMZ 开头及空 SKU 汇总行会自动排除。同月再次导入会整月覆盖。
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

  </div>
</template>

<script setup name="PerformanceRanking">
import { computed, getCurrentInstance, nextTick, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import * as echarts from 'echarts'
import ebayMonthlyProfitGuide from '@/assets/images/performance-ranking-ebay-monthly-profit-guide.png'
import {
  exportAmzPerformanceSource,
  getPerformanceMonths,
  importEbayPerformanceProfit,
  listPerformanceRanking,
  listPerformanceUnmatched,
  refreshPerformanceRanking
} from '@/api/finance/performanceRanking'

const { proxy } = getCurrentInstance()
const loading = ref(false)
const rows = ref([])
const monthOptions = ref([])
const actualMonth = ref('')
const refreshing = ref(false)
const sourceExporting = ref(false)
const profitImporting = ref(false)
const profitDialogVisible = ref(false)
const profitUploadRef = ref()
const lastRefreshStats = ref()
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
  principalName: undefined,
  // 排名是人与人的比较，未分配不参与；明细通过「未匹配排查」查看。
  excludeUnassigned: true
})
const unmatchedVisible = ref(false)
const unmatchedLoading = ref(false)
const unmatchedItems = ref([])
const unmatchedTotals = ref()
const profitImportForm = reactive({
  file: undefined,
  statMonth: undefined
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
const grossProfitRanking = computed(() => sortRanking('grossProfit'))
const netSalesRanking = computed(() => sortRanking('netSalesAmount'))
const dataOperationLoading = computed(() => (
  sourceExporting.value || profitImporting.value
))

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
      nameTextStyle: { color: '#8a99b0' },
      axisLabel: {
        color: '#8a99b0',
        formatter(value) {
          const absolute = Math.abs(value)
          if (absolute >= 10000) return `${(value / 10000).toFixed(1)}万`
          return Number(value).toLocaleString('zh-CN')
        }
      },
      splitLine: { lineStyle: { color: '#e9eef6' } }
    },
    yAxis: {
      type: 'category',
      inverse: true,
      data: ranking.map(item => item.principalNames || '未分配'),
      axisTick: { show: false },
      axisLabel: {
        color: '#24334a',
        fontSize: 13,
        margin: 12
      },
      axisLine: { lineStyle: { color: '#e3e9f2' } }
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
          color: '#24334a',
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
            style: { text: '暂无排名数据', fill: '#8a99b0', fontSize: 14 }
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
        '#12a150',
        '毛利润'
      ),
      true
    )
  }
  if (netSalesChartRef.value) {
    netSalesChart ||= echarts.init(netSalesChartRef.value)
    netSalesChart.setOption(
      buildChartOption(netSalesRanking.value, 'netSalesAmount', '#1257d6', '净销售额'),
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

async function openUnmatched() {
  unmatchedVisible.value = true
  unmatchedLoading.value = true
  try {
    const response = await listPerformanceUnmatched({
      platform: query.platform,
      statMonth: query.statMonth
    })
    unmatchedItems.value = response.data?.items || []
    unmatchedTotals.value = response.data?.totals
  } finally {
    unmatchedLoading.value = false
  }
}

const reasonTagType = reason => ({
  RULE_MISSING: 'danger',
  OWNER_BLANK: 'warning',
  OWNER_WHITESPACE: 'danger',
  KEY_EMPTY: 'warning',
  SHOP_UNKNOWN: 'info'
}[reason] || 'info')

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

async function handleAmzSourceExport() {
  if (!query.statMonth) {
    proxy.$modal.msgError('请选择需要导出的统计月份')
    return
  }
  sourceExporting.value = true
  try {
    const data = await exportAmzPerformanceSource(query.statMonth)
    const blob = data instanceof Blob
      ? data
      : new Blob([data], {
          type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = `amz_performance_source_${query.statMonth}.xlsx`
    document.body.appendChild(link)
    link.click()
    link.remove()
    URL.revokeObjectURL(url)
    proxy.$modal.msgSuccess(`${query.statMonth} AMZ源数据导出成功`)
  } finally {
    sourceExporting.value = false
  }
}

function handleDataCommand(command) {
  const actions = {
    exportAmzSource: handleAmzSourceExport,
    importEbayProfit: openProfitImportDialog
  }
  actions[command]?.()
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

function openProfitImportDialog() {
  profitImportForm.file = undefined
  profitImportForm.statMonth = query.statMonth || previousNaturalMonth()
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
  profitImportForm.statMonth = undefined
}

function previousNaturalMonth() {
  const date = new Date()
  date.setDate(1)
  date.setMonth(date.getMonth() - 1)
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}`
}

async function submitEbayProfit() {
  if (!profitImportForm.statMonth) {
    proxy.$modal.msgError('请选择 eBay 利润表归属的统计月份')
    return
  }
  if (!profitImportForm.file) {
    proxy.$modal.msgError('请选择 eBay 月度利润表Excel文件')
    return
  }

  profitImporting.value = true
  try {
    const response = await importEbayPerformanceProfit(
      profitImportForm.file,
      profitImportForm.statMonth,
      true
    )
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
.platform-heading { color: #0b1526; font-size: 18px; font-weight: 650; }
.platform-hint { margin-top: 5px; color: #8a99b0; font-size: 12px; }
.filter-card { margin-bottom: 16px; }
.filter-card :deep(.el-form-item:last-child .el-form-item__content) {
  display: flex;
  align-items: center;
  gap: 8px;
}
.filter-card :deep(.el-form-item:last-child .el-button + .el-button) { margin-left: 0; }
.data-action-trigger {
  min-width: 154px;
  border-color: #c9dcfb;
  background: linear-gradient(135deg, #f4f8ff 0%, #fbfdff 100%);
  box-shadow: 0 2px 8px rgb(18 87 214 / 8%);
}
.data-action-trigger:hover,
.data-action-trigger:focus {
  border-color: #a9c6f4;
  background: #e7efff;
  box-shadow: 0 4px 12px rgb(18 87 214 / 14%);
}
.data-action-trigger span { margin-left: 7px; }
:global(.performance-data-menu .el-dropdown-menu) { padding: 7px; }
:global(.performance-data-menu .el-dropdown-menu__item) {
  min-width: 252px;
  min-height: 52px;
  padding: 7px 11px;
  border-radius: 7px;
  line-height: 1.25;
}
:global(.performance-data-menu .el-dropdown-menu__item--divided) { margin-top: 7px; }
:global(.performance-data-menu .data-menu-icon) {
  width: 30px;
  height: 30px;
  margin-right: 10px;
  border-radius: 7px;
  font-size: 16px;
}
:global(.performance-data-menu .export-icon) { color: #12a150; background: #e7f6ec; }
:global(.performance-data-menu .profit-icon) { color: #1257d6; background: #e7efff; }
:global(.performance-data-menu .data-menu-copy) {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
:global(.performance-data-menu .data-menu-copy span) { color: #0b1526; font-weight: 600; }
:global(.performance-data-menu .data-menu-copy small) { color: #8a99b0; font-size: 11px; }
:global(.performance-data-menu .ebay-profit-import-item) { padding: 0; }
:global(.performance-data-menu .ebay-profit-import-trigger) {
  display: flex;
  align-items: center;
  width: 100%;
  min-height: 52px;
  padding: 7px 11px;
  box-sizing: border-box;
}
:global(.performance-ebay-profit-guide) { max-width: calc(100vw - 32px); }
:global(.performance-ebay-profit-guide .ebay-profit-guide__title) {
  color: #1e293b;
  font-size: 16px;
  font-weight: 650;
}
:global(.performance-ebay-profit-guide .ebay-profit-guide__hint) {
  margin: 7px 0 12px;
  color: #64748b;
  font-size: 13px;
  line-height: 1.6;
}
:global(.performance-ebay-profit-guide .ebay-profit-guide__image) {
  display: block;
  width: 100%;
  max-height: 70vh;
  overflow: hidden;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  background: #f8fafc;
  cursor: zoom-in;
}
:global(.performance-ebay-profit-guide .ebay-profit-guide__image img) {
  max-height: 70vh;
}
.summary-card { margin-bottom: 16px; }
.unassigned-hint {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-top: 10px;
}
.unmatched-alert { margin-bottom: 12px; }
.unmatched-alert code {
  padding: 0 4px;
  border-radius: 3px;
  background: var(--el-fill-color-light);
}
.unmatched-summary {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 12px;
}
.not-counted { margin-left: 6px; }
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
.gross-profit-card { border-top: 3px solid #12a150; }
.net-sales-card { border-top: 3px solid #1257d6; }
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
.upload-hero { color: var(--jb-brand-500, #2c74f0); }
</style>
