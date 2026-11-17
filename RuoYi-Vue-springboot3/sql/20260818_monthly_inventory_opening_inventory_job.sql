-- 目标库：jmh_data_platform（Java ERP / Quartz数据库）。
-- 每月2日23:00调用Python，用上月期末数回填次月月初库存数量。

UPDATE sys_job
SET job_name = '月度库存次月月初库存填充',
    job_group = 'DATA_CENTER',
    invoke_target = 'pythonMonthlyInventoryReportTask.fillPreviousMonthOpeningInventory()',
    cron_expression = '0 0 23 2 * ?',
    misfire_policy = '2',
    concurrent = '1',
    status = '0',
    update_by = 'SYSTEM',
    update_time = NOW(),
    remark = '每月2日23:00将上月海外仓与FBA仓期末库存数量之和回填为次月月初库存数量。'
WHERE invoke_target IN (
    'pythonMonthlyInventoryReportTask.fillPreviousMonthOpeningInventory',
    'pythonMonthlyInventoryReportTask.fillPreviousMonthOpeningInventory()'
);

INSERT INTO sys_job (
    job_name, job_group, invoke_target, cron_expression,
    misfire_policy, concurrent, status,
    create_by, create_time, remark
)
SELECT
    '月度库存次月月初库存填充',
    'DATA_CENTER',
    'pythonMonthlyInventoryReportTask.fillPreviousMonthOpeningInventory()',
    '0 0 23 2 * ?',
    '2', '1', '0',
    'SYSTEM', NOW(),
    '每月2日23:00将上月海外仓与FBA仓期末库存数量之和回填为次月月初库存数量。'
WHERE NOT EXISTS (
    SELECT 1
    FROM sys_job
    WHERE invoke_target IN (
        'pythonMonthlyInventoryReportTask.fillPreviousMonthOpeningInventory',
        'pythonMonthlyInventoryReportTask.fillPreviousMonthOpeningInventory()'
    )
);

SELECT job_id,job_name,job_group,invoke_target,cron_expression,
       misfire_policy,concurrent,status,remark
FROM sys_job
WHERE invoke_target IN (
    'pythonMonthlyInventoryReportTask.fillPreviousMonthOpeningInventory',
    'pythonMonthlyInventoryReportTask.fillPreviousMonthOpeningInventory()'
);
