<template>
  <svg
    class="brand-mark"
    :width="size"
    :height="size"
    viewBox="0 0 24 24"
    role="img"
    :aria-label="alt"
  >
    <defs>
      <linearGradient :id="`${uid}-tile`" x1="0" y1="0" x2="1" y2="1">
        <stop offset="0" stop-color="#0B3D93" />
        <stop offset=".5" stop-color="#1268C9" />
        <stop offset="1" stop-color="#12B2A6" />
      </linearGradient>
      <linearGradient :id="`${uid}-ink`" x1="0" y1="0" x2="1" y2="1">
        <stop offset="0" stop-color="#0E45A8" />
        <stop offset="1" stop-color="#12B2A6" />
      </linearGradient>
    </defs>

    <!-- 深底：白底瓷砖 + 渐变字 -->
    <template v-if="variant === 'onDark'">
      <rect width="24" height="24" rx="6.2" fill="#fff" />
      <path :d="J" fill="none" :stroke="`url(#${uid}-ink)`" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" />
    </template>

    <!-- 浅底：渐变瓷砖 + 白字（与浏览器 favicon 完全一致） -->
    <template v-else>
      <rect width="24" height="24" rx="6.2" :fill="`url(#${uid}-tile)`" />
      <path :d="J" fill="none" stroke="#fff" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" />
    </template>
  </svg>
</template>

<script setup>
defineOptions({ name: 'BrandMark' })

defineProps({
  /** 尺寸（px） */
  size: { type: [Number, String], default: 28 },
  /** onDark = 放在深色背景上；onLight = 放在浅色背景上（默认，等同 favicon） */
  variant: { type: String, default: 'onLight', validator: v => ['onLight', 'onDark'].includes(v) },
  alt: { type: String, default: 'JMH' }
})

const uid = `bm${Math.random().toString(36).slice(2, 7)}`
const J = 'M14.9 5.8 L14.9 13.2 C14.9 16.6 12.8 18.5 10.1 18.5 C7.7 18.5 6.1 17.1 5.6 15.2'
</script>

<style scoped>
.brand-mark {
  display: block;
  flex: none;
}
</style>
