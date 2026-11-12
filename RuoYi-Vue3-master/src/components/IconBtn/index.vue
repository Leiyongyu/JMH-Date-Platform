<template>
  <el-tooltip
    :content="tooltip"
    placement="top"
    :show-after="120"
    :disabled="!tooltip || tooltipDisabled"
    popper-class="icon-btn__popper"
  >
    <button
      type="button"
      class="icon-btn"
      :class="[
        `icon-btn--${size}`,
        `icon-btn--${type}`,
        {
          'is-active': active,
          'is-disabled': disabled,
          'is-loading': loading,
          'icon-btn--with-label': !!label
        }
      ]"
      :disabled="disabled || loading"
      :aria-label="ariaText"
      :aria-pressed="active ? 'true' : undefined"
      @click="onClick"
    >
      <app-icon
        :name="loading ? 'loading' : icon"
        :size="iconSize"
        :stroke-width="strokeWidth"
        :spin="loading"
        class="icon-btn__icon"
      />
      <span v-if="label" class="icon-btn__label">{{ label }}</span>
      <span v-if="count" class="icon-btn__badge">{{ count > 99 ? '99+' : count }}</span>
    </button>
  </el-tooltip>
</template>

<script setup>
defineOptions({ name: 'IconBtn' })

const props = defineProps({
  /** 图标名，支持 Element Plus 图标名或 src/assets/icons/svg 下的文件名 */
  icon: { type: String, required: true },
  /** 传了文字就变成「图标 + 文字」的轻量按钮（无边框） */
  label: { type: String, default: '' },
  /** 悬停提示；传 null 可关闭 */
  tooltip: { type: String, default: null },
  /** 尺寸 */
  size: { type: String, default: 'md', validator: (v) => ['xs', 'sm', 'md', 'lg'].includes(v) },
  /** 视觉类型：default 透明 / primary 实心 / ghost 描边 / danger 危险 */
  type: { type: String, default: 'default', validator: (v) => ['default', 'primary', 'ghost', 'danger'].includes(v) },
  /** 线宽（仅 Lucide 线性图标生效） */
  strokeWidth: { type: [Number, String], default: 1.9 },
  /** 选中态（用于开关类按钮，如「显示搜索」） */
  active: { type: Boolean, default: false },
  disabled: { type: Boolean, default: false },
  loading: { type: Boolean, default: false },
  /** 角标数字，0 不显示 */
  count: { type: [Number, String], default: 0 },
  /** 无 tooltip 时禁用提示气泡（避免与外部 tooltip 叠加） */
  tooltipDisabled: { type: Boolean, default: false }
})

const emit = defineEmits(['click'])

const sizeMap = { xs: 12, sm: 14, md: 16, lg: 18 }

const iconSize = computed(() => sizeMap[props.size] || 16)

const ariaText = computed(() => props.tooltip || props.label || props.icon)

function onClick(event) {
  if (props.disabled || props.loading) return
  emit('click', event)
}
</script>

<style scoped>
.icon-btn {
  position: relative;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  padding: 0;
  border: 1px solid transparent;
  border-radius: var(--jb-r-md, 6px);
  background: transparent;
  color: var(--jb-ink-500, #5a6b85);
  font-family: inherit;
  font-size: 13px;
  font-weight: 500;
  line-height: 1;
  cursor: pointer;
  user-select: none;
  transition:
    background-color var(--jb-dur, 150ms) var(--jb-ease, ease),
    color var(--jb-dur, 150ms) var(--jb-ease, ease),
    border-color var(--jb-dur, 150ms) var(--jb-ease, ease);
}

/* ---------- 尺寸 ---------- */
.icon-btn--xs { width: var(--jb-h-xs, 24px); height: var(--jb-h-xs, 24px); }
.icon-btn--sm { width: var(--jb-h-sm, 28px); height: var(--jb-h-sm, 28px); }
.icon-btn--md { width: var(--jb-h-md, 32px); height: var(--jb-h-md, 32px); }
.icon-btn--lg { width: var(--jb-h-lg, 36px); height: var(--jb-h-lg, 36px); }

/* 带文字时自动横向展开 */
.icon-btn--with-label {
  width: auto;
  padding: 0 10px;
  gap: 6px;
}
.icon-btn--with-label.icon-btn--sm { padding: 0 8px; }
.icon-btn--with-label.icon-btn--lg { padding: 0 13px; }

/* ---------- 默认（透明） ---------- */
.icon-btn--default:hover:not(.is-disabled) {
  background: var(--jb-hover, #f1f5fb);
  color: var(--jb-ink-900, #0b1526);
}
.icon-btn--default:active:not(.is-disabled) {
  background: var(--jb-pressed, #e7edf7);
}

/* ---------- 主色实心 ---------- */
.icon-btn--primary {
  background: var(--jb-accent, #409eff);
  color: #fff;
}
.icon-btn--primary:hover:not(.is-disabled) {
  background: var(--jb-accent-hover, #337ecc);
}

/* ---------- 描边 ---------- */
.icon-btn--ghost {
  background: var(--jb-surface, #fff);
  border-color: var(--jb-line-strong, #cfd9e8);
  color: var(--jb-ink-700, #24334a);
}
.icon-btn--ghost:hover:not(.is-disabled) {
  border-color: var(--jb-accent, #409eff);
  color: var(--jb-accent, #409eff);
  background: var(--jb-accent-weak, #ecf5ff);
}

/* ---------- 危险 ---------- */
.icon-btn--danger {
  color: var(--jb-danger, #dc2626);
}
.icon-btn--danger:hover:not(.is-disabled) {
  background: var(--jb-danger-bg, #fdecec);
}

/* ---------- 选中态 ---------- */
.icon-btn.is-active {
  background: var(--jb-accent-weak, #ecf5ff);
  color: var(--jb-accent, #409eff);
}

/* ---------- 禁用 ---------- */
.icon-btn.is-disabled,
.icon-btn:disabled {
  opacity: 0.38;
  cursor: not-allowed;
  background: transparent;
}

/* ---------- 加载 ---------- */
.icon-btn.is-loading {
  cursor: progress;
  opacity: 0.85;
}

/* ---------- 焦点 ---------- */
.icon-btn:focus { outline: none; }
.icon-btn:focus-visible {
  outline: 2px solid var(--jb-accent, #409eff);
  outline-offset: 2px;
}

/* ---------- 角标 ---------- */
.icon-btn__badge {
  position: absolute;
  top: -2px;
  right: -2px;
  min-width: 15px;
  height: 15px;
  padding: 0 4px;
  border-radius: 999px;
  background: var(--jb-danger, #dc2626);
  color: #fff;
  font-size: 10px;
  font-weight: 600;
  line-height: 15px;
  text-align: center;
  box-shadow: 0 0 0 2px var(--jb-surface, #fff);
}

@media (prefers-reduced-motion: reduce) {
  .icon-btn { transition: none; }
}
</style>
