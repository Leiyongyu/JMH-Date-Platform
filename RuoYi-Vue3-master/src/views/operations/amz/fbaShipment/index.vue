<template>
  <div class="app-container fba-shipment-page">
    <el-form :model="queryParams" ref="queryRef" :inline="true" v-show="showSearch" label-width="90px">
      <el-form-item label="店铺" prop="storeName">
        <el-input v-model="queryParams.storeName" placeholder="搜索店铺名称" clearable style="width:180px" @keyup.enter="handleQuery" />
      </el-form-item>
      <el-form-item label="货件单号" prop="shipmentId">
        <el-input v-model="queryParams.shipmentId" placeholder="请输入" clearable style="width:200px" @keyup.enter="handleQuery" />
      </el-form-item>
      <el-form-item label="SKU" prop="sku">
        <el-input v-model="queryParams.sku" placeholder="请输入" clearable style="width:200px" @keyup.enter="handleQuery" />
      </el-form-item>
      <el-form-item label="MSKU" prop="msku">
        <el-input v-model="queryParams.msku" placeholder="请输入" clearable style="width:200px" @keyup.enter="handleQuery" />
      </el-form-item>
      <el-form-item label="创建人" prop="username">
        <el-input v-model="queryParams.username" placeholder="搜索创建人" clearable style="width:160px" @keyup.enter="handleQuery" />
      </el-form-item>
      <el-form-item label="创建时间" prop="gmtCreateRange">
        <el-date-picker v-model="gmtCreateRange" type="daterange" range-separator="-" start-placeholder="开始" end-placeholder="结束" value-format="YYYY-MM-DD" style="width:240px" @change="handleQuery" />
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
      <el-table-column label="店铺" prop="storeName" align="left" width="160" sortable="custom" show-overflow-tooltip />
      <el-table-column label="货件单号" prop="shipmentId" align="left" width="180" sortable="custom" show-overflow-tooltip />
      <el-table-column label="货件名称" prop="shipmentName" align="left" width="220" show-overflow-tooltip />
      <el-table-column label="MSKU" prop="msku" align="left" width="160" sortable="custom" show-overflow-tooltip />
      <el-table-column label="SKU" prop="sku" align="left" width="170" sortable="custom" show-overflow-tooltip />
      <el-table-column label="申报量" prop="quantityShipped" align="right" width="90" sortable="custom" />
      <el-table-column label="签收量" prop="quantityReceived" align="right" width="90" sortable="custom">
        <template #default="scope">
          <span style="color:#67c23a">{{ scope.row.quantityReceived ?? 0 }}</span>
        </template>
      </el-table-column>
      <el-table-column label="申收差异" prop="declaredDiff" align="right" width="100" sortable="custom">
        <template #default="scope">
          <span :style="{ color: scope.row.declaredDiff && scope.row.declaredDiff > 0 ? '#f56c6c' : '' }">{{ scope.row.declaredDiff ?? 0 }}</span>
        </template>
      </el-table-column>
      <el-table-column label="创建人" prop="username" align="center" width="100" />
      <el-table-column label="创建时间" prop="gmtCreate" align="center" width="120">
        <template #default="scope">{{ scope.row.gmtCreate ? scope.row.gmtCreate.substring(0,10) : '-' }}</template>
      </el-table-column>
      <el-table-column label="更新时间" prop="gmtModified" align="center" width="120">
        <template #default="scope">{{ scope.row.gmtModified ? scope.row.gmtModified.substring(0,10) : '-' }}</template>
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
const gmtCreateRange = ref(null)

const data = reactive({
  queryParams: {
    pageNum: 1, pageSize: 50,
    storeName: undefined, shipmentId: undefined, sku: undefined, msku: undefined, username: undefined,
    sortField: undefined, sortOrder: undefined
  }
})
const { queryParams } = toRefs(data)

function getList() {
  loading.value = true
  const body = { pageNum: queryParams.value.pageNum, pageSize: queryParams.value.pageSize, sortField: queryParams.value.sortField || undefined, sortOrder: queryParams.value.sortOrder || undefined }
  const filters = []
  const p = queryParams.value
  if (p.storeName) filters.push({ field: 'storeName', value: p.storeName })
  if (p.shipmentId) filters.push({ field: 'shipmentId', value: p.shipmentId })
  if (p.sku) filters.push({ field: 'sku', value: p.sku })
  if (p.msku) filters.push({ field: 'msku', value: p.msku })
  if (p.username) filters.push({ field: 'username', value: p.username })
  if (gmtCreateRange.value && gmtCreateRange.value.length === 2) {
    if (gmtCreateRange.value[0]) filters.push({ field: 'gmtCreateStart', value: gmtCreateRange.value[0] })
    if (gmtCreateRange.value[1]) filters.push({ field: 'gmtCreateEnd', value: gmtCreateRange.value[1] })
  }
  if (filters.length) body.filters = filters
  searchFbaShipment(body).then(res => { records.value = res.rows || []; total.value = res.total || 0 }).finally(() => { loading.value = false })
}

function handleQuery() { queryParams.value.pageNum = 1; getList() }
function resetQuery() { proxy.resetForm('queryRef'); queryParams.value.sortField = undefined; queryParams.value.sortOrder = undefined; handleQuery() }
function handleSortChange({ prop, order }) { queryParams.value.sortField = order ? prop : undefined; queryParams.value.sortOrder = order || undefined; queryParams.value.pageNum = 1; getList() }

function handleExport() {
  const filters = []
  const p = queryParams.value
  if (p.storeName) filters.push({ field: 'storeName', value: p.storeName })
  if (p.shipmentId) filters.push({ field: 'shipmentId', value: p.shipmentId })
  if (p.sku) filters.push({ field: 'sku', value: p.sku })
  if (p.msku) filters.push({ field: 'msku', value: p.msku })
  if (p.username) filters.push({ field: 'username', value: p.username })
  if (gmtCreateRange.value && gmtCreateRange.value.length === 2) {
    if (gmtCreateRange.value[0]) filters.push({ field: 'gmtCreateStart', value: gmtCreateRange.value[0] })
    if (gmtCreateRange.value[1]) filters.push({ field: 'gmtCreateEnd', value: gmtCreateRange.value[1] })
  }
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
