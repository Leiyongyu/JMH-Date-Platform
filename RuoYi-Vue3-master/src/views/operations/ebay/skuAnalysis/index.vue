<template>
  <div class="app-container sku-analysis">
    <el-card shadow="never" class="filter-card">
      <el-form :model="query" inline>
        <el-form-item label="站点">
          <el-select v-model="query.site" clearable placeholder="所有站点" style="width: 130px">
            <el-option v-for="item in sites" :key="item" :label="item" :value="item" />
          </el-select>
        </el-form-item>
        <el-form-item label="SKU">
          <el-input v-model="query.sku" clearable placeholder="输入SKU" style="width: 190px" @keyup.enter="search" />
        </el-form-item>
        <el-form-item label="付款日期">
          <el-date-picker v-model="paymentRange" type="daterange" value-format="YYYY-MM-DD"
            range-separator="至" start-placeholder="开始日期" end-placeholder="结束日期"
            :clearable="false" :disabled-date="disabledPaymentDate" style="width: 260px" @change="handleDateChange" />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" icon="Search" @click="search">搜索</el-button>
          <el-button icon="Refresh" @click="reset">重置</el-button>
          <el-button type="success" icon="Upload" v-hasPermi="['operations:ebaySkuAnalysis:import']" @click="openImport">上传订单</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <div class="summary-grid">
      <div v-for="card in cards" :key="card.label" class="summary-card">
        <span>{{ card.label }}</span><strong>{{ card.value }}</strong>
      </div>
    </div>

    <el-card shadow="never" class="chart-card">
      <template #header>
        <div class="card-title chart-title">
          <span>分析图表</span>
          <div class="chart-controls">
            <el-select v-model="query.chartMetric" style="width: 150px" @change="handleChartQueryChange">
              <el-option v-for="item in chartMetrics" :key="item.value" :label="item.label" :value="item.value" />
            </el-select>
            <el-select v-model="query.chartOrder" style="width: 92px" @change="handleChartQueryChange">
              <el-option label="降序" value="desc" /><el-option label="升序" value="asc" />
            </el-select>
            <el-button-group class="chart-switch">
              <el-tooltip content="横向柱状图" placement="top">
                <el-button :class="{ active: chartType==='horizontalBar' }" aria-label="横向柱状图" @click="changeChartType('horizontalBar')">
                  <svg viewBox="0 0 20 20" aria-hidden="true"><rect x="3" y="4" width="11" height="2.4" rx="1"/><rect x="3" y="8.8" width="15" height="2.4" rx="1"/><rect x="3" y="13.6" width="8" height="2.4" rx="1"/></svg>
                </el-button>
              </el-tooltip>
              <el-tooltip content="纵向柱状图" placement="top">
                <el-button :class="{ active: chartType==='bar' }" aria-label="纵向柱状图" @click="changeChartType('bar')">
                  <svg viewBox="0 0 20 20" aria-hidden="true"><rect x="3" y="10" width="3" height="7" rx="1"/><rect x="8.5" y="5" width="3" height="12" rx="1"/><rect x="14" y="8" width="3" height="9" rx="1"/></svg>
                </el-button>
              </el-tooltip>
              <el-tooltip content="折线图" placement="top">
                <el-button :class="{ active: chartType==='line' }" aria-label="折线图" @click="changeChartType('line')">
                  <svg viewBox="0 0 20 20" aria-hidden="true"><polyline points="2.5,15 7,10.5 10.5,12.5 17.5,5" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/><circle cx="7" cy="10.5" r="1.3"/><circle cx="10.5" cy="12.5" r="1.3"/></svg>
                </el-button>
              </el-tooltip>
            </el-button-group>
          </div>
        </div>
      </template>
      <div ref="chartRef" class="chart"></div>
    </el-card>

    <el-card shadow="never" class="table-card">
      <template #header><div class="card-title"><span>SKU销售基础表格</span><small>按付款日期实时计算；所有金额按Excel汇率统一换算为人民币</small></div></template>
      <el-table v-loading="loading" :data="rows" stripe height="520">
        <el-table-column label="图片" width="82" fixed>
          <template #default="scope"><el-image v-if="scope.row.picture_url" :src="scope.row.picture_url" fit="cover"
            class="sku-image" :preview-src-list="[scope.row.picture_url]" preview-teleported /><span v-else class="no-image">暂无</span></template>
        </el-table-column>
        <el-table-column prop="site_name" label="站点" width="85" align="center" fixed />
        <el-table-column prop="inventory_sku" label="SKU" min-width="170" fixed />
        <el-table-column prop="paid_amount" label="已支付金额" min-width="130" align="right">
          <template #default="scope">{{ money(scope.row.paid_amount) }}</template>
        </el-table-column>
        <el-table-column prop="sold_quantity" label="已售出" width="95" align="right" />
        <el-table-column prop="average_order_value" label="客单价" width="135" align="right">
          <template #default="scope">{{ money(scope.row.average_order_value) }}</template>
        </el-table-column>
        <el-table-column prop="buyer_count" label="买家数" width="125" align="right" />
        <el-table-column prop="refund_count" label="退货数" width="90" align="right" />
        <el-table-column prop="refund_amount" label="同期退款金额" width="135" align="right">
          <template #default="scope">{{ money(scope.row.refund_amount) }}</template>
        </el-table-column>
        <el-table-column prop="return_rate" label="退货率" width="105" align="right">
          <template #default="scope">{{ percentage(scope.row.return_rate) }}</template>
        </el-table-column>
        <el-table-column prop="shipping_amount" label="运费" width="125" align="right">
          <template #default="scope">{{ money(scope.row.shipping_amount) }}</template>
        </el-table-column>
        <el-table-column prop="listing_start_time" label="上架时间" width="165" />
        <el-table-column prop="latest_listing_start_time" label="最近上架时间" width="165" />
      </el-table>
      <pagination v-show="total > 0" :total="total" v-model:page="query.pageNum" v-model:limit="query.pageSize" @pagination="load" />
    </el-card>

    <el-dialog v-model="importVisible" title="上传数字酋长eBay订单文件" width="560px" append-to-body>
      <el-upload ref="uploadRef" drag accept=".xlsx,.xls" :auto-upload="false" :limit="1" :on-change="onFile" :on-remove="onRemove">
        <el-icon class="el-icon--upload"><UploadFilled /></el-icon>
        <div class="el-upload__text">拖入文件，或<em>点击选择</em></div>
        <template #tip><div class="el-upload__tip">支持“数字酋长-Order-YYYY-MM.xlsx”。按平台订单号＋付款日期增量覆盖，可安全重复上传。</div></template>
      </el-upload>
      <template #footer><el-button @click="importVisible=false">取消</el-button><el-button type="primary" :loading="importing" @click="submitImport">导入并分析</el-button></template>
    </el-dialog>
  </div>
</template>

<script setup name="EbaySkuAnalysis">
import { computed, getCurrentInstance, nextTick, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import * as echarts from 'echarts'
import { getEbaySkuAnalysisDates, getEbaySkuAnalysisSummary, importEbaySkuAnalysis } from '@/api/operations/ebay/skuAnalysis'

const { proxy } = getCurrentInstance()
const chartRef = ref(); const uploadRef = ref(); const loading = ref(false); const importing = ref(false); const importVisible = ref(false)
const rows = ref([]); const chartRows = ref([]); const paymentRange = ref([]); const dateBounds = ref({}); const sites = ref([]); const total = ref(0); const file = ref()
const summary = ref({}); const chartType = ref('horizontalBar'); let chart
const query = reactive({ startDate: undefined, endDate: undefined, sku: undefined, site: undefined, chartMetric: 'paid_amount', chartOrder: 'desc', pageNum: 1, pageSize: 50 })
const chartMetrics = [
  { label: '按已支付金额', value: 'paid_amount', money: true },
  { label: '按已售出', value: 'sold_quantity' },
  { label: '按已支付订单数', value: 'paid_order_count' },
  { label: '按客单价', value: 'average_order_value', money: true },
  { label: '按买家数', value: 'buyer_count' },
  { label: '按退货数', value: 'refund_count' },
  { label: '按同期退款金额', value: 'refund_amount', money: true },
  { label: '按退货率', value: 'return_rate', percent: true },
  { label: '按运费', value: 'shipping_amount', money: true }
]
const cards = computed(() => [
  { label: '已支付金额', value: money(summary.value.paid_amount) }, { label: '已售数量', value: number(summary.value.sold_quantity) },
  { label: '已支付订单', value: number(summary.value.paid_order_count) }, { label: 'SKU数', value: number(summary.value.sku_count) },
  { label: '买家数', value: number(summary.value.buyer_count) }
])
function money(value) { return `¥${Number(value || 0).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}` }
function number(value) { return Number(value || 0).toLocaleString('zh-CN') }
function percentage(value) { return value === null || value === undefined ? '--' : `${(Number(value) * 100).toFixed(2)}%` }
function disabledPaymentDate(date) {
  const min = dateBounds.value.min_date ? new Date(`${dateBounds.value.min_date}T00:00:00`).getTime() : undefined
  const max = dateBounds.value.max_date ? new Date(`${dateBounds.value.max_date}T23:59:59`).getTime() : undefined
  const value = date.getTime()
  return (min !== undefined && value < min) || (max !== undefined && value > max)
}
async function init() {
  const response = await getEbaySkuAnalysisDates(); dateBounds.value = response.data || {}
  if (dateBounds.value.min_date) {
    paymentRange.value = [dateBounds.value.min_date, dateBounds.value.max_date]
    query.startDate = paymentRange.value[0]; query.endDate = paymentRange.value[1]
  }
  await load()
}
async function load() {
  loading.value = true
  try {
    const response = await getEbaySkuAnalysisSummary(query); const data = response.data || {}
    rows.value = data.items || []; chartRows.value = data.chart || []; summary.value = data.summary || {}; total.value = data.pagination?.total || 0
    sites.value = data.sites || sites.value
    await nextTick(); render()
  } finally { loading.value = false }
}
function render() {
  if (!chartRef.value) return
  chart ||= echarts.init(chartRef.value)
  const metric = chartMetrics.find(item => item.value === query.chartMetric) || chartMetrics[0]
  const categories = chartRows.value.map(item => item.inventory_sku)
  const values = chartRows.value.map(item => Number(item[metric.value] || 0))
  const valueLabel = value => metric.percent ? percentage(value) : `${metric.money ? '¥' : ''}${Number(value).toLocaleString('zh-CN')}`
  const common = {
    grid: { left: chartType.value === 'horizontalBar' ? 150 : 70, right: 28, top: 28, bottom: chartType.value === 'horizontalBar' ? 35 : 100 },
    tooltip: { trigger: 'axis', valueFormatter: valueLabel },
    series: [{ name: metric.label.replace('按', ''), type: chartType.value === 'line' ? 'line' : 'bar', smooth: chartType.value === 'line',
      barMaxWidth: 30, data: values, itemStyle: { color: '#409eff', borderRadius: chartType.value === 'line' ? 0 : [4, 4, 0, 0] } }]
  }
  if (chartType.value === 'horizontalBar') {
    common.xAxis = { type: 'value', axisLabel: { formatter: valueLabel } }
    common.yAxis = { type: 'category', inverse: true, data: categories, axisLabel: { width: 125, overflow: 'truncate' } }
    common.series[0].itemStyle.borderRadius = [0, 4, 4, 0]
  } else {
    common.xAxis = { type: 'category', data: categories, axisLabel: { rotate: 35, interval: 0 } }
    common.yAxis = { type: 'value', axisLabel: { formatter: valueLabel } }
  }
  chart.clear(); chart.setOption(common, true)
}
function handleChartQueryChange() { load() }
function changeChartType(type) { chartType.value = type; render() }
function search() { query.pageNum = 1; load() }
function handleDateChange(value) { query.startDate=value?.[0]; query.endDate=value?.[1]; search() }
function reset() { query.sku=undefined; query.site=undefined; query.pageNum=1; paymentRange.value=[dateBounds.value.min_date,dateBounds.value.max_date]; query.startDate=paymentRange.value[0]; query.endDate=paymentRange.value[1]; load() }
function openImport() { file.value=undefined; uploadRef.value?.clearFiles(); importVisible.value=true }
function onFile(uploadFile) { file.value=uploadFile.raw }
function onRemove() { file.value=undefined }
async function submitImport() {
  if (!file.value) return proxy.$modal.msgError('请选择Excel文件')
  importing.value=true
  try { const response=await importEbaySkuAnalysis(file.value); proxy.$modal.msgSuccess(`导入完成：有效${response.data?.valid_rows || 0}行`); importVisible.value=false; await init() }
  finally { importing.value=false }
}
onMounted(() => { init(); window.addEventListener('resize', () => chart?.resize()) })
onBeforeUnmount(() => chart?.dispose())
</script>

<style scoped>
.sku-analysis{background:#f5f7fa;min-height:calc(100vh - 84px)}.filter-card,.chart-card,.table-card{border:0;border-radius:10px;margin-bottom:14px}.filter-card :deep(.el-card__body){padding-bottom:2px}.range-separator{margin:0 8px;color:#909399}.summary-grid{display:grid;grid-template-columns:repeat(5,1fr);gap:12px;margin-bottom:14px}.summary-card{background:#fff;border-radius:10px;padding:16px 20px;border-left:4px solid #409eff}.summary-card span{display:block;color:#909399;font-size:13px}.summary-card strong{display:block;margin-top:8px;font-size:22px;color:#303133}.card-title{display:flex;align-items:center;justify-content:space-between;font-weight:600}.card-title small{font-weight:400;color:#909399}.chart-title{gap:16px}.chart-controls{display:flex;align-items:center;gap:8px}.chart-switch :deep(.el-button){width:34px;height:32px;padding:0;color:#a8abb2;background:#fff}.chart-switch :deep(.el-button svg){width:18px;height:18px;fill:currentColor}.chart-switch :deep(.el-button.active){position:relative;z-index:1;color:#ff7a00;border-color:#ffad66;background:#fff7ed}.chart-switch :deep(.el-button:hover){color:#ff7a00;border-color:#ffc58f}.chart{height:500px}.sku-image{width:52px;height:52px;border-radius:6px}.no-image{color:#c0c4cc;font-size:12px}@media(max-width:1000px){.summary-grid{grid-template-columns:repeat(2,1fr)}}
</style>
