<template>
  <div class="app-container report-page">
    <el-page-header @back="$router.push('/report/inventory')">
      <template #content>月初库存货值检查</template>
    </el-page-header>

    <div class="filter-panel">
      <el-form :model="queryParams" :inline="true" label-width="76px">
        <el-form-item label="报表日期">
          <el-date-picker
            v-model="queryParams.reportDate"
            type="month"
            value-format="YYYY-MM"
            placeholder="选择月份"
            style="width: 150px"
          />
        </el-form-item>
        <el-form-item label="仓库类型">
          <el-select v-model="queryParams.warehouseType" clearable style="width: 150px">
            <el-option label="本地仓" value="LOCAL" />
            <el-option label="海外仓" value="OVERSEAS" />
            <el-option label="FBA仓" value="FBA" />
            <el-option label="AWD仓" value="AWD" />
          </el-select>
        </el-form-item>
        <el-form-item label="成本状态">
          <el-select v-model="queryParams.costStatus" clearable style="width: 150px">
            <el-option label="正常" value="OK" />
            <el-option label="零成本" value="ZERO_COST" />
            <el-option label="零数量" value="ZERO_QTY" />
            <el-option label="缺成本" value="MISSING_COST" />
          </el-select>
        </el-form-item>
        <el-form-item label="运营组">
          <el-select v-model="queryParams.operationGroup" clearable style="width: 150px">
            <el-option label="刘子洋组" value="刘子洋组" />
            <el-option label="李雷组" value="李雷组" />
            <el-option label="王敏组" value="王敏组" />
          </el-select>
        </el-form-item>
        <el-form-item label="关键字">
          <el-input
            v-model="queryParams.keyword"
            clearable
            placeholder="SKU/仓库/商品"
            style="width: 190px"
            @keyup.enter="handleQuery"
          />
        </el-form-item>
        <el-form-item label="仅异常">
          <el-switch v-model="queryParams.onlyAnomaly" />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" icon="Search" @click="handleQuery">筛选</el-button>
          <el-button icon="Refresh" @click="resetQuery">重置</el-button>
        </el-form-item>
      </el-form>

      <div class="slicer-row">
        <span class="slicer-label">切片器</span>
        <el-check-tag
          v-for="item in warehouseSlices"
          :key="item.value"
          :checked="queryParams.warehouseType === item.value"
          @change="toggleWarehouseSlice(item.value)"
        >
          {{ item.label }}
        </el-check-tag>
        <el-divider direction="vertical" />
        <el-check-tag
          v-for="item in statusSlices"
          :key="item.value"
          :checked="queryParams.costStatus === item.value"
          @change="toggleStatusSlice(item.value)"
        >
          {{ item.label }}
        </el-check-tag>
      </div>
    </div>

    <el-row :gutter="12" class="metric-row">
      <el-col :xs="12" :sm="6" v-for="card in metricCards" :key="card.label">
        <div class="metric-card">
          <div class="metric-label">{{ card.label }}</div>
          <div class="metric-value">{{ card.value }}</div>
          <div class="metric-sub" :class="{ danger: card.danger }">{{ card.sub }}</div>
        </div>
      </el-col>
    </el-row>

    <el-row :gutter="12" class="chart-row">
      <el-col :xs="24" :lg="12">
        <div class="chart-panel">
          <div class="panel-title">仓库类型库存货值</div>
          <div ref="barChartRef" class="chart"></div>
        </div>
      </el-col>
      <el-col :xs="24" :lg="12">
        <div class="chart-panel">
          <div class="panel-title">月度期初库存成本趋势</div>
          <div ref="lineChartRef" class="chart"></div>
        </div>
      </el-col>
    </el-row>

    <el-row :gutter="12" class="chart-row">
      <el-col :xs="24" :lg="8">
        <div class="chart-panel">
          <div class="panel-title">成本状态分布</div>
          <div ref="pieChartRef" class="small-chart"></div>
        </div>
      </el-col>
      <el-col :xs="24" :lg="16">
        <div class="chart-panel">
          <div class="panel-title">运营组库存金额 TOP</div>
          <div ref="groupChartRef" class="small-chart"></div>
        </div>
      </el-col>
    </el-row>

    <div class="table-panel">
      <div class="table-toolbar">
        <div class="panel-title">库存明细</div>
        <div>
          <el-select v-model="sortKey" size="small" style="width: 150px" @change="handleQuery">
            <el-option label="期初成本" value="openingCost" />
            <el-option label="期初数量" value="openingQty" />
            <el-option label="单位成本" value="unitCost" />
            <el-option label="异常优先" value="anomalyFlag" />
          </el-select>
          <el-button size="small" icon="Sort" @click="toggleSortOrder">{{ sortOrderText }}</el-button>
        </div>
      </div>

      <el-table
        :data="pagedRows"
        border
        stripe
        height="420"
        @sort-change="handleTableSort"
      >
        <el-table-column label="报表日期" prop="reportDate" width="110" sortable="custom" />
        <el-table-column label="仓库类型" prop="warehouseTypeName" width="96" />
        <el-table-column label="仓库" prop="warehouseName" min-width="150" show-overflow-tooltip />
        <el-table-column label="运营组" prop="operationGroup" width="100" />
        <el-table-column label="SKU" prop="sku" width="150" show-overflow-tooltip />
        <el-table-column label="商品名称" prop="productName" min-width="180" show-overflow-tooltip />
        <el-table-column label="期初数量" prop="openingQty" width="105" align="right" sortable="custom" />
        <el-table-column label="期初成本" prop="openingCost" width="120" align="right" sortable="custom">
          <template #default="{ row }">{{ formatMoney(row.openingCost) }}</template>
        </el-table-column>
        <el-table-column label="单位成本" prop="unitCost" width="100" align="right" sortable="custom">
          <template #default="{ row }">{{ formatMoney(row.unitCost) }}</template>
        </el-table-column>
        <el-table-column label="成本状态" width="100">
          <template #default="{ row }">
            <el-tag :type="statusType(row.costStatus)" size="small">{{ statusText(row.costStatus) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="异常原因" prop="anomalyReason" min-width="170" show-overflow-tooltip />
      </el-table>

      <pagination
        v-show="filteredRows.length > 0"
        :total="filteredRows.length"
        v-model:page="queryParams.pageNum"
        v-model:limit="queryParams.pageSize"
      />
    </div>
  </div>
</template>

<script setup name="InventoryOpening">
import * as echarts from 'echarts'
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'

const barChartRef = ref()
const lineChartRef = ref()
const pieChartRef = ref()
const groupChartRef = ref()

let barChart
let lineChart
let pieChart
let groupChart

const queryParams = reactive({
  pageNum: 1,
  pageSize: 20,
  reportDate: '2026-07',
  warehouseType: '',
  costStatus: '',
  operationGroup: '',
  keyword: '',
  onlyAnomaly: false
})

const sortKey = ref('openingCost')
const sortOrder = ref('descending')

const warehouseSlices = [
  { label: '本地仓', value: 'LOCAL' },
  { label: '海外仓', value: 'OVERSEAS' },
  { label: 'FBA仓', value: 'FBA' },
  { label: 'AWD仓', value: 'AWD' }
]

const statusSlices = [
  { label: '正常', value: 'OK' },
  { label: '零成本', value: 'ZERO_COST' },
  { label: '零数量', value: 'ZERO_QTY' },
  { label: '缺成本', value: 'MISSING_COST' }
]

const baseRows = [
  ['2026-07-01', 'LOCAL', '本地仓', 'CTUeBay-US中转仓', '刘子洋组', 'BMW-30024-0028', '气门室盖垫', 328, 24600, 'OK'],
  ['2026-07-01', 'LOCAL', '本地仓', 'CTUeBay-DE中转仓', '刘子洋组', 'AUDI-11876-UK', '机油滤芯', 149, 0, 'ZERO_COST'],
  ['2026-07-01', 'LOCAL', '本地仓', 'CTUebay-UK中转仓', '李雷组', 'BENZ-55120-DE', '空气滤芯', 0, 0, 'ZERO_QTY'],
  ['2026-07-01', 'OVERSEAS', '海外仓', '美西海外仓', '王敏组', 'FORD-77881-US', '刹车片套装', 612, 73500, 'OK'],
  ['2026-07-01', 'OVERSEAS', '海外仓', '德国海外仓', '刘子洋组', 'VW-93210-DE', '点火线圈', 236, null, 'MISSING_COST'],
  ['2026-07-01', 'FBA', 'FBA仓', 'Amazon US FBA', '李雷组', 'TESLA-22019-US', '雨刮器', 95, 14250, 'OK'],
  ['2026-07-01', 'AWD', 'AWD仓', 'Amazon AWD', '王敏组', 'HONDA-65001-US', '燃油泵', 43, 6450, 'OK'],
  ['2026-07-01', 'LOCAL', '本地仓', '义乌本地仓', '王敏组', 'TOYOTA-77890-CN', '后视镜总成', 503, 87920, 'OK'],
  ['2026-07-01', 'OVERSEAS', '海外仓', '英国海外仓', '李雷组', 'BMW-44021-UK', '水箱盖', 88, 0, 'ZERO_COST'],
  ['2026-07-01', 'FBA', 'FBA仓', 'Amazon DE FBA', '刘子洋组', 'AUDI-90018-DE', '车门拉手', 31, 3720, 'OK'],
  ['2026-06-01', 'LOCAL', '本地仓', 'CTUeBay-US中转仓', '刘子洋组', 'BMW-30024-0028', '气门室盖垫', 288, 21800, 'OK'],
  ['2026-06-01', 'OVERSEAS', '海外仓', '美西海外仓', '王敏组', 'FORD-77881-US', '刹车片套装', 580, 69600, 'OK'],
  ['2026-05-01', 'LOCAL', '本地仓', '义乌本地仓', '王敏组', 'TOYOTA-77890-CN', '后视镜总成', 460, 80500, 'OK'],
  ['2026-05-01', 'FBA', 'FBA仓', 'Amazon US FBA', '李雷组', 'TESLA-22019-US', '雨刮器', 72, 10800, 'OK'],
  ['2026-04-01', 'OVERSEAS', '海外仓', '德国海外仓', '刘子洋组', 'VW-93210-DE', '点火线圈', 198, 0, 'ZERO_COST'],
  ['2026-04-01', 'LOCAL', '本地仓', 'CTUebay-UK中转仓', '李雷组', 'BENZ-55120-DE', '空气滤芯', 120, 9600, 'OK']
]

const allRows = baseRows.map((item, index) => {
  const openingCost = item[8]
  const openingQty = item[7]
  return {
    id: index + 1,
    reportDate: item[0],
    reportMonth: item[0].slice(0, 7),
    warehouseType: item[1],
    warehouseTypeName: item[2],
    warehouseName: item[3],
    operationGroup: item[4],
    sku: item[5],
    productName: item[6],
    openingQty,
    openingCost,
    unitCost: openingQty && openingCost ? openingCost / openingQty : 0,
    costStatus: item[9],
    anomalyFlag: ['ZERO_COST', 'MISSING_COST'].includes(item[9]) ? 1 : 0,
    anomalyReason: getReason(item[9])
  }
})

const filteredRows = computed(() => {
  const keyword = queryParams.keyword.trim().toLowerCase()
  const rows = allRows.filter(row => {
    const hitKeyword = !keyword || [row.sku, row.warehouseName, row.productName].some(v => String(v).toLowerCase().includes(keyword))
    return (!queryParams.reportDate || row.reportMonth === queryParams.reportDate)
      && (!queryParams.warehouseType || row.warehouseType === queryParams.warehouseType)
      && (!queryParams.costStatus || row.costStatus === queryParams.costStatus)
      && (!queryParams.operationGroup || row.operationGroup === queryParams.operationGroup)
      && (!queryParams.onlyAnomaly || row.anomalyFlag === 1)
      && hitKeyword
  })

  return rows.sort((a, b) => {
    const av = a[sortKey.value] ?? 0
    const bv = b[sortKey.value] ?? 0
    const result = av > bv ? 1 : av < bv ? -1 : 0
    return sortOrder.value === 'ascending' ? result : -result
  })
})

const pagedRows = computed(() => {
  const start = (queryParams.pageNum - 1) * queryParams.pageSize
  return filteredRows.value.slice(start, start + queryParams.pageSize)
})

const metricCards = computed(() => {
  const rows = filteredRows.value
  const totalCost = rows.reduce((sum, row) => sum + Number(row.openingCost || 0), 0)
  const totalQty = rows.reduce((sum, row) => sum + Number(row.openingQty || 0), 0)
  const anomalyCount = rows.filter(row => row.anomalyFlag === 1).length
  return [
    { label: 'SKU行数', value: rows.length.toLocaleString(), sub: '当前筛选结果' },
    { label: '期初数量', value: totalQty.toLocaleString(), sub: '显示数量口径' },
    { label: '期初货值', value: formatMoney(totalCost), sub: '期初成本合计' },
    { label: '异常行数', value: anomalyCount.toLocaleString(), sub: `${rows.length ? ((anomalyCount / rows.length) * 100).toFixed(1) : 0}%`, danger: anomalyCount > 0 }
  ]
})

const sortOrderText = computed(() => sortOrder.value === 'ascending' ? '升序' : '降序')

function getReason(status) {
  if (status === 'ZERO_COST') return '期初数量不为0，但期初成本为0'
  if (status === 'MISSING_COST') return '期初数量不为0，但期初成本为空'
  if (status === 'ZERO_QTY') return '期初数量为0，不参与成本异常'
  return ''
}

function statusText(status) {
  return { OK: '正常', ZERO_COST: '零成本', ZERO_QTY: '零数量', MISSING_COST: '缺成本' }[status] || status
}

function statusType(status) {
  if (status === 'OK') return 'success'
  if (status === 'MISSING_COST') return 'danger'
  if (status === 'ZERO_COST') return 'warning'
  return 'info'
}

function formatMoney(value) {
  return Number(value || 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function handleQuery() {
  queryParams.pageNum = 1
  renderCharts()
}

function resetQuery() {
  queryParams.reportDate = '2026-07'
  queryParams.warehouseType = ''
  queryParams.costStatus = ''
  queryParams.operationGroup = ''
  queryParams.keyword = ''
  queryParams.onlyAnomaly = false
  handleQuery()
}

function toggleWarehouseSlice(value) {
  queryParams.warehouseType = queryParams.warehouseType === value ? '' : value
  handleQuery()
}

function toggleStatusSlice(value) {
  queryParams.costStatus = queryParams.costStatus === value ? '' : value
  handleQuery()
}

function toggleSortOrder() {
  sortOrder.value = sortOrder.value === 'ascending' ? 'descending' : 'ascending'
}

function handleTableSort({ prop, order }) {
  if (prop && order) {
    sortKey.value = prop
    sortOrder.value = order
  }
}

function groupBy(rows, key, valueKey = 'openingCost') {
  return rows.reduce((map, row) => {
    const name = row[key] || '未分类'
    map[name] = (map[name] || 0) + Number(row[valueKey] || 0)
    return map
  }, {})
}

function renderCharts() {
  nextTick(() => {
    if (!barChart || !lineChart || !pieChart || !groupChart) return
    const rows = filteredRows.value
    const warehouseData = groupBy(rows, 'warehouseTypeName')
    const groupData = groupBy(rows, 'operationGroup')
    const statusData = rows.reduce((map, row) => {
      const name = statusText(row.costStatus)
      map[name] = (map[name] || 0) + 1
      return map
    }, {})
    const trendData = groupBy(allRows, 'reportMonth')
    const months = Object.keys(trendData).sort()

    barChart?.setOption({
      tooltip: { trigger: 'axis' },
      grid: { left: 48, right: 18, top: 30, bottom: 36 },
      xAxis: { type: 'category', data: Object.keys(warehouseData) },
      yAxis: { type: 'value' },
      series: [{ type: 'bar', data: Object.values(warehouseData), itemStyle: { color: '#409eff' } }]
    })

    lineChart?.setOption({
      tooltip: { trigger: 'axis' },
      grid: { left: 48, right: 18, top: 30, bottom: 36 },
      xAxis: { type: 'category', data: months },
      yAxis: { type: 'value' },
      series: [{ type: 'line', smooth: true, areaStyle: {}, data: months.map(m => trendData[m]), itemStyle: { color: '#67c23a' } }]
    })

    pieChart?.setOption({
      tooltip: { trigger: 'item' },
      legend: { bottom: 0 },
      series: [{
        type: 'pie',
        radius: ['45%', '70%'],
        center: ['50%', '44%'],
        data: Object.keys(statusData).map(name => ({ name, value: statusData[name] }))
      }]
    })

    groupChart?.setOption({
      tooltip: { trigger: 'axis' },
      grid: { left: 48, right: 18, top: 30, bottom: 36 },
      xAxis: { type: 'category', data: Object.keys(groupData) },
      yAxis: { type: 'value' },
      series: [{ type: 'bar', data: Object.values(groupData), itemStyle: { color: '#e6a23c' } }]
    })
  })
}

function resizeCharts() {
  barChart?.resize()
  lineChart?.resize()
  pieChart?.resize()
  groupChart?.resize()
}

watch([filteredRows, sortKey, sortOrder], renderCharts)

onMounted(() => {
  if (!barChartRef.value || !lineChartRef.value || !pieChartRef.value || !groupChartRef.value) return
  barChart = echarts.init(barChartRef.value)
  lineChart = echarts.init(lineChartRef.value)
  pieChart = echarts.init(pieChartRef.value)
  groupChart = echarts.init(groupChartRef.value)
  renderCharts()
  window.addEventListener('resize', resizeCharts)
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', resizeCharts)
  barChart?.dispose()
  lineChart?.dispose()
  pieChart?.dispose()
  groupChart?.dispose()
})
</script>

<style scoped>
.report-page {
  background: #f5f7fa;
}

.filter-panel,
.chart-panel,
.table-panel,
.metric-card {
  background: #fff;
  border: 1px solid #e5e7eb;
  border-radius: 6px;
}

.filter-panel {
  margin-top: 12px;
  padding: 14px 14px 10px;
}

.slicer-row {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  min-height: 30px;
}

.slicer-label {
  color: #606266;
  font-size: 13px;
  margin-right: 4px;
}

.metric-row,
.chart-row {
  margin-top: 12px;
}

.metric-card {
  padding: 14px 16px;
  min-height: 92px;
}

.metric-label {
  color: #606266;
  font-size: 13px;
}

.metric-value {
  margin-top: 8px;
  color: #1f2937;
  font-size: 24px;
  font-weight: 700;
}

.metric-sub {
  margin-top: 6px;
  color: #909399;
  font-size: 12px;
}

.metric-sub.danger {
  color: #f56c6c;
}

.chart-panel {
  padding: 12px;
}

.panel-title {
  color: #303133;
  font-size: 15px;
  font-weight: 600;
}

.chart {
  width: 100%;
  height: 320px;
}

.small-chart {
  width: 100%;
  height: 260px;
}

.table-panel {
  margin-top: 12px;
  padding: 12px;
}

.table-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 10px;
  gap: 12px;
}

@media (max-width: 768px) {
  .table-toolbar {
    align-items: flex-start;
    flex-direction: column;
  }

  .chart,
  .small-chart {
    height: 260px;
  }
}
</style>
