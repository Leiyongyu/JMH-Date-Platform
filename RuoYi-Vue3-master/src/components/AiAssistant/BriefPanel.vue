<template>
  <el-dialog v-model="visible" title="定时简报" width="620px" append-to-body @open="load">
    <div class="brief-tip">到点后助手按你当时的账号权限自动提问，结果保存在「定时简报：名称」对话里。</div>
    <el-table v-loading="loading" :data="briefs" size="small" border empty-text="还没有定时简报">
      <el-table-column prop="title" label="名称" min-width="110" show-overflow-tooltip />
      <el-table-column label="周期" width="120">
        <template #default="{ row }">{{ briefSchedule(row) }}</template>
      </el-table-column>
      <el-table-column label="状态" width="70">
        <template #default="{ row }">{{ row.enabled ? '启用' : '停用' }}</template>
      </el-table-column>
      <el-table-column label="上次执行" width="110">
        <template #default="{ row }">{{ formatTime(row.lastRunAt) }}</template>
      </el-table-column>
      <el-table-column label="操作" width="150">
        <template #default="{ row }">
          <el-button link type="primary" @click="edit(row)">编辑</el-button>
          <el-button link type="primary" :loading="runningId === row.id" @click="runNow(row)">立即运行</el-button>
          <el-button link type="danger" @click="remove(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-form ref="formRef" :model="form" :rules="rules" label-width="72px" class="brief-form">
      <div class="brief-form-title">{{ form.id ? '编辑简报' : '新建简报' }}</div>
      <el-form-item label="名称" prop="title"><el-input v-model="form.title" maxlength="60" placeholder="例如：每周销售周报" /></el-form-item>
      <el-form-item label="问题" prop="question">
        <el-input v-model="form.question" type="textarea" :rows="2" maxlength="1000" placeholder="例如：上周各组别净销售额和毛利率，和前一周相比变化多少？" />
      </el-form-item>
      <el-form-item label="周期">
        <el-select v-model="form.frequency" style="width: 96px">
          <el-option v-for="(label, value) in BRIEF_FREQUENCY" :key="value" :label="label" :value="value" />
        </el-select>
        <el-select v-if="form.frequency === 'weekly'" v-model="form.weekday" style="width: 96px; margin-left: 8px">
          <el-option v-for="(label, index) in WEEKDAYS" :key="index" :label="`周${label}`" :value="index + 1" />
        </el-select>
        <el-select v-if="form.frequency === 'monthly'" v-model="form.monthDay" style="width: 96px; margin-left: 8px">
          <el-option v-for="day in 28" :key="day" :label="`${day}日`" :value="day" />
        </el-select>
        <el-select v-model="form.runHour" style="width: 96px; margin-left: 8px">
          <el-option v-for="hour in 24" :key="hour" :label="`${String(hour - 1).padStart(2, '0')}:00`" :value="hour - 1" />
        </el-select>
        <el-switch v-model="form.enabled" active-text="启用" style="margin-left: 12px" />
      </el-form-item>
      <div class="brief-actions">
        <el-button v-if="form.id" @click="reset">取消编辑</el-button>
        <el-button type="primary" :loading="saving" @click="save">{{ form.id ? '保存' : '新建' }}</el-button>
      </div>
    </el-form>
  </el-dialog>
</template>

<script setup>
import { reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { deleteAiBrief, listAiBriefs, runAiBrief, saveAiBrief } from '@/api/system/aiAssistant'
import { BRIEF_FREQUENCY, WEEKDAYS, briefSchedule } from './agentRun'

const emit = defineEmits(['ran'])
const visible = defineModel({ type: Boolean, default: false })
const briefs = ref([])
const loading = ref(false)
const saving = ref(false)
const runningId = ref(null)
const formRef = ref()
const empty = () => ({ id: null, title: '', question: '', frequency: 'weekly', weekday: 1, monthDay: 1, runHour: 9, enabled: true })
const form = reactive(empty())
const rules = {
  title: [{ required: true, message: '请填写名称', trigger: 'blur' }],
  question: [{ required: true, min: 2, message: '请填写要问的问题', trigger: 'blur' }]
}

function requestId(scope) {
  return `erp-ai-brief-${scope}-${Date.now()}-${Math.random().toString(16).slice(2, 10)}`
}

async function load() {
  loading.value = true
  try {
    const response = await listAiBriefs(requestId('list'))
    briefs.value = Array.isArray(response.data) ? response.data : []
  } catch (error) {
    ElMessage.error(error?.msg || error?.message || '加载定时简报失败')
  } finally {
    loading.value = false
  }
}

function reset() {
  Object.assign(form, empty())
  formRef.value?.clearValidate()
}

function edit(row) {
  Object.assign(form, {
    id: row.id, title: row.title, question: row.question, frequency: row.frequency,
    weekday: row.weekday || 1, monthDay: row.monthDay || 1, runHour: row.runHour, enabled: row.enabled
  })
}

async function save() {
  if (!(await formRef.value.validate().catch(() => false))) return
  saving.value = true
  try {
    await saveAiBrief(form.id, {
      title: form.title.trim(), question: form.question.trim(), frequency: form.frequency,
      weekday: form.frequency === 'weekly' ? form.weekday : null,
      month_day: form.frequency === 'monthly' ? form.monthDay : null,
      run_hour: form.runHour, enabled: form.enabled
    }, requestId('save'))
    ElMessage.success('已保存')
    reset()
    await load()
  } catch (error) {
    ElMessage.error(error?.msg || error?.message || '保存失败')
  } finally {
    saving.value = false
  }
}

async function runNow(row) {
  runningId.value = row.id
  try {
    const response = await runAiBrief(row.id, requestId('run'))
    ElMessage.success('已开始执行，稍后在对应对话里查看结果')
    emit('ran', response.data)
    await load()
  } catch (error) {
    ElMessage.error(error?.msg || error?.message || '执行失败')
  } finally {
    runningId.value = null
  }
}

async function remove(row) {
  try {
    await ElMessageBox.confirm(`确定删除定时简报「${row.title}」吗？已生成的对话会保留。`, '删除简报', { type: 'warning' })
    await deleteAiBrief(row.id, requestId('delete'))
    if (form.id === row.id) reset()
    await load()
  } catch (error) {
    if (error !== 'cancel' && error !== 'close') ElMessage.error(error?.msg || error?.message || '删除失败')
  }
}

function formatTime(value) {
  if (!value) return '--'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? '--'
    : date.toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })
}
</script>

<style lang="scss" scoped>
.brief-tip { margin-bottom: 10px; color: var(--el-text-color-secondary, #909399); font-size: 12px; }
.brief-form { margin-top: 16px; padding-top: 12px; border-top: 1px solid var(--el-border-color-lighter, #ebeef5); }
.brief-form-title { margin-bottom: 10px; font-weight: 600; font-size: 13px; }
.brief-actions { text-align: right; }
</style>
