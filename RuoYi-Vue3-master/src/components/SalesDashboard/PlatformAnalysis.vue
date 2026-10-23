<template>
  <section class="platform-analysis">
    <header><h3>平台专项分析</h3><span>{{ scope }}</span></header>
    <el-tabs v-model="platform"><el-tab-pane v-for="p in platforms" :key="p" :name="p" :label="p === 'ebay' ? 'eBay' : 'AMZ'" /></el-tabs>
    <p>各平台保留原始项目口径，成交费不等同于佣金，广告费不等同于广告和推广费；赔偿独立展示，不计作费用。不适用项目不补0。</p>
    <div class="special-cards"><button v-for="field in fields" :key="field.key" :class="{ active: selected === field.key }" :aria-pressed="selected === field.key" @click="selected = field.key">
      <span>{{ field.label }}</span><strong>{{ formatMetric(metrics[field.key]?.summary.value, 'CNY', true) }}</strong>
      <div class="comparisons"><ComparisonValue v-for="kind in ['mom', 'yoy']" :key="kind" :label="kind === 'mom' ? '环比' : '同比'" :value="metrics[field.key]?.summary[kind]" :current="metrics[field.key]?.summary.value" unit="CNY" :range="range" /></div>
    </button></div>
    <div class="controls"><strong>{{ metrics[selected]?.label || '专项项目' }}趋势</strong><el-radio-group v-model="trend"><el-radio-button value="total">平台合计</el-radio-button><el-radio-button value="group">按组别</el-radio-button></el-radio-group><el-checkbox v-model="showYear" :disabled="trend !== 'total'">显示去年同期</el-checkbox></div>
    <DashboardChart :option="chartOption" :loading="loading" :empty="!hasValues" label="平台专项项目趋势" />
    <div class="controls"><h4>专项项目对比</h4><el-radio-group v-model="tableMode" @change="page = 1"><el-radio-button value="items">按项目</el-radio-button><el-radio-button value="groups">按组别</el-radio-button></el-radio-group>
      <el-select v-model="kind" aria-label="专项对比期" style="width: 100px"><el-option label="环比" value="mom" /><el-option label="同比" value="yoy" /></el-select><span v-if="tableMode === 'groups'">当前项目：{{ metrics[selected]?.label }}</span></div>
    <el-table v-loading="loading" :data="pageRows" border stripe max-height="480">
      <el-table-column prop="name" :label="tableMode === 'items' ? '项目' : '平台 / 组别'" min-width="160" fixed="left" />
      <el-table-column label="本期金额" min-width="160" align="right"><template #default="{ row }">{{ formatMetric(row.summary.value) }}</template></el-table-column>
      <el-table-column label="对比期金额" min-width="160" align="right"><template #default="{ row }">{{ formatMetric(row.summary[kind].baseline) }}</template></el-table-column>
      <el-table-column label="增减金额" min-width="160" align="right"><template #default="{ row }"><TrendValue :value="row.summary[kind].difference">{{ formatMetric(row.summary[kind].difference) }}</TrendValue></template></el-table-column>
      <el-table-column label="环比" min-width="165" align="right"><template #default="{ row }"><ComparisonValue :value="row.summary.mom" :current="row.summary.value" unit="CNY" :range="range" /></template></el-table-column>
      <el-table-column label="同比" min-width="165" align="right"><template #default="{ row }"><ComparisonValue :value="row.summary.yoy" :current="row.summary.value" unit="CNY" :range="range" /></template></el-table-column>
      <el-table-column label="占销售总额比例" min-width="160" align="right"><template #default="{ row }"><el-tooltip content="项目金额合计 ÷ 销售总额合计 × 100%，保留正负号；赔偿不代表费用"><span>{{ formatMetric(row.share?.value, 'ratio') }}</span></el-tooltip></template></el-table-column>
    </el-table>
    <div class="footer"><p>金额与占比保留原始正负号；基期为0、缺失数据及未完整周期的增长率不计算。不同项目不直接相加为平台支出。</p><el-pagination v-model:current-page="page" :page-size="20" :total="tableRows.length" layout="total, prev, pager, next" /></div>
  </section>
</template>
<script setup>
import { computed, ref, watch } from 'vue'
import { formatMetric, salesChartOption } from './chart'
import ComparisonValue from './ComparisonValue.vue'
import TrendValue from './TrendValue.vue'
import DashboardChart from './DashboardChart.vue'
const props = defineProps({ report: Object, loading: Boolean, scope: String })
const platform = ref('ebay'), selected = ref('transaction_fee'), trend = ref('total'), showYear = ref(false), tableMode = ref('items'), kind = ref('mom'), page = ref(1)
const platforms = computed(() => Object.keys(props.report?.specials || {}))
const data = computed(() => props.report?.specials?.[platform.value])
const fields = computed(() => data.value?.fields || [])
const metrics = computed(() => data.value?.metrics || {})
const range = computed(() => props.report ? [props.report.start, props.report.end] : [])
const chartOption = computed(() => salesChartOption({ months: props.report?.months || [], metrics: metrics.value }, selected.value, trend.value, showYear.value))
const hasValues = computed(() => metrics.value[selected.value]?.total?.some(v => v != null))
const tableRows = computed(() => tableMode.value === 'items' ? fields.value.map(f => ({ name: f.label, ...metrics.value[f.key] }))
  : (data.value?.groups || []).map(g => ({ name: g.name, summary: g.metrics[selected.value], share: g.metrics[`${selected.value}_share`] })).filter(r => r.summary))
const pageRows = computed(() => tableRows.value.slice((page.value - 1) * 20, page.value * 20))
watch(platforms, values => { if (values.length && !values.includes(platform.value)) platform.value = values[0] }, { immediate: true })
watch(fields, values => { if (values.length && !values.some(f => f.key === selected.value)) selected.value = values[0].key; page.value = 1 }, { immediate: true })
watch(selected, () => { page.value = 1 })
</script>
<style scoped>
.platform-analysis { margin-top: 18px; padding: 22px; background: var(--el-bg-color); border: 1px solid var(--el-border-color-light); border-radius: 12px; }
header, .controls, .footer { display: flex; align-items: center; gap: 16px; flex-wrap: wrap; }
header { justify-content: space-between; margin-bottom: 12px; } h3 { margin: 0; font-size: 17px; } h4 { margin: 0; }
header span, p, .controls > span { font-size: 12px; color: var(--el-text-color-secondary); line-height: 1.7; }
.special-cards { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 12px; margin: 18px 0; }
.special-cards button { text-align: left; font: inherit; background: var(--el-bg-color); color: var(--el-text-color-primary); padding: 16px; border: 1px solid var(--el-border-color-light); border-top: 3px solid #7a87d5; border-radius: 8px; cursor: pointer; }
.special-cards button.active { background: var(--el-color-primary-light-9); border-color: var(--el-color-primary); }
.special-cards strong { display: block; font-size: 22px; margin: 10px 0; }
.comparisons { display: flex; gap: 10px; flex-wrap: wrap; }
.controls { margin: 16px 0; } .footer { justify-content: space-between; overflow-x: auto; }
:deep(.el-table th.el-table__cell) { background: var(--el-fill-color-light); }
@media (max-width: 900px) { .special-cards { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
@media (max-width: 600px) { .special-cards { grid-template-columns: 1fr; } }
</style>
