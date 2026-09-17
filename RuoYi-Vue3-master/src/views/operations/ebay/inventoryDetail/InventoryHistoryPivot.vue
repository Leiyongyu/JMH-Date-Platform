<template>
  <section class="pivot-panel">
    <el-form :model="query" :inline="true" class="pivot-query" @submit.prevent="handleQuery">
      <el-form-item label="统计日期">
        <el-date-picker v-model="query.dateRange" type="daterange" value-format="YYYY-MM-DD"
          start-placeholder="开始日期" end-placeholder="结束日期" range-separator="至"
          :disabled="!options.dates.length" :disabled-date="disabledStatDate" :editable="false"
          unlink-panels clearable style="width: 280px" />
      </el-form-item>
      <el-form-item label="负责人">
        <el-select v-model="query.owner" clearable filterable placeholder="全部负责人" style="width: 150px">
          <el-option v-for="owner in options.owners" :key="owner" :label="owner" :value="owner" />
        </el-select>
      </el-form-item>
      <el-form-item label="站点">
        <el-select v-model="query.site" clearable filterable placeholder="全部站点" style="width: 140px">
          <el-option v-for="site in options.sites" :key="site" :label="site" :value="site" />
        </el-select>
      </el-form-item>
      <el-form-item class="pivot-actions">
        <el-button type="primary" icon="Search" :disabled="loading" @click="handleQuery">查询</el-button>
        <el-button icon="Refresh" :disabled="loading" @click="resetQuery">重置</el-button>
        <el-button v-hasPermi="['operations:ebayInventoryDetail:export']" icon="Download"
          :loading="exporting" :disabled="loading || !dataReady || filtersDirty || total === 0"
          @click="handleExport">导出历史透视</el-button>
      </el-form-item>
    </el-form>

    <div class="pivot-toolbar">
      <span>共 <b>{{ total.toLocaleString() }}</b> 组负责人日期
        <span class="snapshot-count">｜{{ detailCount.toLocaleString() }} 条站点明细</span>
        <span class="snapshot-count">｜{{ snapshotCount }} 个统计日期</span>
        <span v-if="filtersDirty" class="pending-filter">筛选条件已更改，请点击查询</span>
      </span>
      <div class="pivot-display-actions">
        <el-checkbox v-model="onlyOwnerTotals">仅看负责人汇总</el-checkbox>
        <el-button icon="Refresh" :disabled="loading" @click="loadRows">刷新</el-button>
      </div>
    </div>
    <p class="history-note">每周一 07:30 随周报成功拉取后采集库存明细；历史按统计日期冻结，同日重新生成覆盖当日，跨日长期保留。负责人保留采集时归属，不随之后的规则调整改变。金额仅汇总有值数据，缺失金额不计入；已冻结历史中未记录的金额汇总不追溯重算。日期筛选仅可选择已有快照日期。</p>
    <p class="summary-note">每个统计日期按负责人汇总当前筛选站点，汇总行以红色加粗显示；筛选负责人并勾选“仅看负责人汇总”，可按日期查看每周变化。开关仅隐藏当前页站点明细，不改变分页或排序；导出始终包含全部筛选结果的站点明细和负责人汇总。</p>
    <el-alert v-if="dataReady && !options.dates.length" title="暂无历史快照，请等待周报任务成功采集。"
      type="info" :closable="false" show-icon class="empty-history" />

    <el-table ref="tableRef" v-loading="loading" :data="visibleRows" :row-key="rowKey" :row-class-name="rowClassName"
      :default-sort="defaultSort" border stripe height="620" class="pivot-table"
      empty-text="暂无符合条件的历史快照" @sort-change="handleSortChange">
      <el-table-column v-for="column in columns" :key="column.key" :prop="column.key"
        :label="column.label" :min-width="column.width || 145" :fixed="column.fixed"
        :align="column.format ? 'right' : 'left'" sortable="custom" :show-overflow-tooltip="!column.format">
        <template #header>
          <el-tooltip :content="column.tip" placement="top" :show-after="200">
            <span class="pivot-heading">{{ column.label }}<el-icon><QuestionFilled /></el-icon></span>
          </el-tooltip>
        </template>
        <template #default="{ row }">
          <el-tooltip v-if="column.key === 'stat_date'" :content="'统计年月：' + (row.stat_month || '--') + '；生成时间：' + (row.generated_at || '--') + '；库存源日期：' + (row.inventory_snapshot_date || '--') + '；库存拉取时间：' + (row.inventory_pulled_at || '--')" placement="top">
            <span>{{ row.stat_date || '--' }}</span>
          </el-tooltip>
          <el-tooltip v-else-if="missingMessage(row, column.key)" :content="missingMessage(row, column.key)" placement="top">
            <span class="missing-value">{{ formatValue(row[column.key], column.format) }} <el-icon><QuestionFilled /></el-icon></span>
          </el-tooltip>
          <span v-else :class="{ 'numeric-value': column.format }">{{ formatValue(row[column.key], column.format) }}</span>
        </template>
      </el-table-column>
    </el-table>
    <div class="pivot-pagination">
      <span class="page-range" role="status" aria-live="polite">
        当前显示 {{ pageRange.start.toLocaleString() }}–{{ pageRange.end.toLocaleString() }} 组负责人日期，共 {{ total.toLocaleString() }} 组
      </span>
      <div class="pagination-controls">
        <el-select :model-value="pageQuery.pageSize" aria-label="每页负责人日期组数" style="width: 125px"
          @change="handlePagination({ page: 1, limit: $event })">
          <el-option v-for="size in [10, 20, 30, 50, 100, 200]" :key="size" :label="size + ' 组/页'" :value="size" />
        </el-select>
        <Pagination v-model:page="pageQuery.pageNum" v-model:limit="pageQuery.pageSize"
          :total="total" :auto-scroll="false" layout="prev, pager, next, jumper" @pagination="handlePagination" />
      </div>
    </div>
  </section>
</template>

<script setup name="EbayInventoryHistoryPivot">
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { QuestionFilled } from '@element-plus/icons-vue'
import Pagination from '@/components/Pagination/index.vue'
import { listEbayInventoryPivot, exportEbayInventoryPivot } from '@/api/operations/ebay/inventoryDetail'
import download from '@/plugins/download'
import { blobValidate } from '@/utils/ruoyi'
import { checkPermi } from '@/utils/permission'

const rows = ref([])
const total = ref(0)
const loading = ref(false)
const exporting = ref(false)
const dataReady = ref(false)
const metadata = ref({})
const tableRef = ref()
const options = reactive({ owners: [], sites: [], dates: [] })
const query = reactive({ dateRange: [], owner: undefined, site: undefined })
const appliedFilters = ref({})
const filtersDirty = computed(() => JSON.stringify(currentFilters()) !== JSON.stringify(appliedFilters.value))
const pageQuery = reactive({ pageNum: 1, pageSize: 50 })
const sort = reactive({ sortField: 'stat_date', sortOrder: 'descending' })
const defaultSort = computed(() => ({ prop: sort.sortField, order: sort.sortOrder }))
const validDates = computed(() => new Set(options.dates))
const snapshotCount = computed(() => Number(metadata.value.snapshot_count || 0))
const detailCount = computed(() => Number(metadata.value.detail_count || 0))
const onlyOwnerTotals = ref(false)
const visibleRows = computed(() => onlyOwnerTotals.value ? rows.value.filter(isOwnerTotal) : rows.value)
const pageOwnerTotalCount = computed(() => rows.value.filter(isOwnerTotal).length)
const pageRange = computed(() => {
  if (!pageOwnerTotalCount.value || total.value <= 0) return { start: 0, end: 0 }
  const start = (pageQuery.pageNum - 1) * pageQuery.pageSize + 1
  return { start, end: Math.min(total.value, start + pageOwnerTotalCount.value - 1) }
})
let loadVersion = 0
let unmounted = false

const columns = [
  { key: 'owner', label: '负责人', width: 135, fixed: 'left', tip: '历史库存明细采集时匹配的负责人，归属已冻结；未分配记录也保留。' },
  { key: 'site', label: '站点', width: 120, fixed: 'left', tip: '沿用库存明细的仓库与站点映射；站点明细后附红色负责人汇总，仅汇总该日期当前筛选的站点。' },
  { key: 'stat_date', label: '统计日期', width: 145, tip: '按北京时间记录真实生成日期（YYYY-MM-DD）；同日覆盖，跨日长期保存。悬浮单元格可查看统计年月。' },
  { key: 'sku_count', label: 'SKU数', format: 'quantity', width: 110, tip: '新生成快照按站点＋中间码合并后计数，无有效中间码的SKU独立保留；负责人汇总为各站点计数之和，跨站点分别计数。旧日期保持原完整SKU计数，不追溯重算。' },
  { key: 'overseas_sellable_quantity', label: '海外可售', format: 'quantity', tip: '该负责人、站点下库存明细的海外可售数量合计。' },
  { key: 'overseas_total_quantity', label: '海外总库存', format: 'quantity', tip: '该负责人、站点下海外在途与海外可售之和；由库存明细汇总。' },
  { key: 'sales_qty_30d', label: '近30天销量', format: 'quantity', tip: '采集时库存明细的近30天销量合计；销量窗口跟随当时源数据最新付款日，不随查询历史的当前日期变动。' },
  { key: 'in_stock_sales_ratio', label: '可售库销比', format: 'percent', tip: '汇总海外可售 ÷ 汇总近30天销量，显示为百分比；销量为0时为0%。负责人汇总亦先加总各站点库存和销量再相除，不对SKU行或站点库销比求和或平均。' },
  { key: 'total_stock_sales_ratio', label: '总库销比', format: 'percent', tip: '汇总海外总库存 ÷ 汇总近30天销量，显示为百分比；销量为0时为0%。负责人汇总亦先加总各站点库存和销量再相除，不对SKU行或站点库销比求和或平均。' },
  { key: 'overseas_sellable_value', label: '海外可售货值', format: 'money', width: 160, tip: '采集时各SKU海外可售货值合计（人民币）；忽略缺失金额，仅汇总有值金额，0为有效值；该项金额全部缺失才显示--。已冻结历史中未记录的金额汇总不追溯重算，仍显示--。' },
  { key: 'overseas_total_value', label: '海外总货值', format: 'money', width: 160, tip: '采集时各SKU海外总货值合计（人民币）；忽略缺失金额，仅汇总有值金额，0为有效值；该项金额全部缺失才显示--。已冻结历史中未记录的金额汇总不追溯重算，仍显示--。' },
  { key: 'warehouse_rent_30d_cny', label: '30天谷仓仓租', format: 'money', width: 165, tip: '采集时各SKU的人民币仓租合计；匹配冲突、缺汇率或缺仓租数据造成的缺失金额不计入，仅汇总有值金额，0为有效值；该项金额全部缺失才显示--。已冻结历史中未记录的金额汇总不追溯重算，仍显示--。' }
]

function currentFilters() {
  const dates = query.dateRange || []
  return {
    startDate: dates[0] || undefined,
    endDate: dates[1] || undefined,
    owner: query.owner || undefined,
    site: query.site || undefined
  }
}

function disabledStatDate(value) {
  if (!(value instanceof Date) || Number.isNaN(value.getTime())) return true
  // Use local calendar components: toISOString() can move China's midnight to the previous day.
  const key = [value.getFullYear(), String(value.getMonth() + 1).padStart(2, '0'),
    String(value.getDate()).padStart(2, '0')].join('-')
  return !validDates.value.has(key)
}

function rowKey(row) {
  return JSON.stringify([row.stat_date, row.owner, row.site, row.row_type || 'DETAIL'])
}

function isOwnerTotal(row) {
  return row.row_type === 'OWNER_TOTAL'
}

function rowClassName({ row }) {
  return isOwnerTotal(row) ? 'owner-total-row' : ''
}

function formatValue(value, format) {
  if (value === null || value === undefined || String(value).trim() === '') return '--'
  if (!format) return String(value)
  const number = Number(value)
  if (!Number.isFinite(number)) return '--'
  if (format === 'percent') {
    return number.toLocaleString('zh-CN', { style: 'percent', minimumFractionDigits: 2, maximumFractionDigits: 2 })
  }
  const money = format === 'money'
  return (money ? '¥' : '') + number.toLocaleString('zh-CN', {
    minimumFractionDigits: money ? 2 : 0, maximumFractionDigits: money ? 2 : 0
  })
}

function missingMessage(row, key) {
  const isPrice = ['overseas_sellable_value', 'overseas_total_value'].includes(key)
  if (!isPrice && key !== 'warehouse_rent_30d_cny') return ''
  const missingCount = Number(row[isPrice ? 'missing_price_count' : 'missing_rent_count'] || 0)
  const reason = isPrice ? '缺少有效采购价' : '仓租无法完整计算'
  if (isOwnerTotal(row)) {
    return '按当前筛选站点的已冻结金额汇总相加，忽略空值，0为有效值；未记录的历史金额不追溯重算。'
      + (formatValue(row[key], 'money') === '--' ? '该项站点金额均无有效记录，合计显示--。' : '')
      + (missingCount > 0 ? '原快照记录有 ' + missingCount + ' 个SKU' + reason + '（跨站点分别计数）。' : '')
  }
  if (formatValue(row[key], 'money') !== '--') {
    return missingCount > 0
      ? '有 ' + missingCount + ' 个库存行存在缺失（' + reason + '），仅汇总有值金额；合并行只排除缺失部分，未将缺失值按0计算。'
      : ''
  }
  if (Number(row.sku_count) > 0 && missingCount >= Number(row.sku_count)) {
    return '该组 ' + missingCount + ' 个SKU' + reason + '，该项金额全部缺失，合计显示--，未将缺失值按0计算。'
  }
  return '历史该项未记录金额汇总，显示--；已冻结历史不追溯重算。'
    + (missingCount > 0 ? '该组有 ' + missingCount + ' 个SKU' + reason + '。' : '')
}

async function loadRows() {
  const version = ++loadVersion
  loading.value = true
  dataReady.value = false
  try {
    const response = await listEbayInventoryPivot({ ...appliedFilters.value, ...pageQuery, ...sort })
    if (unmounted || version !== loadVersion) return
    const data = response.data || {}
    rows.value = data.items || []
    total.value = Number(data.pagination?.total || 0)
    pageQuery.pageNum = Number(data.pagination?.page || pageQuery.pageNum)
    pageQuery.pageSize = Number(data.pagination?.page_size || pageQuery.pageSize)
    options.owners = data.options?.owners || []
    options.sites = data.options?.sites || []
    options.dates = data.options?.dates || []
    metadata.value = data.metadata || {}
    dataReady.value = true
  } catch (error) {
    // Shared request interceptor reports failure; keep the last view but disable export.
  } finally {
    if (!unmounted && version === loadVersion) loading.value = false
  }
}

function handleQuery() {
  const dates = query.dateRange || []
  if (dates.length && (dates.length !== 2 || dates.some(value => !validDates.value.has(value)) || dates[0] > dates[1])) {
    ElMessage.warning('请选择已有历史快照的统计日期，且开始日期不能晚于结束日期')
    return
  }
  appliedFilters.value = currentFilters()
  pageQuery.pageNum = 1
  return loadRows()
}

function resetQuery() {
  Object.assign(query, { dateRange: [], owner: undefined, site: undefined })
  Object.assign(sort, { sortField: 'stat_date', sortOrder: 'descending' })
  tableRef.value?.sort(sort.sortField, sort.sortOrder)
  return handleQuery()
}

function handlePagination({ page, limit }) {
  Object.assign(pageQuery, { pageNum: page, pageSize: limit })
  return loadRows()
}

function handleSortChange({ prop, order }) {
  const nextField = order ? prop : 'stat_date'
  const nextOrder = order || 'descending'
  if (!columns.some(column => column.key === nextField)) return
  if (sort.sortField === nextField && sort.sortOrder === nextOrder) return
  Object.assign(sort, { sortField: nextField, sortOrder: nextOrder })
  pageQuery.pageNum = 1
  return loadRows()
}

async function handleExport() {
  if (exporting.value || loading.value || !dataReady.value || filtersDirty.value || total.value === 0
    || !checkPermi(['operations:ebayInventoryDetail:export'])) return
  exporting.value = true
  try {
    const data = await exportEbayInventoryPivot({ ...appliedFilters.value, ...sort })
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
    download.saveAs(data, 'Ebay库存历史透视-' + stamp + '.xlsx')
  } catch (error) {
    ElMessage.error(error?.message || '导出失败，请稍后重试')
  } finally {
    exporting.value = false
  }
}

onMounted(() => {
  appliedFilters.value = currentFilters()
  loadRows()
})
onBeforeUnmount(() => {
  unmounted = true
  loadVersion += 1
})
</script>

<style scoped>
.pivot-panel { background: #fff; border: 1px solid #e5eaf2; border-radius: 10px; padding: 18px; color: #23324a; }
.pivot-query { border-bottom: 1px solid #edf0f5; padding-bottom: 2px; margin-bottom: 14px; }
.pivot-query :deep(.el-form-item) { margin-right: 16px; margin-bottom: 14px; }
.pivot-actions :deep(.el-form-item__content) { gap: 8px; }
.pivot-actions :deep(.el-button + .el-button) { margin-left: 0; }
.pivot-toolbar { display: flex; align-items: center; justify-content: space-between; gap: 12px; color: #65758c; font-size: 12px; }
.pivot-toolbar b { color: #2a3951; }
.pivot-display-actions { display: flex; align-items: center; gap: 16px; flex-shrink: 0; }
.snapshot-count { color: #8591a3; margin-left: 8px; }
.pending-filter { color: #b88230; margin-left: 12px; }
.history-note { color: #8591a3; font-size: 12px; line-height: 1.8; margin: 12px 0; }
.summary-note { color: #65758c; font-size: 12px; line-height: 1.8; margin: 0 0 12px; }
.empty-history { margin-bottom: 12px; }
.pivot-table { --el-table-header-bg-color: #f4f7fc; --el-table-header-text-color: #51627c; --el-table-border-color: #e9edf4; --el-table-row-hover-bg-color: #edf4ff; border-radius: 6px; }
.pivot-table :deep(th.el-table__cell) { height: 46px; font-size: 12px; }
.pivot-table :deep(td.el-table__cell) { height: 44px; font-size: 12px; }
.pivot-heading { display: inline-flex; align-items: center; gap: 4px; cursor: help; }
.pivot-heading .el-icon { color: #9ba8bb; font-size: 12px; }
.missing-value { display: inline-flex; align-items: center; gap: 4px; color: #b88230; }
.pivot-table :deep(.owner-total-row > td.el-table__cell) { background: #fff1f0 !important; color: #c62828; font-weight: 700; }
.pivot-table :deep(.owner-total-row .cell), .pivot-table :deep(.owner-total-row .missing-value) { color: #c62828; font-weight: 700; }
.numeric-value { font-variant-numeric: tabular-nums; }
.pivot-pagination { display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 12px; margin-top: 16px; padding-top: 14px; border-top: 1px solid #edf0f5; }
.page-range { color: #65758c; font-size: 12px; white-space: nowrap; }
.pagination-controls { display: flex; align-items: center; flex-wrap: wrap; gap: 12px; max-width: 100%; }
.pivot-pagination :deep(.pagination-container) { margin-top: 0; max-width: 100%; overflow-x: auto; }
@media (max-width: 600px) { .pivot-panel { padding: 12px; } .pivot-toolbar { align-items: flex-start; flex-wrap: wrap; } }
</style>
