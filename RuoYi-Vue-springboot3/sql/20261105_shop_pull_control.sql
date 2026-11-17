-- Target DB: jmh_data_platform (Java ERP). Pure ASCII: Chinese text is written as UTF-8 hex literals.
-- Store pull control: shop_list gets pull switch / stop reason / stop date and a Lingxing-presence flag.
-- Lingxing pull tasks (Java selectSidsByPlatform, Python shop_pull) skip stores with pull_enabled=0 or
-- lingxing_present=0; monthly pulls still include a stopped store for months starting before pull_stop_date.
-- Existing business data is not changed. Also adds menu Operations > Sync > Store management (admin only).
-- Safe to re-run. Execute BEFORE deploying the matching Java build (its SQL reads the new columns).
USE jmh_data_platform;
SET NAMES utf8mb4;

-- 1) columns (idempotent: only added when missing)
SET @ddl := IF((SELECT COUNT(*) FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='shop_list' AND COLUMN_NAME='pull_enabled')=0,
  CONCAT('ALTER TABLE shop_list ADD COLUMN pull_enabled TINYINT NOT NULL DEFAULT 1 COMMENT ''', CONVERT(X'E698AFE590A6E59091E9A286E6989FE68B89E58F96E8AFA5E5BA97E993BAE695B0E68DAEEFBC9A31E68B89E58F962030E5819CE6ADA2E68B89E58F96EFBC88E5BA97E993BAE7AEA1E79086E9A1B5E99DA2E7BBB4E68AA4EFBC8CE58E86E58FB2E695B0E68DAEE4BF9DE79599EFBC8CE9A286E6989FE5BA97E993BAE5908CE6ADA5E4B88DE8A686E79B96EFBC89' USING utf8mb4), ''' AFTER status'),
  'SELECT 1');
PREPARE stmt FROM @ddl; EXECUTE stmt; DEALLOCATE PREPARE stmt;
SET @ddl := IF((SELECT COUNT(*) FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='shop_list' AND COLUMN_NAME='pull_stop_reason')=0,
  CONCAT('ALTER TABLE shop_list ADD COLUMN pull_stop_reason VARCHAR(200) NULL COMMENT ''', CONVERT(X'E5819CE6ADA2E68B89E58F96E58E9FE59BA0EFBC88E5A682E5B081E5BA97E38081E5819CE5BA97E38081E59BBDE58685E4B8BBE4BD93E6B3A8E99480EFBC89' USING utf8mb4), ''' AFTER pull_enabled'),
  'SELECT 1');
PREPARE stmt FROM @ddl; EXECUTE stmt; DEALLOCATE PREPARE stmt;
SET @ddl := IF((SELECT COUNT(*) FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='shop_list' AND COLUMN_NAME='pull_stop_date')=0,
  CONCAT('ALTER TABLE shop_list ADD COLUMN pull_stop_date DATE NULL COMMENT ''', CONVERT(X'E5819CE6ADA2E68B89E58F96E7949FE69588E697A5E69C9FEFBC9AE68C89E69C88E68B89E58F96E79A84E4BBBBE58AA1E5AFB9E5BC80E5A78BE4BA8EE8AFA5E697A5E69C9FE4B98BE5898DE79A84E69C88E4BBBDE4BB8DE4BC9AE68B89E58F96' USING utf8mb4), ''' AFTER pull_stop_reason'),
  'SELECT 1');
PREPARE stmt FROM @ddl; EXECUTE stmt; DEALLOCATE PREPARE stmt;
SET @ddl := IF((SELECT COUNT(*) FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='shop_list' AND COLUMN_NAME='pull_updated_by')=0,
  CONCAT('ALTER TABLE shop_list ADD COLUMN pull_updated_by VARCHAR(64) NULL COMMENT ''', CONVERT(X'E69C80E5908EE4BFAEE694B9E68B89E58F96E5BC80E585B3E79A84E794A8E688B7' USING utf8mb4), ''' AFTER pull_stop_date'),
  'SELECT 1');
PREPARE stmt FROM @ddl; EXECUTE stmt; DEALLOCATE PREPARE stmt;
SET @ddl := IF((SELECT COUNT(*) FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='shop_list' AND COLUMN_NAME='pull_updated_at')=0,
  CONCAT('ALTER TABLE shop_list ADD COLUMN pull_updated_at DATETIME NULL COMMENT ''', CONVERT(X'E69C80E5908EE4BFAEE694B9E68B89E58F96E5BC80E585B3E79A84E697B6E997B4' USING utf8mb4), ''' AFTER pull_updated_by'),
  'SELECT 1');
PREPARE stmt FROM @ddl; EXECUTE stmt; DEALLOCATE PREPARE stmt;
SET @ddl := IF((SELECT COUNT(*) FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='shop_list' AND COLUMN_NAME='lingxing_present')=0,
  CONCAT('ALTER TABLE shop_list ADD COLUMN lingxing_present TINYINT NOT NULL DEFAULT 1 COMMENT ''', CONVERT(X'E69C80E8BF91E4B880E6ACA1E5AE8CE695B4E79A84E9A286E6989FE5BA97E993BAE5908CE6ADA5E698AFE590A6E8BF94E59B9EE8AFA5E5BA97E993BAEFBC9A31E698AF2030E9A286E6989FE5B7B2E7A7BBE999A4EFBC88E887AAE58AA8E5819CE6ADA2E68B89E58F96EFBC8CE9878DE696B0E587BAE78EB0E887AAE58AA8E681A2E5A48DEFBC89' USING utf8mb4), ''' AFTER pull_updated_at'),
  'SELECT 1');
PREPARE stmt FROM @ddl; EXECUTE stmt; DEALLOCATE PREPARE stmt;
SET @ddl := IF((SELECT COUNT(*) FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='shop_list' AND COLUMN_NAME='lingxing_last_seen_at')=0,
  CONCAT('ALTER TABLE shop_list ADD COLUMN lingxing_last_seen_at DATETIME NULL COMMENT ''', CONVERT(X'E69C80E8BF91E4B880E6ACA1E59CA8E9A286E6989FE5BA97E993BAE58897E8A1A8E4B8ADE587BAE78EB0E79A84E697B6E997B4' USING utf8mb4), ''' AFTER lingxing_present'),
  'SELECT 1');
PREPARE stmt FROM @ddl; EXECUTE stmt; DEALLOCATE PREPARE stmt;

START TRANSACTION;
-- 2) first batch: closed stores stop pulling from 2026-11 (October and earlier months stay pullable)
-- EU-: sid 12598,12599,12600,12601,12602,12603,12604,12605,12662
UPDATE shop_list SET pull_enabled=0, pull_stop_reason=CONVERT(X'E5B081E5BA97EFBC8CE9A286E6989FE695B0E68DAEE5819CE6ADA2E5908CE6ADA5EFBC8CE59BBDE58685E4B8BBE4BD93E5B7B2E6B3A8E99480' USING utf8mb4), pull_stop_date='2026-11-01',
  pull_updated_by='SYSTEM', pull_updated_at=NOW()
WHERE platform_code='10001' AND sid IN (12598,12599,12600,12601,12602,12603,12604,12605,12662) AND pull_enabled=1;
-- US2-: sid 12518,12519
UPDATE shop_list SET pull_enabled=0, pull_stop_reason=CONVERT(X'E5819CE5BA97EFBC8CE9A286E6989FE695B0E68DAEE5819CE6ADA2E5908CE6ADA5EFBC8CE59BBDE58685E4B8BBE4BD93E794B3E8AFB7E6B3A8E99480' USING utf8mb4), pull_stop_date='2026-11-01',
  pull_updated_by='SYSTEM', pull_updated_at=NOW()
WHERE platform_code='10001' AND sid IN (12518,12519) AND pull_enabled=1;
-- US1-: sid 12642,12643,12644
UPDATE shop_list SET pull_enabled=0, pull_stop_reason=CONVERT(X'E5819CE5BA97EFBC8CE9A286E6989FE695B0E68DAEE5819CE6ADA2E5908CE6ADA5EFBC8CE59BBDE58685E4B8BBE4BD93E794B3E8AFB7E6B3A8E99480' USING utf8mb4), pull_stop_date='2026-11-01',
  pull_updated_by='SYSTEM', pull_updated_at=NOW()
WHERE platform_code='10001' AND sid IN (12642,12643,12644) AND pull_enabled=1;

-- 3) stores no longer returned by Lingxing (checked 2026-11-05: CHENSUL x8, US1 John x3); later syncs auto-mark
UPDATE shop_list SET lingxing_present=0 WHERE platform_code='10001' AND sid IN (14114,14115,14116,14117,14118,14119,14120,14121,13378,13379,13380);

-- 4) menu: Operations > Sync management > Store management + edit button, admin only
SET @sync_dir := (
  SELECT m.menu_id FROM sys_menu m JOIN sys_menu p ON p.menu_id=m.parent_id
  WHERE m.path='sync' AND m.menu_type='M' AND p.path='operations' ORDER BY m.menu_id LIMIT 1
);
INSERT INTO sys_menu(menu_name,parent_id,order_num,path,component,route_name,menu_type,visible,status,is_frame,is_cache,perms,icon,create_by,create_time,remark)
SELECT CONVERT(X'E5BA97E993BAE7AEA1E79086' USING utf8mb4),@sync_dir,2,'shop','operations/sync/shop/index','ShopPull','C','0','0',1,1,
  'operations:shopPull:list','shopping','SYSTEM',NOW(),CONVERT(X'E68EA7E588B6E6AF8FE4B8AAE5BA97E993BAE698AFE590A6E7BBA7E7BBADE59091E9A286E6989FE68B89E58F96E695B0E68DAEEFBC88E5819CE6ADA2E68B89E58F96E4B88DE5BDB1E5938DE58E86E58FB2E695B0E68DAEEFBC89' USING utf8mb4)
WHERE @sync_dir IS NOT NULL AND NOT EXISTS(SELECT 1 FROM sys_menu WHERE perms='operations:shopPull:list');
SET @shop_page := (SELECT menu_id FROM sys_menu WHERE perms='operations:shopPull:list' ORDER BY menu_id LIMIT 1);
INSERT INTO sys_menu(menu_name,parent_id,order_num,path,menu_type,visible,status,is_frame,is_cache,perms,icon,create_by,create_time)
SELECT CONVERT(X'E4BFAEE694B9E68B89E58F96E5BC80E585B3' USING utf8mb4),@shop_page,1,'#','F','0','0',1,0,'operations:shopPull:edit','#','SYSTEM',NOW()
WHERE @shop_page IS NOT NULL AND NOT EXISTS(SELECT 1 FROM sys_menu WHERE perms='operations:shopPull:edit');
SET @shop_edit := (SELECT menu_id FROM sys_menu WHERE perms='operations:shopPull:edit' ORDER BY menu_id LIMIT 1);
INSERT INTO sys_role_menu(role_id,menu_id)
SELECT r.role_id,m.menu_id FROM sys_role r
JOIN sys_menu m ON m.menu_id IN (@sync_dir,@shop_page,@shop_edit)
WHERE r.role_key='admin' AND r.del_flag='0'
  AND NOT EXISTS(SELECT 1 FROM sys_role_menu e WHERE e.role_id=r.role_id AND e.menu_id=m.menu_id);
COMMIT;
