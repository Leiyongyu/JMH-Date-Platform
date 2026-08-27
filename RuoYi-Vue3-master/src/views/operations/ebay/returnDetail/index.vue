<template>
  <div class="app-container return-detail-page">
    <el-card shadow="never" class="filter-card">
      <el-form :model="filters" inline>
        <el-form-item><el-select v-model="filters.account" placeholder="所有账号" clearable style="width:135px"><el-option label="所有账号" value="all" /><el-option label="Aplus-Shop" value="Aplus-Shop" /><el-option label="moses-motorsports" value="moses-motorsports" /><el-option label="vehicle-faster-boost" value="vehicle-faster-boost" /></el-select></el-form-item>
        <el-form-item><el-select v-model="filters.site" placeholder="所有站点" clearable style="width:125px"><el-option v-for="site in sites" :key="site" :label="site" :value="site" /></el-select></el-form-item>
        <el-form-item><el-input v-model="filters.sku" placeholder="SKU" clearable style="width:145px" /></el-form-item>
        <el-form-item><el-input v-model="filters.listingId" placeholder="Listing ID" clearable style="width:145px" /></el-form-item>
        <el-form-item><el-input v-model="filters.orderNo" placeholder="订单号" clearable style="width:165px" /></el-form-item>
        <el-form-item><el-button type="primary" icon="Search" @click="search">搜索</el-button><el-button icon="Refresh" @click="reset">重置</el-button></el-form-item>
        <el-form-item class="date-filter"><el-select v-model="filters.timeType" style="width:120px"><el-option label="按退款时间" value="refund" /><el-option label="按付款时间" value="payment" /></el-select><el-date-picker v-model="filters.dateRange" type="daterange" value-format="YYYY-MM-DD" range-separator="至" start-placeholder="开始日期" end-placeholder="结束日期" :clearable="false" style="width:250px" /></el-form-item>
      </el-form>
    </el-card>

    <div class="summary-row">
      <div><span>退款订单</span><strong>{{ filteredRows.length }}</strong></div>
      <div><span>退货数量</span><strong>{{ totalRefundCount }}</strong></div>
      <div><span>退款金额</span><strong>{{ money(totalRefundAmount) }}</strong></div>
      <div><span>涉及站点</span><strong>{{ siteCount }}</strong></div>
    </div>

    <el-card shadow="never" class="table-card">
      <template #header><div class="card-title"><div><b>退货明细</b><small>当前为静态演示数据，后续接入真实退款数据源</small></div><el-button icon="Download">导出</el-button></div></template>
      <el-table :data="pagedRows" stripe height="620">
        <el-table-column label="订单号 / 店铺 / 站点" min-width="220" fixed>
          <template #default="scope"><div class="order-cell"><b>{{ scope.row.orderNo }}</b><span>{{ scope.row.account }}</span><span>{{ scope.row.site }}</span></div></template>
        </el-table-column>
        <el-table-column label="商品" min-width="260">
          <template #default="scope"><div class="product-cell"><span class="product-thumb">{{ scope.row.sku.slice(0,3) }}</span><div><b>{{ scope.row.sku }}</b><a href="javascript:void(0)">{{ scope.row.listingId }} ↗</a></div></div></template>
        </el-table-column>
        <el-table-column prop="refundCount" label="退货数" width="105" align="right" />
        <el-table-column prop="reason" label="退款原因" min-width="210"><template #default="scope"><el-tag v-if="scope.row.reason !== '--'" effect="plain" type="warning">{{ scope.row.reason }}</el-tag><span v-else>--</span></template></el-table-column>
        <el-table-column label="退款金额" width="135" align="right"><template #default="scope"><b class="amount">{{ money(scope.row.refundAmount) }}</b></template></el-table-column>
        <el-table-column prop="refundTime" label="退款时间" width="180" sortable />
        <el-table-column label="状态" width="105" align="center"><template #default><el-tag type="success" effect="light">已退款</el-tag></template></el-table-column>
      </el-table>
      <pagination v-show="filteredRows.length > 0" :total="filteredRows.length" v-model:page="pageNum" v-model:limit="pageSize" />
    </el-card>
  </div>
</template>

<script setup name="EbayReturnDetail">
import { computed, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'

const sites = ['eBay德国站', 'eBay英国站', 'eBay美国站', 'eBay意大利站']
const filters = reactive({ account: 'all', site: undefined, sku: '', listingId: '', orderNo: '', timeType: 'refund', dateRange: ['2026-08-20', '2026-08-26'] })
const pageNum = ref(1); const pageSize = ref(20)
const rows = [
  { orderNo:'23-15033-30068',account:'moses-motorsports',site:'eBay德国站',sku:'RNG-80001-0042',listingId:'157741645003',refundCount:1,reason:'与商品描述不符',refundAmount:137.15,refundTime:'2026-08-26 03:38:04' },
  { orderNo:'24-15033-92793',account:'vehicle-faster-boost',site:'eBay汽车站',sku:'MCD-20046-0200',listingId:'355587107720',refundCount:1,reason:'--',refundAmount:1110.62,refundTime:'2026-08-25 19:18:05' },
  { orderNo:'21-15007-61005',account:'Automobile-Planet',site:'eBay英国站',sku:'DAS-10623-0772',listingId:'406989241464',refundCount:1,reason:"Doesn't fit my vehicle",refundAmount:1473.84,refundTime:'2026-08-25 15:34:57' },
  { orderNo:'07-15045-88104',account:'moses-motorsports',site:'eBay德国站',sku:'MCD-20251-0293',listingId:'157835163404',refundCount:1,reason:'--',refundAmount:125.37,refundTime:'2026-08-25 11:15:24' },
  { orderNo:'03-15074-56437',account:'Aplus-Shop',site:'eBay德国站',sku:'PSA-60257-1158',listingId:'236959853260',refundCount:1,reason:'与商品描述不符',refundAmount:95.01,refundTime:'2026-08-25 08:54:47' },
  { orderNo:'02-15063-38626',account:'Aplus-Shop',site:'eBay美国站',sku:'PSA-60003-0003',listingId:'405771283004',refundCount:2,reason:'Arrived damaged',refundAmount:684.50,refundTime:'2026-08-24 22:13:08' },
  { orderNo:'19-15062-50741',account:'vehicle-faster-boost',site:'eBay英国站',sku:'BMW-30388-0557',listingId:'156337950117',refundCount:1,reason:'Changed mind',refundAmount:963.95,refundTime:'2026-08-24 17:45:32' },
  { orderNo:'11-15012-92044',account:'moses-motorsports',site:'eBay意大利站',sku:'MCD-20049-0101',listingId:'356117439822',refundCount:1,reason:'Ordered by mistake',refundAmount:1258.68,refundTime:'2026-08-23 14:22:10' },
  { orderNo:'18-15008-44139',account:'Aplus-Shop',site:'eBay德国站',sku:'RNG-80100-0443',listingId:'235914780731',refundCount:1,reason:'Wrong item sent',refundAmount:877.11,refundTime:'2026-08-22 12:06:43' },
  { orderNo:'06-15026-31577',account:'Automobile-Planet',site:'eBay美国站',sku:'TYT-90050-0159',listingId:'404738210066',refundCount:1,reason:"Doesn't work or defective",refundAmount:721.36,refundTime:'2026-08-21 09:37:26' }
]
const filteredRows = computed(()=>rows.filter(row=>(filters.account==='all'||!filters.account||row.account===filters.account)&&(!filters.site||row.site===filters.site)&&(!filters.sku||row.sku.includes(filters.sku.trim().toUpperCase()))&&(!filters.listingId||row.listingId.includes(filters.listingId.trim()))&&(!filters.orderNo||row.orderNo.includes(filters.orderNo.trim()))))
const pagedRows = computed(()=>filteredRows.value.slice((pageNum.value-1)*pageSize.value,pageNum.value*pageSize.value))
const totalRefundCount = computed(()=>filteredRows.value.reduce((sum,row)=>sum+row.refundCount,0))
const totalRefundAmount = computed(()=>filteredRows.value.reduce((sum,row)=>sum+row.refundAmount,0))
const siteCount = computed(()=>new Set(filteredRows.value.map(row=>row.site)).size)
const money = value=>`¥${Number(value||0).toLocaleString('zh-CN',{minimumFractionDigits:2,maximumFractionDigits:2})}`
function search(){ pageNum.value=1; ElMessage.success('演示数据筛选完成') }
function reset(){ Object.assign(filters,{account:'all',site:undefined,sku:'',listingId:'',orderNo:'',timeType:'refund',dateRange:['2026-08-20','2026-08-26']}); pageNum.value=1 }
</script>

<style scoped>
.return-detail-page{min-height:calc(100vh - 84px);background:#f4f6f9}.filter-card,.table-card{border:0;border-radius:10px;margin-bottom:14px}.filter-card :deep(.el-card__body){padding:14px 16px 2px}.date-filter{float:right}.summary-row{display:grid;grid-template-columns:repeat(4,1fr);gap:14px;margin-bottom:14px}.summary-row>div{background:#fff;border-radius:10px;padding:15px 20px;border-left:4px solid #409eff}.summary-row span{display:block;color:#909399;font-size:13px}.summary-row strong{display:block;margin-top:7px;font-size:22px;color:#303133}.card-title{display:flex;align-items:center;justify-content:space-between}.card-title>div{display:flex;align-items:baseline;gap:12px}.card-title small{color:#909399;font-weight:400}.order-cell,.product-cell>div{display:flex;flex-direction:column;gap:4px}.order-cell span{color:#909399;font-size:12px}.product-cell{display:flex;align-items:center;gap:12px}.product-cell a{color:#909399;font-size:12px;text-decoration:underline}.product-thumb{display:flex;align-items:center;justify-content:center;width:50px;height:50px;border-radius:8px;background:linear-gradient(145deg,#eef6ff,#d8eaff);color:#409eff;font-size:12px;font-weight:700}.amount{font-weight:500;color:#303133}@media(max-width:1200px){.date-filter{float:none}.summary-row{grid-template-columns:repeat(2,1fr)}}
</style>
