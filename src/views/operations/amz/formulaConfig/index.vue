<template>
  <div class="app-container">
    <el-row :gutter="10" class="mb8">
      <el-col :span="1.5">
        <el-button type="primary" icon="Plus" @click="handleAdd" v-hasPermi="['operations:amzReplenishment:list']">新增</el-button>
      </el-col>
    </el-row>

    <el-table v-loading="loading" :data="list" border stripe>
      <el-table-column label="区域组" prop="regionGroup" width="80" />
      <el-table-column label="区域名称" prop="regionName" width="120" />
      <el-table-column label="匹配仓库" prop="marketplaces" width="280" show-overflow-tooltip />
      <el-table-column label="14d权重" prop="salesWeight14d" width="85" align="right" />
      <el-table-column label="30d权重" prop="salesWeight30d" width="85" align="right" />
      <el-table-column label="60d权重" prop="salesWeight60d" width="85" align="right" />
      <el-table-column label="月销" prop="monthMultiplier" width="65" align="right" />
      <el-table-column label="安全" prop="safetyDays" width="65" align="right" />
      <el-table-column label="发货" prop="shipDays" width="65" align="right" />
      <el-table-column label="补货" prop="replenishDays" width="65" align="right" />
      <el-table-column label="启用" prop="enabled" width="60" align="center">
        <template #default="scope">{{ scope.row.enabled === 1 ? '是' : '否' }}</template>
      </el-table-column>
      <el-table-column label="更新时间" width="150" align="center">
        <template #default="scope">{{ parseTime(scope.row.updateTime) }}</template>
      </el-table-column>
      <el-table-column label="操作" width="80" align="center" fixed="right">
        <template #default="scope">
          <el-button size="small" text type="primary" @click="handleEdit(scope.row)">编辑</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog :title="dialogTitle" v-model="dialogVisible" width="900px" @close="resetForm">
      <el-form ref="formRef" :model="form" :rules="rules" label-width="80px">
        <el-row :gutter="12">
          <el-col :span="6"><el-form-item label="区域组" prop="regionGroup"><el-input v-model="form.regionGroup" placeholder="US/EU" :disabled="isEdit" size="small" /></el-form-item></el-col>
          <el-col :span="8"><el-form-item label="名称" prop="regionName"><el-input v-model="form.regionName" placeholder="美国组" size="small" /></el-form-item></el-col>
          <el-col :span="6"><el-form-item label="启用"><el-switch v-model="form.enabled" :active-value="1" :inactive-value="0" size="small" /></el-form-item></el-col>
        </el-row>
        <el-form-item label="匹配仓库"><el-select v-model="form.marketplaces" multiple filterable placeholder="选择归属仓库" style="width:100%" size="small"><el-option v-for="wh in warehouseOptions" :key="wh" :label="wh" :value="wh" /></el-select></el-form-item>

        <!-- 系数面板 -->
        <div class="coef-panel">
          <div class="coef-row">
            <span class="coef-label">权重</span>
            <span class="coef-tag">14天</span><el-input-number v-model="form.salesWeight14d" :min="0" :max="1" :step="0.1" :precision="3" size="small" style="width:100px" />
            <span class="coef-tag">30天</span><el-input-number v-model="form.salesWeight30d" :min="0" :max="1" :step="0.1" :precision="3" size="small" style="width:100px" />
            <span class="coef-tag">60天</span><el-input-number v-model="form.salesWeight60d" :min="0" :max="1" :step="0.1" :precision="3" size="small" style="width:100px" />
          </div>
          <div class="coef-row">
            <span class="coef-label">天数</span>
            <span class="coef-tag">月销</span><el-input-number v-model="form.monthMultiplier" :min="1" :step="1" size="small" style="width:100px" />
            <span class="coef-tag">安全</span><el-input-number v-model="form.safetyDays" :min="1" :step="1" size="small" style="width:100px" />
            <span class="coef-tag">发货</span><el-input-number v-model="form.shipDays" :min="1" :step="1" size="small" style="width:100px" />
            <span class="coef-tag">补货</span><el-input-number v-model="form.replenishDays" :min="1" :step="1" size="small" style="width:100px" />
          </div>
        </div>

        <!-- 公式构建器 -->
        <div v-for="item in formulaItems" :key="item.key" class="builder-block">
          <div class="builder-header">
            <span class="builder-icon">{{ item.icon }}</span>
            <span>{{ item.label }}</span>
            <el-button size="small" text type="danger" @click="form[item.key]=''" style="margin-left:auto">清空</el-button>
          </div>
          <div class="builder-display" @click="activeField=item.key" :class="{active:activeField===item.key}">
            <template v-if="form[item.key]">
              <span v-for="(part,i) in renderFormula(item.key)" :key="i" :class="part.type">{{ part.text }}</span>
            </template>
            <span v-else class="placeholder">点击下方变量和运算符组装公式</span>
          </div>
          <div v-show="activeField===item.key" class="builder-palette">
            <div class="palette-title">📐 数据变量</div>
            <div class="chip-group">
              <span v-for="v in dataVars" :key="v.key" class="chip var" @click="insertVar(item.key, v.key)">{{ v.label }}</span>
            </div>
            <div class="palette-title" style="margin-top:8px">⚙️ 系数变量</div>
            <div class="chip-group">
              <span v-for="v in coefVars" :key="v.key" class="chip coef" @click="insertVar(item.key, v.key)">{{ v.label }}</span>
            </div>
            <div class="palette-title" style="margin-top:8px">➕ 运算符</div>
            <div class="chip-group">
              <span v-for="op in operators" :key="op.key" class="chip op" @click="insertVar(item.key, op.key)">{{ op.label }}</span>
            </div>
          </div>
        </div>

        <el-form-item label="备注" style="margin-top:12px"><el-input v-model="form.remark" size="small" placeholder="可选" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false" size="small">取消</el-button>
        <el-button type="primary" @click="submitForm" size="small">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup name="AmzFormulaConfig">
import { ref, reactive, getCurrentInstance } from 'vue'
import { listFormulaConfig, addFormulaConfig, updateFormulaConfig, listWarehouses } from '@/api/operations/amz/formulaConfig'
import { parseTime } from '@/utils/ruoyi'

const { proxy } = getCurrentInstance()
const loading = ref(false), list = ref([]), warehouseOptions = ref([])
const dialogVisible = ref(false), dialogTitle = ref(''), isEdit = ref(false), formRef = ref(null)
const activeField = ref('')

const dataVars = [
  { key: '{d14}', label: '14天日均' }, { key: '{d30}', label: '30天日均' }, { key: '{d60}', label: '60天日均' },
  { key: '{fba}', label: 'FBA库存' }, { key: '{purchases}', label: '已采购' },
  { key: '{domestic}', label: '国内仓' }, { key: '{locked}', label: '待出库' }
]
const coefVars = [
  { key: '{w14}', label: '14天权重' }, { key: '{w30}', label: '30天权重' }, { key: '{w60}', label: '60天权重' },
  { key: '{month}', label: '月销乘数' }, { key: '{safety}', label: '安全天数' },
  { key: '{ship}', label: '发货天数' }, { key: '{replenish}', label: '补货天数' }
]
const operators = [
  { key: '+', label: '＋' }, { key: '-', label: '－' }, { key: '*', label: '×' }, { key: '/', label: '÷' },
  { key: '(', label: '( )' }, { key: ')', label: ')' }
]

const formulaItems = [
  { key: 'formulaMonthly', label: '月均销量', icon: '📊' },
  { key: 'formulaSafety', label: '安全库存', icon: '🛡️' },
  { key: 'formulaShip', label: '发货量', icon: '🚚' },
  { key: 'formulaReplenish', label: '补货量', icon: '📦' },
  { key: 'formulaRestock', label: '补货时间', icon: '⏱️' }
]

const defaultForm = {
  regionGroup: '', regionName: '', marketplaces: [],
  salesWeight14d: 0.5, salesWeight30d: 0.4, salesWeight60d: 0.1,
  monthMultiplier: 30, safetyDays: 90, shipDays: 90, replenishDays: 120,
  enabled: 1, remark: '',
  formulaMonthly: '{d14}*{w14}+{d30}*{w30}+{d60}*{w60}',
  formulaSafety: '{d14}*{w14}+{d30}*{w30}+{d60}*{w60}',
  formulaShip: '{d14}*{w14}+{d30}*{w30}+{d60}*{w60}',
  formulaReplenish: '{d14}*{w14}+{d30}*{w30}+{d60}*{w60}',
  formulaRestock: '{d14}*{w14}+{d30}*{w30}+{d60}*{w60}'
}
const form = reactive({ ...defaultForm })
const rules = { regionGroup: [{ required: true }], regionName: [{ required: true }] }

function insertVar(field, key) {
  if (!form[field]) form[field] = ''
  form[field] += key
}
function renderFormula(field) {
  const expr = form[field] || ''
  const parts = []
  let remaining = expr
  while (remaining.length) {
    let match = null
    for (const v of [...dataVars, ...coefVars]) {
      if (remaining.startsWith(v.key)) { match = v; break }
    }
    if (match) {
      parts.push({ text: match.label, type: match.key.startsWith('{w') || match.key.startsWith('{m') || match.key.startsWith('{sa') || match.key.startsWith('{sh') || match.key.startsWith('{r') ? 'chip-coef' : 'chip-data' })
      remaining = remaining.slice(match.key.length)
    } else {
      const ch = remaining[0]
      parts.push({ text: ch, type: ch.match(/[+\-*/()]/) ? 'chip-op' : 'raw' })
      remaining = remaining.slice(1)
    }
  }
  return parts
}

function getList() {
  loading.value = true
  listFormulaConfig().then(res => { list.value = res.data || [] }).finally(() => { loading.value = false })
}
async function openDialog(row) {
  if (!warehouseOptions.value.length) { const r = await listWarehouses(); warehouseOptions.value = r.data || [] }
  if (row) {
    isEdit.value = true; dialogTitle.value = '编辑公式配置'
    const d = { ...row, marketplaces: row.marketplaces ? row.marketplaces.split(',') : [] }
    for (const k of formulaItems.map(i => i.key)) { if (!d[k]) d[k] = defaultForm[k] }
    Object.assign(form, d)
  } else {
    isEdit.value = false; dialogTitle.value = '新增公式配置'
    Object.assign(form, { ...defaultForm, marketplaces: [] })
  }
  activeField.value = ''; dialogVisible.value = true
}
function handleAdd() { openDialog() }
function handleEdit(row) { openDialog(row) }
function resetForm() { formRef.value?.resetFields() }
function submitForm() {
  formRef.value?.validate(async (valid) => {
    if (!valid) return
    const data = { ...form, marketplaces: Array.isArray(form.marketplaces) ? form.marketplaces.join(',') : form.marketplaces }
    await (isEdit.value ? updateFormulaConfig : addFormulaConfig)(data)
    proxy.$modal.msgSuccess(isEdit.value ? '修改成功' : '新增成功')
    dialogVisible.value = false; getList()
  })
}
getList()
</script>

<style scoped>
.coef-panel { margin:12px 0;padding:10px 14px;background:#fafafa;border-radius:6px;border:1px solid #eee }
.coef-row { display:flex;align-items:center;gap:6px;margin-bottom:4px;flex-wrap:wrap }
.coef-label { font-size:12px;color:#909399;width:32px }
.coef-tag { font-size:12px;color:#606266;width:28px }
.builder-block { margin:10px 0;border:1px solid #ebeef5;border-radius:6px;overflow:hidden }
.builder-header { display:flex;align-items:center;padding:8px 12px;background:#f5f7fa;font-size:13px;font-weight:500;gap:6px }
.builder-icon { font-size:15px }
.builder-display { padding:10px 12px;min-height:36px;cursor:pointer;font-family:monospace;font-size:14px;line-height:1.8;background:#fff;border-bottom:1px solid #ebeef5 }
.builder-display.active { background:#f0f5ff }
.placeholder { color:#c0c4cc;font-family:inherit }
.builder-palette { padding:8px 12px;background:#fafafa }
.palette-title { font-size:12px;color:#909399;margin-bottom:4px }
.chip-group { display:flex;flex-wrap:wrap;gap:6px }
.chip { display:inline-block;padding:3px 8px;border-radius:4px;font-size:12px;cursor:pointer;user-select:none;transition:all 0.15s }
.chip:hover { filter:brightness(0.95) }
.chip.var { background:#e6f7ff;color:#1890ff;border:1px solid #91d5ff }
.chip.coef { background:#fff7e6;color:#fa8c16;border:1px solid #ffd591 }
.chip.op { background:#f5f5f5;color:#303133;border:1px solid #d9d9d9;font-weight:600;font-size:14px }
.chip-data { display:inline;padding:1px 4px;border-radius:3px;background:#e6f7ff;color:#1890ff;font-size:11px;margin:0 1px }
.chip-coef { display:inline;padding:1px 4px;border-radius:3px;background:#fff7e6;color:#fa8c16;font-size:11px;margin:0 1px }
.chip-op { display:inline;color:#303133;font-weight:600;margin:0 1px }
.raw { display:inline;color:#c0c4cc;margin:0 1px }
</style>
