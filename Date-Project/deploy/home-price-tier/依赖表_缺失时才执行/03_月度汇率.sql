-- 只建表，不写入源数据、不注册同步任务。
USE `date-project`;
CREATE TABLE IF NOT EXISTS `dim_lingxing_currency_month` (
    `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '主键',
    `rate_month` CHAR(7) NOT NULL COMMENT '汇率月份YYYY-MM；领星date字段',
    `currency_code` VARCHAR(16) NOT NULL COMMENT '币种代码；领星code字段',
    `my_rate` DECIMAL(20,6) NOT NULL COMMENT '我的汇率；领星my_rate，系统优先使用',
    `rate_org` DECIMAL(20,6) NULL COMMENT '官方汇率；领星rate_org，仅留档',
    `sync_batch_id` VARCHAR(64) NULL COMMENT '同步批次ID',
    `synced_at` DATETIME NULL COMMENT '同步时间',
    `create_time` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '记录创建时间',
    `update_time` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '记录更新时间',
    PRIMARY KEY (`id`),
    UNIQUE KEY `uk_currency_month` (`rate_month`, `currency_code`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='DIM-领星月度汇率';
