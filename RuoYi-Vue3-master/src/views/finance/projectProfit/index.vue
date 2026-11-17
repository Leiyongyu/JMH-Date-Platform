<template>
  <div class="app-container project-profit">
    <!-- 筛选栏 -->
    <div class="filter-bar">
      <span class="f-label">统计月份</span>
      <el-date-picker v-model="statMonth" type="month" value-format="YYYY-MM" format="YYYY-MM" :clearable="false"
        class="month-select" placeholder="选择月份" @change="loadReport" />
      <span class="f-hint">
        人民币 · AMZ {{ report?.amz_upload ? `${report.amz_upload.file_name}（${report.amz_upload.uploaded_at}）` : '未上传' }}
        · eBay {{ report?.ebay_upload ? `${report.ebay_upload.file_name}（${report.ebay_upload.uploaded_at}）` : '未上传' }}
      </span>
      <el-tooltip content="页面逻辑与数据来源" placement="left">
        <button type="button" class="icon-btn help-btn" aria-label="页面逻辑与数据来源" @click="helpVisible = true">
          <app-icon name="help" :size="15" />
        </button>
      </el-tooltip>
    </div>

    <div v-for="text in report?.notices || []" :key="text" class="notice notice--warning" role="alert">
      <div class="notice__icon">
        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round">
          <path d="M12 4l9 16H3z" /><path d="M12 10v4" /><path d="M12 17.2h.01" />
        </svg>
      </div>
      <div class="notice__body"><div class="notice__desc">{{ text }}</div></div>
    </div>

    <div class="table-card">
      <div class="tc-head">
        <div>
          <div class="tc-title">项目利润总表<template v-if="report"> · {{ report.stat_month }}</template></div>
          <div class="tc-sub">{{ subtitle }}</div>
        </div>
        <div class="tc-actions">
          <div class="chips" role="tablist" aria-label="报表">
            <button v-for="item in views" :key="item.value" type="button" class="chip"
              :class="{ active: view === item.value }" role="tab" :aria-selected="view === item.value"
              @click="view = item.value">{{ item.label }}</button>
          </div>
          <el-upload v-hasPermi="['finance:projectProfit:edit']" :show-file-list="false" accept=".xlsx"
            :http-request="handleAmzUpload" :disabled="uploadingAmz || !statMonth">
            <el-button plain :loading="uploadingAmz" :disabled="!statMonth">
              <app-icon v-if="!uploadingAmz" name="upload" :size="15" class="btn-icon" />
              {{ uploadingAmz ? '读取中…' : report?.amz_upload ? '重新上传领星' : '上传领星利润报表' }}
            </el-button>
          </el-upload>
          <el-upload v-hasPermi="['finance:projectProfit:edit']" :show-file-list="false" accept=".xlsx"
            :http-request="handleEbayUpload" :disabled="uploading || !statMonth">
            <el-button plain :loading="uploading" :disabled="!statMonth">
              <app-icon v-if="!uploading" name="upload" :size="15" class="btn-icon" />
              {{ uploading ? '读取中…' : report?.ebay_upload ? '重新上传 eBay' : '上传 eBay 利润表' }}
            </el-button>
          </el-upload>
          <el-button v-hasPermi="['finance:projectProfit:edit']" type="primary" :disabled="!report" @click="openEditor">
            <app-icon name="edit" :size="15" class="btn-icon" />录入手工项
          </el-button>
          <el-tooltip content="刷新" placement="top">
            <button type="button" class="icon-btn" aria-label="刷新" :disabled="loading || !statMonth" @click="loadReport">
              <app-icon name="refresh" :size="17" :spin="loading" class="report-icon" />
            </button>
          </el-tooltip>
          <span v-hasPermi="['finance:projectProfit:export']" class="export-entry">
            <el-tooltip content="导出 Excel（小组表、店铺维度两张表）" placement="top">
              <button type="button" class="icon-btn" aria-label="导出 Excel" :disabled="!report || exporting" @click="handleExport">
                <app-icon name="export" :size="17" class="report-icon" />
              </button>
            </el-tooltip>
          </span>
        </div>
      </div>

      <!-- 小组项目利润表 -->
      <el-table v-if="view === 'group'" key="group-table" v-loading="loading" class="report-table"
        :data="report?.statement || []" :span-method="categorySpan" :row-class-name="statementRowClass"
        max-height="720" empty-text="暂无数据">
        <el-table-column label="类别" width="118" fixed="left" class-name="cat-col">
          <template #default="{ row }"><span class="cat">{{ row.category }}</span></template>
        </el-table-column>
        <el-table-column label="项目" min-width="250" fixed="left">
          <template #default="{ row }">
            <span class="item" :class="{ indent: row.indent, strong: row.strong, memo: row.memo }">{{ row.label }}</span>
            <span v-if="row.memo" class="memo-tag">仅展示</span>
          </template>
        </el-table-column>
        <el-table-column v-for="group in report?.groups || []" :key="group.code" :label="group.label"
          min-width="122" align="right" :class-name="group.code === 'TOTAL' ? 'total-col' : ''">
          <template #default="{ row }">
            <span class="v" :class="valueClass(row, group.code)" :title="sourceTitle(row, group.code)">
              {{ display(row, row.values[group.code]) }}
            </span>
            <i v-if="row.sources?.[group.code] === 'MANUAL'" class="src-dot src-dot--manual" />
            <i v-else-if="row.sources?.[group.code] === 'UPLOAD'" class="src-dot src-dot--upload" />
          </template>
        </el-table-column>
        <el-table-column label="标准" min-width="150">
          <template #default="{ row }"><span class="target">{{ row.target || '' }}</span></template>
        </el-table-column>
      </el-table>

      <!-- 店铺维度利润表 -->
      <el-table v-else key="store-table" v-loading="loading" class="report-table" :data="storeRows"
        :row-class-name="storeRowClass" max-height="720" empty-text="暂无数据">
        <el-table-column label="组别" width="84" fixed="left">
          <template #default="{ row }">
            <span v-if="row.row_type === 'ENTITY'" class="g-tag"><i />{{ row.group_code }}</span>
          </template>
        </el-table-column>
        <el-table-column label="主体" min-width="110" fixed="left">
          <template #default="{ row }"><span :class="row.row_type === 'ENTITY' ? 'shop-name' : 'sum-label'">{{ row.entity }}</span></template>
        </el-table-column>
        <el-table-column v-for="column in report?.stores?.columns || []" :key="column.key" :label="column.label"
          :min-width="column.key === 'sales_qty' ? 86 : 124" align="right">
          <template #default="{ row }">
            <span class="v" :class="{ neg: ['gross_profit', 'platform_receipt'].includes(column.key) && row[column.key] < 0 }">
              {{ column.key === 'sales_qty' ? formatQty(row[column.key]) : formatMoney(row[column.key]) }}
            </span>
          </template>
        </el-table-column>
      </el-table>

      <div class="tc-foot">
        <span>费用为负数表示支出；比率分母为 0 时显示 --</span>
        <span v-if="view === 'group'" class="legend">
          <i class="src-dot src-dot--upload" />eBay 上传 <i class="src-dot src-dot--manual" />手工录入
          <b class="lv lv--red">红</b>/<b class="lv lv--yellow">黄</b> 超出标准
        </span>
      </div>
    </div>

    <!-- 页面逻辑与数据来源 -->
    <el-drawer v-model="helpVisible" title="项目利润总表 · 逻辑与数据来源" size="640px" append-to-body>
      <div class="help">
        <section v-if="report?.amz_upload" class="help-sec">
          <div class="help-h">本月领星利润报表上传</div>
          <div class="help-kv">
            <div><span>文件</span><b>{{ report.amz_upload.file_name }}</b></div>
            <div><span>上传</span><b>{{ report.amz_upload.uploaded_by || '--' }} · {{ report.amz_upload.uploaded_at }}</b></div>
            <div><span>行数</span><b>{{ formatQty(report.amz_upload.msku_rows) }} 行 · {{ formatQty(report.amz_upload.check.stores) }} 个店铺</b></div>
            <div><span>平台收入</span><b>{{ formatMoney(report.amz_upload.check.platform_income) }}</b></div>
            <div><span>毛利润</span><b>{{ formatMoney(report.amz_upload.check.gross_profit) }}</b></div>
          </div>
        </section>
        <section v-if="report?.ebay_upload" class="help-sec">
          <div class="help-h">本月 eBay 上传</div>
          <div class="help-kv">
            <div><span>文件</span><b>{{ report.ebay_upload.file_name }}</b></div>
            <div><span>上传</span><b>{{ report.ebay_upload.uploaded_by || '--' }} · {{ report.ebay_upload.uploaded_at }}</b></div>
            <div><span>汇总毛利</span><b>{{ formatMoney(report.ebay_upload.check.gross_profit) }}</b></div>
            <div><span>口径差</span><b>{{ formatMoney(report.ebay_upload.check.method_diff) }}（平台支出-总 与 净收入−收入 之差 + 资金占用费）</b></div>
            <div><span>核对差额</span><b>{{ formatMoney(report.ebay_upload.check.gross_diff) }}</b></div>
          </div>
        </section>
        <section class="help-sec">
          <div class="help-h">数据来源</div>
          <div class="help-kv">
            <div v-for="item in sourceInfo" :key="item.label"><span>{{ item.label }}</span><b>{{ item.value }}</b></div>
          </div>
        </section>
        <section class="help-sec">
          <div class="help-h">整体逻辑</div>
          <ol class="help-steps">
            <li v-for="(step, index) in logicSteps" :key="step.title">
              <i>{{ index + 1 }}</i><div><b>{{ step.title }}</b><p>{{ step.text }}</p></div>
            </li>
          </ol>
        </section>
        <section class="help-sec">
          <div class="help-h">如何核对</div>
          <ol class="help-check">
            <li v-for="text in checkSteps" :key="text">{{ text }}</li>
          </ol>
        </section>
      </div>
    </el-drawer>

    <!-- 录入手工项 -->
    <el-dialog v-model="editorVisible" :title="`录入手工项 · ${statMonth || ''}`" width="1080px" append-to-body top="6vh">
      <div class="adjust-note">
        按表内正负填写（支出为负数、抵扣与加回为正数），留空表示不填；退款率填百分数。AMZ 的订单销量、退款率留空时用领星数，
        填了就覆盖。eBay 列的上传项也可以在这里改，重新上传会覆盖这些上传项。
      </div>
      <el-table :data="editorRows" size="small" max-height="560" class="editor-table">
        <el-table-column label="项目" min-width="230" fixed="left">
          <template #default="{ row }">
            <span class="item" :class="{ indent: row.indent }">{{ row.label }}</span>
            <span v-if="row.unit === 'rate'" class="memo-tag">%</span>
          </template>
        </el-table-column>
        <el-table-column v-for="group in editGroups" :key="group.code" :label="group.label" min-width="138">
          <template #default="{ row }">
            <el-input v-if="row.editable.includes(group.code)" v-model="editForm[group.code][row.code]" size="small"
              clearable :placeholder="placeholder(row, group.code)" class="cell-input" />
            <span v-else class="muted">自动</span>
          </template>
        </el-table-column>
      </el-table>
      <template #footer>
        <el-button @click="editorVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="submitEditor">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup name="ProjectProfit">
import { computed, getCurrentInstance, onMounted, reactive, ref } from 'vue'
import { checkSteps, logicSteps, sourceInfo } from './help'
import {
  exportProjectProfit, getProjectProfit, importProjectProfitAmz, importProjectProfitEbay, saveProjectProfitItems
} from '@/api/finance/projectProfit'

const { proxy } = getCurrentInstance()
const views = [
  { value: 'group', label: '小组项目利润表' },
  { value: 'store', label: '店铺维度利润表' }
]

function previousMonth() {
  const now = new Date()
  const date = new Date(now.getFullYear(), now.getMonth() - 1, 1)
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}`
}

const statMonth = ref(previousMonth())
const view = ref('group')
const loading = ref(false)
const exporting = ref(false)
const uploading = ref(false)
const uploadingAmz = ref(false)
const report = ref(null)
const helpVisible = ref(false)
let requestSeq = 0

const subtitle = computed(() => {
  const data = report.value
  if (!data) return '选择月份查看；AMZ 需上传领星利润报表-MSKU（人民币），eBay 需上传财务利润明细表'
  if (view.value === 'store') {
    const entities = data.stores.rows.filter(row => row.row_type === 'ENTITY').length
    return `AMZ ${entities} 个主体（按组别汇总，关停店铺照手工表计入）`
  }
  return 'eBay / EU / US1 / US2 / US3 / 合计；行与公式照财务手工表'
})

const storeRows = computed(() => {
  const stores = report.value?.stores
  return stores ? [...stores.rows, stores.total] : []
})

function formatMoney(value) {
  if (value === null || value === undefined || value === '') return '--'
  return Number(value).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function formatQty(value) {
  if (value === null || value === undefined || value === '') return '--'
  return Number(value).toLocaleString('zh-CN', { maximumFractionDigits: 2 })
}

function display(row, value) {
  if (value === null || value === undefined || value === '') return '--'
  if (row.unit === 'rate') return `${(Number(value) * 100).toFixed(2)}%`
  if (row.unit === 'qty') return formatQty(value)
  return formatMoney(value)
}

function valueClass(row, group) {
  const level = row.levels?.[group]
  return {
    strong: row.strong,
    memo: row.memo,
    neg: ['project_gross', 'group_net', 'net_profit', 'gross_margin', 'net_margin'].includes(row.code) && row.values[group] < 0,
    'lv--red': level === 'red',
    'lv--yellow': level === 'yellow'
  }
}

function sourceTitle(row, group) {
  const source = row.sources?.[group]
  if (source === 'CARRY') return '本月未填，沿用当年最近一次填写的年度目标'
  return source === 'MANUAL' ? '手工录入' : source === 'UPLOAD' ? 'eBay 利润明细表上传' : ''
}

// 「类别」列按相邻同类别合并单元格。
function categorySpan({ row, rowIndex, columnIndex }) {
  if (columnIndex !== 0) return undefined
  const rows = report.value?.statement || []
  if (rowIndex > 0 && rows[rowIndex - 1].category === row.category) return { rowspan: 0, colspan: 0 }
  let span = 1
  while (rowIndex + span < rows.length && rows[rowIndex + span].category === row.category) span += 1
  return { rowspan: span, colspan: 1 }
}

function statementRowClass({ row }) {
  if (['project_gross', 'net_profit'].includes(row.code)) return 'report-total-row'
  if (row.strong) return 'report-sub-row'
  return ''
}

function storeRowClass({ row }) {
  if (row.row_type === 'TOTAL') return 'report-total-row'
  if (row.row_type === 'GROUP') return 'report-sub-row'
  return ''
}

async function loadReport() {
  if (!statMonth.value) {
    report.value = null
    return
  }
  const seq = ++requestSeq
  loading.value = true
  try {
    const response = await getProjectProfit(statMonth.value)
    if (seq === requestSeq) report.value = response.data || null
  } catch {
    if (seq === requestSeq) report.value = null
  } finally {
    if (seq === requestSeq) loading.value = false
  }
}

async function handleAmzUpload({ file }) {
  uploadingAmz.value = true
  try {
    const response = await importProjectProfitAmz(statMonth.value, file)
    const check = response.data?.check || {}
    proxy.$modal.msgSuccess(`已上传 ${response.data?.stat_month} 领星利润报表：${formatQty(check.rows)} 行、${formatQty(check.stores)} 个店铺，平台收入 ${formatMoney(check.platform_income)}`)
    await loadReport()
  } finally {
    uploadingAmz.value = false
  }
}

async function handleEbayUpload({ file }) {
  uploading.value = true
  try {
    const response = await importProjectProfitEbay(statMonth.value, file)
    const data = response.data || {}
    const diff = Number(data.check?.gross_diff || 0)
    const missing = (data.missing || []).length ? `；未读到：${data.missing.join('、')}` : ''
    if (Math.abs(diff) > 1) proxy.$modal.msgWarning(`已上传，但按小组表公式算出的 eBay 毛利与汇总相差 ${formatMoney(diff)}${missing}`)
    else proxy.$modal.msgSuccess(`已上传 ${data.stat_month} eBay 利润明细表，毛利核对一致${missing}`)
    await loadReport()
  } finally {
    uploading.value = false
  }
}

async function handleExport() {
  exporting.value = true
  try {
    const data = await exportProjectProfit(statMonth.value)
    const blob = data instanceof Blob
      ? data
      : new Blob([data], { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = `项目利润总表-${statMonth.value}.xlsx`
    document.body.appendChild(link)
    link.click()
    link.remove()
    URL.revokeObjectURL(url)
    proxy.$modal.msgSuccess('导出成功')
  } catch (error) {
    const responseData = error?.response?.data
    const message = responseData instanceof Blob
      ? await responseData.text()
      : String(responseData?.msg || error?.message || '导出失败')
    proxy.$modal.msgError(message || '导出失败')
  } finally {
    exporting.value = false
  }
}

// ---------------- 录入手工项
const editorVisible = ref(false)
const saving = ref(false)
const editGroups = computed(() => (report.value?.groups || []).filter(group => group.code !== 'TOTAL'))
const editorRows = computed(() => (report.value?.statement || []).filter(row => row.editable.length))
const editForm = reactive({})
let original = {}

function toInput(row, value) {
  if (value === null || value === undefined) return ''
  return row.unit === 'rate' ? String(Number((Number(value) * 100).toFixed(4))) : String(value)
}

function placeholder(row, group) {
  if (row.sources?.[group] === 'AUTO') return `领星 ${display(row, row.values[group])}`
  if (row.sources?.[group] === 'CARRY') return `沿用 ${display(row, row.values[group])}`
  return row.unit === 'rate' ? '如 8.5' : ''
}

function openEditor() {
  original = {}
  for (const group of editGroups.value) {
    editForm[group.code] = {}
    original[group.code] = {}
    for (const row of editorRows.value) {
      if (!row.editable.includes(group.code)) continue
      const source = row.sources?.[group.code]
      const value = source === 'MANUAL' || source === 'UPLOAD' ? toInput(row, row.values[group.code]) : ''
      editForm[group.code][row.code] = value
      original[group.code][row.code] = value
    }
  }
  editorVisible.value = true
}

async function submitEditor() {
  const items = []
  for (const row of editorRows.value) {
    for (const group of editGroups.value) {
      if (!row.editable.includes(group.code)) continue
      const text = String(editForm[group.code][row.code] ?? '').replace(/,/g, '').trim()
      if (text === String(original[group.code][row.code] ?? '').trim()) continue
      if (text !== '' && !Number.isFinite(Number(text))) {
        proxy.$modal.msgError(`${group.label}「${row.label}」不是数字`)
        return
      }
      const amount = text === '' ? '' : row.unit === 'rate' ? String(Number(text) / 100) : text
      items.push({ groupCode: group.code, itemCode: row.code, amount })
    }
  }
  if (!items.length) {
    editorVisible.value = false
    return
  }
  saving.value = true
  try {
    await saveProjectProfitItems({ statMonth: statMonth.value, items })
    proxy.$modal.msgSuccess(`已保存 ${items.length} 项`)
    editorVisible.value = false
    await loadReport()
  } finally {
    saving.value = false
  }
}

onMounted(loadReport)
</script>

<style scoped>
.project-profit {
  --sky-50: #f4f8ff;
  --sky-100: #e7efff;
  --sky-200: #c9dcfb;
  --sky-300: #a9c6f4;
  --sky-600: #1257d6;
  --sky-700: #0e45a8;
  --teal-500: #12b2a6;
  --ink-900: #0b1526;
  --ink-700: #24334a;
  --ink-500: #5a6b85;
  --ink-400: #8a99b0;
  --line: #e3e9f2;
  --radius: 14px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.filter-bar {
  background: #fff;
  border: 1px solid var(--line);
  border-radius: var(--radius);
  padding: 14px 18px;
  display: flex;
  align-items: center;
  gap: 14px;
  flex-wrap: wrap;
  box-shadow: 0 2px 10px rgba(13, 26, 45, .06);
}
.f-label { font-size: 13.5px; color: var(--ink-700); font-weight: 500; }
.f-hint { font-size: 12px; color: var(--ink-400); }
.month-select { width: 150px; }

.notice {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  padding: 10px 14px;
  background: linear-gradient(100deg, #fffbef, #fffdf7);
  border: 1px solid #fce3b0;
  border-radius: 12px;
}
.notice__icon {
  width: 28px;
  height: 28px;
  flex-shrink: 0;
  border-radius: 9px;
  background: #fdf1d4;
  color: #b26b09;
  display: flex;
  align-items: center;
  justify-content: center;
}
.notice__body { flex: 1; min-width: 0; }
.notice__desc { font-size: 12.5px; color: #8a5a12; line-height: 28px; }

.table-card {
  background: #fff;
  border: 1px solid var(--line);
  border-radius: var(--radius);
  box-shadow: 0 2px 10px rgba(13, 26, 45, .06);
  overflow: hidden;
}
.tc-head {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 14px 18px;
  border-bottom: 1px solid var(--line);
  flex-wrap: wrap;
}
.tc-title { font-size: 14.5px; font-weight: 650; color: var(--ink-900); }
.tc-sub { font-size: 12px; color: var(--ink-400); margin-top: 4px; }
.tc-actions { margin-left: auto; display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.chips {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  background: #f5f8fd;
  border: 1px solid var(--line);
  border-radius: 9px;
  padding: 3px;
}
.chip {
  font-size: 12.5px;
  font-weight: 500;
  font-family: inherit;
  padding: 5px 14px;
  border-radius: 7px;
  border: none;
  background: transparent;
  color: var(--ink-500);
  cursor: pointer;
  white-space: nowrap;
}
.chip:hover { color: var(--sky-600); background: #fff; }
.chip.active { background: #fff; color: var(--sky-700); box-shadow: 0 1px 4px rgba(18, 87, 214, .22); font-weight: 600; }
.btn-icon { margin-right: 4px; }
.export-entry { display: inline-flex; }
.icon-btn {
  width: 34px;
  height: 34px;
  border-radius: 9px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border: 1px solid var(--line);
  background: #fff;
  cursor: pointer;
}
.icon-btn:hover { border-color: var(--sky-300); background: var(--sky-50); }
.icon-btn:disabled { opacity: .4; cursor: not-allowed; }
.report-icon { color: #1257d6; }
.help-btn { margin-left: auto; color: #1257d6; }

.report-table {
  --el-table-border-color: var(--jb-line, #e3e9f2);
  --el-table-header-bg-color: #f7f9fc;
  --el-table-row-hover-bg-color: rgba(18, 87, 214, 0.055);
  --el-table-text-color: var(--ink-700);
  --el-table-header-text-color: var(--ink-500);
  font-size: 12.5px;
}
.report-table :deep(th.el-table__cell) { font-size: 11.5px; font-weight: 600; border-bottom: 1px solid var(--jb-line, #e3e9f2) !important; }
.report-table :deep(.el-table__cell) { padding: 8px 0; }
.report-table :deep(.report-total-row) { background: #eef3fd; font-weight: 600; }
.report-table :deep(.report-sub-row) { background: #fafcff; }
.report-table :deep(td.cat-col) { background: #fbfcfe; vertical-align: middle; }
.report-table :deep(td.total-col) { background: #f7faff; }
.cat { font-size: 12px; font-weight: 600; color: var(--ink-500); }
.item { color: var(--ink-900); }
.item.indent { padding-left: 14px; color: var(--ink-700); }
.item.strong { font-weight: 650; }
.item.memo { color: var(--ink-500); }
.memo-tag {
  margin-left: 6px;
  font-size: 11px;
  padding: 0 6px;
  border-radius: 6px;
  color: var(--ink-500);
  background: #f1f4f9;
}
.v { font-variant-numeric: tabular-nums; }
.v.strong { font-weight: 650; color: var(--ink-900); }
.v.memo { color: var(--ink-500); }
.v.neg { color: #dc2626; }
.v.lv--red { color: #dc2626; font-weight: 600; }
.v.lv--yellow { color: #b26b09; font-weight: 600; }
.src-dot { display: inline-block; width: 5px; height: 5px; border-radius: 50%; margin-left: 4px; vertical-align: middle; }
.src-dot--manual { background: var(--teal-500); }
.src-dot--upload { background: var(--sky-600); }
.target { font-size: 12px; color: var(--ink-400); }
.g-tag { display: inline-flex; align-items: center; gap: 6px; font-weight: 600; color: var(--sky-700); }
.g-tag i { width: 6px; height: 6px; border-radius: 50%; background: var(--sky-600); }
.shop-name { color: var(--ink-900); }
.sum-label { font-weight: 650; color: var(--ink-900); }
.tc-foot {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  padding: 10px 18px;
  font-size: 12px;
  color: var(--ink-400);
  border-top: 1px solid var(--line);
  flex-wrap: wrap;
}
.legend { display: inline-flex; align-items: center; gap: 4px; }
.legend .src-dot { margin-left: 8px; }
.lv { font-weight: 600; }
.lv--red { color: #dc2626; }
.lv--yellow { color: #b26b09; margin-right: 4px; }

/* 抽屉、弹窗挂在 body 下，取不到页面根上的 CSS 变量，颜色直接写值。 */
.help { display: flex; flex-direction: column; gap: 18px; padding: 0 4px 12px; color: #24334a; font-size: 13px; }
.help-h { font-size: 14px; font-weight: 650; color: #0b1526; margin-bottom: 8px; padding-left: 8px; border-left: 3px solid #1257d6; }
.help-kv { display: flex; flex-direction: column; gap: 6px; }
.help-kv > div { display: flex; gap: 12px; line-height: 1.6; }
.help-kv span { flex: 0 0 88px; color: #5a6b85; }
.help-kv b { font-weight: 500; color: #0b1526; }
.help-steps { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 10px; }
.help-steps li { display: flex; gap: 10px; }
.help-steps i {
  flex: 0 0 22px;
  height: 22px;
  border-radius: 50%;
  background: #e4f2fe;
  color: #0b6b98;
  font-style: normal;
  font-size: 12px;
  font-weight: 600;
  display: flex;
  align-items: center;
  justify-content: center;
}
.help-steps b { color: #0b1526; }
.help-steps p { margin: 2px 0 0; line-height: 1.7; color: #24334a; }
.help-check { margin: 0; padding-left: 18px; line-height: 1.8; }
.help-check li + li { margin-top: 4px; }

.adjust-note { font-size: 12.5px; color: #5a6b85; line-height: 1.7; margin-bottom: 10px; }
.editor-table .item.indent { padding-left: 14px; }
.editor-table .memo-tag { margin-left: 6px; font-size: 11px; padding: 0 6px; border-radius: 6px; color: #5a6b85; background: #f1f4f9; }
.cell-input :deep(input) { text-align: right; font-variant-numeric: tabular-nums; }
.muted { color: #8a99b0; font-size: 12px; }
</style>
