<template>
  <div class="app-container amz-monthly-profit">
    <!-- 筛选栏 -->
    <div class="filter-bar">
      <span class="f-label">统计月份</span>
      <el-select v-model="statMonth" class="month-select" placeholder="请选择月份" :loading="monthsLoading"
        :disabled="!months.length" @change="loadReport">
        <el-option v-for="item in months" :key="item.stat_month" :label="item.stat_month" :value="item.stat_month" />
      </el-select>
      <span class="f-hint">
        <template v-if="report">统计期 {{ report.period }} · 人民币 · 拉取于 {{ report.pulled_at || '--' }}</template>
        <template v-else>只能选择已拉取领星利润报表的月份；每月 7 日 06:00 自动拉取上个月</template>
      </span>
      <el-tooltip content="页面逻辑与数据来源" placement="left">
        <button type="button" class="icon-btn help-btn" aria-label="页面逻辑与数据来源" @click="helpVisible = true">
          <app-icon name="help" :size="15" />
        </button>
      </el-tooltip>
    </div>

    <!-- 提示（拉取不完整、未单列的自定义费用等） -->
    <div v-for="text in report?.notices || []" :key="text" class="notice notice--warning" role="alert">
      <div class="notice__icon">
        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round">
          <path d="M12 4l9 16H3z" /><path d="M12 10v4" /><path d="M12 17.2h.01" />
        </svg>
      </div>
      <div class="notice__body"><div class="notice__desc">{{ text }}</div></div>
    </div>

    <!-- 数据表格 -->
    <div class="table-card">
      <div class="tc-head">
        <div>
          <div class="tc-title">AMZ月度利润表<template v-if="report"> · {{ report.stat_month }}</template></div>
          <div class="tc-sub">{{ subtitle }}</div>
        </div>
        <div class="tc-actions">
          <div class="chips" role="tablist" aria-label="报表">
            <button v-for="item in views" :key="item.value" type="button" class="chip"
              :class="{ active: view === item.value }" role="tab" :aria-selected="view === item.value"
              @click="view = item.value">{{ item.label }}</button>
          </div>
          <el-button v-hasPermi="['finance:amzMonthlyProfit:edit']" plain :disabled="!report" @click="openAdjustments">
            补充费用<template v-if="report?.adjustment_count">（{{ report.adjustment_count }}）</template>
          </el-button>
          <el-tooltip content="刷新" placement="top">
            <button type="button" class="icon-btn" aria-label="刷新" :disabled="loading || !statMonth" @click="loadReport">
              <app-icon name="refresh" :size="17" :spin="loading" class="report-icon" />
            </button>
          </el-tooltip>
          <span v-hasPermi="['finance:amzMonthlyProfit:export']" class="export-entry">
            <el-tooltip content="导出 Excel（店铺利润、小组利润两张表）" placement="top">
              <button type="button" class="icon-btn" aria-label="导出 Excel" :disabled="!report || exporting" @click="handleExport">
                <app-icon name="export" :size="17" class="report-icon" />
              </button>
            </el-tooltip>
          </span>
        </div>
      </div>

      <el-table v-loading="loading" class="report-table" :data="tableRows" :row-class-name="rowClassName"
        max-height="640" empty-text="暂无数据">
        <el-table-column label="组别" min-width="90" fixed="left">
          <template #default="{ row }">
            <span v-if="row.isTotal" class="sum-label">合计</span>
            <span v-else-if="view === 'group' && row.row_type === 'SUBTEAM'" class="sub-label">└ {{ row.row_code }}</span>
            <span v-else class="g-tag"><i />{{ view === 'group' ? row.row_code : row.group_code }}</span>
          </template>
        </el-table-column>
        <el-table-column v-if="view === 'store'" label="店铺名" min-width="120" fixed="left">
          <template #default="{ row }">
            <span class="shop-name">{{ row.isTotal ? '' : row.store_name }}</span>
            <span v-if="!row.isTotal && row.subteam_code" class="team-tag">{{ row.subteam_code }}</span>
          </template>
        </el-table-column>
        <el-table-column v-for="column in columns" :key="column.key" :label="column.label"
          :min-width="column.kind === 'money' ? 120 : 96" align="right">
          <template #default="{ row }">
            <span class="v" :class="{ strong: column.key === 'final_profit', neg: isNegative(column, row[column.key]) }">
              {{ display(column, row[column.key]) }}
            </span>
          </template>
        </el-table-column>
      </el-table>

      <div class="tc-foot">
        <span>费用为负数表示支出；比率分母为 0 时显示 --</span>
        <span v-if="report">剔除 {{ excludedText }}</span>
      </div>
    </div>

    <!-- 页面逻辑与数据来源 -->
    <el-drawer v-model="helpVisible" title="AMZ月度利润表 · 逻辑与数据来源" size="640px" append-to-body>
      <div class="help">
        <section v-if="report" class="help-sec">
          <div class="help-h">本月数据</div>
          <div class="help-kv">
            <div><span>统计期</span><b>{{ report.period }}</b></div>
            <div><span>拉取时间</span><b>{{ report.pulled_at || '--' }}</b></div>
            <div><span>店铺 / 组别</span><b>{{ report.store_rows.length }} 家店 · {{ report.group_rows.filter(row => row.row_type === 'GROUP').length }} 个组别</b></div>
            <div><span>剔除</span><b>{{ excludedText }}</b></div>
            <div><span>手工补充费用</span><b>{{ report.adjustment_count || 0 }} 笔</b></div>
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
          <div class="help-h">各列口径（{{ view === 'store' ? '店铺利润' : '小组利润' }}）</div>
          <el-table :data="helpColumns" size="small" class="help-table">
            <el-table-column label="列" prop="label" width="110" />
            <el-table-column label="来源" min-width="170">
              <template #default="{ row }"><code>{{ row.source }}</code></template>
            </el-table-column>
            <el-table-column label="说明" prop="note" min-width="230" />
          </el-table>
        </section>
        <section class="help-sec">
          <div class="help-h">如何核对</div>
          <ol class="help-check">
            <li v-for="text in checkSteps" :key="text">{{ text }}</li>
          </ol>
        </section>
      </div>
    </el-drawer>

    <!-- 补充费用 -->
    <el-dialog v-model="adjustVisible" :title="`补充费用 · ${statMonth || ''}`" width="760px" append-to-body
      @closed="resetForm">
      <div class="adjust-note">
        记在小组利润的末级行上（EU / US1 / US2 / MJ / ZXY，US3 请分到 MJ 或 ZXY），金额加到所选列并计入最终毛利；
        支出填负数、收入填正数。不属于现有费用列的金额请选「补充费用」。
      </div>
      <el-table v-loading="adjustLoading" :data="adjustments" size="small" max-height="260" empty-text="本月还没有补充费用">
        <el-table-column label="行" prop="row_code" width="70" />
        <el-table-column label="费用列" prop="fee_label" min-width="110" />
        <el-table-column label="金额" width="120" align="right">
          <template #default="{ row }">{{ formatMoney(row.amount) }}</template>
        </el-table-column>
        <el-table-column label="备注" prop="remark" min-width="140" show-overflow-tooltip />
        <el-table-column label="维护人" width="90">
          <template #default="{ row }">{{ row.updated_by || row.created_by || '--' }}</template>
        </el-table-column>
        <el-table-column label="操作" width="110" align="center">
          <template #default="{ row }">
            <el-button link type="primary" @click="editAdjustment(row)">修改</el-button>
            <el-button link type="danger" @click="removeAdjustment(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
      <el-form ref="formRef" :model="form" :rules="formRules" label-width="70px" class="adjust-form" @submit.prevent>
        <div class="adjust-form__title">{{ form.id ? '修改补充费用' : '新增补充费用' }}</div>
        <el-row :gutter="12">
          <el-col :span="6">
            <el-form-item label="行" prop="rowCode">
              <el-select v-model="form.rowCode" placeholder="末级行">
                <el-option v-for="code in report?.leaf_codes || []" :key="code" :label="code" :value="code" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="9">
            <el-form-item label="费用列" prop="feeItem">
              <el-select v-model="form.feeItem" placeholder="加到哪一列">
                <el-option v-for="item in report?.adjustment_items || []" :key="item.key" :label="item.label" :value="item.key" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="9">
            <el-form-item label="金额" prop="amount">
              <el-input-number v-model="form.amount" :precision="2" :step="100" controls-position="right" class="amount-input" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item label="备注" prop="remark">
          <el-input v-model="form.remark" maxlength="255" show-word-limit placeholder="费用来源、说明" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button v-if="form.id" @click="resetForm">取消修改</el-button>
        <el-button type="primary" :loading="saving" @click="submitAdjustment">{{ form.id ? '保存修改' : '新增' }}</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup name="AmzMonthlyProfit">
import { computed, getCurrentInstance, onMounted, reactive, ref } from 'vue'
import { checkSteps, columnHelp, logicSteps, sourceInfo } from './help'
import {
  addAmzMonthlyProfitAdjustment, deleteAmzMonthlyProfitAdjustment, exportAmzMonthlyProfit,
  getAmzMonthlyProfit, listAmzMonthlyProfitAdjustments, listAmzMonthlyProfitMonths,
  updateAmzMonthlyProfitAdjustment
} from '@/api/finance/amzMonthlyProfit'

const { proxy } = getCurrentInstance()
const views = [
  { value: 'store', label: '店铺利润' },
  { value: 'group', label: '小组利润' }
]
const EXCLUDED_LABELS = {
  excluded_shop: '关停店铺',
  excluded_special_msku: '智贸云/优贝诺非 zmy/dsq MSKU',
  unmatched_department: '非部门店铺'
}

const months = ref([])
const monthsLoading = ref(false)
const statMonth = ref('')
const view = ref('store')
const loading = ref(false)
const exporting = ref(false)
const report = ref(null)

const columns = computed(() => {
  if (!report.value) return []
  return view.value === 'store' ? report.value.store_columns : report.value.group_columns
})

const tableRows = computed(() => {
  const data = report.value
  if (!data) return []
  const rows = view.value === 'store' ? data.store_rows : data.group_rows
  const total = view.value === 'store' ? data.store_total : data.group_total
  return [{ ...total, isTotal: true }, ...rows]
})

const subtitle = computed(() => {
  const data = report.value
  if (!data) return months.value.length ? '请选择月份' : '还没有拉取任何月份，请先在定时任务里执行「AMZ月度利润表数据拉取」'
  return view.value === 'store'
    ? `${data.store_rows.length} 家店铺（按 组别 + 店铺名 汇总所有站点）`
    : `${data.group_rows.filter(row => row.row_type === 'GROUP').length} 个组别，US3 下拆 MJ / ZXY 小组`
})

const helpVisible = ref(false)
// 说明里的列清单跟着当前页签走；没拉到报表时按店铺利润的列顺序列出。
const helpColumns = computed(() => {
  const list = columns.value.length ? columns.value : Object.keys(columnHelp).map(key => ({ key, label: key }))
  return list.map(column => ({ label: column.label, ...(columnHelp[column.key] || { source: '--', note: '' }) }))
})

const excludedText = computed(() => {
  const items = Object.entries(report.value?.excluded || {})
  return items.length ? items.map(([key, count]) => `${EXCLUDED_LABELS[key] || key} ${count} 行`).join('，') : '无'
})

function formatMoney(value) {
  if (value === null || value === undefined || value === '') return '--'
  return Number(value).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function display(column, value) {
  if (value === null || value === undefined || value === '') return '--'
  if (column.kind === 'rate') return `${(Number(value) * 100).toFixed(2)}%`
  if (column.kind === 'qty') return Number(value).toLocaleString('zh-CN')
  return formatMoney(value)
}

function isNegative(column, value) {
  return ['final_profit', 'gross_profit', 'gross_margin'].includes(column.key) && Number(value) < 0
}

function rowClassName({ row }) {
  if (row.isTotal) return 'report-total-row'
  if (view.value === 'group' && row.row_type === 'SUBTEAM') return 'report-sub-row'
  return ''
}

async function loadMonths() {
  monthsLoading.value = true
  try {
    const response = await listAmzMonthlyProfitMonths()
    months.value = response.data || []
    if (!statMonth.value && months.value.length) statMonth.value = months.value[0].stat_month
  } finally {
    monthsLoading.value = false
  }
}

async function loadReport() {
  if (!statMonth.value) {
    report.value = null
    return
  }
  loading.value = true
  try {
    const response = await getAmzMonthlyProfit(statMonth.value)
    report.value = response.data || null
  } catch {
    report.value = null
  } finally {
    loading.value = false
  }
}

async function handleExport() {
  exporting.value = true
  try {
    const data = await exportAmzMonthlyProfit(statMonth.value)
    const blob = data instanceof Blob
      ? data
      : new Blob([data], { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = `AMZ月度利润表-${statMonth.value}.xlsx`
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

// ---------------- 补充费用
const adjustVisible = ref(false)
const adjustLoading = ref(false)
const adjustments = ref([])
const saving = ref(false)
const formRef = ref()
const form = reactive({ id: null, rowCode: '', feeItem: '', amount: null, remark: '' })
const formRules = {
  rowCode: [{ required: true, message: '请选择行', trigger: 'change' }],
  feeItem: [{ required: true, message: '请选择费用列', trigger: 'change' }],
  amount: [{
    validator: (_rule, value, callback) =>
      value === null || value === undefined || Number(value) === 0 ? callback(new Error('请填写非 0 金额')) : callback(),
    trigger: 'blur'
  }]
}

function resetForm() {
  Object.assign(form, { id: null, rowCode: '', feeItem: '', amount: null, remark: '' })
  formRef.value?.clearValidate()
}

async function loadAdjustments() {
  adjustLoading.value = true
  try {
    const response = await listAmzMonthlyProfitAdjustments(statMonth.value)
    adjustments.value = response.data || []
  } finally {
    adjustLoading.value = false
  }
}

function openAdjustments() {
  resetForm()
  adjustVisible.value = true
  loadAdjustments()
}

function editAdjustment(row) {
  Object.assign(form, {
    id: row.id, rowCode: row.row_code, feeItem: row.fee_item, amount: Number(row.amount), remark: row.remark || ''
  })
}

async function submitAdjustment() {
  await formRef.value.validate()
  saving.value = true
  try {
    const data = { statMonth: statMonth.value, rowCode: form.rowCode, feeItem: form.feeItem, amount: form.amount, remark: form.remark }
    if (form.id) await updateAmzMonthlyProfitAdjustment(form.id, data)
    else await addAmzMonthlyProfitAdjustment(data)
    proxy.$modal.msgSuccess(form.id ? '已保存' : '已新增')
    resetForm()
    await Promise.all([loadAdjustments(), loadReport()])
  } finally {
    saving.value = false
  }
}

async function removeAdjustment(row) {
  await proxy.$modal.confirm(`确认删除 ${row.row_code} 的「${row.fee_label}」${formatMoney(row.amount)}？`)
  await deleteAmzMonthlyProfitAdjustment(row.id)
  proxy.$modal.msgSuccess('已删除')
  if (form.id === row.id) resetForm()
  await Promise.all([loadAdjustments(), loadReport()])
}

onMounted(async () => {
  await loadMonths()
  await loadReport()
})
</script>

<style scoped>
.amz-monthly-profit {
  --sky-50: #f4f8ff;
  --sky-100: #e7efff;
  --sky-200: #c9dcfb;
  --sky-300: #a9c6f4;
  --sky-600: #1257d6;
  --sky-700: #0e45a8;
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
  --n-bg: linear-gradient(100deg, #f6f9ff 0%, #fbfdff 100%);
  --n-bd: var(--sky-200);
  --n-fg: var(--sky-700);
  --n-ico-bg: var(--sky-100);
  display: flex;
  align-items: flex-start;
  gap: 12px;
  padding: 12px 14px;
  background: var(--n-bg);
  border: 1px solid var(--n-bd);
  border-radius: 12px;
}
.notice--warning { --n-bg: linear-gradient(100deg, #fffbef, #fffdf7); --n-bd: #fce3b0; --n-fg: #b26b09; --n-ico-bg: #fdf1d4; }
.notice__icon {
  width: 28px;
  height: 28px;
  flex-shrink: 0;
  border-radius: 9px;
  background: var(--n-ico-bg);
  color: var(--n-fg);
  display: flex;
  align-items: center;
  justify-content: center;
}
.notice__body { flex: 1; min-width: 0; }
.notice__title { font-size: 13px; font-weight: 600; color: var(--n-fg); margin-bottom: 3px; }
.notice__desc { font-size: 12.5px; line-height: 1.75; color: var(--ink-500); }
.notice--warning .notice__desc { color: #8a5a12; line-height: 24px; }
.notice__desc b { color: var(--ink-700); font-weight: 600; }
.notice__desc .kv { color: var(--sky-700); font-weight: 500; font-variant-numeric: tabular-nums; margin: 0 2px; }

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
.tc-actions { margin-left: auto; display: flex; align-items: center; gap: 8px; }
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
.report-icon.spinning { animation: report-icon-spin 1s linear infinite; }
@keyframes report-icon-spin { to { transform: rotate(360deg); } }

.report-table {
  --el-table-border-color: var(--jb-line, #e3e9f2);
  --el-table-header-bg-color: #f5f8fd;
  --el-table-row-hover-bg-color: rgba(18, 87, 214, 0.055);
  --el-table-text-color: var(--ink-700);
  --el-table-header-text-color: var(--ink-500);
  font-size: 12.5px;
}
.report-table :deep(th.el-table__cell) { font-size: 11.5px; font-weight: 600; border-bottom: 1px solid var(--jb-line, #e3e9f2) !important; }
.report-table :deep(.el-table__cell) { padding: 9px 0; }
.report-table :deep(.report-total-row) { background: #eef3fd; font-weight: 600; }
.report-table :deep(.report-sub-row) { background: #fafcff; }
.v { font-variant-numeric: tabular-nums; }
.v.strong { font-weight: 600; color: var(--ink-900); }
.v.neg { color: #dc2626; }
.sum-label { font-weight: 650; color: var(--ink-900); }
.sub-label { color: var(--ink-500); padding-left: 6px; }
.g-tag { display: inline-flex; align-items: center; gap: 6px; font-weight: 600; color: var(--sky-700); }
.g-tag i { width: 6px; height: 6px; border-radius: 50%; background: var(--sky-600); }
.shop-name { color: var(--ink-900); }
.team-tag {
  margin-left: 6px;
  font-size: 11px;
  padding: 0 6px;
  border-radius: 6px;
  color: var(--sky-700);
  background: var(--sky-100);
}
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
.help-btn { margin-left: auto; color: #1257d6; }

/* 说明抽屉挂在 body 下，取不到页面根上的 CSS 变量，颜色直接写值。 */
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
.help-table code { font-size: 12px; color: #0b6b98; background: #f2f9ff; padding: 1px 4px; border-radius: 4px; white-space: normal; }
.help-check { margin: 0; padding-left: 18px; line-height: 1.8; }
.help-check li + li { margin-top: 4px; }

.adjust-note { font-size: 12.5px; color: var(--ink-500); line-height: 1.7; margin-bottom: 10px; }
.adjust-form { margin-top: 14px; padding-top: 12px; border-top: 1px dashed var(--line); }
.adjust-form__title { font-size: 13px; font-weight: 600; color: var(--ink-700); margin-bottom: 10px; }
.amount-input { width: 100%; }
</style>
