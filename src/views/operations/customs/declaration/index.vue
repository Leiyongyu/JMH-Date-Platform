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
        <el-button type="success" icon="Connection" @click="openDataSourceDialog"
          v-hasPermi="['customs:declaration:query']">关联数据源</el-button>
        <el-dropdown trigger="click" @command="handleToolbarCommand" :disabled="fbaBoxImporting">
          <el-button :loading="fbaBoxImporting">
            {{ fbaBoxImporting ? '导入中' : '更多操作' }}<el-icon v-if="!fbaBoxImporting" class="dropdown-icon"><ArrowDown /></el-icon>
          </el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="sku" icon="DocumentAdd"
                v-hasPermi="['customs:declaration:import']">批量导入 SKU</el-dropdown-item>
              <el-dropdown-item command="fbaBox" icon="Box" :disabled="fbaBoxImporting"
                v-hasPermi="['customs:declaration:import']">导入 FBA 装箱明细</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
      </div>
      <input ref="skuFileRef" class="file-input" type="file" accept=".xlsx" @change="handleSkuFile">
      <input ref="fbaBoxFileRef" class="file-input" type="file" accept=".xlsx" @change="handleFbaBoxFile">
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
          <el-form-item label="毛重（千克）"><el-input :model-value="totalGrossWeight" readonly /></el-form-item>
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
      <span>毛重 {{ totalGrossWeight }} kg</span>
      <span>净重 {{ totalNetWeight }} kg</span>
      <el-button type="primary" plain size="small" icon="Finished" :loading="saving" @click="handleSaveProducts"
        v-hasPermi="['customs:product:edit']">保存商品</el-button>
      <el-button type="danger" plain size="small" icon="Delete" @click="handleClear">清空商品</el-button>
    </div>

    <section ref="itemTableRef" class="packing-workbench">
      <div class="packing-head">
        <div class="packing-head__title">
          <el-icon><Box /></el-icon>
          装箱商品
        </div>
        <div class="packing-head__meta">
          <span>箱组 {{ boxGroups.length }}</span>
          <span>总箱数 {{ totalBoxCount }}</span>
          <span>总体积 {{ totalCbm }} m³</span>
          <span>箱毛重 {{ totalBoxGrossWeight }} kg</span>
        </div>
      </div>

      <div class="box-list">
        <div v-for="(group, groupIndex) in boxGroups" :key="group.key" class="box-panel">
          <div class="box-panel__summary">
            <div class="box-check">
              <el-checkbox v-model="group.checked" disabled />
            </div>
            <div class="box-no">
              <span class="box-chip"><el-icon><Box /></el-icon>{{ group.label }}</span>
              <span class="box-sub">{{ group.items.length }} 个SKU</span>
            </div>
            <div class="box-stat">
              <span>商品数量</span>
              <strong>{{ group.quantity }}</strong>
            </div>
            <div class="box-stat">
              <span>箱子毛重(kg)</span>
              <strong>{{ group.grossWeight }}</strong>
            </div>
            <div class="box-stat box-stat--wide">
              <span>箱子尺寸(cm)</span>
              <strong>{{ group.dimensionText }}</strong>
            </div>
            <div class="box-stat">
              <span>单箱体积(m³)</span>
              <strong>{{ group.cbm }}</strong>
            </div>
            <div class="box-stat">
              <span>商品净重(kg)</span>
              <strong>{{ group.netWeight }}</strong>
            </div>
            <div class="box-stat">
              <span>箱数</span>
              <strong>{{ group.boxCount }}</strong>
            </div>
            <div class="box-actions">
              <el-button link type="primary" icon="Plus" title="添加商品" @click="addRow(group.lastIndex)" />
            </div>
          </div>

          <div class="box-items">
            <div class="box-items__head">
              <span>品名 / SKU</span>
              <span>申报信息</span>
              <span>数量</span>
              <span>单价</span>
              <span>净重</span>
              <span>地区</span>
              <span>操作</span>
            </div>
            <div v-for="entry in group.items" :key="entry.row._key" class="box-item-row">
              <div class="item-product">
                <div class="item-main">
                  <el-input v-model="entry.row.descriptionCn" size="small" placeholder="商品名称" />
                  <el-select v-model="entry.row.sku" filterable remote clearable size="small" placeholder="输入SKU或品名"
                    :remote-method="searchProducts" :loading="searching" @change="value => selectProduct(entry.row, value)">
                    <el-option v-for="product in productOptions" :key="product.sku" :label="product.sku" :value="product.sku" />
                  </el-select>
                </div>
              </div>
              <div class="item-declare">
                <el-input v-model="entry.row.productCode" size="small" placeholder="商品编码" />
                <el-input v-model="entry.row.hsDescription" size="small" placeholder="申报要素" />
              </div>
              <div class="item-qty">
                <el-input-number v-model="entry.row.quantity" :min="1" :controls="false" size="small" />
                <el-input v-model="entry.row.unit" size="small" placeholder="单位" />
              </div>
              <div class="item-price">
                <el-input-number v-model="entry.row.unitPriceUsd" :min="0" :precision="2" :controls="false" size="small" />
                <span>{{ calcAmount(entry.row) }} {{ entry.row.currency || 'USD' }}</span>
              </div>
              <div class="item-weight">
                <el-input-number v-model="entry.row.singleWeight" :min="0" :precision="2" :controls="false" size="small" />
                <span>{{ calcNetWeight(entry.row) }} kg</span>
              </div>
              <div class="item-country">
                <el-input v-model="entry.row.destinationCountry" size="small" placeholder="目的国" />
                <el-input v-model="entry.row.sourceLocation" size="small" placeholder="货源地" />
              </div>
              <div class="item-actions">
                <el-button link type="primary" icon="Plus" title="在下方添加" @click="addRow(entry.index)" />
                <el-button link type="danger" icon="Minus" title="删除" @click="removeRow(entry.index)" />
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>

    <el-dialog v-model="dataSourceDialog.visible" title="关联数据源" width="980px" append-to-body class="stock-order-dialog">
      <el-tabs v-model="dataSourceDialog.platform" class="source-tabs" @tab-change="handleLinkPlatformChange">
        <el-tab-pane label="eBay备货单" name="stock">
          <div class="stock-link-tip">保存关联后会将所选备货单对应商品合并到当前报关单，重复 SKU 会合并并累加数量。</div>
          <div class="stock-search-row">
            <el-input v-model="stockDialog.keyword" clearable placeholder="搜索备货单号" class="stock-search-input"
              @keyup.enter="loadStockOrders">
              <template #prepend>备货单号</template>
              <template #append>
                <el-button icon="Search" :loading="stockDialog.loading" @click="loadStockOrders" />
              </template>
            </el-input>
          </div>
          <el-table ref="stockOrderTableRef" v-loading="stockDialog.loading" :data="stockDialog.orders" border
            row-key="overseasOrderNo" height="460" class="stock-order-table" @selection-change="handleStockOrderSelection">
            <el-table-column type="selection" width="44" fixed="left" :reserve-selection="true" />
            <el-table-column prop="overseasOrderNo" label="备货单号" min-width="170" fixed="left" />
            <el-table-column prop="productCount" label="装箱商品数量" min-width="140" />
            <el-table-column prop="totalBoxCount" label="总箱数" min-width="120" />
            <el-table-column prop="totalQuantity" label="总装箱量" min-width="140" />
            <el-table-column prop="totalGrossWeight" label="总毛重(kg)" min-width="140">
              <template #default="{ row }">{{ formatNumber(row.totalGrossWeight, 2) }}</template>
            </el-table-column>
          </el-table>
          <div class="stock-dialog-summary">
            <span>共 {{ stockDialog.orders.length }} 条</span>
            <span>已选 {{ stockDialog.selectedOrderNos.length }} 条</span>
          </div>
          <div v-if="stockDialog.missingSkus.length" class="missing-sku-box">
            <div class="missing-sku-title">未匹配到商品库的 SKU（{{ stockDialog.missingSkus.length }}）</div>
            <el-tag v-for="sku in stockDialog.missingSkus" :key="sku" type="danger" effect="plain">{{ sku }}</el-tag>
          </div>
        </el-tab-pane>
        <el-tab-pane label="AMZ FBA货件" name="fba">
          <div class="stock-link-tip">保存关联后会将所选 FBA 货件对应商品合并到当前报关单，重复 SKU 会合并并累加数量。</div>
          <div class="stock-search-row">
            <el-input v-model="fbaDialog.keyword" clearable placeholder="搜索货件编号" class="stock-search-input"
              @keyup.enter="loadFbaShipments">
              <template #prepend>货件编号</template>
              <template #append>
                <el-button icon="Search" :loading="fbaDialog.loading" @click="loadFbaShipments" />
              </template>
            </el-input>
          </div>
          <el-table ref="fbaShipmentTableRef" v-loading="fbaDialog.loading" :data="fbaDialog.shipments" border
            row-key="shipmentId" height="460" class="stock-order-table" @selection-change="handleFbaShipmentSelection">
            <el-table-column type="selection" width="44" fixed="left" :reserve-selection="true" />
            <el-table-column prop="shipmentId" label="货件编号" min-width="170" fixed="left" />
            <el-table-column prop="productCount" label="装箱商品数量" min-width="140" />
            <el-table-column prop="totalBoxCount" label="总箱数" min-width="120" />
            <el-table-column prop="totalQuantity" label="总装箱量" min-width="140" />
            <el-table-column prop="totalGrossWeight" label="总毛重(kg)" min-width="140">
              <template #default="{ row }">{{ formatNumber(row.totalGrossWeight, 2) }}</template>
            </el-table-column>
          </el-table>
          <div class="stock-dialog-summary">
            <span>共 {{ fbaDialog.shipments.length }} 条</span>
            <span>已选 {{ fbaDialog.selectedShipmentIds.length }} 条</span>
          </div>
          <div v-if="fbaDialog.missingSkus.length" class="missing-sku-box">
            <div class="missing-sku-title">未匹配到商品库的 SKU（{{ fbaDialog.missingSkus.length }}）</div>
            <el-tag v-for="sku in fbaDialog.missingSkus" :key="sku" type="danger" effect="plain">{{ sku }}</el-tag>
          </div>
        </el-tab-pane>
      </el-tabs>
      <template #footer>
        <el-button @click="dataSourceDialog.visible = false">取消</el-button>
        <el-button type="primary" :loading="activeLinkSaving" @click="confirmDataSourceLink">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup name="CustomsDeclaration">
import { computed, nextTick, reactive, ref, watch } from 'vue'
import { saveAs } from 'file-saver'
import { blobValidate } from '@/utils/ruoyi'
import {
  checkCustomsProducts,
  exportCustomsDeclaration,
  importFbaShipmentBox,
  importCustomsSkus,
  loadFbaShipmentProducts,
  loadStockOrderProducts,
  saveCustomsProducts,
  searchCustomsProducts,
  searchFbaShipments,
  searchStockOrders
} from '@/api/operations/customs/declaration'

const { proxy } = getCurrentInstance()
const skuFileRef = ref()
const fbaBoxFileRef = ref()
const searching = ref(false)
const saving = ref(false)
const exporting = ref(false)
const fbaBoxImporting = ref(false)
const headerExpanded = ref(false)
const productOptions = ref([])
const stockOrderTableRef = ref()
const fbaShipmentTableRef = ref()
const itemTableRef = ref()
let keySeed = 0

const defaultCompany = '成都玖马赫供应链管理有限公司   信用代码：91510106MACMNJMB6A'
const header = reactive(createHeader())
const items = ref([createEmptyItem()])
const itemPage = reactive({ pageNum: 1, pageSize: 50 })
const dataSourceDialog = reactive({
  visible: false,
  platform: 'stock'
})
const stockDialog = reactive({
  visible: false,
  keyword: '',
  loading: false,
  saving: false,
  orders: [],
  selected: [],
  selectedOrderNos: [],
  restoring: false,
  missingSkus: []
})
const fbaDialog = reactive({
  visible: false,
  keyword: '',
  loading: false,
  saving: false,
  shipments: [],
  selected: [],
  selectedShipmentIds: [],
  restoring: false,
  missingSkus: []
})

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
    sourceLocation: '', exemption: '', boxNo: null, boxCount: 1, sourceOrderNo: '', orderTotalCbm: null, isTax: null,
    packingNetWeight: null, packingGrossWeight: null, packingCbm: null,
    boxLength: null, boxWidth: null, boxHeight: null
  }
}

const validItems = computed(() => items.value.filter(item => item.sku && item.sku.trim()))
const pagedItems = computed(() => {
  const start = (itemPage.pageNum - 1) * itemPage.pageSize
  return items.value.slice(start, start + itemPage.pageSize)
})
const totalQuantity = computed(() => validItems.value.reduce((sum, item) => sum + Number(item.quantity || 0), 0))
const totalAmount = computed(() => validItems.value.reduce((sum, item) => sum + Number(calcAmount(item)), 0).toFixed(2))
const totalNetWeight = computed(() => validItems.value.reduce((sum, item) => sum + Number(calcNetWeight(item)), 0).toFixed(2))
const boxGroups = computed(() => buildBoxGroups(items.value))
const totalBoxCount = computed(() => boxGroups.value.reduce((sum, group) => sum + Number(group.boxCount || 0), 0))
const totalCbm = computed(() => calcTotalCbm())
const totalBoxGrossWeight = computed(() => boxGroups.value.reduce((sum, group) => sum + Number(group.totalGrossWeight || 0), 0).toFixed(2))
const totalGrossWeight = computed(() => totalBoxGrossWeight.value)
const activeLinkSaving = computed(() => dataSourceDialog.platform === 'stock' ? stockDialog.saving : fbaDialog.saving)

watch(totalGrossWeight, v => { header.grossWt = v })
watch(totalNetWeight, v => { header.netWt = v })
watch(
  totalBoxCount,
  value => { header.packQty = value },
  { immediate: true }
)
watch(
  () => items.value.length,
  total => {
    const maxPage = Math.max(1, Math.ceil(total / itemPage.pageSize))
    if (itemPage.pageNum > maxPage) itemPage.pageNum = maxPage
  }
)
watch(
  () => [itemPage.pageNum, itemPage.pageSize],
  () => scrollItemTableTop()
)

function calcAmount(row) {
  return (Number(row.unitPriceUsd || 0) * Number(row.quantity || 0)).toFixed(2)
}

function calcWeight(row) {
  return (Number(row.singleWeight || 0) * Number(row.quantity || 0)).toFixed(2)
}

function calcNetWeight(row) {
  if (Number(row.packingNetWeight || 0) > 0) {
    return (Number(row.packingNetWeight) * Number(row.quantity || 1)).toFixed(2)
  }
  return calcWeight(row)
}

function calcGrossWeight(row) {
  return Number(row.packingGrossWeight || 0) > 0 ? Number(row.packingGrossWeight).toFixed(2) : calcNetWeight(row)
}

function formatNumber(value, precision = 0) {
  const number = Number(value || 0)
  return precision > 0 ? number.toFixed(precision) : number.toString()
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

function productToRow(product) {
  return {
    ...JSON.parse(JSON.stringify(product)),
    quantity: Number(product.quantity || 1),
    boxCount: Number(product.boxCount || 1),
    orderTotalCbm: product.orderTotalCbm ?? null,
    sourceOrderNo: product.sourceOrderNo || '',
    _key: ++keySeed,
    productCode: product.productCode || product.hsCode || '',
    boxNo: product.boxNo || null,
    isTax: product.isTax != null ? product.isTax : null
  }
}

async function openDataSourceDialog() {
  dataSourceDialog.visible = true
  await loadActiveLinkOptions()
  await restoreActiveLinkSelection()
}

async function handleLinkPlatformChange() {
  await loadActiveLinkOptions()
  await restoreActiveLinkSelection()
}

async function loadActiveLinkOptions() {
  if (dataSourceDialog.platform === 'stock') await loadStockOrders()
  else await loadFbaShipments()
}

async function confirmDataSourceLink() {
  if (dataSourceDialog.platform === 'stock') await confirmStockOrderLink()
  else await confirmFbaShipmentLink()
}

async function restoreActiveLinkSelection() {
  if (dataSourceDialog.platform === 'stock') await restoreStockOrderSelection()
  else await restoreFbaShipmentSelection()
}

function handleItemPagination() {
  scrollItemTableTop()
}

async function scrollItemTableTop() {
  await nextTick()
  itemTableRef.value?.setScrollTop?.(0)
  if (itemTableRef.value?.scrollTo) itemTableRef.value.scrollTo({ top: 0, behavior: 'smooth' })
}

function buildBoxGroups(sourceItems) {
  const groups = new Map()
  sourceItems.forEach((row, index) => {
    const key = boxGroupKey(row)
    if (!groups.has(key)) {
      groups.set(key, {
        key,
        checked: true,
        label: row.boxNo ? String(row.boxNo) : '',
        boxCount: inferBoxCount(row),
        grossWeight: boxGrossWeight(row),
        totalGrossWeight: key === 'unboxed' ? 0 : boxGrossWeight(row) * inferBoxCount(row),
        cbm: boxCbm(row),
        totalCbm: key === 'unboxed' ? 0 : boxCbm(row) * inferBoxCount(row),
        dimensionText: dimensionText(row),
        quantity: 0,
        netWeight: 0,
        items: [],
        lastIndex: index
      })
    }
    const group = groups.get(key)
    group.boxCount = Math.max(Number(group.boxCount || 1), inferBoxCount(row))
    group.items.push({ row, index })
    group.quantity += Number(row.quantity || 0)
    group.netWeight += Number(calcNetWeight(row))
    if (key === 'unboxed') group.totalGrossWeight += Number(calcGrossWeight(row))
    if (key === 'unboxed') group.grossWeight = group.totalGrossWeight
    group.lastIndex = index
  })
  return Array.from(groups.values()).map((group, index) => ({
    ...group,
    label: group.key === 'unboxed' ? '未分箱' : (group.label || String(index + 1)),
    grossWeight: formatNumber(group.grossWeight, 2),
    totalGrossWeight: Number(group.totalGrossWeight || 0),
    cbm: formatNumber(group.cbm, 2),
    totalCbm: Number(group.totalCbm || 0),
    netWeight: formatNumber(group.netWeight, 2),
    quantity: formatNumber(group.quantity, 0)
  }))
}

function boxGroupKey(row) {
  if (row.boxNo) return row.boxNo
  const values = [row.packingGrossWeight, row.boxLength, row.boxWidth, row.boxHeight, row.packingCbm]
    .map(value => Number(value || 0).toFixed(2))
  return values.some(value => Number(value) > 0) ? values.join('|') : 'unboxed'
}

function inferBoxCount(row) {
  const count = Number(row.boxCount || 0)
  return count > 0 ? count : 1
}

function calcTotalCbm() {
  const orderTotals = new Map()
  boxGroups.value.forEach(group => {
    const orderItem = group.items.find(entry => Number(entry.row.orderTotalCbm || 0) > 0 && entry.row.sourceOrderNo)
    if (orderItem) {
      orderTotals.set(orderItem.row.sourceOrderNo, Number(orderItem.row.orderTotalCbm))
    }
  })
  const orderCbm = Array.from(orderTotals.values()).reduce((sum, value) => sum + value, 0)
  const manualCbm = boxGroups.value
    .filter(group => !group.items.some(entry => Number(entry.row.orderTotalCbm || 0) > 0 && entry.row.sourceOrderNo))
    .reduce((sum, group) => sum + Number(group.totalCbm || 0), 0)
  return (orderCbm + manualCbm).toFixed(2)
}

function boxGrossWeight(row) {
  return Number(row.packingGrossWeight || 0) > 0 ? Number(row.packingGrossWeight || 0) : 0
}

function boxCbm(row) {
  if (Number(row.packingCbm || 0) > 0) return Number(row.packingCbm || 0)
  const length = Number(row.boxLength || 0)
  const width = Number(row.boxWidth || 0)
  const height = Number(row.boxHeight || 0)
  return length && width && height ? length * width * height / 1000000 : 0
}

function dimensionText(row) {
  const length = Number(row.boxLength || 0)
  const width = Number(row.boxWidth || 0)
  const height = Number(row.boxHeight || 0)
  return length && width && height
    ? `${formatNumber(length, 2)}*${formatNumber(width, 2)}*${formatNumber(height, 2)}`
    : '-'
}

async function openStockOrderDialog() {
  dataSourceDialog.visible = true
  dataSourceDialog.platform = 'stock'
  stockDialog.keyword = ''
  stockDialog.missingSkus = []
  await loadStockOrders()
}

async function loadStockOrders() {
  stockDialog.loading = true
  try {
    const response = await searchStockOrders({ keyword: stockDialog.keyword, limit: 100 })
    stockDialog.orders = response.data || []
    stockDialog.missingSkus = []
    await restoreStockOrderSelection()
  } finally {
    stockDialog.loading = false
  }
}

function handleStockOrderSelection(selection) {
  if (stockDialog.restoring) return
  stockDialog.selected = selection
  stockDialog.selectedOrderNos = mergeVisibleSelection(
    stockDialog.selectedOrderNos,
    stockDialog.orders,
    selection,
    'overseasOrderNo'
  )
}

async function restoreStockOrderSelection() {
  await nextTick()
  await delay(0)
  stockDialog.restoring = true
  const selected = new Set(stockDialog.selectedOrderNos)
  stockDialog.orders.forEach(row => {
    stockOrderTableRef.value?.toggleRowSelection(row, selected.has(row.overseasOrderNo))
  })
  await nextTick()
  stockDialog.restoring = false
}

async function confirmStockOrderLink() {
  if (!stockDialog.selectedOrderNos.length) {
    proxy.$modal.msgWarning('请先选择备货单')
    return
  }
  stockDialog.saving = true
  try {
    const response = await loadStockOrderProducts({ overseasOrderNos: stockDialog.selectedOrderNos })
    const result = normalizeLinkResult(response.data)
    const rows = result.products.map(productToRow)
    stockDialog.missingSkus = result.missingSkus
    if (!rows.length && !result.missingSkus.length) {
      proxy.$modal.msgWarning('未匹配到报关产品库商品，请先同步或维护商品库')
      return
    }
    appendLinkedRows(rows)
    if (result.missingSkus.length) proxy.$modal.msgWarning(`已关联 ${rows.length} 个商品，${result.missingSkus.length} 个SKU未匹配`)
    else {
      dataSourceDialog.visible = false
      proxy.$modal.msgSuccess(`已关联 ${rows.length} 个商品`)
    }
  } finally {
    stockDialog.saving = false
  }
}

async function openFbaShipmentDialog() {
  dataSourceDialog.visible = true
  dataSourceDialog.platform = 'fba'
  fbaDialog.keyword = ''
  fbaDialog.missingSkus = []
  await loadFbaShipments()
}

async function loadFbaShipments() {
  fbaDialog.loading = true
  try {
    const response = await searchFbaShipments({ keyword: fbaDialog.keyword, limit: 100 })
    fbaDialog.shipments = response.data || []
    fbaDialog.missingSkus = []
    await restoreFbaShipmentSelection()
  } finally {
    fbaDialog.loading = false
  }
}

function handleFbaShipmentSelection(selection) {
  if (fbaDialog.restoring) return
  fbaDialog.selected = selection
  fbaDialog.selectedShipmentIds = mergeVisibleSelection(
    fbaDialog.selectedShipmentIds,
    fbaDialog.shipments,
    selection,
    'shipmentId'
  )
}

async function restoreFbaShipmentSelection() {
  await nextTick()
  await delay(0)
  fbaDialog.restoring = true
  const selected = new Set(fbaDialog.selectedShipmentIds)
  fbaDialog.shipments.forEach(row => {
    fbaShipmentTableRef.value?.toggleRowSelection(row, selected.has(row.shipmentId))
  })
  await nextTick()
  fbaDialog.restoring = false
}

function mergeVisibleSelection(existingIds, visibleRows, selection, key) {
  const next = new Set(existingIds)
  const selected = new Set(selection.map(item => item[key]).filter(Boolean))
  visibleRows.forEach(row => {
    const id = row[key]
    if (!id) return
    if (selected.has(id)) next.add(id)
    else next.delete(id)
  })
  return Array.from(next)
}

function delay(ms) {
  return new Promise(resolve => setTimeout(resolve, ms))
}

async function confirmFbaShipmentLink() {
  if (!fbaDialog.selectedShipmentIds.length) {
    proxy.$modal.msgWarning('请先选择FBA货件')
    return
  }
  fbaDialog.saving = true
  try {
    const response = await loadFbaShipmentProducts({ shipmentIds: fbaDialog.selectedShipmentIds })
    const result = normalizeLinkResult(response.data)
    const rows = result.products.map(productToRow)
    fbaDialog.missingSkus = result.missingSkus
    if (!rows.length && !result.missingSkus.length) {
      proxy.$modal.msgWarning('未匹配到报关产品库商品，请先同步或维护商品库')
      return
    }
    appendLinkedRows(rows)
    if (result.missingSkus.length) proxy.$modal.msgWarning(`已关联 ${rows.length} 个商品，${result.missingSkus.length} 个SKU未匹配`)
    else {
      dataSourceDialog.visible = false
      proxy.$modal.msgSuccess(`已关联 ${rows.length} 个商品`)
    }
  } finally {
    fbaDialog.saving = false
  }
}

function normalizeLinkResult(data) {
  if (Array.isArray(data)) return { products: data, missingSkus: [] }
  return {
    products: data?.products || [],
    missingSkus: data?.missingSkus || []
  }
}

function canMergeCustomsProduct(existing, incoming) {
  const isTax = Number(incoming.isTax || existing.isTax || 0) === 1
  if (!isTax) return false
  return normalize(existing.sku) === normalize(incoming.sku)
    && normalize(existing.sourceLocation) === normalize(incoming.sourceLocation)
    && normalize(existing.boxNo) === normalize(incoming.boxNo)
    && normalize(existing.destinationCountry) === normalize(incoming.destinationCountry)
}

function normalize(v) { return (v || '').trim() }

function mergeCustomsProductRows(currentRows, incomingRows) {
  const result = [...currentRows]
  incomingRows.forEach(incoming => {
    if (!incoming.sku?.trim()) return
    const match = result.find(existing => canMergeCustomsProduct(existing, incoming))
    if (match) {
      match.quantity = Number(match.quantity || 0) + Number(incoming.quantity || 1)
      match.boxCount = Math.max(Number(match.boxCount || 1), Number(incoming.boxCount || 1))
    } else {
      result.push({ ...incoming, quantity: Number(incoming.quantity || 1), boxCount: Number(incoming.boxCount || 1) })
    }
  })
  return result
}

function appendLinkedRows(rows) {
  if (!rows.length) return
  const onlyEmptyRow = items.value.length === 1 && !items.value[0].sku
  if (onlyEmptyRow) items.value = []
  items.value = mergeCustomsProductRows(items.value, rows)
  if (!items.value.length) items.value = [createEmptyItem()]
  itemPage.pageNum = Math.max(1, Math.ceil(items.value.length / itemPage.pageSize))
}

function addRow(index) {
  items.value.splice(index + 1, 0, createEmptyItem())
  itemPage.pageNum = Math.max(1, Math.ceil((index + 2) / itemPage.pageSize))
}

function removeRow(index) {
  if (items.value.length === 1) {
    proxy.$modal.msgWarning('至少保留一行')
    return
  }
  items.value.splice(index, 1)
}

function toActualIndex(pageIndex) {
  return (itemPage.pageNum - 1) * itemPage.pageSize + pageIndex
}

function openSkuFile() { skuFileRef.value?.click() }
function openFbaBoxFile() { fbaBoxFileRef.value?.click() }

function handleToolbarCommand(command) {
  const actions = {
    sku: openSkuFile,
    fbaBox: openFbaBoxFile,
  }
  actions[command]?.()
}

async function handleSkuFile(event) {
  const file = event.target.files?.[0]
  if (!file) return
  try {
    const response = await importCustomsSkus(file)
    const result = response.data || {}
    const loaded = (result.products || []).map(productToRow)
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

async function handleFbaBoxFile(event) {
  const file = event.target.files?.[0]
  if (!file) return
  fbaBoxImporting.value = true
  proxy.$modal.loading('正在导入 FBA 装箱明细，请稍候...')
  try {
    const response = await importFbaShipmentBox(file)
    const result = response.data || {}
    const message = `FBA 装箱明细导入完成：读取 ${result.readRows || 0} 行，新增 ${result.insertedRows || 0} 行，货件 ${result.importedShipments || 0} 个`
      + (result.skippedExistingShipments ? `，跳过已存在货件 ${result.skippedExistingShipments} 个` : '')
      + (result.failedRows ? `，失败 ${result.failedRows} 行` : '')
      + (result.unmatchedShops?.length ? `，未匹配店铺 ${result.unmatchedShops.length} 个` : '')
    if (result.failedRows || result.unmatchedShops?.length) {
      proxy.$alert(message, '导入完成但有异常', { type: 'warning' })
    } else {
      proxy.$alert(message, '导入成功', { type: 'success' })
    }
  } catch (error) {
    proxy.$modal.msgError(`FBA 装箱明细导入失败：${error?.message || error || '请查看后台日志'}`)
  } finally {
    proxy.$modal.closeLoading()
    fbaBoxImporting.value = false
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
  const data = validItems.value.map(toProductPayload)
  const checkResponse = await checkCustomsProducts(data)
  const existing = checkResponse.data || []
  if (existing.length) {
    const preview = existing.slice(0, 8)
      .map(item => `${item.sku || ''}${item.sourceLocation ? ` / ${item.sourceLocation}` : ''}`)
      .join('、')
    await proxy.$modal.confirm(`已有 ${existing.length} 条商品资料存在：${preview}${existing.length > 8 ? '...' : ''}，是否覆盖？`)
  }
  saving.value = true
  try {
    const response = await saveCustomsProducts(data, existing.length > 0)
    proxy.$modal.msgSuccess(`已保存 ${response.data || data.length} 条商品资料`)
  } finally {
    saving.value = false
  }
}

function toProductPayload(item) {
  return {
    id: item.id,
    sku: item.sku,
    descriptionCn: item.descriptionCn,
    model: item.model,
    unit: item.unit,
    unitPriceUsd: item.unitPriceUsd,
    currency: item.currency,
    singleWeight: item.singleWeight,
    packingNetWeight: item.packingNetWeight,
    packingGrossWeight: item.packingGrossWeight,
    packingCbm: item.packingCbm,
    boxLength: item.boxLength,
    boxWidth: item.boxWidth,
    boxHeight: item.boxHeight,
    boxNo: item.boxNo,
    hsCode: item.hsCode,
    hsDescription: item.hsDescription,
    originCountry: item.originCountry,
    destinationCountry: item.destinationCountry,
    sourceLocation: item.sourceLocation,
    exemption: item.exemption,
    isTax: item.isTax
  }
}

async function handleExport() {
  if (!validateItems()) return
  exporting.value = true
  try {
    const exportHeader = {
      ...header,
      packQty: totalBoxCount.value,
      grossWt: totalGrossWeight.value,
      netWt: totalNetWeight.value
    }
    const response = await exportCustomsDeclaration({ header: exportHeader, items: validItems.value })
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
  itemPage.pageNum = 1
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

.packing-workbench {
  height: 620px;
  overflow: auto;
  border: 1px solid #dcdfe6;
  background: #f7f9fc;
}

.packing-head {
  position: sticky;
  top: 0;
  z-index: 3;
  display: flex;
  min-width: 1320px;
  height: 42px;
  padding: 0 12px;
  border-bottom: 1px solid #dcdfe6;
  background: #fff;
  align-items: center;
  justify-content: space-between;
}

.packing-head__title,
.packing-head__meta {
  display: flex;
  align-items: center;
}

.packing-head__title {
  gap: 7px;
  color: #303133;
  font-size: 14px;
  font-weight: 600;
}

.packing-head__meta {
  gap: 18px;
  color: #606266;
  font-size: 13px;
}

.box-list {
  min-width: 1320px;
}

.box-panel {
  border-bottom: 1px solid #e4e7ed;
  background: #fff;
}

.box-panel__summary {
  display: grid;
  grid-template-columns: 38px 150px 78px 130px 180px 120px 120px 90px 58px;
  min-height: 52px;
  background: #f8fbff;
  align-items: center;
}

.box-panel:nth-child(even) .box-panel__summary {
  background: #eef5ff;
}

.box-check,
.box-actions {
  text-align: center;
}

.box-no {
  display: flex;
  min-width: 0;
  flex-direction: column;
  gap: 3px;
}

.box-chip {
  display: inline-flex;
  width: fit-content;
  align-items: center;
  gap: 5px;
  color: #1f4f7a;
  font-size: 13px;
  font-weight: 600;
}

.box-chip .el-icon {
  color: #e6b95c;
}

.box-sub {
  color: #909399;
  font-size: 12px;
}

.box-stat {
  display: flex;
  min-width: 0;
  flex-direction: column;
  gap: 4px;
  padding: 0 10px;
  border-left: 1px solid #e4e7ed;
}

.box-stat span {
  overflow: hidden;
  color: #909399;
  font-size: 12px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.box-stat strong {
  overflow: hidden;
  color: #111827;
  font-size: 13px;
  font-variant-numeric: tabular-nums;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.box-stat--wide strong {
  font-family: Consolas, monospace;
}

.box-items {
  border-top: 1px solid #ebeef5;
  background: #fff;
}

.box-items__head,
.box-item-row {
  display: grid;
  grid-template-columns: 280px 260px 130px 130px 130px 190px 72px;
  column-gap: 10px;
  align-items: center;
}

.box-items__head {
  height: 32px;
  padding: 0 12px 0 188px;
  color: #909399;
  font-size: 12px;
}

.box-item-row {
  min-height: 76px;
  padding: 8px 12px 8px 188px;
  border-top: 1px solid #edf0f5;
}

.item-product {
  display: grid;
  min-width: 0;
  gap: 5px;
}

.item-main,
.item-declare,
.item-qty,
.item-price,
.item-weight,
.item-country {
  display: grid;
  min-width: 0;
  gap: 5px;
}

.item-qty {
  grid-template-columns: minmax(0, 1fr) 42px;
}

.item-price span,
.item-weight span {
  color: #606266;
  font-size: 12px;
  font-variant-numeric: tabular-nums;
}

.item-actions {
  display: flex;
  justify-content: center;
}

.packing-workbench :deep(.el-input-number),
.packing-workbench :deep(.el-select) {
  width: 100%;
}

.packing-workbench :deep(.el-input__wrapper) {
  padding: 1px 7px;
}

.packing-inputs {
  display: grid;
  grid-template-columns: repeat(6, minmax(0, 1fr));
  gap: 4px;
}

.packing-inputs :deep(.el-input-number) {
  width: 100%;
}

.calculated-value {
  color: #303133;
  font-size: 13px;
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}

.stock-link-tip {
  margin-bottom: 10px;
  padding: 11px 14px;
  border-radius: 4px;
  background: #fff4dc;
  color: #303133;
  font-size: 13px;
}

.stock-search-row {
  display: flex;
  margin-bottom: 12px;
}

.stock-search-input {
  width: 320px;
}

.stock-order-table {
  width: 100%;
}

.stock-dialog-summary {
  display: flex;
  justify-content: flex-end;
  gap: 18px;
  padding-top: 10px;
  color: #606266;
  font-size: 13px;
}

.missing-sku-box {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  max-height: 110px;
  padding: 10px;
  margin-top: 10px;
  overflow-y: auto;
  border: 1px solid #f3d0d0;
  border-radius: 4px;
  background: #fff7f7;
}

.missing-sku-title {
  width: 100%;
  color: #c45656;
  font-size: 13px;
  font-weight: 600;
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
