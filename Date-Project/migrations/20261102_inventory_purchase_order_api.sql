-- 手动执行于 Python 数据库。仅新增表和任务登记，不修改旧表或已有库存数据。
-- 不加入启动自动迁移；先执行本脚本，再部署服务。
CREATE TABLE IF NOT EXISTS ods_inventory_purchase_order_api_latest (
    order_sn VARCHAR(100) COLLATE utf8mb4_bin NOT NULL,
    payload_json JSON NOT NULL COMMENT '系统/自定义单号及全部商品明细；仅保存计算所需字段',
    sync_batch_id VARCHAR(64) NOT NULL,
    pulled_at DATETIME NOT NULL,
    PRIMARY KEY (order_sn)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS inventory_purchase_order_api_state (
    id TINYINT NOT NULL,
    pulled_at DATETIME NOT NULL COMMENT '上次成功采集开始时间；增量水位',
    full_pulled_at DATETIME NOT NULL COMMENT '上次全量校准开始时间',
    sync_batch_id VARCHAR(64) NOT NULL,
    PRIMARY KEY (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS inventory_purchase_order_api_month (
    stat_month CHAR(7) NOT NULL COMMENT '源数据月份，报表展示月份为次月',
    sync_batch_id VARCHAR(64) NOT NULL,
    pulled_at DATETIME NOT NULL,
    published_at DATETIME NOT NULL,
    result_json JSON NOT NULL COMMENT '数量金额、未识别仓库及接口范围',
    source_json JSON NOT NULL COMMENT '本月待到货采购单完整计算字段；保留自定义单号和明细ID',
    PRIMARY KEY (stat_month)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

INSERT INTO scheduler_task(task_code,task_name,cron_expression,enabled,description)
SELECT 'monthly_inventory_purchase_order_sync','月度库存采购在途同步','0 30 8 * * ?',0,
 'Java Quartz每天08:30调度；只更新当期报表，历史月份保留；Python禁用自动调度避免重复'
WHERE NOT EXISTS(SELECT 1 FROM scheduler_task WHERE task_code='monthly_inventory_purchase_order_sync');
