<template>
  <div ref="chartRef" class="inventory-cost-chart" />
</template>

<script setup>
import * as echarts from 'echarts'
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'

const props = defineProps({
  title: { type: String, default: '' },
  xAxisData: { type: Array, default: () => [] },
  series: { type: Array, default: () => [] }
})

const chartRef = ref()
let chart
let resizeObserver

function compactMoney(value) {
  const number = Number(value || 0)
  if (Math.abs(number) >= 100000000) return `${(number / 100000000).toFixed(1)}亿`
  if (Math.abs(number) >= 10000) return `${(number / 10000).toFixed(1)}万`
  return number.toFixed(0)
}

function renderChart() {
  if (!chartRef.value) return
  chart ||= echarts.init(chartRef.value)
  chart.setOption({
    color: ['#3b82f6', '#10b981', '#f59e0b', '#8b5cf6', '#ef4444', '#06b6d4'],
    title: {
      text: props.title,
      left: 12,
      top: 8,
      textStyle: { color: '#1f2937', fontSize: 15, fontWeight: 600 }
    },
    tooltip: {
      trigger: 'axis',
      valueFormatter: value => `¥${Number(value || 0).toLocaleString('zh-CN', {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2
      })}`
    },
    legend: {
      top: 34,
      left: 12,
      type: 'scroll',
      textStyle: { color: '#64748b', fontSize: 11 }
    },
    grid: { top: 78, left: 18, right: 20, bottom: 16, containLabel: true },
    xAxis: {
      type: 'category',
      boundaryGap: false,
      data: props.xAxisData,
      axisLine: { lineStyle: { color: '#cbd5e1' } },
      axisLabel: { color: '#64748b' }
    },
    yAxis: {
      type: 'value',
      axisLabel: { color: '#64748b', formatter: compactMoney },
      splitLine: { lineStyle: { color: '#eef2f7' } }
    },
    series: props.series.map(item => ({
      ...item,
      type: 'line',
      smooth: true,
      connectNulls: false,
      showSymbol: props.xAxisData.length <= 12,
      symbolSize: 6,
      lineStyle: { width: 2 },
      emphasis: { focus: 'series' }
    }))
  }, true)
}

watch(() => [props.title, props.xAxisData, props.series], () => nextTick(renderChart), { deep: true })

onMounted(() => {
  renderChart()
  resizeObserver = new ResizeObserver(() => chart?.resize())
  resizeObserver.observe(chartRef.value)
})

onBeforeUnmount(() => {
  resizeObserver?.disconnect()
  chart?.dispose()
  chart = undefined
})
</script>

<style scoped>
.inventory-cost-chart {
  width: 100%;
  height: 460px;
}
</style>
