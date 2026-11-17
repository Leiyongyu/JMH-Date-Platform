-- 在 Python 数据库 date-project 执行；仅新增报表表，不修改任何 ODS 原始数据。
CREATE TABLE IF NOT EXISTS dws_ebay_price_tier_report (
    id TINYINT UNSIGNED NOT NULL COMMENT '单例主键，固定为1，仅保存最新报表',
    report_id CHAR(36) NOT NULL COMMENT '报表计算批次UUID',
    generated_at DATETIME NOT NULL COMMENT '报表生成北京时间',
    source_state_json JSON NOT NULL COMMENT '原始表账号批次、行数及拉取时间，用于检测报表是否过期',
    summary_json JSON NOT NULL COMMENT '报表总体统计及口径版本，不含凭证',
    PRIMARY KEY (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin COMMENT='eBay原币种价格分层报表发布状态；与原始表隔离';

CREATE TABLE IF NOT EXISTS dws_ebay_price_tier (
    seller_user_id VARCHAR(128) NOT NULL COMMENT '原始表稳定账号标识',
    seller_account VARCHAR(128) NOT NULL COMMENT 'eBay店铺账号',
    site VARCHAR(16) NOT NULL COMMENT '刊登站点代码；空字符串表示缺失',
    currency VARCHAR(16) NOT NULL COMMENT '原币种代码，不进行汇率换算；空字符串表示缺失',
    tier_no TINYINT UNSIGNED NOT NULL COMMENT '档位1至6：小于10、10至100、100至300、300至500、500至1000、大于等于1000；区间左闭右开',
    sku_count BIGINT UNSIGNED NOT NULL COMMENT '本档去重SKU数量；同账号站点币种SKU取最低有效价格',
    sku_percent DECIMAL(7,2) NOT NULL COMMENT '本档SKU占已成功归档SKU的百分数，两位小数',
    group_sku_count BIGINT UNSIGNED NOT NULL COMMENT '本账号站点币种成功归档的去重SKU总数',
    unclassified_sku_count BIGINT UNSIGNED NOT NULL COMMENT '有SKU但无有效价格或站点币种缺失的去重SKU数，不参与占比',
    missing_sku_rows BIGINT UNSIGNED NOT NULL COMMENT '缺少SKU的候选记录数；多规格按变体计',
    invalid_price_rows BIGINT UNSIGNED NOT NULL COMMENT '价格或站点币种无效的候选记录数，可能与缺SKU重叠',
    candidate_count BIGINT UNSIGNED NOT NULL COMMENT '归档前候选数；多规格取变体，不重复计父商品',
    source_listing_count BIGINT UNSIGNED NOT NULL COMMENT '涉及原始刊登数量，同一刊登在本组仅计一次',
    report_id CHAR(36) NOT NULL COMMENT '对应已发布报表的计算批次',
    PRIMARY KEY (seller_user_id,site,currency,tier_no)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin COMMENT='eBay店铺站点原币种六档SKU数量与占比汇总；仅存最新计算结果';
