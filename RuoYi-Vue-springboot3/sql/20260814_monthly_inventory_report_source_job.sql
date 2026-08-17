-- 目标库：jmh_data_platform（Java ERP / Quartz 数据库）。
-- 仅注册三类月度库存报表源数据同步任务，不创建 Python ODS 表。
-- Python 三张表请执行：Date-Project/migrations/20260814_inventory_report_source_tables.sql

UPDATE sys_job
SET job_name = '领星-月度库存报表三接口源数据同步',
    job_group = 'DATA_CENTER',
    invoke_target = 'pythonMonthlyInventoryReportTask.syncPreviousMonth()',
    cron_expression = '0 0 6 1 * ?',
    misfire_policy = '2',
    concurrent = '1',
    status = '0',
    update_by = 'SYSTEM',
    update_time = NOW(),
    remark = '每月1日06:00由Java Quartz调用Python拉取上一个完整自然月三类库存源数据（月初至月末），并重建DWD与DWS报表'
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
    '领星-月度库存报表三接口源数据同步',
    'DATA_CENTER',
    'pythonMonthlyInventoryReportTask.syncPreviousMonth()',
    '0 0 6 1 * ?',
    '2', '1', '0',
    'SYSTEM', NOW(),
    '每月1日06:00由Java Quartz调用Python拉取上一个完整自然月三类库存源数据（月初至月末），并重建DWD与DWS报表'
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
