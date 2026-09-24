<template>
  <el-dialog v-model="visible" title="产品结构" width="min(1560px, 97vw)" append-to-body @opened="renderAll">
    <div class="toolbar">
      <span>年份</span>
      <el-select v-model="year" size="small" style="width: 116px" @change="load">
        <el-option v-for="y in years" :key="y" :label="`${y} 年`" :value="y" />
      </el-select>
      <el-button size="small" :disabled="loading" @click="load">刷新</el-button>
      <span class="legend">
        <i v-for="(label, i) in labels" :key="label" :style="{ background: COLORS[i] }" :title="label" />
        <em>{{ labels.join(' · ') }}</em>
      </span>
    </div>

    <el-alert v-if="error" :title="error" type="error" :closable="false" />
    <div v-else v-loading="loading" class="panels">
      <section v-for="panel in panels" :key="panel.key" class="panel">
        <h3>{{ panel.title }}<small v-if="panel.subtitle">{{ panel.subtitle }}</small></h3>
        <div v-if="panel.ready" :ref="el => setChart(panel.key, el)" class="chart" />
        <el-empty v-else :image-size="38" :description="panel.empty" />
        <p class="note">{{ panel.note }}</p>
      </section>
    </div>

    <template #footer><el-button @click="visible = false">关闭</el-button></template>
  </el-dialog>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import * as echarts from 'echarts/core'
import { BarChart, LineChart } from 'echarts/charts'
import { GridComponent, LegendComponent, TooltipComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import { getEbayProductStructure } from '@/api/operations/listingPriceTier'
echarts.use([BarChart, LineChart, GridComponent, LegendComponent, TooltipComponent, CanvasRenderer])

// 与后端 USD_LABELS 同序；第8个留给不良率图里的「总体」基准线。
const COLORS = ['#4a72b0', '#e8913a', '#d6564f', '#6fbfb4', '#5aa25c', '#e5c04a', '#9d6fa8', '#b6bcc4']
const visible = defineModel({ type: Boolean, default: false })
const loading = ref(false), error = ref(''), data = ref(null)
const year = ref(''), years = ref([])
const charts = new Map(), elements = new Map()
let observer = null

const defect = computed(() => data.value || {})
const sales = computed(() => data.value?.sales || {})
const labels = computed(() => (defect.value.series || []).filter(s => s.tier_no !== 0).map(s => s.label))
// 标题右边直接给出这一年的合计，省得逐月悬浮去加。
const salesTotal = computed(() => {
  const rows = sales.value.quantities || []
  if (!rows.length) return ''
  const qty = rows.reduce((sum, x) => sum + (x.matched_qty || 0), 0)
  const orders = rows.reduce((sum, x) => sum + (x.matched_orders || 0), 0)
  return `　全年 ${qty.toLocaleString()} 件 / ${orders.toLocaleString()} 单`
})

// 覆盖率 = 能配上价格档的销量 ÷ 当月总销量。配不上的是当月在售刊登里没有的
// SKU（已下架、或从没在配置的账号里上过架），它们不进任何一档，所以这个数
// 必须写在图下面，否则占比看着像是全部销量的结构。
const salesCoverage = computed(() => {
  const rows = (sales.value.coverage || []).filter(x => x.rate != null)
  if (!rows.length) return ''
  const rates = rows.map(x => Number(x.rate) * 100)
  const low = Math.min(...rates), high = Math.max(...rates)
  return `　本图覆盖当年 ${low.toFixed(1)}%~${high.toFixed(1)}% 的销量。`
})

const panels = computed(() => [
  { key: 'sales', title: '不同价格段销售数量占比',
    subtitle: salesTotal.value,
    ready: (sales.value.months || []).length > 0,
    empty: '该年份没有可统计的销量',
    note: (sales.value.note || '') + salesCoverage.value },
  { key: 'defect', title: '不同价格段不良交易率',
    ready: (defect.value.months || []).length > 0,
    empty: '该年份没有可统计的不良交易',
    note: defect.value.note || '' },
  { key: 'conversion', title: '不同价格段转化率',
    ready: false,
    empty: '转化率数据源尚未接入',
    note: '转化率需要曝光/访问量数据，当前库里没有对应来源，接入后此处自动出图。' },
])

function setChart(key, el) {
  if (el) elements.set(key, el)
}

// 年份已经在上面筛过了，横坐标只留月份数字；类目值仍是完整的 2026-08，
// 悬浮提示里看到的还是年月，不会丢上下文。
const monthLabel = value => String(Number(String(value).slice(5)) || value)

function salesOption() {
  const months = sales.value.months || []
  const qty = Object.fromEntries((sales.value.quantities || []).map(x => [x.stat_month, x]))
  return {
    // 占比之外把绝对量也带上：光看百分比分不清是"卖得多"还是"基数小"。
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' },
      formatter: params => {
        if (!params.length) return ''
        const month = params[0].axisValue
        const info = qty[month] || { tiers: {} }
        const lines = params.filter(p => p.value !== null && p.value !== undefined).map(p => {
          const tier = (sales.value.series || []).find(s => s.label === p.seriesName)
          const cell = info.tiers?.[tier?.tier_no] || {}
          return `${p.marker}${p.seriesName}　<b>${(p.value * 100).toFixed(1)}%</b>`
            + `　${cell.qty ?? 0} 件 / ${cell.order_rows ?? 0} 单`
        })
        return `${month}　合计 ${info.matched_qty ?? 0} 件 / ${info.matched_orders ?? 0} 单<br/>`
          + lines.join('<br/>')
      } },
    legend: { bottom: 0, itemWidth: 12, itemHeight: 8, textStyle: { fontSize: 10 } },
    grid: { left: 46, right: 12, top: 12, bottom: 44 },
    xAxis: { type: 'category', data: months, axisLabel: { fontSize: 11, formatter: monthLabel } },
    yAxis: { type: 'value', max: 1, axisLabel: { fontSize: 10, formatter: v => (v * 100).toFixed(0) + '%' } },
    // 堆叠百分比柱：每个月各档相加为100%，看的是结构而不是绝对量。
    series: (sales.value.series || []).map((item, i) => ({
      name: item.label, type: 'bar', stack: 'total', barMaxWidth: 30,
      data: item.points.map(p => p === null ? null : Number(p)),
      itemStyle: { color: COLORS[i] },
      // 段太薄时标不下，只在占比够大的段上直接标销量件数。
      label: {
        show: true, fontSize: 9, color: '#fff', formatter: p => {
          const cell = qty[months[p.dataIndex]]?.tiers?.[item.tier_no] || {}
          return p.value >= 0.08 && cell.qty ? cell.qty : ''
        },
      },
    })),
  }
}

function defectOption() {
  const months = defect.value.months || []
  return {
    tooltip: { trigger: 'axis',
      valueFormatter: v => v === null || v === undefined ? '--' : (v * 100).toFixed(2) + '%' },
    legend: { bottom: 0, itemWidth: 12, itemHeight: 8, textStyle: { fontSize: 10 } },
    grid: { left: 46, right: 12, top: 12, bottom: 44 },
    xAxis: { type: 'category', data: months, axisLabel: { fontSize: 11, formatter: monthLabel } },
    yAxis: { type: 'value', axisLabel: { fontSize: 10, formatter: v => (v * 100).toFixed(0) + '%' } },
    series: (defect.value.series || []).map((item, i) => ({
      // 点到点直线：平滑会在两个月之间插出实际不存在的取值。
      name: item.label, type: 'line', smooth: false,
      showSymbol: true, symbol: 'circle', symbolSize: 4,
      // null 保持断开，不用 connectNulls，否则没有成交的月份会连出假趋势。
      data: item.points.map(p => p === null ? null : Number(p)),
      lineStyle: { width: item.tier_no === 0 ? 3.5 : 1.8 },
      itemStyle: { color: item.tier_no === 0 ? COLORS[7] : COLORS[i] },
      z: item.tier_no === 0 ? 1 : 2,
    })),
  }
}

const OPTIONS = { sales: salesOption, defect: defectOption }

function renderAll() {
  nextTick(() => {
    if (!observer) observer = new ResizeObserver(() => charts.forEach(c => c.resize()))
    for (const panel of panels.value) {
      const el = elements.get(panel.key)
      if (!panel.ready || !el || !OPTIONS[panel.key]) continue
      let chart = charts.get(panel.key)
      if (!chart) {
        chart = echarts.init(el)
        charts.set(panel.key, chart)
        observer.observe(el)
      }
      chart.setOption(OPTIONS[panel.key](), true)
      chart.resize()
    }
  })
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    const response = await getEbayProductStructure(year.value)
    data.value = response.data
    years.value = response.data?.years || []
    // 首次打开时后端还不知道要哪一年，拿它给的最新一年回填选择器。
    if (!year.value && years.value.length) year.value = years.value[0]
    renderAll()
  } catch (e) {
    error.value = e?.message || '产品结构加载失败'
  } finally {
    loading.value = false
  }
}

watch(visible, open => { if (open) load() })
onBeforeUnmount(() => {
  observer?.disconnect()
  charts.forEach(c => c.dispose())
  charts.clear()
})
</script>

<style scoped>
.toolbar { display: flex; align-items: center; gap: 8px; font-size: 12px; margin-bottom: 8px; }
.legend { display: flex; align-items: center; gap: 4px; margin-left: auto; color: var(--el-text-color-secondary); }
.legend i { width: 11px; height: 8px; border-radius: 2px; display: inline-block; }
.legend em { font-style: normal; margin-left: 6px; font-size: 11px; }
/* 三图并排；窄屏自动落到一列，不横向滚动。 */
.panels { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 14px; }
@media (max-width: 1100px) { .panels { grid-template-columns: 1fr; } }
.panel { min-width: 0; }
.panel h3 { font-size: 13px; font-weight: 600; margin: 0 0 6px; }
.panel h3 small { font-weight: 400; font-size: 11px; color: var(--el-text-color-secondary); }
.chart { width: 100%; height: 320px; }
.note { font-size: 11px; color: var(--el-text-color-secondary); line-height: 1.6; margin: 6px 0 0; }
</style>
