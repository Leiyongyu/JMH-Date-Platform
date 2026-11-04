<template>
  <div class="app-container ops-target">
    <el-card shadow="never">
      <el-form :inline="true" @submit.prevent>
        <el-form-item label="年度">
          <el-select v-model="year" placeholder="请选择年度" style="width: 120px" :disabled="editing" @change="loadReport">
            <el-option v-for="item in years" :key="item" :label="`${item}年`" :value="item" />
          </el-select>
        </el-form-item>
        <el-form-item>
          <el-tooltip content="刷新" placement="top">
            <el-button class="icon-button" text aria-label="刷新" :disabled="loading || editing" @click="loadReport">
              <svg-icon icon-class="jmh-refresh" class="report-icon" :class="{ spinning: loading }" />
            </el-button>
          </el-tooltip>
          <el-button text type="primary" @click="helpVisible = true">管控说明</el-button>
          <template v-if="canEdit">
            <el-button v-if="!editing" type="primary" plain :disabled="!rows.length" @click="startEdit">编辑</el-button>
            <template v-else>
              <el-button type="primary" :loading="saving" :disabled="!changedCount" @click="saveChanges">
                保存{{ changedCount ? `（${changedCount}项）` : '' }}
              </el-button>
              <el-button :disabled="saving" @click="cancelEdit">取消</el-button>
            </template>
          </template>
        </el-form-item>
      </el-form>

      <el-alert v-if="notes.length" class="report-notice" type="warning" :closable="false" show-icon>
        <template #title>
          数据核对提示（{{ notes.length }} 条，不影响保存）
          <el-button link type="primary" class="notice-toggle" @click="notesOpen = !notesOpen">{{ notesOpen ? '收起' : '展开' }}</el-button>
        </template>
        <ul v-if="notesOpen" class="notice-list">
          <li v-for="text in notes" :key="text">{{ text }}</li>
        </ul>
      </el-alert>
      <div class="report-meta">
        金额单位：万元；合计、达成率、全年目标、实际人效等为系统计算，不可编辑。<span v-if="report?.updatedAt">
          最后修改：{{ report.updatedBy || '--' }} {{ formatTime(report.updatedAt) }}</span>
      </div>

      <el-tabs v-model="activeTab">
        <el-tab-pane v-for="tab in TABS" :key="tab.name" :label="tab.label" :name="tab.name">
          <el-table v-loading="loading" :data="tableRows" border stripe :row-class-name="rowClassName" empty-text="暂无数据">
            <el-table-column label="部门" prop="dept_code" min-width="100" fixed="left" />
            <el-table-column v-for="column in tab.columns" :key="column.key" :min-width="columnWidth(column)" align="right">
              <template #header>
                <el-tooltip v-if="column.help" :content="column.help" placement="top">
                  <span class="column-heading">{{ column.label }}<el-icon class="column-tip"><QuestionFilled /></el-icon></span>
                </el-tooltip>
                <span v-else>{{ column.label }}</span>
              </template>
              <template #default="{ row }">
                <el-input-number
                  v-if="editing && !row.isTotal && !column.derived"
                  v-model="drafts[row.dept_code][column.key]"
                  :class="['cell-input', { changed: isChanged(row.dept_code, column) }]"
                  :min="0"
                  :max="column.type === 'rate' ? 100 : undefined"
                  :precision="column.type === 'int' ? 0 : column.type === 'rate' ? 2 : 4"
                  :controls="false"
                  size="small"
                  :placeholder="column.type === 'rate' ? '%' : ''"
                />
                <span v-else :class="levelClass(row, column)">{{ cellText(row, column) }}</span>
              </template>
            </el-table-column>
          </el-table>
        </el-tab-pane>
      </el-tabs>
    </el-card>

    <el-drawer v-model="helpVisible" title="管控说明" size="720px" append-to-body>
      <section v-for="section in [REVIEW_MECHANISM, EFFICIENCY_RULES]" :key="section.title" class="help-section">
        <h3>{{ section.title }}</h3>
        <el-table :data="section.rows" border size="small">
          <el-table-column v-for="(header, index) in section.headers" :key="header" :label="header" :min-width="index === 0 ? 110 : 140">
            <template #default="{ row }">{{ row[index] }}</template>
          </el-table-column>
        </el-table>
        <div class="help-list-title">{{ section.listTitle }}</div>
        <ol class="help-list">
          <li v-for="item in section.list" :key="item">{{ item }}</li>
        </ol>
      </section>
    </el-drawer>
  </div>
</template>

<script setup name="OpsTarget">
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { QuestionFilled } from '@element-plus/icons-vue'
import { getOpsTargetReport, updateOpsTarget } from '@/api/finance/opsTarget'
import { checkPermi } from '@/utils/permission'
import {
  AVERAGE_KEYS, EFFICIENCY_RULES, REVIEW_MECHANISM, TABS, formatValue, fromInput, toInput
} from './columns'

const report = ref(null)
const years = ref([])
const year = ref(null)
const loading = ref(false)
const saving = ref(false)
const editing = ref(false)
const helpVisible = ref(false)
const notesOpen = ref(false)
const activeTab = ref('annual')
const drafts = reactive({})
const canEdit = computed(() => checkPermi(['finance:opsTarget:edit']))

const rows = computed(() => report.value?.rows || [])
const notes = computed(() => report.value?.notes || [])
const tableRows = computed(() => (report.value?.total && rows.value.length
  ? [...rows.value, { ...report.value.total, isTotal: true, dept_code: '合计' }]
  : rows.value))
const editableColumns = TABS.flatMap(tab => tab.columns).filter(column => !column.derived)
  .filter((column, index, list) => list.findIndex(item => item.key === column.key) === index)

function changesOf(row) {
  const draft = drafts[row.dept_code] || {}
  const values = {}
  for (const column of editableColumns) {
    const next = fromInput(draft[column.key], column.type)
    const current = row[column.key] === undefined ? null : row[column.key]
    if (!sameNumber(next, current)) values[column.key] = next
  }
  return values
}

function sameNumber(a, b) {
  if (a === null || b === null) return a === b
  return Math.abs(Number(a) - Number(b)) < 1e-9
}

const changedCount = computed(() => (editing.value
  ? rows.value.reduce((count, row) => count + Object.keys(changesOf(row)).length, 0)
  : 0))

function isChanged(dept, column) {
  const row = rows.value.find(item => item.dept_code === dept)
  return row ? column.key in changesOf(row) : false
}

async function loadReport() {
  loading.value = true
  try {
    const response = await getOpsTargetReport(year.value || undefined)
    report.value = response.data || null
    years.value = report.value?.years || []
    year.value = report.value?.year ?? null
  } catch (error) {
    report.value = null
  } finally {
    loading.value = false
  }
}

function startEdit() {
  for (const key of Object.keys(drafts)) delete drafts[key]
  for (const row of rows.value) {
    drafts[row.dept_code] = Object.fromEntries(editableColumns.map(column => [column.key, toInput(row[column.key], column.type)]))
  }
  editing.value = true
}

function cancelEdit() {
  editing.value = false
}

async function saveChanges() {
  const pending = rows.value.map(row => [row.dept_code, changesOf(row)]).filter(([, values]) => Object.keys(values).length)
  if (!pending.length) return
  saving.value = true
  let latest = null
  try {
    for (const [dept, values] of pending) {
      latest = (await updateOpsTarget(year.value, dept, values)).data
    }
    if (latest) report.value = latest
    editing.value = false
    ElMessage.success(`已保存 ${pending.length} 个部门的修改`)
  } catch (error) {
    // 已成功的部门保留，失败的部门留在编辑状态便于修正
    await loadReport()
    if (editing.value) startEdit()
  } finally {
    saving.value = false
  }
}

function cellText(row, column) {
  // 合计行的毛利率、人效目标为各部门平均，标出来避免误读成求和
  if (row.isTotal && AVERAGE_KEYS.has(column.key) && row[column.key] !== null && row[column.key] !== undefined) {
    return `${formatValue(row[column.key], column.type)}（平均）`
  }
  return formatValue(row[column.key], column.type)
}

function levelClass(row, column) {
  const level = row.levels?.[column.key]
  return level ? `level-${level}` : ''
}

function columnWidth(column) {
  return column.label.length > 10 ? 150 : 118
}

function rowClassName({ row }) {
  return row.isTotal ? 'total-row' : ''
}

function formatTime(value) {
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString('zh-CN', { hour12: false })
}

onMounted(loadReport)
</script>

<style scoped>
.report-notice { margin-bottom: 10px; }
.notice-toggle { margin-left: 8px; }
.notice-list { margin: 4px 0 0; padding-left: 18px; line-height: 1.7; }
.report-meta { margin-bottom: 8px; color: var(--el-text-color-secondary); font-size: 12px; }
.icon-button { padding: 4px 8px; }
.report-icon { color: #f4ea2a; font-size: 20px; }
.spinning { animation: spin 1s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }
.column-heading { display: inline-flex; align-items: center; gap: 2px; cursor: help; }
.column-tip { color: var(--el-text-color-placeholder); font-size: 13px; }
.cell-input { width: 100%; }
.cell-input.changed :deep(.el-input__wrapper) { box-shadow: 0 0 0 1px var(--el-color-warning) inset; background: var(--el-color-warning-light-9); }
.level-red { color: var(--el-color-danger); font-weight: 600; }
.level-yellow { color: var(--el-color-warning-dark-2, #b88230); font-weight: 600; }
:deep(.total-row) { font-weight: 600; background: var(--el-fill-color-light); }
.help-section + .help-section { margin-top: 24px; }
.help-section h3 { margin: 0 0 10px; font-size: 15px; }
.help-list-title { margin: 12px 0 4px; font-weight: 600; font-size: 13px; }
.help-list { margin: 0; padding-left: 20px; line-height: 1.8; font-size: 13px; }
</style>
