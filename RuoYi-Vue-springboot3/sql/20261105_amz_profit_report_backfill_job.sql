-- 目标库：jmh_data_platform（Java ERP）。
-- 功能：新增 Quartz 任务「AMZ利润报表数据补拉（2026-07~2026-09）」，用于首次上线补齐 7、8、9 月数据。
-- 用法：任务默认【暂停】，不会自动执行；在「系统监控 > 定时任务」中点「执行一次」即可依次补拉 3 个月。
--       每个月单独拉取、单独记日志，某月失败不影响后续月份；重复执行会按月份整月覆盖，不会重复累加。
--       以后要补其他月份，复制本任务并修改调用目标中的两个月份即可（一次最多 12 个月）。
-- 安全性：只插入一条 sys_job，已存在同一调用目标时不重复插入；不改其他任务和业务数据。
-- 依赖：需部署包含 pythonAmzProfitReportTask.syncMonthRange 的新版 Java，并已执行 20261102_amz_profit_report.sql。
USE `jmh_data_platform`;
SET NAMES utf8mb4;

INSERT INTO sys_job(job_name,job_group,invoke_target,cron_expression,misfire_policy,concurrent,status,create_by,create_time,remark)
SELECT 'AMZ利润报表数据补拉（2026-07~2026-09）','DATA_CENTER',
  'pythonAmzProfitReportTask.syncMonthRange(''2026-07'', ''2026-09'')',
  '0 0 3 1 1 ?','3','1','1','SYSTEM',NOW(),
  '一次性补数任务，默认暂停，手动点「执行一次」；依次补拉 2026-07、2026-08、2026-09 的领星利润统计（结算）与订单利润，USD，每月约 20~40 分钟'
WHERE NOT EXISTS(
  SELECT 1 FROM sys_job WHERE invoke_target='pythonAmzProfitReportTask.syncMonthRange(''2026-07'', ''2026-09'')'
);
