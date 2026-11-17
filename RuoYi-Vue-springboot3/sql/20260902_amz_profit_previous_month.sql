-- Amazon绩效利润恢复为每月同步上一个完整自然月。
-- 可重复执行；不删除或重算任何业务数据。
-- ERP Quartz任务位于jmh_data_platform；Python调度与利润表位于date-project。

-- 一、ERP Quartz任务
USE `jmh_data_platform`;

START TRANSACTION;

UPDATE sys_job
SET job_name = 'Amazon月度完整订单利润同步',
    job_group = 'FINANCE',
    invoke_target = 'pythonPerformanceTask.syncPreviousMonth()',
    cron_expression = '0 0 22 4 * ?',
    misfire_policy = '2',
    concurrent = '1',
    status = '0',
    update_by = 'SYSTEM',
    update_time = NOW(),
    remark = '每月4日22:00同步上一个完整自然月；手工syncMonth只补跑指定月份'
WHERE job_id = 240
   OR invoke_target IN (
       'pythonPerformanceTask.syncPreviousMonth',
       'pythonPerformanceTask.syncPreviousMonth()',
       'pythonPerformanceTask.syncRecentThreeMonths',
       'pythonPerformanceTask.syncRecentThreeMonths()'
   );

COMMIT;

SELECT job_id, job_name, invoke_target, cron_expression, status, remark
FROM sys_job
WHERE job_id = 240
   OR invoke_target IN (
       'pythonPerformanceTask.syncPreviousMonth',
       'pythonPerformanceTask.syncPreviousMonth()'
   );

-- 二、Python内部调度任务
USE `date-project`;

START TRANSACTION;

UPDATE scheduler_task
SET task_name = 'Amazon月度完整订单利润同步',
    cron_expression = '0 0 22 4 * ?',
    description = '每月4日22:00拉取上一个完整自然月的领星Amazon订单利润',
    update_time = CURRENT_TIMESTAMP
WHERE task_code = 'amz_monthly_order_profit_sync';

COMMIT;

SELECT task_code, task_name, cron_expression, enabled, description
FROM scheduler_task
WHERE task_code = 'amz_monthly_order_profit_sync';

-- 三、Python利润字段注释；DDL会隐式提交，因此不混入上面的事务。
ALTER TABLE ods_lingxing_amz_order_profit_raw
    MODIFY COLUMN net_sales_amount DECIMAL(20,6) NULL
    COMMENT '领星原始净销售额(net_amount)';

ALTER TABLE dwd_amz_monthly_order_profit
    MODIFY COLUMN net_sales_amount DECIMAL(20,6) NOT NULL DEFAULT 0
    COMMENT '业务净销售额=销售额-促销折扣绝对值-退款金额绝对值';
