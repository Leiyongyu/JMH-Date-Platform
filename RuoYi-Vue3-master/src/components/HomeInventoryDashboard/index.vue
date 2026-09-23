<template>
  <section v-loading="loading" class="inventory-dashboard" aria-label="库存分析看板">
    <div class="toolbar">
      <div class="board-heading">
        <span class="board-icon" aria-hidden="true"><DataAnalysis /></span>
        <div><h2>库存分析看板</h2><span class="subtitle">汽配库存概览 <span class="heading-dot">·</span> 人民币 CNY</span></div>
        <span v-if="report" class="period-tag">{{ report.report_month }} 月报</span>
      </div>
      <div class="actions">
        <el-select v-model="month" aria-label="统计月份" placeholder="统计月份" style="width: 135px" :disabled="loading" @change="load">
          <el-option v-for="m in months" :key="m" :label="m" :value="m" />
        </el-select>
        <el-button icon="Refresh" :disabled="loading || saving" @click="load()">刷新</el-button>
        <el-button v-if="canViewSku && month === currentMonth" :loading="saving" :disabled="loading" @click="saveSnapshot">保存当月SKU快照</el-button>
      </div>
    </div>
    <el-alert v-if="error" type="error" :title="error" :closable="false" show-icon />
    <div v-if="report" class="inventory-kpis">
      <article class="kpi total-card" :title="'月度库存汽配小计：本地仓、海外仓/FBA仓的期末在途总成本与期末库存总成本之和。'">
        <div class="card-heading"><span class="kpi-label">库存总额</span><span class="metric-icon" aria-hidden="true"><Box /></span></div>
        <strong class="main-value">{{ displayValue(report.inventory_total.value) }}</strong>
        <span class="change" :class="report.inventory_total.direction">{{ changeText(report.inventory_total) }}</span>
        <span class="footnote">在途 + 在库 · 上月 {{ displayValue(report.inventory_total.previous) }}</span>
      </article>
      <article class="kpi transit-card" title="月度库存汽配小计：本地仓、海外仓和FBA仓的期末在途总成本之和。">
        <div class="card-heading"><span class="kpi-label">在途金额</span><span class="metric-icon" aria-hidden="true"><Van /></span></div>
        <strong class="main-value">{{ displayValue(report.transit.value) }}</strong>
        <span class="change" :class="report.transit.direction">{{ changeText(report.transit) }}</span>
        <span class="footnote">本地 + 海外/FBA · 上月 {{ displayValue(report.transit.previous) }}</span>
      </article>
      <article class="kpi age-card" title="复用滞销清货组别成本；仅海外仓/FBA，不含成都仓；91–180与181天以上计入滞销金额，0–90天单独作为对照。">
        <div class="card-heading"><span class="kpi-label">滞销库存金额 <small>海外仓 / FBA</small></span><span class="metric-icon" aria-hidden="true"><Warning /></span></div>
        <strong class="main-value">{{ displayValue(report.slow_total.value) }}</strong>
        <span class="change" :class="report.slow_total.direction">{{ changeText(report.slow_total) }}</span>
        <div class="age-buckets">
          <div v-for="bucket in buckets" :key="bucket.key" class="age-bucket">
            <span>{{ bucket.label }}</span><b>{{ displayValue(report.age_buckets[bucket.key].value) }}</b>
            <small class="change" :class="report.age_buckets[bucket.key].direction">{{ changeText(report.age_buckets[bucket.key]) }}</small>
          </div>
        </div>
      </article>
      <article class="kpi sku-card" title="直接汇总首页AMZ及eBay负责人在售SKU数，含未分配；同SKU由不同负责人负责时仍各自计数，不改原去重规则。历史月份仅用当时已保存的快照。">
        <div class="card-heading"><span class="kpi-label">SKU 总数</span><span class="metric-icon" aria-hidden="true"><Grid /></span></div>
        <strong class="main-value">{{ displayValue(sku?.metric?.value, true) }} <small>个</small></strong>
        <span class="change" :class="sku?.metric?.direction">{{ changeText(sku?.metric, true) }}</span>
        <div v-if="sku" class="platform-split"><span>AMZ <b>{{ displayValue(sku.platforms.amz?.total, true) }}</b></span><span>eBay <b>{{ displayValue(sku.platforms.ebay?.total, true) }}</b></span></div>
        <span v-if="!canViewSku" class="footnote">需要两平台在售SKU查看权限</span>
        <span v-if="skuError || sku?.warning" class="sku-warning">{{ skuError || sku.warning }}</span>
        <span v-if="sku?.live" class="footnote">当前实时统计 · 月末自动留存</span>
        <span v-if="sku?.saved_at" class="footnote snapshot-time">快照保存于 {{ sku.saved_at }}</span>
      </article>
    </div>
    <details v-if="report" class="source-note">
      <summary>统计口径 <span>展示月 {{ report.report_month }} · 对比 {{ report.previous_month }}</span></summary>
      <p>库存金额源数据月 {{ report.source_stat_month }}，库龄快照月 {{ report.report_month }}（与原菜单一致）。缺历史或上月为0时不计算涨跌率；成都仓库龄本轮不纳入。滞销金额为91–180天与181天以上之和，0–90天仅作对照。</p>
    </details>
  </section>
</template>
<script setup>
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { DataAnalysis, Box, Van, Warning, Grid } from '@element-plus/icons-vue'
import { checkPermi } from '@/utils/permission'
import { getHomeInventory, getHomeInventorySku, captureHomeInventorySku } from '@/api/finance/homeInventory'
import { changeText, displayValue } from './metric'
const canViewSku = checkPermi(['operations:amzReplenishment:list']) && checkPermi(['operations:ebayReplenishmentV2:list'])
const report = ref(null), sku = ref(null), month = ref(''), months = ref([]), currentMonth = ref('')
const loading = ref(false), saving = ref(false), error = ref(''), skuError = ref('')
const buckets = [
  { key: 'inventory_0_90_cost', label: '0–90天（对照）' },
  { key: 'inventory_91_180_cost', label: '91–180天' },
  { key: 'inventory_181_plus_cost', label: '181天以上' }
]
let version = 0, disposed = false
async function load() {
  const requestVersion = ++version
  loading.value = true; error.value = ''; skuError.value = ''; sku.value = null; report.value = null
  try {
    const response = await getHomeInventory(month.value || undefined)
    if (disposed || requestVersion !== version) return
    report.value = response.data; months.value = response.data.months
    month.value = response.data.report_month; currentMonth.value = response.data.current_month
    if (canViewSku) {
      try {
        const counts = await getHomeInventorySku(month.value)
        if (!disposed && requestVersion === version) sku.value = counts.data
      } catch {
        if (!disposed && requestVersion === version) skuError.value = 'SKU统计暂不可用，请检查快照表、权限及数据同步。'
      }
    }
  } catch {
    if (!disposed && requestVersion === version) error.value = '库存分析加载失败，请检查报表权限和服务状态。'
  } finally {
    if (!disposed && requestVersion === version) loading.value = false
  }
}
async function saveSnapshot() {
  if (saving.value || loading.value || month.value !== currentMonth.value) return
  saving.value = true
  try {
    await captureHomeInventorySku()
    if (!disposed) { ElMessage.success('已保存当月真实SKU快照，历史月份不变'); await load() }
  } catch {
    if (!disposed) skuError.value = 'SKU快照保存未完成，请检查服务日志；未补填任何历史月份。'
  } finally { saving.value = false }
}
onMounted(load)
onBeforeUnmount(() => { disposed = true; version++ })
</script>
<style scoped>
.inventory-dashboard { padding: 20px; border: 1px solid var(--el-border-color-lighter); border-radius: 16px; background: var(--el-bg-color); box-shadow: 0 4px 24px #2b65c008; }
.toolbar { display: flex; justify-content: space-between; align-items: center; gap: 16px; margin-bottom: 22px; flex-wrap: wrap; }
.board-heading { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
.board-icon { display: grid; place-items: center; width: 40px; height: 40px; border-radius: 12px; color: white; background: linear-gradient(135deg, #499aff, #2563eb); box-shadow: 0 4px 10px #2563eb24; }
.board-icon svg { width: 23px; height: 23px; }
h2 { margin: 0 0 4px; font-size: 18px; font-weight: 650; color: var(--el-text-color-primary); }
.heading-dot { padding: 0 5px; color: var(--el-text-color-placeholder); }
.period-tag { padding: 5px 9px; border-radius: 6px; font-size: 11px; background: var(--el-color-primary-light-9); color: var(--el-color-primary); }
.subtitle, .footnote, .source-note { font-size: 12px; color: var(--el-text-color-secondary); line-height: 1.7; }
.actions { display: flex; gap: 8px; flex-wrap: wrap; }
.actions :deep(.el-button + .el-button) { margin-left: 0; }
.inventory-kpis { display: grid; grid-template-columns: 1fr 1fr 1.65fr 1fr; gap: 14px; }
.kpi { --accent: #2864df; --tint: #edf5ff; --edge: #e0eaff; min-width: 0; padding: 16px; display: flex; flex-direction: column; align-items: flex-start; gap: 12px; border: 1px solid var(--edge); border-radius: 10px; background: linear-gradient(155deg, var(--tint), var(--el-bg-color) 95%); }
.transit-card { --accent: #8051cf; --tint: #f5f0ff; --edge: #ede4fa; }
.age-card { --accent: #cb721b; --tint: #fff7eb; --edge: #f6e8d3; }
.sku-card { --accent: #3776c5; --tint: #eff7ff; --edge: #dfedfc; }
.card-heading { display: flex; align-items: center; justify-content: space-between; gap: 8px; width: 100%; }
.metric-icon { display: grid; place-items: center; color: var(--accent); background: var(--el-bg-color); border: 1px solid var(--edge); width: 29px; height: 29px; border-radius: 8px; flex-shrink: 0; }
.metric-icon svg { width: 16px; height: 16px; }
.kpi-label { color: var(--accent); font-size: 13px; font-weight: 650; }
.kpi-label small { font-weight: 400; font-size: 11px; color: var(--el-text-color-secondary); }
.main-value { font-size: clamp(19px, 1.65vw, 28px); font-variant-numeric: tabular-nums; line-height: 1.25; letter-spacing: -.5px; color: var(--accent); overflow-wrap: anywhere; max-width: 100%; }
.main-value small { font-size: 12px; font-weight: 400; }
.change { font-size: 12px; color: var(--el-text-color-secondary); font-variant-numeric: tabular-nums; line-height: 1.5; }
.kpi > .change { padding: 4px 7px; border-radius: 5px; background: var(--el-bg-color); }
.change.up { color: #d63232; }
.change.down { color: #168342; }
.total-card > .footnote, .transit-card > .footnote { margin-top: auto; padding-top: 14px; border-top: 1px solid var(--edge); width: 100%; }
.age-buckets { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 10px; border-top: 1px solid var(--edge); padding-top: 12px; width: 100%; margin-top: auto; }
.age-bucket { display: flex; flex-direction: column; gap: 7px; min-width: 0; overflow-wrap: anywhere; }
.age-bucket > span { font-size: 11px; color: var(--el-text-color-secondary); }
.age-bucket b { font-size: 12px; color: var(--el-text-color-primary); }
.age-bucket small { font-size: 10px; }
.platform-split { display: flex; gap: 14px; flex-wrap: wrap; border-top: 1px solid var(--edge); padding-top: 12px; width: 100%; font-size: 11px; color: var(--el-text-color-secondary); }
.platform-split b { color: var(--accent); margin-left: 4px; font-size: 13px; font-variant-numeric: tabular-nums; }
.snapshot-time { font-size: 10px; overflow-wrap: anywhere; max-width: 100%; }
.sku-warning { font-size: 12px; color: var(--el-color-warning-dark-2); }
.source-note { margin-top: 16px; padding-top: 12px; border-top: 1px solid var(--el-border-color-lighter); }
.source-note summary { cursor: pointer; width: fit-content; }
.source-note summary span { margin-left: 12px; color: var(--el-text-color-placeholder); }
.source-note p { margin: 8px 0 0; }
.source-note summary:focus-visible { outline: 2px solid var(--el-color-primary); outline-offset: 4px; }
:global(html.dark) .kpi { --tint: #202b3a; --edge: #344154; --accent: #85b2ff; }
:global(html.dark) .transit-card { --tint: #2b2538; --edge: #463753; --accent: #bba0ed; }
:global(html.dark) .age-card { --tint: #332b23; --edge: #4b3b2d; --accent: #edb36e; }
@media (max-width: 1199px) { .inventory-kpis { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
@media (max-width: 639px) {
  .inventory-dashboard { padding: 14px; }
  .inventory-kpis { grid-template-columns: minmax(0, 1fr); }
  .toolbar { gap: 14px; }
  .actions { width: 100%; }
  .period-tag { display: none; }
}
</style>
