-- Amazon 绩效排名负责人规则。
-- 可重复执行；适用于已执行 20260727_amz_monthly_order_profit_performance.sql 的环境。

CREATE TABLE IF NOT EXISTS `amz_performance_owner_rule` (
  `id` bigint NOT NULL AUTO_INCREMENT COMMENT '主键',
  `stat_month` char(7) NOT NULL COMMENT '统计月份YYYY-MM',
  `group_code` varchar(16) NOT NULL COMMENT '组别：EU、US1、US2',
  `rule_type` varchar(32) NOT NULL COMMENT '规则类型：BRAND、OTH_CODE、STORE',
  `match_key` varchar(200) NOT NULL COMMENT '匹配键：品牌、中间码或店铺中文名',
  `principal_name` varchar(100) NOT NULL COMMENT '负责人',
  `source_file_name` varchar(255) DEFAULT NULL COMMENT '来源Excel文件名',
  `source_sheet` varchar(64) DEFAULT NULL COMMENT '来源sheet',
  `source_row` int DEFAULT NULL COMMENT '来源行号',
  `imported_by` varchar(64) DEFAULT NULL COMMENT '导入人',
  `create_time` datetime DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `update_time` datetime DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '修改时间',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_amz_owner_rule_month_group_type_key`
    (`stat_month`,`group_code`,`rule_type`,`match_key`),
  KEY `idx_amz_owner_rule_month_owner` (`stat_month`,`principal_name`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='Amazon月度绩效负责人匹配规则';

-- 旧环境只更新字段注释，不改变绩效汇总表现有结构和数据。
ALTER TABLE `amz_performance_ranking`
  MODIFY COLUMN `principal_name` varchar(200) NOT NULL
  COMMENT '按月度负责人规则匹配后的负责人';

UPDATE `amz_performance_owner_rule`
SET `principal_name` = '未分配',
    `update_time` = NOW()
WHERE TRIM(`principal_name`) IN ('待定', '待到');

SET @net_sales_column_exists := (
  SELECT COUNT(*)
  FROM information_schema.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'amz_performance_ranking'
    AND COLUMN_NAME = 'net_sales_amount'
);

SET @net_sales_ddl := IF(
  @net_sales_column_exists = 0,
  'ALTER TABLE `amz_performance_ranking` ADD COLUMN `net_sales_amount` decimal(20,6) NOT NULL DEFAULT 0 COMMENT ''净销售额=销售额-退款金额'' AFTER `refund_amount`',
  'SELECT 1'
);
PREPARE net_sales_stmt FROM @net_sales_ddl;
EXECUTE net_sales_stmt;
DEALLOCATE PREPARE net_sales_stmt;

-- leiyongyu 已有的绩效排名编辑权限同时用于上传负责人配置；
-- 下面语句确保部署机权限遗漏时可以补齐。
SET @finance_menu_id := (
  SELECT menu_id FROM sys_menu
  WHERE path = 'finance' AND menu_type = 'M'
  ORDER BY menu_id LIMIT 1
);

SET @performance_menu_id := (
  SELECT menu_id FROM sys_menu
  WHERE parent_id = @finance_menu_id AND path = 'performance-ranking'
  ORDER BY menu_id LIMIT 1
);

INSERT IGNORE INTO sys_role_menu (role_id, menu_id)
SELECT ur.role_id, permissions.menu_id
FROM sys_user u
JOIN sys_user_role ur ON ur.user_id = u.user_id
JOIN (
  SELECT @finance_menu_id AS menu_id
  UNION ALL SELECT @performance_menu_id
  UNION ALL
  SELECT menu_id FROM sys_menu
  WHERE parent_id = @performance_menu_id
    AND perms IN (
      'finance:performanceRanking:list',
      'finance:performanceRanking:edit'
    )
) permissions ON permissions.menu_id IS NOT NULL
WHERE u.user_name = 'leiyongyu';
