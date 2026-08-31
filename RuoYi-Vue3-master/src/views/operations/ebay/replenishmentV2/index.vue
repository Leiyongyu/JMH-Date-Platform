<template>
  <div class="app-container ebay-replenishment-v2-page">
    <el-alert
      class="preview-alert"
      title="当前为 eBay补货2.0 前端展示版"
      description="页面字段、筛选、排序、分页和列配置已完成；当前数据仅用于验证展示效果，不会调用或写入原 eBay 补货接口。"
      type="info"
      :closable="false"
      show-icon
    />

    <el-form
      v-show="showSearch"
      ref="queryRef"
      :model="queryParams"
      :inline="true"
      label-width="72px"
      class="query-form"
    >
      <el-form-item label="站点" prop="site">
        <el-select v-model="queryParams.site" placeholder="全部站点" clearable style="width: 160px">
          <el-option v-for="site in siteOptions" :key="site" :label="site" :value="site" />
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
      <el-form-item label="产品等级" prop="productLevel">
        <el-select v-model="queryParams.productLevel" placeholder="全部等级" clearable style="width: 140px">
          <el-option v-for="level in productLevels" :key="level" :label="level" :value="level" />
        </el-select>
      </el-form-item>
      <el-form-item>
        <el-button type="primary" icon="Search" @click="handleQuery">搜索</el-button>
        <el-button icon="Refresh" @click="resetQuery">重置</el-button>
      </el-form-item>
    </el-form>

    <el-row :gutter="10" class="mb8 table-toolbar">
      <el-col :span="1.5">
        <el-tag type="warning" effect="plain">前端演示数据</el-tag>
      </el-col>
      <el-col :span="1.5" class="field-count">共 22 个业务字段</el-col>
      <right-toolbar
        v-model:showSearch="showSearch"
        :show-column-config="true"
        @queryTable="handleRefresh"
        @columnConfig="openColumnConfig"
      />
    </el-row>

    <el-table
      v-if="columnConfigLoaded"
      :key="columnTableKey"
      :data="pagedRows"
      border
      stripe
      height="640"
      :row-key="row => `${row.site}|${row.sku}`"
      :empty-text="emptyText"
      @sort-change="handleSortChange"
    >
      <template v-for="col in visibleColumns" :key="col.key">
        <el-table-column
          v-if="col.key === 'productLevel'"
          :label="col.label"
          :prop="col.key"
          :align="col.align"
          :width="col.width"
          :fixed="col.fixed || false"
          sortable="custom"
        >
          <template #default="scope">
            <el-tag v-if="scope.row.productLevel" :type="levelTagType(scope.row.productLevel)" effect="light">
              {{ scope.row.productLevel }}
            </el-tag>
            <span v-else>--</span>
          </template>
        </el-table-column>

        <el-table-column
          v-else
          :label="col.label"
          :prop="col.key"
          :align="col.align"
          :width="col.width"
          :fixed="col.fixed || false"
          :sortable="col.sortable ? 'custom' : false"
          :show-overflow-tooltip="col.tooltip"
        >
          <template #header>
            <span class="column-header">
              <span>{{ col.label }}</span>
              <el-tooltip v-if="col.tip" :content="col.tip" placement="top">
                <el-icon class="column-tip"><QuestionFilled /></el-icon>
              </el-tooltip>
            </span>
          </template>
          <template #default="scope">
            <strong v-if="col.key === 'suggestedReplenishmentQty' && hasValue(scope.row[col.key])" class="suggested-qty">
              {{ formatCell(scope.row[col.key], col) }}
            </strong>
            <span v-else>{{ formatCell(scope.row[col.key], col) }}</span>
          </template>
        </el-table-column>
      </template>
    </el-table>

    <pagination
      v-show="total > 0"
      :total="total"
      v-model:page="queryParams.pageNum"
      v-model:limit="queryParams.pageSize"
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

<script setup name="EbayReplenishmentV2">
import { computed, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { QuestionFilled } from '@element-plus/icons-vue'
import ColumnConfigDrawer from '@/components/ColumnConfigDrawer/index.vue'
import { useColumnConfig } from '@/composables/useColumnConfig'

const showSearch = ref(true)
const queryRef = ref(null)
const productLevels = ['A', 'B', 'C', 'D', 'E']
const fixedColumnKeys = ['site', 'sku']

const columnDefs = [
  { key: 'site', label: '站点', align: 'center', width: 90, fixed: 'left', sortable: true },
  { key: 'sku', label: 'SKU', align: 'left', width: 170, fixed: 'left', sortable: true, tooltip: true },
  { key: 'productName', label: '产品名称', align: 'left', width: 240, sortable: true, tooltip: true },
  { key: 'salesQty', label: '销量', align: 'right', width: 105, sortable: true, format: 'integer' },
  { key: 'grossProfitAmount', label: '毛利', align: 'right', width: 120, sortable: true, format: 'money', tip: '金额币种和计算口径将在后端接口接入时确定' },
  { key: 'returnQty', label: '退货量', align: 'right', width: 105, sortable: true, format: 'integer' },
  { key: 'returnAmount', label: '退货金额', align: 'right', width: 125, sortable: true, format: 'money', tip: '金额币种和计算口径将在后端接口接入时确定' },
  { key: 'forecastSalesQty', label: '预估销量', align: 'right', width: 115, sortable: true, format: 'integer' },
  { key: 'forecastGrossProfitAmount', label: '预估毛利', align: 'right', width: 125, sortable: true, format: 'money' },
  { key: 'forecastReturnQty', label: '预估退货', align: 'right', width: 115, sortable: true, format: 'integer' },
  { key: 'forecastReturnAmount', label: '预估退货金额', align: 'right', width: 140, sortable: true, format: 'money' },
  { key: 'sellThroughRatio', label: '动销比', align: 'right', width: 105, sortable: true, format: 'ratio', tip: '当前按比值展示，具体计算口径由后端规则确定' },
  { key: 'productLevel', label: '产品等级', align: 'center', width: 105, sortable: true },
  { key: 'chengduInTransitQty', label: '成都在途', align: 'right', width: 115, sortable: true, format: 'integer' },
  { key: 'chengduSellableQty', label: '成都可售', align: 'right', width: 115, sortable: true, format: 'integer' },
  { key: 'overseasInTransitQty', label: '海外在途', align: 'right', width: 115, sortable: true, format: 'integer' },
  { key: 'overseasSellableQty', label: '海外可售', align: 'right', width: 115, sortable: true, format: 'integer' },
  { key: 'chengduWarehouseToWarehouseDays', label: '成都仓到仓时间', align: 'right', width: 145, sortable: true, format: 'days', tip: '按时长展示，单位为天' },
  { key: 'chengduQcToWarehouseDays', label: '成都质检到仓时间', align: 'right', width: 160, sortable: true, format: 'days', tip: '按时长展示，单位为天' },
  { key: 'overseasTransitToListingDays', label: '海外在途到上架时间', align: 'right', width: 175, sortable: true, format: 'days', tip: '按时长展示，单位为天' },
  { key: 'safetyStockQty', label: '安全库存', align: 'right', width: 115, sortable: true, format: 'integer' },
  { key: 'suggestedReplenishmentQty', label: '建议补货量', align: 'right', width: 130, fixed: 'right', sortable: true, format: 'integer' }
]

const {
  showColumnDrawer,
  columnConfigLoaded,
  columnTableKey,
  visibleKeys,
  visibleColumns,
  openColumnConfig,
  initColumnConfig,
  applyColumnConfig
} = useColumnConfig('operations:ebay:replenishment:v2', columnDefs, fixedColumnKeys)

const queryParams = reactive({
  pageNum: 1,
  pageSize: 50,
  site: undefined,
  sku: undefined,
  productName: undefined,
  productLevel: undefined
})

const sortState = reactive({
  prop: undefined,
  order: undefined
})

// 仅用于前端结构验收；2.0 后端接入后替换为独立查询接口。
const sourceRows = ref([
  {
    site: '德国', sku: 'MCD-20150-0001', productName: '发动机冷却液节温器总成',
    salesQty: 126, grossProfitAmount: 18342.58, returnQty: 5, returnAmount: 1456.2,
    forecastSalesQty: 142, forecastGrossProfitAmount: 20586.45, forecastReturnQty: 6, forecastReturnAmount: 1680,
    sellThroughRatio: 1.28, productLevel: 'A', chengduInTransitQty: 80, chengduSellableQty: 46,
    overseasInTransitQty: 110, overseasSellableQty: 182, chengduWarehouseToWarehouseDays: 4,
    chengduQcToWarehouseDays: 3, overseasTransitToListingDays: 42, safetyStockQty: 96,
    suggestedReplenishmentQty: 74
  },
  {
    site: '英国', sku: 'BMW-30388-0557', productName: '汽车空气悬挂压缩机维修包',
    salesQty: 74, grossProfitAmount: 9256.32, returnQty: 2, returnAmount: 618.45,
    forecastSalesQty: 86, forecastGrossProfitAmount: 10880.5, forecastReturnQty: 2, forecastReturnAmount: 702.3,
    sellThroughRatio: 0.92, productLevel: 'B', chengduInTransitQty: 32, chengduSellableQty: 18,
    overseasInTransitQty: 60, overseasSellableQty: 94, chengduWarehouseToWarehouseDays: 5,
    chengduQcToWarehouseDays: 3, overseasTransitToListingDays: 38, safetyStockQty: 62,
    suggestedReplenishmentQty: 40
  },
  {
    site: '美国', sku: 'TYT-90050-0159', productName: '汽车换挡电机',
    salesQty: 51, grossProfitAmount: 6420.18, returnQty: 4, returnAmount: 980.6,
    forecastSalesQty: 58, forecastGrossProfitAmount: 7045.8, forecastReturnQty: 5, forecastReturnAmount: 1120,
    sellThroughRatio: 0.76, productLevel: 'C', chengduInTransitQty: 0, chengduSellableQty: 27,
    overseasInTransitQty: 36, overseasSellableQty: 45, chengduWarehouseToWarehouseDays: 4,
    chengduQcToWarehouseDays: null, overseasTransitToListingDays: 31, safetyStockQty: 48,
    suggestedReplenishmentQty: 25
  },
  {
    site: '法国', sku: 'DAS-10028-0021', productName: '车辆进气歧管控制阀',
    salesQty: 19, grossProfitAmount: 2145.9, returnQty: 0, returnAmount: 0,
    forecastSalesQty: 24, forecastGrossProfitAmount: 2720, forecastReturnQty: 1, forecastReturnAmount: 125,
    sellThroughRatio: 0.41, productLevel: 'D', chengduInTransitQty: 20, chengduSellableQty: 11,
    overseasInTransitQty: 0, overseasSellableQty: 38, chengduWarehouseToWarehouseDays: 5,
    chengduQcToWarehouseDays: 2, overseasTransitToListingDays: 36, safetyStockQty: 22,
    suggestedReplenishmentQty: 0
  },
  {
    site: '意大利', sku: 'FRD-70467-0557', productName: '汽车尾门锁执行器',
    salesQty: 8, grossProfitAmount: -186.3, returnQty: 1, returnAmount: 246.8,
    forecastSalesQty: 10, forecastGrossProfitAmount: null, forecastReturnQty: 1, forecastReturnAmount: null,
    sellThroughRatio: null, productLevel: 'E', chengduInTransitQty: 0, chengduSellableQty: 7,
    overseasInTransitQty: 0, overseasSellableQty: 16, chengduWarehouseToWarehouseDays: null,
    chengduQcToWarehouseDays: null, overseasTransitToListingDays: null, safetyStockQty: 12,
    suggestedReplenishmentQty: 0
  }
])

const siteOptions = computed(() => [...new Set(sourceRows.value.map(row => row.site).filter(Boolean))])

const filteredRows = computed(() => {
  const skuKeyword = String(queryParams.sku || '').trim().toLowerCase()
  const productKeyword = String(queryParams.productName || '').trim().toLowerCase()
  const rows = sourceRows.value.filter(row => {
    if (queryParams.site && row.site !== queryParams.site) return false
    if (queryParams.productLevel && row.productLevel !== queryParams.productLevel) return false
    if (skuKeyword && !String(row.sku || '').toLowerCase().includes(skuKeyword)) return false
    if (productKeyword && !String(row.productName || '').toLowerCase().includes(productKeyword)) return false
    return true
  })

  if (!sortState.prop || !sortState.order) return rows
  const direction = sortState.order === 'ascending' ? 1 : -1
  return [...rows].sort((leftRow, rightRow) => {
    const left = leftRow[sortState.prop]
    const right = rightRow[sortState.prop]
    if (left == null && right == null) return 0
    if (left == null) return 1
    if (right == null) return -1
    const leftNumber = Number(left)
    const rightNumber = Number(right)
    const compared = Number.isFinite(leftNumber) && Number.isFinite(rightNumber)
      ? leftNumber - rightNumber
      : String(left).localeCompare(String(right), 'zh-CN')
    return compared * direction
  })
})

const total = computed(() => filteredRows.value.length)
const pagedRows = computed(() => {
  const start = (queryParams.pageNum - 1) * queryParams.pageSize
  return filteredRows.value.slice(start, start + queryParams.pageSize)
})
const emptyText = computed(() => sourceRows.value.length
  ? '没有符合当前筛选条件的数据'
  : '后端接口待接入，暂无补货数据')

function handleQuery() {
  queryParams.pageNum = 1
}

function handleRefresh() {
  queryParams.pageNum = 1
}

function resetQuery() {
  queryRef.value?.resetFields()
  sortState.prop = undefined
  sortState.order = undefined
  queryParams.pageNum = 1
}

function handleSortChange({ prop, order }) {
  sortState.prop = order ? prop : undefined
  sortState.order = order || undefined
  queryParams.pageNum = 1
}

async function handleColumnApply(keys) {
  try {
    await applyColumnConfig(keys)
    ElMessage.success('列配置已保存')
  } catch (error) {
    ElMessage.warning('列配置已在当前浏览器生效，服务器保存失败')
  }
}

function hasValue(value) {
  return value !== null && value !== undefined && value !== ''
}

function formatCell(value, column) {
  if (!hasValue(value)) return '--'
  if (column.format === 'integer') return formatNumber(value, 0)
  if (column.format === 'money') return formatNumber(value, 2)
  if (column.format === 'ratio') return formatNumber(value, 2)
  if (column.format === 'days') return `${formatNumber(value, 0)} 天`
  return String(value)
}

function formatNumber(value, digits) {
  const number = Number(value)
  if (!Number.isFinite(number)) return '--'
  return number.toLocaleString('zh-CN', {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits
  })
}

function levelTagType(level) {
  const typeMap = { A: 'success', B: 'primary', C: 'warning', D: 'info', E: 'danger' }
  return typeMap[level] || 'info'
}

initColumnConfig()
</script>

<style scoped>
.ebay-replenishment-v2-page {
  min-height: calc(100vh - 84px);
  background: #f5f7fa;
}

.preview-alert {
  margin-bottom: 14px;
}

.query-form {
  padding: 14px 16px 0;
  margin-bottom: 12px;
  border: 1px solid #e4e7ed;
  border-radius: 6px;
  background: #fff;
}

.table-toolbar {
  align-items: center;
}

.field-count {
  color: #909399;
  font-size: 13px;
  line-height: 24px;
  white-space: nowrap;
}

.column-header {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  white-space: nowrap;
}

.column-tip {
  color: #909399;
  cursor: help;
}

.suggested-qty {
  color: #409eff;
}

:deep(.el-table .cell) {
  white-space: nowrap;
}
</style>
