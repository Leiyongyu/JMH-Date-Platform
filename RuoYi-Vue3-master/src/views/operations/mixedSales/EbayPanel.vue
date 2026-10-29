<template>
  <div class="app-container">
    <el-form v-show="showSearch" :inline="true" :model="query" @submit.prevent="search">
      <el-form-item label="产品SKU">
        <el-input v-model="query.sku" clearable placeholder="完整SKU或关键词" style="width: 220px" @keyup.enter="search" />
      </el-form-item>
      <el-form-item label="产品名称">
        <el-input v-model="query.productName" clearable placeholder="请输入产品名称" style="width: 210px" @keyup.enter="search" />
      </el-form-item>
      <el-form-item label="站点">
        <el-select v-model="query.site" clearable placeholder="全部站点" style="width: 160px">
          <el-option v-for="site in sites" :key="site" :value="site" :label="site" />
        </el-select>
      </el-form-item>
      <el-form-item label="库龄">
        <el-tooltip content="按SKU最大库龄筛选，选择站点后按该站点最大库龄筛选。未匹配库龄的数据不参与数值筛选。" placement="top">
          <el-select v-model="query.ageOperator" style="width: 110px">
            <el-option label="大于" value="gt" /><el-option label="大于等于" value="gte" />
            <el-option label="等于" value="eq" /><el-option label="小于等于" value="lte" />
            <el-option label="小于" value="lt" />
          </el-select>
        </el-tooltip>
        <el-input-number v-model="query.ageDays" :min="0" :max="2147483647" :precision="0"
          :controls="false" placeholder="不限" style="width: 115px; margin-left: 8px" @keyup.enter="search" />
        <span style="margin-left: 6px">天</span>
      </el-form-item>
      <el-form-item>
        <el-button type="primary" icon="Search" @click="search">搜索</el-button>
        <el-button icon="Refresh" @click="reset">重置</el-button>
      </el-form-item>
    </el-form>
    <el-row class="mb8 toolbar">
      <div class="table-note">仅展示 Amazon 和 eBay 都存在的 SKU，展开查看站点明细<span v-if="referenceDate"> · 计算基准日 {{ referenceDate }}</span></div>
      <right-toolbar v-model:showSearch="showSearch" @queryTable="refresh" refresh-tooltip="读取补货2.0最新计算结果" />
    </el-row>
    <el-table :key="tableVersion" v-loading="loading" :data="rows" row-key="sku" border stripe
      :default-sort="{ prop: query.sortField, order: ['asc', 'ascending'].includes(query.sortOrder) ? 'ascending' : 'descending' }"
      @sort-change="sortChanged">
      <el-table-column type="expand" width="48">
        <template #default="{ row }">
          <ebay-detail :filters="row.detailFilters" />
        </template>
      </el-table-column>
      <el-table-column prop="sku" label="产品SKU" min-width="210" sortable="custom" show-overflow-tooltip />
      <el-table-column prop="productName" label="产品名称" min-width="230" show-overflow-tooltip />
      <el-table-column prop="siteCount" label="站点数" width="85" align="right"><template #default="{ row }">{{ quantity(row.siteCount) }}</template></el-table-column>
      <inventory-age-column platform="ebay" />
      <el-table-column v-for="col in ebayMetrics" :key="col.key" :prop="col.key" :label="col.label"
        min-width="125" align="right" sortable="custom">
        <template #header>
          <el-tooltip :content="col.tip || '直接复用补货2.0的站点SKU库存值，按完整SKU汇总。'" placement="top"><span>{{ col.label }}</span></el-tooltip>
        </template>
        <template #default="{ row }">{{ quantity(row[col.key]) }}</template>
      </el-table-column>
    </el-table>
    <pagination v-if="total > 0" :total="total" v-model:page="query.pageNum" v-model:limit="query.pageSize" @pagination="load" />
  </div>
</template>

<script setup name="EbayMixedSalesPanel">
import InventoryAgeColumn from './InventoryAgeColumn.vue'
import { onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { listEbayMixedSales } from '@/api/operations/mixedSales'
import EbayDetail from './EbayDetail.vue'
import { quantity } from './format'
import { ebayDetailQuery, ebayMetrics } from './ebayMetrics'

const showSearch = ref(true)
const loading = ref(false)
const rows = ref([])
const sites = ref([])
const total = ref(0)
const tableVersion = ref(0)
const calculationVersion = ref('')
const referenceDate = ref('')
const query = reactive({ sku: '', productName: '', site: undefined, ageOperator: 'gt', ageDays: undefined, pageNum: 1, pageSize: 50,
  sortField: 'sales30d', sortOrder: 'desc' })
let requestId = 0
async function load(latest = false) {
  const id = ++requestId
  const params = { ...query, calculationVersion: latest === true ? undefined : calculationVersion.value || undefined }
  if (params.ageDays == null) { delete params.ageDays; delete params.ageOperator }
  loading.value = true
  try {
    const response = await listEbayMixedSales(params)
    if (id !== requestId) return
    const data = response.data || {}
    rows.value = (data.items || []).map(row => ({ ...row,
      detailFilters: ebayDetailQuery(row, params, data.calculationVersion) }))
    total.value = Number(data.total || 0)
    sites.value = data.sites || []
    calculationVersion.value = data.calculationVersion || ''
    referenceDate.value = data.referenceDate || ''
    tableVersion.value += 1
  } finally {
    if (id === requestId) loading.value = false
  }
}
function refresh() { query.pageNum = 1; load(true) }
function search() { query.pageNum = 1; load() }
function reset() { query.sku = ''; query.productName = ''; query.site = undefined; query.ageDays = undefined; query.ageOperator = 'gt'; search() }
function sortChanged({ prop, order }) { query.sortField = prop || 'sales30d'; query.sortOrder = order || 'desc'; search() }
onMounted(() => load())
onBeforeUnmount(() => { requestId += 1 })
</script>

<style scoped>
.toolbar { align-items: center; justify-content: space-between; }
.table-note { color: var(--el-text-color-secondary); font-size: 12px; }
</style>
