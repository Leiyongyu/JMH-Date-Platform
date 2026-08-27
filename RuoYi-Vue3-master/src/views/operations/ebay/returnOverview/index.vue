<template>
  <div class="app-container return-overview-page">
    <el-card shadow="never" class="filter-card">
      <el-form :model="filters" inline>
        <el-form-item><el-select v-model="filters.site" placeholder="所有站点" clearable style="width:120px"><el-option v-for="site in sites" :key="site" :label="site" :value="site" /></el-select></el-form-item>
        <el-form-item><el-input v-model="filters.sku" placeholder="SKU" clearable style="width:150px" /></el-form-item>
        <el-form-item><el-button type="primary" icon="Search" @click="search">搜索</el-button><el-button icon="Refresh" @click="reset">重置</el-button></el-form-item>
        <el-form-item class="date-filter"><el-select v-model="filters.timeType" style="width:120px"><el-option label="按付款时间" value="payment" /><el-option label="按退款时间" value="refund" /></el-select><el-date-picker v-model="filters.dateRange" type="daterange" value-format="YYYY-MM-DD" range-separator="至" start-placeholder="开始日期" end-placeholder="结束日期" :clearable="false" style="width:250px" /></el-form-item>
      </el-form>
    </el-card>

    <div class="metrics-grid">
      <article v-for="item in metrics" :key="item.label" class="metric-card">
        <div class="metric-label">{{ item.label }} <el-tooltip :content="item.tip" placement="top"><el-icon><QuestionFilled /></el-icon></el-tooltip></div>
        <div class="metric-body"><div><strong>{{ item.value }}</strong><small :class="item.trend > 0 ? 'up' : 'down'">{{ item.trend > 0 ? '↑' : '↓' }} {{ Math.abs(item.trend) }}%</small></div><span class="metric-ring" :style="{ '--ring-color': item.color }"></span></div>
      </article>
    </div>

    <el-card shadow="never" class="panel trend-panel">
      <template #header><div class="panel-title"><span>退货统计趋势</span><el-tag type="info" effect="plain">演示数据</el-tag></div></template>
      <div ref="trendChartRef" class="trend-chart"></div>
    </el-card>

    <div class="two-column">
      <el-card shadow="never" class="panel region-panel">
        <template #header><div class="panel-title"><span>地域分布</span><small>按同期退款金额排序</small></div></template>
        <div ref="regionChartRef" class="region-chart"></div>
        <el-table :data="regionRows" size="small" stripe>
          <el-table-column prop="country" label="国家" min-width="110" />
          <el-table-column prop="refundCount" label="同期退货数" align="right" />
          <el-table-column prop="returnRate" label="同期退货率" align="right" />
          <el-table-column label="同期退款金额" align="right"><template #default="scope">{{ money(scope.row.refundAmount) }}</template></el-table-column>
          <el-table-column prop="refundRatio" label="退款金额占比" align="right" />
        </el-table>
      </el-card>

      <el-card shadow="never" class="panel reason-panel">
        <template #header><div class="panel-title"><span>退款原因分析</span><small>订单数及占比</small></div></template>
        <div class="reason-layout"><div ref="reasonChartRef" class="reason-chart"></div><el-table :data="reasonRows" size="small" max-height="360"><el-table-column prop="reason" label="退货原因" min-width="180" show-overflow-tooltip /><el-table-column prop="count" label="退款订单数" width="100" align="right" /><el-table-column prop="ratio" label="占比" width="85" align="right" /></el-table></div>
      </el-card>
    </div>

    <el-card shadow="never" class="panel listing-panel">
      <template #header><div class="panel-title"><span>Listing 概览</span><el-button icon="Download">导出</el-button></div></template>
      <el-table :data="listingRows" stripe>
        <el-table-column prop="sku" label="SKU / Listing ID" min-width="210"><template #default="scope"><b>{{ scope.row.sku }}</b><small class="sub-line">{{ scope.row.listingId }}</small></template></el-table-column>
        <el-table-column prop="refundCount" label="同期退货数" align="right" />
        <el-table-column label="同期退款金额" align="right"><template #default="scope">{{ money(scope.row.refundAmount) }}</template></el-table-column>
        <el-table-column label="已支付金额" align="right"><template #default="scope">{{ money(scope.row.paidAmount) }}</template></el-table-column>
        <el-table-column prop="soldQuantity" label="已售出" align="right" />
        <el-table-column prop="returnRate" label="同期退货率" align="right" />
        <el-table-column prop="refundRatio" label="退款金额占比" align="right" />
      </el-table>
    </el-card>
  </div>
</template>

<script setup name="EbayReturnOverview">
import { nextTick, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import * as echarts from 'echarts'

const sites = ['德国', '美国', '英国', '瑞典', '意大利']
const filters = reactive({ site: undefined, sku: '', timeType: 'payment', dateRange: ['2026-08-20', '2026-08-26'] })
const metrics = [
  { label: '同期退货数', value: '324', trend: -12.6, color: '#409eff', tip: '所选区间内发生退款的商品数量' },
  { label: '同期退款金额', value: '¥287,904.38', trend: -8.7, color: '#22c55e', tip: '所选区间内退款订单金额合计' },
  { label: '同期退货率', value: '5.63%', trend: -1.8, color: '#6366f1', tip: '同期退货数 ÷ 已售出数量' },
  { label: '同期退款金额占比', value: '14.43%', trend: 2.1, color: '#f59e0b', tip: '同期退款金额 ÷ 已支付金额' },
  { label: '已售出', value: '5,759', trend: 6.9, color: '#14b8a6', tip: '所选付款区间内商品购买数量' },
  { label: '已支付金额', value: '¥1,995,031.90', trend: 7.3, color: '#8b5cf6', tip: '所选付款区间内订单销售额' }
]
const regionRows = [
  { country: '🇩🇪 德国', refundCount: 116, returnRate: '6.17%', refundAmount: 107862.29, refundRatio: '15.05%' },
  { country: '🇺🇸 美国', refundCount: 72, returnRate: '4.80%', refundAmount: 73401.62, refundRatio: '12.51%' },
  { country: '🇬🇧 英国', refundCount: 88, returnRate: '5.92%', refundAmount: 63138.00, refundRatio: '13.23%' },
  { country: '🇸🇪 瑞典', refundCount: 16, returnRate: '3.40%', refundAmount: 24817.91, refundRatio: '11.02%' },
  { country: '🇮🇹 意大利', refundCount: 32, returnRate: '4.61%', refundAmount: 18684.56, refundRatio: '9.22%' }
]
const reasonRows = [
  { reason: "Doesn't fit", count: 67, ratio: '20.68%' }, { reason: 'Changed mind', count: 54, ratio: '16.67%' },
  { reason: "Doesn't fit my vehicle", count: 40, ratio: '12.35%' }, { reason: "Doesn't work or defective", count: 36, ratio: '11.11%' },
  { reason: 'Ordered by mistake', count: 20, ratio: '6.17%' }, { reason: '与商品描述不符', count: 18, ratio: '5.56%' },
  { reason: 'Arrived damaged', count: 15, ratio: '4.63%' }, { reason: '其他原因', count: 74, ratio: '22.83%' }
]
const listingRows = [
  { sku: 'PSA-60259-0557', listingId: '358580566039', refundCount: 14, refundAmount: 4490.93, paidAmount: 22254.41, soldQuantity: 42, returnRate: '33.33%', refundRatio: '20.18%' },
  { sku: 'MCD-20150-0001', listingId: '157741645003', refundCount: 9, refundAmount: 3353.04, paidAmount: 9368.90, soldQuantity: 76, returnRate: '11.84%', refundRatio: '35.79%' },
  { sku: 'BMW-30388-0557', listingId: '355587107720', refundCount: 7, refundAmount: 2639.52, paidAmount: 38387.49, soldQuantity: 36, returnRate: '19.44%', refundRatio: '6.88%' },
  { sku: 'DAS-10028-0021', listingId: '406989241464', refundCount: 5, refundAmount: 1975.38, paidAmount: 37428.87, soldQuantity: 40, returnRate: '12.50%', refundRatio: '5.28%' }
]
const trendChartRef = ref(); const regionChartRef = ref(); const reasonChartRef = ref()
let trendChart; let regionChart; let reasonChart
const money = value => `¥${Number(value || 0).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
function search() { ElMessage.success('演示页面：筛选条件已应用') }
function reset() { Object.assign(filters, { site: undefined, sku: '', timeType: 'payment', dateRange: ['2026-08-20', '2026-08-26'] }); ElMessage.success('已重置') }
function renderCharts() {
  trendChart ||= echarts.init(trendChartRef.value)
  const days = ['08-20','08-21','08-22','08-23','08-24','08-25','08-26']
  trendChart.setOption({ color:['#409eff','#22c55e','#f59e0b','#253b80','#8b5cf6','#14b8a6'], tooltip:{trigger:'axis'}, legend:{bottom:0}, grid:{left:60,right:64,top:32,bottom:54}, xAxis:{type:'category',data:days,boundaryGap:false}, yAxis:[{type:'value',splitLine:{lineStyle:{color:'#eef1f5'}}},{type:'value',axisLabel:{formatter:'{value}%'}}], series:[
    {name:'同期退货数',type:'line',smooth:true,data:[35,42,31,48,55,63,50]}, {name:'同期退货率',type:'line',smooth:true,yAxisIndex:1,data:[5.2,5.8,4.9,6.1,6.8,5.7,5.0]},
    {name:'同期退款金额',type:'line',smooth:true,data:[32000,41000,28500,49000,56800,46200,34400]}, {name:'退款金额占比',type:'line',smooth:true,yAxisIndex:1,data:[12.1,13.6,11.8,15.2,16.1,14.5,12.9]},
    {name:'已售出',type:'line',smooth:true,data:[690,755,710,860,940,1012,792]}, {name:'已支付金额',type:'line',smooth:true,data:[220000,250000,238000,310000,356000,341000,280000]}
  ]})
  regionChart ||= echarts.init(regionChartRef.value)
  regionChart.setOption({ tooltip:{trigger:'axis',axisPointer:{type:'shadow'}}, grid:{left:80,right:24,top:12,bottom:28}, xAxis:{type:'value',axisLabel:{formatter:v=>`${Math.round(v/1000)}k`},splitLine:{lineStyle:{color:'#eef1f5'}}}, yAxis:{type:'category',inverse:true,data:regionRows.map(i=>i.country)}, series:[{type:'bar',data:regionRows.map(i=>i.refundAmount),barWidth:18,itemStyle:{color:'#7cb5ec',borderRadius:[0,5,5,0]}}]})
  reasonChart ||= echarts.init(reasonChartRef.value)
  reasonChart.setOption({ tooltip:{trigger:'item',formatter:'{b}<br/>{c} 单 · {d}%'}, legend:{type:'scroll',bottom:0}, series:[{type:'pie',radius:['36%','68%'],center:['50%','44%'],label:{formatter:'{b}\n{d}%'},data:reasonRows.map(i=>({name:i.reason,value:i.count}))}]})
}
function resizeCharts() { trendChart?.resize(); regionChart?.resize(); reasonChart?.resize() }
onMounted(async()=>{ await nextTick(); renderCharts(); window.addEventListener('resize', resizeCharts) })
onBeforeUnmount(()=>{ window.removeEventListener('resize',resizeCharts); trendChart?.dispose(); regionChart?.dispose(); reasonChart?.dispose() })
</script>

<style scoped>
.return-overview-page{min-height:calc(100vh - 84px);background:#f4f6f9}.filter-card,.panel{border:0;border-radius:10px;margin-bottom:14px}.filter-card :deep(.el-card__body){padding:14px 16px 2px}.date-filter{float:right}.metrics-grid{display:grid;grid-template-columns:repeat(3,minmax(230px,1fr));gap:14px;margin-bottom:14px}.metric-card{background:#fff;border-radius:10px;padding:17px 20px;box-shadow:0 1px 3px rgba(15,23,42,.08)}.metric-label{display:flex;align-items:center;gap:5px;color:#606266;font-size:14px}.metric-body{display:flex;align-items:center;justify-content:space-between;margin-top:10px}.metric-body strong{font-size:25px;font-weight:500;color:#303133}.metric-body small{margin-left:10px;font-size:12px}.up{color:#ef4444}.down{color:#16a34a}.metric-ring{width:45px;height:45px;border-radius:50%;background:conic-gradient(var(--ring-color) 0 72%,#edf0f5 72%);position:relative}.metric-ring:after{content:'';position:absolute;inset:7px;border-radius:50%;background:#fff}.panel-title{display:flex;align-items:center;justify-content:space-between;font-weight:600}.panel-title small{font-weight:400;color:#909399}.trend-chart{height:360px}.two-column{display:grid;grid-template-columns:1fr 1fr;gap:14px}.region-chart{height:225px}.reason-layout{display:grid;grid-template-columns:46% 54%;align-items:center}.reason-chart{height:390px}.sub-line{display:block;color:#909399;margin-top:4px}.listing-panel{margin-bottom:0}@media(max-width:1200px){.date-filter{float:none}.metrics-grid{grid-template-columns:repeat(2,1fr)}.two-column{grid-template-columns:1fr}.reason-layout{grid-template-columns:1fr}}@media(max-width:700px){.metrics-grid{grid-template-columns:1fr}}
</style>
