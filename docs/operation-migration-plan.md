# Operational-Project to JMH-Date-Platform Migration Plan

生成时间：2026-06-18

目标：将旧项目 `Operational-Project` 中可用的 eBay/AMZ 补货、每日跟价、领星/谷仓数据拉取、计算快照、手工维护和定时任务，迁移到新项目 `JMH-Date-Platform`，后续新功能只在新项目开发。

## 1. 当前判断

### 1.1 旧项目现状

旧项目后端：`Operational-Project/openapi-sdk-java`

旧项目前端：`Operational-Project/inventory front-end`

旧项目数据库：`middleground`

旧项目核心特点：

- 业务链路完整，已经能跑通。
- 技术边界不清晰，Controller、接口同步、计算、日志、权限耦合较重。
- eBay 补货和每日跟价共用 `inventory_overview`，字段混杂，后续扩展风险较高。
- 谷仓仓库与领星仓库存在名称模糊匹配逻辑，应迁移为显式映射。
- 一键同步主要在 `SyncController` 中硬编码，不适合作为长期调度中心。

### 1.2 新项目现状

新项目后端：`JMH-Date-Platform/RuoYi-Vue-springboot3`

新项目前端：`JMH-Date-Platform/RuoYi-Vue3-master`

新项目数据库：`jmh_data_platform`

新项目已有承接点：

- 若依用户、角色、菜单、权限、日志、Quartz 定时任务基础能力。
- eBay 补货快照后端：`/operations/ebay/replenishment`
- AMZ 补货快照后端：`/operations/amz/replenishment`
- eBay 补货前端页面：`src/views/operations/ebay/replenishment/index.vue`
- AMZ 补货前端页面：`src/views/operations/amz/replenishment/index.vue`
- 新库已有规范化快照表：
  - `ebay_replenishment_snapshot`
  - `ebay_price_tracking_snapshot`
  - `ebay_product_profile`
  - `amz_replenishment_snapshot`
  - `warehouse_mapping`
  - `data_sync_log`

当前不足：

- 新库大量源数据表为空，只有快照层有部分迁移数据。
- 新项目尚未完整迁移领星/谷仓接口。
- 新项目尚未迁移 eBay/AMZ 计算服务。
- 新项目尚未迁移每日跟价维护能力。
- 新项目尚未配置业务 Quartz 任务。

## 2. 迁移原则

1. 不整包复制旧项目。
   将旧项目拆成外部接口、源数据、计算服务、快照表、页面、调度六层迁入若依。

2. 保留旧项目可用业务逻辑。
   计算口径先保持一致，迁移后再逐步优化性能和模型。

3. 新库成为唯一业务库。
   迁移完成后新项目不依赖 `middleground`。

4. 源数据与业务快照分离。
   源数据用于追溯和重算，快照表用于页面高性能查询。

5. 手工维护字段独立保存。
   eBay 跟价、OE、备注、底线价、最低价等字段迁入 `ebay_product_profile`，不要继续写入混合快照表。

6. 定时任务可观测、可重跑、可防重。
   所有同步任务接入若依 Quartz、Redis 锁、`data_sync_log`。

## 3. 数据库迁移方案

### 3.1 源数据表迁移

这些表应从 `middleground` 迁入 `jmh_data_platform`，作为后续同步和重算的基础：

| 旧表 | 新表 | 迁移方式 | 说明 |
| --- | --- | --- | --- |
| `warehouse` | `warehouse` | 全量复制后由领星同步维护 | 领星仓库基础表 |
| `warehouse_inventory_detail` | `warehouse_inventory_detail` | 全量复制后由领星同步维护 | 领星库存明细 |
| `shop_list` | `shop_list` | 全量复制后由领星同步维护 | eBay/AMZ 店铺 |
| `ebay_product_listing` | `ebay_product_listing` | 全量复制后由领星同步维护 | eBay listing 源数据 |
| `ebay_sales` | `ebay_sales` | 全量复制，后续 Excel 或接口维护 | eBay 销量 |
| `ebay_link_template` | `ebay_link_template` | 全量复制，后续页面维护 | eBay 链接模板 |
| `brand_owner` | `brand_owner` | 全量复制，后续对接若依用户 | 品牌负责人 |
| `amz_product_listing` | `amz_product_listing` | 全量复制后由领星同步维护 | AMZ listing 源数据 |
| `amz_order_profit` | `amz_order_profit` | 全量复制后由领星同步维护 | AMZ 利润 |
| `amz_restock_summary` | `amz_restock_summary` | 全量复制后由领星同步维护 | AMZ 补货建议 |
| `amz_warehouse_inventory_detail` | `amz_warehouse_inventory_detail` | 全量复制后由领星同步维护 | AMZ 仓库库存 |
| `amz_product_category` | `amz_product_category` | 全量复制，后续页面维护 | AMZ 分类手工字段 |
| `goodcang_warehouse` | `goodcang_warehouse` | 全量复制后由谷仓同步维护 | 谷仓仓库 |
| `goodcang_grn_list` | `goodcang_grn_list` | 全量复制后由谷仓同步维护 | 谷仓入库单 |
| `goodcang_grn_detail` | `goodcang_grn_detail` | 全量复制后由谷仓同步维护 | 谷仓入库明细 |
| `goodcang_product_info` | `goodcang_product_info` | 全量复制后由谷仓同步维护 | 谷仓商品成本/重量体积 |
| `purchase_order` | `purchase_order` | 全量复制后由领星同步维护 | 采购单 |
| `purchase_plan` | `purchase_plan` | 全量复制后由领星同步维护 | 采购计划 |
| `purchase_plan_submit` | `purchase_plan_submit` | 按业务确认迁移 | 创建采购计划提交记录 |
| `warehouse_statement` | `warehouse_statement` | 全量复制后由领星同步维护 | 库存流水 |

### 3.2 旧混合快照拆分

旧表 `inventory_overview` 不建议作为新项目长期核心表。它应拆成：

| 旧表/字段来源 | 新表 | 用途 |
| --- | --- | --- |
| `inventory_overview` 补货字段 | `ebay_replenishment_snapshot` | eBay 补货页面 |
| `inventory_overview` 跟价字段 + `ebay_product_dedup` 手工字段 | `ebay_price_tracking_snapshot` | 每日跟价页面 |
| `ebay_product_dedup` 手工维护字段 | `ebay_product_profile` | eBay 产品画像/跟价维护 |

旧表 `amz_inventory_overview` 应迁入：

| 旧表 | 新表 | 用途 |
| --- | --- | --- |
| `amz_inventory_overview` | `amz_replenishment_snapshot` | AMZ 补货页面 |

### 3.3 不建议原样迁移的表

| 旧表 | 建议 |
| --- | --- |
| `user` | 不迁入业务用户体系，统一使用若依 `sys_user` |
| `team` | 视是否仍需要运营团队维度，必要时映射到若依部门或业务团队表 |
| `operation_log` | 不原样迁移，后续使用若依操作日志 + `data_sync_log` |
| `user_column_config` | 可迁移为新平台列配置，但不要绑定旧用户 ID |
| `profit_report` | 当前无数据，暂缓迁移 |

## 4. 后端迁移模块

### 4.1 包结构建议

在 `ruoyi-system` 中新增业务包：

```text
com.ruoyi.system.domain.operation
com.ruoyi.system.mapper.operation
com.ruoyi.system.service.operation
com.ruoyi.system.service.operation.impl
com.ruoyi.system.service.operation.sync
com.ruoyi.system.service.operation.compute
com.ruoyi.system.service.operation.external.lingxing
com.ruoyi.system.service.operation.external.goodcang
```

在 `ruoyi-admin` 中新增或扩展 Controller：

```text
com.ruoyi.web.controller.operation
com.ruoyi.web.controller.operation.sync
```

### 4.2 领星接口迁移清单

| 旧服务 | 新服务建议 | 依赖表 | 优先级 |
| --- | --- | --- | --- |
| `LingxingAuthService` | `LingxingAuthService` | Redis/token 配置 | P0 |
| `ApiSign` | `LingxingSignService` 或工具类 | 无 | P0 |
| `LingxingWarehouseService` | `LingxingWarehouseSyncService` | `warehouse` | P0 |
| `LingxingWarehouseInventoryService` | `LingxingInventorySyncService` | `warehouse_inventory_detail` | P0 |
| `LingxingShopService` | `LingxingShopSyncService` | `shop_list` | P0 |
| `LingxingEbayService` | `LingxingEbayListingSyncService` | `ebay_product_listing`, `ebay_product_profile` | P0 |
| `LingxingAmazonService` | `LingxingAmzListingSyncService` | `amz_product_listing` | P0 |
| `AmzOrderProfitService` | `LingxingAmzProfitSyncService` | `amz_order_profit` | P0 |
| `AmzRestockSummaryService` | `LingxingAmzRestockSyncService` | `amz_restock_summary` | P0 |
| `AmzWarehouseInventoryService` | `LingxingAmzWarehouseInventorySyncService` | `amz_warehouse_inventory_detail` | P1 |
| `LingxingPurchaseOrderService` | `LingxingPurchaseOrderSyncService` | `purchase_order` | P0 |
| `LingxingPurchasePlanQueryService` | `LingxingPurchasePlanSyncService` | `purchase_plan` | P0 |
| `LingxingWarehouseStatementService` | `LingxingWarehouseStatementSyncService` | `warehouse_statement` | P1 |
| `LingxingPurchasePlanService` | `LingxingPurchasePlanSubmitService` | `purchase_plan_submit` | P2 |

### 4.3 谷仓接口迁移清单

| 旧服务 | 新服务建议 | 依赖表 | 优先级 |
| --- | --- | --- | --- |
| `GoodcangClient` | `GoodcangClient` | 配置/签名 | P0 |
| `GoodcangSyncService.syncWarehouses` | `GoodcangWarehouseSyncService` | `goodcang_warehouse`, `warehouse_mapping` | P0 |
| `GoodcangSyncService.syncGrn` | `GoodcangGrnSyncService` | `goodcang_grn_list` | P0 |
| `GoodcangSyncService.syncAllGrnDetails` | `GoodcangGrnDetailSyncService` | `goodcang_grn_detail` | P0 |
| `GoodcangProductService.syncFromApi` | `GoodcangProductSyncService` | `goodcang_product_info` | P0 |

### 4.4 计算服务迁移清单

| 旧服务 | 新服务建议 | 输出表 | 优先级 |
| --- | --- | --- | --- |
| `InventoryComputeEngine` | `OperationInventoryComputeEngine` | 中间计算结果 | P0 |
| `InventoryOverviewServiceImpl.refreshSnapshot` | `EbayReplenishmentComputeService.refreshSnapshot` | `ebay_replenishment_snapshot` | P0 |
| `DailyPriceTrackingServiceImpl.refreshTable` | `EbayPriceTrackingComputeService.refreshSnapshot` | `ebay_price_tracking_snapshot` | P0 |
| `AmazonComputeService.refreshSnapshot` | `AmzReplenishmentComputeService.refreshSnapshot` | `amz_replenishment_snapshot` | P0 |
| `EbayProductDedupServiceImpl.rebuildFromListing` | `EbayProductProfileService.rebuildFromListing` | `ebay_product_profile` | P0 |

重要调整：

- `InventoryOverviewServiceImpl` 不再写旧 `inventory_overview`。
- `DailyPriceTrackingServiceImpl` 不再混写 `inventory_overview`。
- `AmazonComputeService` 不再写旧 `amz_inventory_overview`。
- 页面查询全部读新快照表。

## 5. 前端迁移范围

### 5.1 已有页面

| 页面 | 当前状态 | 后续动作 |
| --- | --- | --- |
| eBay 补货 | 已有页面，读 `ebay_replenishment_snapshot` | 修复中文编码显示，补齐刷新/同步按钮 |
| AMZ 补货 | 已有页面，读 `amz_replenishment_snapshot` | 修复中文编码显示，补齐分类维护 |

### 5.2 待迁页面

| 旧页面 | 新页面建议 | 优先级 |
| --- | --- | --- |
| `DailyPriceTrackingView.vue` | `operations/ebay/priceTracking/index.vue` | P0 |
| `LinkTemplateView.vue` | eBay 跟价配置页或弹窗 | P1 |
| `BrandOwnerView.vue` | 品牌负责人管理 | P1 |
| `AmzReplenishmentView.vue` | 已有页面增强 | P0 |
| `AmzPurchaseView.vue` | AMZ 采购/发货扩展页 | P2 |
| `PurchasePlanCreateView.vue` | 采购计划创建 | P2 |
| `PurchaseListView.vue` | 采购单/采购计划查询 | P2 |
| `OperationLogView.vue` | 使用若依日志和同步日志替代 | P1 |

## 6. 定时任务设计

### 6.1 任务拆分

旧项目 `/api/sync/all` 应拆为若依 Quartz 任务：

| 任务 Bean | 建议 Cron | 内容 | 防重 |
| --- | --- | --- | --- |
| `operationSyncTask.syncLingxingBaseData` | 每天 01:00 | 领星仓库、店铺 | Redis 锁 |
| `operationSyncTask.syncEbayListings` | 每天 01:30 | eBay listing，重建 eBay profile | Redis 锁 |
| `operationSyncTask.syncEbayOperationData` | 每天 02:00 | eBay 销量、采购单、采购计划、库存流水 | Redis 锁 |
| `operationSyncTask.syncGoodcangData` | 每天 03:00 | 谷仓仓库、入库单、入库明细、商品信息 | Redis 锁 |
| `operationSyncTask.syncAmzData` | 每天 04:00 | AMZ listing、利润、补货建议、仓库库存 | Redis 锁 |
| `operationSyncTask.refreshEbaySnapshots` | 每天 05:00 | eBay 补货、每日跟价快照重算 | Redis 锁 |
| `operationSyncTask.refreshAmzSnapshots` | 每天 05:30 | AMZ 补货快照重算 | Redis 锁 |
| `operationSyncTask.fullSync` | 手动触发 | 串行/分阶段执行全链路 | Redis 锁 |

### 6.2 同步日志

所有任务统一写入 `data_sync_log`：

- `sync_type`
- `sync_name`
- `status`
- `trigger_type`
- `operator`
- `start_time`
- `end_time`
- `total_count`
- `success_count`
- `fail_count`
- `error_message`
- `request_params`

若任务由若依 Quartz 触发，同时保留若依 `sys_job_log`。

## 7. 迁移执行步骤

### 阶段 0：冻结迁移基线

- 记录老库 `middleground` 表行数。
- 记录新库 `jmh_data_platform` 表行数。
- 导出老项目当前可用页面截图或 Excel 样本。
- 明确迁移期间是否允许老项目继续写入。

验收：

- 形成一份行数基线表。
- 明确迁移窗口。

### 阶段 1：数据库结构和数据迁移

- 执行或修正 `jmh_data_platform_normalized_migration.sql`。
- 补齐新库空源表数据。
- 确认新库源表行数与老库一致。
- 给快照表、源表核心字段补索引。

验收：

- 新库源表行数与老库一致。
- 三张快照表可重新生成。
- `warehouse_mapping` 人工检查通过。

### 阶段 2：页面查询迁移

- eBay 补货页面继续读 `ebay_replenishment_snapshot`。
- AMZ 补货页面继续读 `amz_replenishment_snapshot`。
- 新增每日跟价页面，读 `ebay_price_tracking_snapshot`。
- 接入若依权限码和菜单。

验收：

- 页面查询、分页、排序、导出可用。
- 与旧项目导出数据抽样一致。

### 阶段 3：计算服务迁移

- 迁移 `InventoryComputeEngine`。
- 将 eBay 补货计算输出改为 `ebay_replenishment_snapshot`。
- 将每日跟价计算输出改为 `ebay_price_tracking_snapshot`。
- 将 AMZ 补货计算输出改为 `amz_replenishment_snapshot`。

验收：

- 新项目可以从源表独立重算快照。
- 快照总行数与旧项目口径接近或一致。
- 抽样 20 个 SKU 对比核心字段一致。

### 阶段 4：接口同步迁移

- 迁移领星鉴权和签名。
- 迁移领星各同步服务。
- 迁移谷仓同步服务。
- 所有同步写 `data_sync_log`。

验收：

- 手动触发单项同步成功。
- 手动触发全链路同步成功。
- 同步失败时能看到错误和失败步骤。

### 阶段 5：Quartz 定时任务接入

- 新增 `OperationSyncTask`。
- 在若依 `sys_job` 配置业务任务。
- 配置 Redis 分布式锁。
- 配置任务超时、失败告警或日志查看方式。

验收：

- 任务能按 Cron 执行。
- 任务不会并发重复跑。
- 任务日志完整。

### 阶段 6：旧项目下线

- 新旧项目并跑 3 到 7 天。
- 每天对比快照行数和核心字段。
- 关闭老项目定时同步。
- 新功能只在新项目开发。

验收：

- 新项目数据连续稳定。
- 老项目停止写入后业务不受影响。

## 8. 对账清单

### 8.1 行数对账

每次迁移后检查：

```sql
SELECT 'warehouse', COUNT(*) FROM warehouse
UNION ALL SELECT 'warehouse_inventory_detail', COUNT(*) FROM warehouse_inventory_detail
UNION ALL SELECT 'shop_list', COUNT(*) FROM shop_list
UNION ALL SELECT 'ebay_product_listing', COUNT(*) FROM ebay_product_listing
UNION ALL SELECT 'ebay_product_profile', COUNT(*) FROM ebay_product_profile
UNION ALL SELECT 'ebay_replenishment_snapshot', COUNT(*) FROM ebay_replenishment_snapshot
UNION ALL SELECT 'ebay_price_tracking_snapshot', COUNT(*) FROM ebay_price_tracking_snapshot
UNION ALL SELECT 'amz_product_listing', COUNT(*) FROM amz_product_listing
UNION ALL SELECT 'amz_replenishment_snapshot', COUNT(*) FROM amz_replenishment_snapshot
UNION ALL SELECT 'goodcang_warehouse', COUNT(*) FROM goodcang_warehouse
UNION ALL SELECT 'goodcang_grn_list', COUNT(*) FROM goodcang_grn_list
UNION ALL SELECT 'goodcang_grn_detail', COUNT(*) FROM goodcang_grn_detail
UNION ALL SELECT 'purchase_order', COUNT(*) FROM purchase_order
UNION ALL SELECT 'purchase_plan', COUNT(*) FROM purchase_plan;
```

### 8.2 业务字段抽样

eBay 补货抽样字段：

- `site`
- `sku`
- `overseas_sellable`
- `overseas_total`
- `local_sellable`
- `local_onway`
- `sales_7d`
- `sales_30d`
- `sales_90d`
- `suggest_purchase_qty`
- `owner_name`

每日跟价抽样字段：

- `site`
- `sku`
- `our_lowest_price`
- `tracking_price`
- `tracking_profit_margin`
- `floor_price`
- `oe_number`
- `presale_url`
- `sold_url`
- `estimated_replenish_qty`

AMZ 补货抽样字段：

- `sid`
- `seller_sku`
- `warehouse_sku`
- `asin`
- `fba_stock`
- `fba_inbound`
- `sales_7d`
- `sales_30d`
- `avg_monthly_sales`
- `safety_stock`
- `ship_qty`
- `replenish_qty`

## 9. 风险和处理

| 风险 | 表现 | 处理 |
| --- | --- | --- |
| 中文编码异常 | 页面和源码中文乱码 | 统一文件 UTF-8，迁移时修复显示文本 |
| 源表未迁全 | 快照能看但不能重算 | 阶段 1 必须补齐源表 |
| 手工字段丢失 | OE、备注、跟价字段为空 | 先迁 `ebay_product_profile`，再重算快照 |
| 仓库映射错误 | eBay 站点库存不准 | 使用 `warehouse_mapping` 人工确认，废弃模糊匹配 |
| 同步并发重复 | 数据被清空后重复插入 | Redis 锁 + 任务状态日志 |
| 接口限流或失败 | 同步中断 | 分页重试、失败续跑、记录失败页 |
| 旧用户权限不兼容 | 运营人员看不到数据 | 品牌负责人映射到若依用户/角色 |
| SQL 性能差 | 页面慢、导出慢 | 快照表索引 + SQL 分页排序，避免内存全量过滤 |

## 10. 优先级总表

P0 必做：

- 源表数据迁移到新库。
- eBay/AMZ 快照表稳定查询。
- 每日跟价页面和 `ebay_product_profile` 维护。
- 领星核心同步。
- 谷仓核心同步。
- eBay/AMZ 快照重算。
- 若依 Quartz 业务任务。
- 数据对账。

P1 增强：

- 同步日志页面。
- 品牌负责人管理。
- 链接模板管理。
- 仓库映射维护页面。
- 用户列配置迁移。

P2 后续：

- 采购计划创建。
- AMZ 采购/发货扩展。
- 更细的失败续跑和告警。
- 计算逻辑性能重构。

## 11. 推荐下一步

下一步先做阶段 1：

1. 备份 `middleground` 和 `jmh_data_platform`。
2. 修正并执行业务源表迁移 SQL。
3. 对比新老库行数。
4. 校验 `warehouse_mapping`。
5. 从新库重算三张快照。

完成阶段 1 后，再开始迁移若依后端服务。这样不会把问题混在代码迁移里，排查会简单很多。

## 12. 核心字段映射附录

### 12.1 eBay 补货快照

来源：旧表 `inventory_overview`

目标：新表 `ebay_replenishment_snapshot`

| 旧字段 | 新字段 | 说明 |
| --- | --- | --- |
| `warehouse_names` | `site` | 站点，原字段名实际含义不是仓库名 |
| `sku` | `sku` | 补货 SKU |
| `product_name` | `product_name` | 产品名 |
| `sku_level` | `sku_level` | SKU 等级 |
| `last30_days_profit` | `profit_rate_30d` | 近 30 天利润率 |
| `return_rate` | `return_rate` | 退货率 |
| `overseas_onway` | `overseas_onway` | 海外在途 |
| `overseas_sellable` | `overseas_sellable` | 海外可售 |
| `overseas_total` | `overseas_total` | 海外总库存 |
| `purchase_pending_delivery` | `purchase_pending_delivery` | 采购待交付 |
| `local_sellable` | `local_sellable` | 本地可售 |
| `local_onway` | `local_onway` | 本地在途 |
| `purchase_plan` | `purchase_plan_qty` | 采购计划数量 |
| `lock_num` | `locked_qty` | 待出库/锁定数量 |
| `total_inventory` | `total_inventory` | 总库存 |
| `last7_days_sales` | `sales_7d` | 7 天销量 |
| `last30_days_sales` | `sales_30d` | 30 天销量 |
| `last90_days_sales` | `sales_90d` | 90 天销量 |
| `max_monthly_sales` | `max_monthly_sales` | 历史最大月销量 |
| `overseas_in_stock_ratio` | `overseas_sellable_sales_ratio` | 海外可售库销比 |
| `overseas_total_ratio` | `overseas_total_sales_ratio` | 海外总库存库销比 |
| `total_inventory_ratio` | `total_inventory_sales_ratio` | 总库存库销比 |
| `last_local_outbound_time` | `last_local_outbound_time` | 最近本地出库时间 |
| `outbound_days` | `outbound_days` | 出库天数 |
| `purchase_cycle` | `purchase_cycle_days` | 采购周期 |
| `purchase_quantity` | `suggest_purchase_qty` | 建议采购数量 |
| `max_monthly_replenish` | `max_monthly_replenish_qty` | 最大月销补货量 |
| `owner` | `owner_name` | 负责人 |
| `id` | `source_overview_id` | 来源旧快照 ID |
| `updated_at` | `calc_time` | 计算时间 |

### 12.2 eBay 每日跟价快照

来源：旧表 `inventory_overview` + `ebay_product_dedup`

目标：新表 `ebay_price_tracking_snapshot`

| 旧字段 | 新字段 | 说明 |
| --- | --- | --- |
| `inventory_overview.warehouse_names` | `site` | 站点 |
| `inventory_overview.sku` | `sku` | SKU |
| `inventory_overview.product_name` | `product_name` | 产品名 |
| `inventory_overview.sku_level` | `sku_level` | SKU 等级 |
| `inventory_overview.our_lowest_price` / `ebay_product_dedup.lowest_price` | `our_lowest_price` | 我方最低价 |
| `ebay_product_dedup.tracking_price` | `tracking_price` | 跟卖价 |
| `ebay_product_dedup.tracking_profit_margin` | `tracking_profit_margin` | 跟卖利润率 |
| `ebay_product_dedup.floor_price` | `floor_price` | 底线价 |
| `inventory_overview.return_rate` / `ebay_product_dedup.return_rate` | `return_rate` | 退货率 |
| `inventory_overview.last3_days_sales` | `sales_3d` | 3 天销量 |
| `inventory_overview.last7_days_sales` | `sales_7d` | 7 天销量 |
| `inventory_overview.last30_days_sales` | `sales_30d` | 30 天销量 |
| `inventory_overview.last90_days_sales` | `sales_90d` | 90 天销量 |
| `inventory_overview.max_monthly_sales` | `max_monthly_sales` | 历史最大月销量 |
| `inventory_overview.overseas_warehouse_stock` | `overseas_stock` | 海外库存 |
| `inventory_overview.overseas_warehouse_age` | `overseas_stock_age_days` | 海外库龄 |
| `inventory_overview.stock_sales_ratio` | `stock_sales_ratio` | 库销比 |
| `inventory_overview.estimated_replenish` | `estimated_replenish_qty` | 预计补货量 |
| `inventory_overview.brand` | `brand_code` | 品牌 |
| `inventory_overview.operator` | `operator_name` | 操作员/负责人 |
| `inventory_overview.oe_number` / `ebay_product_dedup.oe_number` | `oe_number` | OE 号，优先手工维护值 |
| `inventory_overview.ebay_frontpage_url` | `presale_url` | 售前链接 |
| `inventory_overview.frontpage_sold_url` | `sold_url` | 售后链接 |
| `ebay_product_dedup.remark` | `remark` | 备注 |
| `inventory_overview.id` | `source_overview_id` | 来源旧快照 ID |
| `ebay_product_profile.id` | `source_profile_id` | 来源产品画像 ID |

### 12.3 eBay 产品画像

来源：旧表 `ebay_product_dedup`

目标：新表 `ebay_product_profile`

| 旧字段 | 新字段 | 说明 |
| --- | --- | --- |
| `site` | `site` | 站点 |
| `sku` | `sku` | 归一化 SKU |
| `product_name` | `product_name` | 产品名 |
| `oe_number` | `oe_number` | 手工维护 OE |
| `tracking_price` | `tracking_price` | 手工维护跟卖价 |
| `tracking_profit_margin` | `tracking_profit_margin` | 跟卖利润率 |
| `floor_price` | `floor_price` | 底线价 |
| `remark` | `remark` | 备注 |
| `profit_rate` | `profit_rate_30d` | 导入的 30 天利润率 |
| `return_rate` | `return_rate` | 导入或维护的退货率 |
| `lowest_price` | `lowest_price` | 我方最低价 |
| `lowest_item_number` | `lowest_item_number` | 最低价 item number |
| `lowest_upload_time` | `lowest_upload_time` | 最低价导入时间 |
| `id` | `source_dedup_id` | 来源旧去重表 ID |

### 12.4 AMZ 补货快照

来源：旧表 `amz_inventory_overview`

目标：新表 `amz_replenishment_snapshot`

| 旧字段 | 新字段 | 说明 |
| --- | --- | --- |
| `sid` | `sid` | 店铺 sid |
| `seller_sku` | `seller_sku` | Seller SKU |
| `warehouse_sku` | `warehouse_sku` | 仓库 SKU |
| `warehouse_name` | `warehouse_name` | 仓库名 |
| `asin` | `asin` | ASIN |
| `principal_name` | `principal_name` | 负责人 |
| `store` | `store_name` | 店铺名 |
| `product_category` | `product_category` | 产品分类 |
| `last_star` | `rating` | 评分 |
| `review_num` | `review_count` | 评论数 |
| `ad_rate` | `ad_rate` | 广告费率 |
| `profit_rate30d` | `profit_rate_30d` | 30 天利润率 |
| `refund_rate90d` | `refund_rate_90d` | 90 天退款率 |
| `purchased_qty` | `purchased_qty` | 已采购数量 |
| `domestic_stock` | `domestic_stock` | 国内库存 |
| `pending_ship` | `pending_ship_qty` | 待发货/待出库 |
| `fba_stock` | `fba_stock` | FBA 在库 |
| `fba_inbound` | `fba_inbound` | FBA 在途 |
| `total_inventory` | `total_inventory` | 总库存 |
| `sales7d` | `sales_7d` | 7 天销量 |
| `sales14d` | `sales_14d` | 14 天销量 |
| `sales30d` | `sales_30d` | 30 天销量 |
| `sales60d` | `sales_60d` | 60 天销量 |
| `sales_speed14d` | `sales_speed_14d` | 14 日均销 |
| `sales_speed30d` | `sales_speed_30d` | 30 日均销 |
| `sales_speed60d` | `sales_speed_60d` | 60 日均销 |
| `avg_monthly_sales` | `avg_monthly_sales` | 平均月销量 |
| `safety_stock` | `safety_stock` | 安全库存 |
| `ship_qty` | `ship_qty` | 发货量 |
| `replenish_qty` | `replenish_qty` | 补货量 |
| `restock_days` | `restock_days` | 补货天数 |
| `id` | `source_overview_id` | 来源旧快照 ID |
