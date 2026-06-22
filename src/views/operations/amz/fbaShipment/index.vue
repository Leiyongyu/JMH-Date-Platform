<template>
  <div class="app-container fba-shipment-page">
    <el-form :model="queryParams" ref="queryRef" :inline="true" v-show="showSearch" label-width="90px">
      <el-form-item label="货件单号" prop="shipmentId">
        <el-input v-model="queryParams.shipmentId" placeholder="请输入" clearable style="width:200px" @keyup.enter="handleQuery" />
      </el-form-item>
      <el-form-item label="SKU" prop="sku">
        <el-input v-model="queryParams.sku" placeholder="请输入" clearable style="width:200px" @keyup.enter="handleQuery" />
      </el-form-item>
      <el-form-item label="MSKU" prop="msku">
        <el-input v-model="queryParams.msku" placeholder="请输入" clearable style="width:200px" @keyup.enter="handleQuery" />
      </el-form-item>
      <el-form-item label="店铺ID" prop="sid">
        <el-input v-model="queryParams.sid" placeholder="请输入" clearable style="width:140px" @keyup.enter="handleQuery" />
      </el-form-item>
      <el-form-item>
        <el-button type="primary" icon="Search" @click="handleQuery">搜索</el-button>
        <el-button icon="Refresh" @click="resetQuery">重置</el-button>
      </el-form-item>
    </el-form>

    <el-row :gutter="10" class="mb8">
      <el-col :span="1.5">
        <el-button type="warning" plain icon="Download" @click="handleExport" v-hasPermi="['operations:amzReplenishment:export']">导出</el-button>
      </el-col>
      <right-toolbar v-model:showSearch="showSearch" @queryTable="getList"></right-toolbar>
    </el-row>

    <el-table v-loading="loading" :data="records" border stripe height="640" @sort-change="handleSortChange">
      <el-table-column label="店铺ID" prop="sid" align="center" width="80" sortable="custom" />
      <el-table-column label="货件单号" prop="shipmentId" align="left" width="180" sortable="custom" show-overflow-tooltip />
      <el-table-column label="货件名称" prop="shipmentName" align="left" width="220" show-overflow-tooltip />
      <el-table-column label="MSKU" prop="msku" align="left" width="160" sortable="custom" show-overflow-tooltip />
      <el-table-column label="SKU" prop="sku" align="left" width="170" sortable="custom" show-overflow-tooltip />
      <el-table-column label="申报量" prop="quantityShipped" align="right" width="90" sortable="custom" />
      <el-table-column label="签收量" prop="quantityReceived" align="right" width="90" sortable="custom" />
      <el-table-column label="申收差异" prop="declaredDiff" align="right" width="100" sortable="custom">
        <template #default="scope">
          <span :style="{ color: scope.row.declaredDiff < 0 ? '#f56c6c' : scope.row.declaredDiff > 0 ? '#67c23a' : '' }">{{ scope.row.declaredDiff ?? 0 }}</span>
        </template>
      </el-table-column>
      <el-table-column label="创建人" prop="username" align="center" width="100" />
      <el-table-column label="创建时间" prop="gmtCreate" align="center" width="160">
        <template #default="scope">{{ parseTime(scope.row.gmtCreate) }}</template>
      </el-table-column>
      <el-table-column label="更新时间" prop="gmtModified" align="center" width="160">
        <template #default="scope">{{ parseTime(scope.row.gmtModified) }}</template>
      </el-table-column>
    </el-table>

    <pagination v-show="total > 0" :total="total" v-model:page="queryParams.pageNum" v-model:limit="queryParams.pageSize" @pagination="getList" />
  </div>
</template>

<script setup name="AmzFbaShipment">
import { ref, reactive, toRefs, getCurrentInstance } from 'vue'
import { searchFbaShipment } from '@/api/operations/amz/fbaShipment'
import request from '@/utils/request'
import { parseTime } from '@/utils/ruoyi'

const { proxy } = getCurrentInstance()
const loading = ref(false)
const showSearch = ref(true)
const total = ref(0)
const records = ref([])

const data = reactive({
  queryParams: {
    pageNum: 1, pageSize: 50,
    shipmentId: undefined, sku: undefined, msku: undefined, sid: undefined,
    sortField: undefined, sortOrder: undefined
  }
})
const { queryParams } = toRefs(data)

function getList() {
  loading.value = true
  const body = { pageNum: queryParams.value.pageNum, pageSize: queryParams.value.pageSize, sortField: queryParams.value.sortField || undefined, sortOrder: queryParams.value.sortOrder || undefined }
  const filters = []
  const p = queryParams.value
  if (p.shipmentId) filters.push({ field: 'shipmentId', value: p.shipmentId })
  if (p.sku) filters.push({ field: 'sku', value: p.sku })
  if (p.msku) filters.push({ field: 'msku', value: p.msku })
  if (p.sid) filters.push({ field: 'sid', value: p.sid })
  if (filters.length) body.filters = filters
  searchFbaShipment(body).then(res => { records.value = res.rows || []; total.value = res.total || 0 }).finally(() => { loading.value = false })
}

function handleQuery() { queryParams.value.pageNum = 1; getList() }
function resetQuery() { proxy.resetForm('queryRef'); queryParams.value.sortField = undefined; queryParams.value.sortOrder = undefined; handleQuery() }
function handleSortChange({ prop, order }) { queryParams.value.sortField = order ? prop : undefined; queryParams.value.sortOrder = order || undefined; queryParams.value.pageNum = 1; getList() }

function handleExport() {
  const filters = []
  const p = queryParams.value
  if (p.shipmentId) filters.push({ field: 'shipmentId', value: p.shipmentId })
  if (p.sku) filters.push({ field: 'sku', value: p.sku })
  if (p.msku) filters.push({ field: 'msku', value: p.msku })
  if (p.sid) filters.push({ field: 'sid', value: p.sid })
  const body = { scope: 'FILTERED', filters }
  if (p.sortField) { body.sortField = p.sortField; body.sortOrder = p.sortOrder || 'descending' }
  request({ url: 'operations/amz/fba-shipment/export', method: 'post', data: body, responseType: 'blob' }).then(res => {
    const blob = new Blob([res]); const a = document.createElement('a'); a.href = URL.createObjectURL(blob)
    a.download = `amz_fba_shipment_${new Date().getTime()}.xlsx`; a.click()
  })
}

getList()
</script>

<style scoped>
.fba-shipment-page { background: #f5f7fa; }
:deep(.el-table .cell) { white-space: nowrap; }
</style>
