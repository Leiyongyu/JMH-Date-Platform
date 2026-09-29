<template>
  <el-dialog :model-value="modelValue" title="eBay补货2.0 · 参数" width="min(1180px, 96vw)"
    top="5vh" append-to-body destroy-on-close :close-on-click-modal="false" :before-close="close"
    @update:model-value="value => !value && close()">
    <div v-loading="loading">
      <el-alert type="info" :closable="false" show-icon
        title="全局参数：n训练期天数已用于ADI计算，保存后刷新列表。比例按小数填写，例如 0.3 表示 30%。" />
      <p class="parameter-note">默认值及原始说明来自《模块字段》。当前天数参数可手动维护；说明中的自动计算和历史数据仅作为参考。</p>
      <el-alert v-if="!editable" title="当前账号可查看参数，修改需要公式配置权限。" type="warning" :closable="false" />
      <el-alert v-if="error" :title="error" type="error" :closable="false" class="parameter-error" />
      <el-tabs v-model="activeModule">
        <el-tab-pane v-for="module in modules" :key="module.key" :label="module.label" :name="module.key">
          <el-table :data="module.rows" row-key="key" border max-height="60vh">
            <el-table-column :label="labelFor(module.key)" prop="label" :width="module.key === 'basic' ? 210 : 130" />
            <el-table-column :label="module.key === 'grade' ? '下限分' : module.key === 'dimension' ? '权重' : '值'"
              :width="module.key === 'pattern' ? 440 : 235">
              <template #default="{ row }">
                <div :class="{ 'pattern-values': module.key === 'pattern' }">
                  <div v-for="field in valueFields(module, row)" :key="field.key" class="parameter-input">
                    <label v-if="module.key === 'pattern'" :for="`parameter-${field.key}`">{{ field.label }}</label>
                    <el-select v-if="field.type === 'grade'" v-model="values[field.key]"
                      :aria-label="row.label" :disabled="!editable || saving" style="width: 160px">
                      <el-option v-for="grade in ['S', 'A', 'B', 'C', 'D']" :key="grade" :label="grade" :value="grade" />
                    </el-select>
                    <el-input-number v-else :id="`parameter-${field.key}`" v-model="values[field.key]"
                      :aria-label="`${row.label} ${field.label}`" :min="Number(field.min)" :max="Number(field.max)"
                      :step="field.precision === 0 ? 1 : 0.01" :step-strictly="field.precision === 0"
                      :precision="field.precision === 0 ? 0 : undefined" controls-position="right"
                      :disabled="!editable || saving" :placeholder="field.nullable ? '留空自动推算' : '必填'" />
                    <span class="parameter-default">默认 {{ field.defaultValue }}</span>
                  </div>
                </div>
              </template>
            </el-table-column>
            <el-table-column v-if="module.key === 'dimension'" label="启用" min-width="140">
              <template #default="{ row }">
                <el-switch v-model="values[row.fields[1].key]" :active-value="1" :inactive-value="0"
                  :aria-label="`${row.label}启用`" :disabled="!editable || saving" />
                <span class="parameter-default">默认{{ row.fields[1].defaultValue === '1' ? '启用' : '关闭' }}</span>
              </template>
            </el-table-column>
            <el-table-column v-else prop="description" label="说明" min-width="280">
              <template #default="{ row }"><div class="parameter-description">{{ row.description }}</div></template>
            </el-table-column>
          </el-table>
          <p v-if="module.key === 'grade'" class="parameter-note">等级下限分需满足 S &gt; A &gt; B &gt; C &gt; D，范围 0～100。</p>
          <p v-if="module.key === 'dimension'" class="parameter-note">七个维度权重合计为1（包括未启用维度）；启用状态独立保存。</p>
        </el-tab-pane>
      </el-tabs>
    </div>
    <template #footer>
      <el-button v-if="editable" :disabled="loading || saving || !modules.length" @click="restoreDefaults">恢复默认值</el-button>
      <el-button :disabled="saving" @click="close()">{{ editable ? '取消' : '关闭' }}</el-button>
      <el-button v-if="editable" type="primary" :loading="saving" :disabled="loading || !modules.length" @click="save">保存参数</el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { getEbayReplenishmentV2Parameters, saveEbayReplenishmentV2Parameters } from '@/api/operations/ebay/replenishmentV2'

const props = defineProps({ modelValue: Boolean, editable: Boolean })
const emit = defineEmits(['update:modelValue', 'saved'])
const modules = ref([])
const values = ref({})
const activeModule = ref('basic')
const loading = ref(false)
const saving = ref(false)
const error = ref('')
let revision = ''
let savedValues = ''
let requestVersion = 0
const allFields = () => modules.value.flatMap(module => module.rows.flatMap(row => row.fields))
const labelFor = key => ({ basic: '参数', pattern: '形态', grade: '等级', dimension: '维度' })[key]
const valueFields = (module, row) => module.key === 'dimension' ? row.fields.slice(0, 1) : row.fields

function applySnapshot(data) {
  modules.value = data.modules
  revision = data.revision
  values.value = Object.fromEntries(allFields().map(field => [field.key,
    data.values[field.key] == null ? undefined : field.type === 'grade' ? data.values[field.key] : Number(data.values[field.key])]))
  savedValues = JSON.stringify(values.value)
}

watch(() => props.modelValue, async open => {
  const version = ++requestVersion
  if (!open) return
  modules.value = []
  values.value = {}
  savedValues = '{}'
  revision = ''
  error.value = ''
  activeModule.value = 'basic'
  loading.value = true
  try {
    const response = await getEbayReplenishmentV2Parameters()
    if (version === requestVersion) applySnapshot(response.data)
  } catch (e) {
    if (version === requestVersion) error.value = e?.message || '参数加载失败，请重新打开弹窗重试'
  } finally {
    if (version === requestVersion) loading.value = false
  }
})

async function close(done) {
  if (saving.value) return
  if (JSON.stringify(values.value) !== savedValues) {
    try { await ElMessageBox.confirm('参数尚未保存，确定放弃本次修改吗？', '未保存的修改', { type: 'warning' }) }
    catch { return }
  }
  requestVersion++
  emit('update:modelValue', false)
  if (typeof done === 'function') done()
}

async function restoreDefaults() {
  try { await ElMessageBox.confirm('将四个模块恢复为附件默认值，点击“保存参数”后生效。', '恢复默认值', { type: 'warning' }) }
  catch { return }
  values.value = Object.fromEntries(allFields().map(field => [field.key,
    field.type === 'grade' ? field.defaultValue : Number(field.defaultValue)]))
  error.value = ''
}

async function save() {
  const payload = {}
  for (const field of allFields()) {
    const value = values.value[field.key]
    if (value == null || value === '') {
      if (!field.nullable) { error.value = `${field.label}不能为空`; return }
      payload[field.key] = null
    } else {
      if (field.type !== 'grade' && !Number.isFinite(value)) { error.value = `${field.label}必须为有效数字`; return }
      payload[field.key] = String(value)
    }
  }
  saving.value = true
  error.value = ''
  try {
    const response = await saveEbayReplenishmentV2Parameters({ revision, values: payload })
    applySnapshot(response.data)
    ElMessage.success('参数已保存')
    emit('update:modelValue', false)
    emit('saved')
  } catch (e) {
    error.value = e?.message || '保存失败，请重试'
  } finally {
    saving.value = false
  }
}
</script>

<style scoped>
.parameter-note, .parameter-default { color: var(--el-text-color-secondary); font-size: 12px; }
.parameter-default { display: block; margin-top: 4px; }
.parameter-error { margin-bottom: 12px; }
.parameter-input .el-input-number { width: 185px; max-width: 100%; }
.pattern-values { display: flex; gap: 12px; }
.pattern-values .parameter-input { flex: 1; min-width: 0; }
.pattern-values label { display: block; margin-bottom: 5px; }
.pattern-values .el-input-number { width: 125px; }
.parameter-description { line-height: 1.6; white-space: pre-wrap; overflow-wrap: anywhere; }
</style>
