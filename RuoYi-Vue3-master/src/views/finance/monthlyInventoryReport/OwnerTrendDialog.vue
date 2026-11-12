<template>
  <el-dialog
    :model-value="modelValue"
    title="个人趋势分析"
    width="1240px"
    top="4vh"
    class="owner-trend-dialog"
    destroy-on-close
    @update:model-value="value => emit('update:modelValue', value)"
    @opened="handleOpened"
    @closed="disposeCharts"
  >
    <div class="owner-trend-toolbar">
      <el-date-picker
        v-model="monthRange"
        type="monthrange"
        value-format="YYYY-MM"
        format="YYYY年MM月"
        range-separator="至"
        start-placeholder="开始月份"
        end-placeholder="结束月份"
        :clearable="false"
        :disabled-date="disabledMonth"
        style="width: 300px"
        @change="loadTrend"
      />
      <el-select
        v-model="selectedOwners"
        multiple
        filterable
        collapse-tags
        collapse-tags-tooltip
        :max-collapse-tags="4"
        placeholder="选择负责人"
        style="width: 460px"
        @change="renderCharts"
      >
        <el-option v-for="owner in owners" :key="owner" :label="owner" :value="owner" />
      </el-select>
      <el-button link type="primary" @click="selectAllOwners">全选</el-button>
      <el-button link @click="clearOwners">清空</el-button>
    </div>
    <p class="owner-trend-note">
      销售额、毛利取绩效排名（AMZ + eBay 合并，CNY）；周转天数（货值）和 181 天以上库龄成本取个人维度快照，
      同一负责人分在多个组别时合并计算。断点表示该月没有数据（如下月销售未出、该月未计算个人维度）。
    </p>
    <div v-loading="loading" class="owner-trend-grid">
      <div v-for="chart in CHARTS" :key="chart.key" class="owner-trend-card">
        <div class="owner-trend-card__title">{{ chart.title }}</div>
        <div :ref="el => setChartRef(chart.key, el)" class="owner-trend-card__chart" />
      </div>
    </div>
  </el-dialog>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, ref } from 'vue'
import * as echarts from 'echarts'
import { ElMessage } from 'element-plus'
import { getMonthlyInventoryOwnerTrend } from '@/api/finance/monthlyInventoryReport'

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  // 页面当前选中的报表月（YYYY-MM），作为默认结束月份
  endMonth: { type: String, default: '' }
})
const emit = defineEmits(['update:modelValue'])

const CHARTS = [
  { key: 'sales_amount', title: '销售额（CNY）', unit: 'money' },
  { key: 'gross_profit', title: '毛利（CNY）', unit: 'money' },
  { key: 'turnover_days', title: '库龄周转：周转天数（货值）', unit: 'days' },
  { key: 'aged_181_plus_cost', title: '滞销品清货：181天以上库龄成本（CNY）', unit: 'money' }
]
const EXCLUDED_BY_DEFAULT = new Set(['未分配', '注销'])
const MAX_MONTHS = 24

const monthRange = ref([])
const loading = ref(false)
const trend = ref({ months: [], owners: [], series: {} })
const selectedOwners = ref([])
const owners = computed(() => trend.value.owners || [])
const chartRefs = {}
const charts = {}
let resizeObserver = null

function shiftMonth(month, offset) {
  const [year, value] = month.split('-').map(Number)
  const index = year * 12 + value - 1 + offset
  return `${Math.floor(index / 12)}-${String((index % 12) + 1).padStart(2, '0')}`
}

function currentMonth() {
  const now = new Date()
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`
}

function disabledMonth(date) {
  return date.getTime() > Date.now()
}

function setChartRef(key, el) {
  if (el) chartRefs[key] = el
}

async function handleOpened() {
  const end = /^20\d{2}-\d{2}$/.test(props.endMonth) ? props.endMonth : currentMonth()
  monthRange.value = [shiftMonth(end, -5), end]
  selectedOwners.value = []
  await loadTrend()
}

async function loadTrend() {
  const [start, end] = monthRange.value || []
  if (!start || !end) return
  const span = (Number(end.slice(0, 4)) - Number(start.slice(0, 4))) * 12
    + Number(end.slice(5)) - Number(start.slice(5)) + 1
  if (span > MAX_MONTHS) {
    ElMessage.warning(`时间段最多 ${MAX_MONTHS} 个月`)
    return
  }
  loading.value = true
  try {
    const response = await getMonthlyInventoryOwnerTrend(start, end)
    trend.value = response.data || { months: [], owners: [], series: {} }
    const available = new Set(owners.value)
    const kept = selectedOwners.value.filter(owner => available.has(owner))
    selectedOwners.value = kept.length
      ? kept
      : owners.value.filter(owner => !EXCLUDED_BY_DEFAULT.has(owner))
  } finally {
    loading.value = false
  }
  await nextTick()
  renderCharts()
}

function selectAllOwners() {
  selectedOwners.value = [...owners.value]
  renderCharts()
}

function clearOwners() {
  selectedOwners.value = []
  renderCharts()
}

function formatValue(value, unit) {
  if (value === null || value === undefined) return '--'
  if (unit === 'days') return `${Number(value).toFixed(1)} 天`
  return Number(value).toLocaleString('zh-CN', { maximumFractionDigits: 0 })
}

function axisLabel(value, unit) {
  if (unit === 'days') return value
  if (Math.abs(value) >= 10000) return `${(value / 10000).toFixed(Math.abs(value) >= 100000 ? 0 : 1)}万`
  return value
}

function chartOption(chart) {
  const months = trend.value.months || []
  return {
    color: ['#1257d6', '#12b2a6', '#7c6fe0', '#e8933f', '#e06c8b', '#4e8de8', '#0e45a8',
      '#5470c6', '#91cc75', '#ea7ccc', '#d48265', '#2f4554', '#61a0a8', '#c4ccd3'],
    tooltip: {
      trigger: 'axis',
      confine: true,
      order: 'valueDesc',
      valueFormatter: value => formatValue(value, chart.unit)
    },
    legend: { type: 'scroll', bottom: 0, itemWidth: 14, itemHeight: 8, textStyle: { fontSize: 12 } },
    grid: { left: 12, right: 18, top: 16, bottom: 36, containLabel: true },
    xAxis: {
      type: 'category',
      boundaryGap: false,
      data: months.map(month => `${month.slice(0, 4)}.${Number(month.slice(5))}月`)
    },
    yAxis: {
      type: 'value',
      scale: chart.unit === 'days',
      axisLabel: { formatter: value => axisLabel(value, chart.unit) },
      splitLine: { lineStyle: { type: 'dashed', color: '#e9eef6' } }
    },
    series: selectedOwners.value.map(owner => ({
      name: owner,
      type: 'line',
      smooth: false,
      connectNulls: false,
      symbol: 'circle',
      symbolSize: 6,
      emphasis: { focus: 'series' },
      data: trend.value.series?.[owner]?.[chart.key] || months.map(() => null)
    }))
  }
}

function renderCharts() {
  CHARTS.forEach(chart => {
    const el = chartRefs[chart.key]
    if (!el) return
    if (!charts[chart.key]) charts[chart.key] = echarts.init(el)
    charts[chart.key].setOption(chartOption(chart), { notMerge: true })
  })
  if (!resizeObserver && typeof ResizeObserver !== 'undefined') {
    resizeObserver = new ResizeObserver(() => Object.values(charts).forEach(item => item.resize()))
    Object.values(chartRefs).forEach(el => resizeObserver.observe(el))
  }
}

function disposeCharts() {
  resizeObserver?.disconnect()
  resizeObserver = null
  Object.keys(charts).forEach(key => {
    charts[key].dispose()
    delete charts[key]
  })
  Object.keys(chartRefs).forEach(key => delete chartRefs[key])
}

onBeforeUnmount(disposeCharts)
</script>

<style scoped>
.owner-trend-toolbar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 10px;
}

.owner-trend-note {
  margin: 10px 0 12px;
  color: #8a99b0;
  font-size: 12px;
  line-height: 1.6;
}

.owner-trend-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 14px;
  min-height: 300px;
}

.owner-trend-card {
  border: 1px solid var(--jb-line, #e3e9f2);
  border-radius: 6px;
  padding: 10px 12px 6px;
  background: #fff;
}

.owner-trend-card__title {
  font-size: 14px;
  font-weight: 600;
  color: #24334a;
}

.owner-trend-card__chart {
  height: 320px;
}

@media (max-width: 900px) {
  .owner-trend-grid {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
