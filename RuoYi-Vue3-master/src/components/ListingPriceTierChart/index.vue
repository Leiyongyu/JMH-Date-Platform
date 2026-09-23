<template>
  <section v-loading="loading" class="price-panel" :aria-labelledby="`price-tier-${platform}`"
           :style="{ '--tier-count': definitions.length }">
    <header>
      <div><span class="eyebrow">{{ platformLabel }} · {{ currencyLabel }}价格结构</span><h2 :id="`price-tier-${platform}`">店铺 SKU 价格分层</h2></div>
      <div class="actions">
        <el-button v-if="platform === 'ebay'" size="small" @click="structureOpen = true">产品结构</el-button>
        <el-button size="small" icon="Refresh" circle :disabled="loading" :title="refreshTitle" aria-label="重新统计价格分层" @click="load(true)" />
      </div>
    </header>
    <el-alert v-if="error" :title="error" type="error" :closable="false" />
    <template v-else-if="report?.state === 'READY'">
      <div v-if="platform === 'ebay'" class="filters-inline">
        <el-select v-model="month" size="small" placeholder="统计月份" style="width: 116px" @change="load()">
          <el-option v-for="m in report.months || []" :key="m" :label="m" :value="m" />
        </el-select>
        <el-select v-model="shop" size="small" clearable placeholder="全部店铺" style="width: 176px" @change="load()">
          <el-option v-for="s in report.shops || []" :key="s" :label="s" :value="s" />
        </el-select>
      </div>
      <div class="summary"><span><b>{{ report.shop_count }}</b> 个店铺</span><span><b>{{ report.total_sku_count.toLocaleString() }}</b> SKU</span></div>
      <div class="legend"><span v-for="(tier, i) in definitions" :key="tier.name" :title="`${tier.name}：${tier.range}`"><i :style="{ background: colors[i] }" />{{ tier.short }}</span></div>
      <div v-if="report.stale" class="warning">源数据、汇率或月份已更新，请重新统计。</div>
      <div v-if="presentation.usesFx && report.missing_currencies.length" class="warning">{{ report.missing_currencies.join('、') }} 在汇率表中没有任何可用汇率，相关记录未归档。</div>
      <div v-if="presentation.usesFx && fallbackCurrencies.length" class="warning" :title="rateDescription">{{ fallbackCurrencies.join('、') }} 使用的不是 {{ report.rate_month }} 的汇率，已回退到该币种最近有值的月份。</div>
      <div v-if="report.unclassified_sku_count || report.missing_sku_rows || report.invalid_price_rows || report.missing_shop_rows" class="warning" :title="anomalyText(report)">{{ anomalyText(report) }}</div>
      <div class="chart-scroll" tabindex="0" role="region" :aria-label="`${platformLabel}店铺价格分层，展开查看站点`">
        <details v-for="shop in report.items" :key="shop.node_id" class="shop-row">
          <summary :title="nodeTitle(shop)">
            <div class="store-heading"><span>{{ shop.store_name }}</span><b>{{ shop.group_sku_count.toLocaleString() }}</b></div>
            <div class="stack"><span v-for="(tier, i) in shop.tiers" :key="tier.tier_no" :style="{ flex: tier.sku_count, background: colors[i] }" :title="tierTitle(tier)" /></div>
            <div class="tier-values">
              <span v-for="(tier, i) in shop.tiers" :key="tier.tier_no" :title="tierTitle(tier)">
                <span class="tier-range"><i :style="{ background: colors[i] }" />{{ definitions[i].compact }}</span>
                <b>{{ tier.sku_count.toLocaleString() }} <span class="sku-unit">SKU</span></b>
                <small>{{ tier.sku_percent }}%</small>
              </span>
            </div>
          </summary>
          <div v-for="child in shop.children" :key="child.node_id" class="site-row" :title="nodeTitle(child)">
            <div class="store-heading"><span>{{ child.site || '未知站点' }} · {{ child.currencies.join('/') }}</span><b>{{ child.group_sku_count }}</b></div>
            <div class="stack"><span v-for="(tier, i) in child.tiers" :key="tier.tier_no" :style="{ flex: tier.sku_count, background: colors[i] }" :title="tierTitle(tier)" /></div>
            <div class="tier-values">
              <span v-for="(tier, i) in child.tiers" :key="tier.tier_no" :title="tierTitle(tier)">
                <span class="tier-range"><i :style="{ background: colors[i] }" />{{ definitions[i].compact }}</span>
                <b>{{ tier.sku_count.toLocaleString() }} <span class="sku-unit">SKU</span></b>
                <small>{{ tier.sku_percent }}%</small>
              </span>
            </div>
          </div>
        </details>
        <el-empty v-if="!report.items.length" :image-size="40" description="当前没有可统计的在售商品" />
      </div>
      <footer><span :title="rateDescription">{{ sourceLabel }} ⓘ</span><el-button link type="primary" size="small" @click="detailsOpen = true">展开报表</el-button></footer>
      <div class="generated" :title="ruleDescription">统计 {{ report.generated_at }} · 口径 ⓘ</div>
    </template>
    <el-empty v-else :image-size="45" :description="`尚未生成${currencyLabel}报表，请重新统计`" />

    <el-dialog v-model="detailsOpen" :title="`${platformLabel} 店铺${currencyLabel}价格分层`" width="min(1450px, 96vw)" append-to-body>
      <p class="rules">{{ ruleDescription }}</p>
      <p class="rules">{{ rateDescription }}</p>
      <div class="filters"><el-input v-model="keyword" clearable placeholder="搜索店铺名称" style="width: 260px" /><span>{{ visibleShops.length }} 个店铺；点击箭头展开站点明细</span></div>
      <el-table :data="visibleShops" row-key="node_id" :tree-props="{ children: 'children' }" max-height="540" border stripe>
        <el-table-column label="店铺 / 站点" min-width="225" fixed show-overflow-tooltip><template #default="{ row }">{{ row.scope === 'SHOP' ? row.store_name : row.site || '未知站点' }}</template></el-table-column>
        <el-table-column label="原币种" width="115"><template #default="{ row }">{{ row.currencies.join('/') || '--' }}</template></el-table-column>
        <el-table-column prop="group_sku_count" label="归档SKU" width="95" align="right" />
        <el-table-column v-for="(tier, i) in definitions" :key="tier.name" :min-width="tierColumnWidth" align="right">
          <template #header><div>{{ tier.name }}</div><small>{{ tier.range }}</small></template>
          <template #default="{ row }"><b>{{ row.tiers[i].sku_count }}</b><span class="percent"> / {{ row.tiers[i].sku_percent }}%</span></template>
        </el-table-column>
        <el-table-column label="异常提示" min-width="210"><template #default="{ row }"><span class="warning">{{ anomalyText(row) || '--' }}</span></template></el-table-column>
      </el-table>
      <p class="rules">每格：SKU数量 / 当前店铺或站点占比。店铺数量为站点明细之和，跨站点分别计数；百分比按各自有效SKU总数重新计算，不相加。百分比舍入合计可能不恰好100%。</p>
      <template #footer><el-button @click="detailsOpen = false">关闭</el-button></template>
    </el-dialog>
    <ProductStructure v-if="platform === 'ebay'" v-model="structureOpen" />
  </section>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { getListingPriceTier, refreshListingPriceTier } from '@/api/operations/listingPriceTier'
import { pricePresentation } from './presentation'
import ProductStructure from './ProductStructure.vue'
const props = defineProps({ platform: { type: String, required: true, validator: v => ['amz', 'ebay'].includes(v) } })
const platformLabel = computed(() => props.platform === 'amz' ? 'AMAZON' : 'EBAY')
const presentation = computed(() => pricePresentation(props.platform))
const currencyLabel = computed(() => presentation.value.label)
const report = ref(null)
const loading = ref(false)
const error = ref('')
const detailsOpen = ref(false)
const structureOpen = ref(false)
const keyword = ref('')
// eBay 的统计月份与店铺筛选；单价表按月存，任意历史月份都能查。
const month = ref('')
const shop = ref('')
// 七档要七种颜色；人民币只用前五个，色序不变，改档位数不影响AMZ报表的观感。
const palette = ['#67b8ae', '#629dce', '#666cc6', '#b07baf', '#d79b5e', '#c9756a', '#8a8f98']
const definitions = computed(() => presentation.value.names.map((name, i) => ({
  name, short: presentation.value.shorts[i],
  compact: presentation.value.compacts[i], range: presentation.value.ranges[i]
})))
// 人民币5档时取前5色，保持与改动前完全一致。
const colors = computed(() => palette.slice(0, definitions.value.length))
// 美元7档的表头只有「0-5」这种短字，收窄后弹窗仍不需要横向滚动；人民币5档保持164。
const tierColumnWidth = computed(() => definitions.value.length > 5 ? 112 : 164)
const refreshTitle = computed(() => props.platform === 'ebay'
  ? '先按飞书不良交易刊登表重算SKU美元单价，再重新分档；不拉取任何外部接口'
  : '用汇率表中各币种最新可用汇率重新计算本地数据，不拉取接口')
const ruleDescription = computed(() => `${props.platform === 'amz'
  ? 'AMZ来源：ods_lingxing_amz_listing_latest.landed_price（含促销、运费、积分）；仅status=1且is_delete=0，按完整seller_sku统计。店铺去掉与country_code一致的国家后缀，展开保留各站点。'
  : ''}${props.platform === 'ebay'
  ? 'eBay来源：飞书多维表格「不良交易刊登」，每周三更新一批。单价=该统计月份内最大登记日期那一批、按店铺+SKU汇总的「总交易额」÷「总交易量」，金额本身就是美元，不做任何汇率换算。同一SKU在不同店铺售价不同，故按店铺分别归档、不合并。该源表只收录有不良交易的刊登，不是全部在售商品，所以这里看到的是问题刊登的价格结构；源表没有站点字段，只能按店铺统计。点刷新会先重算单价表再分档。'
  : `按dim_lingxing_currency_month.${presentation.value.rateField}换算${currencyLabel.value}，不截断汇率，分档前不舍入。店铺+站点内完整SKU取最低有效${currencyLabel.value}价格、只计一次，跨站点相加。0为有效价格；缺SKU或价格异常单独提示、不计入占比；汇率按币种回退取最新可用月份，全无汇率才拒绝发布；不按中间码合并、不排除PC。刷新只重新计算本地统计仓库，不拉接口。`}`)
const rateMonths = computed(() => report.value?.rate_months || {})
const fallbackCurrencies = computed(() => Object.entries(rateMonths.value)
  .filter(([, month]) => month && month !== report.value?.rate_month).map(([code]) => code).sort())
// eBay 已不用汇率，页脚与悬浮说明都改成单价来源；AMZ 保持原样。
const sourceLabel = computed(() => presentation.value.usesFx
  ? `汇率 ${report.value?.rate_month || '--'} · ${presentation.value.rateField}`
  : `单价 ${report.value?.unit_price_month || '--'} · 批次 ${report.value?.unit_price_reg_date || '--'}`)
const rateDescription = computed(() => presentation.value.usesFx
  ? `统计月份 ${report.value?.rate_month || '--'}；${presentation.value.formula}。使用的${presentation.value.rateField}：${Object.entries(report.value?.rates || {}).map(([k, v]) => `${k} ${v ?? '--'}${rateMonths.value[k] ? `（${rateMonths.value[k]}）` : ''}`).join('、')}。每个币种各自取不晚于统计月份、且有正值的最新一个月，当月尚未同步时自动回退到上一次有汇率的月份；不取未来月份。某币种任何月份都没有汇率才判定为缺失并拒绝发布。`
  : `统计月份 ${report.value?.unit_price_month || '--'}，来源批次（登记日期）${report.value?.unit_price_reg_date || '--'}。${presentation.value.formula}。不读取任何汇率表，汇率变动不影响本报表。`)
const visibleShops = computed(() => (report.value?.items || []).filter(p => p.store_name.toLowerCase().includes(keyword.value.trim().toLowerCase())))
const tierTitle = t => `${t.label} ${t.range}：${t.sku_count} SKU / ${t.sku_percent}%`
const anomalyText = n => [n.unclassified_sku_count ? `${n.unclassified_sku_count}个SKU未归档` : '', n.missing_sku_rows ? `${n.missing_sku_rows}条缺SKU` : '', n.invalid_price_rows ? `${n.invalid_price_rows}条价格/站点异常` : '', n.missing_rate_rows ? `${n.missing_rate_rows}条无可用汇率` : '', n.missing_shop_rows ? `${n.missing_shop_rows}条店铺未匹配` : ''].filter(Boolean).join('；')
const nodeTitle = n => `${n.store_name} ${n.site || '店铺汇总'}\n${n.tiers.map(tierTitle).join('\n')}\n${anomalyText(n)}`
// 拦截器对业务码500会 reject(new Error(后端msg))，消息在 message 上；
// 非500业务码只给占位串 'error'，HTTP层失败给的是 'Request failed...'，
// 这两种都不是给人看的原因，退回本组件的兜底文案。
function serverMessage(exception) {
  const raw = typeof exception === 'string' ? exception : exception?.message
  const text = String(raw || '').trim()
  return text && text !== 'error' && !text.startsWith('Request failed') ? text : ''
}
let disposed = false
async function load(refresh = false) {
  if (loading.value) return
  loading.value = true
  error.value = ''
  try {
    // 刷新只负责按飞书不良交易刊登表重算单价表，重算完再按当前筛选取数，
    // 这样点刷新不会把用户选好的月份/店铺跳回默认值。
    if (refresh) await refreshListingPriceTier(props.platform)
    const params = props.platform === 'ebay' ? { month: month.value, shop: shop.value } : {}
    const response = await getListingPriceTier(props.platform, params)
    if (!disposed) {
      const next = response.data
      if (next?.state === 'READY' && (next.target_currency || 'CNY') !== presentation.value.currency) {
        report.value = null
        error.value = '报表币种与当前口径不一致，请更新Python服务后重新统计。'
        return
      }
      report.value = next
      // 首次加载时后端不知道要哪个月，拿它给的最新月份回填选择器。
      if (props.platform === 'ebay' && !month.value && next?.stat_month) month.value = next.stat_month
    }
  } catch (exception) {
    // 服务端会说明具体原因（例如某币种全无汇率、源批次不一致），直接透出来；
    // 吞掉消息只剩一句泛化提示的话，看报表的人无从判断该找谁处理。
    if (!disposed) error.value = serverMessage(exception) || '报表加载或统计失败，请检查权限、统计表和服务日志。原始数据未修改。'
  } finally {
    if (!disposed) loading.value = false
  }
}
onMounted(() => load())
onBeforeUnmount(() => { disposed = true })
</script>

<style scoped>
.price-panel { box-sizing: border-box; display: flex; flex-direction: column; min-width: 0; height: 360px; padding: 14px; border: 1px solid var(--el-border-color-lighter); border-radius: 10px; background: var(--el-bg-color); }
header { display: flex; justify-content: space-between; align-items: center; gap: 8px; }
.eyebrow { color: var(--el-color-primary); font-size: 10px; font-weight: 600; }
h2 { margin: 6px 0 10px; font-size: 15px; color: var(--el-text-color-primary); }
.summary { display: flex; justify-content: space-between; font-size: 11px; margin-bottom: 8px; }
.summary b { font-size: 17px; }
.legend { display: flex; flex-wrap: wrap; gap: 5px 8px; font-size: 10px; margin-bottom: 8px; }
i { display: inline-block; width: 7px; height: 7px; border-radius: 2px; margin-right: 3px; }
.chart-scroll { flex: 1; min-height: 0; overflow-y: auto; scrollbar-width: thin; padding-right: 4px; }
.shop-row { margin-bottom: 10px; }
summary { position: relative; cursor: pointer; list-style: none; font-size: 10px; }
summary::-webkit-details-marker { display: none; }
summary::before { content: '▸'; position: absolute; top: 0; left: 0; }
details[open] > summary::before { content: '▾'; }
.store-heading { display: flex; justify-content: space-between; gap: 8px; font-size: 11px; margin: 0 0 5px 12px; }
.store-heading span { overflow: hidden; white-space: nowrap; text-overflow: ellipsis; }
.stack { display: flex; height: 11px; width: 100%; overflow: hidden; border-radius: 3px; background: var(--el-fill-color-light); }
.stack span { min-width: 0; }
.site-row { padding: 9px 0 4px 12px; }
.site-row .store-heading { margin: 0 0 5px; font-size: 10px; color: var(--el-text-color-secondary); }
.tier-values { display: grid; grid-template-columns: repeat(var(--tier-count, 5), minmax(0, 1fr)); gap: 3px; padding-top: 5px; font-size: 10px; font-variant-numeric: tabular-nums; }
.tier-range { display: block; color: var(--el-text-color-regular); line-height: 1.4; margin-bottom: 3px; overflow-wrap: anywhere; }
.sku-unit { font-size: 9px; font-weight: 400; color: var(--el-text-color-secondary); }
.tier-values b, .tier-values small { display: block; white-space: nowrap; }
.tier-values small { color: var(--el-text-color-secondary); font-size: 10px; }
.actions { display: flex; align-items: center; gap: 6px; }
.filters-inline { display: flex; gap: 6px; margin-bottom: 6px; }
.warning { color: var(--el-color-warning-dark-2); font-size: 10px; line-height: 1.5; max-height: 35px; overflow-y: auto; }
footer { display: flex; justify-content: space-between; align-items: center; border-top: 1px solid var(--el-border-color-lighter); padding-top: 6px; margin-top: 5px; font-size: 10px; color: var(--el-text-color-secondary); }
footer span, .generated { cursor: help; }
.generated { color: var(--el-text-color-secondary); font-size: 10px; }
.filters { display: flex; gap: 12px; align-items: center; margin: 12px 0; font-size: 12px; }
.rules { font-size: 12px; color: var(--el-text-color-secondary); line-height: 1.7; margin: 8px 0; }
.percent { color: var(--el-text-color-secondary); font-size: 12px; }
</style>
