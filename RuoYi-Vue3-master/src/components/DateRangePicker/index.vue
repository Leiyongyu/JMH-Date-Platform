<template>
  <el-popover
    v-model:visible="open"
    trigger="click"
    placement="bottom-start"
    width="auto"
    :offset="8"
    :show-arrow="false"
    :disabled="disabled"
    :popper-style="popperStyle"
    @before-enter="syncDraft"
    @after-leave="hover = null"
  >
    <template #reference>
      <button
        type="button"
        class="jmh-drp jmh-drp-trigger"
        :class="{ 'is-open': open, 'is-disabled': disabled }"
        :style="width ? { width } : null"
        :disabled="disabled"
        :aria-expanded="open"
        aria-haspopup="dialog"
      >
        <svg class="ico" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round">
          <rect x="3" y="5" width="18" height="16" rx="3" /><path d="M8 3v4M16 3v4M3 10h18" />
        </svg>
        <span class="val" :class="{ empty: !hasValue }">
          <template v-if="hasValue">
            <span>{{ modelValue[0] }}</span><span class="sep">{{ rangeSeparator }}</span><span>{{ modelValue[1] }}</span>
          </template>
          <template v-else>{{ placeholderText }}</template>
        </span>
        <svg class="caret" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.6" stroke-linecap="round">
          <path d="M6 9l6 6 6-6" />
        </svg>
      </button>
    </template>

    <div class="jmh-drp jmh-drp-panel" role="dialog" :aria-label="placeholderText" @mouseleave="hover = null">
      <div v-if="presetList.length" class="dp-presets">
        <div class="p-title">快捷选择</div>
        <button
          v-for="preset in presetList"
          :key="preset.key"
          type="button"
          class="preset"
          :class="{ active: activePreset === preset.key }"
          :disabled="outOfBounds(preset.range[0]) || outOfBounds(preset.range[1])"
          @click="applyPreset(preset)"
        >{{ preset.label }}</button>
      </div>

      <div class="dp-main">
        <div class="dp-body">
          <div class="dp-calendars">
            <div v-for="(panel, index) in panels" :key="panel.key" class="cal" :class="{ 'cal--month': isMonth }">
              <div class="cal-head">
                <div class="nav-group">
                  <template v-if="index === 0">
                    <button type="button" class="nav-btn" aria-label="上一年" @click="navigate(-12)">«</button>
                    <button v-if="!isMonth" type="button" class="nav-btn" aria-label="上个月" @click="navigate(-1)">‹</button>
                  </template>
                </div>
                <div class="cal-title">{{ panel.year }} 年<small v-if="!isMonth">{{ panel.month + 1 }} 月</small></div>
                <div class="nav-group">
                  <template v-if="index === panels.length - 1">
                    <button v-if="!isMonth" type="button" class="nav-btn" aria-label="下个月" @click="navigate(1)">›</button>
                    <button type="button" class="nav-btn" aria-label="下一年" @click="navigate(12)">»</button>
                  </template>
                </div>
              </div>
              <div v-if="!isMonth" class="week">
                <span v-for="(label, i) in WEEK_LABELS" :key="label" :class="{ wk: i === 0 || i === 6 }">{{ label }}</span>
              </div>
              <div class="grid" :class="{ 'grid--month': isMonth }">
                <button
                  v-for="cell in panel.cells"
                  :key="cell.value"
                  type="button"
                  class="day"
                  :class="cellClass(cell)"
                  :disabled="isDisabled(cell.value)"
                  :aria-label="cell.value"
                  :aria-pressed="cell.value === draft.start || cell.value === draft.end"
                  @click="pick(cell.value)"
                  @mouseenter="onHover(cell.value)"
                ><span class="num">{{ cell.label }}</span></button>
              </div>
            </div>
          </div>
        </div>

        <div class="dp-foot">
          <div class="dp-summary">
            <template v-if="draft.start && draft.end">
              已选 <b>{{ spanLength(draft.start, draft.end, mode) }}</b> {{ unitLabel }}<span class="dot">|</span>{{ draft.start }} → {{ draft.end }}
            </template>
            <template v-else-if="draft.start">
              请选择结束{{ isMonth ? '月份' : '日期' }}<span class="dot">|</span>起始 {{ draft.start }}
            </template>
            <template v-else>请选择开始{{ isMonth ? '月份' : '日期' }}</template>
          </div>
          <div class="dp-foot-actions">
            <button v-if="clearable" type="button" class="btn-sm" @click="clearDraft">清空</button>
            <button type="button" class="btn-sm btn-sm--primary" :disabled="!draft.start && !clearable" @click="confirm">确定</button>
          </div>
        </div>
      </div>
    </div>
  </el-popover>
</template>

<script setup>
// 通用时间段选择器：mode="date" 选日期区间（YYYY-MM-DD），mode="month" 选月份区间（YYYY-MM）。
// v-model 为 [开始, 结束] 或 null；只点一个值就确定时，开始和结束取同一个值。
import { computed, reactive, ref } from 'vue'
import {
  WEEK_LABELS, buildDateCells, buildMonthCells, cellClasses, defaultPresets, formatDate, formatMonth,
  parseValue, pickValue, resolveRange, shiftMonth, spanLength
} from './rangeUtils'

const props = defineProps({
  modelValue: { type: Array, default: null },
  mode: { type: String, default: 'date', validator: value => ['date', 'month'].includes(value) },
  // 不传用默认快捷项；传 [] 隐藏快捷栏；自定义项格式 { key, label, range: [start, end] }
  presets: { type: Array, default: null },
  min: { type: String, default: '' },
  max: { type: String, default: '' },
  // 区间最长跨度（天或月），0 表示不限
  maxSpan: { type: Number, default: 0 },
  disabledDate: { type: Function, default: null },
  placeholder: { type: String, default: '' },
  rangeSeparator: { type: String, default: '至' },
  clearable: { type: Boolean, default: true },
  disabled: { type: Boolean, default: false },
  width: { type: String, default: '' }
})
const emit = defineEmits(['update:modelValue', 'change'])

const popperStyle = {
  padding: 0,
  borderRadius: '16px',
  border: '1px solid #e5eef4',
  overflow: 'hidden',
  boxShadow: '0 24px 60px -12px rgba(11,107,152,.25), 0 4px 14px rgba(11,107,152,.08)'
}

const open = ref(false)
const hover = ref(null)
const activePreset = ref(null)
const draft = reactive({ start: null, end: null })
const view = reactive({ y: new Date().getFullYear(), m: new Date().getMonth() })

const isMonth = computed(() => props.mode === 'month')
const unitLabel = computed(() => (isMonth.value ? '个月' : '天'))
const hasValue = computed(() => Array.isArray(props.modelValue) && !!props.modelValue[0] && !!props.modelValue[1])
const placeholderText = computed(() => props.placeholder || (isMonth.value ? '请选择月份范围' : '请选择日期范围'))
const presetList = computed(() => props.presets || defaultPresets(props.mode))
const todayValue = computed(() => {
  const now = new Date()
  return isMonth.value ? formatMonth(now.getFullYear(), now.getMonth()) : formatDate(now)
})

// 月份模式：两个年份面板；日期模式：两个相邻月份面板。
const panels = computed(() => {
  if (isMonth.value) {
    return [view.y, view.y + 1].map(year => ({ key: `y${year}`, year, cells: buildMonthCells(year) }))
  }
  const next = shiftMonth(view.y, view.m, 1)
  return [{ y: view.y, m: view.m }, next].map(({ y, m }) => ({
    key: `m${y}-${m}`, year: y, month: m, cells: buildDateCells(y, m)
  }))
})
const range = computed(() => resolveRange(draft.start, draft.end, hover.value))

function outOfBounds(value) {
  if (props.min && value < props.min) return true
  if (props.max && value > props.max) return true
  return !!(props.disabledDate && props.disabledDate(value))
}

function isDisabled(value) {
  if (outOfBounds(value)) return true
  if (props.maxSpan && draft.start && !draft.end) {
    const [a, b] = value < draft.start ? [value, draft.start] : [draft.start, value]
    return spanLength(a, b, props.mode) > props.maxSpan
  }
  return false
}

function cellClass(cell) {
  const classes = cellClasses(cell.value, range.value)
  if (cell.other) classes.push('other')
  if (cell.value === todayValue.value) classes.push('is-today')
  return classes
}

function showAround(start, end) {
  if (!start) return
  const a = parseValue(start)
  if (isMonth.value) {
    // 让结束年份落在右侧面板，跨度超过两年时以开始年份为准。
    const endYear = end ? parseValue(end).y : a.y
    view.y = Math.max(a.y, endYear - 1)
  } else {
    view.y = a.y
    view.m = a.m
  }
}

function syncDraft() {
  const [start, end] = hasValue.value ? props.modelValue : [null, null]
  draft.start = start
  draft.end = end
  hover.value = null
  activePreset.value = presetList.value.find(p => p.range[0] === start && p.range[1] === end)?.key || null
  if (start) showAround(start, end)
  else showAround(todayValue.value, todayValue.value)
}

function navigate(delta) {
  if (isMonth.value) {
    view.y += delta / 12
    return
  }
  const next = shiftMonth(view.y, view.m, delta)
  view.y = next.y
  view.m = next.m
}

function pick(value) {
  Object.assign(draft, pickValue(draft, value))
  hover.value = null
  activePreset.value = null
}

function onHover(value) {
  if (draft.start && !draft.end && !isDisabled(value)) hover.value = value
}

function applyPreset(preset) {
  draft.start = preset.range[0]
  draft.end = preset.range[1]
  hover.value = null
  activePreset.value = preset.key
  showAround(draft.start, draft.end)
}

function clearDraft() {
  draft.start = null
  draft.end = null
  hover.value = null
  activePreset.value = null
}

function confirm() {
  const value = draft.start ? [draft.start, draft.end || draft.start] : null
  open.value = false
  emit('update:modelValue', value)
  emit('change', value)
}
</script>

<style scoped>
.jmh-drp {
  --sky-50: #f2f9ff;
  --sky-100: #e4f2fe;
  --sky-200: #c6e6fb;
  --sky-300: #92d3f8;
  --sky-400: #4cbcf1;
  --sky-500: #1ba4e0;
  --sky-600: #0d86bd;
  --sky-700: #0b6b98;
  --ink-900: #0f2333;
  --ink-700: #35505f;
  --ink-500: #6b8595;
  --ink-400: #9aafbb;
  --line: #e5eef4;
  font-family: inherit;
}

/* 触发器 */
.jmh-drp-trigger {
  height: 32px;
  min-width: 240px;
  display: inline-flex;
  align-items: center;
  gap: 9px;
  padding: 0 12px;
  background: #fff;
  border: 1px solid var(--line);
  border-radius: 8px;
  font-size: 13px;
  color: var(--ink-700);
  font-variant-numeric: tabular-nums;
  cursor: pointer;
  transition: border-color .18s, box-shadow .18s;
  vertical-align: middle;
}
.jmh-drp-trigger:hover { border-color: var(--sky-300); }
.jmh-drp-trigger.is-open,
.jmh-drp-trigger:focus-visible {
  outline: none;
  border-color: var(--sky-400);
  box-shadow: 0 0 0 3px rgba(76, 188, 241, .18);
}
.jmh-drp-trigger.is-disabled { cursor: not-allowed; background: #f5f7fa; color: var(--ink-400); }
.jmh-drp-trigger .ico { color: var(--sky-500); flex-shrink: 0; }
.jmh-drp-trigger .val { flex: 1; text-align: left; letter-spacing: .2px; white-space: nowrap; }
.jmh-drp-trigger .val .sep { color: var(--ink-400); margin: 0 6px; font-size: 12.5px; }
.jmh-drp-trigger .val.empty { color: var(--ink-400); }
.jmh-drp-trigger .caret { color: var(--ink-400); transition: transform .2s; flex-shrink: 0; }
.jmh-drp-trigger.is-open .caret { transform: rotate(180deg); color: var(--sky-500); }

/* 面板 */
.jmh-drp-panel { display: flex; background: #fff; color: var(--ink-900); }
.dp-main { display: flex; flex-direction: column; }

.dp-presets {
  width: 116px;
  flex-shrink: 0;
  padding: 14px 10px;
  background: #fafdff;
  border-right: 1px solid var(--line);
  display: flex;
  flex-direction: column;
  gap: 3px;
}
.dp-presets .p-title { font-size: 11px; font-weight: 600; color: var(--ink-400); letter-spacing: 1px; padding: 2px 8px 8px; }
.preset {
  text-align: left;
  padding: 7px 10px;
  font-size: 12.5px;
  color: var(--ink-700);
  background: transparent;
  border: none;
  border-radius: 7px;
  cursor: pointer;
  transition: all .15s;
  font-family: inherit;
}
.preset:hover { background: var(--sky-100); color: var(--sky-700); }
.preset.active { background: var(--sky-500); color: #fff; font-weight: 500; }
.preset:disabled { opacity: .4; cursor: not-allowed; background: transparent; color: var(--ink-700); }

.dp-body { padding: 14px 16px 10px; }
.dp-calendars { display: flex; gap: 18px; }
.cal { width: 268px; }
.cal--month { width: 228px; }

.cal-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 10px; padding: 0 2px; }
.cal-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--ink-900);
  font-variant-numeric: tabular-nums;
  letter-spacing: .4px;
  display: flex;
  align-items: baseline;
  gap: 5px;
}
.cal-title small { font-size: 12px; font-weight: 400; color: var(--ink-400); }
.nav-group { display: flex; gap: 2px; min-width: 58px; }
.cal-head .nav-group:last-child { justify-content: flex-end; }
.nav-btn {
  width: 26px;
  height: 26px;
  border-radius: 7px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: transparent;
  border: none;
  cursor: pointer;
  color: var(--ink-500);
  font-size: 12px;
  transition: all .15s;
}
.nav-btn:hover { background: var(--sky-100); color: var(--sky-600); }
.nav-btn:active { transform: scale(.94); }

.week { display: grid; grid-template-columns: repeat(7, 1fr); margin-bottom: 4px; }
.week span { text-align: center; font-size: 12px; color: var(--ink-400); font-weight: 500; padding: 6px 0; }
.week span.wk { color: var(--sky-500); }

.grid { display: grid; grid-template-columns: repeat(7, 1fr); }
.grid--month { grid-template-columns: repeat(3, 1fr); row-gap: 8px; }

.day {
  height: 36px;
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
  background: transparent;
  border: none;
  padding: 0;
  cursor: pointer;
  font-family: inherit;
  font-size: 13px;
  color: var(--ink-900);
  font-variant-numeric: tabular-nums;
  transition: background .13s ease, color .13s ease;
  border-radius: 0;
}
.day .num {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  position: relative;
  z-index: 2;
  transition: all .15s ease;
}
.grid--month .day { height: 40px; }
.grid--month .day .num { width: 56px; height: 34px; border-radius: 17px; }
.day:hover .num { background: var(--sky-100); }
.day.other { color: #c3d3dd; }
.day.other:hover .num { background: #f2f7fa; }
.day:disabled { cursor: not-allowed; color: #c9d6de; }
.day:disabled .num { background: transparent; }

/* 区间连续高亮 */
.day.in-range { background: #e9f5fe; }
.day.in-range:hover { background: #dceffc; }
.day.in-range .num { color: var(--sky-700); font-weight: 500; }
.day.range-start { border-radius: 18px 0 0 18px; }
.day.range-end { border-radius: 0 18px 18px 0; }
.day.range-start.range-end { border-radius: 18px; }

/* 区间端点 */
.day.is-start .num,
.day.is-end .num,
.day.is-start:hover .num,
.day.is-end:hover .num {
  background: linear-gradient(140deg, #3fbbf0, var(--sky-600));
  color: #fff;
  font-weight: 600;
  box-shadow: 0 4px 10px rgba(13, 134, 189, .32);
}
/* 悬停预览端点 */
.day.is-preview .num {
  background: #fff;
  color: var(--sky-600);
  box-shadow: inset 0 0 0 1.5px var(--sky-400);
  font-weight: 600;
}

/* 今天 / 本月 */
.day.is-today .num::after {
  content: "";
  position: absolute;
  bottom: 4px;
  left: 50%;
  transform: translateX(-50%);
  width: 4px;
  height: 4px;
  border-radius: 50%;
  background: var(--sky-500);
}
.grid--month .day.is-today .num::after { bottom: 3px; }
.day.is-today.is-start .num::after,
.day.is-today.is-end .num::after { background: #fff; }

.day:focus-visible { outline: none; }
.day:focus-visible .num { box-shadow: 0 0 0 2px var(--sky-500), 0 0 0 4px #fff; }

/* 页脚 */
.dp-foot {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 11px 16px;
  border-top: 1px solid var(--line);
  background: #fafdff;
  margin-top: auto;
}
.dp-summary { font-size: 12.5px; color: var(--ink-500); line-height: 1.5; }
.dp-summary b { color: var(--sky-700); font-weight: 600; font-variant-numeric: tabular-nums; }
.dp-summary .dot { color: var(--line); margin: 0 6px; }
.dp-foot-actions { margin-left: auto; display: flex; gap: 8px; }
.btn-sm {
  height: 30px;
  padding: 0 14px;
  border-radius: 8px;
  font-size: 12.5px;
  font-weight: 500;
  cursor: pointer;
  border: 1px solid var(--line);
  background: #fff;
  color: var(--ink-700);
  transition: all .15s;
  font-family: inherit;
}
.btn-sm:hover { border-color: var(--sky-300); color: var(--sky-600); }
.btn-sm--primary {
  background: linear-gradient(135deg, #35b4ea, var(--sky-600));
  border: none;
  color: #fff;
  box-shadow: 0 2px 8px rgba(13, 134, 189, .28);
}
.btn-sm--primary:hover { color: #fff; box-shadow: 0 4px 12px rgba(13, 134, 189, .36); }
.btn-sm:disabled { opacity: .5; cursor: not-allowed; }
</style>
