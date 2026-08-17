-- 月度库存数据表：部署机完整SQL
-- 生成日期：2026-08-17
-- 执行前提：date-project 与 jmh_data_platform 两个数据库均已存在。
-- 可重复执行；不包含TRUNCATE、DELETE或DROP，不会清空现有数据。
-- 数据库边界：
--   date-project：Python ODS/DWD/DWS数据表、Python任务元数据
--   jmh_data_platform：Java ERP菜单、角色权限、Quartz任务

SET NAMES utf8mb4;

-- =====================================================================
-- 第一部分：Python数据库
-- =====================================================================
USE `date-project`;

-- Python任务元数据表（已有则保持原结构和数据）
CREATE TABLE IF NOT EXISTS `scheduler_task` (
    `task_code` VARCHAR(80) NOT NULL COMMENT '任务编码',
    `task_name` VARCHAR(200) NOT NULL COMMENT '任务名称',
    `cron_expression` VARCHAR(100) NOT NULL COMMENT 'Cron表达式',
    `enabled` TINYINT NOT NULL DEFAULT 1 COMMENT '是否启用',
    `description` VARCHAR(1000) NULL COMMENT '说明',
    `last_run_at` DATETIME NULL COMMENT '最近运行时间',
    `next_run_at` DATETIME NULL COMMENT '下次运行时间',
    `create_time` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    `update_time` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '修改时间',
    PRIMARY KEY (`task_code`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='内部定时任务定义表';

CREATE TABLE IF NOT EXISTS `scheduler_task_run` (
    `run_id` VARCHAR(64) NOT NULL COMMENT '运行ID',
    `task_code` VARCHAR(80) NOT NULL COMMENT '任务编码',
    `status` VARCHAR(20) NOT NULL COMMENT '状态',
    `stat_month` CHAR(7) NULL COMMENT '统计月份',
    `trigger_type` VARCHAR(40) NOT NULL COMMENT '触发类型：scheduler/manual',
    `source_rows` INT NOT NULL DEFAULT 0 COMMENT '源行数',
    `sync_batch_id` VARCHAR(64) NULL COMMENT 'ODS同步批次ID',
    `extract_rows` INT NOT NULL DEFAULT 0 COMMENT '领星抽取行数',
    `ods_rows` INT NOT NULL DEFAULT 0 COMMENT 'ODS写入行数',
    `inserted_rows` INT NOT NULL DEFAULT 0 COMMENT '插入行数',
    `updated_rows` INT NOT NULL DEFAULT 0 COMMENT '更新行数',
    `deleted_rows` INT NOT NULL DEFAULT 0 COMMENT '整月替换删除行数',
    `skipped_rows` INT NOT NULL DEFAULT 0 COMMENT '无效或重复跳过行数',
    `amz_ranking_rows` INT NOT NULL DEFAULT 0 COMMENT 'AMZ排名行数',
    `combined_ranking_rows` INT NOT NULL DEFAULT 0 COMMENT '综合排名行数',
    `etl_stage` VARCHAR(32) NULL COMMENT '当前或失败阶段',
    `error_message` TEXT NULL COMMENT '错误摘要',
    `request_id` VARCHAR(128) NULL COMMENT '请求ID',
    `started_at` DATETIME NULL COMMENT '开始时间',
    `completed_at` DATETIME NULL COMMENT '完成时间',
    PRIMARY KEY (`run_id`),
    KEY `idx_scheduler_run_task` (`task_code`,`started_at`),
    KEY `idx_scheduler_run_status` (`status`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='内部定时任务运行记录表';

-- 目标库：Date-Project（Python 数据库）。不要在 jmh_data_platform 执行。
-- 三张表只保存领星库存报表源数据，暂不包含 DWD/DWS 清洗统计逻辑。

CREATE TABLE IF NOT EXISTS `ods_lingxing_fba_monthly_inventory_detail` (
    `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '自增主键',
    `stat_month` CHAR(7) NOT NULL COMMENT '数据归属年月，格式YYYY-MM',
    `sync_batch_id` VARCHAR(64) NOT NULL COMMENT '本次同步批次ID',
    `query_start_date` VARCHAR(10) NOT NULL COMMENT '本次接口查询开始日期',
    `query_end_date` VARCHAR(10) NOT NULL COMMENT '本次接口查询结束日期',
    `request_scope_json` JSON NOT NULL COMMENT '本次请求的seller_id店铺范围（JSON）',
    `source_page` INT NOT NULL DEFAULT 1 COMMENT '接口来源页码',
    `source_offset` INT NOT NULL DEFAULT 0 COMMENT '接口来源偏移量',
    `source_row_no` INT NOT NULL DEFAULT 0 COMMENT '同步批次内原始行号',
    `api_code` VARCHAR(32) NULL COMMENT '接口返回状态码',
    `api_message` TEXT NULL COMMENT '接口返回提示信息',
    `api_trace_id` TEXT NULL COMMENT '接口请求链路ID',
    `api_request_id` TEXT NULL COMMENT '接口请求ID',
    `api_response_time` VARCHAR(64) NULL COMMENT '接口响应时间',
    `api_error_details` JSON NULL COMMENT '接口错误明细（JSON）',
    `api_total` BIGINT NULL COMMENT '接口返回总记录数',
    `api_start_date` VARCHAR(10) NULL COMMENT '接口返回的统计开始日期',
    `api_end_date` VARCHAR(10) NULL COMMENT '接口返回的统计结束日期',
    `api_day_interval` INT NULL COMMENT '接口返回的统计日期间隔天数',
    `api_amount_type` VARCHAR(32) NULL COMMENT '接口返回的计价类型：0成本计价，1固定值计价',
    `api_size` INT NULL COMMENT '接口返回的分页大小',
    `api_current` INT NULL COMMENT '接口返回的当前页码',
    `seller_id` TEXT NULL COMMENT '亚马逊店铺id',
    `sid` TEXT NULL COMMENT '店铺id',
    `wid` TEXT NULL COMMENT '系统仓库id',
    `ware_house_name` TEXT NULL COMMENT '仓库名称',
    `start_count` TEXT NULL COMMENT '期初库存-数量',
    `start_other_amount` TEXT NULL COMMENT '期初库存-商品成本 (精度：2位小数)',
    `start_logistic_amount` TEXT NULL COMMENT '期初库存-物流成本（精度：2位小数）',
    `shipments_count` TEXT NULL COMMENT '订单发货-数量',
    `shipments_other_amount` TEXT NULL COMMENT '订单发货-商品成本 (精度：2位小数)',
    `shipments_logistic_amount` TEXT NULL COMMENT '订单发货-物流成本 (精度：2位小数)',
    `whse_transfers_count` TEXT NULL COMMENT '库房转运-数量',
    `whse_transfers_other_amount` TEXT NULL COMMENT '库房转运-商品成本 (精度：2位小数)',
    `whse_transfers_logistic_amount` TEXT NULL COMMENT '库房转运-物流成本 (精度：2位小数)',
    `disposed_count` TEXT NULL COMMENT '弃置-数量',
    `disposed_other_amount` TEXT NULL COMMENT '弃置-商品成本 (精度：2位小数)',
    `disposed_logistic_amount` TEXT NULL COMMENT '弃置-物流成本 (精度：2位小数)',
    `found_count` TEXT NULL COMMENT '已找到-数量',
    `found_other_amount` TEXT NULL COMMENT '已找到-商品成本 (精度：2位小数)',
    `found_logistic_amount` TEXT NULL COMMENT '已找到-物流成本 (精度：2位小数)',
    `lost_count` TEXT NULL COMMENT '丢失-数量',
    `lost_other_amount` TEXT NULL COMMENT '丢失-商品成本 (精度：2位小数)',
    `lost_logistic_amount` TEXT NULL COMMENT '丢失-物流成本 (精度：2位小数)',
    `other_events_count` TEXT NULL COMMENT '其他-数量',
    `other_events_other_amount` TEXT NULL COMMENT '其他-商品成本 (精度：2位小数)',
    `other_events_logistic_amount` TEXT NULL COMMENT '其他-物流成本 (精度：2位小数)',
    `receipts_count` TEXT NULL COMMENT '货件补货-数量',
    `receipts_other_amount` TEXT NULL COMMENT '货件补货-商品成本 (精度：2位小数)',
    `receipts_logistic_amount` TEXT NULL COMMENT '货件补货-物流成本 (精度：2位小数)',
    `customer_returns_count` TEXT NULL COMMENT '买家退货-数量',
    `customer_returns_other_amount` TEXT NULL COMMENT '买家退货-商品成本 (精度：2位小数)',
    `customer_returns_logistic_amount` TEXT NULL COMMENT '买家退货-物流成本 (精度：2位小数)',
    `vendor_returns_count` TEXT NULL COMMENT '库存移除-数量',
    `vendor_returns_other_amount` TEXT NULL COMMENT '库存移除-商品成本 (精度：2位小数)',
    `vendor_returns_logistic_amount` TEXT NULL COMMENT '库存移除-物流成本 (精度：2位小数)',
    `difference_count` TEXT NULL COMMENT '库存差异-数量',
    `difference_other_amount` TEXT NULL COMMENT '库存差异-商品成本 (精度：2位小数)',
    `difference_logistic_amount` TEXT NULL COMMENT '库存差异-物流成本 (精度：2位小数)',
    `end_count` TEXT NULL COMMENT '期末库存-数量',
    `end_other_amount` TEXT NULL COMMENT '期末库存-商品成本 (精度：2位小数)',
    `end_logistic_amount` TEXT NULL COMMENT '期末库存-物流成本 (精度：2位小数)',
    `damaged_count` TEXT NULL COMMENT '残损-数量',
    `damaged_other_amount` TEXT NULL COMMENT '残损-商品成本 (精度：2位小数)',
    `damaged_logistic_amount` TEXT NULL COMMENT '残损-物流成本 (精度：2位小数)',
    `partition_index` TEXT NULL COMMENT '分区索引',
    `end_on_way_count` TEXT NULL COMMENT '期末在途-数量',
    `end_on_way_other_amount` TEXT NULL COMMENT '期末在途-商品成本 (精度：2位小数)',
    `end_on_way_logistic_amount` TEXT NULL COMMENT '期末在途-物流成本 (精度：2位小数)',
    `category_count` TEXT NULL COMMENT '商品种类',
    `parent_node` TEXT NULL COMMENT '是否父节点',
    `inventory_turnover_rate` TEXT NULL COMMENT '库存周转率 (精度：2位小数)',
    `inventory_turnover_days` TEXT NULL COMMENT '库存周转天数 (精度：2位小数)',
    `start_total_amount` TEXT NULL COMMENT '期初库存-总成本 (精度：2位小数)',
    `shipments_total_amount` TEXT NULL COMMENT '订单发货-总成本 (精度：2位小数)',
    `whse_transfers_total_amount` TEXT NULL COMMENT '库房转运-总成本 (精度：2位小数)',
    `disposed_total_amount` TEXT NULL COMMENT '弃置-总成本 (精度：2位小数)',
    `found_total_amount` TEXT NULL COMMENT '已找到-总成本 (精度：2位小数)',
    `lost_total_amount` TEXT NULL COMMENT '丢失-总成本 (精度：2位小数)',
    `other_events_total_amount` TEXT NULL COMMENT '其他-总成本 (精度：2位小数)',
    `receipts_total_amount` TEXT NULL COMMENT '货件补货-总成本 (精度：2位小数)',
    `customer_returns_total_amount` TEXT NULL COMMENT '订单退货-总成本 (精度：2位小数)',
    `vendor_returns_total_amount` TEXT NULL COMMENT '库存移除-总成本 (精度：2位小数)',
    `difference_total_amount` TEXT NULL COMMENT '库存差异-总成本 (精度：2位小数)',
    `end_total_amount` TEXT NULL COMMENT '期末库存-总成本 (精度：2位小数)',
    `damaged_total_amount` TEXT NULL COMMENT '已残损-总成本 (精度：2位小数)',
    `end_on_way_total_amount` TEXT NULL COMMENT '期末在途-总成本 (精度：2位小数)',
    `stock_to_use_rate` TEXT NULL COMMENT '存销比 (精度：2位小数)',
    `adjustments_count` TEXT NULL COMMENT '成本调整-数量',
    `adjustments_total_amount` TEXT NULL COMMENT '成本调整-总成本 (精度：2位小数)',
    `adjustments_logistic_amount` TEXT NULL COMMENT '成本调整-物流成本 (精度：2位小数)',
    `adjustments_other_amount` TEXT NULL COMMENT '成本调整-商品成本 (精度：2位小数)',
    `transferring_out_count` TEXT NULL COMMENT '移仓在途-数量',
    `transferring_out_total_amount` TEXT NULL COMMENT '移仓在途-总成本 (精度：2位小数)',
    `transferring_out_logistic_amount` TEXT NULL COMMENT '移仓在途-物流成本 (精度：2位小数)',
    `transferring_out_other_amount` TEXT NULL COMMENT '移仓在途-商品成本 (精度：2位小数)',
    `mid` TEXT NULL COMMENT '站点id',
    `parent_asin` TEXT NULL COMMENT '父Asin',
    `msku` TEXT NULL COMMENT '亚马逊卖家SKU（MSKU）',
    `asin` TEXT NULL COMMENT '亚马逊商品标识码（ASIN）',
    `disposition` TEXT NULL COMMENT '库存属性： sellable 可售 unsellable 不可售 all 全部',
    `country_code` TEXT NULL COMMENT '国家编码',
    `fnsku` TEXT NULL COMMENT '亚马逊配送网络SKU（FNSKU）',
    `product_id` TEXT NULL COMMENT '本地产品id',
    `local_sku` TEXT NULL COMMENT '本地产品sku',
    `local_name` TEXT NULL COMMENT '本地产品名称',
    `cid` TEXT NULL COMMENT '商品分类id',
    `product_category_name` TEXT NULL COMMENT '产品分类名',
    `bid` TEXT NULL COMMENT '品牌id',
    `brand_name` TEXT NULL COMMENT '品牌名称',
    `valuation_method` TEXT NULL COMMENT '计价方法： 1 先进先出 2 移动加权 3 月末加权',
    `child_data` JSON NULL COMMENT '返回字段与上级row_data一致',
    `raw_row_json` JSON NOT NULL COMMENT '接口返回的完整原始明细行（JSON），兼容新增字段',
    `pulled_at` DATETIME NOT NULL COMMENT '数据拉取时间',
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '记录创建时间',
    PRIMARY KEY (`id`),
    KEY `idx_stat_month` (`stat_month`),
    KEY `idx_sync_batch` (`sync_batch_id`),
    KEY `idx_fba_identity` (`stat_month`,`sid`(32),`wid`(32),`msku`(191))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='ODS-领星FBA月度库存报表明细原始数据';

CREATE TABLE IF NOT EXISTS `ods_lingxing_overseas_monthly_inventory_detail` (
    `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '自增主键',
    `stat_month` CHAR(7) NOT NULL COMMENT '数据归属年月，格式YYYY-MM',
    `sync_batch_id` VARCHAR(64) NOT NULL COMMENT '本次同步批次ID',
    `query_start_date` VARCHAR(10) NOT NULL COMMENT '本次接口查询开始日期',
    `query_end_date` VARCHAR(10) NOT NULL COMMENT '本次接口查询结束日期',
    `request_scope_json` JSON NOT NULL COMMENT '本次请求的sys_wid仓库范围（JSON）',
    `source_page` INT NOT NULL DEFAULT 1 COMMENT '接口来源页码',
    `source_offset` INT NOT NULL DEFAULT 0 COMMENT '接口来源偏移量',
    `source_row_no` INT NOT NULL DEFAULT 0 COMMENT '同步批次内原始行号',
    `api_code` VARCHAR(32) NULL COMMENT '接口返回状态码',
    `api_message` TEXT NULL COMMENT '接口返回提示信息',
    `api_trace_id` TEXT NULL COMMENT '接口请求链路ID',
    `api_request_id` TEXT NULL COMMENT '接口请求ID',
    `api_response_time` VARCHAR(64) NULL COMMENT '接口响应时间',
    `api_error_details` JSON NULL COMMENT '接口错误明细（JSON）',
    `api_total` BIGINT NULL COMMENT '接口返回总记录数',
    `api_start_date` VARCHAR(10) NULL COMMENT '接口返回的统计开始日期',
    `api_end_date` VARCHAR(10) NULL COMMENT '接口返回的统计结束日期',
    `api_day_interval` INT NULL COMMENT '接口返回的统计日期间隔天数',
    `api_amount_type` VARCHAR(32) NULL COMMENT '接口返回的计价类型：0成本计价，1固定值计价',
    `api_size` INT NULL COMMENT '接口返回的分页大小',
    `api_current` INT NULL COMMENT '接口返回的当前页码',
    `sys_wid` TEXT NULL COMMENT '仓库id',
    `ware_house_name` TEXT NULL COMMENT '仓库名称',
    `seller_name` TEXT NULL COMMENT '店铺名称',
    `product_name` TEXT NULL COMMENT '商品名称',
    `product_type` TEXT NULL COMMENT '产品类型:普通产品 组合产品 辅料 捆绑产品',
    `sku` TEXT NULL COMMENT '商品SKU',
    `fnsku` TEXT NULL COMMENT '亚马逊配送网络SKU（FNSKU）',
    `spu` TEXT NULL COMMENT '标准产品单元（SPU）',
    `spu_name` TEXT NULL COMMENT '款名',
    `api_sku` TEXT NULL COMMENT '第三方SKU',
    `brand` TEXT NULL COMMENT '品牌名称',
    `category1` TEXT NULL COMMENT '一级类目-名称',
    `category2` TEXT NULL COMMENT '二级类目-名称',
    `category3` TEXT NULL COMMENT '三级类目-名称',
    `attribute_text` TEXT NULL COMMENT '库存属性: 全部 可售 待检 不可售',
    `global_tags` JSON NULL COMMENT '产品标签列表',
    `sku_attribute` JSON NULL COMMENT '产品属性',
    `allocation_in_cost` TEXT NULL COMMENT '调拨入库-成本（精度：2位小数点）',
    `allocation_in_count` TEXT NULL COMMENT '调拨入库-数量',
    `allocation_in_transit_cost` TEXT NULL COMMENT '期末在途-成本（精度：2位小数点）',
    `allocation_in_transit_count` TEXT NULL COMMENT '期末在途-数量',
    `allocation_out_cost` TEXT NULL COMMENT '调拨出库-成本（精度：2位小数点）',
    `allocation_out_count` TEXT NULL COMMENT '调拨出库-数量',
    `change_of_standard_in_cost` TEXT NULL COMMENT '换标入库-成本（精度：2位小数点）',
    `change_of_standard_in_count` TEXT NULL COMMENT '换标入库-数量',
    `change_of_standard_out_cost` TEXT NULL COMMENT '换标出库-成本（精度：2位小数点）',
    `change_of_standard_out_count` TEXT NULL COMMENT '换标出库-数量',
    `cost_adjustment` TEXT NULL COMMENT '成本调整（精度：2位小数点）',
    `day_early_cost` TEXT NULL COMMENT '期初库存-成本（精度：2位小数点）',
    `day_early_count` TEXT NULL COMMENT '期初库存-数量',
    `day_end_cost` TEXT NULL COMMENT '期末库存-成本（精度：2位小数点）',
    `day_end_count` TEXT NULL COMMENT '期末库存-数量',
    `fba_out_cost` TEXT NULL COMMENT 'fba出库-成本（精度：2位小数点）',
    `fba_out_count` TEXT NULL COMMENT 'fba出库-数量',
    `fbm_out_cost` TEXT NULL COMMENT 'fbm出库-成本（精度：2位小数点）',
    `fbm_out_count` TEXT NULL COMMENT 'fbm出库-数量',
    `inventory_deficit_out_cost` TEXT NULL COMMENT '盘亏出库-成本（精度：2位小数点）',
    `inventory_deficit_out_count` TEXT NULL COMMENT '盘亏出库-数量',
    `inventory_surplus_in_cost` TEXT NULL COMMENT '盘盈入库-成本（精度：2位小数点）',
    `inventory_surplus_in_count` TEXT NULL COMMENT '盘盈入库-数量',
    `other_in_cost` TEXT NULL COMMENT '其他入库-成本（精度：2位小数点）',
    `other_in_count` TEXT NULL COMMENT '其他入库-数量',
    `other_out_cost` TEXT NULL COMMENT '其他出库-成本（精度：2位小数点）',
    `other_out_count` TEXT NULL COMMENT '其他出库-数量',
    `outsourcing_in_cost` TEXT NULL COMMENT '委外入库-成本（精度：2位小数点）',
    `outsourcing_in_count` TEXT NULL COMMENT '委外入库-数量',
    `outsourcing_out_cost` TEXT NULL COMMENT '委外出库-成本（精度：2位小数点）',
    `outsourcing_out_count` TEXT NULL COMMENT '委外出库-数量',
    `processing_in_cost` TEXT NULL COMMENT '加工入库-成本（精度：2位小数点）',
    `processing_in_count` TEXT NULL COMMENT '加工入库-数量',
    `processing_out_cost` TEXT NULL COMMENT '加工出库-成本（精度：2位小数点）',
    `processing_out_count` TEXT NULL COMMENT '加工出库-数量',
    `purchase_in_cost` TEXT NULL COMMENT '采购入库-成本（精度：2位小数点）',
    `purchase_in_count` TEXT NULL COMMENT '采购入库-数量',
    `purchase_return_cost` TEXT NULL COMMENT '退货出库-成本（精度：2位小数点）',
    `purchase_return_count` TEXT NULL COMMENT '退货出库-数量',
    `remove_in_cost` TEXT NULL COMMENT '移除入库-成本（精度：2位小数点）',
    `remove_in_count` TEXT NULL COMMENT '移除入库-数量',
    `return_goods_in_cost` TEXT NULL COMMENT '退货入库-成本（精度：2位小数点）',
    `return_goods_in_count` TEXT NULL COMMENT '退货入库-数量',
    `split_in_cost` TEXT NULL COMMENT '拆分入库-成本（精度：2位小数点）',
    `split_in_count` TEXT NULL COMMENT '拆分入库-数量',
    `split_out_cost` TEXT NULL COMMENT '拆分出库-成本（精度：2位小数点）',
    `split_out_count` TEXT NULL COMMENT '拆分出库-数量',
    `wfs_out_cost` TEXT NULL COMMENT 'WFS出库-成本（精度：2位小数点）',
    `wfs_out_count` TEXT NULL COMMENT 'WFS出库-数量',
    `gifts_in_cost` TEXT NULL COMMENT '赠品入库-成本(精度：2位小数点)',
    `gifts_in_count` TEXT NULL COMMENT '赠品入库-数量',
    `rotation_day_cost` TEXT NULL COMMENT '周转天数-成本（精度：2位小数点）',
    `rotation_day_count` TEXT NULL COMMENT '周转天数-数量（精度：2位小数点）',
    `rotation_rate_count` TEXT NULL COMMENT '周转率-数量（精度：4位小数点）',
    `rotation_rate_cost` TEXT NULL COMMENT '周转率-成本（精度：4位小数点）',
    `sales_ratio_count` TEXT NULL COMMENT '存销比-数量（精度：4位小数点）',
    `sales_ratio_cost` TEXT NULL COMMENT '存销比-成本（精度：4位小数点）',
    `api_day_early_count` TEXT NULL COMMENT '第三方期初库存-数量',
    `api_day_end_count` TEXT NULL COMMENT '第三方期末库存-数量',
    `divergence_count` TEXT NULL COMMENT '库存差异（第三方期末库存 - 期末库存）',
    `child_list` JSON NULL COMMENT '子项，与外层列表字段一致-库存状态为全部时会有数据',
    `raw_row_json` JSON NOT NULL COMMENT '接口返回的完整原始明细行（JSON），兼容新增字段',
    `pulled_at` DATETIME NOT NULL COMMENT '数据拉取时间',
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '记录创建时间',
    PRIMARY KEY (`id`),
    KEY `idx_stat_month` (`stat_month`),
    KEY `idx_sync_batch` (`sync_batch_id`),
    KEY `idx_overseas_identity` (`stat_month`,`sys_wid`(32),`sku`(191))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='ODS-领星海外仓月度库存报表明细原始数据';

CREATE TABLE IF NOT EXISTS `ods_lingxing_local_monthly_inventory_detail` (
    `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '自增主键',
    `stat_month` CHAR(7) NOT NULL COMMENT '数据归属年月，格式YYYY-MM',
    `sync_batch_id` VARCHAR(64) NOT NULL COMMENT '本次同步批次ID',
    `query_start_date` VARCHAR(10) NOT NULL COMMENT '本次接口查询开始日期',
    `query_end_date` VARCHAR(10) NOT NULL COMMENT '本次接口查询结束日期',
    `request_scope_json` JSON NOT NULL COMMENT '本次请求的sys_wid仓库范围（JSON）',
    `source_page` INT NOT NULL DEFAULT 1 COMMENT '接口来源页码',
    `source_offset` INT NOT NULL DEFAULT 0 COMMENT '接口来源偏移量',
    `source_row_no` INT NOT NULL DEFAULT 0 COMMENT '同步批次内原始行号',
    `api_code` VARCHAR(32) NULL COMMENT '接口返回状态码',
    `api_message` TEXT NULL COMMENT '接口返回提示信息',
    `api_trace_id` TEXT NULL COMMENT '接口请求链路ID',
    `api_request_id` TEXT NULL COMMENT '接口请求ID',
    `api_response_time` VARCHAR(64) NULL COMMENT '接口响应时间',
    `api_error_details` JSON NULL COMMENT '接口错误明细（JSON）',
    `api_total` BIGINT NULL COMMENT '接口返回总记录数',
    `api_start_date` VARCHAR(10) NULL COMMENT '接口返回的统计开始日期',
    `api_end_date` VARCHAR(10) NULL COMMENT '接口返回的统计结束日期',
    `api_day_interval` INT NULL COMMENT '接口返回的统计日期间隔天数',
    `api_amount_type` VARCHAR(32) NULL COMMENT '接口返回的计价类型：0成本计价，1固定值计价',
    `api_size` INT NULL COMMENT '接口返回的分页大小',
    `api_current` INT NULL COMMENT '接口返回的当前页码',
    `sys_wid` TEXT NULL COMMENT '系统仓库ID',
    `ware_house_name` TEXT NULL COMMENT '仓库名称',
    `seller_name` TEXT NULL COMMENT '店铺名称',
    `product_name` TEXT NULL COMMENT '商品名称',
    `product_type` TEXT NULL COMMENT '产品类型:普通产品 组合产品 辅料 捆绑产品',
    `sku` TEXT NULL COMMENT '商品SKU',
    `fnsku` TEXT NULL COMMENT '亚马逊配送网络SKU（FNSKU）',
    `spu` TEXT NULL COMMENT '标准产品单元（SPU）',
    `spu_name` TEXT NULL COMMENT '款名',
    `brand` TEXT NULL COMMENT '品牌名称',
    `category1` TEXT NULL COMMENT '一级类目-名称',
    `category2` TEXT NULL COMMENT '二级类目-名称',
    `category3` TEXT NULL COMMENT '三级类目-名称',
    `attribute_text` TEXT NULL COMMENT '库存属性: 全部 可售 待检 不可售',
    `global_tags` JSON NULL COMMENT '产品标签列表',
    `sku_attribute` JSON NULL COMMENT '产品属性',
    `allocation_in_cost` TEXT NULL COMMENT '调拨入库-成本（精度：2位小数点）',
    `allocation_in_count` TEXT NULL COMMENT '调拨入库-数量',
    `allocation_in_transit_cost` TEXT NULL COMMENT '期末在途-成本（精度：2位小数点）',
    `allocation_in_transit_count` TEXT NULL COMMENT '期末在途-数量',
    `allocation_out_cost` TEXT NULL COMMENT '调拨出库-成本（精度：2位小数点）',
    `allocation_out_count` TEXT NULL COMMENT '调拨出库-数量',
    `change_of_standard_in_cost` TEXT NULL COMMENT '换标入库-成本（精度：2位小数点）',
    `change_of_standard_in_count` TEXT NULL COMMENT '换标入库-数量',
    `change_of_standard_out_cost` TEXT NULL COMMENT '换标出库-成本（精度：2位小数点）',
    `change_of_standard_out_count` TEXT NULL COMMENT '换标出库-数量',
    `cost_adjustment` TEXT NULL COMMENT '成本调整（精度：2位小数点）',
    `day_early_cost` TEXT NULL COMMENT '期初库存-成本（精度：2位小数点）',
    `day_early_count` TEXT NULL COMMENT '期初库存-数量',
    `day_end_cost` TEXT NULL COMMENT '期末库存-成本（精度：2位小数点）',
    `day_end_count` TEXT NULL COMMENT '期末库存-数量',
    `fba_out_cost` TEXT NULL COMMENT 'fba出库-成本（精度：2位小数点）',
    `fba_out_count` TEXT NULL COMMENT 'fba出库-数量',
    `fbm_out_cost` TEXT NULL COMMENT 'fbm出库-成本（精度：2位小数点）',
    `fbm_out_count` TEXT NULL COMMENT 'fbm出库-数量',
    `inventory_deficit_out_cost` TEXT NULL COMMENT '盘亏出库-成本（精度：2位小数点）',
    `inventory_deficit_out_count` TEXT NULL COMMENT '盘亏出库-数量',
    `inventory_surplus_in_cost` TEXT NULL COMMENT '盘盈入库-成本（精度：2位小数点）',
    `inventory_surplus_in_count` TEXT NULL COMMENT '盘盈入库-数量',
    `other_in_cost` TEXT NULL COMMENT '其他入库-成本（精度：2位小数点）',
    `other_in_count` TEXT NULL COMMENT '其他入库-数量',
    `other_out_cost` TEXT NULL COMMENT '其他出库-成本（精度：2位小数点）',
    `other_out_count` TEXT NULL COMMENT '其他出库-数量',
    `outsourcing_in_cost` TEXT NULL COMMENT '委外入库-成本（精度：2位小数点）',
    `outsourcing_in_count` TEXT NULL COMMENT '委外入库-数量',
    `outsourcing_out_cost` TEXT NULL COMMENT '委外出库-成本（精度：2位小数点）',
    `outsourcing_out_count` TEXT NULL COMMENT '委外出库-数量',
    `processing_in_cost` TEXT NULL COMMENT '加工入库-成本（精度：2位小数点）',
    `processing_in_count` TEXT NULL COMMENT '加工入库-数量',
    `processing_out_cost` TEXT NULL COMMENT '加工出库-成本（精度：2位小数点）',
    `processing_out_count` TEXT NULL COMMENT '加工出库-数量',
    `purchase_in_cost` TEXT NULL COMMENT '采购入库-成本（精度：2位小数点）',
    `purchase_in_count` TEXT NULL COMMENT '采购入库-数量',
    `purchase_return_cost` TEXT NULL COMMENT '退货出库-成本（精度：2位小数点）',
    `purchase_return_count` TEXT NULL COMMENT '退货出库-数量',
    `remove_in_cost` TEXT NULL COMMENT '移除入库-成本（精度：2位小数点）',
    `remove_in_count` TEXT NULL COMMENT '移除入库-数量',
    `return_goods_in_cost` TEXT NULL COMMENT '退货入库-成本（精度：2位小数点）',
    `return_goods_in_count` TEXT NULL COMMENT '退货入库-数量',
    `rotation_day_cost` TEXT NULL COMMENT '周转天数-成本（精度：2位小数点）',
    `rotation_day_count` TEXT NULL COMMENT '周转天数-数量（精度：2位小数点）',
    `split_in_cost` TEXT NULL COMMENT '拆分入库-成本（精度：2位小数点）',
    `split_in_count` TEXT NULL COMMENT '拆分入库-数量',
    `split_out_cost` TEXT NULL COMMENT '拆分出库-成本（精度：2位小数点）',
    `split_out_count` TEXT NULL COMMENT '拆分出库-数量',
    `wfs_out_cost` TEXT NULL COMMENT 'WFS出库-成本（精度：2位小数点）',
    `wfs_out_count` TEXT NULL COMMENT 'WFS出库-数量',
    `gifts_in_cost` TEXT NULL COMMENT '赠品入库-成本（精度：2位小数点）',
    `gifts_in_count` TEXT NULL COMMENT '赠品入库-数量',
    `rotation_rate_count` TEXT NULL COMMENT '周转率-数量（精度：4位小数点）',
    `rotation_rate_cost` TEXT NULL COMMENT '周转率-成本（精度：4位小数点）',
    `sales_ratio_count` TEXT NULL COMMENT '存销比-数量（精度：4位小数点）',
    `sales_ratio_cost` TEXT NULL COMMENT '存销比-成本（精度：4位小数点）',
    `child_list` JSON NULL COMMENT '子项，与外层列表字段一致-库存状态为全部时会有数据',
    `raw_row_json` JSON NOT NULL COMMENT '接口返回的完整原始明细行（JSON），兼容新增字段',
    `pulled_at` DATETIME NOT NULL COMMENT '数据拉取时间',
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '记录创建时间',
    PRIMARY KEY (`id`),
    KEY `idx_stat_month` (`stat_month`),
    KEY `idx_sync_batch` (`sync_batch_id`),
    KEY `idx_local_identity` (`stat_month`,`sys_wid`(32),`sku`(191))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='ODS-领星本地仓月度库存报表明细原始数据';

INSERT INTO `scheduler_task` (
    task_code, task_name, cron_expression, enabled, description
) VALUES (
    'monthly_inventory_report_source_sync',
    '领星月度库存报表三接口源数据同步',
    '0 0 6 1 * ?',
    1,
    '每月1日06:00拉取上一个完整自然月的FBA、海外仓、本地仓明细，并重建DWD与DWS库存报表'
)
ON DUPLICATE KEY UPDATE
    task_name = VALUES(task_name),
    cron_expression = VALUES(cron_expression),
    description = VALUES(description);

-- 目标库：Date-Project（Python 数据库）。不要在 jmh_data_platform 执行。
-- 月度库存报表清洗明细、分维度汇总和部门主表；所有表及字段均使用中文注释。

CREATE TABLE IF NOT EXISTS `dwd_inventory_report_fba_detail` (
    `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '自增主键',
    `stat_month` CHAR(7) NOT NULL COMMENT '数据归属年月，格式YYYY-MM',
    `source_id` BIGINT UNSIGNED NOT NULL COMMENT 'FBA库存ODS源表主键',
    `source_child_index` INT NOT NULL DEFAULT 0 COMMENT 'ODS子明细序号，非嵌套明细为0',
    `sync_batch_id` VARCHAR(64) NOT NULL COMMENT '源数据同步批次ID',
    `sid` VARCHAR(32) NULL COMMENT '领星店铺SID',
    `store_name` VARCHAR(255) NULL COMMENT 'ERP店铺名称',
    `group_code` VARCHAR(32) NULL COMMENT '库存归属组别',
    `department_code` VARCHAR(32) NULL COMMENT '汇总部门编码',
    `principal_name` VARCHAR(100) NOT NULL DEFAULT '未分配' COMMENT '负责人姓名',
    `principal_match_source` VARCHAR(32) NOT NULL DEFAULT 'UNMATCHED' COMMENT '负责人匹配来源',
    `ware_house_name` VARCHAR(255) NULL COMMENT '领星仓库名称',
    `msku` VARCHAR(255) NULL COMMENT '亚马逊卖家SKU（MSKU）',
    `asin` VARCHAR(64) NULL COMMENT '亚马逊商品标识码（ASIN）',
    `fnsku` VARCHAR(255) NULL COMMENT '亚马逊配送网络SKU（FNSKU）',
    `local_sku` VARCHAR(255) NULL COMMENT '本地商品SKU',
    `local_name` VARCHAR(1000) NULL COMMENT '本地商品名称',
    `country_code` VARCHAR(32) NULL COMMENT '国家或站点编码',
    `end_inventory_qty` DECIMAL(24,6) NOT NULL DEFAULT 0 COMMENT '期末库存含移仓数量',
    `end_inventory_total_cost` DECIMAL(24,6) NOT NULL DEFAULT 0 COMMENT '期末库存含移仓总成本',
    `end_in_transit_qty` DECIMAL(24,6) NOT NULL DEFAULT 0 COMMENT '期末在途数量',
    `end_in_transit_total_cost` DECIMAL(24,6) NOT NULL DEFAULT 0 COMMENT '期末在途总成本',
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '记录创建时间',
    PRIMARY KEY (`id`),
    UNIQUE KEY `uk_inventory_fba_month_source` (`stat_month`,`source_id`,`source_child_index`),
    KEY `idx_inventory_fba_month_department` (`stat_month`,`department_code`),
    KEY `idx_inventory_fba_month_owner` (`stat_month`,`principal_name`),
    KEY `idx_inventory_fba_month_sid` (`stat_month`,`sid`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='DWD-领星FBA月度库存报表清洗明细';

CREATE TABLE IF NOT EXISTS `dwd_inventory_report_overseas_detail` (
    `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '自增主键',
    `stat_month` CHAR(7) NOT NULL COMMENT '数据归属年月，格式YYYY-MM',
    `source_id` BIGINT UNSIGNED NOT NULL COMMENT '海外仓库存ODS源表主键',
    `source_child_index` INT NOT NULL DEFAULT 0 COMMENT 'ODS子明细序号，非嵌套明细为0',
    `sync_batch_id` VARCHAR(64) NOT NULL COMMENT '源数据同步批次ID',
    `sys_wid` VARCHAR(32) NULL COMMENT '领星系统仓库ID',
    `ware_house_name` VARCHAR(255) NULL COMMENT '领星仓库名称',
    `seller_name` VARCHAR(255) NULL COMMENT '店铺或卖家名称',
    `product_name` VARCHAR(1000) NULL COMMENT '商品名称',
    `sku` VARCHAR(255) NULL COMMENT '商品SKU',
    `fnsku` VARCHAR(255) NULL COMMENT '亚马逊配送网络SKU（FNSKU）',
    `spu` VARCHAR(255) NULL COMMENT '标准产品单元（SPU）',
    `api_sku` VARCHAR(255) NULL COMMENT '第三方库存SKU',
    `brand` VARCHAR(255) NULL COMMENT '商品品牌',
    `platform_code` VARCHAR(16) NOT NULL COMMENT '平台编码：AMZ或EBAY',
    `group_code` VARCHAR(32) NULL COMMENT '库存归属组别',
    `department_code` VARCHAR(32) NULL COMMENT '汇总部门编码',
    `principal_name` VARCHAR(100) NOT NULL DEFAULT '未分配' COMMENT '负责人姓名',
    `principal_match_source` VARCHAR(32) NOT NULL DEFAULT 'UNMATCHED' COMMENT '负责人匹配来源',
    `end_in_transit_qty` DECIMAL(24,6) NOT NULL DEFAULT 0 COMMENT '期末在途数量',
    `end_in_transit_total_cost` DECIMAL(24,6) NOT NULL DEFAULT 0 COMMENT '期末在途总成本',
    `end_inventory_qty` DECIMAL(24,6) NOT NULL DEFAULT 0 COMMENT '期末库存数量',
    `end_inventory_total_cost` DECIMAL(24,6) NOT NULL DEFAULT 0 COMMENT '期末库存总成本',
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '记录创建时间',
    PRIMARY KEY (`id`),
    UNIQUE KEY `uk_inventory_overseas_month_source` (`stat_month`,`source_id`,`source_child_index`),
    KEY `idx_inventory_overseas_month_department` (`stat_month`,`department_code`),
    KEY `idx_inventory_overseas_month_owner` (`stat_month`,`principal_name`),
    KEY `idx_inventory_overseas_month_wid` (`stat_month`,`sys_wid`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='DWD-领星海外仓月度库存报表清洗明细';

CREATE TABLE IF NOT EXISTS `dwd_inventory_report_local_detail` (
    `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '自增主键',
    `stat_month` CHAR(7) NOT NULL COMMENT '数据归属年月，格式YYYY-MM',
    `source_id` BIGINT UNSIGNED NOT NULL COMMENT '本地仓库存ODS源表主键',
    `source_child_index` INT NOT NULL DEFAULT 0 COMMENT 'ODS子明细序号，非嵌套明细为0',
    `sync_batch_id` VARCHAR(64) NOT NULL COMMENT '源数据同步批次ID',
    `sys_wid` VARCHAR(32) NULL COMMENT '领星系统仓库ID',
    `ware_house_name` VARCHAR(255) NULL COMMENT '领星仓库名称',
    `seller_name` VARCHAR(255) NULL COMMENT '店铺或卖家名称',
    `product_name` VARCHAR(1000) NULL COMMENT '商品名称',
    `sku` VARCHAR(255) NULL COMMENT '商品SKU',
    `fnsku` VARCHAR(255) NULL COMMENT '亚马逊配送网络SKU（FNSKU）',
    `spu` VARCHAR(255) NULL COMMENT '标准产品单元（SPU）',
    `brand` VARCHAR(255) NULL COMMENT '商品品牌',
    `platform_code` VARCHAR(16) NOT NULL COMMENT '平台编码：AMZ或EBAY',
    `group_code` VARCHAR(32) NULL COMMENT '库存归属组别',
    `department_code` VARCHAR(32) NULL COMMENT '汇总部门编码',
    `principal_name` VARCHAR(100) NOT NULL DEFAULT '未分配' COMMENT '负责人姓名',
    `principal_match_source` VARCHAR(32) NOT NULL DEFAULT 'UNMATCHED' COMMENT '负责人匹配来源',
    `end_in_transit_qty` DECIMAL(24,6) NOT NULL DEFAULT 0 COMMENT '期末在途数量',
    `end_in_transit_total_cost` DECIMAL(24,6) NOT NULL DEFAULT 0 COMMENT '期末在途总成本',
    `end_inventory_qty` DECIMAL(24,6) NOT NULL DEFAULT 0 COMMENT '期末库存数量',
    `end_inventory_total_cost` DECIMAL(24,6) NOT NULL DEFAULT 0 COMMENT '期末库存总成本',
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '记录创建时间',
    PRIMARY KEY (`id`),
    UNIQUE KEY `uk_inventory_local_month_source` (`stat_month`,`source_id`,`source_child_index`),
    KEY `idx_inventory_local_month_department` (`stat_month`,`department_code`),
    KEY `idx_inventory_local_month_owner` (`stat_month`,`principal_name`),
    KEY `idx_inventory_local_month_wid` (`stat_month`,`sys_wid`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='DWD-领星本地仓月度库存报表清洗明细';

CREATE TABLE IF NOT EXISTS `dws_inventory_report_dimension_summary` (
    `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '自增主键',
    `stat_month` CHAR(7) NOT NULL COMMENT '数据归属年月，格式YYYY-MM',
    `source_type` VARCHAR(16) NOT NULL COMMENT '来源类型：FBA、OVERSEAS或LOCAL',
    `platform_code` VARCHAR(16) NOT NULL COMMENT '平台编码：AMZ或EBAY',
    `dimension_type` VARCHAR(16) NOT NULL COMMENT '汇总维度：GROUP、OWNER或WAREHOUSE',
    `dimension_value` VARCHAR(255) NOT NULL COMMENT '组别、负责人或仓库名称',
    `department_code` VARCHAR(32) NULL COMMENT '汇总部门编码',
    `source_rows` INT NOT NULL DEFAULT 0 COMMENT '参与汇总的明细行数',
    `end_in_transit_qty` DECIMAL(24,6) NOT NULL DEFAULT 0 COMMENT '期末在途数量汇总',
    `end_in_transit_total_cost` DECIMAL(24,6) NOT NULL DEFAULT 0 COMMENT '期末在途总成本汇总',
    `end_inventory_qty` DECIMAL(24,6) NOT NULL DEFAULT 0 COMMENT '期末库存数量汇总',
    `end_inventory_total_cost` DECIMAL(24,6) NOT NULL DEFAULT 0 COMMENT '期末库存总成本汇总',
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '记录创建时间',
    `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '记录更新时间',
    PRIMARY KEY (`id`),
    UNIQUE KEY `uk_inventory_dimension` (`stat_month`,`source_type`,`platform_code`,`dimension_type`,`dimension_value`,`department_code`),
    KEY `idx_inventory_dimension_month_department` (`stat_month`,`department_code`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='DWS-月度库存报表来源维度汇总';

CREATE TABLE IF NOT EXISTS `dws_inventory_report_department_summary` (
    `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '自增主键',
    `stat_month` CHAR(7) NOT NULL COMMENT '数据归属年月，格式YYYY-MM',
    `department_code` VARCHAR(32) NOT NULL COMMENT '部门编码',
    `department_name` VARCHAR(64) NOT NULL COMMENT '部门显示名称',
    `display_order` INT NOT NULL COMMENT '页面显示顺序',
    `is_total` TINYINT NOT NULL DEFAULT 0 COMMENT '是否汽配小计行：0否，1是',
    `local_end_in_transit_qty` DECIMAL(24,6) NOT NULL DEFAULT 0 COMMENT '本地仓期末在途数量',
    `local_end_in_transit_total_cost` DECIMAL(24,6) NOT NULL DEFAULT 0 COMMENT '本地仓期末在途总成本',
    `local_end_inventory_qty` DECIMAL(24,6) NOT NULL DEFAULT 0 COMMENT '本地仓期末库存数量',
    `local_end_inventory_total_cost` DECIMAL(24,6) NOT NULL DEFAULT 0 COMMENT '本地仓期末库存总成本',
    `overseas_end_in_transit_qty` DECIMAL(24,6) NOT NULL DEFAULT 0 COMMENT '海外仓期末在途数量',
    `overseas_end_in_transit_total_cost` DECIMAL(24,6) NOT NULL DEFAULT 0 COMMENT '海外仓期末在途总成本',
    `overseas_end_inventory_qty` DECIMAL(24,6) NOT NULL DEFAULT 0 COMMENT '海外仓期末库存数量',
    `overseas_end_inventory_total_cost` DECIMAL(24,6) NOT NULL DEFAULT 0 COMMENT '海外仓期末库存总成本',
    `fba_end_inventory_qty` DECIMAL(24,6) NOT NULL DEFAULT 0 COMMENT 'FBA仓期末库存含移仓数量',
    `fba_end_inventory_total_cost` DECIMAL(24,6) NOT NULL DEFAULT 0 COMMENT 'FBA仓期末库存含移仓总成本',
    `fba_end_in_transit_qty` DECIMAL(24,6) NOT NULL DEFAULT 0 COMMENT 'FBA仓期末在途数量',
    `fba_end_in_transit_total_cost` DECIMAL(24,6) NOT NULL DEFAULT 0 COMMENT 'FBA仓期末在途总成本',
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '记录创建时间',
    `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '记录更新时间',
    PRIMARY KEY (`id`),
    UNIQUE KEY `uk_inventory_department_month` (`stat_month`,`department_code`),
    KEY `idx_inventory_department_month_order` (`stat_month`,`display_order`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='DWS-月度库存报表部门主表';

-- =====================================================================
-- 第二部分：Java ERP数据库
-- =====================================================================
USE `jmh_data_platform`;

-- 目标库：jmh_data_platform（Java ERP / Quartz 数据库）。
-- 仅注册三类月度库存报表源数据同步任务，不创建 Python ODS 表。
-- Python 三张表请执行：Date-Project/migrations/20260814_inventory_report_source_tables.sql

UPDATE sys_job
SET job_name = '领星-月度库存报表三接口源数据同步',
    job_group = 'DATA_CENTER',
    invoke_target = 'pythonMonthlyInventoryReportTask.syncPreviousMonth()',
    cron_expression = '0 0 6 1 * ?',
    misfire_policy = '2',
    concurrent = '1',
    status = '0',
    update_by = 'SYSTEM',
    update_time = NOW(),
    remark = '每月1日06:00由Java Quartz调用Python拉取上一个完整自然月三类库存源数据（月初至月末），并重建DWD与DWS报表'
WHERE invoke_target IN (
    'pythonMonthlyInventoryReportTask.syncCurrentMonth',
    'pythonMonthlyInventoryReportTask.syncCurrentMonth()',
    'pythonMonthlyInventoryReportTask.syncPreviousMonth',
    'pythonMonthlyInventoryReportTask.syncPreviousMonth()'
);

INSERT INTO sys_job (
    job_name, job_group, invoke_target, cron_expression,
    misfire_policy, concurrent, status,
    create_by, create_time, remark
)
SELECT
    '领星-月度库存报表三接口源数据同步',
    'DATA_CENTER',
    'pythonMonthlyInventoryReportTask.syncPreviousMonth()',
    '0 0 6 1 * ?',
    '2', '1', '0',
    'SYSTEM', NOW(),
    '每月1日06:00由Java Quartz调用Python拉取上一个完整自然月三类库存源数据（月初至月末），并重建DWD与DWS报表'
WHERE NOT EXISTS (
    SELECT 1
    FROM sys_job
    WHERE invoke_target IN (
        'pythonMonthlyInventoryReportTask.syncCurrentMonth',
        'pythonMonthlyInventoryReportTask.syncCurrentMonth()',
        'pythonMonthlyInventoryReportTask.syncPreviousMonth',
        'pythonMonthlyInventoryReportTask.syncPreviousMonth()'
    )
);

SELECT job_id, job_name, job_group, invoke_target,
       cron_expression, misfire_policy, concurrent, status
FROM sys_job
WHERE invoke_target IN (
    'pythonMonthlyInventoryReportTask.syncCurrentMonth',
    'pythonMonthlyInventoryReportTask.syncCurrentMonth()',
    'pythonMonthlyInventoryReportTask.syncPreviousMonth',
    'pythonMonthlyInventoryReportTask.syncPreviousMonth()'
);

-- 目标库：jmh_data_platform（Java ERP数据库）。
-- 在“数据中心”下新增“月度库存数据表”菜单，并将全部权限授予 leiyongyu 当前绑定的角色。

SET @inventory_parent_id := (
    SELECT menu_id FROM sys_menu
    WHERE menu_name='数据中心'
      AND menu_type='M'
      AND status='0'
    ORDER BY IF(menu_id=2101, 0, 1), menu_id
    LIMIT 1
);

SET @inventory_menu_id := (
    SELECT menu_id FROM sys_menu
    WHERE component='finance/monthlyInventoryReport/index'
       OR perms='finance:monthlyInventoryReport:list'
    ORDER BY menu_id LIMIT 1
);

INSERT INTO sys_menu (
    menu_name,parent_id,order_num,path,component,query,route_name,
    is_frame,is_cache,menu_type,visible,status,perms,icon,
    create_by,create_time,remark
)
SELECT
    '月度库存数据表',@inventory_parent_id,5,'monthly-inventory-report',
    'finance/monthlyInventoryReport/index',NULL,'MonthlyInventoryReport',
    1,0,'C','0','0','finance:monthlyInventoryReport:list','chart',
    'SYSTEM',NOW(),'展示本地仓、海外仓和FBA仓月度库存汇总及清洗明细'
WHERE @inventory_parent_id IS NOT NULL
  AND @inventory_menu_id IS NULL;

SET @inventory_menu_id := COALESCE(
    @inventory_menu_id,
    (
        SELECT menu_id FROM sys_menu
        WHERE component='finance/monthlyInventoryReport/index'
        ORDER BY menu_id DESC LIMIT 1
    )
);

UPDATE sys_menu
SET menu_name='月度库存数据表',
    parent_id=@inventory_parent_id,
    order_num=5,
    path='monthly-inventory-report',
    component='finance/monthlyInventoryReport/index',
    route_name='MonthlyInventoryReport',
    is_frame=1,
    is_cache=0,
    menu_type='C',
    visible='0',
    status='0',
    perms='finance:monthlyInventoryReport:list',
    icon='chart',
    update_by='SYSTEM',
    update_time=NOW(),
    remark='展示本地仓、海外仓和FBA仓月度库存汇总及清洗明细'
WHERE menu_id=@inventory_menu_id;

INSERT INTO sys_menu (
    menu_name,parent_id,order_num,path,component,query,route_name,
    is_frame,is_cache,menu_type,visible,status,perms,icon,
    create_by,create_time,remark
)
SELECT
    '月度库存查询',@inventory_menu_id,1,'',NULL,NULL,NULL,
    1,0,'F','0','0','finance:monthlyInventoryReport:list','#',
    'SYSTEM',NOW(),'查询月度库存汇总与清洗明细'
WHERE @inventory_menu_id IS NOT NULL
  AND NOT EXISTS (
      SELECT 1 FROM sys_menu
      WHERE parent_id=@inventory_menu_id
        AND perms='finance:monthlyInventoryReport:list'
  );

INSERT INTO sys_menu (
    menu_name,parent_id,order_num,path,component,query,route_name,
    is_frame,is_cache,menu_type,visible,status,perms,icon,
    create_by,create_time,remark
)
SELECT
    '月度库存重新清洗',@inventory_menu_id,2,'',NULL,NULL,NULL,
    1,0,'F','0','0','finance:monthlyInventoryReport:edit','#',
    'SYSTEM',NOW(),'使用现有ODS数据重新生成DWD和DWS报表'
WHERE @inventory_menu_id IS NOT NULL
  AND NOT EXISTS (
      SELECT 1 FROM sys_menu
      WHERE parent_id=@inventory_menu_id
        AND perms='finance:monthlyInventoryReport:edit'
  );

-- leiyongyu 登录后需要先进入“数据中心”，因此同时补齐父菜单权限。
INSERT IGNORE INTO sys_role_menu (role_id,menu_id)
SELECT DISTINCT ur.role_id,@inventory_parent_id
FROM sys_user user_info
JOIN sys_user_role ur ON ur.user_id=user_info.user_id
JOIN sys_role role_info ON role_info.role_id=ur.role_id
WHERE user_info.user_name='leiyongyu'
  AND user_info.del_flag='0'
  AND user_info.status='0'
  AND role_info.status='0'
  AND @inventory_parent_id IS NOT NULL;

-- 授予页面菜单权限。
INSERT IGNORE INTO sys_role_menu (role_id,menu_id)
SELECT DISTINCT ur.role_id,@inventory_menu_id
FROM sys_user user_info
JOIN sys_user_role ur ON ur.user_id=user_info.user_id
JOIN sys_role role_info ON role_info.role_id=ur.role_id
WHERE user_info.user_name='leiyongyu'
  AND user_info.del_flag='0'
  AND user_info.status='0'
  AND role_info.status='0'
  AND @inventory_menu_id IS NOT NULL;

-- 授予该页面下的查询、重新清洗全部按钮权限。
INSERT IGNORE INTO sys_role_menu (role_id,menu_id)
SELECT DISTINCT ur.role_id,button.menu_id
FROM sys_user user_info
JOIN sys_user_role ur ON ur.user_id=user_info.user_id
JOIN sys_role role_info ON role_info.role_id=ur.role_id
JOIN sys_menu button ON button.parent_id=@inventory_menu_id
WHERE user_info.user_name='leiyongyu'
  AND user_info.del_flag='0'
  AND user_info.status='0'
  AND role_info.status='0'
  AND button.perms IN (
      'finance:monthlyInventoryReport:list',
      'finance:monthlyInventoryReport:edit'
  );

SELECT menu_id,menu_name,parent_id,order_num,path,component,perms,menu_type,status
FROM sys_menu
WHERE menu_id=@inventory_menu_id OR parent_id=@inventory_menu_id
ORDER BY menu_type,order_num,menu_id;

SELECT user_info.user_name,role_info.role_id,role_info.role_name,
       menu_info.menu_id,menu_info.menu_name,menu_info.perms
FROM sys_user user_info
JOIN sys_user_role ur ON ur.user_id=user_info.user_id
JOIN sys_role role_info ON role_info.role_id=ur.role_id
JOIN sys_role_menu rm ON rm.role_id=role_info.role_id
JOIN sys_menu menu_info ON menu_info.menu_id=rm.menu_id
WHERE user_info.user_name='leiyongyu'
  AND (menu_info.menu_id=@inventory_parent_id
       OR menu_info.menu_id=@inventory_menu_id
       OR menu_info.parent_id=@inventory_menu_id)
ORDER BY role_info.role_id,menu_info.menu_type,menu_info.order_num,menu_info.menu_id;
