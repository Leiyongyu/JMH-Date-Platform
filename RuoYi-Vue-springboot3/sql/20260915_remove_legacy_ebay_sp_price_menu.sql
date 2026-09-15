-- 下线旧SOP「eBay SP价格批量审核」入口，不影响脚本菜单的新组件。
-- 只删除sys_menu与对应sys_role_menu；历史业务表不删除、不清空。
-- 已有菜单按精确权限/路由定位，不依赖不同环境中的menu_id。
SET NAMES utf8mb4;
USE `jmh_data_platform`;

-- 持久备份：重复执行只补缺失记录，不覆盖第一次备份。
CREATE TABLE IF NOT EXISTS bak_sys_menu_ebay_sp_20260915 LIKE sys_menu;
CREATE TABLE IF NOT EXISTS bak_sys_role_menu_ebay_sp_20260915 LIKE sys_role_menu;

DROP TEMPORARY TABLE IF EXISTS tmp_ebay_sp_retired_menu;
CREATE TEMPORARY TABLE tmp_ebay_sp_retired_menu (menu_id BIGINT NOT NULL PRIMARY KEY);
DROP TEMPORARY TABLE IF EXISTS tmp_ebay_sp_cleanup_guard;
CREATE TEMPORARY TABLE tmp_ebay_sp_cleanup_guard (id INT NOT NULL PRIMARY KEY);
INSERT INTO tmp_ebay_sp_cleanup_guard VALUES (1);

START TRANSACTION;
INSERT INTO tmp_ebay_sp_retired_menu(menu_id)
SELECT menu_id FROM sys_menu
WHERE menu_type IN ('C','F')
  AND COALESCE(perms,'') NOT IN ('sop:scriptTools:view','sop:ebayTool:use')
  AND (
    perms IN ('scripts:ebayPrice:list','scripts:ebayPrice:query',
              'scripts:ebayPrice:import','scripts:ebayPrice:export')
    OR (menu_type='C' AND (
      component='scripts/ebayPrice/index' OR path='ebay-sp-price' OR route_name='EbaySpPrice'
    ))
  );

-- 如旧菜单下挂了不属于本功能的子菜单，拒绝删除，先人工迁移这些子菜单。
-- 安全检查仅引用一次目标临时表，兼容MySQL临时表使用限制。
SET @ebay_sp_cleanup_safe := NOT EXISTS (
  SELECT 1
  FROM sys_menu child
  JOIN tmp_ebay_sp_retired_menu parent ON child.parent_id=parent.menu_id
  WHERE NOT (
    COALESCE(child.menu_type,'') IN ('C','F')
    AND COALESCE(child.perms,'') NOT IN ('sop:scriptTools:view','sop:ebayTool:use')
    AND (
      COALESCE(child.perms,'') IN ('scripts:ebayPrice:list','scripts:ebayPrice:query',
                                 'scripts:ebayPrice:import','scripts:ebayPrice:export')
      OR (child.menu_type='C' AND (
        COALESCE(child.component,'')='scripts/ebayPrice/index'
        OR COALESCE(child.path,'')='ebay-sp-price'
        OR COALESCE(child.route_name,'')='EbaySpPrice'
      ))
    )
  )
);
-- 若此处出现Duplicate entry错误，即安全检查未通过；后续DELETE也以safe=1为前提。
INSERT INTO tmp_ebay_sp_cleanup_guard(id)
SELECT 1 WHERE @ebay_sp_cleanup_safe=0;

SELECT m.menu_id,m.parent_id,m.menu_name,m.perms
FROM sys_menu m JOIN tmp_ebay_sp_retired_menu t ON t.menu_id=m.menu_id
ORDER BY m.parent_id,m.menu_id;

INSERT IGNORE INTO bak_sys_menu_ebay_sp_20260915
SELECT m.* FROM sys_menu m JOIN tmp_ebay_sp_retired_menu t ON t.menu_id=m.menu_id
WHERE @ebay_sp_cleanup_safe=1;
INSERT IGNORE INTO bak_sys_role_menu_ebay_sp_20260915
SELECT rm.* FROM sys_role_menu rm JOIN tmp_ebay_sp_retired_menu t ON t.menu_id=rm.menu_id
WHERE @ebay_sp_cleanup_safe=1;

DELETE rm FROM sys_role_menu rm
JOIN tmp_ebay_sp_retired_menu t ON t.menu_id=rm.menu_id
WHERE @ebay_sp_cleanup_safe=1;
SELECT ROW_COUNT() AS removed_role_permissions;
DELETE m FROM sys_menu m
JOIN tmp_ebay_sp_retired_menu t ON t.menu_id=m.menu_id
WHERE @ebay_sp_cleanup_safe=1;
SELECT ROW_COUNT() AS removed_menus;
COMMIT;

DROP TEMPORARY TABLE tmp_ebay_sp_retired_menu;
DROP TEMPORARY TABLE tmp_ebay_sp_cleanup_guard;

-- 保留的新脚本与脚本菜单，执行后应仍存在，权限分配未修改。
SELECT menu_id,parent_id,menu_name,perms,status
FROM sys_menu WHERE perms IN ('sop:scriptTools:view','sop:ebayTool:use');
