<template>
  <div class="app-container ebay-replenishment-page">
    <el-form :model="queryParams" ref="queryRef" :inline="true" v-show="showSearch" label-width="72px">
      <el-form-item label="站点" prop="site">
        <el-select v-model="queryParams.site" placeholder="全部站点" clearable style="width: 160px">
          <el-option label="美国" value="美国" />
          <el-option label="英国" value="英国" />
          <el-option label="德国" value="德国" />
        </el-select>
      </el-form-item>
      <el-form-item label="SKU" prop="sku">
        <el-input
          v-model="queryParams.sku"
          placeholder="请输入SKU"
          clearable
          style="width: 220px"
          @keyup.enter="handleQuery"
        />
      </el-form-item>
      <el-form-item label="产品名称" prop="productName">
        <el-input
          v-model="queryParams.productName"
          placeholder="请输入产品名称"
          clearable
          style="width: 220px"
          @keyup.enter="handleQuery"
        />
      </el-form-item>
      <el-form-item label="等级" prop="skuLevel">
        <el-select v-model="queryParams.skuLevel" placeholder="全部等级" clearable style="width: 140px">
          <el-option label="A" value="A" />
          <el-option label="B" value="B" />
          <el-option label="C" value="C" />
          <el-option label="D" value="D" />
          <el-option label="E" value="E" />
        </el-select>
      </el-form-item>
      <el-form-item label="负责人" prop="ownerName">
        <el-input
          v-model="queryParams.ownerName"
          placeholder="请输入负责人"
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
        <el-dropdown @command="handleImport" v-hasPermi="['operations:ebayReplenishment:import']">
          <el-button type="info" plain icon="Upload">
            导入<el-icon class="el-icon--right"><arrow-down /></el-icon>
          </el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="sales">导入销量</el-dropdown-item>
              <el-dropdown-item command="profitRate">导入利润率</el-dropdown-item>
              <el-dropdown-item command="returnRate">导入退货率</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
      </el-col>
      <el-col :span="1.5">
        <el-button type="warning" plain icon="Download" @click="handleExport"
          v-hasPermi="['operations:ebayReplenishment:export']">导出</el-button>
      </el-col>
      <right-toolbar v-model:showSearch="showSearch" @queryTable="getList"></right-toolbar>
    </el-row>

    <el-table
      v-loading="loading"
      :data="replenishmentList"
      border stripe height="640"
      :row-key="(row) => row.site + '|' + row.sku"
      @selection-change="handleSelectionChange"
      @sort-change="handleSortChange"
    >
      <el-table-column type="selection" width="45" fixed />
      <el-table-column label="站点" align="center" prop="site" width="90" fixed sortable="custom" />
      <el-table-column label="SKU" align="left" prop="sku" width="170" fixed sortable="custom" :show-overflow-tooltip="true" />
      <el-table-column label="产品名称" align="left" prop="productName" width="260" :show-overflow-tooltip="true" />
      <el-table-column label="等级" align="center" prop="skuLevel" width="80" sortable="custom">
        <template #default="scope">
          <el-tag :type="levelTagType(scope.row.skuLevel)" effect="light">{{ scope.row.skuLevel || '-' }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="近30天利润" align="right" prop="profitRate30d" width="120" sortable="custom">
        <template #default="scope">{{ formatPercentNumber(scope.row.profitRate30d) }}</template>
      </el-table-column>
      <el-table-column label="退货率" align="right" prop="returnRate" width="100" sortable="custom">
        <template #default="scope">{{ formatRate(scope.row.returnRate) }}</template>
      </el-table-column>
      <el-table-column label="海外在途" align="right" prop="overseasOnway" width="105" sortable="custom" />
      <el-table-column label="海外可售" align="right" prop="overseasSellable" width="105" sortable="custom" />
      <el-table-column label="海外总库存" align="right" prop="overseasTotal" width="120" sortable="custom" />
      <el-table-column label="采购待交付" align="right" prop="purchasePendingDelivery" width="120" sortable="custom" />
      <el-table-column label="成都可售" align="right" prop="localSellable" width="105" sortable="custom" />
      <el-table-column label="成都在途" align="right" prop="localOnway" width="105" sortable="custom" />
      <el-table-column label="采购计划" align="right" prop="purchasePlanQty" width="105" sortable="custom" />
      <el-table-column label="待出库" align="right" prop="lockedQty" width="95" sortable="custom" />
      <el-table-column label="总库存" align="right" prop="totalInventory" width="105" sortable="custom" />
      <el-table-column label="近7天销量" align="right" prop="sales7d" width="110" sortable="custom" />
      <el-table-column label="近30天销量" align="right" prop="sales30d" width="120" sortable="custom" />
      <el-table-column label="近90天销量" align="right" prop="sales90d" width="120" sortable="custom" />
      <el-table-column label="历史最大月销" align="right" prop="maxMonthlySales" width="130" sortable="custom" />
      <el-table-column label="海外在库库销比" align="right" prop="overseasSellableSalesRatio" width="145" sortable="custom">
        <template #default="scope">{{ formatRatio(scope.row.overseasSellableSalesRatio) }}</template>
      </el-table-column>
      <el-table-column label="海外总库销比" align="right" prop="overseasTotalSalesRatio" width="135" sortable="custom">
        <template #default="scope">{{ formatRatio(scope.row.overseasTotalSalesRatio) }}</template>
      </el-table-column>
      <el-table-column label="总库存库销比" align="right" prop="totalInventorySalesRatio" width="135" sortable="custom">
        <template #default="scope">{{ formatRatio(scope.row.totalInventorySalesRatio) }}</template>
      </el-table-column>
      <el-table-column label="最近本地出库" align="center" prop="lastLocalOutboundTime" width="140" :show-overflow-tooltip="true" />
      <el-table-column label="出库天数" align="right" prop="outboundDays" width="105" sortable="custom" />
      <el-table-column label="采购周期" align="right" prop="purchaseCycleDays" width="105" sortable="custom" />
      <el-table-column label="采购数量" align="right" prop="suggestPurchaseQty" width="110" sortable="custom" />
      <el-table-column label="最大月销补货量" align="right" prop="maxMonthlyReplenishQty" width="145" sortable="custom" />
      <el-table-column label="负责人" align="center" prop="ownerName" width="110" :show-overflow-tooltip="true" />
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

<script setup name="EbayReplenishment">
import { listEbayReplenishment } from '@/api/operations/ebay/replenishment'
import request from '@/utils/request'

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
    site: undefined,
    sku: undefined,
    productName: undefined,
    skuLevel: undefined,
    ownerName: undefined,
    sortField: undefined,
    sortOrder: undefined
  }
})

const { queryParams } = toRefs(data)

function getList() {
  loading.value = true
  listEbayReplenishment(queryParams.value).then(response => {
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

function handleImport(command) {
  const input = document.createElement('input')
  input.type = 'file'; input.accept = '.xlsx,.xls'
  input.onchange = async (e) => {
    const file = e.target.files[0]
    if (!file) return
    const form = new FormData(); form.append('file', file)
    const urlMap = { sales: 'import-sales', profitRate: 'import-profit-rate', returnRate: 'import-return-rate' }
    const labelMap = { sales: '销量', profitRate: '利润率', returnRate: '退货率' }
    try {
      const res = await request({ url: `/operations/ebay/replenishment/${urlMap[command]}`, method: 'post', data: form, headers: { 'Content-Type': 'multipart/form-data' } })
      proxy.$modal.msgSuccess(`导入${labelMap[command]}完成：成功${res.data?.successRows || 0}条`)
      getList()
    } catch (e) { proxy.$modal.msgError(`导入失败: ${e.message || e}`) }
  }
  input.click()
}

function handleSelectionChange(rows) { checkedRows.value = rows }

function handleExport() {
  const selected = checkedRows.value.length > 0
  const body = {
    scope: selected ? 'SELECTED' : 'FILTERED',
    rowKeys: selected ? checkedRows.value.map(r => r.site + '|' + r.sku) : undefined
  }
  if (!selected) {
    body.filters = []
    const p = queryParams.value
    if (p.site) body.filters.push({ field: 'site', value: p.site })
    if (p.sku) body.filters.push({ field: 'sku', value: p.sku })
    if (p.productName) body.filters.push({ field: 'productName', value: p.productName })
    if (p.skuLevel) body.filters.push({ field: 'skuLevel', value: p.skuLevel })
    if (p.ownerName) body.filters.push({ field: 'ownerName', value: p.ownerName })
    if (p.sortField) { body.sortField = p.sortField; body.sortOrder = p.sortOrder || 'descending' }
  }
  request({ url: 'operations/ebay/replenishment/export', method: 'post', data: body, responseType: 'blob' }).then(res => {
    const blob = new Blob([res]); const a = document.createElement('a'); a.href = URL.createObjectURL(blob)
    a.download = `ebay_replenishment_${new Date().getTime()}.xlsx`; a.click()
  })
}

function formatPercentNumber(value) {
  if (value === null || value === undefined || value === '') return '-'
  const num = Number(value)
  return Number.isFinite(num) ? `${num.toFixed(1)}%` : '-'
}

function formatRate(value) {
  if (value === null || value === undefined || value === '') return '-'
  const num = Number(value)
  return Number.isFinite(num) ? `${(num * 100).toFixed(1)}%` : '-'
}

function formatRatio(value) {
  if (value === null || value === undefined || value === '') return '-'
  const num = Number(value)
  return Number.isFinite(num) ? num.toFixed(1) : '-'
}

function levelTagType(level) {
  const map = { A: 'success', B: 'primary', C: 'warning', D: 'info', E: 'danger' }
  return map[level] || 'info'
}

getList()
</script>

<style scoped>
.ebay-replenishment-page { background: #f5f7fa; }
:deep(.el-table .cell) { white-space: nowrap; }
</style>
