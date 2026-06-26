<template>
  <div class="app-container customs-page">
    <div class="page-bar">
      <div class="page-heading">
        <h2>报关单制作</h2>
        <span>中华人民共和国海关出口货物报关单</span>
      </div>
      <div class="toolbar">
        <el-button type="primary" icon="Download" :loading="exporting" @click="handleExport"
          v-hasPermi="['customs:declaration:export']">导出报关单</el-button>
        <el-dropdown trigger="click" @command="handleToolbarCommand">
          <el-button>
            更多操作<el-icon class="dropdown-icon"><ArrowDown /></el-icon>
          </el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="history" icon="Upload"
                v-hasPermi="['customs:declaration:import']">导入历史报关单</el-dropdown-item>
              <el-dropdown-item command="sku" icon="DocumentAdd"
                v-hasPermi="['customs:declaration:import']">批量导入 SKU</el-dropdown-item>
              <el-dropdown-item command="save" icon="Finished" :disabled="saving"
                v-hasPermi="['customs:product:edit']">保存至商品库</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
      </div>
      <input ref="historyFileRef" class="file-input" type="file" accept=".xlsx" multiple @change="handleHistoryFile">
      <input ref="skuFileRef" class="file-input" type="file" accept=".xlsx" @change="handleSkuFile">
    </div>

    <section class="declaration-sheet">
      <button class="section-toggle" type="button" @click="headerExpanded = !headerExpanded">
        <span class="section-toggle__title">
          <el-icon><Tickets /></el-icon>
          报关基本信息
          <span class="section-toggle__hint">{{ headerExpanded ? '收起后可专注编辑商品' : '点击展开编辑' }}</span>
        </span>
        <el-icon class="section-toggle__arrow" :class="{ 'is-expanded': headerExpanded }"><ArrowDown /></el-icon>
      </button>
      <el-collapse-transition>
        <el-form v-show="headerExpanded" ref="headerFormRef" :model="header" label-position="top" class="header-form">
        <div class="header-grid">
          <el-form-item label="预录入编号"><el-input v-model="header.preEntry" /></el-form-item>
          <el-form-item label="海关编号"><el-input v-model="header.customsNo" /></el-form-item>
          <el-form-item label="境内发货人" class="span-2"><el-input v-model="header.consignor" type="textarea" :rows="2" /></el-form-item>
          <el-form-item label="出境关别"><el-input v-model="header.customsArea" /></el-form-item>
          <el-form-item label="出口日期"><el-date-picker v-model="header.exportDate" type="date" value-format="YYYY-MM-DD" /></el-form-item>
          <el-form-item label="申报日期"><el-date-picker v-model="header.declareDate" type="date" value-format="YYYY-MM-DD" /></el-form-item>
          <el-form-item label="备案号"><el-input v-model="header.recordNo" /></el-form-item>
          <el-form-item label="境外收货人" class="span-2"><el-input v-model="header.consignee" type="textarea" :rows="2" /></el-form-item>
          <el-form-item label="运输方式"><el-input v-model="header.transportMode" /></el-form-item>
          <el-form-item label="运输工具名称及航次号"><el-input v-model="header.transportName" /></el-form-item>
          <el-form-item label="提运单号" class="span-2"><el-input v-model="header.billNo" /></el-form-item>
          <el-form-item label="生产销售单位" class="span-2"><el-input v-model="header.producer" type="textarea" :rows="2" /></el-form-item>
          <el-form-item label="监管方式"><el-input v-model="header.supervision" /></el-form-item>
          <el-form-item label="征免性质"><el-input v-model="header.taxNature" /></el-form-item>
          <el-form-item label="许可证号"><el-input v-model="header.licenseNo" /></el-form-item>
          <el-form-item label="合同协议号"><el-input v-model="header.contractNo" /></el-form-item>
          <el-form-item label="贸易国（地区）"><el-input v-model="header.tradeCountry" /></el-form-item>
          <el-form-item label="运抵国（地区）"><el-input v-model="header.destCountry" /></el-form-item>
          <el-form-item label="指运港"><el-input v-model="header.destPort" /></el-form-item>
          <el-form-item label="离境口岸"><el-input v-model="header.entryPort" /></el-form-item>
          <el-form-item label="包装种类"><el-input v-model="header.packType" /></el-form-item>
          <el-form-item label="件数"><el-input-number v-model="header.packQty" :min="0" controls-position="right" /></el-form-item>
          <el-form-item label="毛重（千克）"><el-input :model-value="totalWeight" readonly /></el-form-item>
          <el-form-item label="净重（千克）"><el-input v-model="header.netWt" /></el-form-item>
          <el-form-item label="成交方式"><el-input v-model="header.tradeTerm" /></el-form-item>
          <el-form-item label="运费"><el-input v-model="header.freight" /></el-form-item>
          <el-form-item label="保费"><el-input v-model="header.insurance" /></el-form-item>
          <el-form-item label="杂费"><el-input v-model="header.otherFee" /></el-form-item>
          <el-form-item label="随附单证及编号" class="span-4"><el-input v-model="header.docs" /></el-form-item>
          <el-form-item label="标记唛码及备注" class="span-4"><el-input v-model="header.marks" type="textarea" :rows="2" /></el-form-item>
        </div>
        </el-form>
      </el-collapse-transition>
    </section>

    <div class="summary-bar">
      <span>商品 {{ validItems.length }} 项</span>
      <span>数量 {{ totalQuantity }}</span>
      <span>总价 {{ totalAmount }}</span>
      <span>总重 {{ totalWeight }} kg</span>
      <el-button type="danger" plain size="small" icon="Delete" @click="handleClear">清空商品</el-button>
    </div>

    <el-table :data="items" border stripe row-key="_key" class="item-table">
      <el-table-column type="index" label="项号" width="58" fixed="left" align="center" />
      <el-table-column label="商品编码" width="130">
        <template #default="{ row }"><el-input v-model="row.productCode" /></template>
      </el-table-column>
      <el-table-column label="商品申报要素" width="200">
        <template #default="{ row }">
          <el-input v-model="row.hsDescription" type="textarea" :rows="2" size="small" style="font-size:12px" />
        </template>
      </el-table-column>
      <el-table-column label="商品名称" width="140">
        <template #default="{ row }"><el-input v-model="row.descriptionCn" /></template>
      </el-table-column>
      <el-table-column label="SKU" width="180" fixed="left">
        <template #default="{ row }">
          <el-select v-model="row.sku" filterable remote clearable placeholder="输入SKU或品名"
            :remote-method="searchProducts" :loading="searching" @change="value => selectProduct(row, value)">
            <el-option v-for="product in productOptions" :key="product.sku"
              :label="product.sku"
              :value="product.sku" />
          </el-select>
        </template>
      </el-table-column>
      <el-table-column label="规格型号" width="110">
        <template #default="{ row }"><el-input v-model="row.model" /></template>
      </el-table-column>
      <el-table-column label="数量及单位" width="148">
        <template #default="{ row }">
          <div style="display:flex;gap:4px;align-items:center">
            <el-input-number v-model="row.quantity" :min="1" :controls="false" size="small" style="width:70px" />
            <el-input v-model="row.unit" size="small" style="width:60px" placeholder="单位" />
          </div>
        </template>
      </el-table-column>
      <el-table-column label="单重(kg)" width="94">
        <template #default="{ row }">
          <el-input-number v-model="row.singleWeight" :min="0" :precision="4" :controls="false" />
        </template>
      </el-table-column>
      <el-table-column label="总重(kg)" width="92" align="right">
        <template #default="{ row }"><span class="calculated-value">{{ calcWeight(row) }}</span></template>
      </el-table-column>
      <el-table-column label="单价/总价/币制" width="230">
        <template #default="{ row }">
          <div style="display:flex;gap:4px;align-items:center">
            <el-input-number v-model="row.unitPriceUsd" :min="0" :precision="2" :controls="false" size="small" style="width:80px" placeholder="单价" />
            <span class="calculated-value" style="min-width:70px;text-align:right">{{ calcAmount(row) }}</span>
            <el-input v-model="row.currency" size="small" style="width:60px" placeholder="币制" />
          </div>
        </template>
      </el-table-column>
      <el-table-column label="原产国" width="100">
        <template #default="{ row }"><el-input v-model="row.originCountry" /></template>
      </el-table-column>
      <el-table-column label="最终目的国" width="115">
        <template #default="{ row }"><el-input v-model="row.destinationCountry" /></template>
      </el-table-column>
      <el-table-column label="境内货源地" width="135">
        <template #default="{ row }"><el-input v-model="row.sourceLocation" /></template>
      </el-table-column>
      <el-table-column label="征免" width="90">
        <template #default="{ row }"><el-input v-model="row.exemption" /></template>
      </el-table-column>
      <el-table-column label="操作" width="96" fixed="right" align="center">
        <template #default="{ $index }">
          <el-button link type="primary" icon="Plus" title="在下方添加" @click="addRow($index)" />
          <el-button link type="danger" icon="Minus" title="删除" @click="removeRow($index)" />
        </template>
      </el-table-column>
    </el-table>
  </div>
</template>

<script setup name="CustomsDeclaration">
import { computed, reactive, ref, watch } from 'vue'
import { saveAs } from 'file-saver'
import { blobValidate } from '@/utils/ruoyi'
import {
  exportCustomsDeclaration,
  importCustomsHistory,
  importCustomsSkus,
  saveCustomsProducts,
  searchCustomsProducts
} from '@/api/operations/customs/declaration'

const { proxy } = getCurrentInstance()
const historyFileRef = ref()
const skuFileRef = ref()
const searching = ref(false)
const saving = ref(false)
const exporting = ref(false)
const headerExpanded = ref(false)
const productOptions = ref([])
let keySeed = 0

const defaultCompany = '成都玖马赫供应链管理有限公司   信用代码：91510106MACMNJMB6A'
const header = reactive(createHeader())
const items = ref([createEmptyItem()])

function createHeader() {
  return {
    preEntry: '', customsNo: '', consignor: defaultCompany, customsArea: '',
    exportDate: '', declareDate: '', recordNo: '', consignee: 'Hong Kong Cammy Yeson Limited',
    transportMode: '', transportName: '', billNo: '', producer: defaultCompany,
    supervision: '一般贸易', taxNature: '一般征税', licenseNo: '', contractNo: '',
    tradeCountry: '美国', destCountry: '美国', destPort: '', entryPort: '',
    packType: '纸箱', packQty: 0, grossWt: '', netWt: '', tradeTerm: 'FOB',
    freight: '', insurance: '', otherFee: '',
    docs: '合同、发票、装箱单等，收货人信息提示：Hong Kong Cammy Yeson Limited', marks: ''
  }
}

function createEmptyItem() {
  return {
    _key: ++keySeed, productCode: '', sku: '', descriptionCn: '', model: '', unit: '个',
    unitPriceUsd: 0, currency: 'USD', singleWeight: 0, quantity: 1,
    hsCode: '', hsDescription: '', originCountry: '', destinationCountry: '',
    sourceLocation: '', exemption: ''
  }
}

const validItems = computed(() => items.value.filter(item => item.sku && item.sku.trim()))
const totalQuantity = computed(() => validItems.value.reduce((sum, item) => sum + Number(item.quantity || 0), 0))
const totalAmount = computed(() => validItems.value.reduce((sum, item) => sum + Number(calcAmount(item)), 0).toFixed(2))
const totalWeight = computed(() => validItems.value.reduce((sum, item) => sum + Number(calcWeight(item)), 0).toFixed(4))

watch(totalWeight, v => { header.grossWt = v })
watch(
  () => validItems.value.map(item => item.sku),
  skus => { header.packQty = skus.length },
  { immediate: true }
)

function calcAmount(row) {
  return (Number(row.unitPriceUsd || 0) * Number(row.quantity || 0)).toFixed(2)
}

function calcWeight(row) {
  return (Number(row.singleWeight || 0) * Number(row.quantity || 0)).toFixed(4)
}

async function searchProducts(keyword) {
  if (!keyword || !keyword.trim()) {
    productOptions.value = []
    return
  }
  searching.value = true
  try {
    const response = await searchCustomsProducts(keyword.trim())
    productOptions.value = response.data || []
  } finally {
    searching.value = false
  }
}

function selectProduct(row, sku) {
  const product = productOptions.value.find(item => item.sku === sku)
  if (!product) return
  const quantity = row.quantity || 1
  const key = row._key
  Object.assign(row, JSON.parse(JSON.stringify(product)), { quantity, _key: key })
  if (!row.productCode) row.productCode = product.hsCode || ''
}

function addRow(index) {
  items.value.splice(index + 1, 0, createEmptyItem())
}

function removeRow(index) {
  if (items.value.length === 1) {
    proxy.$modal.msgWarning('至少保留一行')
    return
  }
  items.value.splice(index, 1)
}

function openHistoryFile() { historyFileRef.value?.click() }
function openSkuFile() { skuFileRef.value?.click() }

function handleToolbarCommand(command) {
  const actions = {
    history: openHistoryFile,
    sku: openSkuFile,
    save: handleSaveProducts,
  }
  actions[command]?.()
}

async function handleHistoryFile(event) {
  const files = Array.from(event.target.files || [])
  if (!files.length) return
  try {
    let inserted = 0
    let updated = 0
    let failed = 0
    const errorFiles = []
    for (const file of files) {
      try {
        const response = await importCustomsHistory(file)
        const result = response.data || {}
        inserted += result.inserted || 0
        updated += result.updated || 0
        failed += result.failed || 0
      } catch {
        errorFiles.push(file.name)
      }
    }
    const message = `新增 ${inserted} 条，更新 ${updated} 条`
      + (failed ? `，失败 ${failed} 条` : '')
      + (errorFiles.length ? `，${errorFiles.length} 个文件出错` : '')
    if (failed || errorFiles.length) proxy.$modal.msgWarning(message)
    else proxy.$modal.msgSuccess(message)
  } finally {
    event.target.value = ''
  }
}

async function handleSkuFile(event) {
  const file = event.target.files?.[0]
  if (!file) return
  try {
    const response = await importCustomsSkus(file)
    const result = response.data || {}
    const loaded = (result.products || []).map(product => ({ ...product, _key: ++keySeed }))
    const missing = result.missingSkus || []
    if (!loaded.length) {
      proxy.$modal.msgError('未找到任何匹配商品')
      return
    }
    items.value = loaded
    if (missing.length) proxy.$modal.msgWarning(`已加载 ${loaded.length} 个商品，${missing.length} 个未找到`)
    else proxy.$modal.msgSuccess(`已加载 ${loaded.length} 个商品`)
  } finally {
    event.target.value = ''
  }
}

function validateItems() {
  if (!validItems.value.length) {
    proxy.$modal.msgWarning('请先添加商品')
    return false
  }
  for (const item of validItems.value) {
    if (item.quantity === null || item.quantity === undefined || item.quantity === '') item.quantity = 1
    if (!item.currency) item.currency = 'USD'
  }
  return true
}

async function handleSaveProducts() {
  if (!validateItems()) return
  await proxy.$modal.confirm('确认将当前商品资料保存至商品库吗？临时修改将覆盖同SKU主数据。')
  saving.value = true
  try {
    const data = validItems.value.map(({ _key, quantity, ...product }) => product)
    const response = await saveCustomsProducts(data)
    proxy.$modal.msgSuccess(`已保存 ${response.data || data.length} 条商品资料`)
  } finally {
    saving.value = false
  }
}

async function handleExport() {
  if (!validateItems()) return
  exporting.value = true
  try {
    const response = await exportCustomsDeclaration({ header, items: validItems.value })
    const blob = response instanceof Blob ? response : new Blob([response])
    if (!blobValidate(blob)) {
      const error = JSON.parse(await blob.text())
      throw new Error(error.msg || '导出失败')
    }
    const date = new Date()
    const stamp = String(date.getFullYear()).slice(-2)
      + String(date.getMonth() + 1).padStart(2, '0')
      + String(date.getDate()).padStart(2, '0')
    saveAs(blob, `报关单_${stamp}.xlsx`)
    proxy.$modal.msgSuccess('导出成功')
  } finally {
    exporting.value = false
  }
}

async function handleClear() {
  await proxy.$modal.confirm('清空全部商品行？')
  items.value = [createEmptyItem()]
  proxy.$modal.msgSuccess('已清空')
}
</script>

<style scoped>
.customs-page {
  min-width: 1080px;
  padding-top: 14px;
}

.page-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  min-height: 40px;
  margin-bottom: 12px;
}

.page-heading {
  display: flex;
  align-items: baseline;
  gap: 12px;
  min-width: 0;
}

.page-heading h2 {
  margin: 0;
  color: #303133;
  font-size: 18px;
  font-weight: 600;
}

.page-heading span {
  overflow: hidden;
  color: #909399;
  font-size: 12px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.toolbar {
  display: flex;
  flex: none;
  align-items: center;
  gap: 8px;
}

.dropdown-icon {
  margin-left: 6px;
}

.file-input {
  display: none;
}

.declaration-sheet {
  overflow: hidden;
  border: 1px solid #dcdfe6;
  border-radius: 4px;
  background: #fff;
}

.section-toggle {
  display: flex;
  width: 100%;
  height: 42px;
  padding: 0 14px;
  border: 0;
  background: #f7f8fa;
  color: #303133;
  cursor: pointer;
  align-items: center;
  justify-content: space-between;
}

.section-toggle:hover {
  background: #f2f4f7;
}

.section-toggle__title {
  display: flex;
  align-items: center;
  gap: 7px;
  font-size: 14px;
  font-weight: 600;
}

.section-toggle__hint {
  color: #909399;
  font-size: 12px;
  font-weight: 400;
}

.section-toggle__arrow {
  color: #909399;
  transition: transform 0.2s ease;
}

.section-toggle__arrow.is-expanded {
  transform: rotate(180deg);
}

.header-form {
  padding: 12px 14px 4px;
  border-top: 1px solid #ebeef5;
}

.header-grid {
  display: grid;
  grid-template-columns: repeat(6, minmax(140px, 1fr));
  gap: 0 10px;
}

.span-2 {
  grid-column: span 2;
}

.span-4 {
  grid-column: span 4;
}

.header-form :deep(.el-form-item) {
  margin-bottom: 8px;
}

.header-form :deep(.el-form-item__label) {
  height: 22px;
  padding-bottom: 2px;
  line-height: 20px;
  font-size: 12px;
}

.header-form :deep(.el-date-editor),
.header-form :deep(.el-input-number) {
  width: 100%;
}

.header-form :deep(.el-textarea__inner) {
  min-height: 32px !important;
}

.summary-bar {
  display: flex;
  gap: 24px;
  height: 38px;
  padding: 0 12px;
  margin-top: 10px;
  border: 1px solid #dcdfe6;
  border-bottom: none;
  background: #f5f7fa;
  color: #606266;
  font-size: 13px;
  align-items: center;
}

.item-table :deep(.el-input-number),
.item-table :deep(.el-select) {
  width: 100%;
}

.item-table :deep(.el-table__cell) {
  padding: 7px 0;
}

.item-table :deep(.cell) {
  padding: 0 5px;
}

.item-table :deep(.el-input__wrapper) {
  padding: 1px 7px;
}

.calculated-value {
  color: #303133;
  font-size: 13px;
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}

@media (max-width: 1280px) {
  .header-grid {
    grid-template-columns: repeat(4, minmax(160px, 1fr));
  }

  .span-4 {
    grid-column: span 4;
  }
}
</style>
