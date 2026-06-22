-- ============================================================
-- Amazon FBA 货件数据表
-- 数据来源：领星 API /erp/sc/data/fba_report/shipmentList
-- 每行 = 一个货件的 item_list 中的一条明细
-- ============================================================
USE `jmh_data_platform`;

DROP TABLE IF EXISTS `amz_fba_shipment`;
CREATE TABLE `amz_fba_shipment` (
    `id`                    BIGINT(20)   NOT NULL AUTO_INCREMENT COMMENT '主键',
    `sid`                   INT(11)      NOT NULL                COMMENT '店铺ID',
    `username`              VARCHAR(100) DEFAULT ''              COMMENT '创建人姓名',
    `shipment_id`           VARCHAR(100) NOT NULL                COMMENT '亚马逊货件编号',
    `shipment_name`         VARCHAR(200) DEFAULT ''              COMMENT '货件名称',
    `msku`                  VARCHAR(200) NOT NULL                COMMENT 'MSKU',
    `sku`                   VARCHAR(200) DEFAULT ''              COMMENT 'SKU',
    `quantity_shipped`      INT(11)      DEFAULT 0               COMMENT '当前申报量',
    `init_quantity_shipped` INT(11)      DEFAULT 0               COMMENT '货件初始申报量',
    `quantity_received`     INT(11)      DEFAULT 0               COMMENT '签收数量',
    `quantity_shipped_local` INT(11)     DEFAULT 0               COMMENT '已发货数量（本地数据）',
    `declared_diff`         INT(11)      DEFAULT 0               COMMENT '申收差异 = 申报量 - 签收量',
    `gmt_create`            DATETIME     DEFAULT NULL            COMMENT '货件创建时间',
    `gmt_modified`          DATETIME     DEFAULT NULL            COMMENT '数据更新时间',
    `create_time`           DATETIME     DEFAULT CURRENT_TIMESTAMP COMMENT '记录创建时间',
    `update_time`           DATETIME     DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '记录更新时间',
    PRIMARY KEY (`id`),
    UNIQUE KEY `uk_sid_shipment_sku` (`sid`, `shipment_id`, `sku`),
    KEY `idx_sid` (`sid`),
    KEY `idx_shipment_id` (`shipment_id`),
    KEY `idx_msku` (`msku`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Amazon FBA货件明细表';
