-- Java ERP / Quartz库，与Python源数据表分库执行。
-- 首次插入启用；重复执行保留人工启停状态。无硬编码job_id。
-- 新增Bean需要部署新JAR并重启Java；只写sys_job不会刷新运行中的Quartz。
SET NAMES utf8mb4;
USE `jmh_data_platform`;
START TRANSACTION;
UPDATE sys_job
SET job_name='谷仓仓租概要及明细近30天同步', cron_expression='0 0 7 ? * MON',
    invoke_target='pythonGoodcangStorageTask.runWeekly()',
    misfire_policy='2', concurrent='1',
    update_by='SYSTEM', update_time=NOW(),
    remark='每周一北京时间07:00；包含当天近30天；先拉概要单号再逐单分页拉明细；Python两表同事务全量替换。服务器时区须为Asia/Shanghai。'
WHERE invoke_target IN ('pythonGoodcangStorageTask.runWeekly','pythonGoodcangStorageTask.runWeekly()');

INSERT INTO sys_job (job_name,job_group,invoke_target,cron_expression,misfire_policy,
 concurrent,status,create_by,create_time,remark)
SELECT '谷仓仓租概要及明细近30天同步','DEFAULT','pythonGoodcangStorageTask.runWeekly()',
 '0 0 7 ? * MON','2','1','0','SYSTEM',NOW(),
 '每周一北京时间07:00；包含当天近30天；先拉概要单号再逐单分页拉明细；Python两表同事务全量替换。服务器时区须为Asia/Shanghai。'
WHERE NOT EXISTS (SELECT 1 FROM sys_job
 WHERE invoke_target IN ('pythonGoodcangStorageTask.runWeekly','pythonGoodcangStorageTask.runWeekly()'));
COMMIT;
