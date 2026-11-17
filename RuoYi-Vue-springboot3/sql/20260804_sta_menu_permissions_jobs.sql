-- STA页面菜单、leiyongyu权限及依赖定时任务。
-- 适用数据库：MySQL 8.0+ / RuoYi 3.9.2
-- 可重复执行，不删除现有菜单、权限或任务。

SET NAMES utf8mb4;
USE `jmh_data_platform`;

-- ============================================================
-- 一、STA页面及按钮权限
-- ============================================================

-- 查找现有“运营中心 / 报关管理”菜单链路。
SET @customs_menu_id := (
  SELECT `menu_id`
  FROM `sys_menu`
  WHERE `menu_type` = 'M'
    AND (`path` = 'customs' OR `menu_name` = '报关管理')
  ORDER BY CASE WHEN `path` = 'customs' THEN 0 ELSE 1 END, `menu_id`
  LIMIT 1
);

-- 只新增STA页面，不创建其他业务目录。
INSERT INTO `sys_menu` (
  `menu_name`, `parent_id`, `order_num`, `path`, `component`, `query`, `route_name`,
  `is_frame`, `is_cache`, `menu_type`, `visible`, `status`, `perms`, `icon`,
  `create_by`, `create_time`, `remark`
)
SELECT
  '发货单与装箱信息上传', @customs_menu_id, 3, 'shipment-fee',
  'operations/customs/shipmentFee/index', NULL, 'CustomsShipmentFee',
  1, 0, 'C', '0', '0', 'customs:shipmentFee:list', 'upload',
  'SYSTEM', CURRENT_TIMESTAMP, 'STA费用明细、装箱信息上传及装箱提交'
WHERE @customs_menu_id IS NOT NULL
  AND NOT EXISTS (
    SELECT 1
    FROM `sys_menu`
    WHERE `parent_id` = @customs_menu_id
      AND (`path` = 'shipment-fee'
           OR `component` = 'operations/customs/shipmentFee/index'
           OR `perms` = 'customs:shipmentFee:list')
  );

-- 已存在时统一修正为当前前端路由、显示状态和查询权限。
UPDATE `sys_menu`
SET `menu_name` = '发货单与装箱信息上传',
    `order_num` = 3,
    `path` = 'shipment-fee',
    `component` = 'operations/customs/shipmentFee/index',
    `route_name` = 'CustomsShipmentFee',
    `is_frame` = 1,
    `is_cache` = 0,
    `menu_type` = 'C',
    `visible` = '0',
    `status` = '0',
    `perms` = 'customs:shipmentFee:list',
    `icon` = 'upload',
    `update_by` = 'SYSTEM',
    `update_time` = CURRENT_TIMESTAMP,
    `remark` = 'STA费用明细、装箱信息上传及装箱提交'
WHERE `parent_id` = @customs_menu_id
  AND (`path` = 'shipment-fee'
       OR `component` = 'operations/customs/shipmentFee/index'
       OR `perms` = 'customs:shipmentFee:list');

SET @sta_page_id := (
  SELECT `menu_id`
  FROM `sys_menu`
  WHERE `parent_id` = @customs_menu_id
    AND (`path` = 'shipment-fee'
         OR `component` = 'operations/customs/shipmentFee/index'
         OR `perms` = 'customs:shipmentFee:list')
  ORDER BY `menu_id`
  LIMIT 1
);

-- 上传费用明细、上传装箱信息共用此权限。
INSERT INTO `sys_menu` (
  `menu_name`, `parent_id`, `order_num`, `path`, `component`, `query`, `route_name`,
  `is_frame`, `is_cache`, `menu_type`, `visible`, `status`, `perms`, `icon`,
  `create_by`, `create_time`, `remark`
)
SELECT
  '上传费用与装箱信息', @sta_page_id, 1, '#', '', NULL, '',
  1, 0, 'F', '0', '0', 'customs:shipmentFee:import', '#',
  'SYSTEM', CURRENT_TIMESTAMP, '上传费用明细或装箱信息Excel'
WHERE @sta_page_id IS NOT NULL
  AND NOT EXISTS (
    SELECT 1 FROM `sys_menu`
    WHERE `parent_id` = @sta_page_id
      AND `perms` = 'customs:shipmentFee:import'
  );

-- STA装箱最终提交及异步状态查询权限。
INSERT INTO `sys_menu` (
  `menu_name`, `parent_id`, `order_num`, `path`, `component`, `query`, `route_name`,
  `is_frame`, `is_cache`, `menu_type`, `visible`, `status`, `perms`, `icon`,
  `create_by`, `create_time`, `remark`
)
SELECT
  '提交STA装箱信息', @sta_page_id, 2, '#', '', NULL, '',
  1, 0, 'F', '0', '0', 'customs:packingSubmission:submit', '#',
  'SYSTEM', CURRENT_TIMESTAMP, '提交装箱并查询领星异步任务状态'
WHERE @sta_page_id IS NOT NULL
  AND NOT EXISTS (
    SELECT 1 FROM `sys_menu`
    WHERE `parent_id` = @sta_page_id
      AND `perms` = 'customs:packingSubmission:submit'
  );

-- leiyongyu为超级管理员时框架会自动拥有全部权限；
-- 同时把STA导航链路和按钮关联到该账号当前角色，兼容非user_id=1的超级管理员配置。
SET @operations_menu_id := (
  SELECT `parent_id`
  FROM `sys_menu`
  WHERE `menu_id` = @customs_menu_id
  LIMIT 1
);

INSERT IGNORE INTO `sys_role_menu` (`role_id`, `menu_id`)
SELECT DISTINCT ur.`role_id`, target_menu.`menu_id`
FROM `sys_user` u
INNER JOIN `sys_user_role` ur ON ur.`user_id` = u.`user_id`
INNER JOIN `sys_menu` target_menu
  ON target_menu.`menu_id` IN (
    @operations_menu_id,
    @customs_menu_id,
    @sta_page_id,
    (SELECT `menu_id` FROM `sys_menu`
     WHERE `parent_id` = @sta_page_id
       AND `perms` = 'customs:shipmentFee:import'
     ORDER BY `menu_id` LIMIT 1),
    (SELECT `menu_id` FROM `sys_menu`
     WHERE `parent_id` = @sta_page_id
       AND `perms` = 'customs:packingSubmission:submit'
     ORDER BY `menu_id` LIMIT 1)
  )
WHERE u.`user_name` = 'leiyongyu'
  AND u.`del_flag` = '0';

-- ============================================================
-- 二、STA依赖定时任务
-- ============================================================

-- 1. STA发货链路：货件与发货单映射 -> STA任务/货件/商品关系表。
-- 每天03:00执行，status=0表示启用。
UPDATE `sys_job`
SET `job_name` = 'STA发货链路同步',
    `job_group` = 'OPERATION',
    `invoke_target` = 'operationSyncTask.runStaShipmentChain()',
    `cron_expression` = '0 0 3 * * ?',
    `misfire_policy` = '1',
    `concurrent` = '1',
    `status` = '0',
    `update_by` = 'SYSTEM',
    `update_time` = CURRENT_TIMESTAMP,
    `remark` = '货件与发货单映射（空表全量/非空最近3天）→STA任务列表；每天03:00执行'
WHERE `invoke_target` IN (
  'operationSyncTask.runStaShipmentChain',
  'operationSyncTask.runStaShipmentChain()',
  'chainSyncTask.runStaShipmentChain',
  'chainSyncTask.runStaShipmentChain()'
);

INSERT INTO `sys_job` (
  `job_name`, `job_group`, `invoke_target`, `cron_expression`,
  `misfire_policy`, `concurrent`, `status`,
  `create_by`, `create_time`, `update_by`, `update_time`, `remark`
)
SELECT
  'STA发货链路同步', 'OPERATION',
  'operationSyncTask.runStaShipmentChain()', '0 0 3 * * ?',
  '1', '1', '0',
  'SYSTEM', CURRENT_TIMESTAMP, 'SYSTEM', CURRENT_TIMESTAMP,
  '货件与发货单映射（空表全量/非空最近3天）→STA任务列表；每天03:00执行'
WHERE NOT EXISTS (
  SELECT 1 FROM `sys_job`
  WHERE `invoke_target` IN (
    'operationSyncTask.runStaShipmentChain',
    'operationSyncTask.runStaShipmentChain()',
    'chainSyncTask.runStaShipmentChain',
    'chainSyncTask.runStaShipmentChain()'
  )
);

-- 2. 领星头程物流渠道：供费用Excel校验物流商ID与provider.id。
-- 每天03:30执行；沿用项目原设计，status=1表示创建后默认暂停，确认接口配置后可在任务页面启用。
UPDATE `sys_job`
SET `job_name` = '领星-头程物流渠道',
    `job_group` = 'OPERATION',
    `invoke_target` = 'operationSyncTask.syncLingxingLogisticsChannel()',
    `cron_expression` = '0 30 3 * * ?',
    `misfire_policy` = '1',
    `concurrent` = '1',
    `status` = '1',
    `update_by` = 'SYSTEM',
    `update_time` = CURRENT_TIMESTAMP,
    `remark` = '每天03:30全量同步头程物流渠道；默认暂停，确认领星接口配置后启用'
WHERE `invoke_target` IN (
  'operationSyncTask.syncLingxingLogisticsChannel',
  'operationSyncTask.syncLingxingLogisticsChannel()'
);

INSERT INTO `sys_job` (
  `job_name`, `job_group`, `invoke_target`, `cron_expression`,
  `misfire_policy`, `concurrent`, `status`,
  `create_by`, `create_time`, `update_by`, `update_time`, `remark`
)
SELECT
  '领星-头程物流渠道', 'OPERATION',
  'operationSyncTask.syncLingxingLogisticsChannel()', '0 30 3 * * ?',
  '1', '1', '1',
  'SYSTEM', CURRENT_TIMESTAMP, 'SYSTEM', CURRENT_TIMESTAMP,
  '每天03:30全量同步头程物流渠道；默认暂停，确认领星接口配置后启用'
WHERE NOT EXISTS (
  SELECT 1 FROM `sys_job`
  WHERE `invoke_target` IN (
    'operationSyncTask.syncLingxingLogisticsChannel',
    'operationSyncTask.syncLingxingLogisticsChannel()'
  )
);

-- ============================================================
-- 三、部署检查
-- ============================================================
SELECT `menu_id`, `menu_name`, `parent_id`, `path`, `component`,
       `menu_type`, `visible`, `status`, `perms`
FROM `sys_menu`
WHERE `menu_id` = @sta_page_id OR `parent_id` = @sta_page_id
ORDER BY `menu_type`, `order_num`, `menu_id`;

SELECT u.`user_name`, ur.`role_id`, m.`menu_name`, m.`perms`
FROM `sys_user` u
INNER JOIN `sys_user_role` ur ON ur.`user_id` = u.`user_id`
INNER JOIN `sys_role_menu` rm ON rm.`role_id` = ur.`role_id`
INNER JOIN `sys_menu` m ON m.`menu_id` = rm.`menu_id`
WHERE u.`user_name` = 'leiyongyu'
  AND (m.`menu_id` = @sta_page_id OR m.`parent_id` = @sta_page_id)
ORDER BY ur.`role_id`, m.`menu_type`, m.`order_num`;

SELECT `job_id`, `job_name`, `invoke_target`, `cron_expression`, `status`, `remark`
FROM `sys_job`
WHERE `invoke_target` IN (
  'operationSyncTask.runStaShipmentChain()',
  'operationSyncTask.syncLingxingLogisticsChannel()'
)
ORDER BY `job_id`;
