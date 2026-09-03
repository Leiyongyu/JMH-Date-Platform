<template>
  <div class="app-container clearance-page">
    <el-card shadow="never" class="hero-card">
      <div class="hero">
        <div>
          <div class="eyebrow">FINANCE / INVENTORY AGE</div>
          <h2>滞销清货</h2>
          <p>按 eBay、EU、US1、US2 及拆分后的 US3 组别，展示海外仓/FBA库龄成本与成都仓30天以上库存。</p>
        </div>
        <el-button
          class="cost-action-trigger"
          type="primary"
          plain
          :loading="costExporting"
          @click="handleCostDetailExport"
        >
          <el-icon><Download /></el-icon>
          <span>导出库龄明细</span>
        </el-button>
      </div>
    </el-card>

    <section class="summary-grid">
      <article class="summary-item snapshot-item">
        <span>快照月份</span>
        <el-select
          v-model="query.pullMonth"
          class="snapshot-select"
          placeholder="暂无快照"
          :loading="monthsLoading"
          clearable
          @change="handleMonthChange"
        >
          <el-option
            v-for="item in snapshotMonths"
            :key="item.pull_month"
            :label="item.pull_month"
            :value="item.pull_month"
          />
        </el-select>
      </article>
      <article class="summary-item ctu">
        <el-tooltip content="成都中转仓31天及以上库龄；数据自2026-09起提供" placement="top">
          <span>30天以上成都仓数量 / 成本</span>
        </el-tooltip>
        <strong>{{ numberOrDash(summary.ctu_over_30_qty) }}</strong>
        <small>{{ moneyOrDash(summary.ctu_over_30_cost) }}</small>
      </article>
      <article class="summary-item">
        <span>0–90天数量 / 成本</span>
        <strong>{{ number(summary.inventory_0_90_qty) }}</strong>
        <small>{{ money(summary.inventory_0_90_cost) }}</small>
      </article>
      <article class="summary-item warning">
        <span>91–180天数量 / 成本</span>
        <strong>{{ number(summary.inventory_91_180_qty) }}</strong>
        <small>{{ money(summary.inventory_91_180_cost) }}</small>
      </article>
      <article class="summary-item danger">
        <span>181天以上数量 / 成本</span>
        <strong>{{ number(summary.inventory_181_plus_qty) }}</strong>
        <small>{{ money(summary.inventory_181_plus_cost) }}</small>
      </article>
    </section>

    <el-card shadow="never" class="table-card">
      <template #header>
        <div class="table-header">
          <div>
            <div class="table-title">eBay / FBA 库龄组别汇总</div>
            <div class="table-hint">eBay组：EBAY-1；欧洲组：EU；美国组：US1、US2、US2-MJ、US1-ZXY</div>
          </div>
          <el-tag effect="light">{{ summary.pull_month || '最新月份' }}</el-tag>
        </div>
      </template>

      <el-table
        v-loading="loading"
        :data="rows"
        border
        stripe
        :fit="true"
        :span-method="spanCtuUs3"
        class="age-table"
      >
        <el-table-column prop="region_name" label="区域" width="100" fixed>
          <template #default="{ row }">
            <el-tag :type="row.region_code === 'EBAY' ? 'warning' : row.region_code === 'EU' ? 'primary' : 'success'" effect="light">
              {{ row.region_name }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="group_name" label="组名" width="90" fixed>
          <template #default="{ row }"><strong>{{ row.group_name }}</strong></template>
        </el-table-column>
        <el-table-column prop="shop_count" label="店铺/仓库数" width="115" align="right">
          <template #default="{ row }">{{ number(row.shop_count) }}</template>
        </el-table-column>
        <el-table-column align="center">
          <template #header>
            <el-tooltip content="成都中转仓31天及以上库龄；数据自2026-09起提供" placement="top">
              <span>30天以上成都仓</span>
            </el-tooltip>
          </template>
          <el-table-column prop="ctu_over_30_qty" label="库存数量" min-width="120" align="right">
            <template #default="{ row }">{{ numberOrDash(row.ctu_over_30_qty) }}</template>
          </el-table-column>
          <el-table-column prop="ctu_over_30_cost" label="库龄成本" min-width="130" align="right">
            <template #default="{ row }">{{ moneyOrDash(row.ctu_over_30_cost) }}</template>
          </el-table-column>
        </el-table-column>
        <el-table-column label="0–90天" align="center">
          <el-table-column prop="inventory_0_90_qty" label="库存数量" min-width="120" align="right">
            <template #default="{ row }">{{ number(row.inventory_0_90_qty) }}</template>
          </el-table-column>
          <el-table-column prop="inventory_0_90_cost" label="库龄成本" min-width="130" align="right">
            <template #default="{ row }">{{ money(row.inventory_0_90_cost) }}</template>
          </el-table-column>
        </el-table-column>
        <el-table-column label="91–180天" align="center">
          <el-table-column prop="inventory_91_180_qty" label="库存数量" min-width="120" align="right">
            <template #default="{ row }">{{ number(row.inventory_91_180_qty) }}</template>
          </el-table-column>
          <el-table-column prop="inventory_91_180_cost" label="库龄成本" min-width="130" align="right">
            <template #default="{ row }">{{ money(row.inventory_91_180_cost) }}</template>
          </el-table-column>
          <el-table-column prop="previous_month_91_180_cost" label="上月库龄成本" min-width="145" align="right">
            <template #default="{ row }">{{ moneyOrDash(row.previous_month_91_180_cost) }}</template>
          </el-table-column>
          <el-table-column prop="inventory_91_180_variance" label="差值" min-width="135" align="right">
            <template #default="{ row }">
              <span :class="{ 'negative-value': isNegative(row.inventory_91_180_variance) }">
                {{ moneyOrDash(row.inventory_91_180_variance) }}
              </span>
            </template>
          </el-table-column>
        </el-table-column>
        <el-table-column label="181天以上" align="center">
          <el-table-column prop="inventory_181_plus_qty" label="库存数量" min-width="120" align="right">
            <template #default="{ row }">{{ number(row.inventory_181_plus_qty) }}</template>
          </el-table-column>
          <el-table-column prop="inventory_181_plus_cost" label="库龄成本" min-width="130" align="right">
            <template #default="{ row }">{{ money(row.inventory_181_plus_cost) }}</template>
          </el-table-column>
          <el-table-column prop="previous_month_181_plus_cost" label="上月库龄成本" min-width="145" align="right">
            <template #default="{ row }">{{ moneyOrDash(row.previous_month_181_plus_cost) }}</template>
          </el-table-column>
          <el-table-column prop="inventory_181_plus_variance" label="差值" min-width="135" align="right">
            <template #default="{ row }">
              <span :class="{ 'negative-value': isNegative(row.inventory_181_plus_variance) }">
                {{ moneyOrDash(row.inventory_181_plus_variance) }}
              </span>
            </template>
          </el-table-column>
        </el-table-column>
      </el-table>
    </el-card>

  </div>
</template>

<script setup name="SlowMovingClearance">
import { getCurrentInstance, onMounted, reactive, ref } from 'vue'
import {
  exportInventoryAgeDetails,
  getSlowMovingClearanceSummary,
  listSlowMovingClearance,
  listSlowMovingClearanceMonths
} from '@/api/finance/slowMovingClearance'

const { proxy } = getCurrentInstance()
const loading = ref(false)
const monthsLoading = ref(false)
const costExporting = ref(false)
const rows = ref([])
const snapshotMonths = ref([])
const summary = reactive({})
const query = reactive({
  pageNum: 1,
  pageSize: 20,
  pullMonth: undefined
})

function number(value) {
  return Number(value || 0).toLocaleString('zh-CN', {
    maximumFractionDigits: 2
  })
}

function numberOrDash(value) {
  return value === null || value === undefined ? '--' : number(value)
}

function money(value) {
  return `¥${Number(value || 0).toLocaleString('zh-CN', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2
  })}`
}

function moneyOrDash(value) {
  return value === null || value === undefined ? '--' : money(value)
}

function isNegative(value) {
  return value !== null && value !== undefined && Number(value) < 0
}

function spanCtuUs3({ row, column }) {
  if (!['ctu_over_30_qty', 'ctu_over_30_cost'].includes(column.property)) {
    return [1, 1]
  }
  if (row.group_code === 'US2-MJ') return [2, 1]
  if (row.group_code === 'US1-ZXY') return [0, 0]
  return [1, 1]
}

async function loadData() {
  loading.value = true
  try {
    const [listResponse, summaryResponse] = await Promise.all([
      listSlowMovingClearance(query),
      getSlowMovingClearanceSummary(query.pullMonth)
    ])
    rows.value = listResponse.rows || []
    Object.keys(summary).forEach(key => delete summary[key])
    Object.assign(summary, summaryResponse.data || {})
    query.pullMonth = summary.pull_month || listResponse.pullMonth || query.pullMonth
  } finally {
    loading.value = false
  }
}

async function loadMonths() {
  monthsLoading.value = true
  try {
    const response = await listSlowMovingClearanceMonths()
    snapshotMonths.value = response.data || []
  } finally {
    monthsLoading.value = false
  }
}

function handleMonthChange() {
  query.pageNum = 1
  loadData()
}

async function handleCostDetailExport() {
  const month = query.pullMonth || summary.pull_month
  if (!month) {
    proxy.$modal.msgError('请选择需要导出的快照月份')
    return
  }
  costExporting.value = true
  try {
    const data = await exportInventoryAgeDetails(month)
    const blob = data instanceof Blob
      ? data
      : new Blob([data], {
          type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        })
    const timestamp = new Date().toISOString().replace(/[-:T.Z]/g, '').slice(0, 14)
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = `${month}-库龄明细-${timestamp}.xlsx`
    document.body.appendChild(link)
    link.click()
    link.remove()
    URL.revokeObjectURL(url)
    proxy.$modal.msgSuccess(`${month} 库龄明细导出成功`)
  } finally {
    costExporting.value = false
  }
}

onMounted(() => Promise.all([loadMonths(), loadData()]))
</script>

<style scoped>
.clearance-page { background: #f6f8fb; min-height: calc(100vh - 84px); }
.hero-card,
.table-card { border-radius: 10px; margin-bottom: 16px; }
.hero {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 24px;
}
.hero h2 { margin: 5px 0 7px; color: #172033; font-size: 24px; }
.hero p { margin: 0; color: #64748b; }
.eyebrow { color: #2563eb; font-size: 12px; font-weight: 700; letter-spacing: 1px; }
.summary-grid {
  display: grid;
  grid-template-columns: repeat(5, minmax(180px, 1fr));
  gap: 10px;
  margin-bottom: 16px;
  overflow-x: auto;
  padding-bottom: 2px;
}
.summary-item {
  min-width: 0;
  min-height: 98px;
  padding: 14px 16px;
  border: 1px solid #e7ebf1;
  border-radius: 10px;
  background: #fff;
  box-sizing: border-box;
}
.summary-item span { display: block; color: #64748b; font-size: 12px; }
.summary-item strong {
  display: block;
  overflow: hidden;
  margin-top: 8px;
  color: #172033;
  font-size: clamp(17px, 1.25vw, 21px);
  text-overflow: ellipsis;
  white-space: nowrap;
}
.summary-item small { display: block; margin-top: 4px; color: #64748b; font-size: 13px; }
.summary-item.snapshot-item { border-top: 3px solid #2563eb; }
.summary-item.ctu { border-top: 3px solid #d97706; }
.summary-item.warning { border-top: 3px solid #f59e0b; }
.summary-item.danger { border-top: 3px solid #dc2626; }
.snapshot-select { width: 100%; margin-top: 9px; }
.snapshot-select :deep(.el-select__wrapper) {
  min-height: 34px;
  background: #f8fafc;
  box-shadow: 0 0 0 1px #dbe4f0 inset;
}
.table-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.table-title { color: #1e293b; font-size: 16px; font-weight: 650; }
.table-hint { margin-top: 4px; color: #94a3b8; font-size: 12px; }
.negative-value { color: #dc2626; }
.cost-action-trigger { min-width: 164px; }
.age-table :deep(.el-table__header th) { background: #f8fafc; color: #475569; }
@media (max-width: 768px) {
  .hero { align-items: flex-start; flex-direction: column; }
}
</style>
