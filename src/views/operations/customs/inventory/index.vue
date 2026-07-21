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
        <el-dropdown trigger="click" @command="handleToolCommand" :disabled="importing || exporting">
          <el-button type="primary" :loading="importing || exporting">
            导入导出 ▾
          </el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item v-if="checkPermi(['customs:inventory:import'])" command="importExcel" icon="Upload">导入 Excel</el-dropdown-item>
              <el-dropdown-item v-if="checkPermi(['customs:inventory:export'])" command="exportSelected" icon="Download" :disabled="!selectedRows.length" divided>导出选中</el-dropdown-item>
              <el-dropdown-item v-if="checkPermi(['customs:inventory:export'])" command="exportAll" icon="Download">导出全部</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
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
      <el-table-column label="捷克仓" width="116" align="right">
        <template #default="{ row }"><warehouse-cell :row="row" bucket="CZ" base-field="czechWarehouseQty" auto-field="autoCzechWarehouseQty" declared-field="declaredCzechWarehouseQty" /></template>
      </el-table-column>
      <el-table-column label="英国仓" width="116" align="right">
        <template #default="{ row }"><warehouse-cell :row="row" bucket="UK" base-field="ukWarehouseQty" auto-field="autoUkWarehouseQty" declared-field="declaredUkWarehouseQty" /></template>
      </el-table-column>
      <el-table-column label="美国谷仓" width="126" align="right">
        <template #default="{ row }"><warehouse-cell :row="row" bucket="US_GC" base-field="usWarehouseQty" auto-field="autoUsWarehouseQty" declared-field="declaredUsWarehouseQty" /></template>
      </el-table-column>
      <el-table-column label="德国仓" width="116" align="right">
        <template #default="{ row }"><warehouse-cell :row="row" bucket="DE" base-field="deWarehouseQty" auto-field="autoDeWarehouseQty" declared-field="declaredDeWarehouseQty" /></template>
      </el-table-column>
      <el-table-column label="FBA(DE)" width="120" align="right">
        <template #default="{ row }"><warehouse-cell :row="row" bucket="FBA_DE" base-field="fbaDeQty" auto-field="autoFbaDeQty" declared-field="declaredFbaDeQty" /></template>
      </el-table-column>
      <el-table-column label="FBA(UK)" width="120" align="right">
        <template #default="{ row }"><warehouse-cell :row="row" bucket="FBA_UK" base-field="fbaUkQty" auto-field="autoFbaUkQty" declared-field="declaredFbaUkQty" /></template>
      </el-table-column>
      <el-table-column label="FBA(US)" width="120" align="right">
        <template #default="{ row }"><warehouse-cell :row="row" bucket="FBA_US" base-field="fbaUsQty" auto-field="autoFbaUsQty" declared-field="declaredFbaUsQty" /></template>
      </el-table-column>
      <el-table-column label="FBA(FR)" width="120" align="right">
        <template #default="{ row }"><warehouse-cell :row="row" bucket="FBA_FR" base-field="fbaFrQty" auto-field="autoFbaFrQty" declared-field="declaredFbaFrQty" /></template>
      </el-table-column>
      <el-table-column label="未知仓" width="112" align="right">
        <template #default="{ row }"><warehouse-cell :row="row" bucket="UNKNOWN" declared-field="declaredUnknownWarehouseQty" unknown /></template>
      </el-table-column>
      <el-table-column label="剩余库存" width="120" align="right">
        <template #default="{ row }">
          <div class="stock-cell">
            <strong>手动 {{ formatQty(row.remainingStock) }}</strong>
            <small v-if="Number(row.declaredTotalQty || 0)">自动支出 {{ formatQty(row.declaredTotalQty) }}</small>
            <span>自动 {{ formatQty(row.availableRemainingStock ?? row.autoRemainingStock ?? row.inboundQuantity) }}</span>
          </div>
        </template>
      </el-table-column>
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
            value-format="YYYY-MM-DD"
            format="YYYY-MM-DD"
            placeholder="选择采购日期"
            :disabled="!canEditField('purchaseDate')"
            clearable
          />
        </el-form-item>
        <el-form-item label="入库日期">
          <el-date-picker
            v-model="form.inboundDate"
            type="date"
            value-format="YYYY-MM-DD"
            format="YYYY-MM-DD"
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
          <el-input
            v-model="form.outboundDate"
            placeholder="可填写多个日期，如 2026-07-01，2026-07-05"
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
        <el-form-item label="剩余库存"><el-input-number :model-value="calcRemainingStock" :controls="false" :precision="0" disabled /></el-form-item>
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
import { defineComponent, h, resolveComponent } from 'vue'
import { saveAs } from 'file-saver'
import { blobValidate } from '@/utils/ruoyi'
import { checkPermi } from '@/utils/permission'
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
const warehouseLinkTextStyle = {
  color: '#1677ff',
  textDecoration: 'underline',
  textUnderlineOffset: '2px'
}

const WarehouseCell = defineComponent({
  name: 'WarehouseCell',
  props: {
    row: { type: Object, required: true },
    bucket: { type: String, required: true },
    baseField: { type: String, default: '' },
    autoField: { type: String, default: '' },
    declaredField: { type: String, required: true },
    unknown: { type: Boolean, default: false }
  },
  setup(props) {
    return () => {
      const ElPopover = resolveComponent('el-popover')
      const logs = bucketLogs(props.row, props.bucket)
      const base = props.baseField ? Number(props.row[props.baseField] || 0) : 0
      const declared = Number(props.row[props.declaredField] || 0)
      const trigger = h('div', {
        class: ['stock-cell', 'has-popover', declared ? 'has-declared' : ''],
        'data-inventory-id': props.row.id,
        'data-warehouse-bucket': props.bucket,
        title: `点击查看 ${bucketLabel(props.bucket)} 报关扣减日志`
      }, [
        props.unknown
          ? h('strong', { class: 'warehouse-log-link', style: warehouseLinkTextStyle }, `自动 ${formatQty(declared)}`)
          : h('strong', { class: 'warehouse-log-link', style: warehouseLinkTextStyle }, `手动 ${formatQty(base)}`),
        props.unknown ? null : h('span', { class: 'warehouse-log-link', style: warehouseLinkTextStyle }, `自动 ${formatQty(declared)}`)
      ])
      return h(ElPopover, {
        trigger: 'click',
        width: 600,
        placement: 'top',
        popperClass: 'customs-inventory-log-popper'
      }, {
        reference: () => trigger,
        default: () => renderWarehouseLogs(props.row, props.bucket, logs)
      })
    }
  }
})

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

const calcRemainingStock = computed(() => {
  const inbound = Number(form.inboundQuantity || 0)
  const sum = (form.czechWarehouseQty || 0) + (form.ukWarehouseQty || 0) + (form.usWarehouseQty || 0) + (form.deWarehouseQty || 0)
    + (form.fbaDeQty || 0) + (form.fbaUkQty || 0) + (form.fbaUsQty || 0) + (form.fbaFrQty || 0)
  return inbound - sum
})

function todayText() {
  const date = new Date()
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`
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

function formatQty(value) {
  if (value === null || value === undefined || value === '') return '0'
  const numberValue = Number(value)
  if (Number.isNaN(numberValue)) return String(value)
  return String(Math.trunc(numberValue))
}

function bucketLogs(row, bucket) {
  return row?.declarationLogs?.[bucket] || []
}

function renderWarehouseLogs(row, bucket, logs) {
  const declaredTotal = logs.reduce((total, log) => total + Number(log.quantity || 0), 0)
  const children = [
    h('div', { class: 'log-popover-title' }, [
      h('div', { class: 'log-title-main' }, [
        h('strong', bucketLabel(bucket)),
        h('span', { title: `${row.sku || '-'} / ${row.productCode || '-'}` }, `${row.sku || '-'} / ${row.productCode || '-'}`)
      ]),
      h('div', { class: 'log-title-summary' }, [
        h('span', `${logs.length} 条记录`),
        h('strong', `累计扣减 ${formatQty(declaredTotal)} 件`)
      ])
    ])
  ]
  if (!logs.length) {
    children.push(h('div', { class: 'log-empty' }, '暂无报关记录'))
  } else {
    children.push(h('div', { class: 'log-list' }, logs.map((log, index) => h('article', {
      class: 'log-row',
      key: log.id || `${log.declarationNo || ''}-${log.createdTime || ''}-${index}`
    }, [
      h('header', { class: 'log-row-main' }, [
        h('div', { class: 'log-order' }, [
          h('span', { class: 'log-index' }, `#${index + 1}`),
          h('span', { class: ['log-source-tag', `is-${String(log.sourceType || 'manual').toLowerCase()}`] }, sourceTypeLabel(log.sourceType)),
          h('strong', { title: log.sourceOrderNo || '-' }, log.sourceOrderNo || '无来源单号')
        ]),
        h('strong', { class: 'log-quantity' }, `扣减 ${formatQty(log.quantity)} 件`)
      ]),
      h('div', { class: 'log-meta-grid' }, [
        logMetaItem('原始 SKU', log.rawSku || '-'),
        logMetaItem('库存 SKU', log.standardSku || row.sku || '-'),
        logMetaItem('仓库', log.warehouseName || bucketLabel(bucket)),
        logMetaItem('货源地', log.sourceLocation || '-'),
        logMetaItem('商品编码', log.productCode || row.productCode || '-', true)
      ]),
      h('footer', { class: 'log-row-footer' }, [
        h('span', { title: log.declarationNo || '-' }, `批次：${log.declarationNo || '-'}`),
        h('time', formatLogTime(log.createdTime))
      ])
    ]))))
  }
  return h('div', { class: 'log-popover' }, children)
}

function logMetaItem(label, value, wide = false) {
  const text = value === null || value === undefined || value === '' ? '-' : String(value)
  return h('div', { class: ['log-meta-item', wide ? 'is-wide' : ''] }, [
    h('span', label),
    h('strong', { title: text }, text)
  ])
}

function sourceTypeLabel(sourceType) {
  return ({ EBAY: 'eBay备货', FBA: '亚马逊FBA', MANUAL: '手工录入' })[String(sourceType || '').toUpperCase()] || sourceType || '其他来源'
}

function formatLogTime(value) {
  if (!value) return '时间：-'
  return `时间：${String(value).replace('T', ' ').replace(/\.\d+$/, '')}`
}

function bucketLabel(bucket) {
  return ({
    CZ: '捷克仓',
    UK: '英国仓',
    US_GC: '美国谷仓',
    DE: '德国仓',
    FBA_DE: 'FBA(DE)',
    FBA_UK: 'FBA(UK)',
    FBA_US: 'FBA(US)',
    FBA_FR: 'FBA(FR)',
    UNKNOWN: '未知仓'
  })[bucket] || bucket || '未知仓'
}

function openFile() {
  fileRef.value?.click()
}

function handleToolCommand(cmd) {
  if (cmd === 'importExcel') openFile()
  else if (cmd === 'exportSelected') handleExportSelected()
  else if (cmd === 'exportAll') handleExportAll()
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
    ...row,
    purchaseDate: normalizeDateValue(row.purchaseDate),
    inboundDate: normalizeDateValue(row.inboundDate),
    outboundDate: normalizeLooseDateText(row.outboundDate)
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
    form.remainingStock = calcRemainingStock.value
    form.purchaseDate = normalizeDateValue(form.purchaseDate)
    form.inboundDate = normalizeDateValue(form.inboundDate)
    form.outboundDate = normalizeLooseDateText(form.outboundDate)
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

function normalizeDateValue(value) {
  if (!value) return ''
  const text = String(value).trim()
  const match = text.match(/^(\d{4})[./-](\d{1,2})[./-](\d{1,2})$/)
  if (!match) return text
  return `${match[1]}-${match[2].padStart(2, '0')}-${match[3].padStart(2, '0')}`
}

function normalizeLooseDateText(value) {
  if (!value) return ''
  return String(value)
    .split(/[\r\n,，;；]+/)
    .map(item => normalizeDateValue(item.trim()))
    .filter(Boolean)
    .join('，')
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

.stock-cell {
  display: grid;
  gap: 2px;
  min-height: 42px;
  align-content: center;
  line-height: 1.15;
  cursor: help;
}

.stock-cell strong {
  color: #1f2937;
  font-size: 13px;
  font-variant-numeric: tabular-nums;
}

.stock-cell small {
  color: #c2410c;
  font-size: 11px;
  font-variant-numeric: tabular-nums;
}

.stock-cell span {
  color: #409eff;
  font-size: 11px;
  font-variant-numeric: tabular-nums;
}

.stock-cell.has-popover :deep(strong),
.stock-cell.has-popover :deep(span) {
  color: #1677ff;
  text-decoration: underline;
  text-underline-offset: 2px;
}

.stock-cell.has-declared :deep(strong) {
  color: #1677ff;
}

.log-popover {
  display: grid;
  gap: 10px;
  color: #1f2937;
}

.log-popover-title {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 18px;
  padding: 2px 2px 10px;
  border-bottom: 1px solid #ebeef5;
}

.log-title-main,
.log-title-summary {
  display: grid;
  gap: 3px;
  min-width: 0;
}

.log-title-main strong {
  color: #1f2937;
  font-size: 15px;
}

.log-title-main span {
  overflow: hidden;
  max-width: 315px;
  color: #6b7280;
  font-size: 12px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.log-title-summary {
  flex: none;
  text-align: right;
}

.log-title-summary span {
  color: #909399;
  font-size: 11px;
}

.log-title-summary strong {
  color: #c2410c;
  font-size: 12px;
  font-variant-numeric: tabular-nums;
}

.log-list {
  display: grid;
  gap: 10px;
  max-height: 430px;
  padding-right: 3px;
  overflow-y: auto;
}

.log-row {
  display: grid;
  gap: 9px;
  padding: 11px 12px;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  background: #f8fafc;
}

.log-row-main {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.log-order {
  display: flex;
  align-items: center;
  min-width: 0;
  gap: 8px;
}

.log-order strong {
  overflow: hidden;
  color: #303133;
  font-size: 13px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.log-source-tag {
  flex: none;
  padding: 2px 7px;
  border-radius: 999px;
  background: #e0f2fe;
  color: #0369a1;
  font-size: 11px;
  line-height: 18px;
}

.log-source-tag.is-fba {
  background: #fef3c7;
  color: #92400e;
}

.log-source-tag.is-manual {
  background: #f3e8ff;
  color: #7e22ce;
}

.log-quantity {
  flex: none;
  color: #c2410c;
  font-size: 13px;
  font-variant-numeric: tabular-nums;
}

.log-meta-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 7px 16px;
}

.log-meta-item {
  display: grid;
  grid-template-columns: 62px minmax(0, 1fr);
  gap: 6px;
  min-width: 0;
  font-size: 12px;
}

.log-meta-item.is-wide {
  grid-column: 1 / -1;
}

.log-meta-item span {
  color: #909399;
}

.log-meta-item strong {
  overflow: hidden;
  color: #374151;
  font-weight: 500;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.log-row-footer {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  padding-top: 7px;
  border-top: 1px dashed #dbe3ec;
  color: #909399;
  font-size: 11px;
}

.log-row-footer span {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.log-row-footer time {
  flex: none;
  font-variant-numeric: tabular-nums;
}

.log-more {
  color: #909399;
  font-size: 11px;
  text-align: center;
}

.log-empty {
  padding: 10px 0;
  color: #909399;
  text-align: center;
}
</style>

<!-- el-popover 默认 Teleport 到 body，日志样式必须是全局选择器。 -->
<style>
.customs-inventory-log-popper.el-popover {
  padding: 14px 16px;
  border-radius: 10px;
  box-shadow: 0 10px 30px rgb(15 23 42 / 16%);
}

.customs-inventory-log-popper .log-popover {
  display: grid;
  gap: 10px;
  color: #1f2937;
}

.customs-inventory-log-popper .log-popover-title {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 18px;
  padding: 2px 2px 10px;
  border-bottom: 1px solid #e5e7eb;
}

.customs-inventory-log-popper .log-title-main,
.customs-inventory-log-popper .log-title-summary {
  display: grid;
  gap: 3px;
  min-width: 0;
}

.customs-inventory-log-popper .log-title-main strong {
  color: #1f2937;
  font-size: 15px;
}

.customs-inventory-log-popper .log-title-main span {
  overflow: hidden;
  max-width: 350px;
  color: #6b7280;
  font-size: 12px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.customs-inventory-log-popper .log-title-summary {
  flex: none;
  text-align: right;
}

.customs-inventory-log-popper .log-title-summary span {
  color: #909399;
  font-size: 11px;
}

.customs-inventory-log-popper .log-title-summary strong {
  color: #c2410c;
  font-size: 12px;
  font-variant-numeric: tabular-nums;
}

.customs-inventory-log-popper .log-list {
  display: grid;
  gap: 10px;
  max-height: min(520px, 68vh);
  padding-right: 6px;
  overflow-y: auto;
  overscroll-behavior: contain;
  scrollbar-gutter: stable;
}

.customs-inventory-log-popper .log-list::-webkit-scrollbar {
  width: 7px;
}

.customs-inventory-log-popper .log-list::-webkit-scrollbar-thumb {
  border-radius: 8px;
  background: #cbd5e1;
}

.customs-inventory-log-popper .log-row {
  display: grid;
  gap: 9px;
  padding: 11px 12px;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  background: #f8fafc;
}

.customs-inventory-log-popper .log-row-main,
.customs-inventory-log-popper .log-row-footer,
.customs-inventory-log-popper .log-order {
  display: flex;
  align-items: center;
}

.customs-inventory-log-popper .log-row-main,
.customs-inventory-log-popper .log-row-footer {
  justify-content: space-between;
  gap: 12px;
}

.customs-inventory-log-popper .log-order {
  min-width: 0;
  gap: 7px;
}

.customs-inventory-log-popper .log-index {
  flex: none;
  width: 28px;
  color: #94a3b8;
  font-size: 11px;
  font-variant-numeric: tabular-nums;
}

.customs-inventory-log-popper .log-order strong {
  overflow: hidden;
  color: #303133;
  font-size: 13px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.customs-inventory-log-popper .log-source-tag {
  flex: none;
  padding: 2px 7px;
  border-radius: 999px;
  background: #e0f2fe;
  color: #0369a1;
  font-size: 11px;
  line-height: 18px;
}

.customs-inventory-log-popper .log-source-tag.is-fba {
  background: #fef3c7;
  color: #92400e;
}

.customs-inventory-log-popper .log-source-tag.is-manual {
  background: #f3e8ff;
  color: #7e22ce;
}

.customs-inventory-log-popper .log-quantity {
  flex: none;
  color: #c2410c;
  font-size: 13px;
  font-variant-numeric: tabular-nums;
}

.customs-inventory-log-popper .log-meta-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 7px 16px;
}

.customs-inventory-log-popper .log-meta-item {
  display: grid;
  grid-template-columns: 62px minmax(0, 1fr);
  gap: 6px;
  min-width: 0;
  font-size: 12px;
}

.customs-inventory-log-popper .log-meta-item.is-wide {
  grid-column: 1 / -1;
}

.customs-inventory-log-popper .log-meta-item span {
  color: #909399;
}

.customs-inventory-log-popper .log-meta-item strong {
  overflow: hidden;
  color: #374151;
  font-weight: 500;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.customs-inventory-log-popper .log-row-footer {
  padding-top: 7px;
  border-top: 1px dashed #dbe3ec;
  color: #909399;
  font-size: 11px;
}

.customs-inventory-log-popper .log-row-footer span {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.customs-inventory-log-popper .log-row-footer time {
  flex: none;
  font-variant-numeric: tabular-nums;
}

.customs-inventory-log-popper .log-empty {
  padding: 18px 0;
  color: #909399;
  text-align: center;
}
</style>
