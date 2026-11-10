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
            <svg-icon icon-class="jmh-refresh" class="report-icon" :class="{ spinning: loading }" />刷新
          </el-button>
          <el-tooltip
            content="导出当前筛选下全部记录（店铺维度按刊登、SKU 维度按站点 + SKU），仅包含角色授权的导出字段；不受分页或页面隐藏列限制"
            placement="top"
          >
            <el-button
              type="warning"
              plain
              :loading="exporting"
              :disabled="loading"
              v-hasPermi="['operations:ebayPriceAnalysis:export']"
              @click="handleExport"
            >
              <svg-icon v-if="!exporting" icon-class="jmh-export" class="report-icon" />导出明细
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
        <el-form-item label="状态">
          <el-select
            v-model="query.status"
            clearable
            placeholder="全部状态"
            class="filter-control filter-control--status"
            @change="handleListFilter"
          >
            <el-option v-for="status in statusOptions" :key="status" :label="status" :value="status" />
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
          <el-checkbox v-model="query.onlySiteOversell" @change="handleListFilter">只看多店超卖</el-checkbox>
          <el-checkbox v-model="query.onlyOutOfStockListed" @change="handleListFilter">只看断货在售</el-checkbox>
        </el-form-item>
        <el-form-item label-width="0">
          <el-button type="primary" icon="Search" @click="handleQuery">搜索</el-button>
          <el-button icon="Refresh" @click="resetQuery">重置</el-button>
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
            empty-text="没有符合条件的店铺，换个站点或店铺试试"
            @row-click="selectStore"
          >
            <el-table-column prop="seller_account" label="店铺" min-width="150" show-overflow-tooltip />
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
            <el-table-column prop="out_of_stock_listed" width="110" align="right">
              <template #header>
                <span class="column-header">
                  <span>断货在售</span>
                  <el-tooltip content="已匹配到库存，谷仓可售 + 成都可售 = 0，但 eBay 可售 > 0 的刊登数；点数字只看这些" placement="top">
                    <el-icon class="column-tip"><QuestionFilled /></el-icon>
                  </el-tooltip>
                </span>
              </template>
              <template #default="{ row }">
                <el-link
                  v-if="Number(row.out_of_stock_listed) > 0"
                  type="warning"
                  :underline="false"
                  class="count-link"
                  @click.stop="focusStore(row, 'outOfStock')"
                >{{ integer(row.out_of_stock_listed) }}</el-link>
                <span v-else class="muted">{{ integer(row.out_of_stock_listed) }}</span>
              </template>
            </el-table-column>
            <el-table-column prop="site_oversell_sku_count" width="130" align="right">
              <template #header>
                <span class="column-header">
                  <span>多店超卖 SKU</span>
                  <el-tooltip content="本店在售的 SKU 里，同站点所有店铺 eBay 可售合计超过谷仓可售 + 成都可售的个数；点数字只看这些" placement="top">
                    <el-icon class="column-tip"><QuestionFilled /></el-icon>
                  </el-tooltip>
                </span>
              </template>
              <template #default="{ row }">
                <el-link
                  v-if="Number(row.site_oversell_sku_count) > 0"
                  type="danger"
                  :underline="false"
                  class="count-link count-link--danger"
                  @click.stop="focusStore(row, 'oversell')"
                >{{ integer(row.site_oversell_sku_count) }}</el-link>
                <span v-else class="muted">{{ integer(row.site_oversell_sku_count) }}</span>
              </template>
            </el-table-column>
            <el-table-column prop="unmatched_count" label="未匹配" width="90" align="right">
              <template #default="{ row }">{{ integer(row.unmatched_count) }}</template>
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
              <el-button icon="Setting" @click="openColumnConfig">自定义列</el-button>
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
              :row-class-name="oversellRowClass"
              border
              height="520"
              empty-text="这个店铺没有符合条件的刊登，换个状态、关键词或取消「只看」筛选试试"
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
                      <el-icon class="column-tip"><QuestionFilled /></el-icon>
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
                  <el-tag v-else-if="col.format === 'status'" :type="statusTagType(row.status)" effect="light">
                    {{ displayValue(row.status) }}
                  </el-tag>
                  <el-tooltip
                    v-else-if="col.format === 'oversell' && isTrue(row[col.key])"
                    :content="oversellTip(row)"
                    placement="top"
                  >
                    <el-tag type="danger" effect="dark" class="oversell-tag">多店超卖</el-tag>
                  </el-tooltip>
                  <el-tag
                    v-else-if="col.format === 'outOfStock' && isTrue(row[col.key])"
                    type="warning"
                    effect="dark"
                    class="oversell-tag"
                  >断货在售</el-tag>
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
            :row-class-name="oversellRowClass"
            border
            height="560"
            empty-text="没有符合条件的 SKU，换个站点、店铺、状态或关键词试试"
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
                        <template #default="scope">
                          <el-tooltip
                            v-if="col.format === 'oversell' && isTrue(scope.row[col.key])"
                            :content="oversellTip(scope.row)"
                            placement="top"
                          >
                            <el-tag type="danger" effect="dark" size="small" class="oversell-tag">多店超卖</el-tag>
                          </el-tooltip>
                          <span v-else>{{ cellText(scope.row, col) }}</span>
                        </template>
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
                          <el-tag v-else-if="col.format === 'status'" :type="statusTagType(scope.row.status)" size="small">
                            {{ displayValue(scope.row.status) }}
                          </el-tag>
                          <span v-else-if="col.format === 'usd'" class="usd-cell">
                            {{ decimal(scope.row.price_usd) }}
                            <el-tag
                              v-if="lowestListingKeys(skuListing(row.sku).data.listings).has(listingKey(scope.row))"
                              type="success"
                              size="small"
                              effect="plain"
                            >站点最低</el-tag>
                          </span>
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
                    <el-icon class="column-tip"><QuestionFilled /></el-icon>
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
                <span v-else-if="col.format === 'statuses'" class="status-tags">
                  <el-tag
                    v-for="status in toArray(row.statuses)"
                    :key="status"
                    :type="statusTagType(status)"
                    effect="light"
                    size="small"
                  >{{ status }}</el-tag>
                  <span v-if="!toArray(row.statuses).length" class="muted">—</span>
                </span>
                <el-tooltip
                  v-else-if="col.format === 'oversell' && isTrue(row[col.key])"
                  :content="oversellTip(row)"
                  placement="top"
                >
                  <el-tag type="danger" effect="dark" class="oversell-tag">多店超卖</el-tag>
                </el-tooltip>
                <el-tag
                  v-else-if="col.format === 'outOfStock' && isTrue(row[col.key])"
                  type="warning"
                  effect="dark"
                  class="oversell-tag"
                >断货在售</el-tag>
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
        <li>多店超卖：同站点所有店铺 eBay 可售合计 &gt; 该站点谷仓可售 + 成都可售；多个店铺共用一个仓，单看一个店铺看不出来</li>
        <li>断货在售：已匹配到库存，谷仓可售 + 成都可售 = 0，但 eBay 可售 &gt; 0；一条刊登可以同时是断货在售和多店超卖，两个标记都会显示</li>
        <li>比最低价高出 =（本店 USD 售价 − 同站点最低 USD 售价）÷ 同站点最低 USD 售价</li>
        <li>售价按站点币种和领星月度企业汇率折算 USD；当月汇率未出时，沿用该币种最近一个已出月份的汇率；完全没有汇率时不折算</li>
        <li>采购成本取订单文件中的真实采购成本，未参与售价估算</li>
        <li>未关联到库存的 listing 计入「未匹配」，不计入断货在售与多店超卖判断</li>
      </ul>
    </el-card>

    <!-- ===== 这个 SKU 在其他店铺 ===== -->
    <el-drawer
      v-model="compareDrawer.visible"
      size="820px"
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
            <template #default="scope">
              <el-tooltip
                v-if="col.format === 'oversell' && isTrue(scope.row[col.key])"
                :content="oversellTip(scope.row)"
                placement="top"
              >
                <el-tag type="danger" effect="dark" size="small" class="oversell-tag">多店超卖</el-tag>
              </el-tooltip>
              <span v-else>{{ cellText(scope.row, col) }}</span>
            </template>
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
              <el-tag v-else-if="col.format === 'status'" :type="statusTagType(scope.row.status)" size="small">
                {{ displayValue(scope.row.status) }}
              </el-tag>
              <span v-else-if="col.format === 'usd'" class="usd-cell">
                {{ decimal(scope.row.price_usd) }}
                <el-tag
                  v-if="compareLowestKeys.has(listingKey(scope.row))"
                  type="success"
                  size="small"
                  effect="plain"
                >站点最低</el-tag>
              </span>
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

// 状态、多店超卖、断货在售、跨店比价都由后端算好，前端只按返回值渲染和筛选，不自己推导。
const statusOptions = ['未匹配', '超卖风险', '断货', '待补货', '滞销', '健康']
const STATUS_TAG_TYPE = {
  未匹配: 'info',
  超卖风险: 'danger',
  断货: 'danger',
  待补货: 'warning',
  滞销: 'primary',
  健康: 'success'
}
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
  status: undefined,
  keyword: undefined,
  onlySiteOversell: false,
  onlyOutOfStockListed: false
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
    key: 'site_price_range', label: '同站点最低 / 最高价(USD)', width: 190, align: 'right', format: 'range',
    minKey: 'site_price_usd_min', maxKey: 'site_price_usd_max'
  },
  {
    key: 'price_vs_site_min_pct', label: '比最低价高出', width: 130, align: 'right', format: 'pct',
    tip: '（本店 USD 售价 − 同站点最低 USD 售价）÷ 同站点最低 USD 售价；任一价格缺失时显示「—」。'
  },
  {
    key: 'site_oversell', label: '多店超卖', width: 105, align: 'center', format: 'oversell',
    tip: '同站点所有店铺 eBay 可售合计 > 该站点谷仓可售 + 成都可售。'
  },
  {
    key: 'out_of_stock_listed', label: '断货在售', width: 105, align: 'center', format: 'outOfStock',
    tip: '已匹配到库存，谷仓可售 + 成都可售 = 0，但 eBay 可售 > 0。可以和多店超卖同时出现。'
  },
  { key: 'status', label: '状态', width: 100, align: 'center', format: 'status' }
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
  requiredColumnKeys
)

// SKU 维度列：库存取同站点的一份（后端 MAX），eBay 可售是各店铺相加。
const skuColumns = [
  { key: 'image_url', label: '图片', width: 70, fixed: true, align: 'center', format: 'image' },
  { key: 'site_name', label: '站点', width: 80, fixed: true, align: 'center' },
  { key: 'sku', label: 'SKU', minWidth: 160, fixed: true },
  { key: 'title', label: '产品名称', minWidth: 200, tooltip: true },
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
    key: 'price_range', label: '最低 / 最高价(USD)', width: 170, align: 'right', format: 'range',
    minKey: 'price_usd_min', maxKey: 'price_usd_max'
  },
  {
    key: 'site_oversell', label: '多店超卖', width: 105, align: 'center', format: 'oversell',
    tip: '这个站点所有店铺 eBay 可售合计 > 谷仓可售 + 成都可售。'
  },
  {
    key: 'out_of_stock_listed', label: '断货在售', width: 105, align: 'center', format: 'outOfStock',
    tip: '这个站点有店铺在库存为 0 时仍挂着 eBay 可售。可以和多店超卖同时出现。'
  },
  { key: 'statuses', label: '状态', minWidth: 130, format: 'statuses' }
]
// 抽屉和展开行共用的两张对比表。
const compareSiteColumns = [
  { key: 'site_name', label: '站点', width: 80, align: 'center' },
  { key: 'overseas_sellable', label: '谷仓可售', width: 95, align: 'right', format: 'integer' },
  { key: 'chengdu_sellable', label: '成都可售', width: 95, align: 'right', format: 'integer' },
  { key: 'overseas_in_transit', label: '海外在途', width: 95, align: 'right', format: 'integer' },
  { key: 'pending_outbound', label: '待出库', width: 85, align: 'right', format: 'integer' },
  { key: 'store_count', label: '在售店铺数', width: 100, align: 'right', format: 'integer' },
  { key: 'ebay_available_total', label: 'eBay可售合计', minWidth: 115, align: 'right', format: 'integer' },
  { key: 'site_oversell', label: '多店超卖', width: 100, align: 'center', format: 'oversell' }
]
const compareListingColumns = [
  { key: 'seller_account', label: '店铺', minWidth: 140, tooltip: true },
  { key: 'site_name', label: '站点', width: 70, align: 'center' },
  { key: 'item_id', label: 'Item ID', minWidth: 130, format: 'itemLink' },
  { key: 'current_price', label: '原币售价', width: 115, align: 'right', format: 'price' },
  { key: 'price_usd', label: '售价(USD)', width: 160, align: 'right', format: 'usd' },
  { key: 'ebay_quantity_available', label: 'eBay可售', width: 90, align: 'right', format: 'integer' },
  { key: 'status', label: '状态', width: 90, align: 'center', format: 'status' }
]

const loading = computed(() => storesLoading.value || detailLoading.value || skuLoading.value)
const siteOptions = computed(() => {
  const fromData = stores.value.map(item => item.site).filter(Boolean)
  return [...new Set([...SITE_OPTIONS, ...fromData])]
})
// 选了店铺之后汇总表只剩这几家，下拉里的其他店铺不能跟着消失，所以累计记下见过的店铺。
const accountOptions = computed(() => [...new Set([...knownAccounts.value, ...query.accounts])])
const compareState = computed(() => skuListing(compareDrawer.sku))
const compareLowestKeys = computed(() => lowestListingKeys(compareState.value.data?.listings))

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
// 后端给的是比例（0.125 = 高 12.5%），只换算成百分比显示，不自己算。
function percent(value) {
  if (value === null || value === undefined || String(value).trim() === '') return '—'
  const numeric = Number(value)
  if (!Number.isFinite(numeric)) return '—'
  if (numeric === 0) return '最低价'
  const text = `${(numeric * 100).toFixed(1)}%`
  return numeric > 0 ? `+${text}` : text
}
function pctClass(value) {
  if (value === null || value === undefined || String(value).trim() === '') return 'muted'
  const numeric = Number(value)
  if (!Number.isFinite(numeric)) return 'muted'
  if (numeric === 0) return 'price-lowest'
  return numeric >= 0.2 ? 'price-high' : 'price-above'
}
// MySQL 的布尔列经 Python / Java 转发后可能是 true、1 或 '1'。
function isTrue(value) {
  return value === true || value === 1 || value === '1' || value === 'true'
}
function statusTagType(status) {
  return STATUS_TAG_TYPE[status] || 'info'
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
    case 'range': {
      const low = decimal(row?.[col.minKey])
      const high = decimal(row?.[col.maxKey])
      if (low === '—' && high === '—') return '—'
      return low === high ? low : `${low} ~ ${high}`
    }
    case 'pct':
      return percent(value)
    case 'oversell':
      return isTrue(value) ? '多店超卖' : '—'
    case 'outOfStock':
      return isTrue(value) ? '断货在售' : '—'
    default:
      return displayValue(value)
  }
}
function cellClass(row, col) {
  if (col.format === 'pct') return pctClass(row?.[col.key])
  return cellText(row, col) === '—' ? 'muted' : ''
}
function oversellTip(row) {
  const storeCount = row?.site_store_count ?? row?.store_count
  const ebayTotal = row?.site_ebay_available_total ?? row?.ebay_available_total ?? row?.ebay_quantity_available
  return `同站点 ${integer(storeCount)} 个店铺 eBay 可售合计 ${integer(ebayTotal)}，`
    + `超过谷仓可售 ${integer(row?.overseas_sellable)} + 成都可售 ${integer(row?.chengdu_sellable)}`
}
function toArray(value) {
  if (Array.isArray(value)) return value.map(item => String(item).trim()).filter(Boolean)
  const text = String(value === null || value === undefined ? '' : value).trim()
  return text ? text.split(',').map(item => item.trim()).filter(Boolean) : []
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
function listingKey(row) {
  return `${row?.seller_account ?? ''}|${row?.site ?? ''}|${row?.item_id ?? ''}`
}
// 接口按 site、price_usd 升序给 listings，每个站点第一条有价格的就是站点最低价，不在前端比价。
function lowestListingKeys(listings) {
  const keys = new Set()
  const seen = new Set()
  for (const item of Array.isArray(listings) ? listings : []) {
    if (seen.has(item?.site) || item?.price_usd === null || item?.price_usd === undefined) continue
    seen.add(item.site)
    keys.add(listingKey(item))
  }
  return keys
}

function buildFilterParams() {
  return {
    sites: csv(query.sites),
    accounts: csv(query.accounts),
    status: csv(query.status),
    keyword: csv(query.keyword),
    siteOversell: flag(query.onlySiteOversell),
    outOfStockListed: flag(query.onlyOutOfStockListed)
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
// 状态、关键词和两个「只看」只作用于明细，不影响店铺汇总。
function handleListFilter() {
  filterVersion += 1
  resetPages()
  return loadActiveTab()
}
function resetQuery() {
  query.sites = []
  query.accounts = []
  query.status = undefined
  query.keyword = undefined
  query.onlySiteOversell = false
  query.onlyOutOfStockListed = false
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
// 点汇总表里的「断货在售」「多店超卖 SKU」数字：选中这家店并打开对应的「只看」。
function focusStore(row, kind) {
  if (kind === 'oversell') query.onlySiteOversell = true
  if (kind === 'outOfStock') query.onlyOutOfStockListed = true
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
// 两个标记各自独立：同时满足时两个 class 都挂上，不互相覆盖。
function oversellRowClass({ row }) {
  const classes = []
  if (isTrue(row?.site_oversell)) classes.push('is-oversell')
  if (isTrue(row?.out_of_stock_listed)) classes.push('is-out-of-stock')
  return classes.join(' ')
}
function compareSiteRowClass({ row }, site) {
  const classes = []
  if (site && row?.site === site) classes.push('is-origin')
  if (isTrue(row?.site_oversell)) classes.push('is-oversell')
  return classes.join(' ')
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
  background: #f5f7fa;
  min-height: calc(100vh - 84px);
}
.ebay-price-analysis :deep(.el-card) {
  border: 0;
  border-radius: 10px;
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
  color: #303133;
}
.head-meta {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
  margin: 6px 0 0;
  font-size: 13px;
  color: #909399;
}
.head-meta strong {
  color: #303133;
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
/* 自有图标库 jmh-refresh / jmh-export。按钮带文字，图标不设 color，
   用 currentColor 跟随按钮文字色（导出按钮即 warning 橙色）；loading 时刷新图标旋转 */
.report-icon {
  margin-right: 6px;
  font-size: 16px;
}
.report-icon.spinning {
  animation: report-icon-spin 1s linear infinite;
}
@keyframes report-icon-spin {
  to {
    transform: rotate(360deg);
  }
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
.filter-control {
  width: 220px;
}
.filter-control--status {
  width: 150px;
}
.dimension-tabs :deep(.el-tabs__header) {
  margin-bottom: 12px;
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
  border-top: 1px dashed #e4e7ed;
}
.section-head__text {
  display: flex;
  flex-direction: column;
  min-width: 0;
}
.section-head__text small {
  margin-top: 2px;
  font-size: 12px;
  color: #909399;
}
.card-title {
  font-weight: 600;
  color: #303133;
}
.table-tools {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
}
.store-table :deep(.el-table__row) {
  cursor: pointer;
}
.store-table :deep(.el-table__row.is-selected > td.el-table__cell) {
  background: #ecf5ff;
}
.store-table :deep(.el-table__row.is-selected > td.el-table__cell:first-child) {
  box-shadow: inset 3px 0 0 #409eff;
}
.count-link {
  font-weight: 600;
}
.count-link--danger {
  font-size: 15px;
}
/* 多店超卖要一眼看到：整行浅红底 + 实心红标签 */
.ebay-price-analysis :deep(.el-table__row.is-oversell > td.el-table__cell) {
  background: #fef0f0;
}
.oversell-tag {
  font-weight: 600;
}
.price-lowest {
  color: #67c23a;
}
.price-above {
  color: #e6a23c;
  font-weight: 600;
}
.price-high {
  color: #f56c6c;
  font-weight: 600;
}
.status-tags {
  display: inline-flex;
  flex-wrap: wrap;
  gap: 4px;
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
.row-image {
  width: 46px;
  height: 46px;
  border-radius: 6px;
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
  border-radius: 6px;
  background: #fdf6ec;
  color: #b88230;
  font-size: 13px;
}
.compare-title {
  margin: 12px 0 6px;
  font-size: 13px;
  font-weight: 600;
  color: #303133;
}
.usd-cell {
  display: inline-flex;
  align-items: center;
  justify-content: flex-end;
  gap: 6px;
}
.ebay-price-analysis :deep(.el-table__row.is-origin > td.el-table__cell) {
  background: #ecf5ff;
}
.note-list {
  margin: 0;
  padding-left: 18px;
  color: #606266;
  font-size: 13px;
  line-height: 2;
}
.note-key {
  color: #b88230;
  font-weight: 600;
}
@media (max-width: 768px) {
  .head-acts,
  .table-tools {
    width: 100%;
  }
  .filter-control,
  .filter-control--status {
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
  color: #606266;
  font-size: 13px;
}
.sku-compare-drawer .compare-head__text strong {
  color: #303133;
  font-size: 15px;
}
.sku-compare-drawer .shared-hint {
  margin: 0 0 10px;
  padding: 8px 12px;
  border-radius: 6px;
  background: #fdf6ec;
  color: #b88230;
  font-size: 13px;
}
.sku-compare-drawer .compare-title {
  margin: 12px 0 6px;
  font-size: 13px;
  font-weight: 600;
  color: #303133;
}
.sku-compare-drawer .usd-cell {
  display: inline-flex;
  align-items: center;
  justify-content: flex-end;
  gap: 6px;
}
.sku-compare-drawer .el-table__row.is-origin > td.el-table__cell {
  background: #ecf5ff;
}
.sku-compare-drawer .el-table__row.is-oversell > td.el-table__cell {
  background: #fef0f0;
}
</style>
