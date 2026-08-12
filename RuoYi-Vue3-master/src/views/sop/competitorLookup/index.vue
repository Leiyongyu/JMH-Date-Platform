<template>
  <div class="competitor-page">
    <section class="page-head">
      <div>
        <span class="eyebrow">SOP · EBAY COMPETITOR</span>
        <h2>选竞品</h2>
        <p>保存合适的竞品，并按照站点公式实时测算利润。</p>
      </div>
      <div class="head-badges">
        <el-tag effect="plain" round>DE · EUR</el-tag>
        <el-tag type="success" effect="plain" round>UK · GBP</el-tag>
        <el-tag type="warning" effect="plain" round>US · USD</el-tag>
      </div>
    </section>

    <el-tabs v-model="activeTab" class="feature-tabs" @tab-change="handleTabChange">
      <el-tab-pane name="library">
        <template #label>
          <span class="tab-label"><el-icon><Collection /></el-icon>已保存商品库</span>
        </template>

        <section class="panel filter-panel">
          <el-form :model="filters" inline @submit.prevent>
            <el-form-item label="OE号">
              <el-input v-model.trim="filters.oe" clearable placeholder="输入OE号" @keyup.enter="handleSearch" />
            </el-form-item>
            <el-form-item label="SKU">
              <el-input v-model.trim="filters.sku" clearable placeholder="输入SKU" @keyup.enter="handleSearch" />
            </el-form-item>
            <el-form-item label="站点">
              <el-select v-model="filters.siteCode" clearable placeholder="全部站点" style="width: 140px">
                <el-option label="德国站 DE" value="DE" />
                <el-option label="英国站 UK" value="UK" />
                <el-option label="美国站 US" value="US" />
              </el-select>
            </el-form-item>
            <el-form-item>
              <el-button type="primary" :icon="Search" @click="handleSearch">查询</el-button>
              <el-button :icon="Refresh" @click="resetSearch">重置</el-button>
            </el-form-item>
          </el-form>
          <div class="filter-tip">OE和SKU支持模糊查询，两个条件同时填写时取交集。</div>
        </section>

        <section class="panel library-panel">
          <div class="panel-title">
            <div>
              <strong>已保存竞品</strong>
              <span>共 {{ total }} 条，已选择 {{ librarySelection.length }} 条；点击左侧箭头查看全部计算字段</span>
            </div>
            <div class="panel-actions">
              <el-dropdown
                v-hasPermi="['sop:competitor:export']"
                trigger="click"
                :disabled="exportLoading || total === 0"
                @command="handleExportCommand"
              >
                <el-button type="primary" plain :icon="Download" :loading="exportLoading">
                  导出商品库<el-icon class="el-icon--right"><ArrowDown /></el-icon>
                </el-button>
                <template #dropdown>
                  <el-dropdown-menu>
                    <el-dropdown-item command="selected" :disabled="librarySelection.length === 0">
                      导出选中（{{ librarySelection.length }}条）
                    </el-dropdown-item>
                    <el-dropdown-item command="all" divided>导出全部（{{ total }}条）</el-dropdown-item>
                  </el-dropdown-menu>
                </template>
              </el-dropdown>
              <el-button text type="primary" :icon="Refresh" :loading="libraryLoading" @click="loadLibrary">刷新</el-button>
            </div>
          </div>

          <el-table
            ref="libraryTableRef"
            v-loading="libraryLoading"
            :data="savedProducts"
            row-key="id"
            stripe
            class="library-table"
            empty-text="暂时没有已保存的竞品"
            @selection-change="handleLibrarySelection"
          >
            <el-table-column type="selection" width="46" fixed="left" reserve-selection />
            <el-table-column type="expand" width="42">
              <template #default="scope">
                <div class="detail-wrap">
                  <div class="detail-grid">
                    <div class="detail-item"><span>商品ID / 编号</span><b>{{ textValue(scope.row.ebayItemId) }}</b></div>
                    <div class="detail-item"><span>Marketplace</span><b>{{ textValue(scope.row.marketplaceId) }}</b></div>
                    <div class="detail-item"><span>长 × 宽 × 高</span><b>{{ dimensions(scope.row) }}</b></div>
                    <div class="detail-item"><span>实时汇率</span><b>{{ numberValue(scope.row.exchangeRate, 2) }}</b></div>
                    <div class="detail-item"><span>海运底价</span><b>{{ moneyValue(scope.row.seaFloorPrice, scope.row.currency) }}</b></div>
                    <div class="detail-item"><span>铁路底价</span><b>{{ moneyValue(scope.row.railFloorPrice, scope.row.currency) }}</b></div>
                    <div class="detail-item"><span>目标产品成本（海运）</span><b>¥ {{ numberValue(scope.row.targetProductCostSea, 2) }}</b></div>
                    <div class="detail-item"><span>目标产品成本（铁路）</span><b>{{ scope.row.targetProductCostRail == null ? '--' : `¥ ${numberValue(scope.row.targetProductCostRail, 2)}` }}</b></div>
                    <div class="detail-item"><span>公式版本</span><b>{{ textValue(scope.row.formulaVersion) }}</b></div>
                    <div class="detail-item"><span>更新时间</span><b>{{ parseTime(scope.row.updateTime || scope.row.createTime) }}</b></div>
                    <div class="detail-item detail-wide"><span>备注</span><b>{{ textValue(scope.row.remark) }}</b></div>
                    <div class="detail-item detail-wide"><span>参考链接</span><el-link :href="scope.row.referenceUrl" target="_blank" type="primary">{{ scope.row.referenceUrl }}</el-link></div>
                    <div class="detail-item detail-wide"><span>本地图片地址</span><b>{{ textValue(scope.row.localImageUrl) }}</b></div>
                    <div class="detail-item detail-wide image-gallery-detail">
                      <span>全部商品图片（{{ savedImageUrls(scope.row).length }}张）</span>
                      <div class="image-gallery">
                        <el-image
                          v-for="(url, imageIndex) in savedImageUrls(scope.row)"
                          :key="url"
                          class="gallery-thumb"
                          :src="url"
                          :preview-src-list="savedImageUrls(scope.row)"
                          :initial-index="imageIndex"
                          preview-teleported
                          fit="contain"
                        />
                      </div>
                    </div>
                  </div>
                </div>
              </template>
            </el-table-column>
            <el-table-column label="图片" width="82" fixed="left">
              <template #default="scope">
                <div class="image-cell">
                  <el-image
                    class="product-image"
                    :src="resourceUrl(scope.row.localImageUrl)"
                    :preview-src-list="savedImageUrls(scope.row)"
                    preview-teleported
                    fit="contain"
                  >
                    <template #error><div class="image-empty"><el-icon><Picture /></el-icon></div></template>
                  </el-image>
                  <span v-if="savedImageUrls(scope.row).length > 1" class="image-count">{{ savedImageUrls(scope.row).length }}张</span>
                </div>
              </template>
            </el-table-column>
            <el-table-column label="站点" prop="siteCode" width="72" align="center">
              <template #default="scope"><el-tag :type="siteTagType(scope.row.siteCode)" size="small">{{ scope.row.siteCode }}</el-tag></template>
            </el-table-column>
            <el-table-column label="OE" prop="oe" min-width="160" show-overflow-tooltip />
            <el-table-column label="SKU" prop="sku" min-width="155" show-overflow-tooltip />
            <el-table-column label="实际卖价" width="115" align="right">
              <template #default="scope"><b>{{ moneyValue(scope.row.salePrice, scope.row.currency) }}</b></template>
            </el-table-column>
            <el-table-column label="产品成本" width="105" align="right">
              <template #default="scope">¥ {{ numberValue(scope.row.productCostCny, 2) }}</template>
            </el-table-column>
            <el-table-column label="体积重 / 实重" width="128" align="center">
              <template #default="scope">{{ numberValue(scope.row.volumetricWeightKg, 2) }} / {{ numberValue(scope.row.actualWeightKg, 3) }} kg</template>
            </el-table-column>
            <el-table-column label="海运利润率" width="105" align="right">
              <template #default="scope"><span :class="rateClass(scope.row.seaProfitRate)">{{ rateValue(scope.row.seaProfitRate) }}</span></template>
            </el-table-column>
            <el-table-column label="铁路利润率" width="105" align="right">
              <template #default="scope"><span :class="rateClass(scope.row.railProfitRate)">{{ rateValue(scope.row.railProfitRate) }}</span></template>
            </el-table-column>
            <el-table-column label="目标利润率" width="105" align="right">
              <template #default="scope">{{ rateValue(scope.row.targetProfitRate) }}</template>
            </el-table-column>
            <el-table-column label="保存人" prop="createBy" width="100" show-overflow-tooltip />
            <el-table-column label="保存时间" width="155">
              <template #default="scope">{{ parseTime(scope.row.createTime) }}</template>
            </el-table-column>
            <el-table-column label="操作" width="172" fixed="right" align="center">
              <template #default="scope">
                <el-link :href="scope.row.referenceUrl" target="_blank" type="primary">链接</el-link>
                <el-button v-hasPermi="['sop:competitor:edit']" link type="primary" @click="openEdit(scope.row)">编辑</el-button>
                <el-button
                  v-hasPermi="['sop:competitor:remove']"
                  link type="danger"
                  :loading="deletingId === scope.row.id"
                  @click="handleDelete(scope.row)"
                >删除</el-button>
              </template>
            </el-table-column>
          </el-table>

          <pagination
            v-show="total > 0"
            :total="total"
            v-model:page="filters.pageNum"
            v-model:limit="filters.pageSize"
            @pagination="loadLibrary"
          />
        </section>
      </el-tab-pane>

      <el-tab-pane name="calculator">
        <template #label>
          <span class="tab-label"><el-icon><DataAnalysis /></el-icon>拉取商品并测算</span>
        </template>

        <section class="panel query-panel">
          <div class="query-row">
            <el-input
              v-model.trim="queryUrl"
              size="large"
              clearable
              placeholder="输入eBay商品链接，例如：https://www.ebay.co.uk/itm/186929412574"
              @keyup.enter="handleQuery"
            >
              <template #prefix><el-icon><Link /></el-icon></template>
            </el-input>
            <el-button
              v-hasPermi="['sop:competitor:query']"
              type="primary"
              size="large"
              :loading="queryLoading"
              :disabled="batchRunning"
              :icon="Search"
              @click="handleQuery"
            >拉取商品</el-button>
            <el-upload
              ref="linkUploadRef"
              v-hasPermi="['sop:competitor:import']"
              action="#"
              accept=".xlsx,.xls,.xlsm"
              :auto-upload="false"
              :show-file-list="false"
              :disabled="batchParsing || batchRunning"
              :on-change="handleLinkFileChange"
            >
              <el-button size="large" :icon="Upload" :loading="batchParsing" :disabled="batchRunning">
                批量导入链接
              </el-button>
            </el-upload>
            <el-button v-if="drafts.length" size="large" :icon="Delete" @click="clearDrafts">清空</el-button>
          </div>
          <div class="query-hints">
            <span><i></i>链接自动识别DE、UK、US站点</span>
            <span>批量模板：A1为“参考链接”，A2起每行一个链接，最多500个</span>
            <span>接口获取全部商品图片、实际卖价和商品链接</span>
            <span>体积重 = 长 × 宽 × 高 ÷ 6000</span>
            <span>保存时后端会重新拉取价格并复算</span>
          </div>

          <div v-if="batchItems.length" class="batch-card">
            <div class="batch-head">
              <div>
                <strong>{{ batchFileName }}</strong>
                <span>共 {{ batchItems.length }} 个 · 成功 {{ batchSuccessCount }} · 失败 {{ batchFailedCount }} · 待处理 {{ batchPendingCount }}</span>
              </div>
              <div class="batch-actions">
                <el-button v-if="batchRunning" type="warning" plain size="small" @click="stopBatch">完成当前条后停止</el-button>
                <el-button v-else-if="batchPendingCount" type="primary" plain size="small" @click="processBatch">继续抓取</el-button>
                <el-button v-if="!batchRunning && batchFailedCount" size="small" @click="retryFailedBatch">重试失败项</el-button>
                <el-button v-if="!batchRunning" text size="small" @click="clearBatch">清除记录</el-button>
              </div>
            </div>
            <el-progress :percentage="batchProgress" :status="batchProgressStatus" :stroke-width="8" />
            <div v-if="batchCurrentItem" class="batch-current">
              正在处理第 {{ batchCurrentItem.index }} / {{ batchItems.length }} 个：{{ batchCurrentItem.url }}
            </div>
            <el-collapse class="batch-detail">
              <el-collapse-item name="detail">
                <template #title>查看逐条抓取明细</template>
                <el-table :data="batchItems" size="small" max-height="260" stripe>
                  <el-table-column label="#" prop="index" width="55" />
                  <el-table-column label="商品链接" prop="url" min-width="420" show-overflow-tooltip />
                  <el-table-column label="状态" width="90" align="center">
                    <template #default="scope"><el-tag :type="batchStatusType(scope.row.status)" size="small">{{ batchStatusText(scope.row.status) }}</el-tag></template>
                  </el-table-column>
                  <el-table-column label="结果" min-width="230" show-overflow-tooltip>
                    <template #default="scope">{{ scope.row.message || '--' }}</template>
                  </el-table-column>
                </el-table>
              </el-collapse-item>
            </el-collapse>
          </div>
        </section>

        <section class="panel draft-panel">
          <div class="panel-title">
            <div>
              <strong>待判断商品</strong>
              <span>共 {{ drafts.length }} 条，每页10条；横向滚动填写全部字段</span>
            </div>
            <div class="legend"><i class="manual"></i>人工填写 <i class="calculated"></i>自动计算</div>
          </div>

          <el-table
            v-loading="queryLoading"
            :data="pagedDrafts"
            row-key="_key"
            border
            class="calculator-table"
            empty-text="请输入一个eBay商品链接开始测算"
          >
            <el-table-column label="图片" width="82" fixed="left">
              <template #default="scope">
                <div class="image-cell">
                  <el-image
                    class="product-image"
                    :src="scope.row.remoteImageUrl"
                    :preview-src-list="draftImageUrls(scope.row)"
                    preview-teleported
                    fit="contain"
                  >
                    <template #error><div class="image-empty"><el-icon><Picture /></el-icon></div></template>
                  </el-image>
                  <span v-if="draftImageUrls(scope.row).length > 1" class="image-count">{{ draftImageUrls(scope.row).length }}张</span>
                </div>
              </template>
            </el-table-column>
            <el-table-column label="站点" width="70" fixed="left" align="center">
              <template #default="scope"><el-tag :type="siteTagType(scope.row.siteCode)" size="small">{{ scope.row.siteCode }}</el-tag></template>
            </el-table-column>
            <el-table-column label="商品ID / 编号" prop="ebayItemId" width="135" />
            <el-table-column label="OE" width="175" class-name="manual-column">
              <template #default="scope"><el-input v-model.trim="scope.row.oe" placeholder="OE号" maxlength="500" /></template>
            </el-table-column>
            <el-table-column label="SKU" width="155" class-name="manual-column">
              <template #default="scope"><el-input v-model.trim="scope.row.sku" placeholder="SKU" maxlength="255" /></template>
            </el-table-column>
            <el-table-column label="参考链接" width="88" align="center">
              <template #default="scope"><el-link :href="scope.row.referenceUrl" target="_blank" type="primary">打开链接</el-link></template>
            </el-table-column>
            <el-table-column label="备注" width="160" class-name="manual-column">
              <template #default="scope"><el-input v-model.trim="scope.row.remark" placeholder="备注" maxlength="1000" /></template>
            </el-table-column>
            <el-table-column label="海运底价" width="105" align="right" class-name="calculated-column">
              <template #default="scope">{{ moneyValue(scope.row.seaFloorPrice, scope.row.currency) }}</template>
            </el-table-column>
            <el-table-column label="铁路底价" width="105" align="right" class-name="calculated-column">
              <template #default="scope">{{ moneyValue(scope.row.railFloorPrice, scope.row.currency) }}</template>
            </el-table-column>
            <el-table-column label="实际卖价" width="105" align="right">
              <template #default="scope"><b>{{ moneyValue(scope.row.salePrice, scope.row.currency) }}</b></template>
            </el-table-column>
            <el-table-column label="产品成本(¥)" width="125" class-name="manual-column">
              <template #default="scope"><number-input v-model="scope.row.productCostCny" :min="0" @change="calculateRow(scope.row)" /></template>
            </el-table-column>
            <el-table-column label="长(cm)" width="105" class-name="manual-column">
              <template #default="scope"><number-input v-model="scope.row.lengthCm" :min="0" :precision="2" @change="calculateRow(scope.row)" /></template>
            </el-table-column>
            <el-table-column label="宽(cm)" width="105" class-name="manual-column">
              <template #default="scope"><number-input v-model="scope.row.widthCm" :min="0" :precision="2" @change="calculateRow(scope.row)" /></template>
            </el-table-column>
            <el-table-column label="高(cm)" width="105" class-name="manual-column">
              <template #default="scope"><number-input v-model="scope.row.heightCm" :min="0" :precision="2" @change="calculateRow(scope.row)" /></template>
            </el-table-column>
            <el-table-column label="体积重(kg)" width="110" align="right" class-name="calculated-column">
              <template #default="scope">{{ numberValue(scope.row.volumetricWeightKg, 2) }}</template>
            </el-table-column>
            <el-table-column label="实重(kg)" width="110" class-name="manual-column">
              <template #default="scope"><number-input v-model="scope.row.actualWeightKg" :min="0" @change="calculateRow(scope.row)" /></template>
            </el-table-column>
            <el-table-column label="实时汇率" width="110" class-name="manual-column">
              <template #default="scope"><number-input v-model="scope.row.exchangeRate" :min="0" :precision="2" @change="calculateRow(scope.row)" /></template>
            </el-table-column>
            <el-table-column label="海运利润率" width="112" align="right" class-name="calculated-column">
              <template #default="scope"><span :class="rateClass(scope.row.seaProfitRate)">{{ rateValue(scope.row.seaProfitRate) }}</span></template>
            </el-table-column>
            <el-table-column label="铁路利润率" width="112" align="right" class-name="calculated-column">
              <template #default="scope"><span :class="rateClass(scope.row.railProfitRate)">{{ rateValue(scope.row.railProfitRate) }}</span></template>
            </el-table-column>
            <el-table-column label="目标利润率(%)" width="135" class-name="manual-column">
              <template #default="scope"><number-input v-model="scope.row.targetProfitPercent" :min="0" :max="80" :precision="2" @change="calculateRow(scope.row)" /></template>
            </el-table-column>
            <el-table-column label="目标成本(海运)" width="125" align="right" class-name="calculated-column">
              <template #default="scope">{{ scope.row.targetProductCostSea == null ? '--' : `¥ ${numberValue(scope.row.targetProductCostSea, 2)}` }}</template>
            </el-table-column>
            <el-table-column label="目标成本(铁路)" width="125" align="right" class-name="calculated-column">
              <template #default="scope">{{ scope.row.targetProductCostRail == null ? '--' : `¥ ${numberValue(scope.row.targetProductCostRail, 2)}` }}</template>
            </el-table-column>
            <el-table-column label="操作" width="128" fixed="right" align="center">
              <template #default="scope">
                <el-button
                  v-hasPermi="['sop:competitor:save']"
                  link type="primary" :loading="scope.row.saving" @click="handleSave(scope.row)"
                >保存</el-button>
                <el-button link type="danger" @click="removeDraft(scope.row)">删除</el-button>
              </template>
            </el-table-column>
          </el-table>

          <el-pagination
            v-if="drafts.length > 10"
            v-model:current-page="draftPage"
            :page-size="10"
            layout="total, prev, pager, next"
            :total="drafts.length"
            class="draft-pagination"
          />
        </section>
      </el-tab-pane>
    </el-tabs>

    <el-dialog
      v-model="editVisible"
      title="编辑已保存竞品"
      width="920px"
      append-to-body
      destroy-on-close
      :close-on-click-modal="false"
    >
      <template v-if="editForm">
        <div class="edit-product-head">
          <el-image
            class="edit-product-image"
            :src="resourceUrl(editForm.localImageUrl)"
            :preview-src-list="savedImageUrls(editForm)"
            preview-teleported
            fit="contain"
          />
          <div>
            <div class="edit-product-title">
              <el-tag :type="siteTagType(editForm.siteCode)" size="small">{{ editForm.siteCode }}</el-tag>
              <b>商品ID / 编号：{{ editForm.ebayItemId }}</b>
            </div>
            <el-link :href="editForm.referenceUrl" target="_blank" type="primary">查看原商品链接</el-link>
          </div>
        </div>

        <el-form label-position="top" class="edit-form">
          <el-row :gutter="16">
            <el-col :span="8"><el-form-item label="OE号"><el-input v-model.trim="editForm.oe" maxlength="500" /></el-form-item></el-col>
            <el-col :span="8"><el-form-item label="SKU"><el-input v-model.trim="editForm.sku" maxlength="255" /></el-form-item></el-col>
            <el-col :span="8"><el-form-item label="备注"><el-input v-model.trim="editForm.remark" maxlength="1000" /></el-form-item></el-col>
            <el-col :span="8"><el-form-item :label="`实际卖价（${editForm.currency}）`"><number-input v-model="editForm.salePrice" :min="0" :precision="2" @change="calculateRow(editForm)" /></el-form-item></el-col>
            <el-col :span="8"><el-form-item label="产品成本（¥）"><number-input v-model="editForm.productCostCny" :min="0" :precision="2" @change="calculateRow(editForm)" /></el-form-item></el-col>
            <el-col :span="8"><el-form-item label="实重（kg）"><number-input v-model="editForm.actualWeightKg" :min="0" :precision="2" @change="calculateRow(editForm)" /></el-form-item></el-col>
            <el-col :span="6"><el-form-item label="长（cm）"><number-input v-model="editForm.lengthCm" :min="0" :precision="2" @change="calculateRow(editForm)" /></el-form-item></el-col>
            <el-col :span="6"><el-form-item label="宽（cm）"><number-input v-model="editForm.widthCm" :min="0" :precision="2" @change="calculateRow(editForm)" /></el-form-item></el-col>
            <el-col :span="6"><el-form-item label="高（cm）"><number-input v-model="editForm.heightCm" :min="0" :precision="2" @change="calculateRow(editForm)" /></el-form-item></el-col>
            <el-col :span="6"><el-form-item label="体积重（kg）"><el-input :model-value="numberValue(editForm.volumetricWeightKg, 2)" disabled /></el-form-item></el-col>
            <el-col :span="8"><el-form-item label="实时汇率"><number-input v-model="editForm.exchangeRate" :min="0" :precision="2" @change="calculateRow(editForm)" /></el-form-item></el-col>
            <el-col :span="8"><el-form-item label="目标利润率（%）"><number-input v-model="editForm.targetProfitPercent" :min="0" :max="80" :precision="2" @change="calculateRow(editForm)" /></el-form-item></el-col>
          </el-row>
        </el-form>

        <div class="edit-result-grid">
          <div><span>海运利润率</span><b :class="rateClass(editForm.seaProfitRate)">{{ rateValue(editForm.seaProfitRate) }}</b></div>
          <div><span>铁路利润率</span><b :class="rateClass(editForm.railProfitRate)">{{ rateValue(editForm.railProfitRate) }}</b></div>
          <div><span>海运底价</span><b>{{ moneyValue(editForm.seaFloorPrice, editForm.currency) }}</b></div>
          <div><span>铁路底价</span><b>{{ moneyValue(editForm.railFloorPrice, editForm.currency) }}</b></div>
          <div><span>目标成本（海运）</span><b>¥ {{ numberValue(editForm.targetProductCostSea, 2) }}</b></div>
          <div><span>目标成本（铁路）</span><b>{{ editForm.targetProductCostRail == null ? '--' : `¥ ${numberValue(editForm.targetProductCostRail, 2)}` }}</b></div>
        </div>
      </template>
      <template #footer>
        <el-button @click="editVisible = false">取消</el-button>
        <el-button v-hasPermi="['sop:competitor:edit']" type="primary" :loading="editSaving" @click="handleUpdate">保存并重新计算</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, defineComponent, h, onMounted, reactive, ref } from 'vue'
import { ElInputNumber, ElMessage, ElMessageBox } from 'element-plus'
import { saveAs } from 'file-saver'
import { blobValidate } from '@/utils/ruoyi'
import { ArrowDown, Collection, DataAnalysis, Delete, Download, Link, Picture, Refresh, Search, Upload } from '@element-plus/icons-vue'
import {
  deleteEbayCompetitor,
  exportEbayCompetitors,
  importEbayCompetitorLinks,
  listEbayCompetitors,
  queryEbayCompetitor,
  saveEbayCompetitor,
  updateEbayCompetitor
} from '@/api/sop/competitor'

const NumberInput = defineComponent({
  name: 'NumberInput',
  inheritAttrs: false,
  props: {
    modelValue: { type: Number, default: null },
    min: { type: Number, default: undefined },
    max: { type: Number, default: undefined },
    precision: { type: Number, default: 2 }
  },
  emits: ['update:modelValue', 'change'],
  setup(props, { emit, attrs }) {
    return () => h(ElInputNumber, {
      ...attrs,
      modelValue: props.modelValue,
      min: props.min,
      max: props.max,
      precision: props.precision,
      controls: false,
      valueOnClear: null,
      style: { width: '100%' },
      'onUpdate:modelValue': value => emit('update:modelValue', value),
      onChange: value => emit('change', value)
    })
  }
})

const activeTab = ref('library')
const queryUrl = ref('')
const queryLoading = ref(false)
const libraryLoading = ref(false)
const exportLoading = ref(false)
const savedProducts = ref([])
const total = ref(0)
const libraryTableRef = ref(null)
const librarySelection = ref([])
const drafts = ref([])
const draftPage = ref(1)
const editVisible = ref(false)
const editSaving = ref(false)
const editForm = ref(null)
const deletingId = ref(null)
const linkUploadRef = ref(null)
const batchParsing = ref(false)
const batchRunning = ref(false)
const batchStopRequested = ref(false)
const batchItems = ref([])
const batchFileName = ref('')

const filters = reactive({
  pageNum: 1,
  pageSize: 20,
  oe: '',
  sku: '',
  siteCode: ''
})

const pagedDrafts = computed(() => {
  const start = (draftPage.value - 1) * 10
  return drafts.value.slice(start, start + 10)
})

const batchSuccessCount = computed(() => batchItems.value.filter(item => item.status === 'success').length)
const batchFailedCount = computed(() => batchItems.value.filter(item => item.status === 'failed').length)
const batchPendingCount = computed(() => batchItems.value.filter(item => item.status === 'pending').length)
const batchCurrentItem = computed(() => batchItems.value.find(item => item.status === 'loading'))
const batchProgress = computed(() => {
  if (!batchItems.value.length) return 0
  return Math.round((batchSuccessCount.value + batchFailedCount.value) * 100 / batchItems.value.length)
})
const batchProgressStatus = computed(() => {
  if (batchRunning.value || batchProgress.value < 100) return undefined
  return batchFailedCount.value ? 'exception' : 'success'
})

onMounted(loadLibrary)

function handleTabChange(name) {
  if (name === 'library') loadLibrary()
}

async function loadLibrary() {
  libraryLoading.value = true
  try {
    const response = await listEbayCompetitors(filters)
    savedProducts.value = response.rows || []
    total.value = Number(response.total || 0)
  } finally {
    libraryLoading.value = false
  }
}

function handleSearch() {
  filters.pageNum = 1
  clearLibrarySelection()
  loadLibrary()
}

function resetSearch() {
  filters.pageNum = 1
  filters.oe = ''
  filters.sku = ''
  filters.siteCode = ''
  clearLibrarySelection()
  loadLibrary()
}

function handleLibrarySelection(rows) {
  librarySelection.value = rows || []
}

function clearLibrarySelection() {
  libraryTableRef.value?.clearSelection()
  librarySelection.value = []
}

async function handleExportCommand(command) {
  const exportAll = command === 'all'
  const ids = exportAll ? [] : [...new Set(librarySelection.value.map(item => item.id).filter(Boolean))]
  if (!exportAll && !ids.length) {
    ElMessage.warning('请先勾选需要导出的商品')
    return
  }
  if (exportAll) {
    await ElMessageBox.confirm('确认导出商品库中的全部已保存商品吗？', '导出全部商品库', {
      type: 'info',
      confirmButtonText: '确认导出'
    })
  }
  exportLoading.value = true
  try {
    const data = await exportEbayCompetitors({ exportAll, ids })
    if (!blobValidate(data)) {
      const text = await data.text()
      let message = '导出失败'
      try { message = JSON.parse(text).msg || message } catch { message = text || message }
      throw new Error(message)
    }
    saveAs(new Blob([data]), `eBay竞品商品库_${fileTimestamp()}.xlsx`)
    ElMessage.success(exportAll ? '全部商品库已导出' : `已导出选中的${ids.length}条商品`)
  } catch (error) {
    ElMessage.error(error?.message || '商品库导出失败')
  } finally {
    exportLoading.value = false
  }
}

function openEdit(row) {
  if (!row.formulaConfig) {
    ElMessage.warning(`${row.siteCode}站点计算公式不可用，暂时不能编辑`)
    return
  }
  editForm.value = {
    ...row,
    images: Array.isArray(row.images) ? row.images.map(item => ({ ...item })) : [],
    formulaConfig: { ...row.formulaConfig },
    targetProfitPercent: round(Number(row.targetProfitRate || 0) * 100, 2)
  }
  calculateRow(editForm.value)
  editVisible.value = true
}

async function handleUpdate() {
  if (!editForm.value) return
  calculateRow(editForm.value)
  const error = validateDraft(editForm.value)
  if (error) {
    ElMessage.warning(error)
    return
  }
  editSaving.value = true
  try {
    await updateEbayCompetitor(editForm.value.id, buildPayload(editForm.value))
    editVisible.value = false
    ElMessage.success('商品已更新，并按当前站点公式重新计算')
    await loadLibrary()
  } finally {
    editSaving.value = false
  }
}

async function handleDelete(row) {
  await ElMessageBox.confirm(
    `确认删除商品 ${row.ebayItemId} 吗？数据库记录和本地全部图片将一起删除。`,
    '删除已保存竞品',
    { type: 'warning', confirmButtonText: '确认删除' }
  )
  deletingId.value = row.id
  try {
    await deleteEbayCompetitor(row.id)
    if (savedProducts.value.length === 1 && filters.pageNum > 1) filters.pageNum--
    ElMessage.success('竞品商品及其本地图片已删除')
    await loadLibrary()
  } finally {
    deletingId.value = null
  }
}

async function handleQuery() {
  if (batchRunning.value) {
    ElMessage.info('批量队列正在逐条抓取，请等待完成或先停止任务')
    return
  }
  if (!queryUrl.value) {
    ElMessage.warning('请输入eBay商品链接')
    return
  }
  queryLoading.value = true
  try {
    const response = await queryEbayCompetitor(queryUrl.value)
    upsertDraft(response.data || {}, true)
    draftPage.value = 1
    queryUrl.value = ''
    ElMessage.success('商品信息拉取成功，请填写计算参数')
  } finally {
    queryLoading.value = false
  }
}

async function handleLinkFileChange(uploadFile) {
  const file = uploadFile?.raw
  if (!file) return
  if (file.size > 5 * 1024 * 1024) {
    ElMessage.warning('Excel文件不能超过5MB')
    linkUploadRef.value?.clearFiles()
    return
  }
  batchParsing.value = true
  try {
    const response = await importEbayCompetitorLinks(file)
    const result = response.data || {}
    const links = Array.isArray(result.links) ? result.links : []
    batchFileName.value = result.fileName || file.name
    batchItems.value = links.map((url, index) => ({ index: index + 1, url, status: 'pending', message: '' }))
    const ignored = Number(result.blankRows || 0) + Number(result.duplicateLinks || 0)
    ElMessage.success(`已读取${links.length}个链接${ignored ? `，忽略${ignored}个空白或重复项` : ''}，开始逐条抓取`)
    batchParsing.value = false
    linkUploadRef.value?.clearFiles()
    processBatch()
  } finally {
    batchParsing.value = false
    linkUploadRef.value?.clearFiles()
  }
}

async function processBatch() {
  if (batchRunning.value || !batchPendingCount.value) return
  batchRunning.value = true
  batchStopRequested.value = false
  try {
    for (const item of batchItems.value) {
      if (batchStopRequested.value) break
      if (item.status !== 'pending') continue
      item.status = 'loading'
      item.message = '正在调用eBay接口'
      try {
        const response = await queryEbayCompetitor(item.url, { silent: true })
        const data = response.data || {}
        upsertDraft(data, false)
        item.status = 'success'
        item.message = `${data.siteCode || '--'}站 · 商品ID ${data.ebayItemId || '--'}`
      } catch (error) {
        item.status = 'failed'
        item.message = friendlyRequestError(error)
      }
    }
  } finally {
    batchRunning.value = false
    batchStopRequested.value = false
    if (!batchPendingCount.value) {
      draftPage.value = 1
      if (batchFailedCount.value) {
        ElMessage.warning(`批量抓取完成：成功${batchSuccessCount.value}个，失败${batchFailedCount.value}个，可展开明细查看或重试`)
      } else {
        ElMessage.success(`批量抓取完成，共成功${batchSuccessCount.value}个`)
      }
    }
  }
}

function stopBatch() {
  batchStopRequested.value = true
  ElMessage.info('将在当前链接处理完成后停止')
}

function retryFailedBatch() {
  batchItems.value.forEach(item => {
    if (item.status === 'failed') {
      item.status = 'pending'
      item.message = ''
    }
  })
  processBatch()
}

function clearBatch() {
  batchItems.value = []
  batchFileName.value = ''
}

function upsertDraft(data, placeFirst) {
  const row = createDraft(data)
  const index = drafts.value.findIndex(item => item._key === row._key)
  if (index >= 0) drafts.value.splice(index, 1)
  if (placeFirst) drafts.value.unshift(row)
  else drafts.value.push(row)
  return row
}

function batchStatusText(status) {
  return { pending: '待处理', loading: '抓取中', success: '成功', failed: '失败' }[status] || status
}

function batchStatusType(status) {
  return { pending: 'info', loading: 'warning', success: 'success', failed: 'danger' }[status] || 'info'
}

function friendlyRequestError(error) {
  const message = String(error?.message || error || '抓取失败').replace(/[\r\n]+/g, ' ').trim()
  return message.length > 300 ? `${message.slice(0, 300)}…` : message
}

function fileTimestamp() {
  const now = new Date()
  const pad = value => String(value).padStart(2, '0')
  return `${now.getFullYear()}${pad(now.getMonth() + 1)}${pad(now.getDate())}${pad(now.getHours())}${pad(now.getMinutes())}${pad(now.getSeconds())}`
}

function createDraft(data) {
  return {
    _key: `${data.siteCode || ''}:${data.ebayItemId || Date.now()}`,
    siteCode: data.siteCode,
    marketplaceId: data.marketplaceId,
    currency: data.currency,
    ebayItemId: data.ebayItemId,
    oe: '',
    sku: '',
    referenceUrl: data.referenceUrl || data.sourceUrl,
    remoteImageUrl: data.remoteImageUrl,
    remoteImageUrls: Array.isArray(data.remoteImageUrls) ? data.remoteImageUrls : (data.remoteImageUrl ? [data.remoteImageUrl] : []),
    remark: '',
    salePrice: numberOrNull(data.salePrice),
    productCostCny: null,
    lengthCm: null,
    widthCm: null,
    heightCm: null,
    volumetricWeightKg: null,
    actualWeightKg: null,
    exchangeRate: null,
    seaFloorPrice: null,
    railFloorPrice: null,
    seaProfitRate: null,
    railProfitRate: null,
    targetProfitPercent: null,
    targetProfitRate: null,
    targetProductCostSea: null,
    targetProductCostRail: null,
    formulaConfig: data.formulaConfig || {},
    saving: false
  }
}

function calculateRow(row) {
  const cfg = row.formulaConfig || {}
  const length = roundedPositiveNumber(row.lengthCm, 2)
  const width = roundedPositiveNumber(row.widthCm, 2)
  const height = roundedPositiveNumber(row.heightCm, 2)
  row.lengthCm = length
  row.widthCm = width
  row.heightCm = height
  const divisor = positiveNumber(cfg.volumetricDivisor) || 6000
  const rawVolume = length && width && height ? length * width * height / divisor : null
  row.volumetricWeightKg = rawVolume == null ? null : round(rawVolume, 2)

  const price = positiveNumber(row.salePrice)
  const cost = positiveNumber(row.productCostCny)
  const actual = positiveNumber(row.actualWeightKg)
  const exchange = positiveNumber(row.exchangeRate)
  const targetPercent = positiveNumber(row.targetProfitPercent)
  const volume = positiveNumber(row.volumetricWeightKg)
  const platform = positiveNumber(cfg.platformNetRate)
  if (!(price && cost && actual && exchange && targetPercent && volume && platform)) {
    clearCalculated(row, true)
    return
  }
  const target = targetPercent / 100
  row.targetProfitRate = round(target, 6)
  if (target >= platform) {
    clearCalculated(row, false)
    return
  }

  const seaRate = Number(cfg.seaFirstLegRate || 0)
  const netSale = price * platform
  const denominator = platform - target
  if (row.siteCode === 'US') {
    const formulaVolume = positiveNumber(rawVolume)
    const thresholdWeight = Math.max(formulaVolume, actual)
    const factor = Number(cfg.chargeableVolumeFactor || 0.8)
    const deliveryWeight = Math.max(factor * formulaVolume, actual)
    const small = thresholdWeight < Number(cfg.smallWeightThreshold || 0.5)
    const fixed = Number(small ? cfg.smallFixedFee : cfg.largeFixedFee)
    const deliveryRate = Number(small ? cfg.smallDeliveryRate : cfg.largeDeliveryRate)
    const delivery = deliveryRate * deliveryWeight
    const floorFirstLegCny = seaRate * formulaVolume
    const profitFirstLegCny = Number(cfg.profitFirstLegRate ?? seaRate) * formulaVolume
    const targetFirstLegCny = Number(cfg.targetCostFirstLegRate ?? seaRate) * formulaVolume
    const floorLocalCost = (cost + floorFirstLegCny) / exchange
    const profitLocalCost = (cost + profitFirstLegCny) / exchange
    row.seaProfitRate = round((netSale - profitLocalCost - fixed - delivery) / price, 6)
    row.seaFloorPrice = round((floorLocalCost + fixed + delivery) / denominator, 2)
    row.targetProductCostSea = round(exchange * (netSale - fixed - delivery - target * price) - targetFirstLegCny, 2)
    row.railProfitRate = null
    row.railFloorPrice = null
    row.targetProductCostRail = null
    return
  }

  const chargeable = Math.max(volume, actual)
  const fixed = Number(cfg.fixedFee || 0)
  const handling = Number(cfg.weightHandlingRate || 0) * chargeable
  const seaFirstLegCny = seaRate * volume
  const seaLocalCost = (cost + seaFirstLegCny) / exchange
  row.seaProfitRate = round((netSale - seaLocalCost - fixed - handling) / price, 6)
  row.seaFloorPrice = round((seaLocalCost + fixed + handling) / denominator, 2)
  row.targetProductCostSea = round(exchange * (netSale - fixed - handling - target * price) - seaFirstLegCny, 2)

  const railRate = Number(cfg.railFirstLegRate || 0)
  const railFirstLegCny = railRate * chargeable
  const railLocalCost = (cost + railFirstLegCny) / exchange
  row.railProfitRate = round((netSale - railLocalCost - fixed - handling) / price, 6)
  row.railFloorPrice = round((railLocalCost + fixed + handling) / denominator, 2)
  row.targetProductCostRail = round(exchange * (netSale - fixed - handling - target * price) - railFirstLegCny, 2)
}

function clearCalculated(row, clearTarget) {
  row.seaFloorPrice = null
  row.railFloorPrice = null
  row.seaProfitRate = null
  row.railProfitRate = null
  row.targetProductCostSea = null
  row.targetProductCostRail = null
  if (clearTarget) row.targetProfitRate = null
}

async function handleSave(row) {
  calculateRow(row)
  const error = validateDraft(row)
  if (error) {
    ElMessage.warning(error)
    return
  }
  row.saving = true
  try {
    await saveEbayCompetitor(buildPayload(row))
    drafts.value = drafts.value.filter(item => item._key !== row._key)
    fixDraftPage()
    ElMessage.success('竞品已保存到商品库，图片已本地化')
  } finally {
    row.saving = false
  }
}

function validateDraft(row) {
  if (!row.oe && !row.sku) return 'OE号和SKU至少填写一个'
  const required = [
    ['实际卖价', row.salePrice], ['产品成本', row.productCostCny], ['长', row.lengthCm], ['宽', row.widthCm],
    ['高', row.heightCm], ['实重', row.actualWeightKg], ['实时汇率', row.exchangeRate],
    ['目标利润率', row.targetProfitPercent]
  ]
  const missing = required.find(([, value]) => !positiveNumber(value))
  if (missing) return `${missing[0]}必须大于0`
  const platformPercent = Number(row.formulaConfig?.platformNetRate || 0) * 100
  if (Number(row.targetProfitPercent) >= platformPercent) return `目标利润率必须小于${round(platformPercent, 2)}%`
  if (row.seaProfitRate == null) return '计算参数不完整，暂时不能保存'
  return ''
}

function buildPayload(row) {
  return {
    siteCode: row.siteCode,
    marketplaceId: row.marketplaceId,
    currency: row.currency,
    ebayItemId: row.ebayItemId,
    oe: row.oe,
    sku: row.sku,
    referenceUrl: row.referenceUrl,
    remoteImageUrl: row.remoteImageUrl,
    remark: row.remark,
    salePrice: row.salePrice,
    productCostCny: row.productCostCny,
    lengthCm: row.lengthCm,
    widthCm: row.widthCm,
    heightCm: row.heightCm,
    actualWeightKg: row.actualWeightKg,
    exchangeRate: row.exchangeRate,
    targetProfitRate: row.targetProfitRate
  }
}

function removeDraft(row) {
  drafts.value = drafts.value.filter(item => item._key !== row._key)
  fixDraftPage()
}

async function clearDrafts() {
  await ElMessageBox.confirm('确认清空当前所有未保存商品吗？', '清空待判断商品', { type: 'warning' })
  drafts.value = []
  draftPage.value = 1
}

function fixDraftPage() {
  const maxPage = Math.max(1, Math.ceil(drafts.value.length / 10))
  if (draftPage.value > maxPage) draftPage.value = maxPage
}

function resourceUrl(url) {
  if (!url) return ''
  if (/^https?:\/\//i.test(url)) return url
  return `${import.meta.env.VITE_APP_BASE_API}${url}`
}

function savedImageUrls(row) {
  const urls = Array.isArray(row?.images)
    ? row.images.map(item => resourceUrl(item.localImageUrl)).filter(Boolean)
    : []
  if (!urls.length && row?.localImageUrl) urls.push(resourceUrl(row.localImageUrl))
  return [...new Set(urls)]
}

function draftImageUrls(row) {
  const urls = Array.isArray(row?.remoteImageUrls) ? row.remoteImageUrls.filter(Boolean) : []
  if (!urls.length && row?.remoteImageUrl) urls.push(row.remoteImageUrl)
  return [...new Set(urls)]
}

function positiveNumber(value) {
  const number = Number(value)
  return Number.isFinite(number) && number > 0 ? number : null
}

function roundedPositiveNumber(value, scale) {
  const number = positiveNumber(value)
  return number == null ? null : round(number, scale)
}

function numberOrNull(value) {
  const number = Number(value)
  return Number.isFinite(number) ? number : null
}

function round(value, scale) {
  if (!Number.isFinite(value)) return null
  const factor = 10 ** scale
  return Math.round((value + Number.EPSILON) * factor) / factor
}

function numberValue(value, scale = 2) {
  if (value == null || value === '' || !Number.isFinite(Number(value))) return '--'
  return Number(value).toLocaleString('zh-CN', { minimumFractionDigits: scale, maximumFractionDigits: scale })
}

function moneyValue(value, currency) {
  if (value == null || value === '' || !Number.isFinite(Number(value))) return '--'
  const symbols = { EUR: '€', GBP: '£', USD: '$' }
  return `${symbols[currency] || currency || ''} ${numberValue(value, 2)}`.trim()
}

function rateValue(value) {
  if (value == null || value === '' || !Number.isFinite(Number(value))) return '--'
  return `${numberValue(Number(value) * 100, 2)}%`
}

function rateClass(value) {
  return Number(value) < 0 ? 'negative-rate' : 'positive-rate'
}

function textValue(value) {
  return value == null || value === '' ? '--' : value
}

function dimensions(row) {
  return `${numberValue(row.lengthCm, 2)} × ${numberValue(row.widthCm, 2)} × ${numberValue(row.heightCm, 2)} cm`
}

function siteTagType(site) {
  return site === 'UK' ? 'success' : site === 'US' ? 'warning' : 'primary'
}
</script>

<style scoped>
.competitor-page { min-height: calc(100vh - 84px); padding: 16px; background: #f4f7fb; color: #27364a; }
.page-head { display: flex; align-items: center; justify-content: space-between; gap: 20px; margin-bottom: 12px; padding: 18px 22px; border: 1px solid #e6edf6; border-radius: 14px; background: linear-gradient(120deg, #fff 55%, #edf6ff); box-shadow: 0 8px 24px rgba(38, 82, 124, .06); }
.eyebrow { color: #4b97e5; font-size: 11px; font-weight: 700; letter-spacing: 1.2px; }
.page-head h2 { margin: 4px 0 2px; color: #20334b; font-size: 24px; }
.page-head p { margin: 0; color: #7b899b; font-size: 13px; }
.head-badges { display: flex; gap: 8px; }
.feature-tabs { --el-color-primary: #409eff; }
:deep(.feature-tabs > .el-tabs__header) { margin: 0; padding: 0 18px; border: 1px solid #e6edf6; border-bottom: 0; border-radius: 12px 12px 0 0; background: #fff; }
:deep(.feature-tabs > .el-tabs__content) { overflow: visible; }
.tab-label { display: inline-flex; align-items: center; gap: 7px; font-weight: 600; }
.panel { margin-top: 12px; border: 1px solid #e6edf6; border-radius: 12px; background: #fff; box-shadow: 0 5px 18px rgba(38, 82, 124, .045); }
.filter-panel { padding: 15px 18px 9px; }
.filter-panel .el-form-item { margin-bottom: 8px; }
.filter-panel :deep(.el-input) { width: 220px; }
.filter-tip { margin: 0 0 2px 50px; color: #98a4b4; font-size: 12px; }
.library-panel, .draft-panel { overflow: hidden; }
.panel-title { display: flex; align-items: center; justify-content: space-between; min-height: 50px; padding: 0 16px; border-bottom: 1px solid #edf1f6; }
.panel-title strong { margin-right: 10px; color: #2c3c52; font-size: 15px; }
.panel-title span { color: #8a97a8; font-size: 12px; }
.panel-actions, .batch-actions { display: flex; align-items: center; gap: 8px; }
.library-table, .calculator-table { width: 100%; }
:deep(.el-table th.el-table__cell) { height: 42px; padding: 0; color: #68778c; background: #f7f9fc; font-size: 12px; font-weight: 600; }
:deep(.library-table td.el-table__cell) { height: 66px; padding: 5px 0; }
:deep(.calculator-table td.el-table__cell) { height: 72px; padding: 5px 0; }
:deep(.calculator-table .el-input__wrapper) { padding: 1px 7px; }
:deep(.manual-column) { background: #fffdf7; }
:deep(.calculated-column) { background: #f5faff; }
.product-image { width: 58px; height: 58px; border: 1px solid #e8edf3; border-radius: 8px; background: #fff; }
.image-cell { position: relative; width: 58px; height: 58px; margin: 0 auto; }
.image-count { position: absolute; right: -5px; bottom: -4px; padding: 1px 5px; border: 1px solid #fff; border-radius: 8px; color: #fff; background: rgba(40, 102, 165, .86); font-size: 9px; line-height: 15px; pointer-events: none; }
.image-empty { display: flex; width: 100%; height: 100%; align-items: center; justify-content: center; color: #b9c2ce; background: #f7f9fc; font-size: 22px; }
.detail-wrap { padding: 16px 20px; background: #f8fbff; }
.detail-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 10px 18px; }
.detail-item { display: flex; min-width: 0; flex-direction: column; gap: 4px; }
.detail-item span { color: #909dad; font-size: 11px; }
.detail-item b { overflow: hidden; color: #3c4b60; font-size: 12px; font-weight: 500; text-overflow: ellipsis; white-space: nowrap; }
.detail-wide { grid-column: span 2; }
.image-gallery-detail { grid-column: 1 / -1; }
.image-gallery { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 2px; }
.gallery-thumb { width: 64px; height: 64px; border: 1px solid #e3eaf3; border-radius: 7px; background: #fff; cursor: zoom-in; }
.query-panel { padding: 15px 18px 12px; }
.query-row { display: grid; grid-template-columns: minmax(360px, 1fr) repeat(3, auto); gap: 10px; }
.query-hints { display: flex; flex-wrap: wrap; gap: 24px; margin-top: 10px; color: #8996a8; font-size: 12px; }
.query-hints span { display: inline-flex; align-items: center; gap: 6px; }
.query-hints i { width: 6px; height: 6px; border-radius: 50%; background: #59b684; }
.batch-card { margin-top: 14px; padding: 13px 14px 5px; border: 1px solid #dceafa; border-radius: 10px; background: #f8fbff; }
.batch-head { display: flex; align-items: center; justify-content: space-between; gap: 16px; margin-bottom: 10px; }
.batch-head > div:first-child { display: flex; min-width: 0; flex-direction: column; gap: 4px; }
.batch-head strong { overflow: hidden; color: #34475e; font-size: 13px; text-overflow: ellipsis; white-space: nowrap; }
.batch-head span, .batch-current { color: #7f8da0; font-size: 12px; }
.batch-current { overflow: hidden; margin-top: 8px; text-overflow: ellipsis; white-space: nowrap; }
.batch-detail { margin-top: 4px; border-top: 0; }
:deep(.batch-detail .el-collapse-item__header) { height: 38px; color: #5f7898; background: transparent; font-size: 12px; }
:deep(.batch-detail .el-collapse-item__wrap) { background: transparent; }
.legend { display: flex; align-items: center; gap: 7px; color: #8996a8; font-size: 12px; }
.legend i { width: 10px; height: 10px; border: 1px solid #eadfb8; border-radius: 2px; background: #fffdf7; }
.legend i.calculated { margin-left: 10px; border-color: #cce2f8; background: #f5faff; }
.positive-rate { color: #27865e; font-weight: 600; }
.negative-rate { color: #e45656; font-weight: 600; }
.draft-pagination { display: flex; justify-content: flex-end; padding: 14px 16px; }
.edit-product-head { display: flex; align-items: center; gap: 14px; margin: -4px 0 14px; padding: 12px; border: 1px solid #e6edf6; border-radius: 10px; background: #f8fbff; }
.edit-product-image { width: 68px; height: 68px; flex: 0 0 auto; border: 1px solid #e3eaf3; border-radius: 8px; background: #fff; }
.edit-product-title { display: flex; align-items: center; gap: 10px; margin-bottom: 8px; color: #34455c; }
.edit-form :deep(.el-form-item) { margin-bottom: 14px; }
.edit-result-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 10px; padding: 14px; border: 1px solid #dceafa; border-radius: 10px; background: #f5faff; }
.edit-result-grid > div { display: flex; flex-direction: column; gap: 5px; }
.edit-result-grid span { color: #8493a6; font-size: 12px; }
.edit-result-grid b { color: #30445d; font-size: 15px; }
.edit-result-grid b.positive-rate { color: #27865e; }
.edit-result-grid b.negative-rate { color: #e45656; }
:deep(.pagination-container) { margin: 0; padding: 15px 18px !important; }
@media (max-width: 900px) {
  .competitor-page { padding: 10px; }
  .page-head { align-items: flex-start; padding: 15px; }
  .head-badges { display: none; }
  .query-row { grid-template-columns: 1fr; }
  .batch-head { align-items: flex-start; flex-direction: column; }
  .query-hints { gap: 8px 16px; }
  .detail-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}
</style>
