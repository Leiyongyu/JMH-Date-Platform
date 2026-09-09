<template>
  <el-dialog :model-value="modelValue" title="产品等级规则配置" width="1050px"
    append-to-body destroy-on-close :close-on-click-modal="false" :before-close="close"
    @update:model-value="value => !value && close()">
    <el-alert type="warning" :closable="false" show-icon
      title="全局配置：修改后影响全部 SKU 的产品等级及两组安全库存、建议补货量。按序号从小到大取第一条命中。" />
    <p class="help">变量：return_rate（退货率）、profit_rate（利润率）、sell_through_ratio（动销比），百分比用小数，如 6% 写 0.06。
      支持 + - * /、比较、and / or / not、括号及 true / false。缺少规则所需数据时显示 --。</p>
    <el-alert v-if="error" :title="error" type="error" :closable="false" />
    <el-table :data="rows" v-loading="loading" row-key="rule_no" max-height="520" border>
      <el-table-column prop="rule_no" label="序号" width="60" />
      <el-table-column label="条件表达式" min-width="370">
        <template #default="{ row }"><el-input v-model="row.condition_expr" type="textarea"
          :rows="2" maxlength="500" :disabled="saving" @input="changed" /></template>
      </el-table-column>
      <el-table-column label="等级" width="100">
        <template #default="{ row }"><el-select v-model="row.result_level" :disabled="saving" @change="changed">
          <el-option v-for="level in ['S','A','B','C']" :key="level" :label="level" :value="level" />
        </el-select></template>
      </el-table-column>
      <el-table-column label="说明" min-width="170">
        <template #default="{ row }"><el-input v-model="row.remark" maxlength="255" :disabled="saving" @input="changed" /></template>
      </el-table-column>
      <el-table-column label="启用" width="75">
        <template #default="{ row }"><el-switch v-model="row.status" :active-value="1" :inactive-value="0"
          :disabled="saving" @change="changed" /></template>
      </el-table-column>
      <el-table-column label="校验" min-width="140">
        <template #default="{ row }">
          <span :class="{ invalid: checks[row.rule_no]?.valid === false }">
            {{ checks[row.rule_no]?.error || (checks[row.rule_no]?.valid ? '语法正确' : '待校验') }}
          </span>
        </template>
      </el-table-column>
    </el-table>
    <template #footer>
      <el-button :disabled="saving" @click="close()">取消</el-button>
      <el-button type="primary" :loading="saving" :disabled="loading || rows.length !== 9"
        @click="save">保存并重新计算</el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref, watch, onBeforeUnmount } from 'vue'
import { ElMessage } from 'element-plus'
import { getEbayReplenishmentV2LevelRules, saveEbayReplenishmentV2LevelRules,
  validateEbayReplenishmentV2LevelRules } from '@/api/operations/ebay/replenishmentV2'

const props = defineProps({ modelValue: Boolean })
const emit = defineEmits(['update:modelValue', 'saved'])
const rows = ref([])
const checks = ref({})
const error = ref('')
const loading = ref(false)
const saving = ref(false)
let revision = ''
let version = 0
let timer
function draft() {
  return rows.value.map(({ rule_no, condition_expr, result_level, remark, status }) =>
    ({ rule_no, condition_expr, result_level, remark, status }))
}
function close(done) {
  if (saving.value) return
  version++
  clearTimeout(timer)
  emit('update:modelValue', false)
  if (typeof done === 'function') done()
}
async function validate(token, configs) {
  const response = await validateEbayReplenishmentV2LevelRules({ configs })
  if (token !== version || !props.modelValue) return false
  const data = response?.data || {}
  checks.value = Object.fromEntries((data.rows || []).map(row => [row.rule_no, row]))
  return data.valid === true
}
function changed() {
  const token = ++version
  checks.value = {}
  error.value = ''
  clearTimeout(timer)
  timer = setTimeout(async () => {
    try { await validate(token, draft()) }
    catch (e) { if (token === version) error.value = '校验失败，请检查表达式或稍后重试；未保存任何改动。' }
  }, 500)
}
watch(() => props.modelValue, async open => {
  const token = ++version
  clearTimeout(timer)
  if (!open) return
  rows.value = []
  checks.value = {}
  error.value = ''
  revision = ''
  loading.value = true
  try {
    const response = await getEbayReplenishmentV2LevelRules()
    if (token !== version || !props.modelValue) return
    rows.value = response?.data?.configs || []
    revision = response?.data?.revision || ''
    await validate(token, draft())
  } catch (e) {
    if (token === version) error.value = '规则加载或校验失败，请检查配置表和权限后重新打开。'
  } finally { if (token === version) loading.value = false }
})
async function save() {
  if (saving.value || loading.value) return
  saving.value = true
  clearTimeout(timer)
  const token = ++version
  const configs = draft()
  error.value = ''
  try {
    if (!await validate(token, configs)) {
      error.value = '有规则校验未通过，请修正标红的行；未保存任何改动。'
      return
    }
    await saveEbayReplenishmentV2LevelRules({ configs, revision })
    ElMessage.success('已保存，正在重新计算')
    emit('update:modelValue', false)
    emit('saved')
  } catch (e) {
    error.value = '保存失败，未完成本次配置更新；若规则已被他人修改，请重新打开后编辑。'
  } finally { saving.value = false }
}
onBeforeUnmount(() => { version++; clearTimeout(timer) })
</script>

<style scoped>
.help { line-height: 1.8; color: #606266; }
.invalid { color: #f56c6c; }
</style>

