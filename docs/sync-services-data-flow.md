# 18 条同步任务 - 外部数据拉取逻辑对照

> 新项目路径: `ruoyi-system/.../service/operation/external/`  
> 旧项目路径: `Operational-Project/openapi-sdk-java/.../service/`

---

## 1. 谷仓-仓库信息

| 项 | 值 |
|---|-----|
| 新项目服务 | `GoodcangWarehouseSyncService.syncWarehouses()` |
| 旧项目服务 | `GoodcangSyncService.syncWarehouses()` |
| API | `POST https://oms.goodcang.net/public_open/base_data/get_warehouse` |
| 认证 | Header `app-token` + `app-key` |

**拉取逻辑:**
1. 调 `GoodcangClient.getWarehouses()` → 返回 `{data: [...]}`
2. `data` 是仓库列表，每个仓库含 `warehouse_code/warehouse_name/country_code/wp_list`
3. `wp_list` 是分仓列表，含 `code/name`
4. 清空 `goodcang_warehouse` 表，全量写入
5. 每个仓库×分仓笛卡尔积一条记录

**新旧差异:** 无

---

## 2. 领星-仓库信息

| 项 | 值 |
|---|-----|
| 新项目服务 | `LingxingWarehouseSyncService.syncWarehouses()` |
| 旧项目服务 | `LingxingWarehouseService.syncOverseaWarehouses()` |
| API | `POST erp/sc/data/local_inventory/warehouse` |
| 参数 | `type=1,3,4,6`, `is_delete=0`, `offset=0`, `length=1000` |
| 鉴权 | query string: `timestamp/access_token/app_key/sign`, body: 业务参数 |

**拉取逻辑:**
1. 对 `type=[1,3,4,6]` 分别调 API
2. 返回 `{total, data: [...]}`
3. `data` 每条按 `wid` 增量 upsert 到 `warehouse` 表
4. 过滤 `is_delete != 0` 的记录
5. 字段映射: `wid/name/type/sub_type/is_delete/country_code/wp_id/wp_name/t_warehouse_name/t_warehouse_code/t_country_area_name/t_status`

**注意:** `postSignedQueryAuth` — 鉴权参数在 query string，业务参数在 JSON body

---

## 3. 领星-店铺列表

| 项 | 值 |
|---|-----|
| 新项目服务 | `LingxingShopSyncService.syncShops()` |
| 旧项目服务 | `LingxingShopService.getActiveShops()` |
| API | `POST pb/mp/shop/v2/getSellerList` |
| 参数 | `platform_code=[10003,10001]`, `is_sync=1`, `status=1` |

**拉取逻辑:**
1. 调 API，传 `platform_code: [10003, 10001]`
2. 返回结构: `{code, data: {total, list: [...]}}`  **← 注意嵌套 `data.list`**
3. 按 `(platform_code, store_id)` 联合键 upsert 到 `shop_list`
4. 过滤 `status != 1` 的停用店铺

**签名关键:** `platform_code` 是数组，签名时需转紧凑 JSON `"[10003,10001]"`，不是 Java 默认 `[10003, 10001]`（多空格）。已在 `LingxingSignUtils` 修复

---

## 4. 领星-eBay商品刊登

| 项 | 值 |
|---|-----|
| 新项目服务 | `LingxingEbaySyncService.syncAll()` |
| 旧项目服务 | `LingxingEbayService.syncAllEbayItems()` |
| API | `POST basicOpen/multiplatform/ebay/list` |
| 参数 | `offset/length` + 可选 `store_ids/site_code/listing_status` |

**拉取逻辑:**
1. 分页拉取，每页200条
2. 返回 `{total, data: [...]}`
3. `data` 每条按 `item_id` 增量 upsert 到 `ebay_product_listing`
4. 完成后调 `EbayProductDedupMapper.rebuildFromListing()` 重建去重表

**字段映射要点:**
- `msku` → 提取 `sku`（`extractBaseSku`: 取前两段 / PC前缀取前三段）
- `local_sku` 默认 `""`（不是 null）
- `listing_start_time/listing_end_time` 格式 `yyyy-MM-dd HH:mm:ss`

**已知问题:** 同批 API 返回可能有重复 `item_id`，`existing` Map 已修复去重 + `INSERT IGNORE` 兜底

---

## 5. 谷仓-商品信息

| 项 | 值 |
|---|-----|
| 新项目服务 | `GoodcangProductSyncService.syncFromApi()` |
| 旧项目服务 | `GoodcangProductService.syncFromApi()` |
| API | `POST https://oms.goodcang.net/public_open/product/get_product_sku_list` |
| 参数 | `page/pageSize` |

**拉取逻辑:**
1. 分页拉取全部数据，每页100条
2. 对每条取 `product_sku` → `InventoryUtils.extractMiddleCodeForInventory()` 提取中间码
3. 按中间码去重（`putIfAbsent`）
4. 按中间码 upsert 到 `goodcang_product_info`

**字段映射:**
| API 字段 | 实体字段 |
|---------|---------|
| `product_sku` → 提取中间码 | `skuMiddle` |
| `product_title_cn` | `productNameCn` |
| `product_weight` | `realWeight` |
| `product_length` | `realLength` |
| `product_width` | `realWidth` |
| `product_height` | `realHeight` |
| 长×宽×高÷6000 | `volume` |

**与旧项目差异:** 旧项目实体用 `middleCode`，新项目用 `skuMiddle`（同一字段）

---

## 6. 领星-Amazon商品刊登

| 项 | 值 |
|---|-----|
| 新项目服务 | `LingxingAmzListingSyncService.syncAll()` |
| 旧项目服务 | `LingxingAmazonService.syncAllAmzListings()` |
| API | `POST erp/sc/data/mws/listing` |
| 参数 | `sid`, `is_pair=1`, `is_delete=0`, `status=1`, `offset/length` |

**拉取逻辑:**
1. 从 `shop_list` 取 `platform_code=10001` 的 `sid` 列表
2. 每批 20 个 sid，分页拉取（每页200条）
3. 按 `(sid, seller_sku)` 增量 upsert 到 `amz_product_listing`
4. 旧项目是 `deleteAll()` 后重建 → 新项目改为 upsert

**字段映射:** `sid/marketplace/seller_sku/asin/local_sku/local_name/status/review_num/last_star/principal_name`

**过滤:** 请求参数 `status=1` + 入库前 `if (status != 1) continue`

---

## 7. 领星-库存明细

| 项 | 值 |
|---|-----|
| 新项目服务 | `LingxingInventorySyncService.syncAll()` |
| 旧项目服务 | `LingxingWarehouseInventoryService` |
| API | `POST erp/sc/routing/data/local_inventory/inventoryDetails` |
| 参数 | `wid`, `offset/length` |

**拉取逻辑:**
1. 从配置 `lingxing.inventory-wids` 取仓库 wid 列表
2. 对每个 wid 分页拉取
3. `deleteAll()` 后全量写入 `warehouse_inventory_detail`

**字段映射:** `wid/sku/product_id/seller_id/fnsku/product_valid_num/product_lock_num/product_onway/quantity_receive`

**注意:** 所有数量字段在实体中是 `String` 类型，不是 `Integer`

---

## 8. 谷仓-入库单

| 项 | 值 |
|---|-----|
| 新项目服务 | `GoodcangGrnSyncService.syncGrnList(2)` |
| 旧项目服务 | `GoodcangSyncService.syncGrn()` |
| API | `POST /inbound_order/get_grn_list` |
| 参数 | `create_date_from/to` (最近2天), `page/pageSize=200` |

**拉取逻辑:**
1. 分页拉取最近2天的入库单
2. 按 `receiving_code` 增量 upsert 到 `goodcang_grn_list`

---

## 9. 谷仓-入库单详情

| 项 | 值 |
|---|-----|
| 新项目服务 | `GoodcangGrnSyncService.syncAllGrnDetails()` |
| 旧项目服务 | `GoodcangSyncService.syncAllGrnDetails()` |
| API | `POST /inbound_order/get_grn_detail` |
| 参数 | `receiving_code` |

**拉取逻辑:**
1. 从 `goodcang_grn_list` 取所有 `receiving_code`
2. 逐条调详情接口
3. 先删旧详情 `deleteByReceivingCode`，再 `batchInsert` 新详情
4. 优先取 `overseas_detail`，其次 `transfer_detail`

---

## 10. 领星-库存流水

| 项 | 值 |
|---|-----|
| 新项目服务 | `LingxingStatementSyncService.sync()` |
| 旧项目服务 | `LingxingWarehouseStatementService.syncStatements()` |
| API | `POST erp/sc/routing/inventoryLog/WareHouseInventory/wareHouseCenterStatement` |
| 参数 | `wids`, `types=22`, `start_date/end_date`(最近2天), `offset/length` |

**拉取逻辑:**
1. 固定仓库 `18676,18701,18675,18674,18702,18700,18699`
2. 分页拉取最近2天的流水
3. 按 `(wid, sku, opt_time)` 唯一键增量 upsert → `warehouse_statement`

**字段映射:** `statement_id/wid/ware_house_name/order_sn/ref_order_sn/seller_id/fnsku/sku/opt_time/type/type_text/sub_type/sub_type_text/product_name/product_good_num/product_bad_num`

---

## 11. 领星-采购单

| 项 | 值 |
|---|-----|
| 新项目服务 | `LingxingPurchaseOrderSyncService.sync()` |
| 旧项目服务 | `LingxingPurchaseOrderService.sync()` |
| API | `POST erp/sc/routing/data/local_inventory/purchaseOrderList` |
| 参数 | `search_field_time=create_time`, `start_date/end_date`(前一天), `offset/length=500` |

**拉取逻辑:**
1. 分页拉取前一天的采购单
2. 按 `(order_sn, create_time)` 唯一键 upsert → `purchase_order`
3. `item_list[0]` 取第一条商品明细字段

---

## 12. 领星-采购计划

| 项 | 值 |
|---|-----|
| 新项目服务 | `LingxingPurchasePlanSyncService.sync()` |
| 旧项目服务 | `LingxingPurchasePlanQueryService.sync()` |
| API | `POST erp/sc/routing/data/local_inventory/getPurchasePlans` |
| 参数 | `search_field_time=creator_time`, `start_date/end_date`(前一天), `offset/length=500` |

**拉取逻辑:**
1. 分页拉取前一天的采购计划
2. 按 `(plan_sn, sku)` 唯一键 upsert → `purchase_plan`
3. `attribute/file/msku/perm_uid/perm_username` 字段转 JSON 字符串存储

---

## 13. 刷新eBay补货快照

| 项 | 值 |
|---|-----|
| 新项目服务 | `IEbayReplenishmentSnapshotService.refreshSnapshot()` |
| 调用方式 | 内部计算，不调外部 API |
| 说明 | 从 `ebay_product_listing/warehouse_inventory_detail/goodcang_product_info` 等源表计算 |

---

## 14. 刷新eBay跟价快照

| 项 | 值 |
|---|-----|
| 新项目服务 | `IEbayPriceTrackingService.refreshSnapshot()` |
| 调用方式 | 内部计算，不调外部 API |

---

## 15. 领星-Amazon订单利润

| 项 | 值 |
|---|-----|
| 新项目服务 | `AmzOrderProfitSyncService.syncAll()` |
| 旧项目服务 | `AmzOrderProfitService.syncAll()` |
| API | `POST basicOpen/finance/mreport/OrderProfit` |
| 参数 | 按 sid 逐一拉取，`offset/length=200` |

**拉取逻辑:**
1. 从 `shop_list` 取 `platform_code=10001` 的 sid 列表
2. 对每个 sid 分页拉取利润数据
3. `deleteAll()` 后全量写入 `amz_order_profit`

**字段映射:** `sid/seller_sku/gross_margin/spend_rate/refund_amount_rate`

---

## 16. 领星-Amazon补货建议

| 项 | 值 |
|---|-----|
| 新项目服务 | `AmzRestockSummarySyncService.syncAll()` |
| 旧项目服务 | `AmzRestockSummaryService.syncAll()` |
| API | `POST erp/sc/routing/restocking/analysis/getSummaryList` |
| 参数 | 按 sid 逐一拉取 |

**拉取逻辑:**
1. 从 `shop_list` 取 Amazon sid 列表
2. 对每个 sid 分页拉取补货建议
3. `deleteAll()` 后全量写入 `amz_restock_summary`

**字段映射:** `hash_id/sid/msku/fba_sellable/fba_inbound/sales_7d~60d/avg_sales_14d~60d`

---

## 17. 领星-Amazon库存明细

| 项 | 值 |
|---|-----|
| 新项目服务 | `AmzWarehouseInventorySyncService.syncAll()` |
| 旧项目服务 | `AmzWarehouseInventoryService.syncAll()` |
| API | `POST erp/sc/routing/data/local_inventory/inventoryDetails` |
| 参数 | `wid=18680`, 分页拉取 |

**拉取逻辑:**
1. 固定 `wid=18680` 分页拉取
2. `deleteAll()` 后全量写入 `amz_warehouse_inventory_detail`

**字段映射:** `wid=18680/seller_id/sku/quantity_receive/product_valid_num/product_lock_num`

---

## 18. 刷新Amazon补货快照

| 项 | 值 |
|---|-----|
| 新项目服务 | `IAmzReplenishmentSnapshotService.refreshSnapshot()` |
| 调用方式 | 内部计算，从 AMZ 源表计算，不调外部 API |

---

## 通用注意事项

1. **鉴权方式**: 领星接口鉴权参数在 **query string** (`timestamp/access_token/app_key/sign`)，业务参数在 **JSON body**。方法 `postSignedQueryAuth`

2. **数组签名**: 参数值为 `List` 时，签名计算需转紧凑 JSON（如 `[10003,10001]`），不是 Java `toString()` 的 `[10003, 10001]`。`LingxingSignUtils` 已修复

3. **空值处理**: 旧项目 `str()` 返回 `""`，新项目部分服务返回 `null`。NOT NULL 字段必须默认 `""`

4. **响应解析**: v2 接口（店铺列表）返回 `{data: {total, list: [...]}}` 嵌套结构，不是 `{data: [...]}`

5. **批量插入去重**: 同批数据可能有重复键，需要 `existing` Map 即时更新 + `INSERT IGNORE` 兜底
