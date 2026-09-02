<template>
  <div class="app-container pending-purchase-page">
    <el-form v-show="showSearch" ref="queryRef" :model="queryParams" :inline="true"
      label-width="68px" class="query-form">
      <el-form-item label="站点" prop="site">
        <el-input v-model="queryParams.site" placeholder="请输入站点" clearable style="width: 180px"
          @keyup.enter="handleQuery" />
      </el-form-item>
      <el-form-item label="SKU" prop="sku">
        <el-input v-model="queryParams.sku" placeholder="请输入SKU" clearable style="width: 220px"
          @keyup.enter="handleQuery" />
      </el-form-item>
      <el-form-item label="状态" prop="status">
        <el-select v-model="queryParams.status" placeholder="全部状态" clearable style="width: 150px">
          <el-option label="待采购" value="0" />
          <el-option label="已采购" value="1" />
        </el-select>
      </el-form-item>
      <el-form-item>
        <el-button type="primary" icon="Search" @click="handleQuery">搜索</el-button>
        <el-button icon="Refresh" @click="resetQuery">重置</el-button>
      </el-form-item>
    </el-form>

    <el-row :gutter="10" class="mb8 toolbar-row">
      <el-col :span="1.5">
        <el-button type="primary" icon="Download" :disabled="selectedIds.length === 0"
          :loading="exporting" v-hasPermi="['procurement:pendingPurchase:export']"
          @click="handleExport(selectedIds)">
          导出选中（{{ selectedIds.length }}）
        </el-button>
      </el-col>
      <el-col :span="1.5" class="export-tip">导出成功后，所选待采购记录自动转为已采购</el-col>
      <right-toolbar v-model:showSearch="showSearch" @queryTable="getList" />
    </el-row>

    <el-table ref="tableRef" v-loading="loading" :data="rows" border stripe height="640"
      row-key="id" empty-text="暂无待采购记录" @selection-change="handleSelectionChange">
      <el-table-column type="selection" width="50" fixed="left" align="center"
        :selectable="rowSelectable" :reserve-selection="true" />
      <el-table-column label="站点" prop="site" width="130" fixed="left" show-overflow-tooltip />
      <el-table-column label="SKU" prop="sku" min-width="220" fixed="left" show-overflow-tooltip />
      <el-table-column label="最终采购量" prop="purchaseQuantity" width="150" align="right">
        <template #default="{ row }"><strong>{{ formatInteger(row.purchaseQuantity) }}</strong></template>
      </el-table-column>
      <el-table-column label="采购时间" prop="purchaseTime" width="180" align="center" />
      <el-table-column label="状态" prop="status" width="110" align="center">
        <template #default="{ row }">
          <el-tag :type="row.status === '1' ? 'success' : 'danger'" effect="light">
            {{ row.status === '1' ? '已采购' : '待采购' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="导出时间" prop="exportTime" width="180" align="center">
        <template #default="{ row }">{{ row.exportTime || '--' }}</template>
      </el-table-column>
      <el-table-column label="确认人" prop="updateBy" width="130" align="center">
        <template #default="{ row }">{{ row.updateBy || row.createBy || '--' }}</template>
      </el-table-column>
      <el-table-column label="操作" width="100" fixed="right" align="center">
        <template #default="{ row }">
          <el-button v-if="row.status === '0'" link type="primary" :disabled="exporting"
            v-hasPermi="['procurement:pendingPurchase:export']" @click="handleExport([row.id])">
            导出
          </el-button>
          <span v-else class="completed-text">已完成</span>
        </template>
      </el-table-column>
    </el-table>

    <pagination v-show="total > 0" :total="total" v-model:page="queryParams.pageNum"
      v-model:limit="queryParams.pageSize" @pagination="getList" />
  </div>
</template>

<script setup name="PendingPurchase">
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { saveAs } from 'file-saver'
import { exportPendingPurchase, listPendingPurchase } from '@/api/procurement/pendingPurchase'

const showSearch = ref(true)
const queryRef = ref(null)
const tableRef = ref(null)
const loading = ref(false)
const exporting = ref(false)
const rows = ref([])
const total = ref(0)
const selectedIdSet = ref(new Set())
const queryParams = reactive({ pageNum: 1, pageSize: 20, site: undefined, sku: undefined, status: undefined })
const selectedIds = computed(() => [...selectedIdSet.value])

async function getList() {
  loading.value = true
  try {
    const response = await listPendingPurchase({
      ...queryParams,
      site: String(queryParams.site || '').trim() || undefined,
      sku: String(queryParams.sku || '').trim() || undefined
    })
    rows.value = Array.isArray(response.rows) ? response.rows : []
    total.value = Number(response.total || 0)
  } finally {
    loading.value = false
  }
}

function handleQuery() { clearSelection(); queryParams.pageNum = 1; getList() }
function resetQuery() { clearSelection(); queryRef.value?.resetFields(); queryParams.pageNum = 1; getList() }
function handleSelectionChange(selection) {
  const next = new Set(selectedIdSet.value)
  rows.value.filter(rowSelectable).forEach(row => next.delete(row.id))
  selection.filter(rowSelectable).forEach(row => next.add(row.id))
  selectedIdSet.value = next
}
function rowSelectable(row) { return row.status === '0' }

function clearSelection() {
  selectedIdSet.value = new Set()
  tableRef.value?.clearSelection()
}

async function handleExport(ids) {
  if (exporting.value) return
  const uniqueIds = [...new Set((ids || []).filter(Boolean))]
  if (!uniqueIds.length) { ElMessage.warning('请选择需要导出的待采购记录'); return }
  exporting.value = true
  try {
    try {
      await ElMessageBox.confirm(
        `将导出 ${uniqueIds.length} 条记录，并把状态改为“已采购”。是否继续？`,
        '确认采购',
        { type: 'warning', confirmButtonText: '确认导出', cancelButtonText: '取消' }
      )
    } catch (error) { return }
    const data = await exportPendingPurchase(uniqueIds)
    const blob = data instanceof Blob ? data : new Blob([data])
    if (!(await isExcelBlob(blob))) {
      ElMessage.error(await readBlobError(data))
      clearSelection()
      await getList()
      return
    }
    const stamp = new Date().toISOString().replace(/[-:T]/g, '').slice(0, 14)
    saveAs(blob, `待采购_${stamp}.xlsx`)
    ElMessage.success(`已导出 ${uniqueIds.length} 条记录，状态已更新为已采购`)
    clearSelection()
    await getList()
  } finally { exporting.value = false }
}

async function isExcelBlob(blob) {
  const mime = String(blob?.type || '').toLowerCase()
  if (mime.includes('json') || mime.includes('problem') || mime.startsWith('text/')) return false
  const signature = new Uint8Array(await blob.slice(0, 4).arrayBuffer())
  return signature.length >= 2 && signature[0] === 0x50 && signature[1] === 0x4b
}

async function readBlobError(data) {
  try {
    const payload = JSON.parse(await new Blob([data]).text())
    return payload.msg || payload.message || '导出失败'
  } catch (error) { return '导出失败，请刷新后重试' }
}

function formatInteger(value) {
  const number = Number(value)
  return Number.isFinite(number) ? number.toLocaleString('zh-CN', { maximumFractionDigits: 0 }) : '--'
}

onMounted(getList)
</script>

<style scoped>
.pending-purchase-page { min-height: calc(100vh - 84px); background: #f5f7fa; }
.query-form { padding: 14px 16px 0; margin-bottom: 12px; border: 1px solid #e4e7ed; border-radius: 6px; background: #fff; }
.toolbar-row { align-items: center; }
.export-tip { color: #909399; font-size: 13px; line-height: 32px; white-space: nowrap; }
.completed-text { color: #67c23a; }
:deep(.el-table .cell) { white-space: nowrap; }
</style>
