<template>
  <section class="performance-details" aria-label="业绩详情">
    <header><div><h3>业绩详情</h3><span class="group-tag">按组别</span></div><span class="scope">{{ scope }}</span></header>
    <el-table ref="table" v-loading="loading" :data="pageRows" border stripe max-height="540"
      :row-key="row => `${row.stat_month}:${row.platform}:${row.group_code}`"
      show-summary :summary-method="summaryMethod" @sort-change="changeSort"
      :empty-text="error ? '查询失败，请重新查询' : '所选范围暂无数据'">
      <el-table-column type="index" label="序号" width="65" fixed="left" :index="index => (page - 1) * pageSize + index + 1" />
      <el-table-column prop="stat_month" label="年月" width="110" fixed="left" sortable="custom" />
      <el-table-column prop="group_code" label="组别" width="110" fixed="left" sortable="custom" />
      <el-table-column prop="platform" label="平台" width="85"><template #default="{ row }">{{ row.platform === 'ebay' ? 'eBay' : 'AMZ' }}</template></el-table-column>
      <el-table-column v-for="column in columns" :key="column.key" :prop="column.key" :label="column.label"
        :min-width="column.label.length > 10 ? 210 : 160" :align="column.unit === 'text' ? 'left' : 'right'"
        sortable="custom" show-overflow-tooltip>
        <template #default="{ row }">{{ formatDetail(row[column.key], column.unit) }}</template>
      </el-table-column>
    </el-table>
    <div class="table-footer"><p>每行对应一个月份、一个组别；金额单位为人民币。毛利率明细保留原表值，合计按毛利润合计 ÷ 平台收入合计计算。合计包含筛选后的所有页。</p>
      <el-pagination v-model:current-page="page" v-model:page-size="pageSize" :total="rows.length"
        :page-sizes="[10, 20, 50, 100]" layout="total, sizes, prev, pager, next" background @size-change="page = 1" />
    </div>
  </section>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { formatDetail, sortDetails, detailSummary } from './details'

const props = defineProps({ details: Object, loading: Boolean, error: String, scope: String })
const page = ref(1), pageSize = ref(20), sort = ref({}), table = ref(null)
const columns = computed(() => props.details?.columns || [])
const rows = computed(() => props.details?.rows || [])
const sortedRows = computed(() => sortDetails(rows.value, sort.value, columns.value))
const pageRows = computed(() => sortedRows.value.slice((page.value - 1) * pageSize.value, page.value * pageSize.value))
const summaryMethod = ({ columns }) => detailSummary(columns, props.details)
function changeSort(value) { sort.value = value; page.value = 1 }
watch(() => props.details, () => { page.value = 1; sort.value = {}; table.value?.clearSort() })
</script>

<style scoped>
.performance-details { min-width: 0; margin-top: 18px; padding: 22px; background: var(--el-bg-color); border: 1px solid var(--el-border-color-light); border-radius: 12px; }
header { display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 12px; margin-bottom: 20px; }
header > div { display: flex; align-items: center; gap: 12px; }
h3 { font-size: 17px; margin: 0; color: var(--el-text-color-primary); }
.group-tag { font-size: 12px; padding: 5px 10px; color: var(--el-color-primary); background: var(--el-color-primary-light-9); border-radius: 5px; }
.scope, .table-footer p { font-size: 12px; color: var(--el-text-color-secondary); line-height: 1.7; }
.scope { overflow-wrap: anywhere; }
:deep(.el-table th.el-table__cell) { background: var(--el-fill-color-light); color: var(--el-text-color-regular); }
:deep(.el-table .cell) { font-variant-numeric: tabular-nums; }
:deep(.el-table__footer-wrapper) { font-weight: 600; }
.table-footer { display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 12px; margin-top: 14px; }
.table-footer p { margin: 0; flex: 1 1 350px; }
@media (max-width: 600px) { .performance-details { padding: 16px; } .table-footer { overflow-x: auto; } }
</style>
