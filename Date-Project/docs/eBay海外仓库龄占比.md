# eBay 海外仓库龄占比

入口：eBay 库存明细 → 海外仓库龄占比，个人/站点两种维度，分别11列。

## 口径

- 谷仓库存来源：Java库 ods_goodcang_inventory_age_latest，保留库龄明细行，不能先取SKU最大库龄。
- 货值：iba_quantity ×（采购单价＋对应仓库国家的头程单价），人民币。
- SKU结构为“品牌-核心码-供应商编号-其他”；匹配键只保留第2、3段“核心码＋供应商编号”（保留字母及前导零），忽略品牌及第4段起的所有后缀。例如FRD-70013-0082、FRD-70013-0082-YXQ、FRD-70013-0082-GWC、FRD-70013-0082-YXQ-2、JMH-70013-0082-YXR均以70013-0082匹配；70013-0099属于另一供应商，不得混用。JMH-110147-0740-YXR以110147-0740匹配LR-110147-0740。
- 优先无任何附加后缀的三段SKU，没有三段SKU才使用同键后缀候选；同优先级沿用非JMH优先。多个优先候选取“采购价＋对应国家头程价”最高且两项均有效非负的一条，采购和头程来自同一SKU，不跨产品拼价、不跨供应商、不重复计算库存。最高价并列且负责人不同才列为归属冲突；都缺有效成本则列为成本缺失。
- 单位成本仍复用清货口径：采购价取正数阶梯价，否则cg_price；头程按US/UK/DE/CZ匹配。只修改本模块匹配规则，旧清货页的SKU匹配及不乘数量的金额逻辑不变。
- 成本和负责人均使用刷新当月的数据，不自动回退上月。负责人复用绩效品牌规则及JMH产品映射，FLL/LEJ、CL固定规则保持一致；无法归属的金额计入未分配。
- 分段：0≤库龄<90、90≤库龄<120、120≤库龄≤180、库龄>180。负数、空库龄视为异常。
- 分母是本行四档货值合计，占比存0至1的比值，页面格式化为百分数。总货值为0时占比为null，显示--。
- 站点沿用库存页映射：DE/CZ/IT→德国，UK→英国，US开头→美国，FR→法国，其他保留未识别站点；头程成本仍按原仓库国家匹配。
- 个人/站点共用同一批可计价明细。缺成本或产品冲突等异常不伪造零值，异常记录保留在后台快照，页面不展示排除明细及缺数标签；全无可计价明细时刷新失败，保留旧快照。

## 刷新和历史

模块自己的“刷新统计”只读已落库源数据，不调用外部接口，不改变库存明细/历史透视/滞销清货。
统计日期取北京时间当天；同一天刷新覆盖当日，跨日保留。快照同时保存个人、站点、来源批次/时间、规则月份及异常明细。
查询历史只读已保存JSON，不按今天的负责人或成本重算。源数据拉取时间与统计生成时间分别展示。
页面按开始日期至结束日期筛选（包含首尾），各统计日分别展示个人/站点数据，不跨天汇总金额或重新计算占比。无快照日期不补造数据；空区间显示无统计快照。初次进入或清空范围读取最新统计日；刷新统计后切回当天。

## 部署

先对Python业务库执行 RuoYi-Vue-springboot3/sql/20260929_ebay_inventory_age_ratio.sql。
新表 ebay_inventory_age_ratio_snapshot；脚本默认库名date-project，部署库名不同应调整USE。
再部署Python、Java和Vue。新模块读取复用 operations:ebayInventoryDetail:list，刷新复用 operations:ebayInventoryDetail:import；无新菜单权限SQL。

Java接口：GET /finance/ebay-inventory-detail/age-ratio?statDate=latest，
范围查询：GET /finance/ebay-inventory-detail/age-ratio?startDate=2026-09-01&endDate=2026-09-30（范围优先于单日参数）。
POST /finance/ebay-inventory-detail/age-ratio/recalculate（不接受客户端统计日期/金额/筛选）。
Python路径前缀 /api/v1/finance/ebay-inventory-detail，参数使用stat_date或start_date/end_date；保留内部Token验证。范围两端必须同时提供、使用YYYY-MM-DD且开始日期不晚于结束日期。
