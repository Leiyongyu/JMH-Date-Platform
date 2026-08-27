<template>
  <div class="app-container return-detail-page">
    <el-card shadow="never" class="filter-card">
      <el-form :model="query" inline>
        <el-form-item label="站点">
          <el-select v-model="query.site" placeholder="所有站点" clearable style="width: 125px">
            <el-option v-for="item in sites" :key="item" :label="item" :value="item" />
          </el-select>
        </el-form-item>
        <el-form-item label="SKU">
          <el-input v-model="query.sku" placeholder="输入SKU" clearable style="width: 155px" @keyup.enter="search" />
        </el-form-item>
        <el-form-item label="订单号">
          <el-input v-model="query.orderNo" placeholder="输入订单号" clearable style="width: 175px" @keyup.enter="search" />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" icon="Search" @click="search">搜索</el-button>
          <el-button icon="Refresh" @click="reset">重置</el-button>
        </el-form-item>
        <el-form-item class="date-filter">
          <el-select v-model="query.timeType" style="width: 120px" @change="handleTimeTypeChange">
            <el-option label="按退款时间" value="refund" />
            <el-option label="按付款时间" value="payment" />
          </el-select>
          <el-date-picker
            v-model="dateRange"
            type="daterange"
            value-format="YYYY-MM-DD"
            range-separator="至"
            start-placeholder="开始日期"
            end-placeholder="结束日期"
            :clearable="false"
            :disabled-date="disabledDate"
            style="width: 255px"
            @change="handleDateChange"
          />
        </el-form-item>
      </el-form>
    </el-card>

    <div class="summary-row">
      <div><span>退款订单</span><strong>{{ number(summary.refund_order_count) }}</strong></div>
      <div><span>退货数量</span><strong>{{ number(summary.refund_count) }}</strong></div>
      <div><span>退款金额</span><strong>{{ money(summary.refund_amount) }}</strong></div>
      <div><span>涉及站点</span><strong>{{ number(summary.site_count) }}</strong></div>
    </div>

    <el-card shadow="never" class="table-card">
      <template #header>
        <div class="card-title">
          <div>
            <b>退货明细</b>
            <small>仅展示发货状态包含“已作废”或“已退款”的订单</small>
          </div>
        </div>
      </template>
      <el-table v-loading="loading" :data="rows" stripe height="620">
        <el-table-column label="订单号 / 站点" min-width="205" fixed>
          <template #default="scope">
            <div class="order-cell">
              <b>{{ scope.row.platform_order_no }}</b>
              <span>{{ scope.row.site_name }}</span>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="商品" min-width="255">
          <template #default="scope">
            <div class="product-cell">
              <el-image
                v-if="scope.row.picture_url"
                :src="scope.row.picture_url"
                :preview-src-list="[scope.row.picture_url]"
                fit="cover"
                preview-teleported
                class="product-image"
              />
              <span v-else class="product-placeholder">暂无</span>
              <el-link
                v-if="scope.row.listing_url"
                :href="scope.row.listing_url"
                target="_blank"
                type="primary"
                :underline="false"
              >{{ scope.row.inventory_sku }}</el-link>
              <b v-else>{{ scope.row.inventory_sku }}</b>
            </div>
          </template>
        </el-table-column>
        <el-table-column prop="refund_count" label="退货数" width="100" align="right" />
        <el-table-column label="退款金额" width="135" align="right">
          <template #default="scope"><b class="amount">{{ money(scope.row.refund_amount) }}</b></template>
        </el-table-column>
        <el-table-column prop="refund_reason" label="退款原因" min-width="280">
          <template #default="scope">
            <el-popover
              v-if="scope.row.refund_reason"
              placement="top-start"
              :width="440"
              trigger="hover"
              popper-class="return-reason-popper"
            >
              <template #reference>
                <div class="reason-summary">{{ scope.row.refund_reason }}</div>
              </template>
              <div class="reason-detail">{{ scope.row.refund_reason }}</div>
            </el-popover>
            <span v-else class="empty-text">--</span>
          </template>
        </el-table-column>
        <el-table-column label="售后分类" min-width="330">
          <template #default="scope">
            <el-cascader
              v-model="scope.row.category_id"
              :options="categoryOptions"
              :props="cascaderProps"
              :disabled="scope.row.classification_loading"
              placeholder="选择负责方 / 大类 / 小类"
              filterable
              style="width: 100%"
              @change="value => saveClassification(scope.row, value)"
            />
          </template>
        </el-table-column>
        <el-table-column prop="refund_time" label="退款时间" width="180" sortable>
          <template #default="scope">{{ scope.row.refund_time || '--' }}</template>
        </el-table-column>
      </el-table>
      <pagination
        v-show="total > 0"
        :total="total"
        v-model:page="query.pageNum"
        v-model:limit="query.pageSize"
        @pagination="load"
      />
    </el-card>
  </div>
</template>

<script setup name="EbayReturnDetail">
import { computed, getCurrentInstance, onMounted, reactive, ref } from 'vue'
import {
  getEbayReturnCategories,
  getEbayReturnDetails,
  saveEbayReturnClassification
} from '@/api/operations/ebay/skuAnalysis'

const { proxy } = getCurrentInstance()
const loading = ref(false)
const rows = ref([])
const sites = ref([])
const categories = ref([])
const dateRange = ref([])
const dateBounds = ref({ min_date: '', max_date: '' })
const total = ref(0)
const summary = ref({ refund_order_count: 0, refund_count: 0, refund_amount: 0, site_count: 0 })
const query = reactive({
  site: undefined,
  sku: '',
  orderNo: '',
  timeType: 'refund',
  startDate: undefined,
  endDate: undefined,
  pageNum: 1,
  pageSize: 50
})
const cascaderProps = { emitPath: false, expandTrigger: 'hover' }

const categoryOptions = computed(() => {
  const parties = new Map()
  categories.value.forEach(item => {
    const party = item.responsible_party || '未指定负责方'
    if (!parties.has(party)) parties.set(party, new Map())
    const groups = parties.get(party)
    if (!groups.has(item.big_category)) groups.set(item.big_category, [])
    groups.get(item.big_category).push({
      value: Number(item.category_id),
      label: item.small_category,
      description: item.classification_description
    })
  })
  return Array.from(parties.entries()).map(([party, groups]) => ({
    value: `party:${party}`,
    label: party,
    children: Array.from(groups.entries()).map(([bigCategory, children]) => ({
      value: `big:${party}:${bigCategory}`,
      label: bigCategory,
      children
    }))
  }))
})

function money(value) {
  return `¥${Number(value || 0).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
}
function number(value) { return Number(value || 0).toLocaleString('zh-CN') }
function disabledDate(date) {
  const min = dateBounds.value.min_date ? new Date(`${dateBounds.value.min_date}T00:00:00`).getTime() : undefined
  const max = dateBounds.value.max_date ? new Date(`${dateBounds.value.max_date}T23:59:59`).getTime() : undefined
  const value = date.getTime()
  return (min !== undefined && value < min) || (max !== undefined && value > max)
}

async function loadCategories() {
  const response = await getEbayReturnCategories()
  categories.value = response.data || []
}
async function load() {
  loading.value = true
  try {
    const response = await getEbayReturnDetails(query)
    const data = response.data || {}
    rows.value = (data.items || []).map(item => ({
      ...item,
      category_id: item.category_id ? Number(item.category_id) : undefined,
      saved_category_id: item.category_id ? Number(item.category_id) : undefined,
      classification_loading: false
    }))
    sites.value = data.sites || []
    summary.value = data.summary || summary.value
    total.value = data.pagination?.total || 0
    dateBounds.value = data.date_bounds || { min_date: '', max_date: '' }
    if (!query.startDate && data.start_date) {
      query.startDate = data.start_date
      query.endDate = data.end_date
      dateRange.value = [data.start_date, data.end_date]
    }
  } finally {
    loading.value = false
  }
}
function search() {
  query.pageNum = 1
  load()
}
function handleDateChange(value) {
  query.startDate = value?.[0]
  query.endDate = value?.[1]
  search()
}
function handleTimeTypeChange() {
  query.startDate = undefined
  query.endDate = undefined
  dateRange.value = []
  query.pageNum = 1
  load()
}
function reset() {
  Object.assign(query, {
    site: undefined, sku: '', orderNo: '', timeType: 'refund',
    startDate: undefined, endDate: undefined, pageNum: 1
  })
  dateRange.value = []
  load()
}
async function saveClassification(row, categoryId) {
  if (!categoryId || categoryId === row.saved_category_id) return
  const previous = row.saved_category_id
  row.classification_loading = true
  try {
    const response = await saveEbayReturnClassification({
      platform_order_no: row.platform_order_no,
      category_id: categoryId
    })
    const saved = response.data || {}
    rows.value.forEach(item => {
      if (item.platform_order_no === row.platform_order_no) {
        item.category_id = Number(saved.category_id)
        item.saved_category_id = Number(saved.category_id)
        item.responsible_party = saved.responsible_party
        item.big_category = saved.big_category
        item.small_category = saved.small_category
      }
    })
    proxy.$modal.msgSuccess('售后分类已保存')
  } catch {
    row.category_id = previous
  } finally {
    row.classification_loading = false
  }
}

onMounted(async () => {
  await loadCategories()
  await load()
})
</script>

<style scoped>
.return-detail-page{min-height:calc(100vh - 84px);background:#f4f6f9}.filter-card,.table-card{border:0;border-radius:10px;margin-bottom:14px}.filter-card :deep(.el-card__body){padding:14px 16px 2px}.date-filter{float:right}.summary-row{display:grid;grid-template-columns:repeat(4,1fr);gap:14px;margin-bottom:14px}.summary-row>div{background:#fff;border-radius:10px;padding:15px 20px;border-left:4px solid #409eff}.summary-row span{display:block;color:#909399;font-size:13px}.summary-row strong{display:block;margin-top:7px;font-size:22px;color:#303133}.card-title{display:flex;align-items:center;justify-content:space-between}.card-title>div{display:flex;align-items:baseline;gap:12px}.card-title small{color:#909399;font-weight:400}.order-cell{display:flex;flex-direction:column;gap:5px}.order-cell span{color:#909399;font-size:12px}.product-cell{display:flex;align-items:center;gap:12px}.product-image,.product-placeholder{width:52px;height:52px;border-radius:7px;flex:0 0 52px}.product-placeholder{display:flex;align-items:center;justify-content:center;background:#f2f3f5;color:#a8abb2;font-size:12px}.amount{font-weight:500;color:#303133}.reason-summary{display:-webkit-box;overflow:hidden;-webkit-box-orient:vertical;-webkit-line-clamp:2;max-height:40px;line-height:20px;word-break:break-all;color:#606266;cursor:help}.reason-detail{max-height:280px;overflow:auto;white-space:pre-wrap;word-break:break-word;line-height:1.65;color:#303133}.empty-text{color:#a8abb2}@media(max-width:1200px){.date-filter{float:none}.summary-row{grid-template-columns:repeat(2,1fr)}}
</style>
