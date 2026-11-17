// 与 AmzReplenishmentSnapshotMapper.xml 的当前快照口径保持一致。
// 这里解释字段的来源和规则，不将快照值误称为实时接口数据。
const listing = '领星 Listing 接口 erp/sc/data/mws/listing → amz_product_listing'
const shop = '领星店铺接口 pb/mp/shop/v2/getSellerList → shop_list'
const warehouse = '领星仓库接口 erp/sc/data/local_inventory/warehouse → warehouse'
const localInventory = '领星库存明细接口 erp/sc/routing/data/local_inventory/inventoryDetails → amz_warehouse_inventory_detail'
const productInventory = '领星产品表现接口 bd/productPerformance/openApi/asinList → amz_product_performance_inventory'
const restock = '领星补货建议接口 erp/sc/routing/restocking/analysis/getSummaryList → amz_restock_summary'
const profit = '领星订单利润接口 basicOpen/finance/mreport/OrderProfit → amz_order_profit'
const profit90 = '领星订单利润接口 basicOpen/finance/mreport/OrderProfit → amz_order_profit_90d'
const formula = '本地配置表 amz_replenishment_formula_config'

const help = {
  storeName: { source: `${shop}.store_name`, logic: '按刊登记录的 sid 匹配 Amazon 店铺（platform_code=10001）。' },
  sellerSku: { source: `${listing}.seller_sku`, logic: '商品刊登的 Seller SKU/MSKU；与多张来源表按 sid + Seller SKU 关联。' },
  imageUrl: { source: `${listing}.small_image_url`, logic: '直接显示刊登商品的小图地址。' },
  warehouseSku: { source: `${listing}.local_sku；${localInventory}.sku`, logic: '优先显示匹配到的库存明细 SKU，匹配不到时显示刊登的本地 SKU。' },
  warehouseName: { source: `${shop}.store_name；${warehouse}.name`, logic: '按店铺名称第一个“-”前的部分拼接 CTUAMZ-<前缀>中转仓；匹配到仓库时显示仓库名，找不到仓库记录时显示拼接名。' },
  asin: { source: `${listing}.asin`, logic: '直接取商品刊登的 ASIN。' },
  price: { source: `${listing}.price`, logic: '直接取商品刊登价格；页面不做汇率换算。' },
  tagName: { source: `${listing}.tag_name（接口 global_tags）`, logic: '同步时将 global_tags 中的 tagName 用逗号连接。' },
  regionGroup: { source: `${formula}.region_group`, logic: '启用的公式配置决定 US/EU 分组；店铺中转仓名称须包含在配置的 marketplaces 中。' },
  principalName: { source: `${listing}.principal_name（接口 principal_info[0].principal_name）`, logic: '取 Listing 返回的第一条负责人信息。' },
  productCategory: { source: '本地 amz_product_category.category；人工覆盖表 amz_replenishment_override.product_category', logic: '快照先按 sid + Seller SKU 取本地分类；页面查询时若有人工覆盖值，优先显示覆盖值。' },
  rating: { source: `${listing}.last_star`, logic: '直接取 Listing 评分；空字符串按空值处理。' },
  reviewCount: { source: `${listing}.review_num`, logic: '直接取 Listing 评论数。' },
  adRate: { source: `${profit}.spend_rate`, logic: '订单利润接口的 spend_rate × 100，作为百分数显示。同步请求日期为昨日往前 30 天至昨日。' },
  profitRate30d: { source: `${profit}.gross_margin`, logic: '订单利润接口的 gross_margin × 100。同步请求日期为昨日往前 30 天至昨日。' },
  refundRate90d: { source: `${profit}.refund_amount_rate`, logic: '当前代码取订单利润表 refund_amount_rate × 100；该表使用昨日往前 30 天至昨日的请求区间，字段名称虽为“90天退款率”，实际未单独拉取 90 天退款率。' },
  purchasedQty: { source: `${localInventory}.quantity_receive + product_qc_num`, logic: '对应店铺中转仓与本地 SKU，分别取 quantity_receive 和 product_qc_num 的最大值后相加；缺失按 0。页面内修改会更新 quantity_receive，重新同步源表可能覆盖该值。' },
  domesticStock: { source: `${localInventory}.product_valid_num`, logic: '本地 SKU 匹配店铺对应的 CTUAMZ 中转仓 WID，取可用库存最大值；不汇总所有国内仓，缺失按 0。' },
  pendingShipQty: { source: `${localInventory}.product_lock_num`, logic: '匹配店铺中转仓和本地 SKU 后取锁定库存最大值；缺失按 0。' },
  fbaStock: { source: `${productInventory}.fba_stock`, logic: '按 sid + Seller SKU 匹配；FBA在库 = 可售 + 待调仓 + 入库中 + 预留，缺失按 0。' },
  fbaInbound: { source: `${productInventory}.fba_inbound（接口 afn_inbound_shipped_quantity）`, logic: '按 sid + Seller SKU 匹配，取已发出的 FBA 在途；缺失按 0。' },
  fbaInboundWorking: { source: `${productInventory}.fba_inbound_working（接口 afn_inbound_working_quantity）`, logic: '按 sid + Seller SKU 匹配，取 FBA 计划入库；优先用接口顶层字段，缺失才回退 available_inventory 内同名字段；仍缺失按 0。' },
  totalInventory: { source: '补货快照中的 FBA在库、FBA在途', logic: '总库存 = FBA在库 + FBA在途；不含国内仓库存或 FBA计划入库。' },
  sales7d: { source: `${restock}.sales_7d（接口 sales_info.sales_total_7）`, logic: '按 sid + MSKU 匹配后取最大值；缺失按 0。' },
  sales14d: { source: `${restock}.sales_14d（接口 sales_info.sales_total_14）`, logic: '按 sid + MSKU 匹配后取最大值；缺失按 0。' },
  sales30d: { source: `${restock}.sales_30d（接口 sales_info.sales_total_30）`, logic: '按 sid + MSKU 匹配后取最大值；缺失按 0。' },
  sales60d: { source: `${restock}.sales_60d（接口 sales_info.sales_total_60）`, logic: '按 sid + MSKU 匹配后取最大值；缺失按 0。' },
  salesSpeed14d: { source: `${restock}.sales_14d`, logic: '14日均销 = 14天销量 ÷ 14，保留两位小数。' },
  salesSpeed30d: { source: `${restock}.sales_30d`, logic: '30日均销 = 30天销量 ÷ 30，保留两位小数。' },
  salesSpeed60d: { source: `${restock}.sales_60d`, logic: '60日均销 = 60天销量 ÷ 60，保留两位小数。' },
  avgMonthlySales: { source: `${restock}；${formula}`, logic: '先按公式配置的 14/30/60 日销量权重算加权日均销量，再乘 month_multiplier（默认 30），保留两位小数。' },
  safetyStock: { source: `${restock}；${formula}`, logic: '加权日均销量 × safety_days（默认 90），保留两位小数。' },
  shipQty: { source: `${restock}；${productInventory}；${formula}`, logic: '加权日均销量 × ship_days（默认 90），减去配置允许扣减的 FBA在库和 FBA在途；保留两位小数。' },
  replenishQty: { source: `${restock}；${localInventory}；${productInventory}；${formula}`, logic: '加权日均销量 × replenish_days（默认 120），减去配置启用的国内仓、已采购、FBA在库、FBA在途、待出库、FBA计划入库；再按负数开关、上下限和取整方式处理。' },
  restockDays: { source: '补货快照的总库存、补货量、加权日均销量', logic: '补货时间 =（总库存 − 最终补货量）÷ 加权日均销量，保留两位小数；日均销量为 0 时为空。' },
  remark: { source: '人工覆盖表 amz_replenishment_override.remark', logic: '用户在补货页面填写的备注；没有记录时显示空。' },
  calcTime: { source: '补货快照表 calc_time', logic: '最近一次生成当前补货快照的数据库时间，不是各上游接口的同步时间。' },
  grossProfit30d: { source: `${profit}.gross_profit`, logic: '直接取领星订单利润接口返回的人民币毛利润，要求币种 CNY；不通过利润率反推。同步请求日期为昨日往前 30 天至昨日。' },
  grossProfit90d: { source: `${profit90}.gross_profit`, logic: '直接取领星订单利润接口返回的人民币毛利润，要求币种 CNY；同步请求最近 90 个自然日。' }
}

export function getAmzReplenishmentFieldHelp(key, region) {
  if (key === 'productNature') {
    const days = region === 'EU' ? 90 : 60
    return { source: `${listing}.listing_create_date（接口 open_date_display）`, logic: `刊登日期距计算当天不超过 ${days} 天为新品（含第 ${days} 天）；超过或日期缺失为老品。` }
  }
  if (key === 'profitRate90d') {
    return region === 'EU'
      ? { source: `${profit90}.gross_margin`, logic: '当前欧洲组快照 SQL 未写入 90 天利润率，页面此列可能为空；源表虽有数据，也不会自动显示在欧洲组。' }
      : { source: `${profit90}.gross_margin`, logic: '美国组生成快照后，按 sid + Seller SKU 更新为 gross_margin × 100；接口请求最近 90 个自然日。' }
  }
  const item = help[key]
  if (!item) return null
  if (['avgMonthlySales', 'safetyStock', 'shipQty', 'replenishQty', 'restockDays'].includes(key)) {
    const weights = region === 'EU' ? '14/30/60 日默认权重 0.2/0.35/0.45' : '14/30/60 日默认权重 0.5/0.4/0.1'
    return { ...item, logic: `${item.logic} ${weights}，可由公式配置调整。` }
  }
  return item
}
