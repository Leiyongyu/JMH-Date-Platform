<template>
  <div class="app-container ebay-price-tracking-page">
    <el-form :model="queryParams" ref="queryRef" :inline="true" v-show="showSearch" label-width="72px">
      <el-form-item label="站点" prop="site">
        <el-select v-model="queryParams.site" placeholder="全部站点" clearable style="width: 160px">
          <el-option label="美国" value="美国" />
          <el-option label="英国" value="英国" />
          <el-option label="德国" value="德国" />
        </el-select>
      </el-form-item>
      <el-form-item label="SKU" prop="sku">
        <el-input v-model="queryParams.sku" placeholder="请输入SKU" clearable style="width: 220px" @keyup.enter="handleQuery" />
      </el-form-item>
      <el-form-item label="产品名称" prop="productName">
        <el-input v-model="queryParams.productName" placeholder="请输入产品名称" clearable style="width: 220px" @keyup.enter="handleQuery" />
      </el-form-item>
      <el-form-item label="品牌" prop="brandCode">
        <el-input v-model="queryParams.brandCode" placeholder="请输入品牌" clearable style="width: 180px" @keyup.enter="handleQuery" />
      </el-form-item>
      <el-form-item label="操作员" prop="operatorName">
        <el-input v-model="queryParams.operatorName" placeholder="请输入操作员" clearable style="width: 180px" @keyup.enter="handleQuery" />
      </el-form-item>
      <el-form-item>
        <el-button type="primary" icon="Search" @click="handleQuery">搜索</el-button>
        <el-button icon="Refresh" @click="resetQuery">重置</el-button>
      </el-form-item>
    </el-form>

    <el-row :gutter="10" class="mb8">
      <el-col :span="1.5">
        <el-dropdown @command="handleImport" v-hasPermi="['operations:ebayReplenishment:import']">
          <el-button type="info" plain icon="Upload">
            导入<el-icon class="el-icon--right"><arrow-down /></el-icon>
          </el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="lowestPrice">导入最低价</el-dropdown-item>
              <el-dropdown-item command="productPrice">导入商品单价</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
      </el-col>
      <el-col :span="1.5">
        <el-dropdown @command="handleExport" v-hasPermi="['operations:ebayReplenishment:export']">
          <el-button type="warning" plain icon="Download">导出<el-icon class="el-icon--right"><arrow-down /></el-icon></el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="filtered">导出筛选结果</el-dropdown-item>
              <el-dropdown-item command="selected">导出选中数据</el-dropdown-item>
              <el-dropdown-item command="all">导出全部数据</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
      </el-col>
      <el-col :span="1.5"><el-button icon="Setting" circle @click="openColDrawer" title="列设置" /></el-col>
      <right-toolbar v-model:showSearch="showSearch" @queryTable="handleRefresh"></right-toolbar>
    </el-row>

    <el-table v-loading="loading" :data="records" border stripe height="640" :row-key="(row) => row.site + '|' + row.sku" @selection-change="handleSelectionChange" @sort-change="handleSortChange">
      <el-table-column type="selection" width="45" fixed />
      <el-table-column label="站点" align="center" prop="site" v-if="colVisible('site')" width="90" fixed sortable="custom" />
      <el-table-column label="SKU" align="left" prop="sku" v-if="colVisible('sku')" width="170" fixed sortable="custom" :show-overflow-tooltip="true" />
      <el-table-column label="产品名称" align="left" prop="productName" v-if="colVisible('productName')" width="260" :show-overflow-tooltip="true" />
      <el-table-column label="等级" align="center" prop="skuLevel" v-if="colVisible('skuLevel')" width="80">
        <template #default="scope">
          <el-tag :type="levelTagType(scope.row.skuLevel)" effect="light">{{ scope.row.skuLevel || '-' }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="我方最低价" align="right" prop="ourLowestPrice" v-if="colVisible('ourLowestPrice')" width="110" sortable="custom">
        <template #default="scope">{{ scope.row.ourLowestPrice ?? '-' }}</template>
      </el-table-column>
      <el-table-column label="跟卖价" align="right" prop="trackingPrice" v-if="colVisible('trackingPrice')" width="110" sortable="custom">
        <template #default="scope">{{ scope.row.trackingPrice ?? '-' }}</template>
      </el-table-column>
      <el-table-column label="跟卖利润率" align="right" prop="trackingProfitMargin" v-if="colVisible('trackingProfitMargin')" width="130" sortable="custom">
        <template #default="scope">{{ formatPercent(scope.row.trackingProfitMargin) }}</template>
      </el-table-column>
      <el-table-column label="底线价" align="right" prop="floorPrice" v-if="colVisible('floorPrice')" width="100" sortable="custom">
        <template #default="scope">{{ scope.row.floorPrice ?? '-' }}</template>
      </el-table-column>
      <el-table-column label="退货率" align="right" prop="returnRate" v-if="colVisible('returnRate')" width="90" sortable="custom">
        <template #default="scope">{{ formatRate(scope.row.returnRate) }}</template>
      </el-table-column>
      <el-table-column label="近3天销量" align="right" prop="sales3d" v-if="colVisible('sales3d')" width="110" sortable="custom" />
      <el-table-column label="近7天销量" align="right" prop="sales7d" v-if="colVisible('sales7d')" width="110" sortable="custom" />
      <el-table-column label="近30天销量" align="right" prop="sales30d" v-if="colVisible('sales30d')" width="120" sortable="custom" />
      <el-table-column label="近90天销量" align="right" prop="sales90d" v-if="colVisible('sales90d')" width="120" sortable="custom" />
      <el-table-column label="历史最大月销" align="right" prop="maxMonthlySales" v-if="colVisible('maxMonthlySales')" width="140" sortable="custom" />
      <el-table-column label="OE号" align="center" prop="oeNumber" v-if="colVisible('oeNumber')" width="120" :show-overflow-tooltip="true" />
      <el-table-column label="售前链接" align="center" prop="presaleUrl" v-if="colVisible('presaleUrl')" width="70">
        <template #default="scope"><a v-if="scope.row.presaleUrl" :href="scope.row.presaleUrl" target="_blank" style="color:#409EFF">链接</a><span v-else>-</span></template>
      </el-table-column>
      <el-table-column label="售后链接" align="center" prop="soldUrl" v-if="colVisible('soldUrl')" width="70">
        <template #default="scope"><a v-if="scope.row.soldUrl" :href="scope.row.soldUrl" target="_blank" style="color:#409EFF">链接</a><span v-else>-</span></template>
      </el-table-column>
      <el-table-column label="海外仓库存" align="right" prop="overseasStock" v-if="colVisible('overseasStock')" width="120" sortable="custom" />
      <el-table-column label="海外仓库龄" align="right" prop="overseasStockAgeDays" v-if="colVisible('overseasStockAgeDays')" width="120" sortable="custom">
        <template #default="scope">{{ scope.row.overseasStockAgeDays != null ? scope.row.overseasStockAgeDays + '天' : '-' }}</template>
      </el-table-column>
      <el-table-column label="库销比" align="right" prop="stockSalesRatio" v-if="colVisible('stockSalesRatio')" width="100" sortable="custom">
        <template #default="scope">{{ scope.row.stockSalesRatio != null ? scope.row.stockSalesRatio + '%' : '-' }}</template>
      </el-table-column>
      <el-table-column label="预估补货量" align="right" prop="estimatedReplenishQty" v-if="colVisible('estimatedReplenishQty')" width="120" sortable="custom" />
      <el-table-column label="品牌" align="center" prop="brandCode" v-if="colVisible('brandCode')" width="90" :show-overflow-tooltip="true" />
      <el-table-column label="操作员" align="center" prop="operatorName" v-if="colVisible('operatorName')" width="100" :show-overflow-tooltip="true" />
      <el-table-column label="备注" align="left" prop="remark" v-if="colVisible('remark')" width="180" :show-overflow-tooltip="true" />
      <el-table-column label="计算时间" align="center" prop="calcTime" v-if="colVisible('calcTime')" width="170">
        <template #default="scope"><span>{{ parseTime(scope.row.calcTime) }}</span></template>
      </el-table-column>
    </el-table>

    <pagination v-show="total > 0" :total="total" v-model:page="queryParams.pageNum" v-model:limit="queryParams.pageSize" @pagination="getList" />
  </div>
<ColumnConfigDrawer :showDrawer="colShowDrawer" :leftCols="colLeftCols" :selectedColumns="colSelected" :isAllChecked="colIsAllChecked" :fixedKeys="colFixedKeys" :toggleAll="colToggleAll" :toggleColumn="colToggleColumn" :onDragStart="colOnDragStart" :onDragOver="colOnDragOver" :onDrop="colOnDrop" :onDragEnd="colOnDragEnd" @close="closeColDrawer(false)" @save="closeColDrawer(true)" />
</template>

<script setup name="EbayPriceTracking">
import { useColumnConfig } from '@/composables/useColumnConfig'
import ColumnConfigDrawer from '@/components/ColumnConfigDrawer/index.vue'
import { searchPriceTracking, refreshPriceTracking } from '@/api/operations/ebay/priceTracking'
import request from '@/utils/request'

const router = useRouter()
const { proxy } = getCurrentInstance()

const loading = ref(false)
const showSearch = ref(true)
const total = ref(0)
const records = ref([])
const checkedRows = ref([])
const data = reactive({
  queryParams: {
    pageNum: 1,
    pageSize: 50,
    site: undefined,
    sku: undefined,
    productName: undefined,
    brandCode: undefined,
    operatorName: undefined,
    sortField: undefined,
    sortOrder: undefined
  }
})
const { queryParams } = toRefs(data)

function getList() {
  loading.value = true
  const body = {
    pageNum: queryParams.value.pageNum,
    pageSize: queryParams.value.pageSize,
    sortField: queryParams.value.sortField || undefined,
    sortOrder: queryParams.value.sortOrder || undefined
  }
  const p = queryParams.value
  if (p.site) body.filters = body.filters || []
  // 用 filters 方式提交文本筛选
  const filters = []
  if (p.site) filters.push({ field: 'site', value: p.site })
  if (p.sku) filters.push({ field: 'sku', value: p.sku })
  if (p.productName) filters.push({ field: 'productName', value: p.productName })
  if (p.brandCode) filters.push({ field: 'brandCode', value: p.brandCode })
  if (p.operatorName) filters.push({ field: 'operatorName', value: p.operatorName })
  if (filters.length) body.filters = filters

  searchPriceTracking(body).then(response => {
    records.value = response.rows || []
    total.value = response.total || 0
  }).finally(() => { loading.value = false })
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

async function handleRefresh() {
  if (loading.value) return
  loading.value = true
  try { await refreshPriceTracking(); await getList(); proxy.$modal.msgSuccess('刷新完成') }
  catch { proxy.$modal.msgError('刷新失败') }
  finally { loading.value = false }
}

function handleImport(command) {
  const input = document.createElement('input')
  input.type = 'file'; input.accept = '.xlsx,.xls'
  input.onchange = async (e) => {
    const file = e.target.files[0]
    if (!file) return
    const form = new FormData(); form.append('file', file)
    const urlMap = { lowestPrice: 'import-lowest-price', productPrice: 'import-product-price' }
    const labelMap = { lowestPrice: '最低价', productPrice: '商品单价' }
    try {
      const res = await request({ url: `/operations/ebay/price-tracking/${urlMap[command]}`, method: 'post', data: form, headers: { 'Content-Type': 'multipart/form-data' } })
      proxy.$modal.msgSuccess(`导入${labelMap[command]}完成：成功${res.data?.successRows || 0}条`)
      getList()
    } catch (e) { proxy.$modal.msgError(`导入失败: ${e.message || e}`) }
  }
  input.click()
}

function handleSelectionChange(rows) { checkedRows.value = rows }

function handleExport(command) {
  if (command === 'selected' && checkedRows.value.length === 0) {
    proxy.$modal.msgWarning('请先选择要导出的数据'); return
  }
  const body = {
    scope: command === 'selected' ? 'SELECTED' : (command === 'all' ? 'ALL' : 'FILTERED'),
    rowKeys: command === 'selected' ? checkedRows.value.map(r => r.site + '|' + r.sku) : undefined
  }
  if (command !== 'all') {
    body.filters = []
    const p = queryParams.value
    if (p.site) body.filters.push({ field: 'site', value: p.site })
    if (p.sku) body.filters.push({ field: 'sku', value: p.sku })
    if (p.productName) body.filters.push({ field: 'productName', value: p.productName })
    if (p.brandCode) body.filters.push({ field: 'brandCode', value: p.brandCode })
    if (p.operatorName) body.filters.push({ field: 'operatorName', value: p.operatorName })
    if (p.sortField) { body.sortField = p.sortField; body.sortOrder = p.sortOrder || 'descending' }
  }
  request({ url: 'operations/ebay/price-tracking/export', method: 'post', data: body, responseType: 'blob' }).then(res => {
    const blob = new Blob([res]); const a = document.createElement('a'); a.href = URL.createObjectURL(blob)
    a.download = `ebay_price_tracking_${new Date().getTime()}.xlsx`; a.click()
  })
}

function formatPercent(value) {
  if (value === null || value === undefined || value === '') return '-'
  const num = Number(value)
  return Number.isFinite(num) ? `${(num * 100).toFixed(1)}%` : '-'
}

function formatRate(value) {
  if (value === null || value === undefined || value === '') return '-'
  const num = Number(value)
  return Number.isFinite(num) ? `${(num * 100).toFixed(1)}%` : '-'
}

function levelTagType(level) {
  const map = { A: 'success', B: 'primary', C: 'warning', D: 'info', E: 'danger' }
  return map[level] || 'info'
}

getList()
</script>

<style scoped>
.ebay-price-tracking-page { background: #f5f7fa; }
:deep(.el-table .cell) { white-space: nowrap; }
</style>
