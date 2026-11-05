// Display-only lineage, verified against amz_profit_report_service.py.
// Header tooltips never calculate values or call upstream APIs.
const settlementApi = '领星 POST /bd/profit/statistics/open/msku/list（利润统计-MSKU，结算口径，currencyCode=USD）。每月7日05:00按≤7天分段拉取上个自然月，页面不实时调用。'
const settlementTable = 'date-project.dwd_lingxing_profit_msku_month（日记录按 店铺sid＋MSKU 汇总为月）'
const orderApi = '领星 POST /basicOpen/finance/mreport/OrderProfit（订单利润-MSKU，订单口径，currencyCode=USD）。每月7日05:00整月拉取上个自然月。'
const orderTable = 'date-project.ods_lingxing_order_profit_msku_month'
const targetApi = '无外部接口；取月度库存报表的“销售目标（USD）”。'
const targetTable = 'date-project.monthly_inventory_report_view_snapshot（库存月＝报表月−1；组别取GROUP、店铺取STORE、个人取OWNER维度的AMZ行；组别不含US3展示行，MJ、ZXY各用各的目标）'
const scope = '口径同月度库存：剔除斯露星、斯鑫雅、水金余等店铺；智贸云、优贝诺只保留MSKU含zmy/dsq；组别按店铺名前缀（US3按店铺分MJ/ZXY）；个人按各月AMZ负责人规则（US按店铺，EU按SKU品牌/OTH编码，UK固定负责人）逐月归属后再汇总，匹配不上归“未分配”。选多个月时为各月之和。\n货币：源数据按USD拉取；选人民币时，整个时间段的金额 × 时间段最大月份的领星USD「我的汇率」（dim_lingxing_currency_month.my_rate，不用官方汇率rate_org），上期用上期最大月份的汇率；销量等数量不换算。'
const ratioEmpty = '分母为0或缺少数据时显示--，不按0计算。'
const arrow = '涨跌图标：与上期同一指标比较（红色上升、绿色下降）。上期为所选区间之前、月数相同的区间（选2026-07至2026-09则上期为2026-04至2026-06，单月即上月）。图标右侧为变化幅度——金额、销量为（本期−上期）÷|上期|，比率类为本期−上期的百分点（pp）；上期有月份未拉取时不显示图标，上期为0时不显示幅度。'

function settlement(formula, emptyHandling = '所选区间各月都未拉取结算数据时显示--；部分月份未拉取时只汇总已拉取的月份（页面顶部提示缺失月份）；有数据但该行无记录时为0。') {
  return { sourceApi: settlementApi, sourceTable: settlementTable, formula: `${formula}\n${scope}`, emptyHandling }
}

export const amzProfitColumnHelp = {
  target_usd: {
    sourceApi: targetApi,
    sourceTable: targetTable,
    formula: '所选区间内各月业绩目标之和。每月目标直接引用月度库存销售目标（USD）：在库金额÷3与（在库＋在途金额）÷5，分别除以组别系数和固定汇率6.6后取平均。店铺维度为同一店铺各站点合计。选人民币时，目标 × 时间段最大月份的领星USD「我的汇率」，与销售额用同一汇率。',
    emptyHandling: '区间内各月都没有该店铺/负责人的库存目标时显示--；某月月度库存未计算时该月不计入并在顶部提示；合计为有目标行之和。'
  },
  achievement_rate: {
    sourceApi: `${settlementApi}\n${targetApi}`,
    sourceTable: `${settlementTable}\n${targetTable}`,
    formula: '达成率 ＝ 区间销售额（结算，USD）÷ 区间业绩目标。目标按固定汇率6.6折算，销售额按领星USD汇率，二者汇率口径不同。',
    emptyHandling: `无目标或目标为0时显示--。`
  },
  sales_qty: settlement(`销量 ＝ Σ totalSalesQuantity。${arrow}`),
  sales_amount: settlement(`销售额 ＝ Σ totalSalesAmount（USD）。${arrow}`),
  sales_mom: settlement('销售额环比 ＝（本期销售额 − 上期销售额）÷ |上期销售额|，上期为所选区间之前等长的区间；图标表示正负。', `上期有月份未拉取或上期销售额为0时显示--。`),
  order_gross_profit: {
    sourceApi: orderApi,
    sourceTable: orderTable,
    formula: `订单毛利润 ＝ Σ gross_profit（订单口径，USD）。${arrow}\n${scope}`,
    emptyHandling: '所选区间各月都未拉取订单利润时显示--；部分月份未拉取时只汇总已拉取的月份；有数据但该行无订单时为0。'
  },
  order_gross_margin: {
    sourceApi: orderApi,
    sourceTable: orderTable,
    formula: `订单毛利率 ＝ 订单毛利润 ÷ Σ amount（订单口径销售额）。不使用结算销售额作分母。${arrow}\n${scope}`,
    emptyHandling: ratioEmpty
  },
  settlement_gross_profit: settlement(`结算毛利润 ＝ Σ grossProfit（结算口径，USD）。${arrow}`),
  settlement_gross_margin: settlement(
    `结算毛利率 ＝ 结算毛利润 ÷（销售额＋买家运费＋促销折扣＋FBA库存赔偿＋COD＋其他收入＋收入退款额），与领星毛利率口径一致。${arrow}`,
    ratioEmpty
  ),
  return_rate: settlement(`退货率 ＝ Σ fbaReturnsQuantity ÷ 销量。${arrow}`, ratioEmpty),
  refund_rate: settlement(`退款率 ＝ Σ refundsQuantity ÷ 销量。${arrow}`, ratioEmpty),
  acos: settlement(`ACOS ＝ |Σ totalAdsCost| ÷ Σ totalAdsSales（广告费 ÷ 广告销售额）。${arrow}`, ratioEmpty),
  ad_ratio: settlement(`广告占比 ＝ |Σ totalAdsCost| ÷ 销售额。${arrow}`, ratioEmpty)
}
