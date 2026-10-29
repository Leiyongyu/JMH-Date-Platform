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
      <el-form-item label="负责人" prop="principalName">
        <el-select v-model="queryParams.principalName" placeholder="全部负责人" clearable filterable
          :disabled="loading" style="width: 160px" @change="handleQuery">
          <el-option v-for="principal in principalOptions" :key="principal" :label="principal" :value="principal" />
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
        <el-tooltip content="括号内为建议补货量 / 建议补货量2合计，单位：件；统计其他筛选条件下的全部记录，无法计算的值不计入合计。" placement="top">
          <el-select
            v-model="queryParams.productLevel"
            placeholder="全部等级"
            clearable
            :disabled="loading"
            style="width: 160px"
            @change="handleQuery"
          >
            <el-option
              v-for="level in productLevelOptions"
              :key="level"
              :label="levelOptionLabel(level)"
              :value="level"
            />
          </el-select>
        </el-tooltip>
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
      <el-form-item label="运营确认" prop="operationsConfirmed">
        <el-select v-model="queryParams.operationsConfirmed" placeholder="全部状态" clearable :disabled="reviewAvailable !== true" style="width: 160px">
          <el-option label="已确认" :value="true" />
          <el-option label="待确认" :value="false" />
        </el-select>
      </el-form-item>
      <el-form-item>
        <el-button type="primary" icon="Search" @click="handleQuery">搜索</el-button>
        <el-button icon="Refresh" @click="resetQuery">重置</el-button>
      </el-form-item>
    </el-form>

    <el-row :gutter="10" class="mb8 table-toolbar">
      <el-col :span="1.5">
        <el-tooltip content="导出当前筛选下全部记录，仅包含角色授权的导出字段；不受分页或页面隐藏列限制，页面可见字段不受影响" placement="top">
          <el-button
            type="warning"
            plain
            icon="Download"
            :loading="exporting"
            :disabled="loading || savingLeadTimeKeys.size > 0 || salesTypeSaving.size > 0 || recalculatingRowKeys.size > 0"
            v-hasPermi="['operations:ebayReplenishmentV2:export']"
            @click="handleExport"
          >导出全部数据</el-button>
        </el-tooltip>
      </el-col>
      <el-col :span="1.5" class="data-source-note">
        站点 → 品牌＋中间码 → SKU；末尾-YXR/-RXY并入原SKU
      </el-col>
      <right-toolbar
        v-model:showSearch="showSearch"
        :show-column-config="true"
        :refresh-loading="loading"
        refresh-tooltip="重新读取源数据并计算全部补货指标"
        @queryTable="refreshRows"
        @columnConfig="openColumnConfig"
      />
    </el-row>

    <el-alert v-if="salesTypeAvailable === false" type="warning" :closable="false" show-icon class="mb8"
      title="销售类型功能尚未部署：请执行09_补货2.0销售类型.sql并更新后端。原有数据计算不受影响。" />
    <el-alert v-if="reviewAvailable === false" type="warning" :closable="false" show-icon class="mb8"
      title="运营/开发备注尚未部署，请执行20261015_ebay_replenishment_v2_review.sql。" />

    <el-table
      v-if="columnConfigLoaded"
      ref="tableRef"
      v-loading="loading"
      :key="`${columnTableKey}:${treeRevision}`"
      :data="rows"
      :default-sort="defaultSort"
      border
      stripe
      height="640"
      row-key="nodeId"
      lazy
      :load="loadChildren"
      :tree-props="{ children: 'children', hasChildren: 'hasChildren' }"
      empty-text="暂无符合条件的订单数据"
      @sort-change="handleSortChange"
      @expand-change="rememberExpansion"
    >
      <el-table-column label="站点 / 品牌＋中间码 / SKU" width="310" fixed="left" show-overflow-tooltip>
        <template #default="{ row }">
          <el-button v-if="row.nodeKind === 'more'" link type="primary"
            :loading="loadingNodes.has(row.parent.nodeId)" @click="loadMoreChildren(row)">{{ row.nodeLabel }}</el-button>
          <template v-else>
            <span :title="row.summaryHint">{{ row.nodeLabel }}</span>
            <span v-if="!isSkuRow(row)" class="hierarchy-count">（{{ row.skuCount }}个SKU）</span>
          </template>
        </template>
      </el-table-column>
      <template v-for="col in hierarchyColumns" :key="col.key">
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
            <span v-if="scope.row.nodeKind === 'more'"></span>
            <el-tag v-else-if="scope.row.productLevel" :type="levelTagType(scope.row.productLevel)" effect="light">
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
            <span v-if="scope.row.nodeKind === 'more'"></span>
            <span v-else-if="col.reviewField && !isSkuRow(scope.row)">--</span>
            <div v-else-if="col.reviewField" class="review-cell">
              <review-note-cell :site="scope.row.site" :sku="scope.row.sku" :field="col.reviewField"
                :value="scope.row[col.key]" :version="scope.row[`${col.reviewField}Version`]"
                :disabled="!reviewAvailable || confirmingRows.has(rowKey(scope.row))"
                @busy="value => setNoteBusy(scope.row, col.reviewField, value)"
                @saved="data => applyReview(scope.row, data)" />
              <template v-if="col.reviewField === 'operations'">
                <el-tag v-if="scope.row.operationsConfirmed" type="success" size="small"
                  :title="`${scope.row.operationsConfirmedBy || ''} ${scope.row.operationsConfirmedAt || ''}`">已确认</el-tag>
                <el-button v-else link type="primary" size="small" :loading="confirmingRows.has(rowKey(scope.row))"
                  :disabled="!reviewAvailable || isNoteBusy(scope.row)" @click="confirmOperations(scope.row)">确认</el-button>
              </template>
            </div>
            <template v-else-if="col.key === 'salesType'">
              <el-select v-if="isSkuRow(scope.row) && canEditSalesType && salesTypeAvailable"
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
                v-if="isSkuRow(scope.row) && canEditLeadTime"
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
              <span v-else-if="isSkuRow(scope.row) && canEditLeadTime" class="lead-time-unit">天</span>
            </div>
            <span
              v-else-if="col.monthlyKey"
              class="monthly-metric-trigger"
              @mouseenter="showMonthlyPopover($event, scope.row, col)"
              @mouseleave="hideMonthlyPopover"
            >
              <strong>{{ formatCell(scope.row[col.key], col) }}</strong>
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
            v-if="isSkuRow(row)"
            link
            type="primary"
            v-hasPermi="['operations:ebayReplenishmentV2:purchase']"
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
            <thead><tr><th>日期区间</th><th>总退货量</th><th>质量问题退货量</th><th>质量问题退货率</th></tr></thead>
            <tbody>
              <tr v-for="metric in monthlyPopoverRows" :key="metric.month">
                <td>{{ formatMonth(metric.month, true) }}</td>
                <td>{{ formatCell(metric.returnQty, { format: 'integer' }) }}</td>
                <td>{{ formatQualityReturn(metric.qualityReturnQty) }}</td>
                <td>{{ formatQualityReturn(metric.qualityReturnRate, true) }}</td>
              </tr>
            </tbody>
            <tfoot><tr>
              <td>近90天合计</td>
              <td>{{ formatCell(monthlyReturnSummary.returnQty, { format: 'integer' }) }}</td>
              <td>{{ formatQualityReturn(monthlyReturnSummary.qualityReturnQty) }}</td>
              <td>{{ formatQualityReturn(monthlyReturnSummary.qualityReturnRate, true) }}</td>
            </tr></tfoot>
          </table>
          <div class="quality-return-note">
            统计退货明细中人工中间分类为“产品质量问题”的全部退货件数，
            包含“产品质量差”“产品无法使用”等所有下级分类，按付款日期归属。
            退货率 = 质量问题退货量 ÷ 同期销量；合计按90天数量合计计算，不平均各段退货率。
            无质量问题退货或无法计算时显示--。
          </div>
          <div v-if="monthlyReturnSummary.unclassifiedReturnQty > 0" class="quality-return-warning">
            近90天还有 {{ formatNumber(monthlyReturnSummary.unclassifiedReturnQty, 0) }} 件退货未分类，
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


    <div class="hierarchy-footer">共 {{ total }} 个SKU；展开行内可继续加载。汇总仅包含当前筛选结果，导出为SKU明细。</div>

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

    <level-rule-dialog v-if="canEditFormula" v-model="levelRuleDialogVisible" @saved="refreshRows" />
    <forecast-rule-dialog
      v-if="canEditFormula"
      v-model="forecastRuleDialogVisible"
      :site-options="siteOptions"
      @saved="refreshRows"
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

  </div>
</template>

<script setup name="EbayReplenishmentV2">
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { QuestionFilled } from '@element-plus/icons-vue'
import {
  exportEbayReplenishmentV2,
  submitEbayReplenishmentV2Purchase,
  confirmEbayReplenishmentReview,
  getEbayReplenishmentV2Formula,
  listEbayReplenishmentV2,
  listEbayReplenishmentHierarchy,
  saveEbayReplenishmentV2Formula,
  saveEbayReplenishmentV2LeadTime,
  saveEbayReplenishmentV2SalesType
} from '@/api/operations/ebay/replenishmentV2'
import { checkPermi } from '@/utils/permission'
import ColumnConfigDrawer from '@/components/ColumnConfigDrawer/index.vue'
import ForecastRuleDialog from './components/ForecastRuleDialog.vue'
import LevelRuleDialog from './components/LevelRuleDialog.vue'
import ReviewNoteCell from './components/ReviewNoteCell.vue'
import { childQuery, withMoreRow, isSkuRow } from './hierarchy'
import { useColumnConfig } from '@/composables/useColumnConfig'

const showSearch = ref(true)
const queryRef = ref(null)
const tableRef = ref(null)
const loading = ref(false)
const exporting = ref(false)
const rows = ref([])
const treeRevision = ref(0)
const childrenByNode = new Map()
const restoredChildren = new Map()
const expandedNodes = new Set()
const loadingNodes = reactive(new Set())
const failedNodes = reactive(new Set())
const appliedFilters = ref({})
let treeReloadTimer = null
let disposed = false
const total = ref(0)
const siteOptions = ref([])
const principalOptions = ref([])
// 与后端 _product_level 的取值保持一致：D 级已并入 C，长尾产品统一按 B 展示
const productLevelOptions = ['', 'S', 'A', 'B', 'C', '--']
const levelSummary = ref({})
const ownerRuleMonth = ref('')
const calculationVersion = ref('')
function levelQuantity(level, field) {
  const value = levelSummary.value[level || 'ALL']?.[field]
  return value == null ? '--' : formatNumber(value, 0)
}
function levelOptionLabel(level) {
  return `${level || '全部'}（${levelQuantity(level, 'suggested_replenishment_quantity')} / ${levelQuantity(level, 'suggested_replenishment_quantity_2')}）`
}
const productNatureOptions = ['新品', '老品']
const salesTypeOptions = [{ value: 'NORMAL', label: '正常' }, { value: 'BRUSH', label: '刷单' }]
const salesTypeAvailable = ref(null)
const reviewAvailable = ref(null)
const noteBusy = reactive(new Set())
const confirmingRows = reactive(new Set())
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
const canSubmitPurchase = checkPermi(['operations:ebayReplenishmentV2:purchase'])
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
    tip: '以北京时间当天为基准，统计此前7天销量，不含今天；源订单未更新的日期不会自动补销量。'
  },
  {
    key: 'salesQty15d', label: '近15天销量', align: 'right', width: 110, sortable: true, format: 'integer',
    tip: '口径同近7天，窗口为往前15天。'
  },
  {
    key: 'salesQty30d', label: '近30天销量', align: 'right', width: 110, sortable: true, format: 'integer',
    tip: '以北京时间当天为基准，统计此前30天销量，不含今天；与“销量”列口径一致。'
  },
  {
    key: 'salesQty', label: '销量', align: 'right', width: 130, sortable: true, format: 'integer', monthlyKey: 'salesQty',
    tip: '主值为近30天的销量；鼠标悬停可查看最近90天（每30天一段）。'
  },
  {
    key: 'grossProfitAmount', label: '毛利', align: 'right', width: 145, sortable: true, format: 'money', monthlyKey: 'grossProfitAmount',
    tip: '毛利取订单数据中的“订单利润(￥)”；主值为近30天，鼠标悬停可查看近90天。'
  },
  {
    key: 'profitRate', label: '利润率', align: 'right', width: 110, sortable: true, format: 'percentage',
    tip: '最近90天（每30天一段）利润率 = 90天订单利润(￥)合计 ÷ 90天净支付金额合计 × 100%；不按单月拆分或平均月度百分比。'
  },
  {
    key: 'returnQty', label: '退货量', align: 'right', width: 130, sortable: true, format: 'integer', monthlyKey: 'returnQty',
    tip: '主值为近30天的退货量；悬停可查看近90天总退货量、中间分类为产品质量问题（含所有小类）的退货量及其占同期销量的退货率。无质量问题退货显示--。'
  },
  {
    key: 'returnRate', label: '退货率', align: 'right', width: 110, sortable: true, format: 'percentage',
    tip: '最近90天（每30天一段）退货率 = 90天退货量合计 ÷ 90天销量合计 × 100%；使用清洗订单中的退货数量；当前导入已排除已作废订单。'
  },
  {
    key: 'returnAmount', label: '退货金额', align: 'right', width: 150, sortable: true, format: 'money', monthlyKey: 'returnAmount',
    tip: '退货金额为人民币；主值为近30天，鼠标悬停可查看近90天。'
  },
  {
    key: 'warehouseRentAmount', label: '仓租费用', align: 'right', width: 135, format: 'money',
    tip: '与库存明细共用谷仓近30天仓租快照，按站点及去首段前缀的SKU匹配，使用拉取月份汇率折人民币。'
  },
  {
    key: 'forecastSalesQty', label: '预估销量', align: 'right', width: 115, format: 'quantity2',
    tip: '预估销量 = 最近90天（每30天一段）的销量合计 ÷ 3；缺失区间按0计算。'
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
    tip: '预估毛利 = 最近90天（每30天一段）的毛利合计 ÷ 3；缺失区间按0计算。'
  },
  {
    key: 'forecastReturnQty', label: '预估退货', align: 'right', width: 115, format: 'quantity2',
    tip: '预估退货 = 最近90天（每30天一段）的退货量合计 ÷ 3；缺失区间按0计算。'
  },
  {
    key: 'forecastReturnAmount', label: '预估退货金额', align: 'right', width: 140, format: 'money',
    tip: '预估退货金额 = 最近90天（每30天一段）的退货金额合计 ÷ 3；缺失区间按0计算。'
  },
  { key: 'sellThroughRatio', label: '动销比', align: 'right', width: 105, format: 'percentage', tip: '动销比 = 预估销量 ÷ 海外可售 × 100%；海外可售为0时仅计算分母按1，库存原值不变；产品等级使用此动销比。' },
  { key: 'productLevel', label: '产品等级', align: 'center', width: 125, tip: '按数据库启用规则顺序取第一条命中。利润率、退货率使用近90天汇总口径；数据或配置缺失时显示--。有权限可点击表头编辑全局规则。' },
  { key: 'productNature', label: '产品性质', align: 'center', width: 105, tip: '按站点和完整MSKU精确匹配最早刊登时间；距今天数>90天为老品，≤90天为新品，查不到刊登记录时显示--。' },
  { key: 'salesType', label: '销售类型', align: 'center', width: 125,
    tip: '人工选择正常或刷单，按站点和完整SKU长期保存；未设置按正常。与新品/老品独立，本次不改变任何计算公式。' },
  { key: 'chengduInTransitQty', label: '成都在途', align: 'right', width: 115, format: 'integer', tip: '原eBay补货库存源：按站点和完整SKU精确匹配，取成都中转仓待接收数' },
  { key: 'chengduSellableQty', label: '成都可售', align: 'right', width: 115, format: 'integer', tip: '原eBay补货库存源：按站点和完整SKU精确匹配，取成都中转仓可售数' },
  { key: 'overseasInTransitQty', label: '海外在途', align: 'right', width: 115, format: 'integer', tip: '原eBay补货库存源：按站点和完整SKU精确匹配，取海外仓在途数' },
  { key: 'overseasSellableQty', label: '海外可售', align: 'right', width: 115, format: 'integer', tip: '原eBay补货库存源：按站点和完整SKU精确匹配，取海外仓可售数' },
  { key: 'chengduWarehouseToWarehouseDays', label: '成都仓到仓时间', align: 'right', width: 165, format: 'days', manualLeadTime: true, tip: '人工填写整数天数；按站点和完整SKU长期保存，回车或鼠标离开后自动保存。' },
  { key: 'chengduQcToWarehouseDays', label: '成都质检出仓时间', align: 'right', width: 175, format: 'days', manualLeadTime: true, tip: '人工填写整数天数；按站点和完整SKU长期保存，回车或鼠标离开后自动保存。' },
  { key: 'overseasTransitToListingDays', label: '海外在途到上架时间', align: 'right', width: 185, format: 'days', manualLeadTime: true, tip: '未手动设置时默认德国67天、英国72天、美国60天。可按站点和完整SKU编辑，回车或鼠标离开后自动保存；手动值（包括0）优先，清空恢复站点默认值。' },
  { key: 'safetyStockQty', label: '安全库存', align: 'right', width: 115, sortable: true, format: 'integer', tip: '安全库存 = 月均日销 ×（总提前天数 × 安全系数）；无时效或分级系数配置时显示--。' },
  { key: 'suggestedReplenishmentQty', label: '建议补货量', align: 'right', width: 130, sortable: true, format: 'integer', tip: '建议补货量 = 月均日销 ×（总提前天数 × 补货系数）− 库存合计；负数按0显示。无时效或分级系数配置时显示--。' },
  { key: 'safetyStockQty2', label: '安全库存2', align: 'right', width: 120, sortable: true, format: 'integer', tip: '安全库存2 = 预估销量2 ÷ 30 × 总提前天数 × 安全系数，与安全库存共用S/A/B/C系数；缺依赖显示--。' },
  { key: 'suggestedReplenishmentQty2', label: '建议补货量2', align: 'right', width: 140, sortable: true, format: 'integer', tip: '建议补货量2 = 预估销量2 ÷ 30 × 总提前天数 × 补货系数 − 四项库存合计；负数取0，与建议补货量共用系数。' },
  { key: 'operationsNote', label: '运营', align: 'left', width: 180, reviewField: 'operations' },
  { key: 'developmentNote', label: '开发', align: 'left', width: 125, reviewField: 'development' },
  { key: 'principalName', label: '负责人', align: 'center', width: 115, tooltip: true,
    tip: '按北京时间当月的绩效排名eBay品牌负责人规则匹配SKU前缀，跨站点同品牌同负责人；不回退其他月份。FLL/LEJ、CL沿用绩效排名固定归属，缺规则显示未分配。' }
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
} = useColumnConfig('operations:ebay:replenishment:v2', columnDefs, fixedColumnKeys, fixedColumnKeys, {}, { operationsNote: '__append__', developmentNote: '__append__', principalName: '__append__' })

const hierarchyColumns = computed(() => visibleColumns.value.filter(col => !['site', 'sku'].includes(col.key)))

const queryParams = reactive({
  pageNum: 1,
  pageSize: 50,
  site: undefined,
  principalName: undefined,
    sku: undefined,
    productLevel: '',
    productNature: undefined,
    salesType: undefined,
    operationsConfirmed: undefined,
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
  safetyStockQty: 'safetyStockQty',
  suggestedReplenishmentQty: 'suggestedReplenishmentQty',
  safetyStockQty2: 'safetyStockQty2',
  suggestedReplenishmentQty2: 'suggestedReplenishmentQty2',
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


let rowsRequest = 0
async function loadRows(forceRefresh = false, restoreExpanded = false) {
  if (noteBusy.size || confirmingRows.size || savingLeadTimeKeys.size ||
      leadTimeSaveTimers.size || rowRecalcTimers.size || recalculatingRowKeys.size) {
    ElMessage.warning('请先完成当前编辑保存和计算')
    return
  }
  const request = ++rowsRequest
  const params = buildRequestParams()
  const expanded = restoreExpanded ? new Set(expandedNodes) : new Set()
  loading.value = true
  try {
    const response = await listEbayReplenishmentHierarchy({ ...params,
      hierarchyLevel: 'site', pageNum: 1, pageSize: 200, refresh: forceRefresh === true })
    const data = response.data || {}
    if (request !== rowsRequest || noteBusy.size || confirmingRows.size) return
    salesTypeAvailable.value = data.sales_type_available === true
    reviewAvailable.value = data.review_available === true
    months.value = Array.isArray(data.months) ? data.months : []
    latestCompleteMonth.value = data.latest_complete_month || months.value[0] || ''
    siteOptions.value = Array.isArray(data.sites) ? data.sites : []
    principalOptions.value = Array.isArray(data.principals) ? data.principals : []
    levelSummary.value = data.level_summary || {}
    ownerRuleMonth.value = data.owner_rule_month || ''
    calculationVersion.value = data.calculation_version || ''
    appliedFilters.value = params
    childrenByNode.clear()
    restoredChildren.clear()
    expandedNodes.clear()
    loadingNodes.clear()
    failedNodes.clear()
    treeRevision.value += 1
    rows.value = Array.isArray(data.items) ? data.items.map(normalizeRow) : []
    initializeLeadTimeSavedValues(rows.value)
    total.value = Number(data.matched_sku_count || 0)
    if (expanded.size) {
      await nextTick()
      await restoreExpansion(rows.value, expanded, request)
    }
  } finally {
    if (request === rowsRequest) loading.value = false
  }
}

function refreshRows() {
  return loadRows(true)
}

function rememberExpansion(row, expanded) {
  if (expanded) expandedNodes.add(row.nodeId)
  else expandedNodes.delete(row.nodeId)
}

async function restoreExpansion(nodes, expanded, request) {
  for (const row of nodes) {
    if (request !== rowsRequest) return
    if (!expanded.has(row.nodeId) || !row.hasChildren) continue
    const children = await fetchChildren(row)
    if (!children || request !== rowsRequest) continue
    // Element Plus updateKeyChildren only updates already loaded branches.
    // Feed restored children through its initial lazy-load callback instead.
    restoredChildren.set(row.nodeId, children)
    tableRef.value?.toggleRowExpansion(row, true)
    expandedNodes.add(row.nodeId)
    await nextTick()
    await restoreExpansion(children, expanded, request)
  }
}

async function fetchChildren(parent, page = 1) {
  const request = rowsRequest
  const version = calculationVersion.value
  if (!version) {
    failedNodes.add(parent.nodeId)
    ElMessage.info('数据正在重新计算，请稍后刷新再展开')
    return null
  }
  loadingNodes.add(parent.nodeId)
  try {
    const response = await listEbayReplenishmentHierarchy(childQuery(parent, appliedFilters.value, version, page))
    if (request !== rowsRequest || version !== calculationVersion.value) return null
    const data = response.data || {}
    const fresh = (data.items || []).map(normalizeRow)
    initializeLeadTimeSavedValues(fresh, false)
    const previous = page === 1 ? [] : childrenByNode.get(parent.nodeId) || []
    const children = [...previous, ...fresh]
    childrenByNode.set(parent.nodeId, children)
    failedNodes.delete(parent.nodeId)
    return withMoreRow(parent, children, Number(data.pagination?.total || 0), page + 1)
  } catch (error) {
    if (request === rowsRequest) failedNodes.add(parent.nodeId)
    return null
  } finally {
    if (request === rowsRequest) loadingNodes.delete(parent.nodeId)
  }
}

async function loadChildren(row, _treeNode, resolve) {
  if (restoredChildren.has(row.nodeId)) {
    const children = restoredChildren.get(row.nodeId)
    restoredChildren.delete(row.nodeId)
    resolve(children)
    return
  }
  const children = await fetchChildren(row)
  // An empty failure callback marks the branch permanently loaded without a
  // lazy child map. A retry row keeps updateKeyChildren usable after failure.
  resolve(children || [{nodeId: `${row.nodeId}:retry`, nodeKind: 'more', parent: row,
    nodeLabel: '加载失败，点击重试', nextPage: 1, hasChildren: false}])
}

async function loadMoreChildren(row) {
  if (loadingNodes.has(row.parent.nodeId)) return
  const children = await fetchChildren(row.parent, row.nextPage)
  if (children) tableRef.value?.updateKeyChildren(row.parent.nodeId, children)
}

function scheduleTreeReload() {
  if (disposed) return
  clearTimeout(treeReloadTimer)
  treeReloadTimer = setTimeout(() => {
    if (noteBusy.size || confirmingRows.size || savingLeadTimeKeys.size ||
        recalculatingRowKeys.size || leadTimeSaveTimers.size || rowRecalcTimers.size) {
      scheduleTreeReload()
      return
    }
    loadRows(false, true).catch(() => {})
  }, 500)
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
    await refreshRows()
  } finally {
    formulaSaving.value = false
  }
}

function buildRequestParams() {
  return {
    pageNum: queryParams.pageNum,
    pageSize: queryParams.pageSize,
    site: queryParams.site || undefined,
    principalName: queryParams.principalName || undefined,
    sku: String(queryParams.sku || '').trim() || undefined,
    productLevel: queryParams.productLevel || undefined,
    productNature: queryParams.productNature || undefined,
    salesType: queryParams.salesType || undefined,
    operationsConfirmed: typeof queryParams.operationsConfirmed === 'boolean' ? queryParams.operationsConfirmed : undefined,
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
    nodeId: item.node_id,
    nodeKind: item.node_kind || 'sku',
    nodeLabel: item.node_label || item.sku,
    brandCore: item.brand_core,
    hasChildren: item.has_children === true,
    skuCount: Number(item.sku_count || 1),
    summaryHint: Object.keys(item.partial_fields || {}).length
      ? '部分SKU的指标尚未计算；对应汇总仅合计有值的SKU，展开可核对。' : '',
    site: item.site ?? item.site_name,
    sku: item.sku ?? item.inventory_sku,
    productName: item.product_name ?? item.product_name_cn,
    principalName: item.principal_name || (item.node_kind && item.node_kind !== 'sku' ? '--' : '未分配'),
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
    suggestedReplenishmentQty: numberOrNull(item.suggested_replenishment_quantity),
    operationsNote: item.operations_note || '',
    developmentNote: item.development_note || '',
    operationsVersion: Number(item.operations_version || 0),
    developmentVersion: Number(item.development_version || 0),
    operationsConfirmed: Boolean(item.operations_confirmed),
    operationsConfirmedBy: item.operations_confirmed_by || '',
    operationsConfirmedAt: item.operations_confirmed_at || ''
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
    monthlyPopoverTitle.value = `${column.label} · 最近90天（每30天一段）`
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
  if (!canSubmitPurchase) return
  if (isNoteBusy(row)) return ElMessage.warning('请先完成备注保存')
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
  if (!canSubmitPurchase) return
  const valid = await purchaseFormRef.value?.validate().catch(() => false)
  if (!valid) return
  purchaseSubmitting.value = true
  try {
    await submitEbayReplenishmentV2Purchase({
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

function initializeLeadTimeSavedValues(sourceRows, reset = true) {
  if (reset) {
    for (const timer of leadTimeSaveTimers.values()) clearTimeout(timer)
    leadTimeSaveTimers.clear()
    leadTimeSavedValues.clear()
    leadTimeEditVersions.clear()
  }
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
      const response = await saveEbayReplenishmentV2LeadTime({
        site: String(row.site || '').trim(),
        sku: String(row.sku || '').trim(),
        field: leadTimeFieldMap[column.key],
        days
      })
      const savedDays = response?.data && Object.hasOwn(response.data, 'days')
        ? numberOrNull(response.data.days) : days
      leadTimeSavedValues.set(key, savedDays)
      if (leadTimeEditVersions.get(key) === version) row[column.key] = savedDays
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
  calculationVersion.value = ''
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
  const tableVersion = rowsRequest
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
      sku: String(row.sku || '').trim(),
      exactSku: true,
      refresh: true
    })
    // 慢响应不得覆盖期间产生的新输入。
    if (rowRecalcVersions.get(key) !== version || tableVersion !== rowsRequest) return
    const fresh = (response?.data?.items || [])[0]
    if (!fresh) return
    // A row refresh creates a new generation. Reload the full filtered view
    // before exporting, rather than pinning a mixed old/new page to that version.
    calculationVersion.value = ''
    // The server already calculated the new row values. Keep full-filter totals in sync
    // without substituting this single-SKU response's summary for the whole table.
    const level = row.productLevel || '--'
    for (const [column, field] of [['suggestedReplenishmentQty', 'suggested_replenishment_quantity'],
      ['suggestedReplenishmentQty2', 'suggested_replenishment_quantity_2']]) {
      const delta = Number(fresh[field] ?? 0) - Number(row[column] ?? 0)
      for (const bucket of ['ALL', level]) {
        if (levelSummary.value[bucket]) levelSummary.value[bucket][field] = String(Number(levelSummary.value[bucket][field]) + delta)
      }
    }
    // 只回填受时效影响的四个派生字段，避免冲掉用户正在编辑的时效输入。
    row.safetyStockQty = numberOrNull(fresh.safety_stock_quantity)
    row.safetyStockQty2 = numberOrNull(fresh.safety_stock_quantity_2)
    row.suggestedReplenishmentQty2 = numberOrNull(fresh.suggested_replenishment_quantity_2)
    row.suggestedReplenishmentQty = numberOrNull(fresh.suggested_replenishment_quantity)
    scheduleTreeReload()
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
  if (noteBusy.size || confirmingRows.size) {
    ElMessage.warning('请先完成备注保存或运营确认，再调整列')
    return
  }
  try {
    await applyColumnConfig(keys)
    ElMessage.success('列配置已保存')
  } catch (error) {
    ElMessage.warning('列配置已在当前浏览器生效，服务器保存失败')
  }
}

function columnTip(column) {
  const summaryTip = ' 汇总行数量和金额合计，比例按汇总分子/分母重算；等级、性质、负责人和时效仅在子项一致时显示，库龄取最大值。'
  if (column.key === 'principalName') return `${column.tip} 当前规则月份：${ownerRuleMonth.value || '--'}。`
  if (!column.monthlyKey || !latestCompleteMonth.value) return column.tip + summaryTip
  return `${column.tip} 当前主值区间：${formatMonth(latestCompleteMonth.value, true)}。${summaryTip}`
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

async function handleExport() {
  if (!checkPermi(['operations:ebayReplenishmentV2:export'])) {
    ElMessage.warning('没有eBay补货2.0导出权限，请联系管理员授权')
    return
  }
  if (exporting.value || loading.value) return
  if (rowRecalcTimers.size || recalculatingRowKeys.size) {
    ElMessage.warning('请等待补货指标重新计算完成后再导出')
    return
  }
  if (leadTimeSaveTimers.size || leadTimeSaveChains.size || salesTypeSaving.size || noteBusy.size || confirmingRows.size) {
    ElMessage.warning('请完成备注编辑，并等待时效、销售类型或确认保存后再导出')
    return
  }
  exporting.value = true
  try {
    if (!calculationVersion.value) await loadRows(true)
    if (!calculationVersion.value) {
      ElMessage.warning('请先刷新数据后再导出')
      return
    }
    const { pageNum, pageSize, ...params } = buildRequestParams()
    params.calculationVersion = calculationVersion.value
    await exportEbayReplenishmentV2(params)
  } finally {
    exporting.value = false
  }
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
  if (/^\d{4}-\d{2}-\d{2} ~ \d{4}-\d{2}-\d{2}$/.test(String(value || ''))) return value
  const matched = /^(\d{4})-(\d{2})$/.exec(String(value || ''))
  if (!matched) return '--'
  const month = Number(matched[2])
  return includeYear ? `${matched[1]}年${month}月` : `${month}月`
}

function setNoteBusy(row, field, busy) {
  const key = `${rowKey(row)}|${field}`
  if (busy) noteBusy.add(key)
  else noteBusy.delete(key)
}

function isNoteBusy(row) {
  return ['operations', 'development'].some(field => noteBusy.has(`${rowKey(row)}|${field}`))
}

function applyReview(row, data) {
  // Concurrent replies from different cells cannot roll back a newer version.
  for (const field of ['operations', 'development']) {
    const version = Number(data[`${field}_version`])
    if (version < row[`${field}Version`]) continue
    row[`${field}Version`] = version
    row[`${field}Note`] = data[`${field}_note`] || ''
    if (field === 'operations') {
      row.operationsConfirmed = Boolean(data.operations_confirmed)
      row.operationsConfirmedBy = data.operations_confirmed_by || ''
      row.operationsConfirmedAt = data.operations_confirmed_at || ''
    }
  }
  if (typeof queryParams.operationsConfirmed === 'boolean') scheduleTreeReload()
}

async function confirmOperations(row) {
  const key = rowKey(row)
  if (!reviewAvailable.value || isNoteBusy(row) || confirmingRows.has(key) || row.operationsConfirmed) return
  confirmingRows.add(key)
  try {
    await ElMessageBox.confirm(`确认 ${row.site} / ${row.sku} 已完成运营审核？`, '再次确认', {
      confirmButtonText: '确认', cancelButtonText: '取消', type: 'warning'
    })
    const response = await confirmEbayReplenishmentReview({ site: row.site, sku: row.sku,
      expected_version: row.operationsVersion })
    applyReview(row, response.data)
    ElMessage.success('已确认')
  } catch (error) {
    // Cancel changes nothing; request errors are displayed by the HTTP client.
  } finally {
    confirmingRows.delete(key)
  }
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
  disposed = true
  rowsRequest += 1
  clearTimeout(treeReloadTimer)
  clearTimeout(monthlyPopoverTimer)
  for (const timer of leadTimeSaveTimers.values()) clearTimeout(timer)
  leadTimeSaveTimers.clear()
  for (const timer of rowRecalcTimers.values()) clearTimeout(timer)
  rowRecalcTimers.clear()
})
</script>

<style scoped>
.hierarchy-count, .hierarchy-footer { color: var(--el-text-color-secondary); font-size: 12px; }
.hierarchy-footer { padding: 12px 0; }
.review-cell { display: flex; align-items: center; gap: 8px; }
.review-cell :deep(.el-input) { width: 85px; }
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

.data-source-note {
  color: #f56c6c;
  font-size: 14px;
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
