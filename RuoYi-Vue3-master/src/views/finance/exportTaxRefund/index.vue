<template>
  <div class="app-container export-tax-page">
    <el-row :gutter="12" class="filter-row">
      <el-col :xs="24" :sm="12" :md="6">
        <el-date-picker
          v-model="query.month"
          type="month"
          value-format="YYYY-MM"
          placeholder="选择月份"
          clearable
          style="width: 100%"
        />
      </el-col>
      <el-col :xs="24" :sm="12" :md="5">
        <el-select v-model="query.platform" placeholder="平台" clearable style="width: 100%">
          <el-option label="Amazon" value="Amazon" />
          <el-option label="eBay" value="eBay" />
          <el-option label="线下" value="Offline" />
        </el-select>
      </el-col>
      <el-col :xs="24" :sm="12" :md="5">
        <el-select v-model="query.status" placeholder="退税状态" clearable style="width: 100%">
          <el-option label="待申报" value="待申报" />
          <el-option label="申报中" value="申报中" />
          <el-option label="已退税" value="已退税" />
          <el-option label="异常" value="异常" />
        </el-select>
      </el-col>
      <el-col :xs="24" :sm="12" :md="8" class="toolbar">
        <el-button type="primary" icon="Search" @click="handleQuery" v-hasPermi="['finance:exportTaxRefund:query']">查询</el-button>
        <el-button icon="Refresh" @click="resetQuery">重置</el-button>
        <el-button type="warning" plain icon="Download" @click="handleMockExport" v-hasPermi="['finance:exportTaxRefund:export']">导出</el-button>
      </el-col>
    </el-row>

    <el-row :gutter="12" class="summary-row">
      <el-col v-for="item in summaryCards" :key="item.label" :xs="12" :sm="12" :md="6">
        <div class="metric-card">
          <div class="metric-label">{{ item.label }}</div>
          <div class="metric-value">{{ item.value }}</div>
          <div class="metric-sub" :class="{ up: item.trend > 0, down: item.trend < 0 }">
            {{ item.trend > 0 ? '+' : '' }}{{ item.trend }}% 较上月
          </div>
        </div>
      </el-col>
    </el-row>

    <el-row :gutter="12" class="chart-row">
      <el-col :xs="24" :lg="14">
        <div class="panel">
          <div class="panel-title">平台退税金额</div>
          <div ref="barChartRef" class="chart"></div>
        </div>
      </el-col>
      <el-col :xs="24" :lg="10">
        <div class="panel">
          <div class="panel-title">月度退税趋势</div>
          <div ref="lineChartRef" class="chart"></div>
        </div>
      </el-col>
    </el-row>

    <div class="panel table-panel">
      <div class="panel-head">
        <div>
          <div class="panel-title">外汇退税明细</div>
          <div class="panel-subtitle">当前为测试静态数据，后续可接入报关单、收汇和退税申报数据源。</div>
        </div>
        <el-tag type="info">共 {{ filteredRows.length }} 条</el-tag>
      </div>
      <el-table :data="filteredRows" border stripe height="430" @sort-change="handleSortChange">
        <el-table-column prop="declareNo" label="报关单号" min-width="150" show-overflow-tooltip />
        <el-table-column prop="platform" label="平台" width="100" />
        <el-table-column prop="country" label="目的国" width="100" />
        <el-table-column prop="declareDate" label="出口日期" width="120" sortable="custom" />
        <el-table-column prop="foreignAmount" label="收汇金额" width="120" align="right" sortable="custom">
          <template #default="scope">{{ money(scope.row.foreignAmount) }}</template>
        </el-table-column>
        <el-table-column prop="rmbAmount" label="人民币金额" width="130" align="right" sortable="custom">
          <template #default="scope">{{ money(scope.row.rmbAmount) }}</template>
        </el-table-column>
        <el-table-column prop="taxRefundAmount" label="预计退税" width="120" align="right" sortable="custom">
          <template #default="scope">{{ money(scope.row.taxRefundAmount) }}</template>
        </el-table-column>
        <el-table-column prop="status" label="状态" width="100">
          <template #default="scope">
            <el-tag :type="statusType(scope.row.status)">{{ scope.row.status }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="owner" label="负责人" width="110" />
        <el-table-column prop="remark" label="备注" min-width="180" show-overflow-tooltip />
      </el-table>
    </div>
  </div>
</template>

<script setup name="ExportTaxRefund">
import * as echarts from 'echarts'

const { proxy } = getCurrentInstance()
const barChartRef = ref()
const lineChartRef = ref()
let barChart
let lineChart

const query = reactive({
  month: '',
  platform: '',
  status: ''
})

const sortState = reactive({
  prop: '',
  order: ''
})

const rows = ref([
  { declareNo: '310120260501001', platform: 'Amazon', country: '美国', declareDate: '2026-05-01', foreignAmount: 128600, rmbAmount: 916420, taxRefundAmount: 119135, status: '已退税', owner: '欧洲组', remark: 'FBA货件资料齐全' },
  { declareNo: '310120260508014', platform: 'eBay', country: '英国', declareDate: '2026-05-08', foreignAmount: 84200, rmbAmount: 600346, taxRefundAmount: 78045, status: '申报中', owner: '英国组', remark: '等待银行水单复核' },
  { declareNo: '310120260516027', platform: 'Amazon', country: '德国', declareDate: '2026-05-16', foreignAmount: 156300, rmbAmount: 1114401, taxRefundAmount: 144872, status: '待申报', owner: '欧洲组', remark: '缺少部分采购发票' },
  { declareNo: '310120260523036', platform: 'eBay', country: '美国', declareDate: '2026-05-23', foreignAmount: 96500, rmbAmount: 688045, taxRefundAmount: 89446, status: '异常', owner: '美国组', remark: '报关金额与收汇金额差异待确认' },
  { declareNo: '310120260601006', platform: 'Amazon', country: '法国', declareDate: '2026-06-01', foreignAmount: 112900, rmbAmount: 804957, taxRefundAmount: 104644, status: '已退税', owner: '欧洲组', remark: '已完成退税入账' },
  { declareNo: '310120260612020', platform: 'Offline', country: '加拿大', declareDate: '2026-06-12', foreignAmount: 47800, rmbAmount: 340814, taxRefundAmount: 44306, status: '待申报', owner: '线下组', remark: '测试订单' },
  { declareNo: '310120260625032', platform: 'Amazon', country: '美国', declareDate: '2026-06-25', foreignAmount: 203400, rmbAmount: 1450242, taxRefundAmount: 188531, status: '申报中', owner: '美国组', remark: '批次金额较大，优先跟进' },
  { declareNo: '310120260704011', platform: 'eBay', country: '德国', declareDate: '2026-07-04', foreignAmount: 73800, rmbAmount: 526194, taxRefundAmount: 68405, status: '待申报', owner: '欧洲组', remark: '静态演示数据' }
])

const filteredRows = computed(() => {
  let list = rows.value.filter(row => {
    const matchMonth = !query.month || row.declareDate.startsWith(query.month)
    const matchPlatform = !query.platform || row.platform === query.platform
    const matchStatus = !query.status || row.status === query.status
    return matchMonth && matchPlatform && matchStatus
  })

  if (sortState.prop && sortState.order) {
    const direction = sortState.order === 'ascending' ? 1 : -1
    list = [...list].sort((a, b) => {
      const av = a[sortState.prop]
      const bv = b[sortState.prop]
      return av > bv ? direction : av < bv ? -direction : 0
    })
  }

  return list
})

const summaryCards = computed(() => {
  const list = filteredRows.value
  const rmb = list.reduce((sum, row) => sum + row.rmbAmount, 0)
  const refund = list.reduce((sum, row) => sum + row.taxRefundAmount, 0)
  const abnormal = list.filter(row => row.status === '异常').length
  const pending = list.filter(row => row.status === '待申报').length
  return [
    { label: '出口人民币金额', value: money(rmb), trend: 8.4 },
    { label: '预计退税金额', value: money(refund), trend: 6.2 },
    { label: '待申报批次', value: pending, trend: -12.5 },
    { label: '异常批次', value: abnormal, trend: abnormal > 0 ? 3.1 : 0 }
  ]
})

watch(filteredRows, () => renderCharts(), { deep: true })

onMounted(() => {
  nextTick(() => {
    barChart = echarts.init(barChartRef.value)
    lineChart = echarts.init(lineChartRef.value)
    renderCharts()
    window.addEventListener('resize', resizeCharts)
  })
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', resizeCharts)
  barChart?.dispose()
  lineChart?.dispose()
})

function renderCharts() {
  if (!barChart || !lineChart) return
  const platformMap = {}
  filteredRows.value.forEach(row => {
    platformMap[row.platform] = (platformMap[row.platform] || 0) + row.taxRefundAmount
  })

  barChart.setOption({
    tooltip: { trigger: 'axis' },
    grid: { left: 48, right: 20, top: 28, bottom: 32 },
    xAxis: { type: 'category', data: Object.keys(platformMap) },
    yAxis: { type: 'value' },
    series: [{ type: 'bar', data: Object.values(platformMap), barWidth: 36, itemStyle: { color: '#337ecc' } }]
  })

  lineChart.setOption({
    tooltip: { trigger: 'axis' },
    grid: { left: 48, right: 20, top: 28, bottom: 32 },
    xAxis: { type: 'category', data: ['2026-02', '2026-03', '2026-04', '2026-05', '2026-06', '2026-07'] },
    yAxis: { type: 'value' },
    series: [{ type: 'line', smooth: true, data: [82000, 94000, 103000, 117000, 149000, 68405], itemStyle: { color: '#67c23a' }, areaStyle: { color: 'rgba(103,194,58,.12)' } }]
  })
}

function resizeCharts() {
  barChart?.resize()
  lineChart?.resize()
}

function handleQuery() {
  renderCharts()
}

function resetQuery() {
  query.month = ''
  query.platform = ''
  query.status = ''
  sortState.prop = ''
  sortState.order = ''
}

function handleSortChange({ prop, order }) {
  sortState.prop = prop
  sortState.order = order
}

function handleMockExport() {
  proxy.$modal.msgSuccess('静态演示页面，真实导出接口后续接入')
}

function money(value) {
  return Number(value || 0).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function statusType(status) {
  return {
    '已退税': 'success',
    '申报中': 'warning',
    '待申报': 'info',
    '异常': 'danger'
  }[status] || 'info'
}
</script>

<style scoped>
.export-tax-page {
  background: #f6f8fb;
}

.filter-row {
  margin-bottom: 12px;
}

.toolbar {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}

.summary-row,
.chart-row {
  margin-bottom: 12px;
}

.metric-card,
.panel {
  background: #fff;
  border: 1px solid #e5e7eb;
  border-radius: 6px;
}

.metric-card {
  padding: 16px;
  min-height: 104px;
}

.metric-label {
  color: #64748b;
  font-size: 13px;
}

.metric-value {
  margin-top: 10px;
  color: #1f2937;
  font-size: 24px;
  font-weight: 700;
}

.metric-sub {
  margin-top: 8px;
  color: #909399;
  font-size: 12px;
}

.metric-sub.up {
  color: #67c23a;
}

.metric-sub.down {
  color: #f56c6c;
}

.panel {
  padding: 14px;
}

.panel-title {
  color: #1f2937;
  font-size: 15px;
  font-weight: 700;
}

.panel-subtitle {
  margin-top: 4px;
  color: #909399;
  font-size: 12px;
}

.panel-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}

.chart {
  width: 100%;
  height: 300px;
}

.table-panel {
  margin-bottom: 12px;
}

@media (max-width: 768px) {
  .toolbar {
    justify-content: flex-start;
    margin-top: 8px;
  }

  .metric-card {
    margin-bottom: 12px;
  }
}
</style>
