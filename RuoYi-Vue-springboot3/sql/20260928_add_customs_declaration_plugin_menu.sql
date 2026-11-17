-- JMH 报关单生成器：在 SOP 的“插件菜单”（原脚本菜单）中注册一张功能卡片权限。
-- 不创建根菜单，不创建侧栏 C 路由；卡片由 Date-Project/frontend/src/scripts.js 注册。
-- 目标库：jmh_data_platform，MySQL 8.0+。

USE jmh_data_platform;
SET NAMES utf8mb4;

DROP PROCEDURE IF EXISTS sp_install_customs_declaration_script_card;
DELIMITER $$

CREATE PROCEDURE sp_install_customs_declaration_script_card()
main: BEGIN
    DECLARE v_parent_count INT DEFAULT 0;
    DECLARE v_script_tools_menu_id BIGINT DEFAULT NULL;
    DECLARE v_card_count INT DEFAULT 0;
    DECLARE v_card_menu_id BIGINT DEFAULT NULL;
    DECLARE v_card_order INT DEFAULT 1;

    -- 以稳定权限标识定位父节点，允许管理员把“脚本菜单”改名为“插件菜单”。
    SELECT COUNT(*), MIN(menu_id)
      INTO v_parent_count, v_script_tools_menu_id
    FROM sys_menu
    WHERE menu_type = 'C'
      AND perms = 'sop:scriptTools:view'
      AND status = '0';

    IF v_parent_count <> 1 THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'Expected exactly one enabled sop:scriptTools:view parent menu';
    END IF;

    SELECT COUNT(*), MIN(menu_id)
      INTO v_card_count, v_card_menu_id
    FROM sys_menu
    WHERE parent_id = v_script_tools_menu_id
      AND menu_type = 'F'
      AND perms = 'customs:declaration:query';

    IF v_card_count > 1 THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'Duplicate customs declaration cards found under script tools';
    END IF;

    SELECT COALESCE(MAX(order_num), 0) + 1
      INTO v_card_order
    FROM sys_menu
    WHERE parent_id = v_script_tools_menu_id
      AND (v_card_menu_id IS NULL OR menu_id <> v_card_menu_id);

    IF v_card_menu_id IS NULL THEN
        INSERT INTO sys_menu (
            menu_name, parent_id, order_num, path, component, query, route_name,
            is_frame, is_cache, menu_type, visible, status, perms, icon,
            create_by, create_time, remark
        ) VALUES (
            '报关单生成器', v_script_tools_menu_id, v_card_order,
            '', NULL, NULL, '', 1, 0, 'F', '0', '0',
            'customs:declaration:query', '#', 'SYSTEM', NOW(),
            'SOP 插件工作台报关单生成器卡片；经 ERP 安全代理打开独立报关单系统'
        );
        SET v_card_menu_id = LAST_INSERT_ID();
    ELSE
        UPDATE sys_menu
        SET menu_name = '报关单生成器',
            parent_id = v_script_tools_menu_id,
            order_num = v_card_order,
            path = '',
            component = NULL,
            query = NULL,
            route_name = '',
            is_frame = 1,
            is_cache = 0,
            menu_type = 'F',
            visible = '0',
            status = '0',
            perms = 'customs:declaration:query',
            icon = '#',
            update_by = 'SYSTEM',
            update_time = NOW(),
            remark = 'SOP 插件工作台报关单生成器卡片；经 ERP 安全代理打开独立报关单系统'
        WHERE menu_id = v_card_menu_id;
    END IF;

    -- 只给同时拥有插件菜单和既有报关查询权限的角色添加卡片节点。
    INSERT IGNORE INTO sys_role_menu (role_id, menu_id)
    SELECT DISTINCT parent_grant.role_id, v_card_menu_id
    FROM sys_role_menu parent_grant
    JOIN sys_role r
      ON r.role_id = parent_grant.role_id
     AND r.status = '0'
     AND r.del_flag = '0'
    WHERE parent_grant.menu_id = v_script_tools_menu_id
      AND EXISTS (
          SELECT 1
          FROM sys_role_menu query_grant
          JOIN sys_menu query_menu ON query_menu.menu_id = query_grant.menu_id
          WHERE query_grant.role_id = parent_grant.role_id
            AND query_menu.perms = 'customs:declaration:query'
            AND query_menu.menu_id <> v_card_menu_id
      );
END$$

DELIMITER ;
CALL sp_install_customs_declaration_script_card();
DROP PROCEDURE IF EXISTS sp_install_customs_declaration_script_card;

-- 验收 1：层级必须是 SOP -> 插件菜单(script-tools) -> 报关单生成器(F)。
SELECT sop.menu_id AS sop_menu_id, sop.menu_name AS sop_menu_name,
       tools.menu_id AS tools_menu_id, tools.menu_name AS tools_menu_name,
       tools.path AS tools_path, tools.component AS tools_component,
       card.menu_id AS card_menu_id, card.menu_name AS card_menu_name,
       card.menu_type AS card_menu_type, card.perms AS card_permission,
       card.order_num AS card_order
FROM sys_menu card
JOIN sys_menu tools ON tools.menu_id = card.parent_id
JOIN sys_menu sop ON sop.menu_id = tools.parent_id
WHERE tools.perms = 'sop:scriptTools:view'
  AND card.menu_type = 'F'
  AND card.perms = 'customs:declaration:query';

-- 验收 2：只应列出原本同时具有插件菜单与报关查询权限的角色。
SELECT r.role_id, r.role_name, r.role_key, card.menu_id, card.menu_name, card.perms
FROM sys_role_menu rm
JOIN sys_role r ON r.role_id = rm.role_id
JOIN sys_menu card ON card.menu_id = rm.menu_id
WHERE card.parent_id = (
        SELECT menu_id FROM sys_menu
        WHERE menu_type = 'C' AND perms = 'sop:scriptTools:view'
        LIMIT 1
      )
  AND card.menu_type = 'F'
  AND card.perms = 'customs:declaration:query'
ORDER BY r.role_id;

-- 验收 3：以下问题数必须全部为 0。
SELECT 'duplicate_card' AS check_name, GREATEST(COUNT(*) - 1, 0) AS problem_count
FROM sys_menu card
JOIN sys_menu tools ON tools.menu_id = card.parent_id
WHERE tools.perms = 'sop:scriptTools:view'
  AND card.menu_type = 'F'
  AND card.perms = 'customs:declaration:query'
UNION ALL
SELECT 'wrong_root_plugin_menu', COUNT(*)
FROM sys_menu
WHERE parent_id = 0 AND path = 'plugins'
UNION ALL
SELECT 'unexpected_sidebar_route', COUNT(*)
FROM sys_menu
WHERE route_name = 'PluginCustomsDeclaration';
