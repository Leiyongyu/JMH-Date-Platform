<template>
  <div class="app-container">
    <el-card shadow="never" class="filter-card">
      <el-form ref="queryRef" :model="query" inline label-width="82px">
        <el-form-item label="统计月份" prop="statMonth">
          <el-date-picker
            v-model="query.statMonth"
            type="month"
            value-format="YYYY-MM"
            placeholder="默认最新月份"
            clearable
          />
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
            type="warning"
            icon="Upload"
            v-hasPermi="['finance:performanceRanking:edit']"
            @click="openImportDialog"
          >
            导入负责人配置
          </el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <el-card shadow="never" class="summary-card">
      <template #header>
        <div class="card-header">
          <div>
            <span class="title">Amazon 月度绩效排名</span>
            <span class="subtitle">按负责人降序排名，金额统一为 CNY</span>
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
          {{ lastRefreshStats.statMonth }} 共匹配 {{ lastRefreshStats.matchedRows || 0 }} 条利润数据，
          未分配 {{ lastRefreshStats.unmatchedRows || 0 }} 条，生成 {{ lastRefreshStats.rows || 0 }} 条负责人汇总
        </template>
      </el-alert>
    </el-card>

    <div v-loading="loading" class="ranking-grid">
      <el-card shadow="never" class="ranking-card gross-profit-card">
        <template #header>
          <div class="ranking-header">
            <div>
              <div class="ranking-title">毛利润排名</div>
              <div class="ranking-description">各负责人毛利润对比</div>
            </div>
            <el-tag v-if="grossProfitRanking.length" type="success" effect="light">
              第1名：{{ grossProfitRanking[0].principalNames }}
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
              第1名：{{ netSalesRanking[0].principalNames }}
            </el-tag>
          </div>
        </template>
        <div ref="netSalesChartRef" class="ranking-chart"></div>
      </el-card>
    </div>

    <el-dialog
      v-model="importDialogVisible"
      title="导入月度负责人配置"
      width="560px"
      append-to-body
      :close-on-click-modal="false"
      @closed="resetImportDialog"
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
                自动读取 EU-品牌、EU-OTH、US1、US2 四个sheet中的全部“YYYYMM负责人”列；
                相同月份、组别和匹配键覆盖，其余数据保留。
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
        <el-button @click="importDialogVisible = false">取消</el-button>
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
  importPerformanceOwnerRules,
  listPerformanceRanking,
  refreshPerformanceRanking
} from '@/api/finance/performanceRanking'

const { proxy } = getCurrentInstance()
const loading = ref(false)
const rows = ref([])
const refreshing = ref(false)
const importing = ref(false)
const importDialogVisible = ref(false)
const uploadRef = ref()
const lastRefreshStats = ref()
const queryRef = ref()
const grossProfitChartRef = ref()
const netSalesChartRef = ref()
let grossProfitChart
let netSalesChart
const query = reactive({
  pageNum: 1,
  pageSize: 1000,
  statMonth: undefined,
  principalName: undefined
})
const importForm = reactive({
  file: undefined,
  rebuildAfterImport: true
})

const displayedMonth = computed(() => query.statMonth || rows.value[0]?.statMonth || '')
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
  return {
    color: [color],
    animationDuration: 700,
    grid: {
      left: 70,
      right: 28,
      top: 52,
      bottom: showZoom ? 104 : 78,
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
      type: 'category',
      data: ranking.map((item, index) => `第${index + 1}名\n${item.principalNames || '未分配'}`),
      axisTick: { alignWithLabel: true },
      axisLabel: {
        interval: 0,
        rotate: ranking.length > 6 ? 32 : 0,
        color: '#475569',
        fontSize: 12,
        lineHeight: 18
      },
      axisLine: { lineStyle: { color: '#cbd5e1' } }
    },
    yAxis: {
      type: 'value',
      name: '金额（CNY）',
      nameTextStyle: { color: '#64748b', padding: [0, 0, 8, 0] },
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
    dataZoom: showZoom
      ? [
          { type: 'inside', start: 0, end: Math.min(100, (10 / ranking.length) * 100) },
          {
            type: 'slider',
            height: 18,
            bottom: 8,
            start: 0,
            end: Math.min(100, (10 / ranking.length) * 100),
            brushSelect: false
          }
        ]
      : [],
    series: [
      {
        name: seriesName,
        type: 'bar',
        barMaxWidth: 48,
        data: ranking.map(item => Number(item[field] || 0)),
        itemStyle: {
          borderRadius: [6, 6, 0, 0],
          color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
            { offset: 0, color },
            { offset: 1, color: `${color}99` }
          ])
        },
        label: {
          show: true,
          position: 'top',
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
      buildChartOption(grossProfitRanking.value, 'grossProfit', '#16a34a', '毛利润'),
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
    await renderCharts()
  } finally {
    loading.value = false
  }
}

function handleQuery() {
  query.pageNum = 1
  loadData()
}

function resetQuery() {
  queryRef.value?.resetFields()
  query.pageNum = 1
  loadData()
}

async function handleRefresh() {
  refreshing.value = true
  try {
    const response = await refreshPerformanceRanking(query.statMonth)
    const result = response.data || {}
    lastRefreshStats.value = result
    if (!query.statMonth) query.statMonth = result.statMonth
    if ((result.unmatchedRows || 0) > 0) {
      proxy.$modal.msgWarning(
        `汇总完成，但有${result.unmatchedRows}条利润数据归入未分配，请检查当月负责人配置`
      )
    } else {
      proxy.$modal.msgSuccess(`负责人匹配完成，共生成${result.rows || 0}条汇总数据`)
    }
    query.pageNum = 1
    await loadData()
  } finally {
    refreshing.value = false
  }
}

function openImportDialog() {
  importForm.file = undefined
  importForm.rebuildAfterImport = true
  importDialogVisible.value = true
}

function handleFileChange(uploadFile) {
  importForm.file = uploadFile.raw
}

function handleFileRemove() {
  importForm.file = undefined
}

function resetImportDialog() {
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
    const response = await importPerformanceOwnerRules(importForm.file)
    const result = response.data || {}
    proxy.$modal.msgSuccess(
      `负责人配置导入完成：${result.sheets?.length || 0}个sheet、${result.monthCount || 0}个月份，共写入${result.importedRows || 0}条规则`
    )
    query.pageNum = 1
    const rebuildAfterImport = importForm.rebuildAfterImport
    importDialogVisible.value = false
    if (rebuildAfterImport) await handleRefresh()
    else await loadData()
  } finally {
    importing.value = false
  }
}

function resizeCharts() {
  grossProfitChart?.resize()
  netSalesChart?.resize()
}

onMounted(() => {
  window.addEventListener('resize', resizeCharts)
  loadData()
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', resizeCharts)
  grossProfitChart?.dispose()
  netSalesChart?.dispose()
})
</script>

<style scoped>
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
  .card-header,
  .ranking-header { align-items: flex-start; flex-direction: column; }
  .subtitle { display: block; margin: 5px 0 0; }
  .ranking-chart { height: 400px; }
}
</style>
