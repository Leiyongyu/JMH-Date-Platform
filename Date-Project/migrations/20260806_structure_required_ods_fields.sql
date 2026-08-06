-- 仅执行一次：将三个 JSON 型 ODS 表补充为可直接查询的结构化字段。
-- 数据保留策略：不删除、不覆盖任何历史 raw_json；新版本同步不再写完整领星 JSON。
-- 建议先完成数据库备份，再在 Date-Project 使用的数据库中执行本文件。

ALTER TABLE ods_lingxing_amz_order_profit_raw
    ADD COLUMN local_sku VARCHAR(255) NULL COMMENT '本地SKU' AFTER seller_sku,
    ADD COLUMN asin VARCHAR(32) NULL COMMENT 'ASIN' AFTER local_sku,
    ADD COLUMN country VARCHAR(64) NULL COMMENT '国家/站点' AFTER asin,
    ADD COLUMN currency_code VARCHAR(16) NULL COMMENT '币种' AFTER country,
    ADD COLUMN gross_profit DECIMAL(20,6) NULL COMMENT '毛利润' AFTER currency_code,
    ADD COLUMN amount DECIMAL(20,6) NULL COMMENT '销售额' AFTER gross_profit,
    ADD COLUMN refund_amount DECIMAL(20,6) NULL COMMENT '退款金额' AFTER amount,
    ADD COLUMN net_sales_amount DECIMAL(20,6) NULL COMMENT '净销售额' AFTER refund_amount,
    ADD COLUMN principal_names VARCHAR(1000) NULL COMMENT '领星负责人' AFTER net_sales_amount,
    ADD COLUMN sync_time DATETIME NULL COMMENT '同步时间' AFTER sync_batch_id,
    MODIFY COLUMN raw_json LONGTEXT NULL COMMENT '历史领星原始JSON；新同步仅保存结构化必需字段';

UPDATE ods_lingxing_amz_order_profit_raw
SET local_sku = COALESCE(
        NULLIF(JSON_UNQUOTE(JSON_EXTRACT(raw_json, '$.price_list[0].local_sku')), 'null'),
        NULLIF(JSON_UNQUOTE(JSON_EXTRACT(raw_json, '$.local_infos[0].local_sku')), 'null')
    ),
    asin = COALESCE(
        NULLIF(JSON_UNQUOTE(JSON_EXTRACT(raw_json, '$.price_list[0].asin')), 'null'),
        NULLIF(JSON_UNQUOTE(JSON_EXTRACT(raw_json, '$.asins[0].asin')), 'null')
    ),
    country = COALESCE(
        NULLIF(JSON_UNQUOTE(JSON_EXTRACT(raw_json, '$.seller_store_countries[0].country')), 'null'),
        NULLIF(JSON_UNQUOTE(JSON_EXTRACT(raw_json, '$.country')), 'null')
    ),
    currency_code = COALESCE(
        NULLIF(JSON_UNQUOTE(JSON_EXTRACT(raw_json, '$.currency_code')), 'null'),
        'CNY'
    ),
    gross_profit = CAST(COALESCE(NULLIF(JSON_UNQUOTE(JSON_EXTRACT(raw_json, '$.gross_profit')), 'null'), '0') AS DECIMAL(20,6)),
    amount = CAST(COALESCE(NULLIF(JSON_UNQUOTE(JSON_EXTRACT(raw_json, '$.amount')), 'null'), '0') AS DECIMAL(20,6)),
    refund_amount = CAST(COALESCE(NULLIF(JSON_UNQUOTE(JSON_EXTRACT(raw_json, '$.refund_amount')), 'null'), '0') AS DECIMAL(20,6)),
    net_sales_amount =
        CAST(COALESCE(NULLIF(JSON_UNQUOTE(JSON_EXTRACT(raw_json, '$.amount')), 'null'), '0') AS DECIMAL(20,6))
        - CAST(COALESCE(NULLIF(JSON_UNQUOTE(JSON_EXTRACT(raw_json, '$.refund_amount')), 'null'), '0') AS DECIMAL(20,6)),
    principal_names = NULLIF(JSON_UNQUOTE(JSON_EXTRACT(raw_json, '$.principal_names')), 'null'),
    sync_time = COALESCE(sync_time, create_time)
WHERE raw_json IS NOT NULL AND JSON_VALID(raw_json) = 1;

ALTER TABLE ods_lingxing_amz_fba_inventory_raw
    ADD COLUMN sku VARCHAR(255) NULL AFTER seller_sku,
    ADD COLUMN inv_age_0_to_30_days DECIMAL(24,6) NULL AFTER sku,
    ADD COLUMN inv_age_0_to_30_price DECIMAL(24,6) NULL AFTER inv_age_0_to_30_days,
    ADD COLUMN inv_age_31_to_60_days DECIMAL(24,6) NULL AFTER inv_age_0_to_30_price,
    ADD COLUMN inv_age_31_to_60_price DECIMAL(24,6) NULL AFTER inv_age_31_to_60_days,
    ADD COLUMN inv_age_61_to_90_days DECIMAL(24,6) NULL AFTER inv_age_31_to_60_price,
    ADD COLUMN inv_age_61_to_90_price DECIMAL(24,6) NULL AFTER inv_age_61_to_90_days,
    ADD COLUMN inv_age_0_to_90_days DECIMAL(24,6) NULL AFTER inv_age_61_to_90_price,
    ADD COLUMN inv_age_0_to_90_price DECIMAL(24,6) NULL AFTER inv_age_0_to_90_days,
    ADD COLUMN inv_age_91_to_180_days DECIMAL(24,6) NULL AFTER inv_age_0_to_90_price,
    ADD COLUMN inv_age_91_to_180_price DECIMAL(24,6) NULL AFTER inv_age_91_to_180_days,
    ADD COLUMN inv_age_181_to_270_days DECIMAL(24,6) NULL AFTER inv_age_91_to_180_price,
    ADD COLUMN inv_age_181_to_270_price DECIMAL(24,6) NULL AFTER inv_age_181_to_270_days,
    ADD COLUMN inv_age_271_to_330_days DECIMAL(24,6) NULL AFTER inv_age_181_to_270_price,
    ADD COLUMN inv_age_271_to_330_price DECIMAL(24,6) NULL AFTER inv_age_271_to_330_days,
    ADD COLUMN inv_age_271_to_365_days DECIMAL(24,6) NULL AFTER inv_age_271_to_330_price,
    ADD COLUMN inv_age_271_to_365_price DECIMAL(24,6) NULL AFTER inv_age_271_to_365_days,
    ADD COLUMN inv_age_331_to_365_days DECIMAL(24,6) NULL AFTER inv_age_271_to_365_price,
    ADD COLUMN inv_age_331_to_365_price DECIMAL(24,6) NULL AFTER inv_age_331_to_365_days,
    ADD COLUMN inv_age_365_plus_days DECIMAL(24,6) NULL AFTER inv_age_331_to_365_price,
    ADD COLUMN inv_age_365_plus_price DECIMAL(24,6) NULL AFTER inv_age_365_plus_days,
    MODIFY COLUMN raw_json LONGTEXT NULL COMMENT '历史领星原始JSON；新同步仅保存结构化必需字段';

UPDATE ods_lingxing_amz_fba_inventory_raw
SET sku = NULLIF(JSON_UNQUOTE(JSON_EXTRACT(raw_json, '$.sku')), 'null'),
    inv_age_0_to_30_days = CAST(COALESCE(NULLIF(JSON_UNQUOTE(JSON_EXTRACT(raw_json, '$.inv_age_0_to_30_days')), 'null'), '0') AS DECIMAL(24,6)),
    inv_age_0_to_30_price = CAST(COALESCE(NULLIF(JSON_UNQUOTE(JSON_EXTRACT(raw_json, '$.inv_age_0_to_30_price')), 'null'), '0') AS DECIMAL(24,6)),
    inv_age_31_to_60_days = CAST(COALESCE(NULLIF(JSON_UNQUOTE(JSON_EXTRACT(raw_json, '$.inv_age_31_to_60_days')), 'null'), '0') AS DECIMAL(24,6)),
    inv_age_31_to_60_price = CAST(COALESCE(NULLIF(JSON_UNQUOTE(JSON_EXTRACT(raw_json, '$.inv_age_31_to_60_price')), 'null'), '0') AS DECIMAL(24,6)),
    inv_age_61_to_90_days = CAST(COALESCE(NULLIF(JSON_UNQUOTE(JSON_EXTRACT(raw_json, '$.inv_age_61_to_90_days')), 'null'), '0') AS DECIMAL(24,6)),
    inv_age_61_to_90_price = CAST(COALESCE(NULLIF(JSON_UNQUOTE(JSON_EXTRACT(raw_json, '$.inv_age_61_to_90_price')), 'null'), '0') AS DECIMAL(24,6)),
    inv_age_0_to_90_days = CAST(COALESCE(NULLIF(JSON_UNQUOTE(JSON_EXTRACT(raw_json, '$.inv_age_0_to_90_days')), 'null'), '0') AS DECIMAL(24,6)),
    inv_age_0_to_90_price = CAST(COALESCE(NULLIF(JSON_UNQUOTE(JSON_EXTRACT(raw_json, '$.inv_age_0_to_90_price')), 'null'), '0') AS DECIMAL(24,6)),
    inv_age_91_to_180_days = CAST(COALESCE(NULLIF(JSON_UNQUOTE(JSON_EXTRACT(raw_json, '$.inv_age_91_to_180_days')), 'null'), '0') AS DECIMAL(24,6)),
    inv_age_91_to_180_price = CAST(COALESCE(NULLIF(JSON_UNQUOTE(JSON_EXTRACT(raw_json, '$.inv_age_91_to_180_price')), 'null'), '0') AS DECIMAL(24,6)),
    inv_age_181_to_270_days = CAST(COALESCE(NULLIF(JSON_UNQUOTE(JSON_EXTRACT(raw_json, '$.inv_age_181_to_270_days')), 'null'), '0') AS DECIMAL(24,6)),
    inv_age_181_to_270_price = CAST(COALESCE(NULLIF(JSON_UNQUOTE(JSON_EXTRACT(raw_json, '$.inv_age_181_to_270_price')), 'null'), '0') AS DECIMAL(24,6)),
    inv_age_271_to_330_days = CAST(COALESCE(NULLIF(JSON_UNQUOTE(JSON_EXTRACT(raw_json, '$.inv_age_271_to_330_days')), 'null'), '0') AS DECIMAL(24,6)),
    inv_age_271_to_330_price = CAST(COALESCE(NULLIF(JSON_UNQUOTE(JSON_EXTRACT(raw_json, '$.inv_age_271_to_330_price')), 'null'), '0') AS DECIMAL(24,6)),
    inv_age_271_to_365_days = CAST(COALESCE(NULLIF(JSON_UNQUOTE(JSON_EXTRACT(raw_json, '$.inv_age_271_to_365_days')), 'null'), '0') AS DECIMAL(24,6)),
    inv_age_271_to_365_price = CAST(COALESCE(NULLIF(JSON_UNQUOTE(JSON_EXTRACT(raw_json, '$.inv_age_271_to_365_price')), 'null'), '0') AS DECIMAL(24,6)),
    inv_age_331_to_365_days = CAST(COALESCE(NULLIF(JSON_UNQUOTE(JSON_EXTRACT(raw_json, '$.inv_age_331_to_365_days')), 'null'), '0') AS DECIMAL(24,6)),
    inv_age_331_to_365_price = CAST(COALESCE(NULLIF(JSON_UNQUOTE(JSON_EXTRACT(raw_json, '$.inv_age_331_to_365_price')), 'null'), '0') AS DECIMAL(24,6)),
    inv_age_365_plus_days = CAST(COALESCE(NULLIF(JSON_UNQUOTE(JSON_EXTRACT(raw_json, '$.inv_age_365_plus_days')), 'null'), '0') AS DECIMAL(24,6)),
    inv_age_365_plus_price = CAST(COALESCE(NULLIF(JSON_UNQUOTE(JSON_EXTRACT(raw_json, '$.inv_age_365_plus_price')), 'null'), '0') AS DECIMAL(24,6))
WHERE raw_json IS NOT NULL AND JSON_VALID(raw_json) = 1;

ALTER TABLE ods_performance_owner_rule_raw
    ADD COLUMN record_type VARCHAR(16) NOT NULL DEFAULT 'SOURCE_ROW' COMMENT 'RULE结构化规则；SOURCE_ROW历史原始行' AFTER source_row,
    ADD COLUMN group_code VARCHAR(16) NULL COMMENT '业务组别' AFTER record_type,
    ADD COLUMN rule_type VARCHAR(32) NULL COMMENT '匹配规则类型' AFTER group_code,
    ADD COLUMN match_key VARCHAR(200) NULL COMMENT '匹配键' AFTER rule_type,
    ADD COLUMN principal_name VARCHAR(100) NULL COMMENT '负责人' AFTER match_key;

INSERT INTO ods_performance_owner_rule_raw (
    platform, stat_month, source_file_name, source_sheet, source_row,
    record_type, group_code, rule_type, match_key, principal_name,
    raw_json, import_batch_id, create_time
)
SELECT d.platform, d.stat_month, d.source_file_name, d.source_sheet, d.source_row,
       'RULE', d.group_code, d.rule_type, d.match_key, d.principal_name,
       COALESCE(s.raw_json, JSON_OBJECT(
           'group_code', d.group_code, 'rule_type', d.rule_type,
           'match_key', d.match_key, 'principal_name', d.principal_name
       )),
       d.import_batch_id, d.create_time
FROM dwd_performance_owner_rule d
LEFT JOIN ods_performance_owner_rule_raw s
  ON s.import_batch_id = d.import_batch_id
 AND s.platform = d.platform
 AND s.source_sheet = d.source_sheet
 AND s.source_row = d.source_row
 AND s.record_type = 'SOURCE_ROW'
WHERE NOT EXISTS (
    SELECT 1
    FROM ods_performance_owner_rule_raw x
    WHERE x.record_type = 'RULE'
      AND x.platform = d.platform
      AND x.stat_month = d.stat_month
      AND COALESCE(x.group_code, '') = COALESCE(d.group_code, '')
      AND x.rule_type = d.rule_type
      AND x.match_key = d.match_key
      AND x.import_batch_id = d.import_batch_id
);

ALTER TABLE ods_performance_owner_rule_raw
    ALTER COLUMN record_type SET DEFAULT 'RULE',
    ADD INDEX idx_ods_rule_structured (platform, stat_month, group_code, rule_type, match_key);

ALTER TABLE ods_lingxing_amz_order_profit_raw
    ADD INDEX idx_ods_amz_profit_month_sid_sku (stat_month, sid, seller_sku);

ALTER TABLE ods_lingxing_amz_fba_inventory_raw
    ADD INDEX idx_fba_ods_month_sid_sku (pull_month, sid, seller_sku);

-- 执行后核对：structured_rows 应与 total_rows 一致（无法解析的历史异常 JSON 除外）。
SELECT 'amz_profit' table_name, COUNT(*) total_rows,
       SUM(gross_profit IS NOT NULL AND amount IS NOT NULL AND refund_amount IS NOT NULL) structured_rows,
       SUM(raw_json IS NOT NULL) preserved_raw_rows
FROM ods_lingxing_amz_order_profit_raw
UNION ALL
SELECT 'fba_inventory', COUNT(*),
       SUM(inv_age_0_to_90_days IS NOT NULL AND inv_age_365_plus_price IS NOT NULL),
       SUM(raw_json IS NOT NULL)
FROM ods_lingxing_amz_fba_inventory_raw
UNION ALL
SELECT 'owner_rule', COUNT(*), SUM(record_type = 'RULE'), SUM(raw_json IS NOT NULL)
FROM ods_performance_owner_rule_raw;
