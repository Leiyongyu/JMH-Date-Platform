<template><el-tooltip :content="changeTip(value, current, unit, range)" placement="top" :show-after="200"><span class="comparison-value">{{ label }} {{ changeText(value) }}<small v-if="value?.reason === 'incomplete'">（数据不完整）</small></span></el-tooltip></template>
<script setup>
import { changeText, changeTip } from './comparison'
defineProps({ value: Object, current: [String, Number], unit: String, range: Array, label: String })
</script>
<style scoped>
.comparison-value { font-size: 12px; color: var(--el-text-color-regular); cursor: help; font-variant-numeric: tabular-nums; }
small { display: inline-block; font-size: 11px; color: var(--el-text-color-secondary); }
</style>
