-- 目标库：jmh_data_platform（Java ERP / Quartz 数据库）。
-- 注册月度库存统计表数据拉取任务，不创建 Python ODS/DWD/DWS 表。

UPDATE sys_job
SET job_name = '月度库存统计表数据拉取',
    job_group = 'DATA_CENTER',
    invoke_target = 'pythonMonthlyInventoryReportTask.syncPreviousMonth()',
    cron_expression = '0 0 6 1 * ?',
    misfire_policy = '2',
    concurrent = '1',
    status = '0',
    update_by = 'SYSTEM',
    update_time = NOW(),
    remark = '每月1日06:00调用Python拉取上月FBA、海外仓、本地仓数据，每月2日23:00回填次月月初库存，每月11日23:00拉取上月Amazon实际达成和销量。'
WHERE invoke_target IN (
    'pythonMonthlyInventoryReportTask.syncCurrentMonth',
    'pythonMonthlyInventoryReportTask.syncCurrentMonth()',
    'pythonMonthlyInventoryReportTask.syncPreviousMonth',
    'pythonMonthlyInventoryReportTask.syncPreviousMonth()'
);

INSERT INTO sys_job (
    job_name, job_group, invoke_target, cron_expression,
    misfire_policy, concurrent, status,
    create_by, create_time, remark
)
SELECT
    '月度库存统计表数据拉取',
    'DATA_CENTER',
    'pythonMonthlyInventoryReportTask.syncPreviousMonth()',
    '0 0 6 1 * ?',
    '2', '1', '0',
    'SYSTEM', NOW(),
    '每月1日06:00调用Python拉取上月FBA、海外仓、本地仓数据，每月2日23:00回填次月月初库存，每月11日23:00拉取上月Amazon实际达成和销量。'
WHERE NOT EXISTS (
    SELECT 1
    FROM sys_job
    WHERE invoke_target IN (
        'pythonMonthlyInventoryReportTask.syncCurrentMonth',
        'pythonMonthlyInventoryReportTask.syncCurrentMonth()',
        'pythonMonthlyInventoryReportTask.syncPreviousMonth',
        'pythonMonthlyInventoryReportTask.syncPreviousMonth()'
    )
);

SELECT job_id, job_name, job_group, invoke_target,
       cron_expression, misfire_policy, concurrent, status
FROM sys_job
WHERE invoke_target IN (
    'pythonMonthlyInventoryReportTask.syncCurrentMonth',
    'pythonMonthlyInventoryReportTask.syncCurrentMonth()',
    'pythonMonthlyInventoryReportTask.syncPreviousMonth',
    'pythonMonthlyInventoryReportTask.syncPreviousMonth()'
);
