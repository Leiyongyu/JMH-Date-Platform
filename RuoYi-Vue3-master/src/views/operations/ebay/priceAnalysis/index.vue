<template>
  <div class="app-container ebay-price-analysis">
    <!-- ===== 页头 ===== -->
    <el-card shadow="never" class="head-card">
      <div class="head-top">
        <div class="head-title">
          <h2>价格分析</h2>
          <p class="head-meta">
            <span class="meta-item">
              快照日期
              <strong>{{ displayValue(snapshot.stat_date) }}</strong>
            </span>
            <span class="meta-sep">·</span>
            <span class="meta-item">
              刷新时间
              <strong>{{ displayValue(snapshot.refreshed_at) }}</strong>
            </span>
            <span class="meta-sep">·</span>
            <span class="meta-item">eBay 在售刊登 × 谷仓海外仓库存</span>
          </p>
        </div>
        <div class="head-acts">
          <!-- 只重新读看板表；生产数据由 ERP 定时任务负责，页面不触发同步 -->
          <el-button :disabled="loading" @click="handleQuery">
            <app-icon name="refresh" :size="15" class="report-icon" :spin="loading" />刷新
          </el-button>
          <el-tooltip
            content="导出当前筛选下全部记录（店铺维度按刊登、SKU 维度按站点 + SKU），仅包含角色授权的导出字段；不受分页或页面隐藏列限制"
            placement="top"
          >
            <el-button
              type="primary"
              plain
              :loading="exporting"
              :disabled="loading"
              v-hasPermi="['operations:ebayPriceAnalysis:export']"
              @click="handleExport"
            >
              <app-icon v-if="!exporting" name="export" :size="15" class="report-icon" />导出明细
            </el-button>
          </el-tooltip>
        </div>
      </div>

      <el-alert type="info" :closable="false" show-icon class="snapshot-alert">
        <template #title>
          看板展示 {{ displayValue(snapshot.stat_date) }} 的快照：eBay 侧为在售刊登每周快照（每周一更新），
          海外仓为谷仓区域仓接口每周快照，成都中转仓为领星周快照，均<strong>不是实时库存</strong>。
        </template>
      </el-alert>

      <el-form :model="query" inline class="filter-form" label-width="56px">
        <el-form-item label="站点">
          <el-select
            v-model="query.sites"
            multiple
            collapse-tags
            collapse-tags-tooltip
            clearable
            placeholder="全部站点"
            class="filter-control"
            @change="handleQuery"
          >
            <el-option v-for="site in siteOptions" :key="site" :label="site" :value="site" />
          </el-select>
        </el-form-item>
        <el-form-item label="店铺">
          <el-select
            v-model="query.accounts"
            multiple
            filterable
            collapse-tags
            collapse-tags-tooltip
            clearable
            placeholder="全部店铺"
            class="filter-control"
            @change="handleQuery"
          >
            <el-option v-for="account in accountOptions" :key="account" :label="account" :value="account" />
          </el-select>
        </el-form-item>
        <el-form-item label="关键词">
          <el-input
            v-model="query.keyword"
            clearable
            placeholder="SKU / 标题 / Item ID"
            class="filter-control"
            @clear="handleListFilter"
            @keyup.enter="handleListFilter"
          />
        </el-form-item>
        <el-form-item label-width="0" class="flag-filters">
          <el-checkbox v-model="query.onlyUnmatched" @change="handleListFilter">只看未匹配</el-checkbox>
        </el-form-item>
        <el-form-item label-width="0">
          <el-button type="primary" @click="handleQuery"><app-icon name="search" :size="15" class="btn-icon" />搜索</el-button>
          <el-button @click="resetQuery"><app-icon name="undo" :size="15" class="btn-icon" />重置</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <!-- ===== 主体：店铺维度 / SKU 维度 ===== -->
    <el-card shadow="never" class="table-card">
      <el-tabs v-model="activeTab" class="dimension-tabs" @tab-change="handleTabChange">
        <!-- 店铺维度：上面选店铺，下面看这个店铺在这个站点的 SKU -->
        <el-tab-pane label="店铺维度" name="store">
          <div class="section-head">
            <div class="section-head__text">
              <span class="card-title">店铺汇总</span>
              <small>一行一个「店铺 + 站点」；点一行在下方查看该店铺的 SKU 明细。汇总只受站点、店铺筛选影响</small>
            </div>
          </div>
          <el-table
            v-loading="storesLoading"
            :data="stores"
            :size="dense ? 'small' : 'default'"
            :row-class-name="storeRowClass"
            border
            max-height="320"
            class="store-table"
            style="max-width: 760px"
            empty-text="没有符合条件的店铺，换个站点或店铺试试"
            @row-click="selectStore"
          >
            <!-- 只有店铺列是弹性宽度；不给整表限宽时它会吃掉整张卡片的剩余宽度。最长店铺名约 21 个字符，200px 足够 -->
            <el-table-column prop="seller_account" label="店铺" min-width="200" show-overflow-tooltip />
            <el-table-column prop="site_name" label="站点" width="90" align="center">
              <template #default="{ row }">{{ displayValue(row.site_name || row.site) }}</template>
            </el-table-column>
            <el-table-column prop="listing_count" label="在售刊登" width="100" align="right">
              <template #default="{ row }">{{ integer(row.listing_count) }}</template>
            </el-table-column>
            <el-table-column prop="sku_count" label="SKU 数" width="90" align="right">
              <template #default="{ row }">{{ integer(row.sku_count) }}</template>
            </el-table-column>
            <el-table-column prop="ebay_available" label="eBay 可售合计" width="120" align="right">
              <template #default="{ row }">{{ integer(row.ebay_available) }}</template>
            </el-table-column>
            <el-table-column prop="unmatched_count" width="100" align="right">
              <template #header>
                <span class="column-header">
                  <span>未匹配</span>
                  <el-tooltip content="这家店在本站点的谷仓和成都仓都找不到对应 SKU 的刊登数；点数字只看这些，原因见明细的「未匹配原因」列" placement="top">
                    <app-icon name="help" :size="13" class="column-tip" />
                  </el-tooltip>
                </span>
              </template>
              <template #default="{ row }">
                <el-link
                  v-if="Number(row.unmatched_count) > 0"
                  type="warning"
                  :underline="false"
                  class="count-link"
                  @click.stop="focusStore(row)"
                >{{ integer(row.unmatched_count) }}</el-link>
                <span v-else class="muted">{{ integer(row.unmatched_count) }}</span>
              </template>
            </el-table-column>
          </el-table>

          <div class="section-head section-head--detail">
            <div class="section-head__text">
              <span class="card-title">
                <template v-if="selectedStore">
                  {{ selectedStore.seller_account }} · {{ displayValue(selectedStore.site_name || selectedStore.site) }} 的 SKU 明细
                </template>
                <template v-else>SKU 明细</template>
              </span>
              <small>同站点列是这个 SKU 在同一站点所有店铺的情况；点「其他店铺」看每个店铺的刊登</small>
            </div>
            <div class="table-tools">
              <el-button :type="dense ? 'primary' : 'default'" plain @click="dense = !dense">紧凑</el-button>
              <el-button @click="openColumnConfig"><app-icon name="columns" :size="15" class="btn-icon" />自定义列</el-button>
            </div>
          </div>
          <el-empty v-if="!selectedStore" description="在上方店铺汇总里点一个店铺，查看它的 SKU 明细" :image-size="64" />
          <template v-else>
            <el-table
              v-if="columnConfigLoaded"
              :key="columnTableKey"
              v-loading="detailLoading"
              :data="detailRows"
              :size="dense ? 'small' : 'default'"
              border
              height="520"
              empty-text="这个店铺没有符合条件的刊登，换个关键词或取消「只看未匹配」试试"
              @sort-change="handleDetailSort"
            >
              <el-table-column
                v-for="col in visibleColumns"
                :key="col.key"
                :prop="col.key"
                :label="col.label"
                :width="col.width"
                :min-width="col.minWidth"
                :align="col.align"
                :fixed="col.fixed || false"
                :sortable="col.sortable ? 'custom' : false"
                :show-overflow-tooltip="col.tooltip"
              >
                <template v-if="col.tip" #header>
                  <span class="column-header">
                    <span>{{ col.label }}</span>
                    <el-tooltip :content="col.tip" placement="top">
                      <app-icon name="help" :size="13" class="column-tip" />
                    </el-tooltip>
                  </span>
                </template>
                <template #default="{ row }">
                  <el-image
                    v-if="col.format === 'image' && row.image_url"
                    :src="row.image_url"
                    fit="cover"
                    class="row-image"
                    :preview-src-list="[row.image_url]"
                    preview-teleported
                  />
                  <el-link
                    v-else-if="col.format === 'skuLink' && row.view_item_url"
                    :href="row.view_item_url"
                    target="_blank"
                    type="primary"
                    :underline="false"
                    class="sku-link"
                  >{{ displayValue(row.sku) }}</el-link>
                  <span v-else-if="col.format === 'reason'" class="unmatched-reason">{{ unmatchedReason(row) }}</span>
                  <span v-else :class="cellClass(row, col)">{{ cellText(row, col) }}</span>
                </template>
              </el-table-column>
              <el-table-column label="对比" width="104" align="center" fixed="right">
                <template #default="{ row }">
                  <el-button link type="primary" :disabled="!row.sku" @click="openCompare(row)">其他店铺</el-button>
                </template>
              </el-table-column>
            </el-table>
            <pagination
              v-show="detailTotal > 0"
              :total="detailTotal"
              v-model:page="detailPage.pageNum"
              v-model:limit="detailPage.pageSize"
              @pagination="loadStoreDetail"
            />
          </template>
        </el-tab-pane>

        <!-- SKU 维度：一行一个「站点 + SKU」，展开看所有店铺和所有站点 -->
        <el-tab-pane label="SKU 维度" name="sku">
          <div class="section-head">
            <div class="section-head__text">
              <span class="card-title">按站点 + SKU 汇总</span>
              <small>库存按站点共享取一份，eBay 可售按店铺相加；展开一行查看这个 SKU 在所有店铺、所有站点的刊登和库存</small>
            </div>
            <div class="table-tools">
              <el-button :type="dense ? 'primary' : 'default'" plain @click="dense = !dense">紧凑</el-button>
            </div>
          </div>
          <el-table
            v-loading="skuLoading"
            :data="skuRows"
            :size="dense ? 'small' : 'default'"
            :row-key="skuRowKey"
            border
            height="560"
            empty-text="没有符合条件的 SKU，换个站点、店铺、关键词或取消「只看未匹配」试试"
            @sort-change="handleSkuSort"
            @expand-change="handleSkuExpand"
          >
            <el-table-column type="expand" width="44" fixed>
              <template #default="{ row }">
                <div class="expand-box">
                  <el-skeleton v-if="skuListing(row.sku).loading" :rows="3" animated />
                  <el-alert
                    v-else-if="skuListing(row.sku).error"
                    type="error"
                    :closable="false"
                    title="这个 SKU 的跨店数据没取到，收起再展开重试"
                  />
                  <template v-else-if="skuListing(row.sku).data">
                    <p class="shared-hint">谷仓、成都库存按站点共享，同一站点多个店铺显示的是同一份库存，不能相加</p>
                    <div class="compare-title">各站点库存</div>
                    <el-table
                      :data="skuListing(row.sku).data.sites"
                      size="small"
                      border
                      :row-class-name="params => compareSiteRowClass(params, row.site)"
                      empty-text="没有库存记录"
                    >
                      <el-table-column
                        v-for="col in compareSiteColumns"
                        :key="col.key"
                        :label="col.label"
                        :width="col.width"
                        :min-width="col.minWidth"
                        :align="col.align"
                      >
                        <template #default="scope">{{ cellText(scope.row, col) }}</template>
                      </el-table-column>
                    </el-table>
                    <div class="compare-title">各店铺刊登（当前站点高亮）</div>
                    <el-table
                      :data="skuListing(row.sku).data.listings"
                      size="small"
                      border
                      :row-class-name="params => compareListingRowClass(params, { site: row.site })"
                      empty-text="没有在售刊登"
                    >
                      <el-table-column
                        v-for="col in compareListingColumns"
                        :key="col.key"
                        :label="col.label"
                        :width="col.width"
                        :min-width="col.minWidth"
                        :align="col.align"
                        :show-overflow-tooltip="col.tooltip"
                      >
                        <template #default="scope">
                          <el-link
                            v-if="col.format === 'itemLink' && scope.row.view_item_url"
                            :href="scope.row.view_item_url"
                            target="_blank"
                            type="primary"
                            :underline="false"
                          >{{ displayValue(scope.row.item_id) }}</el-link>
                          <span v-else-if="col.format === 'reason'" class="unmatched-reason">{{ unmatchedReason(scope.row) }}</span>
                          <span v-else>{{ cellText(scope.row, col) }}</span>
                        </template>
                      </el-table-column>
                    </el-table>
                  </template>
                </div>
              </template>
            </el-table-column>
            <el-table-column
              v-for="col in skuColumns"
              :key="col.key"
              :prop="col.key"
              :label="col.label"
              :width="col.width"
              :min-width="col.minWidth"
              :align="col.align"
              :fixed="col.fixed || false"
              :sortable="col.sortable ? 'custom' : false"
              :show-overflow-tooltip="col.tooltip"
            >
              <template v-if="col.tip" #header>
                <span class="column-header">
                  <span>{{ col.label }}</span>
                  <el-tooltip :content="col.tip" placement="top">
                    <app-icon name="help" :size="13" class="column-tip" />
                  </el-tooltip>
                </span>
              </template>
              <template #default="{ row }">
                <el-image
                  v-if="col.format === 'image' && row.image_url"
                  :src="row.image_url"
                  fit="cover"
                  class="row-image"
                  :preview-src-list="[row.image_url]"
                  preview-teleported
                />
                <span v-else-if="col.format === 'reason'" class="unmatched-reason">{{ unmatchedReason(row) }}</span>
                <span v-else :class="cellClass(row, col)">{{ cellText(row, col) }}</span>
              </template>
            </el-table-column>
          </el-table>
          <pagination
            v-show="skuTotal > 0"
            :total="skuTotal"
            v-model:page="skuPage.pageNum"
            v-model:limit="skuPage.pageSize"
            @pagination="loadSkuRows"
          />
        </el-tab-pane>
      </el-tabs>
    </el-card>

    <!-- ===== 口径说明 ===== -->
    <el-card shadow="never" class="note-card">
      <template #header>
        <span class="card-title">口径说明</span>
      </template>
      <ul class="note-list">
        <li class="note-key">谷仓、成都库存按站点共享，同一站点多个店铺显示的是同一份库存，不能相加</li>
        <li>eBay 售价与可售量为在售刊登每周快照（每周一更新），快照日期见页头</li>
        <li>海外仓库存为谷仓区域仓接口每周快照（DE / UK / 美东 USEA / 美西 USWE，美国两仓合计；捷克 CZ 暂不纳入），<strong>不是实时库存</strong></li>
        <li>成都中转仓库存仍为领星周快照</li>
        <li>海外仓按「站点 + 去掉 SKU 第一段（品牌前缀，谷仓侧为 JMH）」匹配</li>
        <li>未匹配：这条刊登在所在站点的谷仓和成都仓都找不到对应 SKU，原因见『未匹配原因』列</li>
        <li>售价按站点币种和领星月度企业汇率折算 USD；当月汇率未出时，沿用该币种最近一个已出月份的汇率；完全没有汇率时不折算</li>
        <li>采购成本取订单文件中的真实采购成本，未参与售价估算</li>
      </ul>
    </el-card>

    <!-- ===== 这个 SKU 在其他店铺 ===== -->
    <el-drawer
      v-model="compareDrawer.visible"
      size="920px"
      class="sku-compare-drawer"
      append-to-body
      :title="`其他店铺 · ${displayValue(compareDrawer.sku)}`"
    >
      <el-skeleton v-if="compareState.loading" :rows="6" animated />
      <el-alert
        v-else-if="compareState.error"
        type="error"
        :closable="false"
        title="这个 SKU 的跨店数据没取到，关掉抽屉再点一次重试"
      />
      <template v-else-if="compareState.data">
        <div class="compare-head">
          <el-image
            v-if="compareState.data.image_url"
            :src="compareState.data.image_url"
            fit="cover"
            class="compare-image"
            :preview-src-list="[compareState.data.image_url]"
            preview-teleported
          />
          <div class="compare-head__text">
            <strong>{{ displayValue(compareState.data.sku || compareDrawer.sku) }}</strong>
            <span>{{ displayValue(compareState.data.title) }}</span>
          </div>
        </div>
        <p class="shared-hint">谷仓、成都库存按站点共享，同一站点多个店铺显示的是同一份库存，不能相加</p>
        <div class="compare-title">各站点库存</div>
        <el-table
          :data="compareState.data.sites"
          size="small"
          border
          :row-class-name="params => compareSiteRowClass(params, compareDrawer.origin?.site)"
          empty-text="没有库存记录"
        >
          <el-table-column
            v-for="col in compareSiteColumns"
            :key="col.key"
            :label="col.label"
            :width="col.width"
            :min-width="col.minWidth"
            :align="col.align"
          >
            <template #default="scope">{{ cellText(scope.row, col) }}</template>
          </el-table-column>
        </el-table>
        <div class="compare-title">各店铺刊登（当前店铺高亮）</div>
        <el-table
          :data="compareState.data.listings"
          size="small"
          border
          :row-class-name="params => compareListingRowClass(params, compareDrawer.origin)"
          empty-text="没有在售刊登"
        >
          <el-table-column
            v-for="col in compareListingColumns"
            :key="col.key"
            :label="col.label"
            :width="col.width"
            :min-width="col.minWidth"
            :align="col.align"
            :show-overflow-tooltip="col.tooltip"
          >
            <template #default="scope">
              <el-link
                v-if="col.format === 'itemLink' && scope.row.view_item_url"
                :href="scope.row.view_item_url"
                target="_blank"
                type="primary"
                :underline="false"
              >{{ displayValue(scope.row.item_id) }}</el-link>
              <span v-else-if="col.format === 'reason'" class="unmatched-reason">{{ unmatchedReason(scope.row) }}</span>
              <span v-else>{{ cellText(scope.row, col) }}</span>
            </template>
          </el-table-column>
        </el-table>
      </template>
    </el-drawer>

    <ColumnConfigDrawer
      v-model="showColumnDrawer"
      :columns="columnDefs"
      :fixed-keys="fixedColumnKeys"
      :required-keys="requiredColumnKeys"
      :visible-keys="visibleKeys"
      @apply="applyColumnConfig"
    />
  </div>
</template>

<script setup name="EbayPriceAnalysis">
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import {
  exportEbayPriceAnalysis,
  getEbayPriceAnalysisSkuListings,
  listEbayPriceAnalysisDetail,
  listEbayPriceAnalysisStores
} from '@/api/operations/ebayPriceAnalysis'
import ColumnConfigDrawer from '@/components/ColumnConfigDrawer/index.vue'
import { useColumnConfig } from '@/composables/useColumnConfig'
import { checkPermi } from '@/utils/permission'

// 库存、同站点汇总、未匹配原因都由后端算好（原因在刷表时判定），前端只按返回值渲染和筛选，不自己推导。
const SITE_OPTIONS = ['DE', 'UK', 'US', 'FR']
const SHARED_STOCK_TIP = '按站点共享：同一站点多个店铺显示的是同一份库存，不能相加。'

const storesLoading = ref(false)
const detailLoading = ref(false)
const skuLoading = ref(false)
const exporting = ref(false)
const dense = ref(false)
const activeTab = ref('store')
const snapshot = reactive({ stat_date: undefined, refreshed_at: undefined })
const stores = ref([])
const selectedStore = ref(null)
const detailRows = ref([])
const detailTotal = ref(0)
const skuRows = ref([])
const skuTotal = ref(0)
const knownAccounts = ref([])
const skuListings = reactive({})
const compareDrawer = reactive({ visible: false, sku: '', origin: null })

const query = reactive({
  sites: [],
  accounts: [],
  keyword: undefined,
  onlyUnmatched: false
})
const detailPage = reactive({ pageNum: 1, pageSize: 50, sortBy: undefined, sortOrder: undefined })
const skuPage = reactive({ pageNum: 1, pageSize: 50, sortBy: undefined, sortOrder: undefined })

// 筛选每变一次版本号加一；切页签时版本对不上才重新拉，避免另一个页签拿着旧筛选的数据。
let filterVersion = 0
const loadedVersion = { store: -1, sku: -1 }
let storesSeq = 0
let detailSeq = 0
let skuSeq = 0

// 店铺维度明细列；页面配置换了新 key，旧看板保存的列顺序不会套到新表上。
const fixedColumnKeys = ['image_url', 'sku']
const requiredColumnKeys = ['sku']
const columnDefs = [
  { key: 'image_url', label: '图片', width: 70, fixed: true, align: 'center', format: 'image' },
  { key: 'sku', label: 'SKU', minWidth: 160, fixed: true, format: 'skuLink' },
  { key: 'title', label: '产品名称', minWidth: 200, tooltip: true },
  { key: 'owner_name', label: '负责人', width: 100, sortable: true, tip: '按 eBay 品牌负责人规则匹配，与绩效排名、月度库存同一口径；规则里没有的品牌显示「未分配」。' },
  { key: 'listing_start_time', label: '上架时间', width: 170, sortable: true, tip: 'eBay 刊登的上架时间（北京时间）。eBay 接口不返回改价时间，这里不是最近调价时间。' },
  { key: 'current_price', label: '原币售价', width: 120, align: 'right', format: 'price' },
  {
    key: 'price_usd', label: '售价(USD)', width: 115, align: 'right', format: 'decimal', sortable: true,
    tip: '按站点币种和领星月度企业汇率折算；当月汇率未出时沿用该币种最近一个已出月份的汇率，完全没有汇率时显示「—」。'
  },
  { key: 'ebay_quantity_available', label: 'eBay可售', width: 105, align: 'right', format: 'integer', sortable: true },
  {
    key: 'overseas_sellable', label: '谷仓可售', width: 105, align: 'right', format: 'integer', sortable: true,
    tip: `谷仓区域仓接口每周快照（美国两仓合计），不是实时库存。${SHARED_STOCK_TIP}`
  },
  {
    key: 'chengdu_sellable', label: '成都可售', width: 105, align: 'right', format: 'integer', sortable: true,
    tip: `领星周快照。${SHARED_STOCK_TIP}`
  },
  { key: 'overseas_in_transit', label: '海外在途', width: 100, align: 'right', format: 'integer' },
  {
    key: 'site_store_count', label: '同站点店铺数', width: 125, align: 'right', format: 'integer',
    tip: '同一站点在售这个 SKU 的店铺数。'
  },
  {
    key: 'site_ebay_available_total', label: '同站点eBay可售合计', width: 160, align: 'right', format: 'integer',
    tip: '同一站点所有店铺这个 SKU 的 eBay 可售相加。eBay 可售是各店铺自己的，可以相加；库存不能。'
  },
  {
    key: 'unmatched_reason_text', label: '未匹配原因', minWidth: 220, format: 'reason', tooltip: true,
    tip: '只在这条刊登未匹配到库存时显示原因；已匹配留空。'
  }
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
} = useColumnConfig(
  'operations:ebay:priceAnalysis:store',
  columnDefs,
  fixedColumnKeys,
  requiredColumnKeys,
  {},
  { owner_name: 'title', listing_start_time: 'owner_name' }
)

// SKU 维度列：库存取同站点的一份（后端 MAX），eBay 可售是各店铺相加。
const skuColumns = [
  { key: 'image_url', label: '图片', width: 70, fixed: true, align: 'center', format: 'image' },
  { key: 'site_name', label: '站点', width: 80, fixed: true, align: 'center' },
  { key: 'sku', label: 'SKU', minWidth: 160, fixed: true },
  { key: 'title', label: '产品名称', minWidth: 200, tooltip: true },
  { key: 'owner_name', label: '负责人', width: 100, sortable: true, tip: '按 eBay 品牌负责人规则匹配，与绩效排名、月度库存同一口径；规则里没有的品牌显示「未分配」。' },
  { key: 'store_count', label: '在售店铺数', width: 115, align: 'right', format: 'integer', sortable: true },
  {
    key: 'ebay_quantity_available', label: 'eBay可售合计', width: 125, align: 'right', format: 'integer', sortable: true,
    tip: '这个站点所有店铺的 eBay 可售相加。'
  },
  {
    key: 'overseas_sellable', label: '谷仓可售', width: 105, align: 'right', format: 'integer', sortable: true,
    tip: `谷仓区域仓接口每周快照（美国两仓合计）。${SHARED_STOCK_TIP}`
  },
  {
    key: 'chengdu_sellable', label: '成都可售', width: 105, align: 'right', format: 'integer', sortable: true,
    tip: `领星周快照。${SHARED_STOCK_TIP}`
  },
  { key: 'overseas_in_transit', label: '海外在途', width: 100, align: 'right', format: 'integer' },
  {
    key: 'unmatched_reason_text', label: '未匹配原因', minWidth: 220, format: 'reason', tooltip: true,
    tip: '这个站点 + SKU 下出现最多的未匹配原因；已匹配留空。'
  }
]
// 抽屉和展开行共用的两张对比表。
const compareSiteColumns = [
  { key: 'site_name', label: '站点', width: 80, align: 'center' },
  { key: 'overseas_sellable', label: '谷仓可售', width: 95, align: 'right', format: 'integer' },
  { key: 'chengdu_sellable', label: '成都可售', width: 95, align: 'right', format: 'integer' },
  { key: 'overseas_in_transit', label: '海外在途', width: 95, align: 'right', format: 'integer' },
  { key: 'pending_outbound', label: '待出库', width: 85, align: 'right', format: 'integer' },
  { key: 'store_count', label: '在售店铺数', width: 100, align: 'right', format: 'integer' },
  { key: 'ebay_available_total', label: 'eBay可售合计', minWidth: 115, align: 'right', format: 'integer' }
]
// 抽屉 920px 减去左右各 20px 内边距约 880px 可用；这张表要一眼扫完，列宽合计压在 870px 以内，不出横向滚动。
// 精简掉两列和售价旁的标签后，前几列放回宽松的宽度；未匹配原因是长句，超出部分悬停看全文。
const compareListingColumns = [
  { key: 'seller_account', label: '店铺', minWidth: 130, tooltip: true },
  { key: 'site_name', label: '站点', width: 70, align: 'center' },
  { key: 'item_id', label: 'Item ID', minWidth: 125, format: 'itemLink' },
  { key: 'current_price', label: '原币售价', width: 115, align: 'right', format: 'price' },
  { key: 'price_usd', label: '售价(USD)', width: 105, align: 'right', format: 'decimal' },
  { key: 'ebay_quantity_available', label: 'eBay可售', width: 85, align: 'right', format: 'integer' },
  { key: 'listing_start_time', label: '上架日期', width: 100, format: 'date' },
  { key: 'unmatched_reason_text', label: '未匹配原因', minWidth: 135, format: 'reason', tooltip: true }
]

const loading = computed(() => storesLoading.value || detailLoading.value || skuLoading.value)
const siteOptions = computed(() => {
  const fromData = stores.value.map(item => item.site).filter(Boolean)
  return [...new Set([...SITE_OPTIONS, ...fromData])]
})
// 选了店铺之后汇总表只剩这几家，下拉里的其他店铺不能跟着消失，所以累计记下见过的店铺。
const accountOptions = computed(() => [...new Set([...knownAccounts.value, ...query.accounts])])
const compareState = computed(() => skuListing(compareDrawer.sku))

function displayValue(value) {
  return value === null || value === undefined || value === '' ? '—' : value
}
function integer(value) {
  if (value === null || value === undefined || String(value).trim() === '') return '—'
  const numeric = Number(value)
  return Number.isFinite(numeric) ? numeric.toLocaleString('zh-CN', { maximumFractionDigits: 0 }) : '—'
}
function decimal(value) {
  if (value === null || value === undefined || String(value).trim() === '') return '—'
  const numeric = Number(value)
  return Number.isFinite(numeric)
    ? numeric.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
    : '—'
}
// MySQL 的布尔列经 Python / Java 转发后可能是 true、1 或 '1'。
function isTrue(value) {
  return value === true || value === 1 || value === '1' || value === 'true'
}
// 未匹配原因只在未匹配时显示，已匹配留空。原因文案由后端刷表时写入 unmatched_reason_text，前端不判定；
// 后端上线前没有这个字段时，明细里 inventory_matched=0 的行先显示「未匹配」，不会整列空白。
function unmatchedReason(row) {
  const matched = row?.inventory_matched
  if (isTrue(matched)) return ''
  const text = String(row?.unmatched_reason_text ?? '').trim()
  if (text) return text
  return matched === 0 || matched === '0' || matched === false ? '未匹配' : ''
}
function cellText(row, col) {
  const value = row?.[col.key]
  switch (col.format) {
    case 'image':
      return '—'
    case 'skuLink':
      return displayValue(row?.sku)
    case 'integer':
      return integer(value)
    case 'decimal':
      return decimal(value)
    case 'price': {
      const price = decimal(row?.current_price)
      return price === '—' || !row?.currency ? price : `${price} ${row.currency}`
    }
    case 'reason':
      return unmatchedReason(row)
    case 'date':
      return value ? String(value).slice(0, 10) : '—'
    default:
      return displayValue(value)
  }
}
function cellClass(row, col) {
  return cellText(row, col) === '—' ? 'muted' : ''
}
function csv(value) {
  if (Array.isArray(value)) {
    const items = value.map(item => String(item === null || item === undefined ? '' : item).trim()).filter(Boolean)
    return items.length ? items.join(',') : undefined
  }
  const text = String(value === null || value === undefined ? '' : value).trim()
  return text || undefined
}
function flag(value) {
  return value ? 'true' : undefined
}
function storeKey(row) {
  return `${row?.seller_account ?? ''}|${row?.site ?? ''}`
}
function skuRowKey(row) {
  return `${row?.site ?? ''}|${row?.sku ?? ''}`
}

function buildFilterParams() {
  return {
    sites: csv(query.sites),
    accounts: csv(query.accounts),
    keyword: csv(query.keyword),
    unmatched: flag(query.onlyUnmatched)
  }
}
function buildStoreParams() {
  return { sites: csv(query.sites), accounts: csv(query.accounts) }
}
// 选中店铺后明细只看这一个「店铺 + 站点」，页头的站点 / 店铺多选不再叠加。
function buildStoreDetailParams() {
  const store = selectedStore.value
  return {
    ...buildFilterParams(),
    accounts: csv(store?.seller_account),
    sites: csv(store?.site),
    mode: 'detail',
    sortBy: csv(detailPage.sortBy),
    sortOrder: csv(detailPage.sortOrder),
    pageNum: detailPage.pageNum,
    pageSize: detailPage.pageSize
  }
}
function buildSkuParams() {
  return {
    ...buildFilterParams(),
    mode: 'summary',
    sortBy: csv(skuPage.sortBy),
    sortOrder: csv(skuPage.sortOrder),
    pageNum: skuPage.pageNum,
    pageSize: skuPage.pageSize
  }
}
function buildExportParams() {
  const page = activeTab.value === 'sku' ? skuPage : detailPage
  return {
    ...buildFilterParams(),
    mode: activeTab.value === 'sku' ? 'summary' : 'detail',
    sortBy: csv(page.sortBy),
    sortOrder: csv(page.sortOrder)
  }
}
// 页头的快照日期取列表接口顶层的 stat_date / refreshed_at。
function applySnapshot(data) {
  if (!data || typeof data !== 'object') return
  if (data.stat_date) snapshot.stat_date = data.stat_date
  if (data.refreshed_at) snapshot.refreshed_at = data.refreshed_at
}
function rememberAccounts(rows) {
  const accounts = rows.map(item => item?.seller_account).filter(Boolean)
  knownAccounts.value = [...new Set([...knownAccounts.value, ...accounts])].sort()
}

async function loadStores() {
  const seq = ++storesSeq
  storesLoading.value = true
  try {
    const response = await listEbayPriceAnalysisStores(buildStoreParams())
    if (seq !== storesSeq) return
    const data = response.data || {}
    applySnapshot(data)
    stores.value = Array.isArray(data.rows) ? data.rows : []
    rememberAccounts(stores.value)
    // 筛选后原来选中的店铺还在就保持；不在了默认选第一家，免得下半部分空着。
    const current = selectedStore.value && stores.value.find(item => storeKey(item) === storeKey(selectedStore.value))
    selectedStore.value = current || stores.value[0] || null
  } finally {
    if (seq === storesSeq) storesLoading.value = false
  }
}
async function loadStoreDetail() {
  const seq = ++detailSeq
  if (!selectedStore.value) {
    detailRows.value = []
    detailTotal.value = 0
    detailLoading.value = false
    return
  }
  detailLoading.value = true
  try {
    const response = await listEbayPriceAnalysisDetail(buildStoreDetailParams())
    if (seq !== detailSeq) return
    const data = response.data || {}
    applySnapshot(data)
    detailRows.value = Array.isArray(data.rows) ? data.rows : []
    detailTotal.value = Number(data.total || 0)
  } finally {
    if (seq === detailSeq) detailLoading.value = false
  }
}
async function loadSkuRows() {
  const seq = ++skuSeq
  skuLoading.value = true
  try {
    const response = await listEbayPriceAnalysisDetail(buildSkuParams())
    if (seq !== skuSeq) return
    const data = response.data || {}
    applySnapshot(data)
    skuRows.value = Array.isArray(data.rows) ? data.rows : []
    skuTotal.value = Number(data.total || 0)
  } finally {
    if (seq === skuSeq) skuLoading.value = false
  }
}
async function loadActiveTab() {
  const tab = activeTab.value
  const version = filterVersion
  if (tab === 'sku') await loadSkuRows()
  else await loadStoreDetail()
  loadedVersion[tab] = version
}
function clearSkuListings() {
  for (const key of Object.keys(skuListings)) delete skuListings[key]
}
function resetPages() {
  detailPage.pageNum = 1
  skuPage.pageNum = 1
}
// 站点 / 店铺变了：店铺汇总和当前页签都要重拉；「刷新」也走这里，顺带清掉跨店对比的缓存。
async function handleQuery() {
  filterVersion += 1
  resetPages()
  clearSkuListings()
  await loadStores()
  await loadActiveTab()
}
// 关键词和「只看未匹配」只作用于明细，不影响店铺汇总。
function handleListFilter() {
  filterVersion += 1
  resetPages()
  return loadActiveTab()
}
function resetQuery() {
  query.sites = []
  query.accounts = []
  query.keyword = undefined
  query.onlyUnmatched = false
  detailPage.sortBy = undefined
  detailPage.sortOrder = undefined
  skuPage.sortBy = undefined
  skuPage.sortOrder = undefined
  selectedStore.value = null
  return handleQuery()
}
function handleTabChange() {
  if (loadedVersion[activeTab.value] === filterVersion) return undefined
  return loadActiveTab()
}
function selectStore(row) {
  if (!row) return undefined
  selectedStore.value = { seller_account: row.seller_account, site: row.site, site_name: row.site_name }
  detailPage.pageNum = 1
  return loadStoreDetail()
}
// 点汇总表里的「未匹配」数字：选中这家店并打开「只看未匹配」。
function focusStore(row) {
  query.onlyUnmatched = true
  filterVersion += 1
  loadedVersion.store = filterVersion
  return selectStore(row)
}
function sortState({ prop, order }) {
  return {
    sortBy: order ? prop : undefined,
    sortOrder: order === 'ascending' ? 'asc' : (order === 'descending' ? 'desc' : undefined)
  }
}
function handleDetailSort(event) {
  Object.assign(detailPage, sortState(event), { pageNum: 1 })
  return loadStoreDetail()
}
function handleSkuSort(event) {
  Object.assign(skuPage, sortState(event), { pageNum: 1 })
  return loadSkuRows()
}
function storeRowClass({ row }) {
  return selectedStore.value && storeKey(row) === storeKey(selectedStore.value) ? 'is-selected' : ''
}
function compareSiteRowClass({ row }, site) {
  return site && row?.site === site ? 'is-origin' : ''
}
function compareListingRowClass({ row }, origin) {
  if (!origin) return ''
  if (origin.seller_account) {
    return row?.seller_account === origin.seller_account && row?.site === origin.site ? 'is-origin' : ''
  }
  return row?.site === origin.site ? 'is-origin' : ''
}

const EMPTY_LISTING = Object.freeze({ loading: false, error: false, data: null })
function skuListing(sku) {
  const key = String(sku === null || sku === undefined ? '' : sku).trim()
  return (key && skuListings[key]) || EMPTY_LISTING
}
// 同一个 SKU 在抽屉和展开行之间共用一份结果；失败的不缓存，再点一次会重试。
async function ensureSkuListings(sku) {
  const key = String(sku === null || sku === undefined ? '' : sku).trim()
  if (!key) return undefined
  const cached = skuListings[key]
  if (cached && (cached.loading || cached.data)) return cached
  skuListings[key] = { loading: true, error: false, data: null }
  try {
    const response = await getEbayPriceAnalysisSkuListings(key)
    const data = response.data || {}
    skuListings[key] = {
      loading: false,
      error: false,
      data: {
        ...data,
        listings: Array.isArray(data.listings) ? data.listings : [],
        sites: Array.isArray(data.sites) ? data.sites : []
      }
    }
  } catch (error) {
    skuListings[key] = { loading: false, error: true, data: null }
  }
  return skuListings[key]
}
function openCompare(row) {
  if (!row?.sku) return undefined
  compareDrawer.sku = String(row.sku).trim()
  compareDrawer.origin = { seller_account: row.seller_account, site: row.site }
  compareDrawer.visible = true
  return ensureSkuListings(compareDrawer.sku)
}
function handleSkuExpand(row, expanded) {
  const opened = Array.isArray(expanded) ? expanded.includes(row) : Boolean(expanded)
  if (!opened) return undefined
  return ensureSkuListings(row?.sku)
}

async function handleExport() {
  if (!checkPermi(['operations:ebayPriceAnalysis:export'])) {
    ElMessage.warning('没有价格分析导出权限，请联系管理员授权')
    return
  }
  if (exporting.value || loading.value) return
  exporting.value = true
  try {
    await exportEbayPriceAnalysis(buildExportParams())
  } finally {
    exporting.value = false
  }
}

onMounted(async () => {
  await initColumnConfig()
  await handleQuery()
})
</script>

<style scoped>
.ebay-price-analysis {
  background: var(--jb-page, #f5f7fb);
  min-height: calc(100vh - 84px);
}
.ebay-price-analysis :deep(.el-card) {
  border: 1px solid var(--jb-line, #e3e9f2);
  border-radius: 12px;
  box-shadow: var(--jb-sh-1, 0 1px 2px rgba(16, 42, 90, .04), 0 4px 16px rgba(16, 42, 90, .05));
}
.head-card,
.table-card,
.note-card {
  margin-bottom: 14px;
}
.head-top {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}
.head-title h2 {
  margin: 0;
  font-size: 20px;
  color: var(--jb-ink-700, #24334a);
}
.head-meta {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
  margin: 6px 0 0;
  font-size: 13px;
  color: var(--jb-ink-300, #94a0b1);
}
.head-meta strong {
  color: var(--jb-ink-700, #24334a);
  font-weight: 600;
}
.meta-sep {
  color: #dcdfe6;
}
.head-acts {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.head-acts .el-button,
.filter-form :deep(.el-button),
.table-tools .el-button {
  border-radius: 8px;
  font-weight: 500;
}
.report-icon {
  margin-right: 6px;
  vertical-align: -2px;
}
.btn-icon {
  margin-right: 5px;
  vertical-align: -2px;
}
.snapshot-alert {
  margin: 12px 0 4px;
}
.filter-form {
  margin-top: 8px;
}
.filter-form :deep(.el-form-item) {
  margin-bottom: 10px;
}
.filter-form :deep(.el-form-item__label) {
  color: var(--jb-ink-500, #5a6b85);
  font-weight: 500;
}
.filter-control {
  width: 220px;
}
.dimension-tabs :deep(.el-tabs__header) {
  margin-bottom: 12px;
}
.dimension-tabs :deep(.el-tabs__item) {
  font-size: 14px;
}
.section-head {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-end;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 10px;
}
.section-head--detail {
  margin-top: 18px;
  padding-top: 14px;
  border-top: 1px dashed var(--jb-line, #e3e9f2);
}
.section-head__text {
  display: flex;
  flex-direction: column;
  min-width: 0;
}
.section-head__text small {
  margin-top: 2px;
  font-size: 12px;
  color: var(--jb-ink-300, #94a0b1);
}
.card-title {
  font-weight: 600;
  color: var(--jb-ink-700, #24334a);
}
.table-tools {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
}
/* 表格统一品牌表头 */
.table-card :deep(.el-table),
.sku-compare-drawer .el-table {
  --el-table-header-bg-color: #f5f8fd;
  --el-table-header-text-color: #51627c;
  --el-table-border-color: var(--jb-line, #e3e9f2);
  --el-table-row-hover-bg-color: rgba(18, 87, 214, .055);
}
.store-table :deep(.el-table__row) {
  cursor: pointer;
}
.store-table :deep(.el-table__row.is-selected > td.el-table__cell) {
  background: rgba(18, 87, 214, .08);
}
.store-table :deep(.el-table__row.is-selected > td.el-table__cell:first-child) {
  box-shadow: inset 3px 0 0 var(--jb-brand-500, #1257d6);
}
.count-link {
  font-weight: 600;
}
.unmatched-reason {
  color: var(--jb-warn, #b88230);
}
.column-header {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  white-space: nowrap;
}
.column-tip {
  color: var(--jb-ink-300, #94a0b1);
  cursor: help;
}
.row-image {
  width: 46px;
  height: 46px;
  border-radius: 8px;
}
.sku-link {
  font-weight: 600;
}
.muted {
  color: #c0c4cc;
}
.expand-box {
  padding: 8px 16px 12px 52px;
}
.shared-hint {
  margin: 0 0 10px;
  padding: 8px 12px;
  border-radius: 8px;
  background: #fdf6ec;
  color: var(--jb-warn, #b88230);
  font-size: 13px;
}
.compare-title {
  margin: 12px 0 6px;
  font-size: 13px;
  font-weight: 600;
  color: var(--jb-ink-700, #24334a);
}
.ebay-price-analysis :deep(.el-table__row.is-origin > td.el-table__cell) {
  background: rgba(18, 87, 214, .07);
}
.note-list {
  margin: 0;
  padding-left: 18px;
  color: var(--jb-ink-500, #5a6b85);
  font-size: 13px;
  line-height: 2;
}
.note-key {
  color: var(--jb-warn, #b88230);
  font-weight: 600;
}
@media (max-width: 768px) {
  .head-acts,
  .table-tools {
    width: 100%;
  }
  .filter-control {
    width: 100%;
  }
  .filter-form :deep(.el-form-item) {
    display: block;
    margin-right: 0;
  }
  .expand-box {
    padding: 8px 4px 12px;
  }
}
</style>

<style>
/* 抽屉挂在 body 上，scoped 样式够不到；只在这个类名下生效。手机上不超出屏幕宽度 */
.sku-compare-drawer {
  max-width: 100vw;
}
.sku-compare-drawer .compare-head {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 12px;
}
.sku-compare-drawer .compare-image {
  flex: 0 0 auto;
  width: 64px;
  height: 64px;
  border-radius: 8px;
}
.sku-compare-drawer .compare-head__text {
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 0;
  color: #5a6b85;
  font-size: 13px;
}
.sku-compare-drawer .compare-head__text strong {
  color: #24334a;
  font-size: 15px;
}
.sku-compare-drawer .shared-hint {
  margin: 0 0 10px;
  padding: 8px 12px;
  border-radius: 8px;
  background: #fdf6ec;
  color: #b88230;
  font-size: 13px;
}
.sku-compare-drawer .compare-title {
  margin: 12px 0 6px;
  font-size: 13px;
  font-weight: 600;
  color: #24334a;
}
.sku-compare-drawer .unmatched-reason {
  color: #b88230;
}
.sku-compare-drawer .el-table {
  --el-table-header-bg-color: #f5f8fd;
  --el-table-header-text-color: #51627c;
  --el-table-border-color: #e3e9f2;
  --el-table-row-hover-bg-color: rgba(18, 87, 214, .055);
}
.sku-compare-drawer .el-table__row.is-origin > td.el-table__cell {
  background: rgba(18, 87, 214, .07);
}
</style>
