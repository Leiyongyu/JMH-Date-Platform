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
            @change="loadSummary"
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

        <el-table-column label="本地仓" align="center">
          <el-table-column prop="local_end_in_transit_qty" label="期末在途数量" min-width="130" align="right">
            <template #default="{ row }">{{ qty(row.local_end_in_transit_qty) }}</template>
          </el-table-column>
          <el-table-column prop="local_end_in_transit_total_cost" label="期末在途总成本" min-width="145" align="right">
            <template #default="{ row }">{{ money(row.local_end_in_transit_total_cost) }}</template>
          </el-table-column>
          <el-table-column prop="local_end_inventory_qty" label="期末库存数量" min-width="130" align="right">
            <template #default="{ row }">{{ qty(row.local_end_inventory_qty) }}</template>
          </el-table-column>
          <el-table-column prop="local_end_inventory_total_cost" label="期末库存总成本" min-width="145" align="right">
            <template #default="{ row }">{{ money(row.local_end_inventory_total_cost) }}</template>
          </el-table-column>
        </el-table-column>

        <el-table-column label="海外仓" align="center">
          <el-table-column prop="overseas_end_in_transit_qty" label="期末在途数量" min-width="130" align="right">
            <template #default="{ row }">{{ qty(row.overseas_end_in_transit_qty) }}</template>
          </el-table-column>
          <el-table-column prop="overseas_end_in_transit_total_cost" label="期末在途总成本" min-width="145" align="right">
            <template #default="{ row }">{{ money(row.overseas_end_in_transit_total_cost) }}</template>
          </el-table-column>
          <el-table-column prop="overseas_end_inventory_qty" label="期末库存数量" min-width="130" align="right">
            <template #default="{ row }">{{ qty(row.overseas_end_inventory_qty) }}</template>
          </el-table-column>
          <el-table-column prop="overseas_end_inventory_total_cost" label="期末库存总成本" min-width="145" align="right">
            <template #default="{ row }">{{ money(row.overseas_end_inventory_total_cost) }}</template>
          </el-table-column>
        </el-table-column>

        <el-table-column label="FBA仓" align="center">
          <el-table-column prop="fba_end_inventory_qty" label="期末库存(含移仓)数量" min-width="175" align="right">
            <template #default="{ row }">{{ qty(row.fba_end_inventory_qty) }}</template>
          </el-table-column>
          <el-table-column prop="fba_end_inventory_total_cost" label="期末库存(含移仓)总成本" min-width="190" align="right">
            <template #default="{ row }">{{ money(row.fba_end_inventory_total_cost) }}</template>
          </el-table-column>
          <el-table-column prop="fba_end_in_transit_qty" label="期末在途数量" min-width="130" align="right">
            <template #default="{ row }">{{ qty(row.fba_end_in_transit_qty) }}</template>
          </el-table-column>
          <el-table-column prop="fba_end_in_transit_total_cost" label="期末在途总成本" min-width="145" align="right">
            <template #default="{ row }">{{ money(row.fba_end_in_transit_total_cost) }}</template>
          </el-table-column>
        </el-table-column>
      </el-table>
    </el-card>
  </div>
</template>

<script setup>
import { computed, getCurrentInstance, onMounted, ref } from 'vue'
import {
  getMonthlyInventorySummary,
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

const currentYear = new Date().getFullYear()
const monthOptions = Array.from({ length: 12 }, (_item, index) =>
  String(index + 1).padStart(2, '0')
)

const yearOptions = computed(() => {
  const values = new Set()
  for (let year = currentYear; year >= currentYear - 5; year -= 1) {
    values.add(String(year))
  }
  availablePeriods.value.forEach(item => {
    const year = String(item.stat_month || '').slice(0, 4)
    if (/^20\d{2}$/.test(year)) {
      values.add(year)
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
        || `${currentYear}-${String(new Date().getMonth() + 1).padStart(2, '0')}`
      selectedYear.value = latest.slice(0, 4)
      selectedMonth.value = latest.slice(5, 7)
    }
  } finally {
    periodsLoading.value = false
  }
}

async function loadSummary() {
  if (!statMonth.value) {
    summaryRows.value = []
    return
  }
  summaryLoading.value = true
  try {
    const response = await getMonthlyInventorySummary(statMonth.value)
    summaryRows.value = response.data?.items || []
  } finally {
    summaryLoading.value = false
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
</style>
