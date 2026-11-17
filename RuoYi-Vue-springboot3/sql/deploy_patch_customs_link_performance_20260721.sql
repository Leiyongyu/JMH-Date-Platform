/*
 报关数据源关联性能优化。
 1. 将运行时 SKU 标准化结果持久化，确保等值连接可以命中索引。
 2. 为库存扣减、备货单、FBA、采购含税查询补齐组合索引。
 3. 使用触发器兜底维护匹配键；应用导入代码仍应主动写入。

 可重复执行；先执行 deploy_patch_customs_parenthesized_sku_20260721.sql。
*/

SET @sql := IF((SELECT COUNT(*) FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='customs_inventory_list' AND COLUMN_NAME='sku_match_key')=0,
  'ALTER TABLE customs_inventory_list ADD COLUMN sku_match_key varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL COMMENT ''SKU标准匹配键'' AFTER sku',
  'SELECT ''skip customs_inventory_list.sku_match_key''');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @sql := IF((SELECT COUNT(*) FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='overseas_stock_order_detail' AND COLUMN_NAME='sku_match_key')=0,
  'ALTER TABLE overseas_stock_order_detail ADD COLUMN sku_match_key varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL COMMENT ''SKU标准匹配键'' AFTER sku',
  'SELECT ''skip overseas_stock_order_detail.sku_match_key''');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @sql := IF((SELECT COUNT(*) FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='amz_fba_shipment_box' AND COLUMN_NAME='sku_match_key')=0,
  'ALTER TABLE amz_fba_shipment_box ADD COLUMN sku_match_key varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL COMMENT ''SKU标准匹配键'' AFTER sku',
  'SELECT ''skip amz_fba_shipment_box.sku_match_key''');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @sql := IF((SELECT COUNT(*) FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='purchase_order' AND COLUMN_NAME='item_sku_match_key')=0,
  'ALTER TABLE purchase_order ADD COLUMN item_sku_match_key varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL COMMENT ''采购SKU标准匹配键'' AFTER item_sku',
  'SELECT ''skip purchase_order.item_sku_match_key''');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @sql := IF((SELECT COLLATION_NAME FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='purchase_order' AND COLUMN_NAME='item_sku_match_key') <> 'utf8mb4_0900_ai_ci',
  'ALTER TABLE purchase_order MODIFY COLUMN item_sku_match_key varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL COMMENT ''采购SKU标准匹配键''',
  'SELECT ''skip purchase_order.item_sku_match_key collation''');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

UPDATE customs_inventory_list
SET sku_match_key=normalize_customs_sku_key(sku)
WHERE sku IS NOT NULL AND sku<>'' AND NOT (sku_match_key <=> normalize_customs_sku_key(sku));
UPDATE overseas_stock_order_detail
SET sku_match_key=normalize_customs_sku_key(sku)
WHERE sku IS NOT NULL AND sku<>'' AND NOT (sku_match_key <=> normalize_customs_sku_key(sku));
UPDATE amz_fba_shipment_box
SET sku_match_key=normalize_customs_sku_key(sku)
WHERE sku IS NOT NULL AND sku<>'' AND NOT (sku_match_key <=> normalize_customs_sku_key(sku));
UPDATE purchase_order
SET item_sku_match_key=normalize_customs_sku_key(item_sku)
WHERE item_sku IS NOT NULL AND item_sku<>'' AND NOT (item_sku_match_key <=> normalize_customs_sku_key(item_sku));

SET @sql := IF((SELECT COUNT(*) FROM information_schema.STATISTICS WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='customs_inventory_list' AND INDEX_NAME='idx_inventory_match_code')=0,
  'ALTER TABLE customs_inventory_list ADD INDEX idx_inventory_match_code (sku_match_key, product_code, id)',
  'SELECT ''skip idx_inventory_match_code''');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @sql := IF((SELECT COUNT(*) FROM information_schema.STATISTICS WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='overseas_stock_order_detail' AND INDEX_NAME='idx_stock_order_match')=0,
  'ALTER TABLE overseas_stock_order_detail ADD INDEX idx_stock_order_match (overseas_order_no, sku_match_key)',
  'SELECT ''skip idx_stock_order_match''');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @sql := IF((SELECT COUNT(*) FROM information_schema.STATISTICS WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='amz_fba_shipment_box' AND INDEX_NAME='idx_fba_shipment_match')=0,
  'ALTER TABLE amz_fba_shipment_box ADD INDEX idx_fba_shipment_match (shipment_id, sku_match_key)',
  'SELECT ''skip idx_fba_shipment_match''');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @sql := IF((SELECT COUNT(*) FROM information_schema.STATISTICS WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='purchase_order' AND INDEX_NAME='idx_purchase_match_tax')=0,
  'ALTER TABLE purchase_order ADD INDEX idx_purchase_match_tax (item_sku_match_key, wid, is_tax)',
  'SELECT ''skip idx_purchase_match_tax''');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @sql := IF((SELECT COUNT(*) FROM information_schema.STATISTICS WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='customs_declaration_generate_log' AND INDEX_NAME='idx_decl_used_qty')=0,
  'ALTER TABLE customs_declaration_generate_log ADD INDEX idx_decl_used_qty (standard_sku, product_code, warehouse_bucket)',
  'SELECT ''skip idx_decl_used_qty''');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

DROP TRIGGER IF EXISTS trg_customs_inventory_match_key_bi;
DROP TRIGGER IF EXISTS trg_customs_inventory_match_key_bu;
DROP TRIGGER IF EXISTS trg_stock_detail_match_key_bi;
DROP TRIGGER IF EXISTS trg_stock_detail_match_key_bu;
DROP TRIGGER IF EXISTS trg_fba_box_match_key_bi;
DROP TRIGGER IF EXISTS trg_fba_box_match_key_bu;
DROP TRIGGER IF EXISTS trg_purchase_match_key_bi;
DROP TRIGGER IF EXISTS trg_purchase_match_key_bu;

DELIMITER $$
CREATE TRIGGER trg_customs_inventory_match_key_bi BEFORE INSERT ON customs_inventory_list FOR EACH ROW
BEGIN SET NEW.sku_match_key=normalize_customs_sku_key(NEW.sku); END$$
CREATE TRIGGER trg_customs_inventory_match_key_bu BEFORE UPDATE ON customs_inventory_list FOR EACH ROW
BEGIN IF NOT (NEW.sku <=> OLD.sku) THEN SET NEW.sku_match_key=normalize_customs_sku_key(NEW.sku); END IF; END$$
CREATE TRIGGER trg_stock_detail_match_key_bi BEFORE INSERT ON overseas_stock_order_detail FOR EACH ROW
BEGIN SET NEW.sku_match_key=normalize_customs_sku_key(NEW.sku); END$$
CREATE TRIGGER trg_stock_detail_match_key_bu BEFORE UPDATE ON overseas_stock_order_detail FOR EACH ROW
BEGIN IF NOT (NEW.sku <=> OLD.sku) THEN SET NEW.sku_match_key=normalize_customs_sku_key(NEW.sku); END IF; END$$
CREATE TRIGGER trg_fba_box_match_key_bi BEFORE INSERT ON amz_fba_shipment_box FOR EACH ROW
BEGIN SET NEW.sku_match_key=normalize_customs_sku_key(NEW.sku); END$$
CREATE TRIGGER trg_fba_box_match_key_bu BEFORE UPDATE ON amz_fba_shipment_box FOR EACH ROW
BEGIN IF NOT (NEW.sku <=> OLD.sku) THEN SET NEW.sku_match_key=normalize_customs_sku_key(NEW.sku); END IF; END$$
CREATE TRIGGER trg_purchase_match_key_bi BEFORE INSERT ON purchase_order FOR EACH ROW
BEGIN SET NEW.item_sku_match_key=normalize_customs_sku_key(NEW.item_sku); END$$
CREATE TRIGGER trg_purchase_match_key_bu BEFORE UPDATE ON purchase_order FOR EACH ROW
BEGIN IF NOT (NEW.item_sku <=> OLD.item_sku) THEN SET NEW.item_sku_match_key=normalize_customs_sku_key(NEW.item_sku); END IF; END$$
DELIMITER ;
