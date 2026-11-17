-- 目标库：jmh_data_platform（仅更新Quartz任务说明，不修改业务数据）。
USE `jmh_data_platform`;

START TRANSACTION;

UPDATE `sys_job`
SET `remark` = '每月1日06:00先同步当月和上月领星全部币种汇率，再拉取上个完整自然月FBA、海外仓、本地仓数据并重建月度库存报表',
    `update_by` = 'SYSTEM',
    `update_time` = NOW()
WHERE `invoke_target` IN (
    'pythonMonthlyInventoryReportTask.syncCurrentMonth',
    'pythonMonthlyInventoryReportTask.syncCurrentMonth()',
    'pythonMonthlyInventoryReportTask.syncPreviousMonth',
    'pythonMonthlyInventoryReportTask.syncPreviousMonth()'
);

COMMIT;

SELECT `job_id`, `job_name`, `invoke_target`, `cron_expression`, `status`, `remark`
FROM `sys_job`
WHERE `invoke_target` IN (
    'pythonMonthlyInventoryReportTask.syncCurrentMonth',
    'pythonMonthlyInventoryReportTask.syncCurrentMonth()',
    'pythonMonthlyInventoryReportTask.syncPreviousMonth',
    'pythonMonthlyInventoryReportTask.syncPreviousMonth()'
);
