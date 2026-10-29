-- Java数据库：AMZ Listing保留接口原币种；独立混销售价任务，不改原eBay刊登任务。
USE jmh_data_platform;
SET NAMES utf8mb4;
SET @mixed_currency_ddl := IF(
 (SELECT COUNT(*) FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=DATABASE()
   AND TABLE_NAME='amz_product_listing' AND COLUMN_NAME='currency_code')=0,
 'ALTER TABLE amz_product_listing ADD COLUMN currency_code VARCHAR(16) NULL COMMENT ''Listing接口原始currency_code，不换汇'' AFTER price',
 'SELECT ''currency_code already exists''');
PREPARE mixed_currency_statement FROM @mixed_currency_ddl;
EXECUTE mixed_currency_statement;
DEALLOCATE PREPARE mixed_currency_statement;

INSERT INTO sys_job(job_name,job_group,invoke_target,cron_expression,misfire_policy,concurrent,status,create_by,create_time,remark)
SELECT '混销-eBay在售售价月度同步','DEFAULT','pythonEbayMixedSalesPriceTask.runMonthly()',
 '0 0 7 3 * ?','3','1','0','SYSTEM',NOW(),
 '每月3日北京时间07:00；仅完整核验后覆盖店铺当月快照，其他月份保留；原币售价，独立于原刊登同步'
WHERE NOT EXISTS(SELECT 1 FROM sys_job WHERE invoke_target='pythonEbayMixedSalesPriceTask.runMonthly()');
SELECT job_id,job_name,invoke_target,cron_expression,status FROM sys_job
WHERE invoke_target='pythonEbayMixedSalesPriceTask.runMonthly()';
