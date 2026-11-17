-- ============================================================================
-- 08_FBA货件送达时间.sql
-- 目标库：jmh_data_platform
-- 用途  ：AMZ - FBA货件 页面新增「送达时间」列所需的唯一 DDL
-- 特性  ：幂等，可重复执行；只加一列，不改表结构其它部分、不动任何业务数据
-- 生成  ：2026-09-15
--
-- 【为什么只需要一列】
--   页面显示的是「天数」，但天数不能落库：今天算出 +68，明天还是 +68，
--   除非每天刷全表。正确做法是把接口返回的日期原样存下来，
--   天数在查询时用 DATEDIFF(sta_delivery_start_date, CURDATE()) 实时算，
--   永远准确、零维护。所以只加一个日期列，不加天数列、不建表。
--
-- 【为什么是 DATE 不是 DATETIME】
--   接口文档写 sta_delivery_start_date 格式为 yyyy-MM-dd HH:mm:ss，
--   但实测最近 180 天 2,856 条有值记录，长度全部为 10（如 2026-09-13），
--   没有时分秒。存 DATE 即可，DATETIME 只会多出无意义的 00:00:00。
--
-- 【历史数据不用手工补】
--   AmzFbaShipmentSyncService 默认按「最近365天全量 upsert」同步，
--   本列加上、同步代码补上写入后，下一次定时任务会自动回填最近一年。
--   365 天以前的老货件补不到，但那些基本都已 CLOSED。
--
-- 【预期覆盖率：约 1/3，属正常】
--   该字段仅 STA 货件返回。实测最近 180 天 8,613 个货件中 2,856 个有值（33.2%）。
--   按状态拆分：SHIPPED 468/468(100%)、RECEIVING 214/224(95.5%)、
--   IN_TRANSIT 25/27(92.6%)、CLOSED 2098/6900(30.4%)、CANCELLED 46/911(5.0%)。
--   在途货件基本都有值，已完结/已取消的大多没有，页面显示 -- 是源数据如此。
-- ============================================================================

USE `jmh_data_platform`;
SET NAMES utf8mb4;
-- DDL 可能等待元数据锁；设置短等待，遇到错误必须停下检查。
SET SESSION lock_wait_timeout = 15;

SET @sql := IF(
  (SELECT COUNT(*) FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = 'jmh_data_platform'
      AND TABLE_NAME = 'amz_fba_shipment'
      AND COLUMN_NAME = 'sta_delivery_start_date') = 0,
  'ALTER TABLE `amz_fba_shipment` ADD COLUMN `sta_delivery_start_date` DATE NULL COMMENT ''送达时段开始日期；领星sta_delivery_start_date原值，仅STA货件返回'' AFTER `closed_time`',
  'SELECT ''sta_delivery_start_date 已存在，跳过'' AS `提示`');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

-- ---------------------------------------------------------------------------
-- 核对
-- ---------------------------------------------------------------------------
SELECT '=== 列是否建成（应 1 行，类型 date）===' AS `提示`;
SELECT COLUMN_NAME AS `字段`, COLUMN_TYPE AS `类型`,
       IS_NULLABLE AS `可空`, COLUMN_COMMENT AS `注释`
FROM information_schema.COLUMNS
WHERE TABLE_SCHEMA = 'jmh_data_platform'
  AND TABLE_NAME = 'amz_fba_shipment'
  AND COLUMN_NAME = 'sta_delivery_start_date';

SELECT '=== 当前填充情况（同步跑过之后才会有值）===' AS `提示`;
SELECT COUNT(*) AS `总行数`,
       SUM(sta_delivery_start_date IS NOT NULL) AS `有送达日期`,
       SUM(sta_delivery_start_date IS NOT NULL
           AND sta_delivery_start_date <= DATE_ADD(CURDATE(), INTERVAL 7 DAY)) AS `7天内含逾期`,
       SUM(sta_delivery_start_date < CURDATE()) AS `已逾期`
FROM amz_fba_shipment;
-- 刚执行完本脚本时「有送达日期」为 0 是正常的：
-- 需要发布 Java 代码并等下一次 FBA货件同步任务跑完才会有值。

SELECT '=== 还缺什么（应返回 0 行）===' AS `提示`;
SELECT '缺字段' AS `缺失类型`, 'amz_fba_shipment.sta_delivery_start_date' AS `名称`
WHERE NOT EXISTS (SELECT 1 FROM information_schema.COLUMNS
  WHERE TABLE_SCHEMA = 'jmh_data_platform'
    AND TABLE_NAME = 'amz_fba_shipment'
    AND COLUMN_NAME = 'sta_delivery_start_date');

SELECT '08 脚本执行完毕' AS `结果`;
