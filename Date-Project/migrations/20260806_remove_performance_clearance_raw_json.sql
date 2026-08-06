-- 最终结构化迁移：先执行 20260806_structure_required_ods_fields.sql，再执行本文件。
-- 本文件会删除绩效排名、滞销清货相关表的 raw_json 字段；执行前必须完成备份。

ALTER TABLE ods_ebay_monthly_profit_raw
    ADD COLUMN sku VARCHAR(255) NULL COMMENT 'SKU' AFTER source_row,
    ADD COLUMN brand_code VARCHAR(64) NULL COMMENT '品牌码' AFTER sku,
    ADD COLUMN image_url VARCHAR(1000) NULL COMMENT '图片' AFTER brand_code,
    ADD COLUMN multi_variant VARCHAR(32) NULL COMMENT '是否多属性' AFTER image_url,
    ADD COLUMN gross_profit DECIMAL(20,6) NULL COMMENT '利润' AFTER multi_variant,
    ADD COLUMN product_sales_amount DECIMAL(20,6) NULL COMMENT '商品销售额' AFTER gross_profit,
    ADD COLUMN receivable_shipping_amount DECIMAL(20,6) NULL COMMENT '应收运费' AFTER product_sales_amount,
    ADD COLUMN sales_amount DECIMAL(20,6) NULL COMMENT '销售额' AFTER receivable_shipping_amount,
    ADD COLUMN refund_amount DECIMAL(20,6) NULL COMMENT '退款金额' AFTER sales_amount,
    ADD COLUMN net_sales_amount DECIMAL(20,6) NULL COMMENT '净销售额' AFTER refund_amount;

UPDATE ods_ebay_monthly_profit_raw o
JOIN dwd_ebay_monthly_profit d
  ON d.stat_month=o.stat_month
 AND d.source_file_name <=> o.source_file_name
 AND d.source_sheet <=> o.source_sheet
 AND d.source_row <=> o.source_row
 AND d.import_batch_id <=> o.import_batch_id
SET o.sku=d.sku,
    o.brand_code=d.brand_code,
    o.image_url=d.image_url,
    o.multi_variant=d.multi_variant,
    o.gross_profit=d.gross_profit,
    o.product_sales_amount=d.product_sales_amount,
    o.receivable_shipping_amount=d.receivable_shipping_amount,
    o.sales_amount=d.sales_amount,
    o.refund_amount=d.refund_amount,
    o.net_sales_amount=d.net_sales_amount;

-- 负责人历史 SOURCE_ROW 已在上一迁移中展开为逐月 RULE；保留逐月规则，删除重复载体。
DELETE FROM ods_performance_owner_rule_raw WHERE record_type='SOURCE_ROW';

UPDATE ods_performance_owner_rule_raw o
JOIN dwd_performance_owner_rule d
  ON d.platform=o.platform
 AND d.stat_month=o.stat_month
 AND d.group_code <=> o.group_code
 AND d.rule_type=o.rule_type
 AND d.match_key=o.match_key
SET o.principal_name=d.principal_name,
    o.source_file_name=d.source_file_name,
    o.source_sheet=d.source_sheet,
    o.source_row=d.source_row,
    o.import_batch_id=d.import_batch_id;

DELETE older
FROM ods_performance_owner_rule_raw older
JOIN ods_performance_owner_rule_raw newer
  ON newer.platform=older.platform
 AND newer.stat_month=older.stat_month
 AND newer.group_code <=> older.group_code
 AND newer.rule_type=older.rule_type
 AND newer.match_key=older.match_key
 AND newer.id>older.id;

ALTER TABLE ods_lingxing_amz_fba_inventory_raw
    ADD COLUMN group_code VARCHAR(20) NULL COMMENT '滞销清货组别' AFTER sku,
    ADD COLUMN region_code VARCHAR(10) NULL COMMENT '区域编码' AFTER group_code,
    ADD COLUMN region_name VARCHAR(20) NULL COMMENT '区域名称' AFTER region_code,
    ADD COLUMN group_match_source VARCHAR(32) NULL COMMENT '组别匹配来源' AFTER region_name;

UPDATE ods_lingxing_amz_fba_inventory_raw o
JOIN (
    SELECT sync_batch_id,sid,
           MAX(group_code) group_code,
           MAX(region_code) region_code,
           MAX(region_name) region_name,
           MAX(group_match_source) group_match_source
    FROM dwd_amz_fba_inventory_monthly_snapshot
    GROUP BY sync_batch_id,sid
) d
  ON d.sync_batch_id=o.sync_batch_id
 AND d.sid <=> o.sid
SET o.group_code=d.group_code,
    o.region_code=d.region_code,
    o.region_name=d.region_name,
    o.group_match_source=d.group_match_source;

ALTER TABLE ods_ebay_monthly_profit_raw
    MODIFY COLUMN sku VARCHAR(255) NOT NULL COMMENT 'SKU',
    MODIFY COLUMN brand_code VARCHAR(64) NOT NULL COMMENT '品牌码',
    MODIFY COLUMN gross_profit DECIMAL(20,6) NOT NULL DEFAULT 0 COMMENT '利润',
    MODIFY COLUMN product_sales_amount DECIMAL(20,6) NOT NULL DEFAULT 0 COMMENT '商品销售额',
    MODIFY COLUMN receivable_shipping_amount DECIMAL(20,6) NOT NULL DEFAULT 0 COMMENT '应收运费',
    MODIFY COLUMN sales_amount DECIMAL(20,6) NOT NULL DEFAULT 0 COMMENT '销售额',
    MODIFY COLUMN refund_amount DECIMAL(20,6) NOT NULL DEFAULT 0 COMMENT '退款金额',
    MODIFY COLUMN net_sales_amount DECIMAL(20,6) NOT NULL DEFAULT 0 COMMENT '净销售额',
    DROP COLUMN raw_json,
    ADD INDEX idx_ods_ebay_profit_brand (stat_month,brand_code),
    ADD INDEX idx_ods_ebay_profit_sku (stat_month,sku);

ALTER TABLE ods_performance_owner_rule_raw
    DROP COLUMN record_type,
    DROP COLUMN raw_json,
    ADD UNIQUE INDEX uk_ods_perf_rule
        (platform,stat_month,group_code,rule_type,match_key);

ALTER TABLE ods_lingxing_amz_order_profit_raw DROP COLUMN raw_json;
ALTER TABLE dwd_amz_monthly_order_profit DROP COLUMN raw_json;
ALTER TABLE ods_lingxing_amz_fba_inventory_raw
    DROP COLUMN raw_json,
    ADD INDEX idx_fba_ods_month_group (pull_month,group_code);

-- 最终校验：raw_json_columns 必须为0。
SELECT COUNT(*) AS raw_json_columns
FROM information_schema.COLUMNS
WHERE TABLE_SCHEMA=DATABASE()
  AND COLUMN_NAME='raw_json'
  AND TABLE_NAME IN (
      'ods_lingxing_amz_order_profit_raw',
      'ods_ebay_monthly_profit_raw',
      'ods_performance_owner_rule_raw',
      'dwd_amz_monthly_order_profit',
      'ods_lingxing_amz_fba_inventory_raw'
  );

SELECT 'amz_profit_ods' table_name,COUNT(*) row_count FROM ods_lingxing_amz_order_profit_raw
UNION ALL SELECT 'ebay_profit_ods',COUNT(*) FROM ods_ebay_monthly_profit_raw
UNION ALL SELECT 'owner_rule_ods',COUNT(*) FROM ods_performance_owner_rule_raw
UNION ALL SELECT 'fba_inventory_ods',COUNT(*) FROM ods_lingxing_amz_fba_inventory_raw;
