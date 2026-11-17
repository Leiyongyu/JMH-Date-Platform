-- STA装箱提交、异步状态跟踪与防重复提交。
-- 依赖：
--   deploy_patch_customs_shipment_fee_20260724.sql
--   20260727_lingxing_sta_inbound_plan.sql
--   20260727_sta_relational_lookup_optimization.sql
-- 可重复执行，不删除历史数据。

SET NAMES utf8mb4;

CREATE TABLE IF NOT EXISTS `customs_packing_submission` (
  `id` bigint NOT NULL AUTO_INCREMENT COMMENT '主键',
  `inbound_plan_id` varchar(128) NOT NULL COMMENT 'STA任务编号；提交唯一业务键',
  `sid` bigint NOT NULL COMMENT '领星Amazon店铺SID',
  `position_type` int DEFAULT NULL COMMENT '分仓方式；当前仅支持2先分仓后装箱',
  `status` varchar(30) NOT NULL DEFAULT 'READY'
    COMMENT 'READY/SUBMITTING/PROCESSING/SUCCESS/FAILED/UNKNOWN',
  `task_id` varchar(128) DEFAULT NULL COMMENT '领星异步任务ID',
  `payload_hash` char(64) DEFAULT NULL COMMENT '提交JSON的SHA-256摘要',
  `request_body` longtext COMMENT '提交给领星的完整JSON',
  `initial_response_body` longtext COMMENT '提交接口完整原始响应',
  `final_response_body` longtext COMMENT '最近一次异步状态接口完整响应',
  `request_id` varchar(128) DEFAULT NULL COMMENT '领星最近一次请求链路ID',
  `error_message` text COMMENT '失败或待确认原因',
  `attempt_count` int NOT NULL DEFAULT 0 COMMENT '提交尝试次数',
  `operator` varchar(64) DEFAULT NULL COMMENT '提交人',
  `submit_time` datetime(3) DEFAULT NULL COMMENT '最近提交时间',
  `success_time` datetime(3) DEFAULT NULL COMMENT '最终成功时间',
  `failed_time` datetime(3) DEFAULT NULL COMMENT '明确失败时间',
  `last_poll_time` datetime(3) DEFAULT NULL COMMENT '最近异步状态查询时间',
  `create_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `update_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP
    ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_customs_packing_submission_plan` (`inbound_plan_id`),
  UNIQUE KEY `uk_customs_packing_submission_task` (`task_id`),
  KEY `idx_customs_packing_submission_status` (`status`, `last_poll_time`),
  KEY `idx_customs_packing_submission_operator` (`operator`, `submit_time`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='STA装箱提交及领星异步结果';

SET @packing_page_id := (
  SELECT menu_id
  FROM sys_menu
  WHERE perms = 'customs:shipmentFee:list'
  ORDER BY menu_id
  LIMIT 1
);

INSERT INTO sys_menu (
  menu_name, parent_id, order_num, path, component, query, route_name,
  is_frame, is_cache, menu_type, visible, status, perms, icon,
  create_by, create_time, remark
)
SELECT
  '提交STA装箱信息', @packing_page_id, 3, '#', '', '', '',
  1, 0, 'F', '0', '0', 'customs:packingSubmission:submit', '#',
  'SYSTEM', CURRENT_TIMESTAMP, '提交装箱并查询领星异步任务状态'
WHERE @packing_page_id IS NOT NULL
  AND NOT EXISTS (
    SELECT 1 FROM sys_menu
    WHERE perms = 'customs:packingSubmission:submit'
  );

-- 已拥有“上传发货单与装箱信息”权限的角色，自动获得提交权限。
INSERT INTO sys_role_menu (role_id, menu_id)
SELECT DISTINCT rm.role_id, submit_menu.menu_id
FROM sys_role_menu rm
INNER JOIN sys_menu import_menu
  ON import_menu.menu_id = rm.menu_id
 AND import_menu.perms = 'customs:shipmentFee:import'
INNER JOIN sys_menu submit_menu
  ON submit_menu.perms = 'customs:packingSubmission:submit'
WHERE NOT EXISTS (
  SELECT 1
  FROM sys_role_menu existing
  WHERE existing.role_id = rm.role_id
    AND existing.menu_id = submit_menu.menu_id
);

-- 部署后验证：
-- SELECT * FROM customs_packing_submission ORDER BY id DESC;
-- SELECT menu_id, menu_name, perms FROM sys_menu
-- WHERE perms = 'customs:packingSubmission:submit';
