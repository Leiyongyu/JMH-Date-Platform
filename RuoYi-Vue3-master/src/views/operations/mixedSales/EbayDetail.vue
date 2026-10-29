<template>
  <div class="detail-panel" v-loading="loading">
    <div class="detail-title">{{ filters.sku }} · 站点明细</div>
    <el-table :data="rows" border size="small" @sort-change="sortChanged" empty-text="暂无站点明细">
      <el-table-column prop="site" label="站点" width="100" />
      <el-table-column prop="sku" label="产品SKU" min-width="200" show-overflow-tooltip />
      <el-table-column prop="productName" label="产品名称" min-width="210" show-overflow-tooltip />
      <inventory-age-column platform="ebay" />
      <el-table-column v-for="col in ebaySiteMetrics" :key="col.key" :prop="col.key" :label="col.label"
        align="right" min-width="145" sortable="custom">
        <template #default="{ row }">{{ quantity(row[col.key]) }}</template>
      </el-table-column>
      <el-table-column prop="currency" label="币种" width="90"><template #default="{ row }">{{ row.currency || '--' }}</template></el-table-column>
      <el-table-column v-for="col in priceColumns" :key="col.key" :prop="col.key" :label="col.label"
        min-width="145" align="right" sortable="custom">
        <template #default="{ row }">{{ price(row[col.key]) }}</template>
      </el-table-column>
    </el-table>
    <pagination v-if="total > 0" :total="total" v-model:page="query.pageNum"
      v-model:limit="query.pageSize" @pagination="load" />
    <el-button v-if="failed" link type="primary" @click="load">重新加载明细</el-button>
  </div>
</template>

<script setup>
import InventoryAgeColumn from './InventoryAgeColumn.vue'
import { onBeforeUnmount, reactive, ref, watch } from 'vue'
import { listEbayMixedSalesDetails } from '@/api/operations/mixedSales'
import { quantity, price } from './format'
import { ebaySiteMetrics } from './ebayMetrics'

const props = defineProps({ filters: { type: Object, required: true } })
const priceColumns = [
  { key: 'ebayMinPrice', label: 'eBay最低价' }, { key: 'ebayMaxPrice', label: 'eBay最高价' },
  { key: 'amzMinPrice', label: 'Amazon最低价' }, { key: 'amzMaxPrice', label: 'Amazon最高价' }
]
const loading = ref(false)
const failed = ref(false)
const rows = ref([])
const total = ref(0)
const query = reactive({ pageNum: 1, pageSize: 20, sortField: 'sales30d', sortOrder: 'desc' })
let requestId = 0
async function load() {
  const id = ++requestId
  loading.value = true
  failed.value = false
  try {
    const response = await listEbayMixedSalesDetails({ ...props.filters, ...query })
    if (id !== requestId) return
    rows.value = response.data?.items || []
    total.value = Number(response.data?.total || 0)
  } catch (error) {
    if (id === requestId) failed.value = true
  } finally {
    if (id === requestId) loading.value = false
  }
}
function sortChanged({ prop, order }) {
  query.sortField = prop || 'sales30d'; query.sortOrder = order || 'desc'; query.pageNum = 1; load()
}
function search() { query.pageNum = 1; load() }
watch(() => props.filters, () => { search() }, { immediate: true })
onBeforeUnmount(() => { requestId += 1 })
</script>

<style scoped>
.detail-panel { padding: 14px 24px; background: var(--el-fill-color-lighter); }
.detail-title { margin-bottom: 12px; font-weight: 600; }
</style>
