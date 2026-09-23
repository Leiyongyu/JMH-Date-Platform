<template>
  <div>
    <div class="owner-filter">
      <span>统计年月</span>
      <el-select v-model="month" aria-label="负责人统计年月" style="width: 150px">
        <el-option v-for="item in items" :key="item.stat_month" :label="item.stat_month" :value="item.stat_month" />
      </el-select>
      <span class="owner-note">{{ segmentLabel }} · 按负责人＋完整SKU去重 · 未分配保留</span>
    </div>
    <el-alert v-if="error" :title="error" type="warning" :closable="false" show-icon />
    <el-table v-loading="loading" :data="rows" row-key="owner_key" max-height="430" size="small" :row-class-name="rowClass">
      <el-table-column prop="principal_name" label="负责人" min-width="100" fixed />
      <el-table-column label="SKU总数" min-width="90" align="right"><template #default="{ row }">{{ formatNumber(row.sku_count) }}</template></el-table-column>
      <el-table-column v-for="nature in NATURES" :key="nature.key" :label="nature.label + '数'" min-width="80" align="right"><template #default="{ row }">{{ formatNumber(row.counts?.[nature.key]) }}</template></el-table-column>
      <el-table-column label="新品占比" min-width="90" align="right"><template #default="{ row }">{{ percent(row.percentages?.NEW) }}</template></el-table-column>
      <el-table-column label="老品占比" min-width="90" align="right"><template #default="{ row }">{{ percent(row.percentages?.OLD) }}</template></el-table-column>
      <template #empty>{{ error ? '暂无可展示明细' : '该月份暂无负责人数据' }}</template>
    </el-table>
    <p class="owner-note">占比按每位负责人的SKU总数计算；红色合计与所选月份图表一致。历史使用保存时的负责人及新老品判定，不按当前规则重算。</p>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { getProductNatureOwners } from '@/api/operations/productNature'
import { NATURES, formatNumber, ready } from './presentation'
import { ownerDetailRows } from './ownerPresentation'

const props = defineProps({ platform: String, segment: String, segmentLabel: String, items: { type: Array, default: () => [] }, initialMonth: String })
const availableMonth = value => props.items.some(item => item.stat_month === value) ? value : props.items.at(-1)?.stat_month || ''
const month = ref(availableMonth(props.initialMonth))
const point = computed(() => props.items.find(item => item.stat_month === month.value))
const loading = ref(false), error = ref(''), rows = ref([])
let version = 0, disposed = false
const percent = value => value == null ? '--' : `${value}%`
const rowClass = ({ row }) => row.isTotal ? 'owner-total' : ''
watch(() => props.initialMonth, value => { month.value = availableMonth(value) })
watch(() => props.items, items => {
  if (!items.some(item => item.stat_month === month.value)) month.value = items.at(-1)?.stat_month || ''
})
async function loadOwners() {
  const current = ++version
  rows.value = []; error.value = ''; loading.value = false
  const selected = point.value
  if (!ready(selected)) { error.value = selected?.message || '该月无区域/站点快照，不补算历史明细'; return }
  if (!selected.batch_id) { error.value = '旧版快照缺少批次标识，无法核对负责人明细'; return }
  loading.value = true
  try {
    const response = await getProductNatureOwners(props.platform, month.value, props.segment, selected.batch_id)
    if (disposed || current !== version) return
    rows.value = ownerDetailRows(response?.data, selected, props.segment)
  } catch (cause) {
    if (disposed || current !== version) return
    error.value = cause?.ownerDetailMessage || '负责人明细加载失败，请确认服务已更新及查看权限后重试'
  } finally {
    if (!disposed && current === version) loading.value = false
  }
}
watch([month, () => props.segment, () => props.platform, point], loadOwners, { immediate: true })
onBeforeUnmount(() => { disposed = true; version++ })
</script>

<style scoped>
.owner-filter { display: flex; align-items: center; flex-wrap: wrap; gap: 10px; margin: 10px 0 14px; }
.owner-note { color: var(--el-text-color-secondary); font-size: 12px; line-height: 1.7; }
:deep(.owner-total) { color: var(--el-color-danger); font-weight: 600; }
</style>
