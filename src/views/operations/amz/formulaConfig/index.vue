<template>
  <div class="app-container amz-formula-page">
    <div class="page-toolbar">
      <div>
        <div class="page-title">AMZ公式配置</div>
        <div class="page-subtitle">按区域组维护仓库归属、销量权重和补货计算公式</div>
      </div>
      <el-button type="primary" icon="Plus" @click="handleAdd" v-hasPermi="['operations:amzReplenishment:list']">新增配置</el-button>
    </div>

    <el-table v-loading="loading" :data="list" border stripe class="formula-table">
      <el-table-column label="区域" min-width="160" fixed>
        <template #default="scope">
          <div class="region-cell">
            <el-tag :type="scope.row.enabled === 1 ? 'success' : 'info'" effect="plain">{{ scope.row.regionGroup }}</el-tag>
            <div>
              <div class="region-name">{{ scope.row.regionName }}</div>
              <div class="region-status">{{ scope.row.enabled === 1 ? '已启用' : '已停用' }} / {{ strategyLabel(scope.row.strategyType) }}</div>
            </div>
          </div>
        </template>
      </el-table-column>
      <el-table-column label="匹配仓库" min-width="320">
        <template #default="scope">
          <div class="warehouse-tags">
            <el-tag v-for="wh in warehouseTags(scope.row.marketplaces)" :key="wh" size="small" effect="plain">{{ wh }}</el-tag>
            <span v-if="!scope.row.marketplaces" class="muted">未配置</span>
          </div>
        </template>
      </el-table-column>
      <el-table-column label="销量权重" width="220">
        <template #default="scope">
          <div class="weight-grid">
            <span>14天</span><b>{{ formatWeight(scope.row.salesWeight14d) }}</b>
            <span>30天</span><b>{{ formatWeight(scope.row.salesWeight30d) }}</b>
            <span>60天</span><b>{{ formatWeight(scope.row.salesWeight60d) }}</b>
          </div>
        </template>
      </el-table-column>
      <el-table-column label="计算天数" width="230">
        <template #default="scope">
          <div class="days-line">
            <span>月销 {{ scope.row.monthMultiplier }}</span>
            <span>安全 {{ scope.row.safetyDays }}</span>
            <span>发货 {{ scope.row.shipDays }}</span>
            <span>补货 {{ scope.row.replenishDays }}</span>
          </div>
        </template>
      </el-table-column>
      <el-table-column label="更新时间" width="165" align="center">
        <template #default="scope">{{ parseTime(scope.row.updateTime) }}</template>
      </el-table-column>
      <el-table-column label="操作" width="92" align="center" fixed="right">
        <template #default="scope">
          <el-button size="small" text type="primary" @click="handleEdit(scope.row)">编辑</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog
      :title="dialogTitle"
      v-model="dialogVisible"
      width="1120px"
      top="5vh"
      class="formula-dialog"
      @close="resetForm"
    >
      <el-form ref="formRef" :model="form" :rules="rules" label-width="86px">
        <div class="dialog-grid">
          <section class="config-panel main-panel">
            <div class="panel-title">基础配置</div>
            <el-row :gutter="14">
              <el-col :span="6">
                <el-form-item label="区域组" prop="regionGroup">
                  <el-input v-model="form.regionGroup" placeholder="US / EU" :disabled="isEdit" />
                </el-form-item>
              </el-col>
              <el-col :span="8">
                <el-form-item label="区域名称" prop="regionName">
                  <el-input v-model="form.regionName" placeholder="例如：美国组" />
                </el-form-item>
              </el-col>
              <el-col :span="5">
                <el-form-item label="启用">
                  <el-switch v-model="form.enabled" :active-value="1" :inactive-value="0" />
                </el-form-item>
              </el-col>
            </el-row>
            <el-form-item label="匹配仓库">
              <el-select
                v-model="form.marketplaces"
                multiple
                filterable
                collapse-tags
                collapse-tags-tooltip
                placeholder="选择此区域组包含的仓库"
                style="width:100%"
              >
                <el-option v-for="wh in warehouseOptions" :key="wh" :label="wh" :value="wh" />
              </el-select>
            </el-form-item>
            <el-form-item label="备注">
              <el-input v-model="form.remark" placeholder="可选" />
            </el-form-item>
          </section>

          <section class="config-panel side-panel">
            <div class="panel-title">销量权重</div>
            <div class="weight-summary">
              <span>合计</span>
              <el-tag :type="weightTotalOk ? 'success' : 'warning'" effect="plain">{{ weightTotalText }}</el-tag>
            </div>
            <div class="number-row">
              <span>14天</span>
              <el-input-number v-model="form.salesWeight14d" :min="0" :max="1" :step="0.05" :precision="3" controls-position="right" />
            </div>
            <div class="number-row">
              <span>30天</span>
              <el-input-number v-model="form.salesWeight30d" :min="0" :max="1" :step="0.05" :precision="3" controls-position="right" />
            </div>
            <div class="number-row">
              <span>60天</span>
              <el-input-number v-model="form.salesWeight60d" :min="0" :max="1" :step="0.05" :precision="3" controls-position="right" />
            </div>
          </section>

          <section class="config-panel side-panel">
            <div class="panel-title">计算天数</div>
            <div class="number-row">
              <span>月销</span>
              <el-input-number v-model="form.monthMultiplier" :min="1" :step="1" controls-position="right" />
            </div>
            <div class="number-row">
              <span>安全</span>
              <el-input-number v-model="form.safetyDays" :min="1" :step="1" controls-position="right" />
            </div>
            <div class="number-row">
              <span>发货</span>
              <el-input-number v-model="form.shipDays" :min="1" :step="1" controls-position="right" />
            </div>
            <div class="number-row">
              <span>补货</span>
              <el-input-number v-model="form.replenishDays" :min="1" :step="1" controls-position="right" />
            </div>
          </section>
        </div>

        <section class="config-panel strategy-panel">
          <div class="panel-title">补货策略</div>
          <div class="strategy-grid">
            <button
              v-for="item in strategyOptions"
              :key="item.value"
              type="button"
              class="strategy-card"
              :class="{ active: form.strategyType === item.value }"
              @click="applyStrategy(item.value)"
            >
              <span>{{ item.label }}</span>
              <small>{{ item.desc }}</small>
            </button>
          </div>

          <div class="rule-grid">
            <div class="rule-block">
              <div class="rule-title">销量取值</div>
              <div class="formula-preview">
                <span>平均日销</span>
                <b>14天日均 x {{ formatWeight(form.salesWeight14d) }}</b>
                <b>30天日均 x {{ formatWeight(form.salesWeight30d) }}</b>
                <b>60天日均 x {{ formatWeight(form.salesWeight60d) }}</b>
              </div>
            </div>
            <div class="rule-block">
              <div class="rule-title">补货目标</div>
              <div class="formula-preview">
                <span>目标库存</span>
                <b>平均日销 x {{ form.replenishDays || 0 }} 天</b>
              </div>
            </div>
            <div class="rule-block">
              <div class="rule-title">扣减项</div>
              <el-checkbox v-model="form.deductFbaStock" :true-value="1" :false-value="0">扣减FBA在库</el-checkbox>
              <el-checkbox v-model="form.deductFbaInbound" :true-value="1" :false-value="0">扣减FBA在途</el-checkbox>
              <el-checkbox v-model="form.deductDomesticStock" :true-value="1" :false-value="0">扣减国内仓库存</el-checkbox>
              <el-checkbox v-model="form.deductPurchasedQty" :true-value="1" :false-value="0">扣减已采购数量</el-checkbox>
              <el-checkbox v-model="form.deductPendingShipQty" :true-value="1" :false-value="0">扣减待出库数量</el-checkbox>
            </div>
            <div class="rule-block">
              <div class="rule-title">结果限制</div>
              <el-checkbox v-model="form.allowNegativeReplenish" :true-value="1" :false-value="0">允许负数补货量</el-checkbox>
              <div class="limit-row">
                <span>最小补货量</span>
                <el-input-number v-model="form.minReplenishQty" :min="0" :step="1" controls-position="right" placeholder="不限" />
              </div>
              <div class="limit-row">
                <span>最大补货量</span>
                <el-input-number v-model="form.maxReplenishQty" :min="0" :step="1" controls-position="right" placeholder="不限" />
              </div>
              <div class="limit-row">
                <span>取整方式</span>
                <el-select v-model="form.roundMode">
                  <el-option label="不取整" value="NONE" />
                  <el-option label="四舍五入" value="ROUND" />
                  <el-option label="向上取整" value="CEIL" />
                  <el-option label="向下取整" value="FLOOR" />
                </el-select>
              </div>
            </div>
          </div>
        </section>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" @click="submitForm">保存配置</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup name="AmzFormulaConfig">
import { ref, reactive, getCurrentInstance, computed } from 'vue'
import { listFormulaConfig, addFormulaConfig, updateFormulaConfig, listWarehouses } from '@/api/operations/amz/formulaConfig'
import { parseTime } from '@/utils/ruoyi'

const { proxy } = getCurrentInstance()
const loading = ref(false)
const list = ref([])
const warehouseOptions = ref([])
const dialogVisible = ref(false)
const dialogTitle = ref('')
const isEdit = ref(false)
const formRef = ref(null)

const strategyOptions = [
  { value: 'BALANCED', label: '稳健补货', desc: '兼顾近期和长期销量，适合日常补货' },
  { value: 'AGGRESSIVE', label: '积极补货', desc: '更看重近期销量，适合旺季或增长商品' },
  { value: 'CONSERVATIVE', label: '保守补货', desc: '更看重长期销量，减少短期波动影响' },
  { value: 'CLEARANCE', label: '清库存', desc: '少补或不补，优先消耗现有库存' },
  { value: 'CUSTOM', label: '自定义', desc: '自行调整权重、天数、扣减项和限制' }
]

const strategyPresetMap = {
  BALANCED: {
    salesWeight14d: 0.5, salesWeight30d: 0.4, salesWeight60d: 0.1,
    replenishDays: 120, safetyDays: 90, shipDays: 90,
    deductFbaStock: 1, deductFbaInbound: 1, deductDomesticStock: 1, deductPurchasedQty: 1, deductPendingShipQty: 1,
    allowNegativeReplenish: 1, minReplenishQty: null, maxReplenishQty: null, roundMode: 'NONE'
  },
  AGGRESSIVE: {
    salesWeight14d: 0.7, salesWeight30d: 0.25, salesWeight60d: 0.05,
    replenishDays: 150, safetyDays: 100, shipDays: 100,
    deductFbaStock: 1, deductFbaInbound: 1, deductDomesticStock: 1, deductPurchasedQty: 1, deductPendingShipQty: 1,
    allowNegativeReplenish: 1, minReplenishQty: null, maxReplenishQty: null, roundMode: 'CEIL'
  },
  CONSERVATIVE: {
    salesWeight14d: 0.2, salesWeight30d: 0.5, salesWeight60d: 0.3,
    replenishDays: 90, safetyDays: 75, shipDays: 75,
    deductFbaStock: 1, deductFbaInbound: 1, deductDomesticStock: 1, deductPurchasedQty: 1, deductPendingShipQty: 1,
    allowNegativeReplenish: 0, minReplenishQty: 0, maxReplenishQty: null, roundMode: 'FLOOR'
  },
  CLEARANCE: {
    salesWeight14d: 0.2, salesWeight30d: 0.3, salesWeight60d: 0.5,
    replenishDays: 30, safetyDays: 30, shipDays: 30,
    deductFbaStock: 1, deductFbaInbound: 1, deductDomesticStock: 1, deductPurchasedQty: 1, deductPendingShipQty: 1,
    allowNegativeReplenish: 0, minReplenishQty: 0, maxReplenishQty: 0, roundMode: 'FLOOR'
  }
}

const defaultFormula = '{d14}*{w14}+{d30}*{w30}+{d60}*{w60}'
const defaultForm = {
  strategyType: 'BALANCED',
  regionGroup: '',
  regionName: '',
  marketplaces: [],
  salesWeight14d: 0.5,
  salesWeight30d: 0.4,
  salesWeight60d: 0.1,
  monthMultiplier: 30,
  safetyDays: 90,
  shipDays: 90,
  replenishDays: 120,
  deductFbaStock: 1,
  deductFbaInbound: 1,
  deductDomesticStock: 1,
  deductPurchasedQty: 1,
  deductPendingShipQty: 1,
  allowNegativeReplenish: 1,
  minReplenishQty: null,
  maxReplenishQty: null,
  roundMode: 'NONE',
  enabled: 1,
  remark: '',
  formulaMonthly: defaultFormula,
  formulaSafety: defaultFormula,
  formulaShip: defaultFormula,
  formulaReplenish: defaultFormula,
  formulaRestock: defaultFormula
}
const form = reactive({ ...defaultForm })
const rules = {
  regionGroup: [{ required: true, message: '请输入区域组', trigger: 'blur' }],
  regionName: [{ required: true, message: '请输入区域名称', trigger: 'blur' }]
}

const weightTotal = computed(() =>
  Number(form.salesWeight14d || 0) + Number(form.salesWeight30d || 0) + Number(form.salesWeight60d || 0)
)
const weightTotalText = computed(() => weightTotal.value.toFixed(3).replace(/\.?0+$/, ''))
const weightTotalOk = computed(() => Math.abs(weightTotal.value - 1) < 0.001)

function applyStrategy(type) {
  form.strategyType = type
  const preset = strategyPresetMap[type]
  if (preset) Object.assign(form, preset)
}

function warehouseTags(value) {
  if (!value) return []
  return String(value).split(',').map(v => v.trim()).filter(Boolean)
}

function formatWeight(value) {
  const num = Number(value || 0)
  return Number.isFinite(num) ? num.toFixed(3).replace(/\.?0+$/, '') : '0'
}

function strategyLabel(value) {
  return strategyOptions.find(item => item.value === value)?.label || '自定义'
}

function getList() {
  loading.value = true
  listFormulaConfig().then(res => {
    list.value = res.data || []
  }).finally(() => {
    loading.value = false
  })
}

async function openDialog(row) {
  if (!warehouseOptions.value.length) {
    const r = await listWarehouses()
    warehouseOptions.value = r.data || []
  }
  if (row) {
    isEdit.value = true
    dialogTitle.value = '编辑公式配置'
    const data = { ...row, marketplaces: row.marketplaces ? row.marketplaces.split(',') : [] }
    applyConfigDefaults(data)
    Object.assign(form, data)
  } else {
    isEdit.value = false
    dialogTitle.value = '新增公式配置'
    Object.assign(form, { ...defaultForm, marketplaces: [] })
  }
  dialogVisible.value = true
}

function handleAdd() {
  openDialog()
}

function handleEdit(row) {
  openDialog(row)
}

function resetForm() {
  formRef.value?.resetFields()
}

function applyConfigDefaults(data) {
  Object.keys(defaultForm).forEach(key => {
    if (data[key] === undefined || data[key] === null) data[key] = defaultForm[key]
  })
}

function buildFormulaFields(data) {
  const weighted = '{d14}*{w14}+{d30}*{w30}+{d60}*{w60}'
  const fbaParts = []
  if (Number(data.deductFbaStock) === 1 || Number(data.deductFbaInbound) === 1) fbaParts.push('{fba}')
  const deductParts = []
  if (Number(data.deductPurchasedQty) === 1) deductParts.push('{purchases}')
  if (Number(data.deductDomesticStock) === 1) deductParts.push('{domestic}')
  if (fbaParts.length) deductParts.push(...fbaParts)
  if (Number(data.deductPendingShipQty) === 1) deductParts.push('{locked}')
  const deductExpr = deductParts.length ? ' - ' + deductParts.join(' - ') : ''
  data.formulaWeightedDaily = weighted
  data.formulaMonthly = `(${weighted}) * {month}`
  data.formulaSafety = `(${weighted}) * {safety}`
  data.formulaShip = `(${weighted}) * {ship}${fbaParts.length ? ' - ' + fbaParts.join(' - ') : ''}`
  data.formulaReplenish = `(${weighted}) * {replenish}${deductExpr}`
  data.formulaRestock = `({fba} - ((${weighted}) * {replenish}${deductExpr})) / (${weighted})`
}

function submitForm() {
  formRef.value?.validate(async (valid) => {
    if (!valid) return
    const data = {
      ...form,
      marketplaces: Array.isArray(form.marketplaces) ? form.marketplaces.join(',') : form.marketplaces
    }
    buildFormulaFields(data)
    await (isEdit.value ? updateFormulaConfig : addFormulaConfig)(data)
    proxy.$modal.msgSuccess(isEdit.value ? '修改成功' : '新增成功')
    dialogVisible.value = false
    getList()
  })
}

getList()
</script>

<style scoped>
.amz-formula-page {
  background: #f6f8fb;
}

.page-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 14px 16px;
  margin-bottom: 12px;
  background: #fff;
  border: 1px solid #e6eaf0;
  border-radius: 8px;
}

.page-title {
  font-size: 18px;
  font-weight: 700;
  color: #1f2d3d;
}

.page-subtitle {
  margin-top: 4px;
  font-size: 12px;
  color: #7b8794;
}

.formula-table {
  background: #fff;
}

.region-cell {
  display: flex;
  align-items: center;
  gap: 10px;
}

.region-name {
  font-size: 13px;
  font-weight: 600;
  color: #303133;
}

.region-status,
.muted {
  font-size: 12px;
  color: #909399;
}

.warehouse-tags {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
  min-height: 26px;
}

.weight-grid {
  display: grid;
  grid-template-columns: repeat(3, auto 1fr);
  align-items: center;
  column-gap: 5px;
  row-gap: 4px;
  font-size: 12px;
}

.weight-grid span {
  color: #909399;
}

.weight-grid b {
  color: #303133;
  font-weight: 600;
}

.days-line {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  font-size: 12px;
  color: #606266;
}

.dialog-grid {
  display: grid;
  grid-template-columns: 1fr 250px 250px;
  gap: 12px;
  align-items: stretch;
}

.config-panel {
  background: #fff;
  border: 1px solid #e6eaf0;
  border-radius: 8px;
  padding: 14px;
}

.panel-title {
  margin-bottom: 12px;
  font-size: 14px;
  font-weight: 700;
  color: #303133;
}

.side-panel {
  min-height: 190px;
}

.weight-summary {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 10px;
  font-size: 12px;
  color: #606266;
}

.number-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  margin-bottom: 10px;
}

.number-row span {
  width: 42px;
  font-size: 13px;
  color: #606266;
}

.number-row :deep(.el-input-number) {
  width: 155px;
}

.strategy-panel {
  margin-top: 12px;
}

.strategy-grid {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: 10px;
  margin-bottom: 12px;
}

.strategy-card {
  min-height: 76px;
  padding: 10px 12px;
  text-align: left;
  background: #f7f9fc;
  border: 1px solid #e6eaf0;
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.16s;
}

.strategy-card.active {
  background: #ecf5ff;
  border-color: #409eff;
  box-shadow: 0 0 0 1px rgba(64, 158, 255, 0.12);
}

.strategy-card span {
  display: block;
  font-size: 13px;
  font-weight: 700;
  color: #303133;
}

.strategy-card small {
  display: block;
  margin-top: 6px;
  line-height: 1.45;
  color: #7b8794;
  font-size: 12px;
}

.rule-grid {
  display: grid;
  grid-template-columns: 1fr 1fr 1.1fr 1.2fr;
  gap: 12px;
}

.rule-block {
  min-height: 150px;
  padding: 12px;
  background: #fafbfc;
  border: 1px solid #e6eaf0;
  border-radius: 8px;
}

.rule-title {
  margin-bottom: 10px;
  font-size: 13px;
  font-weight: 700;
  color: #303133;
}

.formula-preview {
  display: flex;
  flex-direction: column;
  gap: 8px;
  color: #606266;
}

.formula-preview span {
  color: #909399;
  font-size: 12px;
}

.formula-preview b {
  font-weight: 600;
  color: #303133;
}

.rule-block :deep(.el-checkbox) {
  display: flex;
  height: 26px;
  margin-right: 0;
}

.limit-row {
  display: grid;
  grid-template-columns: 76px 1fr;
  align-items: center;
  gap: 8px;
  margin-top: 8px;
}

.limit-row span {
  font-size: 12px;
  color: #606266;
}

.limit-row :deep(.el-input-number),
.limit-row :deep(.el-select) {
  width: 100%;
}

@media (max-width: 1200px) {
  .dialog-grid,
  .strategy-grid,
  .rule-grid {
    grid-template-columns: 1fr;
  }
}
</style>
