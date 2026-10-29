<template>
  <div class="app-container mixed-sales-page">
    <el-form v-show="showSearch" :inline="true" :model="query" @submit.prevent="search">
      <el-form-item label="仓库SKU">
        <el-input v-model="query.sku" clearable placeholder="完整SKU或关键词" style="width: 220px" @keyup.enter="search" />
      </el-form-item>
      <el-form-item label="商品名称">
        <el-input v-model="query.productName" clearable placeholder="请输入商品名称" style="width: 210px" @keyup.enter="search" />
      </el-form-item>
      <el-form-item label="店铺">
        <el-select v-model="query.sid" clearable filterable placeholder="全部Amazon店铺" style="width: 220px">
          <el-option v-for="store in stores" :key="store.sid" :value="Number(store.sid)"
            :label="store.storeName || `SID ${store.sid}`" />
        </el-select>
      </el-form-item>
      <el-form-item label="库龄">
        <el-tooltip content="按每个店铺的最高库龄区间筛选SKU；任一店铺符合即显示，选择店铺后只核对该店铺。展开保留全部明细供核对。" placement="top">
          <el-select v-model="query.ageBucket" clearable placeholder="全部库龄" style="width: 170px">
            <el-option v-for="(label, index) in ['0–90天', '91–180天', '181–270天', '271–365天', '365天以上']"
              :key="index" :label="label" :value="index + 1" />
          </el-select>
        </el-tooltip>
      </el-form-item>
      <el-form-item>
        <el-button type="primary" icon="Search" @click="search">搜索</el-button>
        <el-button icon="Refresh" @click="reset">重置</el-button>
      </el-form-item>
    </el-form>
    <el-row class="mb8 toolbar">
      <span class="table-note">仅展示 Amazon 和 eBay 都存在的 SKU，展开查看店铺库存及售价对比</span>
      <right-toolbar v-model:showSearch="showSearch" @queryTable="refresh" refresh-tooltip="读取已同步的库存和销量" />
    </el-row>
    <el-table :key="tableVersion" v-loading="loading" :data="rows" row-key="sku" border stripe
      :default-sort="{ prop: query.sortField, order: ['asc', 'ascending'].includes(query.sortOrder) ? 'ascending' : 'descending' }" @sort-change="sortChanged">
      <el-table-column type="expand" width="48">
        <template #default="{ row }">
          <amz-detail :sku="row.sku" :sid="appliedSid" :calculation-version="calculationVersion" />
        </template>
      </el-table-column>
      <el-table-column label="商品图片" width="90" align="center">
        <template #default="{ row }">
          <el-image v-if="row.imageUrl" :src="row.imageUrl" :preview-src-list="[row.imageUrl]" preview-teleported
            fit="contain" style="height: 46px; width: 58px" />
          <span v-else>--</span>
        </template>
      </el-table-column>
      <el-table-column label="仓库SKU" prop="sku" min-width="200" show-overflow-tooltip sortable="custom" />
      <el-table-column label="商品名称" prop="productName" min-width="240" show-overflow-tooltip>
        <template #default="{ row }">{{ row.productName || '--' }}</template>
      </el-table-column>
      <el-table-column label="仓库" prop="warehouseNames" min-width="180" show-overflow-tooltip>
        <template #default="{ row }">{{ row.warehouseNames || '--' }}</template>
      </el-table-column>
      <el-table-column label="店铺数" prop="storeCount" width="85" align="right"><template #default="{ row }">{{ quantity(row.storeCount) }}</template></el-table-column>
      <el-table-column label="MSKU数" prop="listingCount" width="90" align="right"><template #default="{ row }">{{ quantity(row.listingCount) }}</template></el-table-column>
      <el-table-column v-for="col in metrics" :key="col.key" :prop="col.key" :label="col.label"
        min-width="135" align="right" sortable="custom">
        <template #header>
          <el-tooltip :content="col.tip" placement="top"><span>{{ col.label }}</span></el-tooltip>
        </template>
        <template #default="{ row }">
          <strong v-if="col.key === 'fbaTotalInventory'">{{ quantity(row[col.key]) }}</strong>
          <span v-else>{{ quantity(row[col.key]) }}</span>
          <div v-if="col.matchKey && matchHint(row[col.matchKey], row.listingCount)" class="match-hint">
            {{ matchHint(row[col.matchKey], row.listingCount) }}
          </div>
        </template>
      </el-table-column>
      <el-table-column label="库存同步时间" prop="inventorySyncTime" width="166">
        <template #default="{ row }">{{ parseTime(row.inventorySyncTime) || '--' }}</template>
      </el-table-column>
      <el-table-column label="销量同步时间" prop="salesSyncTime" width="166">
        <template #default="{ row }">{{ parseTime(row.salesSyncTime) || '--' }}</template>
      </el-table-column>
    </el-table>
    <pagination v-if="total > 0" :total="total" v-model:page="query.pageNum" v-model:limit="query.pageSize" @pagination="load" />
  </div>
</template>

<script setup name="AmzMixedSalesPanel">
import { onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { getAmzMixedSalesStores, listAmzMixedSales } from '@/api/operations/mixedSales'
import AmzDetail from './AmzDetail.vue'
import { matchHint, quantity } from './format'

const showSearch = ref(true)
const loading = ref(false)
const rows = ref([])
const stores = ref([])
const total = ref(0)
const tableVersion = ref(0)
const appliedSid = ref(undefined)
const calculationVersion = ref('')
const query = reactive({ sku: '', productName: '', sid: undefined, ageBucket: undefined, pageNum: 1, pageSize: 50,
  sortField: 'fbaTotalInventory', sortOrder: 'desc' })
const metrics = [
  { key: 'fbaStock', label: 'FBA在库', tip: '产品表现库存中的FBA在库：可售＋待调仓＋入库中＋预留。' },
  { key: 'fbaInbound', label: 'FBA在途', tip: '产品表现库存中的已发出FBA在途。' },
  { key: 'fbaTotalInventory', label: 'FBA总库存', matchKey: 'inventoryMatchedCount', tip: 'FBA在库＋FBA在途；按店铺和MSKU匹配后，汇总同一完整仓库SKU。缺少源记录显示--，部分匹配显示已匹配数量。' },
  { key: 'sales30d', label: '30天销量', matchKey: 'salesMatchedCount', tip: '复用领星补货建议表的sales_30d，按店铺＋MSKU取最大值后汇总到完整仓库SKU；时间窗口由现有上游同步决定。' }
]
let requestId = 0
async function load(latest = false) {
  const id = ++requestId
  const params = { ...query, ageBucket: query.ageBucket || undefined, calculationVersion: latest === true ? undefined : calculationVersion.value || undefined }
  loading.value = true
  try {
    const response = await listAmzMixedSales(params)
    if (id !== requestId) return
    rows.value = response.data?.items || []
    total.value = Number(response.data?.total || 0)
    appliedSid.value = params.sid
    calculationVersion.value = response.data?.calculationVersion || ''
    tableVersion.value += 1
  } finally {
    if (id === requestId) loading.value = false
  }
}
function search() { query.pageNum = 1; load() }
function refresh() { query.pageNum = 1; load(true) }
function reset() { query.sku = ''; query.productName = ''; query.sid = undefined; query.ageBucket = undefined; search() }
function sortChanged({ prop, order }) { query.sortField = prop || 'fbaTotalInventory'; query.sortOrder = order || 'desc'; search() }
onMounted(async () => {
  await Promise.all([load(), getAmzMixedSalesStores().then(response => { stores.value = response.data || [] })])
})
onBeforeUnmount(() => { requestId += 1 })
</script>

<style scoped>
.toolbar { align-items: center; justify-content: space-between; }
.table-note, .match-hint { color: var(--el-text-color-secondary); font-size: 12px; }
.match-hint { margin-top: 4px; }
</style>
