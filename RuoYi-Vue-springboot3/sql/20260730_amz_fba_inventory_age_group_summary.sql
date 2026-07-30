-- Amazon FBA 库龄最终展示汇总表。
-- 每个 pull_month 固定按 EU、US1、US2、US3 汇总。

CREATE TABLE IF NOT EXISTS amz_fba_inventory_age_group_summary (
    id BIGINT NOT NULL AUTO_INCREMENT COMMENT '主键',
    pull_month CHAR(7) NOT NULL COMMENT '拉取年月 YYYY-MM',
    region_code VARCHAR(10) NOT NULL COMMENT '区域编码：EU/US',
    region_name VARCHAR(20) NOT NULL COMMENT '区域名称：欧洲组/美国组',
    group_code VARCHAR(20) NOT NULL COMMENT '组编码：EU/US1/US2/US3',
    group_name VARCHAR(50) NOT NULL COMMENT '展示组名',
    shop_count INT NOT NULL DEFAULT 0 COMMENT '匹配店铺数',
    source_row_count INT NOT NULL DEFAULT 0 COMMENT '源快照记录数',
    inventory_0_90_qty DECIMAL(24, 6) NOT NULL DEFAULT 0 COMMENT '0-90天库存数量',
    inventory_0_90_cost DECIMAL(24, 6) NOT NULL DEFAULT 0 COMMENT '0-90天库龄成本',
    inventory_91_180_qty DECIMAL(24, 6) NOT NULL DEFAULT 0 COMMENT '91-180天库存数量',
    inventory_91_180_cost DECIMAL(24, 6) NOT NULL DEFAULT 0 COMMENT '91-180天库龄成本',
    inventory_181_plus_qty DECIMAL(24, 6) NOT NULL DEFAULT 0 COMMENT '181天以上库存数量',
    inventory_181_plus_cost DECIMAL(24, 6) NOT NULL DEFAULT 0 COMMENT '181天以上库龄成本',
    total_inventory_qty DECIMAL(24, 6) NOT NULL DEFAULT 0 COMMENT '三个库龄段库存合计',
    total_inventory_cost DECIMAL(24, 6) NOT NULL DEFAULT 0 COMMENT '三个库龄段成本合计',
    pulled_at DATETIME NOT NULL COMMENT '源数据拉取时间',
    create_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    update_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
        ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uk_pull_month_group (pull_month, group_code),
    KEY idx_pull_month_region (pull_month, region_code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='Amazon FBA库龄最终分组汇总';
