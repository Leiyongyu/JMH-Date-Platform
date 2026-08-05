-- STA发货单费用、装箱信息上传：服务器缺失业务表部署脚本。
-- 适用数据库：MySQL 8.0+
-- 目标库：jmh_data_platform
--
-- 说明：
-- 1. 已按服务器导出的jmh_data_platform.sql（2026-08-04）完成比对。
-- 2. 服务器已存在customs_packing_submission，且字段与索引完整，本文件不会创建或修改该表。
-- 3. 本文件只创建服务器缺失的7张STA业务表及索引，不写入菜单、角色、定时任务。
-- 4. 全部使用CREATE TABLE IF NOT EXISTS，可重复执行，不会清空或覆盖已有数据。

SET NAMES utf8mb4;
USE `jmh_data_platform`;

-- ============================================================
-- 1. 上传批次：费用明细和装箱信息共用
-- ============================================================
CREATE TABLE IF NOT EXISTS `customs_shipment_fee_import_batch` (
  `id` bigint NOT NULL AUTO_INCREMENT COMMENT '主键',
  `business_type` varchar(30) NOT NULL DEFAULT 'SHIPMENT_LOGISTICS'
    COMMENT 'SHIPMENT_LOGISTICS发货单物流/PACKING_INFO装箱信息',
  `batch_no` varchar(40) NOT NULL COMMENT '上传批次号',
  `original_file_name` varchar(255) NOT NULL COMMENT '原始文件名',
  `file_size` bigint NOT NULL DEFAULT 0 COMMENT '文件大小（字节）',
  `file_sha256` char(64) DEFAULT NULL COMMENT '文件SHA-256摘要',
  `total_rows` int NOT NULL DEFAULT 0 COMMENT '读取的数据行数',
  `total_shipments` int NOT NULL DEFAULT 0 COMMENT '唯一单号或货件任务数',
  `success_count` int NOT NULL DEFAULT 0 COMMENT '成功任务数',
  `failed_count` int NOT NULL DEFAULT 0 COMMENT '失败任务数',
  `status` varchar(30) NOT NULL DEFAULT 'RUNNING'
    COMMENT 'QUEUED/RUNNING/SUCCESS/PARTIAL_SUCCESS/FAILED',
  `operator` varchar(64) DEFAULT NULL COMMENT '上传人',
  `error_message` text COMMENT '文件级错误或批次汇总说明',
  `upload_time` datetime(3) NOT NULL COMMENT '上传时间',
  `start_time` datetime(3) NOT NULL COMMENT '开始处理时间',
  `finish_time` datetime(3) DEFAULT NULL COMMENT '处理完成时间',
  `duration_ms` bigint DEFAULT NULL COMMENT '总耗时毫秒',
  `create_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `update_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP
    ON UPDATE CURRENT_TIMESTAMP COMMENT '修改时间',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_customs_shipment_fee_batch_no` (`batch_no`),
  KEY `idx_customs_shipment_fee_batch_business` (`business_type`, `upload_time`),
  KEY `idx_customs_shipment_fee_batch_status` (`status`, `upload_time`),
  KEY `idx_customs_shipment_fee_batch_operator` (`operator`, `upload_time`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='STA费用与装箱文件上传批次';

-- ============================================================
-- 2. 单号处理明细：保存Excel原始数据、请求、响应及错误堆栈
-- ============================================================
CREATE TABLE IF NOT EXISTS `customs_shipment_fee_import_log` (
  `id` bigint NOT NULL AUTO_INCREMENT COMMENT '主键',
  `batch_id` bigint NOT NULL COMMENT '上传批次ID',
  `business_type` varchar(30) NOT NULL DEFAULT 'SHIPMENT_LOGISTICS'
    COMMENT 'SHIPMENT_LOGISTICS发货单物流/PACKING_INFO装箱信息',
  `shipment_id` varchar(128) DEFAULT NULL COMMENT 'Excel来源FBA货件单号',
  `order_sn` varchar(255) DEFAULT NULL COMMENT '领星发货单号或装箱业务货件号',
  `source_rows` varchar(500) DEFAULT NULL COMMENT 'Excel来源行号，多个用逗号分隔',
  `source_row_count` int NOT NULL DEFAULT 0 COMMENT '合并的数据行数',
  `status` varchar(30) NOT NULL DEFAULT 'PROCESSING'
    COMMENT 'PROCESSING/SUCCESS/FAILED',
  `error_stage` varchar(40) DEFAULT NULL
    COMMENT 'VALIDATION/API_EXCEPTION/LINGXING_API/SYSTEM_EXCEPTION',
  `error_code` varchar(100) DEFAULT NULL COMMENT '校验、领星或系统错误码',
  `error_message` text COMMENT '完整失败原因',
  `exception_type` varchar(255) DEFAULT NULL COMMENT 'Java异常类型',
  `stack_trace` longtext COMMENT '异常堆栈',
  `request_id` varchar(100) DEFAULT NULL COMMENT '领星request_id',
  `lingxing_response_time` varchar(50) DEFAULT NULL COMMENT '领星response_time',
  `attempt_count` int NOT NULL DEFAULT 0 COMMENT '接口调用尝试次数',
  `request_body` longtext COMMENT '发送给领星的完整JSON',
  `response_body` longtext COMMENT '领星完整原始响应JSON',
  `source_data` longtext COMMENT '当前单号的Excel原始字段JSON',
  `operator` varchar(64) DEFAULT NULL COMMENT '上传人',
  `upload_time` datetime(3) NOT NULL COMMENT '文件上传时间',
  `start_time` datetime(3) NOT NULL COMMENT '当前单号开始处理时间',
  `success_time` datetime(3) DEFAULT NULL COMMENT '成功时间',
  `failed_time` datetime(3) DEFAULT NULL COMMENT '失败时间',
  `duration_ms` bigint DEFAULT NULL COMMENT '当前单号耗时毫秒',
  `create_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `update_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP
    ON UPDATE CURRENT_TIMESTAMP COMMENT '修改时间',
  PRIMARY KEY (`id`),
  KEY `idx_customs_shipment_fee_log_batch` (`batch_id`, `id`),
  KEY `idx_customs_shipment_fee_log_business` (`business_type`, `upload_time`),
  KEY `idx_customs_shipment_fee_log_shipment` (`shipment_id`),
  KEY `idx_customs_shipment_fee_log_order` (`order_sn`, `upload_time`),
  KEY `idx_customs_shipment_fee_log_status` (`status`, `upload_time`),
  KEY `idx_customs_shipment_fee_log_request` (`request_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='STA费用与装箱逐单处理日志';

-- ============================================================
-- 3. 领星头程物流渠道：校验Excel中的渠道ID和provider.id
-- ============================================================
CREATE TABLE IF NOT EXISTS `lingxing_logistics_channel` (
  `id` bigint NOT NULL COMMENT '物流渠道ID/物流方案代码',
  `channel_name` varchar(255) DEFAULT NULL COMMENT '物流渠道名称',
  `method_id` varchar(64) DEFAULT NULL COMMENT '运输方式ID',
  `method_name` varchar(128) DEFAULT NULL COMMENT '运输方式名称',
  `billing_type` tinyint DEFAULT NULL COMMENT '计费类型：0计费重，1体积',
  `volume_calc_param` varchar(64) DEFAULT NULL COMMENT '材积计算参数',
  `zip_code` varchar(64) DEFAULT NULL COMMENT '邮编',
  `valid_period` int DEFAULT NULL COMMENT '时效天数',
  `remark` varchar(1000) DEFAULT NULL COMMENT '备注',
  `enabled` tinyint DEFAULT NULL COMMENT '状态：0停用，1启用',
  `last_modify_uid` bigint DEFAULT NULL COMMENT '领星最后更新用户ID',
  `gmt_modified` datetime DEFAULT NULL COMMENT '领星更新时间',
  `provider_id` varchar(64) DEFAULT NULL COMMENT '所属头程物流商ID',
  `provider_name` varchar(255) DEFAULT NULL COMMENT '所属头程物流商名称',
  `freight_json` longtext COMMENT '运费规则数组JSON',
  `send_place_code` varchar(64) DEFAULT NULL COMMENT '提货地代码',
  `receive_country_code` varchar(16) DEFAULT NULL COMMENT '目的国家二字码',
  `is_include_tax` tinyint DEFAULT NULL COMMENT '是否包税：0否，1是',
  `is_points_behind` tinyint DEFAULT NULL COMMENT '是否分抛：0否，1是',
  `points_behind_coefficient` decimal(18,6) DEFAULT NULL COMMENT '分抛系数',
  `raw_json` longtext COMMENT '领星原始整行JSON',
  `create_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `update_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP
    ON UPDATE CURRENT_TIMESTAMP COMMENT '修改时间',
  PRIMARY KEY (`id`),
  KEY `idx_lingxing_logistics_channel_enabled` (`enabled`),
  KEY `idx_lingxing_logistics_channel_provider` (`provider_id`),
  KEY `idx_lingxing_logistics_channel_method` (`method_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='领星头程物流渠道全量表';

-- ============================================================
-- 4. FBA货件号与领星发货单号映射：费用上传使用
-- ============================================================
CREATE TABLE IF NOT EXISTS `lingxing_shipment_order_mapping` (
  `id` bigint NOT NULL AUTO_INCREMENT COMMENT '主键',
  `shipment_id` varchar(128) NOT NULL COMMENT 'FBA货件单号',
  `shipment_sn` varchar(128) NOT NULL COMMENT '领星发货单号',
  `shipment_list_id` bigint DEFAULT NULL COMMENT '领星发货单列表记录ID',
  `sid` bigint DEFAULT NULL COMMENT '领星Amazon店铺SID',
  `store_name` varchar(500) DEFAULT NULL COMMENT '领星店铺名称',
  `order_status` int DEFAULT NULL COMMENT '发货单状态',
  `shipment_status` varchar(64) DEFAULT NULL COMMENT '关联货件状态',
  `is_delete` tinyint NOT NULL DEFAULT 0 COMMENT '发货单是否删除：0否1是',
  `remote_create_time` datetime DEFAULT NULL COMMENT '领星发货单创建时间',
  `remote_update_time` datetime DEFAULT NULL COMMENT '领星发货单更新时间',
  `sync_time` datetime NOT NULL COMMENT '最近同步时间',
  `create_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `update_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP
    ON UPDATE CURRENT_TIMESTAMP COMMENT '修改时间',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_lingxing_shipment_order_shipment_id` (`shipment_id`),
  KEY `idx_lingxing_shipment_order_shipment_sn` (`shipment_sn`),
  KEY `idx_lingxing_shipment_order_sid` (`sid`),
  KEY `idx_lingxing_shipment_order_sync_time` (`sync_time`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='领星FBA货件单号与发货单号映射';

-- ============================================================
-- 5. STA任务主表
-- ============================================================
CREATE TABLE IF NOT EXISTS `lingxing_sta_inbound_plan` (
  `id` bigint NOT NULL AUTO_INCREMENT COMMENT '主键',
  `record_key` varchar(255) NOT NULL COMMENT '内部关系键，优先使用货件号',
  `inbound_plan_id` varchar(128) DEFAULT NULL COMMENT '领星STA任务编号',
  `query_shipment_id` varchar(128) DEFAULT NULL COMMENT '旧版精确查询货件号兼容字段',
  `sid` bigint DEFAULT NULL COMMENT '领星Amazon店铺SID',
  `plan_name` varchar(500) DEFAULT NULL COMMENT 'STA任务名称',
  `status` varchar(64) DEFAULT NULL COMMENT 'STA任务状态',
  `position_type` int DEFAULT NULL COMMENT '分仓方式：1先装箱再分仓，2先分仓再装箱',
  `gmt_create` datetime DEFAULT NULL COMMENT '领星创建时间',
  `gmt_modified` datetime DEFAULT NULL COMMENT '领星更新时间',
  `raw_json` longtext COMMENT '旧版STA任务原始JSON兼容字段',
  `sync_time` datetime NOT NULL COMMENT '同步时间',
  `create_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `update_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP
    ON UPDATE CURRENT_TIMESTAMP COMMENT '修改时间',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_lingxing_sta_record_key` (`record_key`),
  UNIQUE KEY `uk_lingxing_sta_plan_id` (`inbound_plan_id`),
  KEY `idx_lingxing_sta_query_shipment` (`query_shipment_id`),
  KEY `idx_lingxing_sta_gmt_create` (`gmt_create`),
  KEY `idx_lingxing_sta_gmt_modified` (`gmt_modified`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='领星STA任务主表';

-- ============================================================
-- 6. STA任务商品明细：装箱上传按SKU解析真实MSKU
-- ============================================================
CREATE TABLE IF NOT EXISTS `lingxing_sta_inbound_plan_item` (
  `id` bigint NOT NULL AUTO_INCREMENT COMMENT '主键',
  `record_key` varchar(255) NOT NULL COMMENT '内部关系键',
  `inbound_plan_id` varchar(128) DEFAULT NULL COMMENT '领星STA任务编号',
  `item_index` int NOT NULL COMMENT '商品在接口数组中的序号',
  `asin` varchar(32) DEFAULT NULL COMMENT 'ASIN',
  `fnsku` varchar(64) DEFAULT NULL COMMENT 'FNSKU',
  `msku` varchar(255) DEFAULT NULL COMMENT '领星MSKU',
  `parent_asin` varchar(32) DEFAULT NULL COMMENT '父ASIN',
  `product_name` varchar(1000) DEFAULT NULL COMMENT '品名',
  `quantity` int DEFAULT NULL COMMENT '申报量',
  `sku` varchar(255) DEFAULT NULL COMMENT 'SKU',
  `title` varchar(2000) DEFAULT NULL COMMENT '标题',
  `url` varchar(2000) DEFAULT NULL COMMENT '图片URL',
  `raw_json` longtext COMMENT '旧版商品原始JSON兼容字段',
  `create_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `update_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP
    ON UPDATE CURRENT_TIMESTAMP COMMENT '修改时间',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_lingxing_sta_plan_item` (`inbound_plan_id`, `item_index`),
  KEY `idx_lingxing_sta_item_record_key` (`record_key`),
  KEY `idx_lingxing_sta_item_msku` (`msku`),
  KEY `idx_lingxing_sta_item_sku` (`sku`),
  KEY `idx_lingxing_sta_item_fnsku` (`fnsku`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='领星STA任务商品明细表';

-- ============================================================
-- 7. STA任务货件明细：装箱上传补齐STA编号、SID和内部货件ID
-- ============================================================
CREATE TABLE IF NOT EXISTS `lingxing_sta_inbound_plan_shipment` (
  `id` bigint NOT NULL AUTO_INCREMENT COMMENT '主键',
  `record_key` varchar(255) NOT NULL COMMENT '内部关系键',
  `inbound_plan_id` varchar(128) DEFAULT NULL COMMENT '领星STA任务编号',
  `shipment_index` int NOT NULL COMMENT '货件在接口数组中的序号',
  `shipment_id` varchar(128) DEFAULT NULL COMMENT '领星内部货件ID',
  `shipment_confirmation_id` varchar(128) DEFAULT NULL COMMENT 'FBA货件单号',
  `raw_json` longtext COMMENT '旧版货件原始JSON兼容字段',
  `create_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `update_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP
    ON UPDATE CURRENT_TIMESTAMP COMMENT '修改时间',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_lingxing_sta_plan_shipment` (`inbound_plan_id`, `shipment_index`),
  UNIQUE KEY `uk_lingxing_sta_confirmation_id` (`shipment_confirmation_id`),
  KEY `idx_lingxing_sta_shipment_record_key` (`record_key`),
  KEY `idx_lingxing_sta_shipment_id` (`shipment_id`),
  KEY `idx_lingxing_sta_confirmation_id` (`shipment_confirmation_id`),
  KEY `idx_lingxing_sta_confirmation_lookup`
    (`shipment_confirmation_id`, `inbound_plan_id`, `shipment_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='领星STA任务货件明细表';

-- ============================================================
-- 部署结果检查：包含服务器原有表在内应返回8行，且missing_count全部为0
-- ============================================================
SELECT expected.table_name,
       CASE WHEN actual.table_name IS NULL THEN 1 ELSE 0 END AS missing_count
FROM (
  SELECT 'customs_shipment_fee_import_batch' AS table_name
  UNION ALL SELECT 'customs_shipment_fee_import_log'
  UNION ALL SELECT 'lingxing_logistics_channel'
  UNION ALL SELECT 'lingxing_shipment_order_mapping'
  UNION ALL SELECT 'lingxing_sta_inbound_plan'
  UNION ALL SELECT 'lingxing_sta_inbound_plan_item'
  UNION ALL SELECT 'lingxing_sta_inbound_plan_shipment'
  UNION ALL SELECT 'customs_packing_submission'
) expected
LEFT JOIN information_schema.tables actual
  ON actual.table_schema = DATABASE()
 AND actual.table_name = expected.table_name
ORDER BY expected.table_name;

-- 字段结构快速核对。
SELECT table_name, column_name, column_type, is_nullable, column_default
FROM information_schema.columns
WHERE table_schema = DATABASE()
  AND table_name IN (
    'customs_shipment_fee_import_batch',
    'customs_shipment_fee_import_log',
    'lingxing_logistics_channel',
    'lingxing_shipment_order_mapping',
    'lingxing_sta_inbound_plan',
    'lingxing_sta_inbound_plan_item',
    'lingxing_sta_inbound_plan_shipment',
    'customs_packing_submission'
  )
ORDER BY table_name, ordinal_position;
