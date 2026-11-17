-- eBay补货2.0不再上传仓租；在新版前后端部署后执行。
-- 仅清理专用功能权限及角色授权，不影响补货2.0其他菜单。
USE `jmh_data_platform`;

START TRANSACTION;

DELETE rm FROM sys_role_menu rm
JOIN sys_menu m ON m.menu_id = rm.menu_id
WHERE m.menu_type = 'F'
  AND m.perms = 'operations:ebayReplenishmentV2:importWarehouseRent';

DELETE FROM sys_menu
WHERE menu_type = 'F'
  AND perms = 'operations:ebayReplenishmentV2:importWarehouseRent';

COMMIT;
