<template>
  <div class="app-container shipment-fee-page">
    <section class="page-hero">
      <div class="hero-copy">
        <div class="hero-eyebrow">
          <span class="eyebrow-dot"></span>
          STA 发货工作台
        </div>
        <h2>发货单与装箱信息上传</h2>
        <p>统一处理物流费用与装箱信息，完整保留每个批次的请求、响应和执行结果。</p>
        <div class="hero-meta">
          <span><el-icon><Document /></el-icon>仅支持 Excel</span>
          <span><el-icon><Tickets /></el-icon>按货件记录日志</span>
          <span><el-icon><Refresh /></el-icon>装箱任务自动更新</span>
        </div>
      </div>

      <div class="hero-note">
        <el-icon><InfoFilled /></el-icon>
        <span>上传前请确认模板与货件数据，费用上传会直接修改领星数据。</span>
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
    </section>

    <section class="upload-grid">
      <article class="upload-card fee-card">
        <div class="upload-card__icon"><el-icon><Wallet /></el-icon></div>
        <div class="upload-card__body">
          <div class="upload-card__heading">
            <div>
              <span class="step-label">01 · 物流费用</span>
              <h3>上传费用明细</h3>
            </div>
            <el-tag type="danger" effect="light" round>修改领星数据</el-tag>
          </div>
          <p>读取 Sheet1 的货件单号、渠道、跟踪信息及预估/实际费用，匹配发货单后逐单提交。</p>
          <div class="upload-card__tips">
            <span>B列：渠道记录 ID</span>
            <span>C列：provider.id</span>
            <span>单条失败不阻断</span>
          </div>
          <el-button
            type="primary"
            icon="Upload"
            :loading="importing"
            v-hasPermi="['customs:shipmentFee:import']"
            @click="selectFile"
          >
            {{ importing ? '正在提交文件' : '选择费用明细文件' }}
          </el-button>
        </div>
      </article>

      <article class="upload-card packing-card">
        <div class="upload-card__icon"><el-icon><Box /></el-icon></div>
        <div class="upload-card__body">
          <div class="upload-card__heading">
            <div>
              <span class="step-label">02 · 装箱信息</span>
              <h3>上传装箱信息</h3>
            </div>
            <el-tag type="success" effect="light" round>仅保存到领星 ERP</el-tag>
          </div>
          <p>按最新版11列表头解析，自动补齐STA编号、SID、内部货件ID和真实MSKU，每行代表一个箱子。</p>
          <div class="upload-card__tips">
            <span>仅读取 Sheet1</span>
            <span>后台逐货件处理</span>
            <span>不会提交亚马逊</span>
          </div>
          <el-button
            type="success"
            icon="Upload"
            :loading="packingImporting"
            v-hasPermi="['customs:shipmentFee:import']"
            @click="selectPackingFile"
          >
            {{ packingImporting ? '正在提交文件' : '选择装箱信息文件' }}
          </el-button>
        </div>
      </article>
    </section>

    <el-card v-if="latestResult.batchNo" shadow="never" class="result-card">
      <div class="result-title">
        <div>
          <span class="section-kicker">最近一次任务</span>
          <strong>{{ latestResult.batchNo }}</strong>
        </div>
        <el-tag :type="batchStatusType(latestResult.status)">
          {{ statusLabel(latestResult.status) }}
        </el-tag>
      </div>
      <div class="result-grid">
        <div><span>文件</span><strong>{{ latestResult.fileName }}</strong></div>
        <div><span>读取行数</span><strong>{{ latestResult.readRows || 0 }}</strong></div>
        <div><span>货件任务数</span><strong>{{ latestResult.totalShipments || 0 }}</strong></div>
        <div class="success"><span>成功</span><strong>{{ latestResult.successCount || 0 }}</strong></div>
        <div class="failed"><span>失败</span><strong>{{ latestResult.failedCount || 0 }}</strong></div>
        <div><span>耗时</span><strong>{{ formatDuration(latestResult.durationMs) }}</strong></div>
      </div>
    </el-card>

    <el-card shadow="never" class="workspace-card">
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
          <el-table-column prop="shipmentId" label="货件单号" min-width="175" show-overflow-tooltip />
          <el-table-column prop="orderSn" label="发货单号" min-width="160" show-overflow-tooltip />
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

      <el-tab-pane label="装箱提交" name="submission">
        <el-alert
          type="warning"
          :closable="false"
          show-icon
          class="submission-alert"
          title="提交成功后不能再次提交"
        >
          <template #default>
            系统会自动聚合历史保存成功的装箱记录，按STA任务一次性提交全部货件。
            领星受理后将持续查询异步任务状态，只有返回success才标记为提交成功。
          </template>
        </el-alert>

        <el-form :model="submissionQuery" :inline="true" class="query-form">
          <el-form-item label="STA编号">
            <el-input
              v-model="submissionQuery.inboundPlanId"
              clearable
              placeholder="输入STA任务编号"
              @keyup.enter="querySubmissions"
            />
          </el-form-item>
          <el-form-item label="提交状态">
            <el-select v-model="submissionQuery.status" clearable placeholder="全部" style="width: 160px">
              <el-option label="待提交" value="READY" />
              <el-option label="正在提交" value="SUBMITTING" />
              <el-option label="领星处理中" value="PROCESSING" />
              <el-option label="提交成功" value="SUCCESS" />
              <el-option label="提交失败" value="FAILED" />
              <el-option label="结果待确认" value="UNKNOWN" />
            </el-select>
          </el-form-item>
          <el-form-item>
            <el-button type="primary" icon="Search" @click="querySubmissions">查询</el-button>
            <el-button icon="Refresh" @click="resetSubmissionQuery">重置</el-button>
          </el-form-item>
        </el-form>

        <el-table v-loading="submissionLoading" :data="submissionList" border stripe>
          <el-table-column type="expand" width="48">
            <template #default="{ row }">
              <div class="log-detail">
                <el-descriptions :column="3" border size="small">
                  <el-descriptions-item label="领星任务ID">{{ row.taskId || '-' }}</el-descriptions-item>
                  <el-descriptions-item label="领星Request ID">{{ row.requestId || '-' }}</el-descriptions-item>
                  <el-descriptions-item label="提交尝试次数">{{ row.attemptCount || 0 }}</el-descriptions-item>
                  <el-descriptions-item label="最近错误" :span="3">{{ row.errorMessage || '-' }}</el-descriptions-item>
                </el-descriptions>
                <div class="json-grid">
                  <section>
                    <h4>提交装箱请求</h4>
                    <pre>{{ prettyJson(row.requestBody) }}</pre>
                  </section>
                  <section>
                    <h4>提交接口响应</h4>
                    <pre>{{ prettyJson(row.initialResponseBody) }}</pre>
                  </section>
                  <section>
                    <h4>异步状态响应</h4>
                    <pre>{{ prettyJson(row.finalResponseBody) }}</pre>
                  </section>
                </div>
              </div>
            </template>
          </el-table-column>
          <el-table-column prop="inboundPlanId" label="STA任务编号" min-width="230" show-overflow-tooltip />
          <el-table-column prop="sid" label="SID" width="95" align="center" />
          <el-table-column label="分仓方式" width="135" align="center">
            <template #default="{ row }">
              {{ row.positionType === 2 ? '先分仓后装箱' : row.positionType === 1 ? '先装箱后分仓' : '-' }}
            </template>
          </el-table-column>
          <el-table-column label="保存进度" width="105" align="center">
            <template #default="{ row }">
              <span :class="{ 'failed-text': !packingComplete(row), 'success-text': packingComplete(row) }">
                {{ row.savedShipmentCount || 0 }}/{{ row.expectedShipmentCount || 0 }}
              </span>
            </template>
          </el-table-column>
          <el-table-column prop="boxCount" label="箱数" width="75" align="center" />
          <el-table-column label="提交状态" width="120" align="center">
            <template #default="{ row }">
              <el-tag :type="submissionStatusType(row.status)">
                {{ submissionStatusLabel(row.status) }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="taskId" label="领星Task ID" min-width="210" show-overflow-tooltip />
          <el-table-column prop="operator" label="提交人" width="100" />
          <el-table-column prop="lastSavedTime" label="最近保存时间" width="175" />
          <el-table-column prop="submitTime" label="提交时间" width="175" />
          <el-table-column prop="successTime" label="成功时间" width="175" />
          <el-table-column prop="errorMessage" label="错误信息" min-width="240" show-overflow-tooltip />
          <el-table-column label="操作" width="175" fixed="right" align="center">
            <template #default="{ row }">
              <el-button
                v-if="['READY', 'FAILED'].includes(row.status)"
                link
                type="primary"
                :disabled="!canSubmitPacking(row)"
                v-hasPermi="['customs:packingSubmission:submit']"
                @click="handleSubmitPacking(row)"
              >
                {{ row.status === 'FAILED' ? '失败重试' : '提交装箱' }}
              </el-button>
              <el-button
                v-if="['PROCESSING', 'UNKNOWN'].includes(row.status) && row.id && row.taskId"
                link
                type="warning"
                v-hasPermi="['customs:packingSubmission:submit']"
                @click="handleRefreshSubmission(row)"
              >
                查询状态
              </el-button>
              <span v-if="row.status === 'SUCCESS'" class="success-text">已完成</span>
              <span v-if="row.status === 'SUBMITTING'" class="muted-text">提交中</span>
            </template>
          </el-table-column>
        </el-table>
        <pagination
          v-show="submissionTotal > 0"
          :total="submissionTotal"
          v-model:page="submissionQuery.pageNum"
          v-model:limit="submissionQuery.pageSize"
          @pagination="loadSubmissions"
        />
      </el-tab-pane>
    </el-tabs>
    </el-card>

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
        <el-table-column prop="shipmentId" label="货件单号" min-width="175" />
        <el-table-column prop="orderSn" label="发货单号" min-width="160" />
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
  listPackingSubmissions,
  listShipmentFeeBatches,
  listShipmentFeeLogs,
  refreshPackingSubmission,
  submitPackingInfo
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

const submissionLoading = ref(false)
const submissionList = ref([])
const submissionTotal = ref(0)
const submissionQuery = reactive({
  pageNum: 1,
  pageSize: 10,
  inboundPlanId: '',
  status: ''
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
    proxy.$modal.msgSuccess(`文件已提交，后台将逐个处理货件。批次号：${latestResult.value.batchNo || '-'}`)
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

function loadSubmissions() {
  submissionLoading.value = true
  return listPackingSubmissions(submissionQuery)
    .then(response => {
      submissionList.value = response.rows || []
      submissionTotal.value = response.total || 0
    })
    .finally(() => {
      submissionLoading.value = false
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

function querySubmissions() {
  submissionQuery.pageNum = 1
  loadSubmissions()
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

function resetSubmissionQuery() {
  Object.assign(submissionQuery, {
    pageNum: 1,
    pageSize: submissionQuery.pageSize,
    inboundPlanId: '',
    status: ''
  })
  loadSubmissions()
}

function handleTabChange(name) {
  if (name === 'batch') loadBatches()
  else if (name === 'log') loadLogs()
  else loadSubmissions()
}

function packingComplete(row) {
  return Number(row.expectedShipmentCount) > 0
    && Number(row.savedShipmentCount) === Number(row.expectedShipmentCount)
}

function canSubmitPacking(row) {
  return ['READY', 'FAILED'].includes(row.status)
    && row.positionType === 2
    && packingComplete(row)
}

async function handleSubmitPacking(row) {
  if (!canSubmitPacking(row)) {
    proxy.$modal.msgError('装箱保存不完整或分仓方式暂不支持提交')
    return
  }
  try {
    await proxy.$modal.confirm(
      `确认提交STA“${row.inboundPlanId}”的装箱信息吗？`
      + `共${row.savedShipmentCount || 0}个货件、${row.boxCount || 0}个箱子；提交成功后不能再次提交。`
    )
  } catch {
    return
  }
  submissionLoading.value = true
  try {
    await submitPackingInfo(row.inboundPlanId)
    proxy.$modal.msgSuccess('已发起提交，系统正在等待领星异步处理结果')
    await loadSubmissions()
  } finally {
    submissionLoading.value = false
  }
}

async function handleRefreshSubmission(row) {
  submissionLoading.value = true
  try {
    const response = await refreshPackingSubmission(row.id)
    const status = response.data?.status
    if (status === 'SUCCESS') proxy.$modal.msgSuccess('装箱提交已成功')
    else if (status === 'FAILED') proxy.$modal.msgError(response.data?.errorMessage || '装箱提交失败')
    else proxy.$modal.msgInfo('领星任务仍在处理中')
    await loadSubmissions()
  } finally {
    submissionLoading.value = false
  }
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

function submissionStatusLabel(status) {
  return {
    READY: '待提交',
    SUBMITTING: '正在提交',
    PROCESSING: '领星处理中',
    SUCCESS: '提交成功',
    FAILED: '提交失败',
    UNKNOWN: '结果待确认'
  }[status] || status || '-'
}

function submissionStatusType(status) {
  return {
    READY: 'info',
    SUBMITTING: 'warning',
    PROCESSING: 'warning',
    SUCCESS: 'success',
    FAILED: 'danger',
    UNKNOWN: 'danger'
  }[status] || 'info'
}

onMounted(() => {
  loadBatches()
  loadLogs()
  loadSubmissions()
  progressTimer = window.setInterval(() => {
    const hasRunningBatch = batchList.value.some(
      row => ['QUEUED', 'RUNNING'].includes(row.status)
    )
    if (hasRunningBatch) Promise.all([loadBatches(), loadLogs()])
    const hasPendingSubmission = submissionList.value.some(
      row => ['SUBMITTING', 'PROCESSING', 'UNKNOWN'].includes(row.status)
    )
    if (hasPendingSubmission) loadSubmissions()
  }, 2500)
})

onBeforeUnmount(() => {
  if (progressTimer) window.clearInterval(progressTimer)
})
</script>

<style scoped lang="scss">
.shipment-fee-page {
  min-height: calc(100vh - 84px);
  padding: 22px 24px 28px;
  background: #f5f7fa;

  .page-hero {
    position: relative;
    display: flex;
    align-items: flex-end;
    justify-content: space-between;
    gap: 32px;
    margin-bottom: 18px;
    padding: 26px 30px;
    overflow: hidden;
    border: 1px solid #e7ebf2;
    border-radius: 14px;
    background: linear-gradient(135deg, #ffffff 0%, #f7faff 68%, #eef5ff 100%);

    &::after {
      position: absolute;
      top: -90px;
      right: -50px;
      width: 250px;
      height: 250px;
      border: 42px solid rgb(64 158 255 / 7%);
      border-radius: 50%;
      content: '';
      pointer-events: none;
    }

    h2 {
      margin: 7px 0 8px;
      color: #1f2937;
      font-size: 26px;
      font-weight: 650;
      letter-spacing: -.5px;
    }

    p {
      margin: 0;
      color: #667085;
      font-size: 14px;
      line-height: 1.7;
    }
  }

  .hero-copy {
    position: relative;
    z-index: 1;
  }

  .hero-eyebrow {
    display: flex;
    align-items: center;
    gap: 7px;
    color: #337ecc;
    font-size: 12px;
    font-weight: 650;
    letter-spacing: .08em;
  }

  .eyebrow-dot {
    width: 7px;
    height: 7px;
    border-radius: 50%;
    background: #409eff;
    box-shadow: 0 0 0 4px rgb(64 158 255 / 12%);
  }

  .hero-meta {
    display: flex;
    flex-wrap: wrap;
    gap: 8px 18px;
    margin-top: 16px;

    span {
      display: inline-flex;
      align-items: center;
      gap: 5px;
      color: #7a8599;
      font-size: 12px;
    }
  }

  .hero-note {
    position: relative;
    z-index: 1;
    display: flex;
    align-items: flex-start;
    gap: 9px;
    max-width: 340px;
    padding: 12px 14px;
    border: 1px solid #f4d7a1;
    border-radius: 10px;
    background: rgb(255 248 235 / 88%);
    color: #8a6428;
    font-size: 13px;
    line-height: 1.55;

    .el-icon {
      flex: 0 0 auto;
      margin-top: 2px;
      font-size: 16px;
    }
  }

  .file-input {
    display: none;
  }

  .upload-grid {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 16px;
    margin-bottom: 18px;
  }

  .upload-card {
    display: flex;
    gap: 16px;
    min-width: 0;
    padding: 22px;
    border: 1px solid #e7ebf2;
    border-radius: 14px;
    background: #fff;
    transition: border-color .2s ease, box-shadow .2s ease, transform .2s ease;

    &:hover {
      border-color: #d8e0ec;
      box-shadow: 0 10px 28px rgb(31 41 55 / 7%);
      transform: translateY(-1px);
    }

    &__icon {
      display: flex;
      align-items: center;
      justify-content: center;
      flex: 0 0 44px;
      width: 44px;
      height: 44px;
      border-radius: 12px;
      font-size: 21px;
    }

    &__body {
      flex: 1;
      min-width: 0;
    }

    &__heading {
      display: flex;
      align-items: flex-start;
      justify-content: space-between;
      gap: 12px;

      h3 {
        margin: 3px 0 0;
        color: #273142;
        font-size: 18px;
        font-weight: 650;
      }
    }

    p {
      min-height: 44px;
      margin: 13px 0;
      color: #667085;
      font-size: 13px;
      line-height: 1.65;
    }

    &__tips {
      display: flex;
      flex-wrap: wrap;
      gap: 6px;
      margin-bottom: 16px;

      span {
        padding: 4px 8px;
        border-radius: 5px;
        background: #f4f6f8;
        color: #7a8599;
        font-size: 11px;
      }
    }
  }

  .fee-card .upload-card__icon {
    background: #edf5ff;
    color: #337ecc;
  }

  .packing-card .upload-card__icon {
    background: #ecf8f3;
    color: #269764;
  }

  .step-label,
  .section-kicker {
    color: #98a2b3;
    font-size: 11px;
    font-weight: 650;
    letter-spacing: .06em;
    text-transform: uppercase;
  }

  .result-title {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 16px;

    div {
      display: flex;
      flex-direction: column;
      gap: 4px;
    }

    strong {
      color: #344054;
      font-size: 15px;
    }
  }

  .result-card {
    margin-bottom: 18px;
    border: 1px solid #e7ebf2;
    border-radius: 14px;
  }

  .result-grid {
    display: grid;
    grid-template-columns: repeat(6, minmax(0, 1fr));
    gap: 10px;

    div {
      min-width: 0;
      padding: 12px 14px;
      border: 1px solid #edf0f4;
      border-radius: 9px;
      background: #fafbfc;
    }

    span {
      display: block;
      margin-bottom: 6px;
      color: var(--el-text-color-secondary);
      font-size: 12px;
    }

    strong {
      display: block;
      overflow: hidden;
      color: #344054;
      text-overflow: ellipsis;
      white-space: nowrap;
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

  .workspace-card {
    border: 1px solid #e7ebf2;
    border-radius: 14px;

    :deep(.el-card__body) {
      padding: 0;
    }
  }

  .log-tabs {
    :deep(.el-tabs__header) {
      margin: 0;
      padding: 0 22px;
      border-bottom: 1px solid #edf0f4;
    }

    :deep(.el-tabs__nav-wrap::after) {
      display: none;
    }

    :deep(.el-tabs__item) {
      height: 54px;
      color: #667085;
      font-weight: 500;
    }

    :deep(.el-tabs__item.is-active) {
      color: #337ecc;
      font-weight: 650;
    }

    :deep(.el-tabs__content) {
      padding: 20px 22px 22px;
    }
  }

  .query-form {
    margin-bottom: 16px;
    padding: 16px 16px 0;
    border: 1px solid #edf0f4;
    border-radius: 10px;
    background: #fafbfc;

    :deep(.el-form-item) {
      margin-right: 14px;
      margin-bottom: 16px;
    }
  }

  .submission-alert {
    margin-bottom: 16px;
    border-radius: 9px;
  }

  :deep(.el-table) {
    --el-table-border-color: #edf0f4;
    --el-table-header-bg-color: #f8fafc;
    --el-table-row-hover-bg-color: #f7faff;
    border-radius: 9px;
  }

  :deep(.el-table th.el-table__cell) {
    height: 46px;
    color: #596579;
    font-weight: 600;
  }

  :deep(.pagination-container) {
    margin-bottom: 0;
    padding: 20px 0 0;
  }

  .success-text {
    color: var(--el-color-success);
  }

  .failed-text {
    color: var(--el-color-danger);
  }

  .muted-text {
    color: var(--el-text-color-secondary);
  }

  .log-detail {
    padding: 16px 18px;
    background: #fafbfc;
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
      color: #475467;
      font-size: 13px;
      font-weight: 600;
    }

    pre {
      max-height: 320px;
      margin: 0;
      padding: 14px;
      overflow: auto;
      border-radius: 9px;
      background: #172033;
      color: #d9e2f2;
      white-space: pre-wrap;
      word-break: break-all;
      font-size: 12px;
      line-height: 1.5;
    }
  }
}

@media (max-width: 1200px) {
  .shipment-fee-page {
    .page-hero {
      align-items: flex-start;
      flex-direction: column;
    }

    .hero-note {
      max-width: none;
    }

    .result-grid {
      grid-template-columns: repeat(3, minmax(0, 1fr));
    }

    .json-grid {
      grid-template-columns: 1fr;
    }
  }
}

@media (max-width: 860px) {
  .shipment-fee-page {
    padding: 14px;

    .page-hero {
      padding: 22px;
    }

    .upload-grid {
      grid-template-columns: 1fr;
    }

    .result-grid {
      grid-template-columns: repeat(2, minmax(0, 1fr));
    }

    .log-tabs :deep(.el-tabs__content) {
      padding: 16px;
    }
  }
}

@media (max-width: 560px) {
  .shipment-fee-page {
    .hero-meta {
      flex-direction: column;
    }

    .upload-card {
      padding: 18px;
    }

    .upload-card__heading {
      align-items: flex-start;
      flex-direction: column;
    }

    .result-grid {
      grid-template-columns: 1fr;
    }
  }
}
</style>
