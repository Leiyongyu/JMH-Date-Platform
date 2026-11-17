-- AMZ 补货快照按区域拆分：US / EU。
-- 可重复执行。首次执行会从旧快照表回填当前数据，后续由刷新任务独立生成两个区域批次。

CREATE TABLE IF NOT EXISTS amz_replenishment_us_snapshot LIKE amz_replenishment_snapshot;
CREATE TABLE IF NOT EXISTS amz_replenishment_eu_snapshot LIKE amz_replenishment_snapshot;

ALTER TABLE amz_replenishment_us_snapshot COMMENT = 'Amazon美国组补货计算快照';
ALTER TABLE amz_replenishment_eu_snapshot COMMENT = 'Amazon欧洲组补货计算快照';

INSERT INTO amz_replenishment_us_snapshot
SELECT legacy.*
FROM amz_replenishment_snapshot legacy
WHERE legacy.region_group = 'US'
  AND NOT EXISTS (SELECT 1 FROM amz_replenishment_us_snapshot LIMIT 1);

INSERT INTO amz_replenishment_eu_snapshot
SELECT legacy.*
FROM amz_replenishment_snapshot legacy
WHERE legacy.region_group = 'EU'
  AND NOT EXISTS (SELECT 1 FROM amz_replenishment_eu_snapshot LIMIT 1);

-- 分表后 region_group 为固定值；修复历史空值或错误默认值。
UPDATE amz_replenishment_us_snapshot SET region_group = 'US' WHERE region_group IS NULL OR region_group != 'US';
UPDATE amz_replenishment_eu_snapshot SET region_group = 'EU' WHERE region_group IS NULL OR region_group != 'EU';

-- 原AMZ页面列配置分别复制给US/EU页面；已存在的新配置不会被覆盖。
INSERT IGNORE INTO sys_user_column_config
    (user_id, user_name, page_key, config_json, create_by, create_time, update_by, update_time)
SELECT user_id, user_name, 'operations:amz:replenishment:us', config_json,
       create_by, COALESCE(create_time, NOW()), update_by, update_time
FROM sys_user_column_config
WHERE page_key = 'operations:amz:replenishment';

INSERT IGNORE INTO sys_user_column_config
    (user_id, user_name, page_key, config_json, create_by, create_time, update_by, update_time)
SELECT user_id, user_name, 'operations:amz:replenishment:eu', config_json,
       create_by, COALESCE(create_time, NOW()), update_by, update_time
FROM sys_user_column_config
WHERE page_key = 'operations:amz:replenishment';
