-- 目标库：Date-Project Python业务库。
-- 功能：注册“月度库存上月销售回填补偿”任务。只新增/对齐一条任务配置，不改表结构和业务数据。

INSERT INTO `scheduler_task` (
    task_code, task_name, cron_expression, enabled, description
) VALUES (
    'monthly_inventory_report_sales_snapshot_refresh',
    '月度库存上月销售回填补偿',
    '0 0 13 * * ?',
    1,
    '每天13:00用已入库的上月Amazon/eBay销量、实际达成和USD汇率回填上月报表快照，只改销售及关联指标，不调用领星接口'
)
ON DUPLICATE KEY UPDATE
    task_name = VALUES(task_name),
    cron_expression = VALUES(cron_expression),
    description = VALUES(description);
