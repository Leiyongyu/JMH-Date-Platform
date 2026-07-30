<template>
  <div class="app-container clearance-page">
    <el-card shadow="never" class="hero-card">
      <div class="hero">
        <div>
          <div class="eyebrow">FINANCE / FBA INVENTORY AGE</div>
          <h2>滞销清货</h2>
          <p>按 EU、US1、US2、US3 汇总展示 FBA 库龄库存数量及对应成本。</p>
        </div>
      </div>
    </el-card>

    <el-card shadow="never" class="filter-card">
      <el-form ref="queryRef" :model="query" inline label-width="72px">
        <el-form-item label="拉取月份" prop="pullMonth">
          <el-date-picker
            v-model="query.pullMonth"
            type="month"
            value-format="YYYY-MM"
            placeholder="默认最新月份"
            clearable
          />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" icon="Search" @click="handleQuery">查询</el-button>
          <el-button icon="Refresh" @click="resetQuery">重置</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <section class="summary-grid">
      <article class="summary-item">
        <span>快照月份</span>
        <strong>{{ summary.pull_month || query.pullMonth || '暂无' }}</strong>
      </article>
      <article class="summary-item">
        <span>库存总数量</span>
        <strong>{{ number(summary.total_inventory_qty) }}</strong>
      </article>
      <article class="summary-item">
        <span>库存总成本</span>
        <strong>{{ money(summary.total_inventory_cost) }}</strong>
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
      <article class="summary-item">
        <span>最近拉取时间</span>
        <strong class="time-value">{{ summary.pulled_at || '-' }}</strong>
      </article>
    </section>

    <el-card shadow="never" class="table-card">
      <template #header>
        <div class="table-header">
          <div>
            <div class="table-title">FBA 库龄组别汇总</div>
            <div class="table-hint">欧洲组：EU；美国组：US1、US2、US3</div>
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
        class="age-table"
      >
        <el-table-column prop="region_name" label="区域" width="100" fixed>
          <template #default="{ row }">
            <el-tag :type="row.region_code === 'EU' ? 'primary' : 'success'" effect="light">
              {{ row.region_name }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="group_name" label="组名" width="90" fixed>
          <template #default="{ row }"><strong>{{ row.group_name }}</strong></template>
        </el-table-column>
        <el-table-column prop="shop_count" label="店铺数" width="90" align="right">
          <template #default="{ row }">{{ number(row.shop_count) }}</template>
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
        </el-table-column>
        <el-table-column label="181天以上" align="center">
          <el-table-column prop="inventory_181_plus_qty" label="库存数量" min-width="120" align="right">
            <template #default="{ row }">
              <span class="age-danger">{{ number(row.inventory_181_plus_qty) }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="inventory_181_plus_cost" label="库龄成本" min-width="130" align="right">
            <template #default="{ row }">
              <span class="age-danger">{{ money(row.inventory_181_plus_cost) }}</span>
            </template>
          </el-table-column>
        </el-table-column>
        <el-table-column label="合计" align="center">
          <el-table-column prop="total_inventory_qty" label="库存数量" min-width="120" align="right">
            <template #default="{ row }">{{ number(row.total_inventory_qty) }}</template>
          </el-table-column>
          <el-table-column prop="total_inventory_cost" label="库龄成本" min-width="130" align="right">
            <template #default="{ row }">{{ money(row.total_inventory_cost) }}</template>
          </el-table-column>
        </el-table-column>
        <el-table-column prop="pulled_at" label="拉取时间" width="165" fixed="right" />
      </el-table>
    </el-card>
  </div>
</template>

<script setup name="SlowMovingClearance">
import { onMounted, reactive, ref } from 'vue'
import {
  getSlowMovingClearanceSummary,
  listSlowMovingClearance
} from '@/api/finance/slowMovingClearance'

const queryRef = ref()
const loading = ref(false)
const rows = ref([])
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

function money(value) {
  return `¥${Number(value || 0).toLocaleString('zh-CN', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2
  })}`
}

async function loadData() {
  loading.value = true
  try {
    const [listResponse, summaryResponse] = await Promise.all([
      listSlowMovingClearance(query),
      getSlowMovingClearanceSummary(query.pullMonth)
    ])
    rows.value = listResponse.rows || []
    Object.assign(summary, summaryResponse.data || {})
  } finally {
    loading.value = false
  }
}

function handleQuery() {
  query.pageNum = 1
  loadData()
}

function resetQuery() {
  queryRef.value?.resetFields()
  query.pageNum = 1
  loadData()
}

onMounted(loadData)
</script>

<style scoped>
.clearance-page { background: #f6f8fb; min-height: calc(100vh - 84px); }
.hero-card,
.filter-card,
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
  grid-template-columns: repeat(6, minmax(0, 1fr));
  gap: 12px;
  margin-bottom: 16px;
}
.summary-item {
  padding: 16px 18px;
  border: 1px solid #e7ebf1;
  border-radius: 10px;
  background: #fff;
}
.summary-item span { display: block; color: #64748b; font-size: 12px; }
.summary-item strong { display: block; margin-top: 8px; color: #172033; font-size: 21px; }
.summary-item small { display: block; margin-top: 4px; color: #64748b; font-size: 13px; }
.summary-item.warning { border-top: 3px solid #f59e0b; }
.summary-item.danger { border-top: 3px solid #dc2626; }
.summary-item .time-value { font-size: 13px; line-height: 26px; }
.table-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.table-title { color: #1e293b; font-size: 16px; font-weight: 650; }
.table-hint { margin-top: 4px; color: #94a3b8; font-size: 12px; }
.age-danger { color: #dc2626; font-weight: 700; }
.age-table :deep(.el-table__header th) { background: #f8fafc; color: #475569; }
@media (max-width: 1400px) {
  .summary-grid { grid-template-columns: repeat(3, minmax(0, 1fr)); }
}
@media (max-width: 768px) {
  .hero { align-items: flex-start; flex-direction: column; }
  .summary-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}
</style>
