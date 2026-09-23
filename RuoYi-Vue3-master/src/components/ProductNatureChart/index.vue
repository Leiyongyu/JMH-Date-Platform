<template>
  <section class="nature-panel" v-loading="loading" :aria-labelledby="`nature-title-${platform}`">
    <header>
      <div><span class="eyebrow">{{ platform === 'amz' ? 'AMAZON' : 'EBAY' }} · 商品结构</span><h2 :id="`nature-title-${platform}`">新老品月度趋势</h2></div>
      <el-button icon="Refresh" circle size="small" :loading="loading" title="刷新报表，不拉取外部数据" aria-label="刷新新老品趋势" @click="load" />
    </header>
    <div class="month-filter">
      <el-select v-model="segment" size="small" class="segment-filter" :aria-label="platform === 'amz' ? '区域' : '站点'">
        <el-option v-for="option in options" :key="option.value" :value="option.value" :label="option.label" />
      </el-select>
      <el-date-picker v-model="range" type="monthrange" value-format="YYYY-MM" format="YYYY-MM" range-separator="至"
        start-placeholder="开始年月" end-placeholder="结束年月" size="small" :clearable="false" :disabled-date="disabledMonth" @change="load" />
    </div>
    <div class="metrics-line">
      <span>最多12个月 · {{ loadedRange }}</span>
      <el-radio-group v-model="mode" size="small" aria-label="趋势指标"><el-radio-button value="count">数量</el-radio-button><el-radio-button value="percent">占比</el-radio-button></el-radio-group>
    </div>
    <el-alert v-if="error" :title="error" type="error" :closable="false" show-icon />
    <template v-else>
      <div class="total-line"><span>{{ segmentLabel }} · {{ lastPoint?.stat_month || '所选范围' }}<small v-if="lastPoint?.provisional"> 暂计</small></span><strong>{{ formatNumber(lastPoint?.sku_count) }} <small>SKU</small></strong></div>
      <div v-if="hasData" ref="chartEl" class="chart" role="img" :aria-label="`${platform}新老品月度折线图，可切换数量或占比`" />
      <el-empty v-else class="empty" :image-size="42" description="所选月份暂无已保存数据" />
    </template>
    <footer>
      <span :title="notes + (platform === 'ebay' ? ' 排除AMZ开头的MSKU，其他未分配SKU保留。' : '')">{{ notice }}</span>
      <el-button link type="primary" size="small" @click="tableOpen = true" :disabled="!items.length || !!error">查看数据</el-button>
    </footer>
    <el-dialog v-model="tableOpen" :title="`${platform.toUpperCase()} · ${segmentLabel} 新老品月度数据`" width="960px" append-to-body destroy-on-close>
      <p class="table-note">{{ notes }}</p>
      <p v-if="platform === 'ebay'" class="table-note">排除 AMZ 开头的 MSKU；其他未匹配负责人的商品仍计入所属站点。</p>
      <el-tabs v-model="dataTab">
      <el-tab-pane label="月度汇总" name="monthly">
      <el-table :data="items" max-height="450" size="small">
        <el-table-column prop="stat_month" label="统计年月" width="110" />
        <el-table-column label="状态" width="130"><template #default="{ row }">{{ ready(row) ? (row.provisional ? '当月暂计' : '已保存') : row.message || '无快照' }}</template></el-table-column>
        <el-table-column label="SKU总数" width="90"><template #default="{ row }">{{ formatNumber(row.sku_count) }}</template></el-table-column>
        <el-table-column v-for="nature in NATURES" :key="nature.key" :label="nature.label" min-width="110"><template #default="{ row }">{{ formatNumber(row.counts?.[nature.key]) }} / {{ row.percentages?.[nature.key] == null ? '--' : row.percentages[nature.key] + '%' }}</template></el-table-column>
        <el-table-column label="明细" width="100" fixed="right"><template #default="{ row }"><el-button link type="primary" :disabled="!ready(row)" @click="showOwners(row.stat_month)">负责人</el-button></template></el-table-column>
      </el-table>
      </el-tab-pane>
      <el-tab-pane label="负责人明细" name="owners">
        <OwnerDetails v-if="tableOpen && dataTab === 'owners'" :platform="platform" :segment="segment" :segment-label="segmentLabel" :items="items" :initial-month="ownerMonth || lastPoint?.stat_month" />
      </el-tab-pane>
      </el-tabs>
    </el-dialog>
  </section>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import * as echarts from 'echarts/core'
import { LineChart } from 'echarts/charts'
import { GridComponent, LegendComponent, TooltipComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import { getProductNatureHistory } from '@/api/operations/productNature'
import OwnerDetails from './OwnerDetails.vue'
import { NATURES, chartOption, currentMonth, formatNumber, rangeError, ready, shiftMonth, segmentOptions, segmentItems } from './presentation'

echarts.use([LineChart, GridComponent, LegendComponent, TooltipComponent, CanvasRenderer])
const props = defineProps({ platform: { type: String, required: true, validator: p => ['amz', 'ebay'].includes(p) } })
const range = ref([shiftMonth(currentMonth(), -11), currentMonth()])
const rawItems = ref([]), loading = ref(false), error = ref(''), mode = ref('count'), tableOpen = ref(false), chartEl = ref(null)
const dataTab = ref('monthly'), ownerMonth = ref('')
function showOwners(month) { ownerMonth.value = month; dataTab.value = 'owners' }
const segment = ref(props.platform === 'amz' ? 'US' : '德国')
const options = computed(() => segmentOptions(props.platform, rawItems.value))
const segmentLabel = computed(() => options.value.find(o => o.value === segment.value)?.label || segment.value)
const items = computed(() => segmentItems(rawItems.value, segment.value))
const loadedRange = ref('')
let chart, observer, disposed = false, requestVersion = 0
const hasData = computed(() => items.value.some(ready))
const lastPoint = computed(() => items.value.filter(ready).at(-1))
const notes = computed(() => `${props.platform === 'amz' ? '按补货区域配置分美国/欧洲；区域内按负责人＋完整seller_sku去重。同一完整seller_sku取所属区域内最早有效刊登日期（跨店铺及负责人，不跨美国/欧洲）。美国≤60天、欧洲≤90天为新品，超过阈值为老品；区域内全部缺失或无效日期时为老品。区域未匹配仍未知。当月按年月覆盖。' : '同站点＋完整MSKU去重，取该站点SKU全部刊登的最早时间，≤60天新品、>60天老品；跨站点独立统计。未匹配负责人仍保留，历史使用月末冻结数据。'}缺月及旧版无分区快照留空，不跨口径版本连线。旧负责人卡片不变。`)
const notice = computed(() => {
  const missing = items.value.filter(i => !ready(i)).length
  const versions = new Set(items.value.filter(ready).map(i => i.rule_version)).size
  return versions > 1 ? '存在不同口径，折线已断开' : missing ? `${missing}个月无有效快照 · 缺月留空` : '当月暂计 · 历史按月保存'
})
function disabledMonth(date) {
  const month = `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}`
  return month > currentMonth() || date.getFullYear() < 2000
}
function disposeChart() { observer?.disconnect(); observer = null; chart?.dispose(); chart = null }
async function render() {
  await nextTick()
  if (disposed) return
  if (!chartEl.value) { disposeChart(); return }
  if (!chart || chart.getDom() !== chartEl.value) {
    disposeChart()
    chart = echarts.init(chartEl.value)
    observer = new ResizeObserver(() => chart?.resize())
    observer.observe(chartEl.value)
  }
  chart.setOption(chartOption(items.value, mode.value), true)
}
async function load() {
  const version = ++requestVersion
  error.value = rangeError(range.value)
  if (error.value) { loading.value = false; rawItems.value = []; await render(); return }
  const selection = [...range.value]
  loading.value = true
  try {
    const response = await getProductNatureHistory(props.platform, ...selection)
    if (disposed || version !== requestVersion) return
    if (!Array.isArray(response?.data?.items)) throw new Error('invalid response')
    if (response.data.items.some(item => item.stat_month === currentMonth() && ready(item) && !Array.isArray(item.segments))) {
      throw new Error('STALE_SERVICE')
    }
    rawItems.value = response.data.items
    loadedRange.value = `${selection[0]} 至 ${selection[1]}`
  } catch (cause) {
    if (disposed || version !== requestVersion) return
    rawItems.value = []
    error.value = cause?.message === 'STALE_SERVICE'
      ? 'Python服务尚未加载区域/站点口径，请重启Python后刷新。'
      : '加载失败，请确认服务、报表建表及查看权限后重试。'
  } finally {
    if (!disposed && version === requestVersion) { loading.value = false; await render() }
  }
}
watch([mode, segment], render)
onMounted(load)
onBeforeUnmount(() => { disposed = true; requestVersion++; disposeChart() })
</script>

<style scoped>
.nature-panel { box-sizing: border-box; height: 400px; min-width: 0; display: flex; flex-direction: column; padding: 16px; background: var(--el-bg-color); border: 1px solid var(--el-border-color-lighter); border-radius: 10px; }
header { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
.eyebrow { color: var(--el-color-primary); font-size: 10px; font-weight: 600; letter-spacing: .5px; }
h2 { margin: 6px 0 10px; font-size: 15px; color: var(--el-text-color-primary); }
.month-filter { display: flex; gap: 8px; }
.segment-filter { width: 115px; flex-shrink: 0; }
.month-filter :deep(.el-date-editor) { flex: 1; width: 100%; min-width: 0; box-sizing: border-box; }
.month-filter :deep(.el-range-input) { font-size: 11px; }
.metrics-line, .total-line, footer { display: flex; justify-content: space-between; align-items: center; gap: 6px; }
.metrics-line { margin: 9px 0 4px; font-size: 10px; color: var(--el-text-color-secondary); }
.metrics-line > span { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.metrics-line :deep(.el-radio-button__inner) { padding: 4px 7px; font-size: 10px; }
.total-line { font-size: 11px; color: var(--el-text-color-secondary); margin: 2px 0 6px; }
.total-line strong { font-size: 20px; color: var(--el-text-color-primary); font-variant-numeric: tabular-nums; }
.total-line small { font-size: 10px; font-weight: normal; }
.chart { width: 100%; flex: 1; min-height: 100px; }
.empty { flex: 1; padding: 4px 0; }
.empty :deep(.el-empty__description p) { font-size: 12px; }
footer { margin-top: auto; padding-top: 7px; border-top: 1px solid var(--el-border-color-lighter); font-size: 10px; color: var(--el-text-color-secondary); }
footer > span { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; cursor: help; }
.el-alert { margin-top: 12px; }
.table-note { color: var(--el-text-color-secondary); font-size: 12px; line-height: 1.7; }
</style>
