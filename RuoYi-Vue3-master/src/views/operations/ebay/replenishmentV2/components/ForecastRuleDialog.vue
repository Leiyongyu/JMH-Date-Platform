<template>
  <el-dialog
    :model-value="modelValue" title="预估销量2规则配置" width="1100px"
    append-to-body destroy-on-close class="forecast-rule-dialog"
    :close-on-click-modal="false" :close-on-press-escape="!saving" :show-close="!saving"
    @update:model-value="changeVisible"
  >
    <el-alert type="warning" :closable="false" show-icon
      title="保存后影响全部SKU的预估销量2；试算只使用当前草稿，不会保存"
      description="语法正确不代表所有输入都能计算，请试算核对。新品缺库龄显示--；改动会影响安全库存2和建议补货量2，原安全库存及建议补货量保持原口径。"
    />
    <div class="rule-help">
      <div>变量：<code>s7 / s15 / s30</code> 近7/15/30天销量；<code>r7 / r15 / r30</code> 对应日均；<code>age</code> 最老批次库龄（缺失按0表示）。</div>
      <div>支持：+ − * /、&gt; &gt;= &lt; &lt;= == !=、and / or / not、括号、true / false。</div>
      <div>按序号升序取第一条命中的启用规则。当前档位只写下界，上界由前一条未命中保证，无需重复维护。</div>
    </div>
    <el-alert v-if="errorText" :title="errorText" type="error" :closable="false" class="rule-error" />
    <el-form :disabled="loading || saving" @submit.prevent>
      <el-table ref="ruleTable" v-loading="loading" :data="configs" row-key="rule_no"
        :row-class-name="({ row }) => 'forecast-rule-' + row.rule_no" border size="small" max-height="450">
        <el-table-column prop="rule_no" label="序号" width="58" align="center" />
        <el-table-column prop="product_nature" label="性质" width="70" align="center" />
        <el-table-column label="条件表达式" min-width="245">
          <template #default="{ row }">
            <el-input v-model="row.condition_expr" type="textarea" :rows="2" maxlength="500"
              :aria-label="'规则' + row.rule_no + '条件'" @input="draftChanged(row.rule_no)" />
          </template>
        </el-table-column>
        <el-table-column label="公式表达式" min-width="245">
          <template #default="{ row }">
            <el-input v-model="row.formula_expr" type="textarea" :rows="2" maxlength="500"
              :aria-label="'规则' + row.rule_no + '公式'" @input="draftChanged(row.rule_no)" />
          </template>
        </el-table-column>
        <el-table-column label="说明" min-width="155">
          <template #default="{ row }">
            <el-input v-model="row.remark" type="textarea" :rows="2" maxlength="255"
              :aria-label="'规则' + row.rule_no + '说明'" @input="draftChanged(row.rule_no)" />
          </template>
        </el-table-column>
        <el-table-column label="启用" width="65" align="center">
          <template #default="{ row }">
            <el-switch v-model="row.status" :active-value="1" :inactive-value="0"
              :aria-label="'启用规则' + row.rule_no" @change="draftChanged(row.rule_no)" />
          </template>
        </el-table-column>
        <el-table-column label="语法校验" min-width="125">
          <template #default="{ row }">
            <span v-if="!validation[row.rule_no]" class="rule-muted">待校验</span>
            <el-tag v-else-if="validation[row.rule_no].valid" type="success" size="small">语法正确</el-tag>
            <div v-else class="rule-invalid">
              <div v-for="(message, field) in validation[row.rule_no].errors" :key="field">
                {{ field === 'condition_expr' ? '条件' : '公式' }}：{{ message }}
              </div>
            </div>
          </template>
        </el-table-column>
      </el-table>

      <el-collapse v-model="expanded" class="rule-preview">
        <el-collapse-item title="试算当前草稿（无需保存）" name="preview">
          <div class="sku-loader">
            <el-select v-model="skuSite" placeholder="站点" filterable allow-create
              aria-label="试算SKU站点" @change="skuChanged">
              <el-option v-for="site in siteOptions" :key="site" :label="site" :value="site" />
            </el-select>
            <el-input v-model="skuCode" placeholder="完整SKU，精确匹配" aria-label="试算完整SKU"
              @input="skuChanged" @keyup.enter="loadSku" />
            <el-button :loading="skuLoading" :disabled="loading || saving" @click="loadSku">载入真实SKU数据</el-button>
          </div>
          <div v-if="sourceText" class="rule-muted">{{ sourceText }}</div>
          <div class="trial-fields">
            <label>近7天销量<el-input v-model="sample.sales_7d" inputmode="decimal" @input="sampleChanged" /></label>
            <label>近15天销量<el-input v-model="sample.sales_15d" inputmode="decimal" @input="sampleChanged" /></label>
            <label>近30天销量<el-input v-model="sample.sales_30d" inputmode="decimal" @input="sampleChanged" /></label>
            <label>库龄（天）<el-input v-model="sample.age_days" inputmode="decimal" placeholder="空值表示缺失" @input="sampleChanged" /></label>
            <label>产品性质
              <el-select v-model="sample.product_nature" @change="sampleChanged">
                <el-option label="新品" value="新品" /><el-option label="老品" value="老品" />
                <el-option label="未知" value="" />
              </el-select>
            </label>
          </div>
          <div v-if="previewResult" class="trial-result" aria-live="polite">
            <strong>结果：{{ previewResult.value ?? '--' }}</strong>
            <span v-if="previewResult.matched_rule_no">　命中规则 {{ previewResult.matched_rule_no }}</span>
            <span v-else-if="previewResult.failed_rule_no">　出错规则 {{ previewResult.failed_rule_no }}</span>
            <div>{{ previewResult.message }}</div>
            <div v-if="previewResult.remark">{{ previewResult.remark }}</div>
            <div v-if="previewResult.condition_expr">条件：<code>{{ previewResult.condition_expr }}</code> → 成立</div>
            <div v-if="previewResult.formula_expr">公式：<code>{{ previewResult.formula_expr }}</code></div>
          </div>
          <div v-else class="rule-muted">输入数据后点击“试算”；修改规则或输入后，旧试算结果自动失效。</div>
        </el-collapse-item>
      </el-collapse>
    </el-form>
    <template #footer>
      <span v-if="validating" class="rule-muted">正在校验草稿…</span>
      <el-button :disabled="saving" @click="changeVisible(false)">取消</el-button>
      <el-button :loading="previewing" :disabled="loading || saving || configs.length !== 13" @click="runPreview">试算</el-button>
      <el-button type="primary" :loading="saving" :disabled="loading || configs.length !== 13" @click="saveRules">保存并重新计算</el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { onBeforeUnmount, reactive, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import {
  getEbayReplenishmentV2ForecastRules, saveEbayReplenishmentV2ForecastRules,
  validateEbayReplenishmentV2ForecastRules, previewEbayReplenishmentV2ForecastRules,
  getEbayReplenishmentV2ForecastSku
} from '@/api/operations/ebay/replenishmentV2'

const props = defineProps({ modelValue: Boolean, siteOptions: { type: Array, default: () => [] } })
const emit = defineEmits(['update:modelValue', 'saved'])
const configs = ref([])
const revision = ref('')
const validation = ref({})
const loading = ref(false)
const saving = ref(false)
const validating = ref(false)
const previewing = ref(false)
const skuLoading = ref(false)
const errorText = ref('')
const ruleTable = ref(null)
const expanded = ref(['preview'])
const previewResult = ref(null)
const skuSite = ref('')
const skuCode = ref('')
const sourceText = ref('')
const sample = reactive({ sales_7d: '0', sales_15d: '0', sales_30d: '0', age_days: '', product_nature: '新品' })
let lifecycle = 0
let draftVersion = 0
let validationRequest = 0
let previewRequest = 0
let skuRequest = 0
let validationTimer = null

function message(error) {
  const detail = error?.response?.data?.msg || error?.response?.data?.detail || error?.message
  if (Array.isArray(detail)) return detail.map(item => item.msg || String(item)).join('；')
  return typeof detail === 'string' ? detail : '操作失败，请重试'
}

function draftPayload() {
  return configs.value.map(row => ({
    rule_no: row.rule_no, product_nature: row.product_nature,
    condition_expr: row.condition_expr, formula_expr: row.formula_expr,
    remark: row.remark || null, status: row.status
  }))
}

function invalidatePreview() {
  previewRequest++
  previewing.value = false
  previewResult.value = null
}

function cancelPending() {
  lifecycle++
  validationRequest++
  skuRequest++
  clearTimeout(validationTimer)
  validationTimer = null
  validating.value = false
  skuLoading.value = false
  invalidatePreview()
}

function changeVisible(value) {
  if (!saving.value) emit('update:modelValue', value)
}

async function loadRules() {
  cancelPending()
  const life = lifecycle
  loading.value = true
  errorText.value = ''
  configs.value = []
  validation.value = {}
  revision.value = ''
  sourceText.value = ''
  try {
    const response = await getEbayReplenishmentV2ForecastRules()
    if (life !== lifecycle || !props.modelValue) return
    const data = response?.data
    if (!Array.isArray(data?.configs) || data.configs.length !== 13 || !data.revision) {
      throw new Error('没有读到完整13条规则，请检查规则表初始化')
    }
    configs.value = data.configs.map(row => ({
      rule_no: Number(row.rule_no), product_nature: row.product_nature,
      condition_expr: row.condition_expr || '', formula_expr: row.formula_expr || '',
      remark: row.remark || '', status: Number(row.status)
    }))
    revision.value = data.revision
    draftVersion++
    await validateCurrent()
  } catch (error) {
    if (life === lifecycle) errorText.value = message(error)
  } finally {
    if (life === lifecycle) loading.value = false
  }
}

function draftChanged(ruleNo) {
  draftVersion++
  validation.value = { ...validation.value, [ruleNo]: null }
  invalidatePreview()
  clearTimeout(validationTimer)
  validationTimer = setTimeout(() => { validateCurrent() }, 500)
}

async function validateCurrent() {
  clearTimeout(validationTimer)
  const version = draftVersion
  const life = lifecycle
  const request = ++validationRequest
  validating.value = true
  try {
    const response = await validateEbayReplenishmentV2ForecastRules({ configs: draftPayload() })
    if (life !== lifecycle || version !== draftVersion || request !== validationRequest || !props.modelValue) return false
    const data = response?.data
    if (!Array.isArray(data?.rows) || data.rows.length !== 13 || typeof data.valid !== 'boolean') {
      throw new Error('校验响应不完整，禁止保存')
    }
    validation.value = Object.fromEntries(data.rows.map(row => [row.rule_no, row]))
    errorText.value = ''
    return data.valid
  } catch (error) {
    if (life === lifecycle && version === draftVersion && request === validationRequest) {
      errorText.value = message(error)
    }
    return false
  } finally {
    if (life === lifecycle && request === validationRequest) validating.value = false
  }
}

function revealInvalidRule() {
  const invalid = configs.value.find(row => !validation.value[row.rule_no]?.valid)
  if (invalid) {
    ruleTable.value?.$el?.querySelector('.forecast-rule-' + invalid.rule_no)?.scrollIntoView({ block: 'nearest' })
  }
}

function sampleChanged() {
  sourceText.value = ''
  skuRequest++ // a late SKU load must not overwrite manually edited values
  skuLoading.value = false
  invalidatePreview()
}

function skuChanged() {
  skuRequest++
  skuLoading.value = false
  sourceText.value = ''
  invalidatePreview()
}

async function loadSku() {
  if (!skuSite.value.trim() || !skuCode.value.trim()) {
    ElMessage.warning('请填写站点和完整SKU')
    return
  }
  const request = ++skuRequest
  const life = lifecycle
  skuLoading.value = true
  errorText.value = ''
  try {
    const response = await getEbayReplenishmentV2ForecastSku({ site: skuSite.value.trim(), sku: skuCode.value.trim() })
    if (life !== lifecycle || request !== skuRequest || !props.modelValue) return
    const data = response?.data
    Object.assign(sample, {
      sales_7d: String(data.sales_7d), sales_15d: String(data.sales_15d), sales_30d: String(data.sales_30d),
      age_days: data.age_days == null ? '' : String(data.age_days), product_nature: data.product_nature || ''
    })
    invalidatePreview()
    sourceText.value = `已载入 ${data.site} / ${data.sku}，销量截至 ${data.anchor_date}。请点击试算当前草稿。`
  } catch (error) {
    if (life === lifecycle && request === skuRequest) errorText.value = message(error)
  } finally {
    if (life === lifecycle && request === skuRequest) skuLoading.value = false
  }
}

async function runPreview() {
  const request = ++previewRequest
  const life = lifecycle
  const version = draftVersion
  previewing.value = true
  previewResult.value = null
  try {
    if (!await validateCurrent()) { revealInvalidRule(); return }
    if (life !== lifecycle || request !== previewRequest || version !== draftVersion) return
    const inputs = {}
    for (const key of ['sales_7d', 'sales_15d', 'sales_30d', 'age_days']) {
      const value = String(sample[key]).trim()
      if (key === 'age_days' && !value) { inputs[key] = null; continue }
      if (!value || !Number.isFinite(Number(value)) || Number(value) < 0 || Number(value) > 1e24) {
        throw new Error('试算销量和库龄须为有效非负数，只有库龄可以留空')
      }
      inputs[key] = value // preserve the user's decimal text in the request
    }
    const response = await previewEbayReplenishmentV2ForecastRules({
      configs: draftPayload(), ...inputs, product_nature: sample.product_nature || null
    })
    if (life !== lifecycle || request !== previewRequest || version !== draftVersion || !props.modelValue) return
    if (!response?.data?.result?.status) throw new Error('试算响应不完整，请重试')
    previewResult.value = response?.data?.result
  } catch (error) {
    if (life === lifecycle && request === previewRequest) errorText.value = message(error)
  } finally {
    if (life === lifecycle && request === previewRequest) previewing.value = false
  }
}

async function saveRules() {
  if (saving.value) return
  saving.value = true
  const life = lifecycle
  try {
    if (!await validateCurrent()) {
      revealInvalidRule()
      ElMessage.warning('规则校验未通过，本次没有保存')
      return
    }
    await saveEbayReplenishmentV2ForecastRules({ configs: draftPayload(), revision: revision.value })
    if (life !== lifecycle) return
    ElMessage.success('规则已保存，正在重新计算全部SKU')
    emit('saved')
    emit('update:modelValue', false)
  } catch (error) {
    if (life === lifecycle) errorText.value = message(error)
  } finally {
    saving.value = false
  }
}

watch(() => props.modelValue, value => { if (value) loadRules(); else cancelPending() }, { immediate: true })
onBeforeUnmount(cancelPending)
</script>

<style scoped>
.rule-help { margin: 12px 0; line-height: 1.8; font-size: 12px; color: #606266; }
.rule-error { margin-bottom: 12px; }
.rule-invalid { color: #c45656; font-size: 12px; overflow-wrap: anywhere; }
.rule-muted { color: #909399; font-size: 12px; }
.rule-preview { margin-top: 16px; }
.sku-loader { display: flex; flex-wrap: wrap; gap: 10px; margin-bottom: 10px; }
.sku-loader > .el-select { width: 150px; }
.sku-loader > .el-input { width: 250px; }
.trial-fields { display: grid; grid-template-columns: repeat(5, minmax(100px, 1fr)); gap: 10px; margin: 12px 0; }
.trial-fields label { display: grid; gap: 6px; color: #606266; font-size: 12px; }
.trial-result { padding: 12px; background: #f5f7fa; line-height: 1.8; overflow-wrap: anywhere; }
code { font-family: Consolas, monospace; }
@media (max-width: 720px) {
  .trial-fields { grid-template-columns: repeat(2, minmax(100px, 1fr)); }
}
</style>
