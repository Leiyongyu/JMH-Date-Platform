<template>
  <div class="app-container monthly-inventory-report">
    <el-card shadow="never">
      <el-form :inline="true" class="report-filter" @submit.prevent>
        <el-form-item label="年份">
          <el-select
            v-model="selectedYear"
            placeholder="请选择年份"
            :loading="periodsLoading"
            style="width: 140px"
            @change="handleYearChange"
          >
            <el-option
              v-for="item in yearOptions"
              :key="item"
              :label="`${item}年`"
              :value="item"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="月份">
          <el-select
            v-model="selectedMonth"
            placeholder="请选择月份"
            style="width: 140px"
            @change="loadSummary"
          >
            <el-option
              v-for="item in monthOptions"
              :key="item"
              :label="`${Number(item)}月`"
              :value="item"
            />
          </el-select>
        </el-form-item>
        <el-form-item>
          <span
            v-hasPermi="['finance:monthlyInventoryReport:edit']"
            class="monthly-inventory-upload"
          >
            <el-dropdown
              trigger="click"
              @command="handleUploadCommand"
            >
              <el-button
                type="warning"
                :loading="ebaySalesUploading || purchaseOrderUploading"
                :disabled="!statMonth"
              >
                上传数据 ▾
              </el-button>
              <template #dropdown>
                <el-dropdown-menu>
                  <el-dropdown-item command="ebay" :disabled="!statMonth">
                    <el-popover
                      placement="right-start"
                      :width="920"
                      trigger="hover"
                      :show-after="250"
                    >
                      <template #reference>
                        <span class="monthly-inventory-upload__item">上传eBay实际达成</span>
                      </template>
                      <div class="inventory-import-guide">
                        <div class="inventory-import-guide__title">
                          下载格式：进入SKU利润表导出数据，在“利润”模块勾选商品销售额和应收运费。
                        </div>
                        <el-image
                          :src="ebaySalesFormatGuide"
                          :preview-src-list="[ebaySalesFormatGuide]"
                          preview-teleported
                          fit="contain"
                          class="inventory-import-guide__image"
                        />
                      </div>
                    </el-popover>
                  </el-dropdown-item>
                  <el-dropdown-item command="purchaseOrder" :disabled="!sourceStatMonth">
                    <el-popover
                      placement="right-start"
                      :width="920"
                      trigger="hover"
                      :show-after="250"
                    >
                      <template #reference>
                        <span class="monthly-inventory-upload__item">上传采购在途</span>
                      </template>
                      <div class="inventory-import-guide">
                        <div class="inventory-import-guide__title">
                          下载格式：采购单导出“产品信息”，勾选采购单号、采购仓库、SKU、店铺、单价和待到货量。
                        </div>
                        <el-image
                          :src="purchaseOrderFormatGuide"
                          :preview-src-list="[purchaseOrderFormatGuide]"
                          preview-teleported
                          fit="contain"
                          class="inventory-import-guide__image"
                        />
                      </div>
                    </el-popover>
                  </el-dropdown-item>
                </el-dropdown-menu>
              </template>
            </el-dropdown>
            <input
              ref="ebaySalesFileInput"
              type="file"
              accept=".xlsx,.xlsm"
              class="native-file-input"
              @change="handleEbaySalesFileChange"
            />
            <input
              ref="purchaseOrderFileInput"
              type="file"
              accept=".xlsx,.xlsm"
              class="native-file-input"
              @change="handlePurchaseOrderFileChange"
            />
          </span>
          <el-button
            type="primary"
            :loading="calculating"
            :disabled="!statMonth"
            v-hasPermi="['finance:monthlyInventoryReport:edit']"
            @click="handleCalculate"
          >
            计算
          </el-button>
        </el-form-item>
      </el-form>

      <el-table
        v-loading="summaryLoading"
        :data="summaryRows"
        border
        stripe
        :row-class-name="summaryRowClass"
        :span-method="spanLocalTransitUs3"
      >
        <el-table-column prop="department_name" label="部门" width="145" fixed="left">
          <template #default="{ row }">
            <strong>{{ row.department_name }}</strong>
          </template>
        </el-table-column>
        <el-table-column label="总货值" min-width="160" align="right" fixed="left">
          <template #default="{ row }">{{ money(totalGoodsValue(row)) }}</template>
        </el-table-column>

        <el-table-column label="本地仓" align="center">
          <el-table-column prop="local_end_in_transit_qty" label="期末在途数量" min-width="190" align="right">
            <template #default="{ row }">{{ qty(row.local_end_in_transit_qty) }}</template>
          </el-table-column>
          <el-table-column prop="local_end_in_transit_total_cost" label="期末在途总成本" min-width="190" align="right">
            <template #default="{ row }">{{ money(row.local_end_in_transit_total_cost) }}</template>
          </el-table-column>
          <el-table-column prop="local_end_inventory_qty" label="期末库存数量" min-width="130" align="right">
            <template #default="{ row }">{{ qty(row.local_end_inventory_qty) }}</template>
          </el-table-column>
          <el-table-column prop="local_end_inventory_total_cost" label="期末库存总成本" min-width="145" align="right">
            <template #default="{ row }">{{ money(row.local_end_inventory_total_cost) }}</template>
          </el-table-column>
        </el-table-column>

        <el-table-column label="海外仓/FBA仓" align="center">
          <el-table-column label="期末在途数量" min-width="130" align="right">
            <template #default="{ row }">
              {{ qty(combinedWarehouseValue(row, 'overseas_end_in_transit_qty', 'fba_end_in_transit_qty')) }}
            </template>
          </el-table-column>
          <el-table-column label="期末在途总成本" min-width="145" align="right">
            <template #default="{ row }">
              {{ money(combinedWarehouseValue(row, 'overseas_end_in_transit_total_cost', 'fba_end_in_transit_total_cost')) }}
            </template>
          </el-table-column>
          <el-table-column label="期末库存数量" min-width="130" align="right">
            <template #default="{ row }">
              {{ qty(combinedWarehouseValue(row, 'overseas_end_inventory_qty', 'fba_end_inventory_qty')) }}
            </template>
          </el-table-column>
          <el-table-column label="期末库存总成本" min-width="145" align="right">
            <template #default="{ row }">
              {{ money(combinedWarehouseValue(row, 'overseas_end_inventory_total_cost', 'fba_end_inventory_total_cost')) }}
            </template>
          </el-table-column>
        </el-table-column>

        <el-table-column label="FBA在途金额+FBA在库金额" min-width="210" align="right">
          <template #default="{ row }">{{ money(combinedWarehouseTotalAmount(row)) }}</template>
        </el-table-column>
        <el-table-column label="销售目标" min-width="175" align="right">
          <template #default="{ row }">{{ money(salesSprintTarget(row)) }}</template>
        </el-table-column>
        <el-table-column prop="actual_achievement_amount" label="实际达成" min-width="145" align="right">
          <template #default="{ row }">{{ money(row.actual_achievement_amount) }}</template>
        </el-table-column>
        <el-table-column prop="target_achievement_rate" label="目标达成率" min-width="135" align="right">
          <template #default="{ row }">{{ percent(row.target_achievement_rate) }}</template>
        </el-table-column>
        <el-table-column min-width="175" align="right">
          <template #header>
            <el-tooltip :content="turnoverValueTip" placement="top">
              <span class="report-column-tip">{{ businessMonthLabel }}周转天数（货值）</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">{{ optionalDecimal(turnoverDaysByValue(row)) }}</template>
        </el-table-column>
        <el-table-column
          :label="`${openingInventoryMonthLabel}初库存数量`"
          min-width="175"
          align="right"
        >
          <template #default="{ row }">{{ optionalQty(reportMetricValue(row, 'next_month_opening_inventory_qty')) }}</template>
        </el-table-column>
        <el-table-column :label="`${businessMonthLabel}销量`" min-width="125" align="right">
          <template #default="{ row }">{{ optionalQty(reportMetricValue(row, 'monthly_sales_qty')) }}</template>
        </el-table-column>
        <el-table-column
          :label="`${openingInventoryMonthLabel}初库销比`"
          min-width="165"
          align="right"
        >
          <template #default="{ row }">{{ optionalDecimal(openingInventorySalesRatio(row)) }}</template>
        </el-table-column>
        <el-table-column min-width="175" align="right">
          <template #header>
            <el-tooltip :content="turnoverSkuTip" placement="top">
              <span class="report-column-tip">{{ businessMonthLabel }}周转天数（SKU）</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">{{ optionalDecimal(turnoverDaysBySku(row)) }}</template>
        </el-table-column>
        <el-table-column label="90-180库龄成本" min-width="165" align="right">
          <template #default="{ row }">{{ optionalMoney(row.inventory_age_90_180_cost) }}</template>
        </el-table-column>
        <el-table-column label="180+库龄成本" min-width="155" align="right">
          <template #default="{ row }">{{ optionalMoney(row.inventory_age_180_plus_cost) }}</template>
        </el-table-column>
      </el-table>
    </el-card>

  </div>
</template>

<script setup>
import { computed, getCurrentInstance, onMounted, ref } from 'vue'
import ebaySalesFormatGuide from '@/assets/images/monthly-inventory/ebay-sku-profit-export-format.png'
import purchaseOrderFormatGuide from '@/assets/images/monthly-inventory/purchase-order-pending-arrival-export-fields.png'
import {
  getMonthlyInventorySummary,
  importMonthlyInventoryEbaySales,
  importMonthlyInventoryPurchaseOrder,
  listMonthlyInventoryMonths,
  rebuildMonthlyInventoryReport
} from '@/api/finance/monthlyInventoryReport'

const { proxy } = getCurrentInstance()

const availablePeriods = ref([])
const selectedYear = ref('')
const selectedMonth = ref('')
const summaryRows = ref([])
const periodsLoading = ref(false)
const summaryLoading = ref(false)
const calculating = ref(false)
const purchaseOrderUploading = ref(false)
const ebaySalesUploading = ref(false)
const ebaySalesFileInput = ref(null)
const purchaseOrderFileInput = ref(null)

function nextNaturalMonth(value) {
  if (!/^20\d{2}-(0[1-9]|1[0-2])$/.test(String(value || ''))) {
    return ''
  }
  const [year, month] = value.split('-').map(Number)
  const next = new Date(year, month, 1)
  return `${next.getFullYear()}-${String(next.getMonth() + 1).padStart(2, '0')}`
}

function periodReportMonth(item) {
  return String(item?.report_month || nextNaturalMonth(item?.stat_month))
}

const yearOptions = computed(() => {
  const values = new Set()
  availablePeriods.value.forEach(item => {
    const year = periodReportMonth(item).slice(0, 4)
    if (/^20\d{2}$/.test(year)) {
      values.add(year)
    }
  })
  return [...values].sort((left, right) => Number(right) - Number(left))
})

const monthOptions = computed(() => {
  const values = new Set()
  availablePeriods.value.forEach(item => {
    const value = periodReportMonth(item)
    if (value.startsWith(`${selectedYear.value}-`) && /^20\d{2}-(0[1-9]|1[0-2])$/.test(value)) {
      values.add(value.slice(5, 7))
    }
  })
  return [...values].sort((left, right) => Number(right) - Number(left))
})

const statMonth = computed(() => {
  if (!selectedYear.value || !selectedMonth.value) {
    return ''
  }
  return `${selectedYear.value}-${selectedMonth.value}`
})

const sourceStatMonth = computed(() => {
  const selected = availablePeriods.value.find(
    item => periodReportMonth(item) === statMonth.value
  )
  return String(selected?.stat_month || '')
})

const businessMonthLabel = computed(() => {
  const month = Number(selectedMonth.value)
  if (!month) {
    return '当月'
  }
  return `${month}月`
})

const openingInventoryMonthLabel = computed(() => {
  return businessMonthLabel.value
})

const turnoverValueTip = computed(
  () => `${businessMonthLabel.value}周转天数（目标小于120天）-货值`
)

const turnoverSkuTip = computed(
  () => `${businessMonthLabel.value}周转天数（目标小于120天）-SKU数量`
)

const editableSummaryRows = computed(() =>
  summaryRows.value.filter(row => Number(row.is_total) !== 1)
)

function numberValue(value) {
  const result = Number(value || 0)
  return Number.isFinite(result) ? result : 0
}

function qty(value) {
  return numberValue(value).toLocaleString('zh-CN', { maximumFractionDigits: 6 })
}

function money(value) {
  return numberValue(value).toLocaleString('zh-CN', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2
  })
}

function optionalQty(value) {
  return value === null || value === undefined || value === '' ? '' : qty(value)
}

function optionalDecimal(value) {
  if (value === null || value === undefined || value === '') {
    return ''
  }
  return numberValue(value).toLocaleString('zh-CN', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2
  })
}

function optionalMoney(value) {
  return value === null || value === undefined || value === '' ? '' : money(value)
}

function percent(value) {
  return `${(numberValue(value) * 100).toLocaleString('zh-CN', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2
  })}%`
}

function combinedWarehouseValue(row, overseasField, fbaField) {
  return numberValue(row?.[overseasField]) + numberValue(row?.[fbaField])
}

function combinedWarehouseTotalAmount(row) {
  return combinedWarehouseValue(
    row,
    'overseas_end_in_transit_total_cost',
    'fba_end_in_transit_total_cost'
  ) + combinedWarehouseValue(
    row,
    'overseas_end_inventory_total_cost',
    'fba_end_inventory_total_cost'
  )
}

function totalGoodsValue(row) {
  return numberValue(row?.local_end_in_transit_total_cost)
    + numberValue(row?.local_end_inventory_total_cost)
    + combinedWarehouseTotalAmount(row)
}

function departmentFactor(row) {
  const factors = {
    'EBAY-1': 0.45,
    'AMZ-EU': 0.3,
    'AMZ-US1': 0.4,
    'AMZ-US2': 0.4,
    'AMZ-US2-MJ': 0.4,
    'AMZ-US1-ZXY': 0.4
  }
  return factors[row?.department_code] || 0.4
}

function overseasFbaInventoryAmount(row) {
  return combinedWarehouseValue(
    row,
    'overseas_end_inventory_total_cost',
    'fba_end_inventory_total_cost'
  )
}

function turnoverDaysByValue(row) {
  if (Number(row?.is_total) === 1) {
    const actualAmount = editableSummaryRows.value.reduce(
      (sum, item) => sum + numberValue(item.actual_achievement_amount),
      0
    )
    if (!actualAmount) {
      return null
    }
    const adjustedInventoryAmount = editableSummaryRows.value.reduce(
      (sum, item) => sum + overseasFbaInventoryAmount(item) / departmentFactor(item),
      0
    )
    return adjustedInventoryAmount / 6.8 / actualAmount * 28
  }
  const actualAmount = numberValue(row?.actual_achievement_amount)
  if (!actualAmount) {
    return null
  }
  return overseasFbaInventoryAmount(row)
    / 6.8
    / departmentFactor(row)
    / actualAmount
    * 28
}

function hasReportMetric(value) {
  return value !== null && value !== undefined && value !== ''
}

function reportMetricValue(row, field) {
  if (Number(row?.is_total) !== 1) {
    return hasReportMetric(row?.[field]) ? numberValue(row[field]) : null
  }
  const values = editableSummaryRows.value.map(item => item?.[field])
  if (!values.length || values.some(value => !hasReportMetric(value))) {
    return null
  }
  return values.reduce((sum, value) => sum + numberValue(value), 0)
}

function openingInventorySalesRatio(row) {
  const openingInventoryQty = reportMetricValue(
    row,
    'next_month_opening_inventory_qty'
  )
  const monthlySalesQty = reportMetricValue(row, 'monthly_sales_qty')
  if (openingInventoryQty === null || !monthlySalesQty) {
    return null
  }
  const inTransitQty = combinedWarehouseValue(
    row,
    'overseas_end_in_transit_qty',
    'fba_end_in_transit_qty'
  )
  return (openingInventoryQty + inTransitQty) / monthlySalesQty
}

function turnoverDaysBySku(row) {
  const openingInventoryQty = reportMetricValue(
    row,
    'next_month_opening_inventory_qty'
  )
  const monthlySalesQty = reportMetricValue(row, 'monthly_sales_qty')
  if (openingInventoryQty === null || !monthlySalesQty) {
    return null
  }
  const inventoryQty = combinedWarehouseValue(
    row,
    'overseas_end_inventory_qty',
    'fba_end_inventory_qty'
  )
  const inTransitQty = combinedWarehouseValue(
    row,
    'overseas_end_in_transit_qty',
    'fba_end_in_transit_qty'
  )
  const averageInventoryQty = (
    openingInventoryQty + inventoryQty + inTransitQty / 2
  ) / 2
  return averageInventoryQty > 0
    ? 28 / (monthlySalesQty / averageInventoryQty)
    : 0
}

function salesSprintTarget(row) {
  if (Number(row?.is_total) === 1) {
    return editableSummaryRows.value.reduce(
      (sum, item) => sum + salesSprintTarget(item),
      0
    )
  }
  const inventoryAmount = overseasFbaInventoryAmount(row)
  const totalAmount = combinedWarehouseTotalAmount(row)
  const factor = departmentFactor(row)
  const inventoryTarget = inventoryAmount / 3 / factor / 6.6
  const totalTarget = totalAmount / 5 / factor / 6.6
  return (inventoryTarget + totalTarget) / 2
}

function summaryRowClass({ row }) {
  return Number(row.is_total) === 1 ? 'total-row' : ''
}

function spanLocalTransitUs3({ row, column }) {
  if (!['local_end_in_transit_qty', 'local_end_in_transit_total_cost'].includes(column.property)) {
    return [1, 1]
  }
  if (row.department_code === 'AMZ-US2-MJ') {
    return [2, 1]
  }
  if (row.department_code === 'AMZ-US1-ZXY') {
    return [0, 0]
  }
  return [1, 1]
}

async function loadPeriods(initialize = false) {
  periodsLoading.value = true
  try {
    const response = await listMonthlyInventoryMonths(24)
    availablePeriods.value = response.data || []
    if (initialize || !selectedYear.value || !selectedMonth.value) {
      const latest = periodReportMonth(availablePeriods.value[0])
      if (latest) {
        selectedYear.value = latest.slice(0, 4)
        selectedMonth.value = latest.slice(5, 7)
      } else {
        selectedYear.value = ''
        selectedMonth.value = ''
      }
    }
  } finally {
    periodsLoading.value = false
  }
}

async function handleYearChange() {
  if (!monthOptions.value.includes(selectedMonth.value)) {
    selectedMonth.value = monthOptions.value[0] || ''
  }
  await loadSummary()
}

async function loadSummary() {
  if (!sourceStatMonth.value) {
    summaryRows.value = []
    return
  }
  summaryLoading.value = true
  try {
    const response = await getMonthlyInventorySummary(sourceStatMonth.value)
    summaryRows.value = response.data?.items || []
  } finally {
    summaryLoading.value = false
  }
}

async function handleCalculate() {
  if (!sourceStatMonth.value) {
    proxy.$modal.msgWarning('请先选择年份和月份')
    return
  }
  calculating.value = true
  try {
    const response = await rebuildMonthlyInventoryReport(sourceStatMonth.value)
    const result = response.data || {}
    proxy.$modal.msgSuccess(
      `计算完成，共生成 ${result.department_summary_rows || 0} 条最终汇总数据`
    )
    await loadPeriods()
    await loadSummary()
  } finally {
    calculating.value = false
  }
}

async function handleEbaySalesUpload(options) {
  if (!statMonth.value) {
    proxy.$modal.msgWarning('请先选择上传数据所属的年份和月份')
    return
  }
  const file = options.file
  if (!/\.(xlsx|xlsm)$/i.test(file?.name || '')) {
    proxy.$modal.msgError('只支持.xlsx或.xlsm文件')
    return
  }
  ebaySalesUploading.value = true
  try {
    const response = await importMonthlyInventoryEbaySales(statMonth.value, file)
    const result = response.data || {}
    proxy.$modal.msgSuccess(
      `导入完成：${result.inserted_rows || 0}条，实际达成${money(result.total_amount)}`
    )
    await loadPeriods()
    await loadSummary()
  } finally {
    ebaySalesUploading.value = false
  }
}

function handleUploadCommand(command) {
  if (command === 'ebay') {
    ebaySalesFileInput.value?.click()
  } else if (command === 'purchaseOrder') {
    purchaseOrderFileInput.value?.click()
  }
}

async function handleEbaySalesFileChange(event) {
  const input = event.target
  const file = input.files?.[0]
  try {
    if (file) {
      await handleEbaySalesUpload({ file })
    }
  } finally {
    input.value = ''
  }
}

async function handlePurchaseOrderFileChange(event) {
  const input = event.target
  const file = input.files?.[0]
  try {
    if (file) {
      await handlePurchaseOrderUpload({ file })
    }
  } finally {
    input.value = ''
  }
}

async function handlePurchaseOrderUpload(options) {
  if (!sourceStatMonth.value) {
    proxy.$modal.msgWarning('请先选择年份和月份')
    return
  }
  const file = options.file
  if (!/\.(xlsx|xlsm)$/i.test(file?.name || '')) {
    proxy.$modal.msgError('只支持.xlsx或.xlsm文件')
    return
  }
  purchaseOrderUploading.value = true
  try {
    const response = await importMonthlyInventoryPurchaseOrder(sourceStatMonth.value, file)
    const result = response.data || {}
    proxy.$modal.msgSuccess(
      `导入完成：${result.inserted_rows || 0}条，待到货${qty(result.total_pending_arrival_qty)}，总成本${money(result.total_pending_cost)}`
    )
    await loadSummary()
  } finally {
    purchaseOrderUploading.value = false
  }
}

onMounted(async () => {
  await loadPeriods(true)
  await loadSummary()
})
</script>

<style scoped>
.report-filter {
  margin-bottom: 2px;
}

.monthly-inventory-report :deep(.el-table__header th) {
  background: #f5f7fa;
  color: #303133;
}

.monthly-inventory-report :deep(.total-row td) {
  background: #fff7e8 !important;
  font-weight: 700;
}

:global(.inventory-import-guide__title) {
  margin-bottom: 10px;
  color: #606266;
  line-height: 1.5;
}

:global(.inventory-import-guide__image) {
  display: block;
  width: 100%;
  cursor: zoom-in;
}

.monthly-inventory-upload {
  display: inline-flex;
  vertical-align: middle;
}

:global(.monthly-inventory-upload__item) {
  display: block;
  min-width: 150px;
}

.native-file-input {
  display: none;
}

.report-column-tip {
  cursor: help;
  border-bottom: 1px dashed #909399;
}

</style>
