-- 仅扩展历史行标识，保留全部原数据；先部署既有明细历史表。
-- 新生成记录record_key为空，原SKU唯一性不变；Excel导入使用sheet代码:原行号。
USE `date-project`;
SET @history_column_exists = (SELECT COUNT(*) FROM information_schema.COLUMNS
 WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='ebay_inventory_detail_history' AND COLUMN_NAME='record_key');
SET @history_ddl = IF(@history_column_exists=0,
 'ALTER TABLE ebay_inventory_detail_history ADD COLUMN record_key VARCHAR(80) NOT NULL DEFAULT '''' COMMENT ''Excel原始行标识；生成记录为空'' AFTER sku',
 'SELECT ''record_key already exists''');
PREPARE history_stmt FROM @history_ddl;
EXECUTE history_stmt;
DEALLOCATE PREPARE history_stmt;
SET @history_index_old = (SELECT COUNT(*) FROM information_schema.STATISTICS
 WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='ebay_inventory_detail_history' AND INDEX_NAME='uk_inventory_history_sku');
SET @history_ddl = IF(@history_index_old>0,
 'ALTER TABLE ebay_inventory_detail_history DROP INDEX uk_inventory_history_sku, ADD UNIQUE KEY uk_inventory_history_row (snapshot_id,site,sku,record_key)',
 'SELECT ''history row index already migrated''');
PREPARE history_stmt FROM @history_ddl;
EXECUTE history_stmt;
DEALLOCATE PREPARE history_stmt;
SHOW INDEX FROM ebay_inventory_detail_history;
