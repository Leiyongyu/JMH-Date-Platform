-- 在Python业务库 date-project 执行；仅新建表，不补造过去月份。
CREATE TABLE IF NOT EXISTS dws_home_inventory_sku_monthly (
    stat_month CHAR(7) NOT NULL COMMENT '实际统计月份YYYY-MM；同月更新，跨月保留',
    rule_version INT NOT NULL COMMENT 'SKU统计口径版本，跨版本不做环比',
    sku_count BIGINT UNSIGNED NOT NULL COMMENT 'AMZ和eBay首页负责人统计SKU数之和，含未分配',
    amz_sku_count BIGINT UNSIGNED NOT NULL COMMENT 'AMZ负责人及卖家SKU去重后合计',
    ebay_sku_count BIGINT UNSIGNED NOT NULL COMMENT 'eBay负责人及MSKU去重后合计',
    captured_at DATETIME NOT NULL COMMENT '实际采集时间，北京时间；不是补算历史日期',
    payload_json JSON NOT NULL COMMENT '平台汇总、来源更新时间及口径；不含密钥',
    PRIMARY KEY (stat_month)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='首页库存分析在售SKU月度统计快照，不改刊登源数据';
