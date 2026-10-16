<template>
  <section class="sales-dashboard" aria-label="销售看板">
    <section class="global-filters" aria-label="销售看板全局筛选">
    <header><div><h2>销售看板</h2><p class="filter-description">统一筛选业绩指标、月度趋势与组别明细</p></div>
      <el-button v-hasPermi="['finance:salesDashboard:import']" icon="Upload" @click="openImport">上传历史数据</el-button>
    </header>
    <div class="filters">
      <div class="filter-control"><span class="filter-label">统计粒度</span><el-radio-group v-model="granularity" @change="changeGranularity"><el-radio-button value="month">按月</el-radio-button><el-radio-button value="quarter">按季度</el-radio-button></el-radio-group></div>
      <div v-if="granularity === 'month'" class="filter-control"><span class="filter-label">统计月份</span><div class="month-range-filter">
        <el-date-picker v-model="range" type="monthrange" value-format="YYYY-MM" format="YYYY-MM"
                        range-separator="至" start-placeholder="开始月份" end-placeholder="结束月份"
                        aria-label="统计月份范围" :clearable="false" :editable="false"
                        :disabled="!monthOptions.length" :disabled-date="isMonthDisabled" @change="loadReport" />
      </div></div>
      <div v-else class="filter-control"><span class="filter-label">统计季度</span><div class="quarter-range">
        <el-select v-model="quarters[0]" aria-label="开始季度" :disabled="!quarterOptions.length" @change="changeQuarter"><el-option v-for="q in quarterOptions" :key="q" :label="q" :value="q" :disabled="q > quarters[1]" /></el-select><span>至</span>
        <el-select v-model="quarters[1]" aria-label="结束季度" :disabled="!quarterOptions.length" @change="changeQuarter"><el-option v-for="q in quarterOptions" :key="q" :label="q" :value="q" :disabled="q < quarters[0]" /></el-select>
      </div></div>
      <div class="filter-control"><span class="filter-label">平台</span>
      <el-select v-model="platform" aria-label="平台" style="width: 130px" @change="changePlatform">
        <el-option label="全部平台" value="all" /><el-option label="eBay" value="ebay" /><el-option label="AMZ" value="amz" />
      </el-select></div>
      <div class="filter-control"><span class="filter-label">组别</span>
      <el-select v-model="groups" aria-label="组别" multiple collapse-tags collapse-tags-tooltip clearable
                 placeholder="全部组别" style="width: 260px" @change="loadReport">
        <el-option v-for="g in groupOptions" :key="g.value" :label="g.label" :value="g.value" />
      </el-select></div>
      <el-button type="primary" icon="Search" :loading="loading" :disabled="!monthOptions.length" @click="loadReport">查询</el-button>
    </div>
    </section>

    <section class="analysis-panel" aria-label="业绩分析">
    <div class="analysis-heading"><h3>业绩总览</h3><span class="range-caption">{{ scopeCaption }}</span></div>
    <el-alert v-if="error" :title="error" type="error" :closable="false" />
    <div class="metric-cards" aria-label="选择趋势指标">
      <button v-for="item in mainMetrics" :key="item.key" type="button" class="metric-card"
        :class="{ active: selectedMetric === item.key }" :style="{ '--metric-color': item.color }"
        :aria-pressed="selectedMetric === item.key" :aria-label="`${item.label}，点击查看趋势`"
        @click="selectMetric(item.key)">
        <span class="card-heading"><span>{{ item.label }}
          <el-tooltip :content="metricDescription(item.key)" placement="top"><el-icon class="info-icon"><InfoFilled /></el-icon></el-tooltip>
        </span><span class="metric-icon"><el-icon><component :is="metricIcons[item.icon]" /></el-icon></span></span>
        <el-tooltip :content="formatMetric(metricData(item.key)?.summary?.value, metricData(item.key)?.unit)" placement="top">
          <strong class="metric-value">{{ loading ? '…' : formatMetric(metricData(item.key)?.summary?.value, metricData(item.key)?.unit, true) }}</strong>
        </el-tooltip>
        <span class="card-footnote">{{ metricFootnote(item.key) }}</span>
        <span class="card-comparisons"><ComparisonValue v-for="kind in ['mom', 'yoy']" :key="kind" :label="kind === 'mom' ? '环比' : '同比'" :value="metricData(item.key)?.summary?.[kind]" :current="metricData(item.key)?.summary?.value" unit="CNY" :range="effectiveRange" /></span>
      </button>
    </div>
    <div class="ratio-cards"><button v-for="item in ratioMetrics" :key="item.key" class="ratio-card" :class="{ active: selectedMetric === item.key }" :aria-pressed="selectedMetric === item.key" @click="selectMetric(item.key)">
      <el-tooltip :content="metricDescription(item.key)"><span>{{ item.label }}</span></el-tooltip><strong>{{ formatMetric(metricData(item.key)?.summary?.value, 'ratio') }}</strong>
      <ComparisonValue v-for="kind in ['mom', 'yoy']" :key="kind" :label="kind === 'mom' ? '环比' : '同比'" :value="metricData(item.key)?.summary?.[kind]" :current="metricData(item.key)?.summary?.value" unit="ratio" :range="effectiveRange" />
    </button></div>
    <div class="trend-heading"><div><span class="trend-dot" :style="{ background: activeDefinition.color }" />
      <strong>{{ activeDefinition.label }}趋势</strong><span class="trend-grain">{{ granularity === 'quarter' ? '按季度' : '按月' }}</span></div>
      <span class="metric-explanation">{{ metricDescription(selectedMetric) }}</span></div>
    <div class="trend-controls"><el-radio-group v-model="trendDimension" @change="renderChart"><el-radio-button value="total">合计</el-radio-button><el-radio-button value="platform">按平台对比</el-radio-button><el-radio-button value="group">按组别对比</el-radio-button></el-radio-group>
      <el-checkbox v-model="showYear" :disabled="trendDimension !== 'total'" @change="renderChart">显示去年同期</el-checkbox></div>
    <div v-loading="loading">
      <div v-show="hasData || loading" ref="chartEl" class="chart" role="img" :aria-label="`${platform}${activeDefinition.label}趋势折线图`" />
      <el-empty v-if="!hasData && !error && !loading" description="所选范围暂无数据，请调整筛选或上传历史数据" />
    </div>
    <p class="hint">公司合计仅含已接入的 eBay＋AMZ。金额汇总已有数据；不完整周期不显示增长率。金额变化率＝增减额 ÷ |对比期金额|，比率变化用百分点表示。负值保留，箭头仅表示数值增减，不代表经营好坏。</p>
    </section>

    <ContributionPanel :report="report" :loading="loading" :scope="scopeCaption" />
    <PlatformAnalysis :report="report" :loading="loading" :scope="scopeCaption" />
    <section class="detail-section"><div class="analysis-heading"><h3>业绩详情</h3><el-radio-group v-model="detailMode"><el-radio-button value="comparison">汇总对比</el-radio-button><el-radio-button value="raw">原始明细</el-radio-button></el-radio-group></div>
      <ComparisonTable v-if="detailMode === 'comparison'" :report="report" :loading="loading" :scope="scopeCaption" />
      <template v-else><el-tabs v-model="rawPlatform"><el-tab-pane v-for="p in rawPlatforms" :key="p" :name="p" :label="p === 'ebay' ? 'eBay' : 'AMZ'" /></el-tabs>
        <PerformanceDetails :details="report?.raw_details?.[rawPlatform]" :loading="loading" :error="error" :scope="scopeCaption" /></template>
    </section>

    <el-dialog v-model="importOpen" title="上传销售历史数据" width="min(900px, 95vw)" :close-on-click-modal="!uploading" :show-close="!uploading" :close-on-press-escape="!uploading" append-to-body>
      <el-alert title="按文件中的平台＋年月整体覆盖：同平台同月请提供完整组别，未包含的月份与平台不变。" type="warning" :closable="false" />
      <div class="file-row"><input ref="fileInput" type="file" accept=".xlsx" :disabled="uploading" @change="chooseFile" />
        <el-button :disabled="!file || uploading" :loading="previewing" @click="previewFile">预览覆盖范围</el-button></div>
      <el-alert v-if="importError" :title="importError" type="error" :closable="false" />
      <template v-if="preview">
        <p>共 {{ preview.row_count }} 条，涉及 {{ preview.scopes.length }} 个平台月份。</p>
        <el-table :data="preview.scopes" max-height="330" border>
          <el-table-column prop="platform" label="平台" width="80" />
          <el-table-column prop="month" label="年月" width="100" />
          <el-table-column label="组别" min-width="180"><template #default="{ row }">{{ row.groups.join('、') }}</template></el-table-column>
          <el-table-column prop="rows" label="条数" width="65" />
          <el-table-column label="业绩金额（元）" min-width="170" align="right"><template #default="{ row }">{{ money(row.amount) }}</template></el-table-column>
        </el-table>
        <div v-if="preview.warnings.length" class="warnings"><p v-for="(warning, i) in preview.warnings" :key="i">{{ warning }}</p></div>
      </template>
      <template #footer><el-button :disabled="uploading" @click="importOpen = false">关闭</el-button>
        <el-button type="primary" :disabled="!preview || previewing" :loading="uploading" @click="confirmImport">确认覆盖并导入</el-button></template>
    </el-dialog>
  </section>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import * as echarts from 'echarts'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Wallet, TrendCharts, DataAnalysis, Coin, RefreshLeft, PieChart, InfoFilled } from '@element-plus/icons-vue'
import { getSalesOptions, getSalesAnalysis, previewSalesHistory, importSalesHistory } from '@/api/finance/salesDashboard'
import { salesChartOption, salesMetrics, formatMetric } from './chart'
import { availableMonths, disabledMonth, fitMonthRange, validMonthRange, availableQuarters, quarterRange, quarterMonths, platformGroups } from './months'
import PerformanceDetails from './PerformanceDetails.vue'
import ComparisonValue from './ComparisonValue.vue'
import ComparisonTable from './ComparisonTable.vue'
import ContributionPanel from './ContributionPanel.vue'
import PlatformAnalysis from './PlatformAnalysis.vue'

const platform = ref('all'), groups = ref([]), range = ref([]), options = ref({})
const granularity = ref('month'), quarters = ref([]), trendDimension = ref('total'), showYear = ref(false), detailMode = ref('comparison'), rawPlatform = ref('ebay')
const mainMetrics = salesMetrics.filter(item => !item.secondary), ratioMetrics = salesMetrics.filter(item => item.secondary)
const effectiveRange = computed(() => granularity.value === 'quarter' ? quarterMonths(quarters.value) : range.value)
const quarterOptions = computed(() => availableQuarters(monthOptions.value))
const rawPlatforms = computed(() => Object.keys(report.value?.raw_details || {}))
const report = ref(null), loading = ref(false), error = ref(''), chartEl = ref(null)
const importOpen = ref(false), file = ref(null), preview = ref(null), previewing = ref(false), uploading = ref(false), importError = ref(''), fileInput = ref(null)
const groupOptions = computed(() => platformGroups(options.value, platform.value))
const monthOptions = computed(() => availableMonths(options.value, platform.value))
const isMonthDisabled = date => disabledMonth(date, monthOptions.value)
const selectedMetric = ref('net_sales')
const metricIcons = { Wallet, TrendCharts, DataAnalysis, Coin, RefreshLeft, PieChart }
const metricData = key => report.value?.metrics?.[key]
const activeDefinition = computed(() => salesMetrics.find(item => item.key === selectedMetric.value))
const hasData = computed(() => {
  const metric = metricData(selectedMetric.value)
  return metric?.total?.some(value => value !== null) || metric?.series?.some(item => item.values.some(value => value !== null))
})
const scopeCaption = computed(() => `${platform.value === 'all' ? groups.value.length ? '跨平台筛选合计' : '公司合计（eBay＋AMZ）' : platform.value === 'ebay' ? 'eBay' : 'AMZ'} · ${effectiveRange.value.length === 2 ? effectiveRange.value.join(' 至 ') : '暂无数据'} · ${groups.value.length ? groups.value.join('、') : '全部组别'}`)
let chart, observer, requestVersion = 0, fileVersion = 0, disposed = false
const money = value => value == null ? '无数据' : Number(value).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })

function metricDescription(key) {
  return { net_sales: '净收款：eBay净额（人民币）＋AMZ总收款（人民币），按当前筛选汇总',
    platform_expense: '来源：平台支出(RMB）-总，保留正负号', gross_sales: 'eBay销售总额／AMZ总销售额（人民币）',
    gross_profit: '来源：毛利(RMB)', gross_margin: '毛利润合计 ÷ 平台收入-总(RMB)合计 × 100%',
    platform_income: '来源：平台收入-总(RMB)',
    refund_amount: '来源：eBay退款／AMZ退款金额（人民币），按当前筛选汇总',
    refund_rate: '退款金额合计 ÷ 销售总额合计 × 100%，按当前筛选计算' }[key]
}
function metricFootnote(key) {
  if (loading.value) return '正在更新所选范围…'
  const summary = metricData(key)?.summary
  if (!summary) return '暂无数据'
  if (summary.reason === 'zero_denominator') return key === 'refund_rate' ? '销售总额为0，无法计算' : '平台收入为0，无法计算'
  if (summary.value == null) return '所选范围暂无数据'
  return key === 'gross_margin' ? '区间毛利润合计 ÷ 平台收入合计' : key === 'refund_rate' ? '区间退款合计 ÷ 销售总额合计' : '所选时间段已有数据合计'
}
async function renderChart() {
  await nextTick()
  if (disposed) return
  if (hasData.value && chartEl.value) {
    chart ||= echarts.init(chartEl.value)
    chart.setOption(salesChartOption(report.value, selectedMetric.value, trendDimension.value, showYear.value), true)
    chart.resize()
  } else { chart?.clear() }
}
function selectMetric(key) {
  selectedMetric.value = key
  renderChart()
}

async function loadOptions() {
  const res = await getSalesOptions()
  if (disposed) return
  options.value = res.data
  range.value = fitMonthRange(range.value, monthOptions.value)
  quarters.value = quarterRange(range.value, monthOptions.value)
}
function changeGranularity() { quarters.value = quarterRange(range.value, monthOptions.value); loadReport() }
function changeQuarter() { const bounds = quarterMonths(quarters.value); range.value = fitMonthRange(bounds, monthOptions.value); loadReport() }
async function loadReport() {
  if (disposed) return
  const version = ++requestVersion
  if (granularity.value === 'month' ? !validMonthRange(range.value, monthOptions.value) : !effectiveRange.value.length || !quarters.value.every(q => quarterOptions.value.includes(q))) {
    report.value = null; loading.value = false; error.value = ''; chart?.clear()
    return
  }
  loading.value = true; error.value = ''; report.value = null; chart?.clear()
  try {
    const res = await getSalesAnalysis({ platform: platform.value, startMonth: effectiveRange.value[0], endMonth: effectiveRange.value[1], groups: groups.value.join(','), granularity: granularity.value })
    if (disposed || version !== requestVersion) return
    report.value = res.data
    if (!rawPlatforms.value.includes(rawPlatform.value)) rawPlatform.value = rawPlatforms.value[0] || 'ebay'
    await renderChart()
  } catch (e) { if (!disposed && version === requestVersion) error.value = e.message || '读取销售数据失败' }
  finally { if (!disposed && version === requestVersion) loading.value = false }
}
function changePlatform() {
  groups.value = []
  range.value = fitMonthRange(range.value, monthOptions.value)
  quarters.value = quarterRange(range.value, monthOptions.value)
  loadReport()
}
function openImport() { fileVersion++; file.value = null; preview.value = null; importError.value = ''; importOpen.value = true; nextTick(() => { if (fileInput.value) fileInput.value.value = '' }) }
function chooseFile(event) {
  fileVersion++; preview.value = null; importError.value = ''; file.value = event.target.files[0] || null
  if (file.value && (!file.value.name.toLowerCase().endsWith('.xlsx') || file.value.size > 10 * 1024 * 1024)) {
    importError.value = '请选择不超过10MB的.xlsx文件'; file.value = null
  }
}
async function previewFile() {
  const version = fileVersion
  previewing.value = true; importError.value = ''; preview.value = null
  try { const res = await previewSalesHistory(file.value); if (version === fileVersion) preview.value = res.data }
  catch (e) { if (version === fileVersion) importError.value = e.message || '预览失败' }
  finally { previewing.value = false }
}
async function confirmImport() {
  if (!preview.value || uploading.value) return
  const chosenFile = file.value, chosenPreview = preview.value
  try { await ElMessageBox.confirm(`将整体替换所列 ${chosenPreview.scopes.length} 个平台月份的数据。是否继续？`, '确认导入', { type: 'warning' }) }
  catch { return }
  if (file.value !== chosenFile || preview.value !== chosenPreview) return
  uploading.value = true; importError.value = ''
  try {
    await importSalesHistory(chosenFile, chosenPreview.sha256)
    ElMessage.success('历史数据已导入'); importOpen.value = false
    const months = chosenPreview.scopes.filter(s => platform.value === 'all' || s.platform === platform.value).map(s => s.month).sort()
    if (months.length) range.value = [months[0], months.at(-1)]
    try { await loadOptions(); groups.value = groups.value.filter(g => groupOptions.value.some(option => option.value === g)); await loadReport() }
    catch (e) { error.value = `数据已导入，但刷新失败：${e.message || '请重新查询'}` }
  } catch (e) { importError.value = e.message || '导入失败' }
  finally { uploading.value = false }
}
onMounted(async () => {
  observer = new ResizeObserver(() => chart?.resize()); observer.observe(chartEl.value)
  try { await loadOptions(); await loadReport() } catch (e) { error.value = e.message || '读取销售数据失败' }
})
onBeforeUnmount(() => { disposed = true; requestVersion++; observer?.disconnect(); chart?.dispose() })
</script>

<style scoped>
.sales-dashboard { margin-bottom: 18px; }
.global-filters, .analysis-panel { background: var(--el-bg-color); border: 1px solid var(--el-border-color-light); border-radius: 12px; padding: 22px; }
.global-filters { margin-bottom: 18px; }
.quarter-range { display: flex; align-items: center; gap: 8px; width: 270px; }
.quarter-range .el-select { width: 125px; }
.card-comparisons { display: flex; flex-wrap: wrap; gap: 8px 12px; margin-top: 12px; }
.ratio-cards { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 16px; margin-bottom: 24px; }
.ratio-card { display: flex; align-items: center; flex-wrap: wrap; gap: 12px; padding: 14px 18px; background: var(--el-bg-color); color: var(--el-text-color-primary); border: 1px solid var(--el-border-color-light); border-radius: 8px; cursor: pointer; }
.ratio-card.active { border-color: var(--el-color-primary); background: var(--el-color-primary-light-9); }
.ratio-card strong { font-size: 20px; }
.trend-controls { display: flex; align-items: center; flex-wrap: wrap; gap: 20px; margin-top: 18px; }
.detail-section { margin-top: 18px; background: var(--el-bg-color); border: 1px solid var(--el-border-color-light); border-radius: 12px; padding: 22px; }
.detail-section :deep(.performance-details) { border: 0; padding: 0; margin-top: 0; }
header { display: flex; justify-content: space-between; align-items: center; gap: 12px; }
h2 { font-size: 20px; margin: 0; color: var(--el-text-color-primary); }
.filter-description { font-size: 12px; color: var(--el-text-color-secondary); margin: 8px 0 0; }
.filters { display: flex; flex-wrap: wrap; align-items: flex-end; gap: 16px; margin-top: 22px; }
.filter-control { min-width: 0; max-width: 100%; }
.filter-label { display: block; font-size: 12px; color: var(--el-text-color-regular); margin-bottom: 8px; }
.filter-control :deep(.el-select) { max-width: 100%; }
.month-range-filter { flex: 0 1 240px; width: 240px; min-width: 0; max-width: 100%; }
.month-range-filter :deep(.el-date-editor) { width: 100%; min-width: 0; box-sizing: border-box; flex-grow: 0; }
.analysis-heading { display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 12px; margin-bottom: 20px; }
h3 { font-size: 17px; margin: 0; color: var(--el-text-color-primary); }
.range-caption { font-size: 12px; color: var(--el-text-color-secondary); overflow-wrap: anywhere; }
.metric-cards { display: grid; grid-template-columns: repeat(6, minmax(0, 1fr)); gap: 16px; margin: 16px 0 28px; }
.metric-card { font: inherit; text-align: left; cursor: pointer; min-width: 0; background: var(--el-bg-color); color: var(--el-text-color-primary); border: 1px solid var(--el-border-color-light); border-top: 3px solid var(--metric-color); border-radius: 9px; padding: 18px 20px; transition: box-shadow .2s, background .2s, transform .2s; }
.metric-card:hover { transform: translateY(-2px); box-shadow: 0 5px 16px #1e293b0d; }
.metric-card.active { background: color-mix(in srgb, var(--metric-color) 5%, var(--el-bg-color)); box-shadow: 0 4px 18px #1e293b12; outline: 1px solid var(--metric-color); }
.metric-card:focus-visible { outline: 2px solid var(--metric-color); outline-offset: 3px; }
.card-heading { display: flex; align-items: center; justify-content: space-between; gap: 8px; font-size: 14px; color: var(--el-text-color-regular); }
.info-icon { margin-left: 5px; color: var(--el-text-color-placeholder); vertical-align: -2px; font-size: 12px; }
.metric-icon { display: inline-flex; align-items: center; justify-content: center; flex-shrink: 0; width: 32px; height: 32px; border-radius: 8px; color: var(--metric-color); background: color-mix(in srgb, var(--metric-color) 10%, transparent); font-size: 19px; }
.metric-value { display: block; font-size: clamp(21px, 2vw, 29px); line-height: 1.3; font-weight: 600; font-variant-numeric: tabular-nums; margin: 12px 0 8px; overflow-wrap: anywhere; }
.card-footnote { display: block; font-size: 12px; color: var(--el-text-color-secondary); }
.trend-heading { display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 10px; padding-top: 8px; }
.trend-heading > div { display: flex; align-items: center; gap: 8px; font-size: 14px; }
.trend-dot { width: 7px; height: 7px; border-radius: 50%; }
.trend-grain { font-size: 11px; padding: 3px 7px; border-radius: 4px; background: var(--el-fill-color-light); color: var(--el-text-color-secondary); }
.metric-explanation, .hint { font-size: 12px; color: var(--el-text-color-secondary); line-height: 1.7; }
.hint { margin: 18px 0 0; }
.chart { width: 100%; height: 400px; margin-top: 14px; }
.file-row { display: flex; flex-wrap: wrap; gap: 12px; margin: 18px 0; }
.warnings { max-height: 150px; overflow: auto; font-size: 12px; color: var(--el-color-warning-dark-2); }
@media (max-width: 1500px) { .metric-cards { grid-template-columns: repeat(3, minmax(0, 1fr)); } }
@media (max-width: 1100px) { .metric-cards { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
@media (max-width: 600px) {
  .global-filters, .analysis-panel { padding: 16px; }
  header { align-items: flex-start; flex-wrap: wrap; }
  .metric-cards { grid-template-columns: 1fr; gap: 12px; }
  .ratio-cards { grid-template-columns: 1fr; }
  .chart { height: 340px; }
}
</style>
