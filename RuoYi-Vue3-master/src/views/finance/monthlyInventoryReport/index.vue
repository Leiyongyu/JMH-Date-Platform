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
                :loading="purchaseOrderUploading"
              >
                上传数据 ▾
              </el-button>
              <template #dropdown>
                <el-dropdown-menu>
                  <el-dropdown-item command="purchaseOrder">
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
            v-hasPermi="['finance:monthlyInventoryReport:edit']"
            @click="handleCalculate"
          >
            计算
          </el-button>
          <el-button
            :loading="exporting"
            v-hasPermi="['finance:monthlyInventoryReport:list']"
            @click="handleExport"
          >
            导出
          </el-button>
        </el-form-item>
      </el-form>

      <div class="dimension-switch">
        <el-radio-group v-model="activeDimension" @change="loadSummary">
          <el-radio-button value="group">组别</el-radio-button>
          <el-radio-button value="store">店铺</el-radio-button>
          <el-radio-button value="owner">个人</el-radio-button>
        </el-radio-group>
      </div>

      <el-table
        v-if="activeDimension === 'group'"
        v-loading="summaryLoading"
        :data="summaryRows"
        border
        stripe
        :row-class-name="summaryRowClass"
        :span-method="spanUs3MergedColumns"
      >
        <el-table-column prop="department_name" label="组别" width="145" fixed="left">
          <template #default="{ row }">
            <strong>{{ row.department_name }}</strong>
          </template>
        </el-table-column>
        <el-table-column label="总货值" min-width="160" align="right" fixed="left">
          <template #default="{ row }">{{ money(row.total_goods_value) }}</template>
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
          <template #default="{ row }">{{ money(row.fba_transit_inventory_amount) }}</template>
        </el-table-column>
        <el-table-column min-width="145" align="right">
          <template #header>
            <el-tooltip content="库龄大于180天的去重SKU数 ÷ 海外仓/FBA期末库存数量；同一SKU只计1个" placement="top">
              <span class="report-column-tip">库存健康度</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">{{ optionalPercent(row.inventory_health_rate) }}</template>
        </el-table-column>
        <el-table-column min-width="175" align="right">
          <template #header>
            <el-tooltip :content="usdRateTip" placement="top">
              <span class="report-column-tip">销售目标（USD）</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">{{ optionalMoney(salesSprintTarget(row)) }}</template>
        </el-table-column>
        <el-table-column prop="actual_achievement_amount_usd" min-width="155" align="right">
          <template #header>
            <el-tooltip :content="usdRateTip" placement="top">
              <span class="report-column-tip">实际达成（USD）</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">{{ optionalMoney(row.actual_achievement_amount_usd) }}</template>
        </el-table-column>
        <el-table-column prop="target_achievement_rate" label="目标达成率" min-width="135" align="right">
          <template #default="{ row }">{{ optionalPercent(row.target_achievement_rate) }}</template>
        </el-table-column>
        <el-table-column min-width="175" align="right">
          <template #header>
            <el-tooltip :content="turnoverValueTip" placement="top">
              <span class="report-column-tip">{{ nextBusinessMonthLabel }}周转天数（货值）</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">{{ optionalDecimal(row.turnover_days_by_value) }}</template>
        </el-table-column>
        <el-table-column
          :label="`${openingInventoryMonthLabel}初库存数量`"
          min-width="175"
          align="right"
        >
          <template #default="{ row }">{{ optionalQty(row.next_month_opening_inventory_qty) }}</template>
        </el-table-column>
        <el-table-column :label="`${businessMonthLabel}销量`" min-width="125" align="right">
          <template #default="{ row }">{{ optionalQty(row.monthly_sales_qty) }}</template>
        </el-table-column>
        <el-table-column
          :label="`${nextBusinessMonthLabel}初库销比`"
          min-width="165"
          align="right"
        >
          <template #default="{ row }">{{ optionalDecimal(row.opening_inventory_sales_ratio) }}</template>
        </el-table-column>
        <el-table-column min-width="175" align="right">
          <template #header>
            <el-tooltip :content="turnoverSkuTip" placement="top">
              <span class="report-column-tip">{{ businessMonthLabel }}周转天数（SKU）</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">{{ optionalDecimal(row.turnover_days_by_sku) }}</template>
        </el-table-column>
        <el-table-column prop="ctu_over_30_cost" min-width="190" align="right">
          <template #header>
            <el-tooltip content="成都中转仓31天及以上库龄货值；与库龄成本使用同一快照月份，US3两组合并显示" placement="top">
              <span class="report-column-tip">成都仓30天以上货值</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">{{ optionalMoney(row.ctu_over_30_cost) }}</template>
        </el-table-column>
        <el-table-column label="90-180库龄成本" min-width="165" align="right">
          <template #default="{ row }">{{ optionalMoney(row.inventory_age_90_180_cost) }}</template>
        </el-table-column>
        <el-table-column label="180+库龄成本" min-width="155" align="right">
          <template #default="{ row }">{{ optionalMoney(row.inventory_age_180_plus_cost) }}</template>
        </el-table-column>
      </el-table>

      <el-table
        v-else
        v-loading="summaryLoading"
        :data="dimensionDisplayRows"
        height="calc(100vh - 285px)"
        border
        stripe
        class="dimension-summary-table"
        :row-class-name="dimensionSummaryRowClass"
        empty-text="当前月份没有对应维度的汇总数据，请先点击计算"
      >
        <el-table-column
          prop="dimension_value"
          :label="activeDimension === 'store' ? '店铺' : '负责人'"
          min-width="190"
          fixed="left"
        >
          <template #default="{ row }">
            <strong>{{ dimensionName(row) }}</strong>
          </template>
        </el-table-column>
        <el-table-column prop="platform_code" label="平台" width="90" align="center" fixed="left">
          <template #default="{ row }">{{ platformLabel(row.platform_code) }}</template>
        </el-table-column>
        <el-table-column prop="department_code" label="组别" width="130" fixed="left" />
        <el-table-column label="总货值" min-width="150" align="right">
          <template #default="{ row }">{{ money(row.total_goods_value) }}</template>
        </el-table-column>

        <el-table-column label="海外仓/FBA仓" align="center">
          <el-table-column label="期末在途数量" min-width="125" align="right">
            <template #default="{ row }">
              {{ qty(combinedWarehouseValue(row, 'overseas_end_in_transit_qty', 'fba_end_in_transit_qty')) }}
            </template>
          </el-table-column>
          <el-table-column label="期末在途总成本" min-width="145" align="right">
            <template #default="{ row }">
              {{ money(combinedWarehouseValue(row, 'overseas_end_in_transit_total_cost', 'fba_end_in_transit_total_cost')) }}
            </template>
          </el-table-column>
          <el-table-column label="期末库存数量" min-width="125" align="right">
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
        <el-table-column
          prop="fba_transit_inventory_amount"
          label="FBA在途金额+FBA在库金额"
          min-width="210"
          align="right"
        >
          <template #default="{ row }">{{ money(row.fba_transit_inventory_amount) }}</template>
        </el-table-column>
        <el-table-column min-width="145" align="right">
          <template #header>
            <el-tooltip content="库龄大于180天的去重SKU数 ÷ 海外仓/FBA期末库存数量；同一SKU只计1个" placement="top">
              <span class="report-column-tip">库存健康度</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">{{ optionalPercent(row.inventory_health_rate) }}</template>
        </el-table-column>
        <el-table-column
          prop="sales_target_usd"
          min-width="150"
          align="right"
        >
          <template #header>
            <el-tooltip :content="usdRateTip" placement="top">
              <span class="report-column-tip">销售目标（USD）</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">{{ optionalMoney(row.sales_target_usd) }}</template>
        </el-table-column>
        <el-table-column
          prop="actual_achievement_amount_usd"
          min-width="150"
          align="right"
        >
          <template #header>
            <el-tooltip :content="usdRateTip" placement="top">
              <span class="report-column-tip">实际达成（USD）</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">{{ optionalMoney(row.actual_achievement_amount_usd) }}</template>
        </el-table-column>
        <el-table-column
          prop="target_achievement_rate"
          label="目标达成率"
          min-width="135"
          align="right"
        >
          <template #default="{ row }">{{ optionalPercent(row.target_achievement_rate) }}</template>
        </el-table-column>
      </el-table>
    </el-card>

  </div>
</template>

<script setup>
import { computed, getCurrentInstance, onMounted, ref } from 'vue'
import purchaseOrderFormatGuide from '@/assets/images/monthly-inventory/purchase-order-pending-arrival-export-fields.png'
import {
  exportMonthlyInventoryReport,
  getMonthlyInventoryDimensionSummary,
  getMonthlyInventorySummary,
  importMonthlyInventoryPurchaseOrder,
  listMonthlyInventoryMonths,
  rebuildMonthlyInventoryReport
} from '@/api/finance/monthlyInventoryReport'

const { proxy } = getCurrentInstance()

const availablePeriods = ref([])
const selectedYear = ref('')
const selectedMonth = ref('')
const activeDimension = ref('group')
const summaryRows = ref([])
const dimensionRows = ref([])
const dimensionTotalRow = ref(null)
const periodsLoading = ref(false)
const summaryLoading = ref(false)
const calculating = ref(false)
const exporting = ref(false)
const purchaseOrderUploading = ref(false)
const purchaseOrderFileInput = ref(null)

function nextNaturalMonth(value) {
  if (!/^20\d{2}-(0[1-9]|1[0-2])$/.test(String(value || ''))) {
    return ''
  }
  const [year, month] = value.split('-').map(Number)
  const next = new Date(year, month, 1)
  return `${next.getFullYear()}-${String(next.getMonth() + 1).padStart(2, '0')}`
}

function previousNaturalMonth(value) {
  if (!/^20\d{2}-(0[1-9]|1[0-2])$/.test(String(value || ''))) {
    return ''
  }
  const [year, month] = value.split('-').map(Number)
  const previous = new Date(year, month - 2, 1)
  return `${previous.getFullYear()}-${String(previous.getMonth() + 1).padStart(2, '0')}`
}

function currentNaturalMonth() {
  const current = new Date()
  return `${current.getFullYear()}-${String(current.getMonth() + 1).padStart(2, '0')}`
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

const nextBusinessMonthLabel = computed(() => {
  const nextMonth = nextNaturalMonth(statMonth.value)
  if (!nextMonth) {
    return '次月'
  }
  return `${Number(nextMonth.slice(5, 7))}月`
})

const turnoverValueTip = computed(
  () => `${nextBusinessMonthLabel.value}周转天数（目标小于120天）-货值`
)

const turnoverSkuTip = computed(
  () => `${businessMonthLabel.value}周转天数（目标小于120天）-SKU数量`
)

const editableSummaryRows = computed(() =>
  summaryRows.value.filter(row => Number(row.is_total) !== 1)
)

const usdRateInfo = computed(() => {
  const rows = summaryRows.value.length ? summaryRows.value : dimensionRows.value
  return rows.find(row => numberValue(row?.usd_rate) > 0) || null
})

const usdRateTip = computed(() => {
  const rateMonth = usdRateInfo.value?.rate_month || statMonth.value
  const rate = numberValue(usdRateInfo.value?.usd_rate)
  if (!rate) {
    return `${rateMonth || '当前月份'}未取得领星USD汇率，金额及达成率暂不计算`
  }
  return `按${rateMonth}领星USD我的汇率 ${rate.toLocaleString('zh-CN', { maximumFractionDigits: 6 })} 折算`
})

const dimensionDisplayRows = computed(() => {
  if (!dimensionRows.value.length) {
    return []
  }
  return dimensionTotalRow.value
    ? [dimensionTotalRow.value, ...dimensionRows.value]
    : dimensionRows.value
})
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

function optionalPercent(value) {
  if (value === null || value === undefined || value === '') {
    return ''
  }
  return percent(value)
}

function platformLabel(value) {
  const platform = String(value || '').toUpperCase()
  if (!platform) {
    return ''
  }
  return platform === 'EBAY' ? 'eBay' : 'Amazon'
}

function dimensionName(row) {
  if (Number(row?.is_dimension_total) === 1) {
    return activeDimension.value === 'store'
      ? '合计（仅Amazon FBA）'
      : '合计'
  }
  return row?.dimension_value || ''
}

function dimensionSummaryRowClass({ row }) {
  return Number(row?.is_dimension_total) === 1 ? 'dimension-total-row' : ''
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

function salesSprintTarget(row) {
  if (Number(row?.is_total) === 1) {
    const targets = editableSummaryRows.value.map(item => salesSprintTarget(item))
    return targets.length && targets.every(value => value !== null)
      ? targets.reduce((sum, value) => sum + value, 0)
      : null
  }
  const usdRate = numberValue(row?.usd_rate)
  if (!usdRate) {
    return null
  }
  const inventoryAmount = overseasFbaInventoryAmount(row)
  const totalAmount = combinedWarehouseTotalAmount(row)
  const factor = departmentFactor(row)
  const inventoryTarget = inventoryAmount / 3 / factor / usdRate
  const totalTarget = totalAmount / 5 / factor / usdRate
  return (inventoryTarget + totalTarget) / 2
}

function summaryRowClass({ row }) {
  return Number(row.is_total) === 1 ? 'total-row' : ''
}

function spanUs3MergedColumns({ row, column }) {
  if (![
    'local_end_in_transit_qty',
    'local_end_in_transit_total_cost',
    'ctu_over_30_cost'
  ].includes(column.property)) {
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
    dimensionRows.value = []
    dimensionTotalRow.value = null
    return
  }
  summaryLoading.value = true
  try {
    if (activeDimension.value === 'group') {
      const response = await getMonthlyInventorySummary(sourceStatMonth.value)
      summaryRows.value = response.data?.items || []
      dimensionRows.value = []
      dimensionTotalRow.value = null
    } else {
      const dimensionType = activeDimension.value === 'store' ? 'STORE' : 'OWNER'
      const response = await getMonthlyInventoryDimensionSummary(
        sourceStatMonth.value,
        dimensionType
      )
      dimensionRows.value = response.data?.items || []
      dimensionTotalRow.value = response.data?.total || null
      summaryRows.value = []
    }
  } finally {
    summaryLoading.value = false
  }
}

async function handleCalculate() {
  const reportMonth = currentNaturalMonth()
  const calculationMonth = previousNaturalMonth(reportMonth)
  calculating.value = true
  try {
    const response = await rebuildMonthlyInventoryReport(calculationMonth)
    const result = response.data || {}
    proxy.$modal.msgSuccess(
      `${reportMonth} 报表计算完成，共生成 ${result.department_summary_rows || 0} 条最终汇总数据`
    )
    await loadPeriods()
    await loadSummary()
  } finally {
    calculating.value = false
  }
}

function handleUploadCommand(command) {
  if (command === 'purchaseOrder') {
    purchaseOrderFileInput.value?.click()
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
  const reportMonth = currentNaturalMonth()
  const uploadMonth = previousNaturalMonth(reportMonth)
  const file = options.file
  if (!/\.(xlsx|xlsm)$/i.test(file?.name || '')) {
    proxy.$modal.msgError('只支持.xlsx或.xlsm文件')
    return
  }
  purchaseOrderUploading.value = true
  try {
    const response = await importMonthlyInventoryPurchaseOrder(uploadMonth, file)
    const result = response.data || {}
    proxy.$modal.msgSuccess(
      `导入完成：${result.inserted_rows || 0}条，待到货${qty(result.total_pending_arrival_qty)}，总成本${money(result.total_pending_cost)}`
    )
    await loadSummary()
  } finally {
    purchaseOrderUploading.value = false
  }
}

async function handleExport() {
  if (!sourceStatMonth.value) {
    proxy.$modal.msgError('请选择需要导出的月份')
    return
  }
  const dimensionType = activeDimension.value === 'group'
    ? 'GROUP'
    : activeDimension.value === 'store' ? 'STORE' : 'OWNER'
  const dimensionLabel = dimensionType === 'GROUP'
    ? '组别'
    : dimensionType === 'STORE' ? '店铺' : '负责人'
  exporting.value = true
  try {
    const data = await exportMonthlyInventoryReport(
      sourceStatMonth.value,
      dimensionType
    )
    const blob = data instanceof Blob
      ? data
      : new Blob([data], {
          type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        })
    const timestamp = new Date().toISOString()
      .replace(/[-:T.Z]/g, '')
      .slice(0, 14)
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = `${statMonth.value}-月度库存-${dimensionLabel}-${timestamp}.xlsx`
    document.body.appendChild(link)
    link.click()
    link.remove()
    URL.revokeObjectURL(url)
    proxy.$modal.msgSuccess(`${statMonth.value}月度库存${dimensionLabel}导出成功`)
  } catch (error) {
    const responseData = error?.response?.data
    const message = responseData instanceof Blob
      ? await responseData.text()
      : String(responseData?.msg || responseData || error?.message || '月度库存导出失败')
    proxy.$modal.msgError(message || '月度库存导出失败')
  } finally {
    exporting.value = false
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

.dimension-switch {
  margin: 4px 0 16px;
}

.dimension-summary-table {
  min-height: 360px;
}

.monthly-inventory-report :deep(.el-table__header th) {
  background: #f5f7fa;
  color: #303133;
}

.monthly-inventory-report :deep(.total-row td) {
  background: #fff7e8 !important;
  font-weight: 700;
}

.monthly-inventory-report :deep(.dimension-total-row td) {
  background: #eaf6ff !important;
  color: #1f4f73;
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
  margin-right: 12px;
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
