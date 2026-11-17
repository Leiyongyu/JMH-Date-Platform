<template>
  <!-- ① 语义图标（Solar 线性） -->
  <component
    :is="lucideComp"
    v-if="lucideComp"
    class="app-icon app-icon--solar"
    :class="{ 'app-icon--spin': spin }"
    :size="numericSize"
    :stroke-width="strokeWidth"
  />

  <!-- ② Element Plus 图标 -->
  <el-icon
    v-else-if="elComp"
    class="app-icon"
    :class="{ 'app-icon--spin': spin }"
    :style="sizeStyle"
    :aria-hidden="true"
  >
    <component :is="elComp" />
  </el-icon>

  <!-- ③ 项目自带 svg 雪碧图（@/assets/icons/svg） -->
  <svg-icon
    v-else
    :icon-class="name"
    class="app-icon app-icon--sprite"
    :class="{ 'app-icon--spin': spin }"
    :style="sizeStyle"
  />
</template>

<script setup>
import * as ElIcons from '@element-plus/icons-vue'
import { resolveLucide } from './registry'

defineOptions({ name: 'AppIcon' })

const props = defineProps({
  /**
   * 图标名，按以下顺序解析：
   *   1. 语义名（refresh / export / columns …）→ Solar linear 线性图标
   *   2. PascalCase（Refresh / Promotion …）    → Element Plus 图标
   *   3. 其他（shopping / money / chart …）      → src/assets/icons/svg
   */
  name: { type: String, required: true },
  /** 尺寸：数字按 px 处理，也可传 '1em' */
  size: { type: [Number, String], default: 16 },
  /** 线宽（仅 Solar 线性生效），密集工具条建议 1.75 */
  strokeWidth: { type: [Number, String], default: 1.9 },
  /** 旋转（加载中） */
  spin: { type: Boolean, default: false }
})

const lucideComp = computed(() => resolveLucide(props.name))
const elComp = computed(() => (lucideComp.value ? null : ElIcons[props.name] || null))

const numericSize = computed(() => {
  const s = props.size
  if (s === undefined || s === null || s === '') return 16
  return s
})

const sizeStyle = computed(() => {
  const s = props.size
  if (s === undefined || s === null || s === '') return null
  return { fontSize: typeof s === 'number' ? `${s}px` : s }
})
</script>

<style scoped>
.app-icon {
  flex: none;
  line-height: 1;
}

.app-icon--sprite {
  width: 1em;
  height: 1em;
  vertical-align: -0.125em;
}

.app-icon--spin {
  animation: app-icon-rotate 1s linear infinite;
}

@keyframes app-icon-rotate {
  to { transform: rotate(360deg); }
}

@media (prefers-reduced-motion: reduce) {
  .app-icon--spin { animation-duration: 2.4s; }
}
</style>
