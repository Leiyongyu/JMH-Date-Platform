<template>
  <div class="app-container amz-replenishment-page">
    <el-form :model="queryParams" ref="queryRef" :inline="true" v-show="showSearch" label-width="82px">
      <el-form-item label="店铺" prop="storeName">
        <el-input
          v-model="queryParams.storeName"
          placeholder="请输入店铺"
          clearable
          style="width: 200px"
          @keyup.enter="handleQuery"
        />
      </el-form-item>
      <el-form-item label="Seller SKU" prop="sellerSku">
        <el-input
          v-model="queryParams.sellerSku"
          placeholder="请输入Seller SKU"
          clearable
          style="width: 220px"
          @keyup.enter="handleQuery"
        />
      </el-form-item>
      <el-form-item label="仓库SKU" prop="warehouseSku">
        <el-input
          v-model="queryParams.warehouseSku"
          placeholder="请输入仓库SKU"
          clearable
          style="width: 220px"
          @keyup.enter="handleQuery"
        />
      </el-form-item>
      <el-form-item label="ASIN" prop="asin">
        <el-input
          v-model="queryParams.asin"
          placeholder="请输入ASIN"
          clearable
          style="width: 170px"
          @keyup.enter="handleQuery"
        />
      </el-form-item>
      <el-form-item label="负责人" prop="principalName">
        <el-input
          v-model="queryParams.principalName"
          placeholder="请输入负责人"
          clearable
          style="width: 180px"
          @keyup.enter="handleQuery"
        />
      </el-form-item>
      <el-form-item label="产品分类" prop="productCategory">
        <el-input
          v-model="queryParams.productCategory"
          placeholder="请输入分类"
          clearable
          style="width: 180px"
          @keyup.enter="handleQuery"
        />
      </el-form-item>
      <el-form-item>
        <el-button type="primary" icon="Search" @click="handleQuery">搜索</el-button>
        <el-button icon="Refresh" @click="resetQuery">重置</el-button>
      </el-form-item>
    </el-form>

    <el-row :gutter="10" class="mb8">
      <el-col :span="1.5">
        <el-button type="warning" plain icon="Download" @click="handleExport"
          v-hasPermi="['operations:amzReplenishment:export']">导出</el-button>
      </el-col>
      <right-toolbar
        v-model:showSearch="showSearch"
        :show-column-config="true"
        @queryTable="handleRefresh"
        @columnConfig="openColumnConfig"
      ></right-toolbar>
    </el-row>

    <el-table
      v-if="columnConfigLoaded"
      :key="columnTableKey"
      v-loading="loading"
      :data="replenishmentList"
      border stripe height="640"
      :row-key="(row) => (row.sid||'') + '|' + (row.sellerSku||'') + '|' + (row.warehouseSku||'')"
      @selection-change="handleSelectionChange"
      @sort-change="handleSortChange"
    >
      <el-table-column type="selection" width="45" fixed />
      <template v-for="col in visibleColumns" :key="col.key">
        <el-table-column
          v-if="col.format === 'percentNumber'"
          :label="col.label"
          :align="col.align"
          :prop="col.key"
          :width="col.width"
          sortable="custom"
        >
          <template #default="scope">{{ formatPercentNumber(scope.row[col.key]) }}</template>
        </el-table-column>
        <el-table-column
          v-else-if="col.format === 'number'"
          :label="col.label"
          :align="col.align"
          :prop="col.key"
          :width="col.width"
          sortable="custom"
        >
          <template #default="scope">
            <span :class="{ 'negative-value': Number(scope.row[col.key]) < 0 }">{{ formatNumber(scope.row[col.key]) }}</span>
          </template>
        </el-table-column>
        <el-table-column
          v-else-if="col.format === 'time'"
          :label="col.label"
          :align="col.align"
          :prop="col.key"
          :width="col.width"
        >
          <template #default="scope">
            <span>{{ parseTime(scope.row[col.key]) }}</span>
          </template>
        </el-table-column>
        <!-- 产品分类：内联编辑 -->
        <el-table-column
          v-else-if="col.format === 'productCategory'"
          :label="col.label" :align="col.align" :width="col.width"
        >
          <template #default="scope">
            <el-input v-model="editCache[amzKey(scope.row,'cat')]" size="small" placeholder="分类" clearable style="width:110px"
              @blur="onAmzCellBlur(scope.row,'cat')" @keyup.enter="onAmzCellBlur(scope.row,'cat')" @clear="onAmzCellClear(scope.row,'cat')" />
          </template>
        </el-table-column>
        <!-- 已采购数量：内联编辑 -->
        <el-table-column
          v-else-if="col.format === 'purchasedQty'"
          :label="col.label" :align="col.align" :width="col.width" sortable="custom"
        >
          <template #default="scope">
            <el-input v-model="editCache[amzKey(scope.row,'pqty')]" size="small" placeholder="数量" clearable style="width:100px"
              @blur="onAmzCellBlur(scope.row,'pqty')" @keyup.enter="onAmzCellBlur(scope.row,'pqty')" @clear="onAmzCellClear(scope.row,'pqty')" />
          </template>
        </el-table-column>
        <el-table-column
          v-else
          :label="col.label"
          :align="col.align"
          :prop="col.key"
          :width="col.width"
          :fixed="col.fixed || false"
          :sortable="col.sortable ? 'custom' : false"
          :show-overflow-tooltip="col.tooltip"
        />
      </template>
    </el-table>

    <pagination
      v-show="total > 0"
      :total="total"
      v-model:page="queryParams.pageNum"
      v-model:limit="queryParams.pageSize"
      @pagination="getList"
    />

    <column-config-drawer
      v-model="showColumnDrawer"
      :columns="columnDefs"
      :fixed-keys="fixedColumnKeys"
      :visible-keys="visibleKeys"
      @apply="handleColumnApply"
    />
  </div>
</template>

<script setup name="AmzReplenishment">
import { listAmzReplenishment, refreshAmzReplenishment } from '@/api/operations/amz/replenishment'
import request from '@/utils/request'
import ColumnConfigDrawer from '@/components/ColumnConfigDrawer/index.vue'
import { useColumnConfig } from '@/composables/useColumnConfig'

const router = useRouter()
const { proxy } = getCurrentInstance()

const loading = ref(false)
const showSearch = ref(true)
const total = ref(0)
const replenishmentList = ref([])
const checkedRows = ref([])
const editCache = reactive({})
function amzKey(row, field) { return (row.sid || '') + '|' + (row.sellerSku || '') + '_' + field }
function initAmzEditCache() {
  for (const row of replenishmentList.value) {
    const cat = amzKey(row, 'cat'); if (!(cat in editCache)) editCache[cat] = row.productCategory ?? ''
    const pq = amzKey(row, 'pqty'); if (!(pq in editCache)) editCache[pq] = row.purchasedQty ?? ''
  }
}
watch(replenishmentList, initAmzEditCache, { flush: 'post' })
async function onAmzCellBlur(row, field) {
  const k = amzKey(row, field)
  const v = editCache[k] || ''; const oldV = field === 'cat' ? (row.productCategory ?? '') : String(row.purchasedQty ?? '')
  if (v === oldV || row._saving) return; row._saving = true
  try {
    const body = { sid: String(row.sid || ''), sellerSku: row.sellerSku }
    if (field === 'cat') body.productCategory = v || ''
    else body.manualPurchasedQty = v || null
    await request({ url: '/operations/amz/replenishment/override', method: 'post', data: body })
    if (field === 'cat') row.productCategory = v || ''
    else row.purchasedQty = v || ''
  } catch { editCache[k] = oldV } finally { row._saving = false }
}
function onAmzCellClear(row, field) { editCache[amzKey(row, field)] = ''; onAmzCellBlur(row, field) }

const fixedColumnKeys = ['storeName', 'sellerSku']
const columnDefs = [
  { key: 'storeName', label: '店铺', align: 'left', width: 160, fixed: true, sortable: true, tooltip: true },
  { key: 'sellerSku', label: 'Seller SKU', align: 'left', width: 180, fixed: true, sortable: true, tooltip: true },
  { key: 'warehouseSku', label: '仓库SKU', align: 'left', width: 170, sortable: true, tooltip: true },
  { key: 'warehouseName', label: '仓库', align: 'left', width: 170, tooltip: true },
  { key: 'asin', label: 'ASIN', align: 'center', width: 130, sortable: true, tooltip: true },
  { key: 'principalName', label: '负责人', align: 'center', width: 120, tooltip: true },
  { key: 'productCategory', label: '产品分类', align: 'center', width: 130, format: 'productCategory' },
  { key: 'rating', label: '评分', align: 'right', width: 80, sortable: true },
  { key: 'reviewCount', label: '评论数', align: 'right', width: 100, sortable: true },
  { key: 'adRate', label: '广告费率', align: 'right', width: 105, sortable: true, format: 'percentNumber' },
  { key: 'profitRate30d', label: '30天利润率', align: 'right', width: 120, sortable: true, format: 'percentNumber' },
  { key: 'refundRate90d', label: '90天退款率', align: 'right', width: 120, sortable: true, format: 'percentNumber' },
  { key: 'purchasedQty', label: '已采购数量', align: 'right', width: 120, sortable: true, format: 'purchasedQty' },
  { key: 'domesticStock', label: '国内仓库存', align: 'right', width: 120, sortable: true },
  { key: 'pendingShipQty', label: '待出库', align: 'right', width: 95, sortable: true },
  { key: 'fbaStock', label: 'FBA在库', align: 'right', width: 105, sortable: true },
  { key: 'fbaInbound', label: 'FBA在途', align: 'right', width: 105, sortable: true },
  { key: 'totalInventory', label: '总库存', align: 'right', width: 105, sortable: true },
  { key: 'sales7d', label: '7天销量', align: 'right', width: 95, sortable: true },
  { key: 'sales14d', label: '14天销量', align: 'right', width: 100, sortable: true },
  { key: 'sales30d', label: '30天销量', align: 'right', width: 100, sortable: true },
  { key: 'sales60d', label: '60天销量', align: 'right', width: 100, sortable: true },
  { key: 'salesSpeed14d', label: '14日均销', align: 'right', width: 105, sortable: true },
  { key: 'salesSpeed30d', label: '30日均销', align: 'right', width: 105, sortable: true },
  { key: 'salesSpeed60d', label: '60日均销', align: 'right', width: 105, sortable: true },
  { key: 'avgMonthlySales', label: '平均月销量', align: 'right', width: 120, sortable: true },
  { key: 'safetyStock', label: '安全库存', align: 'right', width: 110, sortable: true },
  { key: 'shipQty', label: '发货量', align: 'right', width: 100, sortable: true, format: 'number' },
  { key: 'replenishQty', label: '补货量', align: 'right', width: 100, sortable: true, format: 'number' },
  { key: 'restockDays', label: '补货时间', align: 'right', width: 105, sortable: true },
  { key: 'calcTime', label: '计算时间', align: 'center', width: 170, format: 'time' }
]
const {
  showColumnDrawer,
  columnConfigLoaded,
  columnTableKey,
  visibleKeys,
  visibleColumns,
  exportColumns,
  openColumnConfig,
  initColumnConfig,
  applyColumnConfig
} = useColumnConfig('operations:amz:replenishment', columnDefs, fixedColumnKeys)
const data = reactive({
  queryParams: {
    pageNum: 1,
    pageSize: 50,
    storeName: undefined,
    sellerSku: undefined,
    warehouseSku: undefined,
    asin: undefined,
    principalName: undefined,
    productCategory: undefined,
    sortField: undefined,
    sortOrder: undefined
  }
})

const { queryParams } = toRefs(data)

function getList() {
  loading.value = true
  listAmzReplenishment(queryParams.value).then(response => {
    replenishmentList.value = response.rows || []
    total.value = response.total || 0
  }).finally(() => {
    loading.value = false
  })
}

async function handleRefresh() {
  if (loading.value) return
  loading.value = true
  try { await refreshAmzReplenishment(); await getList() }
  finally { loading.value = false }
}

function handleQuery() {
  queryParams.value.pageNum = 1
  getList()
}

function resetQuery() {
  proxy.resetForm('queryRef')
  queryParams.value.sortField = undefined
  queryParams.value.sortOrder = undefined
  handleQuery()
}

function handleSortChange({ prop, order }) {
  queryParams.value.sortField = order ? prop : undefined
  queryParams.value.sortOrder = order || undefined
  queryParams.value.pageNum = 1
  getList()
}

function handleSelectionChange(rows) { checkedRows.value = rows }

async function handleColumnApply(keys) {
  await applyColumnConfig(keys)
  proxy.$modal.msgSuccess('列配置已保存')
}

function handleExport() {
  const sel = checkedRows.value.length > 0
  const body = { scope: sel ? 'SELECTED' : 'FILTERED',
    rowKeys: sel ? checkedRows.value.map(r => (r.sid||'') + '|' + (r.sellerSku||'') + '|' + (r.warehouseSku||'')) : undefined,
    columns: exportColumns.value }
  if (!sel) {
    body.filters = []
    const p = queryParams.value
    if (p.storeName) body.filters.push({ field: 'storeName', value: p.storeName })
    if (p.sellerSku) body.filters.push({ field: 'sellerSku', value: p.sellerSku })
    if (p.warehouseSku) body.filters.push({ field: 'warehouseSku', value: p.warehouseSku })
    if (p.asin) body.filters.push({ field: 'asin', value: p.asin })
    if (p.principalName) body.filters.push({ field: 'principalName', value: p.principalName })
    if (p.productCategory) body.filters.push({ field: 'productCategory', value: p.productCategory })
    if (p.sortField) { body.sortField = p.sortField; body.sortOrder = p.sortOrder || 'descending' }
  }
  request({ url: 'operations/amz/replenishment/export', method: 'post', data: body, responseType: 'blob' }).then(res => {
    const blob = new Blob([res]); const a = document.createElement('a'); a.href = URL.createObjectURL(blob)
    a.download = `amz_replenishment_${new Date().getTime()}.xlsx`; a.click()
  })
}

function formatPercentNumber(value) {
  if (value === null || value === undefined || value === '') return '-'
  const num = Number(value)
  return Number.isFinite(num) ? `${num.toFixed(1)}%` : '-'
}

function formatNumber(value) {
  if (value === null || value === undefined || value === '') return '-'
  const num = Number(value)
  return Number.isFinite(num) ? num.toFixed(2).replace(/\.?0+$/, '') : '-'
}

async function initPage() {
  await initColumnConfig()
  getList()
}

initPage()
</script>

<style scoped>
.amz-replenishment-page { background: #f5f7fa; }

.negative-value {
  color: #f56c6c;
  font-weight: 600;
}

:deep(.el-table .cell) {
  white-space: nowrap;
}
</style>
