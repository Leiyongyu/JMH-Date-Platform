<template>
  <section class="age-ratio-panel" v-loading="loading">
    <div class="age-ratio-toolbar">
      <el-radio-group v-model="dimension" aria-label="库龄统计维度">
        <el-radio-button value="owners">个人维度</el-radio-button>
        <el-radio-button value="sites">站点维度</el-radio-button>
      </el-radio-group>
      <span>统计日期</span>
      <el-date-picker v-model="dateRange" type="daterange" value-format="YYYY-MM-DD"
        range-separator="至" start-placeholder="开始日期" end-placeholder="结束日期"
        style="width: 300px; flex-grow: 0" :disabled="loading || refreshing" @change="loadReport" />
      <el-tooltip content="读取已保存的谷仓最新库龄和当月成本、负责人规则，重新计算并保存当天快照；不会调用谷仓接口。">
        <span><el-button type="primary" icon="Refresh" :loading="refreshing"
          :disabled="loading || refreshing || !canRefresh" @click="refreshReport">刷新统计</el-button></span>
      </el-tooltip>
    </div>
    <p v-if="report.start_date" class="age-ratio-help">
      {{ report.start_date }} 至 {{ report.end_date }}，共 {{ report.snapshot_dates?.length || 0 }} 个统计日
    </p>
    <p v-if="report.generated_at" class="age-ratio-help">
      统计生成：{{ report.generated_at }}　谷仓源数据拉取：{{ report.source_pulled_at || '--' }}　
      成本 / 负责人月份：{{ report.owner_month }}　源明细：{{ report.source_rows }} 条，已计价：{{ report.valued_rows }} 条
    </p>
    <el-alert v-if="report.generated_at && report.calculation_version !== 'core-supplier-max-landed-cost-v4'"
      title="此快照使用旧SKU匹配口径。历史快照不自动改写；点击刷新统计将按核心码＋供应商编号生成当天数据。"
      type="info" :closable="false" show-icon class="age-ratio-warning" />
    <el-alert v-for="warning in visibleWarnings" :key="warning" :title="warning"
      type="warning" :closable="false" show-icon class="age-ratio-warning" />
    <el-table :key="dimension" :data="rows" border stripe max-height="650" :empty-text="emptyText">
      <el-table-column prop="stat_date" label="统计日期" min-width="120" fixed />
      <template v-if="dimension === 'owners'">
      <el-table-column v-for="bucket in buckets" :key="bucket.key + '_value'"
        :prop="bucket.key + '_value'" :label="bucket.label + '货值'" min-width="140" align="right">
        <template #default="{ row }">{{ formatMoney(row[bucket.key + '_value']) }}</template>
      </el-table-column>
      <el-table-column prop="total_value" label="总货值" min-width="145" align="right">
        <template #default="{ row }"><strong>{{ formatMoney(row.total_value) }}</strong></template>
      </el-table-column>
      <el-table-column v-for="bucket in buckets" :key="bucket.key + '_ratio'"
        :prop="bucket.key + '_ratio'" :label="bucket.label + '占比'" min-width="125" align="right">
        <template #default="{ row }">
          <div class="ratio-data-cell">
            <span class="ratio-data-bar" aria-hidden="true"
              :style="{ width: ratioBarWidth(row[bucket.key + '_ratio']) }" />
            <span class="ratio-data-label">{{ formatPercent(row[bucket.key + '_ratio']) }}</span>
          </div>
        </template>
      </el-table-column>
      <el-table-column prop="name" label="负责人" min-width="140" fixed="right" />
      </template>
      <template v-else>
        <el-table-column v-for="column in siteColumns" :key="column.prop"
          :prop="column.prop" :label="column.label" :min-width="column.kind === 'text' ? 100 : 140"
          :align="column.kind === 'text' ? 'left' : 'right'">
          <template #default="{ row }">
            <div v-if="column.kind === 'ratio'" class="ratio-data-cell">
              <span class="ratio-data-bar" aria-hidden="true"
                :style="{ width: ratioBarWidth(row[column.prop]) }" />
              <span class="ratio-data-label">{{ formatPercent(row[column.prop]) }}</span>
            </div>
            <template v-else>
              {{ column.kind === 'quantity' ? formatQuantity(row[column.prop])
                : column.kind === 'money' ? formatMoney(row[column.prop]) : row[column.prop] }}
            </template>
          </template>
        </el-table-column>
      </template>
    </el-table>
  </section>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { checkPermi } from '@/utils/permission'
import { getEbayInventoryAgeRatio, recalculateEbayInventoryAgeRatio } from '@/api/operations/ebay/inventoryDetail'

const emit = defineEmits(['busy-change'])
const report = ref({ owners: [], sites: [], warnings: [] })
const dimension = ref('owners')
const selectedDate = ref('latest')
const dateRange = ref([])
const availableDates = ref([])
const loading = ref(false)
const refreshing = ref(false)
const canRefresh = computed(() => checkPermi(['operations:ebayInventoryDetail:import']))
const rows = computed(() => report.value[dimension.value] || [])
// Hide requested diagnostics in the UI only; preserve source notes in snapshots.
const visibleWarnings = computed(() => (report.value.warnings || []).filter(warning => {
  const message = warning.replace(/^\d{4}-\d{2}-\d{2}：\s*/, '')
  return !message.includes('未计入货值及占比') && ![
    'Excel历史汇总：',
    '历史分段沿用原Excel公式：',
    '原表仅有负责人汇总，无站点数据及SKU明细；'
  ].some(prefix => message.startsWith(prefix))
}))
const emptyText = computed(() => report.value.start_date ? '所选日期范围内没有统计快照' : report.value.generated_at ? '该日期没有可展示的数据' : '尚无统计快照，请点击“刷新统计”')
const buckets = [
  { key: 'under_90', label: '<90' }, { key: 'days_90_120', label: '90-120' },
  { key: 'days_120_180', label: '120-180' }, { key: 'over_180', label: '>180' }
]
const siteColumns = [
  { prop: 'name', label: '站点', kind: 'text' },
  { prop: 'total_quantity', label: '总库存', kind: 'quantity' },
  { prop: 'over_180_quantity', label: '>180天库存', kind: 'quantity' },
  { prop: 'over_180_quantity_ratio', label: '库存占比', kind: 'ratio' },
  { prop: 'total_value', label: '总货值', kind: 'money' },
  { prop: 'over_180_value', label: '>180天货值', kind: 'money' },
  { prop: 'over_180_ratio', label: '货值占比', kind: 'ratio' }
]
// The full cell always represents 100%, regardless of other rows or filters.
function ratioBarWidth(value) {
  const number = Number(value)
  return Number.isFinite(number) && number > 0
    ? `${Number((Math.min(1, number) * 100).toFixed(6))}%` : '0%'
}
let version = 0
let disposed = false
function formatQuantity(value) {
  return value == null ? '--' : Number(value).toLocaleString('zh-CN', { maximumFractionDigits: 6 })
}
function formatMoney(value) {
  return value == null ? '--' : Number(value).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
function formatPercent(value) {
  return value == null || value === '' || !Number.isFinite(Number(value)) ? '--'
    : Number(value).toLocaleString('zh-CN', { style: 'percent', minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
async function loadReport() {
  if (refreshing.value) return
  const current = ++version
  loading.value = true
  try {
    const params = dateRange.value?.length === 2
      ? { startDate: dateRange.value[0], endDate: dateRange.value[1] }
      : { statDate: 'latest' }
    const response = await getEbayInventoryAgeRatio(params)
    if (disposed || current !== version) return
    report.value = response.data
    availableDates.value = response.data.available_dates || []
    selectedDate.value = response.data.stat_date || undefined
    dateRange.value = response.data.start_date
      ? [response.data.start_date, response.data.end_date]
      : response.data.stat_date ? [response.data.stat_date, response.data.stat_date] : []
  } catch {
    if (!disposed && current === version) {
      selectedDate.value = report.value.stat_date || undefined
      dateRange.value = report.value.start_date ? [report.value.start_date, report.value.end_date]
        : report.value.stat_date ? [report.value.stat_date, report.value.stat_date] : []
    }
  } finally {
    if (!disposed && current === version) loading.value = false
  }
}
async function refreshReport() {
  if (loading.value || refreshing.value || !canRefresh.value) return
  refreshing.value = true
  emit('busy-change', true)
  try {
    const response = await recalculateEbayInventoryAgeRatio()
    if (disposed) return
    report.value = response.data
    selectedDate.value = response.data.stat_date
    dateRange.value = [response.data.stat_date, response.data.stat_date]
    availableDates.value = [...new Set([response.data.stat_date, ...availableDates.value])].sort().reverse()
    ElMessage.success('海外仓库龄占比已重新计算并保存')
  } catch {
    // Shared interceptor reports the error. Preserve the last successful snapshot.
  } finally {
    refreshing.value = false
    emit('busy-change', false)
  }
}
onMounted(loadReport)
onBeforeUnmount(() => { disposed = true; version++; emit('busy-change', false) })
</script>

<style scoped>
.age-ratio-toolbar { display: flex; align-items: center; flex-wrap: wrap; gap: 12px; margin-bottom: 14px; }
.age-ratio-help { color: #64748b; font-size: 13px; line-height: 1.8; margin: 8px 0 14px; }
.age-ratio-warning { margin: 10px 0; }
.ratio-data-cell { position: relative; min-height: 24px; line-height: 24px; isolation: isolate; }
.ratio-data-bar { position: absolute; left: 0; top: 1px; bottom: 1px; background: #f5a0ac; pointer-events: none; z-index: -1; }
.ratio-data-label { position: relative; display: block; padding: 0 4px; color: var(--el-text-color-primary); font-variant-numeric: tabular-nums; white-space: nowrap; }
</style>
