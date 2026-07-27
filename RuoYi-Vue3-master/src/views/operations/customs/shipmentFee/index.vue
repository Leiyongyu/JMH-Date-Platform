<template>
  <div class="app-container shipment-fee-page">
    <div class="page-header">
      <div>
        <h2>发货单与装箱信息上传</h2>
        <p>逐条调用领星接口，并在同一批次与明细日志中记录完整请求和响应。</p>
      </div>
      <div class="header-actions">
        <el-button
          type="primary"
          icon="Upload"
          :loading="importing"
          v-hasPermi="['customs:shipmentFee:import']"
          @click="selectFile"
        >
          {{ importing ? '正在逐单上传' : '上传发货单号' }}
        </el-button>
        <el-button
          type="success"
          icon="Upload"
          :loading="packingImporting"
          v-hasPermi="['customs:shipmentFee:import']"
          @click="selectPackingFile"
        >
          {{ packingImporting ? '正在提交文件' : '上传装箱信息' }}
        </el-button>
      </div>
      <input
        ref="fileInputRef"
        class="file-input"
        type="file"
        accept=".xlsx,.xls"
        @change="handleFileChange"
      >
      <input
        ref="packingFileInputRef"
        class="file-input"
        type="file"
        accept=".xlsx,.xls"
        @change="handlePackingFileChange"
      >
    </div>

    <el-alert
      type="warning"
      :closable="false"
      show-icon
      class="upload-tip"
      title="上传会真实修改领星数据"
    >
      <template #default>
        当前仅读取 Sheet1 第一列“发货单号”，并按发货单号逐单提交；
        不上传物流信息、费用信息或空数组，避免覆盖领星已有数据。单条失败不会终止后续发货单。
      </template>
    </el-alert>

    <el-alert
      type="info"
      :closable="false"
      show-icon
      class="upload-tip"
      title="装箱信息会保存到领星ERP"
    >
      <template #default>
        严格按最新版“装箱信息模版.xlsx”的11列表头解析，只需填写FBA货件号、箱规、SKU、申报量及重量等装箱数据。
        后端会根据货件号自动补齐STA编号、SID、领星内部货件ID和真实MSKU；本地没有该货件时会先自动补拉STA任务。
        每个Excel行表示一个箱子；本操作只读取Sheet1，由后台按货件逐个保存，可在批次和明细日志中查看结果，不提交亚马逊。
      </template>
    </el-alert>

    <el-card v-if="latestResult.batchNo" shadow="never" class="result-card">
      <div class="result-title">
        <span>最近上传：{{ latestResult.batchNo }}</span>
        <el-tag :type="batchStatusType(latestResult.status)">
          {{ statusLabel(latestResult.status) }}
        </el-tag>
      </div>
      <div class="result-grid">
        <div><span>文件</span><strong>{{ latestResult.fileName }}</strong></div>
        <div><span>读取行数</span><strong>{{ latestResult.readRows || 0 }}</strong></div>
        <div><span>{{ latestResult.businessType === 'PACKING_INFO' ? '货件保存任务数' : '发货单数' }}</span><strong>{{ latestResult.totalShipments || 0 }}</strong></div>
        <div class="success"><span>成功</span><strong>{{ latestResult.successCount || 0 }}</strong></div>
        <div class="failed"><span>失败</span><strong>{{ latestResult.failedCount || 0 }}</strong></div>
        <div><span>耗时</span><strong>{{ formatDuration(latestResult.durationMs) }}</strong></div>
      </div>
    </el-card>

    <el-tabs v-model="activeTab" class="log-tabs" @tab-change="handleTabChange">
      <el-tab-pane label="上传批次" name="batch">
        <el-form :model="batchQuery" :inline="true" class="query-form">
          <el-form-item label="业务类型">
            <el-select v-model="batchQuery.businessType" clearable placeholder="全部" style="width: 180px">
              <el-option label="发货单物流" value="SHIPMENT_LOGISTICS" />
              <el-option label="装箱信息回传" value="PACKING_INFO" />
            </el-select>
          </el-form-item>
          <el-form-item label="批次号">
            <el-input v-model="batchQuery.batchNo" clearable placeholder="输入批次号" @keyup.enter="queryBatches" />
          </el-form-item>
          <el-form-item label="状态">
            <el-select v-model="batchQuery.status" clearable placeholder="全部" style="width: 160px">
              <el-option label="排队中" value="QUEUED" />
              <el-option label="执行中" value="RUNNING" />
              <el-option label="成功" value="SUCCESS" />
              <el-option label="部分成功" value="PARTIAL_SUCCESS" />
              <el-option label="失败" value="FAILED" />
            </el-select>
          </el-form-item>
          <el-form-item label="上传人">
            <el-input v-model="batchQuery.operator" clearable placeholder="上传账号" @keyup.enter="queryBatches" />
          </el-form-item>
          <el-form-item>
            <el-button type="primary" icon="Search" @click="queryBatches">查询</el-button>
            <el-button icon="Refresh" @click="resetBatchQuery">重置</el-button>
          </el-form-item>
        </el-form>

        <el-table v-loading="batchLoading" :data="batchList" border stripe>
          <el-table-column label="业务类型" width="135" align="center">
            <template #default="{ row }">
              <el-tag :type="row.businessType === 'PACKING_INFO' ? 'success' : 'primary'">
                {{ businessTypeLabel(row.businessType) }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="batchNo" label="批次号" min-width="225" show-overflow-tooltip />
          <el-table-column prop="originalFileName" label="文件名" min-width="180" show-overflow-tooltip />
          <el-table-column label="状态" width="110" align="center">
            <template #default="{ row }">
              <el-tag :type="batchStatusType(row.status)">{{ statusLabel(row.status) }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="成功/失败/总数" width="145" align="center">
            <template #default="{ row }">
              <span class="success-text">{{ row.successCount || 0 }}</span>
              /
              <span class="failed-text">{{ row.failedCount || 0 }}</span>
              /
              {{ row.totalShipments || 0 }}
            </template>
          </el-table-column>
          <el-table-column prop="totalRows" label="Excel行数" width="95" align="center" />
          <el-table-column prop="operator" label="上传人" width="110" />
          <el-table-column prop="uploadTime" label="上传时间" width="175" />
          <el-table-column prop="finishTime" label="完成时间" width="175" />
          <el-table-column label="耗时" width="100" align="right">
            <template #default="{ row }">{{ formatDuration(row.durationMs) }}</template>
          </el-table-column>
          <el-table-column prop="fileSha256" label="文件SHA-256" min-width="190" show-overflow-tooltip />
          <el-table-column prop="errorMessage" label="文件级错误/汇总" min-width="220" show-overflow-tooltip />
        </el-table>
        <pagination
          v-show="batchTotal > 0"
          :total="batchTotal"
          v-model:page="batchQuery.pageNum"
          v-model:limit="batchQuery.pageSize"
          @pagination="loadBatches"
        />
      </el-tab-pane>

      <el-tab-pane label="上传明细日志" name="log">
        <el-form :model="logQuery" :inline="true" class="query-form">
          <el-form-item label="业务类型">
            <el-select v-model="logQuery.businessType" clearable placeholder="全部" style="width: 180px">
              <el-option label="发货单物流" value="SHIPMENT_LOGISTICS" />
              <el-option label="装箱信息回传" value="PACKING_INFO" />
            </el-select>
          </el-form-item>
          <el-form-item label="业务单号">
            <el-input v-model="logQuery.orderSn" clearable placeholder="发货单号/货件号" @keyup.enter="queryLogs" />
          </el-form-item>
          <el-form-item label="批次号">
            <el-input v-model="logQuery.batchNo" clearable placeholder="输入批次号" @keyup.enter="queryLogs" />
          </el-form-item>
          <el-form-item label="状态">
            <el-select v-model="logQuery.status" clearable placeholder="全部" style="width: 130px">
              <el-option label="处理中" value="PROCESSING" />
              <el-option label="成功" value="SUCCESS" />
              <el-option label="失败" value="FAILED" />
            </el-select>
          </el-form-item>
          <el-form-item label="上传时间">
            <el-date-picker
              v-model="logDateRange"
              type="daterange"
              range-separator="至"
              start-placeholder="开始日期"
              end-placeholder="结束日期"
              value-format="YYYY-MM-DD"
              style="width: 250px"
            />
          </el-form-item>
          <el-form-item>
            <el-button type="primary" icon="Search" @click="queryLogs">查询</el-button>
            <el-button icon="Refresh" @click="resetLogQuery">重置</el-button>
          </el-form-item>
        </el-form>

        <el-table v-loading="logLoading" :data="logList" border stripe>
          <el-table-column type="expand" width="48">
            <template #default="{ row }">
              <div class="log-detail">
                <el-descriptions :column="3" border size="small">
                  <el-descriptions-item label="Excel来源行">{{ row.sourceRows || '-' }}</el-descriptions-item>
                  <el-descriptions-item label="尝试次数">{{ row.attemptCount || 0 }}</el-descriptions-item>
                  <el-descriptions-item label="领星响应时间">{{ row.lingxingResponseTime || '-' }}</el-descriptions-item>
                  <el-descriptions-item label="异常类型" :span="3">{{ row.exceptionType || '-' }}</el-descriptions-item>
                  <el-descriptions-item label="失败原因" :span="3">{{ row.errorMessage || '-' }}</el-descriptions-item>
                </el-descriptions>
                <div class="json-grid">
                  <section>
                    <h4>Excel原始数据</h4>
                    <pre>{{ prettyJson(row.sourceData) }}</pre>
                  </section>
                  <section>
                    <h4>发送给领星的请求</h4>
                    <pre>{{ prettyJson(row.requestBody) }}</pre>
                  </section>
                  <section>
                    <h4>领星原始响应</h4>
                    <pre>{{ prettyJson(row.responseBody) }}</pre>
                  </section>
                  <section v-if="row.stackTrace">
                    <h4>异常堆栈</h4>
                    <pre>{{ row.stackTrace }}</pre>
                  </section>
                </div>
              </div>
            </template>
          </el-table-column>
          <el-table-column label="业务类型" width="135" align="center">
            <template #default="{ row }">
              <el-tag :type="row.businessType === 'PACKING_INFO' ? 'success' : 'primary'">
                {{ businessTypeLabel(row.businessType) }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="orderSn" label="业务单号" min-width="210" show-overflow-tooltip />
          <el-table-column label="状态" width="90" align="center">
            <template #default="{ row }">
              <el-tag :type="logStatusType(row.status)">{{ statusLabel(row.status) }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="batchNo" label="批次号" min-width="215" show-overflow-tooltip />
          <el-table-column prop="originalFileName" label="文件名" min-width="160" show-overflow-tooltip />
          <el-table-column prop="sourceRows" label="Excel行" width="100" show-overflow-tooltip />
          <el-table-column prop="errorStage" label="失败阶段" width="125" />
          <el-table-column prop="errorCode" label="错误码" width="135" show-overflow-tooltip />
          <el-table-column prop="errorMessage" label="失败原因" min-width="240" show-overflow-tooltip />
          <el-table-column prop="requestId" label="领星Request ID" min-width="225" show-overflow-tooltip />
          <el-table-column prop="operator" label="上传人" width="100" />
          <el-table-column prop="uploadTime" label="上传时间" width="175" />
          <el-table-column prop="startTime" label="开始时间" width="175" />
          <el-table-column prop="successTime" label="成功时间" width="175" />
          <el-table-column prop="failedTime" label="失败时间" width="175" />
          <el-table-column label="耗时" width="100" align="right">
            <template #default="{ row }">{{ formatDuration(row.durationMs) }}</template>
          </el-table-column>
        </el-table>
        <pagination
          v-show="logTotal > 0"
          :total="logTotal"
          v-model:page="logQuery.pageNum"
          v-model:limit="logQuery.pageSize"
          @pagination="loadLogs"
        />
      </el-tab-pane>
    </el-tabs>

    <el-dialog v-model="resultDialogVisible" title="提交结果" width="760px">
      <el-result
        :icon="resultIcon"
        :title="resultTitle"
        :sub-title="`批次号：${latestResult.batchNo || '-'}`"
      />
      <el-table
        v-if="latestResult.failures?.length"
        :data="latestResult.failures"
        border
        size="small"
        max-height="360"
      >
        <el-table-column prop="orderSn" label="业务单号" min-width="200" />
        <el-table-column prop="sourceRows" label="Excel行" width="90" />
        <el-table-column prop="stage" label="失败阶段" width="120" />
        <el-table-column prop="code" label="错误码" width="130" />
        <el-table-column prop="message" label="失败原因" min-width="240" show-overflow-tooltip />
      </el-table>
      <template #footer>
        <el-button type="primary" @click="openFailedLogs">查看详细日志</el-button>
        <el-button @click="resultDialogVisible = false">关闭</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup name="CustomsShipmentFee">
import { computed, getCurrentInstance, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import {
  importPackingInfo,
  importShipmentFee,
  listShipmentFeeBatches,
  listShipmentFeeLogs
} from '@/api/operations/customs/shipmentFee'

const { proxy } = getCurrentInstance()
const activeTab = ref('batch')
const importing = ref(false)
const packingImporting = ref(false)
const fileInputRef = ref()
const packingFileInputRef = ref()
const resultDialogVisible = ref(false)
const latestResult = ref({})
let progressTimer

const batchLoading = ref(false)
const batchList = ref([])
const batchTotal = ref(0)
const batchQuery = reactive({
  pageNum: 1,
  pageSize: 10,
  businessType: '',
  batchNo: '',
  status: '',
  operator: ''
})

const logLoading = ref(false)
const logList = ref([])
const logTotal = ref(0)
const logDateRange = ref([])
const logQuery = reactive({
  pageNum: 1,
  pageSize: 10,
  businessType: '',
  batchNo: '',
  orderSn: '',
  status: '',
  operator: ''
})

const resultTitle = computed(() => {
  const result = latestResult.value
  if (result.status === 'QUEUED') return `已进入后台队列，共 ${result.totalShipments || 0} 个货件`
  if (result.status === 'RUNNING') {
    const completed = (result.successCount || 0) + (result.failedCount || 0)
    return `后台处理中 ${completed}/${result.totalShipments || 0}`
  }
  return `成功 ${result.successCount || 0} 个，失败 ${result.failedCount || 0} 个`
})

const resultIcon = computed(() => {
  if (['QUEUED', 'RUNNING'].includes(latestResult.value.status)) return 'info'
  return latestResult.value.failedCount ? 'warning' : 'success'
})

function selectFile() {
  fileInputRef.value?.click()
}

function selectPackingFile() {
  packingFileInputRef.value?.click()
}

async function handleFileChange(event) {
  const file = event.target.files?.[0]
  event.target.value = ''
  if (!file) return
  if (!/\.(xlsx|xls)$/i.test(file.name)) {
    proxy.$modal.msgError('仅支持 .xlsx 或 .xls 文件')
    return
  }
  try {
    await proxy.$modal.confirm(
      `确认上传“${file.name}”并逐单修改领星发货单物流费用吗？`
    )
  } catch {
    return
  }

  importing.value = true
  try {
    const response = await importShipmentFee(file)
    latestResult.value = response.data || {}
    resultDialogVisible.value = true
    proxy.$modal.msgSuccess('文件处理完成')
    await Promise.all([loadBatches(), loadLogs()])
  } finally {
    importing.value = false
  }
}

async function handlePackingFileChange(event) {
  const file = event.target.files?.[0]
  event.target.value = ''
  if (!file) return
  if (!/\.(xlsx|xls)$/i.test(file.name)) {
    proxy.$modal.msgError('仅支持 .xlsx 或 .xls 文件')
    return
  }
  try {
    await proxy.$modal.confirm(
      `确认上传“${file.name}”并逐个货件保存装箱信息到领星ERP吗？本操作不会提交到亚马逊。`
    )
  } catch {
    return
  }

  packingImporting.value = true
  try {
    const response = await importPackingInfo(file)
    latestResult.value = response.data || {}
    resultDialogVisible.value = true
    proxy.$modal.msgSuccess(`文件已提交，后台将逐个处理货件。批次号：${latestResult.value.batchNo || '-'}`)
    await Promise.all([loadBatches(), loadLogs()])
  } finally {
    packingImporting.value = false
  }
}

function loadBatches() {
  batchLoading.value = true
  return listShipmentFeeBatches(batchQuery)
    .then(response => {
      batchList.value = response.rows || []
      batchTotal.value = response.total || 0
      const current = batchList.value.find(row => row.batchNo === latestResult.value.batchNo)
      if (current) {
        latestResult.value = {
          ...latestResult.value,
          status: current.status,
          successCount: current.successCount,
          failedCount: current.failedCount,
          totalShipments: current.totalShipments,
          durationMs: current.durationMs
        }
      }
    })
    .finally(() => {
      batchLoading.value = false
    })
}

function loadLogs() {
  logLoading.value = true
  const params = {
    ...logQuery,
    beginTime: logDateRange.value?.[0],
    endTime: logDateRange.value?.[1]
  }
  return listShipmentFeeLogs(params)
    .then(response => {
      logList.value = response.rows || []
      logTotal.value = response.total || 0
    })
    .finally(() => {
      logLoading.value = false
    })
}

function queryBatches() {
  batchQuery.pageNum = 1
  loadBatches()
}

function queryLogs() {
  logQuery.pageNum = 1
  loadLogs()
}

function resetBatchQuery() {
  Object.assign(batchQuery, {
    pageNum: 1,
    pageSize: batchQuery.pageSize,
    businessType: '',
    batchNo: '',
    status: '',
    operator: ''
  })
  loadBatches()
}

function resetLogQuery() {
  Object.assign(logQuery, {
    pageNum: 1,
    pageSize: logQuery.pageSize,
    businessType: '',
    batchNo: '',
    orderSn: '',
    status: '',
    operator: ''
  })
  logDateRange.value = []
  loadLogs()
}

function handleTabChange(name) {
  if (name === 'batch') loadBatches()
  else loadLogs()
}

function openFailedLogs() {
  resultDialogVisible.value = false
  activeTab.value = 'log'
  logQuery.batchNo = latestResult.value.batchNo || ''
  logQuery.status = latestResult.value.failedCount ? 'FAILED' : ''
  queryLogs()
}

function prettyJson(value) {
  if (!value) return '-'
  if (typeof value !== 'string') return JSON.stringify(value, null, 2)
  try {
    return JSON.stringify(JSON.parse(value), null, 2)
  } catch {
    return value
  }
}

function formatDuration(value) {
  if (value === null || value === undefined) return '-'
  if (value < 1000) return `${value}ms`
  return `${(value / 1000).toFixed(2)}s`
}

function statusLabel(status) {
  const labels = {
    QUEUED: '排队中',
    RUNNING: '执行中',
    PROCESSING: '处理中',
    SUCCESS: '成功',
    PARTIAL_SUCCESS: '部分成功',
    FAILED: '失败'
  }
  return labels[status] || status || '-'
}

function businessTypeLabel(value) {
  return {
    SHIPMENT_LOGISTICS: '发货单物流',
    PACKING_INFO: '装箱信息回传'
  }[value] || value || '-'
}

function batchStatusType(status) {
  return {
    QUEUED: 'info',
    RUNNING: 'warning',
    SUCCESS: 'success',
    PARTIAL_SUCCESS: 'warning',
    FAILED: 'danger'
  }[status] || 'info'
}

function logStatusType(status) {
  return {
    PROCESSING: 'warning',
    SUCCESS: 'success',
    FAILED: 'danger'
  }[status] || 'info'
}

onMounted(() => {
  loadBatches()
  loadLogs()
  progressTimer = window.setInterval(() => {
    const hasRunningBatch = batchList.value.some(
      row => row.businessType === 'PACKING_INFO' && ['QUEUED', 'RUNNING'].includes(row.status)
    )
    if (hasRunningBatch) Promise.all([loadBatches(), loadLogs()])
  }, 2500)
})

onBeforeUnmount(() => {
  if (progressTimer) window.clearInterval(progressTimer)
})
</script>

<style scoped lang="scss">
.shipment-fee-page {
  .page-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 24px;
    margin-bottom: 16px;

    h2 {
      margin: 0 0 6px;
      font-size: 22px;
    }

    p {
      margin: 0;
      color: var(--el-text-color-secondary);
    }
  }

  .file-input {
    display: none;
  }

  .header-actions {
    display: flex;
    flex-shrink: 0;
    gap: 8px;
  }

  .upload-tip,
  .result-card,
  .log-tabs {
    margin-bottom: 16px;
  }

  .result-title {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 14px;
    font-weight: 600;
  }

  .result-grid {
    display: grid;
    grid-template-columns: repeat(6, minmax(0, 1fr));
    gap: 12px;

    div {
      padding: 12px;
      border-radius: 6px;
      background: var(--el-fill-color-light);
    }

    span {
      display: block;
      margin-bottom: 6px;
      color: var(--el-text-color-secondary);
      font-size: 12px;
    }

    strong {
      word-break: break-all;
    }

    .success strong,
    .success-text {
      color: var(--el-color-success);
    }

    .failed strong,
    .failed-text {
      color: var(--el-color-danger);
    }
  }

  .query-form {
    margin-bottom: 4px;
  }

  .log-detail {
    padding: 14px 18px;
  }

  .json-grid {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 12px;
    margin-top: 14px;

    section {
      min-width: 0;
    }

    h4 {
      margin: 0 0 8px;
    }

    pre {
      max-height: 320px;
      margin: 0;
      padding: 12px;
      overflow: auto;
      border-radius: 6px;
      background: #111827;
      color: #d1fae5;
      white-space: pre-wrap;
      word-break: break-all;
      font-size: 12px;
      line-height: 1.5;
    }
  }
}

@media (max-width: 1200px) {
  .shipment-fee-page {
    .result-grid {
      grid-template-columns: repeat(3, minmax(0, 1fr));
    }

    .json-grid {
      grid-template-columns: 1fr;
    }
  }
}
</style>
