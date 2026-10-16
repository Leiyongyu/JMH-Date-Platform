-- eBay补货2.0：新增独立“导出”按钮权限，并把41项导出字段移动到其下。
-- 先执行 20261016_ebay_replenishment_v2_export_columns.sql，再执行本文件。
-- 只调整sys_menu父级和新增总开关授权，不修改表结构、不更改已有字段勾选。
-- 首次新增总开关时，仅为同时拥有页面查看和至少一个有效导出字段的有效角色保留导出能力。
-- 重复执行不补回后来取消的总开关或字段权限；执行后账号退出重新登录。
USE `jmh_data_platform`;
SET NAMES utf8mb4;
START TRANSACTION;

SET @ebay_export_page_id := (
    SELECT menu_id FROM sys_menu
    WHERE perms='operations:ebayReplenishmentV2:list' AND menu_type='C' AND status='0'
    ORDER BY menu_id LIMIT 1
);
SET @ebay_export_button_is_new := NOT EXISTS (
    SELECT 1 FROM sys_menu WHERE perms='operations:ebayReplenishmentV2:export'
);
INSERT INTO sys_menu (
    menu_name,parent_id,order_num,path,component,query,route_name,
    is_frame,is_cache,menu_type,visible,status,perms,icon,create_by,create_time,remark
)
SELECT '导出',@ebay_export_page_id,40,'',NULL,NULL,'',1,0,'F','0','0',
       'operations:ebayReplenishmentV2:export','#','SYSTEM',NOW(),
       '控制eBay补货2.0导出按钮和接口；下级字段权限只控制Excel列，不影响页面查看'
WHERE @ebay_export_page_id IS NOT NULL AND @ebay_export_button_is_new=1;

SET @ebay_export_button_id := (
    SELECT menu_id FROM sys_menu
    WHERE perms='operations:ebayReplenishmentV2:export'
      AND parent_id=@ebay_export_page_id AND menu_type='F'
    ORDER BY menu_id LIMIT 1
);

UPDATE sys_menu
SET parent_id=@ebay_export_button_id,update_by='SYSTEM',update_time=NOW()
WHERE parent_id=@ebay_export_page_id AND menu_type='F'
  AND perms LIKE 'operations:ebayReplenishmentV2:exportColumn:%'
  AND @ebay_export_button_id IS NOT NULL;

INSERT INTO sys_role_menu (role_id,menu_id)
SELECT DISTINCT r.role_id,@ebay_export_button_id
FROM sys_role r
JOIN sys_role_menu page_grant ON page_grant.role_id=r.role_id AND page_grant.menu_id=@ebay_export_page_id
JOIN sys_role_menu field_grant ON field_grant.role_id=r.role_id
JOIN sys_menu field ON field.menu_id=field_grant.menu_id AND field.parent_id=@ebay_export_button_id
    AND field.menu_type='F' AND field.status='0'
    AND field.perms LIKE 'operations:ebayReplenishmentV2:exportColumn:%'
WHERE r.status='0' AND r.del_flag='0' AND @ebay_export_button_is_new=1
  AND @ebay_export_button_id IS NOT NULL
  AND NOT EXISTS (
      SELECT 1 FROM sys_role_menu existing
      WHERE existing.role_id=r.role_id AND existing.menu_id=@ebay_export_button_id
  );
COMMIT;

-- 正常应返回“导出”按钮一行，export_field_count=41；无结果时核对前置字段脚本/页面菜单。
SELECT button.menu_id,button.menu_name,button.parent_id,button.perms,COUNT(field.menu_id) AS export_field_count
FROM sys_menu button
LEFT JOIN sys_menu field ON field.parent_id=button.menu_id AND field.menu_type='F'
    AND field.perms LIKE 'operations:ebayReplenishmentV2:exportColumn:%'
WHERE button.menu_id=@ebay_export_button_id
GROUP BY button.menu_id,button.menu_name,button.parent_id,button.perms;
