<template>
  <span class="trend-value" :class="direction ? `trend-${direction}` : ''" :style="direction ? { color: trendColors[direction] } : undefined">
    <span v-if="direction" class="trend-arrow" :aria-label="direction === 'up' ? '增加' : '减少'">{{ direction === 'up' ? '↑' : '↓' }}</span>
    <span><slot /></span>
  </span>
</template>
<script setup>
import { computed } from 'vue'
import { trendDirection, trendColors } from './trend'
const props = defineProps({ value: [String, Number] })
const direction = computed(() => trendDirection(props.value))
</script>
<style scoped>
.trend-value { display: inline-flex; align-items: baseline; gap: 3px; white-space: nowrap; font-variant-numeric: tabular-nums; }
.trend-arrow { font-weight: 700; }
</style>
