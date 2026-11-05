<template>
  <div class="app-container amz-profit-report">
    <!-- 筛选栏 -->
    <div class="filter-bar">
      <span class="f-label">统计区间</span>
      <DateRangePicker v-model="period" mode="month" :min="earliestMonth" :max="latestMonth"
        :max-span="MAX_MONTHS" :presets="periodPresets" :clearable="false"
        :disabled="monthsLoading || !months.length" placeholder="请选择月份范围" @change="loadReport" />
      <span class="f-label f-label--gap">货币</span>
      <div class="chips" role="tablist" aria-label="货币">
        <button v-for="item in currencyOptions" :key="item.value" type="button" class="chip"
          :class="{ active: currency === item.value }" role="tab" :aria-selected="currency === item.value"
          @click="switchCurrency(item.value)">{{ item.label }}</button>
      </div>
      <span class="f-hint">只能选择已拉取数据的月份，一次最多 {{ MAX_MONTHS }} 个月</span>
    </div>

    <!-- 口径说明与缺数提示 -->
    <div v-if="report" class="notice" role="status">
      <div class="notice__icon">
        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round">
          <circle cx="12" cy="12" r="9" /><path d="M12 11v5" /><path d="M12 7.6h.01" />
        </svg>
      </div>
      <div class="notice__body">
        <div class="notice__title">数据口径说明</div>
        <div class="notice__desc">
          单位为 <b>{{ currencyName(report.currency_code) }}（{{ report.currency_code }}）</b><template v-if="report.exchange_rate">，整个时间段按最大月份<span class="kv">{{ report.exchange_rate_month }}</span>的领星 USD「我的汇率」<span class="kv">{{ Number(report.exchange_rate).toFixed(4) }}</span>换算</template>；统计区间<span class="kv">{{ periodLabel(report.start_month, report.end_month) }}</span>（{{ report.months.length }} 个月合计），业绩目标为区间内各月目标之和；
          涨跌与上期<span class="kv">{{ periodLabel(report.previous_start_month, report.previous_end_month) }}</span>比较，金额、销量为变化百分比，比率类为变化的<span class="kv">百分点（pp）</span>。
        </div>
      </div>
    </div>
    <div v-for="text in notices" :key="text" class="notice notice--warning" role="alert">
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
          <div class="tc-title">AMZ利润报表<template v-if="report"> · {{ periodLabel(report.start_month, report.end_month) }}</template></div>
          <div class="tc-sub">{{ tableSubtitle }}</div>
        </div>
        <div class="tc-actions">
          <div class="chips" role="tablist" aria-label="统计维度">
            <button v-for="item in dimensionOptions" :key="item.value" type="button" class="chip"
              :class="{ active: dimension === item.value }" role="tab" :aria-selected="dimension === item.value"
              @click="switchDimension(item.value)">{{ item.label }}</button>
          </div>
          <el-tooltip content="刷新" placement="top">
            <button type="button" class="icon-btn" aria-label="刷新" :disabled="loading" @click="loadReport">
              <svg-icon icon-class="jmh-refresh" class="report-icon" :class="{ spinning: loading }" />
            </button>
          </el-tooltip>
          <span v-hasPermi="['finance:amzProfitReport:export']" class="export-entry">
            <el-tooltip content="导出 Excel（当前时间段）" placement="top">
              <button type="button" class="icon-btn" aria-label="导出 Excel" :disabled="!period" @click="openExport">
                <svg-icon icon-class="jmh-export" class="report-icon" />
              </button>
            </el-tooltip>
          </span>
        </div>
      </div>

      <el-table v-loading="loading" class="report-table" :data="tableRows" :row-class-name="rowClassName"
        max-height="640" empty-text="暂无数据">
        <el-table-column label="组别" min-width="96" fixed="left">
          <template #default="{ row }">
            <span v-if="row.isTotal" class="sum-label">合计</span>
            <span v-else class="g-tag" :class="groupTone(row.department_code)"><i />{{ departmentLabel(row.department_code) }}</span>
          </template>
        </el-table-column>
        <el-table-column v-if="dimension !== 'GROUP'" :label="dimension === 'STORE' ? '店铺' : '负责人'"
          min-width="130" fixed="left">
          <template #default="{ row }"><span class="shop-name">{{ row.isTotal ? '' : row.dimension_value }}</span></template>
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
            <span v-if="column.key === 'achievement_rate'" class="rate" :class="achievementTone(row[column.key])">
              {{ display(column, row[column.key]) }}
            </span>
            <span v-else class="v">{{ display(column, row[column.key]) }}</span>
            <span v-if="trend(column, row)" class="trend-icon" :class="`trend-${trend(column, row)}`">
              <svg-icon :icon-class="trend(column, row) === 'up' ? 'jmh-trend-up' : 'jmh-trend-down'" />
              <span v-if="changeLabel(column, row)" class="trend-change">{{ changeLabel(column, row) }}</span>
            </span>
          </template>
        </el-table-column>
      </el-table>

      <div class="tc-foot">
        <span>表头带 <b>?</b> 的列可悬停查看数据来源与计算规则</span>
        <div class="legend">
          <span><i class="lg-up" />红色：比上期上升</span>
          <span><i class="lg-down" />绿色：比上期下降</span>
          <span><i class="lg-rate" />达成率：≥100% 绿 · ≥80% 蓝 · ≥50% 橙 · &lt;50% 红</span>
        </div>
      </div>
    </div>

    <el-dialog v-model="exportVisible" title="导出 AMZ利润报表" width="440px" append-to-body>
      <el-form label-width="80px" @submit.prevent>
        <el-form-item label="时间段">
          <span class="export-period">{{ period ? periodLabel(period[0], period[1]) : '--' }}</span>
        </el-form-item>
        <el-form-item label="货币">
          <span class="export-period">{{ currencyName(currency) }}（{{ currency }}）</span>
        </el-form-item>
        <el-form-item label="维度">
          <el-checkbox-group v-model="exportDimensions">
            <el-checkbox value="GROUP">组别</el-checkbox>
            <el-checkbox value="STORE">店铺</el-checkbox>
            <el-checkbox value="OWNER">个人</el-checkbox>
          </el-checkbox-group>
        </el-form-item>
        <div class="export-note">导出页面当前选择的时间段和货币，数据与页面一致（区间内各月汇总）；每个维度一个工作表，先合计行再明细行。要换时间段请先在页面上重新选择。</div>
      </el-form>
      <template #footer>
        <el-button @click="exportVisible = false">取消</el-button>
        <el-button type="primary" :loading="exporting"
          :disabled="!period || !exportDimensions.length"
          @click="handleExport">导出 Excel</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup name="AmzProfitReport">
import { computed, getCurrentInstance, onMounted, ref } from 'vue'
import { QuestionFilled } from '@element-plus/icons-vue'
import DateRangePicker from '@/components/DateRangePicker/index.vue'
import { addMonths } from '@/components/DateRangePicker/rangeUtils'
import { exportAmzProfitReport, getAmzProfitReport, listAmzProfitReportMonths } from '@/api/finance/amzProfitReport'
import { amzProfitColumnHelp } from './columnHelp'

// 与后端 MAX_EXPORT_MONTHS 一致：查询和导出一次最多 24 个月。
const MAX_MONTHS = 24

const columns = [
  { key: 'target_usd', label: '业绩目标', format: 'money', width: 140 },
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
const period = ref(null)
const dimension = ref('STORE')
// 默认人民币：后端按所选时间段最大月份的领星 USD「我的汇率」(my_rate) 换算，不用官方汇率。
const currency = ref('CNY')
const currencyOptions = [
  { value: 'CNY', label: '人民币' },
  { value: 'USD', label: '美元' }
]

function currencyName(code) {
  return currencyOptions.find(item => item.value === code)?.label || code
}

function switchCurrency(value) {
  if (currency.value === value) return
  currency.value = value
  loadReport()
}
const loading = ref(false)
const report = ref(null)

const tableRows = computed(() => {
  if (!report.value) return []
  return [{ ...report.value.total, isTotal: true }, ...report.value.rows]
})

const sortedMonths = computed(() => months.value.map(item => item.stat_month).sort())
const earliestMonth = computed(() => sortedMonths.value[0] || '')
const latestMonth = computed(() => sortedMonths.value[sortedMonths.value.length - 1] || '')

// 快捷项以最近一个已拉取的月份为终点，避免选到还没拉取的当月。
const periodPresets = computed(() => {
  const latest = latestMonth.value
  if (!latest) return []
  const year = Number(latest.slice(0, 4))
  return [
    { key: 'latest', label: '最近一个月', range: [latest, latest] },
    { key: 'last3', label: '近 3 个月', range: [addMonths(latest, -2), latest] },
    { key: 'last6', label: '近 6 个月', range: [addMonths(latest, -5), latest] },
    { key: 'thisYear', label: `${year} 年`, range: [`${year}-01`, latest] },
    { key: 'lastYear', label: `${year - 1} 年`, range: [`${year - 1}-01`, `${year - 1}-12`] }
  ]
})

function periodLabel(start, end) {
  return start === end ? start : `${start} 至 ${end}`
}

const notices = computed(() => {
  const data = report.value
  if (!data) return []
  const result = []
  const span = periodLabel(data.start_month, data.end_month)
  if (!data.settlement_ready) result.push(`${span} 结算数据（利润统计）尚未拉取，销量、销售额、结算毛利润等显示--`)
  else if (data.missing_settlement_months.length) result.push(`${data.missing_settlement_months.join('、')} 结算数据尚未拉取，区间合计只包含已拉取的月份`)
  if (!data.order_ready) result.push(`${span} 订单利润尚未拉取，订单毛利润/订单毛利率显示--`)
  else if (data.missing_order_months.length) result.push(`${data.missing_order_months.join('、')} 订单利润尚未拉取，订单毛利润只包含已拉取的月份`)
  if (!data.previous_ready) result.push(`上期 ${periodLabel(data.previous_start_month, data.previous_end_month)} 数据未完整拉取，环比和涨跌图标不显示`)
  if (data.target_note) result.push(data.target_note)
  return result
})

const dimensionOptions = [
  { value: 'GROUP', label: '组别', unit: '个组别' },
  { value: 'STORE', label: '店铺', unit: '家店铺' },
  { value: 'OWNER', label: '个人', unit: '位负责人' }
]

function switchDimension(value) {
  if (dimension.value === value) return
  dimension.value = value
  loadReport()
}

const tableSubtitle = computed(() => {
  const data = report.value
  if (!data) return '请选择统计区间'
  const unit = dimensionOptions.find(item => item.value === data.dimension)?.unit || '行'
  return `共 ${data.rows.length} ${unit} · 金额单位 ${data.currency_code} · 对比上期 ${periodLabel(data.previous_start_month, data.previous_end_month)}`
})

function departmentLabel(code) {
  return String(code || '').replace(/^AMZ-/, '')
}

// 组别标签配色按站点前缀区分，便于扫读。
function groupTone(code) {
  const label = departmentLabel(code)
  if (label.startsWith('EU')) return 'eu'
  if (label.startsWith('US1')) return 'us1'
  if (label.startsWith('US2')) return 'us2'
  if (label.startsWith('UK')) return 'uk'
  return 'other'
}

function achievementTone(value) {
  const number = numberOrNull(value)
  if (number === null) return 'none'
  if (number >= 1) return 'good'
  if (number >= 0.8) return 'normal'
  if (number >= 0.5) return 'warn'
  return 'bad'
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
  const symbol = report.value?.currency_code === 'USD' ? '$' : '¥'
  return `${symbol}${number.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
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
const exportDimensions = ref(['STORE'])
const exporting = ref(false)

// 导出的就是页面所选：同一时间段，默认勾选当前维度。
function openExport() {
  exportDimensions.value = [dimension.value]
  exportVisible.value = true
}

async function handleExport() {
  const [startMonth, endMonth] = period.value
  exporting.value = true
  try {
    const data = await exportAmzProfitReport(startMonth, endMonth, exportDimensions.value.join(','), currency.value)
    const blob = data instanceof Blob
      ? data
      : new Blob([data], { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = `AMZ利润报表-${startMonth === endMonth ? startMonth : `${startMonth}至${endMonth}`}-${currencyName(currency.value)}.xlsx`
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
    if (!period.value && latestMonth.value) period.value = [latestMonth.value, latestMonth.value]
  } finally {
    monthsLoading.value = false
  }
}

async function loadReport() {
  if (!period.value) {
    report.value = null
    return
  }
  const [startMonth, endMonth] = period.value
  loading.value = true
  try {
    const response = await getAmzProfitReport(startMonth, endMonth, dimension.value, currency.value)
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
/* 配色沿用时间段选择器原型（天蓝主色）。 */
.amz-profit-report {
  --sky-50: #f2f9ff;
  --sky-100: #e4f2fe;
  --sky-200: #c6e6fb;
  --sky-300: #92d3f8;
  --sky-500: #1ba4e0;
  --sky-600: #0d86bd;
  --sky-700: #0b6b98;
  --ink-900: #0f2333;
  --ink-700: #35505f;
  --ink-500: #6b8595;
  --ink-400: #9aafbb;
  --line: #e5eef4;
  --radius: 14px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

/* 筛选栏 */
.filter-bar {
  background: #fff;
  border: 1px solid var(--line);
  border-radius: var(--radius);
  padding: 14px 18px;
  display: flex;
  align-items: center;
  gap: 14px;
  flex-wrap: wrap;
  box-shadow: 0 2px 10px rgba(11, 107, 152, .05);
}
.f-label { font-size: 13.5px; color: var(--ink-700); font-weight: 500; letter-spacing: .3px; }
.f-label--gap { margin-left: 10px; }
.f-hint { font-size: 12px; color: var(--ink-400); }

/* 提示框 */
.notice {
  --n-bg: linear-gradient(100deg, #f2faff 0%, #f8fdff 100%);
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
.notice--warning .notice__icon { width: 24px; height: 24px; border-radius: 7px; }
.notice__body { flex: 1; min-width: 0; }
.notice__title { font-size: 13px; font-weight: 600; color: var(--n-fg); letter-spacing: .2px; margin-bottom: 3px; }
.notice__desc { font-size: 12.5px; line-height: 1.75; color: var(--ink-500); }
.notice--warning .notice__desc { color: #8a5a12; line-height: 24px; }
.notice__desc b { color: var(--ink-700); font-weight: 600; }
.notice__desc .kv { color: var(--sky-700); font-weight: 500; font-variant-numeric: tabular-nums; margin: 0 2px; }

/* 表格卡片 */
.table-card {
  background: #fff;
  border: 1px solid var(--line);
  border-radius: var(--radius);
  box-shadow: 0 2px 10px rgba(11, 107, 152, .05);
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
.tc-title { font-size: 14.5px; font-weight: 650; color: var(--ink-900); letter-spacing: .2px; font-variant-numeric: tabular-nums; }
.tc-sub { font-size: 12px; color: var(--ink-400); margin-top: 4px; line-height: 1.6; }
.tc-actions { margin-left: auto; display: flex; align-items: center; gap: 8px; }
.chips {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  background: #f5fafd;
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
  transition: all .15s;
  white-space: nowrap;
}
.chip:hover { color: var(--sky-600); background: #fff; }
.chip.active { background: #fff; color: var(--sky-700); box-shadow: 0 1px 4px rgba(11, 107, 152, .14); font-weight: 600; }
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
  transition: all .15s;
}
.icon-btn:hover { border-color: var(--sky-300); background: var(--sky-50); }
.icon-btn:disabled { opacity: .4; cursor: not-allowed; }
.report-icon { font-size: 18px; color: #1296db; }
.report-icon.spinning { animation: report-icon-spin 1s linear infinite; }
@keyframes report-icon-spin { to { transform: rotate(360deg); } }

/* el-table 换成原型的轻量样式 */
.report-table {
  --el-table-border-color: #f2f7fa;
  --el-table-header-bg-color: #f7fbfe;
  --el-table-row-hover-bg-color: #f7fcff;
  --el-table-text-color: var(--ink-700);
  --el-table-header-text-color: var(--ink-500);
  font-size: 12.5px;
}
.report-table :deep(th.el-table__cell) {
  font-size: 11.5px;
  font-weight: 600;
  letter-spacing: .3px;
  border-bottom: 1px solid var(--sky-200) !important;
}
.report-table :deep(.el-table__cell) { padding: 9px 0; }
.report-table :deep(.el-table__inner-wrapper::before) { display: none; }
.report-table :deep(.report-total-row > td.el-table__cell) {
  background: #f4fbff !important;
  border-bottom: 1px solid var(--sky-200);
  font-weight: 600;
  color: var(--ink-900);
}
.report-table :deep(.report-total-row:hover > td.el-table__cell) { background: #eef8ff !important; }
.column-heading { display: inline-flex; align-items: center; gap: 4px; cursor: help; }
.column-tip { color: #b5c7d3; transition: color .15s; }
.column-heading:hover .column-tip { color: var(--sky-500); }

.v { font-variant-numeric: tabular-nums; color: var(--ink-900); }
.sum-label { color: var(--sky-700); font-weight: 700; letter-spacing: .5px; }
.shop-name { color: var(--ink-900); font-weight: 500; }
.g-tag { display: inline-flex; align-items: center; gap: 6px; font-size: 12px; font-weight: 600; letter-spacing: .3px; }
.g-tag i { width: 6px; height: 6px; border-radius: 50%; display: block; background: currentColor; }
.g-tag.eu { color: #5a61c9; }
.g-tag.us1 { color: #17907a; }
.g-tag.us2 { color: #b8860b; }
.g-tag.uk { color: #c2407a; }
.g-tag.other { color: var(--ink-500); }

/* 涨跌：红升绿降，图标右侧带底色的变化幅度 */
.trend-icon {
  display: inline-flex;
  align-items: center;
  gap: 1px;
  margin-left: 5px;
  padding: 1px 5px 1px 3px;
  border-radius: 4px;
  font-size: 13px;
  white-space: nowrap;
  vertical-align: 1px;
}
.trend-change { font-size: 11px; font-weight: 500; font-variant-numeric: tabular-nums; }
.trend-up { color: #d9524b; background: #fdf1f1; }
.trend-down { color: #0d8f70; background: #ecfaf4; }

.rate {
  display: inline-block;
  min-width: 58px;
  text-align: center;
  font-size: 11.5px;
  font-weight: 600;
  padding: 2px 8px;
  border-radius: 6px;
  font-variant-numeric: tabular-nums;
}
.rate.good { color: #0d8f70; background: #e9f9f3; }
.rate.normal { color: var(--sky-700); background: var(--sky-100); }
.rate.warn { color: #b26b09; background: #fdf4e3; }
.rate.bad { color: #d9524b; background: #fdeeee; }
.rate.none { color: var(--ink-400); background: transparent; }

.tc-foot {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 10px 18px;
  border-top: 1px solid var(--line);
  background: #fbfdff;
  font-size: 12px;
  color: var(--ink-400);
  flex-wrap: wrap;
}
.tc-foot b { color: var(--ink-500); }
.legend { display: flex; align-items: center; gap: 14px; margin-left: auto; flex-wrap: wrap; }
.legend span { display: inline-flex; align-items: center; gap: 5px; }
.legend i { width: 7px; height: 7px; border-radius: 2px; display: block; }
.legend .lg-up { background: #d9524b; }
.legend .lg-down { background: #0d8f70; }
.legend .lg-rate { background: linear-gradient(90deg, #0d8f70, var(--sky-500), #b26b09, #d9524b); width: 14px; }

.export-period { color: var(--ink-900); font-weight: 600; font-variant-numeric: tabular-nums; }
.export-note { color: #7a869a; font-size: 12px; line-height: 1.6; }
.column-help { width: min(540px, calc(100vw - 48px)); max-height: min(520px, calc(100vh - 80px)); overflow-y: auto; font-size: 12px; line-height: 1.7; color: #51627c; }
.column-help-title { color: #24486d; font-size: 13px; font-weight: 600; padding-bottom: 8px; border-bottom: 1px solid #e9edf4; }
.column-help dl { margin: 0; }
.column-help dl > div { display: grid; grid-template-columns: 64px minmax(0, 1fr); gap: 10px; padding-top: 9px; }
.column-help dt { font-weight: 600; color: #344d72; }
.column-help dd { margin: 0; white-space: pre-line; overflow-wrap: anywhere; }
.column-help-table { font-family: ui-monospace, Consolas, monospace; font-size: 11px; }
</style>
