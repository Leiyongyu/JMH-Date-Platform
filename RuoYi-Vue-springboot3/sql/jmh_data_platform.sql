/*
 Navicat Premium Dump SQL

 Source Server         : 运营补货跟价项目
 Source Server Type    : MySQL
 Source Server Version : 90700 (9.7.0)
 Source Host           : localhost:3306
 Source Schema         : jmh_data_platform

 Target Server Type    : MySQL
 Target Server Version : 90700 (9.7.0)
 File Encoding         : 65001

 Date: 07/07/2026 17:33:32
*/

SET NAMES utf8mb4;
SET FOREIGN_KEY_CHECKS = 0;

-- ----------------------------
-- Table structure for amz_fba_shipment
-- ----------------------------
DROP TABLE IF EXISTS `amz_fba_shipment`;
CREATE TABLE `amz_fba_shipment`  (
  `id` bigint NOT NULL AUTO_INCREMENT COMMENT '主键',
  `sid` int NOT NULL COMMENT '店铺ID',
  `username` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT '' COMMENT '创建人姓名',
  `shipment_id` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '亚马逊货件编号',
  `shipment_name` varchar(200) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT '' COMMENT '货件名称',
  `shipment_status` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT '' COMMENT '货件状态',
  `msku` varchar(200) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT 'MSKU',
  `sku` varchar(200) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT '' COMMENT 'SKU',
  `quantity_shipped` int NULL DEFAULT 0 COMMENT '当前申报量',
  `init_quantity_shipped` int NULL DEFAULT 0 COMMENT '货件初始申报量',
  `quantity_received` int NULL DEFAULT 0 COMMENT '签收数量',
  `quantity_shipped_local` int NULL DEFAULT 0 COMMENT '已发货数量（本地数据）',
  `declared_diff` int NULL DEFAULT 0 COMMENT '申收差异 = 申报量 - 签收量',
  `gmt_create` datetime NULL DEFAULT NULL COMMENT '货件创建时间',
  `gmt_modified` datetime NULL DEFAULT NULL COMMENT '数据更新时间',
  `working_time` datetime NULL DEFAULT NULL COMMENT 'WORKING时间',
  `shipped_time` datetime NULL DEFAULT NULL COMMENT 'SHIPPED时间',
  `receiving_time` datetime NULL DEFAULT NULL COMMENT 'RECEIVING时间',
  `closed_time` datetime NULL DEFAULT NULL COMMENT 'CLOSED时间',
  `create_time` datetime NULL DEFAULT CURRENT_TIMESTAMP COMMENT '记录创建时间',
  `update_time` datetime NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '记录更新时间',
  `ship_to_name` varchar(200) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL COMMENT '收件名称',
  `ship_to_country_code` varchar(10) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL COMMENT '国家编码',
  `ship_to_state` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL COMMENT '省州',
  `ship_to_city` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL COMMENT '城市',
  `ship_to_region` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL COMMENT '区',
  `ship_to_address_line1` varchar(500) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL COMMENT '街道地址1',
  `ship_to_address_line2` varchar(500) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL COMMENT '街道地址2',
  `ship_to_postal_code` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL COMMENT '邮编',
  `ship_to_doorplate` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL COMMENT '门牌号',
  PRIMARY KEY (`id`) USING BTREE,
  UNIQUE INDEX `uk_sid_shipment_sku`(`sid` ASC, `shipment_id` ASC, `sku` ASC) USING BTREE,
  INDEX `idx_sid`(`sid` ASC) USING BTREE,
  INDEX `idx_shipment_id`(`shipment_id` ASC) USING BTREE,
  INDEX `idx_msku`(`msku` ASC) USING BTREE,
  INDEX `idx_amz_fba_shipment_gmt_create`(`gmt_create` ASC, `shipment_id` ASC, `sku` ASC) USING BTREE
) ENGINE = InnoDB AUTO_INCREMENT = 575885 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_unicode_ci COMMENT = 'Amazon FBA货件明细表' ROW_FORMAT = DYNAMIC;

-- ----------------------------
-- Table structure for amz_fba_shipment_box
-- ----------------------------
DROP TABLE IF EXISTS `amz_fba_shipment_box`;
CREATE TABLE `amz_fba_shipment_box`  (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `sid` int NOT NULL COMMENT '店铺id',
  `shipment_id` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL COMMENT '货件编号',
  `box_type` varchar(20) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT NULL COMMENT 'SINGLE/MULTIPLE',
  `box_length` varchar(20) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT NULL COMMENT '箱子长',
  `box_width` varchar(20) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT NULL COMMENT '箱子宽',
  `box_height` varchar(20) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT NULL COMMENT '箱子高',
  `box_weight` varchar(20) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT NULL COMMENT '箱子重',
  `box_volume` varchar(20) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT NULL COMMENT '箱子体积m3',
  `box_dimensions_unit` varchar(10) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT 'cm' COMMENT '长度单位',
  `box_weight_unit` varchar(10) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT 'kg' COMMENT '重量单位',
  `box_num` int NULL DEFAULT 1 COMMENT '箱数',
  `box_no` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT NULL COMMENT '箱号',
  `msku` varchar(200) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT NULL COMMENT '货件MSKU',
  `sku` varchar(200) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT NULL COMMENT 'local_sku(从amz_product_listing映射)',
  `product_name` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT NULL COMMENT '商品名称',
  `fulfillment_network_sku` varchar(200) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT NULL COMMENT 'FNSKU',
  `quantity_in_case` varchar(20) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT NULL COMMENT '单箱数量',
  `create_time` datetime NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`) USING BTREE,
  UNIQUE INDEX `uk_ship_box_msku`(`sid` ASC, `shipment_id` ASC, `box_num` ASC, `msku` ASC) USING BTREE
) ENGINE = InnoDB AUTO_INCREMENT = 1 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_0900_ai_ci COMMENT = 'FBA货件装箱信息' ROW_FORMAT = DYNAMIC;

-- ----------------------------
-- Table structure for amz_fba_shipment_mark
-- ----------------------------
DROP TABLE IF EXISTS `amz_fba_shipment_mark`;
CREATE TABLE `amz_fba_shipment_mark`  (
  `id` bigint NOT NULL AUTO_INCREMENT COMMENT '主键',
  `msku` varchar(200) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT 'MSKU',
  `shipment_id` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT '' COMMENT '货件单号',
  `remark` varchar(500) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT '' COMMENT '备注',
  `confirmed` tinyint(1) NOT NULL DEFAULT 0 COMMENT '已完结 0否1是',
  `update_time` datetime NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`) USING BTREE,
  UNIQUE INDEX `uk_shipment_msku`(`shipment_id` ASC, `msku` ASC) USING BTREE,
  INDEX `idx_amz_fba_shipment_mark_msku_shipment`(`msku` ASC, `shipment_id` ASC) USING BTREE
) ENGINE = InnoDB AUTO_INCREMENT = 7 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_unicode_ci COMMENT = 'FBA货件MSKU备注与确认标记' ROW_FORMAT = DYNAMIC;

-- ----------------------------
-- Table structure for amz_order_profit
-- ----------------------------
DROP TABLE IF EXISTS `amz_order_profit`;
CREATE TABLE `amz_order_profit`  (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `sid` int NOT NULL COMMENT '店铺ID',
  `seller_sku` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT 'Seller SKU',
  `gross_margin` decimal(10, 4) NULL DEFAULT NULL COMMENT '毛利率',
  `spend_rate` decimal(10, 4) NULL DEFAULT NULL COMMENT '广告费率',
  `refund_amount_rate` decimal(10, 4) NULL DEFAULT NULL COMMENT '退款率',
  `updated_at` datetime NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`) USING BTREE,
  UNIQUE INDEX `uk_sid_sku`(`sid` ASC, `seller_sku` ASC) USING BTREE
) ENGINE = InnoDB AUTO_INCREMENT = 213542 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_unicode_ci COMMENT = 'Amazon订单利润表(MSKU维度)' ROW_FORMAT = DYNAMIC;

-- ----------------------------
-- Table structure for amz_product_category
-- ----------------------------
DROP TABLE IF EXISTS `amz_product_category`;
CREATE TABLE `amz_product_category`  (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `sid` int NOT NULL COMMENT '店铺ID',
  `seller_sku` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT 'MSKU',
  `category` varchar(200) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT '' COMMENT '产品分类',
  `updated_at` datetime NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`) USING BTREE,
  UNIQUE INDEX `uk_sid_sku`(`sid` ASC, `seller_sku` ASC) USING BTREE
) ENGINE = InnoDB AUTO_INCREMENT = 7 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_unicode_ci COMMENT = 'AMZ产品分类(手动维护)' ROW_FORMAT = DYNAMIC;

-- ----------------------------
-- Table structure for amz_product_listing
-- ----------------------------
DROP TABLE IF EXISTS `amz_product_listing`;
CREATE TABLE `amz_product_listing`  (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `sid` int NOT NULL COMMENT '店铺sid',
  `marketplace` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT '' COMMENT '国家',
  `seller_sku` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT 'MSKU',
  `asin` varchar(20) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT '' COMMENT 'ASIN',
  `local_sku` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT '' COMMENT '本地SKU',
  `local_name` varchar(200) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT '' COMMENT '品名',
  `status` tinyint NULL DEFAULT NULL COMMENT 'Listing状态：0停售，1在售',
  `review_num` int NULL DEFAULT 0 COMMENT '评论数',
  `last_star` varchar(5) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT '' COMMENT '星级评分',
  `principal_name` varchar(200) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT '' COMMENT 'Listing负责人',
  `updated_at` datetime NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  `tag_name` varchar(500) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT '' COMMENT '标签名称(逗号分隔)',
  `small_image_url` varchar(500) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL COMMENT '商品缩略图地址',
  `price` decimal(10, 2) NULL DEFAULT NULL COMMENT '价格',
  PRIMARY KEY (`id`) USING BTREE,
  UNIQUE INDEX `uk_sid_sku`(`sid` ASC, `seller_sku` ASC) USING BTREE,
  INDEX `idx_asin`(`asin` ASC) USING BTREE,
  INDEX `idx_status`(`status` ASC) USING BTREE
) ENGINE = InnoDB AUTO_INCREMENT = 489858 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_unicode_ci COMMENT = 'Amazon商品Listing' ROW_FORMAT = DYNAMIC;

-- ----------------------------
-- Table structure for amz_product_performance_inventory
-- ----------------------------
DROP TABLE IF EXISTS `amz_product_performance_inventory`;
CREATE TABLE `amz_product_performance_inventory`  (
  `id` bigint NOT NULL AUTO_INCREMENT COMMENT '主键ID',
  `sid` int NOT NULL COMMENT '店铺ID',
  `seller_sku` varchar(128) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT 'Seller SKU/MSKU',
  `local_sku` varchar(128) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL COMMENT '本地SKU',
  `fba_fulfillable` int NOT NULL DEFAULT 0 COMMENT 'FBA可售',
  `fba_transfer` int NOT NULL DEFAULT 0 COMMENT 'FBA待调仓',
  `fba_receiving` int NOT NULL DEFAULT 0 COMMENT 'FBA入库中',
  `fba_reserved` int NOT NULL DEFAULT 0 COMMENT 'FBA预留：待发货+调仓中',
  `fba_inbound` int NOT NULL DEFAULT 0 COMMENT 'FBA在途',
  `fba_inbound_working` int NOT NULL DEFAULT 0 COMMENT 'FBA计划入库',
  `fba_stock` int NOT NULL DEFAULT 0 COMMENT 'FBA在库：可售+待调仓+入库中+预留',
  `sync_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '同步时间',
  PRIMARY KEY (`id`) USING BTREE,
  UNIQUE INDEX `uk_sid_seller_sku`(`sid` ASC, `seller_sku` ASC) USING BTREE,
  INDEX `idx_seller_sku`(`seller_sku` ASC) USING BTREE,
  INDEX `idx_sid`(`sid` ASC) USING BTREE
) ENGINE = InnoDB CHARACTER SET = utf8mb4 COLLATE = utf8mb4_unicode_ci COMMENT = '领星Amazon产品表现库存' ROW_FORMAT = Dynamic;

-- ----------------------------
-- Table structure for amz_replenishment_formula_config
-- ----------------------------
DROP TABLE IF EXISTS `amz_replenishment_formula_config`;
CREATE TABLE `amz_replenishment_formula_config`  (
  `id` bigint NOT NULL AUTO_INCREMENT COMMENT '主键',
  `region_group` varchar(10) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '区域组: US/EU',
  `region_name` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '区域名称',
  `marketplaces` varchar(200) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '包含的市场站点，逗号分隔',
  `strategy_type` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'CUSTOM' COMMENT '策略类型',
  `sales_weight_14d` decimal(5, 3) NOT NULL DEFAULT 0.500 COMMENT '14天权重',
  `sales_weight_30d` decimal(5, 3) NOT NULL DEFAULT 0.400 COMMENT '30天权重',
  `sales_weight_60d` decimal(5, 3) NOT NULL DEFAULT 0.100 COMMENT '60天权重',
  `month_multiplier` int NOT NULL DEFAULT 30 COMMENT '月销乘数',
  `safety_days` int NOT NULL DEFAULT 90 COMMENT '安全库存天数',
  `ship_days` int NOT NULL DEFAULT 90 COMMENT '发货计算天数',
  `replenish_days` int NOT NULL DEFAULT 120 COMMENT '补货计算天数',
  `deduct_fba_stock` tinyint(1) NOT NULL DEFAULT 1 COMMENT '扣减FBA在库',
  `deduct_fba_inbound` tinyint(1) NOT NULL DEFAULT 1 COMMENT '扣减FBA在途',
  `deduct_fba_inbound_working` tinyint(1) NOT NULL DEFAULT 0 COMMENT '扣减FBA计划入库',
  `deduct_domestic_stock` tinyint(1) NOT NULL DEFAULT 1 COMMENT '扣减国内仓库存',
  `deduct_purchased_qty` tinyint(1) NOT NULL DEFAULT 1 COMMENT '扣减已采购数量',
  `deduct_pending_ship_qty` tinyint(1) NOT NULL DEFAULT 1 COMMENT '扣减待出库数量',
  `allow_negative_replenish` tinyint(1) NOT NULL DEFAULT 1 COMMENT '允许负数补货量',
  `min_replenish_qty` decimal(18, 2) NULL DEFAULT NULL COMMENT '最小补货量',
  `max_replenish_qty` decimal(18, 2) NULL DEFAULT NULL COMMENT '最大补货量',
  `round_mode` varchar(30) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'NONE' COMMENT '取整方式',
  `formula_weighted_daily` varchar(500) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT '{d14}*{w14} + {d30}*{w30} + {d60}*{w60}' COMMENT '加权日均公式',
  `formula_monthly` varchar(500) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT '({d14}*{w14} + {d30}*{w30} + {d60}*{w60}) * {month}' COMMENT '月均销量公式',
  `formula_safety` varchar(500) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT '({d14}*{w14} + {d30}*{w30} + {d60}*{w60}) * {safety}' COMMENT '安全库存公式',
  `formula_ship` varchar(500) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT '({d14}*{w14} + {d30}*{w30} + {d60}*{w60}) * {ship} - {fba}' COMMENT '发货量公式',
  `formula_replenish` varchar(500) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT '({d14}*{w14} + {d30}*{w30} + {d60}*{w60}) * {replenish} - {purchases} - {domestic} - {fba} - {locked}' COMMENT '补货量公式',
  `formula_restock` varchar(500) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT '({fba} - (({d14}*{w14} + {d30}*{w30} + {d60}*{w60}) * {replenish} - {purchases} - {domestic} - {fba} - {locked})) / ({d14}*{w14} + {d30}*{w30} + {d60}*{w60})' COMMENT '补货时间公式',
  `enabled` tinyint(1) NOT NULL DEFAULT 1 COMMENT '启用',
  `remark` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL COMMENT '备注',
  `update_time` datetime NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`) USING BTREE,
  UNIQUE INDEX `uk_region_group`(`region_group` ASC) USING BTREE
) ENGINE = InnoDB AUTO_INCREMENT = 5 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_unicode_ci COMMENT = 'AMZ补货公式配置表' ROW_FORMAT = DYNAMIC;

-- ----------------------------
-- Table structure for amz_replenishment_override
-- ----------------------------
DROP TABLE IF EXISTS `amz_replenishment_override`;
CREATE TABLE `amz_replenishment_override`  (
  `id` bigint NOT NULL AUTO_INCREMENT COMMENT '主键ID',
  `sid` varchar(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '店铺ID',
  `seller_sku` varchar(128) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT 'Seller SKU',
  `manual_purchased_qty` decimal(18, 2) NULL DEFAULT NULL COMMENT '人工调整已采购数量',
  `product_category` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL COMMENT '产品分类',
  `remark` varchar(500) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT '' COMMENT '备注',
  `create_time` datetime NULL DEFAULT NULL,
  `update_time` datetime NULL DEFAULT NULL,
  PRIMARY KEY (`id`) USING BTREE,
  UNIQUE INDEX `uk_sid_seller_sku`(`sid` ASC, `seller_sku` ASC) USING BTREE
) ENGINE = InnoDB AUTO_INCREMENT = 157 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_unicode_ci COMMENT = 'AMZ补货人工调整表' ROW_FORMAT = DYNAMIC;

-- ----------------------------
-- Table structure for amz_replenishment_snapshot
-- ----------------------------
DROP TABLE IF EXISTS `amz_replenishment_snapshot`;
CREATE TABLE `amz_replenishment_snapshot`  (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `sid` int NULL DEFAULT NULL,
  `seller_sku` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL,
  `warehouse_sku` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `warehouse_name` varchar(200) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT '',
  `asin` varchar(20) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT '',
  `price` decimal(10, 2) NULL DEFAULT NULL COMMENT '价格',
  `tag_name` varchar(500) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT '' COMMENT '标签名称',
  `principal_name` varchar(200) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT '',
  `store_name` varchar(200) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT '',
  `product_category` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT '',
  `rating` decimal(3, 1) NULL DEFAULT NULL,
  `review_count` int NULL DEFAULT 0,
  `ad_rate` decimal(10, 4) NULL DEFAULT NULL,
  `profit_rate_30d` decimal(10, 4) NULL DEFAULT NULL,
  `refund_rate_90d` decimal(10, 4) NULL DEFAULT NULL,
  `tacos` decimal(10, 2) NULL DEFAULT NULL COMMENT 'TACOS广告费占比',
  `purchased_qty` int NULL DEFAULT 0,
  `domestic_stock` int NULL DEFAULT 0,
  `pending_ship_qty` int NULL DEFAULT 0,
  `product_qc_num` int NULL DEFAULT 0 COMMENT '待检待上架量',
  `fba_stock` int NULL DEFAULT 0,
  `fba_inbound` int NULL DEFAULT 0,
  `fba_inbound_working` int NULL DEFAULT 0 COMMENT 'FBA计划入库',
  `fba_reserved` int NULL DEFAULT 0 COMMENT 'FBA预留',
  `total_inventory` int NULL DEFAULT 0,
  `sales_7d` int NULL DEFAULT 0,
  `sales_14d` int NULL DEFAULT 0,
  `sales_30d` int NULL DEFAULT 0,
  `sales_60d` int NULL DEFAULT 0,
  `sales_speed_14d` decimal(10, 2) NULL DEFAULT NULL,
  `sales_speed_30d` decimal(10, 2) NULL DEFAULT NULL,
  `sales_speed_60d` decimal(10, 2) NULL DEFAULT NULL,
  `avg_monthly_sales` decimal(10, 2) NULL DEFAULT NULL,
  `safety_stock` decimal(10, 2) NULL DEFAULT NULL,
  `ship_qty` decimal(10, 2) NULL DEFAULT NULL,
  `replenish_qty` decimal(10, 2) NULL DEFAULT NULL,
  `restock_days` decimal(10, 2) NULL DEFAULT NULL,
  `shortage_qty` int NULL DEFAULT 0 COMMENT '缺货量=安全库存-FBA总库存',
  `region_group` varchar(10) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT 'US' COMMENT '区域组 US/EU',
  `fba_shipment_id` varchar(2000) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT '' COMMENT 'FBA货件单号(多个逗号分隔)',
  `fba_quantity_shipped` int NULL DEFAULT 0 COMMENT 'FBA申报量合计',
  `fba_quantity_received` int NULL DEFAULT 0 COMMENT 'FBA签收量合计',
  `fba_declared_diff` int NULL DEFAULT 0 COMMENT 'FBA申报差异合计',
  `fba_shipment_create_time` datetime NULL DEFAULT NULL COMMENT 'FBA最新货件创建时间',
  `source_overview_id` bigint NULL DEFAULT NULL,
  `calc_time` datetime NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  `batch_no` varchar(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL,
  `current_flag` tinyint NOT NULL DEFAULT 1,
  `image_url` varchar(500) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL COMMENT '商品缩略图',
  PRIMARY KEY (`id`) USING BTREE,
  INDEX `idx_sid_seller_sku`(`sid` ASC, `seller_sku` ASC) USING BTREE,
  INDEX `idx_warehouse_sku`(`warehouse_sku` ASC) USING BTREE,
  INDEX `idx_asin`(`asin` ASC) USING BTREE,
  INDEX `idx_store_name`(`store_name` ASC) USING BTREE,
  INDEX `idx_amz_store`(`store_name` ASC) USING BTREE,
  INDEX `idx_amz_seller_sku`(`seller_sku` ASC) USING BTREE,
  INDEX `idx_amz_warehouse_sku`(`warehouse_sku` ASC) USING BTREE,
  INDEX `idx_amz_asin`(`asin` ASC) USING BTREE,
  INDEX `idx_amz_principal`(`principal_name` ASC) USING BTREE,
  INDEX `idx_amz_category`(`product_category` ASC) USING BTREE,
  INDEX `idx_ars_current`(`current_flag` ASC) USING BTREE,
  INDEX `idx_ars_batch`(`batch_no` ASC) USING BTREE
) ENGINE = InnoDB AUTO_INCREMENT = 2112025 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_unicode_ci COMMENT = 'Amazon补货计算快照' ROW_FORMAT = DYNAMIC;

-- ----------------------------
-- Table structure for amz_restock_summary
-- ----------------------------
DROP TABLE IF EXISTS `amz_restock_summary`;
CREATE TABLE `amz_restock_summary`  (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `hash_id` varchar(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '领星唯一标识',
  `node_type` int NULL DEFAULT NULL COMMENT '节点类型:1共享库存父行,2共享库存子行,3非共享库存,4汇总行',
  `sid` int NOT NULL COMMENT '店铺ID',
  `msku` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT 'MSKU',
  `sync_time` varchar(30) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT '' COMMENT '数据更新时间',
  `fba_sellable` int NULL DEFAULT 0 COMMENT 'FBA可售',
  `fba_inbound` int NULL DEFAULT 0 COMMENT 'FBA在途',
  `fba_reserved` int NULL DEFAULT 0 COMMENT 'FBA预留',
  `sales_7d` int NULL DEFAULT 0 COMMENT '近7天销量',
  `sales_14d` int NULL DEFAULT 0 COMMENT '近14天销量',
  `sales_30d` int NULL DEFAULT 0 COMMENT '近30天销量',
  `sales_60d` int NULL DEFAULT 0 COMMENT '近60天销量',
  `updated_at` datetime NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  `avg_sales_14d` decimal(10, 2) NULL DEFAULT NULL COMMENT '14日均销量',
  `avg_sales_30d` decimal(10, 2) NULL DEFAULT NULL COMMENT '30日均销量',
  `avg_sales_60d` decimal(10, 2) NULL DEFAULT NULL COMMENT '60日均销量',
  PRIMARY KEY (`id`) USING BTREE,
  UNIQUE INDEX `uk_hash_id`(`hash_id` ASC) USING BTREE
) ENGINE = InnoDB AUTO_INCREMENT = 566072 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_unicode_ci COMMENT = 'amz补货建议表' ROW_FORMAT = DYNAMIC;

-- ----------------------------
-- Table structure for amz_warehouse_inventory_detail
-- ----------------------------
DROP TABLE IF EXISTS `amz_warehouse_inventory_detail`;
CREATE TABLE `amz_warehouse_inventory_detail`  (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `wid` int NOT NULL COMMENT '仓库ID',
  `seller_id` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT '' COMMENT '卖家ID',
  `sku` varchar(200) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT 'SKU',
  `quantity_receive` decimal(10, 2) NULL DEFAULT NULL COMMENT '待收数量',
  `product_valid_num` int NULL DEFAULT 0 COMMENT '可用库存',
  `product_lock_num` int NULL DEFAULT 0 COMMENT '锁定库存',
  `product_qc_num` int NULL DEFAULT 0 COMMENT '待检待上架量',
  `updated_at` datetime NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`) USING BTREE,
  UNIQUE INDEX `uk_wid_sku`(`wid` ASC, `sku` ASC) USING BTREE
) ENGINE = InnoDB AUTO_INCREMENT = 32426 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_unicode_ci COMMENT = 'AMZ仓库库存明细' ROW_FORMAT = DYNAMIC;

-- ----------------------------
-- Table structure for brand_owner
-- ----------------------------
DROP TABLE IF EXISTS `brand_owner`;
CREATE TABLE `brand_owner`  (
  `id` int NOT NULL AUTO_INCREMENT COMMENT '主键ID',
  `brand_code` varchar(20) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '品牌代码',
  `owner_name` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '负责人姓名',
  `user_id` bigint NULL DEFAULT NULL,
  `create_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `update_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '修改时间',
  `version` int NOT NULL DEFAULT 0 COMMENT '乐观锁版本号',
  PRIMARY KEY (`id`) USING BTREE,
  UNIQUE INDEX `uk_brand_code`(`brand_code` ASC) USING BTREE,
  INDEX `idx_owner_name`(`owner_name` ASC) USING BTREE,
  INDEX `idx_user_id`(`user_id` ASC) USING BTREE
) ENGINE = InnoDB AUTO_INCREMENT = 35 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_unicode_ci COMMENT = '品牌负责人维护表' ROW_FORMAT = DYNAMIC;

-- ----------------------------
-- Table structure for customs_inventory_list
-- ----------------------------
DROP TABLE IF EXISTS `customs_inventory_list`;
CREATE TABLE `customs_inventory_list`  (
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
) ENGINE = InnoDB AUTO_INCREMENT = 3398 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_0900_ai_ci COMMENT = '报关出入库清单' ROW_FORMAT = DYNAMIC;

-- ----------------------------
-- Table structure for customs_products_list
-- ----------------------------
DROP TABLE IF EXISTS `customs_products_list`;
CREATE TABLE `customs_products_list`  (
  `id` int NOT NULL AUTO_INCREMENT,
  `sku` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL COMMENT 'SKU编码',
  `description_cn` varchar(200) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT NULL COMMENT '中文品名',
  `model` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT '通用型' COMMENT '规格型号',
  `unit` varchar(20) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT 'PIECE' COMMENT '单位',
  `unit_price_usd` decimal(10, 2) NULL DEFAULT 0.00 COMMENT 'USD单价',
  `currency` varchar(10) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT 'USD' COMMENT '币制',
  `single_weight` decimal(10, 4) NULL DEFAULT NULL COMMENT '单个重量(kg)',
  `packing_net_weight` decimal(12, 4) NULL DEFAULT NULL COMMENT '装箱单净重kg',
  `packing_gross_weight` decimal(12, 4) NULL DEFAULT NULL COMMENT '装箱单毛重kg',
  `packing_cbm` decimal(12, 6) NULL DEFAULT NULL COMMENT '装箱单体积CBM',
  `packing_volume_cm3` decimal(18, 2) NULL DEFAULT NULL COMMENT '装箱单体积cm3',
  `box_length` decimal(12, 4) NULL DEFAULT NULL COMMENT '箱长cm',
  `box_width` decimal(12, 4) NULL DEFAULT NULL COMMENT '箱宽cm',
  `box_height` decimal(12, 4) NULL DEFAULT NULL COMMENT '箱高cm',
  `box_no` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT NULL COMMENT '箱号/箱组标识',
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
) ENGINE = InnoDB AUTO_INCREMENT = 1153 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_0900_ai_ci ROW_FORMAT = DYNAMIC;

-- ----------------------------
-- Table structure for data_sync_log
-- ----------------------------
DROP TABLE IF EXISTS `data_sync_log`;
CREATE TABLE `data_sync_log`  (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `sync_type` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `sync_name` varchar(200) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT '',
  `status` varchar(20) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT 'RUNNING/SUCCESS/FAILED',
  `trigger_type` varchar(20) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT '' COMMENT 'MANUAL/JOB',
  `operator` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT '',
  `start_time` datetime NULL DEFAULT NULL,
  `end_time` datetime NULL DEFAULT NULL,
  `total_count` int NULL DEFAULT 0,
  `success_count` int NULL DEFAULT 0,
  `fail_count` int NULL DEFAULT 0,
  `error_message` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL,
  `request_params` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL,
  `create_time` datetime NULL DEFAULT CURRENT_TIMESTAMP,
  `api_path` varchar(300) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT '' COMMENT '调用的API路径',
  `job_id` bigint NULL DEFAULT NULL COMMENT '若依sys_job.job_id',
  `job_log_id` bigint NULL DEFAULT NULL COMMENT '若依sys_job_log.job_log_id',
  `detail_json` longtext CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL COMMENT '完整执行详情JSON',
  `failed_json` longtext CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL COMMENT '失败明细JSON',
  `parent_id` bigint NULL DEFAULT NULL COMMENT '父日志ID，用于关联父子步骤',
  PRIMARY KEY (`id`) USING BTREE,
  INDEX `idx_sync_type`(`sync_type` ASC) USING BTREE,
  INDEX `idx_status`(`status` ASC) USING BTREE,
  INDEX `idx_start_time`(`start_time` ASC) USING BTREE,
  INDEX `idx_job_id`(`job_id` ASC) USING BTREE,
  INDEX `idx_job_log_id`(`job_log_id` ASC) USING BTREE,
  INDEX `idx_parent_id`(`parent_id` ASC) USING BTREE
) ENGINE = InnoDB AUTO_INCREMENT = 422 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_unicode_ci COMMENT = '业务数据同步执行日志' ROW_FORMAT = DYNAMIC;

-- ----------------------------
-- Table structure for ebay_link_template
-- ----------------------------
DROP TABLE IF EXISTS `ebay_link_template`;
CREATE TABLE `ebay_link_template`  (
  `site` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '站点',
  `presale_url` varchar(500) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL COMMENT '售前链接模板',
  `sold_url` varchar(500) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL COMMENT '售后链接模板',
  `profit_rate` int NULL DEFAULT NULL COMMENT '目标利润率(%)',
  `exchange_rate` decimal(10, 2) NULL DEFAULT NULL COMMENT '实时汇率',
  PRIMARY KEY (`site`) USING BTREE
) ENGINE = InnoDB CHARACTER SET = utf8mb4 COLLATE = utf8mb4_unicode_ci COMMENT = 'eBay售前售后链接模板表' ROW_FORMAT = DYNAMIC;

-- ----------------------------
-- Table structure for ebay_price_tracking_snapshot
-- ----------------------------
DROP TABLE IF EXISTS `ebay_price_tracking_snapshot`;
CREATE TABLE `ebay_price_tracking_snapshot`  (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `site` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `sku` varchar(200) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `product_name` varchar(500) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT '',
  `sku_level` varchar(5) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT 'E',
  `our_lowest_price` decimal(10, 2) NULL DEFAULT NULL,
  `tracking_price` decimal(10, 2) NULL DEFAULT NULL,
  `tracking_profit_margin` decimal(10, 6) NULL DEFAULT NULL,
  `floor_price` decimal(10, 2) NULL DEFAULT NULL,
  `return_rate` decimal(10, 4) NULL DEFAULT NULL,
  `sales_3d` int NULL DEFAULT 0,
  `sales_7d` int NULL DEFAULT 0,
  `sales_30d` int NULL DEFAULT 0,
  `sales_90d` int NULL DEFAULT 0,
  `max_monthly_sales` int NULL DEFAULT NULL,
  `overseas_stock` int NULL DEFAULT 0,
  `overseas_stock_age_days` int NULL DEFAULT NULL,
  `stock_sales_ratio` decimal(10, 2) NULL DEFAULT NULL,
  `estimated_replenish_qty` int NULL DEFAULT NULL,
  `brand_code` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT '',
  `operator_name` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT '',
  `oe_number` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT '',
  `presale_url` varchar(500) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT '',
  `sold_url` varchar(500) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT '',
  `remark` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL,
  `source_overview_id` bigint NULL DEFAULT NULL,
  `source_profile_id` bigint NULL DEFAULT NULL,
  `calc_time` datetime NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  `batch_no` varchar(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL,
  `current_flag` tinyint NOT NULL DEFAULT 1,
  PRIMARY KEY (`id`) USING BTREE,
  UNIQUE INDEX `uk_batch_site_sku`(`batch_no` ASC, `site` ASC, `sku` ASC) USING BTREE,
  INDEX `idx_sku`(`sku` ASC) USING BTREE,
  INDEX `idx_site`(`site` ASC) USING BTREE,
  INDEX `idx_brand`(`brand_code` ASC) USING BTREE,
  INDEX `idx_operator`(`operator_name` ASC) USING BTREE,
  INDEX `idx_pt_site_sku`(`site` ASC, `sku` ASC) USING BTREE,
  INDEX `idx_pt_brand`(`brand_code` ASC) USING BTREE,
  INDEX `idx_pt_operator`(`operator_name` ASC) USING BTREE,
  INDEX `idx_epts_current`(`current_flag` ASC) USING BTREE,
  INDEX `idx_epts_batch`(`batch_no` ASC) USING BTREE
) ENGINE = InnoDB AUTO_INCREMENT = 105704 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_unicode_ci COMMENT = 'eBay每日跟价计算快照' ROW_FORMAT = DYNAMIC;

-- ----------------------------
-- Table structure for ebay_product_dedup
-- ----------------------------
DROP TABLE IF EXISTS `ebay_product_dedup`;
CREATE TABLE `ebay_product_dedup`  (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `site` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '站点',
  `sku` varchar(200) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT 'SKU (baseSku)',
  `oe_number` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL COMMENT 'OE号',
  `product_name` varchar(300) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL COMMENT '产品名称',
  `tracking_price` decimal(10, 2) NULL DEFAULT NULL COMMENT '跟卖价格',
  `tracking_profit_margin` decimal(10, 6) NULL DEFAULT NULL COMMENT '跟卖利润率',
  `floor_price` decimal(10, 2) NULL DEFAULT NULL COMMENT '底线价',
  `create_time` datetime NULL DEFAULT CURRENT_TIMESTAMP,
  `update_time` datetime NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  `remark` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL COMMENT '备注',
  `profit_rate` decimal(10, 4) NULL DEFAULT NULL COMMENT '近30天利润率',
  `return_rate` decimal(10, 4) NULL DEFAULT NULL COMMENT '退货率',
  `lowest_price` decimal(10, 2) NULL DEFAULT NULL,
  `lowest_item_number` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL,
  `lowest_upload_time` datetime NULL DEFAULT NULL,
  `product_nature` tinyint NULL DEFAULT NULL COMMENT '产品性质 1老品 2新品',
  PRIMARY KEY (`id`) USING BTREE,
  UNIQUE INDEX `uk_site_sku`(`site` ASC, `sku` ASC) USING BTREE
) ENGINE = InnoDB AUTO_INCREMENT = 17769 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_unicode_ci COMMENT = '旧版eBay商品去重与跟价维护表' ROW_FORMAT = DYNAMIC;

-- ----------------------------
-- Table structure for ebay_product_listing
-- ----------------------------
DROP TABLE IF EXISTS `ebay_product_listing`;
CREATE TABLE `ebay_product_listing`  (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `platform` varchar(20) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'eBay' COMMENT '平台名称，默认eBay，可根据需要修改',
  `item_id` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT 'eBay商品ID，唯一标识',
  `item_url` varchar(500) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '商品链接地址',
  `picture_url` varchar(500) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL COMMENT '商品图片URL',
  `msku` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '制造商SKU编码',
  `sku` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT '' COMMENT '基础SKU(前两段)',
  `local_sku` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '本地SKU编码',
  `title` varchar(500) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '商品标题',
  `local_name` varchar(200) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL COMMENT '商品本地名称（中文名称）',
  `attribute` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL COMMENT '商品属性，JSON格式存储',
  `listing_type` tinyint NOT NULL COMMENT '刊登类型：2-固价',
  `listing_type_name` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '刊登类型名称',
  `listing_status` tinyint NOT NULL COMMENT '刊登状态：2-已下架',
  `listing_status_name` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '刊登状态名称',
  `price` decimal(10, 2) NOT NULL DEFAULT 0.00 COMMENT '商品价格',
  `start_price` decimal(10, 2) NOT NULL DEFAULT 0.00 COMMENT '起始价格',
  `accept_price` decimal(10, 2) NOT NULL DEFAULT 0.00 COMMENT '接受价格',
  `quantity` int NOT NULL DEFAULT 0 COMMENT '商品库存数量',
  `auto_restock` tinyint NULL DEFAULT NULL COMMENT '自动补货设置，0-关闭，1-开启',
  `product_auto_restock_response` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL COMMENT '自动补货响应配置，JSON格式',
  `location` varchar(200) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL COMMENT '商品所在地',
  `dispatch_time_max` tinyint NULL DEFAULT NULL COMMENT '最长发货时间（天）',
  `listing_start_time` datetime NOT NULL COMMENT '刊登开始时间',
  `listing_end_time` datetime NOT NULL COMMENT '刊登结束时间',
  `store_id` bigint NOT NULL DEFAULT 0,
  `store_name` varchar(200) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '店铺名称',
  `site_code` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '站点代码',
  `site_name` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '站点名称',
  `created_at` datetime NULL DEFAULT CURRENT_TIMESTAMP COMMENT '记录创建时间',
  `updated_at` datetime NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '记录更新时间',
  PRIMARY KEY (`id`) USING BTREE,
  UNIQUE INDEX `uk_item_id`(`item_id` ASC) USING BTREE,
  INDEX `idx_store_id`(`store_id` ASC) USING BTREE,
  INDEX `idx_listing_status`(`listing_status` ASC) USING BTREE,
  INDEX `idx_listing_start_time`(`listing_start_time` ASC) USING BTREE,
  INDEX `idx_listing_end_time`(`listing_end_time` ASC) USING BTREE,
  INDEX `idx_platform`(`platform` ASC) USING BTREE,
  INDEX `idx_quantity`(`quantity` ASC) USING BTREE,
  INDEX `idx_msku_local_sku`(`msku` ASC, `local_sku` ASC) USING BTREE
) ENGINE = InnoDB AUTO_INCREMENT = 86272 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_unicode_ci COMMENT = '领星eBay商品Listing源数据表' ROW_FORMAT = DYNAMIC;

-- ----------------------------
-- Table structure for ebay_replenish_formula
-- ----------------------------
DROP TABLE IF EXISTS `ebay_replenish_formula`;
CREATE TABLE `ebay_replenish_formula`  (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `name` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '公式名称',
  `scenario_order` int NOT NULL DEFAULT 0 COMMENT '场景序号1-13',
  `product_nature` tinyint NOT NULL DEFAULT 1 COMMENT '0新品 1老品',
  `rule_group` varchar(30) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL COMMENT 'NEW_PRODUCT/OLD_D7_POSITIVE/OLD_D7_ZERO_D15_POSITIVE/OLD_NO_SALES',
  `condition_desc` varchar(500) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL COMMENT '条件说明',
  `lower_bound` decimal(10, 4) NULL DEFAULT NULL COMMENT '阈值下限',
  `upper_bound` decimal(10, 4) NULL DEFAULT NULL COMMENT '阈值上限',
  `compare_metric` varchar(10) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL COMMENT 'D7_AVG/D15_AVG/NONE',
  `weight_7d` decimal(10, 3) NULL DEFAULT 0.000 COMMENT '7天权重',
  `weight_15d` decimal(10, 3) NULL DEFAULT 0.000 COMMENT '15天权重',
  `weight_30d` decimal(10, 3) NULL DEFAULT 1.000 COMMENT '30天权重',
  `multiplier` decimal(10, 2) NULL DEFAULT 30.00 COMMENT '乘数',
  `multiply_30` tinyint NOT NULL DEFAULT 1 COMMENT '是否乘以30',
  `remark` varchar(500) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL,
  `status` tinyint NULL DEFAULT 1 COMMENT '1启用 0停用',
  `create_time` datetime NULL DEFAULT CURRENT_TIMESTAMP,
  `update_time` datetime NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`) USING BTREE
) ENGINE = InnoDB AUTO_INCREMENT = 14 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_unicode_ci COMMENT = 'eBay补货公式配置' ROW_FORMAT = Dynamic;

-- ----------------------------
-- Table structure for ebay_replenishment_snapshot
-- ----------------------------
DROP TABLE IF EXISTS `ebay_replenishment_snapshot`;
CREATE TABLE `ebay_replenishment_snapshot`  (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `site` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT 'Original inventory_overview.warehouse_names',
  `sku` varchar(200) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `product_name` varchar(500) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT '',
  `sku_level` varchar(5) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT 'E',
  `product_nature` tinyint NULL DEFAULT NULL COMMENT '产品性质: 1老品 2新品',
  `profit_rate_30d` decimal(10, 2) NULL DEFAULT NULL COMMENT 'Original last30_days_profit, percentage value',
  `return_rate` decimal(10, 4) NULL DEFAULT NULL,
  `overseas_onway` int NULL DEFAULT 0,
  `overseas_sellable` int NULL DEFAULT 0,
  `overseas_total` int NULL DEFAULT 0,
  `purchase_pending_delivery` int NULL DEFAULT 0,
  `local_sellable` int NULL DEFAULT 0,
  `local_onway` int NULL DEFAULT 0,
  `purchase_plan_qty` int NULL DEFAULT 0,
  `locked_qty` int NULL DEFAULT 0,
  `total_inventory` int NULL DEFAULT 0,
  `sales_7d` int NULL DEFAULT 0,
  `sales_15d` int NULL DEFAULT 0 COMMENT '15天销量',
  `sales_30d` int NULL DEFAULT 0,
  `sales_90d` int NULL DEFAULT 0,
  `max_monthly_sales` int NULL DEFAULT NULL,
  `monthly_sales_forecast` int NULL DEFAULT 0 COMMENT '月销预测',
  `overseas_sellable_sales_ratio` decimal(10, 1) NULL DEFAULT NULL,
  `overseas_total_sales_ratio` decimal(10, 1) NULL DEFAULT NULL,
  `total_inventory_sales_ratio` decimal(10, 1) NULL DEFAULT NULL,
  `last_local_outbound_time` varchar(20) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT '',
  `outbound_days` int NULL DEFAULT NULL,
  `purchase_cycle_days` int NULL DEFAULT NULL,
  `suggest_purchase_qty` decimal(10, 0) NULL DEFAULT NULL,
  `max_monthly_replenish_qty` int NULL DEFAULT NULL,
  `owner_name` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT '',
  `source_overview_id` bigint NULL DEFAULT NULL,
  `calc_time` datetime NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  `batch_no` varchar(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL,
  `current_flag` tinyint NOT NULL DEFAULT 1,
  `return_level` varchar(20) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL COMMENT '退货等级',
  `monthly_turnover_rate` decimal(10, 2) NULL DEFAULT NULL COMMENT '月动销率',
  PRIMARY KEY (`id`) USING BTREE,
  UNIQUE INDEX `uk_batch_site_sku`(`batch_no` ASC, `site` ASC, `sku` ASC) USING BTREE,
  INDEX `idx_sku`(`sku` ASC) USING BTREE,
  INDEX `idx_site`(`site` ASC) USING BTREE,
  INDEX `idx_owner`(`owner_name` ASC) USING BTREE,
  INDEX `idx_site_sku`(`site` ASC, `sku` ASC) USING BTREE,
  INDEX `idx_ers_current`(`current_flag` ASC) USING BTREE,
  INDEX `idx_ers_batch`(`batch_no` ASC) USING BTREE
) ENGINE = InnoDB AUTO_INCREMENT = 153173 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_unicode_ci COMMENT = 'eBay补货计算快照' ROW_FORMAT = DYNAMIC;

-- ----------------------------
-- Table structure for ebay_sales
-- ----------------------------
DROP TABLE IF EXISTS `ebay_sales`;
CREATE TABLE `ebay_sales`  (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `platform_order_no` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '平台订单号',
  `currency` varchar(10) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT '' COMMENT '币种',
  `sku` varchar(200) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '库存SKU',
  `quantity` int NULL DEFAULT 0 COMMENT '购买数量',
  `payment_time` datetime NULL DEFAULT NULL COMMENT '付款时间',
  `upload_time` datetime NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`) USING BTREE,
  UNIQUE INDEX `uk_order_sku`(`platform_order_no` ASC, `sku` ASC) USING BTREE,
  INDEX `idx_sku`(`sku` ASC) USING BTREE,
  INDEX `idx_payment_time`(`payment_time` ASC) USING BTREE,
  INDEX `idx_payment_currency`(`payment_time` ASC, `currency` ASC) USING BTREE,
  INDEX `idx_sku_currency_payment`(`sku` ASC, `currency` ASC, `payment_time` ASC) USING BTREE
) ENGINE = InnoDB AUTO_INCREMENT = 2518860 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_unicode_ci COMMENT = 'eBay销量导入明细表' ROW_FORMAT = DYNAMIC;

-- ----------------------------
-- Table structure for gen_table
-- ----------------------------
DROP TABLE IF EXISTS `gen_table`;
CREATE TABLE `gen_table`  (
  `table_id` bigint NOT NULL AUTO_INCREMENT COMMENT '编号',
  `table_name` varchar(200) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT '' COMMENT '表名称',
  `table_comment` varchar(500) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT '' COMMENT '表描述',
  `sub_table_name` varchar(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT NULL COMMENT '关联子表的表名',
  `sub_table_fk_name` varchar(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT NULL COMMENT '子表关联的外键名',
  `class_name` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT '' COMMENT '实体类名称',
  `tpl_category` varchar(200) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT 'crud' COMMENT '使用的模板（crud单表操作 tree树表操作）',
  `tpl_web_type` varchar(30) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT '' COMMENT '前端模板类型（element-ui模版 element-plus模版）',
  `package_name` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT NULL COMMENT '生成包路径',
  `module_name` varchar(30) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT NULL COMMENT '生成模块名',
  `business_name` varchar(30) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT NULL COMMENT '生成业务名',
  `function_name` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT NULL COMMENT '生成功能名',
  `function_author` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT NULL COMMENT '生成功能作者',
  `form_col_num` int NULL DEFAULT 1 COMMENT '表单布局（单列 双列 三列）',
  `gen_type` char(1) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT '0' COMMENT '生成代码方式（0zip压缩包 1自定义路径）',
  `gen_path` varchar(200) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT '/' COMMENT '生成路径（不填默认项目路径）',
  `options` varchar(1000) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT NULL COMMENT '其它生成选项',
  `create_by` varchar(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT '' COMMENT '创建者',
  `create_time` datetime NULL DEFAULT NULL COMMENT '创建时间',
  `update_by` varchar(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT '' COMMENT '更新者',
  `update_time` datetime NULL DEFAULT NULL COMMENT '更新时间',
  `remark` varchar(500) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT NULL COMMENT '备注',
  PRIMARY KEY (`table_id`) USING BTREE
) ENGINE = InnoDB AUTO_INCREMENT = 2 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_0900_ai_ci COMMENT = '代码生成业务表' ROW_FORMAT = DYNAMIC;

-- ----------------------------
-- Table structure for gen_table_column
-- ----------------------------
DROP TABLE IF EXISTS `gen_table_column`;
CREATE TABLE `gen_table_column`  (
  `column_id` bigint NOT NULL AUTO_INCREMENT COMMENT '编号',
  `table_id` bigint NULL DEFAULT NULL COMMENT '归属表编号',
  `column_name` varchar(200) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT NULL COMMENT '列名称',
  `column_comment` varchar(500) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT NULL COMMENT '列描述',
  `column_type` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT NULL COMMENT '列类型',
  `java_type` varchar(500) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT NULL COMMENT 'JAVA类型',
  `java_field` varchar(200) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT NULL COMMENT 'JAVA字段名',
  `is_pk` char(1) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT NULL COMMENT '是否主键（1是）',
  `is_increment` char(1) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT NULL COMMENT '是否自增（1是）',
  `is_required` char(1) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT NULL COMMENT '是否必填（1是）',
  `is_insert` char(1) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT NULL COMMENT '是否为插入字段（1是）',
  `is_edit` char(1) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT NULL COMMENT '是否编辑字段（1是）',
  `is_list` char(1) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT NULL COMMENT '是否列表字段（1是）',
  `is_query` char(1) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT NULL COMMENT '是否查询字段（1是）',
  `query_type` varchar(200) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT 'EQ' COMMENT '查询方式（等于、不等于、大于、小于、范围）',
  `html_type` varchar(200) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT NULL COMMENT '显示类型（文本框、文本域、下拉框、复选框、单选框、日期控件）',
  `dict_type` varchar(200) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT '' COMMENT '字典类型',
  `sort` int NULL DEFAULT NULL COMMENT '排序',
  `create_by` varchar(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT '' COMMENT '创建者',
  `create_time` datetime NULL DEFAULT NULL COMMENT '创建时间',
  `update_by` varchar(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT '' COMMENT '更新者',
  `update_time` datetime NULL DEFAULT NULL COMMENT '更新时间',
  PRIMARY KEY (`column_id`) USING BTREE
) ENGINE = InnoDB AUTO_INCREMENT = 14 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_0900_ai_ci COMMENT = '代码生成业务表字段' ROW_FORMAT = DYNAMIC;

-- ----------------------------
-- Table structure for goodcang_grn_detail
-- ----------------------------
DROP TABLE IF EXISTS `goodcang_grn_detail`;
CREATE TABLE `goodcang_grn_detail`  (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `receiving_code` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '入库单号',
  `product_sku` varchar(200) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT '' COMMENT '商品SKU',
  `box_no` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT '' COMMENT '箱号',
  `transit_pre_count` int NULL DEFAULT 0 COMMENT '中转预报数量',
  `transit_receiving_count` int NULL DEFAULT 0 COMMENT '中转收货数量',
  `reference_box_no` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT '' COMMENT '第三方箱唛号',
  `upload_time` datetime NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`) USING BTREE,
  INDEX `idx_receiving_code`(`receiving_code` ASC) USING BTREE,
  INDEX `idx_product_sku`(`product_sku` ASC) USING BTREE
) ENGINE = InnoDB AUTO_INCREMENT = 141595 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_unicode_ci COMMENT = '谷仓入库单明细表' ROW_FORMAT = DYNAMIC;

-- ----------------------------
-- Table structure for goodcang_grn_list
-- ----------------------------
DROP TABLE IF EXISTS `goodcang_grn_list`;
CREATE TABLE `goodcang_grn_list`  (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `receiving_code` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '入库单号',
  `warehouse_code` varchar(20) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT '' COMMENT '海外仓仓库编码',
  `transit_warehouse_code` varchar(20) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT '' COMMENT '中转仓仓库编码',
  `reference_no` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT '' COMMENT '客户参考号',
  `receiving_status` int NULL DEFAULT 0 COMMENT '入库单状态',
  `transit_type` int NULL DEFAULT 0 COMMENT '入库单类型',
  `create_at` datetime NULL DEFAULT NULL COMMENT '创建时间',
  `update_at` datetime NULL DEFAULT NULL COMMENT '修改时间',
  `upload_time` datetime NULL DEFAULT CURRENT_TIMESTAMP,
  `ca_address1` varchar(500) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL COMMENT '提货地址1',
  PRIMARY KEY (`id`) USING BTREE,
  UNIQUE INDEX `uk_receiving_code`(`receiving_code` ASC) USING BTREE,
  INDEX `idx_warehouse`(`warehouse_code` ASC) USING BTREE,
  INDEX `idx_create_at`(`create_at` ASC) USING BTREE
) ENGINE = InnoDB AUTO_INCREMENT = 555 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_unicode_ci COMMENT = '谷仓入库单列表表' ROW_FORMAT = DYNAMIC;

-- ----------------------------
-- Table structure for goodcang_product_info
-- ----------------------------
DROP TABLE IF EXISTS `goodcang_product_info`;
CREATE TABLE `goodcang_product_info`  (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `sku_middle` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '中间码',
  `product_name_cn` varchar(300) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL COMMENT '中文名称',
  `real_weight` decimal(10, 3) NULL DEFAULT NULL COMMENT '实收重量(KG)',
  `real_length` decimal(10, 2) NULL DEFAULT NULL COMMENT '实收长(CM)',
  `real_width` decimal(10, 2) NULL DEFAULT NULL COMMENT '实收宽(CM)',
  `real_height` decimal(10, 2) NULL DEFAULT NULL COMMENT '实收高(CM)',
  `volume` decimal(10, 2) NULL DEFAULT NULL COMMENT '体积(长*宽*高/6000)',
  `price` decimal(10, 2) NULL DEFAULT NULL COMMENT '单价',
  `create_time` datetime NULL DEFAULT CURRENT_TIMESTAMP,
  `update_time` datetime NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`) USING BTREE,
  UNIQUE INDEX `middle_code`(`sku_middle` ASC) USING BTREE
) ENGINE = InnoDB AUTO_INCREMENT = 2291 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_unicode_ci COMMENT = '谷仓商品成本重量体积信息表' ROW_FORMAT = DYNAMIC;

-- ----------------------------
-- Table structure for goodcang_warehouse
-- ----------------------------
DROP TABLE IF EXISTS `goodcang_warehouse`;
CREATE TABLE `goodcang_warehouse`  (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `warehouse_code` varchar(20) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '区域仓代码',
  `wid` int NULL DEFAULT 0 COMMENT '关联warehouse.wid',
  `warehouse_name` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT '' COMMENT '仓库名称',
  `country_code` varchar(10) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT '' COMMENT '国家代码',
  `wp_code` varchar(30) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT '' COMMENT '物理仓编码',
  `wp_name` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT '' COMMENT '物理仓名称',
  `state` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT '' COMMENT '州/省份',
  `city` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT '' COMMENT '城市',
  `postcode` varchar(20) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT '' COMMENT '邮编',
  `contacter` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT '' COMMENT '联系人',
  `phone` varchar(30) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT '' COMMENT '电话',
  `street_address1` varchar(200) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT '' COMMENT '地址1',
  `street_address2` varchar(200) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT '' COMMENT '地址2',
  `street_number` varchar(20) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT '' COMMENT '门牌号',
  `upload_time` datetime NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`) USING BTREE,
  UNIQUE INDEX `uk_wp_code`(`wp_code` ASC) USING BTREE,
  INDEX `idx_warehouse_code`(`warehouse_code` ASC) USING BTREE,
  INDEX `idx_country_code`(`country_code` ASC) USING BTREE
) ENGINE = InnoDB AUTO_INCREMENT = 82 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_unicode_ci COMMENT = '谷仓仓库基础表' ROW_FORMAT = DYNAMIC;

-- ----------------------------
-- Table structure for lingxing_product_weight
-- ----------------------------
DROP TABLE IF EXISTS `lingxing_product_weight`;
CREATE TABLE `lingxing_product_weight`  (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `sku` varchar(200) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '产品SKU',
  `gross_weight` decimal(12, 4) NULL DEFAULT NULL COMMENT '产品毛重',
  `net_weight` decimal(12, 4) NULL DEFAULT NULL COMMENT '产品净重G',
  `create_time` datetime NULL DEFAULT CURRENT_TIMESTAMP,
  `update_time` datetime NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`) USING BTREE,
  UNIQUE INDEX `uk_sku`(`sku` ASC) USING BTREE
) ENGINE = InnoDB AUTO_INCREMENT = 5417 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_unicode_ci COMMENT = '领星产品毛重' ROW_FORMAT = Dynamic;

-- ----------------------------
-- Table structure for operation_import_task
-- ----------------------------
DROP TABLE IF EXISTS `operation_import_task`;
CREATE TABLE `operation_import_task`  (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `file_name` varchar(300) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL COMMENT '文件名',
  `task_type` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL COMMENT '导入类型',
  `operator` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT NULL COMMENT '操作者',
  `status` varchar(20) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL DEFAULT 'PENDING' COMMENT 'PENDING/RUNNING/SUCCESS/FAILED',
  `total_rows` int NULL DEFAULT 0 COMMENT '总行数',
  `success_rows` int NULL DEFAULT 0 COMMENT '成功数',
  `fail_rows` int NULL DEFAULT 0 COMMENT '失败数',
  `error_file_path` varchar(500) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT NULL COMMENT '错误明细文件路径',
  `start_time` datetime NULL DEFAULT NULL,
  `end_time` datetime NULL DEFAULT NULL,
  `create_time` datetime NULL DEFAULT CURRENT_TIMESTAMP,
  `fail_detail_json` longtext CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL COMMENT '???????????SON',
  PRIMARY KEY (`id`) USING BTREE,
  INDEX `idx_type_status`(`task_type` ASC, `status` ASC) USING BTREE,
  INDEX `idx_create`(`create_time` ASC) USING BTREE
) ENGINE = InnoDB AUTO_INCREMENT = 18 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_0900_ai_ci COMMENT = '运营导入任务表' ROW_FORMAT = DYNAMIC;

-- ----------------------------
-- Table structure for overseas_stock_order
-- ----------------------------
DROP TABLE IF EXISTS `overseas_stock_order`;
CREATE TABLE `overseas_stock_order`  (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `overseas_order_no` varchar(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL COMMENT '备货单号',
  `inbound_order_no` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT NULL COMMENT '三方入库单号',
  `create_time` datetime NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`) USING BTREE,
  UNIQUE INDEX `uk_overseas_order_no`(`overseas_order_no` ASC) USING BTREE
) ENGINE = InnoDB AUTO_INCREMENT = 118 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_0900_ai_ci COMMENT = '领星备货单号表' ROW_FORMAT = DYNAMIC;

-- ----------------------------
-- Table structure for overseas_stock_order_detail
-- ----------------------------
DROP TABLE IF EXISTS `overseas_stock_order_detail`;
CREATE TABLE `overseas_stock_order_detail`  (
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
) ENGINE = InnoDB AUTO_INCREMENT = 26273 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_0900_ai_ci COMMENT = '领星备货单详情' ROW_FORMAT = DYNAMIC;

-- ----------------------------
-- Table structure for purchase_order
-- ----------------------------
DROP TABLE IF EXISTS `purchase_order`;
CREATE TABLE `purchase_order`  (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `order_sn` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT '' COMMENT '采购单号',
  `custom_order_sn` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT '' COMMENT '自定义单号',
  `supplier_id` int NULL DEFAULT 0 COMMENT '供应商id',
  `supplier_name` varchar(200) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT '' COMMENT '供应商',
  `opt_uid` int NULL DEFAULT 0 COMMENT '采购员id',
  `opt_realname` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT '' COMMENT '操作人姓名',
  `auditor_realname` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT '' COMMENT '审核人姓名',
  `last_realname` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT '' COMMENT '最后操作人姓名',
  `create_time` datetime NULL DEFAULT NULL COMMENT '创建时间',
  `order_time` datetime NULL DEFAULT NULL COMMENT '下单时间',
  `update_time` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT '' COMMENT '采购单更新时间',
  `status` int NULL DEFAULT 0 COMMENT '采购单状态',
  `status_text` varchar(20) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT '' COMMENT '状态说明',
  `wid` int NULL DEFAULT 0 COMMENT '仓库id',
  `ware_house_name` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT '' COMMENT '仓库名',
  `item_sku` varchar(200) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT '' COMMENT '子项SKU',
  `item_product_name` varchar(200) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT '' COMMENT '子项品名',
  `item_product_id` int NULL DEFAULT 0 COMMENT '子项产品id',
  `item_quantity_real` int NULL DEFAULT 0 COMMENT '子项实际采购量',
  `item_quantity_entry` int NULL DEFAULT 0 COMMENT '子项到货入库量',
  `item_quantity_receive` int NULL DEFAULT 0 COMMENT '待到货量',
  `item_price` decimal(16, 4) NULL DEFAULT 0.0000 COMMENT '子项含税单价',
  `item_amount` decimal(16, 4) NULL DEFAULT 0.0000 COMMENT '子项价税合计',
  `upload_time` datetime NULL DEFAULT CURRENT_TIMESTAMP,
  `is_tax` int NULL DEFAULT NULL COMMENT '是否含税 0否 1是',
  PRIMARY KEY (`id`) USING BTREE,
  UNIQUE INDEX `uk_order_create`(`order_sn` ASC, `create_time` ASC) USING BTREE,
  INDEX `idx_create_time`(`create_time` ASC) USING BTREE,
  INDEX `idx_item_sku`(`item_sku` ASC) USING BTREE,
  INDEX `idx_create_time_status`(`create_time` ASC, `status_text` ASC) USING BTREE
) ENGINE = InnoDB AUTO_INCREMENT = 5185 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_unicode_ci COMMENT = '领星采购单明细表' ROW_FORMAT = DYNAMIC;

-- ----------------------------
-- Table structure for purchase_plan
-- ----------------------------
DROP TABLE IF EXISTS `purchase_plan`;
CREATE TABLE `purchase_plan`  (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `plan_sn` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT '' COMMENT '采购计划编号',
  `ppg_sn` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT '' COMMENT '采购计划批次号',
  `product_name` varchar(200) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT '' COMMENT '品名',
  `sku` varchar(200) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT '' COMMENT 'SKU',
  `fnsku` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT '' COMMENT 'FNSKU',
  `pic_url` varchar(500) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT '' COMMENT '产品图片',
  `supplier_id` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT '' COMMENT '供应商id',
  `supplier_name` varchar(200) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT '' COMMENT '供应商名称',
  `status_text` varchar(20) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT '' COMMENT '状态说明',
  `status` int NULL DEFAULT 0 COMMENT '状态值: 2待采购 -2已完成 121待审批 122已驳回 -3/124已作废',
  `sid` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT '' COMMENT '店铺id',
  `seller_name` varchar(200) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT '' COMMENT '店铺名称',
  `marketplace` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT '' COMMENT '国家',
  `expect_arrive_time` varchar(20) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT '' COMMENT '期望到货时间',
  `remark` varchar(500) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT '' COMMENT '产品备注',
  `quantity_plan` int NULL DEFAULT 0 COMMENT '计划采购量',
  `product_id` int NULL DEFAULT 0 COMMENT '商品id',
  `cg_uid` int NULL DEFAULT 0 COMMENT '采购员id',
  `cg_opt_username` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT '' COMMENT '采购员名称',
  `cg_box_pcs` int NULL DEFAULT 0 COMMENT '单箱数量',
  `is_combo` int NULL DEFAULT 0 COMMENT '组合商品: 0否 1是',
  `is_aux` int NULL DEFAULT 0 COMMENT '辅料: 0否 1是',
  `is_related_process_plan` int NULL DEFAULT 0 COMMENT '关联加工计划: 0否 1是',
  `spu` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT '' COMMENT 'SPU',
  `spu_name` varchar(200) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT '' COMMENT '款名',
  `creator_uid` int NULL DEFAULT 0 COMMENT '创建人id',
  `creator_real_name` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT '' COMMENT '创建人名称',
  `wid` int NULL DEFAULT 0 COMMENT '仓库id',
  `warehouse_name` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT '' COMMENT '仓库名称',
  `purchaser_id` int NULL DEFAULT 0 COMMENT '采购方id',
  `purchaser_name` varchar(200) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT '' COMMENT '采购方名称',
  `create_time` datetime NULL DEFAULT NULL,
  `plan_remark` varchar(500) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT '' COMMENT '计划备注',
  `attribute_json` json NULL COMMENT '属性',
  `file_json` json NULL COMMENT '附件',
  `msku_json` json NULL COMMENT 'MSKU',
  `perm_uid_json` json NULL COMMENT '单据负责人uid',
  `perm_username_json` json NULL COMMENT '单据负责人名称',
  `upload_time` datetime NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`) USING BTREE,
  UNIQUE INDEX `uk_plan_sku`(`plan_sn` ASC, `sku` ASC) USING BTREE,
  INDEX `idx_ppg_sn`(`ppg_sn` ASC) USING BTREE,
  INDEX `idx_sku`(`sku` ASC) USING BTREE,
  INDEX `idx_status`(`status` ASC) USING BTREE,
  INDEX `idx_create_time`(`create_time` ASC) USING BTREE,
  INDEX `idx_status_upload`(`status_text` ASC, `upload_time` ASC) USING BTREE,
  INDEX `idx_upload_time`(`upload_time` ASC) USING BTREE
) ENGINE = InnoDB AUTO_INCREMENT = 2612 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_unicode_ci COMMENT = '领星采购计划明细表' ROW_FORMAT = DYNAMIC;

-- ----------------------------
-- Table structure for qrtz_blob_triggers
-- ----------------------------
DROP TABLE IF EXISTS `qrtz_blob_triggers`;
CREATE TABLE `qrtz_blob_triggers`  (
  `sched_name` varchar(120) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL COMMENT '调度名称',
  `trigger_name` varchar(200) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL COMMENT 'qrtz_triggers表trigger_name的外键',
  `trigger_group` varchar(200) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL COMMENT 'qrtz_triggers表trigger_group的外键',
  `blob_data` blob NULL COMMENT '存放持久化Trigger对象',
  PRIMARY KEY (`sched_name`, `trigger_name`, `trigger_group`) USING BTREE,
  CONSTRAINT `qrtz_blob_triggers_ibfk_1` FOREIGN KEY (`sched_name`, `trigger_name`, `trigger_group`) REFERENCES `qrtz_triggers` (`sched_name`, `trigger_name`, `trigger_group`) ON DELETE RESTRICT ON UPDATE RESTRICT
) ENGINE = InnoDB CHARACTER SET = utf8mb4 COLLATE = utf8mb4_0900_ai_ci COMMENT = 'Blob类型的触发器表' ROW_FORMAT = DYNAMIC;

-- ----------------------------
-- Table structure for qrtz_calendars
-- ----------------------------
DROP TABLE IF EXISTS `qrtz_calendars`;
CREATE TABLE `qrtz_calendars`  (
  `sched_name` varchar(120) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL COMMENT '调度名称',
  `calendar_name` varchar(200) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL COMMENT '日历名称',
  `calendar` blob NOT NULL COMMENT '存放持久化calendar对象',
  PRIMARY KEY (`sched_name`, `calendar_name`) USING BTREE
) ENGINE = InnoDB CHARACTER SET = utf8mb4 COLLATE = utf8mb4_0900_ai_ci COMMENT = '日历信息表' ROW_FORMAT = DYNAMIC;

-- ----------------------------
-- Table structure for qrtz_cron_triggers
-- ----------------------------
DROP TABLE IF EXISTS `qrtz_cron_triggers`;
CREATE TABLE `qrtz_cron_triggers`  (
  `sched_name` varchar(120) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL COMMENT '调度名称',
  `trigger_name` varchar(200) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL COMMENT 'qrtz_triggers表trigger_name的外键',
  `trigger_group` varchar(200) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL COMMENT 'qrtz_triggers表trigger_group的外键',
  `cron_expression` varchar(200) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL COMMENT 'cron表达式',
  `time_zone_id` varchar(80) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT NULL COMMENT '时区',
  PRIMARY KEY (`sched_name`, `trigger_name`, `trigger_group`) USING BTREE,
  CONSTRAINT `qrtz_cron_triggers_ibfk_1` FOREIGN KEY (`sched_name`, `trigger_name`, `trigger_group`) REFERENCES `qrtz_triggers` (`sched_name`, `trigger_name`, `trigger_group`) ON DELETE RESTRICT ON UPDATE RESTRICT
) ENGINE = InnoDB CHARACTER SET = utf8mb4 COLLATE = utf8mb4_0900_ai_ci COMMENT = 'Cron类型的触发器表' ROW_FORMAT = DYNAMIC;

-- ----------------------------
-- Table structure for qrtz_fired_triggers
-- ----------------------------
DROP TABLE IF EXISTS `qrtz_fired_triggers`;
CREATE TABLE `qrtz_fired_triggers`  (
  `sched_name` varchar(120) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL COMMENT '调度名称',
  `entry_id` varchar(95) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL COMMENT '调度器实例id',
  `trigger_name` varchar(200) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL COMMENT 'qrtz_triggers表trigger_name的外键',
  `trigger_group` varchar(200) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL COMMENT 'qrtz_triggers表trigger_group的外键',
  `instance_name` varchar(200) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL COMMENT '调度器实例名',
  `fired_time` bigint NOT NULL COMMENT '触发的时间',
  `sched_time` bigint NOT NULL COMMENT '定时器制定的时间',
  `priority` int NOT NULL COMMENT '优先级',
  `state` varchar(16) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL COMMENT '状态',
  `job_name` varchar(200) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT NULL COMMENT '任务名称',
  `job_group` varchar(200) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT NULL COMMENT '任务组名',
  `is_nonconcurrent` varchar(1) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT NULL COMMENT '是否并发',
  `requests_recovery` varchar(1) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT NULL COMMENT '是否接受恢复执行',
  PRIMARY KEY (`sched_name`, `entry_id`) USING BTREE
) ENGINE = InnoDB CHARACTER SET = utf8mb4 COLLATE = utf8mb4_0900_ai_ci COMMENT = '已触发的触发器表' ROW_FORMAT = DYNAMIC;

-- ----------------------------
-- Table structure for qrtz_job_details
-- ----------------------------
DROP TABLE IF EXISTS `qrtz_job_details`;
CREATE TABLE `qrtz_job_details`  (
  `sched_name` varchar(120) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL COMMENT '调度名称',
  `job_name` varchar(200) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL COMMENT '任务名称',
  `job_group` varchar(200) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL COMMENT '任务组名',
  `description` varchar(250) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT NULL COMMENT '相关介绍',
  `job_class_name` varchar(250) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL COMMENT '执行任务类名称',
  `is_durable` varchar(1) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL COMMENT '是否持久化',
  `is_nonconcurrent` varchar(1) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL COMMENT '是否并发',
  `is_update_data` varchar(1) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL COMMENT '是否更新数据',
  `requests_recovery` varchar(1) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL COMMENT '是否接受恢复执行',
  `job_data` blob NULL COMMENT '存放持久化job对象',
  PRIMARY KEY (`sched_name`, `job_name`, `job_group`) USING BTREE
) ENGINE = InnoDB CHARACTER SET = utf8mb4 COLLATE = utf8mb4_0900_ai_ci COMMENT = '任务详细信息表' ROW_FORMAT = DYNAMIC;

-- ----------------------------
-- Table structure for qrtz_locks
-- ----------------------------
DROP TABLE IF EXISTS `qrtz_locks`;
CREATE TABLE `qrtz_locks`  (
  `sched_name` varchar(120) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL COMMENT '调度名称',
  `lock_name` varchar(40) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL COMMENT '悲观锁名称',
  PRIMARY KEY (`sched_name`, `lock_name`) USING BTREE
) ENGINE = InnoDB CHARACTER SET = utf8mb4 COLLATE = utf8mb4_0900_ai_ci COMMENT = '存储的悲观锁信息表' ROW_FORMAT = DYNAMIC;

-- ----------------------------
-- Table structure for qrtz_paused_trigger_grps
-- ----------------------------
DROP TABLE IF EXISTS `qrtz_paused_trigger_grps`;
CREATE TABLE `qrtz_paused_trigger_grps`  (
  `sched_name` varchar(120) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL COMMENT '调度名称',
  `trigger_group` varchar(200) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL COMMENT 'qrtz_triggers表trigger_group的外键',
  PRIMARY KEY (`sched_name`, `trigger_group`) USING BTREE
) ENGINE = InnoDB CHARACTER SET = utf8mb4 COLLATE = utf8mb4_0900_ai_ci COMMENT = '暂停的触发器表' ROW_FORMAT = DYNAMIC;

-- ----------------------------
-- Table structure for qrtz_scheduler_state
-- ----------------------------
DROP TABLE IF EXISTS `qrtz_scheduler_state`;
CREATE TABLE `qrtz_scheduler_state`  (
  `sched_name` varchar(120) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL COMMENT '调度名称',
  `instance_name` varchar(200) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL COMMENT '实例名称',
  `last_checkin_time` bigint NOT NULL COMMENT '上次检查时间',
  `checkin_interval` bigint NOT NULL COMMENT '检查间隔时间',
  PRIMARY KEY (`sched_name`, `instance_name`) USING BTREE
) ENGINE = InnoDB CHARACTER SET = utf8mb4 COLLATE = utf8mb4_0900_ai_ci COMMENT = '调度器状态表' ROW_FORMAT = DYNAMIC;

-- ----------------------------
-- Table structure for qrtz_simple_triggers
-- ----------------------------
DROP TABLE IF EXISTS `qrtz_simple_triggers`;
CREATE TABLE `qrtz_simple_triggers`  (
  `sched_name` varchar(120) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL COMMENT '调度名称',
  `trigger_name` varchar(200) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL COMMENT 'qrtz_triggers表trigger_name的外键',
  `trigger_group` varchar(200) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL COMMENT 'qrtz_triggers表trigger_group的外键',
  `repeat_count` bigint NOT NULL COMMENT '重复的次数统计',
  `repeat_interval` bigint NOT NULL COMMENT '重复的间隔时间',
  `times_triggered` bigint NOT NULL COMMENT '已经触发的次数',
  PRIMARY KEY (`sched_name`, `trigger_name`, `trigger_group`) USING BTREE,
  CONSTRAINT `qrtz_simple_triggers_ibfk_1` FOREIGN KEY (`sched_name`, `trigger_name`, `trigger_group`) REFERENCES `qrtz_triggers` (`sched_name`, `trigger_name`, `trigger_group`) ON DELETE RESTRICT ON UPDATE RESTRICT
) ENGINE = InnoDB CHARACTER SET = utf8mb4 COLLATE = utf8mb4_0900_ai_ci COMMENT = '简单触发器的信息表' ROW_FORMAT = DYNAMIC;

-- ----------------------------
-- Table structure for qrtz_simprop_triggers
-- ----------------------------
DROP TABLE IF EXISTS `qrtz_simprop_triggers`;
CREATE TABLE `qrtz_simprop_triggers`  (
  `sched_name` varchar(120) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL COMMENT '调度名称',
  `trigger_name` varchar(200) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL COMMENT 'qrtz_triggers表trigger_name的外键',
  `trigger_group` varchar(200) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL COMMENT 'qrtz_triggers表trigger_group的外键',
  `str_prop_1` varchar(512) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT NULL COMMENT 'String类型的trigger的第一个参数',
  `str_prop_2` varchar(512) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT NULL COMMENT 'String类型的trigger的第二个参数',
  `str_prop_3` varchar(512) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT NULL COMMENT 'String类型的trigger的第三个参数',
  `int_prop_1` int NULL DEFAULT NULL COMMENT 'int类型的trigger的第一个参数',
  `int_prop_2` int NULL DEFAULT NULL COMMENT 'int类型的trigger的第二个参数',
  `long_prop_1` bigint NULL DEFAULT NULL COMMENT 'long类型的trigger的第一个参数',
  `long_prop_2` bigint NULL DEFAULT NULL COMMENT 'long类型的trigger的第二个参数',
  `dec_prop_1` decimal(13, 4) NULL DEFAULT NULL COMMENT 'decimal类型的trigger的第一个参数',
  `dec_prop_2` decimal(13, 4) NULL DEFAULT NULL COMMENT 'decimal类型的trigger的第二个参数',
  `bool_prop_1` varchar(1) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT NULL COMMENT 'Boolean类型的trigger的第一个参数',
  `bool_prop_2` varchar(1) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT NULL COMMENT 'Boolean类型的trigger的第二个参数',
  PRIMARY KEY (`sched_name`, `trigger_name`, `trigger_group`) USING BTREE,
  CONSTRAINT `qrtz_simprop_triggers_ibfk_1` FOREIGN KEY (`sched_name`, `trigger_name`, `trigger_group`) REFERENCES `qrtz_triggers` (`sched_name`, `trigger_name`, `trigger_group`) ON DELETE RESTRICT ON UPDATE RESTRICT
) ENGINE = InnoDB CHARACTER SET = utf8mb4 COLLATE = utf8mb4_0900_ai_ci COMMENT = '同步机制的行锁表' ROW_FORMAT = DYNAMIC;

-- ----------------------------
-- Table structure for qrtz_triggers
-- ----------------------------
DROP TABLE IF EXISTS `qrtz_triggers`;
CREATE TABLE `qrtz_triggers`  (
  `sched_name` varchar(120) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL COMMENT '调度名称',
  `trigger_name` varchar(200) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL COMMENT '触发器的名字',
  `trigger_group` varchar(200) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL COMMENT '触发器所属组的名字',
  `job_name` varchar(200) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL COMMENT 'qrtz_job_details表job_name的外键',
  `job_group` varchar(200) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL COMMENT 'qrtz_job_details表job_group的外键',
  `description` varchar(250) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT NULL COMMENT '相关介绍',
  `next_fire_time` bigint NULL DEFAULT NULL COMMENT '上一次触发时间（毫秒）',
  `prev_fire_time` bigint NULL DEFAULT NULL COMMENT '下一次触发时间（默认为-1表示不触发）',
  `priority` int NULL DEFAULT NULL COMMENT '优先级',
  `trigger_state` varchar(16) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL COMMENT '触发器状态',
  `trigger_type` varchar(8) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL COMMENT '触发器的类型',
  `start_time` bigint NOT NULL COMMENT '开始时间',
  `end_time` bigint NULL DEFAULT NULL COMMENT '结束时间',
  `calendar_name` varchar(200) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT NULL COMMENT '日程表名称',
  `misfire_instr` smallint NULL DEFAULT NULL COMMENT '补偿执行的策略',
  `job_data` blob NULL COMMENT '存放持久化job对象',
  PRIMARY KEY (`sched_name`, `trigger_name`, `trigger_group`) USING BTREE,
  INDEX `sched_name`(`sched_name` ASC, `job_name` ASC, `job_group` ASC) USING BTREE,
  CONSTRAINT `qrtz_triggers_ibfk_1` FOREIGN KEY (`sched_name`, `job_name`, `job_group`) REFERENCES `qrtz_job_details` (`sched_name`, `job_name`, `job_group`) ON DELETE RESTRICT ON UPDATE RESTRICT
) ENGINE = InnoDB CHARACTER SET = utf8mb4 COLLATE = utf8mb4_0900_ai_ci COMMENT = '触发器详细信息表' ROW_FORMAT = DYNAMIC;

-- ----------------------------
-- Table structure for shop_list
-- ----------------------------
DROP TABLE IF EXISTS `shop_list`;
CREATE TABLE `shop_list`  (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `store_id` varchar(32) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '店铺ID，eBay店铺唯一标识',
  `sid` varchar(32) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT '' COMMENT 'SID标识，默认为空字符串',
  `store_name` varchar(200) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '店铺名称',
  `platform_code` varchar(10) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '平台代码，10003代表eBay平台',
  `platform_name` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '平台名称',
  `currency` varchar(10) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '店铺使用的货币单位，如HKD港币',
  `is_sync` tinyint NOT NULL DEFAULT 0 COMMENT '是否同步数据，1表示同步，0表示未同步',
  `status` tinyint NOT NULL DEFAULT 1 COMMENT '店铺状态，1表示启用，0表示禁用',
  `country_code` varchar(10) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '国家/地区代码，如HK香港',
  `created_at` datetime NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `updated_at` datetime NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  PRIMARY KEY (`id`) USING BTREE,
  UNIQUE INDEX `uk_store_id`(`store_id` ASC) USING BTREE,
  INDEX `idx_platform_code`(`platform_code` ASC) USING BTREE,
  INDEX `idx_status`(`status` ASC) USING BTREE,
  INDEX `idx_country_code`(`country_code` ASC) USING BTREE,
  INDEX `idx_shop_list_platform_sid`(`platform_code` ASC, `sid` ASC) USING BTREE
) ENGINE = InnoDB AUTO_INCREMENT = 174 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_unicode_ci COMMENT = '领星店铺列表表' ROW_FORMAT = DYNAMIC;

-- ----------------------------
-- Table structure for sys_config
-- ----------------------------
DROP TABLE IF EXISTS `sys_config`;
CREATE TABLE `sys_config`  (
  `config_id` int NOT NULL AUTO_INCREMENT COMMENT '参数主键',
  `config_name` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT '' COMMENT '参数名称',
  `config_key` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT '' COMMENT '参数键名',
  `config_value` varchar(500) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT '' COMMENT '参数键值',
  `config_type` char(1) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT 'N' COMMENT '系统内置（Y是 N否）',
  `create_by` varchar(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT '' COMMENT '创建者',
  `create_time` datetime NULL DEFAULT NULL COMMENT '创建时间',
  `update_by` varchar(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT '' COMMENT '更新者',
  `update_time` datetime NULL DEFAULT NULL COMMENT '更新时间',
  `remark` varchar(500) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT NULL COMMENT '备注',
  PRIMARY KEY (`config_id`) USING BTREE
) ENGINE = InnoDB AUTO_INCREMENT = 100 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_0900_ai_ci COMMENT = '参数配置表' ROW_FORMAT = DYNAMIC;

-- ----------------------------
-- Table structure for sys_dept
-- ----------------------------
DROP TABLE IF EXISTS `sys_dept`;
CREATE TABLE `sys_dept`  (
  `dept_id` bigint NOT NULL AUTO_INCREMENT COMMENT '部门id',
  `parent_id` bigint NULL DEFAULT 0 COMMENT '父部门id',
  `ancestors` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT '' COMMENT '祖级列表',
  `dept_name` varchar(30) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT '' COMMENT '部门名称',
  `order_num` int NULL DEFAULT 0 COMMENT '显示顺序',
  `leader` varchar(20) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT NULL COMMENT '负责人',
  `phone` varchar(11) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT NULL COMMENT '联系电话',
  `email` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT NULL COMMENT '邮箱',
  `status` char(1) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT '0' COMMENT '部门状态（0正常 1停用）',
  `del_flag` char(1) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT '0' COMMENT '删除标志（0代表存在 2代表删除）',
  `create_by` varchar(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT '' COMMENT '创建者',
  `create_time` datetime NULL DEFAULT NULL COMMENT '创建时间',
  `update_by` varchar(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT '' COMMENT '更新者',
  `update_time` datetime NULL DEFAULT NULL COMMENT '更新时间',
  PRIMARY KEY (`dept_id`) USING BTREE
) ENGINE = InnoDB AUTO_INCREMENT = 206 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_0900_ai_ci COMMENT = '部门表' ROW_FORMAT = DYNAMIC;

-- ----------------------------
-- Table structure for sys_dict_data
-- ----------------------------
DROP TABLE IF EXISTS `sys_dict_data`;
CREATE TABLE `sys_dict_data`  (
  `dict_code` bigint NOT NULL AUTO_INCREMENT COMMENT '字典编码',
  `dict_sort` int NULL DEFAULT 0 COMMENT '字典排序',
  `dict_label` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT '' COMMENT '字典标签',
  `dict_value` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT '' COMMENT '字典键值',
  `dict_type` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT '' COMMENT '字典类型',
  `css_class` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT NULL COMMENT '样式属性（其他样式扩展）',
  `list_class` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT NULL COMMENT '表格回显样式',
  `is_default` char(1) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT 'N' COMMENT '是否默认（Y是 N否）',
  `status` char(1) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT '0' COMMENT '状态（0正常 1停用）',
  `create_by` varchar(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT '' COMMENT '创建者',
  `create_time` datetime NULL DEFAULT NULL COMMENT '创建时间',
  `update_by` varchar(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT '' COMMENT '更新者',
  `update_time` datetime NULL DEFAULT NULL COMMENT '更新时间',
  `remark` varchar(500) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT NULL COMMENT '备注',
  PRIMARY KEY (`dict_code`) USING BTREE
) ENGINE = InnoDB AUTO_INCREMENT = 103 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_0900_ai_ci COMMENT = '字典数据表' ROW_FORMAT = DYNAMIC;

-- ----------------------------
-- Table structure for sys_dict_type
-- ----------------------------
DROP TABLE IF EXISTS `sys_dict_type`;
CREATE TABLE `sys_dict_type`  (
  `dict_id` bigint NOT NULL AUTO_INCREMENT COMMENT '字典主键',
  `dict_name` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT '' COMMENT '字典名称',
  `dict_type` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT '' COMMENT '字典类型',
  `status` char(1) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT '0' COMMENT '状态（0正常 1停用）',
  `create_by` varchar(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT '' COMMENT '创建者',
  `create_time` datetime NULL DEFAULT NULL COMMENT '创建时间',
  `update_by` varchar(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT '' COMMENT '更新者',
  `update_time` datetime NULL DEFAULT NULL COMMENT '更新时间',
  `remark` varchar(500) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT NULL COMMENT '备注',
  PRIMARY KEY (`dict_id`) USING BTREE,
  UNIQUE INDEX `dict_type`(`dict_type` ASC) USING BTREE
) ENGINE = InnoDB AUTO_INCREMENT = 100 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_0900_ai_ci COMMENT = '字典类型表' ROW_FORMAT = DYNAMIC;

-- ----------------------------
-- Table structure for sys_job
-- ----------------------------
DROP TABLE IF EXISTS `sys_job`;
CREATE TABLE `sys_job`  (
  `job_id` bigint NOT NULL AUTO_INCREMENT COMMENT '任务ID',
  `job_name` varchar(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL DEFAULT '' COMMENT '任务名称',
  `job_group` varchar(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL DEFAULT 'DEFAULT' COMMENT '任务组名',
  `invoke_target` varchar(500) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL COMMENT '调用目标字符串',
  `cron_expression` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT '' COMMENT 'cron执行表达式',
  `misfire_policy` varchar(20) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT '3' COMMENT '计划执行错误策略（1立即执行 2执行一次 3放弃执行）',
  `concurrent` char(1) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT '1' COMMENT '是否并发执行（0允许 1禁止）',
  `status` char(1) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT '0' COMMENT '状态（0正常 1暂停）',
  `create_by` varchar(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT '' COMMENT '创建者',
  `create_time` datetime NULL DEFAULT NULL COMMENT '创建时间',
  `update_by` varchar(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT '' COMMENT '更新者',
  `update_time` datetime NULL DEFAULT NULL COMMENT '更新时间',
  `remark` varchar(500) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT '' COMMENT '备注信息',
  PRIMARY KEY (`job_id`, `job_name`, `job_group`) USING BTREE
) ENGINE = InnoDB AUTO_INCREMENT = 225 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_0900_ai_ci COMMENT = '定时任务调度表' ROW_FORMAT = DYNAMIC;

-- ----------------------------
-- Table structure for sys_job_log
-- ----------------------------
DROP TABLE IF EXISTS `sys_job_log`;
CREATE TABLE `sys_job_log`  (
  `job_log_id` bigint NOT NULL AUTO_INCREMENT COMMENT '任务日志ID',
  `job_name` varchar(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL COMMENT '任务名称',
  `job_group` varchar(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL COMMENT '任务组名',
  `invoke_target` varchar(500) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL COMMENT '调用目标字符串',
  `job_message` varchar(500) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT NULL COMMENT '日志信息',
  `status` char(1) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT '0' COMMENT '执行状态（0正常 1失败）',
  `exception_info` varchar(2000) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT '' COMMENT '异常信息',
  `start_time` datetime NULL DEFAULT NULL COMMENT '执行开始时间',
  `end_time` datetime NULL DEFAULT NULL COMMENT '执行结束时间',
  `create_time` datetime NULL DEFAULT NULL COMMENT '创建时间',
  PRIMARY KEY (`job_log_id`) USING BTREE
) ENGINE = InnoDB AUTO_INCREMENT = 354 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_0900_ai_ci COMMENT = '定时任务调度日志表' ROW_FORMAT = DYNAMIC;

-- ----------------------------
-- Table structure for sys_logininfor
-- ----------------------------
DROP TABLE IF EXISTS `sys_logininfor`;
CREATE TABLE `sys_logininfor`  (
  `info_id` bigint NOT NULL AUTO_INCREMENT COMMENT '访问ID',
  `user_name` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT '' COMMENT '用户账号',
  `ipaddr` varchar(128) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT '' COMMENT '登录IP地址',
  `login_location` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT '' COMMENT '登录地点',
  `browser` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT '' COMMENT '浏览器类型',
  `os` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT '' COMMENT '操作系统',
  `status` char(1) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT '0' COMMENT '登录状态（0成功 1失败）',
  `msg` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT '' COMMENT '提示消息',
  `login_time` datetime NULL DEFAULT NULL COMMENT '访问时间',
  PRIMARY KEY (`info_id`) USING BTREE,
  INDEX `idx_sys_logininfor_s`(`status` ASC) USING BTREE,
  INDEX `idx_sys_logininfor_lt`(`login_time` ASC) USING BTREE
) ENGINE = InnoDB AUTO_INCREMENT = 446 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_0900_ai_ci COMMENT = '系统访问记录' ROW_FORMAT = DYNAMIC;

-- ----------------------------
-- Table structure for sys_menu
-- ----------------------------
DROP TABLE IF EXISTS `sys_menu`;
CREATE TABLE `sys_menu`  (
  `menu_id` bigint NOT NULL AUTO_INCREMENT COMMENT '菜单ID',
  `menu_name` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL COMMENT '菜单名称',
  `parent_id` bigint NULL DEFAULT 0 COMMENT '父菜单ID',
  `order_num` int NULL DEFAULT 0 COMMENT '显示顺序',
  `path` varchar(200) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT '' COMMENT '路由地址',
  `component` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT NULL COMMENT '组件路径',
  `query` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT NULL COMMENT '路由参数',
  `route_name` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT '' COMMENT '路由名称',
  `is_frame` int NULL DEFAULT 1 COMMENT '是否为外链（0是 1否）',
  `is_cache` int NULL DEFAULT 0 COMMENT '是否缓存（0缓存 1不缓存）',
  `menu_type` char(1) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT '' COMMENT '菜单类型（M目录 C菜单 F按钮）',
  `visible` char(1) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT '0' COMMENT '菜单状态（0显示 1隐藏）',
  `status` char(1) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT '0' COMMENT '菜单状态（0正常 1停用）',
  `perms` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT NULL COMMENT '权限标识',
  `icon` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT '#' COMMENT '菜单图标',
  `create_by` varchar(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT '' COMMENT '创建者',
  `create_time` datetime NULL DEFAULT NULL COMMENT '创建时间',
  `update_by` varchar(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT '' COMMENT '更新者',
  `update_time` datetime NULL DEFAULT NULL COMMENT '更新时间',
  `remark` varchar(500) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT '' COMMENT '备注',
  PRIMARY KEY (`menu_id`) USING BTREE
) ENGINE = InnoDB AUTO_INCREMENT = 2096 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_0900_ai_ci COMMENT = '菜单权限表' ROW_FORMAT = DYNAMIC;

-- ----------------------------
-- Table structure for sys_notice
-- ----------------------------
DROP TABLE IF EXISTS `sys_notice`;
CREATE TABLE `sys_notice`  (
  `notice_id` int NOT NULL AUTO_INCREMENT COMMENT '公告ID',
  `notice_title` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL COMMENT '公告标题',
  `notice_type` char(1) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL COMMENT '公告类型（1通知 2公告）',
  `notice_content` longblob NULL COMMENT '公告内容',
  `status` char(1) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT '0' COMMENT '公告状态（0正常 1关闭）',
  `create_by` varchar(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT '' COMMENT '创建者',
  `create_time` datetime NULL DEFAULT NULL COMMENT '创建时间',
  `update_by` varchar(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT '' COMMENT '更新者',
  `update_time` datetime NULL DEFAULT NULL COMMENT '更新时间',
  `remark` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT NULL COMMENT '备注',
  PRIMARY KEY (`notice_id`) USING BTREE
) ENGINE = InnoDB AUTO_INCREMENT = 10 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_0900_ai_ci COMMENT = '通知公告表' ROW_FORMAT = DYNAMIC;

-- ----------------------------
-- Table structure for sys_notice_read
-- ----------------------------
DROP TABLE IF EXISTS `sys_notice_read`;
CREATE TABLE `sys_notice_read`  (
  `read_id` bigint NOT NULL AUTO_INCREMENT COMMENT '已读主键',
  `notice_id` int NOT NULL COMMENT '公告id',
  `user_id` bigint NOT NULL COMMENT '用户id',
  `read_time` datetime NOT NULL COMMENT '阅读时间',
  PRIMARY KEY (`read_id`) USING BTREE,
  UNIQUE INDEX `uk_user_notice`(`user_id` ASC, `notice_id` ASC) USING BTREE COMMENT '同一用户同一公告只记录一次'
) ENGINE = InnoDB AUTO_INCREMENT = 10 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_0900_ai_ci COMMENT = '公告已读记录表' ROW_FORMAT = DYNAMIC;

-- ----------------------------
-- Table structure for sys_oper_log
-- ----------------------------
DROP TABLE IF EXISTS `sys_oper_log`;
CREATE TABLE `sys_oper_log`  (
  `oper_id` bigint NOT NULL AUTO_INCREMENT COMMENT '日志主键',
  `title` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT '' COMMENT '模块标题',
  `business_type` int NULL DEFAULT 0 COMMENT '业务类型（0其它 1新增 2修改 3删除）',
  `method` varchar(200) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT '' COMMENT '方法名称',
  `request_method` varchar(10) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT '' COMMENT '请求方式',
  `operator_type` int NULL DEFAULT 0 COMMENT '操作类别（0其它 1后台用户 2手机端用户）',
  `oper_name` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT '' COMMENT '操作人员',
  `dept_name` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT '' COMMENT '部门名称',
  `oper_url` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT '' COMMENT '请求URL',
  `oper_ip` varchar(128) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT '' COMMENT '主机地址',
  `oper_location` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT '' COMMENT '操作地点',
  `oper_param` varchar(2000) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT '' COMMENT '请求参数',
  `json_result` varchar(2000) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT '' COMMENT '返回参数',
  `status` int NULL DEFAULT 0 COMMENT '操作状态（0正常 1异常）',
  `error_msg` varchar(2000) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT '' COMMENT '错误消息',
  `oper_time` datetime NULL DEFAULT NULL COMMENT '操作时间',
  `cost_time` bigint NULL DEFAULT 0 COMMENT '消耗时间',
  PRIMARY KEY (`oper_id`) USING BTREE,
  INDEX `idx_sys_oper_log_bt`(`business_type` ASC) USING BTREE,
  INDEX `idx_sys_oper_log_s`(`status` ASC) USING BTREE,
  INDEX `idx_sys_oper_log_ot`(`oper_time` ASC) USING BTREE
) ENGINE = InnoDB AUTO_INCREMENT = 702 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_0900_ai_ci COMMENT = '操作日志记录' ROW_FORMAT = DYNAMIC;

-- ----------------------------
-- Table structure for sys_post
-- ----------------------------
DROP TABLE IF EXISTS `sys_post`;
CREATE TABLE `sys_post`  (
  `post_id` bigint NOT NULL AUTO_INCREMENT COMMENT '岗位ID',
  `post_code` varchar(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL COMMENT '岗位编码',
  `post_name` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL COMMENT '岗位名称',
  `post_sort` int NOT NULL COMMENT '显示顺序',
  `status` char(1) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL COMMENT '状态（0正常 1停用）',
  `create_by` varchar(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT '' COMMENT '创建者',
  `create_time` datetime NULL DEFAULT NULL COMMENT '创建时间',
  `update_by` varchar(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT '' COMMENT '更新者',
  `update_time` datetime NULL DEFAULT NULL COMMENT '更新时间',
  `remark` varchar(500) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT NULL COMMENT '备注',
  PRIMARY KEY (`post_id`) USING BTREE
) ENGINE = InnoDB AUTO_INCREMENT = 8 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_0900_ai_ci COMMENT = '岗位信息表' ROW_FORMAT = DYNAMIC;

-- ----------------------------
-- Table structure for sys_role
-- ----------------------------
DROP TABLE IF EXISTS `sys_role`;
CREATE TABLE `sys_role`  (
  `role_id` bigint NOT NULL AUTO_INCREMENT COMMENT '角色ID',
  `role_name` varchar(30) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL COMMENT '角色名称',
  `role_key` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL COMMENT '角色权限字符串',
  `role_sort` int NOT NULL COMMENT '显示顺序',
  `data_scope` char(1) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT '1' COMMENT '数据范围（1：全部数据权限 2：自定数据权限 3：本部门数据权限 4：本部门及以下数据权限）',
  `menu_check_strictly` tinyint(1) NULL DEFAULT 1 COMMENT '菜单树选择项是否关联显示',
  `dept_check_strictly` tinyint(1) NULL DEFAULT 1 COMMENT '部门树选择项是否关联显示',
  `status` char(1) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL COMMENT '角色状态（0正常 1停用）',
  `del_flag` char(1) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT '0' COMMENT '删除标志（0代表存在 2代表删除）',
  `create_by` varchar(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT '' COMMENT '创建者',
  `create_time` datetime NULL DEFAULT NULL COMMENT '创建时间',
  `update_by` varchar(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT '' COMMENT '更新者',
  `update_time` datetime NULL DEFAULT NULL COMMENT '更新时间',
  `remark` varchar(500) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT NULL COMMENT '备注',
  PRIMARY KEY (`role_id`) USING BTREE
) ENGINE = InnoDB AUTO_INCREMENT = 107 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_0900_ai_ci COMMENT = '角色信息表' ROW_FORMAT = DYNAMIC;

-- ----------------------------
-- Table structure for sys_role_dept
-- ----------------------------
DROP TABLE IF EXISTS `sys_role_dept`;
CREATE TABLE `sys_role_dept`  (
  `role_id` bigint NOT NULL COMMENT '角色ID',
  `dept_id` bigint NOT NULL COMMENT '部门ID',
  PRIMARY KEY (`role_id`, `dept_id`) USING BTREE
) ENGINE = InnoDB CHARACTER SET = utf8mb4 COLLATE = utf8mb4_0900_ai_ci COMMENT = '角色和部门关联表' ROW_FORMAT = DYNAMIC;

-- ----------------------------
-- Table structure for sys_role_menu
-- ----------------------------
DROP TABLE IF EXISTS `sys_role_menu`;
CREATE TABLE `sys_role_menu`  (
  `role_id` bigint NOT NULL COMMENT '角色ID',
  `menu_id` bigint NOT NULL COMMENT '菜单ID',
  PRIMARY KEY (`role_id`, `menu_id`) USING BTREE
) ENGINE = InnoDB CHARACTER SET = utf8mb4 COLLATE = utf8mb4_0900_ai_ci COMMENT = '角色和菜单关联表' ROW_FORMAT = DYNAMIC;

-- ----------------------------
-- Table structure for sys_user
-- ----------------------------
DROP TABLE IF EXISTS `sys_user`;
CREATE TABLE `sys_user`  (
  `user_id` bigint NOT NULL AUTO_INCREMENT COMMENT '用户ID',
  `dept_id` bigint NULL DEFAULT NULL COMMENT '部门ID',
  `user_name` varchar(30) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL COMMENT '用户账号',
  `nick_name` varchar(30) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL COMMENT '用户昵称',
  `user_type` varchar(2) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT '00' COMMENT '用户类型（00系统用户）',
  `email` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT '' COMMENT '用户邮箱',
  `phonenumber` varchar(11) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT '' COMMENT '手机号码',
  `sex` char(1) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT '0' COMMENT '用户性别（0男 1女 2未知）',
  `avatar` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT '' COMMENT '头像地址',
  `password` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT '' COMMENT '密码',
  `status` char(1) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT '0' COMMENT '账号状态（0正常 1停用）',
  `del_flag` char(1) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT '0' COMMENT '删除标志（0代表存在 2代表删除）',
  `login_ip` varchar(128) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT '' COMMENT '最后登录IP',
  `login_date` datetime NULL DEFAULT NULL COMMENT '最后登录时间',
  `pwd_update_date` datetime NULL DEFAULT NULL COMMENT '密码最后更新时间',
  `create_by` varchar(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT '' COMMENT '创建者',
  `create_time` datetime NULL DEFAULT NULL COMMENT '创建时间',
  `update_by` varchar(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT '' COMMENT '更新者',
  `update_time` datetime NULL DEFAULT NULL COMMENT '更新时间',
  `remark` varchar(500) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT NULL COMMENT '备注',
  PRIMARY KEY (`user_id`) USING BTREE
) ENGINE = InnoDB AUTO_INCREMENT = 129 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_0900_ai_ci COMMENT = '用户信息表' ROW_FORMAT = DYNAMIC;

-- ----------------------------
-- Table structure for sys_user_column_config
-- ----------------------------
DROP TABLE IF EXISTS `sys_user_column_config`;
CREATE TABLE `sys_user_column_config`  (
  `id` bigint NOT NULL AUTO_INCREMENT COMMENT '主键ID',
  `user_id` bigint NOT NULL COMMENT '用户ID',
  `user_name` varchar(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT NULL COMMENT '用户账号',
  `page_key` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL COMMENT '页面标识',
  `config_json` text CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL COMMENT '列配置JSON',
  `create_by` varchar(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT '',
  `create_time` datetime NULL DEFAULT NULL,
  `update_by` varchar(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT '',
  `update_time` datetime NULL DEFAULT NULL,
  PRIMARY KEY (`id`) USING BTREE,
  UNIQUE INDEX `uk_user_page`(`user_id` ASC, `page_key` ASC) USING BTREE,
  INDEX `idx_page_key`(`page_key` ASC) USING BTREE
) ENGINE = InnoDB AUTO_INCREMENT = 9 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_0900_ai_ci COMMENT = '用户列配置表' ROW_FORMAT = DYNAMIC;

-- ----------------------------
-- Table structure for sys_user_post
-- ----------------------------
DROP TABLE IF EXISTS `sys_user_post`;
CREATE TABLE `sys_user_post`  (
  `user_id` bigint NOT NULL COMMENT '用户ID',
  `post_id` bigint NOT NULL COMMENT '岗位ID',
  PRIMARY KEY (`user_id`, `post_id`) USING BTREE
) ENGINE = InnoDB CHARACTER SET = utf8mb4 COLLATE = utf8mb4_0900_ai_ci COMMENT = '用户与岗位关联表' ROW_FORMAT = DYNAMIC;

-- ----------------------------
-- Table structure for sys_user_role
-- ----------------------------
DROP TABLE IF EXISTS `sys_user_role`;
CREATE TABLE `sys_user_role`  (
  `user_id` bigint NOT NULL COMMENT '用户ID',
  `role_id` bigint NOT NULL COMMENT '角色ID',
  PRIMARY KEY (`user_id`, `role_id`) USING BTREE
) ENGINE = InnoDB CHARACTER SET = utf8mb4 COLLATE = utf8mb4_0900_ai_ci COMMENT = '用户和角色关联表' ROW_FORMAT = DYNAMIC;

-- ----------------------------
-- Table structure for warehouse
-- ----------------------------
DROP TABLE IF EXISTS `warehouse`;
CREATE TABLE `warehouse`  (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `wid` int NOT NULL COMMENT '领星仓库ID',
  `name` varchar(200) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT '' COMMENT '仓库名称',
  `type` int NULL DEFAULT 0 COMMENT '仓库类型',
  `sub_type` int NULL DEFAULT 0 COMMENT '仓库子类型',
  `is_delete` int NULL DEFAULT 0 COMMENT '删除标记',
  `country_code` varchar(10) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT '' COMMENT '国家代码',
  `wp_id` int NULL DEFAULT 0 COMMENT '仓储服务商ID',
  `wp_name` varchar(200) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT '' COMMENT '仓储服务商名称',
  `t_warehouse_name` varchar(200) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT '' COMMENT '第三方仓库名称',
  `t_warehouse_code` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT '' COMMENT '第三方仓库编码',
  `t_country_area_name` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT '' COMMENT '第三方国家地区名称',
  `t_status` int NULL DEFAULT 0 COMMENT '第三方状态',
  `raw_json` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL COMMENT '原始JSON数据',
  `create_time` datetime NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `update_time` datetime NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  PRIMARY KEY (`id`) USING BTREE,
  UNIQUE INDEX `uk_wid`(`wid` ASC) USING BTREE
) ENGINE = InnoDB AUTO_INCREMENT = 40 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_unicode_ci COMMENT = '领星仓库基础表' ROW_FORMAT = DYNAMIC;

-- ----------------------------
-- Table structure for warehouse_inventory_detail
-- ----------------------------
DROP TABLE IF EXISTS `warehouse_inventory_detail`;
CREATE TABLE `warehouse_inventory_detail`  (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `wid` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL COMMENT '仓库id',
  `product_id` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL COMMENT '本地产品id',
  `sku` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL COMMENT 'SKU',
  `seller_id` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL COMMENT '店铺id',
  `fnsku` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL COMMENT 'FNSKU',
  `product_total` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL COMMENT '实际库存总量(可用量+次品量+待检待上架量+锁定量)',
  `product_valid_num` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL COMMENT '可用量',
  `product_bad_num` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL COMMENT '次品量',
  `product_qc_num` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL COMMENT '待检待上架量',
  `product_lock_num` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL COMMENT '锁定量',
  `good_lock_num` int NULL DEFAULT 0 COMMENT '良品锁定数',
  `bad_lock_num` int NULL DEFAULT 0 COMMENT '不良品锁定数',
  `stock_cost_total` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL COMMENT '库存成本',
  `quantity_receive` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL COMMENT '待到货量',
  `stock_cost` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL COMMENT '单位库存成本',
  `product_onway` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL COMMENT '调拨在途',
  `transit_head_cost` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL COMMENT '调拨在途头程成本',
  `average_age` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL COMMENT '平均库龄',
  `expect_valid_num` int NULL DEFAULT 0 COMMENT '海外仓预期有效数',
  `expect_pending_num` decimal(16, 4) NULL DEFAULT 0.0000 COMMENT '海外仓预期待处理数',
  `available_inventory_box_qty` int NULL DEFAULT 0 COMMENT '海外仓可用箱库存',
  `purchase_price` decimal(16, 4) NULL DEFAULT 0.0000 COMMENT '采购单价',
  `price` decimal(16, 4) NULL DEFAULT 0.0000 COMMENT '单位费用',
  `head_stock_price` decimal(16, 4) NULL DEFAULT 0.0000 COMMENT '单位头程',
  `stock_price` decimal(16, 4) NULL DEFAULT 0.0000 COMMENT '单位库存成本',
  `third_inventory_json` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL COMMENT '海外仓第三方库存信息(JSON)',
  `stock_age_list_json` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL COMMENT '库龄信息(JSON)',
  `create_time` datetime NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `update_time` datetime NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  PRIMARY KEY (`id`) USING BTREE,
  UNIQUE INDEX `uk_wid_product`(`wid` ASC, `product_id` ASC) USING BTREE,
  INDEX `idx_sku`(`sku` ASC) USING BTREE,
  INDEX `idx_wid`(`wid` ASC) USING BTREE,
  INDEX `idx_wid_sku`(`wid` ASC, `sku` ASC) USING BTREE
) ENGINE = InnoDB AUTO_INCREMENT = 57302 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_unicode_ci COMMENT = '领星仓库库存明细表' ROW_FORMAT = DYNAMIC;

-- ----------------------------
-- Table structure for warehouse_statement
-- ----------------------------
DROP TABLE IF EXISTS `warehouse_statement`;
CREATE TABLE `warehouse_statement`  (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `wid` int NULL DEFAULT 0 COMMENT '仓库id',
  `ware_house_name` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT '' COMMENT '仓库名称',
  `sku` varchar(200) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT '' COMMENT 'SKU',
  `opt_time` datetime NULL DEFAULT NULL COMMENT '操作时间',
  `type` int NULL DEFAULT 0 COMMENT '流水类型',
  `upload_time` datetime NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`) USING BTREE,
  INDEX `idx_sku`(`sku` ASC) USING BTREE,
  INDEX `idx_wid`(`wid` ASC) USING BTREE,
  INDEX `idx_opt_time`(`opt_time` ASC) USING BTREE,
  INDEX `idx_type_opt_time`(`type` ASC, `opt_time` ASC) USING BTREE,
  INDEX `idx_sku_wid_type`(`sku` ASC, `wid` ASC, `type` ASC) USING BTREE
) ENGINE = InnoDB AUTO_INCREMENT = 1123 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_unicode_ci COMMENT = '领星仓库库存流水表' ROW_FORMAT = DYNAMIC;

SET FOREIGN_KEY_CHECKS = 1;
