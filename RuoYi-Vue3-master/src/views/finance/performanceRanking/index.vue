<template>
  <div class="app-container">
    <el-card shadow="never" class="filter-card">
      <el-form ref="queryRef" :model="query" inline label-width="82px">
        <el-form-item label="统计月份" prop="statMonth">
          <el-date-picker
            v-model="query.statMonth"
            type="month"
            value-format="YYYY-MM"
            placeholder="默认最新月份"
            clearable
          />
        </el-form-item>
        <el-form-item label="负责人" prop="principalName">
          <el-input v-model="query.principalName" clearable placeholder="Listing负责人" @keyup.enter="handleQuery" />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" icon="Search" @click="handleQuery">搜索</el-button>
          <el-button icon="Refresh" @click="resetQuery">重置</el-button>
          <el-button
            type="success"
            icon="Refresh"
            :loading="refreshing"
            v-hasPermi="['finance:performanceRanking:edit']"
            @click="handleRefresh"
          >
            重新计算
          </el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <el-card shadow="never">
      <template #header>
        <div class="card-header">
          <div>
            <span class="title">Amazon 月度绩效排名</span>
            <span class="subtitle">金额统一为 CNY，默认按毛利润从高到低</span>
          </div>
          <el-tag type="success">{{ displayedMonth || '最新月份' }}</el-tag>
        </div>
      </template>

      <el-table v-loading="loading" :data="rows" stripe border>
        <el-table-column type="index" label="排名" width="72" align="center">
          <template #default="{ $index }">
            {{ (query.pageNum - 1) * query.pageSize + $index + 1 }}
          </template>
        </el-table-column>
        <el-table-column prop="statMonth" label="月份" width="100" align="center" />
        <el-table-column prop="principalNames" label="Listing负责人" min-width="140" show-overflow-tooltip />
        <el-table-column prop="grossProfit" label="毛利润" width="130" align="right">
          <template #default="{ row }">{{ money(row.grossProfit) }}</template>
        </el-table-column>
        <el-table-column prop="amount" label="销售额" width="130" align="right">
          <template #default="{ row }">{{ money(row.amount) }}</template>
        </el-table-column>
        <el-table-column prop="refundAmount" label="退款金额" width="130" align="right">
          <template #default="{ row }">{{ money(row.refundAmount) }}</template>
        </el-table-column>
      </el-table>

      <pagination
        v-show="total > 0"
        :total="total"
        v-model:page="query.pageNum"
        v-model:limit="query.pageSize"
        @pagination="loadData"
      />
    </el-card>
  </div>
</template>

<script setup name="PerformanceRanking">
import { computed, getCurrentInstance, onMounted, reactive, ref } from 'vue'
import { listPerformanceRanking, refreshPerformanceRanking } from '@/api/finance/performanceRanking'

const { proxy } = getCurrentInstance()
const loading = ref(false)
const rows = ref([])
const total = ref(0)
const refreshing = ref(false)
const queryRef = ref()
const query = reactive({
  pageNum: 1,
  pageSize: 20,
  statMonth: undefined,
  principalName: undefined
})

const displayedMonth = computed(() => query.statMonth || rows.value[0]?.statMonth || '')

function money(value) {
  if (value === null || value === undefined || value === '') return '-'
  return Number(value).toLocaleString('zh-CN', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2
  })
}

async function loadData() {
  loading.value = true
  try {
    const response = await listPerformanceRanking(query)
    rows.value = response.rows || []
    total.value = response.total || 0
  } finally {
    loading.value = false
  }
}

function handleQuery() {
  query.pageNum = 1
  loadData()
}

function resetQuery() {
  queryRef.value?.resetFields()
  query.pageNum = 1
  loadData()
}

async function handleRefresh() {
  refreshing.value = true
  try {
    const response = await refreshPerformanceRanking(query.statMonth)
    const result = response.data || {}
    if (!query.statMonth) query.statMonth = result.statMonth
    proxy.$modal.msgSuccess(`绩效排名计算完成，共生成${result.rows || 0}条汇总数据`)
    query.pageNum = 1
    await loadData()
  } finally {
    refreshing.value = false
  }
}

onMounted(loadData)
</script>

<style scoped>
.filter-card { margin-bottom: 16px; }
.card-header { display: flex; align-items: center; justify-content: space-between; }
.title { font-size: 16px; font-weight: 600; }
.subtitle { margin-left: 12px; color: var(--el-text-color-secondary); font-size: 13px; }
</style>
