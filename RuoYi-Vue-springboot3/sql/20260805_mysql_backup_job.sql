-- ERP MySQL每日全量备份Quartz任务，可重复执行。
-- 执行前必须：
-- 1. 使用Java服务运行账户配置 mysql_config_editor --login-path=jmh_backup；
-- 2. 确认该账户可写NAS目录；
-- 3. 确认application.yml中的jmh.mysql-backup配置正确。

UPDATE sys_job
SET job_name = 'MySQL双库每日全量备份',
    job_group = 'SYSTEM',
    invoke_target = 'mysqlBackupTask.backup()',
    cron_expression = '0 0 20 * * ?',
    misfire_policy = '2',
    concurrent = '1',
    status = '0',
    update_by = 'SYSTEM',
    update_time = NOW(),
    remark = '每天20:00备份Date-Project、jmh_data_platform到NAS；保留最近30天；错过后立即补跑；禁止并发'
WHERE invoke_target IN (
  'mysqlBackupTask.backup',
  'mysqlBackupTask.backup()'
);

INSERT INTO sys_job (
  job_name, job_group, invoke_target, cron_expression,
  misfire_policy, concurrent, status,
  create_by, create_time, remark
)
SELECT
  'MySQL双库每日全量备份',
  'SYSTEM',
  'mysqlBackupTask.backup()',
  '0 0 20 * * ?',
  '2',
  '1',
  '0',
  'SYSTEM',
  NOW(),
  '每天20:00备份Date-Project、jmh_data_platform到NAS；保留最近30天；错过后立即补跑；禁止并发'
WHERE NOT EXISTS (
  SELECT 1
  FROM sys_job
  WHERE invoke_target IN (
    'mysqlBackupTask.backup',
    'mysqlBackupTask.backup()'
  )
);

SELECT job_id, job_name, job_group, invoke_target,
       cron_expression, misfire_policy, concurrent, status, remark
FROM sys_job
WHERE invoke_target IN (
  'mysqlBackupTask.backup',
  'mysqlBackupTask.backup()'
);
