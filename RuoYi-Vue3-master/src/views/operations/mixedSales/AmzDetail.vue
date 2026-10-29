<template>
  <div class="detail-panel" v-loading="loading">
    <div class="detail-title">{{ sku }} · 店铺明细</div>
    <el-table :data="rows" border size="small" @sort-change="sortChanged" empty-text="暂无店铺明细">
      <el-table-column prop="storeName" label="Amazon店铺" min-width="180" sortable="custom" show-overflow-tooltip>
        <template #default="{ row }">{{ row.storeName || (row.sid ? `未匹配店铺（${row.sid}）` : '--') }}</template>
      </el-table-column>
      <el-table-column prop="site" label="站点" width="100"><template #default="{ row }">{{ row.site || '--' }}</template></el-table-column>
      <inventory-age-column platform="amz" />
      <el-table-column v-for="col in metrics" :key="col.key" :prop="col.key" :label="col.label"
        align="right" min-width="145" sortable="custom">
        <template #header>
          <el-tooltip v-if="col.key === 'ebaySales30d'" content="同一SKU、同一站点的eBay总销量，供各Amazon店铺对比，不应将重复展示值相加。" placement="top">
            <span>{{ col.label }}</span>
          </el-tooltip>
          <span v-else>{{ col.label }}</span>
        </template>
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
    <el-button v-if="failed" link type="primary" @click="load">重试明细查询</el-button>
  </div>
</template>

<script setup>
import InventoryAgeColumn from './InventoryAgeColumn.vue'
import { onBeforeUnmount, reactive, ref, watch } from 'vue'
import { listAmzMixedSalesDetails } from '@/api/operations/mixedSales'
import { quantity, price } from './format'

const props = defineProps({ sku: { type: String, required: true }, sid: Number, calculationVersion: String })
const metrics = [
  { key: 'fbaStock', label: 'FBA在库' }, { key: 'fbaInbound', label: 'FBA在途' },
  { key: 'fbaTotalInventory', label: 'FBA总库存' },
  { key: 'amzSales30d', label: '本店近30天销量' }, { key: 'ebaySales30d', label: 'eBay站点近30天销量' }
]
const priceColumns = [
  { key: 'amzMinPrice', label: '本店最低价' }, { key: 'amzMaxPrice', label: '本店最高价' },
  { key: 'ebayMinPrice', label: 'eBay最低价' }, { key: 'ebayMaxPrice', label: 'eBay最高价' }
]
const loading = ref(false)
const failed = ref(false)
const rows = ref([])
const total = ref(0)
const query = reactive({ pageNum: 1, pageSize: 20, sortField: 'fbaTotalInventory', sortOrder: 'desc' })
let requestId = 0
async function load() {
  const id = ++requestId
  loading.value = true
  failed.value = false
  try {
    const response = await listAmzMixedSalesDetails({ ...query, sku: props.sku, sid: props.sid, calculationVersion: props.calculationVersion })
    if (id !== requestId) return
    rows.value = response.data?.items || []
    total.value = Number(response.data?.total || 0)
  } catch (error) { if (id === requestId) failed.value = true }
  finally {
    if (id === requestId) loading.value = false
  }
}
function sortChanged({ prop, order }) {
  query.sortField = prop || 'fbaTotalInventory'
  query.sortOrder = order || 'desc'
  query.pageNum = 1
  load()
}
function search() { query.pageNum = 1; load() }
watch(() => [props.sku, props.sid, props.calculationVersion], () => {
  search()
}, { immediate: true })
onBeforeUnmount(() => { requestId += 1 })
</script>

<style scoped>
.detail-panel { padding: 14px 24px; background: var(--el-fill-color-lighter); }
.detail-title { margin-bottom: 12px; font-weight: 600; }
</style>
