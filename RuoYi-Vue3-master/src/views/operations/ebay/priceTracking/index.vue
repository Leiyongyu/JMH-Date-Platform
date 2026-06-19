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
        <el-dropdown @command="handleSyncCommand" v-hasPermi="['operations:ebayReplenishment:sync']">
          <el-button type="primary" plain icon="RefreshRight">
            拉取eBay最新数据<el-icon class="el-icon--right"><arrow-down /></el-icon>
          </el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="full">拉取eBay最新数据</el-dropdown-item>
              <el-dropdown-item command="refreshOnly">仅刷新当前页面</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
      </el-col>
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

    <el-table v-if="columnConfigLoaded" :key="columnTableKey" v-loading="loading" :data="records" border stripe height="640" :row-key="(row) => row.site + '|' + row.sku" @selection-change="handleSelectionChange" @sort-change="handleSortChange">
      <el-table-column type="selection" width="45" fixed />
      <template v-for="col in visibleColumns" :key="col.key">
        <el-table-column
          v-if="col.key === 'skuLevel'"
          :label="col.label"
          align="center"
          prop="skuLevel"
          :width="col.width"
        >
          <template #default="scope">
            <el-tag :type="levelTagType(scope.row.skuLevel)" effect="light">{{ scope.row.skuLevel || '-' }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column
          v-else-if="col.format === 'percent'"
          :label="col.label"
          :align="col.align"
          :prop="col.key"
          :width="col.width"
          sortable="custom"
        >
          <template #default="scope">{{ formatPercent(scope.row[col.key]) }}</template>
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
          v-else-if="col.format === 'days'"
          :label="col.label"
          :align="col.align"
          :prop="col.key"
          :width="col.width"
          sortable="custom"
        >
          <template #default="scope">{{ scope.row[col.key] != null ? scope.row[col.key] + '天' : '-' }}</template>
        </el-table-column>
        <el-table-column
          v-else-if="col.format === 'percentText'"
          :label="col.label"
          :align="col.align"
          :prop="col.key"
          :width="col.width"
          sortable="custom"
        >
          <template #default="scope">{{ scope.row[col.key] != null ? scope.row[col.key] + '%' : '-' }}</template>
        </el-table-column>
        <el-table-column
          v-else-if="col.format === 'link'"
          :label="col.label"
          :align="col.align"
          :prop="col.key"
          :width="col.width"
        >
          <template #default="scope">
            <a v-if="scope.row[col.key]" :href="scope.row[col.key]" target="_blank" style="color:#409EFF">链接</a>
            <span v-else>-</span>
          </template>
        </el-table-column>
        <el-table-column
          v-else-if="col.format === 'time'"
          :label="col.label"
          :align="col.align"
          :prop="col.key"
          :width="col.width"
        >
          <template #default="scope"><span>{{ parseTime(scope.row[col.key]) }}</span></template>
        </el-table-column>
        <!-- 跟卖价：内联编辑 -->
        <el-table-column
          v-else-if="col.format === 'trackingPrice'"
          :label="col.label" :align="col.align" :width="col.width" sortable="custom"
        >
          <template #default="scope">
            <el-input v-model="editCache[key(scope.row, 'tp')]" size="small" placeholder="跟卖价" style="width:100px"
              @blur="onTrackingBlur(scope.row)" @keyup.enter="onTrackingBlur(scope.row)" />
          </template>
        </el-table-column>
        <!-- OE号：内联编辑 -->
        <el-table-column
          v-else-if="col.format === 'oeNumber'"
          :label="col.label" :align="col.align" :width="col.width"
        >
          <template #default="scope">
            <el-input v-model="editCache[key(scope.row, 'oe')]" size="small" placeholder="OE号" clearable style="width:110px"
              @blur="onOeBlur(scope.row)" @keyup.enter="onOeBlur(scope.row)" @clear="onOeClear(scope.row)" />
          </template>
        </el-table-column>
        <!-- 备注：内联编辑 -->
        <el-table-column
          v-else-if="col.format === 'remark'"
          :label="col.label" :align="col.align" :width="col.width"
        >
          <template #default="scope">
            <el-input v-model="editCache[key(scope.row, 'rk')]" size="small" placeholder="备注" clearable style="width:160px"
              @blur="onRemarkBlur(scope.row)" @keyup.enter="onRemarkBlur(scope.row)" @clear="onRemarkClear(scope.row)" />
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

    <pagination v-show="total > 0" :total="total" v-model:page="queryParams.pageNum" v-model:limit="queryParams.pageSize" @pagination="getList" />

    <column-config-drawer
      v-model="showColumnDrawer"
      :columns="columnDefs"
      :fixed-keys="fixedColumnKeys"
      :visible-keys="visibleKeys"
      @apply="handleColumnApply"
    />
  </div>
</template>

<script setup name="EbayPriceTracking">
import { searchPriceTracking, refreshPriceTracking, calcTracking, saveOe, saveRemark } from '@/api/operations/ebay/priceTracking'
import { syncEbayAll, refreshEbayOnly } from '@/api/operations/sync'
import request from '@/utils/request'
import ColumnConfigDrawer from '@/components/ColumnConfigDrawer/index.vue'
import { useColumnConfig } from '@/composables/useColumnConfig'

const router = useRouter()
const { proxy } = getCurrentInstance()

const loading = ref(false)
const showSearch = ref(true)
const total = ref(0)
const records = ref([])
const checkedRows = ref([])
const editCache = reactive({})

function key(row, field) { return (row.site || '') + '|' + (row.sku || '') + '_' + field }
function initEditCache() {
  for (const row of records.value) {
    const k = key(row, 'tp'); if (!(k in editCache)) editCache[k] = row.trackingPrice ?? ''
    const ko = key(row, 'oe'); if (!(ko in editCache)) editCache[ko] = row.oeNumber ?? ''
    const kr = key(row, 'rk'); if (!(kr in editCache)) editCache[kr] = row.remark ?? ''
  }
}
watch(records, initEditCache, { flush: 'post' })

async function onTrackingBlur(row) {
  const k = key(row, 'tp')
  const v = editCache[k]
  const oldValue = row.trackingPrice != null ? String(row.trackingPrice) : ''
  const needRecalculate = row.trackingProfitMargin == null || row.floorPrice == null
  if (v === oldValue && !needRecalculate) return
  if (row._saving) return; row._saving = true
  try {
    const r = await calcTracking(row.site, row.sku, v || '')
    const d = r.data || {}
    if (d.success === false) throw new Error('invalid tracking price')
    row.trackingPrice = d.trackingPrice ?? v ?? ''
    row.trackingProfitMargin = d.trackingProfitMargin ?? null
    row.floorPrice = d.floorPrice ?? null
    editCache[k] = row.trackingPrice ?? ''
    if (d.message) proxy.$modal.msgWarning(d.message)
  } catch { editCache[k] = row.trackingPrice ?? '' }
  finally { row._saving = false }
}
async function onOeBlur(row) {
  const k = key(row, 'oe')
  const v = editCache[k] || ''; if (v === (row.oeNumber || '')) return
  if (row._saving) return; row._saving = true
  try {
    const r = await saveOe(row.site, row.sku, v)
    const d = r.data || {}
    row.oeNumber = d.oeNumber ?? v
    row.presaleUrl = d.presaleUrl ?? row.presaleUrl
    row.soldUrl = d.soldUrl ?? row.soldUrl
    editCache[k] = row.oeNumber ?? ''
  } catch { editCache[k] = row.oeNumber || '' }
  finally { row._saving = false }
}
async function onOeClear(row) { editCache[key(row, 'oe')] = ''; onOeBlur(row) }
async function onRemarkBlur(row) {
  const k = key(row, 'rk')
  const v = editCache[k] || ''; if (v === (row.remark || '')) return
  if (row._saving) return; row._saving = true
  try { await saveRemark(row.site, row.sku, v); row.remark = v; editCache[k] = v }
  catch { editCache[k] = row.remark || '' }
  finally { row._saving = false }
}
async function onRemarkClear(row) { editCache[key(row, 'rk')] = ''; onRemarkBlur(row) }

const fixedColumnKeys = ['site', 'sku']
const columnDefs = [
  { key: 'site', label: '站点', align: 'center', width: 90, fixed: true, sortable: true },
  { key: 'sku', label: 'SKU', align: 'left', width: 170, fixed: true, sortable: true, tooltip: true },
  { key: 'productName', label: '产品名称', align: 'left', width: 260, tooltip: true },
  { key: 'skuLevel', label: '等级', align: 'center', width: 80 },
  { key: 'ourLowestPrice', label: '我方最低价', align: 'right', width: 110, sortable: true },
  { key: 'trackingPrice', label: '跟卖价', align: 'right', width: 120, format: 'trackingPrice', sortable: true },
  { key: 'trackingProfitMargin', label: '跟卖利润率', align: 'right', width: 130, sortable: true, format: 'percent' },
  { key: 'floorPrice', label: '底线价', align: 'right', width: 100, sortable: true },
  { key: 'returnRate', label: '退货率', align: 'right', width: 90, sortable: true, format: 'rate' },
  { key: 'sales3d', label: '近3天销量', align: 'right', width: 110, sortable: true },
  { key: 'sales7d', label: '近7天销量', align: 'right', width: 110, sortable: true },
  { key: 'sales30d', label: '近30天销量', align: 'right', width: 120, sortable: true },
  { key: 'sales90d', label: '近90天销量', align: 'right', width: 120, sortable: true },
  { key: 'maxMonthlySales', label: '历史最大月销', align: 'right', width: 140, sortable: true },
  { key: 'oeNumber', label: 'OE号', align: 'center', width: 130, format: 'oeNumber' },
  { key: 'presaleUrl', label: '售前链接', align: 'center', width: 70, format: 'link' },
  { key: 'soldUrl', label: '售后链接', align: 'center', width: 70, format: 'link' },
  { key: 'overseasStock', label: '海外仓库存', align: 'right', width: 120, sortable: true },
  { key: 'overseasStockAgeDays', label: '海外仓库龄', align: 'right', width: 120, sortable: true, format: 'days' },
  { key: 'stockSalesRatio', label: '库销比', align: 'right', width: 100, sortable: true, format: 'percentText' },
  { key: 'estimatedReplenishQty', label: '预估补货量', align: 'right', width: 120, sortable: true },
  { key: 'brandCode', label: '品牌', align: 'center', width: 90, tooltip: true },
  { key: 'operatorName', label: '操作员', align: 'center', width: 100, tooltip: true },
  { key: 'remark', label: '备注', align: 'left', width: 180, format: 'remark' },
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
} = useColumnConfig('operations:ebay:priceTracking', columnDefs, fixedColumnKeys)
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

async function handleSyncCommand(command) {
  if (loading.value) return
  loading.value = true
  try {
    let res
    if (command === 'full') {
      res = await syncEbayAll()
    } else {
      res = await refreshEbayOnly()
    }
    if (res.code === 200) {
      proxy.$modal.msgSuccess(typeof res.msg === 'string' ? res.msg : '同步完成')
    } else {
      proxy.$modal.msgError(res.msg || '同步失败')
    }
    await getList()
  } catch (e) {
    proxy.$modal.msgError('同步失败: ' + (e.message || e))
  } finally {
    loading.value = false
  }
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

async function handleColumnApply(keys) {
  await applyColumnConfig(keys)
  proxy.$modal.msgSuccess('列配置已保存')
}

function handleExport() {
  const sel = checkedRows.value.length > 0
  const body = { scope: sel ? 'SELECTED' : 'FILTERED',
    rowKeys: sel ? checkedRows.value.map(r => r.site + '|' + r.sku) : undefined,
    columns: exportColumns.value }
  if (!sel) {
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

async function initPage() {
  await initColumnConfig()
  getList()
}

initPage()
</script>

<style scoped>
.ebay-price-tracking-page { background: #f5f7fa; }
:deep(.el-table .cell) { white-space: nowrap; }
</style>
