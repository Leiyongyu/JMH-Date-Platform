-- Target DB: jmh_data_platform (Java ERP). Pure ASCII on purpose (Windows mysql client defaults to gbk).
-- Grants the page "Finance center > eBay monthly profit statement" to the role whose role_key is '2'
-- (role_name: general administration / finance), which already has the finance center root and the project
-- profit statement together with both of its buttons.
-- 20261117_ebay_monthly_profit_menu.sql granted this module to admin only. Finance asked for the same access
-- they already have on the project profit statement, so the page and BOTH buttons are granted here, at the
-- same granularity. RuoYi builds its routes from the root down, so the finance center root must be granted
-- too; it already is for this role, and is included only as a safety net.
-- The role is looked up by role_key and the menus by perms, so no id is hard coded and the script is portable
-- between this machine and the deployment machine. If the role is missing, the insert matches nothing and
-- nothing changes.
-- Idempotent; grants only -- it revokes nothing and touches no other role.
USE `jmh_data_platform`;
SET NAMES utf8mb4;
START TRANSACTION;

SET @role := (
  SELECT role_id FROM sys_role WHERE role_key = '2' AND del_flag = '0' ORDER BY role_id LIMIT 1
);
SET @finance_root := (
  SELECT menu_id FROM sys_menu WHERE parent_id = 0 AND menu_type = 'M' AND path = 'finance-center'
  ORDER BY menu_id LIMIT 1
);

INSERT INTO sys_role_menu(role_id, menu_id)
SELECT @role, m.menu_id
FROM sys_menu m
WHERE @role IS NOT NULL
  AND (m.menu_id = @finance_root OR m.perms LIKE 'finance:ebayMonthlyProfit:%')
  AND NOT EXISTS(
    SELECT 1 FROM sys_role_menu rm WHERE rm.role_id = @role AND rm.menu_id = m.menu_id
  );

COMMIT;

-- Check: the role should now hold the finance center root plus the three menus of this module.
SELECT r.role_id, r.role_key, r.role_name, m.menu_id, m.menu_name, IFNULL(m.perms, '') AS perms
FROM sys_role_menu rm
JOIN sys_role r ON r.role_id = rm.role_id
JOIN sys_menu m ON m.menu_id = rm.menu_id
WHERE r.role_key = '2'
  AND (m.path = 'finance-center' OR m.perms LIKE 'finance:ebayMonthlyProfit:%')
ORDER BY m.menu_id;
