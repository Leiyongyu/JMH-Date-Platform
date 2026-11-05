-- 目标库：jmh_data_platform（Java ERP）。
-- 功能：把补数任务「AMZ利润报表数据补拉（2026-07~2026-09）」改为补拉 2026-04~2026-06。
--       7~9 月已补完，不再需要；直接改原任务的名称、调用目标和备注，不新增任务。
-- 用法：任务保持【暂停】，不会自动执行；在「系统监控 > 定时任务」中点「执行一次」即可依次补拉 4、5、6 月。
--       每个月单独拉取、单独记日志，某月失败不影响后续月份；重复执行按月份整月覆盖，不会重复累加。
-- 安全性：只改调用目标为 7~9 月的那一条 sys_job；没有这条任务的环境则补插一条 4~6 月任务（同样暂停）；
--         不改其他任务和业务数据。可重复执行。
-- 依赖：20261105_amz_profit_report_backfill_job.sql。
USE `jmh_data_platform`;
SET NAMES utf8mb4;

UPDATE sys_job
SET job_name='AMZ利润报表数据补拉（2026-04~2026-06）',
    invoke_target='pythonAmzProfitReportTask.syncMonthRange(''2026-04'', ''2026-06'')',
    status='1',
    update_by='SYSTEM',
    update_time=NOW(),
    remark='一次性补数任务，默认暂停，手动点「执行一次」；依次补拉 2026-04、2026-05、2026-06 的领星利润统计（结算）与订单利润，USD，每月约 20~40 分钟'
WHERE invoke_target='pythonAmzProfitReportTask.syncMonthRange(''2026-07'', ''2026-09'')';

INSERT INTO sys_job(job_name,job_group,invoke_target,cron_expression,misfire_policy,concurrent,status,create_by,create_time,remark)
SELECT 'AMZ利润报表数据补拉（2026-04~2026-06）','DATA_CENTER',
  'pythonAmzProfitReportTask.syncMonthRange(''2026-04'', ''2026-06'')',
  '0 0 3 1 1 ?','3','1','1','SYSTEM',NOW(),
  '一次性补数任务，默认暂停，手动点「执行一次」；依次补拉 2026-04、2026-05、2026-06 的领星利润统计（结算）与订单利润，USD，每月约 20~40 分钟'
WHERE NOT EXISTS(
  SELECT 1 FROM sys_job WHERE invoke_target='pythonAmzProfitReportTask.syncMonthRange(''2026-04'', ''2026-06'')'
);
