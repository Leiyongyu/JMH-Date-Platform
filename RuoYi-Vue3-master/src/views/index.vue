<template>
  <div class="app-container home">
    <el-card v-if="hasInventoryPermission" class="trend-card" shadow="never">
      <template #header>
        <div class="card-header">
          <div>
            <div class="card-title">月度库存成本趋势</div>
            <div class="card-subtitle">数据来自月度库存组别汇总，展示各仓在途与库存成本</div>
          </div>
          <div class="filters">
            <el-radio-group v-model="viewMode" @change="handleModeChange">
              <el-radio-button value="year">按年</el-radio-button>
              <el-radio-button value="month">按月</el-radio-button>
            </el-radio-group>
            <el-select v-model="selectedYear" class="year-select" placeholder="年份" @change="handleYearChange">
              <el-option v-for="year in yearOptions" :key="year" :label="`${year}年`" :value="year" />
            </el-select>
            <el-select
              v-if="viewMode === 'month'"
              v-model="selectedMonth"
              class="month-select"
              placeholder="月份"
              @change="loadTrend"
            >
              <el-option
                v-for="month in monthOptions"
                :key="month"
                :label="`${Number(month)}月`"
                :value="month"
              />
            </el-select>
            <el-select
              v-if="viewMode === 'year'"
              v-model="selectedMetric"
              class="metric-select"
              placeholder="成本类型"
            >
              <el-option
                v-for="metric in METRICS"
                :key="metric.key"
                :label="metric.name"
                :value="metric.key"
              />
            </el-select>
          </div>
        </div>
      </template>

      <div v-loading="loading" class="trend-content">
        <el-empty v-if="!loading && !trendRows.length" description="当前筛选范围暂无月度库存数据" />
        <div v-else class="chart-panel">
          <InventoryCostTrendChart
            :title="currentChart.title"
            :x-axis-data="currentChart.xAxisData"
            :series="currentChart.series"
          />
        </div>
      </div>
    </el-card>
  </div>
</template>

<script setup name="Index">
import { computed, onMounted, ref } from 'vue'
import auth from '@/plugins/auth'
import InventoryCostTrendChart from '@/components/InventoryCostTrendChart/index.vue'
import { getMonthlyInventoryCostTrend } from '@/api/finance/monthlyInventoryReport'

const DEPARTMENTS = [
  { code: 'EBAY-1', name: 'EBAY-1' },
  { code: 'AMZ-EU', name: 'AMZ-EU' },
  { code: 'AMZ-US1', name: 'AMZ-US1' },
  { code: 'AMZ-US2', name: 'AMZ-US2' },
  { code: 'AMZ-US2-MJ', name: 'AMZ-US2-MJ' },
  { code: 'AMZ-US1-ZXY', name: 'AMZ-US1-ZXY' }
]

const METRICS = [
  { key: 'local_in_transit_cost', name: '本地仓在途成本' },
  { key: 'local_inventory_cost', name: '本地仓库存成本' },
  { key: 'overseas_fba_in_transit_cost', name: '海外仓/FBA在途成本' },
  { key: 'overseas_fba_inventory_cost', name: '海外仓/FBA库存成本' }
]

const hasInventoryPermission = computed(() => auth.hasPermi('finance:monthlyInventoryReport:list'))
const loading = ref(false)
const viewMode = ref('year')
const selectedYear = ref('')
const selectedMonth = ref('')
const selectedMetric = ref(METRICS[3].key)
const periods = ref([])
const trendRows = ref([])

const yearOptions = computed(() => [...new Set(
  periods.value.map(item => String(item.report_month || '').slice(0, 4)).filter(Boolean)
)].sort((a, b) => b.localeCompare(a)))

const monthOptions = computed(() => [...new Set(
  periods.value
    .map(item => String(item.report_month || ''))
    .filter(value => value.startsWith(`${selectedYear.value}-`))
    .map(value => value.slice(5, 7))
)].sort((a, b) => b.localeCompare(a)))

const annualChart = computed(() => {
  const months = [...new Set(trendRows.value.map(row => row.report_month))].sort()
  const metric = METRICS.find(item => item.key === selectedMetric.value) || METRICS[3]
  return {
    title: `${selectedYear.value}年各组${metric.name}趋势对比`,
    xAxisData: months.map(month => `${Number(month.slice(5, 7))}月`),
    series: DEPARTMENTS.map(department => {
      const rows = trendRows.value.filter(row => row.department_code === department.code)
      const byMonth = Object.fromEntries(rows.map(row => [row.report_month, row]))
      return {
        name: department.name,
        data: months.map(month => {
          const row = byMonth[month]
          return row ? Number(row[metric.key] || 0) : null
        })
      }
    })
  }
})

const monthlyChart = computed(() => {
  const byDepartment = Object.fromEntries(
    trendRows.value.map(row => [row.department_code, row])
  )
  return {
    title: `${selectedYear.value}年${Number(selectedMonth.value || 0)}月各组仓库成本对比`,
    xAxisData: METRICS.map(metric => metric.name),
    series: DEPARTMENTS.map(department => ({
      name: department.name,
      data: METRICS.map(metric => Number(
        byDepartment[department.code]?.[metric.key] || 0
      ))
    }))
  }
})

const currentChart = computed(() => (
  viewMode.value === 'year' ? annualChart.value : monthlyChart.value
))

async function loadTrend() {
  if (!hasInventoryPermission.value) return
  loading.value = true
  try {
    const response = await getMonthlyInventoryCostTrend(
      selectedYear.value || undefined,
      viewMode.value === 'month' ? selectedMonth.value || undefined : undefined
    )
    const data = response.data || {}
    periods.value = data.periods || []
    trendRows.value = data.items || []
    selectedYear.value ||= data.year || yearOptions.value[0] || ''
    if (!selectedMonth.value || !monthOptions.value.includes(selectedMonth.value)) {
      selectedMonth.value = monthOptions.value[0] || ''
    }
  } finally {
    loading.value = false
  }
}

async function handleYearChange() {
  selectedMonth.value = monthOptions.value[0] || ''
  await loadTrend()
}

async function handleModeChange() {
  if (viewMode.value === 'month' && !selectedMonth.value) {
    selectedMonth.value = monthOptions.value[0] || ''
  }
  await loadTrend()
}

onMounted(loadTrend)
</script>

<style scoped lang="scss">
.home {
  padding: 20px;
  min-height: calc(100vh - 84px);
  background: #f5f7fb;
}

.trend-card {
  border: 0;
  border-radius: 12px;
}

.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 20px;
}

.card-title {
  color: #172033;
  font-size: 19px;
  font-weight: 650;
}

.card-subtitle {
  margin-top: 6px;
  color: #8491a7;
  font-size: 13px;
}

.filters {
  display: flex;
  align-items: center;
  gap: 10px;
}

.year-select {
  width: 118px;
}

.month-select {
  width: 100px;
}

.metric-select {
  width: 190px;
}

.trend-content {
  min-height: 350px;
}

.chart-panel {
  overflow: hidden;
  border: 1px solid #e8edf5;
  border-radius: 10px;
  background: #fff;
}

@media (max-width: 1100px) {
  .card-header {
    align-items: flex-start;
    flex-direction: column;
  }
}

@media (max-width: 640px) {
  .home {
    padding: 10px;
  }
  .filters {
    align-items: stretch;
    flex-wrap: wrap;
  }
}
</style>
