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
    <el-table :data="rows" border stripe max-height="650" :empty-text="emptyText">
      <el-table-column prop="stat_date" label="统计日期" min-width="120" fixed />
      <el-table-column v-for="bucket in buckets" :key="bucket.key + '_value'"
        :prop="bucket.key + '_value'" :label="bucket.label + '货值'" min-width="140" align="right">
        <template #default="{ row }">{{ formatMoney(row[bucket.key + '_value']) }}</template>
      </el-table-column>
      <el-table-column prop="total_value" label="总货值" min-width="145" align="right">
        <template #default="{ row }"><strong>{{ formatMoney(row.total_value) }}</strong></template>
      </el-table-column>
      <el-table-column v-for="bucket in buckets" :key="bucket.key + '_ratio'"
        :prop="bucket.key + '_ratio'" :label="bucket.label + '占比'" min-width="125" align="right">
        <template #default="{ row }">{{ formatPercent(row[bucket.key + '_ratio']) }}</template>
      </el-table-column>
      <el-table-column prop="name" :label="dimension === 'owners' ? '负责人' : '站点'" min-width="140" fixed="right" />
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
// Hide exclusion diagnostics only in the UI; retain them in the saved report.
const visibleWarnings = computed(() => (report.value.warnings || []).filter(warning => !warning.includes('未计入货值及占比')))
const emptyText = computed(() => report.value.start_date ? '所选日期范围内没有统计快照' : report.value.generated_at ? '该日期没有可展示的数据' : '尚无统计快照，请点击“刷新统计”')
const buckets = [
  { key: 'under_90', label: '<90' }, { key: 'days_90_120', label: '90-120' },
  { key: 'days_120_180', label: '120-180' }, { key: 'over_180', label: '>180' }
]
let version = 0
let disposed = false
function formatMoney(value) {
  return value == null ? '--' : Number(value).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
function formatPercent(value) {
  return value == null ? '--' : Number(value).toLocaleString('zh-CN', { style: 'percent', minimumFractionDigits: 2, maximumFractionDigits: 2 })
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
</style>
