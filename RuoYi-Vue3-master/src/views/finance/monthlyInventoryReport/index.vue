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
          <el-popover
            v-hasPermi="['finance:monthlyInventoryReport:edit']"
            placement="bottom-start"
            :width="920"
            trigger="hover"
            :show-after="250"
          >
            <template #reference>
              <el-upload
                :show-file-list="false"
                :http-request="handleEbaySalesUpload"
                accept=".xlsx,.xlsm"
              >
                <el-button
                  type="warning"
                  :loading="ebaySalesUploading"
                  :disabled="!statMonth"
                >
                  上传eBay实际达成
                </el-button>
              </el-upload>
            </template>
            <div class="ebay-import-guide">
              <div class="ebay-import-guide__title">
                下载格式：进入SKU利润表导出数据，在“利润”模块勾选商品销售额和应收运费。
              </div>
              <el-image
                :src="ebaySalesFormatGuide"
                :preview-src-list="[ebaySalesFormatGuide]"
                preview-teleported
                fit="contain"
                class="ebay-import-guide__image"
              />
            </div>
          </el-popover>
          <el-button
            :disabled="!statMonth"
            @click="openEbayDetail"
          >
            查看eBay明细
          </el-button>
          <el-button
            type="success"
            :loading="localTransitSaving"
            :disabled="!statMonth || !editableSummaryRows.length"
            v-hasPermi="['finance:monthlyInventoryReport:edit']"
            @click="saveLocalTransitInputs"
          >
            保存本地仓在途
          </el-button>
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
            <template #default="{ row }">
              <span v-if="Number(row.is_total) === 1">{{ qty(row.local_end_in_transit_qty) }}</span>
              <el-input-number
                v-else
                v-model="row.local_end_in_transit_qty"
                :min="0"
                :precision="6"
                :controls="false"
                placeholder="请输入数量"
                style="width: 100%"
                @input="recalculateLocalTransitTotal"
              />
            </template>
          </el-table-column>
          <el-table-column prop="local_end_in_transit_total_cost" label="期末在途总成本" min-width="190" align="right">
            <template #default="{ row }">
              <span v-if="Number(row.is_total) === 1">{{ money(row.local_end_in_transit_total_cost) }}</span>
              <el-input-number
                v-else
                v-model="row.local_end_in_transit_total_cost"
                :min="0"
                :precision="6"
                :controls="false"
                placeholder="请输入金额"
                style="width: 100%"
                @input="recalculateLocalTransitTotal"
              />
            </template>
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

    <el-dialog
      v-model="ebayDetailVisible"
      :title="`${statMonth || ''} eBay实际达成明细`"
      width="1180px"
      append-to-body
    >
      <el-form :inline="true" @submit.prevent>
        <el-form-item label="负责人">
          <el-input
            v-model="ebayDetailQuery.principalName"
            clearable
            placeholder="负责人姓名"
            @keyup.enter="searchEbayDetail"
          />
        </el-form-item>
        <el-form-item label="SKU/品牌">
          <el-input
            v-model="ebayDetailQuery.keyword"
            clearable
            placeholder="SKU、品牌编码或负责人"
            @keyup.enter="searchEbayDetail"
          />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="searchEbayDetail">查询</el-button>
          <el-button @click="resetEbayDetail">重置</el-button>
        </el-form-item>
      </el-form>
      <el-table v-loading="ebayDetailLoading" :data="ebayDetailRows" border>
        <el-table-column label="图片" width="72" align="center">
          <template #default="{ row }">
            <el-image
              v-if="row.image_url"
              :src="row.image_url"
              :preview-src-list="[row.image_url]"
              preview-teleported
              fit="cover"
              style="width: 42px; height: 42px"
            />
          </template>
        </el-table-column>
        <el-table-column prop="sku" label="SKU" min-width="210" show-overflow-tooltip />
        <el-table-column prop="brand_code" label="品牌编码" width="105" />
        <el-table-column prop="principal_name" label="负责人" width="105" />
        <el-table-column prop="principal_match_source" label="匹配来源" width="145" />
        <el-table-column prop="multi_variant" label="多属性" width="85" align="center" />
        <el-table-column label="商品销售额" width="135" align="right">
          <template #default="{ row }">{{ money(row.product_sales_amount) }}</template>
        </el-table-column>
        <el-table-column label="应收运费" width="120" align="right">
          <template #default="{ row }">{{ money(row.receivable_shipping_amount) }}</template>
        </el-table-column>
        <el-table-column label="实际达成" width="135" align="right">
          <template #default="{ row }">{{ money(row.amount) }}</template>
        </el-table-column>
      </el-table>
      <pagination
        v-show="ebayDetailTotal > 0"
        :total="ebayDetailTotal"
        v-model:page="ebayDetailQuery.pageNum"
        v-model:limit="ebayDetailQuery.pageSize"
        @pagination="loadEbayDetail"
      />
    </el-dialog>

  </div>
</template>

<script setup>
import { computed, getCurrentInstance, onMounted, reactive, ref } from 'vue'
import ebaySalesFormatGuide from '@/assets/images/monthly-inventory/ebay-sku-profit-export-format.png'
import {
  getMonthlyInventorySummary,
  importMonthlyInventoryEbaySales,
  listMonthlyInventoryDetails,
  listMonthlyInventoryMonths,
  rebuildMonthlyInventoryReport,
  saveMonthlyInventoryManualInputs
} from '@/api/finance/monthlyInventoryReport'

const { proxy } = getCurrentInstance()

const availablePeriods = ref([])
const selectedYear = ref('')
const selectedMonth = ref('')
const summaryRows = ref([])
const periodsLoading = ref(false)
const summaryLoading = ref(false)
const calculating = ref(false)
const localTransitSaving = ref(false)
const ebaySalesUploading = ref(false)
const ebayDetailVisible = ref(false)
const ebayDetailLoading = ref(false)
const ebayDetailRows = ref([])
const ebayDetailTotal = ref(0)
const ebayDetailQuery = reactive({
  pageNum: 1,
  pageSize: 50,
  principalName: '',
  keyword: ''
})

const yearOptions = computed(() => {
  const values = new Set()
  availablePeriods.value.forEach(item => {
    const year = String(item.stat_month || '').slice(0, 4)
    if (/^20\d{2}$/.test(year)) {
      values.add(year)
    }
  })
  return [...values].sort((left, right) => Number(right) - Number(left))
})

const monthOptions = computed(() => {
  const values = new Set()
  availablePeriods.value.forEach(item => {
    const value = String(item.stat_month || '')
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

const businessMonthLabel = computed(() => {
  const month = Number(selectedMonth.value)
  if (!month) {
    return '次月'
  }
  return `${month === 12 ? 1 : month + 1}月`
})

const openingInventoryMonthLabel = computed(() => {
  const month = Number(selectedMonth.value)
  if (!month) {
    return '后月'
  }
  return `${((month + 1) % 12) + 1}月`
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

function nullableNumberValue(value) {
  const result = Number(value)
  return value !== null && value !== undefined && value !== ''
    && Number.isFinite(result) && result !== 0
    ? result
    : null
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

async function loadPeriods(initialize = false) {
  periodsLoading.value = true
  try {
    const response = await listMonthlyInventoryMonths(24)
    availablePeriods.value = response.data || []
    if (initialize || !selectedYear.value || !selectedMonth.value) {
      const latest = availablePeriods.value[0]?.stat_month
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
  if (!statMonth.value) {
    summaryRows.value = []
    return
  }
  summaryLoading.value = true
  try {
    const response = await getMonthlyInventorySummary(statMonth.value)
    summaryRows.value = (response.data?.items || []).map(item => ({
      ...item,
      local_end_in_transit_qty: Number(item.is_total) === 1
        ? numberValue(item.local_end_in_transit_qty)
        : nullableNumberValue(item.local_end_in_transit_qty),
      local_end_in_transit_total_cost: Number(item.is_total) === 1
        ? numberValue(item.local_end_in_transit_total_cost)
        : nullableNumberValue(item.local_end_in_transit_total_cost)
    }))
  } finally {
    summaryLoading.value = false
  }
}

function recalculateLocalTransitTotal() {
  const total = summaryRows.value.find(row => Number(row.is_total) === 1)
  if (!total) {
    return
  }
  total.local_end_in_transit_qty = editableSummaryRows.value.reduce(
    (sum, row) => sum + numberValue(row.local_end_in_transit_qty),
    0
  )
  total.local_end_in_transit_total_cost = editableSummaryRows.value.reduce(
    (sum, row) => sum + numberValue(row.local_end_in_transit_total_cost),
    0
  )
}

async function saveLocalTransitInputs() {
  if (!statMonth.value || !editableSummaryRows.value.length) {
    proxy.$modal.msgWarning('当前月份没有可填写的部门汇总数据')
    return
  }
  localTransitSaving.value = true
  try {
    await saveMonthlyInventoryManualInputs({
      stat_month: statMonth.value,
      items: editableSummaryRows.value.map(item => ({
        department_code: item.department_code,
        local_end_in_transit_qty: numberValue(item.local_end_in_transit_qty),
        local_end_in_transit_total_cost: numberValue(item.local_end_in_transit_total_cost)
      }))
    })
    proxy.$modal.msgSuccess('本地仓在途数据保存成功')
    await loadSummary()
  } finally {
    localTransitSaving.value = false
  }
}

async function handleCalculate() {
  if (!statMonth.value) {
    proxy.$modal.msgWarning('请先选择年份和月份')
    return
  }
  calculating.value = true
  try {
    const response = await rebuildMonthlyInventoryReport(statMonth.value)
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
    if (ebayDetailVisible.value) {
      await loadEbayDetail()
    }
  } finally {
    ebaySalesUploading.value = false
  }
}

async function openEbayDetail() {
  ebayDetailVisible.value = true
  ebayDetailQuery.pageNum = 1
  await loadEbayDetail()
}

async function loadEbayDetail() {
  if (!statMonth.value) {
    ebayDetailRows.value = []
    ebayDetailTotal.value = 0
    return
  }
  ebayDetailLoading.value = true
  try {
    const response = await listMonthlyInventoryDetails({
      sourceType: 'ebay_sales',
      statMonth: statMonth.value,
      principalName: ebayDetailQuery.principalName || undefined,
      keyword: ebayDetailQuery.keyword || undefined,
      pageNum: ebayDetailQuery.pageNum,
      pageSize: ebayDetailQuery.pageSize
    })
    ebayDetailRows.value = response.rows || []
    ebayDetailTotal.value = Number(response.total || 0)
  } finally {
    ebayDetailLoading.value = false
  }
}

async function searchEbayDetail() {
  ebayDetailQuery.pageNum = 1
  await loadEbayDetail()
}

async function resetEbayDetail() {
  ebayDetailQuery.principalName = ''
  ebayDetailQuery.keyword = ''
  ebayDetailQuery.pageNum = 1
  await loadEbayDetail()
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

:global(.ebay-import-guide__title) {
  margin-bottom: 10px;
  color: #606266;
  line-height: 1.5;
}

:global(.ebay-import-guide__image) {
  display: block;
  width: 100%;
  cursor: zoom-in;
}

.report-column-tip {
  cursor: help;
  border-bottom: 1px dashed #909399;
}

</style>
