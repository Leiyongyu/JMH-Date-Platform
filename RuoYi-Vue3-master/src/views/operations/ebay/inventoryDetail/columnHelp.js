// Display-only lineage, verified against ebay_inventory_detail_repository/service.
// Do not calculate values or call upstream APIs from these header tooltips.
const inventoryApi = '领星 POST /erp/sc/routing/data/local_inventory/inventoryDetails（仓位库存明细周报任务计划每周一07:30同步，查询页面不实时调用）'
const inventoryTable = 'date-project.ods_lingxing_inventory_detail_weekly'
const inventoryBatchRule = '只取实际pulled_at最新的成功快照批次（Excel已删除不影响读取），不混合历史批次、不回退旧库存表。同仓库wid＋产品product_id多店铺记录，按product_total最大、seller_id降序选一条完整记录，再按站点＋完整SKU汇总。'
const orderImport = '数字酋长订单 Excel 导入，非 eBay 在线销量接口。系统入口：POST /operations/ebay/sku-analysis/import'
const orderTable = 'date-project.dwd_ebay_sku_analysis_order（清洗自 ods_ebay_sku_analysis_order_raw）'
const productApi = '领星 POST /erp/sc/routing/data/local_inventory/batchGetProductInfo'
const salesWindow = '全表 DATE(MAX(payment_time)) 为锚点，按站点＋完整 SKU 汇总锚点前29天00:00至锚点次日00:00（不含）的 purchase_quantity；含锚点当天共30天，不随查询当天或筛选条件变化'
const overseasScope = '海外仓：德国18699、英国18702、美国18700＋18701'
const chengduScope = '成都中转仓：德国18674、英国18675、美国18676'
const stockEmpty = '当前库存行中，该类仓库无记录或数量字段为空时按0；0正常显示，不显示--。'
const procurementPriceApi = `先由productList取得全量产品目录，再调用${productApi}，读取响应cg_price；复用已落库的采购月快照，页面查询不实时拉接口。`
const procurementPriceTable = 'jmh_data_platform.ods_lingxing_product_procurement_monthly'
const procurementPriceRule = '取全表最新snapshot_month整月批次，按完整SKU精确匹配cg_price，不区分站点、不去前缀、不按库存加权；不按SKU回退旧月份价格。按确认的人民币原值计算，不再汇率换算或额外加税。'
const procurementPriceEmpty = '未匹配、cg_price为空或价格异常时，单价和两项货值均返回null，显示--并提示原因；不把缺价当0。cg_price明确为0是有效价格，单价及两货值显示¥0.00。'

function reserved(formula = '尚未接入数据或启用计算，本轮保留空值。') {
  return {
    sourceApi: '预留字段，尚未对接接口，也未接入 Excel 导入。',
    sourceTable: '无（尚未接入源表）。',
    formula,
    emptyHandling: '当前返回 null，页面显示--；不自动填0。'
  }
}

export const inventoryColumnHelp = {
  site: {
    sourceApi: inventoryApi,
    sourceTable: `${inventoryTable}.wid`,
    formula: `${inventoryBatchRule}按仓库ID映射站点：18674/18699→德国，18675/18702→英国，18676/18700/18701→美国；按站点＋完整SKU聚合为一行，并非取订单站点作为行全集。`,
    emptyHandling: '仅纳入这7个仓库且SKU非空的库存记录；其他仓库或空SKU不生成行。无库存数据时列表为空。'
  },
  sku: {
    sourceApi: inventoryApi,
    sourceTable: `${inventoryTable}.sku`,
    formula: '取去除首尾空格后的完整SKU，按站点＋完整SKU聚合。此列不去品牌前缀；仓租的去前缀匹配仅用于仓租计算。',
    emptyHandling: '源SKU为null、空串或全空格时整条记录不参与列表。'
  },
  brand: {
    sourceApi: `派生字段，复用库存SKU来源：${inventoryApi}`,
    sourceTable: `${inventoryTable}.sku`,
    formula: '取完整SKU第一个“-”之前的内容并转大写，例如FRD-70618-0687→FRD；无“-”时取整个SKU。JMH或多件装前缀在本列不做品牌还原。',
    emptyHandling: '空SKU已在取数时过滤；若派生结果为空则显示--。此列展示前缀，负责人匹配另有品牌还原规则。'
  },
  product_name: {
    sourceApi: `优先：${orderImport}。\n备用：${productApi}（产品资料周报快照）。`,
    sourceTable: 'date-project.dwd_ebay_sku_analysis_order.product_name_cn（清洗自 ods_ebay_sku_analysis_order_raw）\n备用：date-project.ods_lingxing_product_info_weekly.product_name',
    formula: '按站点＋完整SKU取最新付款订单的中文产品名（payment_time降序、id降序，不限30天）；名称为空时，取产品资料最新批次中该完整SKU唯一的非空名称。',
    emptyHandling: '最新订单名称为空且产品资料没有唯一非空名称（缺失或名称冲突）时返回null，显示--。'
  },
  grade: {
    sourceApi: 'Excel等级表导入，非外部接口。系统入口：POST /finance/ebay-inventory-detail/grades/import；文件包含SKU、站点、等级。',
    sourceTable: 'date-project.ebay_inventory_detail_grade.grade',
    formula: '按站点＋完整SKU匹配已导入等级，保留等级原值；不使用补货2.0的计算等级。导入只更新文件中的有效键。',
    emptyHandling: '没有匹配等级时返回null，显示--；导入的无效行不覆盖已有等级。'
  },
  overseas_in_transit_quantity: {
    sourceApi: inventoryApi,
    sourceTable: `${inventoryTable}.product_onway`,
    formula: `${inventoryBatchRule}按站点＋完整SKU求SUM(product_onway)。${overseasScope}；不计成都仓。`,
    emptyHandling: stockEmpty
  },
  overseas_sellable_quantity: {
    sourceApi: inventoryApi,
    sourceTable: `${inventoryTable}.product_valid_num`,
    formula: `${inventoryBatchRule}按站点＋完整SKU求SUM(product_valid_num)。${overseasScope}；不计成都仓。`,
    emptyHandling: stockEmpty
  },
  overseas_total_quantity: {
    sourceApi: `派生字段，复用海外库存来源：${inventoryApi}`,
    sourceTable: `${inventoryTable}（product_onway、product_valid_num）`,
    formula: `海外总库存＝海外在途＋海外可售。${overseasScope}，按站点＋完整SKU计算。`,
    emptyHandling: '两个依赖数量的空值均按0后相加；合计为0时显示0。'
  },
  chengdu_in_transit_quantity: {
    sourceApi: inventoryApi,
    sourceTable: `${inventoryTable}.quantity_receive`,
    formula: `${inventoryBatchRule}按站点＋完整SKU求SUM(quantity_receive)。${chengduScope}；不使用海外仓的product_onway。`,
    emptyHandling: stockEmpty
  },
  chengdu_sellable_quantity: {
    sourceApi: inventoryApi,
    sourceTable: `${inventoryTable}.product_valid_num`,
    formula: `${inventoryBatchRule}按站点＋完整SKU求SUM(product_valid_num)。${chengduScope}；不计海外仓。`,
    emptyHandling: stockEmpty
  },
  procurement_plan_quantity: {
    sourceApi: '业务默认值，尚未接入外部接口。',
    sourceTable: '无；本页后端统一返回0，不读取采购单或补货表。',
    formula: '所有站点、SKU的采购计划默认固定为0，按0参与周期总库存及后续派生公式。',
    emptyHandling: '明确显示0，不显示--；Excel写入数值0，不留空。'
  },
  pending_outbound_quantity: {
    sourceApi: inventoryApi,
    sourceTable: `${inventoryTable}.product_total`,
    formula: `${inventoryBatchRule}按已与领星核对确认的业务口径，待出库直接取product_total，保留源字段名称和注释不改。按站点＋完整SKU汇总页面全部7个仓库：${chengduScope}；${overseasScope}。此值参与周期总库存、总库销比（月）和申购量计算。`,
    emptyHandling: stockEmpty
  },
  cycle_total_quantity: {
    sourceApi: `派生字段，已接入库存来自：${inventoryApi}。采购计划尚未接入接口。`,
    sourceTable: `${inventoryTable}（product_onway、product_valid_num、quantity_receive、product_total）；采购计划暂无源表。`,
    formula: '周期总库存＝海外总库存＋成都在途＋成都可售＋采购计划＋待出库。待出库按确认口径取product_total汇总；采购计划统一默认0并参与合计。',
    emptyHandling: '库存数量空值按0；采购计划显示0。合计为0时显示0。'
  },
  overseas_max_age_days: {
    sourceApi: '谷仓 POST /inventory/inventory_age_list，独立任务计划每周一06:00（中国时区）刷新；页面只查库，不新增接口或触发拉取。',
    sourceTable: 'jmh_data_platform.ods_goodcang_inventory_age_latest（warehouse_age、warehouse_code、product_sku、snapshot_month、pulled_at），仅保存最新成功拉取的单批数据。',
    formula: '读取最新单批全表，不按snapshot_month筛选；snapshot_month仅标记拉取归属月，pulled_at为实际拉取时间。成功拉取后事务整表覆盖、只留一批，与月度库存及滞销月快照隔离。库存SKU与来源product_sku两端仅去首段前缀，按站点＋剩余完整尾码匹配，不连续剥前缀。仓库站点映射：DE/CZ/IT→德国，UK→英国，FR→法国，US开头→美国。同一拉取批次内，同站点多仓库、多库存批次取MAX(warehouse_age)，单位为天；不加距快照日的天数，不做库存加权。直接读取ODS库龄，不依赖成本match_status或采购价格是否匹配。',
    emptyHandling: '刷新失败保留上次成功数据及其实际拉取时间。缺快照、无匹配或无效库龄时返回null，显示--并提示；真实warehouse_age=0时显示0。库存侧同站点不同完整SKU同尾码冲突，或来源侧同站点不同product_sku同尾码冲突时，也显示--并提示，不任意选一条或将冲突混合取最大值。'
  },
  sales_qty_30d: {
    sourceApi: orderImport,
    sourceTable: `${orderTable}（site_name、inventory_sku、payment_time、purchase_quantity）`,
    formula: `${salesWindow}。这是购买数量合计，不扣减退货数量。`,
    emptyHandling: '当前SKU窗口内无订单或订单源表无数据时显示0；导入时无效/空购买数量按0，负购买数量按0清洗。'
  },
  average_monthly_sales_3m: {
    sourceApi: `派生字段，复用销量来源：${orderImport}`,
    sourceTable: `${orderTable}（payment_time、purchase_quantity）`,
    formula: '近3个月均销量＝近3个完整自然月的purchase_quantity总销量÷固定3，为月均销量。按中国时区查询当月以前三个月、站点＋完整SKU统计；例如2026年9月取6、7、8月，不包含9月，不是滚动90天或近30天日均。Decimal计算，输出时四舍五入（ROUND_HALF_UP）保留2位小数，页面与Excel均显示2位；排序及总库销比（月）使用未舍入值。',
    emptyHandling: '无销量时显示0.00；缺失月份按0计，仍固定除以3，不按有销量的月份数作分母。'
  },
  in_stock_sales_ratio: {
    sourceApi: `库存：${inventoryApi}。\n销量：${orderImport}。`,
    sourceTable: `${inventoryTable}.product_valid_num\n${orderTable}（payment_time、purchase_quantity）`,
    formula: '在库库销比＝海外可售÷近30天销量（同站点＋完整SKU），以比值×100%显示，保留2位小数，如1.25显示125.00%。销量按订单全表最新付款日及前29天统计；底层Decimal比值保留6位小数，页面与Excel只改变显示格式。',
    emptyHandling: '销量缺失或为0时按比值0处理，显示0.00%；海外可售缺失按0。不会除零。'
  },
  total_stock_sales_ratio: {
    sourceApi: `库存：${inventoryApi}。\n销量：${orderImport}。`,
    sourceTable: `${inventoryTable}（product_onway、product_valid_num）\n${orderTable}（payment_time、purchase_quantity）`,
    formula: '总库销比＝海外总库存÷近30天销量＝（海外在途＋海外可售）÷近30天销量，以比值×100%显示并保留2位小数。销量按全表最新付款日及前29天统计；底层比值保留6位小数，不含成都库存，页面与Excel不重复乘100。',
    emptyHandling: '销量缺失或为0时显示0.00%；库存数量空值按0。'
  },
  unit_price_tax: {
    sourceApi: procurementPriceApi,
    sourceTable: `${procurementPriceTable}.cg_price`,
    formula: `${procurementPriceRule} 沿用“单价（含税）”列名，不据此宣称接口自动含税；Decimal原价最终按ROUND_HALF_UP保留2位小数，显示人民币。`,
    emptyHandling: procurementPriceEmpty
  },
  overseas_sellable_value: {
    sourceApi: `采购价：${procurementPriceApi}\n当前库存：${inventoryApi}。`,
    sourceTable: `${procurementPriceTable}.cg_price（按sku、snapshot_month匹配）\n${inventoryTable}.product_valid_num`,
    formula: `海外可售货值＝未舍入cg_price原价×当前海外可售。${procurementPriceRule} 原价乘库存后，货值最终按ROUND_HALF_UP保留2位，不先把单价舍入再乘。采购价月快照与当前库存可能来自不同批次时间。`,
    emptyHandling: `${procurementPriceEmpty} 有有效价格且当前海外可售为0时，货值显示¥0.00。`
  },
  overseas_total_value: {
    sourceApi: `采购价：${procurementPriceApi}\n当前库存：${inventoryApi}。`,
    sourceTable: `${procurementPriceTable}.cg_price（按sku、snapshot_month匹配）\n${inventoryTable}（product_onway、product_valid_num）`,
    formula: `海外总货值＝未舍入cg_price原价×当前海外总库存＝原价×（海外在途＋海外可售）。${procurementPriceRule} 原价乘库存后，货值最终按ROUND_HALF_UP保留2位，不先把单价舍入再乘。采购价月快照与当前库存可能来自不同批次时间。`,
    emptyHandling: `${procurementPriceEmpty} 有有效价格且当前海外总库存为0时，货值显示¥0.00。`
  },
  owner: {
    sourceApi: `《负责人划分》Excel的EBAY工作表导入：POST /finance/performance-ranking/owner-rules/import，非在线人员接口。\nJMH品牌还原的产品资料来源：${productApi}。`,
    sourceTable: 'date-project.dwd_performance_owner_rule（清洗自 ods_performance_owner_rule_raw）\n品牌还原：jmh_data_platform.ods_lingxing_product_procurement_monthly',
    formula: '取中国时区查询当月的ebay/EBAY_BRAND规则，以品牌match_key匹配principal_name；JMH先用当月产品映射还原品牌，多件装按既有品牌解析。复用月度库存规则：FLL/LEJ固定归方黎力，CL固定归陈丽，其余按当月规则。',
    emptyHandling: '未匹配或缺当月规则时显示“未分配”（固定归属除外），不是--；不自动回退上月负责人。'
  },
  warehouse_rent_30d_cny: {
    sourceApi: '谷仓 POST /public_open/finance/get_wh_inventory_storage 取单号，再 POST /public_open/finance/get_wh_inventory_storage_detail 取明细。\n汇率：领星 POST /erp/sc/routing/finance/currency/currencyMonth。',
    sourceTable: 'date-project.ods_goodcang_wh_inventory_storage_detail\ndate-project.dim_lingxing_currency_month（my_rate）',
    formula: '使用最近成功拉取批次的近30天明细（拉取日-29天00:00至拉取时刻），不随页面刷新滑窗。先按仓库＋原SKU＋币种汇总未税warehouse_rent_amount，再乘本批pulled_at月份的my_rate折人民币；不使用bill_amount，不提前截断汇率，金额最终保留2位。双方仅去SKU首段前缀后按站点＋尾码匹配。DE/CZ/IT→德国、UK→英国、FR→法国、US开头→美国。',
    emptyHandling: '无快照、匹配冲突、对应币种缺汇率或部分明细缺仓租金额时显示--并提示；有快照且该SKU无收费记录时显示0。汇率不回退其他月份；无效或非正汇率会使查询报错，不静默折算。'
  },
  total_duration_months: {
    sourceApi: '业务固定值，无外部接口。',
    sourceTable: '无；本页后端固定常量TOTAL_DURATION_MONTHS。',
    formula: '所有站点、SKU固定为4.03个月，参与申购量计算；不读取补货2.0时效或按天换算。',
    emptyHandling: '固定返回4.03，不依赖订单或库存是否有值。'
  },
  total_stock_sales_ratio_months: {
    sourceApi: `库存：${inventoryApi}。\n销量：${orderImport}。`,
    sourceTable: `${inventoryTable}（product_onway、product_valid_num、quantity_receive、product_total）\n${orderTable}（payment_time、site_name、inventory_sku、purchase_quantity）`,
    formula: '总库销比（月）＝周期总库存÷近3月均销量。近3月均销量＝中国时区查询当月以前三个完整自然月的purchase_quantity合计÷固定3，按站点＋完整SKU匹配；例如2026年9月查询取6、7、8月，时间范围6月1日00:00至9月1日00:00（不含）。不是近30天日均、预估销量2或滚动90天销量，也不按有销量月数作分母。周期总库存＝海外总库存＋成都在途＋成都可售＋采购计划＋待出库；待出库取product_total，未接入的采购计划仅合计时按0。分母不预先舍入为2位，后端Decimal原比值保留6位；页面/Excel按比值×100%显示并保留2位小数，不重复乘100。',
    emptyHandling: '三个完整月无销量或均销量为0时，原比值返回0，显示0.00%；缺失月份按0参与合计，但分母仍固定3。周期库存中的空数量按0，不会除零。'
  },
  purchase_quantity: {
    sourceApi: `派生字段。销量：${orderImport}；库存：${inventoryApi}。总时长（月）为业务固定值4.03。`,
    sourceTable: `${orderTable}（purchase_quantity、payment_time、site_name、inventory_sku）\n${inventoryTable}（product_valid_num、product_onway、quantity_receive、product_total）；总时长固定4.03，无源表。`,
    formula: '申购量＝近3个月均销量×总时长（月）－周期总库存。均销量按最近3个完整自然月总销量÷3，使用未舍入值；后端全程Decimal，公式计算完后按ROUND_HALF_UP四舍五入到整数，页面和Excel共用整数结果。不将负数截为0，不套用补货2.0建议补货量。',
    emptyHandling: '总时长固定4.03；无销量时均销量按0，库存数量空值沿用0参与合计。结果为0或负数也如实显示，不把负数改为--。'
  },
  last_sold_at: {
    sourceApi: orderImport,
    sourceTable: `${orderTable}（site_name、inventory_sku、payment_time）`,
    formula: '按站点＋完整SKU精确匹配全部历史订单，取MAX(payment_time)，只显示YYYY-MM年月（例如2026-08）。不限制近30天或近3个月，不去SKU前缀，不跨站点取最大值。',
    emptyHandling: '没有匹配订单或付款时间全为空时返回null，页面显示--、Excel留空；不填当前年月。'
  }
}
