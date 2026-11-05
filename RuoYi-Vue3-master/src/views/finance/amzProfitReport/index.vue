<template>
  <div class="app-container amz-profit-report">
    <el-card shadow="never">
      <el-form :inline="true" @submit.prevent>
        <el-form-item label="月份">
          <el-select v-model="statMonth" placeholder="请选择月份" :loading="monthsLoading" style="width: 150px" @change="loadReport">
            <el-option v-for="item in months" :key="item.stat_month" :label="item.stat_month" :value="item.stat_month" />
          </el-select>
        </el-form-item>
        <el-form-item>
          <el-radio-group v-model="dimension" @change="loadReport">
            <el-radio-button value="GROUP">组别</el-radio-button>
            <el-radio-button value="STORE">店铺</el-radio-button>
            <el-radio-button value="OWNER">个人</el-radio-button>
          </el-radio-group>
        </el-form-item>
        <el-form-item>
          <el-tooltip content="刷新" placement="top">
            <el-button class="icon-button" text aria-label="刷新" :disabled="loading" @click="loadReport">
              <svg-icon icon-class="jmh-refresh" class="report-icon" :class="{ spinning: loading }" />
            </el-button>
          </el-tooltip>
          <span v-hasPermi="['finance:amzProfitReport:export']" class="export-entry">
            <el-tooltip content="导出 Excel" placement="top">
              <el-button class="icon-button" text aria-label="导出 Excel"
                :disabled="!months.length" @click="openExport">
                <svg-icon icon-class="jmh-export" class="report-icon" />
              </el-button>
            </el-tooltip>
          </span>
        </el-form-item>
      </el-form>

      <el-alert v-for="text in notices" :key="text" class="report-notice" type="warning" :closable="false" :title="text" show-icon />
      <div v-if="report" class="report-meta">
        金额单位 USD；业绩目标取月度库存 {{ report.target_stat_month }} 库存月快照；涨跌图标与 {{ report.previous_month }} 比较，图标右侧为变化幅度：金额、销量为变化百分比，比率类为变化的百分点（pp）。
      </div>

      <el-table v-loading="loading" :data="tableRows" border stripe :row-class-name="rowClassName" empty-text="暂无数据">
        <el-table-column label="组别" min-width="110" fixed="left">
          <template #default="{ row }">{{ row.isTotal ? '合计' : departmentLabel(row.department_code) }}</template>
        </el-table-column>
        <el-table-column v-if="dimension !== 'GROUP'" :label="dimension === 'STORE' ? '店铺' : '负责人'"
          min-width="120" fixed="left">
          <template #default="{ row }">{{ row.isTotal ? '' : row.dimension_value }}</template>
        </el-table-column>
        <el-table-column v-for="column in columns" :key="column.key" :min-width="column.width || 120" align="right">
          <template #header>
            <el-tooltip placement="top" effect="light" :show-after="200">
              <template #content>
                <div class="column-help">
                  <div class="column-help-title">{{ column.label }} · 数据口径</div>
                  <dl>
                    <div><dt>来源接口</dt><dd>{{ column.help.sourceApi }}</dd></div>
                    <div><dt>源表</dt><dd class="column-help-table">{{ column.help.sourceTable }}</dd></div>
                    <div><dt>计算规则</dt><dd>{{ column.help.formula }}</dd></div>
                    <div><dt>空值处理</dt><dd>{{ column.help.emptyHandling }}</dd></div>
                  </dl>
                </div>
              </template>
              <span class="column-heading" tabindex="0" :aria-label="`${column.label}：数据来源与计算规则`">
                {{ column.label }}<el-icon class="column-tip" aria-hidden="true"><QuestionFilled /></el-icon>
              </span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <span>{{ display(column, row[column.key]) }}</span>
            <span v-if="trend(column, row)" class="trend-icon" :class="`trend-${trend(column, row)}`">
              <svg-icon :icon-class="trend(column, row) === 'up' ? 'jmh-trend-up' : 'jmh-trend-down'" />
              <span v-if="changeLabel(column, row)" class="trend-change">{{ changeLabel(column, row) }}</span>
            </span>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-dialog v-model="exportVisible" title="导出 AMZ利润报表" width="440px" append-to-body>
      <el-form label-width="80px" @submit.prevent>
        <el-form-item label="时间段">
          <el-date-picker v-model="exportRange" type="monthrange" value-format="YYYY-MM"
            range-separator="至" start-placeholder="开始月份" end-placeholder="结束月份"
            :disabled-date="exportDisabledDate" style="width: 100%" />
        </el-form-item>
        <el-form-item label="维度">
          <el-checkbox-group v-model="exportDimensions">
            <el-checkbox value="GROUP">组别</el-checkbox>
            <el-checkbox value="STORE">店铺</el-checkbox>
            <el-checkbox value="OWNER">个人</el-checkbox>
          </el-checkbox-group>
        </el-form-item>
        <div class="export-note">每个维度一个工作表，按月份依次列出合计行和明细行；只导出已拉取数据的月份，一次最多 24 个月。</div>
      </el-form>
      <template #footer>
        <el-button @click="exportVisible = false">取消</el-button>
        <el-button type="primary" :loading="exporting"
          :disabled="!exportRange || exportRange.length !== 2 || !exportDimensions.length"
          @click="handleExport">导出 Excel</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup name="AmzProfitReport">
import { computed, getCurrentInstance, onMounted, ref } from 'vue'
import { QuestionFilled } from '@element-plus/icons-vue'
import { exportAmzProfitReport, getAmzProfitReport, listAmzProfitReportMonths } from '@/api/finance/amzProfitReport'
import { amzProfitColumnHelp } from './columnHelp'

const columns = [
  { key: 'target_usd', label: '每月业绩目标', format: 'money', width: 140 },
  { key: 'achievement_rate', label: '达成率', format: 'rate' },
  { key: 'sales_qty', label: '销量', format: 'qty', trend: true, width: 140 },
  { key: 'sales_amount', label: '销售额', format: 'money', trend: true, width: 180 },
  { key: 'sales_mom', label: '销售额环比', format: 'rate', trend: 'sign', width: 130 },
  { key: 'order_gross_profit', label: '订单毛利润', format: 'money', trend: true, width: 180 },
  { key: 'order_gross_margin', label: '订单毛利率', format: 'rate', trend: true, width: 160 },
  { key: 'settlement_gross_profit', label: '结算毛利润', format: 'money', trend: true, width: 180 },
  { key: 'settlement_gross_margin', label: '结算毛利率', format: 'rate', trend: true, width: 160 },
  { key: 'return_rate', label: '退货率', format: 'rate', trend: true, width: 150 },
  { key: 'refund_rate', label: '退款率', format: 'rate', trend: true, width: 150 },
  { key: 'acos', label: 'ACOS', format: 'rate', trend: true, width: 150 },
  { key: 'ad_ratio', label: '广告占比', format: 'rate', trend: true, width: 150 }
].map(column => ({ ...column, help: amzProfitColumnHelp[column.key] }))

const { proxy } = getCurrentInstance()
const months = ref([])
const monthsLoading = ref(false)
const statMonth = ref('')
const dimension = ref('STORE')
const loading = ref(false)
const report = ref(null)

const tableRows = computed(() => {
  if (!report.value) return []
  return [{ ...report.value.total, isTotal: true }, ...report.value.rows]
})

const notices = computed(() => {
  const data = report.value
  if (!data) return []
  const result = []
  if (!data.settlement_ready) result.push(`${data.stat_month} 结算数据（利润统计）尚未拉取，销量、销售额、结算毛利润等显示--`)
  if (!data.order_ready) result.push(`${data.stat_month} 订单利润尚未拉取，订单毛利润/订单毛利率显示--`)
  if (!data.previous_ready) result.push(`${data.previous_month} 数据尚未拉取，环比和涨跌图标不显示`)
  if (data.target_note) result.push(data.target_note)
  return result
})

function departmentLabel(code) {
  return String(code || '').replace(/^AMZ-/, '')
}

function numberOrNull(value) {
  if (value === null || value === undefined || value === '') return null
  const number = Number(value)
  return Number.isFinite(number) ? number : null
}

function display(column, value) {
  const number = numberOrNull(value)
  const missing = column.format === 'rate' || column.key === 'target_usd'
    ? number === null
    : number === null || (!readyFor(column) && number === 0)
  if (missing) return '--'
  if (column.format === 'qty') return number.toLocaleString('zh-CN')
  if (column.format === 'rate') return `${(number * 100).toFixed(2)}%`
  return `$${number.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
}

function readyFor(column) {
  const data = report.value
  if (!data) return false
  return column.key.startsWith('order_') ? data.order_ready : data.settlement_ready
}

function trend(column, row) {
  if (!column.trend || !readyFor(column)) return ''
  const current = numberOrNull(row[column.key])
  if (current === null) return ''
  if (column.trend === 'sign') return current > 0 ? 'up' : current < 0 ? 'down' : ''
  const previous = numberOrNull(row.previous?.[column.key])
  if (previous === null || !report.value?.previous_ready) return ''
  return current > previous ? 'up' : current < previous ? 'down' : ''
}

// Magnitude next to the icon (the icon already shows the direction).
// Amounts and quantities: change vs last month in %; rates: change in
// percentage points, since a relative change of a rate is easy to misread.
function changeLabel(column, row) {
  if (column.trend === 'sign') return ''
  const current = numberOrNull(row[column.key])
  const previous = numberOrNull(row.previous?.[column.key])
  if (current === null || previous === null) return ''
  if (column.format === 'rate') return `${Math.abs((current - previous) * 100).toFixed(2)}pp`
  if (previous === 0) return ''
  return `${Math.abs((current - previous) / previous * 100).toFixed(2)}%`
}

const exportVisible = ref(false)
const exportRange = ref([])
const exportDimensions = ref(['GROUP', 'STORE', 'OWNER'])
const exporting = ref(false)
const pulledMonths = computed(() => new Set(months.value.map(item => item.stat_month)))

function openExport() {
  const sorted = [...pulledMonths.value].sort()
  exportRange.value = sorted.length ? [sorted[0], sorted[sorted.length - 1]] : []
  exportVisible.value = true
}

function exportDisabledDate(date) {
  const month = `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}`
  return !pulledMonths.value.has(month)
}

async function handleExport() {
  const [startMonth, endMonth] = exportRange.value || []
  exporting.value = true
  try {
    const data = await exportAmzProfitReport(startMonth, endMonth, exportDimensions.value.join(','))
    const blob = data instanceof Blob
      ? data
      : new Blob([data], { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = `AMZ利润报表-${startMonth}至${endMonth}.xlsx`
    document.body.appendChild(link)
    link.click()
    link.remove()
    URL.revokeObjectURL(url)
    exportVisible.value = false
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

function rowClassName({ row }) {
  return row.isTotal ? 'report-total-row' : ''
}

async function loadMonths() {
  monthsLoading.value = true
  try {
    const response = await listAmzProfitReportMonths()
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
    const response = await getAmzProfitReport(statMonth.value, dimension.value)
    report.value = response.data || null
  } finally {
    loading.value = false
  }
}

onMounted(async () => {
  await loadMonths()
  await loadReport()
})
</script>

<style scoped>
.report-notice { margin-bottom: 8px; }
.report-meta { margin: 4px 0 10px; color: #7a869a; font-size: 12px; }
.column-heading { display: inline-flex; align-items: center; gap: 4px; cursor: help; }
.column-tip { color: #a0a9b8; }
.trend-icon { margin-left: 3px; font-size: 14px; white-space: nowrap; }
.trend-change { margin-left: 1px; font-size: 12px; }
.trend-up { color: #f56c6c; }
.trend-down { color: #67c23a; }
.export-note { color: #7a869a; font-size: 12px; line-height: 1.6; }
.export-entry { margin-left: 4px; }
.icon-button { padding: 4px 6px; }
.icon-button.is-disabled { opacity: 0.4; }
.report-icon { font-size: 22px; color: #f4ea2a; }
.report-icon.spinning { animation: report-icon-spin 1s linear infinite; }
@keyframes report-icon-spin { to { transform: rotate(360deg); } }
:deep(.report-total-row) { font-weight: 600; background: #f5f7fa; }
.column-help { width: min(540px, calc(100vw - 48px)); max-height: min(520px, calc(100vh - 80px)); overflow-y: auto; font-size: 12px; line-height: 1.7; color: #51627c; }
.column-help-title { color: #24486d; font-size: 13px; font-weight: 600; padding-bottom: 8px; border-bottom: 1px solid #e9edf4; }
.column-help dl { margin: 0; }
.column-help dl > div { display: grid; grid-template-columns: 64px minmax(0, 1fr); gap: 10px; padding-top: 9px; }
.column-help dt { font-weight: 600; color: #344d72; }
.column-help dd { margin: 0; white-space: pre-line; overflow-wrap: anywhere; }
.column-help-table { font-family: ui-monospace, Consolas, monospace; font-size: 11px; }
</style>
