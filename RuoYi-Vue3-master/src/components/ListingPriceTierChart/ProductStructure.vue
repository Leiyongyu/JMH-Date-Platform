<template>
  <el-dialog v-model="visible" title="产品结构 · 不同价格段不良交易率" width="min(1100px, 96vw)" append-to-body
             @opened="render">
    <div class="toolbar">
      <span>年份</span>
      <el-select v-model="year" size="small" style="width: 120px" @change="load">
        <el-option v-for="y in years" :key="y" :label="`${y} 年`" :value="y" />
      </el-select>
      <el-button size="small" :disabled="loading" @click="load">刷新</el-button>
      <span v-if="months.length" class="hint">{{ months[0] }} ~ {{ months[months.length - 1] }}，共 {{ months.length }} 个月</span>
    </div>

    <el-alert v-if="error" :title="error" type="error" :closable="false" />
    <template v-else>
      <div v-loading="loading" ref="chartEl" class="chart" />
      <p class="note">{{ note }}</p>
      <el-table v-if="details.length" :data="tableRows" size="small" max-height="240" border stripe>
        <el-table-column prop="month" label="月份" width="100" fixed />
        <el-table-column v-for="(label, i) in labels" :key="label" :label="label" min-width="104" align="right">
          <template #default="{ row }">
            <b>{{ row.rates[i] === null ? '--' : (row.rates[i] * 100).toFixed(2) + '%' }}</b>
            <span class="qty">{{ row.defects[i] }}/{{ row.totals[i] }}</span>
          </template>
        </el-table-column>
      </el-table>
    </template>

    <template #footer><el-button @click="visible = false">关闭</el-button></template>
  </el-dialog>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import * as echarts from 'echarts/core'
import { LineChart } from 'echarts/charts'
import { GridComponent, LegendComponent, TooltipComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import { getEbayProductStructure } from '@/api/operations/listingPriceTier'
echarts.use([LineChart, GridComponent, LegendComponent, TooltipComponent, CanvasRenderer])

// 与后端 USD_LABELS 同序；最后一条是「总体」，画成灰色粗线当基准。
const COLORS = ['#67b8ae', '#629dce', '#666cc6', '#b07baf', '#d79b5e', '#c9756a', '#8a8f98', '#c9ccd1']
const visible = defineModel({ type: Boolean, default: false })
const loading = ref(false), error = ref(''), chartEl = ref(null)
const year = ref(''), years = ref([]), months = ref([]), series = ref([]), details = ref([]), note = ref('')
let chart = null, observer = null

const labels = computed(() => series.value.filter(s => s.tier_no !== 0).map(s => s.label))
const tableRows = computed(() => details.value.map((item, index) => ({
  month: item.stat_month,
  rates: series.value.filter(s => s.tier_no !== 0).map(s => s.points[index] === null ? null : Number(s.points[index])),
  defects: series.value.filter(s => s.tier_no !== 0).map(s => item.tiers[s.tier_no]?.defect_qty ?? 0),
  totals: series.value.filter(s => s.tier_no !== 0).map(s => item.tiers[s.tier_no]?.total_qty ?? 0),
})))

function option() {
  return {
    tooltip: { trigger: 'axis', valueFormatter: v => v === null || v === undefined ? '--' : (v * 100).toFixed(2) + '%' },
    legend: { bottom: 0, itemWidth: 14, itemHeight: 8, textStyle: { fontSize: 11 } },
    grid: { left: 52, right: 20, top: 16, bottom: 46 },
    xAxis: { type: 'category', data: months.value, axisLabel: { fontSize: 11 } },
    yAxis: { type: 'value', axisLabel: { fontSize: 11, formatter: v => (v * 100).toFixed(0) + '%' } },
    series: series.value.map((item, i) => ({
      // 直线段而不是平滑曲线：平滑会在两个月份之间插出实际不存在的弧线，
      // 看起来像中间还有别的取值；这里每个月只有一个观测点，点到点连直线才准。
      name: item.label, type: 'line', smooth: false,
      showSymbol: true, symbol: 'circle', symbolSize: 5,
      // 后端把"该档该月没有成交"返回成 null，这里保持 null 让线断开，
      // 不要 connectNulls，否则会在没有数据的月份之间画出一段假趋势。
      data: item.points.map(p => p === null ? null : Number(p)),
      lineStyle: { width: item.tier_no === 0 ? 4 : 2 },
      itemStyle: { color: item.tier_no === 0 ? COLORS[7] : COLORS[i] },
      z: item.tier_no === 0 ? 1 : 2,
    })),
  }
}

function render() {
  nextTick(() => {
    if (!chartEl.value) return
    if (!chart) {
      chart = echarts.init(chartEl.value)
      observer = new ResizeObserver(() => chart?.resize())
      observer.observe(chartEl.value)
    }
    chart.setOption(option(), true)
    chart.resize()
  })
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    const { data } = await getEbayProductStructure(year.value)
    months.value = data.months || []
    series.value = data.series || []
    details.value = data.details || []
    note.value = data.note || ''
    years.value = data.years || []
    // 首次打开时后端还不知道要哪一年，拿它给的最新一年回填选择器。
    if (!year.value && years.value.length) year.value = years.value[0]
    render()
  } catch (e) {
    error.value = e?.message || '产品结构加载失败'
  } finally {
    loading.value = false
  }
}

watch(visible, open => { if (open) load() })
onBeforeUnmount(() => { observer?.disconnect(); chart?.dispose(); chart = null })
</script>

<style scoped>
.toolbar { display: flex; align-items: center; gap: 8px; font-size: 12px; margin-bottom: 10px; }
.hint { color: var(--el-text-color-secondary); }
.chart { width: 100%; height: 340px; }
.note { font-size: 12px; color: var(--el-text-color-secondary); line-height: 1.7; margin: 8px 0; }
.qty { display: block; font-size: 10px; color: var(--el-text-color-secondary); font-variant-numeric: tabular-nums; }
</style>
