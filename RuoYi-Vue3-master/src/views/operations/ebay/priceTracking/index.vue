<template>
  <div class="app-container ebay-price-tracking-page">
    <!-- 顶部栏 -->
    <el-row :gutter="10" class="mb8">
      <el-col :span="1.5">
        <el-button type="primary" plain icon="Refresh" :loading="loading" @click="handleRefresh">刷新快照</el-button>
      </el-col>
      <el-col :span="1.5">
        <el-button type="warning" plain icon="Download" @click="handleExport" v-hasPermi="['operations:ebayReplenishment:export']">导出</el-button>
      </el-col>
      <el-col :span="1.5">
        <el-tag type="info" size="large">{{ total }} 条</el-tag>
      </el-col>
      <right-toolbar v-model:showSearch="showSearch" @queryTable="loadData"></right-toolbar>
    </el-row>

    <!-- 筛选标签 -->
    <div v-if="activeFilters.length" style="margin-bottom:8px;display:flex;flex-wrap:wrap;align-items:center;gap:6px">
      <el-tag v-for="f in activeFilters" :key="f.field" closable size="small" type="info"
              @close="removeFilter(f.field)">{{ f.display }}</el-tag>
      <el-button size="small" text type="danger" @click="clearAllFilters">清除全部</el-button>
    </div>

    <!-- 表格 -->
    <el-table v-loading="loading" :data="records" border stripe height="640"
              row-key="id" @sort-change="handleSort">
      <el-table-column label="站点" prop="site" width="90" fixed sortable="custom">
        <template #header><HeaderWithFilter field="site" label="站点" :filterInfo="filterInfo" @open-filter="openFilter"/></template>
      </el-table-column>
      <el-table-column label="SKU" prop="sku" width="160" fixed sortable="custom" show-overflow-tooltip>
        <template #header><HeaderWithFilter field="sku" label="SKU" :filterInfo="filterInfo" @open-filter="openFilter"/></template>
      </el-table-column>
      <el-table-column label="产品名称" prop="productName" width="240" show-overflow-tooltip />
      <el-table-column label="等级" prop="skuLevel" width="80" align="center">
        <template #header><HeaderWithFilter field="skuLevel" label="等级" :filterInfo="filterInfo" @open-filter="openFilter"/></template>
        <template #default="{row}"><el-tag :type="levelTag(row.skuLevel)" effect="light" size="small">{{ row.skuLevel || '-' }}</el-tag></template>
      </el-table-column>

      <!-- 最低价 -->
      <el-table-column label="最低价" prop="ourLowestPrice" width="100" align="right" sortable="custom">
        <template #header><HeaderWithFilter field="ourLowestPrice" label="最低价" :filterInfo="filterInfo" numeric @open-filter="openFilter"/></template>
        <template #default="{row}">{{ row.ourLowestPrice ?? '-' }}</template>
      </el-table-column>

      <!-- 跟卖价（可编辑） -->
      <el-table-column label="跟卖价" prop="trackingPrice" width="120" align="center" sortable="custom">
        <template #header><HeaderWithFilter field="trackingPrice" label="跟卖价" :filterInfo="filterInfo" numeric @open-filter="openFilter"/></template>
        <template #default="{row}">
          <el-input v-model="trackingInputs[key(row,'tp')]" size="small" placeholder="跟卖价"
                    @blur="onTrackingBlur(row)" @keyup.enter="onTrackingBlur(row)" style="width:100px" />
        </template>
      </el-table-column>

      <!-- 跟卖利润率 -->
      <el-table-column label="跟卖利润率" prop="trackingProfitMargin" width="120" align="center">
        <template #default="{row}">{{ fmtPercent(row.trackingProfitMargin) }}</template>
      </el-table-column>

      <!-- 底线价 -->
      <el-table-column label="底线价" prop="floorPrice" width="100" align="right">
        <template #default="{row}">{{ row.floorPrice ?? '-' }}</template>
      </el-table-column>

      <el-table-column label="退货率" prop="returnRate" width="90" align="right" sortable="custom">
        <template #default="{row}">{{ fmtRate(row.returnRate) }}</template>
      </el-table-column>
      <el-table-column label="近3天销量" prop="sales3d" width="110" align="right" sortable="custom">
        <template #header><HeaderWithFilter field="sales3d" label="近3天销量" :filterInfo="filterInfo" numeric @open-filter="openFilter"/></template>
      </el-table-column>
      <el-table-column label="近7天销量" prop="sales7d" width="110" align="right" sortable="custom">
        <template #header><HeaderWithFilter field="sales7d" label="近7天销量" :filterInfo="filterInfo" numeric @open-filter="openFilter"/></template>
      </el-table-column>
      <el-table-column label="近30天销量" prop="sales30d" width="120" align="right" sortable="custom">
        <template #header><HeaderWithFilter field="sales30d" label="近30天销量" :filterInfo="filterInfo" numeric @open-filter="openFilter"/></template>
      </el-table-column>
      <el-table-column label="近90天销量" prop="sales90d" width="120" align="right" sortable="custom">
        <template #header><HeaderWithFilter field="sales90d" label="近90天销量" :filterInfo="filterInfo" numeric @open-filter="openFilter"/></template>
      </el-table-column>
      <el-table-column label="历史最大月销" prop="maxMonthlySales" width="130" align="right" sortable="custom">
        <template #header><HeaderWithFilter field="maxMonthlySales" label="历史最大月销" :filterInfo="filterInfo" numeric @open-filter="openFilter"/></template>
      </el-table-column>

      <!-- OE号（可编辑） -->
      <el-table-column label="OE号" prop="oeNumber" width="130" show-overflow-tooltip>
        <template #default="{row}">
          <el-input v-model="oeInputs[key(row,'oe')]" size="small" placeholder="OE号" clearable
                    @blur="onOeBlur(row)" @clear="onOeClear(row)" style="width:110px" />
        </template>
      </el-table-column>

      <el-table-column label="售前链接" prop="presaleUrl" width="140" show-overflow-tooltip>
        <template #default="{row}"><a v-if="row.presaleUrl" :href="row.presaleUrl" target="_blank" style="color:#409EFF">{{ truncate(row.presaleUrl, 35) }}</a></template>
      </el-table-column>
      <el-table-column label="售后链接" prop="soldUrl" width="140" show-overflow-tooltip>
        <template #default="{row}"><a v-if="row.soldUrl" :href="row.soldUrl" target="_blank" style="color:#409EFF">{{ truncate(row.soldUrl, 35) }}</a></template>
      </el-table-column>

      <el-table-column label="海外仓库存" prop="overseasStock" width="120" align="right" sortable="custom">
        <template #header><HeaderWithFilter field="overseasStock" label="海外仓库存" :filterInfo="filterInfo" numeric @open-filter="openFilter"/></template>
      </el-table-column>
      <el-table-column label="海外仓库龄" prop="overseasStockAgeDays" width="120" align="right" sortable="custom">
        <template #header><HeaderWithFilter field="overseasStockAgeDays" label="海外仓库龄" :filterInfo="filterInfo" numeric @open-filter="openFilter"/></template>
        <template #default="{row}">{{ row.overseasStockAgeDays != null ? row.overseasStockAgeDays + '天' : '-' }}</template>
      </el-table-column>
      <el-table-column label="库销比" prop="stockSalesRatio" width="90" align="right" sortable="custom">
        <template #default="{row}">{{ row.stockSalesRatio != null ? row.stockSalesRatio + '%' : '-' }}</template>
      </el-table-column>
      <el-table-column label="预估补货量" prop="estimatedReplenishQty" width="120" align="right" sortable="custom">
        <template #header><HeaderWithFilter field="estimatedReplenishQty" label="预估补货量" :filterInfo="filterInfo" numeric @open-filter="openFilter"/></template>
        <template #default="{row}">{{ row.estimatedReplenishQty ?? '-' }}</template>
      </el-table-column>

      <el-table-column label="品牌" prop="brandCode" width="90" show-overflow-tooltip>
        <template #header><HeaderWithFilter field="brandCode" label="品牌" :filterInfo="filterInfo" @open-filter="openFilter"/></template>
      </el-table-column>
      <el-table-column label="操作员" prop="operatorName" width="100" show-overflow-tooltip>
        <template #header><HeaderWithFilter field="operatorName" label="操作员" :filterInfo="filterInfo" @open-filter="openFilter"/></template>
      </el-table-column>

      <!-- 备注（可编辑） -->
      <el-table-column label="备注" prop="remark" width="180" show-overflow-tooltip>
        <template #default="{row}">
          <el-input v-model="remarkInputs[key(row,'rk')]" size="small" placeholder="备注" clearable
                    @blur="onRemarkBlur(row)" @clear="onRemarkClear(row)" style="width:160px" />
        </template>
      </el-table-column>
    </el-table>

    <pagination v-show="total>0" :total="total" v-model:page="query.pageNum" v-model:limit="query.pageSize" @pagination="loadData" />

    <!-- 筛选弹窗 -->
    <el-popover v-model:visible="filterVisible" :virtual-ref="filterAnchorEl" virtual-triggering placement="bottom-start" :width="240" :offset="2">
      <div style="max-height:300px">
        <template v-if="!NUMERIC_KEYS.has(filterField)">
          <el-input v-model="filterText" placeholder="搜索..." size="small" clearable @keyup.enter="applyFilter" />
          <div v-if="filterText" style="max-height:160px;overflow-y:auto;margin-top:6px">
            <div v-for="v in filterSearchResults" :key="v" style="padding:3px 0">
              <el-checkbox v-model="filterCheckedSet[v]" @change="()=>{}" :label="v" size="small">{{ v }}</el-checkbox>
            </div>
          </div>
          <div v-else style="max-height:160px;overflow-y:auto;margin-top:6px">
            <div style="font-size:11px;color:#999;padding:4px 0">可选值</div>
            <div v-for="v in distinctValuesList" :key="v" style="padding:2px 0">
              <el-checkbox v-model="filterCheckedSet[v]" @change="()=>{}" :label="v" size="small">{{ v }}</el-checkbox>
            </div>
          </div>
        </template>
        <template v-else>
          <div style="display:flex;gap:6px;align-items:center">
            <el-select v-model="filterNumOp" size="small" style="width:65px">
              <el-option v-for="op in ['>','>=','=','<=','<']" :key="op" :value="op" :label="op" />
            </el-select>
            <el-input v-model="filterNumVal" size="small" type="number" placeholder="数值" @keyup.enter="applyFilter" style="flex:1" />
          </div>
        </template>
        <div style="display:flex;justify-content:flex-end;gap:6px;margin-top:8px">
          <el-button size="small" @click="clearFilter">清除</el-button>
          <el-button size="small" type="primary" @click="applyFilter">确定</el-button>
        </div>
      </div>
    </el-popover>
  </div>
</template>

<script setup>
import { computed, getCurrentInstance, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { searchPriceTracking, fetchDistinctValues, refreshPriceTracking, calcTracking, saveOe, saveRemark } from '@/api/operations/ebay/priceTracking'
import { ElMessage } from 'element-plus'
import HeaderWithFilter from '@/components/HeaderWithFilter/index.vue'

const { proxy } = getCurrentInstance()
const loading = ref(false), total = ref(0), records = ref([]), showSearch = ref(true)

// ====== 查询参数 ======
const query = reactive({ pageNum: 1, pageSize: 50, sortField: '', sortOrder: '' })
const activeFilters = ref([])  // [{ field, value, display }]

// ====== 筛选弹窗 ======
const filterVisible = ref(false), filterAnchorEl = ref(null), filterField = ref('')
const filterText = ref(''), filterNumOp = ref('>'), filterNumVal = ref('')
const filterCheckedSet = reactive({}), filterSearchResults = ref([]), filterTimer = ref(null)
const TEXT_KEYS = new Set(['site','sku','skuLevel','productName','oeNumber','brandCode','operatorName'])
const NUMERIC_KEYS = new Set(['ourLowestPrice','trackingPrice','trackingProfitMargin','floorPrice','returnRate',
  'sales3d','sales7d','sales30d','sales90d','maxMonthlySales','overseasStock','overseasStockAgeDays',
  'stockSalesRatio','estimatedReplenishQty'])

const colMap = { site:'site', sku:'sku', skuLevel:'sku_level', productName:'product_name', oeNumber:'oe_number',
  brandCode:'brand_code', operatorName:'operator_name' }

// 当前页 distinct（仅来自 records 的本地聚合）
const distinctValuesList = computed(() => {
  if (!filterField.value || NUMERIC_KEYS.has(filterField.value)) return []
  const set = new Set()
  for (const row of records.value) { const v = row[filterField.value]; if (v != null && String(v).trim()) set.add(String(v).trim()) }
  return [...set].sort().slice(0, 50)
})

// 远程 distinct 搜索
watch(filterText, (val) => {
  if (!filterVisible.value || !filterField.value || NUMERIC_KEYS.has(filterField.value)) return
  clearTimeout(filterTimer.value)
  filterTimer.value = setTimeout(async () => {
    if (!val || !val.trim()) { filterSearchResults.value = []; return }
    try { const r = await fetchDistinctValues(filterField.value, val.trim()); filterSearchResults.value = r?.data || [] }
    catch { filterSearchResults.value = [] }
  }, 200)
})

function openFilter(field, el) {
  filterField.value = field; filterText.value = ''; filterNumOp.value = '>'; filterNumVal.value = ''; filterSearchResults.value = []
  // 清空多选
  Object.keys(filterCheckedSet).forEach(k => delete filterCheckedSet[k])
  const exist = activeFilters.value.find(f => f.field === field)
  if (exist) {
    if (NUMERIC_KEYS.has(field)) {
      const m = exist.value.match(/^(>=|<=|>|<|=)(.+)$/)
      if (m) { filterNumOp.value = m[1]; filterNumVal.value = m[2] }
    } else {
      filterText.value = exist.value
      exist.value.split(',').filter(Boolean).forEach(v => filterCheckedSet[v] = true)
    }
  }
  filterAnchorEl.value = el
  nextTick(() => { filterVisible.value = true })
}

function applyFilter() {
  const f = filterField.value; let val = ''
  if (NUMERIC_KEYS.has(f)) {
    if (filterNumVal.value) val = filterNumOp.value + filterNumVal.value.trim()
  } else {
    const checked = Object.entries(filterCheckedSet).filter(([,v]) => v).map(([k]) => k)
    val = checked.length ? checked.join(',') : (filterText.value?.trim() || '')
  }
  removeFilter(f)
  if (val) activeFilters.value.push({ field: f, value: val, display: (colMap[f] || f) + ':' + val })
  filterVisible.value = false
  query.pageNum = 1
  loadData()
}

function clearFilter() {
  removeFilter(filterField.value)
  filterText.value = ''; filterNumVal.value = ''; filterNumOp.value = '>'
  Object.keys(filterCheckedSet).forEach(k => delete filterCheckedSet[k])
  filterVisible.value = false
  query.pageNum = 1; loadData()
}

function removeFilter(field) { activeFilters.value = activeFilters.value.filter(af => af.field !== field) }
function clearAllFilters() { activeFilters.value = []; query.pageNum = 1; loadData() }

// ====== 内联编辑状态 ======
const trackingInputs = reactive({}), oeInputs = reactive({}), remarkInputs = reactive({})
function key(row, prefix) { return prefix + '_' + (row.site||'') + '|' + (row.sku||'') }

function initInputs() {
  for (const row of records.value) {
    const k = key(row, 'tp'); if (!(k in trackingInputs)) trackingInputs[k] = row.trackingPrice ?? ''
    const ko = key(row, 'oe'); if (!(ko in oeInputs)) oeInputs[ko] = row.oeNumber ?? ''
    const kr = key(row, 'rk'); if (!(kr in remarkInputs)) remarkInputs[kr] = row.remark ?? ''
  }
}

async function onTrackingBlur(row) {
  const v = trackingInputs[key(row, 'tp')]
  if (v === (row.trackingPrice != null ? String(row.trackingPrice) : '')) return
  try {
    const price = v && !isNaN(parseFloat(v)) ? v : ''
    const r = await calcTracking(row.site, row.sku, price)
    const d = r.data
    row.trackingPrice = d.trackingPrice != null ? d.trackingPrice : d.trackingPrice
    row.trackingProfitMargin = d.trackingProfitMargin
    row.floorPrice = d.floorPrice
    ElMessage.success('已计算')
  } catch { ElMessage.error('计算失败') }
}

async function onOeBlur(row) {
  const v = oeInputs[key(row, 'oe')] || ''
  if (v === (row.oeNumber || '')) return
  try { await saveOe(row.site, row.sku, v); row.oeNumber = v; ElMessage.success('OE已保存') }
  catch { ElMessage.error('保存失败') }
}

async function onOeClear(row) { oeInputs[key(row, 'oe')] = ''; try { await saveOe(row.site, row.sku, ''); row.oeNumber = '' } catch {} }

async function onRemarkBlur(row) {
  const v = remarkInputs[key(row, 'rk')] || ''
  if (v === (row.remark || '')) return
  try { await saveRemark(row.site, row.sku, v); row.remark = v; ElMessage.success('备注已保存') }
  catch { ElMessage.error('保存失败') }
}

async function onRemarkClear(row) { remarkInputs[key(row, 'rk')] = ''; try { await saveRemark(row.site, row.sku, ''); row.remark = '' } catch {} }

// ====== 数据加载 ======
watch(records, initInputs, { flush: 'post' })

async function loadData() {
  loading.value = true
  try {
    const body = { pageNum: query.pageNum, pageSize: query.pageSize, sortField: query.sortField || undefined, sortOrder: query.sortOrder || undefined }
    if (activeFilters.value.length) body.filters = activeFilters.value.map(f => ({ field: f.field, value: f.value }))
    const r = await searchPriceTracking(body)
    records.value = r.rows || []; total.value = r.total || 0
    initInputs()
  } finally { loading.value = false }
}

async function handleRefresh() {
  if (loading.value) return; loading.value = true
  try { await refreshPriceTracking(); await loadData(); ElMessage.success('刷新完成') }
  catch { ElMessage.error('刷新失败') } finally { loading.value = false }
}

function handleSort({ prop, order }) {
  query.sortField = order ? prop : ''; query.sortOrder = order || ''
  query.pageNum = 1; loadData()
}

function handleExport() {
  proxy.download('operations/ebay/price-tracking/export', {}, `ebay_price_tracking_${new Date().getTime()}.xlsx`)
}

const filterInfo = computed(() => {
  const m = {}
  for (const f of activeFilters.value) m[f.field] = true
  return m
})

// ====== 格式化 ======
function fmtPercent(v) { if (v == null) return '-'; return (Number(v) * 100).toFixed(1) + '%' }
function fmtRate(v) { if (v == null) return '-'; return (Number(v) * 100).toFixed(1) + '%' }
function truncate(s, n) { if (!s) return ''; return s.length > n ? s.substring(0, n) + '...' : s }
function levelTag(l) { const m = { A:'success', B:'primary', C:'warning', D:'info', E:'danger' }; return m[l] || 'info' }

onMounted(() => loadData())
onBeforeUnmount(() => clearTimeout(filterTimer.value))
</script>

<style scoped>
.ebay-price-tracking-page { background: #f5f7fa; }
:deep(.el-table .cell) { white-space: nowrap; }
:deep(.el-input--small .el-input__wrapper) { padding: 1px 6px; }
</style>
