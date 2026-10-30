<template>
  <div class="app-container clearance-page">
    <el-card shadow="never" class="hero-card">
      <div class="hero">
        <div>
          <div class="eyebrow">FINANCE / INVENTORY AGE</div>
          <h2>滞销清货</h2>
          <p>按 eBay、EU、US1、US2 及拆分后的 US3 组别，展示海外仓/FBA库龄成本与成都仓30天以上库存。</p>
        </div>
        <el-dropdown trigger="click" :disabled="costExporting || loading" @command="handleExport">
          <el-button class="cost-action-trigger" type="primary" plain :loading="costExporting" :disabled="loading">
            <el-icon><Download /></el-icon>
            <span>导出</span>
            <el-icon><ArrowDown /></el-icon>
          </el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="summary">导出当月汇总（组别 / 店铺 / 个人 / 站点）</el-dropdown-item>
              <el-dropdown-item command="detail">导出库龄明细</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
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
      <article v-for="bucket in drilldownBuckets" :key="bucket.key" class="summary-item" :class="bucket.tone">
        <span>{{ bucket.label }}</span>
        <strong>{{ number(summary[`${bucket.key}_sku_count`]) }} 个产品</strong>
        <small>{{ number(summary[`${bucket.key}_qty`]) }} 件 · {{ money(summary[`${bucket.key}_cost`]) }}</small>
      </article>
    </section>

    <el-card shadow="never" class="table-card">
      <template #header>
        <div class="table-header">
          <div>
            <div class="table-title">eBay / FBA 库龄组别汇总</div>
            <div class="table-hint">每段按有库存的中间码去重，同一中间码的不同品牌、供应商合并计一个产品；合计跨组、店铺、站点和个人再次去重，不相加各行产品数。成本沿用原口径；差值＝上月－本月。</div>
          </div>
          <el-tag effect="light">{{ summary.pull_month || '最新月份' }}</el-tag>
        </div>
      </template>

      <el-alert v-if="summary.unbucketed_rows" :title="`有 ${summary.unbucketed_rows} 条明细缺少可分段库龄，已保留在合计中，未推测分配到五个区间。`" type="warning" :closable="false" show-icon />
      <el-alert v-if="summary.missing_sku_rows" :title="`有 ${summary.missing_sku_rows} 条有库存的明细无法识别中间码，保留数量与成本，不计入去重产品数。`" type="warning" :closable="false" show-icon />
      <el-table
        v-loading="loading"
        :data="rows"
        border
        stripe
        :fit="true"
        :span-method="spanCtuUs3"
        show-summary :summary-method="groupSummary"
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
        <el-table-column v-for="bucket in drilldownBuckets" :key="bucket.key" :label="bucket.label" align="center">
          <el-table-column :prop="`${bucket.key}_sku_count`" label="去重SKU数（中间码）" min-width="165" align="right">
            <template #default="{ row }">{{ number(row[`${bucket.key}_sku_count`]) }}</template>
          </el-table-column>
          <el-table-column :prop="`${bucket.key}_qty`" label="库存数量" min-width="120" align="right">
            <template #default="{ row }">{{ number(row[`${bucket.key}_qty`]) }}</template>
          </el-table-column>
          <el-table-column :prop="`${bucket.key}_cost`" label="库龄成本" min-width="130" align="right">
            <template #default="{ row }">{{ money(row[`${bucket.key}_cost`]) }}</template>
          </el-table-column>
          <el-table-column :prop="bucket.previous" label="上月库龄成本" min-width="145" align="right">
            <template #default="{ row }">{{ moneyOrDash(row[bucket.previous]) }}</template>
          </el-table-column>
          <el-table-column :prop="`${bucket.key}_variance`" label="差值" min-width="135" align="right">
            <template #default="{ row }"><span :class="{ 'negative-value': isNegative(row[`${bucket.key}_variance`]) }">{{ moneyOrDash(row[`${bucket.key}_variance`]) }}</span></template>
          </el-table-column>
        </el-table-column>
        <el-table-column label="合计" align="center">
          <el-table-column prop="total_inventory_sku_count" label="去重SKU数（中间码）" min-width="165" align="right"><template #default="{ row }">{{ number(row.total_inventory_sku_count) }}</template></el-table-column>
          <el-table-column prop="total_inventory_qty" label="库存数量" min-width="120" align="right"><template #default="{ row }">{{ number(row.total_inventory_qty) }}</template></el-table-column>
          <el-table-column prop="total_inventory_cost" label="库龄成本" min-width="140" align="right"><template #default="{ row }">{{ money(row.total_inventory_cost) }}</template></el-table-column>
        </el-table-column>
        <el-table-column label="下钻" width="200" fixed="right" align="center">
          <template #default="{ row }">
            <el-button link type="primary" :disabled="loading" @click="openDrilldown(row)">
              {{ row.group_code === 'EBAY-1' ? '按站点查看' : '按店铺查看' }}
            </el-button>
            <el-button link type="primary" :disabled="loading" @click="openDrilldown(row, 'OWNER')">按个人查看</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-dialog v-model="drilldown.visible" :title="drilldown.title" width="94%" destroy-on-close @close="closeDrilldown">
      <p class="drilldown-hint">
        快照月份：{{ drilldown.month }}。仅拆分海外仓/FBA库龄；成都仓仍按组别展示。
        {{ drilldown.isEbay ? '美国东西仓合并 US，捷克仓归 DE；个人按各自快照月份的负责人规则匹配，未匹配计入未分配。' : '按中文店铺主体合并各国家站点，不按 SID 拆分；可识别同名店铺的共享仓一并汇总，不重复分摊。' }}
        个人按快照当月规则归属；仅上月存在的站点/店铺/负责人仍保留用于核对，当前数量及成本为 0；差值＝上月成本－本月成本。
      </p>
      <el-alert v-for="warning in drilldown.warnings" :key="warning" :title="warning" type="warning" :closable="false" show-icon />
      <el-alert v-if="drilldown.summary.unbucketed_rows" :title="`有 ${drilldown.summary.unbucketed_rows} 条明细缺少可分段库龄，仅保留在合计中。`" type="warning" :closable="false" show-icon />
      <el-alert v-if="drilldown.summary.missing_sku_rows" :title="`有 ${drilldown.summary.missing_sku_rows} 条有库存的明细无法识别中间码，不计入去重产品数。`" type="warning" :closable="false" show-icon />
      <el-alert v-if="drilldown.error" :title="drilldown.error" type="error" :closable="false" show-icon />
      <el-table v-loading="drilldown.loading" :data="drilldown.rows" border stripe show-summary :summary-method="drilldownSummary" max-height="65vh" class="age-table">
        <el-table-column prop="dimension_name" :label="drilldown.dimension === 'OWNER' ? '负责人' : drilldown.isEbay ? '站点' : '中文店铺名称'" min-width="240" fixed show-overflow-tooltip />
        <el-table-column prop="source_row_count" label="本月明细行数" width="120" align="right" />
        <el-table-column v-for="bucket in drilldownBuckets" :key="bucket.key" :label="bucket.label" align="center">
          <el-table-column :prop="`${bucket.key}_sku_count`" label="去重SKU数（中间码）" min-width="165" align="right">
            <template #default="{ row }">{{ number(row[`${bucket.key}_sku_count`]) }}</template>
          </el-table-column>
          <el-table-column :prop="`${bucket.key}_qty`" label="库存数量" min-width="120" align="right">
            <template #default="{ row }">{{ number(row[`${bucket.key}_qty`]) }}</template>
          </el-table-column>
          <el-table-column :prop="`${bucket.key}_cost`" label="库龄成本" min-width="140" align="right">
            <template #default="{ row }">{{ money(row[`${bucket.key}_cost`]) }}</template>
          </el-table-column>
          <el-table-column v-if="bucket.previous" :prop="bucket.previous" label="上月库龄成本" min-width="140" align="right">
            <template #default="{ row }">{{ moneyOrDash(row[bucket.previous]) }}</template>
          </el-table-column>
          <el-table-column v-if="bucket.previous" :prop="`${bucket.key}_variance`" label="差值" min-width="140" align="right">
            <template #default="{ row }">
              <span :class="{ 'negative-value': isNegative(row[`${bucket.key}_variance`]) }">{{ moneyOrDash(row[`${bucket.key}_variance`]) }}</span>
            </template>
          </el-table-column>
        </el-table-column>
        <el-table-column label="合计" align="center">
          <el-table-column prop="total_inventory_sku_count" label="去重SKU数（中间码）" min-width="165" align="right"><template #default="{ row }">{{ number(row.total_inventory_sku_count) }}</template></el-table-column>
          <el-table-column prop="total_inventory_qty" label="库存数量" min-width="120" align="right">
            <template #default="{ row }">{{ number(row.total_inventory_qty) }}</template>
          </el-table-column>
          <el-table-column prop="total_inventory_cost" label="库龄成本" min-width="140" align="right">
            <template #default="{ row }">{{ money(row.total_inventory_cost) }}</template>
          </el-table-column>
        </el-table-column>
      </el-table>
      <template #footer><el-button @click="drilldown.visible = false">关闭</el-button></template>
    </el-dialog>
  </div>
</template>

<script setup name="SlowMovingClearance">
import { getCurrentInstance, onMounted, reactive, ref } from 'vue'
import {
  exportInventoryAgeDetails,
  exportClearanceMonthlySummary,
  getSlowMovingClearanceOwners,
  getSlowMovingClearanceDimensions,
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
const drilldown = reactive({ visible: false, loading: false, title: '', month: '', isEbay: false, rows: [], error: '', dimension: '', warnings: [], summary: {} })
let drilldownRequest = 0
const drilldownBuckets = [
  ['0_90', '0–90天（健康）', ''], ['91_180', '91–180天（关注）', 'warning'],
  ['181_270', '181–270天（预警）', 'warning'], ['271_365', '271–365天（紧急）', 'danger'],
  ['365_plus', '365天以上（严重）', 'danger']
].map(([key, label, tone]) => ({ key: `inventory_${key}`, label, tone, previous: `previous_month_${key}_cost` }))

function closeDrilldown() {
  drilldownRequest++
  drilldown.rows = []
  drilldown.summary = {}
  drilldown.warnings = []
  drilldown.loading = false
}

function totalsRow({ columns, data }, totals) {
  return columns.map((column, index) => {
    if (index === 0) return '合计'
    const key = column.property
    if (!key || /region|group_name|dimension_name/.test(key)) return ''
    if (Object.prototype.hasOwnProperty.call(totals, key)) return /cost|variance/.test(key) ? moneyOrDash(totals[key]) : numberOrDash(totals[key])
    if (key.endsWith('_sku_count')) return '--'
    const values = data.map(row => row[key]).filter(value => value !== null && value !== undefined)
    if (!values.length) return '--'
    const total = values.reduce((sum, value) => sum + Number(value), 0)
    return /cost|variance/.test(key) ? money(total) : number(total)
  })
}
function drilldownSummary(input) { return totalsRow(input, drilldown.summary) }
function groupSummary(input) { return totalsRow(input, summary) }

async function openDrilldown(row, dimension) {
  if (loading.value) return
  const month = query.pullMonth || summary.pull_month
  if (!month) return
  const isOwner = dimension === 'OWNER'
  const request = ++drilldownRequest
  Object.assign(drilldown, {
    visible: true, loading: true, rows: [], error: '', month, warnings: [], summary: {},
    dimension: isOwner ? 'OWNER' : row.group_code === 'EBAY-1' ? 'SITE' : 'STORE',
    isEbay: row.group_code === 'EBAY-1',
    title: `${row.group_name} · ${month} · ${isOwner ? (row.group_code === 'EBAY-1' ? '个人库龄明细（全部站点）' : '个人库龄明细（全部店铺）') : row.group_code === 'EBAY-1' ? '站点库龄明细' : '店铺库龄明细'}`
  })
  try {
    const response = isOwner
      ? await getSlowMovingClearanceOwners(month, undefined, row.group_code)
      : await getSlowMovingClearanceDimensions(month, row.group_code)
    if (request === drilldownRequest) {
      drilldown.rows = response.data?.items || []
      drilldown.summary = response.data?.summary || {}
      drilldown.warnings = response.data?.warnings || []
    }
  } catch (error) {
    if (request === drilldownRequest) drilldown.error = '下钻数据加载失败，请关闭后重试'
  } finally {
    if (request === drilldownRequest) drilldown.loading = false
  }
}

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
  const first = rows.value.findIndex(item => item.group_code === 'US2-MJ')
  const second = rows.value.findIndex(item => item.group_code === 'US1-ZXY')
  if (first >= 0 && second === first + 1) {
    if (row.group_code === 'US2-MJ') return [2, 1]
    if (row.group_code === 'US1-ZXY') return [0, 0]
  }
  return [1, 1]
}

let listRequest = 0
async function loadData() {
  const request = ++listRequest
  loading.value = true
  try {
    const listResponse = await listSlowMovingClearance({ ...query })
    if (request !== listRequest) return
    rows.value = listResponse.rows || []
    Object.keys(summary).forEach(key => delete summary[key])
    Object.assign(summary, listResponse.summary || {})
    query.pullMonth = summary.pull_month || listResponse.pullMonth || query.pullMonth
  } catch (error) {
    if (request === listRequest) {
      rows.value = []
      Object.keys(summary).forEach(key => delete summary[key])
    }
  } finally {
    if (request === listRequest) loading.value = false
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
  drilldown.visible = false
  closeDrilldown()
  query.pageNum = 1
  loadData()
}

async function handleExport(command) {
  if (costExporting.value || loading.value) return
  const month = query.pullMonth || summary.pull_month
  if (!month) {
    proxy.$modal.msgError('请选择需要导出的快照月份')
    return
  }
  costExporting.value = true
  const label = command === 'summary' ? '滞销清货当月汇总' : '库龄明细'
  try {
    const data = await (command === 'summary' ? exportClearanceMonthlySummary(month) : exportInventoryAgeDetails(month))
    const blob = data instanceof Blob
      ? data
      : new Blob([data], {
          type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        })
    // Auth / backend failures may arrive as JSON blobs with HTTP 200.
    if (/json|text/i.test(blob.type)) {
      const text = await blob.text()
      let message = '导出失败，请重试'
      try {
        const error = JSON.parse(text)
        message = error.msg || error.detail || message
      } catch (_) { /* Do not download an error response as Excel. */ }
      proxy.$modal.msgError(message)
      return
    }
    const timestamp = new Date().toISOString().replace(/[-:T.Z]/g, '').slice(0, 14)
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = `${month}-${label}-${timestamp}.xlsx`
    document.body.appendChild(link)
    link.click()
    link.remove()
    URL.revokeObjectURL(url)
    proxy.$modal.msgSuccess(`${month} ${label}导出成功`)
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
  grid-template-columns: repeat(7, minmax(180px, 1fr));
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
.drilldown-hint { color: #64748b; line-height: 1.8; margin: 0 0 14px; }
.cost-action-trigger { min-width: 164px; }
.age-table :deep(.el-table__header th) { background: #f8fafc; color: #475569; }
@media (max-width: 768px) {
  .hero { align-items: flex-start; flex-direction: column; }
}
</style>
