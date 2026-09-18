<template>
  <section class="owner-panel" :aria-labelledby="`owner-sku-title-${platform}`" v-loading="loading">
    <header class="panel-header">
      <div>
        <span class="eyebrow">{{ platformLabel }} · 在售商品</span>
        <h2 :id="`owner-sku-title-${platform}`">负责人在售 SKU 数</h2>
      </div>
      <el-button :loading="loading" icon="Refresh" size="small" circle title="刷新统计" :aria-label="`${platformLabel}刷新统计`" @click="load" />
    </header>
    <el-alert v-if="error" :title="error" type="error" :closable="false" show-icon />
    <template v-else-if="summary">
      <el-alert v-if="!['READY', 'EMPTY'].includes(summary.state)" :title="summary.message" type="warning" :closable="false" show-icon />
      <template v-else>
        <div class="summary-line">
          <span>SKU 合计 <strong>{{ formatCount(summary.total) }}</strong></span>
          <span class="owner-total">{{ summary.owner_count }} 位负责人</span>
        </div>
        <div class="source-time" :title="`规则月份 ${summary.rule_month} · 源数据更新 ${summary.source_updated_at || '--'}`">规则 {{ summary.rule_month }} · 更新 {{ summary.source_updated_at || '--' }}</div>
        <div class="chart-scroll" tabindex="0" role="region" :aria-label="`${platformLabel}负责人柱状图，可上下滚动`">
        <el-empty v-if="!summary.items.length" :image-size="48" :description="summary.message || '暂无在售SKU'" />
        <ol v-else class="bar-chart" aria-label="各负责人在售SKU数量，按数量降序">
          <li v-for="(item, index) in summary.items" :key="item.principal_name" :class="{ unassigned: item.unassigned }">
            <span class="owner-name" :title="item.principal_name">{{ item.principal_name }}</span>
            <div class="bar-track" aria-hidden="true"><div v-if="item.sku_count > 0" class="bar" :style="{ width: `${item.sku_count / maxCount * 100}%` }" /></div>
            <strong class="bar-value">{{ formatCount(item.sku_count) }}</strong>
          </li>
        </ol>
        <el-alert v-for="warning in summary.warnings" :key="warning" :title="warning" type="warning" :closable="false" show-icon />
        </div>
        <footer tabindex="0" :title="`${dedupDescription}。来源：领星商品刊登 ${summary.source_api}；仅统计源表 ${statusField}=1${platform === 'amz' ? ' 且 is_delete=0（未删除）' : ''}；排除PC及任意数字+PC前缀（如2PC、12PC）的SKU，AMZ检查本地SKU和卖家SKU，eBay检查MSKU；沿用当月绩效排名规则，未匹配保留为未分配。刷新统计不触发接口拉取。`"><span>统计口径 ⓘ</span><span>上下滚动查看</span></footer>
      </template>
    </template>
  </section>
</template>

<script setup>
import { computed, onMounted, onBeforeUnmount, ref } from 'vue'
import { getAmzOwnerSkuSummary, getEbayOwnerSkuSummary } from '@/api/operations/amzOwnerSku'

const props = defineProps({ platform: { type: String, default: 'amz', validator: value => ['amz', 'ebay'].includes(value) } })
const platformLabel = computed(() => props.platform === 'ebay' ? 'EBAY' : 'AMAZON')
const statusField = computed(() => props.platform === 'ebay' ? 'listing_status' : 'status')
const dedupDescription = computed(() => props.platform === 'ebay'
  ? '按负责人及完整 MSKU 去重，同一MSKU跨店铺只计一次' : '按当月规则匹配负责人，再按负责人及完整 seller_sku 去重，同一负责人跨店铺只计一次；本地SKU仅用于品牌及OTH归属匹配')

const loading = ref(false)
const summary = ref(null)
const error = ref('')
let disposed = false
const maxCount = computed(() => Math.max(1, ...(summary.value?.items || []).map(item => item.sku_count)))
const formatCount = value => Number(value ?? 0).toLocaleString('zh-CN')

async function load() {
  if (loading.value) return
  loading.value = true
  error.value = ''
  try {
    const response = await (props.platform === 'ebay' ? getEbayOwnerSkuSummary() : getAmzOwnerSkuSummary())
    if (!disposed) summary.value = response.data
  } catch (e) {
    if (!disposed) {
      summary.value = null
      error.value = '统计加载失败，请检查服务或权限后点击刷新重试。'
    }
  } finally {
    if (!disposed) loading.value = false
  }
}
onMounted(load)
onBeforeUnmount(() => { disposed = true })
</script>

<style scoped>
.owner-panel { box-sizing: border-box; display: flex; flex-direction: column; width: 100%; min-width: 0; height: 360px; padding: 14px; background: var(--el-bg-color); border: 1px solid var(--el-border-color-lighter); border-radius: 10px; }
.panel-header { display: flex; justify-content: space-between; align-items: center; gap: 8px; flex-shrink: 0; }
.eyebrow { color: var(--el-color-primary); font-size: 10px; font-weight: 600; letter-spacing: .5px; }
h2 { margin: 6px 0 10px; color: var(--el-text-color-primary); font-size: 15px; line-height: 1.4; }
.summary-line { display: flex; justify-content: space-between; align-items: baseline; flex-wrap: wrap; gap: 4px; padding-top: 10px; border-top: 1px solid var(--el-border-color-lighter); color: var(--el-text-color-regular); font-size: 11px; flex-shrink: 0; }
.summary-line strong { color: var(--el-text-color-primary); font-size: 21px; margin-left: 5px; font-variant-numeric: tabular-nums; }
.owner-total { color: var(--el-text-color-secondary); }
.source-time { margin: 6px 0 10px; color: var(--el-text-color-secondary); font-size: 10px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; flex-shrink: 0; }
.chart-scroll { flex: 1; min-height: 0; overflow-y: auto; overflow-x: hidden; overscroll-behavior-y: contain; scrollbar-width: thin; scrollbar-gutter: stable; padding-right: 4px; }
.chart-scroll:focus-visible { outline: 2px solid var(--el-color-primary); outline-offset: -2px; }
.bar-chart { list-style: none; padding: 0; margin: 0; }
.bar-chart li { display: grid; grid-template-columns: 48px minmax(0, 1fr) 43px; gap: 6px; align-items: center; min-height: 32px; font-size: 12px; }
.owner-name { color: var(--el-text-color-primary); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.bar-track { height: 12px; background: var(--el-fill-color-light); border-radius: 3px; overflow: hidden; }
.bar { height: 100%; min-width: 2px; background: linear-gradient(90deg, #387ae5, #79b1fa); border-radius: 4px; }
.bar-value { text-align: right; font-variant-numeric: tabular-nums; color: var(--el-text-color-primary); }
.unassigned .bar { background: #e6a23c; }
.unassigned .owner-name, .unassigned .bar-value { color: var(--el-color-warning); }
footer { display: flex; justify-content: space-between; gap: 6px; border-top: 1px solid var(--el-border-color-lighter); margin-top: 10px; padding-top: 8px; color: var(--el-text-color-secondary); font-size: 10px; flex-shrink: 0; }
footer span:first-child { cursor: help; }
.el-alert { margin: 8px 0; overflow-y: auto; }
</style>
