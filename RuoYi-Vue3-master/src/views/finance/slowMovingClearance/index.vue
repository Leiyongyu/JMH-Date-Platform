<template>
  <div class="app-container clearance-page">
    <el-card shadow="never" class="hero-card">
      <div class="hero">
        <div>
          <div class="eyebrow">FINANCE / FBA INVENTORY AGE</div>
          <h2>滞销清货</h2>
          <p>按 EU、US1、US2 及拆分后的 US3 组别，展示 FBA 库龄成本与上月库存成本差异。</p>
        </div>
        <el-button
          v-hasPermi="['finance:slowMovingClearance:import']"
          type="primary"
          plain
          @click="openCostImportDialog"
        >
          <el-icon><Upload /></el-icon>
          导入上月库存成本
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
            <div class="table-title">FBA 库龄组别汇总</div>
            <div class="table-hint">欧洲组：EU；美国组：US1、US2、US2-MJ、US1-ZXY</div>
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

    <el-dialog
      v-model="costImportVisible"
      title="导入上月库存成本"
      width="560px"
      append-to-body
      :close-on-click-modal="false"
      @closed="resetCostImport"
    >
      <el-form label-width="96px">
        <el-form-item label="成本文件" required>
          <el-upload
            ref="costUploadRef"
            class="cost-upload"
            drag
            accept=".xlsx,.xlsm"
            :auto-upload="false"
            :limit="1"
            :on-change="handleCostFileChange"
            :on-remove="handleCostFileRemove"
          >
            <el-icon class="el-icon--upload"><UploadFilled /></el-icon>
            <div class="el-upload__text">拖入文件，或<em>点击选择</em></div>
            <template #tip>
              <div class="el-upload__tip">
                工作表名称必须为 YYYY-MM；同月重复导入将整月覆盖。该月份数据用于下一月快照的“上月库龄成本”和差值。
              </div>
            </template>
          </el-upload>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="costImportVisible = false">取消</el-button>
        <el-button type="primary" :loading="costImporting" @click="submitCostImport">
          开始导入
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup name="SlowMovingClearance">
import { getCurrentInstance, onMounted, reactive, ref } from 'vue'
import {
  getSlowMovingClearanceSummary,
  importInventoryAgeCost,
  listSlowMovingClearance,
  listSlowMovingClearanceMonths
} from '@/api/finance/slowMovingClearance'

const { proxy } = getCurrentInstance()
const loading = ref(false)
const monthsLoading = ref(false)
const costImportVisible = ref(false)
const costImporting = ref(false)
const costUploadRef = ref()
const costFile = ref()
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

function openCostImportDialog() {
  costFile.value = undefined
  costImportVisible.value = true
}

function handleCostFileChange(uploadFile) {
  costFile.value = uploadFile.raw
}

function handleCostFileRemove() {
  costFile.value = undefined
}

function resetCostImport() {
  costUploadRef.value?.clearFiles()
  costFile.value = undefined
}

function nextMonth(month) {
  const [year, monthNumber] = month.split('-').map(Number)
  const date = new Date(year, monthNumber, 1)
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}`
}

async function submitCostImport() {
  if (!costFile.value) {
    proxy.$modal.msgError('请选择库存成本Excel文件')
    return
  }
  costImporting.value = true
  try {
    const response = await importInventoryAgeCost(costFile.value)
    const result = response.data || {}
    costImportVisible.value = false
    proxy.$modal.msgSuccess(
      `${result.cost_month || ''} 库存成本导入完成，共${result.inserted_rows || 0}条；将用于下一月快照对比`
    )
    await loadMonths()
    const comparisonMonth = result.cost_month ? nextMonth(result.cost_month) : undefined
    if (comparisonMonth && snapshotMonths.value.some(item => item.pull_month === comparisonMonth)) {
      query.pullMonth = comparisonMonth
    }
    await loadData()
  } finally {
    costImporting.value = false
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
  grid-template-columns: repeat(4, minmax(180px, 1fr));
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
.cost-upload :deep(.el-upload),
.cost-upload :deep(.el-upload-dragger) { width: 100%; }
.age-table :deep(.el-table__header th) { background: #f8fafc; color: #475569; }
@media (max-width: 768px) {
  .hero { align-items: flex-start; flex-direction: column; }
}
</style>
