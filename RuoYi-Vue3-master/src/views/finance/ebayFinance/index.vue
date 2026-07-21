<template>
  <div class="app-container ebay-finance-page">
    <section class="page-hero">
      <div>
        <div class="eyebrow">FINANCE / EBAY</div>
        <h1>eBay 财务驾驶舱</h1>
        <p>经营指标可视化、酋长利润增量导入与 SKU 财务明细维护</p>
      </div>
      <div class="hero-actions">
        <el-upload
          accept=".xlsx"
          :show-file-list="false"
          :before-upload="handleChiefProfitImport"
          v-hasPermi="['finance:ebayFinance:import']"
        >
          <el-button type="primary" icon="Upload" :loading="importing">导入酋长利润</el-button>
        </el-upload>
        <el-button icon="Refresh" :loading="loading" @click="refreshAll">刷新数据</el-button>
      </div>
    </section>

    <el-alert
      class="file-rule"
      type="info"
      :closable="false"
      show-icon
      title="文件名规则：平台-站点-开始日期-结束日期.xlsx（例如 ebay-美国-20260705-20260714.xlsx）；同周期同 SKU 自动覆盖，其他周期增量新增。"
    />

    <section class="kpi-grid">
      <article v-for="item in kpis" :key="item.label" class="kpi-card">
        <div class="kpi-label">{{ item.label }}</div>
        <div class="kpi-value">{{ item.value }}</div>
        <div class="kpi-foot" :class="item.trend >= 0 ? 'up' : 'down'">
          <span>{{ item.trend >= 0 ? '↑' : '↓' }} {{ Math.abs(item.trend) }}%</span>
          <span>较上期</span>
        </div>
      </article>
    </section>

    <el-row :gutter="16" class="chart-row">
      <el-col :xs="24" :lg="16">
        <el-card shadow="never" class="chart-card">
          <template #header>
            <div class="card-title"><span>销售与利润趋势</span><small>USD · 静态演示数据</small></div>
          </template>
          <div ref="trendChartRef" class="chart chart-large" />
        </el-card>
      </el-col>
      <el-col :xs="24" :lg="8">
        <el-card shadow="never" class="chart-card">
          <template #header>
            <div class="card-title"><span>费用构成</span><small>静态演示数据</small></div>
          </template>
          <div ref="costChartRef" class="chart chart-large" />
        </el-card>
      </el-col>
    </el-row>

    <el-card shadow="never" class="chart-card site-card">
      <template #header>
        <div class="card-title"><span>站点经营表现</span><small>销售额 / 利润 · 静态演示数据</small></div>
      </template>
      <div ref="siteChartRef" class="chart chart-site" />
    </el-card>

    <el-card shadow="never" class="data-card">
      <template #header>
        <div class="data-card-header">
          <div class="card-title"><span>已导入财务明细</span><small>真实数据库数据</small></div>
          <el-form :model="query" inline class="query-form">
            <el-form-item label="站点">
              <el-input v-model="query.site" clearable placeholder="美国" style="width: 120px" />
            </el-form-item>
            <el-form-item label="SKU">
              <el-input v-model="query.sku" clearable placeholder="输入 SKU" style="width: 180px" @keyup.enter="loadRows" />
            </el-form-item>
            <el-form-item>
              <el-button type="primary" icon="Search" @click="handleQuery">查询</el-button>
              <el-button icon="Refresh" @click="resetQuery">重置</el-button>
            </el-form-item>
          </el-form>
        </div>
      </template>

      <el-table v-loading="loading" :data="rows" border stripe height="430">
        <el-table-column prop="site" label="站点" width="80" fixed />
        <el-table-column prop="periodStart" label="开始日期" width="105" />
        <el-table-column prop="periodEnd" label="结束日期" width="105" />
        <el-table-column prop="sku" label="SKU" min-width="165" show-overflow-tooltip />
        <el-table-column prop="orderTotal" label="订单总额" width="120" align="right">
          <template #default="{ row }">{{ money(row.orderTotal) }}</template>
        </el-table-column>
        <el-table-column prop="unitsSold" label="售出数" width="90" align="right" />
        <el-table-column prop="orderCount" label="订单数" width="90" align="right" />
        <el-table-column prop="profit" label="利润" width="115" align="right">
          <template #default="{ row }"><span :class="Number(row.profit) >= 0 ? 'profit-positive' : 'profit-negative'">{{ money(row.profit) }}</span></template>
        </el-table-column>
        <el-table-column prop="profitMargin" label="利润率" width="95" align="right">
          <template #default="{ row }">{{ percent(row.profitMargin) }}</template>
        </el-table-column>
        <el-table-column prop="platformFee" label="平台费用" width="110" align="right">
          <template #default="{ row }">{{ money(row.platformFee) }}</template>
        </el-table-column>
        <el-table-column prop="purchaseCost" label="采购成本" width="110" align="right">
          <template #default="{ row }">{{ money(row.purchaseCost) }}</template>
        </el-table-column>
        <el-table-column prop="advertisingFee" label="广告费" width="105" align="right">
          <template #default="{ row }">{{ money(row.advertisingFee) }}</template>
        </el-table-column>
        <el-table-column prop="updateTime" label="修改时间" width="165" />
        <el-table-column label="操作" width="80" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" icon="Edit" @click="openEdit(row)" v-hasPermi="['finance:ebayFinance:edit']">编辑</el-button>
          </template>
        </el-table-column>
      </el-table>
      <Pagination
        v-show="total > 0"
        :total="total"
        v-model:page="query.pageNum"
        v-model:limit="query.pageSize"
        @pagination="loadRows"
      />
    </el-card>

    <el-card shadow="never" class="data-card import-card">
      <template #header><div class="card-title"><span>导入记录</span><small>真实导入结果</small></div></template>
      <el-table :data="imports" size="small" border>
        <el-table-column prop="fileName" label="文件名" min-width="260" show-overflow-tooltip />
        <el-table-column prop="site" label="站点" width="80" />
        <el-table-column label="统计周期" width="205">
          <template #default="{ row }">{{ row.periodStart }} 至 {{ row.periodEnd }}</template>
        </el-table-column>
        <el-table-column prop="totalRows" label="有效行" width="85" align="right" />
        <el-table-column prop="insertedRows" label="新增" width="80" align="right" />
        <el-table-column prop="updatedRows" label="覆盖" width="80" align="right" />
        <el-table-column prop="operator" label="导入人" width="105" />
        <el-table-column prop="updateTime" label="导入时间" width="165" />
        <el-table-column prop="status" label="状态" width="90">
          <template #default="{ row }"><el-tag type="success">{{ row.status }}</el-tag></template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-dialog v-model="editVisible" title="编辑 eBay 财务明细" width="720px" append-to-body>
      <el-form :model="editForm" label-width="92px">
        <el-row :gutter="16">
          <el-col :span="12"><el-form-item label="SKU"><el-input :model-value="editForm.sku" disabled /></el-form-item></el-col>
          <el-col :span="12"><el-form-item label="统计周期"><el-input :model-value="`${editForm.periodStart || ''} ~ ${editForm.periodEnd || ''}`" disabled /></el-form-item></el-col>
          <el-col v-for="field in editFields" :key="field.key" :span="12">
            <el-form-item :label="field.label">
              <el-input-number v-model="editForm[field.key]" :precision="field.precision" :step="field.step" controls-position="right" style="width: 100%" />
            </el-form-item>
          </el-col>
        </el-row>
      </el-form>
      <template #footer>
        <el-button @click="editVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="saveEdit">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup name="EbayFinance">
import { getCurrentInstance, nextTick, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import * as echarts from 'echarts'
import { importChiefProfit, listEbayFinance, listEbayFinanceImports, updateEbayFinance } from '@/api/finance/ebayFinance'

const { proxy } = getCurrentInstance()
const loading = ref(false)
const importing = ref(false)
const saving = ref(false)
const rows = ref([])
const imports = ref([])
const total = ref(0)
const editVisible = ref(false)
const editForm = reactive({})
const trendChartRef = ref(null)
const costChartRef = ref(null)
const siteChartRef = ref(null)
const charts = []

const query = reactive({ pageNum: 1, pageSize: 20, site: '', sku: '' })

const kpis = [
  { label: '销售总额', value: '$286,430', trend: 12.6 },
  { label: '净利润', value: '$61,842', trend: 8.9 },
  { label: '整体利润率', value: '21.59%', trend: 1.8 },
  { label: '广告投入产出比', value: '6.42', trend: -2.3 }
]

const editFields = [
  { key: 'orderTotal', label: '订单总额', precision: 2, step: 1 },
  { key: 'orderAmount', label: '订单金额', precision: 2, step: 1 },
  { key: 'unitsSold', label: '售出数', precision: 0, step: 1 },
  { key: 'orderCount', label: '订单数', precision: 0, step: 1 },
  { key: 'taxAmount', label: '税费', precision: 2, step: 1 },
  { key: 'profit', label: '利润', precision: 2, step: 1 },
  { key: 'profitMargin', label: '利润率小数', precision: 4, step: 0.01 },
  { key: 'productSalesAmount', label: '商品销售额', precision: 2, step: 1 },
  { key: 'platformFee', label: '平台费用', precision: 2, step: 1 },
  { key: 'purchaseCost', label: '采购成本', precision: 2, step: 1 },
  { key: 'advertisingFee', label: '广告费', precision: 2, step: 1 },
  { key: 'refundAmount', label: '退款金额', precision: 2, step: 1 }
]

async function loadRows() {
  loading.value = true
  try {
    const res = await listEbayFinance(query)
    rows.value = res.rows || []
    total.value = res.total || 0
  } finally {
    loading.value = false
  }
}

async function loadImports() {
  const res = await listEbayFinanceImports({ pageNum: 1, pageSize: 10 })
  imports.value = res.rows || []
}

function handleQuery() {
  query.pageNum = 1
  loadRows()
}

function resetQuery() {
  query.pageNum = 1
  query.site = ''
  query.sku = ''
  loadRows()
}

async function refreshAll() {
  await Promise.all([loadRows(), loadImports()])
}

async function handleChiefProfitImport(file) {
  if (!/\.xlsx$/i.test(file.name)) {
    proxy.$modal.msgError('仅支持 .xlsx 文件')
    return false
  }
  importing.value = true
  try {
    const res = await importChiefProfit(file)
    const data = res.data || {}
    proxy.$modal.msgSuccess(`导入成功：新增 ${data.insertedRows || 0} 条，覆盖 ${data.updatedRows || 0} 条`)
    await refreshAll()
  } finally {
    importing.value = false
  }
  return false
}

function openEdit(row) {
  Object.keys(editForm).forEach(key => delete editForm[key])
  Object.assign(editForm, JSON.parse(JSON.stringify(row)))
  editVisible.value = true
}

async function saveEdit() {
  saving.value = true
  try {
    await updateEbayFinance(editForm.id, editForm)
    proxy.$modal.msgSuccess('保存成功')
    editVisible.value = false
    await loadRows()
  } finally {
    saving.value = false
  }
}

function money(value) {
  if (value === null || value === undefined || value === '') return '-'
  return '$' + Number(value).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function percent(value) {
  if (value === null || value === undefined || value === '') return '-'
  return (Number(value) * 100).toFixed(2) + '%'
}

function createChart(element, option) {
  const chart = echarts.init(element)
  chart.setOption(option)
  charts.push(chart)
}

function initCharts() {
  createChart(trendChartRef.value, {
    color: ['#2563eb', '#10b981'],
    tooltip: { trigger: 'axis' },
    legend: { data: ['销售额', '净利润'], top: 0 },
    grid: { left: 18, right: 18, bottom: 10, top: 44, containLabel: true },
    xAxis: { type: 'category', boundaryGap: false, data: ['1月', '2月', '3月', '4月', '5月', '6月', '7月'] },
    yAxis: { type: 'value', axisLabel: { formatter: value => '$' + (value / 1000) + 'k' }, splitLine: { lineStyle: { color: '#eef2f7' } } },
    series: [
      { name: '销售额', type: 'line', smooth: true, symbolSize: 7, areaStyle: { opacity: 0.1 }, data: [182000, 201500, 194200, 226800, 241300, 259700, 286430] },
      { name: '净利润', type: 'line', smooth: true, symbolSize: 7, data: [36800, 42100, 39700, 49200, 52800, 56700, 61842] }
    ]
  })
  createChart(costChartRef.value, {
    color: ['#2563eb', '#7c3aed', '#f59e0b', '#ef4444', '#14b8a6'],
    tooltip: { trigger: 'item', formatter: '{b}<br/>${c} · {d}%' },
    legend: { bottom: 0, left: 'center' },
    series: [{
      type: 'pie', radius: ['48%', '72%'], center: ['50%', '43%'], avoidLabelOverlap: true,
      label: { formatter: '{d}%' },
      data: [
        { name: '采购成本', value: 109600 }, { name: '平台费用', value: 46100 },
        { name: '广告费', value: 27600 }, { name: '物流费用', value: 23200 }, { name: '其他', value: 18100 }
      ]
    }]
  })
  createChart(siteChartRef.value, {
    color: ['#2563eb', '#10b981'],
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
    legend: { top: 0 },
    grid: { left: 20, right: 20, bottom: 5, top: 42, containLabel: true },
    xAxis: { type: 'category', data: ['美国', '英国', '德国', '澳洲', '加拿大'] },
    yAxis: { type: 'value', axisLabel: { formatter: value => '$' + (value / 1000) + 'k' }, splitLine: { lineStyle: { color: '#eef2f7' } } },
    series: [
      { name: '销售额', type: 'bar', barMaxWidth: 34, data: [142600, 54800, 42100, 26800, 20130] },
      { name: '利润', type: 'bar', barMaxWidth: 34, data: [32900, 11200, 8700, 5100, 3942] }
    ]
  })
}

function resizeCharts() {
  charts.forEach(chart => chart.resize())
}

onMounted(async () => {
  await nextTick()
  initCharts()
  window.addEventListener('resize', resizeCharts)
  refreshAll()
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', resizeCharts)
  charts.forEach(chart => chart.dispose())
})
</script>

<style scoped>
.ebay-finance-page { background: #f5f7fb; min-height: calc(100vh - 84px); }
.page-hero { display: flex; justify-content: space-between; align-items: center; padding: 24px 28px; border-radius: 14px; color: #fff; background: linear-gradient(125deg, #102a56 0%, #164ca2 55%, #1f75d6 100%); box-shadow: 0 14px 32px rgba(16, 42, 86, .18); }
.eyebrow { font-size: 11px; letter-spacing: 2.4px; color: #93c5fd; }
.page-hero h1 { margin: 7px 0 5px; font-size: 27px; font-weight: 650; }
.page-hero p { margin: 0; color: rgba(255,255,255,.76); }
.hero-actions { display: flex; align-items: center; gap: 10px; }
.hero-actions :deep(.el-button:not(.el-button--primary)) { color: #e5efff; border-color: rgba(255,255,255,.28); background: rgba(255,255,255,.08); }
.file-rule { margin: 16px 0; }
.kpi-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px; margin-bottom: 16px; }
.kpi-card { padding: 19px 21px; border: 1px solid #e7ebf2; border-radius: 12px; background: #fff; box-shadow: 0 4px 16px rgba(15, 23, 42, .04); }
.kpi-label { color: #64748b; font-size: 13px; }
.kpi-value { margin: 9px 0 10px; color: #0f172a; font-size: 27px; font-weight: 650; font-variant-numeric: tabular-nums; }
.kpi-foot { display: flex; justify-content: space-between; font-size: 12px; color: #94a3b8; }
.kpi-foot.up span:first-child { color: #059669; }
.kpi-foot.down span:first-child { color: #dc2626; }
.chart-row { margin-bottom: 16px; }
.chart-card, .data-card { border: 1px solid #e7ebf2; border-radius: 12px; }
.card-title { display: flex; align-items: baseline; justify-content: space-between; gap: 12px; color: #172033; font-size: 15px; font-weight: 600; }
.card-title small { color: #94a3b8; font-size: 11px; font-weight: 400; }
.chart { width: 100%; }
.chart-large { height: 330px; }
.chart-site { height: 250px; }
.site-card, .data-card { margin-bottom: 16px; }
.data-card-header { display: flex; justify-content: space-between; align-items: center; gap: 16px; }
.query-form :deep(.el-form-item) { margin-bottom: 0; }
.profit-positive { color: #059669; font-weight: 600; }
.profit-negative { color: #dc2626; font-weight: 600; }
.import-card { margin-bottom: 0; }
@media (max-width: 1100px) {
  .kpi-grid { grid-template-columns: repeat(2, 1fr); }
  .data-card-header { display: block; }
  .query-form { margin-top: 14px; }
}
@media (max-width: 720px) {
  .page-hero { align-items: flex-start; flex-direction: column; gap: 18px; }
  .kpi-grid { grid-template-columns: 1fr; }
  .hero-actions { flex-wrap: wrap; }
}
</style>
