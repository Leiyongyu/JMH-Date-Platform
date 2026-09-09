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
      <el-form-item label="销售类型" prop="salesType">
        <el-select v-model="queryParams.salesType" placeholder="全部类型" clearable
          :disabled="salesTypeAvailable !== true" style="width: 160px">
          <el-option v-for="item in salesTypeOptions" :key="item.value" :label="item.label" :value="item.value" />
        </el-select>
      </el-form-item>
      <el-form-item>
        <el-button type="primary" icon="Search" @click="handleQuery">搜索</el-button>
        <el-button icon="Refresh" @click="resetQuery">重置</el-button>
      </el-form-item>
    </el-form>

    <el-row :gutter="10" class="mb8 table-toolbar">
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

    <el-alert v-if="salesTypeAvailable === false" type="warning" :closable="false" show-icon class="mb8"
      title="销售类型功能尚未部署：请执行09_补货2.0销售类型.sql并更新后端。原有数据计算不受影响。" />

    <el-table
      v-if="columnConfigLoaded"
      ref="tableRef"
      v-loading="loading"
      :key="columnTableKey"
      :data="rows"
      :default-sort="defaultSort"
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
              <button v-if="canEditFormula" type="button" class="formula-header-button"
                @click.stop="openFormulaDialog('productLevel')">{{ col.label }}</button>
              <span v-else>{{ col.label }}</span>
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
              @click="canEditFormula && isFormulaColumn(col) && openFormulaDialog(col.key)"
            >
              <span>{{ col.label }}</span>
              <el-tooltip v-if="col.tip" :content="columnTip(col)" placement="top">
                <el-icon class="column-tip"><QuestionFilled /></el-icon>
              </el-tooltip>
            </span>
          </template>
          <template #default="scope">
            <template v-if="col.key === 'salesType'">
              <el-select v-if="canEditSalesType && salesTypeAvailable"
                :model-value="scope.row.salesType" :disabled="salesTypeSaving.has(rowKey(scope.row))"
                :loading="salesTypeSaving.has(rowKey(scope.row))" size="small" style="width: 95px"
                @change="value => saveSalesType(scope.row, value)">
                <el-option v-for="item in salesTypeOptions" :key="item.value" :label="item.label" :value="item.value" />
              </el-select>
              <el-tag v-else-if="scope.row.salesType" :type="scope.row.salesType === 'BRUSH' ? 'warning' : 'info'">
                {{ salesTypeLabel(scope.row.salesType) }}
              </el-tag>
              <span v-else>--</span>
            </template>
            <div v-else-if="col.manualLeadTime" class="lead-time-cell">
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
              <span v-else-if="isRowRecalculating(scope.row)" class="lead-time-saving">计算中</span>
              <span v-else-if="canEditLeadTime" class="lead-time-unit">天</span>
            </div>
            <span
              v-else-if="col.monthlyKey"
              class="monthly-metric-trigger"
              @mouseenter="showMonthlyPopover($event, scope.row, col)"
              @mouseleave="hideMonthlyPopover"
            >
              <strong>{{ formatCell(scope.row[col.key], col) }}</strong>
              <span class="monthly-metric-month">{{ formatMonth(latestCompleteMonth, false) }}</span>
            </span>
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

    <!--
      月度明细弹窗：全表共用一个实例。
      原先每个带 monthlyKey 的单元格各挂一个 el-popover（4列×50行=200个），
      Element Plus 会提前渲染其内容，占了约 30% 的 DOM 节点，且翻页时全部重建。
      改为虚拟触发后只保留 1 个实例，hover 时切换锚点与数据，行为与原先一致。
    -->
    <el-popover
      :virtual-ref="monthlyPopoverRef"
      virtual-triggering
      :visible="monthlyPopoverVisible"
      placement="top"
      :width="monthlyPopoverKey === 'returnQty' ? 530 : 300"
      :show-after="0"
      :hide-after="0"
      popper-class="replenishment-monthly-popper"
    >
      <div class="monthly-history">
        <div class="monthly-history__title">{{ monthlyPopoverTitle }}</div>
        <template v-if="monthlyPopoverKey === 'returnQty'">
          <table class="quality-return-table">
            <thead><tr><th>月份</th><th>总退货量</th><th>质量问题退货量</th><th>质量问题退货率</th></tr></thead>
            <tbody>
              <tr v-for="metric in monthlyPopoverRows" :key="metric.month">
                <td>{{ formatMonth(metric.month, true) }}</td>
                <td>{{ formatCell(metric.returnQty, { format: 'integer' }) }}</td>
                <td>{{ formatQualityReturn(metric.qualityReturnQty) }}</td>
                <td>{{ formatQualityReturn(metric.qualityReturnRate, true) }}</td>
              </tr>
            </tbody>
            <tfoot><tr>
              <td>近3个月合计</td>
              <td>{{ formatCell(monthlyReturnSummary.returnQty, { format: 'integer' }) }}</td>
              <td>{{ formatQualityReturn(monthlyReturnSummary.qualityReturnQty) }}</td>
              <td>{{ formatQualityReturn(monthlyReturnSummary.qualityReturnRate, true) }}</td>
            </tr></tfoot>
          </table>
          <div class="quality-return-note">
            统计退货明细中人工中间分类为“产品质量问题”的全部退货件数，
            包含“产品质量差”“产品无法使用”等所有下级分类，按付款月份归属。
            退货率 = 质量问题退货量 ÷ 同期销量；合计按3个月数量合计计算，不平均月退货率。
            无质量问题退货或无法计算时显示--。
          </div>
          <div v-if="monthlyReturnSummary.unclassifiedReturnQty > 0" class="quality-return-warning">
            近3个月还有 {{ formatNumber(monthlyReturnSummary.unclassifiedReturnQty, 0) }} 件退货未分类，
            暂未计入质量问题退货；完成售后分类后刷新本页更新。
          </div>
        </template>
        <template v-else>
          <div v-for="metric in monthlyPopoverRows" :key="metric.month" class="monthly-history__row">
            <span>{{ formatMonth(metric.month, true) }}</span>
            <strong>{{ formatMonthlyValue(metric[monthlyPopoverKey], monthlyPopoverColumn) }}</strong>
          </div>
        </template>
      </div>
    </el-popover>


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
        title="修改后影响全部同级别 SKU 的两组安全库存和建议补货量，共用本组系数"
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

    <level-rule-dialog v-if="canEditFormula" v-model="levelRuleDialogVisible" @saved="loadRows" />
    <forecast-rule-dialog
      v-if="canEditFormula"
      v-model="forecastRuleDialogVisible"
      :site-options="siteOptions"
      @saved="loadRows"
    />

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
        title="按仓库、商品编码和账单日增量覆盖"
        description="系统仅读取“仓租明细”Sheet，并按“仓库+商品编码+账单日”增量覆盖：同月分段文件会自动拼接，重叠日期会由后上传文件覆盖；未出现的日期明细继续保留。文件会先完整校验，校验失败不会修改旧数据。"
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
import { onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { QuestionFilled, UploadFilled } from '@element-plus/icons-vue'
import {
  getEbayReplenishmentV2Formula,
  importEbayReplenishmentV2WarehouseRent,
  listEbayReplenishmentV2,
  saveEbayReplenishmentV2Formula,
  saveEbayReplenishmentV2LeadTime,
  saveEbayReplenishmentV2SalesType
} from '@/api/operations/ebay/replenishmentV2'
import { submitPendingPurchase } from '@/api/procurement/pendingPurchase'
import { checkPermi } from '@/utils/permission'
import ColumnConfigDrawer from '@/components/ColumnConfigDrawer/index.vue'
import ForecastRuleDialog from './components/ForecastRuleDialog.vue'
import LevelRuleDialog from './components/LevelRuleDialog.vue'
import { useColumnConfig } from '@/composables/useColumnConfig'

const showSearch = ref(true)
const queryRef = ref(null)
const tableRef = ref(null)
const loading = ref(false)
const rows = ref([])
const total = ref(0)
const siteOptions = ref([])
// 与后端 _product_level 的取值保持一致：D 级已并入 C，长尾产品统一按 B 展示
const productLevelOptions = ['S', 'A', 'B', 'C']
const productNatureOptions = ['新品', '老品']
const salesTypeOptions = [{ value: 'NORMAL', label: '正常' }, { value: 'BRUSH', label: '刷单' }]
const salesTypeAvailable = ref(null)
const salesTypeSaving = reactive(new Set())
const canEditSalesType = checkPermi(['operations:ebayReplenishmentV2:editSalesType'])
const months = ref([])
// 月度明细弹窗的共享状态：全表只有一个 el-popover 实例，
// hover 时把锚点指向当前单元格并换掉内容，避免每格各建一个组件。
const monthlyPopoverRef = ref(null)
const monthlyPopoverVisible = ref(false)
const monthlyPopoverRows = ref([])
const monthlyPopoverTitle = ref('')
const monthlyPopoverKey = ref('')
const monthlyPopoverColumn = ref(null)
const monthlyReturnSummary = ref({})
let monthlyPopoverTimer = null
const latestCompleteMonth = ref('')
const canSubmitPurchase = checkPermi(['procurement:pendingPurchase:add'])
const canEditLeadTime = checkPermi(['operations:ebayReplenishmentV2:editLeadTime'])
const canEditFormula = checkPermi(['operations:ebayReplenishmentV2:formula'])
const leadTimeSavedValues = new Map()
const leadTimeSaveTimers = new Map()
const leadTimeSaveChains = new Map()
const leadTimeEditVersions = new Map()
const savingLeadTimeKeys = reactive(new Set())
// 行级重算：时效改动只影响安全库存和建议补货量，保存成功后按SKU局部重查回填。
// 防抖键用“站点|SKU”而非“站点|SKU|字段”，连填三个格子只会触发一次重算。
const rowRecalcTimers = new Map()
const rowRecalcVersions = new Map()
const recalculatingRowKeys = reactive(new Set())
const purchaseDialogVisible = ref(false)
const purchaseSubmitting = ref(false)
const purchaseFormRef = ref(null)
const warehouseRentDialogVisible = ref(false)
const warehouseRentUploading = ref(false)
const warehouseRentUploadRef = ref(null)
const warehouseRentFiles = ref([])
const formulaDialogVisible = ref(false)
const forecastRuleDialogVisible = ref(false)
const levelRuleDialogVisible = ref(false)
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
    key: 'salesQty7d', label: '近7天销量', align: 'right', width: 105, sortable: true, format: 'integer',
    tip: '截至数据最新日往前7天（含当日）的销量。数据按月上传，最新日通常是上个自然月月末，不随当前日期变化。'
  },
  {
    key: 'salesQty15d', label: '近15天销量', align: 'right', width: 110, sortable: true, format: 'integer',
    tip: '口径同近7天，窗口为往前15天。'
  },
  {
    key: 'salesQty30d', label: '近30天销量', align: 'right', width: 110, sortable: true, format: 'integer',
    tip: '口径同近7天，窗口为往前30天。与“销量”列（上一个完整自然月）高度接近，差异来自月初若干天。'
  },
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
    tip: '主值为最近一个完整自然月的退货量；悬停可查看近3个月总退货量、中间分类为产品质量问题（含所有小类）的退货量及其占同期销量的退货率。无质量问题退货显示--。'
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
    key: 'overseasInventoryAgeDays', label: '海外仓库龄', align: 'right', width: 110, format: 'integer',
    tip: '该SKU在本站点海外仓最老批次的库龄天数，取自谷仓库龄接口最新月快照。同一SKU多批次时取最老的那批（即首次到货至今的天数）。无快照记录时显示--。'
  },
  {
    key: 'forecastSalesQuantity2', label: '预估销量2', align: 'right', width: 125, sortable: true, format: 'quantity2',
    tip: '按13条规则顺序匹配计算；有权限时点击表头可编辑规则并试算。新品按最老批次库龄折算、不封顶；新品缺库龄、性质未知、无规则命中或规则错误时显示--。'
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
  { key: 'sellThroughRatio', label: '动销比', align: 'right', width: 105, format: 'percentage', tip: '动销比 = 预估销量 ÷ 海外可售 × 100%；海外可售为0时仅计算分母按1，库存原值不变；产品等级使用此动销比。' },
  { key: 'productLevel', label: '产品等级', align: 'center', width: 125, tip: '按数据库启用规则顺序取第一条命中。利润率、退货率使用近3个完整自然月汇总口径；数据或配置缺失时显示--。有权限可点击表头编辑全局规则。' },
  { key: 'productNature', label: '产品性质', align: 'center', width: 105, tip: '按站点和完整MSKU精确匹配最早刊登时间；距今天数>90天为老品，≤90天为新品，查不到刊登记录时显示--。' },
  { key: 'salesType', label: '销售类型', align: 'center', width: 125,
    tip: '人工选择正常或刷单，按站点和完整SKU长期保存；未设置按正常。与新品/老品独立，本次不改变任何计算公式。' },
  { key: 'chengduInTransitQty', label: '成都在途', align: 'right', width: 115, format: 'integer', tip: '原eBay补货库存源：按站点和完整SKU精确匹配，取成都中转仓待接收数' },
  { key: 'chengduSellableQty', label: '成都可售', align: 'right', width: 115, format: 'integer', tip: '原eBay补货库存源：按站点和完整SKU精确匹配，取成都中转仓可售数' },
  { key: 'overseasInTransitQty', label: '海外在途', align: 'right', width: 115, format: 'integer', tip: '原eBay补货库存源：按站点和完整SKU精确匹配，取海外仓在途数' },
  { key: 'overseasSellableQty', label: '海外可售', align: 'right', width: 115, format: 'integer', tip: '原eBay补货库存源：按站点和完整SKU精确匹配，取海外仓可售数' },
  { key: 'chengduWarehouseToWarehouseDays', label: '成都仓到仓时间', align: 'right', width: 165, format: 'days', manualLeadTime: true, tip: '人工填写整数天数；按站点和完整SKU长期保存，回车或鼠标离开后自动保存。' },
  { key: 'chengduQcToWarehouseDays', label: '成都质检出仓时间', align: 'right', width: 175, format: 'days', manualLeadTime: true, tip: '人工填写整数天数；按站点和完整SKU长期保存，回车或鼠标离开后自动保存。' },
  { key: 'overseasTransitToListingDays', label: '海外在途到上架时间', align: 'right', width: 185, format: 'days', manualLeadTime: true, tip: '人工填写整数天数；按站点和完整SKU长期保存，回车或鼠标离开后自动保存。' },
  { key: 'safetyStockQty', label: '安全库存', align: 'right', width: 115, format: 'integer', tip: '安全库存 = 月均日销 ×（总提前天数 × 安全系数）；无时效或分级系数配置时显示--。' },
  { key: 'suggestedReplenishmentQty', label: '建议补货量', align: 'right', width: 130, format: 'integer', tip: '建议补货量 = 月均日销 ×（总提前天数 × 补货系数）− 库存合计；负数按0显示。无时效或分级系数配置时显示--。' },
  { key: 'safetyStockQty2', label: '安全库存2', align: 'right', width: 120, format: 'integer', tip: '安全库存2 = 预估销量2 ÷ 30 × 总提前天数 × 安全系数，与安全库存共用S/A/B/C系数；缺依赖显示--。' },
  { key: 'suggestedReplenishmentQty2', label: '建议补货量2', align: 'right', width: 140, fixed: 'right', format: 'integer', tip: '建议补货量2 = 预估销量2 ÷ 30 × 总提前天数 × 补货系数 − 四项库存合计；负数取0，与建议补货量共用系数。' }
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
    salesType: undefined,
  sortField: 'salesQty30d',
  sortOrder: 'descending'
})

const defaultSort = Object.freeze({
  prop: 'salesQty30d',
  order: 'descending'
})

const sortFieldMap = {
  site: 'site',
  sku: 'sku',
  productName: 'productName',
  salesQty: 'salesQty',
  salesQty7d: 'salesQty7d',
  salesQty15d: 'salesQty15d',
  salesQty30d: 'salesQty30d',
  forecastSalesQuantity2: 'forecastSalesQuantity2',
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


async function loadRows() {
  loading.value = true
  try {
    const response = await listEbayReplenishmentV2(buildRequestParams())
    const data = response.data || {}
    salesTypeAvailable.value = data.sales_type_available === true
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
  return [
    'forecastSalesQuantity2', 'productLevel', 'safetyStockQty2', 'suggestedReplenishmentQty2',
    'safetyStockQty',
    'suggestedReplenishmentQty'
  ].includes(column?.key)
}

function salesTypeLabel(value) {
  return salesTypeOptions.find(item => item.value === value)?.label || '--'
}

async function saveSalesType(row, value) {
  if (!canEditSalesType || !salesTypeAvailable.value || value === row.salesType) return
  if (!salesTypeOptions.some(item => item.value === value)) return
  const key = rowKey(row)
  if (salesTypeSaving.has(key)) return
  salesTypeSaving.add(key)
  try {
    await saveEbayReplenishmentV2SalesType({ site: row.site, sku: row.sku, sales_type: value })
    row.salesType = value
    ElMessage.success('销售类型已保存')
    // 改标记可能使当前行移出筛选结果，从第一页重查避免空页。
    if (queryParams.salesType) queryParams.pageNum = 1
    await loadRows()
  } finally {
    salesTypeSaving.delete(key)
  }
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

async function openFormulaDialog(columnKey) {
  if (!canEditFormula) return
  if (columnKey === 'productLevel') {
    levelRuleDialogVisible.value = true
    return
  }
  if (columnKey === 'forecastSalesQuantity2') {
    forecastRuleDialogVisible.value = true
    return
  }
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
    salesType: queryParams.salesType || undefined,
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
      qualityReturnQty: numberOrNull(metric.quality_return_qty),
      qualityReturnRate: numberOrNull(metric.quality_return_rate),
      returnAmount: numberOrNull(metric.return_amount)
    }))
  const latestMetric = monthlyMetrics.find(metric => metric.month === latestCompleteMonth.value) || monthlyMetrics[0] || {}
  return {
    site: item.site ?? item.site_name,
    sku: item.sku ?? item.inventory_sku,
    productName: item.product_name ?? item.product_name_cn,
    salesQty7d: numberOrNull(item.sales_qty_7d),
    salesQty15d: numberOrNull(item.sales_qty_15d),
    salesQty30d: numberOrNull(item.sales_qty_30d),
    salesQty: numberOrNull(item.sales_qty ?? item.sales_quantity ?? latestMetric.salesQty),
    grossProfitAmount: numberOrNull(item.gross_profit_amount ?? latestMetric.grossProfitAmount),
    profitRate: numberOrNull(item.profit_rate),
    returnQty: numberOrNull(item.return_qty ?? item.return_quantity ?? latestMetric.returnQty),
    returnRate: numberOrNull(item.return_rate),
    returnAmount: numberOrNull(item.return_amount ?? latestMetric.returnAmount),
    warehouseRentAmount: numberOrNull(item.warehouse_rent_amount_cny),
    monthlyMetrics,
    qualityReturnSummary: {
      returnQty: numberOrNull(item.quality_return_summary?.return_qty),
      qualityReturnQty: numberOrNull(item.quality_return_summary?.quality_return_qty),
      qualityReturnRate: numberOrNull(item.quality_return_summary?.quality_return_rate),
      unclassifiedReturnQty: numberOrNull(item.quality_return_summary?.unclassified_return_qty)
    },
    forecastSalesQty: numberOrNull(item.forecast_sales_quantity),
    overseasInventoryAgeDays: numberOrNull(item.overseas_inventory_age_days),
    forecastSalesQuantity2: numberOrNull(item.forecast_sales_quantity_2),
    forecastGrossProfitAmount: numberOrNull(item.forecast_gross_profit_amount),
    forecastReturnQty: numberOrNull(item.forecast_return_quantity),
    forecastReturnAmount: numberOrNull(item.forecast_return_amount),
    sellThroughRatio: numberOrNull(item.sell_through_ratio),
    productLevel: item.product_level || null,
    productNature: item.product_nature || null,
    salesType: item.sales_type || null,
    chengduInTransitQty: numberOrNull(item.chengdu_in_transit_quantity),
    chengduSellableQty: numberOrNull(item.chengdu_sellable_quantity),
    overseasInTransitQty: numberOrNull(item.overseas_in_transit_quantity),
    overseasSellableQty: numberOrNull(item.overseas_sellable_quantity),
    chengduWarehouseToWarehouseDays: numberOrNull(item.chengdu_warehouse_to_warehouse_days),
    chengduQcToWarehouseDays: numberOrNull(item.chengdu_qc_outbound_days),
    overseasTransitToListingDays: numberOrNull(item.overseas_transit_to_listing_days),
    safetyStockQty: numberOrNull(item.safety_stock_quantity),
    safetyStockQty2: numberOrNull(item.safety_stock_quantity_2),
    suggestedReplenishmentQty2: numberOrNull(item.suggested_replenishment_quantity_2),
    suggestedReplenishmentQty: numberOrNull(item.suggested_replenishment_quantity)
  }
}

/** 保留原 el-popover 的 180ms 延迟显示，手感与改造前一致。 */
function showMonthlyPopover(event, row, column) {
  clearTimeout(monthlyPopoverTimer)
  const anchor = event.currentTarget
  monthlyPopoverTimer = setTimeout(() => {
    monthlyPopoverRef.value = anchor
    monthlyPopoverRows.value = monthlyRows(row)
    monthlyReturnSummary.value = row.qualityReturnSummary || {}
    monthlyPopoverTitle.value = `${column.label} · 最近3个完整自然月`
    monthlyPopoverKey.value = column.monthlyKey
    monthlyPopoverColumn.value = column
    monthlyPopoverVisible.value = true
  }, 180)
}

function hideMonthlyPopover() {
  clearTimeout(monthlyPopoverTimer)
  monthlyPopoverVisible.value = false
}

function monthlyRows(row) {
  const source = Array.isArray(row.monthlyMetrics) ? row.monthlyMetrics : []
  if (!months.value.length) return source
  return months.value.map(month => source.find(metric => metric.month === month) || {
    month,
    salesQty: 0,
    grossProfitAmount: 0,
    returnQty: 0,
    qualityReturnQty: null,
    qualityReturnRate: null,
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
    const coveredBillingDays = summary.coveredWarehouseProductBillingDayCount
      ?? summary.coveredWarehouseProductCount
    if (hasValue(coveredBillingDays)) {
      summaryParts.push(`覆盖${formatNumber(coveredBillingDays, 0)}个仓库商品账单日组合`)
    }
    if (hasValue(summary.sourceRowCount)) {
      summaryParts.push(`读取${formatNumber(summary.sourceRowCount, 0)}条明细`)
    }
    if (hasValue(summary.aggregateRowCount)) {
      summaryParts.push(`汇总${formatNumber(summary.aggregateRowCount, 0)}个站点SKU`)
    }
    if (summary.exchangeRateSummary) {
      summaryParts.push(`本次使用汇率：${summary.exchangeRateSummary}`)
    }
    const summaryText = summaryParts.length ? `：${summaryParts.join('，')}` : ''
    const successMessage = `仓租明细增量导入成功${summaryText}`
    if (summary.hasExchangeRateFallback) {
      ElMessage.warning(successMessage)
    } else {
      ElMessage.success(successMessage)
    }
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
  queryParams.sortField = 'salesQty30d'
  queryParams.sortOrder = 'descending'
  queryParams.pageNum = 1
  if (tableRef.value) {
    tableRef.value.sort('salesQty30d', 'descending')
  } else {
    loadRows()
  }
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
      scheduleRowRecalc(row)
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

function rowKey(row) {
  return `${String(row.site || '').trim()}|${String(row.sku || '').trim()}`
}

function isRowRecalculating(row) {
  return recalculatingRowKeys.has(rowKey(row))
}

/** 行级防抖：三个时效格子连续填写时合并为一次重算。 */
function scheduleRowRecalc(row) {
  const key = rowKey(row)
  const version = (rowRecalcVersions.get(key) || 0) + 1
  rowRecalcVersions.set(key, version)
  const oldTimer = rowRecalcTimers.get(key)
  if (oldTimer) clearTimeout(oldTimer)
  rowRecalcTimers.set(key, setTimeout(() => {
    rowRecalcTimers.delete(key)
    recalcRow(row, key, version)
  }, 500))
}

/**
 * 重新计算单行的安全库存与建议补货量。
 * 公式在后端，前端不复刻，避免两个真相源。
 */
async function recalcRow(row, key, version) {
  // 三个时效格子各有独立保存链，必须全部落库后再查，避免读到半新半旧的值。
  const chains = Object.keys(leadTimeFieldMap)
    .map(columnKey => leadTimeSaveChains.get(leadTimeCellKey(row, columnKey)))
    .filter(Boolean)
  if (chains.length) {
    await Promise.allSettled(chains)
  }
  if (rowRecalcVersions.get(key) !== version) return

  recalculatingRowKeys.add(key)
  try {
    const response = await listEbayReplenishmentV2({
      pageNum: 1,
      pageSize: 1,
      site: String(row.site || '').trim(),
      sku: String(row.sku || '').trim()
    })
    // 慢响应不得覆盖期间产生的新输入。
    if (rowRecalcVersions.get(key) !== version) return
    const fresh = (response?.data?.items || [])[0]
    if (!fresh) return
    // 只回填受时效影响的四个派生字段，避免冲掉用户正在编辑的时效输入。
    row.safetyStockQty = numberOrNull(fresh.safety_stock_quantity)
    row.safetyStockQty2 = numberOrNull(fresh.safety_stock_quantity_2)
    row.suggestedReplenishmentQty2 = numberOrNull(fresh.suggested_replenishment_quantity_2)
    row.suggestedReplenishmentQty = numberOrNull(fresh.suggested_replenishment_quantity)
  } catch (error) {
    // 时效已经保存成功；展示重算失败时保持原值，用户刷新页面即可恢复。
  } finally {
    if (rowRecalcVersions.get(key) === version) recalculatingRowKeys.delete(key)
  }
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

function formatQualityReturn(value, percentage = false) {
  const number = numberOrNull(value)
  if (number === null || number <= 0) return '--'
  return percentage ? `${formatNumber(number * 100, 2)}%` : formatNumber(number, 0)
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
  clearTimeout(monthlyPopoverTimer)
  for (const timer of leadTimeSaveTimers.values()) clearTimeout(timer)
  leadTimeSaveTimers.clear()
  for (const timer of rowRecalcTimers.values()) clearTimeout(timer)
  rowRecalcTimers.clear()
})
</script>

<style scoped>
.formula-header-button { border: 0; padding: 0; background: transparent; font: inherit; color: inherit; cursor: pointer; }
.formula-header-button:hover { color: var(--el-color-primary); }
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

.quality-return-table {
  width: 100%;
  border-collapse: collapse;
  font-variant-numeric: tabular-nums;
}
.quality-return-table th,
.quality-return-table td {
  padding: 8px 4px;
  border-bottom: 1px solid #ebeef5;
  text-align: right;
  white-space: nowrap;
}
.quality-return-table th:first-child,
.quality-return-table td:first-child { text-align: left; }
.quality-return-table tfoot { font-weight: 600; }
.quality-return-note { margin-top: 8px; color: #909399; font-size: 12px; line-height: 1.6; }
.quality-return-warning { margin-top: 6px; color: #b88230; font-size: 12px; line-height: 1.6; }

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
