-- 成都中转仓31天及以上库存库龄明细与分组汇总；仅新增表，不修改既有数据。

CREATE TABLE IF NOT EXISTS ods_lingxing_ctu_inventory_detail (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '主键',
    pull_month CHAR(7) NOT NULL COMMENT '快照标签月份YYYY-MM；接口仅返回实时库存，不支持补拉历史',
    wid VARCHAR(32) NOT NULL COMMENT '领星仓库ID',
    warehouse_name VARCHAR(200) NULL COMMENT '成都中转仓名称',
    group_code VARCHAR(20) NOT NULL COMMENT '映射后的组别：EU、US1、US2、US3、EBAY-1',
    sku VARCHAR(255) NULL COMMENT 'SKU；领星sku原值',
    product_id VARCHAR(64) NULL COMMENT '本地产品ID；领星product_id原值',
    product_total DECIMAL(24,6) NULL COMMENT '实际库存总量；领星product_total原值',
    stock_price DECIMAL(24,6) NULL COMMENT '单位库存成本；领星stock_price原值',
    average_age INT NULL COMMENT '平均库龄天数；领星average_age原值',
    over_30_qty DECIMAL(24,6) NOT NULL DEFAULT 0 COMMENT '该SKU 31天及以上库存数量',
    over_30_cost DECIMAL(24,6) NOT NULL DEFAULT 0 COMMENT '该SKU 31天及以上库龄成本；数量乘单位库存成本',
    stock_age_list JSON NULL COMMENT '库龄分档数组原值；领星stock_age_list',
    raw_json JSON NULL COMMENT '接口返回的整条记录原值，用于追溯',
    sync_batch_id VARCHAR(64) NOT NULL COMMENT '同步批次ID',
    pulled_at DATETIME NOT NULL COMMENT '实际拉取时间',
    create_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '记录创建时间',
    PRIMARY KEY (id),
    KEY idx_ctu_month_wid (pull_month,wid),
    KEY idx_ctu_month_group (pull_month,group_code),
    KEY idx_ctu_month_sku (pull_month,sku),
    KEY idx_ctu_batch (sync_batch_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='ODS-领星成都中转仓库存库龄明细';

CREATE TABLE IF NOT EXISTS dws_ctu_inventory_age_group (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '主键',
    pull_month CHAR(7) NOT NULL COMMENT '快照标签月份YYYY-MM',
    group_code VARCHAR(20) NOT NULL COMMENT '组别：EU、US1、US2、US3、EBAY-1',
    warehouse_count INT NOT NULL DEFAULT 0 COMMENT '参与汇总的仓库数',
    source_row_count INT NOT NULL DEFAULT 0 COMMENT '参与汇总的明细行数',
    over_30_qty DECIMAL(24,6) NOT NULL DEFAULT 0 COMMENT '31天及以上库存数量合计',
    over_30_cost DECIMAL(24,6) NOT NULL DEFAULT 0 COMMENT '31天及以上库龄成本合计',
    pulled_at DATETIME NOT NULL COMMENT '实际拉取时间',
    create_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '记录创建时间',
    update_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '记录更新时间',
    PRIMARY KEY (id),
    UNIQUE KEY uk_ctu_group (pull_month,group_code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='DWS-成都中转仓31天及以上库龄分组汇总';
