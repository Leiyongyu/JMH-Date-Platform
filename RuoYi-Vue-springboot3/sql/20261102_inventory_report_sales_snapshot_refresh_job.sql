-- 目标库：jmh_data_platform（Java ERP）。
-- 功能：新增 Quartz 任务“月度库存上月销售回填补偿”，每天13:00调用Python补偿接口。
-- 安全性：只插入一条 sys_job；已存在同一入口时不重复插入，不改其他任务和业务数据。
-- 需在部署包含 pythonMonthlyInventoryReportTask.refreshPreviousMonthSalesSnapshot 的新版 Java 后执行，
-- 执行后重启 Java（或在任务页面刷新）使 Quartz 加载。

INSERT INTO `sys_job` (
    `job_name`, `job_group`, `invoke_target`, `cron_expression`,
    `misfire_policy`, `concurrent`, `status`,
    `create_by`, `create_time`, `remark`
)
SELECT
    '月度库存上月销售回填补偿',
    'DATA_CENTER',
    'pythonMonthlyInventoryReportTask.refreshPreviousMonthSalesSnapshot()',
    '0 0 13 * * ?',
    '2', '1', '0',
    'SYSTEM', NOW(),
    '每天13:00用已入库的上月销量、实际达成和汇率回填上月月度库存报表快照；回填失败或版本落后时自动补齐，不调用领星接口'
WHERE NOT EXISTS (
    SELECT 1 FROM `sys_job`
    WHERE `invoke_target` IN (
        'pythonMonthlyInventoryReportTask.refreshPreviousMonthSalesSnapshot',
        'pythonMonthlyInventoryReportTask.refreshPreviousMonthSalesSnapshot()'
    )
);
