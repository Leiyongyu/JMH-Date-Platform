-- 目标库：jmh_data_platform（Java ERP数据库）。
-- 功能：将谷仓eBay库龄、领星产品采购与头程源数据刷新并入原FBA库存库龄任务。

UPDATE `sys_job`
SET `job_name`='AMZ FBA与谷仓eBay库存库龄同步',
    `job_group`='FINANCE',
    `invoke_target`='pythonFbaInventoryTask.syncCurrentMonth()',
    `misfire_policy`='2',
    `concurrent`='1',
    `status`='0',
    `update_by`='SYSTEM',
    `update_time`=NOW(),
    `remark`='原FBA库龄链路：先刷新谷仓eBay库存库龄和领星产品采购价/国家头程费用，再调用Python生成AMZ FBA与eBay库龄成本明细及汇总。'
WHERE `invoke_target` IN (
    'pythonFbaInventoryTask.syncCurrentMonth',
    'pythonFbaInventoryTask.syncCurrentMonth()'
);

INSERT INTO `sys_job` (
    `job_name`,`job_group`,`invoke_target`,`cron_expression`,
    `misfire_policy`,`concurrent`,`status`,`create_by`,`create_time`,`remark`
)
SELECT
    'AMZ FBA与谷仓eBay库存库龄同步','FINANCE',
    'pythonFbaInventoryTask.syncCurrentMonth()','0 30 22 1 * ?',
    '2','1','0','SYSTEM',NOW(),
    '原FBA库龄链路：先刷新谷仓eBay库存库龄和领星产品采购价/国家头程费用，再调用Python生成AMZ FBA与eBay库龄成本明细及汇总。'
WHERE NOT EXISTS (
    SELECT 1 FROM `sys_job`
    WHERE `invoke_target` IN (
        'pythonFbaInventoryTask.syncCurrentMonth',
        'pythonFbaInventoryTask.syncCurrentMonth()'
    )
);

-- 两份源数据已经由上面的统一任务顺序拉取，停用原来的独立定时任务，保留手工调用入口。
UPDATE `sys_job`
SET `status`='1',
    `update_by`='SYSTEM',
    `update_time`=NOW(),
    `remark`=CONCAT(
        COALESCE(`remark`,''),
        ' 已并入AMZ FBA与谷仓eBay库存库龄同步任务，独立定时任务停用。'
    )
WHERE `invoke_target` IN (
    'operationSyncTask.syncGoodcangInventoryAge',
    'operationSyncTask.syncGoodcangInventoryAge()',
    'operationSyncTask.syncLingxingProductProcurement',
    'operationSyncTask.syncLingxingProductProcurement()'
);

SELECT `job_id`,`job_name`,`invoke_target`,`cron_expression`,`status`,`remark`
FROM `sys_job`
WHERE `invoke_target` IN (
    'pythonFbaInventoryTask.syncCurrentMonth()',
    'operationSyncTask.syncGoodcangInventoryAge()',
    'operationSyncTask.syncLingxingProductProcurement()'
)
ORDER BY `job_id`;
