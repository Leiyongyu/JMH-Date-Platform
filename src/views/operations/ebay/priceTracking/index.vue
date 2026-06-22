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
      <el-form-item label="等级" prop="skuLevel">
        <el-select v-model="queryParams.skuLevel" placeholder="全部等级" clearable style="width: 140px">
          <el-option label="S" value="S" />
          <el-option label="A" value="A" />
          <el-option label="B" value="B" />
          <el-option label="C" value="C" />
          <el-option label="D" value="D" />
          <el-option label="E" value="E" />
        </el-select>
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
        <el-dropdown @command="handleImport" :disabled="importing" v-hasPermi="['operations:ebayReplenishment:import']">
          <el-button type="info" plain icon="Upload" :loading="importing">
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

    <el-table ref="tableRef" v-if="columnConfigLoaded" :key="columnTableKey" v-loading="loading" :data="records" border stripe height="640" :row-key="(row) => row.site + '|' + row.sku" @selection-change="handleSelectionChange" @sort-change="handleSortChange">
      <el-table-column type="selection" width="45" fixed />
      <template v-for="col in visibleColumns" :key="col.key">
        <el-table-column
          v-if="col.key === 'skuLevel'"
          :label="col.label"
          align="center"
          prop="skuLevel"
          :width="col.width"
          :render-header="renderColumnHeader(col)"
        >
          <template #default="scope">
            <el-tag :type="levelTagType(scope.row.skuLevel)" effect="light">{{ scope.row.skuLevel || '-' }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column
          v-else-if="col.format === 'percent'"
          :label="col.label" :align="col.align" :prop="col.key" :width="col.width"
          sortable="custom" :render-header="renderColumnHeader(col)"
        >
          <template #default="scope">{{ formatPercent(scope.row[col.key]) }}</template>
        </el-table-column>
        <el-table-column
          v-else-if="col.format === 'rate'"
          :label="col.label" :align="col.align" :prop="col.key" :width="col.width"
          sortable="custom" :render-header="renderColumnHeader(col)"
        >
          <template #default="scope">{{ formatRate(scope.row[col.key]) }}</template>
        </el-table-column>
        <el-table-column
          v-else-if="col.format === 'days'"
          :label="col.label" :align="col.align" :prop="col.key" :width="col.width"
          sortable="custom" :render-header="renderColumnHeader(col)"
        >
          <template #default="scope">{{ scope.row[col.key] != null ? scope.row[col.key] + '天' : '-' }}</template>
        </el-table-column>
        <el-table-column
          v-else-if="col.format === 'percentText'"
          :label="col.label" :align="col.align" :prop="col.key" :width="col.width"
          sortable="custom" :render-header="renderColumnHeader(col)"
        >
          <template #default="scope">{{ scope.row[col.key] != null ? scope.row[col.key] + '%' : '-' }}</template>
        </el-table-column>
        <el-table-column
          v-else-if="col.format === 'link'"
          :label="col.label" :align="col.align" :prop="col.key" :width="col.width"
          :render-header="renderColumnHeader(col)"
        >
          <template #default="scope">
            <a v-if="scope.row[col.key]" :href="scope.row[col.key]" target="_blank" style="color:#409EFF">链接</a>
            <span v-else>-</span>
          </template>
        </el-table-column>
        <el-table-column
          v-else-if="col.format === 'time'"
          :label="col.label" :align="col.align" :prop="col.key" :width="col.width"
          :render-header="renderColumnHeader(col)"
        >
          <template #default="scope"><span>{{ parseTime(scope.row[col.key]) }}</span></template>
        </el-table-column>
        <!-- 跟卖价：内联编辑 -->
        <el-table-column
          v-else-if="col.format === 'trackingPrice'"
          :label="col.label" :align="col.align" :width="col.width" sortable="custom"
          :render-header="renderColumnHeader(col)"
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
          :render-header="renderColumnHeader(col)"
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
          :render-header="renderColumnHeader(col)"
        >
          <template #default="scope">
            <el-input v-model="editCache[key(scope.row, 'rk')]" size="small" placeholder="备注" clearable style="width:160px"
              @blur="onRemarkBlur(scope.row)" @keyup.enter="onRemarkBlur(scope.row)" @clear="onRemarkClear(scope.row)" />
          </template>
        </el-table-column>
        <el-table-column
          v-else
          :label="col.label" :align="col.align" :prop="col.key" :width="col.width"
          :fixed="col.fixed || false" :sortable="col.sortable ? 'custom' : false"
          :show-overflow-tooltip="col.tooltip"
          :render-header="renderColumnHeader(col)"
        >
          <template #default="scope">
            <span>{{ formatCell(col, scope.row[col.key]) }}</span>
          </template>
        </el-table-column>
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

    <Teleport to="body">
      <div v-if="filterPopoverVisible" class="number-filter-overlay" @click.self="filterPopoverVisible = false">
        <div class="number-filter-popover" :style="popoverStyle" @click.stop>
          <div class="popover-header">
            <span>{{ filterEditingCol?.label || '' }} 筛选</span>
            <el-icon class="close-btn" @click="filterPopoverVisible = false"><Delete /></el-icon>
          </div>
          <div class="popover-body">
            <el-select v-model="filterEditingData.operator" size="small" style="width:100%" :teleported="false" popper-class="number-filter-select-popper">
              <el-option v-for="op in OPERATOR_OPTIONS" :key="op.value" :label="op.label" :value="op.value" />
            </el-select>
            <el-input v-if="filterEditingData.operator !== 'isNull' && filterEditingData.operator !== 'isNotNull'" v-model="filterEditingData.value" size="small" :placeholder="filterEditingData.operator === 'between' ? '最小值' : '请输入数值'" style="margin-top:8px" @keyup.enter="applyFilter" />
            <el-input v-if="filterEditingData.operator === 'between'" v-model="filterEditingData.value2" size="small" placeholder="最大值" style="margin-top:8px" @keyup.enter="applyFilter" />
          </div>
          <div class="popover-footer">
            <el-button size="small" @click="clearFilter(filterEditingCol?.key)">清除</el-button>
            <el-button size="small" type="primary" @click="applyFilter">确定</el-button>
          </div>
        </div>
      </div>
    </Teleport>

    <div v-if="activeFilterTags.length > 0" style="margin-top:8px;display:flex;flex-wrap:wrap;gap:6px;align-items:center">
      <span style="font-size:12px;color:#909399">列筛选:</span>
      <el-tag v-for="tag in activeFilterTags" :key="tag.field" size="small" closable type="info" @close="clearFilter(tag.field)">{{ tag.label }}</el-tag>
      <el-button size="small" text type="danger" @click="clearAllColumnFilters">清空全部</el-button>
    </div>
  </div>
</template>

<script setup name="EbayPriceTracking">
import { ref, reactive, toRefs, h, resolveComponent, getCurrentInstance, computed, watch } from 'vue'
import { searchPriceTracking, refreshPriceTracking, calcTracking, saveOe, saveRemark } from '@/api/operations/ebay/priceTracking'
import request from '@/utils/request'
import { parseTime } from '@/utils/ruoyi'
import { ElMessageBox } from 'element-plus'
import { Filter, Delete } from '@element-plus/icons-vue'
import ColumnConfigDrawer from '@/components/ColumnConfigDrawer/index.vue'
import { useColumnConfig } from '@/composables/useColumnConfig'

const router = useRouter()
const { proxy } = getCurrentInstance()

const loading = ref(false)
const tableRef = ref(null)
const importing = ref(false)
const IMPORT_TIMEOUT = 10 * 60 * 1000
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
  { key: 'ourLowestPrice', label: '最低价', align: 'right', width: 110, sortable: true, filterType: 'number' },
  { key: 'trackingPrice', label: '跟卖价', align: 'right', width: 120, format: 'trackingPrice', sortable: true, filterType: 'number' },
  { key: 'trackingProfitMargin', label: '跟卖利润率', align: 'right', width: 130, sortable: true, format: 'percent', filterType: 'number' },
  { key: 'floorPrice', label: '底线价', align: 'right', width: 100, sortable: true, filterType: 'number' },
  { key: 'returnRate', label: '退货率', align: 'right', width: 90, sortable: true, format: 'rate', filterType: 'number' },
  { key: 'sales3d', label: '近3天销量', align: 'right', width: 110, sortable: true, filterType: 'number' },
  { key: 'sales7d', label: '近7天销量', align: 'right', width: 110, sortable: true, filterType: 'number' },
  { key: 'sales30d', label: '近30天销量', align: 'right', width: 120, sortable: true, filterType: 'number' },
  { key: 'sales90d', label: '近90天销量', align: 'right', width: 120, sortable: true, filterType: 'number' },
  { key: 'maxMonthlySales', label: '历史最大月销', align: 'right', width: 140, sortable: true, filterType: 'number' },
  { key: 'oeNumber', label: 'OE号', align: 'center', width: 130, format: 'oeNumber' },
  { key: 'presaleUrl', label: '售前链接', align: 'center', width: 70, format: 'link' },
  { key: 'soldUrl', label: '售后链接', align: 'center', width: 70, format: 'link' },
  { key: 'overseasStock', label: '海外仓库存', align: 'right', width: 120, sortable: true, filterType: 'number' },
  { key: 'overseasStockAgeDays', label: '海外仓库龄', align: 'right', width: 120, sortable: true, format: 'days', filterType: 'number' },
  { key: 'stockSalesRatio', label: '库销比', align: 'right', width: 100, sortable: true, format: 'percentText', filterType: 'number' },
  { key: 'estimatedReplenishQty', label: '预估补货量', align: 'right', width: 120, sortable: true, filterType: 'number' },
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
    skuLevel: undefined,
    sortField: undefined,
    sortOrder: undefined
  }
})
const { queryParams } = toRefs(data)

// ---- 数值列头筛选 ----
const OPERATOR_OPTIONS = [
  { label: '等于', value: '=' }, { label: '大于', value: '>' }, { label: '大于等于', value: '>=' },
  { label: '小于', value: '<' }, { label: '小于等于', value: '<=' }, { label: '介于', value: 'between' },
  { label: '为空', value: 'isNull' }, { label: '不为空', value: 'isNotNull' }
]
const columnFilters = reactive({})
const filterPopoverVisible = ref(false)
const filterEditingCol = ref(null)
const filterEditingData = reactive({ operator: '>', value: '', value2: '' })
const filterPopoverPos = ref({ top: 200, left: 400 })

function hasActiveFilter(field) {
  const f = columnFilters[field]
  if (!f) return false
  if (f.operator === 'isNull' || f.operator === 'isNotNull') return true
  return f.value !== '' && f.value != null
}

function openFilter(col, triggerEl) {
  filterEditingCol.value = col
  const existing = columnFilters[col.key]
  if (existing) {
    filterEditingData.operator = existing.operator || '>'
    filterEditingData.value = existing.value != null ? String(existing.value) : ''
    filterEditingData.value2 = existing.value2 != null ? String(existing.value2) : ''
  } else {
    filterEditingData.operator = '>'; filterEditingData.value = ''; filterEditingData.value2 = ''
  }
  if (triggerEl) {
    const rect = triggerEl.getBoundingClientRect()
    filterPopoverPos.value = { top: rect.bottom + 4, left: rect.left }
  }
  filterPopoverVisible.value = true
}

function applyFilter() {
  const col = filterEditingCol.value
  if (!col) return
  const op = filterEditingData.operator
  const needsValue = op !== 'isNull' && op !== 'isNotNull'
  const needsValue2 = op === 'between'
  if (needsValue && !filterEditingData.value) { delete columnFilters[col.key]; filterPopoverVisible.value = false; return }
  if (needsValue2 && !filterEditingData.value2) { delete columnFilters[col.key]; filterPopoverVisible.value = false; return }
  columnFilters[col.key] = { operator: op, value: needsValue ? filterEditingData.value : undefined, value2: needsValue2 ? filterEditingData.value2 : undefined }
  filterPopoverVisible.value = false
  handleQuery()
}

function clearFilter(field) { delete columnFilters[field]; filterPopoverVisible.value = false; handleQuery() }
function clearAllColumnFilters() { Object.keys(columnFilters).forEach(k => delete columnFilters[k]); handleQuery() }
  tableRef.value?.clearSort()

const popoverStyle = computed(() => ({ position: 'fixed', top: filterPopoverPos.value.top + 'px', left: filterPopoverPos.value.left + 'px', zIndex: 3000 }))

const activeFilterTags = computed(() => {
  return Object.entries(columnFilters)
    .filter(([field]) => hasActiveFilter(field))
    .map(([field, f]) => {
      const col = columnDefs.find(c => c.key === field)
      const opLabel = OPERATOR_OPTIONS.find(o => o.value === f.operator)?.label || f.operator
      let label = (col?.label || field) + ' ' + opLabel
      if (f.value != null) label += ' ' + f.value
      if (f.operator === 'between' && f.value2 != null) label += ' ~ ' + f.value2
      return { field, label }
    })
})

function buildFilters() {
  const filters = []
  const p = queryParams.value
  if (p.site) filters.push({ field: 'site', value: p.site })
  if (p.sku) filters.push({ field: 'sku', value: p.sku })
  if (p.productName) filters.push({ field: 'productName', value: p.productName })
  if (p.brandCode) filters.push({ field: 'brandCode', value: p.brandCode })
  if (p.operatorName) filters.push({ field: 'operatorName', value: p.operatorName })
  if (p.skuLevel) filters.push({ field: 'skuLevel', value: p.skuLevel })
  Object.entries(columnFilters).forEach(([field, f]) => {
    if (hasActiveFilter(field)) {
      filters.push({ field, type: 'number', operator: f.operator, value: f.value != null ? String(f.value) : undefined, value2: f.value2 != null ? String(f.value2) : undefined })
    }
  })
  return filters
}

function renderColumnHeader(col) {
  return ({ column }) => {
    const label = column.label || col.label
    if (col.filterType !== 'number') return h('span', label)
    const active = hasActiveFilter(col.key)
    const icon = resolveComponent('el-icon')
    const filterIcon = resolveComponent('Filter')
    return h('div', { class: 'col-header-cell', style: 'display:inline-flex;align-items:center;justify-content:flex-start;gap:2px;overflow:hidden' }, [
      h(icon, { size: 13, style: `flex-shrink:0;cursor:pointer;color:${active ? '#409EFF' : '#909399'}`, onClick: (e) => { e.stopPropagation(); openFilter(col, (e && e.currentTarget) || null) } }, [h(filterIcon)]),
      h('span', { style: 'overflow:hidden;text-overflow:ellipsis;white-space:nowrap' }, label)
    ])
  }
}

function getList() {
  loading.value = true
  const body = {
    pageNum: queryParams.value.pageNum,
    pageSize: queryParams.value.pageSize,
    sortField: queryParams.value.sortField || undefined,
    sortOrder: queryParams.value.sortOrder || undefined
  }
  const filters = buildFilters()
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
  Object.keys(columnFilters).forEach(k => delete columnFilters[k])
  tableRef.value?.clearSort()
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
  if (importing.value) return
  const input = document.createElement('input')
  input.type = 'file'; input.accept = '.xlsx,.xls'
  input.onchange = async (e) => {
    const file = e.target.files[0]
    if (!file) return
    const form = new FormData(); form.append('file', file)
    const urlMap = { lowestPrice: 'import-lowest-price', productPrice: 'import-product-price' }
    const labelMap = { lowestPrice: '最低价', productPrice: '商品单价' }
    importing.value = true
    try {
      const res = await request({ url: `/operations/ebay/price-tracking/${urlMap[command]}`, method: 'post', data: form, headers: { 'Content-Type': 'multipart/form-data' }, timeout: IMPORT_TIMEOUT })
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
  const sel = checkedRows.value.length > 0
  const body = { scope: sel ? 'SELECTED' : 'FILTERED',
    rowKeys: sel ? checkedRows.value.map(r => r.site + '|' + r.sku) : undefined,
    columns: exportColumns.value }
  if (!sel) {
    body.filters = buildFilters()
    if (queryParams.value.sortField) { body.sortField = queryParams.value.sortField; body.sortOrder = queryParams.value.sortOrder || 'descending' }
  }
  request({ url: 'operations/ebay/price-tracking/export', method: 'post', data: body, responseType: 'blob' }).then(res => {
    const blob = new Blob([res]); const a = document.createElement('a'); a.href = URL.createObjectURL(blob)
    a.download = `ebay_price_tracking_${new Date().getTime()}.xlsx`; a.click()
  })
}

function formatCell(col, value) {
  if (value === null || value === undefined) return col.filterType === 'number' ? '0' : ''
  return value
}

function formatPercent(value) {
  if (value === null || value === undefined || value === '') return '0.0%'
  const num = Number(value)
  return Number.isFinite(num) ? `${(num * 100).toFixed(1)}%` : '0.0%'
}

function formatRate(value) {
  if (value === null || value === undefined || value === '') return '0.0%'
  const num = Number(value)
  return Number.isFinite(num) ? `${(num * 100).toFixed(1)}%` : '0.0%'
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
:deep(.col-header-cell) { cursor: default; user-select: none; }
:deep(.col-header-cell .el-icon) { opacity: 0.5; transition: opacity 0.2s; }
:deep(.col-header-cell:hover .el-icon) { opacity: 1; }
</style>

<style>
.number-filter-overlay { position: fixed; top: 0; left: 0; right: 0; bottom: 0; z-index: 2999; background: transparent; }
.number-filter-popover { position: fixed; background: #fff; border-radius: 8px; box-shadow: 0 6px 24px rgba(0,0,0,0.15); min-width: 240px; z-index: 3000; }
.number-filter-popover .popover-header { display: flex; align-items: center; justify-content: space-between; padding: 10px 14px 6px; font-size: 14px; font-weight: 600; border-bottom: 1px solid #ebeef5; }
.number-filter-popover .popover-header .close-btn { cursor: pointer; color: #909399; font-size: 14px; }
.number-filter-popover .popover-body { padding: 12px 14px; overflow: visible; }
.number-filter-popover .popover-footer { padding: 8px 14px 12px; display: flex; justify-content: flex-end; gap: 8px; }
.number-filter-select-popper { z-index: 3100 !important; }
</style>
