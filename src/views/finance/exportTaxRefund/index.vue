<template>
  <div class="app-container tax-refund-page">
    <section class="tax-header">
      <div>
        <div class="tax-title">外汇退税工作台</div>
        <div class="tax-subtitle">数据导入、任务跟踪、三表查询和退税资料生成</div>
      </div>
      <div class="header-actions">
        <el-button type="primary" icon="Upload" @click="importDialog.open = true">
          数据导入
        </el-button>
        <el-button icon="Clock" @click="taskStatusDialog.open = true">
          当前任务
        </el-button>
        <el-button icon="Tickets" @click="openRecentTasks">
          最近任务
        </el-button>
        <el-button
          type="success"
          icon="Finished"
          class="export-refund-btn"
          :loading="uploading.REFUND_PACKAGE_GENERATE"
          @click="openGenerateDialog(false)"
        >
          导出外汇退税资料
        </el-button>
        <el-button icon="Refresh" @click="loadAll" :loading="loading.tasks">刷新数据</el-button>
      </div>
    </section>

    <div class="workspace">
      <main class="main-panel">
        <el-tabs v-model="activeTab" class="data-tabs" @tab-change="handleTabChange">
          <el-tab-pane label="出口明细" name="exports">
            <el-card shadow="never" class="data-card">
              <el-form :model="exportQuery" inline class="query-form">
                <el-form-item label="报关单号">
                  <el-input v-model="exportQuery.customs_declaration_no" clearable placeholder="18位前缀匹配" />
                </el-form-item>
                <el-form-item label="合同协议号">
                  <el-input v-model="exportQuery.contract_no" clearable placeholder="FBA15L7CCK57" />
                </el-form-item>
                <el-form-item label="申报月份">
                  <el-input v-model="exportQuery.declaration_month" clearable placeholder="202601" maxlength="6" />
                </el-form-item>
                <el-form-item label="申报批次">
                  <el-input v-model="exportQuery.declaration_batch" clearable placeholder="001" maxlength="3" />
                </el-form-item>
                <el-form-item label="关联号">
                  <el-input v-model="exportQuery.relation_no" clearable placeholder="关联号" />
                </el-form-item>
                <el-form-item label="匹配状态">
                  <el-select v-model="exportQuery.customs_match_status" clearable placeholder="全部" style="width: 120px">
                    <el-option label="已匹配" value="MATCHED" />
                    <el-option label="未匹配" value="UNMATCHED" />
                  </el-select>
                </el-form-item>
                <el-form-item>
                  <el-button type="primary" icon="Search" @click="loadExports" v-hasPermi="['finance:exportTaxRefund:query']">查询</el-button>
                  <el-button icon="Refresh" @click="resetExportQuery">重置</el-button>
                </el-form-item>
              </el-form>

              <div class="table-actions">
                <div class="table-stat">共 {{ exportTotal }} 条，已选 {{ selectedExportIds.length }} 条</div>
                <el-button
                  type="success"
                  plain
                  icon="Finished"
                  :disabled="!selectedExportIds.length"
                  @click="generateSelectedExports"
                  v-hasPermi="['finance:exportTaxRefund:generate']"
                >
                  按选中明细生成
                </el-button>
              </div>

              <el-table
                class="refund-table"
                :fit="false"
                :data="exports"
                border
                stripe
                v-loading="loading.exports"
                height="640"
                row-key="id"
                @selection-change="handleExportSelection"
              >
                <el-table-column type="selection" width="44" />
                <el-table-column prop="customs_declaration_no" label="报关单号" width="150" show-overflow-tooltip />
                <el-table-column prop="contract_no" label="合同协议号" width="120" show-overflow-tooltip />
                <el-table-column prop="customs_item_no" label="项号" width="64" />
                <el-table-column prop="sequence_no" label="序号" width="70" />
                <el-table-column prop="sku_normalized" label="SKU" width="118" show-overflow-tooltip />
                <el-table-column prop="export_product_name" label="商品名称" width="170" show-overflow-tooltip />
                <el-table-column label="数量" width="88" align="right">
                  <template #default="{ row }">{{ displayValue(row.export_quantity, row.quantity) }}</template>
                </el-table-column>
                <el-table-column prop="unit" label="单位" width="60" />
                <el-table-column label="FOB金额" width="108" align="right">
                  <template #default="{ row }">{{ money(displayValue(row.fob_amount, row.total_amount)) }}</template>
                </el-table-column>
                <el-table-column prop="export_date" label="出口日期" width="104" />
                <el-table-column prop="customs_match_status" label="匹配" width="88">
                  <template #default="{ row }"><el-tag :type="matchStatusType(row.customs_match_status)">{{ row.customs_match_status || '-' }}</el-tag></template>
                </el-table-column>
                <el-table-column prop="declaration_month" label="申报月份" width="88" />
                <el-table-column prop="declaration_batch" label="批次" width="68" />
                <el-table-column prop="relation_no" label="关联号" width="130" show-overflow-tooltip />
              </el-table>
              <pagination v-show="exportTotal > 0" :total="exportTotal" v-model:page="exportQuery.page" v-model:limit="exportQuery.page_size" @pagination="loadExports" />
            </el-card>
          </el-tab-pane>

          <el-tab-pane label="进货库存" name="purchase">
            <el-card shadow="never" class="data-card">
              <el-form :model="purchaseQuery" inline class="query-form">
                <el-form-item label="发票号"><el-input v-model="purchaseQuery.invoice_no" clearable placeholder="发票号" /></el-form-item>
                <el-form-item label="开票起"><el-date-picker v-model="purchaseQuery.invoice_date_from" type="date" value-format="YYYY-MM-DD" clearable /></el-form-item>
                <el-form-item label="开票止"><el-date-picker v-model="purchaseQuery.invoice_date_to" type="date" value-format="YYYY-MM-DD" clearable /></el-form-item>
                <el-form-item label="销售方税号"><el-input v-model="purchaseQuery.supplier_tax_no" clearable placeholder="纳税号" /></el-form-item>
                <el-form-item label="购买方税号"><el-input v-model="purchaseQuery.buyer_tax_no" clearable placeholder="纳税号" /></el-form-item>
                <el-form-item label="SKU"><el-input v-model="purchaseQuery.sku_normalized" clearable placeholder="SKU" /></el-form-item>
                <el-form-item label="状态">
                  <el-select v-model="purchaseQuery.inventory_status" clearable placeholder="全部" style="width: 120px">
                    <el-option label="可用" value="AVAILABLE" />
                    <el-option label="部分" value="PARTIAL" />
                    <el-option label="用完" value="EXHAUSTED" />
                  </el-select>
                </el-form-item>
                <el-form-item>
                  <el-button type="primary" icon="Search" @click="loadPurchase" v-hasPermi="['finance:exportTaxRefund:query']">查询</el-button>
                  <el-button icon="Refresh" @click="resetPurchaseQuery">重置</el-button>
                </el-form-item>
              </el-form>

              <div class="table-stat">共 {{ purchaseTotal }} 条</div>
              <el-table class="refund-table" :fit="false" :data="purchase" border stripe v-loading="loading.purchase" height="640">
                <el-table-column prop="invoice_no" label="发票号" width="138" show-overflow-tooltip />
                <el-table-column prop="invoice_date" label="发票日期" width="104" />
                <el-table-column prop="invoice_item_no" label="项号" width="64" />
                <el-table-column prop="sequence_no" label="序号" width="70" />
                <el-table-column prop="sku_normalized" label="SKU" width="118" show-overflow-tooltip />
                <el-table-column prop="product_name" label="商品名称" width="170" show-overflow-tooltip />
                <el-table-column prop="supplier_name" label="供应商" width="135" show-overflow-tooltip />
                <el-table-column prop="supplier_tax_no" label="供方税号" width="148" show-overflow-tooltip />
                <el-table-column label="采购数量" width="88" align="right">
                  <template #default="{ row }">{{ displayValue(row.purchased_quantity, row.quantity) }}</template>
                </el-table-column>
                <el-table-column prop="unit" label="单位" width="60" />
                <el-table-column prop="remaining_quantity" label="剩余" width="80" align="right" />
                <el-table-column label="单价" width="92" align="right">
                  <template #default="{ row }">{{ money(row.unit_price) }}</template>
                </el-table-column>
                <el-table-column label="不含税金额" width="108" align="right">
                  <template #default="{ row }">{{ money(row.taxable_amount) }}</template>
                </el-table-column>
                <el-table-column prop="tax_rate" label="税率" width="70" align="right" />
                <el-table-column label="税额" width="92" align="right">
                  <template #default="{ row }">{{ money(row.tax_amount) }}</template>
                </el-table-column>
                <el-table-column prop="declaration_month" label="申报月份" width="88" />
                <el-table-column prop="declaration_batch" label="批次" width="68" />
                <el-table-column prop="relation_no" label="关联号" width="130" show-overflow-tooltip />
                <el-table-column prop="inventory_status" label="状态" width="88">
                  <template #default="{ row }"><el-tag :type="inventoryStatusType(row.inventory_status)">{{ row.inventory_status || '-' }}</el-tag></template>
                </el-table-column>
              </el-table>
              <pagination v-show="purchaseTotal > 0" :total="purchaseTotal" v-model:page="purchaseQuery.page" v-model:limit="purchaseQuery.page_size" @pagination="loadPurchase" />
            </el-card>
          </el-tab-pane>

          <el-tab-pane label="外汇应收" name="forex">
            <el-card shadow="never" class="data-card">
              <el-form :model="forexQuery" inline class="query-form">
                <el-form-item label="报关单号"><el-input v-model="forexQuery.customs_no" clearable placeholder="18位报关单号" /></el-form-item>
                <el-form-item label="合同协议号"><el-input v-model="forexQuery.contract_no" clearable placeholder="合同协议号" /></el-form-item>
                <el-form-item label="业务主体"><el-input v-model="forexQuery.business_entity" clearable placeholder="业务主体" /></el-form-item>
                <el-form-item label="来源类型"><el-input v-model="forexQuery.source_type" clearable placeholder="来源类型" /></el-form-item>
                <el-form-item label="出口起"><el-date-picker v-model="forexQuery.export_date_from" type="date" value-format="YYYY-MM-DD" clearable /></el-form-item>
                <el-form-item label="出口止"><el-date-picker v-model="forexQuery.export_date_to" type="date" value-format="YYYY-MM-DD" clearable /></el-form-item>
                <el-form-item>
                  <el-button type="primary" icon="Search" @click="loadForex" v-hasPermi="['finance:exportTaxRefund:query']">查询</el-button>
                  <el-button icon="Refresh" @click="resetForexQuery">重置</el-button>
                </el-form-item>
              </el-form>

              <div class="table-stat">共 {{ forexTotal }} 条</div>
              <el-table class="refund-table" :fit="false" :data="forex" border stripe v-loading="loading.forex" height="640">
                <el-table-column prop="id" label="ID" width="64" />
                <el-table-column prop="customs_declaration_no" label="报关单号" width="150" show-overflow-tooltip />
                <el-table-column prop="contract_no" label="合同协议号" width="120" show-overflow-tooltip />
                <el-table-column prop="business_entity" label="业务主体" width="140" show-overflow-tooltip />
                <el-table-column prop="export_date" label="出口日期" width="104" />
                <el-table-column prop="export_amount_usd" label="出口金额USD" width="118" align="right" />
                <el-table-column prop="received_amount_usd" label="已收汇USD" width="118" align="right" />
                <el-table-column prop="monthly_exchange_rate" label="汇率" width="82" align="right" />
                <el-table-column prop="source_type" label="来源" width="90" />
                <el-table-column prop="created_at" label="创建时间" width="150" />
              </el-table>
              <pagination v-show="forexTotal > 0" :total="forexTotal" v-model:page="forexQuery.page" v-model:limit="forexQuery.page_size" @pagination="loadForex" />
            </el-card>
          </el-tab-pane>

          <el-tab-pane label="任务历史" name="history">
            <el-card shadow="never" class="data-card">
              <el-form :model="taskQuery" inline class="query-form">
                <el-form-item label="任务类型">
                  <el-select v-model="taskQuery.task_type" clearable placeholder="全部" style="width: 220px">
                    <el-option v-for="item in allTaskTypes" :key="item.value" :label="item.label" :value="item.value" />
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
              <el-table class="refund-table" :fit="false" :data="tasks" border stripe v-loading="loading.tasks" height="640">
                <el-table-column prop="id" label="ID" width="64" />
                <el-table-column prop="task_type" label="任务类型" width="170">
                  <template #default="{ row }">{{ taskTypeLabel(row.task_type) }}</template>
                </el-table-column>
                <el-table-column prop="task_status" label="状态" width="100">
                  <template #default="{ row }"><el-tag :type="statusType(row.task_status)">{{ row.task_status }}</el-tag></template>
                </el-table-column>
                <el-table-column label="进度" width="160">
                  <template #default="{ row }"><el-progress :percentage="progress(row)" :status="progressStatus(row.task_status)" /></template>
                </el-table-column>
                <el-table-column prop="original_file_name" label="文件名" width="170" show-overflow-tooltip />
                <el-table-column label="结果" width="190" show-overflow-tooltip>
                  <template #default="{ row }">{{ payloadSummary(row.result_payload) }}</template>
                </el-table-column>
                <el-table-column prop="error_message" label="错误信息" width="190" show-overflow-tooltip />
                <el-table-column prop="created_by" label="创建人" width="96" />
                <el-table-column prop="created_at" label="创建时间" width="150" />
                <el-table-column label="操作" width="90" fixed="right">
                  <template #default="{ row }"><el-button link type="primary" @click="showTask(row)">详情</el-button></template>
                </el-table-column>
              </el-table>
              <pagination v-show="taskTotal > 0" :total="taskTotal" v-model:page="taskQuery.page" v-model:limit="taskQuery.page_size" @pagination="loadTasks" />
            </el-card>
          </el-tab-pane>
        </el-tabs>
      </main>
    </div>

    <el-dialog v-model="importDialog.open" title="数据导入" width="560px">
      <el-form label-position="top" class="dialog-import-form">
        <el-form-item label="任务类型">
          <el-select v-model="taskForm.type" class="full" @change="resetUploadFile">
            <el-option v-for="item in taskTypes" :key="item.value" :label="item.label" :value="item.value" />
          </el-select>
        </el-form-item>

        <el-form-item label="选择文件">
          <el-upload
            ref="uploadRef"
            :auto-upload="false"
            multiple
            :limit="20"
            :accept="currentTask.accept"
            :on-change="selectUploadFile"
            :on-remove="removeUploadFile"
          >
            <el-button icon="Upload">选择{{ currentTask.ext }}文件</el-button>
            <template #tip>
              <div class="upload-tip">{{ currentTask.hint }}，可一次选择多个文件</div>
            </template>
          </el-upload>
        </el-form-item>

        <template v-if="taskForm.type === 'CUSTOMS_DECLARATION_IMPORT'">
          <el-form-item label="申报年月">
            <el-input v-model="customsForm.declarationMonth" placeholder="202601，可为空" maxlength="6" clearable />
          </el-form-item>
          <el-form-item label="申报批次">
            <el-input v-model="customsForm.declarationBatch" placeholder="001，可为空" maxlength="3" clearable />
          </el-form-item>
          <el-form-item label="出口日期">
            <el-date-picker v-model="customsForm.exportDate" type="date" value-format="YYYY-MM-DD" placeholder="可为空" clearable class="full" />
          </el-form-item>
        </template>
      </el-form>
      <template #footer>
        <el-button @click="importDialog.open = false">取消</el-button>
        <el-button
          type="primary"
          icon="UploadFilled"
          :loading="currentSubmitting"
          @click="submitCurrentTask"
          :disabled="!uploadFiles.length"
        >
          上传并创建任务<span v-if="uploadFiles.length">（{{ uploadFiles.length }}个）</span>
        </el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="taskStatusDialog.open" title="当前任务" width="560px">
      <template #header>
        <div class="dialog-head">
          <span>当前任务</span>
          <el-button link type="primary" @click="loadTasks">刷新</el-button>
        </div>
      </template>
      <div v-if="currentTaskStatus.id" class="task-current">
        <div class="task-line"><span>ID</span><b>#{{ currentTaskStatus.id }}</b></div>
        <div class="task-line"><span>类型</span><b>{{ taskTypeLabel(currentTaskStatus.task_type) }}</b></div>
        <div class="task-line">
          <span>状态</span>
          <el-tag :type="statusType(currentTaskStatus.task_status)">{{ currentTaskStatus.task_status }}</el-tag>
        </div>
        <el-progress :percentage="progress(currentTaskStatus)" :status="progressStatus(currentTaskStatus.task_status)" />
        <el-alert v-if="currentTaskStatus.error_message" class="mt8" type="error" :title="currentTaskStatus.error_message" show-icon />
        <el-alert v-if="currentTaskStatus.result_payload" class="mt8" type="success" :title="payloadSummary(currentTaskStatus.result_payload)" show-icon />
        <el-button class="full mt8" @click="showTask(currentTaskStatus)">查看详情</el-button>
      </div>
      <el-empty v-else description="创建任务后自动跟踪" :image-size="72" />
    </el-dialog>

    <el-dialog v-model="recentTaskDialog.open" title="最近任务" width="920px">
      <template #header>
        <div class="dialog-head">
          <span>最近任务</span>
          <el-button link type="primary" :loading="loading.tasks" @click="loadTasks">刷新</el-button>
        </div>
      </template>
      <el-table class="refund-table recent-task-table" :fit="false" :data="recentTasks" border stripe v-loading="loading.tasks" height="420">
        <el-table-column prop="id" label="ID" width="64" />
        <el-table-column prop="task_type" label="任务类型" width="170">
          <template #default="{ row }">{{ taskTypeLabel(row.task_type) }}</template>
        </el-table-column>
        <el-table-column prop="task_status" label="状态" width="96">
          <template #default="{ row }"><el-tag :type="statusType(row.task_status)">{{ row.task_status }}</el-tag></template>
        </el-table-column>
        <el-table-column label="进度" width="150">
          <template #default="{ row }"><el-progress :percentage="progress(row)" :status="progressStatus(row.task_status)" /></template>
        </el-table-column>
        <el-table-column prop="original_file_name" label="文件名" width="170" show-overflow-tooltip />
        <el-table-column label="结果" width="180" show-overflow-tooltip>
          <template #default="{ row }">{{ payloadSummary(row.result_payload) }}</template>
        </el-table-column>
        <el-table-column prop="error_message" label="错误信息" width="180" show-overflow-tooltip />
        <el-table-column prop="created_at" label="创建时间" width="150" />
        <el-table-column label="操作" width="80" fixed="right">
          <template #default="{ row }"><el-button link type="primary" @click="showTask(row)">详情</el-button></template>
        </el-table-column>
      </el-table>
      <div class="recent-task-footer">
        <span>显示最近 {{ recentTasks.length }} 条，可到“任务历史”页签查看更多</span>
        <el-button type="primary" plain @click="goTaskHistory">查看全部</el-button>
      </div>
    </el-dialog>

    <el-dialog v-model="taskDialog.open" title="任务详情" width="820px">
      <el-descriptions :column="2" border>
        <el-descriptions-item label="任务ID">{{ taskDialog.row.id }}</el-descriptions-item>
        <el-descriptions-item label="状态">{{ taskDialog.row.task_status }}</el-descriptions-item>
        <el-descriptions-item label="任务类型">{{ taskTypeLabel(taskDialog.row.task_type) }}</el-descriptions-item>
        <el-descriptions-item label="创建人">{{ taskDialog.row.created_by }}</el-descriptions-item>
        <el-descriptions-item label="开始时间">{{ taskDialog.row.started_at }}</el-descriptions-item>
        <el-descriptions-item label="完成时间">{{ taskDialog.row.completed_at }}</el-descriptions-item>
      </el-descriptions>
      <el-alert v-if="taskDialog.row.error_message" class="mt12" type="error" :title="taskDialog.row.error_message" show-icon />
      <pre class="json-box">{{ pretty(taskDialog.row.result_payload || taskDialog.row.request_payload || taskDialog.row) }}</pre>
    </el-dialog>

    <el-dialog v-model="generateDialog.open" :title="generateDialog.selectedOnly ? '按选中出口明细生成退税资料' : '生成退税资料'" width="620px">
      <el-alert
        v-if="generateDialog.selectedOnly"
        type="info"
        show-icon
        :closable="false"
        class="mb12"
        :title="`已选择 ${selectedExportIds.length} 条出口明细`"
      />
      <el-form :model="generateSelectedForm" label-width="110px">
        <el-form-item label="输出父目录">
          <el-input v-model="generateSelectedForm.output_parent_dir" placeholder="D:/JMH/退税输出" />
        </el-form-item>
        <el-form-item label="申报年月">
          <el-input v-model="generateSelectedForm.declaration_month" placeholder="202601" maxlength="6" />
        </el-form-item>
        <el-form-item label="付款人">
          <el-input v-model="generateSelectedForm.payer_name" />
        </el-form-item>
        <el-form-item label="覆盖目录">
          <el-switch v-model="generateSelectedForm.overwrite" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="generateDialog.open = false">取消</el-button>
        <el-button type="success" :loading="uploading.REFUND_PACKAGE_GENERATE" @click="submitGenerateFromDialog">生成</el-button>
      </template>
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
const uploadRef = ref()
const activeTab = ref('exports')
const tasks = ref([])
const exports = ref([])
const purchase = ref([])
const forex = ref([])
const taskTotal = ref(0)
const exportTotal = ref(0)
const purchaseTotal = ref(0)
const forexTotal = ref(0)
const selectedExportIds = ref([])
const uploadFiles = ref([])
const polling = new Map()

const loading = reactive({ tasks: false, exports: false, purchase: false, forex: false })
const uploading = reactive({
  CUSTOMS_MATERIAL_IMPORT: false,
  CUSTOMS_DECLARATION_IMPORT: false,
  PURCHASE_INVOICE_IMPORT: false,
  FOREX_IMPORT: false,
  REFUND_PACKAGE_GENERATE: false
})

const taskForm = reactive({ type: 'CUSTOMS_MATERIAL_IMPORT' })
const customsForm = reactive({ declarationMonth: '', declarationBatch: '', exportDate: '' })
const generateForm = reactive({
  output_parent_dir: 'D:/JMH/退税输出',
  declaration_month: '',
  payer_name: 'Hong Kong Cammy Yeson Limited',
  overwrite: false
})
const generateSelectedForm = reactive({ ...generateForm, overwrite: true })

const taskQuery = reactive({ page: 1, page_size: 20, task_type: '', task_status: '' })
const exportQuery = reactive({
  page: 1,
  page_size: 50,
  customs_declaration_no: '',
  contract_no: '',
  declaration_month: '',
  declaration_batch: '',
  relation_no: '',
  customs_match_status: ''
})
const purchaseQuery = reactive({
  page: 1,
  page_size: 50,
  invoice_no: '',
  invoice_date_from: '',
  invoice_date_to: '',
  supplier_tax_no: '',
  buyer_tax_no: '',
  sku_normalized: '',
  inventory_status: ''
})
const forexQuery = reactive({
  page: 1,
  page_size: 50,
  customs_no: '',
  contract_no: '',
  business_entity: '',
  source_type: '',
  export_date_from: '',
  export_date_to: ''
})

const importDialog = reactive({ open: false })
const taskStatusDialog = reactive({ open: false })
const recentTaskDialog = reactive({ open: false })
const taskDialog = reactive({ open: false, row: {} })
const generateDialog = reactive({ open: false, selectedOnly: false })
const currentTaskStatus = reactive({})

const taskTypes = [
  { label: '报关资料 Excel', value: 'CUSTOMS_MATERIAL_IMPORT', ext: '.xlsx', accept: '.xlsx', hint: '.xlsx，最大 50 MB' },
  { label: '出口报关单 PDF', value: 'CUSTOMS_DECLARATION_IMPORT', ext: '.pdf', accept: '.pdf', hint: '.pdf，最大 50 MB，可填写申报年月/批次/出口日期' },
  { label: '进货发票 PDF', value: 'PURCHASE_INVOICE_IMPORT', ext: '.pdf', accept: '.pdf', hint: '.pdf，最大 50 MB' },
  { label: '外汇数据 Excel', value: 'FOREX_IMPORT', ext: '.xlsx', accept: '.xlsx', hint: '.xlsx，仅解析 Sheet1' }
]
const allTaskTypes = [
  ...taskTypes,
  { label: '退税资料生成', value: 'REFUND_PACKAGE_GENERATE' }
]
const statuses = ['PENDING', 'RUNNING', 'SUCCESS', 'PARTIAL', 'FAILED']

const currentTask = computed(() => taskTypes.find(item => item.value === taskForm.type) || taskTypes[0])
const currentSubmitting = computed(() => uploading[taskForm.type])
const recentTasks = computed(() => tasks.value.slice(0, 10))

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

function handleTabChange(tab) {
  if (tab === 'exports') loadExports()
  if (tab === 'purchase') loadPurchase()
  if (tab === 'forex') loadForex()
  if (tab === 'history') loadTasks()
}

function openRecentTasks() {
  recentTaskDialog.open = true
  loadTasks()
}

function goTaskHistory() {
  recentTaskDialog.open = false
  activeTab.value = 'history'
  loadTasks()
}

function selectUploadFile(file, fileList) {
  uploadFiles.value = fileList.map(item => item.raw).filter(Boolean)
}

function removeUploadFile(file, fileList) {
  uploadFiles.value = fileList.map(item => item.raw).filter(Boolean)
}

function resetUploadFile() {
  uploadFiles.value = []
  uploadRef.value?.clearFiles()
}

async function submitCurrentTask() {
  return submitImport(taskForm.type)
}

async function submitImport(type) {
  if (!uploadFiles.value.length) {
    proxy.$modal.msgWarning('请先选择文件')
    return
  }
  uploading[type] = true
  try {
    let res
    if (type === 'CUSTOMS_MATERIAL_IMPORT') res = await importCustomsMaterial(uploadFiles.value)
    if (type === 'CUSTOMS_DECLARATION_IMPORT') {
      res = await importCustomsDeclaration(uploadFiles.value, {
        declarationMonth: customsForm.declarationMonth,
        declarationBatch: customsForm.declarationBatch,
        exportDate: customsForm.exportDate
      })
    }
    if (type === 'PURCHASE_INVOICE_IMPORT') res = await importPurchaseInvoice(uploadFiles.value)
    if (type === 'FOREX_IMPORT') res = await importForex(uploadFiles.value)
    afterTaskCreated(res)
  } finally {
    uploading[type] = false
  }
}

function generateSelectedExports() {
  if (!selectedExportIds.value.length) {
    proxy.$modal.msgWarning('请先勾选出口明细')
    return
  }
  openGenerateDialog(true)
}

function openGenerateDialog(selectedOnly) {
  generateDialog.selectedOnly = selectedOnly
  Object.assign(generateSelectedForm, {
    ...generateForm,
    overwrite: selectedOnly ? true : generateForm.overwrite
  })
  generateDialog.open = true
}

async function submitGenerateFromDialog() {
  if (!generateSelectedForm.output_parent_dir || !generateSelectedForm.declaration_month) {
    proxy.$modal.msgWarning('请填写输出目录和申报年月')
    return
  }
  uploading.REFUND_PACKAGE_GENERATE = true
  try {
    const payload = { ...generateSelectedForm }
    if (generateDialog.selectedOnly) payload.export_ids = selectedExportIds.value
    const res = await generateRefundPackage(payload)
    Object.assign(generateForm, {
      output_parent_dir: generateSelectedForm.output_parent_dir,
      declaration_month: generateSelectedForm.declaration_month,
      payer_name: generateSelectedForm.payer_name,
      overwrite: generateSelectedForm.overwrite
    })
    generateDialog.open = false
    afterTaskCreated(res)
  } finally {
    uploading.REFUND_PACKAGE_GENERATE = false
  }
}

function afterTaskCreated(res) {
  if (importDialog.open) {
    importDialog.open = false
    resetUploadFile()
  }
  const task = res?.data?.data
  const tasks = task?.data?.tasks || task?.tasks || []
  if (tasks.length) {
    Object.assign(currentTaskStatus, tasks[0])
    proxy.$modal.msgSuccess(`任务已提交：${tasks.length} 个`)
    tasks.forEach(item => item?.id && startPolling(item.id))
    loadTasks()
    return
  }
  const batch = task?.data || task || {}
  const taskIds = Array.isArray(batch.task_ids) ? batch.task_ids : []
  if (taskIds.length) {
    Object.assign(currentTaskStatus, {
      id: taskIds[0],
      task_type: batch.task_type,
      task_status: batch.task_status || 'PENDING'
    })
    proxy.$modal.msgSuccess(`任务已提交：${taskIds.length} 个`)
    taskIds.forEach(id => id && startPolling(id))
    loadTasks()
    return
  }
  if (!task?.id) {
    proxy.$modal.msgSuccess('任务已提交')
    loadTasks()
    return
  }
  Object.assign(currentTaskStatus, task)
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
      if (task) Object.assign(currentTaskStatus, task)
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
    const res = await listPurchaseInventory(cleanParams(purchaseQuery))
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
  Object.assign(taskQuery, { page: 1, page_size: 20, task_type: '', task_status: '' })
  loadTasks()
}

function resetExportQuery() {
  Object.assign(exportQuery, { page: 1, page_size: 50, customs_declaration_no: '', contract_no: '', declaration_month: '', declaration_batch: '', relation_no: '', customs_match_status: '' })
  loadExports()
}

function resetPurchaseQuery() {
  Object.assign(purchaseQuery, { page: 1, page_size: 50, invoice_no: '', invoice_date_from: '', invoice_date_to: '', supplier_tax_no: '', buyer_tax_no: '', sku_normalized: '', inventory_status: '' })
  loadPurchase()
}

function resetForexQuery() {
  Object.assign(forexQuery, { page: 1, page_size: 50, customs_no: '', contract_no: '', business_entity: '', source_type: '', export_date_from: '', export_date_to: '' })
  loadForex()
}

function handleExportSelection(selection) {
  selectedExportIds.value = selection.map(row => Number(row.id)).filter(Boolean)
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
  return { PENDING: 'info', RUNNING: 'warning', SUCCESS: 'success', PARTIAL: 'warning', FAILED: 'danger' }[status] || 'info'
}

function matchStatusType(status) {
  return status === 'MATCHED' ? 'success' : status === 'UNMATCHED' ? 'warning' : 'info'
}

function inventoryStatusType(status) {
  return { AVAILABLE: 'success', PARTIAL: 'warning', EXHAUSTED: 'danger' }[status] || 'info'
}

function taskTypeLabel(type) {
  return allTaskTypes.find(item => item.value === type)?.label || type
}

function cleanParams(source) {
  const params = {}
  Object.keys(source).forEach(key => {
    if (source[key] !== undefined && source[key] !== null && source[key] !== '') params[key] = source[key]
  })
  return params
}

function pretty(value) {
  if (!value) return ''
  return JSON.stringify(value, null, 2)
}

function payloadSummary(value) {
  if (!value) return ''
  const payload = typeof value === 'string' ? tryParseJson(value) : value
  if (!payload || typeof payload !== 'object') return String(value)
  return displayValue(
    payload.output_dir,
    payload.output_path,
    payload.message,
    payload.summary,
    payload.file_path,
    payload.file_name,
    payload.batch_id ? `批次 ${payload.batch_id}` : '',
    payload.count !== undefined ? `数量 ${payload.count}` : '',
    JSON.stringify(payload)
  )
}

function tryParseJson(value) {
  try {
    return JSON.parse(value)
  } catch (e) {
    return value
  }
}

function displayValue(...values) {
  return values.find(value => value !== undefined && value !== null && value !== '') ?? ''
}

function money(value) {
  if (value === '' || value === null || value === undefined) return ''
  return Number(value).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<style scoped>
.tax-refund-page {
  background: #f5f7fb;
  min-height: calc(100vh - 84px);
  overflow-x: hidden;
}

.tax-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 16px;
  padding: 14px 16px;
  margin-bottom: 12px;
  background: #fff;
  border: 1px solid #e5e7eb;
  border-radius: 6px;
}

.tax-title {
  color: #1f2937;
  font-size: 20px;
  font-weight: 700;
}

.tax-subtitle {
  color: #64748b;
  font-size: 12px;
}

.header-actions {
  flex-shrink: 0;
}

.export-refund-btn {
  min-width: 150px;
}

.data-card {
  background: #fff;
  border: 1px solid #e5e7eb;
  border-radius: 6px;
  overflow: hidden;
}

.workspace {
  display: grid;
  gap: 12px;
}

.data-card {
  margin-bottom: 0;
}

.card-head,
.header-actions,
.table-actions,
.task-line {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.full {
  width: 100%;
}

.upload-tip {
  color: #909399;
  font-size: 12px;
  line-height: 18px;
  white-space: nowrap;
}

.dialog-import-form :deep(.el-form-item) {
  margin-bottom: 14px;
}

.dialog-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding-right: 28px;
}

.task-current {
  display: grid;
  gap: 8px;
}

.task-line {
  color: #64748b;
  font-size: 13px;
}

.task-line b {
  color: #1f2937;
}

.main-panel {
  min-width: 0;
  display: grid;
  gap: 12px;
}

.data-card {
  min-width: 0;
}

.data-card :deep(.el-card__body) {
  padding: 10px 12px 12px;
}

.data-tabs :deep(.el-tabs__header) {
  margin-bottom: 8px;
  padding: 0 12px;
  background: #fff;
  border: 1px solid #e5e7eb;
  border-radius: 6px;
}

.query-form {
  padding-bottom: 6px;
  border-bottom: 1px solid #eef2f7;
}

.query-form :deep(.el-form-item) {
  margin-right: 10px;
  margin-bottom: 10px;
}

.query-form :deep(.el-input),
.query-form :deep(.el-select),
.query-form :deep(.el-date-editor.el-input) {
  width: 142px;
}

.table-actions {
  margin: 10px 0;
}

.table-stat {
  color: #64748b;
  font-size: 12px;
  font-weight: 600;
}

.refund-table {
  width: 100%;
}

.refund-table :deep(.el-table__inner-wrapper) {
  min-width: max-content;
}

.refund-table :deep(.el-scrollbar__bar.is-horizontal) {
  height: 10px;
}

.refund-table :deep(.el-scrollbar__bar.is-horizontal .el-scrollbar__thumb) {
  background-color: #94a3b8;
}

.refund-table :deep(.el-table__cell) {
  padding: 5px 0;
}

.refund-table :deep(.cell) {
  padding-left: 6px;
  padding-right: 6px;
  white-space: nowrap;
}

.refund-table :deep(.el-tag) {
  max-width: 76px;
}

.refund-table :deep(.el-progress__text) {
  min-width: 36px;
}

.recent-task-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-top: 12px;
  color: #64748b;
  font-size: 12px;
}

.json-box {
  max-height: 380px;
  overflow: auto;
  margin-top: 12px;
  padding: 12px;
  color: #d7e0ef;
  background: #111827;
  border-radius: 6px;
  font-size: 12px;
  white-space: pre-wrap;
}

.mt8 {
  margin-top: 8px;
}

.mt12 {
  margin-top: 12px;
}

.mb12 {
  margin-bottom: 12px;
}

@media (max-width: 900px) {
  .tax-header {
    align-items: flex-start;
    flex-direction: column;
  }
}
</style>
