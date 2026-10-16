<template>
  <section class="contribution-panel">
    <div class="heading"><h3>贡献分析</h3><el-select v-model="metric" aria-label="贡献指标" style="width: 150px"><el-option v-for="m in moneyMetrics" :key="m.key" :label="m.label" :value="m.key" /></el-select><span>{{ scope }}</span></div>
    <div class="charts">
      <div class="chart-panel"><h4>平台金额构成</h4><p>按月／季度显示各平台金额，正负值分别堆叠。</p>
        <DashboardChart :option="platformBars(report, metric)" :empty="!hasPlatformValues" :loading="loading" label="各平台金额构成柱状图" /></div>
      <div class="chart-panel"><div class="controls"><el-radio-group v-model="mode"><el-radio-button value="delta">增减贡献</el-radio-button><el-radio-button value="rank">金额排名</el-radio-button></el-radio-group>
        <el-select v-model="dimension" aria-label="贡献维度" style="width: 110px"><el-option label="按平台" value="platform" /><el-option label="按组别" value="group" /></el-select>
        <el-select v-if="mode === 'delta'" v-model="kind" aria-label="贡献对比期" style="width: 100px"><el-option label="环比" value="mom" /><el-option label="同比" value="yoy" /></el-select></div>
        <DashboardChart :option="contributionBars(items, mode)" :empty="!items.length" :loading="loading" :label="mode === 'delta' ? '增减贡献条形图' : '金额排名条形图'" empty-text="暂无可展示数据，请核对本期和对比期覆盖情况" />
        <template v-if="mode === 'delta' && contribution"><p>整体增减：{{ formatMetric(contribution.total_difference) }}；已纳入增减：{{ formatMetric(contribution.covered_difference) }}。
          {{ contribution.reconciled ? '已与筛选合计核对一致。' : '数据未完整对齐，不作为完整增减归因。' }}</p>
          <el-alert v-if="contribution.unavailable.length" type="info" :closable="false" :title="`未纳入增减图：${contribution.unavailable.map(r => r.name).join('、')}（两期缺值或周期不完整，不按0补齐）`" /></template>
      </div>
    </div>
    <p>增减贡献按金额变化计算，不相加各组增长率；颜色仅区分正负，不表示经营好坏。</p>
  </section>
</template>
<script setup>
import { computed, ref } from 'vue'
import { salesMetrics, formatMetric } from './chart'
import { rankedItems, platformBars, contributionBars } from './contribution'
import DashboardChart from './DashboardChart.vue'
const props = defineProps({ report: Object, loading: Boolean, scope: String })
const moneyMetrics = salesMetrics.filter(m => !m.secondary)
const metric = ref('gross_profit'), mode = ref('delta'), dimension = ref('platform'), kind = ref('mom')
const items = computed(() => rankedItems(props.report, metric.value, dimension.value, mode.value, kind.value))
const contribution = computed(() => props.report?.contributions?.[metric.value]?.[kind.value]?.[dimension.value])
const hasPlatformValues = computed(() => props.report?.metrics?.[metric.value]?.platform_series?.some(s => s.values.some(v => v != null)))
</script>
<style scoped>
.contribution-panel { padding: 22px; margin-top: 18px; border: 1px solid var(--el-border-color-light); border-radius: 12px; background: var(--el-bg-color); }
.heading, .controls { display: flex; align-items: center; flex-wrap: wrap; gap: 12px; }
h3 { margin: 0; font-size: 17px; } h4 { margin: 0; font-size: 14px; }
.heading > span, p { font-size: 12px; color: var(--el-text-color-secondary); line-height: 1.7; }
.charts { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 22px; margin-top: 22px; }
.chart-panel { min-width: 0; }
@media (max-width: 1100px) { .charts { grid-template-columns: 1fr; } }
</style>
