-- eBay 跟价商品站点标准化：统一为中文站点。
-- 目标表：ebay_product_dedup
-- 映射：US/MOTO -> 美国，UK -> 英国，DE -> 德国，FR -> 法国。
-- 脚本可重复执行；首次执行会把待清理英文行备份到独立备份表。

CREATE TABLE IF NOT EXISTS ebay_product_dedup_site_backup_20260803
LIKE ebay_product_dedup;

INSERT IGNORE INTO ebay_product_dedup_site_backup_20260803
SELECT *
FROM ebay_product_dedup
WHERE site IN ('US', 'MOTO', 'UK', 'DE', 'FR');

START TRANSACTION;

-- 将英文重复行中的有效字段补入对应中文行。
-- 中文行已有业务值时保持中文行；最低价存在冲突时取上传时间更新的一组值。
UPDATE ebay_product_dedup target
JOIN ebay_product_dedup source
  ON target.site = CASE
       WHEN source.site IN ('US', 'MOTO') THEN '美国'
       WHEN source.site = 'UK' THEN '英国'
       WHEN source.site = 'DE' THEN '德国'
       WHEN source.site = 'FR' THEN '法国'
     END
 AND target.sku = source.sku
SET target.product_name = COALESCE(NULLIF(target.product_name, ''), source.product_name),
    target.product_nature = COALESCE(target.product_nature, source.product_nature),
    target.oe_number = COALESCE(NULLIF(target.oe_number, ''), source.oe_number),
    target.tracking_price = COALESCE(target.tracking_price, source.tracking_price),
    target.tracking_profit_margin = COALESCE(target.tracking_profit_margin, source.tracking_profit_margin),
    target.floor_price = COALESCE(target.floor_price, source.floor_price),
    target.remark = COALESCE(NULLIF(target.remark, ''), source.remark),
    target.profit_rate = COALESCE(target.profit_rate, source.profit_rate),
    target.return_rate = COALESCE(target.return_rate, source.return_rate)
WHERE source.site IN ('US', 'MOTO', 'UK', 'DE', 'FR');

-- 最低价、Item Number、上传时间必须整组迁移，避免三个字段来自不同记录。
UPDATE ebay_product_dedup target
JOIN ebay_product_dedup source
  ON target.site = CASE
       WHEN source.site IN ('US', 'MOTO') THEN '美国'
       WHEN source.site = 'UK' THEN '英国'
       WHEN source.site = 'DE' THEN '德国'
       WHEN source.site = 'FR' THEN '法国'
     END
 AND target.sku = source.sku
SET target.lowest_price = source.lowest_price,
    target.lowest_item_number = source.lowest_item_number,
    target.lowest_upload_time = source.lowest_upload_time
WHERE source.site IN ('US', 'MOTO', 'UK', 'DE', 'FR')
  AND source.lowest_price IS NOT NULL
  AND (target.lowest_price IS NULL
    OR target.lowest_upload_time IS NULL
    OR source.lowest_upload_time > target.lowest_upload_time);

-- 删除已经合并到中文行的英文重复记录。
DELETE source
FROM ebay_product_dedup source
JOIN ebay_product_dedup target
  ON target.site = CASE
       WHEN source.site IN ('US', 'MOTO') THEN '美国'
       WHEN source.site = 'UK' THEN '英国'
       WHEN source.site = 'DE' THEN '德国'
       WHEN source.site = 'FR' THEN '法国'
     END
 AND target.sku = source.sku
WHERE source.site IN ('US', 'MOTO', 'UK', 'DE', 'FR');

-- 若其他环境存在没有中文对应行的英文记录，则直接改为中文站点后保留。
UPDATE ebay_product_dedup
SET site = CASE
  WHEN site IN ('US', 'MOTO') THEN '美国'
  WHEN site = 'UK' THEN '英国'
  WHEN site = 'DE' THEN '德国'
  WHEN site = 'FR' THEN '法国'
  ELSE site
END
WHERE site IN ('US', 'MOTO', 'UK', 'DE', 'FR');

COMMIT;

-- 验证：english_site_rows 应为 0，duplicate_site_sku_rows 应为 0。
SELECT COUNT(*) AS english_site_rows
FROM ebay_product_dedup
WHERE site IN ('US', 'MOTO', 'UK', 'DE', 'FR');

SELECT COUNT(*) AS duplicate_site_sku_rows
FROM (
  SELECT site, sku
  FROM ebay_product_dedup
  GROUP BY site, sku
  HAVING COUNT(*) > 1
) duplicate_rows;
