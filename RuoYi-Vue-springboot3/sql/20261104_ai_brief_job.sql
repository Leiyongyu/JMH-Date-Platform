-- Target DB: jmh_data_platform (Java ERP). Adds one Quartz job for AI assistant scheduled briefs.
-- Runs hourly at minute 2; only briefs created by users and due now are executed.
-- Safe to re-run: inserts only when the job does not exist; changes no other job or data.
-- Execute after deploying the Java build that contains aiBriefTask and the Python agent migration 20261104.
USE jmh_data_platform;
INSERT INTO sys_job(job_name,job_group,invoke_target,cron_expression,misfire_policy,concurrent,status,create_by,create_time,remark)
SELECT 'AI assistant scheduled briefs','DEFAULT','aiBriefTask.runDue()',
 '0 2 * * * ?','3','1','0','SYSTEM',NOW(),
 'Hourly at :02 Beijing time; runs due briefs with each owner''s current permissions and data scope'
WHERE NOT EXISTS(SELECT 1 FROM sys_job WHERE invoke_target='aiBriefTask.runDue()');
