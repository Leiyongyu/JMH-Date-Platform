<template>
  <div class="ebay-audit-page">
    <section class="page-heading">
      <div>
        <div class="eyebrow">EBAY SP PRICE REVIEW</div>
        <h2>eBay SP 价格批量审核</h2>
        <p>上传 SKU / OE 清单，系统解析查询 OE 后异步获取最低价前 10 个商品，再由人工逐项确认导出范围。</p>
      </div>
      <div class="heading-actions">
        <el-tag :type="health.configured ? 'success' : 'danger'" effect="plain" round>
          {{ health.configured ? 'eBay 接口正常' : 'eBay 接口未配置' }}
        </el-tag>
        <el-button
          v-hasPermi="['scripts:ebayPrice:import']"
          :icon="UploadFilled"
          @click="mappingDialogVisible = true"
        >
          导入 SKU-OE 映射
        </el-button>
        <el-button v-if="historyTasks.length" :icon="Clock" @click="historyVisible = true">历史批次</el-button>
        <el-button v-if="task && !showUploader" @click="openNewTask">新建批次</el-button>
        <el-button
          v-if="task && !showUploader"
          v-hasPermi="['scripts:ebayPrice:export']"
          type="primary"
          :icon="Download"
          :loading="exporting"
          :disabled="task.status !== 'COMPLETED' || !task.selectedCount"
          @click="handleExport"
        >
          导出已选商品（{{ task.selectedCount || 0 }}）
        </el-button>
      </div>
    </section>

    <section v-if="showUploader || !task" class="upload-card">
      <div class="flow-steps">
        <div v-for="(step, index) in flowSteps" :key="step.title" class="flow-step">
          <span>{{ index + 1 }}</span>
          <div><strong>{{ step.title }}</strong><small>{{ step.text }}</small></div>
        </div>
      </div>

      <div class="upload-body">
        <div class="upload-copy">
          <h3>上传 SKU / OE 查询文件</h3>
          <p>只读取第一个工作表，支持以下两种固定格式：</p>
          <ul>
            <li><b>一列表：</b>A1 为“OE号”，从 A2 开始每行一个 OE。</li>
            <li><b>两列表：</b>A1 为“SKU”、B1 为“OE号”，数据顺序固定为 A列SKU、B列OE。</li>
            <li>有 SKU 时优先查询 SKU-OE 对照表，同一 SKU 有多个 OE 时取排序第一的 OE；SKU 无映射时回退使用该行 B 列 OE。</li>
            <li>支持 .xlsx、.xlsm、.xls；单批最多 2000 个不同 SKU 或查询 OE，空白行会自动忽略。</li>
            <li>重复 OE 只查询一次，并在任务概览中提示数量。</li>
            <li>单个 OE 查询失败不会影响其他 OE，可在审核时单独重试。</li>
            <li>查询在后台执行，刷新页面后仍可继续查看和审核。</li>
          </ul>
          <div class="site-picker">
            <span>查询站点</span>
            <el-radio-group v-model="uploadSite">
              <el-radio-button value="de">德国站</el-radio-button>
              <el-radio-button value="uk">英国站</el-radio-button>
              <el-radio-button value="us">美国站</el-radio-button>
            </el-radio-group>
          </div>
        </div>

        <div class="upload-panel">
          <section class="create-method">
            <div class="method-heading">
              <div><strong>上传 Excel 文件</strong><span>适合批量数据</span></div>
              <el-tag size="small" effect="plain">最多 2000 条</el-tag>
            </div>
            <div class="file-picker-row">
              <el-upload
                ref="uploadRef"
                v-model:file-list="uploadFiles"
                :auto-upload="false"
                :limit="1"
                :show-file-list="false"
                accept=".xlsx,.xlsm,.xls"
                :on-change="handleFileChange"
              >
                <el-button :icon="UploadFilled">选择 Excel 文件</el-button>
              </el-upload>
              <span :class="{ selected: uploadFile }">{{ uploadFile?.name || '尚未选择文件' }}</span>
              <el-button v-if="uploadFile" link type="danger" @click="handleFileRemove">移除</el-button>
            </div>
            <p>支持 A列OE号，或 A列SKU + B列OE号。</p>
            <el-button
              v-hasPermi="['scripts:ebayPrice:query']"
              type="primary"
              :loading="uploading"
              :disabled="!uploadFile || !health.configured || manualSubmitting"
              @click="startAuditTask"
            >
              {{ uploading ? '正在创建任务…' : '上传并开始查询' }}
            </el-button>
          </section>

          <div class="method-divider"><span>或者直接输入</span></div>

          <section class="create-method manual-method">
            <div class="method-heading">
              <div><strong>手工输入 SKU / OE</strong><span>适合少量临时查询</span></div>
              <span class="input-count">{{ manualKeywordCount }} / 2000</span>
            </div>
            <el-radio-group v-model="manualInputType" size="small">
              <el-radio-button value="sku">输入 SKU</el-radio-button>
              <el-radio-button value="oe">输入 OE号</el-radio-button>
            </el-radio-group>
            <el-input
              v-model="manualInput"
              type="textarea"
              :rows="5"
              maxlength="100000"
              resize="vertical"
              :placeholder="manualInputType === 'sku'
                ? '输入SKU，多个使用逗号或换行分隔。系统将从SKU-OE映射表取第一个OE。'
                : '输入OE号，多个使用逗号或换行分隔。'"
            />
            <p v-if="manualInputType === 'sku'">SKU 未建立映射时会明确提示，请先导入 SKU-OE 对照表。</p>
            <el-button
              v-hasPermi="['scripts:ebayPrice:query']"
              type="primary"
              :loading="manualSubmitting"
              :disabled="!manualInput.trim() || !health.configured || uploading || manualKeywordCount > 2000"
              @click="startManualAuditTask"
            >
              {{ manualSubmitting ? '正在创建任务…' : '开始查询输入内容' }}
            </el-button>
          </section>

          <div v-if="task" class="upload-actions">
            <el-button @click="cancelNewTask">返回当前任务</el-button>
          </div>
        </div>
      </div>
    </section>

    <template v-else>
      <section class="task-summary">
        <div class="summary-main">
          <div class="task-title">
            <div>
              <span class="task-label">当前批次</span>
              <h3>{{ task.taskName }}</h3>
              <p>{{ task.sourceFileName }} · {{ siteLabel(task.site) }}</p>
            </div>
            <el-tag :type="taskStatusType(task.status)" effect="light" round>{{ taskStatusText(task.status) }}</el-tag>
          </div>
          <div class="progress-row">
            <span>查询进度</span>
            <el-progress :percentage="queryPercent" :stroke-width="10" />
            <strong>{{ task.processedOe || 0 }} / {{ task.totalOe || 0 }}</strong>
          </div>
          <div class="progress-row">
            <span>审核进度</span>
            <el-progress :percentage="reviewPercent" :stroke-width="10" color="#12b76a" />
            <strong>{{ task.reviewedOe || 0 }} / {{ task.totalOe || 0 }}</strong>
          </div>
        </div>
        <div class="summary-grid">
          <div><span>OE 总数</span><strong>{{ task.totalOe || 0 }}</strong></div>
          <div><span>有结果</span><strong class="success">{{ task.successOe || 0 }}</strong></div>
          <div><span>无结果</span><strong class="muted-number">{{ task.emptyOe || 0 }}</strong></div>
          <div><span>查询失败</span><strong class="danger">{{ task.failedOe || 0 }}</strong></div>
          <div><span>已选商品</span><strong class="primary">{{ task.selectedCount || 0 }}</strong></div>
        </div>
      </section>

      <el-alert
        v-if="task.duplicateOe || task.blankRows"
        class="file-notice"
        type="info"
        :closable="false"
        show-icon
        :title="`文件已清理：忽略 ${task.duplicateOe || 0} 个重复 OE、${task.blankRows || 0} 个空白行。`"
      />

      <section class="review-workbench">
        <aside class="oe-sidebar">
          <div class="sidebar-heading">
            <div><strong>审核清单</strong><span>{{ filteredOes.length }} 个</span></div>
            <el-button circle text :icon="Refresh" :loading="refreshing" title="刷新进度" @click="refreshTask(false)" />
          </div>
          <el-input v-model="oeKeyword" :prefix-icon="Search" clearable placeholder="搜索 OE" />
          <el-select v-model="oeFilter" class="status-filter">
            <el-option label="全部状态" value="all" />
            <el-option label="待审核" value="pending" />
            <el-option label="已审核" value="reviewed" />
            <el-option label="无结果" value="empty" />
            <el-option label="查询失败" value="failed" />
          </el-select>
          <div class="oe-list">
            <button
              v-for="row in filteredOes"
              :key="row.id"
              type="button"
              class="oe-row"
              :class="{ active: currentOe?.id === row.id }"
              @click="switchOe(row)"
            >
              <span class="oe-index">{{ row.sortNo }}</span>
              <span class="oe-name" :title="row.oe">{{ row.oe }}</span>
              <span class="oe-state" :class="statusClass(row)">{{ shortStatus(row) }}</span>
              <small v-if="row.selectedCount">已选 {{ row.selectedCount }}</small>
            </button>
            <el-empty v-if="!filteredOes.length" :image-size="58" description="没有符合条件的 OE" />
          </div>
        </aside>

        <main class="review-main">
          <div v-if="currentOe" class="review-heading">
            <div>
              <span class="review-position">当前审核：第 {{ currentPosition }} / 共 {{ task.totalOe }} 个</span>
              <div class="current-oe-line">
                <h3>{{ currentOe.oe }}</h3>
                <el-tag :type="queryStatusType(currentOe.queryStatus)" effect="plain" round>
                  {{ queryStatusText(currentOe.queryStatus) }}
                </el-tag>
                <el-tag v-if="currentOe.reviewStatus !== 'PENDING'" type="success" effect="plain" round>
                  {{ reviewStatusText(currentOe.reviewStatus) }}
                </el-tag>
              </div>
              <p>按含运费前的商品价格从低到高展示，最多 10 个候选商品。</p>
            </div>
            <div class="position-jump">
              <el-button :icon="ArrowLeft" :disabled="currentPosition <= 1" @click="goPrevious">上一个</el-button>
              <el-button :icon="ArrowRight" :disabled="currentPosition >= task.totalOe" @click="handleTopNext">
                {{ currentOe.queryStatus === 'SUCCESS' ? '保存并下一个' : (currentOe.queryStatus === 'FAILED' ? '跳过并下一个' : '下一个') }}
              </el-button>
            </div>
          </div>

          <div v-if="detailLoading" class="state-panel">
            <el-skeleton :rows="6" animated />
          </div>

          <div v-else-if="!currentOe" class="state-panel">
            <el-empty description="请选择一个 OE 查看审核内容" />
          </div>

          <div v-else-if="['PENDING', 'QUERYING'].includes(currentOe.queryStatus)" class="state-panel waiting-state">
            <div class="state-icon loading"><el-icon><Loading /></el-icon></div>
            <h3>正在查询 {{ currentOe.oe }}</h3>
            <p>后台正在请求 eBay 并补充商品详情。你可以先审核左侧已经完成的 OE，系统会自动刷新状态。</p>
            <el-button :icon="Refresh" :loading="refreshing" @click="refreshCurrent">立即刷新</el-button>
          </div>

          <div v-else-if="currentOe.queryStatus === 'EMPTY'" class="state-panel empty-state">
            <div class="state-icon empty"><el-icon><Search /></el-icon></div>
            <h3>没有搜索到商品</h3>
            <p>eBay 在当前站点没有返回有效且价格大于 0 的商品。该 OE 已自动计入“无结果”，不会阻塞最终导出。</p>
            <div>
              <el-button :icon="Refresh" :loading="retrying" @click="retryCurrent">重新查询</el-button>
              <el-button type="primary" :icon="ArrowRight" @click="goNextAfterHandled">继续下一个</el-button>
            </div>
          </div>

          <div v-else-if="currentOe.queryStatus === 'FAILED'" class="state-panel failed-state">
            <div class="state-icon failed"><el-icon><WarningFilled /></el-icon></div>
            <h3>该 OE 查询失败</h3>
            <p>其他 OE 不受影响。可以先重试；如果确认暂不处理，也可以跳过并继续，后续仍可返回重试。</p>
            <el-alert type="error" :closable="false" show-icon :title="currentOe.errorMessage || 'eBay 接口请求失败'" />
            <div>
              <el-button :icon="Refresh" :loading="retrying" @click="retryCurrent">重新查询</el-button>
              <el-button type="warning" plain :loading="savingReview" @click="skipCurrent">跳过并继续</el-button>
            </div>
          </div>

          <template v-else>
            <div class="selection-bar">
              <div>
                <strong>请选择确认匹配的商品</strong>
                <span>可以多选，也可以一件不选</span>
              </div>
              <div>
                <span>已选 <b>{{ selectedItemIds.length }}</b> / {{ currentItems.length }}</span>
                <el-button link type="primary" @click="toggleAll(true)">全选</el-button>
                <el-button link @click="toggleAll(false)">清空</el-button>
              </div>
            </div>

            <el-table
              ref="resultTableRef"
              class="result-table"
              :data="currentItems"
              row-key="id"
              max-height="calc(100vh - 460px)"
              @selection-change="handleSelectionChange"
            >
              <el-table-column type="selection" width="48" fixed="left" reserve-selection />
              <el-table-column label="排名" width="62" align="center">
                <template #default="{ row }"><span class="rank-badge">{{ row.rankNo }}</span></template>
              </el-table-column>
              <el-table-column label="图片" width="90">
                <template #default="{ row }">
                  <div v-if="row.images?.length" class="image-cell">
                    <el-image class="product-image" :src="row.images[0]" :preview-src-list="row.images" preview-teleported fit="cover" />
                    <span>{{ row.images.length }}</span>
                  </div>
                  <span class="muted">无图片</span>
                </template>
              </el-table-column>
              <el-table-column label="商品信息" min-width="330">
                <template #default="{ row }">
                  <div class="product-info">
                    <div><el-tag size="small" effect="plain">{{ displayProductId(row) }}</el-tag><span>{{ row.condition || '成色未知' }}</span></div>
                    <strong :title="row.title">{{ row.title || '—' }}</strong>
                    <small v-if="row.imageDetailComplete === false">详情读取不完整，当前展示搜索摘要信息</small>
                  </div>
                </template>
              </el-table-column>
              <el-table-column label="价格" width="135" align="right">
                <template #default="{ row }"><div class="price-cell"><strong>{{ row.price || '—' }}</strong><small>{{ row.shipping || '运费未知' }}</small></div></template>
              </el-table-column>
              <el-table-column label="预计已售" width="90" align="right">
                <template #default="{ row }">{{ row.estimatedSoldQuantity ?? '—' }}</template>
              </el-table-column>
              <el-table-column label="卖家" width="160">
                <template #default="{ row }"><div class="seller-cell"><span>{{ row.seller || '—' }}</span><small>{{ row.sellerFeedback ? `${row.sellerFeedback}% 好评` : '暂无好评率' }}</small></div></template>
              </el-table-column>
              <el-table-column label="链接" width="70" fixed="right" align="center">
                <template #default="{ row }"><el-link v-if="row.link" :href="row.link" target="_blank" type="primary" :underline="false"><el-icon><Link /></el-icon></el-link><span v-else>—</span></template>
              </el-table-column>
            </el-table>

            <div class="review-footer">
              <div>
                <el-icon><InfoFilled /></el-icon>
                <span>选择结果会保存到当前批次；已审核 OE 仍可返回修改。</span>
              </div>
              <el-button
                v-hasPermi="['scripts:ebayPrice:query']"
                type="primary"
                size="large"
                :loading="savingReview"
                @click="saveAndNext"
              >
                {{ currentPosition >= task.totalOe ? `保存审核（已选 ${selectedItemIds.length}）` : `保存并审核下一个（已选 ${selectedItemIds.length}）` }}
                <el-icon class="el-icon--right"><ArrowRight /></el-icon>
              </el-button>
            </div>
          </template>
        </main>
      </section>
    </template>

    <el-drawer v-model="historyVisible" title="最近批次" size="420px">
      <div class="history-list">
        <div
          v-for="row in historyTasks"
          :key="row.id"
          class="history-row"
          :class="{ active: task?.id === row.id }"
          role="button"
          tabindex="0"
          @click="openHistoryTask(row)"
          @keyup.enter="openHistoryTask(row)"
        >
          <div>
            <strong>{{ row.taskName }}</strong>
            <div class="history-row-actions">
              <el-tag :type="taskStatusType(row.status)" size="small" effect="plain">{{ taskStatusText(row.status) }}</el-tag>
              <el-button
                v-hasPermi="['scripts:ebayPrice:query']"
                circle
                text
                type="danger"
                :icon="Delete"
                :loading="deletingTaskId === row.id"
                :disabled="row.status === 'QUERYING'"
                :title="row.status === 'QUERYING' ? '后台查询完成后才能删除' : '删除历史任务'"
                @click.stop="handleDeleteTask(row)"
              />
            </div>
          </div>
          <p>{{ row.sourceFileName }} · {{ siteLabel(row.site) }}</p>
          <span>OE {{ row.totalOe }} · 已查询 {{ row.processedOe }} · 已审核 {{ row.reviewedOe }} · 已选 {{ row.selectedCount }}</span>
        </div>
      </div>
    </el-drawer>

    <el-dialog
      v-model="mappingDialogVisible"
      title="导入 SKU-OE 映射"
      width="600px"
      :close-on-click-modal="!mappingImporting"
      :close-on-press-escape="!mappingImporting"
      :show-close="!mappingImporting"
      @closed="resetMappingImport"
    >
      <div class="mapping-import-dialog">
        <el-alert type="info" :closable="false" show-icon>
          <template #title>按 SKU 增量覆盖，不会清空整张映射表</template>
          <p>Excel 表头必须包含 <b>sku</b> 和 <b>oe</b> 两列；一个 SKU 的多个 OE 可使用英文逗号、中文逗号或换行分隔。</p>
          <p>文件中出现的 SKU 会删除旧 OE 后重建；文件中没有出现的 SKU 保持不变。</p>
        </el-alert>

        <div class="mapping-file-row">
          <el-upload
            ref="mappingUploadRef"
            v-model:file-list="mappingFiles"
            :auto-upload="false"
            :limit="1"
            :show-file-list="false"
            accept=".xlsx,.xlsm"
            :disabled="mappingImporting"
            :on-change="handleMappingFileChange"
          >
            <el-button :icon="UploadFilled" :disabled="mappingImporting">选择映射文件</el-button>
          </el-upload>
          <span :class="{ selected: mappingFile }">{{ mappingFile?.name || '尚未选择文件' }}</span>
          <el-button v-if="mappingFile" link type="danger" :disabled="mappingImporting" @click="clearMappingFile">移除</el-button>
        </div>

        <div v-if="mappingImportResult" class="mapping-result">
          <div><span>文件数据行</span><strong>{{ mappingImportResult.totalRows || 0 }}</strong></div>
          <div><span>影响 SKU</span><strong>{{ mappingImportResult.affectedSkus || 0 }}</strong></div>
          <div><span>新增 SKU</span><strong>{{ mappingImportResult.createdSkus || 0 }}</strong></div>
          <div><span>覆盖 SKU</span><strong>{{ mappingImportResult.updatedSkus || 0 }}</strong></div>
          <div><span>写入映射</span><strong>{{ mappingImportResult.insertedMappings || 0 }}</strong></div>
          <div><span>跳过行</span><strong>{{ mappingImportResult.skippedRows || 0 }}</strong></div>
        </div>
      </div>
      <template #footer>
        <el-button :disabled="mappingImporting" @click="mappingDialogVisible = false">关闭</el-button>
        <el-button
          v-hasPermi="['scripts:ebayPrice:import']"
          type="primary"
          :loading="mappingImporting"
          :disabled="!mappingFile"
          @click="handleMappingImport"
        >
          {{ mappingImporting ? '正在导入…' : '确认增量覆盖导入' }}
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, nextTick, onMounted, onUnmounted, reactive, ref } from 'vue'
import {
  ArrowLeft, ArrowRight, Clock, Delete, Download, InfoFilled, Link, Loading,
  Refresh, Search, UploadFilled, WarningFilled
} from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { saveAs } from 'file-saver'
import {
  createEbayManualAuditTask,
  createEbayAuditTask,
  deleteEbayAuditTask,
  exportEbayAuditTask,
  getEbayAuditOe,
  getEbayAuditTask,
  getEbayAuditTasks,
  getEbayHealth,
  getLatestEbayAuditTask,
  importSkuOeMapping,
  retryEbayAuditOe,
  reviewEbayAuditOe
} from '@/api/scripts/ebayPrice'

const flowSteps = [
  { title: '上传清单', text: '支持OE或SKU+OE' },
  { title: '后台查询', text: '异步获取最低价TOP10' },
  { title: '人工审核', text: '逐个OE多选或不选' },
  { title: '统一导出', text: '只导出已选商品' }
]

const health = reactive({ configured: false, status: 'unknown' })
const historyTasks = ref([])
const historyVisible = ref(false)
const deletingTaskId = ref(null)
const mappingDialogVisible = ref(false)
const mappingUploadRef = ref()
const mappingFiles = ref([])
const mappingFile = ref(null)
const mappingImporting = ref(false)
const mappingImportResult = ref(null)
const task = ref(null)
const oes = ref([])
const currentOe = ref(null)
const currentItems = ref([])
const selectedItemIds = ref([])
const initialSelectedIds = ref([])
const showUploader = ref(false)
const uploadSite = ref('de')
const uploadRef = ref()
const uploadFiles = ref([])
const uploadFile = ref(null)
const manualInputType = ref('sku')
const manualInput = ref('')
const manualSubmitting = ref(false)
const resultTableRef = ref()
const uploading = ref(false)
const refreshing = ref(false)
const detailLoading = ref(false)
const savingReview = ref(false)
const retrying = ref(false)
const exporting = ref(false)
const oeKeyword = ref('')
const oeFilter = ref('all')
let pollTimer = null

const queryPercent = computed(() => percent(task.value?.processedOe, task.value?.totalOe))
const reviewPercent = computed(() => percent(task.value?.reviewedOe, task.value?.totalOe))
const manualKeywords = computed(() => splitManualKeywords(manualInput.value))
const manualKeywordCount = computed(() => manualKeywords.value.length)
const currentPosition = computed(() => {
  const index = oes.value.findIndex(row => row.id === currentOe.value?.id)
  return index < 0 ? 0 : index + 1
})
const selectionChanged = computed(() => normalizeIds(selectedItemIds.value).join(',') !== normalizeIds(initialSelectedIds.value).join(','))
const filteredOes = computed(() => {
  const keyword = oeKeyword.value.trim().toLowerCase()
  return oes.value.filter(row => {
    if (keyword && !String(row.oe || '').toLowerCase().includes(keyword)) return false
    if (oeFilter.value === 'pending') return row.reviewStatus === 'PENDING' && row.queryStatus === 'SUCCESS'
    if (oeFilter.value === 'reviewed') return row.reviewStatus !== 'PENDING'
    if (oeFilter.value === 'empty') return row.queryStatus === 'EMPTY'
    if (oeFilter.value === 'failed') return row.queryStatus === 'FAILED'
    return true
  })
})

onMounted(async () => {
  await Promise.all([loadHealth(), loadHistory(), restoreLatestTask()])
})

onUnmounted(stopPolling)

async function loadHealth() {
  try {
    const response = await getEbayHealth()
    Object.assign(health, response.data || {})
  } catch (_) {
    health.configured = false
    health.status = 'unavailable'
  }
}

async function restoreLatestTask() {
  try {
    const response = await getLatestEbayAuditTask()
    if (response.data?.task) {
      applyTaskView(response.data)
      await openInitialOe()
    }
  } catch (_) {
    // 新环境尚未执行审核任务建表脚本时仍允许页面展示上传说明。
  }
}

async function loadHistory() {
  try {
    const response = await getEbayAuditTasks()
    historyTasks.value = response.data || []
  } catch (_) {
    historyTasks.value = []
  }
}

async function openHistoryTask(row) {
  if (!await confirmDiscardSelection()) return
  const response = await getEbayAuditTask(row.id)
  currentOe.value = null
  currentItems.value = []
  applyTaskView(response.data)
  historyVisible.value = false
  showUploader.value = false
  await openInitialOe()
}

async function handleDeleteTask(row) {
  if (row.status === 'QUERYING') {
    ElMessage.warning('该批次仍在后台查询中，完成后才能删除')
    return
  }
  try {
    await ElMessageBox.confirm(
      `确定删除历史任务“${row.taskName}”吗？任务、OE审核明细和候选商品都将被删除，且无法恢复。`,
      '删除历史任务',
      {
        confirmButtonText: '确认删除',
        cancelButtonText: '取消',
        type: 'warning'
      }
    )
  } catch (_) {
    return
  }

  deletingTaskId.value = row.id
  try {
    await deleteEbayAuditTask(row.id)
    const deletingCurrent = task.value?.id === row.id
    await loadHistory()
    if (deletingCurrent) {
      stopPolling()
      task.value = null
      oes.value = []
      currentOe.value = null
      currentItems.value = []
      selectedItemIds.value = []
      initialSelectedIds.value = []
      const nextTask = historyTasks.value[0]
      if (nextTask) {
        const response = await getEbayAuditTask(nextTask.id)
        applyTaskView(response.data)
        await openInitialOe()
      } else {
        showUploader.value = true
        historyVisible.value = false
      }
    }
    ElMessage.success('历史任务已删除')
  } finally {
    deletingTaskId.value = null
  }
}

function handleFileChange(file) {
  uploadFile.value = file.raw || null
}

function handleFileRemove() {
  uploadRef.value?.clearFiles()
  uploadFiles.value = []
  uploadFile.value = null
}

function handleMappingFileChange(file) {
  mappingFile.value = file.raw || null
  mappingImportResult.value = null
}

function clearMappingFile() {
  mappingUploadRef.value?.clearFiles()
  mappingFiles.value = []
  mappingFile.value = null
}

function resetMappingImport() {
  clearMappingFile()
  mappingImportResult.value = null
}

async function handleMappingImport() {
  if (!mappingFile.value) {
    ElMessage.warning('请先选择 SKU-OE 映射文件')
    return
  }
  mappingImporting.value = true
  try {
    const response = await importSkuOeMapping(mappingFile.value, createRequestId('sku-oe-import'))
    mappingImportResult.value = response.data || {}
    clearMappingFile()
    ElMessage.success(`映射导入成功：影响 ${mappingImportResult.value.affectedSkus || 0} 个 SKU`)
  } finally {
    mappingImporting.value = false
  }
}

async function startAuditTask() {
  if (!uploadFile.value) {
    ElMessage.warning('请先选择SKU / OE Excel文件')
    return
  }
  uploading.value = true
  try {
    const response = await createEbayAuditTask(uploadFile.value, uploadSite.value, createRequestId('audit'))
    applyTaskView(response.data)
    showUploader.value = false
    uploadFiles.value = []
    uploadFile.value = null
    uploadRef.value?.clearFiles()
    await loadHistory()
    await openInitialOe()
    ElMessage.success('文件读取成功，后台查询已开始')
  } finally {
    uploading.value = false
  }
}

async function startManualAuditTask() {
  if (!manualKeywordCount.value) {
    ElMessage.warning(`请先输入${manualInputType.value === 'sku' ? 'SKU' : 'OE号'}`)
    return
  }
  if (manualKeywordCount.value > 2000) {
    ElMessage.warning(`单批最多输入2000个，本次识别到${manualKeywordCount.value}个`)
    return
  }
  manualSubmitting.value = true
  try {
    const response = await createEbayManualAuditTask({
      keywords: manualKeywords.value,
      site: uploadSite.value,
      inputType: manualInputType.value
    }, createRequestId('manual-audit'))
    applyTaskView(response.data)
    showUploader.value = false
    manualInput.value = ''
    await loadHistory()
    await openInitialOe()
    ElMessage.success('输入解析成功，后台查询已开始')
  } finally {
    manualSubmitting.value = false
  }
}

function applyTaskView(data) {
  if (!data?.task) return
  task.value = data.task
  oes.value = data.oes || []
  syncCurrentOe()
  configurePolling()
}

function syncCurrentOe() {
  if (!currentOe.value) return
  const updated = oes.value.find(row => row.id === currentOe.value.id)
  if (updated) currentOe.value = updated
}

async function openInitialOe() {
  const target = oes.value.find(row => row.queryStatus === 'SUCCESS' && row.reviewStatus === 'PENDING')
    || oes.value.find(row => row.queryStatus === 'FAILED' && row.reviewStatus === 'PENDING')
    || oes.value.find(row => ['PENDING', 'QUERYING'].includes(row.queryStatus))
    || oes.value[0]
  if (target) await loadOe(target)
}

async function refreshTask(silent = true) {
  if (!task.value?.id) return
  if (!silent) refreshing.value = true
  try {
    const previousStatus = currentOe.value?.queryStatus
    const response = await getEbayAuditTask(task.value.id)
    applyTaskView(response.data)
    if (currentOe.value && ['PENDING', 'QUERYING'].includes(previousStatus)
      && !['PENDING', 'QUERYING'].includes(currentOe.value.queryStatus)) {
      await loadOe(currentOe.value, true)
    }
  } finally {
    refreshing.value = false
  }
}

async function refreshCurrent() {
  await refreshTask(false)
  if (currentOe.value && !['PENDING', 'QUERYING'].includes(currentOe.value.queryStatus)) {
    await loadOe(currentOe.value, true)
  }
}

function configurePolling() {
  stopPolling()
  if (task.value?.status === 'QUERYING') {
    pollTimer = window.setInterval(() => refreshTask(true), 2500)
  }
}

function stopPolling() {
  if (pollTimer) window.clearInterval(pollTimer)
  pollTimer = null
}

async function loadOe(row, force = false) {
  if (!row || (!force && currentOe.value?.id === row.id && currentItems.value.length)) return
  detailLoading.value = true
  currentOe.value = row
  currentItems.value = []
  selectedItemIds.value = []
  initialSelectedIds.value = []
  try {
    const response = await getEbayAuditOe(task.value.id, row.id)
    currentOe.value = response.data?.oe || row
    currentItems.value = response.data?.items || []
    const saved = currentItems.value.filter(item => item.selected).map(item => item.id)
    selectedItemIds.value = saved
    initialSelectedIds.value = [...saved]
    await nextTick()
    resultTableRef.value?.clearSelection()
    currentItems.value.forEach(item => {
      if (saved.includes(item.id)) resultTableRef.value?.toggleRowSelection(item, true)
    })
  } finally {
    detailLoading.value = false
  }
}

async function switchOe(row) {
  if (row.id === currentOe.value?.id) return
  if (!await confirmDiscardSelection()) return
  await loadOe(row)
}

async function confirmDiscardSelection() {
  if (!selectionChanged.value) return true
  try {
    await ElMessageBox.confirm('当前OE的勾选尚未保存，切换后将放弃本次修改。', '未保存的审核结果', {
      confirmButtonText: '放弃并切换',
      cancelButtonText: '继续审核',
      type: 'warning'
    })
    return true
  } catch (_) {
    return false
  }
}

function handleSelectionChange(rows) {
  selectedItemIds.value = rows.map(row => row.id)
}

function toggleAll(selected) {
  resultTableRef.value?.clearSelection()
  if (selected) currentItems.value.forEach(row => resultTableRef.value?.toggleRowSelection(row, true))
}

async function saveAndNext() {
  if (!currentOe.value || currentOe.value.queryStatus !== 'SUCCESS') return
  savingReview.value = true
  try {
    const response = await reviewEbayAuditOe(task.value.id, currentOe.value.id, {
      selectedItemIds: selectedItemIds.value,
      decision: 'REVIEWED'
    })
    applyTaskView(response.data)
    initialSelectedIds.value = [...selectedItemIds.value]
    const hasNext = currentPosition.value < oes.value.length
    if (hasNext) {
      await loadOe(oes.value[currentPosition.value])
    } else {
      ElMessage.success(task.value.status === 'COMPLETED' ? '全部审核完成，现在可以导出已选商品' : '当前审核已保存，仍有OE正在查询')
    }
  } finally {
    savingReview.value = false
  }
}

async function skipCurrent() {
  savingReview.value = true
  try {
    const response = await reviewEbayAuditOe(task.value.id, currentOe.value.id, {
      selectedItemIds: [],
      decision: 'SKIPPED'
    })
    applyTaskView(response.data)
    await moveRelative(1)
  } finally {
    savingReview.value = false
  }
}

async function retryCurrent() {
  retrying.value = true
  try {
    const response = await retryEbayAuditOe(task.value.id, currentOe.value.id)
    applyTaskView(response.data)
    currentItems.value = []
    selectedItemIds.value = []
    initialSelectedIds.value = []
    ElMessage.success('已重新提交该OE查询')
  } finally {
    retrying.value = false
  }
}

async function goPrevious() {
  if (!await confirmDiscardSelection()) return
  await moveRelative(-1)
}

async function handleTopNext() {
  if (currentOe.value?.queryStatus === 'SUCCESS') {
    await saveAndNext()
    return
  }
  if (currentOe.value?.queryStatus === 'FAILED') {
    try {
      await ElMessageBox.confirm('该OE查询失败。跳过后可继续审核，后续仍能返回重试。', '确认跳过', {
        confirmButtonText: '跳过并继续',
        cancelButtonText: '取消',
        type: 'warning'
      })
      await skipCurrent()
    } catch (_) {
      // 用户取消跳过。
    }
    return
  }
  await moveRelative(1)
}

async function goNextAfterHandled() {
  await moveRelative(1)
}

async function moveRelative(offset) {
  const index = oes.value.findIndex(row => row.id === currentOe.value?.id)
  const next = oes.value[index + offset]
  if (next) await loadOe(next)
}

async function handleExport() {
  exporting.value = true
  try {
    const blob = await exportEbayAuditTask(task.value.id, createRequestId('audit-export'))
    if (!(blob instanceof Blob) || (blob.type && !blob.type.includes('spreadsheetml') && !blob.type.includes('octet-stream'))) {
      throw new Error(await readBlobError(blob))
    }
    saveAs(blob, `eBay审核结果-${task.value.taskName}.xlsx`)
    ElMessage.success('审核结果导出完成')
  } catch (error) {
    ElMessage.error(error?.message || '导出失败')
  } finally {
    exporting.value = false
  }
}

function openNewTask() {
  showUploader.value = true
  uploadFiles.value = []
  uploadFile.value = null
  manualInput.value = ''
}

function cancelNewTask() {
  showUploader.value = false
}

function shortStatus(row) {
  if (row.queryStatus === 'FAILED') return '失败'
  if (row.queryStatus === 'EMPTY') return '无结果'
  if (['PENDING', 'QUERYING'].includes(row.queryStatus)) return '查询中'
  if (row.reviewStatus === 'REVIEWED') return '已审核'
  if (row.reviewStatus === 'SKIPPED') return '已跳过'
  return '待审核'
}

function statusClass(row) {
  if (row.queryStatus === 'FAILED') return 'failed'
  if (row.queryStatus === 'EMPTY') return 'empty'
  if (['PENDING', 'QUERYING'].includes(row.queryStatus)) return 'querying'
  if (row.reviewStatus !== 'PENDING') return 'reviewed'
  return 'pending'
}

function taskStatusText(value) {
  return { QUERYING: '后台查询中', REVIEWING: '等待人工审核', COMPLETED: '审核已完成' }[value] || value
}

function taskStatusType(value) {
  return { QUERYING: 'primary', REVIEWING: 'warning', COMPLETED: 'success' }[value] || 'info'
}

function queryStatusText(value) {
  return { PENDING: '等待查询', QUERYING: '正在查询', SUCCESS: '查询成功', EMPTY: '无结果', FAILED: '查询失败' }[value] || value
}

function queryStatusType(value) {
  return { PENDING: 'info', QUERYING: 'primary', SUCCESS: 'success', EMPTY: 'info', FAILED: 'danger' }[value] || 'info'
}

function reviewStatusText(value) {
  return { REVIEWED: '已审核', SKIPPED: '已跳过', NOT_REQUIRED: '无需审核' }[value] || value
}

function siteLabel(value) {
  return { de: '德国站', uk: '英国站', us: '美国站' }[value] || value
}

function displayProductId(item) {
  if (item?.productId) return item.productId
  const parts = String(item?.itemId || '').split('|')
  return parts.length >= 2 && parts[1] ? parts[1] : (item?.itemId || '商品ID未知')
}

function percent(value, total) {
  return total ? Math.min(100, Math.round((Number(value || 0) / Number(total)) * 100)) : 0
}

function normalizeIds(values) {
  return [...values].map(Number).sort((a, b) => a - b)
}

function splitManualKeywords(value) {
  const unique = new Map()
  String(value || '').split(/[\r\n,，]+/).forEach(item => {
    const normalized = item.trim()
    if (normalized) unique.set(normalized.toUpperCase(), normalized)
  })
  return [...unique.values()]
}

async function readBlobError(blob) {
  try {
    const payload = JSON.parse(await blob.text())
    return payload.msg || payload.message || '导出失败'
  } catch (_) {
    return '导出失败'
  }
}

function createRequestId(action) {
  const random = globalThis.crypto?.randomUUID?.().replaceAll('-', '') || Math.random().toString(16).slice(2)
  return `erp-ebay-${action}-${Date.now()}-${random}`
}
</script>

<style scoped>
.ebay-audit-page {
  min-height: calc(100vh - 84px);
  padding: 18px;
  background: #f4f6f8;
  color: #182230;
}

.page-heading,
.upload-card,
.task-summary,
.review-workbench {
  border: 1px solid #e6eaf0;
  border-radius: 14px;
  background: #fff;
  box-shadow: 0 3px 14px rgb(15 23 42 / 4%);
}

.page-heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 24px;
  padding: 20px 22px;
}

.eyebrow {
  margin-bottom: 4px;
  color: #356fe5;
  font-size: 11px;
  font-weight: 800;
  letter-spacing: 1.3px;
}

.page-heading h2 { margin: 0; font-size: 22px; }
.page-heading p { margin: 7px 0 0; color: #667085; font-size: 13px; }
.heading-actions { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }

.mapping-import-dialog { display: flex; flex-direction: column; gap: 18px; }
.mapping-import-dialog :deep(.el-alert__content) { min-width: 0; }
.mapping-import-dialog :deep(.el-alert__title) { font-weight: 700; }
.mapping-import-dialog :deep(.el-alert__description) { margin-top: 7px; }
.mapping-import-dialog p { margin: 3px 0; color: #667085; font-size: 12px; line-height: 1.65; }
.mapping-file-row { display: flex; min-width: 0; align-items: center; gap: 10px; padding: 15px; border: 1px dashed #cfd8e6; border-radius: 10px; background: #fbfcfe; }
.mapping-file-row > span { overflow: hidden; flex: 1; color: #98a2b3; font-size: 12px; text-overflow: ellipsis; white-space: nowrap; }
.mapping-file-row > span.selected { color: #344054; font-weight: 600; }
.mapping-result { display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; }
.mapping-result > div { display: flex; align-items: center; justify-content: space-between; padding: 11px 12px; border-radius: 8px; background: #f6f8fb; }
.mapping-result span { color: #667085; font-size: 11px; }
.mapping-result strong { color: #356fe5; font-size: 16px; }

.upload-card { margin-top: 14px; overflow: hidden; }
.flow-steps { display: grid; grid-template-columns: repeat(4, 1fr); border-bottom: 1px solid #edf0f4; background: #f9fafb; }
.flow-step { display: flex; align-items: center; gap: 10px; padding: 16px 18px; border-right: 1px solid #edf0f4; }
.flow-step:last-child { border-right: 0; }
.flow-step > span { display: grid; width: 28px; height: 28px; flex: 0 0 28px; place-items: center; border-radius: 50%; background: #eaf1ff; color: #356fe5; font-weight: 700; }
.flow-step div { display: flex; min-width: 0; flex-direction: column; gap: 2px; }
.flow-step strong { font-size: 13px; }
.flow-step small { overflow: hidden; color: #7b8796; font-size: 11px; text-overflow: ellipsis; white-space: nowrap; }
.upload-body { display: grid; grid-template-columns: minmax(340px, .9fr) minmax(430px, 1.1fr); gap: 36px; padding: 34px; }
.upload-copy h3 { margin: 0 0 8px; font-size: 18px; }
.upload-copy p { margin: 0; color: #667085; font-size: 13px; line-height: 1.7; }
.upload-copy ul { margin: 18px 0; padding-left: 20px; color: #475467; font-size: 13px; line-height: 2; }
.site-picker { display: flex; align-items: center; gap: 14px; }
.site-picker > span { color: #475467; font-size: 13px; font-weight: 600; }
.upload-panel { display: flex; flex-direction: column; gap: 14px; padding: 4px; }
.create-method { display: flex; flex-direction: column; gap: 13px; padding: 18px; border: 1px solid #e4e9f0; border-radius: 12px; background: #fbfcfe; }
.create-method > .el-button { align-self: flex-end; }
.method-heading { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
.method-heading > div { display: flex; align-items: baseline; gap: 9px; }
.method-heading strong { color: #27364a; font-size: 14px; }
.method-heading span, .create-method p { color: #7b8796; font-size: 11px; }
.create-method p { margin: 0; }
.file-picker-row { display: flex; min-width: 0; align-items: center; gap: 10px; }
.file-picker-row > span { overflow: hidden; flex: 1; color: #98a2b3; font-size: 12px; text-overflow: ellipsis; white-space: nowrap; }
.file-picker-row > span.selected { color: #344054; font-weight: 600; }
.method-divider { display: flex; align-items: center; gap: 12px; color: #98a2b3; font-size: 11px; }
.method-divider::before, .method-divider::after { height: 1px; flex: 1; background: #e9edf3; content: ''; }
.input-count { color: #356fe5 !important; font-variant-numeric: tabular-nums; }
.upload-actions { display: flex; justify-content: flex-end; gap: 10px; margin-top: 18px; }

.task-summary { display: grid; grid-template-columns: minmax(450px, 1.5fr) minmax(420px, 1fr); gap: 24px; margin-top: 14px; padding: 18px 20px; }
.task-title { display: flex; align-items: flex-start; justify-content: space-between; gap: 16px; margin-bottom: 13px; }
.task-label { color: #7b8796; font-size: 11px; }
.task-title h3 { margin: 2px 0; font-size: 16px; }
.task-title p { margin: 0; color: #7b8796; font-size: 11px; }
.progress-row { display: grid; grid-template-columns: 64px minmax(160px, 1fr) 76px; align-items: center; gap: 12px; margin-top: 8px; }
.progress-row > span { color: #667085; font-size: 12px; }
.progress-row > strong { color: #344054; font-size: 12px; text-align: right; }
.summary-grid { display: grid; grid-template-columns: repeat(5, 1fr); gap: 8px; align-content: center; }
.summary-grid > div { display: flex; align-items: center; flex-direction: column; gap: 4px; padding: 12px 6px; border-radius: 9px; background: #f8fafc; }
.summary-grid span { color: #7b8796; font-size: 11px; }
.summary-grid strong { font-size: 20px; }
.summary-grid .success { color: #079455; }
.summary-grid .danger { color: #d92d20; }
.summary-grid .primary { color: #356fe5; }
.summary-grid .muted-number { color: #667085; }
.file-notice { margin-top: 10px; }

.review-workbench { display: grid; grid-template-columns: 265px minmax(0, 1fr); min-height: 610px; margin-top: 10px; overflow: hidden; }
.oe-sidebar { display: flex; min-height: 0; flex-direction: column; gap: 10px; padding: 14px; border-right: 1px solid #e9edf3; background: #fbfcfd; }
.sidebar-heading { display: flex; align-items: center; justify-content: space-between; }
.sidebar-heading > div { display: flex; align-items: baseline; gap: 8px; }
.sidebar-heading strong { font-size: 15px; }
.sidebar-heading span { color: #98a2b3; font-size: 11px; }
.status-filter { width: 100%; }
.oe-list { display: flex; max-height: calc(100vh - 390px); min-height: 430px; flex-direction: column; gap: 5px; overflow-y: auto; }
.oe-row { display: grid; grid-template-columns: 28px minmax(0, 1fr) auto; gap: 7px; align-items: center; width: 100%; padding: 9px 8px; border: 1px solid transparent; border-radius: 8px; background: transparent; color: inherit; text-align: left; cursor: pointer; }
.oe-row:hover { background: #f1f5fb; }
.oe-row.active { border-color: #b8ccf7; background: #eaf1ff; }
.oe-index { color: #98a2b3; font-size: 11px; text-align: center; }
.oe-name { overflow: hidden; font-size: 12px; font-weight: 600; text-overflow: ellipsis; white-space: nowrap; }
.oe-state { padding: 2px 6px; border-radius: 8px; font-size: 10px; white-space: nowrap; }
.oe-state.querying { background: #eef4ff; color: #356fe5; }
.oe-state.pending { background: #fff6e8; color: #b54708; }
.oe-state.reviewed { background: #ecfdf3; color: #027a48; }
.oe-state.empty { background: #f2f4f7; color: #667085; }
.oe-state.failed { background: #fff1f0; color: #b42318; }
.oe-row small { grid-column: 2 / 4; color: #356fe5; font-size: 10px; }

.review-main { min-width: 0; }
.review-heading { display: flex; align-items: center; justify-content: space-between; gap: 18px; padding: 16px 18px; border-bottom: 1px solid #edf0f4; }
.review-position { color: #356fe5; font-size: 12px; font-weight: 700; }
.current-oe-line { display: flex; align-items: center; gap: 8px; margin-top: 3px; }
.current-oe-line h3 { margin: 0; font-size: 19px; }
.review-heading p { margin: 5px 0 0; color: #7b8796; font-size: 11px; }
.position-jump { display: flex; gap: 8px; }
.state-panel { display: flex; min-height: 470px; align-items: center; justify-content: center; flex-direction: column; padding: 40px; text-align: center; }
.state-panel h3 { margin: 15px 0 6px; }
.state-panel p { max-width: 620px; margin: 0 0 18px; color: #667085; font-size: 13px; line-height: 1.7; }
.state-panel .el-alert { max-width: 700px; margin: 0 0 18px; text-align: left; }
.state-icon { display: grid; width: 58px; height: 58px; place-items: center; border-radius: 50%; font-size: 25px; }
.state-icon.loading { background: #eef4ff; color: #356fe5; }
.state-icon.loading .el-icon { animation: rotating 1.5s linear infinite; }
.state-icon.empty { background: #f2f4f7; color: #667085; }
.state-icon.failed { background: #fff1f0; color: #d92d20; }
.selection-bar { display: flex; align-items: center; justify-content: space-between; gap: 16px; padding: 11px 18px; border-bottom: 1px solid #edf0f4; background: #fcfcfd; }
.selection-bar > div { display: flex; align-items: center; gap: 8px; }
.selection-bar strong { font-size: 13px; }
.selection-bar span { color: #7b8796; font-size: 11px; }
.selection-bar b { color: #356fe5; font-size: 14px; }
.image-cell { position: relative; width: 64px; }
.product-image { width: 62px; height: 62px; overflow: hidden; border: 1px solid #eaecf0; border-radius: 8px; background: #f8fafc; }
.image-cell > span { position: absolute; right: -2px; bottom: 3px; padding: 1px 5px; border-radius: 8px; background: rgb(17 24 39 / 72%); color: #fff; font-size: 10px; }
.rank-badge { display: inline-grid; width: 27px; height: 27px; place-items: center; border-radius: 8px; background: #ecfdf3; color: #027a48; font-size: 11px; font-weight: 700; }
.product-info { display: flex; min-width: 0; flex-direction: column; gap: 5px; }
.product-info > div { display: flex; align-items: center; gap: 8px; color: #7b8796; font-size: 11px; }
.product-info strong { display: -webkit-box; overflow: hidden; color: #243244; font-size: 13px; font-weight: 500; line-height: 1.45; -webkit-box-orient: vertical; -webkit-line-clamp: 2; }
.product-info small { color: #b54708; font-size: 10px; }
.price-cell, .seller-cell { display: flex; flex-direction: column; gap: 4px; }
.price-cell { align-items: flex-end; }
.price-cell strong { color: #b54708; font-variant-numeric: tabular-nums; white-space: nowrap; }
.price-cell small, .seller-cell small { color: #7b8796; font-size: 10px; }
.seller-cell span { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.muted { color: #98a2b3; font-size: 11px; }
.review-footer { display: flex; align-items: center; justify-content: space-between; gap: 20px; padding: 14px 18px; border-top: 1px solid #edf0f4; }
.review-footer > div { display: flex; align-items: center; gap: 7px; color: #667085; font-size: 11px; }
.history-list { display: flex; flex-direction: column; gap: 9px; }
.history-row { width: 100%; padding: 13px 14px; border: 1px solid #e6eaf0; border-radius: 10px; background: #fff; color: inherit; text-align: left; cursor: pointer; }
.history-row:hover { border-color: #b8ccf7; background: #f8faff; }
.history-row.active { border-color: #7da2ef; background: #eef4ff; }
.history-row > div { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
.history-row-actions { display: flex; align-items: center; gap: 4px; }
.history-row strong { overflow: hidden; font-size: 13px; text-overflow: ellipsis; white-space: nowrap; }
.history-row p { margin: 7px 0 4px; overflow: hidden; color: #667085; font-size: 11px; text-overflow: ellipsis; white-space: nowrap; }
.history-row > span { color: #98a2b3; font-size: 10px; }

:deep(.el-table th.el-table__cell) { background: #f7f8fa; color: #475467; font-weight: 600; }

@media (max-width: 1200px) {
  .task-summary { grid-template-columns: 1fr; }
  .upload-body { grid-template-columns: 1fr; }
}

@media (max-width: 900px) {
  .flow-steps { grid-template-columns: 1fr 1fr; }
  .review-workbench { grid-template-columns: 1fr; }
  .oe-sidebar { border-right: 0; border-bottom: 1px solid #e9edf3; }
  .oe-list { max-height: 260px; min-height: 160px; }
}

@media (max-width: 680px) {
  .ebay-audit-page { padding: 10px; }
  .page-heading, .heading-actions, .review-heading, .selection-bar, .review-footer { align-items: flex-start; flex-direction: column; }
  .flow-steps, .summary-grid { grid-template-columns: 1fr 1fr; }
  .upload-body { padding: 20px; }
  .position-jump, .review-footer .el-button { width: 100%; }
}
</style>
