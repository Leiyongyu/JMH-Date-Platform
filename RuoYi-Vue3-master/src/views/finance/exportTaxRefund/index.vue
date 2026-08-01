<template>
  <div class="app-container refund-page">
    <div class="page-head">
      <div>
        <div class="page-title">外汇退税工作台</div>
        <div class="page-subtitle">数据由 Date-Project 统一处理，ERP 负责导入、选择、生成和下载</div>
      </div>
      <div class="head-actions">
        <el-button v-hasPermi="['finance:exportTaxRefund:import']" type="primary" @click="openImport">
          <el-icon><Upload /></el-icon>导入数据
        </el-button>
        <el-button
          v-hasPermi="['finance:exportTaxRefund:generate']"
          type="success"
          :disabled="!selectedDeclarations.length"
          @click="openGenerate"
        >
          <el-icon><DocumentChecked /></el-icon>生成所选批次
        </el-button>
        <el-button
          v-hasPermi="['finance:exportTaxRefund:export']"
          :loading="downloadLoading"
          @click="handleDownload"
        >
          <el-icon><Download /></el-icon>下载最新资料包
        </el-button>
      </div>
    </div>

    <el-alert
      v-if="currentJob"
      class="job-alert"
      :type="jobAlertType"
      :closable="jobFinished"
      show-icon
      @close="currentJob = null"
    >
      <template #title>
        报关资料导入：{{ jobStatusText(currentJob.status) }}
        <span v-if="currentJob.processed_files !== undefined">
          （{{ currentJob.processed_files }}/{{ currentJob.total_files || 0 }}）
        </span>
      </template>
      <div v-if="currentJob.message">{{ currentJob.message }}</div>
      <div v-if="currentJob.error">{{ currentJob.error }}</div>
    </el-alert>

    <el-row :gutter="14" class="summary-row">
      <el-col :xs="12" :sm="6">
        <div class="summary-card">
          <span>报关单总数</span><strong>{{ declarationStats.total }}</strong>
        </div>
      </el-col>
      <el-col :xs="12" :sm="6">
        <div class="summary-card ready">
          <span>可生成</span><strong>{{ declarationStats.ready }}</strong>
        </div>
      </el-col>
      <el-col :xs="12" :sm="6">
        <div class="summary-card done">
          <span>已生成</span><strong>{{ declarationStats.generated }}</strong>
        </div>
      </el-col>
      <el-col :xs="12" :sm="6">
        <div class="summary-card selected">
          <span>本次已选</span><strong>{{ selectedDeclarations.length }}</strong>
        </div>
      </el-col>
    </el-row>

    <el-card shadow="never" class="main-card">
      <el-tabs v-model="activeTab" @tab-change="handleTabChange">
        <el-tab-pane label="申报工作台" name="declarations">
          <el-form :inline="true" class="toolbar" @submit.prevent>
            <el-form-item label="关键词">
              <el-input
                v-model="declarationQuery.keyword"
                clearable
                placeholder="报关单号 / 合同号 / 发票号"
                @keyup.enter="declarationPage = 1"
              />
            </el-form-item>
            <el-form-item label="状态">
              <el-select v-model="declarationQuery.status" style="width: 130px" @change="declarationPage = 1">
                <el-option label="全部" value="all" />
                <el-option label="可生成" value="ready" />
                <el-option label="已生成" value="generated" />
                <el-option label="待完善" value="blocked" />
              </el-select>
            </el-form-item>
            <el-form-item>
              <el-button :loading="declarationLoading" @click="loadDeclarations">
                <el-icon><Refresh /></el-icon>刷新
              </el-button>
            </el-form-item>
          </el-form>

          <el-table
            ref="declarationTableRef"
            v-loading="declarationLoading"
            :data="pagedDeclarations"
            row-key="customs_declaration_no"
            @selection-change="handleSelectionChange"
          >
            <el-table-column type="selection" width="48" reserve-selection :selectable="canSelect" />
            <el-table-column label="报关单号" prop="customs_declaration_no" min-width="180" fixed="left" />
            <el-table-column label="合同号" prop="contract_no" min-width="135" show-overflow-tooltip />
            <el-table-column label="出口日期" prop="export_date" width="115" />
            <el-table-column label="发票号" prop="invoice_no" min-width="145" show-overflow-tooltip />
            <el-table-column label="明细数" prop="item_count" width="85" align="right" />
            <el-table-column label="单证金额(USD)" min-width="130" align="right">
              <template #default="{ row }">{{ money(row.document_total_usd) }}</template>
            </el-table-column>
            <el-table-column label="匹配状态" width="110">
              <template #default="{ row }">
                <el-tag :type="matchTagType(row)" effect="plain">{{ matchText(row) }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column label="生成状态" width="105">
              <template #default="{ row }">
                <el-tag v-if="isGenerated(row)" type="success">已生成</el-tag>
                <el-tag v-else-if="canSelect(row)" type="primary">可生成</el-tag>
                <el-tag v-else type="warning">待完善</el-tag>
              </template>
            </el-table-column>
          </el-table>
          <pagination
            v-show="filteredDeclarations.length > 0"
            :total="filteredDeclarations.length"
            v-model:page="declarationPage"
            v-model:limit="declarationPageSize"
          />
        </el-tab-pane>

        <el-tab-pane label="发票库存" name="inventory">
          <el-form :inline="true" class="toolbar" @submit.prevent>
            <el-form-item label="关键词">
              <el-input
                v-model="inventoryQuery.keyword"
                clearable
                placeholder="发票号 / SKU / 品名 / 销方"
                @keyup.enter="searchInventory"
              />
            </el-form-item>
            <el-form-item>
              <el-checkbox v-model="inventoryQuery.availableOnly" @change="searchInventory">仅看有余量</el-checkbox>
            </el-form-item>
            <el-form-item>
              <el-button type="primary" @click="searchInventory">查询</el-button>
              <el-button @click="resetInventory">重置</el-button>
            </el-form-item>
          </el-form>
          <el-table v-loading="inventoryLoading" :data="inventoryRows">
            <el-table-column label="发票号码" prop="invoice_no" min-width="155" fixed="left" />
            <el-table-column label="开票日期" prop="invoice_date" width="115" />
            <el-table-column label="销售方" prop="seller_name" min-width="190" show-overflow-tooltip />
            <el-table-column label="税号" prop="seller_tax_no" min-width="180" show-overflow-tooltip />
            <el-table-column label="SKU" prop="normalized_sku" min-width="130" />
            <el-table-column label="项目名称" prop="project_name" min-width="180" show-overflow-tooltip />
            <el-table-column label="规格" prop="specification" min-width="130" show-overflow-tooltip />
            <el-table-column label="单位" prop="unit" width="70" />
            <el-table-column label="原始数量" prop="original_quantity" width="105" align="right" />
            <el-table-column label="可用数量" prop="available_quantity" width="105" align="right" />
            <el-table-column label="单价" width="105" align="right">
              <template #default="{ row }">{{ money(row.unit_price) }}</template>
            </el-table-column>
            <el-table-column label="可用金额" width="115" align="right">
              <template #default="{ row }">{{ money(row.available_amount) }}</template>
            </el-table-column>
            <el-table-column label="税率" width="85" align="right">
              <template #default="{ row }">{{ percent(row.tax_rate) }}</template>
            </el-table-column>
          </el-table>
          <pagination
            v-show="inventoryTotal > 0"
            :total="inventoryTotal"
            v-model:page="inventoryQuery.page"
            v-model:limit="inventoryQuery.pageSize"
            @pagination="loadInventory"
          />
        </el-tab-pane>
      </el-tabs>
    </el-card>

    <el-dialog v-model="importDialog.visible" title="导入外汇退税数据" width="620px" append-to-body>
      <el-alert
        title="文件会直接提交给 Date-Project；报关资料支持一次选择多个 Excel 文件。"
        type="info"
        :closable="false"
        show-icon
        class="dialog-alert"
      />
      <el-form label-width="110px">
        <el-form-item label="导入类型">
          <el-radio-group v-model="importDialog.type" @change="clearUpload">
            <el-radio-button value="customs">报关资料</el-radio-button>
            <el-radio-button value="purchase">进项发票汇总</el-radio-button>
            <el-radio-button value="forex">外汇收汇明细</el-radio-button>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="Excel 文件">
          <el-upload
            ref="uploadRef"
            drag
            action="#"
            accept=".xlsx,.xlsm"
            :auto-upload="false"
            :multiple="importDialog.type === 'customs'"
            :limit="importDialog.type === 'customs' ? 100 : 1"
            :on-change="handleFileChange"
            :on-remove="handleFileRemove"
          >
            <el-icon class="el-icon--upload"><UploadFilled /></el-icon>
            <div class="el-upload__text">拖入文件，或<em>点击选择</em></div>
            <template #tip>
              <div class="el-upload__tip">{{ importTip }}</div>
            </template>
          </el-upload>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="importDialog.visible = false">取消</el-button>
        <el-button type="primary" :loading="importDialog.loading" @click="submitImport">开始导入</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="generateDialog.visible" title="生成退税申报批次" width="520px" append-to-body>
      <el-alert
        :title="`本次将处理 ${selectedDeclarations.length} 张报关单，并生成最新资料包。`"
        type="success"
        :closable="false"
        show-icon
        class="dialog-alert"
      />
      <el-form label-width="110px">
        <el-form-item label="申报月份" required>
          <el-input v-model.trim="generateDialog.month" maxlength="6" placeholder="例如 202607" />
        </el-form-item>
        <el-form-item label="申报批次" required>
          <el-input v-model.trim="generateDialog.batch" maxlength="40" placeholder="例如 202607-01" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="generateDialog.visible = false">取消</el-button>
        <el-button type="primary" :loading="generateDialog.loading" @click="submitGenerate">
          生成批次和资料包
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, getCurrentInstance, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import {
  createDeclarationBatch,
  downloadLatestPackage,
  generateFinalPackage,
  getImportJob,
  importCustomsFolder,
  importForeignExchangeReceipts,
  importPurchaseInvoiceSummary,
  listCustomsDeclarations,
  listPurchaseInventory
} from '@/api/finance/exportTaxRefund'

const { proxy } = getCurrentInstance()
const activeTab = ref('declarations')
const declarationLoading = ref(false)
const declarations = ref([])
const selectedDeclarations = ref([])
const declarationTableRef = ref()
const declarationPage = ref(1)
const declarationPageSize = ref(10)
const declarationQuery = reactive({ keyword: '', status: 'all' })

const inventoryLoading = ref(false)
const inventoryRows = ref([])
const inventoryTotal = ref(0)
const inventoryLoaded = ref(false)
const inventoryQuery = reactive({ page: 1, pageSize: 10, keyword: '', availableOnly: true })

const uploadRef = ref()
const importDialog = reactive({ visible: false, loading: false, type: 'customs', files: [] })
const generateDialog = reactive({ visible: false, loading: false, month: '', batch: '' })
const currentJob = ref(null)
const pollTimer = ref(null)
const downloadLoading = ref(false)

const filteredDeclarations = computed(() => {
  const keyword = declarationQuery.keyword.trim().toLowerCase()
  return declarations.value.filter(row => {
    const text = [row.customs_declaration_no, row.contract_no, row.invoice_no]
      .filter(Boolean).join(' ').toLowerCase()
    if (keyword && !text.includes(keyword)) return false
    if (declarationQuery.status === 'ready') return canSelect(row)
    if (declarationQuery.status === 'generated') return isGenerated(row)
    if (declarationQuery.status === 'blocked') return !canSelect(row) && !isGenerated(row)
    return true
  })
})

const pagedDeclarations = computed(() => {
  const start = (declarationPage.value - 1) * declarationPageSize.value
  return filteredDeclarations.value.slice(start, start + declarationPageSize.value)
})

const declarationStats = computed(() => ({
  total: declarations.value.length,
  ready: declarations.value.filter(canSelect).length,
  generated: declarations.value.filter(isGenerated).length
}))

const importTip = computed(() => {
  if (importDialog.type === 'customs') return '请选择报关资料文件夹中的全部 .xlsx/.xlsm 文件'
  if (importDialog.type === 'purchase') return '请选择一份进项发票汇总表'
  return '请选择一份外汇收汇明细表'
})

const jobFinished = computed(() =>
  ['completed', 'completed_with_errors', 'failed'].includes(currentJob.value?.status)
)
const jobAlertType = computed(() => {
  if (!currentJob.value || !jobFinished.value) return 'info'
  return currentJob.value.status === 'completed' ? 'success' : currentJob.value.status === 'failed' ? 'error' : 'warning'
})

function responseData(res) {
  return res?.data ?? res ?? {}
}

function rowsFrom(data) {
  if (Array.isArray(data)) return data
  return data.items || data.rows || data.list || []
}

function canSelect(row) {
  return Boolean(row.selectable) && !isGenerated(row)
}

function isGenerated(row) {
  return Number(row.generated_count || 0) > 0 || row.generated === true
}

function matchText(row) {
  const status = String(row.customs_match_status || row.match_status || '').toLowerCase()
  if (status === 'matched' || status === 'success') return '已匹配'
  if (status === 'partial' || status === 'partially_matched') return '部分匹配'
  if (status === 'unmatched' || status === 'missing') return '未匹配'
  return canSelect(row) ? '已就绪' : (status || '待完善')
}

function matchTagType(row) {
  const text = matchText(row)
  if (text === '已匹配' || text === '已就绪') return 'success'
  if (text === '部分匹配') return 'warning'
  return 'danger'
}

function money(value) {
  const number = Number(value)
  return Number.isFinite(number) ? number.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : '-'
}

function percent(value) {
  const number = Number(value)
  if (!Number.isFinite(number)) return '-'
  return `${number > 1 ? number : number * 100}%`
}

function jobStatusText(status) {
  return {
    pending: '等待处理',
    processing: '处理中',
    completed: '导入完成',
    completed_with_errors: '完成，但部分文件失败',
    failed: '导入失败'
  }[status] || status || '等待处理'
}

async function loadDeclarations() {
  declarationLoading.value = true
  try {
    const data = responseData(await listCustomsDeclarations())
    declarations.value = rowsFrom(data)
    declarationPage.value = 1
  } finally {
    declarationLoading.value = false
  }
}

function handleSelectionChange(rows) {
  selectedDeclarations.value = rows
}

function handleTabChange(name) {
  if (name === 'inventory' && !inventoryLoaded.value) loadInventory()
}

async function loadInventory() {
  inventoryLoading.value = true
  try {
    const data = responseData(await listPurchaseInventory({
      page: inventoryQuery.page,
      page_size: inventoryQuery.pageSize,
      keyword: inventoryQuery.keyword || undefined,
      available_only: inventoryQuery.availableOnly
    }))
    inventoryRows.value = rowsFrom(data)
    inventoryTotal.value = Number(data.total || data.total_count || inventoryRows.value.length)
    inventoryLoaded.value = true
  } finally {
    inventoryLoading.value = false
  }
}

function searchInventory() {
  inventoryQuery.page = 1
  loadInventory()
}

function resetInventory() {
  inventoryQuery.page = 1
  inventoryQuery.keyword = ''
  inventoryQuery.availableOnly = true
  loadInventory()
}

function openImport() {
  importDialog.visible = true
  importDialog.type = 'customs'
  clearUpload()
}

function clearUpload() {
  importDialog.files = []
  uploadRef.value?.clearFiles()
}

function handleFileChange(_file, files) {
  importDialog.files = files.map(item => item.raw).filter(Boolean)
}

function handleFileRemove(_file, files) {
  importDialog.files = files.map(item => item.raw).filter(Boolean)
}

async function submitImport() {
  if (!importDialog.files.length) {
    proxy.$modal.msgWarning('请先选择需要导入的 Excel 文件')
    return
  }
  if (importDialog.type !== 'customs' && importDialog.files.length !== 1) {
    proxy.$modal.msgWarning('该类型每次只能导入一个文件')
    return
  }
  importDialog.loading = true
  try {
    let res
    if (importDialog.type === 'customs') {
      res = await importCustomsFolder(importDialog.files)
      const job = responseData(res)
      currentJob.value = job
      importDialog.visible = false
      startPolling(job.job_id || job.id)
      proxy.$modal.msgSuccess('文件已提交，正在后台导入')
    } else if (importDialog.type === 'purchase') {
      res = await importPurchaseInvoiceSummary(importDialog.files[0])
      proxy.$modal.msgSuccess(responseData(res).message || '进项发票汇总导入完成')
      importDialog.visible = false
      inventoryLoaded.value = false
      await loadDeclarations()
    } else {
      res = await importForeignExchangeReceipts(importDialog.files[0])
      proxy.$modal.msgSuccess(responseData(res).message || '外汇收汇明细导入完成')
      importDialog.visible = false
      await loadDeclarations()
    }
  } finally {
    importDialog.loading = false
  }
}

function startPolling(jobId) {
  stopPolling()
  if (!jobId) return
  const poll = async () => {
    try {
      currentJob.value = responseData(await getImportJob(jobId))
      if (jobFinished.value) {
        stopPolling()
        await loadDeclarations()
        inventoryLoaded.value = false
      }
    } catch (_error) {
      stopPolling()
    }
  }
  poll()
  pollTimer.value = window.setInterval(poll, 1500)
}

function stopPolling() {
  if (pollTimer.value) window.clearInterval(pollTimer.value)
  pollTimer.value = null
}

function openGenerate() {
  const now = new Date()
  const month = `${now.getFullYear()}${String(now.getMonth() + 1).padStart(2, '0')}`
  generateDialog.month = month
  generateDialog.batch = '001'
  generateDialog.visible = true
}

async function submitGenerate() {
  if (!/^\d{6}$/.test(generateDialog.month)) {
    proxy.$modal.msgWarning('申报月份需填写 6 位年月，例如 202607')
    return
  }
  if (!generateDialog.batch) {
    proxy.$modal.msgWarning('请填写申报批次')
    return
  }
  generateDialog.loading = true
  try {
    const numbers = selectedDeclarations.value.map(row => row.customs_declaration_no).filter(Boolean)
    const conversion = responseData(await createDeclarationBatch({
      customs_declaration_numbers: numbers,
      declaration_month: generateDialog.month,
      declaration_batch: generateDialog.batch
    }))
    const packageResult = responseData(await generateFinalPackage({
      errors: conversion.errors || []
    }))
    const errorCount = Number(conversion.error_count || conversion.errors?.length || 0)
    proxy.$modal.msgSuccess(
      `批次生成完成：成功 ${conversion.successful_customs_declaration_count ?? numbers.length} 张，失败 ${errorCount} 张`
    )
    if (packageResult.message) console.info(packageResult.message)
    generateDialog.visible = false
    declarationTableRef.value?.clearSelection()
    selectedDeclarations.value = []
    await loadDeclarations()
    inventoryLoaded.value = false
  } finally {
    generateDialog.loading = false
  }
}

async function handleDownload() {
  downloadLoading.value = true
  try {
    const data = await downloadLatestPackage()
    const blob = data instanceof Blob ? data : new Blob([data], { type: 'application/zip' })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = `外汇退税资料包_${new Date().getTime()}.zip`
    document.body.appendChild(link)
    link.click()
    link.remove()
    URL.revokeObjectURL(url)
  } finally {
    downloadLoading.value = false
  }
}

onMounted(loadDeclarations)
onBeforeUnmount(stopPolling)
</script>

<style scoped lang="scss">
.refund-page {
  background: #f5f7fa;
  min-height: calc(100vh - 84px);
}

.page-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 20px;
  padding: 20px 22px;
  margin-bottom: 14px;
  color: #fff;
  border-radius: 10px;
  background: linear-gradient(125deg, #1d4ed8, #0f766e);
}

.page-title { font-size: 24px; font-weight: 700; }
.page-subtitle { margin-top: 7px; color: rgba(255, 255, 255, .82); }
.head-actions { display: flex; flex-wrap: wrap; justify-content: flex-end; gap: 8px; }
.job-alert { margin-bottom: 14px; }
.summary-row { margin-bottom: 14px; }

.summary-card {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 18px 20px;
  background: #fff;
  border-radius: 9px;
  border-left: 4px solid #64748b;
  box-shadow: 0 1px 3px rgba(15, 23, 42, .06);
}
.summary-card span { color: #64748b; }
.summary-card strong { font-size: 27px; color: #0f172a; }
.summary-card.ready { border-left-color: #2563eb; }
.summary-card.done { border-left-color: #16a34a; }
.summary-card.selected { border-left-color: #f59e0b; }
.main-card { border: none; }
.toolbar { padding-top: 4px; }
.dialog-alert { margin-bottom: 20px; }

:deep(.el-upload), :deep(.el-upload-dragger) { width: 100%; }

@media (max-width: 900px) {
  .page-head { align-items: flex-start; flex-direction: column; }
  .head-actions { justify-content: flex-start; }
}
</style>
