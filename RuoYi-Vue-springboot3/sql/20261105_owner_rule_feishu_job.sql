-- Target DB: jmh_data_platform (Java ERP). Pure ASCII: Chinese text is written as UTF-8 hex literals.
-- Adds one Quartz job: owner mapping rules synced daily 05:30 from the Feishu bitable (Python task owner_rule_feishu_sync).
-- Unchanged Feishu content is skipped; only months whose owners changed are re-calculated. Manual Excel upload still works.
-- Safe to re-run; changes nothing else. Execute after deploying the Java build that contains pythonOwnerRuleFeishuTask.
USE jmh_data_platform;
SET NAMES utf8mb4;
INSERT INTO sys_job(job_name,job_group,invoke_target,cron_expression,misfire_policy,concurrent,status,create_by,create_time,remark)
SELECT CONVERT(X'E8B49FE8B4A3E4BABAE698A0E5B084E8A1A8E9A39EE4B9A6E5908CE6ADA5' USING utf8mb4),'DATA_CENTER','pythonOwnerRuleFeishuTask.runDaily()','0 30 5 * * ?','3','1','0','SYSTEM',NOW(),
  CONVERT(X'E6AF8FE5A4A930353A3330E6A380E69FA5E9A39EE4B9A6E5A49AE7BBB4E8A1A8E6A0BCE8B49FE8B4A3E4BABAE698A0E5B084E8A1A8EFBC8CE58685E5AEB9E69C89E58F98E58C96E6898DE585A5E5BA93EFBC8CE58FAAE9878DE7AE97E8B49FE8B4A3E4BABAE69C89E58F98E58C96E69C88E4BBBDE79A84E7BBA9E69588EFBC9BE6898BE5B7A5E4B88AE4BCA0E4BB8DE58FAFE794A8' USING utf8mb4)
WHERE NOT EXISTS(SELECT 1 FROM sys_job WHERE invoke_target='pythonOwnerRuleFeishuTask.runDaily()');
