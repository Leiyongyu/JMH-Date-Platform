<template>
  <div class="app-container customs-inventory-page">
    <div class="page-bar">
      <div class="page-heading">
        <h2>出入库清单</h2>
        <span>汽配含税产品出入库明细</span>
      </div>
      <div class="toolbar">
        <el-button type="primary" icon="Plus" @click="handleAdd"
          v-hasPermi="['customs:inventory:add']">新增</el-button>
        <el-button type="primary" icon="Upload" :loading="importing" @click="openFile"
          v-hasPermi="['customs:inventory:import']">导入 Excel</el-button>
        <el-button icon="Download" :disabled="!selectedRows.length" :loading="exporting" @click="handleExportSelected"
          v-hasPermi="['customs:inventory:export']">导出选中</el-button>
        <el-button icon="Download" :loading="exporting" @click="handleExportAll"
          v-hasPermi="['customs:inventory:export']">导出全部</el-button>
        <el-button icon="Refresh" @click="getList">刷新</el-button>
      </div>
      <input ref="fileRef" class="file-input" type="file" accept=".xlsx" @change="handleFileChange">
    </div>

    <el-form :model="queryParams" ref="queryRef" :inline="true" class="query-form">
      <el-form-item label="关键词" prop="keyword">
        <el-input v-model="queryParams.keyword" placeholder="SKU / 编码 / 产品名称" clearable @keyup.enter="handleQuery" />
      </el-form-item>
      <el-form-item>
        <el-button type="primary" icon="Search" @click="handleQuery">搜索</el-button>
        <el-button icon="Refresh" @click="resetQuery">重置</el-button>
      </el-form-item>
    </el-form>

    <el-table v-loading="loading" :data="list" border stripe height="620" class="inventory-table"
      @selection-change="handleSelectionChange">
      <el-table-column type="selection" width="48" fixed="left" align="center" />
      <el-table-column label="编码" prop="productCode" width="135" fixed="left" show-overflow-tooltip />
      <el-table-column label="产品名称" prop="productName" width="130" show-overflow-tooltip />
      <el-table-column label="SKU" prop="sku" width="150" show-overflow-tooltip />
      <el-table-column label="采购数量" prop="purchaseQuantity" width="120" show-overflow-tooltip />
      <el-table-column label="单位" prop="unit" width="70" align="center" />
      <el-table-column label="含税单价" prop="taxIncludedPrice" width="105" show-overflow-tooltip />
      <el-table-column label="采购日期" prop="purchaseDate" width="100" />
      <el-table-column label="入库日期" prop="inboundDate" width="100" />
      <el-table-column label="入库数量" prop="inboundQuantity" width="95" align="right" :formatter="integerFormatter" />
      <el-table-column label="入库备注" prop="inboundRemark" width="120" show-overflow-tooltip />
      <el-table-column label="出库日期" prop="outboundDate" width="150" show-overflow-tooltip />
      <el-table-column label="捷克仓" prop="czechWarehouseQty" width="85" align="right" :formatter="integerFormatter" />
      <el-table-column label="英国仓" prop="ukWarehouseQty" width="85" align="right" :formatter="integerFormatter" />
      <el-table-column label="美国谷仓" prop="usWarehouseQty" width="95" align="right" :formatter="integerFormatter" />
      <el-table-column label="德国仓" prop="deWarehouseQty" width="85" align="right" :formatter="integerFormatter" />
      <el-table-column label="FBA(DE)" prop="fbaDeQty" width="88" align="right" :formatter="integerFormatter" />
      <el-table-column label="FBA(UK)" prop="fbaUkQty" width="88" align="right" :formatter="integerFormatter" />
      <el-table-column label="FBA(US)" prop="fbaUsQty" width="88" align="right" :formatter="integerFormatter" />
      <el-table-column label="FBA(FR)" prop="fbaFrQty" width="88" align="right" :formatter="integerFormatter" />
      <el-table-column label="剩余库存" prop="remainingStock" width="95" align="right" :formatter="integerFormatter" />
      <el-table-column label="备注" prop="remark" width="140" show-overflow-tooltip />
      <el-table-column label="报关计量单位" prop="customsUnit" width="115" align="center" />
      <el-table-column label="申报要素" prop="declarationElements" min-width="180" show-overflow-tooltip />
      <el-table-column label="操作" width="86" fixed="right" align="center">
        <template #default="scope">
          <el-button link type="primary" icon="Edit" @click="handleEdit(scope.row)"
            v-hasPermi="['customs:inventory:edit']">编辑</el-button>
        </template>
      </el-table-column>
    </el-table>

    <pagination v-show="total > 0" :total="total" v-model:page="queryParams.pageNum"
      v-model:limit="queryParams.pageSize" @pagination="getList" />

    <el-dialog :title="dialogTitle" v-model="dialogVisible" width="980px" append-to-body>
      <el-form ref="formRef" :model="form" :rules="rules" label-width="108px" class="inventory-form">
        <el-form-item label="编码" prop="productCode">
          <el-autocomplete
            v-model="form.productCode"
            clearable
            value-key="value"
            :fetch-suggestions="(query, callback) => queryProductSuggestions('productCode', query, callback)"
            :disabled="!canEditField('productCode')"
            placeholder="输入或搜索编码"
            @select="applyProductOption"
            @clear="clearProductField('productCode')"
          >
            <template #default="{ item }">
              <div class="product-option">
                <span>{{ item.productCode || '-' }}</span>
                <small>{{ item.productName || '-' }} / {{ item.sku || '-' }} / {{ item.unit || '-' }}</small>
              </div>
            </template>
          </el-autocomplete>
        </el-form-item>
        <el-form-item label="产品名称" prop="productName">
          <el-autocomplete
            v-model="form.productName"
            clearable
            value-key="value"
            :fetch-suggestions="(query, callback) => queryProductSuggestions('productName', query, callback)"
            :disabled="!canEditField('productName')"
            placeholder="输入或搜索产品名称"
            @select="applyProductOption"
            @clear="clearProductField('productName')"
          >
            <template #default="{ item }">
              <div class="product-option">
                <span>{{ item.productName || '-' }}</span>
                <small>{{ item.productCode || '-' }} / {{ item.sku || '-' }} / {{ item.unit || '-' }}</small>
              </div>
            </template>
          </el-autocomplete>
        </el-form-item>
        <el-form-item label="SKU" prop="sku">
          <el-autocomplete
            v-model="form.sku"
            clearable
            value-key="value"
            :fetch-suggestions="(query, callback) => queryProductSuggestions('sku', query, callback)"
            :disabled="!canEditField('sku')"
            placeholder="输入或搜索SKU"
            @select="applyProductOption"
            @clear="clearProductField('sku')"
          >
            <template #default="{ item }">
              <div class="product-option">
                <span>{{ item.sku || '-' }}</span>
                <small>{{ item.productCode || '-' }} / {{ item.productName || '-' }} / {{ item.unit || '-' }}</small>
              </div>
            </template>
          </el-autocomplete>
        </el-form-item>
        <el-form-item label="采购数量"><el-input v-model="form.purchaseQuantity" :disabled="!canEditField('purchaseQuantity')" /></el-form-item>
        <el-form-item label="单位">
          <el-autocomplete
            v-model="form.unit"
            clearable
            value-key="value"
            :fetch-suggestions="(query, callback) => queryProductSuggestions('unit', query, callback)"
            :disabled="!canEditField('unit')"
            placeholder="输入或搜索单位"
            @select="applyProductOption"
            @clear="clearProductField('unit')"
          >
            <template #default="{ item }">
              <div class="product-option">
                <span>{{ item.unit || '-' }}</span>
                <small>{{ item.productCode || '-' }} / {{ item.productName || '-' }} / {{ item.sku || '-' }}</small>
              </div>
            </template>
          </el-autocomplete>
        </el-form-item>
        <el-form-item label="含税单价"><el-input v-model="form.taxIncludedPrice" :disabled="!canEditField('taxIncludedPrice')" /></el-form-item>
        <el-form-item label="采购日期">
          <el-date-picker
            v-model="form.purchaseDate"
            type="date"
            value-format="YYYY/M/D"
            format="YYYY/M/D"
            placeholder="选择采购日期"
            :disabled="!canEditField('purchaseDate')"
            clearable
          />
        </el-form-item>
        <el-form-item label="入库日期">
          <el-date-picker
            v-model="form.inboundDate"
            type="date"
            value-format="YYYY/M/D"
            format="YYYY/M/D"
            placeholder="选择入库日期"
            :disabled="!canEditField('inboundDate')"
            clearable
          />
        </el-form-item>
        <el-form-item label="入库数量">
          <el-input-number v-model="form.inboundQuantity" :controls="false" :precision="0" :step="1" step-strictly :disabled="!canEditField('inboundQuantity')" />
        </el-form-item>
        <el-form-item label="入库备注"><el-input v-model="form.inboundRemark" :disabled="!canEditField('inboundRemark')" /></el-form-item>
        <el-form-item label="出库日期">
          <el-date-picker
            v-model="form.outboundDate"
            type="date"
            value-format="YYYY/M/D"
            format="YYYY/M/D"
            placeholder="选择出库日期"
            :disabled="!canEditField('outboundDate')"
            clearable
          />
        </el-form-item>
        <el-form-item label="捷克仓"><el-input-number v-model="form.czechWarehouseQty" :controls="false" :precision="0" :step="1" step-strictly :disabled="!canEditField('czechWarehouseQty')" /></el-form-item>
        <el-form-item label="英国仓"><el-input-number v-model="form.ukWarehouseQty" :controls="false" :precision="0" :step="1" step-strictly :disabled="!canEditField('ukWarehouseQty')" /></el-form-item>
        <el-form-item label="美国谷仓"><el-input-number v-model="form.usWarehouseQty" :controls="false" :precision="0" :step="1" step-strictly :disabled="!canEditField('usWarehouseQty')" /></el-form-item>
        <el-form-item label="德国仓"><el-input-number v-model="form.deWarehouseQty" :controls="false" :precision="0" :step="1" step-strictly :disabled="!canEditField('deWarehouseQty')" /></el-form-item>
        <el-form-item label="FBA(DE)"><el-input-number v-model="form.fbaDeQty" :controls="false" :precision="0" :step="1" step-strictly :disabled="!canEditField('fbaDeQty')" /></el-form-item>
        <el-form-item label="FBA(UK)"><el-input-number v-model="form.fbaUkQty" :controls="false" :precision="0" :step="1" step-strictly :disabled="!canEditField('fbaUkQty')" /></el-form-item>
        <el-form-item label="FBA(US)"><el-input-number v-model="form.fbaUsQty" :controls="false" :precision="0" :step="1" step-strictly :disabled="!canEditField('fbaUsQty')" /></el-form-item>
        <el-form-item label="FBA(FR)"><el-input-number v-model="form.fbaFrQty" :controls="false" :precision="0" :step="1" step-strictly :disabled="!canEditField('fbaFrQty')" /></el-form-item>
        <el-form-item label="剩余库存"><el-input-number v-model="form.remainingStock" :controls="false" :precision="0" :step="1" step-strictly :disabled="!canEditField('remainingStock')" /></el-form-item>
        <el-form-item label="备注"><el-input v-model="form.remark" :disabled="!canEditField('remark')" /></el-form-item>
        <el-form-item label="报关计量单位"><el-input v-model="form.customsUnit" :disabled="!canEditField('customsUnit')" /></el-form-item>
        <el-form-item label="申报要素" class="span-3"><el-input v-model="form.declarationElements" type="textarea" :rows="2" :disabled="!canEditField('declarationElements')" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取 消</el-button>
        <el-button type="primary" :loading="saving" @click="submitForm">保 存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup name="CustomsInventory">
import { saveAs } from 'file-saver'
import { blobValidate } from '@/utils/ruoyi'
import {
  addCustomsInventory,
  exportCustomsInventory,
  getCustomsInventoryEditableFields,
  importCustomsInventory,
  listCustomsInventory,
  searchCustomsInventoryProducts,
  updateCustomsInventory
} from '@/api/operations/customs/inventory'

const { proxy } = getCurrentInstance()
const loading = ref(false)
const importing = ref(false)
const exporting = ref(false)
const saving = ref(false)
const total = ref(0)
const list = ref([])
const fileRef = ref()
const selectedRows = ref([])
const dialogVisible = ref(false)
const editMode = ref(false)
const editableFields = ref([])
let productSearchSeq = 0
const dialogTitle = computed(() => editMode.value ? '编辑出入库记录' : '新增出入库记录')

const queryParams = reactive({
  pageNum: 1,
  pageSize: 20,
  keyword: ''
})

const form = reactive(createForm())
const rules = {
  sku: [{ validator: validateSkuOrName, trigger: 'blur' }],
  productName: [{ validator: validateSkuOrName, trigger: 'blur' }]
}

function createForm() {
  const today = todayText()
  return {
    id: null,
    productCode: '',
    productName: '',
    sku: '',
    purchaseQuantity: '',
    unit: '',
    taxIncludedPrice: '',
    purchaseDate: today,
    inboundDate: today,
    inboundQuantity: null,
    inboundRemark: '',
    outboundDate: today,
    czechWarehouseQty: null,
    ukWarehouseQty: null,
    usWarehouseQty: null,
    deWarehouseQty: null,
    fbaDeQty: null,
    fbaUkQty: null,
    fbaUsQty: null,
    fbaFrQty: null,
    remainingStock: null,
    remark: '',
    customsUnit: '',
    declarationElements: ''
  }
}

function todayText() {
  const date = new Date()
  return `${date.getFullYear()}/${date.getMonth() + 1}/${date.getDate()}`
}

function resetFormModel() {
  Object.assign(form, createForm())
  resetProductSearch()
}

function getList() {
  loading.value = true
  listCustomsInventory(queryParams).then(response => {
    list.value = response.rows || []
    total.value = response.total || 0
  }).finally(() => { loading.value = false })
}

function handleQuery() {
  queryParams.pageNum = 1
  getList()
}

function resetQuery() {
  proxy.resetForm('queryRef')
  handleQuery()
}

function integerFormatter(row, column, value) {
  if (value === null || value === undefined || value === '') return ''
  const numberValue = Number(value)
  if (Number.isNaN(numberValue)) return value
  return String(Math.trunc(numberValue))
}

function openFile() {
  fileRef.value?.click()
}

function handleSelectionChange(selection) {
  selectedRows.value = selection
}

function handleAdd() {
  resetFormModel()
  editableFields.value = []
  editMode.value = false
  dialogVisible.value = true
}

async function handleEdit(row) {
  resetFormModel()
  await loadEditableFields()
  Object.assign(form, {
    ...createForm(),
    ...row
  })
  editMode.value = true
  dialogVisible.value = true
}

async function queryProductSuggestions(field, query, callback) {
  const seq = ++productSearchSeq
  try {
    const response = await searchCustomsInventoryProducts(buildProductSearchParams(field, query))
    if (seq !== productSearchSeq) return
    const options = (response.data || []).map(item => normalizeProductOption(item, field))
    callback(options)
  } catch (error) {
    callback([])
  }
}

function buildProductSearchParams(field, query) {
  const keyword = query || ''
  return {
    productCode: field === 'productCode' ? keyword : form.productCode,
    productName: field === 'productName' ? keyword : form.productName,
    sku: field === 'sku' ? keyword : form.sku,
    unit: field === 'unit' ? keyword : form.unit
  }
}

function normalizeProductOption(item, field) {
  return {
    ...item,
    value: item[field] || item.productCode || item.productName || item.sku || item.unit || ''
  }
}

function applyProductOption(option) {
  form.productCode = option.productCode || ''
  form.productName = option.productName || ''
  form.sku = option.sku || ''
  form.unit = option.unit || ''
  proxy.$refs.formRef?.clearValidate?.(['sku', 'productName'])
}

function clearProductField(field) {
  form[field] = ''
}

function resetProductSearch() {
  productSearchSeq++
}

async function loadEditableFields() {
  editableFields.value = []
  try {
    const response = await getCustomsInventoryEditableFields()
    editableFields.value = response.data || []
  } catch (error) {
    editableFields.value = []
  }
}

function submitForm() {
  proxy.$refs.formRef.validate(async valid => {
    if (!valid) return
    saving.value = true
    try {
      if (editMode.value) {
        await updateCustomsInventory(form)
        proxy.$modal.msgSuccess('编辑成功')
      } else {
        await addCustomsInventory(form)
        proxy.$modal.msgSuccess('新增成功')
      }
      dialogVisible.value = false
      getList()
    } finally {
      saving.value = false
    }
  })
}

function canEditField(field) {
  return !editMode.value || editableFields.value.includes(field)
}

function validateSkuOrName(rule, value, callback) {
  if (!form.sku && !form.productName) callback(new Error('SKU和产品名称至少填写一项'))
  else callback()
}

async function handleFileChange(event) {
  const file = event.target.files?.[0]
  event.target.value = ''
  if (!file) return
  importing.value = true
  try {
    const response = await importCustomsInventory(file)
    const data = response.data || {}
    proxy.$modal.msgSuccess(`导入完成，保存 ${data.saved || 0} 行`)
    handleQuery()
    const errors = data.errors || []
    if (errors.length) proxy.$modal.msgWarning(errors.slice(0, 3).join('；'))
  } finally {
    importing.value = false
  }
}

async function handleExportSelected() {
  const ids = selectedRows.value.map(row => row.id).filter(Boolean)
  if (!ids.length) {
    proxy.$modal.msgWarning('请选择需要导出的记录')
    return
  }
  await doExport(ids, '出入库清单_选中.xlsx')
}

async function handleExportAll() {
  await doExport([], '出入库清单_全部.xlsx')
}

async function doExport(ids, fileName) {
  exporting.value = true
  try {
    const data = await exportCustomsInventory(ids)
    if (await blobValidate(data)) saveAs(new Blob([data]), fileName)
    else proxy.$modal.msgError('导出失败')
  } finally {
    exporting.value = false
  }
}

getList()
</script>

<style scoped>
.customs-inventory-page {
  background: #f6f8fb;
  min-height: calc(100vh - 84px);
}

.page-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 12px;
  padding: 14px 16px;
  background: #fff;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
}

.page-heading h2 {
  margin: 0;
  font-size: 20px;
  font-weight: 650;
  color: #1f2937;
}

.page-heading span {
  display: block;
  margin-top: 4px;
  font-size: 13px;
  color: #6b7280;
}

.toolbar {
  display: flex;
  gap: 8px;
}

.file-input {
  display: none;
}

.query-form {
  padding: 12px 16px 0;
  margin-bottom: 12px;
  background: #fff;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
}

.inventory-table {
  background: #fff;
}

:deep(.inventory-table .el-table__cell) {
  padding: 6px 0;
}

.inventory-form {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 0 12px;
}

.inventory-form .span-2 {
  grid-column: span 2;
}

.inventory-form .span-3 {
  grid-column: span 3;
}

:deep(.inventory-form .el-input-number) {
  width: 100%;
}

:deep(.inventory-form .el-select) {
  width: 100%;
}

:deep(.inventory-form .el-autocomplete) {
  width: 100%;
}

:deep(.inventory-form .el-date-editor) {
  width: 100%;
}

.product-option {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  min-width: 520px;
}

.product-option span {
  overflow: hidden;
  color: #1f2937;
  font-weight: 500;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.product-option small {
  overflow: hidden;
  color: #6b7280;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
