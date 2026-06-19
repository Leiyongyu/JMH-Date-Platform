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
        <el-button type="primary" plain icon="RefreshRight" @click="handleSyncAll"
          :loading="syncing" v-hasPermi="['operations:ebayReplenishment:sync']">拉取eBay最新数据</el-button>
      </el-col>
      <el-col :span="1.5">
        <el-dropdown @command="handleImport" :disabled="importing" v-hasPermi="['operations:ebayReplenishment:import']">
          <el-button type="info" plain icon="Upload" :loading="importing">
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
      :row-key="(row) => row.site + '|' + row.sku"
      @selection-change="handleSelectionChange"
      @sort-change="handleSortChange"
    >
      <el-table-column type="selection" width="45" fixed />
      <template v-for="col in visibleColumns" :key="col.key">
        <el-table-column
          v-if="col.key === 'skuLevel'"
          :label="col.label"
          align="center"
          prop="skuLevel"
          :width="col.width"
          sortable="custom"
        >
          <template #default="scope">
            <el-tag :type="levelTagType(scope.row.skuLevel)" effect="light">{{ scope.row.skuLevel || '-' }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column
          v-else-if="col.format === 'percentNumber'"
          :label="col.label"
          :align="col.align"
          :prop="col.key"
          :width="col.width"
          sortable="custom"
        >
          <template #default="scope">{{ formatPercentNumber(scope.row[col.key]) }}</template>
        </el-table-column>
        <el-table-column
          v-else-if="col.format === 'rate'"
          :label="col.label"
          :align="col.align"
          :prop="col.key"
          :width="col.width"
          sortable="custom"
        >
          <template #default="scope">{{ formatRate(scope.row[col.key]) }}</template>
        </el-table-column>
        <el-table-column
          v-else-if="col.format === 'ratio'"
          :label="col.label"
          :align="col.align"
          :prop="col.key"
          :width="col.width"
          sortable="custom"
        >
          <template #default="scope">{{ formatRatio(scope.row[col.key]) }}</template>
        </el-table-column>
        <el-table-column
          v-else-if="col.format === 'time'"
          :label="col.label"
          :align="col.align"
          :prop="col.key"
          :width="col.width"
          :show-overflow-tooltip="col.tooltip"
        >
          <template #default="scope">
            <span>{{ parseTime(scope.row[col.key]) }}</span>
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

<script setup name="EbayReplenishment">
import { listEbayReplenishment, refreshEbayReplenishment } from '@/api/operations/ebay/replenishment'
import { syncEbayAll } from '@/api/operations/sync'
import request from '@/utils/request'
import { parseTime } from '@/utils/ruoyi'
import { ElMessageBox } from 'element-plus'
import ColumnConfigDrawer from '@/components/ColumnConfigDrawer/index.vue'
import { useColumnConfig } from '@/composables/useColumnConfig'

const router = useRouter()
const { proxy } = getCurrentInstance()

const loading = ref(false)
const importing = ref(false)
const IMPORT_TIMEOUT = 10 * 60 * 1000
const showSearch = ref(true)
const total = ref(0)
const replenishmentList = ref([])
const checkedRows = ref([])
const fixedColumnKeys = ['site', 'sku']
const columnDefs = [
  { key: 'site', label: '站点', align: 'center', width: 90, fixed: true, sortable: true },
  { key: 'sku', label: 'SKU', align: 'left', width: 170, fixed: true, sortable: true, tooltip: true },
  { key: 'productName', label: '产品名称', align: 'left', width: 260, tooltip: true },
  { key: 'skuLevel', label: '等级', align: 'center', width: 80, sortable: true },
  { key: 'profitRate30d', label: '近30天利润', align: 'right', width: 120, sortable: true, format: 'percentNumber' },
  { key: 'returnRate', label: '退货率', align: 'right', width: 100, sortable: true, format: 'rate' },
  { key: 'overseasOnway', label: '海外在途', align: 'right', width: 105, sortable: true },
  { key: 'overseasSellable', label: '海外可售', align: 'right', width: 105, sortable: true },
  { key: 'overseasTotal', label: '海外总库存', align: 'right', width: 120, sortable: true },
  { key: 'purchasePendingDelivery', label: '采购待交付', align: 'right', width: 120, sortable: true },
  { key: 'localSellable', label: '成都可售', align: 'right', width: 105, sortable: true },
  { key: 'localOnway', label: '成都在途', align: 'right', width: 105, sortable: true },
  { key: 'purchasePlanQty', label: '采购计划', align: 'right', width: 105, sortable: true },
  { key: 'lockedQty', label: '待出库', align: 'right', width: 95, sortable: true },
  { key: 'totalInventory', label: '总库存', align: 'right', width: 105, sortable: true },
  { key: 'sales7d', label: '近7天销量', align: 'right', width: 110, sortable: true },
  { key: 'sales30d', label: '近30天销量', align: 'right', width: 120, sortable: true },
  { key: 'sales90d', label: '近90天销量', align: 'right', width: 120, sortable: true },
  { key: 'maxMonthlySales', label: '历史最大月销', align: 'right', width: 130, sortable: true },
  { key: 'overseasSellableSalesRatio', label: '海外在库库销比', align: 'right', width: 145, sortable: true, format: 'ratio' },
  { key: 'overseasTotalSalesRatio', label: '海外总库销比', align: 'right', width: 135, sortable: true, format: 'ratio' },
  { key: 'totalInventorySalesRatio', label: '总库存库销比', align: 'right', width: 135, sortable: true, format: 'ratio' },
  { key: 'lastLocalOutboundTime', label: '最近本地出库', align: 'center', width: 140, tooltip: true },
  { key: 'outboundDays', label: '出库天数', align: 'right', width: 105, sortable: true },
  { key: 'purchaseCycleDays', label: '采购周期', align: 'right', width: 105, sortable: true },
  { key: 'suggestPurchaseQty', label: '采购数量', align: 'right', width: 110, sortable: true },
  { key: 'maxMonthlyReplenishQty', label: '最大月销补货量', align: 'right', width: 145, sortable: true },
  { key: 'ownerName', label: '负责人', align: 'center', width: 110, tooltip: true },
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
} = useColumnConfig('operations:ebay:replenishment', columnDefs, fixedColumnKeys)
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

async function handleRefresh() {
  if (loading.value) return
  loading.value = true
  try { await refreshEbayReplenishment(); await getList() }
  finally { loading.value = false }
}

const syncing = ref(false)

async function handleSyncAll() {
  if (syncing.value) { proxy.$modal.msgWarning('eBay数据同步正在执行中，请稍后再试'); return }
  syncing.value = true
  try {
    const res = await syncEbayAll()
    if (res.code === 200) proxy.$modal.msgSuccess('拉取完成')
    else proxy.$modal.msgError(res.msg || '拉取失败')
    await getList()
  } catch (e) {
    proxy.$modal.msgError('拉取失败: ' + (e.message || e))
  } finally {
    syncing.value = false
  }
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
  if (importing.value) return
  const input = document.createElement('input')
  input.type = 'file'; input.accept = '.xlsx,.xls'
  input.onchange = async (e) => {
    const file = e.target.files[0]
    if (!file) return
    const form = new FormData(); form.append('file', file)
    const urlMap = { sales: 'import-sales', profitRate: 'import-profit-rate', returnRate: 'import-return-rate' }
    const labelMap = { sales: '销量', profitRate: '利润率', returnRate: '退货率' }
    importing.value = true
    try {
      const res = await request({ url: `/operations/ebay/replenishment/${urlMap[command]}`, method: 'post', data: form, headers: { 'Content-Type': 'multipart/form-data' }, timeout: IMPORT_TIMEOUT })
      showImportResult(labelMap[command], res.data)
      await getList()
    } catch (e) { proxy.$modal.msgError(`导入失败: ${e.message || e}`) }
    finally { importing.value = false }
  }
  input.click()
}

function showImportResult(label, task = {}) {
  const status = task.status || 'SUCCESS'
  const statusText = status === 'SUCCESS' ? '成功' : (status === 'PARTIAL' ? '部分成功' : status)
  const failRows = task.failRows ?? 0
  const html = `
    <div style="padding:4px 2px 0;">
      <div style="font-size:15px;font-weight:600;margin-bottom:12px;">导入${escapeHtml(label)}完成</div>
      <div style="display:grid;grid-template-columns:88px 1fr;gap:8px 12px;line-height:22px;">
        <span style="color:#606266;">文件名称</span><strong>${escapeHtml(task.fileName || '-')}</strong>
        <span style="color:#606266;">任务状态</span><strong>${escapeHtml(statusText)}</strong>
        <span style="color:#606266;">总行数</span><strong>${task.totalRows ?? 0}</strong>
        <span style="color:#606266;">成功行数</span><strong style="color:#67c23a;">${task.successRows ?? 0}</strong>
        <span style="color:#606266;">失败行数</span><strong style="color:${failRows > 0 ? '#f56c6c' : '#303133'};">${failRows}</strong>
        <span style="color:#606266;">操作人</span><strong>${escapeHtml(task.operator || '-')}</strong>
        <span style="color:#606266;">完成时间</span><strong>${parseTime(task.endTime) || '-'}</strong>
      </div>
    </div>`
  ElMessageBox.alert(html, '导入结果', {
    dangerouslyUseHTMLString: true,
    confirmButtonText: '确定',
    type: status === 'SUCCESS' ? 'success' : 'warning'
  })
}

function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, (ch) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[ch]))
}

function handleSelectionChange(rows) { checkedRows.value = rows }

async function handleColumnApply(keys) {
  await applyColumnConfig(keys)
  proxy.$modal.msgSuccess('列配置已保存')
}

function handleExport() {
  const selected = checkedRows.value.length > 0
  const body = {
    scope: selected ? 'SELECTED' : 'FILTERED',
    rowKeys: selected ? checkedRows.value.map(r => r.site + '|' + r.sku) : undefined,
    columns: exportColumns.value
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

async function initPage() {
  await initColumnConfig()
  getList()
}

initPage()
</script>

<style scoped>
.ebay-replenishment-page { background: #f5f7fa; }
:deep(.el-table .cell) { white-space: nowrap; }
</style>
