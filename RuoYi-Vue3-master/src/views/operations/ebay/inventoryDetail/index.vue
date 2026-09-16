<template>
  <div class="app-container inventory-detail-page">
    <div class="view-switch">
      <el-radio-group v-model="activeView" :disabled="recalculating" aria-label="库存视图切换">
        <el-radio-button value="detail">库存明细</el-radio-button>
        <el-radio-button value="pivot">历史透视</el-radio-button>
      </el-radio-group>
    </div>
    <InventoryHistoryPivot v-if="activeView === 'pivot'" />
    <section v-show="activeView === 'detail'" class="table-panel">
      <el-form v-show="showSearch" :model="query" :inline="true" :disabled="recalculating" class="query-form" @submit.prevent="handleQuery">
        <el-form-item label="统计日期">
          <el-date-picker v-model="query.statDate" type="date" value-format="YYYY-MM-DD"
            placeholder="最新已保存日期" :clearable="false" :disabled-date="disabledStatDate"
            style="width: 175px" @change="handleQuery" />
        </el-form-item>
        <el-form-item label="站点">
          <el-select v-model="query.site" clearable filterable placeholder="全部站点" style="width: 160px">
            <el-option v-for="site in sites" :key="site" :label="site" :value="site" />
          </el-select>
        </el-form-item>
        <el-form-item label="SKU">
          <el-input v-model="query.sku" clearable placeholder="搜索 SKU" style="width: 230px" @keyup.enter="handleQuery" />
        </el-form-item>
        <el-form-item label="品牌">
          <el-select v-model="query.brand" clearable filterable placeholder="全部品牌" style="width: 150px">
            <el-option v-for="brand in brands" :key="brand" :label="brand" :value="brand" />
          </el-select>
        </el-form-item>
        <el-form-item label="等级">
          <el-select v-model="query.grade" clearable filterable placeholder="全部等级" style="width: 150px">
            <el-option v-for="grade in grades" :key="grade" :label="grade" :value="grade" />
          </el-select>
        </el-form-item>
        <el-form-item class="query-actions">
          <el-button type="primary" icon="Search" :disabled="loading" @click="handleQuery">查询</el-button>
          <el-button icon="Refresh" :disabled="loading" @click="resetQuery">重置</el-button>
          <el-button v-hasPermi="['operations:ebayInventoryDetail:import']" icon="Upload" plain
            :disabled="loading || importing" @click="importDialogVisible = true">导入产品等级</el-button>
          <el-tooltip content="已勾选时导出所选记录；未勾选时导出当前统计日期及筛选下的全部记录。包含全部29个字段。" placement="top">
            <el-button v-hasPermi="['operations:ebayInventoryDetail:export']" type="primary" icon="Download"
              :loading="exporting" :disabled="loading || !dataReady || filtersDirty || total === 0" @click="handleExport">
              {{ selectedCount ? `导出已选（${selectedCount}）` : '导出全部数据' }}
            </el-button>
          </el-tooltip>
        </el-form-item>
      </el-form>

      <div class="table-toolbar">
        <div class="selection-info">
          <span>共 <b>{{ total.toLocaleString() }}</b> 条</span>
          <span v-if="filtersDirty" class="pending-filter-text">筛选条件已更改，请点击查询</span>
          <span v-if="selectedCount" class="selected-text">已选 {{ selectedCount }} 条（支持跨页）</span>
          <span v-else-if="!filtersDirty" class="muted">未勾选时，导出当前筛选的全部数据</span>
          <el-button v-if="selectedCount" link type="primary" @click="clearSelection">清空选择</el-button>
        </div>
        <right-toolbar v-model:showSearch="showSearch" :show-column-config="true"
          :refresh-loading="recalculating" :refresh-disabled="loading || importing || exporting || !canRecalculate"
          :refresh-tooltip="canRecalculate ? '刷新：重新计算并覆盖今日快照，不重新拉取接口' : '重新计算需要产品等级导入权限'"
          @queryTable="handleRefresh" @columnConfig="openColumnConfig" />
      </div>

      <el-table v-if="columnConfigLoaded" :key="columnTableKey" ref="tableRef" v-loading="loading || recalculating"
        :data="rows" :row-key="rowKey" :default-sort="defaultSort" border stripe
        height="620" empty-text="暂无符合条件的库存数据" class="inventory-table"
        @selection-change="handleSelectionChange" @sort-change="handleSortChange">
        <el-table-column type="selection" width="46" fixed="left" align="center" :selectable="() => dataReady && !loading && !recalculating && !filtersDirty" />
        <el-table-column v-for="column in visibleColumns" :key="column.key" :prop="column.key"
          :label="column.label" :min-width="column.width || 132"
          :fixed="fixedColumnKeys.includes(column.key) ? 'left' : false"
          :align="column.format ? 'right' : 'left'" :sortable="column.sortable ? 'custom' : false"
          :show-overflow-tooltip="!column.format">
          <template #header>
            <el-tooltip placement="top" effect="light" :show-after="200">
              <template #content>
                <div class="column-help">
                  <p>以下说明为快照生成时的取数口径；历史日期读取已冻结值，不按最新来源重算。</p>
                  <div class="column-help-title">{{ column.label }} · 数据口径</div>
                  <dl>
                    <div><dt>来源接口</dt><dd>{{ column.help.sourceApi }}</dd></div>
                    <div><dt>源表</dt><dd class="column-help-table">{{ column.help.sourceTable }}</dd></div>
                    <div><dt>计算公式</dt><dd>{{ column.help.formula }}</dd></div>
                    <div><dt>空值处理</dt><dd>{{ column.help.emptyHandling }}</dd></div>
                  </dl>
                </div>
              </template>
              <span class="column-heading" tabindex="0" :aria-label="`${column.label}：数据来源与计算口径`">
                {{ column.label }}<el-icon class="column-tip" aria-hidden="true"><QuestionFilled /></el-icon>
              </span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <el-tag v-if="column.key === 'grade' && hasValue(row.grade)" type="info" effect="plain" size="small" class="grade-tag">{{ row.grade }}</el-tag>
            <el-tooltip v-else-if="column.key === 'warehouse_rent_30d_cny' && row.rent_warning"
              :content="row.rent_warning" placement="top">
              <span class="rent-warning-value">{{ formatValue(row[column.key], column.format) }} <el-icon><QuestionFilled /></el-icon></span>
            </el-tooltip>
            <el-tooltip v-else-if="priceColumnKeys.includes(column.key) && row.price_warning"
              :content="row.price_warning" placement="top">
              <span class="price-warning-value">{{ formatValue(row[column.key], column.format) }} <el-icon><QuestionFilled /></el-icon></span>
            </el-tooltip>
            <el-tooltip v-else-if="column.key === 'overseas_max_age_days' && row.age_warning"
              :content="row.age_warning" placement="top">
              <span class="age-warning-value">{{ formatValue(row[column.key], column.format) }} <el-icon><QuestionFilled /></el-icon></span>
            </el-tooltip>
            <span v-else :class="{ 'sku-text': column.key === 'sku', 'empty-value': !hasValue(row[column.key]), 'numeric-value': !!column.format }">
              {{ formatValue(row[column.key], column.format) }}
            </span>
          </template>
        </el-table-column>
      </el-table>
      <div class="table-pagination">
        <span class="page-range" role="status" aria-live="polite">
          当前显示 {{ pageRange.start.toLocaleString() }}–{{ pageRange.end.toLocaleString() }} 条，共 {{ total.toLocaleString() }} 条
        </span>
        <Pagination v-model:page="pageQuery.pageNum" v-model:limit="pageQuery.pageSize"
          :total="total" :page-sizes="[10, 20, 30, 50, 100, 200]" :auto-scroll="false"
          layout="total, sizes, prev, pager, next, jumper" @pagination="handlePagination" />
      </div>
    </section>

    <column-config-drawer v-model="showColumnDrawer" :columns="columnDefs" :fixed-keys="fixedColumnKeys"
      :visible-keys="visibleKeys" @apply="handleColumnApply" />

    <el-dialog v-model="importDialogVisible" title="导入 eBay 产品等级" width="580px" append-to-body
      :close-on-click-modal="!importing" :close-on-press-escape="!importing" :show-close="!importing">
      <el-alert type="info" :closable="false" show-icon title="按 SKU ＋站点更新等级，不影响文件以外的记录。" />
      <p class="import-description">上传 Excel（.xlsx），表头需包含「SKU」「站点」「等级」。站点支持德国 / 英国 / 美国等名称或 DE / UK / US 等对应代码，等级按文件原值保存。无效行会跳过并列明原因，不覆盖这些记录原有的等级。</p>
      <el-upload ref="uploadRef" drag :auto-upload="false" :limit="1" accept=".xlsx" :disabled="importing"
        :on-change="handleGradeFileChange" :on-remove="handleGradeFileRemove" :on-exceed="handleFileExceed">
        <el-icon class="upload-icon"><UploadFilled /></el-icon>
        <div>拖入等级文件，或<span class="upload-link">点击选择</span></div>
        <template #tip><div class="el-upload__tip">仅支持 .xlsx，最大 10 MB；重复的 SKU ＋站点须使用相同等级。</div></template>
      </el-upload>
      <template #footer>
        <el-button :disabled="importing" @click="importDialogVisible = false">取消</el-button>
        <el-button type="primary" :disabled="!gradeFile" :loading="importing" @click="handleGradeImport">确认导入</el-button>
      </template>
    </el-dialog>
    <el-dialog v-model="importResultVisible" title="产品等级导入结果" width="680px" append-to-body>
      <el-alert :type="Number(importResult.skipped_rows) ? 'warning' : 'success'" :closable="false" show-icon
        :title="`更新 ${importResult.imported_rows ?? 0} 条，合并重复 ${importResult.duplicate_rows ?? 0} 条，跳过无效 ${importResult.skipped_rows ?? 0} 条`" />
      <p class="import-description">仅更新有效的 SKU ＋站点，文件之外的记录及跳过行原有等级均保持不变。</p>
      <el-scrollbar v-if="importWarnings.length" max-height="330px" class="import-warning-list">
        <div v-for="(warning, index) in importWarnings" :key="index">{{ warning }}</div>
      </el-scrollbar>
      <template #footer><el-button type="primary" @click="importResultVisible = false">知道了</el-button></template>
    </el-dialog>
  </div>
</template>

<script setup name="EbayInventoryDetail">
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { QuestionFilled, UploadFilled } from '@element-plus/icons-vue'
import Pagination from '@/components/Pagination/index.vue'
import ColumnConfigDrawer from '@/components/ColumnConfigDrawer/index.vue'
import { useColumnConfig } from '@/composables/useColumnConfig'
import download from '@/plugins/download'
import { blobValidate } from '@/utils/ruoyi'
import { checkPermi } from '@/utils/permission'
import { listEbayInventoryDetail, exportEbayInventoryDetail, importEbayInventoryGrades, recalculateEbayInventorySnapshot } from '@/api/operations/ebay/inventoryDetail'
import { inventoryColumnHelp } from './columnHelp'
import InventoryHistoryPivot from './InventoryHistoryPivot.vue'

const activeView = ref('detail')
const rows = ref([])
const total = ref(0)
const sites = ref([])
const brands = ref([])
const grades = ref([])
const availableDates = ref([])
const loading = ref(false)
const recalculating = ref(false)
const canRecalculate = computed(() => checkPermi(['operations:ebayInventoryDetail:import']))
const dataReady = ref(false)
const exporting = ref(false)
const showSearch = ref(true)
const tableRef = ref()
const query = reactive({ statDate: undefined, site: undefined, sku: '', brand: undefined, grade: undefined })
const appliedFilters = ref({})
const filtersDirty = computed(() => JSON.stringify(currentFilters()) !== JSON.stringify(appliedFilters.value))
// Keep state distinct from the Pagination component: script-setup bindings win
// over globally registered components with the same name.
const pageQuery = reactive({ pageNum: 1, pageSize: 50 })
const pageRange = computed(() => {
  if (!rows.value.length || total.value <= 0) return { start: 0, end: 0 }
  const start = (pageQuery.pageNum - 1) * pageQuery.pageSize + 1
  return { start, end: Math.min(total.value, start + rows.value.length - 1) }
})
const sort = reactive({ sortField: 'sales_qty_30d', sortOrder: 'descending' })
const defaultSort = computed(() => ({ prop: sort.sortField, order: sort.sortOrder }))
const selection = reactive(new Map())
const selectedCount = computed(() => selection.size)
let restoringSelection = false
let loadVersion = 0
let unmounted = false

const fixedColumnKeys = ['site', 'sku']
const priceColumnKeys = ['unit_price_tax', 'overseas_sellable_value', 'overseas_total_value']
const columnDefs = [
  { key: 'site', label: '站点', width: 90 },
  { key: 'sku', label: 'SKU', width: 205 },
  { key: 'sku_middle_code', label: '中间码', width: 110 },
  { key: 'brand', label: '品牌', width: 100 },
  { key: 'product_name', label: '产品名称', width: 240 },
  { key: 'grade', label: '等级', width: 100 },
  { key: 'overseas_in_transit_quantity', label: '海外在途', format: 'quantity', sortable: true },
  { key: 'overseas_sellable_quantity', label: '海外可售', format: 'quantity', sortable: true },
  { key: 'overseas_total_quantity', label: '海外总库存', format: 'quantity', sortable: true },
  { key: 'chengdu_in_transit_quantity', label: '成都在途', format: 'quantity', sortable: true },
  { key: 'chengdu_sellable_quantity', label: '成都可售', format: 'quantity', sortable: true },
  { key: 'procurement_plan_quantity', label: '采购计划', format: 'quantity' },
  { key: 'pending_outbound_quantity', label: '待出库', format: 'quantity' },
  { key: 'cycle_total_quantity', label: '周期总库存', format: 'quantity', sortable: true },
  { key: 'overseas_max_age_days', label: '海外最高库龄', format: 'quantity', sortable: true, width: 150 },
  { key: 'sales_qty_30d', label: '近30天销量', format: 'quantity', sortable: true },
  { key: 'average_monthly_sales_3m', label: '近3个月均销量', format: 'decimal2', sortable: true, width: 150 },
  { key: 'in_stock_sales_ratio', label: '在库库销比', format: 'percent', sortable: true },
  { key: 'total_stock_sales_ratio', label: '总库销比', format: 'percent', sortable: true },
  { key: 'unit_price_tax', label: '单价（含税）', format: 'money', sortable: true, width: 140 },
  { key: 'overseas_sellable_value', label: '海外可售货值', format: 'money', sortable: true, width: 150 },
  { key: 'overseas_total_value', label: '海外总货值', format: 'money', sortable: true, width: 145 },
  { key: 'owner', label: '负责人', width: 125 },
  { key: 'warehouse_rent_30d_cny', label: '30天谷仓仓租', format: 'money', sortable: true, width: 155 },
  { key: 'total_duration_months', label: '总时长（月）', format: 'decimal', width: 145 },
  { key: 'total_stock_sales_ratio_months', label: '总库销比（月）', format: 'percent', sortable: true, width: 155 },
  { key: 'purchase_quantity', label: '申购量', format: 'quantity' },
  { key: 'last_sold_at', label: '最后售出时间', width: 180 },
  { key: 'stat_date', label: '统计日期', width: 130 }
].map(column => ({ ...column, help: inventoryColumnHelp[column.key] }))
const {
  showColumnDrawer, columnConfigLoaded, columnTableKey, visibleKeys, visibleColumns,
  openColumnConfig, initColumnConfig, applyColumnConfig
} = useColumnConfig('operations:ebay:inventory-detail', columnDefs, fixedColumnKeys, fixedColumnKeys,
  { average_daily_sales_30d: 'average_monthly_sales_3m' }, { sku_middle_code: 'sku' })

function hasValue(value) {
  return value !== undefined && value !== null && String(value).trim() !== ''
}

function formatValue(value, format) {
  if (!hasValue(value)) return '--'
  if (!format) return String(value)
  const number = Number(value)
  if (!Number.isFinite(number)) return '--'
  if (format === 'percent') {
    // Intl percent formatting scales the ratio by 100 for display only.
    return number.toLocaleString('zh-CN', {
      style: 'percent', minimumFractionDigits: 2, maximumFractionDigits: 2
    })
  }
  const money = format === 'money'
  const fixedTwo = money || format === 'decimal2'
  return `${money ? '¥' : ''}${number.toLocaleString('zh-CN', {
    minimumFractionDigits: fixedTwo ? 2 : 0,
    maximumFractionDigits: fixedTwo ? 2 : (format === 'decimal' ? 6 : 0)
  })}`
}

function rowKey(row) {
  return JSON.stringify([String(row.site || '').trim(), String(row.sku || '').trim()])
}

function currentFilters() {
  return {
    statDate: query.statDate || 'latest',
    site: query.site || undefined,
    sku: query.sku.trim() || undefined,
    brand: query.brand || undefined,
    grade: query.grade || undefined
  }
}

function disabledStatDate(value) {
  const key = [value.getFullYear(), String(value.getMonth() + 1).padStart(2, '0'),
    String(value.getDate()).padStart(2, '0')].join('-')
  return !availableDates.value.includes(key)
}

function handleSelectionChange(selectedRows) {
  if (restoringSelection || loading.value || filtersDirty.value || !dataReady.value) return
  // Only mutate the current page's keys, preserving selections on other pages.
  rows.value.forEach(row => selection.delete(rowKey(row)))
  selectedRows.forEach(row => selection.set(rowKey(row), { site: row.site, sku: row.sku }))
}

function clearSelection() {
  selection.clear()
  tableRef.value?.clearSelection()
}

async function restorePageSelection() {
  restoringSelection = true
  try {
    await nextTick()
    tableRef.value?.clearSelection()
    for (const row of rows.value) {
      if (selection.has(rowKey(row))) tableRef.value?.toggleRowSelection(row, true)
    }
  } finally {
    restoringSelection = false
  }
}

async function loadRows() {
  const version = ++loadVersion
  loading.value = true
  dataReady.value = false
  try {
    const response = await listEbayInventoryDetail({ ...appliedFilters.value, ...pageQuery, ...sort })
    if (unmounted || version !== loadVersion) return
    const data = response.data || {}
    restoringSelection = true
    rows.value = data.items || []
    total.value = Number(data.pagination?.total || 0)
    pageQuery.pageNum = Number(data.pagination?.page || pageQuery.pageNum)
    pageQuery.pageSize = Number(data.pagination?.page_size || pageQuery.pageSize)
    sites.value = data.sites || []
    brands.value = data.brands || []
    grades.value = data.grades || []
    availableDates.value = data.metadata?.available_dates || []
    // Resolve "latest" once; pagination and export stay on the displayed date.
    if (appliedFilters.value.statDate === 'latest' && data.metadata?.stat_date) {
      appliedFilters.value = { ...appliedFilters.value, statDate: data.metadata.stat_date }
      if (!query.statDate) query.statDate = data.metadata.stat_date
    }
    await restorePageSelection()
    if (version === loadVersion) dataReady.value = true
  } catch (error) {
    // The shared request interceptor displays the server error. Keep the last successful view.
  } finally {
    if (!unmounted && version === loadVersion) loading.value = false
  }
}

function handlePagination({ page, limit }) {
  if (recalculating.value) return
  Object.assign(pageQuery, { pageNum: page, pageSize: limit })
  return loadRows()
}

function handleQuery() {
  if (recalculating.value) return
  clearSelection()
  pageQuery.pageNum = 1
  appliedFilters.value = currentFilters()
  return loadRows()
}

function resetQuery() {
  Object.assign(query, { statDate: undefined, site: undefined, sku: '', brand: undefined, grade: undefined })
  Object.assign(sort, { sortField: 'sales_qty_30d', sortOrder: 'descending' })
  tableRef.value?.sort(sort.sortField, sort.sortOrder)
  return handleQuery()
}

function handleSortChange({ prop, order }) {
  if (recalculating.value) return
  const nextField = order ? prop : 'sales_qty_30d'
  const nextOrder = order || 'descending'
  if (sort.sortField === nextField && sort.sortOrder === nextOrder) return
  Object.assign(sort, { sortField: nextField, sortOrder: nextOrder })
  pageQuery.pageNum = 1
  loadRows()
}

async function handleRefresh() {
  if (recalculating.value || loading.value || importing.value || exporting.value || !canRecalculate.value) return
  recalculating.value = true
  dataReady.value = false
  clearSelection()
  try {
    const response = await recalculateEbayInventorySnapshot()
    if (unmounted) return
    const day = response.data?.stat_date
    if (!/^\d{4}-\d{2}-\d{2}$/.test(day || '')) {
      ElMessage.error('服务未返回有效的统计日期，请查询核对后再操作')
      return
    }
    // Never write the date currently selected by the user; the server supplies today.
    query.statDate = day
    pageQuery.pageNum = 1
    appliedFilters.value = currentFilters()
    await loadRows()
    if (unmounted) return
    if (dataReady.value) ElMessage.success(`已重新计算并保存 ${day} 的库存明细及透视`)
    else ElMessage.warning('今日快照已保存，列表读取失败，请点击查询重试')
  } catch (error) {
    // The request interceptor displays server errors; no second write/retry is automatic.
  } finally {
    recalculating.value = false
  }
}

async function handleColumnApply(keys) {
  restoringSelection = true
  try {
    // Applying keys remounts the table immediately; do not block selection while
    // the unrelated preference save is still waiting for the server.
    const saving = applyColumnConfig(keys)
    await restorePageSelection()
    await saving
    ElMessage.success('列配置已保存')
  } catch (error) {
    ElMessage.warning('列配置已在本机应用，服务器保存失败')
  }
}

async function handleExport() {
  if (exporting.value || loading.value || !dataReady.value || filtersDirty.value || !checkPermi(['operations:ebayInventoryDetail:export'])) return
  exporting.value = true
  try {
    const data = await exportEbayInventoryDetail({
      ...appliedFilters.value,
      ...sort,
      selectedKeys: Array.from(selection.values())
    })
    if (!(data instanceof Blob)) throw new Error('导出响应不是文件，请稍后重试')
    const contentType = data.type.split(';')[0].toLowerCase()
    if (!blobValidate(data) || contentType === 'application/json' || contentType.endsWith('+json')) {
      const error = JSON.parse(await data.text())
      throw new Error(error.detail || error.msg || error.error || '导出失败，请稍后重试')
    }
    const signature = new Uint8Array(await data.slice(0, 4).arrayBuffer())
    if (signature[0] !== 0x50 || signature[1] !== 0x4b || signature[2] !== 0x03 || signature[3] !== 0x04) {
      throw new Error('服务未返回有效的 Excel 文件，请稍后重试')
    }
    const stamp = new Date().toLocaleString('sv-SE').replace(/[- :]/g, '')
    download.saveAs(data, `Ebay库存明细-${stamp}.xlsx`)
  } catch (error) {
    ElMessage.error(error?.message || '导出失败，请稍后重试')
  } finally {
    exporting.value = false
  }
}

const importDialogVisible = ref(false)
const importing = ref(false)
const gradeFile = ref(null)
const uploadRef = ref()
const importResultVisible = ref(false)
const importResult = ref({})
const importWarnings = computed(() => Array.isArray(importResult.value.warnings) ? importResult.value.warnings : [])

function handleGradeFileChange(file) {
  const raw = file.raw
  if (!raw || !/\.xlsx$/i.test(raw.name) || raw.size > 10 * 1024 * 1024) {
    ElMessage.warning('请选择不超过10 MB的 .xlsx 文件')
    gradeFile.value = null
    uploadRef.value?.clearFiles()
    ElMessage.success('等级已导入；请点击表格右上角刷新，重新计算并覆盖今日快照')
    return
  }
  gradeFile.value = raw
}

function handleGradeFileRemove() {
  gradeFile.value = null
}

function handleFileExceed() {
  ElMessage.warning('一次只导入一个文件，请先移除当前文件')
}

async function handleGradeImport() {
  if (!gradeFile.value || importing.value || !checkPermi(['operations:ebayInventoryDetail:import'])) return
  importing.value = true
  try {
    const response = await importEbayInventoryGrades(gradeFile.value)
    const result = response.data || {}
    importResult.value = result
    importResultVisible.value = true
    importDialogVisible.value = false
    gradeFile.value = null
    uploadRef.value?.clearFiles()
    await handleQuery()
  } catch (error) {
    // The shared request interceptor reports validation and transport errors.
  } finally {
    importing.value = false
  }
}

watch(() => [query.statDate, query.site, query.sku, query.brand, query.grade], clearSelection)
onMounted(async () => {
  appliedFilters.value = currentFilters()
  await Promise.all([initColumnConfig(), loadRows()])
})
onBeforeUnmount(() => {
  unmounted = true
  loadVersion += 1
})
</script>

<style scoped>
.inventory-detail-page { background: #f5f7fb; min-height: calc(100vh - 84px); color: #23324a; }
.view-switch { margin-bottom: 14px; }
.table-panel { background: #fff; border: 1px solid #e5eaf2; border-radius: 10px; padding: 18px; }
.query-form { border-bottom: 1px solid #edf0f5; padding: 0 0 2px; margin-bottom: 14px; }
.query-form :deep(.el-form-item) { margin-right: 20px; margin-bottom: 14px; }
.query-form :deep(.el-form-item__label) { color: #65758c; }
.query-actions :deep(.el-form-item__content) { gap: 8px; }
.query-actions :deep(.el-button + .el-button) { margin-left: 0; }
.table-toolbar { display: flex; align-items: center; justify-content: space-between; gap: 12px; margin-bottom: 14px; }
.selection-info { display: flex; align-items: center; gap: 16px; flex-wrap: wrap; font-size: 12px; color: #65758c; }
.selection-info b { color: #2a3951; font-weight: 600; }
.selected-text { color: #3d71bf; }
.pending-filter-text { color: #b88230; }
.muted { color: #94a0b1; }
.table-pagination { display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 12px; margin-top: 16px; padding-top: 14px; border-top: 1px solid #edf0f5; }
.page-range { color: #65758c; font-size: 12px; white-space: nowrap; }
.table-pagination :deep(.pagination-container) { margin-top: 0; max-width: 100%; overflow-x: auto; }
.inventory-table { --el-table-header-bg-color: #f4f7fc; --el-table-header-text-color: #51627c; --el-table-border-color: #e9edf4; --el-table-row-hover-bg-color: #edf4ff; border-radius: 6px; }
.inventory-table :deep(th.el-table__cell) { height: 46px; font-size: 12px; font-weight: 600; }
.inventory-table :deep(td.el-table__cell) { height: 44px; font-size: 12px; }
.column-heading { display: inline-flex; align-items: center; gap: 4px; cursor: help; }
.column-heading:focus-visible { outline: 2px solid #7297cd; outline-offset: 3px; border-radius: 2px; }
.column-tip { color: #9ba8bb; font-size: 12px; }
.column-help { width: min(540px, calc(100vw - 48px)); max-height: min(520px, calc(100vh - 80px)); overflow-y: auto; font-size: 12px; line-height: 1.7; color: #51627c; }
.column-help-title { color: #24486d; font-size: 13px; font-weight: 600; padding-bottom: 8px; border-bottom: 1px solid #e9edf4; }
.column-help dl { margin: 0; }
.column-help dl > div { display: grid; grid-template-columns: 64px minmax(0, 1fr); gap: 10px; padding-top: 9px; }
.column-help dt { font-weight: 600; color: #344d72; }
.column-help dd { margin: 0; white-space: pre-line; overflow-wrap: anywhere; }
.column-help-table { font-family: ui-monospace, Consolas, monospace; font-size: 11px; }
.sku-text { font-weight: 550; color: #344d72; }
.numeric-value { font-variant-numeric: tabular-nums; }
.empty-value { color: #b3bdcb; }
.grade-tag { border-radius: 4px; }
.rent-warning-value { display: inline-flex; align-items: center; gap: 4px; color: #b88230; }
.price-warning-value { display: inline-flex; align-items: center; gap: 4px; color: #b88230; }
.age-warning-value { display: inline-flex; align-items: center; gap: 4px; color: #b88230; }
.import-warning-list { padding: 12px; border-radius: 6px; background: #fff8ec; color: #947142; font-size: 12px; line-height: 1.9; }
.import-description { line-height: 1.8; color: #687991; font-size: 13px; margin: 16px 0; }
.upload-icon { font-size: 36px; color: #7297cd; margin-bottom: 12px; }
.upload-link { color: #409eff; }
@media (max-width: 600px) { .inventory-detail-page { padding: 12px; } .table-panel { padding: 12px; } .table-toolbar { align-items: flex-start; } .selection-info { gap: 8px; } }
</style>
