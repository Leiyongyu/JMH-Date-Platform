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

    <el-row :gutter="10" class="mb8" style="display:flex;align-items:center">
      <el-col :span="1.5">
        <span style="font-size:13px;color:#606266;margin-right:8px">区域组：</span>
      </el-col>
      <el-col :span="1.5">
        <el-radio-group v-model="regionGroup" size="small" @change="handleRegionChange">
          <el-radio-button value="">全部</el-radio-button>
          <el-radio-button value="US">美国组</el-radio-button>
          <el-radio-button value="EU">欧洲组</el-radio-button>
        </el-radio-group>
      </el-col>
    </el-row>

    <el-row :gutter="10" class="mb8">
      <el-col :span="1.5">
        <el-button type="primary" plain icon="RefreshRight" @click="handleSyncAll"
          :loading="syncing" v-hasPermi="['operations:amzReplenishment:sync']">拉取AMZ最新数据</el-button>
      </el-col>
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
      ref="tableRef"
      v-if="columnConfigLoaded"
      :key="columnTableKey"
      v-loading="loading"
      :data="replenishmentList"
      border stripe height="640"
      show-summary :summary-method="getSummaries"
      :row-key="(row) => (row.sid||'') + '|' + (row.sellerSku||'') + '|' + (row.warehouseSku||'')"
      @selection-change="handleSelectionChange"
      @sort-change="handleSortChange"
    >
      <el-table-column type="selection" width="45" fixed />
      <template v-for="col in visibleColumns" :key="col.key">
        <el-table-column
          v-if="col.format === 'percentNumber'"
          :label="col.label" :align="col.align" :prop="col.key" :width="col.width"
          sortable="custom" :render-header="renderColumnHeader(col)"
        >
          <template #default="scope">{{ formatPercentNumber(scope.row[col.key]) }}</template>
        </el-table-column>
        <el-table-column
          v-else-if="col.format === 'number'"
          :label="col.label" :align="col.align" :prop="col.key" :width="col.width"
          sortable="custom" :render-header="renderColumnHeader(col)"
        >
          <template #default="scope">
            <span :class="{ 'negative-value': Number(scope.row[col.key]) < 0 }">{{ formatNumber(scope.row[col.key]) }}</span>
          </template>
        </el-table-column>
        <el-table-column
          v-else-if="col.format === 'time'"
          :label="col.label" :align="col.align" :prop="col.key" :width="col.width"
          :render-header="renderColumnHeader(col)"
        >
          <template #default="scope"><span>{{ parseTime(scope.row[col.key]) }}</span></template>
        </el-table-column>
        <!-- 产品分类：内联编辑 -->
        <el-table-column
          v-else-if="col.format === 'productCategory'"
          :label="col.label" :align="col.align" :width="col.width"
          :render-header="renderColumnHeader(col)"
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
          :render-header="renderColumnHeader(col)"
        >
          <template #default="scope">
            <el-input v-model="editCache[amzKey(scope.row,'pqty')]" size="small" placeholder="数量" clearable style="width:100px"
              @blur="onAmzCellBlur(scope.row,'pqty')" @keyup.enter="onAmzCellBlur(scope.row,'pqty')" @clear="onAmzCellClear(scope.row,'pqty')" />
          </template>
        </el-table-column>
        <!-- 备注：内联编辑 -->
        <el-table-column
          v-else-if="col.format === 'remark'"
          :label="col.label" :align="col.align" :width="col.width" sortable="custom"
          :render-header="renderColumnHeader(col)"
        >
          <template #default="scope">
            <el-input v-model="editCache[amzKey(scope.row,'rem')]" size="small" placeholder="备注" clearable
              @blur="onAmzCellBlur(scope.row,'rem')" @keyup.enter="onAmzCellBlur(scope.row,'rem')" @clear="onAmzCellClear(scope.row,'rem')" />
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

<script setup name="AmzReplenishment">
import { ref, reactive, toRefs, h, resolveComponent, getCurrentInstance, computed, watch } from 'vue'
import { listAmzReplenishment, searchAmzReplenishment, refreshAmzReplenishment } from '@/api/operations/amz/replenishment'
import { syncAmzAll } from '@/api/operations/sync'
import request from '@/utils/request'
import { parseTime } from '@/utils/ruoyi'
import { Filter, Delete } from '@element-plus/icons-vue'
import ColumnConfigDrawer from '@/components/ColumnConfigDrawer/index.vue'
import { useColumnConfig } from '@/composables/useColumnConfig'

const router = useRouter()
const { proxy } = getCurrentInstance()

const loading = ref(false)
const tableRef = ref(null)
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
    const rem = amzKey(row, 'rem'); if (!(rem in editCache)) editCache[rem] = row.remark ?? ''
  }
}
watch(replenishmentList, initAmzEditCache, { flush: 'post' })
async function onAmzCellBlur(row, field) {
  const k = amzKey(row, field)
  const v = editCache[k] || ''; const oldV = field === 'cat' ? (row.productCategory ?? '') : String(row.purchasedQty ?? '')
  if (v === oldV || row._saving) return; row._saving = true
  try {
    if (field === 'cat') {
      await request({ url: '/operations/amz/replenishment/override', method: 'post', data: { sid: String(row.sid||''), sellerSku: row.sellerSku, productCategory: v || '' } })
    } else if (field === 'rem') {
      await request({ url: '/operations/amz/replenishment/override', method: 'post', data: { sid: String(row.sid||''), sellerSku: row.sellerSku, remark: v || '' } })
    } else {
      await request({ url: '/operations/amz/replenishment/update-qty-receive', method: 'post', data: { warehouseSku: row.warehouseSku, value: v || null } })
    }
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
  { key: 'tagName', label: '标签', align: 'left', width: 140, tooltip: true },
  { key: 'regionGroup', label: '区域组', align: 'center', width: 80 },
  { key: 'principalName', label: '负责人', align: 'center', width: 120, tooltip: true },
  { key: 'productCategory', label: '产品分类', align: 'center', width: 130, format: 'productCategory' },
  { key: 'rating', label: '评分', align: 'right', width: 80, sortable: true, filterType: 'number' },
  { key: 'reviewCount', label: '评论数', align: 'right', width: 100, sortable: true, filterType: 'number' },
  { key: 'adRate', label: '广告费率', align: 'right', width: 105, sortable: true, format: 'percentNumber', filterType: 'number' },
  { key: 'profitRate30d', label: '30天利润率', align: 'right', width: 120, sortable: true, format: 'percentNumber', filterType: 'number' },
  { key: 'refundRate90d', label: '90天退款率', align: 'right', width: 120, sortable: true, format: 'percentNumber', filterType: 'number' },
  { key: 'purchasedQty', label: '已采购数量', align: 'right', width: 120, sortable: true, format: 'purchasedQty', filterType: 'number' },
  { key: 'domesticStock', label: '国内仓库存', align: 'right', width: 120, sortable: true, filterType: 'number' },
  { key: 'pendingShipQty', label: '待出库', align: 'right', width: 95, sortable: true, filterType: 'number' },
  { key: 'fbaStock', label: 'FBA在库', align: 'right', width: 105, sortable: true, filterType: 'number' },
  { key: 'fbaInbound', label: 'FBA在途', align: 'right', width: 105, sortable: true, filterType: 'number' },
  { key: 'totalInventory', label: '总库存', align: 'right', width: 105, sortable: true, filterType: 'number' },
  { key: 'sales7d', label: '7天销量', align: 'right', width: 95, sortable: true, filterType: 'number' },
  { key: 'sales14d', label: '14天销量', align: 'right', width: 100, sortable: true, filterType: 'number' },
  { key: 'sales30d', label: '30天销量', align: 'right', width: 100, sortable: true, filterType: 'number' },
  { key: 'sales60d', label: '60天销量', align: 'right', width: 100, sortable: true, filterType: 'number' },
  { key: 'salesSpeed14d', label: '14日均销', align: 'right', width: 105, sortable: true, filterType: 'number' },
  { key: 'salesSpeed30d', label: '30日均销', align: 'right', width: 105, sortable: true, filterType: 'number' },
  { key: 'salesSpeed60d', label: '60日均销', align: 'right', width: 105, sortable: true, filterType: 'number' },
  { key: 'avgMonthlySales', label: '平均月销量', align: 'right', width: 120, sortable: true, filterType: 'number' },
  { key: 'safetyStock', label: '安全库存', align: 'right', width: 110, sortable: true, filterType: 'number' },
  { key: 'shipQty', label: '发货量', align: 'right', width: 100, sortable: true, format: 'number', filterType: 'number' },
  { key: 'replenishQty', label: '补货量', align: 'right', width: 100, sortable: true, format: 'number', filterType: 'number' },
  { key: 'restockDays', label: '补货时间', align: 'right', width: 105, sortable: true, filterType: 'number' },
  { key: 'remark', label: '备注', align: 'left', width: 160, format: 'remark' },
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
const regionGroup = ref('')

function handleRegionChange() { queryParams.value.pageNum = 1; getList() }

const summaryFields = ['reviewCount','sales7d','sales14d','sales30d','sales60d']
function getSummaries({ columns, data }) {
  const sums = {}
  if (!data || !data.length) return []
  summaryFields.forEach(f => { sums[f] = data.reduce((s, r) => s + (Number(r[f]) || 0), 0) })
  return columns.map((col, i) => {
    if (i === 0) return ''
    const key = col.property
    if (summaryFields.includes(key)) return sums[key]
    return ''
  })
}

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
  const f = columnFilters[field]; if (!f) return false
  if (f.operator === 'isNull' || f.operator === 'isNotNull') return true
  return f.value !== '' && f.value != null
}
function openFilter(col, triggerEl) {
  filterEditingCol.value = col
  const existing = columnFilters[col.key]
  if (existing) { filterEditingData.operator = existing.operator || '>'; filterEditingData.value = existing.value != null ? String(existing.value) : ''; filterEditingData.value2 = existing.value2 != null ? String(existing.value2) : '' }
  else { filterEditingData.operator = '>'; filterEditingData.value = ''; filterEditingData.value2 = '' }
  if (triggerEl) { const rect = triggerEl.getBoundingClientRect(); filterPopoverPos.value = { top: rect.bottom + 4, left: rect.left } }
  filterPopoverVisible.value = true
}
function applyFilter() {
  const col = filterEditingCol.value; if (!col) return
  const op = filterEditingData.operator; const needsValue = op !== 'isNull' && op !== 'isNotNull'; const needsValue2 = op === 'between'
  if (needsValue && !filterEditingData.value) { delete columnFilters[col.key]; filterPopoverVisible.value = false; return }
  if (needsValue2 && !filterEditingData.value2) { delete columnFilters[col.key]; filterPopoverVisible.value = false; return }
  columnFilters[col.key] = { operator: op, value: needsValue ? filterEditingData.value : undefined, value2: needsValue2 ? filterEditingData.value2 : undefined }
  filterPopoverVisible.value = false; handleQuery()
}
function clearFilter(field) { delete columnFilters[field]; filterPopoverVisible.value = false; handleQuery() }
function clearAllColumnFilters() { Object.keys(columnFilters).forEach(k => delete columnFilters[k]); handleQuery() }
const popoverStyle = computed(() => ({ position: 'fixed', top: filterPopoverPos.value.top + 'px', left: filterPopoverPos.value.left + 'px', zIndex: 3000 }))
const activeFilterTags = computed(() => {
  return Object.entries(columnFilters).filter(([field]) => hasActiveFilter(field)).map(([field, f]) => {
    const col = columnDefs.find(c => c.key === field); const opLabel = OPERATOR_OPTIONS.find(o => o.value === f.operator)?.label || f.operator
    let label = (col?.label || field) + ' ' + opLabel
    if (f.value != null) label += ' ' + f.value; if (f.operator === 'between' && f.value2 != null) label += ' ~ ' + f.value2
    return { field, label }
  })
})
function buildFilters() {
  const filters = []; const p = queryParams.value
  if (regionGroup.value) filters.push({ field: 'regionGroup', value: regionGroup.value })
  if (p.storeName) filters.push({ field: 'storeName', value: p.storeName })
  if (p.sellerSku) filters.push({ field: 'sellerSku', value: p.sellerSku })
  if (p.warehouseSku) filters.push({ field: 'warehouseSku', value: p.warehouseSku })
  if (p.asin) filters.push({ field: 'asin', value: p.asin })
  if (p.principalName) filters.push({ field: 'principalName', value: p.principalName })
  if (p.productCategory) filters.push({ field: 'productCategory', value: p.productCategory })
  Object.entries(columnFilters).forEach(([field, f]) => {
    if (hasActiveFilter(field)) { filters.push({ field, type: 'number', operator: f.operator, value: f.value != null ? String(f.value) : undefined, value2: f.value2 != null ? String(f.value2) : undefined }) }
  })
  return filters
}
function renderColumnHeader(col) {
  return ({ column }) => {
    const label = column.label || col.label
    if (col.filterType !== 'number') return h('span', label)
    const active = hasActiveFilter(col.key)
    const icon = resolveComponent('el-icon'); const filterIcon = resolveComponent('Filter')
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
  searchAmzReplenishment(body).then(response => {
    replenishmentList.value = response.rows || []
    total.value = response.total || 0
  }).finally(() => { loading.value = false })
}

async function handleRefresh() {
  if (loading.value) return
  loading.value = true
  try { await refreshAmzReplenishment(); await getList() }
  finally { loading.value = false }
}

const syncing = ref(false)

async function handleSyncAll() {
  if (syncing.value) { proxy.$modal.msgWarning('AMZ数据同步正在执行中，请稍后再试'); return }
  syncing.value = true
  try {
    const res = await syncAmzAll()
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
  regionGroup.value = ''
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
    body.filters = buildFilters()
    if (queryParams.value.sortField) { body.sortField = queryParams.value.sortField; body.sortOrder = queryParams.value.sortOrder || 'descending' }
  }
  request({ url: 'operations/amz/replenishment/export', method: 'post', data: body, responseType: 'blob' }).then(res => {
    const blob = new Blob([res]); const a = document.createElement('a'); a.href = URL.createObjectURL(blob)
    a.download = `amz_replenishment_${new Date().getTime()}.xlsx`; a.click()
  })
}

function formatCell(col, value) {
  if (value === null || value === undefined) return col.filterType === 'number' ? '0' : ''
  return value
}

function formatPercentNumber(value) {
  if (value === null || value === undefined || value === '') return '0.0%'
  const num = Number(value)
  return Number.isFinite(num) ? `${num.toFixed(1)}%` : '0.0%'
}

function formatNumber(value) {
  if (value === null || value === undefined || value === '') return '0'
  const num = Number(value)
  return Number.isFinite(num) ? num.toFixed(2).replace(/\.?0+$/, '') : '0'
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
