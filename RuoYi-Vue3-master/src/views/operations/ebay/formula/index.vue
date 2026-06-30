<template>
  <div class="app-container">
    <el-row :gutter="10" class="mb8">
      <el-col :span="1.5">
        <el-button type="primary" icon="Refresh" @click="loadList">刷新</el-button>
      </el-col>
    </el-row>

    <el-table v-loading="loading" :data="list" border stripe>
      <el-table-column label="序号" width="60" prop="scenarioOrder" align="center" />
      <el-table-column label="分组" width="100" prop="ruleGroup">
        <template #default="{ row }">{{ groupLabel(row.ruleGroup) }}</template>
      </el-table-column>
      <el-table-column label="产品性质" width="80" align="center">
        <template #default="{ row }">{{ row.productNature == 1 ? '老品' : '新品' }}</template>
      </el-table-column>
      <el-table-column label="公式名称" prop="name" width="140" show-overflow-tooltip />
      <el-table-column label="条件说明" prop="conditionDesc" min-width="200" show-overflow-tooltip />
      <el-table-column label="比较基准" width="90" align="center">
        <template #default="{ row }">{{ row.compareMetric || '-' }}</template>
      </el-table-column>
      <el-table-column label="下限" width="80" align="center">
        <template #default="{ row }">
          <el-input-number v-model="row.lowerBound" :min="0" :max="10" :step="0.1" :precision="2" size="small" controls-position="right" style="width:75px" />
        </template>
      </el-table-column>
      <el-table-column label="上限" width="80" align="center">
        <template #default="{ row }">
          <el-input-number v-model="row.upperBound" :min="0" :max="10" :step="0.1" :precision="2" size="small" controls-position="right" style="width:75px" />
        </template>
      </el-table-column>
      <el-table-column label="7天权重" width="85" align="center">
        <template #default="{ row }">
          <el-input-number v-model="row.weight7d" :min="0" :max="1" :step="0.05" :precision="3" size="small" controls-position="right" style="width:80px" />
        </template>
      </el-table-column>
      <el-table-column label="15天权重" width="85" align="center">
        <template #default="{ row }">
          <el-input-number v-model="row.weight15d" :min="0" :max="1" :step="0.05" :precision="3" size="small" controls-position="right" style="width:80px" />
        </template>
      </el-table-column>
      <el-table-column label="30天权重" width="85" align="center">
        <template #default="{ row }">
          <el-input-number v-model="row.weight30d" :min="0" :max="1" :step="0.05" :precision="3" size="small" controls-position="right" style="width:80px" />
        </template>
      </el-table-column>
      <el-table-column label="乘数" width="70" align="center">
        <template #default="{ row }">
          <el-input-number v-model="row.multiplier" :min="0" :step="1" size="small" controls-position="right" style="width:65px" />
        </template>
      </el-table-column>
      <el-table-column label="×30" width="60" align="center">
        <template #default="{ row }">
          <el-switch v-model="row.multiply30" :active-value="1" :inactive-value="0" size="small" />
        </template>
      </el-table-column>
      <el-table-column label="备注" prop="remark" width="140" show-overflow-tooltip />
      <el-table-column label="状态" width="65" align="center">
        <template #default="{ row }">
          <el-switch v-model="row.status" :active-value="1" :inactive-value="0" size="small" />
        </template>
      </el-table-column>
      <el-table-column label="操作" width="80" align="center" fixed="right">
        <template #default="{ row }">
          <el-button link type="primary" size="small" @click="saveRow(row)">保存</el-button>
        </template>
      </el-table-column>
    </el-table>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import request from '@/utils/request'
const { proxy } = getCurrentInstance()

const list = ref([])
const loading = ref(false)

function groupLabel(g) {
  const map = {
    'NEW_PRODUCT': '新品',
    'OLD_D7_POSITIVE': '老品7天+',
    'OLD_D7_ZERO_D15_POSITIVE': '老品15天+',
    'OLD_NO_SALES': '无销量'
  }
  return map[g] || g || '-'
}

function loadList() {
  loading.value = true
  request({ url: '/operations/ebay/replenishment/formula/list', method: 'get' }).then(res => {
    list.value = (res.data || []).map(r => ({
      ...r,
      weight7d: Number(r.weight7d || 0),
      weight15d: Number(r.weight15d || 0),
      weight30d: Number(r.weight30d || 0),
      multiplier: Number(r.multiplier || 0),
      multiply30: Number(r.multiply30 != null ? r.multiply30 : 1),
      lowerBound: r.lowerBound != null ? Number(r.lowerBound) : null,
      upperBound: r.upperBound != null ? Number(r.upperBound) : null,
      status: Number(r.status)
    }))
  }).finally(() => loading.value = false)
}

function saveRow(row) {
  request({ url: '/operations/ebay/replenishment/formula/update', method: 'post', data: row }).then(() => {
    proxy.$modal.msgSuccess('已保存')
    loadList()
  })
}

loadList()
</script>

