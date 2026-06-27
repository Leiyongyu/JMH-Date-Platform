-- jmh_data_platform schema alignment
-- Direction: D:/JMH/jmh_data_platform.sql -> D:/JMH/jmh_data_platform_new.sql
-- Data migration is not included.

-- Missing table: amz_fba_shipment_box
CREATE TABLE IF NOT EXISTS `amz_fba_shipment_box`  (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `sid` int NOT NULL COMMENT '店铺id',
  `shipment_id` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL COMMENT '货件编号',
  `box_type` varchar(20) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT NULL COMMENT 'SINGLE/MULTIPLE',
  `box_length` varchar(20) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT NULL COMMENT '箱子长',
  `box_width` varchar(20) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT NULL COMMENT '箱子宽',
  `box_height` varchar(20) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT NULL COMMENT '箱子高',
  `box_weight` varchar(20) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT NULL COMMENT '箱子重',
  `box_dimensions_unit` varchar(10) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT 'cm' COMMENT '长度单位',
  `box_weight_unit` varchar(10) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT 'kg' COMMENT '重量单位',
  `box_num` int NULL DEFAULT 1 COMMENT '箱数',
  `msku` varchar(200) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT NULL COMMENT '货件MSKU',
  `sku` varchar(200) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT NULL COMMENT 'local_sku(从amz_product_listing映射)',
  `product_name` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT NULL COMMENT '商品名称',
  `fulfillment_network_sku` varchar(200) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT NULL COMMENT 'FNSKU',
  `quantity_in_case` varchar(20) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT NULL COMMENT '单箱数量',
  `create_time` datetime NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`) USING BTREE,
  UNIQUE INDEX `uk_ship_box_msku`(`sid` ASC, `shipment_id` ASC, `box_num` ASC, `msku` ASC) USING BTREE
) ENGINE = InnoDB CHARACTER SET = utf8mb4 COLLATE = utf8mb4_0900_ai_ci COMMENT = 'FBA货件装箱信息' ROW_FORMAT = Dynamic;

-- Existing table supplement: amz_fba_shipment_box.product_name
SET @col_exists := (
  SELECT COUNT(1)
  FROM information_schema.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'amz_fba_shipment_box'
    AND COLUMN_NAME = 'product_name'
);
SET @sql := IF(@col_exists = 0,
  'ALTER TABLE `amz_fba_shipment_box` ADD COLUMN `product_name` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT NULL COMMENT ''商品名称'' AFTER `sku`',
  'SELECT ''amz_fba_shipment_box.product_name already exists'''
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

-- Missing table: customs_inventory_list
CREATE TABLE IF NOT EXISTS `customs_inventory_list`  (
  `id` bigint NOT NULL AUTO_INCREMENT COMMENT '主键',
  `product_code` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT NULL COMMENT '编码',
  `product_name` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT NULL COMMENT '产品名称',
  `sku` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT NULL COMMENT 'SKU',
  `purchase_quantity` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT NULL COMMENT '采购数量',
  `unit` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT NULL COMMENT '单位',
  `tax_included_price` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT NULL COMMENT '含税单价',
  `purchase_date` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT NULL COMMENT '采购日期',
  `inbound_date` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT NULL COMMENT '入库日期',
  `inbound_quantity` decimal(18, 4) NULL DEFAULT NULL COMMENT '入库数量',
  `inbound_remark` varchar(500) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT NULL COMMENT '入库备注',
  `outbound_date` text CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL COMMENT '出库日期',
  `czech_warehouse_qty` decimal(18, 4) NULL DEFAULT NULL COMMENT '捷克仓',
  `uk_warehouse_qty` decimal(18, 4) NULL DEFAULT NULL COMMENT '英国仓',
  `us_warehouse_qty` decimal(18, 4) NULL DEFAULT NULL COMMENT '美国谷仓',
  `de_warehouse_qty` decimal(18, 4) NULL DEFAULT NULL COMMENT '德国仓',
  `fba_de_qty` decimal(18, 4) NULL DEFAULT NULL COMMENT 'FBA(DE)',
  `fba_uk_qty` decimal(18, 4) NULL DEFAULT NULL COMMENT 'FBA(UK)',
  `fba_us_qty` decimal(18, 4) NULL DEFAULT NULL COMMENT 'FBA(US)',
  `fba_fr_qty` decimal(18, 4) NULL DEFAULT NULL COMMENT 'FBA(FR)',
  `remaining_stock` decimal(18, 4) NULL DEFAULT NULL COMMENT '剩余库存',
  `remark` varchar(500) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT NULL COMMENT '备注',
  `customs_unit` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT NULL COMMENT '报关计量单位',
  `declaration_elements` text CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL COMMENT '申报要素',
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  PRIMARY KEY (`id`) USING BTREE,
  INDEX `idx_customs_inventory_sku`(`sku` ASC) USING BTREE,
  INDEX `idx_customs_inventory_product_code`(`product_code` ASC) USING BTREE
) ENGINE = InnoDB CHARACTER SET = utf8mb4 COLLATE = utf8mb4_0900_ai_ci COMMENT = '报关出入库清单' ROW_FORMAT = Dynamic;

-- Missing table: customs_products_list
CREATE TABLE IF NOT EXISTS `customs_products_list`  (
  `id` int NOT NULL AUTO_INCREMENT,
  `sku` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL COMMENT 'SKU编码',
  `description_cn` varchar(200) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT NULL COMMENT '中文品名',
  `model` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT '通用型' COMMENT '规格型号',
  `unit` varchar(20) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT 'PIECE' COMMENT '单位',
  `unit_price_usd` decimal(10, 2) NULL DEFAULT 0.00 COMMENT 'USD单价',
  `currency` varchar(10) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT 'USD' COMMENT '币制',
  `single_weight` decimal(10, 4) NULL DEFAULT NULL COMMENT '单个重量(kg)',
  `hs_code` varchar(20) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT NULL COMMENT 'HS编码',
  `hs_description` text CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL COMMENT '申报要素描述',
  `origin_country` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT '中国' COMMENT '原产国',
  `destination_country` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT '美国' COMMENT '目的国',
  `source_location` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT NULL COMMENT '货源地',
  `exemption` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT '' COMMENT '征免',
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  `version` int NULL DEFAULT 1 COMMENT '乐观锁版本号',
  `is_tax` int NULL DEFAULT NULL COMMENT '是否含税 0否 1是',
  PRIMARY KEY (`id`) USING BTREE,
  UNIQUE INDEX `sku`(`sku` ASC) USING BTREE
) ENGINE = InnoDB CHARACTER SET = utf8mb4 COLLATE = utf8mb4_0900_ai_ci ROW_FORMAT = DYNAMIC;

-- Missing table: overseas_stock_order
CREATE TABLE IF NOT EXISTS `overseas_stock_order`  (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `overseas_order_no` varchar(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL COMMENT '备货单号',
  `inbound_order_no` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT NULL COMMENT '三方入库单号',
  `create_time` datetime NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`) USING BTREE,
  UNIQUE INDEX `uk_overseas_order_no`(`overseas_order_no` ASC) USING BTREE
) ENGINE = InnoDB CHARACTER SET = utf8mb4 COLLATE = utf8mb4_0900_ai_ci COMMENT = '领星备货单号表' ROW_FORMAT = Dynamic;

-- Missing table: overseas_stock_order_detail
CREATE TABLE IF NOT EXISTS `overseas_stock_order_detail`  (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `overseas_order_no` varchar(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL COMMENT '备货单号',
  `s_wid` int NULL DEFAULT NULL COMMENT '发货仓库id',
  `r_wid` int NULL DEFAULT NULL COMMENT '收货仓库id',
  `status` int NULL DEFAULT NULL COMMENT '状态',
  `product_code` varchar(200) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT NULL COMMENT '三方产品编码',
  `sku` varchar(200) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT NULL COMMENT 'SKU',
  `seller_id` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT NULL COMMENT '店铺id',
  `package_num` int NULL DEFAULT NULL COMMENT '装箱数量',
  `tariffs_currency_unit` varchar(10) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT NULL COMMENT '预估税费单位',
  `box_type` int NULL DEFAULT NULL COMMENT '装箱方式 1每箱一款 2每箱多款',
  `box_sku` varchar(200) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT NULL COMMENT '箱内SKU',
  `box_third_party_product_name` varchar(500) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT NULL COMMENT '第三方产品名',
  `box_third_party_product_code` varchar(200) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT NULL COMMENT '第三方产品编码',
  `box_seller_id` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT NULL COMMENT '箱内店铺id',
  `box_range` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT NULL COMMENT '装箱区间',
  `box_number` int NULL DEFAULT NULL COMMENT '箱数',
  `cg_box_weight` decimal(12, 4) NULL DEFAULT NULL COMMENT '箱子毛重',
  `cg_box_length` decimal(12, 4) NULL DEFAULT NULL COMMENT '箱子长cm',
  `cg_box_width` decimal(12, 4) NULL DEFAULT NULL COMMENT '箱子宽cm',
  `cg_box_height` decimal(12, 4) NULL DEFAULT NULL COMMENT '箱子高cm',
  `quantity_in_case` int NULL DEFAULT NULL COMMENT '单箱数量',
  `box_cbm` decimal(12, 6) NULL DEFAULT NULL COMMENT '单箱体积m3',
  `total_box_volume` decimal(12, 6) NULL DEFAULT NULL COMMENT '总体积m3',
  `total_box_weight` decimal(12, 4) NULL DEFAULT NULL COMMENT '总重量kg',
  `total_box_volume_weight` decimal(12, 4) NULL DEFAULT NULL COMMENT '总体积重kg',
  `box_remark` varchar(500) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT NULL COMMENT '装箱备注',
  `order_total_box_num` int NULL DEFAULT NULL COMMENT '整单总箱数',
  `order_total_box_weight` decimal(12, 4) NULL DEFAULT NULL COMMENT '整单总重量kg',
  `order_total_box_volume` decimal(12, 6) NULL DEFAULT NULL COMMENT '整单总体积m3',
  `order_total_box_volume_weight` decimal(12, 4) NULL DEFAULT NULL COMMENT '整单总体积重kg',
  `create_time` datetime NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`) USING BTREE,
  UNIQUE INDEX `uk_order_sku_box`(`overseas_order_no` ASC, `product_code` ASC, `box_range` ASC) USING BTREE
) ENGINE = InnoDB CHARACTER SET = utf8mb4 COLLATE = utf8mb4_0900_ai_ci COMMENT = '领星备货单详情' ROW_FORMAT = Dynamic;

-- Missing columns on amz_fba_shipment
ALTER TABLE `amz_fba_shipment`
  ADD COLUMN `ship_to_name` varchar(200) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL COMMENT '收件名称' AFTER `update_time`,
  ADD COLUMN `ship_to_country_code` varchar(10) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL COMMENT '国家编码' AFTER `ship_to_name`,
  ADD COLUMN `ship_to_state` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL COMMENT '省州' AFTER `ship_to_country_code`,
  ADD COLUMN `ship_to_city` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL COMMENT '城市' AFTER `ship_to_state`,
  ADD COLUMN `ship_to_region` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL COMMENT '区' AFTER `ship_to_city`,
  ADD COLUMN `ship_to_address_line1` varchar(500) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL COMMENT '街道地址1' AFTER `ship_to_region`,
  ADD COLUMN `ship_to_address_line2` varchar(500) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL COMMENT '街道地址2' AFTER `ship_to_address_line1`,
  ADD COLUMN `ship_to_postal_code` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL COMMENT '邮编' AFTER `ship_to_address_line2`,
  ADD COLUMN `ship_to_doorplate` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL COMMENT '门牌号' AFTER `ship_to_postal_code`;

-- Missing columns on amz_product_listing
ALTER TABLE `amz_product_listing`
  ADD COLUMN `small_image_url` varchar(500) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL COMMENT '商品缩略图地址' AFTER `tag_name`;

-- Missing columns on amz_replenishment_snapshot
ALTER TABLE `amz_replenishment_snapshot`
  ADD COLUMN `image_url` varchar(500) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL COMMENT '商品缩略图' AFTER `current_flag`;

-- Missing columns on goodcang_grn_list
ALTER TABLE `goodcang_grn_list`
  ADD COLUMN `ca_address1` varchar(500) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL COMMENT '提货地址1' AFTER `upload_time`;

-- Missing columns on purchase_order
ALTER TABLE `purchase_order`
  ADD COLUMN `is_tax` int NULL DEFAULT NULL COMMENT '是否含税 0否 1是' AFTER `upload_time`;
