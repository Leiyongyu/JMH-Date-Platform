// 周五数据：右上角问号抽屉里的「数据来源」与两张表各列口径，和 Python ebay_friday_report_service 保持一致。

export const sourceInfo = [
  { label: '生成时间', value: '每周五 06:00 自动：先拉 eBay 在售刊登、再拉谷仓区域仓库存，然后生成两张表；只保留最新一期，新一期会覆盖上一期；有权限可用当前快照重新生成' },
  { label: 'eBay 在售刊登', value: '系统通过 eBay 接口拉取的各店铺在售 listing（最新月份批次），代替原来的数字酋长导出' },
  { label: '谷仓库存', value: '谷仓 get_product_inventory 接口的区域仓库存，只取良品可售 > 0 的行' },
  { label: '负责人', value: '当月 eBay 品牌负责人规则（与原表「运营分品」一致），按 SKU 品牌匹配' },
  { label: '店铺主站点', value: '页面右上角「店铺主站点」维护，初始数据取自原表「主」sheet 的 40 个账号' },
  { label: '中间码 → 品牌', value: '从系统里带品牌前缀的 SKU（eBay 刊登、领星本地仓库存、eBay 订单）推出，代替原表「品牌对应中间码」' }
]

export const sheetRules = [
  {
    title: '有货无货（每条在线 listing 一行）',
    rows: [
      { label: '在线库存', note: 'eBay 返回的可售数量' },
      { label: '历史售出', note: 'eBay 返回的已售数量；从没卖出过的刊登 eBay 不返回，按 0' },
      { label: '站点', note: 'eBay 站点 UK → UK；US（含 eBay 汽配）→ US；其他 → DE' },
      { label: '品牌 / 中间码', note: 'SKU 第一段 / 第二段' },
      { label: '二手', note: 'SKU 任一段为 YXR、RXY、YXQ' },
      { label: '海外仓实际库存', note: '谷仓良品可售按「中间码 + 站点 + 是否二手」汇总（与原表 SUMIFS 一致，同一中间码不同尾号合并）' },
      { label: '规划站点', note: '店铺主站点；店铺没有维护时判断显示「未配置」' },
      { label: '判断', note: '站点 = 规划站点为 T，否则为 F' }
    ]
  },
  {
    title: '海外仓库存（谷仓良品可售 > 0 的每一行）',
    rows: [
      { label: '站点', note: '仓库代码 UK → UK；USCE / USEA / USWE → US；其他（含捷克）→ DE' },
      { label: 'SKU', note: '谷仓商品编码里的 JMH 换成品牌' },
      { label: '店铺列', note: '每个店铺一列，按店铺主站点分组：同站点、同 SKU 的 listing Item 号；店铺主站点与站点不一致时写成「Item:历史售出」并标黄' },
      { label: '海外仓有货无在线链接', note: '所有店铺都没有这个 SKU 的同站点 listing 时标「无链接」' },
      { label: '负责人', note: '按换好品牌的 SKU 匹配当月 eBay 品牌负责人规则' }
    ]
  },
  {
    title: '订单售出统计（上传数字酋长「Order-交易级别」导出，只保留最新一份）',
    rows: [
      { label: '取哪些行', note: '只取平台为 eBay、库存SKU 不为空的行；作废、退款的订单照原表一起算' },
      { label: '品牌 / 中间码', note: '库存SKU 第一段 / 第二段（先去掉 2PC- / 4PC- 多件装前缀）' },
      { label: '站点', note: '币种 USD → US；EUR → DE；其他 → UK' },
      { label: '美金收入', note: '收入 × 订单汇率 ÷ 领星当月美元汇率（rate_org，按付款月份取，当月未出时用最近已出的月份）' },
      { label: '负责人', note: '当月飞书负责人规则（与系统其他报表一致）' },
      { label: '透视', note: '每个负责人：中间码 + 站点去重个数、美金收入合计、购买数量合计；总计行的去重数按全部订单重新去重' }
    ]
  }
]
