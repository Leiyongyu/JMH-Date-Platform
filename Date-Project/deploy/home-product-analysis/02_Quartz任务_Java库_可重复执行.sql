-- ============================================================================
-- 首页商品分析相关的 Quartz 定时任务登记
--
-- 在 **Java 库 jmh_data_platform** 执行（注意和 01 不是同一个库）。
-- 整份可重复执行：先 UPDATE 再「不存在才 INSERT」，不会建出重复任务，
-- 也**不会改动任务已有的启用/暂停状态**（status 列只在新建时才写）。
--
-- 前提：Java 端必须已经部署了对应的任务类，否则 Quartz 触发时报找不到 Bean。
--   PythonEbayStoreListingTask      → 本次恢复的在售刊登每月同步
--   PythonFeishuBadTransactionTask  → 飞书不良交易刊登每周同步（早已存在）
--
-- 触发链路都是：Quartz -> Java任务类 -> Python 内部调度接口 -> 实际取数
-- Python 侧 scheduler_task 里也有一条同名登记（见 01 第5步），那只是任务
-- 白名单，真正的计时只由这里的 Quartz 负责。
-- ============================================================================

USE `jmh_data_platform`;


-- ============================================================================
-- 第1步【只读】先看清楚现在有哪些相关任务
--
-- status: 0=正常运行  1=暂停
-- ============================================================================
SELECT job_id, job_name, invoke_target, cron_expression, misfire_policy, concurrent, status
FROM sys_job
WHERE invoke_target LIKE 'pythonEbayStoreListingTask%'
   OR invoke_target LIKE 'pythonFeishuBadTransactionTask%'
   OR invoke_target LIKE 'pythonEbayTokenHealthTask%'
ORDER BY job_name;


-- ============================================================================
-- 第2步 eBay 在售刊登每月同步：每月5日 05:00
--
-- 这是「EBAY · 美元价格结构」的数据源头。2026-09-23 曾把这条任务下线过，
-- 如果当时执行过下线脚本，这里会重新建出来；没执行过就只是刷新名称与备注。
-- ============================================================================
START TRANSACTION;

UPDATE sys_job SET job_name='eBay店铺商品信息每月同步',
 cron_expression='0 0 5 5 * ?', invoke_target='pythonEbayStoreListingTask.runMonthly()',
 misfire_policy='2', concurrent='1', update_by='SYSTEM', update_time=NOW(),
 remark='每月5日北京时间05:00；服务器时区Asia/Shanghai；官方Trading在售商品；按配置账号完整拉取校验后按月覆盖，失败保留旧数据。拉完由价格结构页的刷新按钮走ODS->DWD->DWS重算。'
WHERE invoke_target IN ('pythonEbayStoreListingTask.runMonthly',
                        'pythonEbayStoreListingTask.runMonthly()');

INSERT INTO sys_job (job_name,job_group,invoke_target,cron_expression,misfire_policy,concurrent,status,create_by,create_time,remark)
SELECT 'eBay店铺商品信息每月同步','DEFAULT','pythonEbayStoreListingTask.runMonthly()',
 '0 0 5 5 * ?','2','1','0','SYSTEM',NOW(),
 '每月5日北京时间05:00；服务器时区Asia/Shanghai；官方Trading在售商品；按配置账号完整拉取校验后按月覆盖，失败保留旧数据。拉完由价格结构页的刷新按钮走ODS->DWD->DWS重算。'
WHERE NOT EXISTS (SELECT 1 FROM sys_job
                  WHERE invoke_target IN ('pythonEbayStoreListingTask.runMonthly',
                                          'pythonEbayStoreListingTask.runMonthly()'));

COMMIT;


-- ============================================================================
-- 第3步 飞书不良交易刊登每周同步：每周三 18:00
--
-- 「产品结构」里不良交易率那张图的数据源。一般早就建好了，这一步只是
-- 确保它在、且参数正确；已存在就只刷新名称与备注，不动启停状态。
-- ============================================================================
START TRANSACTION;

UPDATE sys_job SET job_name='飞书不良交易刊登每周同步',
 cron_expression='0 0 18 ? * WED', invoke_target='pythonFeishuBadTransactionTask.runWeekly()',
 misfire_policy='2', concurrent='1', update_by='SYSTEM', update_time=NOW(),
 remark='每周三北京时间18:00；服务器时区Asia/Shanghai；按当月拉取并增量upsert，内容未变的行不写；失败整批回滚不影响历史批次。'
WHERE invoke_target IN ('pythonFeishuBadTransactionTask.runWeekly',
                        'pythonFeishuBadTransactionTask.runWeekly()');

INSERT INTO sys_job (job_name,job_group,invoke_target,cron_expression,misfire_policy,concurrent,status,create_by,create_time,remark)
SELECT '飞书不良交易刊登每周同步','DEFAULT','pythonFeishuBadTransactionTask.runWeekly()',
 '0 0 18 ? * WED','2','1','0','SYSTEM',NOW(),
 '每周三北京时间18:00；服务器时区Asia/Shanghai；按当月拉取并增量upsert，内容未变的行不写；失败整批回滚不影响历史批次。'
WHERE NOT EXISTS (SELECT 1 FROM sys_job
                  WHERE invoke_target IN ('pythonFeishuBadTransactionTask.runWeekly',
                                          'pythonFeishuBadTransactionTask.runWeekly()'));

COMMIT;


-- ============================================================================
-- 第4步【只读】验收
--
-- 预期：两条任务都在，status=0（正常运行）。
-- 若某条 status=1（暂停），是有人主动停过，本脚本不会替你启用——
-- 确认要启用再手动改：UPDATE sys_job SET status='0' WHERE job_id=<那条的id>;
-- ============================================================================
SELECT job_id, job_name, invoke_target, cron_expression, misfire_policy, concurrent,
       status, IF(status='0','正常运行','已暂停') AS 状态说明
FROM sys_job
WHERE invoke_target LIKE 'pythonEbayStoreListingTask%'
   OR invoke_target LIKE 'pythonFeishuBadTransactionTask%'
   OR invoke_target LIKE 'pythonEbayTokenHealthTask%'
ORDER BY job_name;

-- 同一个 invoke_target 只应有一条；出现多条说明以前手动建重了，需人工清理。
SELECT invoke_target AS 重复的任务, COUNT(*) AS 条数
FROM sys_job
WHERE invoke_target LIKE 'pythonEbayStoreListingTask%'
   OR invoke_target LIKE 'pythonFeishuBadTransactionTask%'
GROUP BY invoke_target HAVING COUNT(*) > 1;
