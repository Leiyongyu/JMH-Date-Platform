-- 回滚 SOP 插件工作台中的“报关单生成器”卡片权限。
-- 不删除 SOP、插件菜单、原运营中心报关入口或任何业务数据。

USE jmh_data_platform;
SET NAMES utf8mb4;

DROP PROCEDURE IF EXISTS sp_rollback_customs_declaration_script_card;
DELIMITER $$

CREATE PROCEDURE sp_rollback_customs_declaration_script_card()
main: BEGIN
    DECLARE v_parent_count INT DEFAULT 0;
    DECLARE v_script_tools_menu_id BIGINT DEFAULT NULL;
    DECLARE v_card_count INT DEFAULT 0;
    DECLARE v_card_menu_id BIGINT DEFAULT NULL;

    SELECT COUNT(*), MIN(menu_id)
      INTO v_parent_count, v_script_tools_menu_id
    FROM sys_menu
    WHERE menu_type = 'C'
      AND perms = 'sop:scriptTools:view';

    IF v_parent_count <> 1 THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'Expected exactly one sop:scriptTools:view parent menu';
    END IF;

    SELECT COUNT(*), MIN(menu_id)
      INTO v_card_count, v_card_menu_id
    FROM sys_menu
    WHERE parent_id = v_script_tools_menu_id
      AND menu_type = 'F'
      AND perms = 'customs:declaration:query';

    IF v_card_count = 0 THEN
        SELECT 'ALREADY_REMOVED' AS result;
        LEAVE main;
    END IF;

    IF v_card_count > 1 THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'Duplicate customs declaration cards found; rollback stopped';
    END IF;

    DELETE FROM sys_role_menu WHERE menu_id = v_card_menu_id;
    DELETE FROM sys_menu WHERE menu_id = v_card_menu_id;

    SELECT 'ROLLED_BACK' AS result,
           'Only the customs declaration workbench card was removed' AS detail;
END$$

DELIMITER ;
CALL sp_rollback_customs_declaration_script_card();
DROP PROCEDURE IF EXISTS sp_rollback_customs_declaration_script_card;

SELECT menu_id, parent_id, menu_name, menu_type, perms
FROM sys_menu
WHERE parent_id = (
        SELECT menu_id FROM sys_menu
        WHERE menu_type = 'C' AND perms = 'sop:scriptTools:view'
        LIMIT 1
      )
  AND perms = 'customs:declaration:query';
