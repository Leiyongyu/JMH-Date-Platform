-- 目标库：jmh_data_platform（Java ERP / Quartz 数据库）。
-- 每月最后一天23:00填充月度库存报表销量；Python ODS字段请执行对应Python库迁移。

UPDATE sys_job
SET job_name = '月度库存销量填充',
    job_group = 'DATA_CENTER',
    invoke_target = 'pythonMonthlyInventoryReportTask.syncCurrentMonthSalesVolume()',
    cron_expression = '0 0 23 L * ?',
    misfire_policy = '2',
    concurrent = '1',
    status = '0',
    update_by = 'SYSTEM',
    update_time = NOW(),
    remark = '每月最后一天23:00拉取当月完整自然月Amazon订单利润volume并按月覆盖Python ODS、重建销量DWD；eBay销量由jmh_data_platform.ebay_sales按payment_time汇总quantity。'
WHERE invoke_target IN (
    'pythonMonthlyInventoryReportTask.syncCurrentMonthSalesVolume',
    'pythonMonthlyInventoryReportTask.syncCurrentMonthSalesVolume()'
);

INSERT INTO sys_job (
    job_name, job_group, invoke_target, cron_expression,
    misfire_policy, concurrent, status,
    create_by, create_time, remark
)
SELECT
    '月度库存销量填充',
    'DATA_CENTER',
    'pythonMonthlyInventoryReportTask.syncCurrentMonthSalesVolume()',
    '0 0 23 L * ?',
    '2', '1', '0',
    'SYSTEM', NOW(),
    '每月最后一天23:00拉取当月完整自然月Amazon订单利润volume并按月覆盖Python ODS、重建销量DWD；eBay销量由jmh_data_platform.ebay_sales按payment_time汇总quantity。'
WHERE NOT EXISTS (
    SELECT 1
    FROM sys_job
    WHERE invoke_target IN (
        'pythonMonthlyInventoryReportTask.syncCurrentMonthSalesVolume',
        'pythonMonthlyInventoryReportTask.syncCurrentMonthSalesVolume()'
    )
);

SELECT job_id,job_name,job_group,invoke_target,cron_expression,
       misfire_policy,concurrent,status,remark
FROM sys_job
WHERE invoke_target IN (
    'pythonMonthlyInventoryReportTask.syncCurrentMonthSalesVolume',
    'pythonMonthlyInventoryReportTask.syncCurrentMonthSalesVolume()'
);
