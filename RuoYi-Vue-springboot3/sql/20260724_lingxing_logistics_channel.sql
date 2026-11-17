-- 领星头程物流渠道完整部署脚本
-- 1) 创建渠道全量表
-- 2) 新增独立 Quartz 任务，默认暂停（status='1'）
-- 可重复执行，不会删除已有渠道数据。

SET NAMES utf8mb4;

CREATE TABLE IF NOT EXISTS `lingxing_logistics_channel` (
  `id` bigint NOT NULL COMMENT '物流渠道ID/物流方案代码',
  `channel_name` varchar(255) DEFAULT NULL COMMENT '物流渠道名称',
  `method_id` varchar(64) DEFAULT NULL COMMENT '运输方式ID',
  `method_name` varchar(128) DEFAULT NULL COMMENT '运输方式名称',
  `billing_type` tinyint DEFAULT NULL COMMENT '计费类型：0计费重，1体积',
  `volume_calc_param` varchar(64) DEFAULT NULL COMMENT '材积计算参数',
  `zip_code` varchar(64) DEFAULT NULL COMMENT '邮编',
  `valid_period` int DEFAULT NULL COMMENT '时效天数',
  `remark` varchar(1000) DEFAULT NULL COMMENT '备注',
  `enabled` tinyint DEFAULT NULL COMMENT '状态：0停用，1启用',
  `last_modify_uid` bigint DEFAULT NULL COMMENT '领星最后更新用户ID',
  `gmt_modified` datetime DEFAULT NULL COMMENT '领星更新时间',
  `provider_id` varchar(64) DEFAULT NULL COMMENT '所属头程物流商ID',
  `provider_name` varchar(255) DEFAULT NULL COMMENT '所属头程物流商名称',
  `freight_json` longtext COMMENT '运费规则数组JSON',
  `send_place_code` varchar(64) DEFAULT NULL COMMENT '提货地代码',
  `receive_country_code` varchar(16) DEFAULT NULL COMMENT '目的国家二字码',
  `is_include_tax` tinyint DEFAULT NULL COMMENT '是否包税：0否，1是',
  `is_points_behind` tinyint DEFAULT NULL COMMENT '是否分抛：0否，1是',
  `points_behind_coefficient` decimal(18,6) DEFAULT NULL COMMENT '分抛系数（不带百分号）',
  `raw_json` longtext COMMENT '领星原始整行JSON，保留未来新增字段',
  `create_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `update_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '修改时间',
  PRIMARY KEY (`id`),
  KEY `idx_lingxing_logistics_channel_enabled` (`enabled`),
  KEY `idx_lingxing_logistics_channel_provider` (`provider_id`),
  KEY `idx_lingxing_logistics_channel_method` (`method_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='领星头程物流渠道全量表';

-- 如果已存在相同任务，则统一修正为标准调用格式并保持暂停。
UPDATE `sys_job`
SET `job_name` = '领星-头程物流渠道',
    `job_group` = 'OPERATION',
    `invoke_target` = 'operationSyncTask.syncLingxingLogisticsChannel()',
    `cron_expression` = '0 30 3 * * ?',
    `misfire_policy` = '1',
    `concurrent` = '1',
    `status` = '1',
    `update_by` = 'SYSTEM',
    `update_time` = NOW(),
    `remark` = '每天03:30全量同步头程物流渠道；默认暂停，确认后在定时任务页面启用'
WHERE `invoke_target` IN (
  'operationSyncTask.syncLingxingLogisticsChannel',
  'operationSyncTask.syncLingxingLogisticsChannel()'
);

INSERT INTO `sys_job` (
  `job_name`, `job_group`, `invoke_target`, `cron_expression`,
  `misfire_policy`, `concurrent`, `status`,
  `create_by`, `create_time`, `update_by`, `update_time`, `remark`
)
SELECT
  '领星-头程物流渠道',
  'OPERATION',
  'operationSyncTask.syncLingxingLogisticsChannel()',
  '0 30 3 * * ?',
  '1',
  '1',
  '1',
  'SYSTEM',
  NOW(),
  'SYSTEM',
  NOW(),
  '每天03:30全量同步头程物流渠道；默认暂停，确认后在定时任务页面启用'
WHERE NOT EXISTS (
  SELECT 1
  FROM `sys_job`
  WHERE `invoke_target` IN (
    'operationSyncTask.syncLingxingLogisticsChannel',
    'operationSyncTask.syncLingxingLogisticsChannel()'
  )
);

SELECT
  `job_id`, `job_name`, `invoke_target`, `cron_expression`, `status`, `remark`
FROM `sys_job`
WHERE `invoke_target` = 'operationSyncTask.syncLingxingLogisticsChannel()';
