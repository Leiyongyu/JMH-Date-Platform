-- Target DB: jmh_data_platform (Java ERP). Pure ASCII: Chinese text is written as UTF-8 hex literals.
-- Adds one Quartz job: the open CTU eBay warehouse orders of the Feishu bitable "auto parts purchase orders" are synced every day at
-- 08:00 / 13:00 / 18:00 (Python task feishu_auto_parts_order_sync); eBay replenishment 2.0 reads it for the
-- purchase logistics column. No table structure change, no menu change.
-- Safe to re-run; changes nothing else. Execute after deploying the Java build that contains
-- pythonFeishuAutoPartsOrderTask, and after date-project migration 20261113_feishu_auto_parts_order.sql.
USE jmh_data_platform;
SET NAMES utf8mb4;
INSERT INTO sys_job(job_name,job_group,invoke_target,cron_expression,misfire_policy,concurrent,status,create_by,create_time,remark)
SELECT CONVERT(X'E9A39EE4B9A6E6B1BDE9858DE8AEA2E58D95E5908CE6ADA5' USING utf8mb4),'DATA_CENTER','pythonFeishuAutoPartsOrderTask.run()','0 0 8,13,18 * * ?','3','1','0','SYSTEM',NOW(),
  CONVERT(X'E6AF8FE5A4A930383A3030E3808131333A3030E3808131383A3030E5908CE6ADA5E9A39EE4B9A6E6B1BDE9858DE8AEA2E58D9543545565626179E4BB93E69CAAE5AE8CE68890E98787E8B4ADE58D95EFBC88E4B88DE590AB414D5AE4BB93E38081E5B7B2E5AE8CE68890E38081E5B7B2E58F96E6B688EFBC89EFBC8CE4BE9B65426179E8A1A5E8B4A7322E30E789A9E6B581E78AB6E68081E4BDBFE794A8EFBC9BE99C80E8A681E7AB8BE58DB3E79C8BE588B0E9A39EE4B9A6E694B9E58AA8E697B6E5AFB9E69CACE4BBBBE58AA1E689A7E8A18CE4B880E6ACA1' USING utf8mb4)
WHERE NOT EXISTS(SELECT 1 FROM sys_job WHERE invoke_target='pythonFeishuAutoPartsOrderTask.run()');
