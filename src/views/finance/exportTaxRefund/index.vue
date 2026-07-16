<template>
  <div class="app-container tax-refund-page">
    <el-row :gutter="12" class="metric-row">
      <el-col v-for="item in metrics" :key="item.label" :xs="12" :sm="12" :md="6">
        <div class="metric-card">
          <div class="metric-label">{{ item.label }}</div>
          <div class="metric-value">{{ item.value }}</div>
          <div class="metric-sub">{{ item.sub }}</div>
        </div>
      </el-col>
    </el-row>

    <el-card shadow="never" class="workflow-card">
      <template #header>
        <div class="card-head">
          <span>外汇退税流程</span>
          <el-button icon="Refresh" @click="loadAll" :loading="loading.tasks">刷新</el-button>
        </div>
      </template>
      <el-steps :active="workflowActive" finish-status="success" align-center>
        <el-step title="报关资料" description="Excel导入" />
        <el-step title="出口报关单" description="PDF解析" />
        <el-step title="进货发票" description="PDF解析" />
        <el-step title="外汇数据" description="Excel导入" />
        <el-step title="生成资料" description="汇总输出" />
      </el-steps>
    </el-card>

    <el-tabs v-model="activeTab" class="main-tabs">
      <el-tab-pane label="任务导入" name="tasks">
        <el-row :gutter="12">
          <el-col v-for="item in importCards" :key="item.type" :xs="24" :md="12" :xl="6">
            <el-card shadow="never" class="import-card">
              <template #header>
                <div class="card-head">
                  <span>{{ item.title }}</span>
                  <el-tag :type="item.tagType">{{ item.ext }}</el-tag>
                </div>
              </template>
              <div class="import-desc">{{ item.desc }}</div>
              <el-upload
                :auto-upload="false"
                :show-file-list="true"
                :limit="1"
                :on-change="file => selectFile(item.type, file)"
                :on-remove="() => removeFile(item.type)"
                :accept="item.accept"
              >
                <el-button icon="Upload">选择文件</el-button>
              </el-upload>
              <el-form v-if="item.type === 'CUSTOMS_DECLARATION_IMPORT'" :model="customsForm" label-width="74px" class="mini-form">
                <el-form-item label="申报月份">
                  <el-input v-model="customsForm.declarationMonth" placeholder="202512" clearable />
                </el-form-item>
                <el-form-item label="申报批次">
                  <el-input v-model="customsForm.declarationBatch" placeholder="可为空" clearable />
                </el-form-item>
                <el-form-item label="出口日期">
                  <el-date-picker v-model="customsForm.exportDate" type="date" value-format="YYYY-MM-DD" placeholder="可为空" clearable style="width: 100%" />
                </el-form-item>
              </el-form>
              <el-button
                type="primary"
                class="full-btn"
                :loading="uploading[item.type]"
                @click="submitImport(item.type)"
                v-hasPermi="['finance:exportTaxRefund:import']"
              >
                创建导入任务
              </el-button>
            </el-card>
          </el-col>
        </el-row>

        <el-card shadow="never" class="mt12">
          <template #header>
            <div class="card-head">
              <span>退税资料生成</span>
              <el-tag type="warning">Python服务端目录</el-tag>
            </div>
          </template>
          <el-form :model="generateForm" label-width="120px" class="generate-form">
            <el-row :gutter="12">
              <el-col :xs="24" :md="10">
                <el-form-item label="输出父目录">
                  <el-input v-model="generateForm.output_parent_dir" placeholder="D:/JMH/退税输出" />
                </el-form-item>
              </el-col>
              <el-col :xs="24" :md="5">
                <el-form-item label="申报月份">
                  <el-input v-model="generateForm.declaration_month" placeholder="202512" />
                </el-form-item>
              </el-col>
              <el-col :xs="24" :md="6">
                <el-form-item label="付款人">
                  <el-input v-model="generateForm.payer_name" />
                </el-form-item>
              </el-col>
              <el-col :xs="24" :md="3">
                <el-form-item label="覆盖">
                  <el-switch v-model="generateForm.overwrite" />
                </el-form-item>
              </el-col>
            </el-row>
            <el-button
              type="success"
              icon="Finished"
              :loading="uploading.REFUND_PACKAGE_GENERATE"
              @click="submitGenerate"
              v-hasPermi="['finance:exportTaxRefund:generate']"
            >
              创建生成任务
            </el-button>
          </el-form>
        </el-card>
      </el-tab-pane>

      <el-tab-pane label="任务历史" name="history">
        <el-card shadow="never">
          <el-form :model="taskQuery" inline>
            <el-form-item label="任务类型">
              <el-select v-model="taskQuery.task_type" clearable placeholder="全部" style="width: 220px">
                <el-option v-for="item in taskTypes" :key="item.value" :label="item.label" :value="item.value" />
              </el-select>
            </el-form-item>
            <el-form-item label="状态">
              <el-select v-model="taskQuery.task_status" clearable placeholder="全部" style="width: 140px">
                <el-option v-for="status in statuses" :key="status" :label="status" :value="status" />
              </el-select>
            </el-form-item>
            <el-form-item>
              <el-button type="primary" icon="Search" @click="loadTasks" v-hasPermi="['finance:exportTaxRefund:query']">查询</el-button>
              <el-button icon="Refresh" @click="resetTaskQuery">重置</el-button>
            </el-form-item>
          </el-form>
          <el-table :data="tasks" border stripe v-loading="loading.tasks">
            <el-table-column prop="id" label="任务ID" width="86" />
            <el-table-column prop="task_type" label="任务类型" min-width="190">
              <template #default="scope">{{ taskTypeLabel(scope.row.task_type) }}</template>
            </el-table-column>
            <el-table-column prop="task_status" label="状态" width="100">
              <template #default="scope">
                <el-tag :type="statusType(scope.row.task_status)">{{ scope.row.task_status }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column label="进度" width="180">
              <template #default="scope">
                <el-progress :percentage="progress(scope.row)" :status="progressStatus(scope.row.task_status)" />
              </template>
            </el-table-column>
            <el-table-column prop="original_file_name" label="文件名" min-width="180" show-overflow-tooltip />
            <el-table-column prop="error_message" label="错误信息" min-width="220" show-overflow-tooltip />
            <el-table-column prop="created_by" label="创建人" width="110" />
            <el-table-column prop="created_at" label="创建时间" width="170" />
            <el-table-column label="操作" width="100" fixed="right">
              <template #default="scope">
                <el-button link type="primary" @click="showTask(scope.row)">详情</el-button>
              </template>
            </el-table-column>
          </el-table>
          <pagination v-show="taskTotal > 0" :total="taskTotal" v-model:page="taskQuery.page" v-model:limit="taskQuery.page_size" @pagination="loadTasks" />
        </el-card>
      </el-tab-pane>

      <el-tab-pane label="出口明细" name="exports">
        <el-card shadow="never">
          <el-form :model="exportQuery" inline>
            <el-form-item label="合同协议号">
              <el-input v-model="exportQuery.contract_no" clearable placeholder="FBA15L7CCK57" />
            </el-form-item>
            <el-form-item label="申报月份">
              <el-input v-model="exportQuery.declaration_month" clearable placeholder="202512" />
            </el-form-item>
            <el-form-item label="匹配状态">
              <el-input v-model="exportQuery.customs_match_status" clearable placeholder="可为空" />
            </el-form-item>
            <el-form-item>
              <el-button type="primary" icon="Search" @click="loadExports" v-hasPermi="['finance:exportTaxRefund:query']">查询</el-button>
            </el-form-item>
          </el-form>
          <el-table :data="exports" border stripe v-loading="loading.exports" height="520">
            <el-table-column prop="customs_declaration_no" label="报关单号" min-width="180" show-overflow-tooltip />
            <el-table-column prop="contract_no" label="合同协议号" min-width="150" show-overflow-tooltip />
            <el-table-column prop="customs_item_no" label="项号" width="80" />
            <el-table-column prop="sku_normalized" label="SKU" min-width="140" show-overflow-tooltip />
            <el-table-column prop="export_product_name" label="商品名称" min-width="220" show-overflow-tooltip />
            <el-table-column prop="quantity" label="数量" width="100" align="right" />
            <el-table-column prop="total_amount" label="金额" width="120" align="right" />
            <el-table-column prop="customs_match_status" label="匹配状态" width="110" />
            <el-table-column prop="export_date" label="出口日期" width="120" />
          </el-table>
          <pagination v-show="exportTotal > 0" :total="exportTotal" v-model:page="exportQuery.page" v-model:limit="exportQuery.page_size" @pagination="loadExports" />
        </el-card>
      </el-tab-pane>

      <el-tab-pane label="进货库存" name="purchase">
        <el-card shadow="never">
          <div class="table-toolbar">
            <el-button type="primary" icon="Search" @click="loadPurchase" v-hasPermi="['finance:exportTaxRefund:query']">刷新</el-button>
          </div>
          <el-table :data="purchase" border stripe v-loading="loading.purchase" height="520">
            <el-table-column prop="invoice_no" label="发票号" min-width="160" show-overflow-tooltip />
            <el-table-column prop="supplier_name" label="供应商" min-width="180" show-overflow-tooltip />
            <el-table-column prop="sku_normalized" label="SKU" min-width="140" show-overflow-tooltip />
            <el-table-column prop="product_name" label="商品名称" min-width="220" show-overflow-tooltip />
            <el-table-column prop="quantity" label="数量" width="100" align="right" />
            <el-table-column prop="remaining_quantity" label="剩余库存" width="110" align="right" />
            <el-table-column prop="unit_price" label="单价" width="110" align="right" />
            <el-table-column prop="invoice_date" label="发票日期" width="120" />
          </el-table>
          <pagination v-show="purchaseTotal > 0" :total="purchaseTotal" v-model:page="purchaseQuery.page" v-model:limit="purchaseQuery.page_size" @pagination="loadPurchase" />
        </el-card>
      </el-tab-pane>

      <el-tab-pane label="外汇应收" name="forex">
        <el-card shadow="never">
          <el-form :model="forexQuery" inline>
            <el-form-item label="报关单号">
              <el-input v-model="forexQuery.customs_no" clearable placeholder="报关单号" />
            </el-form-item>
            <el-form-item label="合同协议号">
              <el-input v-model="forexQuery.contract_no" clearable placeholder="合同协议号" />
            </el-form-item>
            <el-form-item>
              <el-button type="primary" icon="Search" @click="loadForex" v-hasPermi="['finance:exportTaxRefund:query']">查询</el-button>
            </el-form-item>
          </el-form>
          <el-table :data="forex" border stripe v-loading="loading.forex" height="520">
            <el-table-column prop="customs_no" label="报关单号" min-width="180" show-overflow-tooltip />
            <el-table-column prop="contract_no" label="合同协议号" min-width="150" show-overflow-tooltip />
            <el-table-column prop="business_entity" label="业务主体" min-width="160" show-overflow-tooltip />
            <el-table-column prop="receivable_amount" label="应收金额" width="120" align="right" />
            <el-table-column prop="currency" label="币种" width="80" />
            <el-table-column prop="source_type" label="来源" width="110" />
            <el-table-column prop="created_at" label="创建时间" width="170" />
          </el-table>
          <pagination v-show="forexTotal > 0" :total="forexTotal" v-model:page="forexQuery.page" v-model:limit="forexQuery.page_size" @pagination="loadForex" />
        </el-card>
      </el-tab-pane>
    </el-tabs>

    <el-dialog v-model="taskDialog.open" title="任务详情" width="760px">
      <el-descriptions :column="2" border>
        <el-descriptions-item label="任务ID">{{ taskDialog.row.id }}</el-descriptions-item>
        <el-descriptions-item label="状态">{{ taskDialog.row.task_status }}</el-descriptions-item>
        <el-descriptions-item label="任务类型">{{ taskTypeLabel(taskDialog.row.task_type) }}</el-descriptions-item>
        <el-descriptions-item label="创建人">{{ taskDialog.row.created_by }}</el-descriptions-item>
        <el-descriptions-item label="开始时间">{{ taskDialog.row.started_at }}</el-descriptions-item>
        <el-descriptions-item label="完成时间">{{ taskDialog.row.completed_at }}</el-descriptions-item>
      </el-descriptions>
      <el-alert v-if="taskDialog.row.error_message" class="mt12" type="error" :title="taskDialog.row.error_message" show-icon />
      <pre class="json-box">{{ pretty(taskDialog.row.result_payload || taskDialog.row.request_payload) }}</pre>
    </el-dialog>
  </div>
</template>

<script setup name="ExportTaxRefund">
import {
  generateRefundPackage,
  getTask,
  importCustomsDeclaration,
  importCustomsMaterial,
  importForex,
  importPurchaseInvoice,
  listExportDetails,
  listForexReceivables,
  listPurchaseInventory,
  listTasks
} from '@/api/finance/exportTaxRefund'

const { proxy } = getCurrentInstance()

const activeTab = ref('tasks')
const tasks = ref([])
const exports = ref([])
const purchase = ref([])
const forex = ref([])
const taskTotal = ref(0)
const exportTotal = ref(0)
const purchaseTotal = ref(0)
const forexTotal = ref(0)
const files = reactive({})
const polling = new Map()

const loading = reactive({
  tasks: false,
  exports: false,
  purchase: false,
  forex: false
})

const uploading = reactive({
  CUSTOMS_MATERIAL_IMPORT: false,
  CUSTOMS_DECLARATION_IMPORT: false,
  PURCHASE_INVOICE_IMPORT: false,
  FOREX_IMPORT: false,
  REFUND_PACKAGE_GENERATE: false
})

const customsForm = reactive({
  declarationMonth: '',
  declarationBatch: '',
  exportDate: ''
})

const generateForm = reactive({
  output_parent_dir: 'D:/JMH/退税输出',
  declaration_month: '',
  payer_name: 'Hong Kong Cammy Yeson Limited',
  overwrite: false
})

const taskQuery = reactive({
  page: 1,
  page_size: 20,
  task_type: '',
  task_status: ''
})

const exportQuery = reactive({
  page: 1,
  page_size: 50,
  contract_no: '',
  declaration_month: '',
  customs_match_status: ''
})

const purchaseQuery = reactive({ page: 1, page_size: 50 })
const forexQuery = reactive({ page: 1, page_size: 50, customs_no: '', contract_no: '' })

const taskDialog = reactive({
  open: false,
  row: {}
})

const taskTypes = [
  { label: '报关资料导入', value: 'CUSTOMS_MATERIAL_IMPORT' },
  { label: '出口报关单导入', value: 'CUSTOMS_DECLARATION_IMPORT' },
  { label: '进货发票导入', value: 'PURCHASE_INVOICE_IMPORT' },
  { label: '外汇数据导入', value: 'FOREX_IMPORT' },
  { label: '退税资料生成', value: 'REFUND_PACKAGE_GENERATE' }
]

const statuses = ['PENDING', 'RUNNING', 'SUCCESS', 'PARTIAL', 'FAILED']

const importCards = [
  { type: 'CUSTOMS_MATERIAL_IMPORT', title: '报关资料商品', ext: '.xlsx', accept: '.xlsx', tagType: 'success', desc: '导入历史报关资料Excel，按合同协议号保存当前有效版本。' },
  { type: 'CUSTOMS_DECLARATION_IMPORT', title: '出口报关单', ext: '.pdf', accept: '.pdf', tagType: 'danger', desc: '解析报关单PDF，并按合同协议号和项号匹配完整出口明细。' },
  { type: 'PURCHASE_INVOICE_IMPORT', title: '进货发票', ext: '.pdf', accept: '.pdf', tagType: 'warning', desc: '解析进货发票PDF，按发票号增量保存进货库存。' },
  { type: 'FOREX_IMPORT', title: '外汇数据', ext: '.xlsx', accept: '.xlsx', tagType: 'info', desc: '导入外汇回款汇总表，仅解析Sheet1并按报关单号增量保存。' }
]

const metrics = computed(() => {
  const running = tasks.value.filter(row => ['PENDING', 'RUNNING'].includes(row.task_status)).length
  const failed = tasks.value.filter(row => row.task_status === 'FAILED').length
  return [
    { label: '最近任务数', value: taskTotal.value || tasks.value.length, sub: 'Python API任务' },
    { label: '执行中', value: running, sub: 'PENDING / RUNNING' },
    { label: '出口明细', value: exportTotal.value, sub: 'export-details' },
    { label: '失败任务', value: failed, sub: '需要查看错误信息' }
  ]
})

const workflowActive = computed(() => {
  const successTypes = new Set(tasks.value.filter(row => ['SUCCESS', 'PARTIAL'].includes(row.task_status)).map(row => row.task_type))
  if (!successTypes.has('CUSTOMS_MATERIAL_IMPORT')) return 0
  if (!successTypes.has('CUSTOMS_DECLARATION_IMPORT')) return 1
  if (!successTypes.has('PURCHASE_INVOICE_IMPORT')) return 2
  if (!successTypes.has('FOREX_IMPORT')) return 3
  if (!successTypes.has('REFUND_PACKAGE_GENERATE')) return 4
  return 5
})

onMounted(() => loadAll())

onBeforeUnmount(() => {
  polling.forEach(timer => clearInterval(timer))
  polling.clear()
})

function loadAll() {
  loadTasks()
  loadExports()
  loadPurchase()
  loadForex()
}

function selectFile(type, file) {
  files[type] = file.raw
}

function removeFile(type) {
  delete files[type]
}

async function submitImport(type) {
  if (!files[type]) {
    proxy.$modal.msgWarning('请先选择文件')
    return
  }
  uploading[type] = true
  try {
    let res
    if (type === 'CUSTOMS_MATERIAL_IMPORT') {
      res = await importCustomsMaterial(files[type])
    } else if (type === 'CUSTOMS_DECLARATION_IMPORT') {
      res = await importCustomsDeclaration(files[type], {
        declarationMonth: customsForm.declarationMonth,
        declarationBatch: customsForm.declarationBatch,
        exportDate: customsForm.exportDate
      })
    } else if (type === 'PURCHASE_INVOICE_IMPORT') {
      res = await importPurchaseInvoice(files[type])
    } else if (type === 'FOREX_IMPORT') {
      res = await importForex(files[type])
    }
    afterTaskCreated(res)
  } finally {
    uploading[type] = false
  }
}

async function submitGenerate() {
  if (!generateForm.output_parent_dir) {
    proxy.$modal.msgWarning('请填写Python服务端输出父目录')
    return
  }
  uploading.REFUND_PACKAGE_GENERATE = true
  try {
    const res = await generateRefundPackage(generateForm)
    afterTaskCreated(res)
  } finally {
    uploading.REFUND_PACKAGE_GENERATE = false
  }
}

function afterTaskCreated(res) {
  const task = res?.data?.data
  if (!task?.id) {
    proxy.$modal.msgSuccess('任务已提交')
    loadTasks()
    return
  }
  proxy.$modal.msgSuccess(`任务已提交：#${task.id}`)
  startPolling(task.id)
  loadTasks()
}

function startPolling(taskId) {
  if (polling.has(taskId)) return
  const timer = setInterval(async () => {
    try {
      const res = await getTask(taskId)
      const task = res?.data?.data
      if (task && ['SUCCESS', 'PARTIAL', 'FAILED'].includes(task.task_status)) {
        clearInterval(timer)
        polling.delete(taskId)
        if (task.task_status === 'SUCCESS') proxy.$modal.msgSuccess(`任务 #${taskId} 执行成功`)
        if (task.task_status === 'PARTIAL') proxy.$modal.msgWarning(`任务 #${taskId} 部分成功`)
        if (task.task_status === 'FAILED') proxy.$modal.msgError(task.error_message || `任务 #${taskId} 执行失败`)
        loadAll()
      }
    } catch (e) {
      clearInterval(timer)
      polling.delete(taskId)
    }
  }, 2000)
  polling.set(taskId, timer)
}

async function loadTasks() {
  loading.tasks = true
  try {
    const res = await listTasks(cleanParams(taskQuery))
    tasks.value = res?.data?.data || []
    taskTotal.value = res?.data?.meta?.total || 0
  } finally {
    loading.tasks = false
  }
}

async function loadExports() {
  loading.exports = true
  try {
    const res = await listExportDetails(cleanParams(exportQuery))
    exports.value = res?.data?.data || []
    exportTotal.value = res?.data?.meta?.total || 0
  } finally {
    loading.exports = false
  }
}

async function loadPurchase() {
  loading.purchase = true
  try {
    const res = await listPurchaseInventory(purchaseQuery)
    purchase.value = res?.data?.data || []
    purchaseTotal.value = res?.data?.meta?.total || 0
  } finally {
    loading.purchase = false
  }
}

async function loadForex() {
  loading.forex = true
  try {
    const res = await listForexReceivables(cleanParams(forexQuery))
    forex.value = res?.data?.data || []
    forexTotal.value = res?.data?.meta?.total || 0
  } finally {
    loading.forex = false
  }
}

function resetTaskQuery() {
  taskQuery.page = 1
  taskQuery.page_size = 20
  taskQuery.task_type = ''
  taskQuery.task_status = ''
  loadTasks()
}

function showTask(row) {
  taskDialog.row = row || {}
  taskDialog.open = true
}

function progress(row) {
  const total = Number(row.progress_total || 0)
  const current = Number(row.progress_current || 0)
  if (!total) return ['SUCCESS', 'PARTIAL'].includes(row.task_status) ? 100 : 0
  return Math.min(100, Math.round((current / total) * 100))
}

function progressStatus(status) {
  if (status === 'SUCCESS') return 'success'
  if (status === 'FAILED') return 'exception'
  if (status === 'PARTIAL') return 'warning'
  return undefined
}

function statusType(status) {
  return {
    PENDING: 'info',
    RUNNING: 'warning',
    SUCCESS: 'success',
    PARTIAL: 'warning',
    FAILED: 'danger'
  }[status] || 'info'
}

function taskTypeLabel(type) {
  return taskTypes.find(item => item.value === type)?.label || type
}

function cleanParams(source) {
  const params = {}
  Object.keys(source).forEach(key => {
    if (source[key] !== undefined && source[key] !== null && source[key] !== '') {
      params[key] = source[key]
    }
  })
  return params
}

function pretty(value) {
  if (!value) return ''
  return JSON.stringify(value, null, 2)
}
</script>

<style scoped>
.tax-refund-page {
  background: #f6f8fb;
}

.metric-row,
.workflow-card,
.main-tabs,
.mt12 {
  margin-bottom: 12px;
}

.metric-card,
.import-card {
  background: #fff;
  border: 1px solid #e5e7eb;
  border-radius: 6px;
}

.metric-card {
  min-height: 100px;
  padding: 16px;
}

.metric-label {
  color: #64748b;
  font-size: 13px;
}

.metric-value {
  margin-top: 10px;
  color: #1f2937;
  font-size: 24px;
  font-weight: 700;
}

.metric-sub,
.import-desc {
  color: #909399;
  font-size: 12px;
}

.metric-sub {
  margin-top: 8px;
}

.card-head,
.table-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.import-card {
  min-height: 310px;
  margin-bottom: 12px;
}

.import-desc {
  min-height: 42px;
  line-height: 1.6;
  margin-bottom: 12px;
}

.mini-form {
  margin-top: 12px;
}

.full-btn {
  width: 100%;
  margin-top: 12px;
}

.generate-form {
  max-width: 100%;
}

.json-box {
  max-height: 360px;
  overflow: auto;
  margin-top: 12px;
  padding: 12px;
  color: #303133;
  background: #f8fafc;
  border: 1px solid #e5e7eb;
  border-radius: 6px;
  font-size: 12px;
}

@media (max-width: 768px) {
  .metric-card {
    margin-bottom: 12px;
  }
}
</style>
