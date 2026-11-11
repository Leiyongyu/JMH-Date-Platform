// AMZ月度利润表「页面说明」：整体逻辑、数据来源、各列口径与核对方法。
// 只做展示，不参与计算；口径与 Date-Project/backend/services/amz_monthly_profit_service.py 一致，改口径时两边一起改。

export const sourceInfo = [
  { label: '数据来源', value: '领星「财务 > 利润报表」，结算口径（按结算日期归月），交易状态「已发放」' },
  { label: '接口', value: '利润报表-MSKU（/bd/profit/report/open/report/msku/list）出数；利润报表-店铺（/bd/profit/report/open/report/seller/list）只用来核对' },
  { label: '币种', value: '人民币。请求时直接要 CNY，由领星按它自己的汇率折算，与在领星页面导出的报表一致；不用系统月度汇率换算' },
  { label: '拉取时间', value: '每月 7 日 06:00 自动拉取上个月；同一月份重新拉取会整月覆盖' },
  { label: '数据表', value: 'date-project.ods_lingxing_profit_report_msku_month（MSKU）、ods_lingxing_profit_report_seller_month（店铺）、fin_amz_monthly_profit_adjustment（手工补充费用）' }
]

export const logicSteps = [
  { title: '拉取', text: '按月拉领星利润报表 MSKU 明细与店铺汇总（人民币）。两份数据按店铺核对销量、销售额，对不上时页面顶部黄色提示，说明可能没拉全。' },
  { title: '剔除', text: '与月度库存、AMZ利润报表同一套规则：剔除关停店铺（斯露星、斯鑫雅、水金余等）；智贸云、优贝诺只保留 MSKU 含 zmy / dsq 的；不属于 EU / US1 / US2 / US3 的店铺（如信博嘉立）不进报表。剔除行数见表格底部。' },
  { title: '归属', text: '组别取领星店铺名第一段（EU-伶斯勋-DE → EU），店铺名取中间段（伶斯勋）。同一店铺主体的各站点（DE / FR / UK…）合并为一行。US3 按月度库存的部门规则拆成 MJ（新志楠、富琳顿）和 ZXY（其余）。' },
  { title: '店铺利润', text: '按「组别 + 店铺名」把 MSKU 汇总；最终毛利 = 毛利润 − FBA途损。' },
  { title: '小组利润', text: '按组别汇总，US3 下面列出 MJ、ZXY；US3 = MJ + ZXY，合计 = EU + US1 + US2 + US3。手工补充费用记在 EU / US1 / US2 / MJ / ZXY 这几行上，记到哪一列就加到哪一列，并计入最终毛利。' },
  { title: '最终毛利', text: '最终毛利 = 毛利润 − FBA途损抵扣 + 手工补充费用。FBA途损抵扣本身是负数，减去即把途损成本加回。' }
]

// 各列：来源（领星字段 / 手工 / 计算）与说明。key 与后端列定义一致。
export const columnHelp = {
  sales_qty: { source: 'totalSalesQuantity', note: '销量（FBA + FBM，含多渠道）' },
  refunds_qty: { source: 'refundsQuantity', note: '退款数量' },
  returns_qty: { source: 'fbaReturnsQuantity', note: 'FBA 退货数量' },
  sales_amount: { source: 'totalSalesAmount', note: '销售额（不含税）' },
  shipping_credits: { source: 'shippingCredits', note: '买家支付的运费' },
  promotional_rebates: { source: 'promotionalRebates', note: '促销折扣，通常为负数' },
  fba_inventory_credit: { source: 'fbaInventoryCredit', note: '亚马逊对 FBA 库存丢失、损坏的赔偿' },
  other_in_amount: { source: 'otherInAmount', note: '其他收入（清算、赔偿收入等）' },
  sales_refunds: { source: 'totalSalesRefunds', note: '收入退款额，负数' },
  fee_refunds: { source: 'totalFeeRefunds', note: '平台退回的费用，正数' },
  platform_fee: { source: 'platformFee', note: '平台佣金' },
  fba_delivery_fee: { source: 'totalFbaDeliveryFee', note: 'FBA 发货费合计（含多渠道、客户退货费）' },
  other_transaction_fees: { source: 'otherTransactionFees', note: '其他订单费用' },
  ads_cost: { source: 'totalAdsCost', note: '广告费（SP / SB / SBV / SD 及分摊差异）' },
  promotion_fee: { source: 'promotionFee', note: '推广费（优惠券、秒杀、Vine、订阅费等）' },
  storage_fee: { source: 'totalStorageFee', note: 'FBA 仓储费合计（月度、长期、移除、销毁等）' },
  inbound_convenience_fee: { source: 'sharedFbaInboundConvenienceFee', note: '入库配置费' },
  adjustment_fee: { source: 'adjustments', note: '调整费用' },
  platform_other_fee: { source: 'totalPlatformOtherFee', note: '平台其他费（运输标签、清算费等）' },
  store_tax_fee: { source: 'otherFeeStr「店铺税务相关」', note: '领星自定义费用（财务在领星里录入）；小组利润另含手工补充' },
  warehouse_fee: { source: 'otherFeeStr「仓库费用」', note: '领星自定义费用；小组利润另含手工补充' },
  store_operation_fee: { source: 'otherFeeStr「店铺运营费」', note: '领星自定义费用；小组利润另含手工补充' },
  slow_moving_fee: { source: 'otherFeeStr「滞销库存费用」', note: '领星自定义费用；小组利润另含手工补充' },
  tax_risk_fee: { source: 'otherFeeStr「税务风险金」', note: '领星自定义费用；小组利润另含手工补充' },
  store_rent_fee: { source: 'otherFeeStr「店租费（法人补贴等）」', note: '领星自定义费用；小组利润另含手工补充' },
  supplement_fee: { source: '手工录入', note: '不属于以上任何费用列的手工补充金额（仅小组利润）' },
  purchase_cost: { source: 'cgPriceTotal', note: '采购成本' },
  first_leg_cost: { source: 'cgTransportCostsTotal', note: '头程成本' },
  gross_profit: { source: 'grossProfit', note: '领星算好的毛利润。除表中各列外，还含 COD、FBA国际物流货运费、站外推广费、税费、其他成本等未单列项目，所以表中各列相加不一定等于毛利润' },
  transit_loss: { source: '采购 / 头程 / 其他成本明细中编码 226（FBA发货途损）+ 11（FBA途损补回）', note: 'FBA 途损抵扣，负数表示途损成本；领星月结后仍会调整' },
  final_profit: { source: '计算', note: '毛利润 − FBA途损抵扣 + 手工补充费用' },
  gross_margin: { source: '计算', note: '最终毛利 ÷（销售额 + 买家运费 + 促销折扣 + FBA库存赔偿 + 其他收入 + 收入退款额 + 费用退款额）' },
  refund_rate: { source: '计算', note: '退款量 ÷ 销量' },
  return_rate: { source: '计算', note: '退货量 ÷ 销量' },
  platform_fee_ratio: { source: '计算', note: '平台费 ÷（销售额 + 买家运费 + 促销折扣 + FBA库存赔偿 + 其他收入）' },
  fba_delivery_fee_ratio: { source: '计算', note: 'FBA发货费 ÷ 同上分母' },
  ads_cost_ratio: { source: '计算', note: '广告费 ÷ 同上分母' },
  storage_fee_ratio: { source: '计算', note: 'FBA仓储费 ÷ 同上分母' },
  purchase_cost_ratio: { source: '计算', note: '采购成本 ÷ 同上分母' },
  first_leg_cost_ratio: { source: '计算', note: '头程成本 ÷ 同上分母' }
}

export const checkSteps = [
  '销量、销售额：领星「财务 > 利润报表 > 店铺」选同一月份、结算、人民币，按店铺加总各站点后应与本页店铺利润一致（系统拉取时已自动核对，不一致会在页面顶部提示）。',
  '某家店某一列对不上：到领星利润报表 MSKU 维度筛这家店的所有站点，看对应字段合计；注意智贸云、优贝诺只算 MSKU 含 zmy / dsq 的部分。',
  '毛利润是领星直接给的，表中各列相加不等于毛利润属正常（还含未单列的 COD、国际物流货运费、站外推广费、税费、其他成本）。',
  '与领星页面数字有小差异时，先看本页「拉取时间」：领星月结后仍会调整（尤其 FBA 途损），以拉取那一刻为准；需要按最新数重出时，在定时任务里对「AMZ月度利润表数据拉取」执行 syncMonth(\'2026-09\') 这类补拉。',
  '小组利润与店铺利润合计不一致时，差额就是手工补充费用，点「补充费用」可看到每一笔及维护人。'
]
