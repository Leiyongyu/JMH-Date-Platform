// eBay月度利润表「页面说明」：整体逻辑、数据来源、各列口径与核对方法。
// 只做展示，不参与计算；口径与 Date-Project/backend/services/ebay_monthly_profit_service.py 一致，改口径时两边一起改。

export const sourceInfo = [
  { label: '交易流水', value: 'eBay Finances 接口（/sell/finances/v1/transaction），全部有授权的店铺；按美国太平洋时间切月，与卖家后台「交易报告」逐条一致' },
  { label: '订单明细', value: 'eBay Fulfillment 订单接口补 SKU、标题、数量；多件订单按商品行拆开' },
  { label: '采购 / 头程', value: '「店铺分析 > SKU分析」导入的数字酋长订单文件，按平台订单号对上交易里的订单' },
  { label: '尾程 / 仓储', value: '谷仓账单接口（billing_list → billing_export），只取 eBay 账户 ACG1064502，账单截止时间落在该月的账单' },
  { label: '仓储按人', value: '谷仓仓租明细（每周同步）按 SKU 归人；与账单仓储费的差额每人平均分' },
  { label: '超龄货值', value: '与「滞销清货」同一套库龄快照，取次月初拍的那份（反映当月底库存，如 10 月报表用 11 月初快照）：海外 91～180 天、180 天以上按站点、按负责人；成都仓 30 天以上按负责人，站点平均分' },
  { label: '汇率', value: '财务每月录入的中行折算价月均值（USD、EUR、GBP）' },
  { label: '拉取时间', value: '每月 7 日 05:00 拉谷仓账单、05:30 拉 eBay 交易流水（AMZ月度利润表 06:00），同一月份重拉整月覆盖' },
  { label: '数据表', value: 'date-project.ods_ebay_finance_transaction、ods_goodcang_bill_fee、fin_ebay_monthly_profit_rate、fin_ebay_monthly_profit_adjustment' }
]

export const logicSteps = [
  { title: '折人民币', text: '每条交易：交易币种金额 × eBay 实际折算率 × 中行美元价，逐行四舍五入到分（同手工表 ROUND）。' },
  { title: '分类', text: '订单 → 销售总额（商品小计+运费，不含 eBay 代收税）；退款、索赔、付款纠纷按关联单号区分；冻结 / 解冻、调整、运单进其他费用；非销售费用描述含 Promoted / value fee / ads 的是广告费，其余是刊登 / 副标题。' },
  { title: '站点', text: '按交易币种：USD → US，EUR → DE，GBP → UK；US 一组，其余为 EU。只有美元金额的调整类交易按店铺当月销售额最多的站点。采购、头程按订单本身的站点。' },
  { title: '负责人', text: 'SKU 第一段品牌按当月 eBay 负责人规则（飞书负责人表）；没有 SKU 或品牌未分配的金额，按各人平台收入占比分摊。' },
  { title: '分摊项', text: '店铺运营费按总额录入：US 1/2、DE 1/4、UK 1/4，个人平均；GU仓销毁：三站各 1/3，个人平均；积分抵扣按站点、按人分别录入。' },
  { title: '毛利', text: '毛利 = 平台净收入 + 采购 + 采购运费 + 头程 + 头程关税 + 尾程 + 仓储 + 店铺运营 + 借货清货 + 成都仓折扣 + 资金占用费 + 包装耗材 + 刷单抵扣 + 积分抵扣 + 税务风险金 + GU仓销毁 + 其他补充。' }
]

export const columnHelp = {
  platform_income: { source: '销售总额 + 退款 + 赔偿', note: '退款、赔偿为负数' },
  platform_expense: { source: '成交费 + 罚款 + 广告费 + 刊登/副标题 + 其他费用', note: '负数' },
  platform_net: { source: '交易净额合计', note: '实际回款（含税费差，所以 ≠ 收入 + 支出）' },
  platform_payback: { source: '平台收入 + 平台支出', note: '' },
  purchase_cost: { source: 'SKU分析订单文件 采购成本(¥)', note: '同 SKU 同成本的重复行：订单行数量 > 1 时只算一次' },
  purchase_freight: { source: '补充费用', note: '易仓采购运费，按站点录入' },
  first_leg_cost: { source: 'SKU分析订单文件 头程运费', note: '整单的数，每单取一次' },
  first_leg_duty: { source: '补充费用', note: '按站点录入' },
  tail_fee: { source: '谷仓账单 除仓储费外的费用', note: '出库、入库、退货、增值、理赔返还；按币种分站点' },
  storage_fee: { source: '谷仓账单 仓储费', note: '个人表按仓租明细归人，差额平均分' },
  store_operation: { source: '补充费用（总额）', note: '紫鸟等，US 1/2、DE 1/4、UK 1/4，个人平均' },
  loan_clear: { source: '补充费用', note: '借货 / 清货调整' },
  ctu_discount: { source: '补充费用', note: '成都仓折扣' },
  capital_cost: { source: '计算', note: '−（91-180天×12% + 180天+×24% + 成都仓30天+×12%）×30/360' },
  packaging: { source: '补充费用', note: '包装耗材' },
  brushing: { source: '补充费用', note: '刷单 SKU 采购成本抵扣' },
  points: { source: '补充费用', note: '积分抵扣，站点、个人分别录入（填人民币）' },
  tax_risk: { source: '计算', note: '−平台收入 × 1%' },
  gu_destruction: { source: '补充费用（总额）', note: '三站各 1/3，个人平均' },
  supplement: { source: '补充费用', note: '不属于现有列的金额' },
  other_cost: { source: '计算', note: '税务风险金 + 资金占用费' },
  gross_profit: { source: '计算', note: '见整体逻辑「毛利」' },
  gross_margin: { source: '毛利 ÷ 平台收入', note: '分母为 0 显示 --' },
  ctu_30: { source: '库龄快照（成都仓）', note: '30 天以上货值' },
  over_180: { source: '库龄快照（海外仓）', note: '180 天以上货值' },
  over_90_180: { source: '库龄快照（海外仓）', note: '91～180 天货值' },
  refund: { source: '退款交易 毛额', note: '' },
  claim: { source: '索赔交易 毛额', note: '' },
  fvf: { source: '成交费（固定 + 按比例）+ 监管运营费 + 跨国交易费', note: '退款时为正（返还）' },
  penalty: { source: '描述不符过高费 + 表现不合格费', note: '' },
  ads: { source: '推广刊登、站外推广等非销售费用', note: '' },
  listing: { source: '刊登费、副标题、跨国费、店铺订阅费等', note: '' },
  other_fee: { source: '冻结 / 解冻、付款纠纷、调整、运单', note: '' },
  sales: { source: '订单 商品小计 + 运费', note: '不含 eBay 代收税' },
  order_count: { source: '订单数', note: '' }
}

export const checkSteps = [
  '交易：卖家后台「付款 > 报告」下载某店当月交易报告（Transaction report），条数、净额与该店「店铺利润」的平台净收入（÷中行美元价）一致；后台报告里的 Payout（放款）行不计入利润表。',
  '尾程 / 仓储：与谷仓后台同月两张账单的费用合计（按币种 × 中行汇率）一致。',
  '采购 / 头程：与「SKU分析」当月导入文件按订单汇总一致；没有成本的订单数见页面顶部提示。',
  '没有授权的店铺（如 Global Auto Store）不在表内，需要补授权或另行加总。'
]
