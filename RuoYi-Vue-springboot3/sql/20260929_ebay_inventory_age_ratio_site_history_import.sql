-- 海外仓库龄占比：站点历史补录，按用户提供的8列数据导入。
-- 执行库：Python业务库date-project；部署库名不同请修改USE。
-- 前置：先执行负责人历史补录20260929_ebay_inventory_age_ratio_history_import.sql。
-- 仅补2026-08-03/10/17/24共4天、每一天US/DE/UK共3行。
-- US=美国、DE=德国、UK=英国。比例按原始分子/分母计算，页面显示两位百分数。
-- 保留原始货值，不为凑齐个人维度合计而调整金额。
-- 只更新sites为空数组或缺失的日期；已有站点数据、非数组异常结构、缺失日期均跳过。
-- 不改owners、generated_at、source_batch_id及其他原有字段；新增独立站点导入元数据。
-- 自动将拟更新的原快照备份至ebay_inventory_age_ratio_history_backup（带批次）。
-- 请在同一连接整份执行；遇错立即停止并ROLLBACK，不要跳过错误继续COMMIT。

USE `date-project`;
SET NAMES utf8mb4 COLLATE utf8mb4_unicode_ci;
SET @age_site_batch = 'site-history-20260929-v1';
SET @age_site_imported_at = DATE_FORMAT(UTC_TIMESTAMP() + INTERVAL 8 HOUR,'%Y-%m-%d %H:%i:%s');

CREATE TABLE IF NOT EXISTS ebay_inventory_age_ratio_history_backup (
    backup_batch_id VARCHAR(64) NOT NULL,
    stat_date DATE NOT NULL,
    generated_at DATETIME NOT NULL,
    source_batch_id VARCHAR(64) NOT NULL,
    report_json JSON NOT NULL,
    backed_up_at DATETIME NOT NULL,
    PRIMARY KEY (backup_batch_id,stat_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='海外仓库龄历史补录前快照备份';

DROP TEMPORARY TABLE IF EXISTS tmp_ebay_age_site_history_20260929;
CREATE TEMPORARY TABLE tmp_ebay_age_site_history_20260929 (
    stat_date DATE NOT NULL,
    site_name VARCHAR(20) NOT NULL,
    total_quantity DECIMAL(18,6) NOT NULL,
    over_180_quantity DECIMAL(18,6) NOT NULL,
    total_value DECIMAL(18,6) NOT NULL,
    over_180_value DECIMAL(18,6) NOT NULL,
    PRIMARY KEY (stat_date,site_name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

INSERT INTO tmp_ebay_age_site_history_20260929
(stat_date,site_name,total_quantity,over_180_quantity,total_value,over_180_value)
VALUES
('2026-08-03','美国',2751,189,502082.4732,45570.33),
('2026-08-03','德国',7764,847,1371777.733,165587.074),
('2026-08-03','英国',5613,466,568262.5991,72211.295),
('2026-08-10','美国',2987,165,532434.4928,39817.802),
('2026-08-10','德国',7069,773,1258845.556,146544.2682),
('2026-08-10','英国',6153,401,705187.7724,60227.2949),
('2026-08-17','美国',3326,150,522723.6028,34766.252),
('2026-08-17','德国',6550,671,1130484.707,115390.4001),
('2026-08-17','英国',5498,331,622819.9255,52776.5324),
('2026-08-24','美国',4618,136,725622.7496,28920.307),
('2026-08-24','德国',9081,632,1635191.474,99353.8806),
('2026-08-24','英国',6785,382,828869.3981,51079.713);

DROP TEMPORARY TABLE IF EXISTS tmp_ebay_age_site_reports_20260929;
CREATE TEMPORARY TABLE tmp_ebay_age_site_reports_20260929 (
    stat_date DATE PRIMARY KEY,
    sites_json JSON NOT NULL
) ENGINE=InnoDB;

INSERT INTO tmp_ebay_age_site_reports_20260929 (stat_date,sites_json)
SELECT stat_date, JSON_ARRAYAGG(JSON_OBJECT(
    'stat_date',DATE_FORMAT(stat_date,'%Y-%m-%d'),
    'name',site_name,
    'total_quantity',CAST(total_quantity AS CHAR),
    'over_180_quantity',CAST(over_180_quantity AS CHAR),
    'over_180_quantity_ratio',CAST(ROUND(CAST(over_180_quantity AS DECIMAL(30,15))/NULLIF(total_quantity,0),15) AS CHAR),
    'total_value',CAST(total_value AS CHAR),
    'over_180_value',CAST(over_180_value AS CHAR),
    'over_180_ratio',CAST(ROUND(CAST(over_180_value AS DECIMAL(30,15))/NULLIF(total_value,0),15) AS CHAR)
))
FROM tmp_ebay_age_site_history_20260929 GROUP BY stat_date;

-- 执行前清单。MISSING_DATE需先执行负责人补录；PRESERVE_EXISTING表示不改该日。
SELECT h.stat_date,
       CASE WHEN s.stat_date IS NULL THEN 'MISSING_DATE'
            WHEN JSON_CONTAINS_PATH(s.report_json,'one','$.sites')=0
                 OR (JSON_TYPE(JSON_EXTRACT(s.report_json,'$.sites'))='ARRAY'
                     AND JSON_LENGTH(s.report_json,'$.sites')=0) THEN 'FILL_EMPTY_SITES'
            ELSE 'PRESERVE_EXISTING' END AS action
FROM tmp_ebay_age_site_reports_20260929 h
LEFT JOIN ebay_inventory_age_ratio_snapshot s ON s.stat_date=h.stat_date
ORDER BY h.stat_date;

START TRANSACTION;

-- 锁定4个目标日期，备份和更新在同一事务中完成。
SELECT s.stat_date FROM ebay_inventory_age_ratio_snapshot s
JOIN tmp_ebay_age_site_reports_20260929 h ON h.stat_date=s.stat_date
ORDER BY s.stat_date FOR UPDATE;

INSERT INTO ebay_inventory_age_ratio_history_backup
(backup_batch_id,stat_date,generated_at,source_batch_id,report_json,backed_up_at)
SELECT @age_site_batch,s.stat_date,s.generated_at,s.source_batch_id,s.report_json,@age_site_imported_at
FROM ebay_inventory_age_ratio_snapshot s
JOIN tmp_ebay_age_site_reports_20260929 h ON h.stat_date=s.stat_date
WHERE JSON_CONTAINS_PATH(s.report_json,'one','$.sites')=0
   OR (JSON_TYPE(JSON_EXTRACT(s.report_json,'$.sites'))='ARRAY'
       AND JSON_LENGTH(s.report_json,'$.sites')=0)
ON DUPLICATE KEY UPDATE backup_batch_id=VALUES(backup_batch_id);

UPDATE ebay_inventory_age_ratio_snapshot s
JOIN tmp_ebay_age_site_reports_20260929 h ON h.stat_date=s.stat_date
SET s.report_json=JSON_SET(s.report_json,
    '$.sites',h.sites_json,
    '$.site_calculation_version','historical-site-manual-v1',
    '$.site_history_import',JSON_OBJECT(
        'batch_id',@age_site_batch,
        'imported_at',@age_site_imported_at,
        'source','用户提供的2026年8月站点历史表',
        'source_rows',3,
        'notes','保留历史库存和货值，占比按原始金额及数量计算，不按今天的源数据重算。'
    ))
WHERE JSON_CONTAINS_PATH(s.report_json,'one','$.sites')=0
   OR (JSON_TYPE(JSON_EXTRACT(s.report_json,'$.sites'))='ARRAY'
       AND JSON_LENGTH(s.report_json,'$.sites')=0);

SET @age_site_updated_days = ROW_COUNT();
COMMIT;

-- 首次已有4天负责人快照且sites为空：updated_days=4；重复执行为0。
SELECT @age_site_updated_days AS updated_days;
SELECT s.stat_date,JSON_LENGTH(s.report_json,'$.owners') AS owner_rows,
       JSON_LENGTH(s.report_json,'$.sites') AS site_rows,
       JSON_UNQUOTE(JSON_EXTRACT(s.report_json,'$.site_history_import.batch_id')) AS site_import_batch
FROM ebay_inventory_age_ratio_snapshot s
JOIN tmp_ebay_age_site_reports_20260929 h ON h.stat_date=s.stat_date
ORDER BY s.stat_date;

DROP TEMPORARY TABLE tmp_ebay_age_site_history_20260929;
DROP TEMPORARY TABLE tmp_ebay_age_site_reports_20260929;
