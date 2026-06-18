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
      <right-toolbar v-model:showSearch="showSearch" @queryTable="getList"></right-toolbar>
    </el-row>

    <el-table
      v-loading="loading"
      :data="replenishmentList"
      border stripe height="640"
      :row-key="(row) => (row.sid||'') + '|' + (row.sellerSku||'') + '|' + (row.warehouseSku||'')"
      @selection-change="handleSelectionChange"
      @sort-change="handleSortChange"
    >
      <el-table-column type="selection" width="45" fixed />
      <el-table-column label="店铺" align="left" prop="storeName" width="160" fixed sortable="custom" :show-overflow-tooltip="true" />
      <el-table-column label="Seller SKU" align="left" prop="sellerSku" width="180" fixed sortable="custom" :show-overflow-tooltip="true" />
      <el-table-column label="仓库SKU" align="left" prop="warehouseSku" width="170" sortable="custom" :show-overflow-tooltip="true" />
      <el-table-column label="仓库" align="left" prop="warehouseName" width="170" :show-overflow-tooltip="true" />
      <el-table-column label="ASIN" align="center" prop="asin" width="130" sortable="custom" :show-overflow-tooltip="true" />
      <el-table-column label="负责人" align="center" prop="principalName" width="120" :show-overflow-tooltip="true" />
      <el-table-column label="产品分类" align="center" prop="productCategory" width="130" :show-overflow-tooltip="true" />
      <el-table-column label="评分" align="right" prop="rating" width="80" sortable="custom" />
      <el-table-column label="评论数" align="right" prop="reviewCount" width="100" sortable="custom" />
      <el-table-column label="广告费率" align="right" prop="adRate" width="105" sortable="custom">
        <template #default="scope">{{ formatPercentNumber(scope.row.adRate) }}</template>
      </el-table-column>
      <el-table-column label="30天利润率" align="right" prop="profitRate30d" width="120" sortable="custom">
        <template #default="scope">{{ formatPercentNumber(scope.row.profitRate30d) }}</template>
      </el-table-column>
      <el-table-column label="90天退款率" align="right" prop="refundRate90d" width="120" sortable="custom">
        <template #default="scope">{{ formatPercentNumber(scope.row.refundRate90d) }}</template>
      </el-table-column>
      <el-table-column label="已采购数量" align="right" prop="purchasedQty" width="120" sortable="custom" />
      <el-table-column label="国内仓库存" align="right" prop="domesticStock" width="120" sortable="custom" />
      <el-table-column label="待出库" align="right" prop="pendingShipQty" width="95" sortable="custom" />
      <el-table-column label="FBA在库" align="right" prop="fbaStock" width="105" sortable="custom" />
      <el-table-column label="FBA在途" align="right" prop="fbaInbound" width="105" sortable="custom" />
      <el-table-column label="总库存" align="right" prop="totalInventory" width="105" sortable="custom" />
      <el-table-column label="7天销量" align="right" prop="sales7d" width="95" sortable="custom" />
      <el-table-column label="14天销量" align="right" prop="sales14d" width="100" sortable="custom" />
      <el-table-column label="30天销量" align="right" prop="sales30d" width="100" sortable="custom" />
      <el-table-column label="60天销量" align="right" prop="sales60d" width="100" sortable="custom" />
      <el-table-column label="14日均销" align="right" prop="salesSpeed14d" width="105" sortable="custom" />
      <el-table-column label="30日均销" align="right" prop="salesSpeed30d" width="105" sortable="custom" />
      <el-table-column label="60日均销" align="right" prop="salesSpeed60d" width="105" sortable="custom" />
      <el-table-column label="平均月销量" align="right" prop="avgMonthlySales" width="120" sortable="custom" />
      <el-table-column label="安全库存" align="right" prop="safetyStock" width="110" sortable="custom" />
      <el-table-column label="发货量" align="right" prop="shipQty" width="100" sortable="custom">
        <template #default="scope">
          <span :class="{ 'negative-value': Number(scope.row.shipQty) < 0 }">{{ formatNumber(scope.row.shipQty) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="补货量" align="right" prop="replenishQty" width="100" sortable="custom">
        <template #default="scope">
          <span :class="{ 'negative-value': Number(scope.row.replenishQty) < 0 }">{{ formatNumber(scope.row.replenishQty) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="补货时间" align="right" prop="restockDays" width="105" sortable="custom" />
      <el-table-column label="计算时间" align="center" prop="calcTime" width="170">
        <template #default="scope">
          <span>{{ parseTime(scope.row.calcTime) }}</span>
        </template>
      </el-table-column>
    </el-table>

    <pagination
      v-show="total > 0"
      :total="total"
      v-model:page="queryParams.pageNum"
      v-model:limit="queryParams.pageSize"
      @pagination="getList"
    />
  </div>
</template>

<script setup name="AmzReplenishment">
import { listAmzReplenishment } from '@/api/operations/amz/replenishment'

const router = useRouter()
const { proxy } = getCurrentInstance()

const loading = ref(false)
const showSearch = ref(true)
const total = ref(0)
const replenishmentList = ref([])
const checkedRows = ref([])
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

function handleExport() {
  const sel = checkedRows.value.length > 0
  const body = { scope: sel ? 'SELECTED' : 'FILTERED',
    rowKeys: sel ? checkedRows.value.map(r => (r.sid||'') + '|' + (r.sellerSku||'') + '|' + (r.warehouseSku||'')) : undefined }
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

getList()
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
