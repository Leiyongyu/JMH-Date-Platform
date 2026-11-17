-- 目标库：jmh_data_platform（Java ERP）。
-- 功能：eBay补货2.0 去掉「待出库」字段后，删除 20261106_ebay_replenishment_v2_pending_outbound_export_column.sql
--       创建的导出字段权限「导出字段-待出库」及其角色授权。
-- 范围：只按 perms='operations:ebayReplenishmentV2:exportColumn:pending_outbound_quantity' 精确匹配，
--       只删这 1 个按钮权限和它的 sys_role_menu 授权；不动其他导出字段、菜单和业务数据。
--       库存明细页自己的「待出库」与此无关，不受影响。可重复执行（没有时删除 0 行）。
USE `jmh_data_platform`;
SET NAMES utf8mb4;

START TRANSACTION;
DELETE rm FROM sys_role_menu rm
JOIN sys_menu m ON m.menu_id=rm.menu_id
WHERE m.perms='operations:ebayReplenishmentV2:exportColumn:pending_outbound_quantity'
  AND m.menu_type='F';

DELETE FROM sys_menu
WHERE perms='operations:ebayReplenishmentV2:exportColumn:pending_outbound_quantity'
  AND menu_type='F';
COMMIT;

-- 应返回0。
SELECT COUNT(*) AS remaining_pending_outbound_export_permission
FROM sys_menu
WHERE perms='operations:ebayReplenishmentV2:exportColumn:pending_outbound_quantity';
-- 角色配置后，账号退出重新登录以刷新权限。
