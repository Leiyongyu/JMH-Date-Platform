<template>
  <div class="app-container return-overview-page">
    <el-card shadow="never" class="filter-card">
      <el-form :model="filters" inline>
        <el-form-item><el-select v-model="filters.site" placeholder="所有站点" clearable style="width:120px"><el-option v-for="site in sites" :key="site" :label="site" :value="site" /></el-select></el-form-item>
        <el-form-item><el-input v-model="filters.sku" placeholder="SKU" clearable style="width:150px" /></el-form-item>
        <el-form-item><el-button type="primary" icon="Search" @click="search">搜索</el-button><el-button icon="Refresh" @click="reset">重置</el-button></el-form-item>
        <el-form-item class="date-filter"><el-select v-model="filters.timeType" style="width:125px" @change="handleTimeTypeChange"><el-option label="按付款时间" value="payment" /><el-option label="按退款时间" value="refund" /></el-select><el-date-picker v-model="filters.dateRange" type="daterange" value-format="YYYY-MM-DD" range-separator="至" start-placeholder="开始日期" end-placeholder="结束日期" :clearable="false" :disabled-date="disabledDate" style="width:250px" @change="search" /></el-form-item>
      </el-form>
    </el-card>

    <div v-loading="loading" class="metrics-grid">
      <article v-for="item in metrics" :key="item.label" class="metric-card">
        <div class="metric-label">{{ item.label }} <el-tooltip :content="item.tip" placement="top"><el-icon><QuestionFilled /></el-icon></el-tooltip></div>
        <div class="metric-body"><div><strong>{{ item.value }}</strong><small :class="item.changeRate > 0 ? 'up' : item.changeRate < 0 ? 'down' : 'flat'" :title="comparisonTitle">{{ item.changeRate > 0 ? '↑' : item.changeRate < 0 ? '↓' : '→' }} {{ Math.abs(item.changeRate).toFixed(2) }}%</small></div><span class="metric-ring" :style="{ '--ring-color': item.color }"></span></div>
      </article>
    </div>

    <el-card shadow="never" class="panel trend-panel">
      <template #header><div class="panel-title"><span>退货统计趋势</span><small>按{{ timeDimensionLabel }}每日统计</small></div></template>
      <div ref="trendChartRef" class="trend-chart"></div>
    </el-card>

    <div class="two-column">
      <el-card shadow="never" class="panel region-panel">
        <template #header><div class="panel-title"><span>站点分布</span><small>按退款金额排序</small></div></template>
        <div ref="regionChartRef" class="region-chart"></div>
        <el-table :data="regionRows" size="small" stripe>
          <el-table-column prop="siteName" label="站点" min-width="90" />
          <el-table-column prop="refundCount" label="退货数" align="right" />
          <el-table-column prop="returnRate" label="退货率" align="right" />
          <el-table-column label="退款金额" min-width="120" align="right"><template #default="scope">{{ money(scope.row.refundAmount) }}</template></el-table-column>
          <el-table-column prop="refundRatio" label="退款金额占比" align="right" />
          <el-table-column label="已支付金额" min-width="120" align="right"><template #default="scope">{{ money(scope.row.paidAmount) }}</template></el-table-column>
          <el-table-column prop="soldQuantity" label="已售出" align="right" />
        </el-table>
      </el-card>

      <el-card shadow="never" class="panel reason-panel">
        <template #header><div class="panel-title"><span>退款原因分析</span><small>按人工售后小类统计</small></div></template>
        <div class="reason-layout">
          <div ref="reasonChartRef" class="reason-chart"></div>
          <div class="reason-table-wrap">
            <el-table :data="reasonRows" size="small" max-height="390" table-layout="fixed" style="width:100%">
              <el-table-column prop="reason" label="售后小类" min-width="170" show-overflow-tooltip />
              <el-table-column prop="count" label="退款订单数" width="110" align="right" header-align="right" />
              <el-table-column prop="ratio" label="占比" width="85" align="right" header-align="right" />
            </el-table>
          </div>
        </div>
      </el-card>
    </div>

    <el-card shadow="never" class="panel listing-panel">
      <template #header><div class="panel-title"><span>Listing 概览</span><small>共 {{ listingRows.length.toLocaleString('zh-CN') }} 条站点SKU，按退款金额降序</small></div></template>
      <el-table :data="pagedListingRows" stripe show-summary :summary-method="listingSummary" max-height="560">
        <el-table-column prop="siteName" label="站点" width="90" />
        <el-table-column prop="pictureUrl" label="图片" width="76" align="center">
          <template #default="scope"><el-image v-if="scope.row.pictureUrl" :src="scope.row.pictureUrl" fit="contain" lazy class="listing-image"><template #error><div class="image-placeholder">暂无</div></template></el-image><div v-else class="image-placeholder">暂无</div></template>
        </el-table-column>
        <el-table-column prop="sku" label="SKU" min-width="190">
          <template #default="scope"><el-link v-if="scope.row.listingUrl" type="primary" :underline="false" :href="scope.row.listingUrl" target="_blank">{{ scope.row.sku }}</el-link><span v-else>{{ scope.row.sku }}</span></template>
        </el-table-column>
        <el-table-column prop="returnCount" label="退货数" min-width="110" align="right" sortable />
        <el-table-column prop="refundAmount" label="退款金额" min-width="135" align="right" sortable><template #default="scope">{{ money(scope.row.refundAmount) }}</template></el-table-column>
        <el-table-column prop="paidAmount" label="已支付金额" min-width="140" align="right" sortable><template #default="scope">{{ money(scope.row.paidAmount) }}</template></el-table-column>
        <el-table-column prop="soldQuantity" label="已售出" min-width="105" align="right" sortable />
        <el-table-column prop="returnRateValue" label="退货率" min-width="115" align="right" sortable><template #default="scope">{{ percentage(scope.row.returnRateValue) }}</template></el-table-column>
        <el-table-column prop="refundRatioValue" label="退款金额占比" min-width="145" align="right" sortable><template #default="scope">{{ percentage(scope.row.refundRatioValue) }}</template></el-table-column>
      </el-table>
      <div class="listing-pagination"><el-pagination v-model:current-page="listingPage" v-model:page-size="listingPageSize" :page-sizes="[20,50,100]" layout="total, sizes, prev, pager, next, jumper" :total="listingRows.length" /></div>
    </el-card>
  </div>
</template>

<script setup name="EbayReturnOverview">
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import * as echarts from 'echarts'
import { getEbayReturnOverviewMetrics } from '@/api/operations/ebay/skuAnalysis'

const loading = ref(false)
const sites = ref([])
const filters = reactive({ site: undefined, sku: '', timeType: 'payment', dateRange: [] })
const dateBounds = ref({ min_date: '', max_date: '' })
const metricData = ref({})
const currentPeriod = ref({ start_date: '', end_date: '', days: 0 })
const previousPeriod = ref({ start_date: '', end_date: '', days: 0 })
const metricDefinitions = [
  { key: 'return_count', label: '退货数', format: 'number', color: '#409eff', tip: '所选日期维度下，已退款、已作废商品数量' },
  { key: 'refund_amount', label: '退款金额', format: 'money', color: '#22c55e', tip: '所选日期维度下，退款金额人民币合计' },
  { key: 'return_rate', label: '退货率', format: 'percentage', color: '#6366f1', tip: '所选日期维度下，退货数 ÷ 已售出数量' },
  { key: 'refund_amount_ratio', label: '退款金额占比', format: 'percentage', color: '#f59e0b', tip: '所选日期维度下，退款金额 ÷ 已支付金额' },
  { key: 'sold_quantity', label: '已售出', format: 'number', color: '#14b8a6', tip: '所选日期维度下，已支付订单商品数量' },
  { key: 'paid_amount', label: '已支付金额', format: 'money', color: '#8b5cf6', tip: '所选日期维度下，与SKU分析一致的已支付金额口径' }
]
const timeDimensionLabel = computed(() => filters.timeType === 'refund' ? '退款时间' : '付款时间')
const metrics = computed(() => metricDefinitions.map(definition => {
  const data = metricData.value[definition.key] || {}
  return {
    ...definition,
    tip: `${timeDimensionLabel.value}：${definition.tip}`,
    value: formatMetricValue(data.value, definition.format),
    changeRate: Number(data.change_rate || 0)
  }
}))
const comparisonTitle = computed(() => {
  if (!previousPeriod.value.start_date) return '暂无上期对比区间'
  return `对比上期：${previousPeriod.value.start_date} 至 ${previousPeriod.value.end_date}`
})
const regionRows = ref([])
const reasonRows = ref([])
const trendRows = ref([])
const listingRows = ref([])
const listingPage = ref(1)
const listingPageSize = ref(50)
const pagedListingRows = computed(() => {
  const start = (listingPage.value - 1) * listingPageSize.value
  return listingRows.value.slice(start, start + listingPageSize.value)
})
const trendChartRef = ref(); const regionChartRef = ref(); const reasonChartRef = ref()
let trendChart; let regionChart; let reasonChart
const money = value => `¥${Number(value || 0).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
const percentage = value => `${(Number(value || 0) * 100).toFixed(2)}%`
function formatMetricValue(value, format) {
  if (format === 'money') return money(value)
  if (format === 'percentage') return percentage(value)
  return Number(value || 0).toLocaleString('zh-CN', { maximumFractionDigits: 0 })
}
function disabledDate(date) {
  const min = dateBounds.value.min_date ? new Date(`${dateBounds.value.min_date}T00:00:00`).getTime() : undefined
  const max = dateBounds.value.max_date ? new Date(`${dateBounds.value.max_date}T23:59:59`).getTime() : undefined
  const value = date.getTime()
  return (min !== undefined && value < min) || (max !== undefined && value > max)
}
async function loadMetrics() {
  loading.value = true
  try {
    const response = await getEbayReturnOverviewMetrics({
      startDate: filters.dateRange?.[0],
      endDate: filters.dateRange?.[1],
      timeType: filters.timeType,
      site: filters.site,
      sku: filters.sku || undefined
    })
    const data = response.data || {}
    metricData.value = data.metrics || {}
    sites.value = data.sites || []
    dateBounds.value = data.date_bounds || {}
    currentPeriod.value = data.current_period || {}
    previousPeriod.value = data.previous_period || {}
    regionRows.value = (data.regions || []).map(item => ({
      siteName: item.site_name,
      refundCount: Number(item.return_count || 0).toLocaleString('zh-CN', { maximumFractionDigits: 0 }),
      returnRate: percentage(item.return_rate),
      refundAmount: Number(item.refund_amount || 0),
      refundRatio: percentage(item.refund_amount_ratio),
      paidAmount: Number(item.paid_amount || 0),
      soldQuantity: Number(item.sold_quantity || 0).toLocaleString('zh-CN', { maximumFractionDigits: 0 })
    }))
    reasonRows.value = (data.reasons || []).map(item => ({
      reason: item.small_category,
      count: Number(item.refund_order_count || 0),
      ratio: percentage(item.ratio)
    }))
    trendRows.value = (data.trend || []).map(item => ({
      date: item.stat_date,
      returnCount: Number(item.return_count || 0),
      refundAmount: Number(item.refund_amount || 0),
      returnRate: Number(item.return_rate || 0) * 100,
      refundRatio: Number(item.refund_amount_ratio || 0) * 100,
      soldQuantity: Number(item.sold_quantity || 0),
      paidAmount: Number(item.paid_amount || 0)
    }))
    listingRows.value = (data.listings || []).map(item => ({
      siteName: item.site_name || '其他',
      pictureUrl: item.picture_url || '',
      listingUrl: /^https?:\/\//i.test(item.listing_url || '') ? item.listing_url : '',
      sku: item.sku || '',
      returnCount: Number(item.return_count || 0),
      refundAmount: Number(item.refund_amount || 0),
      paidAmount: Number(item.paid_amount || 0),
      soldQuantity: Number(item.sold_quantity || 0),
      returnRateValue: Number(item.return_rate || 0),
      refundRatioValue: Number(item.refund_amount_ratio || 0)
    }))
    if (!filters.dateRange?.length && currentPeriod.value.start_date) {
      filters.dateRange = [currentPeriod.value.start_date, currentPeriod.value.end_date]
    }
    await nextTick()
    renderCharts()
  } finally {
    loading.value = false
  }
}
function search() { listingPage.value = 1; loadMetrics() }
function handleTimeTypeChange() {
  filters.dateRange = []
  listingPage.value = 1
  loadMetrics()
}
function reset() {
  filters.site = undefined
  filters.sku = ''
  filters.timeType = 'payment'
  filters.dateRange = []
  listingPage.value = 1
  loadMetrics()
}
function listingSummary({ columns }) {
  const values = metricData.value
  const summaries = {
    siteName: '合计',
    sku: `${listingRows.value.length.toLocaleString('zh-CN')} 条站点SKU`,
    returnCount: Number(values.return_count?.value || 0).toLocaleString('zh-CN', { maximumFractionDigits: 0 }),
    refundAmount: money(values.refund_amount?.value),
    paidAmount: money(values.paid_amount?.value),
    soldQuantity: Number(values.sold_quantity?.value || 0).toLocaleString('zh-CN', { maximumFractionDigits: 0 }),
    returnRateValue: percentage(values.return_rate?.value),
    refundRatioValue: percentage(values.refund_amount_ratio?.value)
  }
  return columns.map(column => summaries[column.property] ?? '')
}
function renderCharts() {
  trendChart ||= echarts.init(trendChartRef.value)
  trendChart.clear()
  const days = trendRows.value.map(item => item.date.slice(5))
  trendChart.setOption({ color:['#409eff','#22c55e','#f59e0b','#253b80','#8b5cf6','#14b8a6'], tooltip:{trigger:'axis',formatter:params=>{const row=trendRows.value[params[0]?.dataIndex];if(!row)return '';return [`<b>${row.date}</b>`,`退货数：${row.returnCount.toLocaleString('zh-CN')}`,`退货率：${row.returnRate.toFixed(2)}%`,`退款金额：${money(row.refundAmount)}`,`退款金额占比：${row.refundRatio.toFixed(2)}%`,`已售出：${row.soldQuantity.toLocaleString('zh-CN')}`,`已支付金额：${money(row.paidAmount)}`].join('<br/>')}}, legend:{bottom:0}, grid:{left:70,right:72,top:32,bottom:58}, xAxis:{type:'category',data:days,boundaryGap:false,axisLabel:{hideOverlap:true}}, yAxis:[{type:'value',splitLine:{lineStyle:{color:'#eef1f5'}},axisLabel:{formatter:value=>Number(value).toLocaleString('zh-CN')}},{type:'value',axisLabel:{formatter:'{value}%'}}], series:[
    {name:'退货数',type:'line',smooth:true,showSymbol:false,data:trendRows.value.map(item=>item.returnCount)}, {name:'退货率',type:'line',smooth:true,showSymbol:false,yAxisIndex:1,data:trendRows.value.map(item=>item.returnRate)},
    {name:'退款金额',type:'line',smooth:true,showSymbol:false,data:trendRows.value.map(item=>item.refundAmount)}, {name:'退款金额占比',type:'line',smooth:true,showSymbol:false,yAxisIndex:1,data:trendRows.value.map(item=>item.refundRatio)},
    {name:'已售出',type:'line',smooth:true,showSymbol:false,data:trendRows.value.map(item=>item.soldQuantity)}, {name:'已支付金额',type:'line',smooth:true,showSymbol:false,data:trendRows.value.map(item=>item.paidAmount)}
  ]})
  regionChart ||= echarts.init(regionChartRef.value)
  regionChart.clear()
  regionChart.setOption({ tooltip:{trigger:'axis',axisPointer:{type:'shadow'},valueFormatter:value=>money(value)}, grid:{left:80,right:24,top:12,bottom:28}, xAxis:{type:'value',axisLabel:{formatter:v=>`${Math.round(v/1000)}k`},splitLine:{lineStyle:{color:'#eef1f5'}}}, yAxis:{type:'category',inverse:true,data:regionRows.value.map(i=>i.siteName)}, series:[{name:'退款金额',type:'bar',data:regionRows.value.map(i=>i.refundAmount),barWidth:18,itemStyle:{color:'#7cb5ec',borderRadius:[0,5,5,0]}}]})
  reasonChart ||= echarts.init(reasonChartRef.value)
  reasonChart.clear()
  reasonChart.setOption({ tooltip:{trigger:'item',formatter:'{b}<br/>{c} 单 · {d}%'}, legend:{type:'scroll',bottom:0}, series:[{name:'售后小类',type:'pie',radius:['36%','68%'],center:['50%','44%'],label:{formatter:'{b}\n{d}%'},data:reasonRows.value.map(i=>({name:i.reason,value:i.count}))}]})
}
function resizeCharts() { trendChart?.resize(); regionChart?.resize(); reasonChart?.resize() }
onMounted(async()=>{ await loadMetrics(); window.addEventListener('resize', resizeCharts) })
onBeforeUnmount(()=>{ window.removeEventListener('resize',resizeCharts); trendChart?.dispose(); regionChart?.dispose(); reasonChart?.dispose() })
</script>

<style scoped>
.return-overview-page{min-height:calc(100vh - 84px);background:#f4f6f9}.filter-card,.panel{border:0;border-radius:10px;margin-bottom:14px}.filter-card :deep(.el-card__body){padding:14px 16px 2px}.date-filter{float:right}.metrics-grid{display:grid;grid-template-columns:repeat(3,minmax(230px,1fr));gap:14px;margin-bottom:14px}.metric-card{background:#fff;border-radius:10px;padding:17px 20px;box-shadow:0 1px 3px rgba(15,23,42,.08)}.metric-label{display:flex;align-items:center;gap:5px;color:#606266;font-size:14px}.metric-body{display:flex;align-items:center;justify-content:space-between;margin-top:10px}.metric-body strong{font-size:25px;font-weight:500;color:#303133}.metric-body small{margin-left:10px;font-size:12px}.up{color:#16a34a}.down{color:#ef4444}.flat{color:#909399}.metric-ring{width:45px;height:45px;border-radius:50%;background:conic-gradient(var(--ring-color) 0 72%,#edf0f5 72%);position:relative}.metric-ring:after{content:'';position:absolute;inset:7px;border-radius:50%;background:#fff}.panel-title{display:flex;align-items:center;justify-content:space-between;font-weight:600}.panel-title small{font-weight:400;color:#909399}.trend-chart{height:360px}.two-column{display:grid;grid-template-columns:1fr 1fr;gap:14px}.region-chart{height:225px}.reason-layout{display:grid;grid-template-columns:minmax(300px,44%) minmax(0,56%);gap:20px;align-items:start}.reason-chart{height:390px;min-width:0}.reason-table-wrap{min-width:0;padding-top:8px}.reason-table-wrap :deep(.el-table__header-wrapper th){height:44px}.reason-table-wrap :deep(.el-table__cell){padding:9px 0}.listing-panel{margin-bottom:0}.listing-image{width:52px;height:52px;border-radius:4px}.image-placeholder{display:flex;align-items:center;justify-content:center;width:52px;height:52px;border-radius:4px;background:#f5f7fa;color:#a8abb2;font-size:12px}.listing-pagination{display:flex;justify-content:flex-end;padding-top:16px}@media(max-width:1200px){.date-filter{float:none}.metrics-grid{grid-template-columns:repeat(2,1fr)}.two-column{grid-template-columns:1fr}.reason-layout{grid-template-columns:1fr}.reason-table-wrap{padding-top:0}}@media(max-width:700px){.metrics-grid{grid-template-columns:1fr}}
</style>
