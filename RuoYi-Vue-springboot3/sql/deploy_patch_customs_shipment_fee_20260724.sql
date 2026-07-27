-- 报关管理 / 发货单费用批量上传、详细日志及 leiyongyu 权限。
-- 可重复执行。请在 Java ERP 数据库 jmh_data_platform 中执行。

USE `jmh_data_platform`;

CREATE TABLE IF NOT EXISTS `customs_shipment_fee_import_batch` (
  `id` bigint NOT NULL AUTO_INCREMENT COMMENT '主键',
  `business_type` varchar(30) NOT NULL DEFAULT 'SHIPMENT_LOGISTICS' COMMENT 'SHIPMENT_LOGISTICS发货单物流/PACKING_INFO装箱信息',
  `batch_no` varchar(40) NOT NULL COMMENT '上传批次号',
  `original_file_name` varchar(255) NOT NULL COMMENT '原始文件名',
  `file_size` bigint NOT NULL DEFAULT 0 COMMENT '文件大小（字节）',
  `file_sha256` char(64) DEFAULT NULL COMMENT '文件SHA-256摘要',
  `total_rows` int NOT NULL DEFAULT 0 COMMENT '读取的数据行数',
  `total_shipments` int NOT NULL DEFAULT 0 COMMENT '发货单数量',
  `success_count` int NOT NULL DEFAULT 0 COMMENT '成功发货单数',
  `failed_count` int NOT NULL DEFAULT 0 COMMENT '失败发货单数',
  `status` varchar(30) NOT NULL DEFAULT 'RUNNING' COMMENT 'RUNNING/SUCCESS/PARTIAL_SUCCESS/FAILED',
  `operator` varchar(64) DEFAULT NULL COMMENT '上传人',
  `error_message` text COMMENT '文件级错误或汇总说明',
  `upload_time` datetime(3) NOT NULL COMMENT '上传时间',
  `start_time` datetime(3) NOT NULL COMMENT '开始处理时间',
  `finish_time` datetime(3) DEFAULT NULL COMMENT '处理完成时间',
  `duration_ms` bigint DEFAULT NULL COMMENT '总耗时毫秒',
  `create_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `update_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '修改时间',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_customs_shipment_fee_batch_no` (`batch_no`),
  KEY `idx_customs_shipment_fee_batch_business` (`business_type`,`upload_time`),
  KEY `idx_customs_shipment_fee_batch_status` (`status`,`upload_time`),
  KEY `idx_customs_shipment_fee_batch_operator` (`operator`,`upload_time`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='发货单费用批量上传批次';

CREATE TABLE IF NOT EXISTS `customs_shipment_fee_import_log` (
  `id` bigint NOT NULL AUTO_INCREMENT COMMENT '主键',
  `batch_id` bigint NOT NULL COMMENT '上传批次ID',
  `business_type` varchar(30) NOT NULL DEFAULT 'SHIPMENT_LOGISTICS' COMMENT 'SHIPMENT_LOGISTICS发货单物流/PACKING_INFO装箱信息',
  `order_sn` varchar(255) DEFAULT NULL COMMENT '业务单号；发货单号或STA编号/店铺',
  `source_rows` varchar(500) DEFAULT NULL COMMENT 'Excel来源行号，多个用逗号分隔',
  `source_row_count` int NOT NULL DEFAULT 0 COMMENT '合并的数据行数',
  `status` varchar(30) NOT NULL DEFAULT 'PROCESSING' COMMENT 'PROCESSING/SUCCESS/FAILED',
  `error_stage` varchar(40) DEFAULT NULL COMMENT 'VALIDATION/API_EXCEPTION/LINGXING_API',
  `error_code` varchar(100) DEFAULT NULL COMMENT '校验或领星错误码',
  `error_message` text COMMENT '完整失败原因',
  `exception_type` varchar(255) DEFAULT NULL COMMENT 'Java异常类型',
  `stack_trace` longtext COMMENT '异常堆栈',
  `request_id` varchar(100) DEFAULT NULL COMMENT '领星request_id',
  `lingxing_response_time` varchar(50) DEFAULT NULL COMMENT '领星返回的response_time',
  `attempt_count` int NOT NULL DEFAULT 0 COMMENT '调用尝试次数',
  `request_body` longtext COMMENT '发送给领星的完整JSON',
  `response_body` longtext COMMENT '领星完整原始响应JSON',
  `source_data` longtext COMMENT '该发货单的Excel原始字段JSON',
  `operator` varchar(64) DEFAULT NULL COMMENT '上传人',
  `upload_time` datetime(3) NOT NULL COMMENT '文件上传时间',
  `start_time` datetime(3) NOT NULL COMMENT '该发货单开始处理时间',
  `success_time` datetime(3) DEFAULT NULL COMMENT '成功时间',
  `failed_time` datetime(3) DEFAULT NULL COMMENT '失败时间',
  `duration_ms` bigint DEFAULT NULL COMMENT '该发货单耗时毫秒',
  `create_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `update_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '修改时间',
  PRIMARY KEY (`id`),
  KEY `idx_customs_shipment_fee_log_batch` (`batch_id`,`id`),
  KEY `idx_customs_shipment_fee_log_business` (`business_type`,`upload_time`),
  KEY `idx_customs_shipment_fee_log_order` (`order_sn`,`upload_time`),
  KEY `idx_customs_shipment_fee_log_status` (`status`,`upload_time`),
  KEY `idx_customs_shipment_fee_log_request` (`request_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='发货单费用逐单更新领星日志';

-- 找到“报关管理”目录。
SET @customs_menu_id := (
  SELECT menu_id
  FROM sys_menu
  WHERE menu_type = 'M'
    AND (path = 'customs' OR menu_name = '报关管理')
  ORDER BY CASE WHEN path = 'customs' THEN 0 ELSE 1 END, menu_id
  LIMIT 1
);

-- 发货单页面。
INSERT INTO sys_menu (
  menu_name, parent_id, order_num, path, component, query, route_name,
  is_frame, is_cache, menu_type, visible, status, perms, icon,
  create_by, create_time, remark
)
SELECT
  '发货单', @customs_menu_id, 3, 'shipment-fee',
  'operations/customs/shipmentFee/index', NULL, 'CustomsShipmentFee',
  1, 0, 'C', '0', '0', 'customs:shipmentFee:list', 'upload',
  'SYSTEM', NOW(), '批量上传发货单费用并查看逐单调用日志'
WHERE @customs_menu_id IS NOT NULL
  AND NOT EXISTS (
    SELECT 1 FROM sys_menu
    WHERE parent_id = @customs_menu_id AND path = 'shipment-fee'
  );

UPDATE sys_menu
SET menu_name = '发货单',
    order_num = 3,
    component = 'operations/customs/shipmentFee/index',
    route_name = 'CustomsShipmentFee',
    is_frame = 1,
    is_cache = 0,
    menu_type = 'C',
    visible = '0',
    status = '0',
    perms = 'customs:shipmentFee:list',
    icon = 'upload',
    update_by = 'SYSTEM',
    update_time = NOW()
WHERE parent_id = @customs_menu_id AND path = 'shipment-fee';

SET @shipment_fee_menu_id := (
  SELECT menu_id
  FROM sys_menu
  WHERE parent_id = @customs_menu_id AND path = 'shipment-fee'
  ORDER BY menu_id
  LIMIT 1
);

-- 查询日志权限。
INSERT INTO sys_menu (
  menu_name, parent_id, order_num, path, component, query, route_name,
  is_frame, is_cache, menu_type, visible, status, perms, icon,
  create_by, create_time, remark
)
SELECT
  '发货单日志查询', @shipment_fee_menu_id, 1, '', NULL, NULL, '',
  1, 0, 'F', '0', '0', 'customs:shipmentFee:list', '#',
  'SYSTEM', NOW(), ''
WHERE @shipment_fee_menu_id IS NOT NULL
  AND NOT EXISTS (
    SELECT 1 FROM sys_menu
    WHERE parent_id = @shipment_fee_menu_id
      AND perms = 'customs:shipmentFee:list'
  );

-- 上传并更新领星权限（即页面编辑能力）。
INSERT INTO sys_menu (
  menu_name, parent_id, order_num, path, component, query, route_name,
  is_frame, is_cache, menu_type, visible, status, perms, icon,
  create_by, create_time, remark
)
SELECT
  '上传发货单费用明细', @shipment_fee_menu_id, 2, '', NULL, NULL, '',
  1, 0, 'F', '0', '0', 'customs:shipmentFee:import', '#',
  'SYSTEM', NOW(), '逐单调用领星更新发货单物流信息'
WHERE @shipment_fee_menu_id IS NOT NULL
  AND NOT EXISTS (
    SELECT 1 FROM sys_menu
    WHERE parent_id = @shipment_fee_menu_id
      AND perms = 'customs:shipmentFee:import'
  );

-- 给 leiyongyu 当前拥有的全部角色授权：运营中心、报关管理、发货单页面、查询和上传。
SET @operations_menu_id := (
  SELECT parent_id FROM sys_menu WHERE menu_id = @customs_menu_id LIMIT 1
);

INSERT IGNORE INTO sys_role_menu (role_id, menu_id)
SELECT ur.role_id, m.menu_id
FROM sys_user u
JOIN sys_user_role ur ON ur.user_id = u.user_id
JOIN sys_menu m ON m.menu_id IN (
  @operations_menu_id,
  @customs_menu_id,
  @shipment_fee_menu_id,
  (SELECT menu_id FROM sys_menu
   WHERE parent_id = @shipment_fee_menu_id
     AND perms = 'customs:shipmentFee:list'
   ORDER BY menu_id LIMIT 1),
  (SELECT menu_id FROM sys_menu
   WHERE parent_id = @shipment_fee_menu_id
     AND perms = 'customs:shipmentFee:import'
   ORDER BY menu_id LIMIT 1)
)
WHERE u.user_name = 'leiyongyu'
  AND m.menu_id IS NOT NULL;

-- 部署检查。
SELECT menu_id, menu_name, parent_id, order_num, path, component, menu_type, perms
FROM sys_menu
WHERE menu_id = @shipment_fee_menu_id OR parent_id = @shipment_fee_menu_id
ORDER BY menu_type, order_num, menu_id;

SELECT u.user_name, r.role_name, m.menu_name, m.perms
FROM sys_user u
JOIN sys_user_role ur ON ur.user_id = u.user_id
JOIN sys_role r ON r.role_id = ur.role_id
JOIN sys_role_menu rm ON rm.role_id = r.role_id
JOIN sys_menu m ON m.menu_id = rm.menu_id
WHERE u.user_name = 'leiyongyu'
  AND (m.menu_id = @shipment_fee_menu_id OR m.parent_id = @shipment_fee_menu_id)
ORDER BY r.role_id, m.menu_type, m.order_num;
