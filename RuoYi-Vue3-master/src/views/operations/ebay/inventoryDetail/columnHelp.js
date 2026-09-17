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
const procurementPriceApi = '产品单价Excel导入：POST /finance/ebay-inventory-detail/prices/import，非领星在线价格接口。支持“产品代码”“单价(默认采购价)”表头。'
const procurementPriceTable = 'date-project.ebay_inventory_detail_price'
const procurementPriceRule = '上传按完整SKU＋价格去重；仅替换本次涉及SKU的价格集合，其他SKU保留。自动提取第二段纯数字中间码并保留前导零；跨站点按中间码匹配，取MIN(unit_price)最低价。人民币原值，不换汇、不额外加税，不再使用产品管理cg_price或库存加权单价。点击刷新后计算今日快照，旧日期不追溯重算。'
const procurementPriceEmpty = '无有效数字中间码、未导入匹配价格或价格异常时，单价与货值为null，显示--并提示，不回退产品管理价格。明确为0是有效价格，也参与最低价；缺失与0不可混同。'

function reserved(formula = '尚未接入数据或启用计算，本轮保留空值。') {
  return {
    sourceApi: '预留字段，尚未对接接口，也未接入 Excel 导入。',
    sourceTable: '无（尚未接入源表）。',
    formula,
    emptyHandling: '当前返回 null，页面显示--；不自动填0。'
  }
}

export const inventoryColumnHelp = {
  stat_date: {
    sourceApi: '无外部接口；周报成功后由库存历史快照链路生成。',
    sourceTable: 'date-project.ebay_inventory_pivot_snapshot.stat_date；明细保存于ebay_inventory_detail_history。',
    formula: '采用生成时的中国时区实际日期YYYY-MM-DD。相同日期只保留一批，明细与负责人透视同事务覆盖；不同日期长期保留。历史查询读取当时冻结值，不按最新来源或最新负责人规则重算。',
    emptyHandling: '未保存明细的日期不可选，不使用当前数据补造过去。默认选择最新已保存明细日期，无历史时列表为空。'
  },
  site: {
    sourceApi: inventoryApi,
    sourceTable: `${inventoryTable}.wid`,
    formula: `${inventoryBatchRule}按仓库ID映射站点：18674/18699→德国，18675/18702→英国，18676/18700/18701→美国；先按站点＋完整SKU取数，最终按站点＋中间码合并为一行，并非取订单站点作为行全集。`,
    emptyHandling: '仅纳入这7个仓库且SKU非空的库存记录；其他仓库或空SKU不生成行。无库存数据时列表为空。'
  },
  sku: {
    sourceApi: inventoryApi,
    sourceTable: `${inventoryTable}.sku`,
    formula: '按站点＋中间码合并为一行。代表SKU按长度最短、再按字典序确定，保留完整品牌前缀。悬浮显示全部合并SKU；搜索任一别名均返回整组，不截断汇总数据。',
    emptyHandling: '源SKU为null、空串或全空格时整条记录不参与列表。'
  },
  sku_middle_site_code: {
    sourceApi: '只读派生标识，复用当前生成行或已保存历史行的中间码、SKU和站点；不新增上游接口，不重新拉取或关联最新来源。',
    sourceTable: '当前生成行的sku_middle_code、site、sku；历史取date-project.ebay_inventory_detail_history.item_json（sku_middle_code、sku、site）及该行site、sku，不新增源表。',
    formula: '优先使用该行sku_middle_code；旧历史未保存中间码字段时，仅从该行SKU按“-”分隔后的第二段纯数字提取。以文本保留前导零，不转数字。站点仅映射德国→DE、美国→US、英国→UK；将中间码与站点代码直接拼接、不加分隔符，例如10053＋德国→10053DE，00100＋英国→00100UK。只读输出派生值，不修改历史快照，也不替代现有站点＋中间码合并键。',
    emptyHandling: '中间码缺失或非纯数字、站点缺失或不在德国/美国/英国映射中时返回null，页面显示--，Excel留空；不猜测其他站点代码。'
  },
  sku_middle_code: {
    sourceApi: `派生字段，复用库存SKU来源：${inventoryApi}`,
    sourceTable: `${inventoryTable}.sku`,
    formula: '取完整SKU按“-”分隔后的第二段数字，例如MCD-20017-0071→20017；以文本保留前导零。站点＋中间码为合并键，不同后缀、第三段或品牌前缀仍合并；原SKU保留用于源数据匹配。',
    emptyHandling: '缺少第二段、第二段为空或含非数字字符时返回null，页面显示--，Excel留空；此时仍按站点＋完整SKU分别保留，不能将所有空中间码合并。'
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
    emptyHandling: '刷新失败保留上次成功数据及其实际拉取时间。缺快照、无匹配或无效库龄时返回null，显示--并提示；真实warehouse_age=0时显示0。同一有效中间码内的前缀别名不再视为冲突，合并取有效库龄最大值；部分别名无库龄时保留提示，全部缺失才显示--。无有效中间码且匹配冲突时仍拒绝匹配。'
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
    sourceTable: `${procurementPriceTable}（middle_code、unit_price、sku）`,
    formula: `${procurementPriceRule} 沿用“单价（含税）”列名，直接使用上传价；Decimal原价最终按ROUND_HALF_UP保留2位小数，显示人民币。`,
    emptyHandling: procurementPriceEmpty
  },
  overseas_sellable_value: {
    sourceApi: `采购价：${procurementPriceApi}\n当前库存：${inventoryApi}。`,
    sourceTable: `${procurementPriceTable}（middle_code、unit_price）\n${inventoryTable}.product_valid_num`,
    formula: `海外可售货值＝未舍入的中间码最低价×合并后海外可售。${procurementPriceRule} 原价乘库存后，货值最终按ROUND_HALF_UP保留2位，不先把单价舍入再乘。`,
    emptyHandling: `${procurementPriceEmpty} 有有效价格且当前海外可售为0时，货值显示¥0.00。`
  },
  overseas_total_value: {
    sourceApi: `采购价：${procurementPriceApi}\n当前库存：${inventoryApi}。`,
    sourceTable: `${procurementPriceTable}（middle_code、unit_price）\n${inventoryTable}（product_onway、product_valid_num）`,
    formula: `海外总货值＝未舍入的中间码最低价×合并后海外总库存＝最低价×（海外在途＋海外可售）。${procurementPriceRule} 原价乘库存后，货值最终按ROUND_HALF_UP保留2位，不先把单价舍入再乘。`,
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
    emptyHandling: '无快照、跨合并组匹配冲突、对应币种缺汇率或部分明细缺仓租金额时显示--并提示；有快照且该SKU无收费记录时显示0。同一合并组共享的仓租键只计一次。汇率不回退其他月份，缺失或非正汇率不静默折算。'
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
    formula: '按站点＋完整SKU精确匹配全部历史订单，取MAX(payment_time)，显示YYYY-MM-DD年月日（例如2026-08-31），不显示时分秒。不限制近30天或近3个月，不去SKU前缀，不跨站点取最大值。',
    emptyHandling: '没有匹配订单或付款时间全为空时返回null，页面显示--、Excel留空；不填当前日期。旧历史只有年月时保持原值，不补造日期；重新生成今天快照后按年月日显示。'
  }
}


// Original-SKU source matching and product-level aggregation are separate stages.
const sumFields = [
  'overseas_in_transit_quantity', 'overseas_sellable_quantity', 'overseas_total_quantity',
  'chengdu_in_transit_quantity', 'chengdu_sellable_quantity', 'procurement_plan_quantity',
  'pending_outbound_quantity', 'cycle_total_quantity', 'sales_qty_30d'
]
for (const key of sumFields) {
  inventoryColumnHelp[key].formula += ' 最终按站点＋中间码汇总各原SKU数量；筛选和分页在合并之后，仓库范围不变。'
}
inventoryColumnHelp.brand.formula += ' 合并行展示代表SKU的品牌；品牌筛选可命中任一成员品牌，返回完整合并行。'
inventoryColumnHelp.product_name.formula += ' 合并后按代表SKU排序取首个有值的名称。'
inventoryColumnHelp.grade.formula += ' 合并行取唯一非空等级；成员等级不同则显示--并提示，不任意挑选。等级筛选命中任一成员后返回整组。'
inventoryColumnHelp.owner.formula += ' 合并SKU负责人一致时保留；若将来出现不一致，合并行归入未分配并提示，不任意转移个人货值。'
inventoryColumnHelp.overseas_max_age_days.formula += ' 最终在同站点＋中间码的成员SKU间取最大有效库龄。'
inventoryColumnHelp.average_monthly_sales_3m.formula += ' 合并时先汇总所有成员的三月总销量，再除以3；不累加已舍入均销量。'
for (const key of ['in_stock_sales_ratio', 'total_stock_sales_ratio', 'total_stock_sales_ratio_months']) {
  inventoryColumnHelp[key].formula += ' 最终使用合并后的库存及销量重新计算，禁止累加各原SKU的库销比。'
}
inventoryColumnHelp.warehouse_rent_30d_cny.formula += ' 最终按站点＋中间码合并；所有成员匹配到的不同仓租尾码金额相加，相同尾码只计一次，避免品牌别名重复收费。'
inventoryColumnHelp.warehouse_rent_30d_cny.emptyHandling += ' 上述为空规则针对单个原匹配键；合并行有部分有效仓租时只汇总有值金额并提示缺失，全部匹配键缺失才显示--。'
inventoryColumnHelp.total_duration_months.formula += ' 合并后仍固定4.03，不累加总时长。'
inventoryColumnHelp.purchase_quantity.formula += ' 合并后用汇总的未舍入三月总销量和周期总库存计算，最后只四舍五入一次，不相加原SKU已取整申购量。'
inventoryColumnHelp.last_sold_at.formula += ' 合并后取所有成员的最近售出日期；全部没有订单才留空。'
inventoryColumnHelp.stat_date.formula += ' 新生成的明细按站点＋中间码一行，负责人透视的SKU数也按合并后计数；旧日期快照不追溯重算。'
