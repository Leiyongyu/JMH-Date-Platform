-- 海外仓库龄占比.xlsx / Sheet1!A1:I19 历史补录
-- 来源 SHA256: 3e138e5595c0d3c9124bbb89b237a2a9cbc0be452327e885539e507c077172e5
-- 在 Python 业务库执行。若部署库名不同，请修改下面 USE。
-- 前置：已执行 20260929_ebay_inventory_age_ratio.sql；执行前备份快照表（包含数据）。
-- 本文件包含全部数据，不需要部署机安装 Excel/Python 或复制原表。
-- 仅补不存在的统计日；同日已有快照完整保留（包括已有站点数据）。可重复执行。
-- 6个统计日，18条负责人汇总；原表无站点信息，sites 保存为空数组，不推测分摊。
-- <90货值/占比按用户要求为0；总货值保留原表E列，不改成B+C+D。
-- 其余占比按原表分段金额/原表总货值计算，保留15位小数。
-- 注意原表公式实际为90<=age<=120、120<=age<=180、age>=180，边界有重叠。
-- 无SKU级原始数据，不能消除120/180重叠；保留历史缓存值，报告内明确标注。
-- 不是按当前互斥分段重算的结果，也不能由总货值倒推出精确的<90金额。
-- 请在同一连接中整份执行，出现错误立即停止并执行 ROLLBACK，不要继续到COMMIT。

USE `date-project`;
SET NAMES utf8mb4 COLLATE utf8mb4_unicode_ci;
SET @age_history_batch = 'excel-age-history-20260929-3e138e5595c0';
SET @age_history_imported_at = DATE_FORMAT(UTC_TIMESTAMP() + INTERVAL 8 HOUR, '%Y-%m-%d %H:%i:%s');

DROP TEMPORARY TABLE IF EXISTS tmp_ebay_age_history_20260929;
CREATE TEMPORARY TABLE tmp_ebay_age_history_20260929 (
    stat_date DATE NOT NULL,
    owner_name VARCHAR(64) NOT NULL,
    over_180_value DECIMAL(18,6) NOT NULL,
    days_90_120_value DECIMAL(18,6) NOT NULL,
    days_120_180_value DECIMAL(18,6) NOT NULL,
    total_value DECIMAL(18,6) NOT NULL,
    PRIMARY KEY (stat_date, owner_name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

INSERT INTO tmp_ebay_age_history_20260929
(stat_date,owner_name,over_180_value,days_90_120_value,days_120_180_value,total_value)
VALUES
('2026-08-03','陈丽',79122.0415,19337.404,13259.221,571847.9906),
('2026-08-03','杨萍',85852.9495,48034.3755,36934.214,797991.4215),
('2026-08-03','方黎力',118393.708,76375.847,29904.8239,1072283.3931),
('2026-08-10','陈丽',67387.6376,14918.1964,15948.17,587628.0938),
('2026-08-10','杨萍',75373.3286,36952.0264,41784.49,847146.1957),
('2026-08-10','方黎力',104001.1259,58599.3787,39587.1713,1061693.5318),
('2026-08-17','陈丽',56204.9796,19828.97,11196.9436,559995.5622),
('2026-08-17','杨萍',60487.8621,44808.1956,46087.5035,753073.9416),
('2026-08-17','方黎力',86413.0698,91952.4217,35867.5158,962958.7316),
('2026-08-24','陈丽',46150.269,18431.04,7367.39,771775.1984),
('2026-08-24','杨萍',55860.5786,49250.1507,42601.043,1167728.9013),
('2026-08-24','方黎力',77515.78,95590.1616,35789.7736,1250179.522),
('2026-08-31','任雅婷',41017.8168,13170.31,6336.96,779214.3059),
('2026-08-31','杨萍',54065.3692,44389.3499,36849.704,1147682.401),
('2026-08-31','方黎力',74673.8365,74857.0013,44953.0475,1267022.838),
('2026-09-07','任雅婷',38096.9218,14639.895,5096.733,826538.5465),
('2026-09-07','杨萍',69512.6814,44161.8304,23302.3856,1114398.8147),
('2026-09-07','方黎力',81352.5352,74225.8757,44951.253,1247057.9859);

-- 执行前清单：已有日期将跳过，不覆盖其中任何个人或站点数据。
SELECT h.stat_date, COUNT(*) AS source_owner_rows,
       SUM(h.total_value) AS source_total_value,
       CASE WHEN s.stat_date IS NULL THEN 'INSERT_NEW_DATE' ELSE 'SKIP_EXISTING_DATE' END AS action
FROM tmp_ebay_age_history_20260929 h
LEFT JOIN ebay_inventory_age_ratio_snapshot s ON s.stat_date=h.stat_date
GROUP BY h.stat_date,s.stat_date ORDER BY h.stat_date;

DROP TEMPORARY TABLE IF EXISTS tmp_ebay_age_reports_20260929;
CREATE TEMPORARY TABLE tmp_ebay_age_reports_20260929 (
    stat_date DATE PRIMARY KEY,
    generated_at DATETIME NOT NULL,
    source_batch_id VARCHAR(64) NOT NULL,
    report_json JSON NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

START TRANSACTION;

INSERT INTO tmp_ebay_age_reports_20260929
(stat_date,generated_at,source_batch_id,report_json)
SELECT h.stat_date, @age_history_imported_at, @age_history_batch,
       JSON_OBJECT(
           'stat_date', DATE_FORMAT(h.stat_date,'%Y-%m-%d'),
           'generated_at', @age_history_imported_at,
           'source_batch_id', @age_history_batch,
           'source_kind', 'HISTORICAL_EXCEL_IMPORT',
           'source_file', '海外仓库龄占比.xlsx',
           'source_sheet_range', 'Sheet1!A1:I19',
           'source_sha256', '3e138e5595c0d3c9124bbb89b237a2a9cbc0be452327e885539e507c077172e5',
           'calculation_version', 'historical-excel-under90-zero-v1',
           'owner_month', DATE_FORMAT(h.stat_date,'%Y-%m'),
           'cost_month', NULL,
           'source_pulled_at', NULL,
           'source_rows', NULL,
           'valued_rows', NULL,
           'source_summary_rows', COUNT(*),
           'excluded_rows', 0,
           'excluded_details', JSON_ARRAY(),
           'warnings', JSON_ARRAY(
               'Excel历史汇总：<90货值及占比按要求补0，总货值保留原表，分段合计及占比不一定等于总货值或100%。',
               '历史分段沿用原Excel公式：90至120含两端、120至180含两端、180及以上；与当前互斥分段口径不同，未按当前规则重算。',
               '原表仅有负责人汇总，无站点数据及SKU明细；站点维度为空。负责人保留原表，不按当前负责人重新匹配。'
           ),
           'owners', JSON_ARRAYAGG(JSON_OBJECT(
               'stat_date', DATE_FORMAT(h.stat_date,'%Y-%m-%d'),
               'name', h.owner_name,
               'source_rows', NULL,
               'valued_rows', NULL,
               'excluded_rows', 0,
               'under_90_value', '0.000000',
               'days_90_120_value', CAST(h.days_90_120_value AS CHAR),
               'days_120_180_value', CAST(h.days_120_180_value AS CHAR),
               'over_180_value', CAST(h.over_180_value AS CHAR),
               'total_value', CAST(h.total_value AS CHAR),
               'under_90_ratio', '0.000000000000000',
               'days_90_120_ratio', CAST(ROUND(CAST(h.days_90_120_value AS DECIMAL(30,15))/NULLIF(h.total_value,0),15) AS CHAR),
               'days_120_180_ratio', CAST(ROUND(CAST(h.days_120_180_value AS DECIMAL(30,15))/NULLIF(h.total_value,0),15) AS CHAR),
               'over_180_ratio', CAST(ROUND(CAST(h.over_180_value AS DECIMAL(30,15))/NULLIF(h.total_value,0),15) AS CHAR)
           )),
           'sites', JSON_ARRAY()
       )
FROM tmp_ebay_age_history_20260929 h
WHERE NOT EXISTS (
    SELECT 1 FROM ebay_inventory_age_ratio_snapshot existing WHERE existing.stat_date=h.stat_date
)
GROUP BY h.stat_date;

INSERT INTO ebay_inventory_age_ratio_snapshot
(stat_date,generated_at,source_batch_id,report_json)
SELECT stat_date,generated_at,source_batch_id,report_json
FROM tmp_ebay_age_reports_20260929;

SET @age_history_inserted_days = ROW_COUNT();
COMMIT;

-- 首次且没有同日快照时：新增6天；重复执行应新增0天。
SELECT @age_history_inserted_days AS inserted_days;
SELECT s.stat_date,s.source_batch_id,
       JSON_LENGTH(s.report_json,'$.owners') AS owner_rows,
       JSON_LENGTH(s.report_json,'$.sites') AS site_rows,
       CASE WHEN s.source_batch_id=@age_history_batch THEN 'THIS_IMPORT' ELSE 'EXISTING_PRESERVED' END AS result
FROM ebay_inventory_age_ratio_snapshot s
WHERE s.stat_date IN (SELECT DISTINCT stat_date FROM tmp_ebay_age_history_20260929)
ORDER BY s.stat_date;

DROP TEMPORARY TABLE tmp_ebay_age_history_20260929;
DROP TEMPORARY TABLE tmp_ebay_age_reports_20260929;
