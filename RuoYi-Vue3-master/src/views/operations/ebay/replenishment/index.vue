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
      <el-form-item label="产品性质" prop="productNature">
        <el-select v-model="queryParams.productNature" placeholder="全部" clearable style="width: 110px" @change="handleQuery">
          <el-option label="新品" value="0" />
          <el-option label="老品" value="1" />
        </el-select>
      </el-form-item>
      <el-form-item label="退货等级" prop="returnLevel">
        <el-select v-model="queryParams.returnLevel" placeholder="全部" clearable style="width: 120px" @change="handleQuery">
          <el-option label="问题产品" value="问题产品" />
          <el-option label="长尾产品" value="长尾产品" />
          <el-option label="主力产品" value="主力产品" />
          <el-option label="明星产品" value="明星产品" />
          <el-option label="未分类" value="未分类" />
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

    <el-table ref="tableRef"
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
          :render-header="renderColumnHeader(col)"
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
          :render-header="renderColumnHeader(col)"
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
          :render-header="renderColumnHeader(col)"
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
          :render-header="renderColumnHeader(col)"
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
          :render-header="renderColumnHeader(col)"
        >
          <template #default="scope">
            <span>{{ parseTime(scope.row[col.key]) }}</span>
          </template>
        </el-table-column>
        <el-table-column
          v-else-if="col.key === 'productNature'"
          :label="col.label" :align="col.align" :width="col.width"
        >
          <template #default="scope">
            <el-select v-model="scope.row.productNature" size="small" placeholder="选择" clearable style="width:90px"
              @change="(v) => updateProductNature(scope.row, v)">
              <el-option label="老品" :value="1" />
              <el-option label="新品" :value="2" />
            </el-select>
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
          :render-header="renderColumnHeader(col)"
        >
          <template #default="scope">
            <span>{{ col.filterType === 'number' && (scope.row[col.key] === null || scope.row[col.key] === undefined) ? '0' : scope.row[col.key] }}</span>
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

    <!-- 数值筛选弹窗 -->
    <Teleport to="body">
      <div
        v-if="filterPopoverVisible"
        class="number-filter-overlay"
        @click.self="filterPopoverVisible = false"
      >
        <div class="number-filter-popover" :style="popoverStyle" @click.stop>
          <div class="popover-header">
            <span>{{ filterEditingCol?.label || '' }} 筛选</span>
            <el-icon class="close-btn" @click="filterPopoverVisible = false"><Delete /></el-icon>
          </div>
          <div class="popover-body">
            <el-select v-model="filterEditingData.operator" size="small" style="width:100%" :teleported="false" popper-class="number-filter-select-popper">
              <el-option v-for="op in OPERATOR_OPTIONS" :key="op.value" :label="op.label" :value="op.value" />
            </el-select>
            <el-input
              v-if="filterEditingData.operator !== 'isNull' && filterEditingData.operator !== 'isNotNull'"
              v-model="filterEditingData.value"
              size="small"
              :placeholder="filterEditingData.operator === 'between' ? '最小值' : '请输入数值'"
              style="margin-top:8px"
              @keyup.enter="applyFilter"
            />
            <el-input
              v-if="filterEditingData.operator === 'between'"
              v-model="filterEditingData.value2"
              size="small"
              placeholder="最大值"
              style="margin-top:8px"
              @keyup.enter="applyFilter"
            />
          </div>
          <div class="popover-footer">
            <el-button size="small" @click="clearFilter(filterEditingCol?.key)">清除</el-button>
            <el-button size="small" type="primary" @click="applyFilter">确定</el-button>
          </div>
        </div>
      </div>
    </Teleport>

    <!-- 激活的列筛选标签 -->
    <div v-if="activeFilterTags.length > 0" style="margin-top:8px;display:flex;flex-wrap:wrap;gap:6px;align-items:center">
      <span style="font-size:12px;color:#909399">列筛选:</span>
      <el-tag
        v-for="tag in activeFilterTags" :key="tag.field"
        size="small" closable type="info"
        @close="clearFilter(tag.field)"
      >{{ tag.label }}</el-tag>
      <el-button size="small" text type="danger" @click="clearAllColumnFilters">清空全部</el-button>
    </div>
  </div>
</template>

<script setup name="EbayReplenishment">
import { ref, reactive, toRefs, h, resolveComponent, getCurrentInstance, computed } from 'vue'
import { searchEbayReplenishment, refreshEbayReplenishment } from '@/api/operations/ebay/replenishment'
import { syncEbayAll } from '@/api/operations/sync'
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
const replenishmentList = ref([])
const checkedRows = ref([])
const fixedColumnKeys = ['site', 'sku']
const columnDefs = [
  { key: 'site', label: '站点', align: 'center', width: 90, fixed: true, sortable: true },
  { key: 'sku', label: 'SKU', align: 'left', width: 170, fixed: true, sortable: true, tooltip: true },
  { key: 'productName', label: '产品名称', align: 'left', width: 260, tooltip: true },
  { key: 'skuLevel', label: '等级', align: 'center', width: 80, sortable: true },
  { key: 'productNature', label: '产品性质', align: 'center', width: 100 },
  { key: 'profitRate30d', label: '近30天利润', align: 'right', width: 120, sortable: true, format: 'percentNumber', filterType: 'number' },
  { key: 'returnRate', label: '退货率', align: 'right', width: 110, sortable: true, format: 'rate', filterType: 'number' },
  { key: 'overseasOnway', label: '海外在途', align: 'right', width: 115, sortable: true, filterType: 'number' },
  { key: 'overseasSellable', label: '海外可售', align: 'right', width: 115, sortable: true, filterType: 'number' },
  { key: 'overseasTotal', label: '海外总库存', align: 'right', width: 130, sortable: true, filterType: 'number' },
  { key: 'purchasePendingDelivery', label: '采购待交付', align: 'right', width: 130, sortable: true, filterType: 'number' },
  { key: 'localSellable', label: '成都可售', align: 'right', width: 115, sortable: true, filterType: 'number' },
  { key: 'localOnway', label: '成都在途', align: 'right', width: 115, sortable: true, filterType: 'number' },
  { key: 'purchasePlanQty', label: '采购计划', align: 'right', width: 115, sortable: true, filterType: 'number' },
  { key: 'lockedQty', label: '待出库', align: 'right', width: 105, sortable: true, filterType: 'number' },
  { key: 'totalInventory', label: '总库存', align: 'right', width: 115, sortable: true, filterType: 'number' },
  { key: 'sales7d', label: '近7天销量', align: 'right', width: 120, sortable: true, filterType: 'number' },
  { key: 'sales15d', label: '近15天销量', align: 'right', width: 120, sortable: true, filterType: 'number' },
  { key: 'sales30d', label: '近30天销量', align: 'right', width: 120, sortable: true, filterType: 'number' },
  { key: 'sales90d', label: '近90天销量', align: 'right', width: 120, sortable: true, filterType: 'number' },
  { key: 'maxMonthlySales', label: '历史最大月销', align: 'right', width: 130, sortable: true, filterType: 'number' },
  { key: 'overseasSellableSalesRatio', label: '海外在库库销比', align: 'right', width: 145, sortable: true, format: 'ratio', filterType: 'number' },
  { key: 'overseasTotalSalesRatio', label: '海外总库销比', align: 'right', width: 135, sortable: true, format: 'ratio', filterType: 'number' },
  { key: 'totalInventorySalesRatio', label: '总库存库销比', align: 'right', width: 135, sortable: true, format: 'ratio', filterType: 'number' },
  { key: 'lastLocalOutboundTime', label: '最近本地出库', align: 'center', width: 140, tooltip: true },
  { key: 'outboundDays', label: '出库天数', align: 'right', width: 115, sortable: true, filterType: 'number' },
  { key: 'purchaseCycleDays', label: '采购周期', align: 'right', width: 115, sortable: true, filterType: 'number' },
  { key: 'suggestPurchaseQty', label: '采购数量', align: 'right', width: 120, sortable: true, filterType: 'number' },
  { key: 'maxMonthlyReplenishQty', label: '最大月销补货量', align: 'right', width: 145, sortable: true, filterType: 'number' },
  { key: 'returnLevel', label: '退货等级', align: 'center', width: 110 },
  { key: 'monthlyTurnoverRate', label: '月动销率', align: 'right', width: 110, sortable: true, format: 'percentNumber', filterType: 'number' },
  { key: 'ownerName', label: '负责人', align: 'center', width: 110, tooltip: true }
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
    productNature: undefined,
    returnLevel: undefined,
    ownerName: undefined,
    sortField: undefined,
    sortOrder: undefined
  }
})

const { queryParams } = toRefs(data)

// ---- 数值列头筛选 ----
const OPERATOR_OPTIONS = [
  { label: '等于', value: '=' },
  { label: '大于', value: '>' },
  { label: '大于等于', value: '>=' },
  { label: '小于', value: '<' },
  { label: '小于等于', value: '<=' },
  { label: '介于', value: 'between' },
  { label: '为空', value: 'isNull' },
  { label: '不为空', value: 'isNotNull' }
]
// columnFilters: { fieldName: { operator, value, value2 } }
const columnFilters = reactive({})
// active filter popover state
const filterPopoverVisible = ref(false)
const filterEditingCol = ref(null)
const filterEditingData = reactive({ operator: '>', value: '', value2: '' })

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
    filterEditingData.operator = '>'
    filterEditingData.value = ''
    filterEditingData.value2 = ''
  }
  // Store trigger element position
  if (triggerEl) {
    const rect = triggerEl.getBoundingClientRect()
    filterPopoverPos.value = { top: rect.bottom + 4, left: rect.left }
  } else {
    filterPopoverPos.value = { top: 200, left: 400 }
  }
  filterPopoverVisible.value = true
}

const filterPopoverPos = ref({ top: 200, left: 400 })
const popoverStyle = computed(() => ({
  position: 'fixed',
  top: filterPopoverPos.value.top + 'px',
  left: filterPopoverPos.value.left + 'px',
  zIndex: 3000
}))

const activeFilterTags = computed(() => {
  return Object.entries(columnFilters)
    .filter(([field]) => hasActiveFilter(field))
    .map(([field, f]) => {
      const col = columnDefs.find(c => c.key === field)
      const opLabel = OPERATOR_OPTIONS.find(o => o.value === f.operator)?.label || f.operator
      let label = (col?.label || field) + ' ' + opLabel
      if (f.operator !== 'isNull' && f.operator !== 'isNotNull' && f.value != null) {
        label += ' ' + f.value
      }
      if (f.operator === 'between' && f.value2 != null) {
        label += ' ~ ' + f.value2
      }
      return { field, label }
    })
})

function applyFilter() {
  const col = filterEditingCol.value
  if (!col) return
  const op = filterEditingData.operator
  const needsValue = op !== 'isNull' && op !== 'isNotNull'
  const needsValue2 = op === 'between'

  if (needsValue && !filterEditingData.value) {
    // Clear if no value
    delete columnFilters[col.key]
    filterPopoverVisible.value = false
    return
  }
  if (needsValue2 && !filterEditingData.value2) {
    delete columnFilters[col.key]
    filterPopoverVisible.value = false
    return
  }

  columnFilters[col.key] = {
    operator: op,
    value: needsValue ? filterEditingData.value : undefined,
    value2: needsValue2 ? filterEditingData.value2 : undefined
  }
  filterPopoverVisible.value = false
  handleQuery()
}

function clearFilter(field) {
  delete columnFilters[field]
  filterPopoverVisible.value = false
  handleQuery()
}

function clearAllColumnFilters() {
  Object.keys(columnFilters).forEach(k => delete columnFilters[k])
  tableRef.value?.clearSort()
}

// Build filters array from both top-form and column filters
function buildFilters() {
  const filters = []
  const p = queryParams.value
  // Top-form text filters
  if (p.site) filters.push({ field: 'site', value: p.site })
  if (p.sku) filters.push({ field: 'sku', value: p.sku })
  if (p.productName) filters.push({ field: 'productName', value: p.productName })
  if (p.skuLevel) filters.push({ field: 'skuLevel', value: p.skuLevel })
  if (p.productNature) filters.push({ field: 'productNature', value: p.productNature })
  if (p.returnLevel) filters.push({ field: 'returnLevel', value: p.returnLevel })
  if (p.ownerName) filters.push({ field: 'ownerName', value: p.ownerName })
  // Column numeric filters
  Object.entries(columnFilters).forEach(([field, f]) => {
    if (hasActiveFilter(field)) {
      filters.push({
        field,
        type: 'number',
        operator: f.operator,
        value: f.value != null ? String(f.value) : undefined,
        value2: f.value2 != null ? String(f.value2) : undefined
      })
    }
  })
  return filters
}

// Render header for columns - adds filter icon for numeric columns
function renderColumnHeader(col) {
  return ({ column }) => {
    const label = column.label || col.label
    if (col.filterType !== 'number') {
      return h('span', label)
    }
    const active = hasActiveFilter(col.key)
    const icon = resolveComponent('el-icon')
    const filterIcon = resolveComponent('Filter')
    return h('div', {
      class: 'col-header-cell',
      style: 'display:inline-flex;align-items:center;justify-content:flex-start;gap:2px;overflow:hidden'
    }, [
      h(icon, {
        size: 13,
        style: `flex-shrink:0;cursor:pointer;color:${active ? '#409EFF' : '#909399'}`,
        onClick: (e) => { e.stopPropagation(); openFilter(col, (e && e.currentTarget) || null) }
      }, [h(filterIcon)]),
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

  searchEbayReplenishment(body).then(response => {
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

function updateProductNature(row, val) {
  request({ url: '/operations/ebay/replenishment/update-product-nature', method: 'post', data: { site: row.site, sku: row.sku, productNature: val } })
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
    body.filters = buildFilters()
    if (queryParams.value.sortField) {
      body.sortField = queryParams.value.sortField
      body.sortOrder = queryParams.value.sortOrder || 'descending'
    }
  }
  request({ url: 'operations/ebay/replenishment/export', method: 'post', data: body, responseType: 'blob' }).then(res => {
    const blob = new Blob([res]); const a = document.createElement('a'); a.href = URL.createObjectURL(blob)
    a.download = `ebay_replenishment_${new Date().getTime()}.xlsx`; a.click()
  })
}

function formatPercentNumber(value) {
  if (value === null || value === undefined || value === '') return '0.0%'
  const num = Number(value)
  return Number.isFinite(num) ? `${num.toFixed(1)}%` : '0.0%'
}

function formatRate(value) {
  if (value === null || value === undefined || value === '') return '0.0%'
  const num = Number(value)
  return Number.isFinite(num) ? `${(num * 100).toFixed(1)}%` : '0.0%'
}

function formatRatio(value) {
  if (value === null || value === undefined || value === '') return '0.0'
  const num = Number(value)
  return Number.isFinite(num) ? num.toFixed(1) : '0.0'
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
:deep(.col-header-cell) { cursor: default; user-select: none; }
:deep(.col-header-cell .el-icon) { opacity: 0.5; transition: opacity 0.2s; }
:deep(.col-header-cell:hover .el-icon) { opacity: 1; }
</style>

<style>
.number-filter-overlay {
  position: fixed;
  top: 0; left: 0; right: 0; bottom: 0;
  z-index: 2999;
  background: transparent;
}
.number-filter-popover {
  position: fixed;
  background: #fff;
  border-radius: 8px;
  box-shadow: 0 6px 24px rgba(0,0,0,0.15);
  min-width: 240px;
  z-index: 3000;
}
.number-filter-popover .popover-header {
  display: flex; align-items: center; justify-content: space-between;
  padding: 10px 14px 6px; font-size: 14px; font-weight: 600;
  border-bottom: 1px solid #ebeef5;
}
.number-filter-popover .popover-header .close-btn {
  cursor: pointer; color: #909399; font-size: 14px;
}
.number-filter-popover .popover-body {
  padding: 12px 14px; overflow: visible;
}
.number-filter-select-popper {
  z-index: 3100 !important;
}
.number-filter-popover .popover-footer {
  padding: 8px 14px 12px;
  display: flex; justify-content: flex-end; gap: 8px;
}
</style>
