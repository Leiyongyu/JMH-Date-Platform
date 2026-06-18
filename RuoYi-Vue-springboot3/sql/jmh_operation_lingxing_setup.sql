USE `jmh_data_platform`;

-- Lingxing backend permission buttons.
-- Adjust parent_id if your operations menu uses a different menu id.
SET @parent_id := (
  SELECT menu_id FROM sys_menu
  WHERE perms = 'operations:ebayReplenishment:list'
  ORDER BY menu_id
  LIMIT 1
);

INSERT INTO sys_menu (
  menu_name, parent_id, order_num, path, component, query, route_name,
  is_frame, is_cache, menu_type, visible, status, perms, icon,
  create_by, create_time, update_by, update_time, remark
)
SELECT '领星Token测试', COALESCE(@parent_id, 0), 1, '#', '', NULL, '',
       1, 0, 'F', '0', '0', 'operations:lingxing:test', '#',
       'admin', NOW(), '', NULL, ''
WHERE NOT EXISTS (SELECT 1 FROM sys_menu WHERE perms = 'operations:lingxing:test');

INSERT INTO sys_menu (
  menu_name, parent_id, order_num, path, component, query, route_name,
  is_frame, is_cache, menu_type, visible, status, perms, icon,
  create_by, create_time, update_by, update_time, remark
)
SELECT '领星接口调用', COALESCE(@parent_id, 0), 2, '#', '', NULL, '',
       1, 0, 'F', '0', '0', 'operations:lingxing:call', '#',
       'admin', NOW(), '', NULL, ''
WHERE NOT EXISTS (SELECT 1 FROM sys_menu WHERE perms = 'operations:lingxing:call');

-- Chinese comments for operation tables migrated from the old project.
ALTER TABLE `ebay_replenishment_snapshot` COMMENT = 'eBay补货计算快照';
ALTER TABLE `ebay_price_tracking_snapshot` COMMENT = 'eBay每日跟价计算快照';
ALTER TABLE `ebay_product_profile` COMMENT = 'eBay产品画像与跟价手工维护表';
ALTER TABLE `amz_replenishment_snapshot` COMMENT = 'Amazon补货计算快照';
ALTER TABLE `warehouse_mapping` COMMENT = '领星仓库与谷仓仓库映射表';
ALTER TABLE `data_sync_log` COMMENT = '业务数据同步执行日志';
ALTER TABLE `warehouse` COMMENT = '领星仓库基础表';
ALTER TABLE `warehouse_inventory_detail` COMMENT = '领星仓库库存明细表';
ALTER TABLE `shop_list` COMMENT = '领星店铺列表表';
ALTER TABLE `ebay_product_listing` COMMENT = '领星eBay商品Listing源数据表';
ALTER TABLE `ebay_product_dedup` COMMENT = '旧版eBay商品去重与跟价维护表';
ALTER TABLE `ebay_sales` COMMENT = 'eBay销量导入明细表';
ALTER TABLE `brand_owner` COMMENT = '品牌负责人维护表';
ALTER TABLE `ebay_link_template` COMMENT = 'eBay售前售后链接模板表';
ALTER TABLE `goodcang_warehouse` COMMENT = '谷仓仓库基础表';
ALTER TABLE `goodcang_grn_list` COMMENT = '谷仓入库单列表表';
ALTER TABLE `goodcang_grn_detail` COMMENT = '谷仓入库单明细表';
ALTER TABLE `goodcang_product_info` COMMENT = '谷仓商品成本重量体积信息表';
ALTER TABLE `purchase_order` COMMENT = '领星采购单明细表';
ALTER TABLE `purchase_plan` COMMENT = '领星采购计划明细表';
ALTER TABLE `warehouse_statement` COMMENT = '领星仓库库存流水表';
ALTER TABLE `inventory_overview` COMMENT = '旧版eBay补货与每日跟价混合快照表';
