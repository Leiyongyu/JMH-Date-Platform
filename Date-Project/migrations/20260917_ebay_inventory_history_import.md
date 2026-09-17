# Ebay库存明细：一次性Excel历史填充

## 部署与使用

1. 备份数据库后，执行同目录 `20260917_ebay_inventory_history_import.sql`。仅在 `date-project.ebay_inventory_detail_history` 增加 `record_key`，将唯一索引改为 `(snapshot_id,site,sku,record_key)`；不删除或改写原历史内容。既有明细历史表/日期主表须已建立。
2. 部署Python、编译重启Java、部署前端。此迁移需要显式执行，重启不替代迁移。
3. 复用权限 `operations:ebayInventoryDetail:import`，无需新菜单SQL。
4. Ebay库存明细 → **导入历史数据** → 选择原Excel，核对导入行数/日期数。导入成功后自动查询文件最新日期；其他日期在统计日期选择器查看。不要为查看历史点击“刷新”：刷新仍只重新计算今天。
5. 文件上限50MiB，解压上限300MiB，三个sheet合计最多100000行；等级/单价上传仍限10MiB。浏览器/Java历史请求预算300秒。部署Nginx等代理时单独确认上传体积和超时满足这些限制；413/504不能视为导入未提交，可重传同文件查询幂等结果。

## 接口

- Java：POST `/finance/ebay-inventory-detail/history/import`，multipart字段`file`；认证用户作为operator，IMPORT审计与导入权限。
- Python：POST `/api/v1/finance/ebay-inventory-detail/history/import`，内部Token访问，不公开给浏览器。
- 成功返回 `imported_rows`、`imported_dates`、`skipped_existing_dates`、`duplicate_rows_preserved`、`missing_sku_rows`、`empty_cells`、起止日期及每sheet行数。
- 不接收客户端统计日期，不按当前日期改写历史，不访问外部接口或当前库存/负责人/采购价。

## 保存规则

- 只读`库存明细持续更新-US/DE/UK`三个sheet，站点分别为美国/德国/英国；其他sheet完全不导入。
- 统计时间按原表日期，必须有效；sheet缺失、表头缺失/重复、日期或站点冲突会整份拒绝。
- 已确认所有原始行保留：同日同站点同SKU不去重、不合并、不汇总。空/错误SKU也保留，页面显示`--`；以sheet代码和原行号作为独立勾选标识。
- 空值、0、Excel错误（如#N/A、#DIV/0!）、数值字段无法识别的文本保存JSON null，页面及历史导出显示`--`。正常数值用Decimal保存；不套新公式、不执行Excel公式，仅取文件已保存的公式缓存。未缓存公式视为缺失。
- 所有日期在一个事务中写入，失败全部回滚。使用与刷新/周报相同的命名锁。已有日期若不是同一文件的完整导入批次，整份拒绝，绝不自动覆盖。
- 相同文件按SHA256识别，重传不增加行；字节改变的文件不视为同一文件。数据库每个统计日期仍只有一个主批次。
- 只填明细，**不生成或修改负责人历史透视**。统计日期中的历史空档不补造。
- `最后售出时间`按文本保存原有月.日值，例如`7.3`、`07.30`，不推断年份、不补日期，不执行订单查询。
- JSON保存完整映射值、原sheet/行号，主批次记录文件名、SHA256、操作者、导入时间。保留未展示的“对应仓库”和“实际申购数”，避免丢失。

## 字段对应

| 原表列 | 页面字段/存储字段 |
| --- | --- |
| 统计时间 | 统计日期 stat_date |
| 中间码+站点 | sku_middle_site_code；不自动补值 |
| 核心码 | 中间码 sku_middle_code；保留文本前导零 |
| 产品代码 | SKU sku |
| 品牌 / 产品名称 / 等级 | brand / product_name / grade |
| 海外在途 / 海外可售 / 海外总库存 | overseas_in_transit_quantity / overseas_sellable_quantity / overseas_total_quantity |
| 成都在途 / 成都可售 | chengdu_in_transit_quantity / chengdu_sellable_quantity |
| 采购计划 / 待出库 / 整个周期总库存 | procurement_plan_quantity / pending_outbound_quantity / cycle_total_quantity |
| 海外最高库龄 | overseas_max_age_days |
| 对应仓库 | source_warehouse，保留JSON，不新增页面列 |
| 近30天销量 | sales_qty_30d |
| 近3月均销量/预估销量 | 近3个月均销量 average_monthly_sales_3m；只保存该混合列的历史值 |
| 在库库销比 / 总库销比 | in_stock_sales_ratio / total_stock_sales_ratio；保存原比值，文本25%规范为0.25，页面百分比显示，不用库存/销量重算 |
| 单价(含税) | unit_price_tax |
| 海外可售货值 / 海外总货值 | overseas_sellable_value / overseas_total_value |
| 负责人 / UK的11月负责人 | owner；不查当前规则 |
| 30天谷仓仓租 | warehouse_rent_30d_cny；原值，不换汇 |
| 站点 | sheet对应美国/德国/英国，校验原列一致 |
| 总时长（月） / 总库销比（月） | total_duration_months / total_stock_sales_ratio_months；不改成当前4.03，不重新除法 |
| 按公式申购 | 申购量 purchase_quantity；不重新计算 |
| 实际申购数 | source_actual_purchase_quantity，保留JSON，不冒充公式申购量 |
| 最后售出时间 | last_sold_at，保留月日文本 |

## 本地验证（2026-09-17）

- 原文件只读解析：75,590行，US 25,561、DE 29,940、UK 20,089；46个日期，2025-10-14至2026-09-07。
- 保留重复48行。原空SKU 3行，加上SKU错误/0共8行显示`--`，未丢弃。
- 经用户授权，迁移SQL本地执行两次，验证幂等；原明细1,926行、主批次1个，原字段内容SHA256前后完全一致。
- **未自动导入原文件**，由用户在页面选择上传。未启动同步任务，未重算快照。
- 相关自动化覆盖：Python库存全套测试、Vue上传/分页/勾选测试、Java内部转发及方法级权限测试。使用内存工作簿与本地HTTP桩，不写入用户历史文件。

## 核对SQL

```sql
SELECT stat_date, trigger_type, item_count, group_count
FROM `date-project`.ebay_inventory_pivot_snapshot ORDER BY stat_date;
SELECT s.stat_date, d.site, COUNT(*) AS row_count
FROM `date-project`.ebay_inventory_detail_history d
JOIN `date-project`.ebay_inventory_pivot_snapshot s ON s.id=d.snapshot_id
WHERE s.trigger_type='EXCEL_IMPORT'
GROUP BY s.stat_date,d.site ORDER BY s.stat_date,d.site;
```
