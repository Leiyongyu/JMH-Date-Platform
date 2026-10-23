<template>
  <div>
    <div class="table-controls"><el-radio-group v-model="dimension" @change="reset"><el-radio-button value="platform">按平台</el-radio-button><el-radio-button value="group">按组别</el-radio-button></el-radio-group>
      <el-checkbox v-model="showMom" @change="reset">显示环比</el-checkbox><el-checkbox v-model="showYoy" @change="reset">显示同比</el-checkbox><el-checkbox v-if="extraFields.length" v-model="showExtra" @change="reset">展开平台独有字段</el-checkbox><span>{{ scope }}</span></div>
    <el-table ref="table" v-loading="loading" :data="pageRows" border stripe max-height="540" show-summary :summary-method="summary" @sort-change="changeSort">
      <el-table-column prop="name" :label="dimension === 'platform' ? '平台' : '平台 / 组别'" fixed="left" min-width="155" sortable="custom" />
      <el-table-column v-for="metric in mainMetrics" :key="metric.key" :label="metric.label" align="center">
        <el-table-column :prop="metric.key" label="本期金额" min-width="170" align="right" sortable="custom"><template #default="{ row }">{{ formatMetric(row[metric.key]) }}</template></el-table-column>
        <template v-for="kind in kinds" :key="kind">
          <el-table-column :prop="`${metric.key}_${kind}_difference`" :label="`${kind === 'mom' ? '环比' : '同比'}增减额`" min-width="165" align="right" sortable="custom"><template #default="{ row }"><TrendValue :value="row[`${metric.key}_${kind}_difference`]">{{ formatMetric(row[`${metric.key}_${kind}_difference`]) }}</TrendValue></template></el-table-column>
          <el-table-column :prop="`${metric.key}_${kind}`" :label="`${kind === 'mom' ? '环比' : '同比'}变化率`" min-width="165" align="right" sortable="custom"><template #default="{ row }"><ComparisonValue :value="row.metrics[metric.key][kind]" :current="row[metric.key]" unit="CNY" :range="range" /></template></el-table-column>
        </template>
      </el-table-column>
    </el-table>
    <div class="table-footer"><span>合计为全部筛选结果；缺失数据仍计入已有金额，增长率仅在周期完整且基期非0时计算。</span><el-pagination v-model:current-page="page" v-model:page-size="size" :page-sizes="[10, 20, 50, 100]" :total="rows.length" layout="total, sizes, prev, pager, next" @size-change="page = 1" /></div>
  </div>
</template>
<script setup>
import { computed, h, ref, watch } from 'vue'
import { salesMetrics, formatMetric } from './chart'
import { sortDetails } from './details'
import ComparisonValue from './ComparisonValue.vue'
import TrendValue from './TrendValue.vue'
const props = defineProps({ report: Object, loading: Boolean, scope: String })
const showExtra = ref(false)
const extraFields = computed(() => props.report?.platform !== 'all' ? props.report?.specials?.[props.report?.platform]?.fields || [] : [])
const mainMetrics = computed(() => [...salesMetrics.filter(m => !m.secondary), ...(showExtra.value ? extraFields.value : [])])
const dimension = ref('platform'), showMom = ref(false), showYoy = ref(false), page = ref(1), size = ref(20), sort = ref({}), table = ref(null)
const range = computed(() => props.report ? [props.report.start, props.report.end] : [])
const kinds = computed(() => [showMom.value ? 'mom' : null, showYoy.value ? 'yoy' : null].filter(Boolean))
const definitions = computed(() => mainMetrics.value.flatMap(m => [{ key: m.key, unit: 'CNY' }, ...kinds.value.flatMap(k => [{ key: `${m.key}_${k}`, unit: 'ratio' }, { key: `${m.key}_${k}_difference`, unit: 'CNY' }])]))
const rows = computed(() => (props.report?.breakdown?.[dimension.value] || []).map(row => ({ ...row, ...Object.fromEntries(mainMetrics.value.flatMap(m => [[m.key, row.metrics[m.key].value], ...kinds.value.flatMap(k => [[`${m.key}_${k}`, row.metrics[m.key][k].value], [`${m.key}_${k}_difference`, row.metrics[m.key][k].difference]])])) })))
const pageRows = computed(() => sortDetails(rows.value, sort.value, definitions.value).slice((page.value - 1) * size.value, page.value * size.value))
function summary({ columns }) {
  return columns.map((column, index) => {
    if (!index) return '筛选合计'
    const def = definitions.value.find(d => d.key === column.property)
    if (!def) return ''
    const metric = mainMetrics.value.find(m => column.property === m.key || column.property.startsWith(m.key + '_'))
    const data = (props.report?.metrics?.[metric.key] || props.report?.specials?.[props.report?.platform]?.metrics?.[metric.key])?.summary
    if (column.property === metric.key) return formatMetric(data?.value)
    const kind = column.property.slice(metric.key.length + 1).startsWith('mom') ? 'mom' : 'yoy'
    const comparison = data?.[kind]
    return column.property.endsWith('_difference')
      ? h(TrendValue, { value: comparison?.difference }, () => formatMetric(comparison?.difference))
      : h(ComparisonValue, { value: comparison, current: data?.value, unit: 'CNY', range: range.value })
  })
}
function reset() { page.value = 1; sort.value = {}; table.value?.clearSort() }
function changeSort(value) { sort.value = value; page.value = 1 }
watch(() => props.report, reset)
</script>
<style scoped>
.table-controls, .table-footer { display: flex; align-items: center; gap: 16px; flex-wrap: wrap; margin: 14px 0; }
.table-controls span, .table-footer span { font-size: 12px; color: var(--el-text-color-secondary); }
.table-footer { justify-content: space-between; overflow-x: auto; }
:deep(.el-table th.el-table__cell) { background: var(--el-fill-color-light); }
:deep(.el-table__footer-wrapper) { font-weight: 600; }
</style>
