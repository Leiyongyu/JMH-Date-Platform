-- 在 Java 库 jmh_data_platform 执行，且要在部署完 PythonFeishuBadTransactionTask 之后。
-- 重复执行不会改动任务的启用/暂停状态。
--
-- 触发链路：Quartz -> pythonFeishuBadTransactionTask.runWeekly()
--           -> Python /api/v1/internal/scheduler/tasks/feishu_bad_transaction_sync/run
--           -> 拉飞书视图 vewohlM1T4（当周那一批）-> 按 record_id 增量 upsert
--
-- Python 侧 scheduler_task 里登记的 cron 与这里保持一致（都是周三18:00），
-- 但真正的计时只由 Quartz 负责，Python 那条是任务目录、不自己起定时器。
USE `jmh_data_platform`;
START TRANSACTION;

UPDATE sys_job SET job_name='飞书不良交易刊登每周同步',
 cron_expression='0 0 18 ? * WED',invoke_target='pythonFeishuBadTransactionTask.runWeekly()',
 misfire_policy='2',concurrent='1',update_by='SYSTEM',update_time=NOW(),
 remark='每周三北京时间18:00；服务器时区Asia/Shanghai；只拉飞书视图当周那一批，按record_id增量upsert，内容未变的行不写；失败整批回滚不影响历史批次。'
WHERE invoke_target IN ('pythonFeishuBadTransactionTask.runWeekly','pythonFeishuBadTransactionTask.runWeekly()');

INSERT INTO sys_job (job_name,job_group,invoke_target,cron_expression,misfire_policy,concurrent,status,create_by,create_time,remark)
SELECT '飞书不良交易刊登每周同步','DEFAULT','pythonFeishuBadTransactionTask.runWeekly()',
 '0 0 18 ? * WED','2','1','0','SYSTEM',NOW(),
 '每周三北京时间18:00；服务器时区Asia/Shanghai；只拉飞书视图当周那一批，按record_id增量upsert，内容未变的行不写；失败整批回滚不影响历史批次。'
WHERE NOT EXISTS (SELECT 1 FROM sys_job
                  WHERE invoke_target IN ('pythonFeishuBadTransactionTask.runWeekly','pythonFeishuBadTransactionTask.runWeekly()'));

COMMIT;

-- 只读验证：status=0 表示正常运行，1 表示暂停
SELECT job_id,job_name,invoke_target,cron_expression,misfire_policy,concurrent,status
FROM sys_job
WHERE invoke_target IN ('pythonFeishuBadTransactionTask.runWeekly','pythonFeishuBadTransactionTask.runWeekly()');
