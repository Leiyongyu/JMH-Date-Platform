<template><div v-loading="loading"><div v-show="!empty" ref="element" class="dashboard-chart" role="img" :aria-label="label" /><el-empty v-if="empty && !loading" :description="emptyText" /></div></template>
<script setup>
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import * as echarts from 'echarts'
const props = defineProps({ option: Object, loading: Boolean, empty: Boolean, label: String, emptyText: { type: String, default: '所选范围暂无数据' } })
const element = ref(null)
let chart, observer, disposed = false
async function render() {
  await nextTick()
  if (disposed || !element.value) return
  if (props.empty) { chart?.clear(); return }
  chart ||= echarts.init(element.value)
  chart.setOption(props.option || {}, true)
  chart.resize()
}
watch(() => [props.option, props.empty], render)
onMounted(() => { observer = new ResizeObserver(() => chart?.resize()); observer.observe(element.value); render() })
onBeforeUnmount(() => { disposed = true; observer?.disconnect(); chart?.dispose() })
</script>
<style scoped>.dashboard-chart { height: 370px; width: 100%; min-width: 0; }</style>
