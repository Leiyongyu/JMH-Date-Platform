-- 目标库：jmh_data_platform（Java ERP）。
-- 功能：eBay补货2.0 新增导出字段「待出库」（锁定量，紧跟「海外可售」）的导出字段权限。
--       页面展示不受此权限控制；只有勾选了该权限的角色导出 Excel 时才包含这一列。
-- 授权：与 20261016_ebay_replenishment_v2_export_columns.sql 一致——首次创建时，
--       为已有补货2.0页面查看权限的有效角色授予；重复执行不会重新勾选管理员已取消的授权。
-- 依赖：20261016_ebay_replenishment_v2_export_columns.sql、20261016_ebay_replenishment_v2_export_menu.sql。
-- 安全性：只新增 1 条 sys_menu 按钮权限和对应 sys_role_menu，不改其他菜单和业务数据。可重复执行。
USE `jmh_data_platform`;
SET NAMES utf8mb4;

START TRANSACTION;
SET @ebay_export_page_id := (
    SELECT menu_id FROM sys_menu
    WHERE perms='operations:ebayReplenishmentV2:list' AND menu_type='C' AND status='0'
    ORDER BY menu_id LIMIT 1
);
SET @ebay_export_field_parent_id := COALESCE((
    SELECT menu_id FROM sys_menu
    WHERE perms='operations:ebayReplenishmentV2:export' AND parent_id=@ebay_export_page_id AND menu_type='F'
    ORDER BY menu_id LIMIT 1
), @ebay_export_page_id);
SET @pending_outbound_is_new := NOT EXISTS (
    SELECT 1 FROM sys_menu
    WHERE perms='operations:ebayReplenishmentV2:exportColumn:pending_outbound_quantity'
);

INSERT INTO sys_menu (
    menu_name,parent_id,order_num,path,component,query,route_name,
    is_frame,is_cache,menu_type,visible,status,perms,icon,create_by,create_time,remark
)
SELECT '导出字段-待出库',@ebay_export_field_parent_id,127,'',NULL,NULL,'',
       1,0,'F','0','0','operations:ebayReplenishmentV2:exportColumn:pending_outbound_quantity',
       '#','SYSTEM',NOW(),'只控制补货2.0 Excel导出列，不控制页面展示；待出库=周快照锁定量'
WHERE @pending_outbound_is_new AND @ebay_export_page_id IS NOT NULL;

INSERT INTO sys_role_menu (role_id,menu_id)
SELECT DISTINCT r.role_id,m.menu_id
FROM sys_role r
JOIN sys_role_menu page_grant ON page_grant.role_id=r.role_id AND page_grant.menu_id=@ebay_export_page_id
JOIN sys_menu m ON m.parent_id=@ebay_export_field_parent_id AND m.menu_type='F' AND m.status='0'
    AND m.perms='operations:ebayReplenishmentV2:exportColumn:pending_outbound_quantity'
WHERE @pending_outbound_is_new AND r.status='0' AND r.del_flag='0'
  AND NOT EXISTS (
      SELECT 1 FROM sys_role_menu existing WHERE existing.role_id=r.role_id AND existing.menu_id=m.menu_id
  );
COMMIT;

-- 应返回1；返回0时检查补货2.0主菜单是否已部署。
SELECT COUNT(*) AS pending_outbound_export_permission
FROM sys_menu
WHERE perms='operations:ebayReplenishmentV2:exportColumn:pending_outbound_quantity'
  AND parent_id=@ebay_export_field_parent_id AND status='0' AND menu_type='F';
-- 角色配置后，账号退出重新登录以刷新权限。
