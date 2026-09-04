<template>
  <div class="app-container ebay-replenishment-v2-page">
    <el-form
      v-show="showSearch"
      ref="queryRef"
      :model="queryParams"
      :inline="true"
      label-width="72px"
      class="query-form"
    >
      <el-form-item label="站点" prop="site">
        <el-select v-model="queryParams.site" placeholder="全部站点" clearable style="width: 160px">
          <el-option v-for="site in siteOptions" :key="site" :label="site" :value="site" />
        </el-select>
      </el-form-item>
      <el-form-item label="SKU" prop="sku">
        <el-input
          v-model="queryParams.sku"
          placeholder="请输入SKU"
          clearable
          style="width: 220px"
          @keyup.enter="handleQuery"
        />
      </el-form-item>
      <el-form-item label="产品等级" prop="productLevel">
        <el-select
          v-model="queryParams.productLevel"
          placeholder="全部等级"
          clearable
          style="width: 160px"
        >
          <el-option
            v-for="level in productLevelOptions"
            :key="level"
            :label="level"
            :value="level"
          />
        </el-select>
      </el-form-item>
      <el-form-item label="产品性质" prop="productNature">
        <el-select
          v-model="queryParams.productNature"
          placeholder="全部性质"
          clearable
          style="width: 160px"
        >
          <el-option
            v-for="nature in productNatureOptions"
            :key="nature"
            :label="nature"
            :value="nature"
          />
        </el-select>
      </el-form-item>
      <el-form-item>
        <el-button type="primary" icon="Search" @click="handleQuery">搜索</el-button>
        <el-button icon="Refresh" @click="resetQuery">重置</el-button>
      </el-form-item>
    </el-form>

    <el-row :gutter="10" class="mb8 table-toolbar">
      <el-col :span="1.5">
        <el-tag type="info" effect="plain">统计月份：{{ monthRangeText }}</el-tag>
      </el-col>
      <el-col :span="1.5" class="field-count">销量、毛利和退货数据按最近3个完整自然月统计；利润率、退货率按3个月合计口径计算</el-col>
      <el-col :span="1.5">
        <el-button
          type="primary"
          plain
          icon="Upload"
          v-hasPermi="['operations:ebayReplenishmentV2:importWarehouseRent']"
          @click="warehouseRentDialogVisible = true"
        >
          上传仓租
        </el-button>
      </el-col>
      <right-toolbar
        v-model:showSearch="showSearch"
        :show-column-config="true"
        @queryTable="loadRows"
        @columnConfig="openColumnConfig"
      />
    </el-row>

    <el-table
      v-if="columnConfigLoaded"
      v-loading="loading"
      :key="columnTableKey"
      :data="rows"
      border
      stripe
      height="640"
      :row-key="row => `${row.site}|${row.sku}`"
      empty-text="暂无符合条件的订单数据"
      @sort-change="handleSortChange"
    >
      <template v-for="col in visibleColumns" :key="col.key">
        <el-table-column
          v-if="col.key === 'productLevel'"
          :label="col.label"
          :prop="col.key"
          :align="col.align"
          :width="col.width"
          :fixed="col.fixed || false"
        >
          <template #header>
            <span class="column-header">
              <span>{{ col.label }}</span>
              <el-tooltip v-if="col.tip" :content="col.tip" placement="top">
                <el-icon class="column-tip"><QuestionFilled /></el-icon>
              </el-tooltip>
            </span>
          </template>
          <template #default="scope">
            <el-tag v-if="scope.row.productLevel" :type="levelTagType(scope.row.productLevel)" effect="light">
              {{ scope.row.productLevel }}
            </el-tag>
            <span v-else>--</span>
          </template>
        </el-table-column>

        <el-table-column
          v-else
          :label="col.label"
          :prop="col.key"
          :align="col.align"
          :width="col.width"
          :fixed="col.fixed || false"
          :sortable="col.sortable ? 'custom' : false"
          :show-overflow-tooltip="col.tooltip"
        >
          <template #header>
            <span
              class="column-header"
              :class="{ 'column-header--formula': canEditFormula && isFormulaColumn(col) }"
              @click="canEditFormula && isFormulaColumn(col) && openFormulaDialog()"
            >
              <span>{{ col.label }}</span>
              <el-tooltip v-if="col.tip" :content="columnTip(col)" placement="top">
                <el-icon class="column-tip"><QuestionFilled /></el-icon>
              </el-tooltip>
            </span>
          </template>
          <template #default="scope">
            <div v-if="col.manualLeadTime" class="lead-time-cell">
              <el-input-number
                v-if="canEditLeadTime"
                v-model="scope.row[col.key]"
                class="lead-time-input"
                :min="0"
                :max="3650"
                :precision="0"
                :step="1"
                step-strictly
                :controls="false"
                placeholder="天数"
                @blur="scheduleLeadTimeSave(scope.row, col)"
                @keyup.enter="handleLeadTimeEnter($event, scope.row, col)"
              />
              <span v-else>{{ formatCell(scope.row[col.key], col) }}</span>
              <span v-if="isLeadTimeSaving(scope.row, col.key)" class="lead-time-saving">保存中</span>
              <span v-else-if="canEditLeadTime" class="lead-time-unit">天</span>
            </div>
            <el-popover
              v-else-if="col.monthlyKey"
              placement="top"
              :width="300"
              trigger="hover"
              :show-after="180"
              popper-class="replenishment-monthly-popper"
            >
              <template #reference>
                <span class="monthly-metric-trigger">
                  <strong>{{ formatCell(scope.row[col.key], col) }}</strong>
                  <span class="monthly-metric-month">{{ formatMonth(latestCompleteMonth, false) }}</span>
                </span>
              </template>
              <div class="monthly-history">
                <div class="monthly-history__title">{{ col.label }} · 最近3个完整自然月</div>
                <div v-for="metric in monthlyRows(scope.row)" :key="metric.month" class="monthly-history__row">
                  <span>{{ formatMonth(metric.month, true) }}</span>
                  <strong>{{ formatMonthlyValue(metric[col.monthlyKey], col) }}</strong>
                </div>
              </div>
            </el-popover>
            <template v-else-if="isFormulaColumn(col)">
              <span :class="{ 'suggested-qty': col.key === 'suggestedReplenishmentQty' && hasValue(scope.row[col.key]) }">
                {{ formatCell(scope.row[col.key], col) }}
              </span>
            </template>
            <span v-else>{{ formatCell(scope.row[col.key], col) }}</span>
          </template>
        </el-table-column>
      </template>
      <el-table-column v-if="canSubmitPurchase" label="操作" width="92" fixed="right" align="center">
        <template #default="{ row }">
          <el-button
            link
            type="primary"
            v-hasPermi="['procurement:pendingPurchase:add']"
            @click="openPurchaseDialog(row)"
          >
            采购
          </el-button>
        </template>
      </el-table-column>
    </el-table>

    <pagination
      v-show="total > 0"
      :total="total"
      v-model:page="queryParams.pageNum"
      v-model:limit="queryParams.pageSize"
      @pagination="loadRows"
    />

    <column-config-drawer
      v-model="showColumnDrawer"
      :columns="columnDefs"
      :fixed-keys="fixedColumnKeys"
      :visible-keys="visibleKeys"
      @apply="handleColumnApply"
    />

    <el-dialog
      v-if="canEditFormula"
      v-model="formulaDialogVisible"
      title="安全库存与建议补货量公式配置"
      width="720px"
      append-to-body
      destroy-on-close
    >
      <el-alert
        type="warning"
        :closable="false"
        show-icon
        title="修改后会影响全部同级别 SKU"
        description="这里配置的是eBay补货2.0全局分级系数，不是当前行的单独配置；保存后页面会重新查询并实时计算全部SKU。"
        class="formula-alert"
      />
      <div class="formula-description">
        <div>安全库存 = 月均日销 ×（总提前天数 × 安全系数）</div>
        <div>建议补货量 = 月均日销 ×（总提前天数 × 补货系数）− 库存合计，负数按0显示</div>
      </div>
      <el-table v-loading="formulaLoading" :data="formulaRows" border>
        <el-table-column prop="productLevel" label="产品等级" width="120" align="center" />
        <el-table-column label="安全系数" min-width="190" align="center">
          <template #default="{ row }">
            <el-input-number
              v-model="row.safetyCoefficient"
              :min="0"
              :precision="4"
              :step="0.1"
              controls-position="right"
            />
          </template>
        </el-table-column>
        <el-table-column label="补货系数" min-width="190" align="center">
          <template #default="{ row }">
            <el-input-number
              v-model="row.suggestCoefficient"
              :min="0"
              :precision="4"
              :step="0.1"
              controls-position="right"
            />
          </template>
        </el-table-column>
      </el-table>
      <template #footer>
        <el-button @click="formulaDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="formulaSaving" @click="submitFormulaConfig">保存并重新计算</el-button>
      </template>
    </el-dialog>

    <el-dialog
      v-model="purchaseDialogVisible"
      title="确认最终采购量"
      width="480px"
      append-to-body
      destroy-on-close
      @closed="resetPurchaseForm"
    >
      <el-form ref="purchaseFormRef" :model="purchaseForm" :rules="purchaseRules" label-width="112px">
        <el-form-item label="站点">
          <el-input :model-value="purchaseForm.site" disabled />
        </el-form-item>
        <el-form-item label="SKU">
          <el-input :model-value="purchaseForm.sku" disabled />
        </el-form-item>
        <el-form-item label="建议补货量">
          <el-input :model-value="formatSuggestedQuantity(purchaseForm.suggestedQuantity)" disabled />
        </el-form-item>
        <el-form-item label="最终采购量" prop="purchaseQuantity">
          <el-input-number
            v-model="purchaseForm.purchaseQuantity"
            :min="1"
            :max="999999999"
            :precision="0"
            :step="1"
            step-strictly
            controls-position="right"
            placeholder="请输入最终采购量"
            style="width: 100%"
          />
        </el-form-item>
        <el-alert type="info" :closable="false" show-icon
          title="确认后进入采购中心的待采购清单；重复确认同一站点和SKU会更新最终采购量。" />
      </el-form>
      <template #footer>
        <el-button @click="purchaseDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="purchaseSubmitting" @click="submitPurchase">确认采购</el-button>
      </template>
    </el-dialog>

    <el-dialog
      v-model="warehouseRentDialogVisible"
      title="上传仓租明细"
      width="560px"
      append-to-body
      destroy-on-close
      @closed="resetWarehouseRentUpload"
    >
      <el-alert
        type="warning"
        :closable="false"
        show-icon
        title="按单号增量覆盖"
        description="系统仅读取“仓租明细”Sheet，并按第一列“单号”增量覆盖：本次文件出现的单号会替换其旧明细，未出现的历史单号继续保留。文件会先完整校验，校验失败不会修改旧数据。"
        class="warehouse-rent-alert"
      />
      <el-upload
        ref="warehouseRentUploadRef"
        v-model:file-list="warehouseRentFiles"
        drag
        :auto-upload="false"
        :limit="1"
        accept=".xlsx"
        :on-change="handleWarehouseRentFileChange"
        :on-exceed="handleWarehouseRentFileExceed"
      >
        <el-icon class="el-icon--upload"><UploadFilled /></el-icon>
        <div class="el-upload__text">将仓租明细拖到此处，或<em>点击选择文件</em></div>
        <template #tip>
          <div class="el-upload__tip">仅支持 .xlsx 文件，单次上传一个完整仓租明细文件。</div>
        </template>
      </el-upload>
      <template #footer>
        <el-button @click="warehouseRentDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="warehouseRentUploading" @click="submitWarehouseRentImport">
          增量导入
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup name="EbayReplenishmentV2">
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { QuestionFilled, UploadFilled } from '@element-plus/icons-vue'
import {
  getEbayReplenishmentV2Formula,
  importEbayReplenishmentV2WarehouseRent,
  listEbayReplenishmentV2,
  saveEbayReplenishmentV2Formula,
  saveEbayReplenishmentV2LeadTime
} from '@/api/operations/ebay/replenishmentV2'
import { submitPendingPurchase } from '@/api/procurement/pendingPurchase'
import { checkPermi } from '@/utils/permission'
import ColumnConfigDrawer from '@/components/ColumnConfigDrawer/index.vue'
import { useColumnConfig } from '@/composables/useColumnConfig'

const showSearch = ref(true)
const queryRef = ref(null)
const loading = ref(false)
const rows = ref([])
const total = ref(0)
const siteOptions = ref([])
// 与后端 _product_level 的取值保持一致：D 级已并入 C，长尾产品统一按 B 展示
const productLevelOptions = ['S', 'A', 'B', 'C']
const productNatureOptions = ['新品', '老品']
const months = ref([])
const latestCompleteMonth = ref('')
const canSubmitPurchase = checkPermi(['procurement:pendingPurchase:add'])
const canEditLeadTime = checkPermi(['operations:ebayReplenishmentV2:editLeadTime'])
const canEditFormula = checkPermi(['operations:ebayReplenishmentV2:formula'])
const leadTimeSavedValues = new Map()
const leadTimeSaveTimers = new Map()
const leadTimeSaveChains = new Map()
const leadTimeEditVersions = new Map()
const savingLeadTimeKeys = reactive(new Set())
const purchaseDialogVisible = ref(false)
const purchaseSubmitting = ref(false)
const purchaseFormRef = ref(null)
const warehouseRentDialogVisible = ref(false)
const warehouseRentUploading = ref(false)
const warehouseRentUploadRef = ref(null)
const warehouseRentFiles = ref([])
const formulaDialogVisible = ref(false)
const formulaLoading = ref(false)
const formulaSaving = ref(false)
const formulaRows = ref([])
const formulaLevels = ['S', 'A', 'B', 'C']
const purchaseForm = reactive({
  site: '',
  sku: '',
  suggestedQuantity: null,
  purchaseQuantity: null
})
const purchaseRules = {
  purchaseQuantity: [{
    validator: (_rule, value, callback) => {
      if (Number.isInteger(Number(value)) && Number(value) > 0) callback()
      else callback(new Error('请输入大于0的整数采购量'))
    },
    trigger: ['blur', 'change']
  }]
}
const fixedColumnKeys = ['site', 'sku']

const columnDefs = [
  { key: 'site', label: '站点', align: 'center', width: 90, fixed: 'left', sortable: true },
  { key: 'sku', label: 'SKU', align: 'left', width: 170, fixed: 'left', sortable: true, tooltip: true },
  { key: 'productName', label: '产品名称', align: 'left', width: 240, sortable: true, tooltip: true },
  {
    key: 'salesQty', label: '销量', align: 'right', width: 130, sortable: true, format: 'integer', monthlyKey: 'salesQty',
    tip: '主值为最近一个完整自然月的销量；鼠标悬停可查看最近3个完整自然月。'
  },
  {
    key: 'grossProfitAmount', label: '毛利', align: 'right', width: 145, sortable: true, format: 'money', monthlyKey: 'grossProfitAmount',
    tip: '毛利取订单数据中的“订单利润(￥)”；主值为最近完整自然月，鼠标悬停可查看近3个月。'
  },
  {
    key: 'profitRate', label: '利润率', align: 'right', width: 110, sortable: true, format: 'percentage',
    tip: '最近3个完整自然月利润率 = 3个月订单利润(￥)合计 ÷ 3个月已支付金额合计 × 100%；不按单月拆分或平均月度百分比。'
  },
  {
    key: 'returnQty', label: '退货量', align: 'right', width: 130, sortable: true, format: 'integer', monthlyKey: 'returnQty',
    tip: '主值为最近一个完整自然月的退货量；鼠标悬停可查看最近3个完整自然月。'
  },
  {
    key: 'returnRate', label: '退货率', align: 'right', width: 110, sortable: true, format: 'percentage',
    tip: '最近3个完整自然月退货率 = 3个月退货量合计 ÷ 3个月销量合计 × 100%；退货量包含发货状态为已退款或已作废的数据。'
  },
  {
    key: 'returnAmount', label: '退货金额', align: 'right', width: 150, sortable: true, format: 'money', monthlyKey: 'returnAmount',
    tip: '退货金额为人民币；主值为最近完整自然月，鼠标悬停可查看近3个月。'
  },
  {
    key: 'warehouseRentAmount', label: '仓租费用', align: 'right', width: 135, format: 'money',
    tip: '取最近一次整表导入的第22列“总金额(不含税)”（包含附加费），按仓库映射站点、商品编码去除JMH-前缀后匹配SKU，再按固定汇率换算为人民币汇总。'
  },
  {
    key: 'forecastSalesQty', label: '预估销量', align: 'right', width: 115, format: 'quantity2',
    tip: '预估销量 = 最近3个完整自然月的销量合计 ÷ 3；缺失月份按0计算。'
  },
  {
    key: 'forecastGrossProfitAmount', label: '预估毛利', align: 'right', width: 125, format: 'money',
    tip: '预估毛利 = 最近3个完整自然月的毛利合计 ÷ 3；缺失月份按0计算。'
  },
  {
    key: 'forecastReturnQty', label: '预估退货', align: 'right', width: 115, format: 'quantity2',
    tip: '预估退货 = 最近3个完整自然月的退货量合计 ÷ 3；缺失月份按0计算。'
  },
  {
    key: 'forecastReturnAmount', label: '预估退货金额', align: 'right', width: 140, format: 'money',
    tip: '预估退货金额 = 最近3个完整自然月的退货金额合计 ÷ 3；缺失月份按0计算。'
  },
  { key: 'sellThroughRatio', label: '动销比', align: 'right', width: 105, format: 'percentage', tip: '动销比 = 预估销量 ÷ 海外可售 × 100%；海外可售为0时不计算。' },
  { key: 'productLevel', label: '产品等级', align: 'center', width: 125, tip: '利润率和退货率使用最近3个完整自然月的合计口径。按顺序判断：退货率>6%为C；退货率≥3%时利润率<18%为C，否则为B（长尾产品并入B级）；退货率<3%时再按利润率12%/22%和动销比12%/15%划分C、B、A、S。' },
  { key: 'productNature', label: '产品性质', align: 'center', width: 105, tip: '按站点和完整MSKU精确匹配最早刊登时间；距今天数>90天为老品，≤90天为新品，查不到刊登记录时显示--。' },
  { key: 'chengduInTransitQty', label: '成都在途', align: 'right', width: 115, format: 'integer', tip: '原eBay补货库存源：按站点和完整SKU精确匹配，取成都中转仓待接收数' },
  { key: 'chengduSellableQty', label: '成都可售', align: 'right', width: 115, format: 'integer', tip: '原eBay补货库存源：按站点和完整SKU精确匹配，取成都中转仓可售数' },
  { key: 'overseasInTransitQty', label: '海外在途', align: 'right', width: 115, format: 'integer', tip: '原eBay补货库存源：按站点和完整SKU精确匹配，取海外仓在途数' },
  { key: 'overseasSellableQty', label: '海外可售', align: 'right', width: 115, format: 'integer', tip: '原eBay补货库存源：按站点和完整SKU精确匹配，取海外仓可售数' },
  { key: 'chengduWarehouseToWarehouseDays', label: '成都仓到仓时间', align: 'right', width: 165, format: 'days', manualLeadTime: true, tip: '人工填写整数天数；按站点和完整SKU长期保存，回车或鼠标离开后自动保存。' },
  { key: 'chengduQcToWarehouseDays', label: '成都质检出仓时间', align: 'right', width: 175, format: 'days', manualLeadTime: true, tip: '人工填写整数天数；按站点和完整SKU长期保存，回车或鼠标离开后自动保存。' },
  { key: 'overseasTransitToListingDays', label: '海外在途到上架时间', align: 'right', width: 185, format: 'days', manualLeadTime: true, tip: '人工填写整数天数；按站点和完整SKU长期保存，回车或鼠标离开后自动保存。' },
  { key: 'safetyStockQty', label: '安全库存', align: 'right', width: 115, format: 'integer', tip: '安全库存 = 月均日销 ×（总提前天数 × 安全系数）；无时效或分级系数配置时显示--。' },
  { key: 'suggestedReplenishmentQty', label: '建议补货量', align: 'right', width: 130, fixed: 'right', format: 'integer', tip: '建议补货量 = 月均日销 ×（总提前天数 × 补货系数）− 库存合计；负数按0显示。无时效或分级系数配置时显示--。' }
]

const {
  showColumnDrawer,
  columnConfigLoaded,
  columnTableKey,
  visibleKeys,
  visibleColumns,
  openColumnConfig,
  initColumnConfig,
  applyColumnConfig
} = useColumnConfig('operations:ebay:replenishment:v2', columnDefs, fixedColumnKeys)

const queryParams = reactive({
  pageNum: 1,
  pageSize: 50,
  site: undefined,
    sku: undefined,
    productLevel: undefined,
    productNature: undefined,
  sortField: undefined,
  sortOrder: undefined
})

const sortFieldMap = {
  site: 'site',
  sku: 'sku',
  productName: 'productName',
  salesQty: 'salesQty',
  grossProfitAmount: 'grossProfitAmount',
  profitRate: 'profitRate',
  returnQty: 'returnQty',
  returnRate: 'returnRate',
  returnAmount: 'returnAmount'
}

const leadTimeFieldMap = {
  chengduWarehouseToWarehouseDays: 'chengduWarehouseToWarehouseDays',
  // 保留旧前端列key，避免用户已保存的列顺序/显隐配置失效；接口语义使用“质检出仓”。
  chengduQcToWarehouseDays: 'chengduQcOutboundDays',
  overseasTransitToListingDays: 'overseasTransitToListingDays'
}

const monthRangeText = computed(() => {
  if (!months.value.length) return '暂无可用月份'
  return months.value.map(month => formatMonth(month, true)).join('、')
})

async function loadRows() {
  loading.value = true
  try {
    const response = await listEbayReplenishmentV2(buildRequestParams())
    const data = response.data || {}
    months.value = Array.isArray(data.months) ? data.months : []
    latestCompleteMonth.value = data.latest_complete_month || months.value[0] || ''
    siteOptions.value = Array.isArray(data.sites) ? data.sites : []
    rows.value = Array.isArray(data.items) ? data.items.map(normalizeRow) : []
    initializeLeadTimeSavedValues(rows.value)
    total.value = Number(data.pagination?.total || 0)
  } finally {
    loading.value = false
  }
}

function isFormulaColumn(column) {
  return ['safetyStockQty', 'suggestedReplenishmentQty'].includes(column?.key)
}

async function loadFormulaConfigs() {
  if (!canEditFormula) return
  formulaLoading.value = true
  try {
    const response = await getEbayReplenishmentV2Formula()
    setFormulaRows(response?.data)
  } finally {
    formulaLoading.value = false
  }
}

function setFormulaRows(configs) {
  const byLevel = new Map((Array.isArray(configs) ? configs : []).map(item => [
    String(item?.product_level || '').trim().toUpperCase(),
    item
  ]))
  formulaRows.value = formulaLevels.map(productLevel => {
    const item = byLevel.get(productLevel) || {}
    return {
      productLevel,
      safetyCoefficient: numberOrNull(item.safety_coefficient),
      suggestCoefficient: numberOrNull(item.suggest_coefficient)
    }
  })
}

async function openFormulaDialog() {
  if (!canEditFormula) return
  formulaDialogVisible.value = true
  await loadFormulaConfigs()
}

async function submitFormulaConfig() {
  const invalid = formulaRows.value.some(row =>
    !Number.isFinite(Number(row.safetyCoefficient))
    || Number(row.safetyCoefficient) < 0
    || !Number.isFinite(Number(row.suggestCoefficient))
    || Number(row.suggestCoefficient) < 0
  )
  if (invalid) {
    ElMessage.warning('S、A、B、C四个级别的安全系数和补货系数都必须填写非负数')
    return
  }
  formulaSaving.value = true
  try {
    const response = await saveEbayReplenishmentV2Formula({
      configs: formulaRows.value.map(row => ({
        product_level: row.productLevel,
        safety_coefficient: Number(row.safetyCoefficient),
        suggest_coefficient: Number(row.suggestCoefficient)
      }))
    })
    setFormulaRows(response?.data)
    ElMessage.success('全局公式系数已保存，正在重新计算全部SKU')
    formulaDialogVisible.value = false
    await loadRows()
  } finally {
    formulaSaving.value = false
  }
}

function buildRequestParams() {
  return {
    pageNum: queryParams.pageNum,
    pageSize: queryParams.pageSize,
    site: queryParams.site || undefined,
    sku: String(queryParams.sku || '').trim() || undefined,
    productLevel: queryParams.productLevel || undefined,
    productNature: queryParams.productNature || undefined,
    sortField: queryParams.sortField || undefined,
    sortOrder: queryParams.sortOrder === 'ascending'
      ? 'asc'
      : queryParams.sortOrder === 'descending' ? 'desc' : undefined
  }
}

function normalizeRow(item) {
  const monthlyMetrics = (Array.isArray(item.monthly_metrics) ? item.monthly_metrics : [])
    .map(metric => ({
      month: metric.month || metric.stat_month || '',
      salesQty: numberOrNull(metric.sales_qty ?? metric.sales_quantity),
      grossProfitAmount: numberOrNull(metric.gross_profit_amount),
      returnQty: numberOrNull(metric.return_qty ?? metric.return_quantity),
      returnAmount: numberOrNull(metric.return_amount)
    }))
  const latestMetric = monthlyMetrics.find(metric => metric.month === latestCompleteMonth.value) || monthlyMetrics[0] || {}
  return {
    site: item.site ?? item.site_name,
    sku: item.sku ?? item.inventory_sku,
    productName: item.product_name ?? item.product_name_cn,
    salesQty: numberOrNull(item.sales_qty ?? item.sales_quantity ?? latestMetric.salesQty),
    grossProfitAmount: numberOrNull(item.gross_profit_amount ?? latestMetric.grossProfitAmount),
    profitRate: numberOrNull(item.profit_rate),
    returnQty: numberOrNull(item.return_qty ?? item.return_quantity ?? latestMetric.returnQty),
    returnRate: numberOrNull(item.return_rate),
    returnAmount: numberOrNull(item.return_amount ?? latestMetric.returnAmount),
    warehouseRentAmount: numberOrNull(item.warehouse_rent_amount_cny),
    monthlyMetrics,
    forecastSalesQty: numberOrNull(item.forecast_sales_quantity),
    forecastGrossProfitAmount: numberOrNull(item.forecast_gross_profit_amount),
    forecastReturnQty: numberOrNull(item.forecast_return_quantity),
    forecastReturnAmount: numberOrNull(item.forecast_return_amount),
    sellThroughRatio: numberOrNull(item.sell_through_ratio),
    productLevel: item.product_level || null,
    productNature: item.product_nature || null,
    chengduInTransitQty: numberOrNull(item.chengdu_in_transit_quantity),
    chengduSellableQty: numberOrNull(item.chengdu_sellable_quantity),
    overseasInTransitQty: numberOrNull(item.overseas_in_transit_quantity),
    overseasSellableQty: numberOrNull(item.overseas_sellable_quantity),
    chengduWarehouseToWarehouseDays: numberOrNull(item.chengdu_warehouse_to_warehouse_days),
    chengduQcToWarehouseDays: numberOrNull(item.chengdu_qc_outbound_days),
    overseasTransitToListingDays: numberOrNull(item.overseas_transit_to_listing_days),
    safetyStockQty: numberOrNull(item.safety_stock_quantity),
    suggestedReplenishmentQty: numberOrNull(item.suggested_replenishment_quantity)
  }
}

function monthlyRows(row) {
  const source = Array.isArray(row.monthlyMetrics) ? row.monthlyMetrics : []
  if (!months.value.length) return source
  return months.value.map(month => source.find(metric => metric.month === month) || {
    month,
    salesQty: 0,
    grossProfitAmount: 0,
    returnQty: 0,
    returnAmount: 0
  })
}

function handleWarehouseRentFileChange(uploadFile, uploadFiles) {
  const fileName = String(uploadFile?.name || '')
  if (!/\.xlsx$/i.test(fileName)) {
    ElMessage.warning('仓租明细只支持 .xlsx 文件')
    warehouseRentUploadRef.value?.clearFiles()
    warehouseRentFiles.value = []
    return
  }
  warehouseRentFiles.value = uploadFiles.slice(-1)
}

function handleWarehouseRentFileExceed() {
  ElMessage.warning('单次只能选择一个仓租明细文件，请先移除已选文件')
}

async function submitWarehouseRentImport() {
  const file = warehouseRentFiles.value[0]?.raw
  if (!file) {
    ElMessage.warning('请先选择仓租明细 .xlsx 文件')
    return
  }
  if (!file.size) {
    ElMessage.warning('不能上传空文件')
    return
  }
  warehouseRentUploading.value = true
  try {
    const result = await importEbayReplenishmentV2WarehouseRent(file)
    const summary = result?.data || {}
    const summaryParts = []
    if (hasValue(summary.coveredDocumentCount)) {
      summaryParts.push(`覆盖${formatNumber(summary.coveredDocumentCount, 0)}个单号`)
    }
    if (hasValue(summary.sourceRowCount)) {
      summaryParts.push(`读取${formatNumber(summary.sourceRowCount, 0)}条明细`)
    }
    if (hasValue(summary.aggregateRowCount)) {
      summaryParts.push(`汇总${formatNumber(summary.aggregateRowCount, 0)}个站点SKU`)
    }
    const summaryText = summaryParts.length ? `：${summaryParts.join('，')}` : ''
    ElMessage.success(`仓租明细增量导入成功${summaryText}`)
    warehouseRentDialogVisible.value = false
    queryParams.pageNum = 1
    await loadRows()
  } finally {
    warehouseRentUploading.value = false
  }
}

function resetWarehouseRentUpload() {
  warehouseRentUploadRef.value?.clearFiles()
  warehouseRentFiles.value = []
}

function handleQuery() {
  queryParams.pageNum = 1
  loadRows()
}

function resetQuery() {
  queryRef.value?.resetFields()
  queryParams.sortField = undefined
  queryParams.sortOrder = undefined
  queryParams.pageNum = 1
  loadRows()
}

function handleSortChange({ prop, order }) {
  queryParams.sortField = order ? sortFieldMap[prop] : undefined
  queryParams.sortOrder = order || undefined
  queryParams.pageNum = 1
  loadRows()
}

function openPurchaseDialog(row) {
  const suggested = Number(row?.suggestedReplenishmentQty)
  Object.assign(purchaseForm, {
    site: String(row?.site || '').trim(),
    sku: String(row?.sku || '').trim(),
    suggestedQuantity: Number.isFinite(suggested) ? Math.max(0, Math.round(suggested)) : null,
    purchaseQuantity: Number.isFinite(suggested) && suggested > 0 ? Math.max(1, Math.round(suggested)) : null
  })
  purchaseDialogVisible.value = true
}

async function submitPurchase() {
  const valid = await purchaseFormRef.value?.validate().catch(() => false)
  if (!valid) return
  purchaseSubmitting.value = true
  try {
    await submitPendingPurchase({
      site: purchaseForm.site,
      sku: purchaseForm.sku,
      purchaseQuantity: Number(purchaseForm.purchaseQuantity)
    })
    ElMessage.success('已加入待采购清单')
    purchaseDialogVisible.value = false
  } finally {
    purchaseSubmitting.value = false
  }
}

function resetPurchaseForm() {
  purchaseFormRef.value?.resetFields()
  Object.assign(purchaseForm, { site: '', sku: '', suggestedQuantity: null, purchaseQuantity: null })
}

function leadTimeCellKey(row, columnKey) {
  return JSON.stringify([String(row?.site || '').trim(), String(row?.sku || '').trim(), columnKey])
}

function initializeLeadTimeSavedValues(sourceRows) {
  for (const timer of leadTimeSaveTimers.values()) clearTimeout(timer)
  leadTimeSaveTimers.clear()
  leadTimeSavedValues.clear()
  leadTimeEditVersions.clear()
  for (const row of sourceRows) {
    for (const columnKey of Object.keys(leadTimeFieldMap)) {
      leadTimeSavedValues.set(leadTimeCellKey(row, columnKey), row[columnKey] ?? null)
    }
  }
}

function isLeadTimeSaving(row, columnKey) {
  return savingLeadTimeKeys.has(leadTimeCellKey(row, columnKey))
}

function handleLeadTimeEnter(event, row, column) {
  scheduleLeadTimeSave(row, column)
  event?.target?.blur?.()
}

function scheduleLeadTimeSave(row, column) {
  if (!canEditLeadTime) return
  const key = leadTimeCellKey(row, column.key)
  const rawValue = row[column.key]
  const days = rawValue === null || rawValue === undefined || rawValue === '' ? null : Number(rawValue)
  if (days !== null && (!Number.isInteger(days) || days < 0 || days > 3650)) {
    row[column.key] = leadTimeSavedValues.get(key) ?? null
    ElMessage.warning('时效天数只能填写0到3650之间的整数')
    return
  }
  row[column.key] = days
  const version = (leadTimeEditVersions.get(key) || 0) + 1
  leadTimeEditVersions.set(key, version)
  const oldTimer = leadTimeSaveTimers.get(key)
  if (oldTimer) clearTimeout(oldTimer)
  leadTimeSaveTimers.set(key, setTimeout(() => {
    leadTimeSaveTimers.delete(key)
    enqueueLeadTimeSave(row, column, key, days, version)
  }, 120))
}

function enqueueLeadTimeSave(row, column, key, days, version) {
  const previous = leadTimeSaveChains.get(key) || Promise.resolve()
  const current = previous.catch(() => undefined).then(async () => {
    if (leadTimeSavedValues.get(key) === days) return
    savingLeadTimeKeys.add(key)
    try {
      await saveEbayReplenishmentV2LeadTime({
        site: String(row.site || '').trim(),
        sku: String(row.sku || '').trim(),
        field: leadTimeFieldMap[column.key],
        days
      })
      leadTimeSavedValues.set(key, days)
    } catch (error) {
      if (leadTimeEditVersions.get(key) === version) {
        row[column.key] = leadTimeSavedValues.get(key) ?? null
        ElMessage.error(`${column.label}保存失败，已恢复原值`)
      }
      throw error
    } finally {
      savingLeadTimeKeys.delete(key)
    }
  })
  leadTimeSaveChains.set(key, current)
  current.finally(() => {
    if (leadTimeSaveChains.get(key) === current) leadTimeSaveChains.delete(key)
  }).catch(() => undefined)
}

function formatSuggestedQuantity(value) {
  return hasValue(value) ? formatNumber(value, 0) : '暂未计算'
}

async function handleColumnApply(keys) {
  try {
    await applyColumnConfig(keys)
    ElMessage.success('列配置已保存')
  } catch (error) {
    ElMessage.warning('列配置已在当前浏览器生效，服务器保存失败')
  }
}

function columnTip(column) {
  if (!column.monthlyKey || !latestCompleteMonth.value) return column.tip
  return `${column.tip} 当前主值月份：${formatMonth(latestCompleteMonth.value, true)}。`
}

function numberOrNull(value) {
  if (value === null || value === undefined || value === '') return null
  const number = Number(value)
  return Number.isFinite(number) ? number : null
}

function hasValue(value) {
  return value !== null && value !== undefined && value !== ''
}

function formatCell(value, column) {
  if (!hasValue(value)) return '--'
  if (column.format === 'integer') return formatNumber(value, 0)
  if (column.format === 'quantity2') return formatNumber(value, 2)
  if (column.format === 'money') return `¥${formatNumber(value, 2)}`
  if (column.format === 'ratio') return formatNumber(value, 2)
  if (column.format === 'percentage') return `${formatNumber(Number(value) * 100, 2)}%`
  if (column.format === 'days') return `${formatNumber(value, 0)} 天`
  return String(value)
}

function formatMonthlyValue(value, column) {
  if (column.format === 'percentage' && !hasValue(value)) return '--'
  return formatCell(value ?? 0, column)
}

function formatNumber(value, digits) {
  const number = Number(value)
  if (!Number.isFinite(number)) return '--'
  return number.toLocaleString('zh-CN', {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits
  })
}

function formatMonth(value, includeYear) {
  const matched = /^(\d{4})-(\d{2})$/.exec(String(value || ''))
  if (!matched) return '--'
  const month = Number(matched[2])
  return includeYear ? `${matched[1]}年${month}月` : `${month}月`
}

function levelTagType(level) {
  const typeMap = { S: 'success', A: 'primary', B: 'warning', C: 'info' }
  return typeMap[level] || 'info'
}

onMounted(async () => {
  await initColumnConfig()
  await Promise.all([
    loadRows(),
    canEditFormula ? loadFormulaConfigs() : Promise.resolve()
  ])
})

onBeforeUnmount(() => {
  for (const timer of leadTimeSaveTimers.values()) clearTimeout(timer)
  leadTimeSaveTimers.clear()
})
</script>

<style scoped>
.ebay-replenishment-v2-page {
  min-height: calc(100vh - 84px);
  background: #f5f7fa;
}

.query-form {
  padding: 14px 16px 0;
  margin-bottom: 12px;
  border: 1px solid #e4e7ed;
  border-radius: 6px;
  background: #fff;
}

.table-toolbar {
  align-items: center;
}

.field-count {
  color: #909399;
  font-size: 13px;
  line-height: 24px;
  white-space: nowrap;
}

.column-header {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  white-space: nowrap;
}

.column-tip {
  color: #909399;
  cursor: help;
}

.monthly-metric-trigger {
  display: inline-flex;
  align-items: baseline;
  justify-content: flex-end;
  gap: 6px;
  min-width: 78px;
  padding-bottom: 1px;
  border-bottom: 1px dashed #a8abb2;
  cursor: help;
}

.monthly-metric-trigger strong {
  color: #303133;
  font-weight: 600;
}

.monthly-metric-month {
  color: #909399;
  font-size: 11px;
}

.monthly-history__title {
  padding-bottom: 8px;
  margin-bottom: 4px;
  border-bottom: 1px solid #ebeef5;
  color: #303133;
  font-weight: 600;
}

.monthly-history__row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  min-height: 34px;
  color: #606266;
}

.monthly-history__row strong {
  color: #303133;
  font-variant-numeric: tabular-nums;
}

.suggested-qty {
  color: #409eff;
  font-weight: 600;
}

.column-header--formula {
  padding: 1px 4px;
  border-radius: 3px;
  cursor: pointer;
  text-decoration: underline dotted #409eff;
  text-underline-offset: 3px;
  transition: color 0.15s ease, background-color 0.15s ease;
}

.column-header--formula:hover {
  color: #409eff;
  background: #ecf5ff;
}

.formula-alert {
  margin-bottom: 14px;
}

.formula-description {
  padding: 10px 12px;
  margin-bottom: 14px;
  border-radius: 4px;
  color: #606266;
  background: #f5f7fa;
  font-size: 13px;
  line-height: 1.8;
}

.lead-time-cell {
  display: inline-flex;
  align-items: center;
  justify-content: flex-end;
  gap: 5px;
  width: 100%;
}

.lead-time-input {
  width: 92px;
}

.lead-time-unit,
.lead-time-saving {
  color: #909399;
  font-size: 12px;
}

.lead-time-saving {
  color: #409eff;
}

:deep(.lead-time-input .el-input__inner) {
  text-align: right;
}

:deep(.el-table .cell) {
  white-space: nowrap;
}
</style>
