-- 每月部门海外仓库龄成本，以及滞销清货 US3 拆分。
-- 可重复执行；执行库：Date-Project。

CREATE TABLE IF NOT EXISTS dwd_inventory_age_cost_monthly (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    cost_month CHAR(7) NOT NULL COMMENT '成本所属月份；页面在下一月快照中作为上月成本',
    department_code VARCHAR(50) NOT NULL COMMENT 'Excel部门原值，例如AMZ-US2-MJ',
    group_code VARCHAR(20) NULL COMMENT 'AMZ页面组别；非AMZ部门为空',
    inventory_91_180_cost DECIMAL(24,6) NOT NULL DEFAULT 0 COMMENT '海外仓90/91-180天货值',
    inventory_181_plus_cost DECIMAL(24,6) NOT NULL DEFAULT 0 COMMENT '海外仓180/181天以上货值',
    source_file_name VARCHAR(255) NOT NULL,
    source_sheet VARCHAR(100) NOT NULL,
    source_row INT NOT NULL,
    import_batch_id VARCHAR(64) NOT NULL,
    operator VARCHAR(100) NULL,
    create_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    update_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uk_inventory_age_cost_month_department (cost_month,department_code),
    KEY idx_inventory_age_cost_month_group (cost_month,group_code),
    KEY idx_inventory_age_cost_batch (import_batch_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='DWD-每月上传的部门海外仓库龄成本快照';

-- 只改原 US3 店铺：新志楠、富琳顿（兼容“富林顿”写法）归 US2-MJ，其他归 US1-ZXY。
UPDATE dwd_amz_fba_inventory_monthly_snapshot
SET group_code = CASE
        WHEN store_name LIKE 'US3-新志楠%'
          OR store_name LIKE 'US3-富琳顿%'
          OR store_name LIKE 'US3-富林顿%'
        THEN 'US2-MJ'
        ELSE 'US1-ZXY'
    END,
    group_match_source = 'shop_list_us3_split'
WHERE store_name LIKE 'US3-%';

-- 重建受 US3 拆分影响月份的全部组汇总，EU/US1/US2 数值按原 DWD 数据重新汇总，口径不变。
DELETE g
FROM dws_amz_fba_inventory_age_group g
WHERE g.pull_month IN (
    SELECT affected.pull_month
    FROM (
        SELECT DISTINCT pull_month
        FROM dwd_amz_fba_inventory_monthly_snapshot
        WHERE group_code IN ('US2-MJ', 'US1-ZXY')
    ) affected
);

INSERT INTO dws_amz_fba_inventory_age_group (
    pull_month,region_code,region_name,group_code,group_name,
    shop_count,source_row_count,inventory_0_90_qty,inventory_0_90_cost,
    inventory_91_180_qty,inventory_91_180_cost,
    inventory_181_plus_qty,inventory_181_plus_cost,
    total_inventory_qty,total_inventory_cost,pulled_at
)
SELECT
    d.pull_month,
    d.region_code,
    d.region_name,
    d.group_code,
    d.group_code,
    COUNT(DISTINCT NULLIF(d.sid, '0')),
    COUNT(*),
    SUM(d.inventory_0_90_qty),
    SUM(d.inventory_0_90_cost),
    SUM(d.inventory_91_180_qty),
    SUM(d.inventory_91_180_cost),
    SUM(d.inventory_181_plus_qty),
    SUM(d.inventory_181_plus_cost),
    SUM(d.total_inventory_qty),
    SUM(d.total_inventory_cost),
    MAX(d.pulled_at)
FROM dwd_amz_fba_inventory_monthly_snapshot d
WHERE d.pull_month IN (
    SELECT affected.pull_month
    FROM (
        SELECT DISTINCT pull_month
        FROM dwd_amz_fba_inventory_monthly_snapshot
        WHERE group_code IN ('US2-MJ', 'US1-ZXY')
    ) affected
)
GROUP BY d.pull_month,d.region_code,d.region_name,d.group_code;
