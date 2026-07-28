-- Amazon 月度完整订单利润 + 财务中心绩效排名 + 每月定时任务。
-- 可重复执行。同步范围：每月4日22:00拉取上一个完整自然月，历史月份保留。

CREATE TABLE IF NOT EXISTS `amz_monthly_order_profit` (
  `id` bigint NOT NULL AUTO_INCREMENT COMMENT '主键',
  `stat_month` char(7) NOT NULL COMMENT '统计月份YYYY-MM',
  `sid` varchar(32) NOT NULL COMMENT '领星店铺SID',
  `seller_sku` varchar(128) NOT NULL COMMENT 'MSKU',
  `local_sku` varchar(255) DEFAULT NULL COMMENT '本地SKU',
  `asin` varchar(32) DEFAULT NULL COMMENT 'ASIN',
  `country` varchar(64) DEFAULT NULL COMMENT '国家',
  `currency_code` varchar(16) DEFAULT NULL COMMENT '币种',
  `currency_icon` varchar(16) DEFAULT NULL COMMENT '币种符号',
  `gross_profit` decimal(20,6) DEFAULT NULL COMMENT '毛利润',
  `gross_margin` decimal(20,6) DEFAULT NULL COMMENT '毛利率',
  `avg_gross_profit` decimal(20,6) DEFAULT NULL COMMENT '平均毛利润',
  `volume` decimal(20,6) DEFAULT NULL COMMENT '销量',
  `replacement_quantity` decimal(20,6) DEFAULT NULL COMMENT '补换货量',
  `multi_channel_volume` decimal(20,6) DEFAULT NULL COMMENT '多渠道销量',
  `ad_sales_amount` decimal(20,6) DEFAULT NULL COMMENT '广告销售额',
  `ad_volume` decimal(20,6) DEFAULT NULL COMMENT '广告销量',
  `amount` decimal(20,6) DEFAULT NULL COMMENT '销售额',
  `tax_amount` decimal(20,6) DEFAULT NULL COMMENT '含税销售额',
  `refund_amount` decimal(20,6) DEFAULT NULL COMMENT '退款金额',
  `refund_amount_rate` decimal(20,6) DEFAULT NULL COMMENT '退款率',
  `shipping_cost` decimal(20,6) DEFAULT NULL COMMENT '买家运费',
  `promotion_discount` decimal(20,6) DEFAULT NULL COMMENT '促销折扣',
  `return_quantity` decimal(20,6) DEFAULT NULL COMMENT '退货量',
  `return_rate` decimal(20,6) DEFAULT NULL COMMENT '退货率',
  `selling_fee` decimal(20,6) DEFAULT NULL COMMENT '平台费',
  `fulfillment_fee` decimal(20,6) DEFAULT NULL COMMENT 'FBA发货费',
  `other_order_fee` decimal(20,6) DEFAULT NULL COMMENT '其他订单费用',
  `spend` decimal(20,6) DEFAULT NULL COMMENT '广告花费',
  `ads_sb_cost` decimal(20,6) DEFAULT NULL COMMENT 'SB花费',
  `ads_sbv_cost` decimal(20,6) DEFAULT NULL COMMENT 'SBV花费',
  `ads_sd_cost` decimal(20,6) DEFAULT NULL COMMENT 'SD花费',
  `ads_sp_cost` decimal(20,6) DEFAULT NULL COMMENT 'SP花费',
  `purchase_costs` decimal(20,6) DEFAULT NULL COMMENT '采购成本',
  `avg_purchase_costs` decimal(20,6) DEFAULT NULL COMMENT '采购均价',
  `logistics_costs` decimal(20,6) DEFAULT NULL COMMENT '头程成本',
  `avg_logistics_costs` decimal(20,6) DEFAULT NULL COMMENT '头程均价',
  `other_costs` decimal(20,6) DEFAULT NULL COMMENT '其他成本',
  `avg_other_costs` decimal(20,6) DEFAULT NULL COMMENT '其他均价',
  `total_costs` decimal(20,6) DEFAULT NULL COMMENT '合计成本',
  `is_parent` tinyint DEFAULT NULL COMMENT '是否有子项',
  `small_image_url` varchar(1000) DEFAULT NULL COMMENT '图片链接',
  `item_name` varchar(1000) DEFAULT NULL COMMENT '品名',
  `refund_quantity` decimal(20,6) DEFAULT NULL COMMENT '退款量',
  `principal_names` varchar(1000) DEFAULT NULL COMMENT 'Listing负责人',
  `ad_sales_amount_sp` decimal(20,6) DEFAULT NULL COMMENT 'SP广告销售额',
  `ad_sales_amount_sd` decimal(20,6) DEFAULT NULL COMMENT 'SD广告销售额',
  `ad_sales_amount_sb` decimal(20,6) DEFAULT NULL COMMENT 'SB广告销售额',
  `ad_sales_amount_sbv` decimal(20,6) DEFAULT NULL COMMENT 'SBV广告销售额',
  `ad_volume_sp` decimal(20,6) DEFAULT NULL COMMENT 'SP广告销量',
  `ad_volume_sd` decimal(20,6) DEFAULT NULL COMMENT 'SD广告销量',
  `ad_volume_sb` decimal(20,6) DEFAULT NULL COMMENT 'SB广告销量',
  `ad_volume_sbv` decimal(20,6) DEFAULT NULL COMMENT 'SBV广告销量',
  `afn_volume` decimal(20,6) DEFAULT NULL COMMENT 'FBA销量',
  `mfn_volume` decimal(20,6) DEFAULT NULL COMMENT 'FBM销量',
  `afn_amount` decimal(20,6) DEFAULT NULL COMMENT 'FBA销售额',
  `mfn_amount` decimal(20,6) DEFAULT NULL COMMENT 'FBM销售额',
  `pm_discount` decimal(20,6) DEFAULT NULL COMMENT '价格折扣',
  `sp_discount` decimal(20,6) DEFAULT NULL COMMENT '配送折扣',
  `net_gross_margin` decimal(20,6) DEFAULT NULL COMMENT '净毛利率',
  `avg_volume` decimal(20,6) DEFAULT NULL COMMENT '平均日销',
  `net_amount` decimal(20,6) DEFAULT NULL COMMENT '净销售额',
  `avg_net_amount` decimal(20,6) DEFAULT NULL COMMENT '平均售价',
  `selling_fee_rate` decimal(20,6) DEFAULT NULL COMMENT '平台费占比',
  `fulfillment_fee_rate` decimal(20,6) DEFAULT NULL COMMENT 'FBA发货费占比',
  `spend_rate` decimal(20,6) DEFAULT NULL COMMENT '广告费率',
  `total_stock_fee` decimal(20,6) DEFAULT NULL COMMENT '仓储费',
  `total_stock_fee_rate` decimal(20,6) DEFAULT NULL COMMENT '仓储费占比',
  `promotion_fee` decimal(20,6) DEFAULT NULL COMMENT '推广费',
  `shared_fba_international_inbound_fee` decimal(20,6) DEFAULT NULL COMMENT 'FBA国际物流运费',
  `adjustments_fee` decimal(20,6) DEFAULT NULL COMMENT '调整费',
  `selling_other_fee` decimal(20,6) DEFAULT NULL COMMENT '平台其他费',
  `inventory_credit` decimal(20,6) DEFAULT NULL COMMENT 'FBA库存赔偿',
  `shared_fba_inbound_convenience_fee` decimal(20,6) DEFAULT NULL COMMENT '入库配置费',
  `cost_of_points_granted` decimal(20,6) DEFAULT NULL COMMENT '积分收入',
  `shared_cost_of_advertising` decimal(20,6) DEFAULT NULL COMMENT '差异分摊',
  `total_other_granted` decimal(20,6) DEFAULT NULL COMMENT '其它收入',
  `shared_fba_liquidation_proceeds` decimal(20,6) DEFAULT NULL COMMENT '清算收入',
  `shared_fba_liquidation_proceeds_adjustments` decimal(20,6) DEFAULT NULL COMMENT '清算调整',
  `shared_amazon_shipping_reimbursement` decimal(20,6) DEFAULT NULL COMMENT '亚马逊运费赔偿',
  `shared_safe_t_reimbursement` decimal(20,6) DEFAULT NULL COMMENT 'Safe-T索赔',
  `shared_netco_transaction` decimal(20,6) DEFAULT NULL COMMENT 'Netco交易',
  `shared_reimbursements` decimal(20,6) DEFAULT NULL COMMENT '赔偿收入',
  `shared_clawbacks` decimal(20,6) DEFAULT NULL COMMENT '追索收入',
  `shared_commingling_vat_income` decimal(20,6) DEFAULT NULL COMMENT '混合VAT收入',
  `gift_wrap_credits` decimal(20,6) DEFAULT NULL COMMENT '包装收入',
  `a_to_z_guarantee_claims` decimal(20,6) DEFAULT NULL COMMENT '买家交易保障索赔额',
  `shared_others` decimal(20,6) DEFAULT NULL COMMENT '其他',
  `fba_storage_fee` decimal(20,6) DEFAULT NULL COMMENT '月仓储费',
  `shared_fba_storage_fee` decimal(20,6) DEFAULT NULL COMMENT '月仓储费差异',
  `long_term_storage_fee` decimal(20,6) DEFAULT NULL COMMENT '长期仓储费',
  `shared_long_term_storage_fee` decimal(20,6) DEFAULT NULL COMMENT '长期仓储费差异',
  `shared_storage_renewal_billing` decimal(20,6) DEFAULT NULL COMMENT '库存续订费',
  `shared_fba_disposal_fee` decimal(20,6) DEFAULT NULL COMMENT 'FBA销毁费',
  `shared_fba_removal_fee` decimal(20,6) DEFAULT NULL COMMENT 'FBA移除费',
  `shared_fba_inbound_transportation_program_fee` decimal(20,6) DEFAULT NULL COMMENT '入仓手续费',
  `shared_labeling_fee` decimal(20,6) DEFAULT NULL COMMENT '标签费',
  `shared_polybagging_fee` decimal(20,6) DEFAULT NULL COMMENT '塑料包装费',
  `shared_bubblewrap_fee` decimal(20,6) DEFAULT NULL COMMENT '泡沫包装费',
  `shared_taping_fee` decimal(20,6) DEFAULT NULL COMMENT '胶带费',
  `shared_awd_processing_fee` decimal(20,6) DEFAULT NULL COMMENT 'AWD处理费',
  `shared_awd_transportation_fee` decimal(20,6) DEFAULT NULL COMMENT 'AWD运输费',
  `shared_awd_storage_fee` decimal(20,6) DEFAULT NULL COMMENT 'AWD仓储费',
  `shared_star_storage_fee` decimal(20,6) DEFAULT NULL COMMENT '卫星仓仓储费',
  `shared_fba_customer_return_fee` decimal(20,6) DEFAULT NULL COMMENT 'FBA退回卖家费',
  `shared_fba_inbound_defect_fee` decimal(20,6) DEFAULT NULL COMMENT '入库缺陷费',
  `shared_fba_overage_fee` decimal(20,6) DEFAULT NULL COMMENT '超量仓储费',
  `shared_amazon_partnered_carrier_shipment_fee` decimal(20,6) DEFAULT NULL COMMENT '合作承运费',
  `shared_item_fee_adjustment` decimal(20,6) DEFAULT NULL COMMENT '库存调整费用',
  `shared_other_fba_inventory_fees` decimal(20,6) DEFAULT NULL COMMENT '其他仓储费',
  `fba_fulfillment_fee` decimal(20,6) DEFAULT NULL COMMENT '订单FBA发货费',
  `shared_fba_transaction_customer_return_fee` decimal(20,6) DEFAULT NULL COMMENT '亚马逊物流客户退货费',
  `off_site_promotion_fee` decimal(20,6) DEFAULT NULL COMMENT '站外推广费',
  `price_list_json` longtext COMMENT '商品基础信息完整JSON',
  `parent_asins_json` longtext COMMENT '父ASIN完整JSON',
  `local_infos_json` longtext COMMENT '本地商品信息完整JSON',
  `asins_json` longtext COMMENT 'ASIN信息完整JSON',
  `sids_json` longtext COMMENT '店铺SID完整JSON',
  `categories_json` longtext COMMENT '分类完整JSON',
  `seller_store_countries_json` longtext COMMENT '国家完整JSON',
  `brands_json` longtext COMMENT '品牌完整JSON',
  `raw_json` longtext COMMENT '接口单条完整原始JSON',
  `sync_time` datetime DEFAULT NULL COMMENT '同步时间',
  `create_time` datetime DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `update_time` datetime DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '修改时间',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_amz_month_profit_month_sid_msku` (`stat_month`,`sid`,`seller_sku`),
  KEY `idx_amz_month_profit_month_gross` (`stat_month`,`gross_profit`),
  KEY `idx_amz_month_profit_sku` (`local_sku`),
  KEY `idx_amz_month_profit_asin` (`asin`),
  KEY `idx_amz_month_profit_principal` (`principal_names`(191))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='Amazon月度完整订单利润表(MSKU维度)';

CREATE TABLE IF NOT EXISTS `amz_performance_ranking` (
  `id` bigint NOT NULL AUTO_INCREMENT COMMENT '主键',
  `stat_month` char(7) NOT NULL COMMENT '统计月份YYYY-MM',
  `principal_name` varchar(200) NOT NULL COMMENT 'Listing负责人，来自amz_product_listing',
  `gross_profit` decimal(20,6) NOT NULL DEFAULT 0 COMMENT '负责人汇总毛利润',
  `amount` decimal(20,6) NOT NULL DEFAULT 0 COMMENT '负责人汇总销售额',
  `refund_amount` decimal(20,6) NOT NULL DEFAULT 0 COMMENT '负责人汇总退款金额',
  `create_time` datetime DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `update_time` datetime DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '修改时间',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_amz_performance_month_principal` (`stat_month`,`principal_name`),
  KEY `idx_amz_performance_month_gross` (`stat_month`,`gross_profit`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='Amazon负责人月度绩效排名汇总表';

-- 每月4日22:00独立同步上一个完整自然月。
UPDATE sys_job
SET job_name = 'Amazon月度完整订单利润同步',
    job_group = 'FINANCE',
    cron_expression = '0 0 22 4 * ?',
    misfire_policy = '2',
    concurrent = '1',
    status = '0',
    update_by = 'SYSTEM',
    update_time = NOW(),
    remark = '每月4日22:00拉取上一个完整自然月，按月份保留历史'
WHERE invoke_target IN (
  'operationSyncTask.syncAmzMonthlyOrderProfit',
  'operationSyncTask.syncAmzMonthlyOrderProfit()'
);

INSERT INTO sys_job (
  job_name, job_group, invoke_target, cron_expression,
  misfire_policy, concurrent, status, create_by, create_time, remark
)
SELECT
  'Amazon月度完整订单利润同步', 'FINANCE',
  'operationSyncTask.syncAmzMonthlyOrderProfit()', '0 0 22 4 * ?',
  '2', '1', '0', 'SYSTEM', NOW(),
  '每月4日22:00拉取上一个完整自然月，按月份保留历史'
WHERE NOT EXISTS (
  SELECT 1 FROM sys_job
  WHERE invoke_target IN (
    'operationSyncTask.syncAmzMonthlyOrderProfit',
    'operationSyncTask.syncAmzMonthlyOrderProfit()'
  )
);

-- 财务中心目录。
SET @finance_menu_id := (
  SELECT menu_id FROM sys_menu
  WHERE path = 'finance' AND menu_type = 'M'
  ORDER BY menu_id LIMIT 1
);

INSERT INTO sys_menu (
  menu_name, parent_id, order_num, path, component, query, route_name,
  is_frame, is_cache, menu_type, visible, status, perms, icon,
  create_by, create_time, remark
)
SELECT
  '财务中心', 0, 2, 'finance', NULL, NULL, 'Finance',
  1, 0, 'M', '0', '0', '', 'money',
  'SYSTEM', NOW(), '财务功能目录'
WHERE @finance_menu_id IS NULL;

SET @finance_menu_id := (
  SELECT menu_id FROM sys_menu
  WHERE path = 'finance' AND menu_type = 'M'
  ORDER BY menu_id LIMIT 1
);

-- 绩效排名页面。
INSERT INTO sys_menu (
  menu_name, parent_id, order_num, path, component, query, route_name,
  is_frame, is_cache, menu_type, visible, status, perms, icon,
  create_by, create_time, remark
)
SELECT
  '绩效排名', @finance_menu_id, 3, 'performance-ranking',
  'finance/performanceRanking/index', NULL, 'PerformanceRanking',
  1, 0, 'C', '0', '0', 'finance:performanceRanking:list', 'ranking',
  'SYSTEM', NOW(), 'Amazon月度订单利润绩效排名'
WHERE NOT EXISTS (
  SELECT 1 FROM sys_menu
  WHERE parent_id = @finance_menu_id AND path = 'performance-ranking'
);

SET @performance_menu_id := (
  SELECT menu_id FROM sys_menu
  WHERE parent_id = @finance_menu_id AND path = 'performance-ranking'
  ORDER BY menu_id LIMIT 1
);

UPDATE sys_menu
SET menu_name = '绩效排名',
    component = 'finance/performanceRanking/index',
    route_name = 'PerformanceRanking',
    visible = '0',
    status = '0',
    perms = 'finance:performanceRanking:list',
    update_by = 'SYSTEM',
    update_time = NOW()
WHERE menu_id = @performance_menu_id;

-- 查询及编辑权限标识（页面当前以查询展示为主，预留编辑权限）。
INSERT INTO sys_menu (
  menu_name, parent_id, order_num, path, component, query, route_name,
  is_frame, is_cache, menu_type, visible, status, perms, icon,
  create_by, create_time, remark
)
SELECT
  '绩效排名查询', @performance_menu_id, 1, '', NULL, NULL, '',
  1, 0, 'F', '0', '0', 'finance:performanceRanking:list', '#',
  'SYSTEM', NOW(), ''
WHERE NOT EXISTS (
  SELECT 1 FROM sys_menu
  WHERE parent_id = @performance_menu_id
    AND perms = 'finance:performanceRanking:list'
);

INSERT INTO sys_menu (
  menu_name, parent_id, order_num, path, component, query, route_name,
  is_frame, is_cache, menu_type, visible, status, perms, icon,
  create_by, create_time, remark
)
SELECT
  '绩效排名编辑', @performance_menu_id, 2, '', NULL, NULL, '',
  1, 0, 'F', '0', '0', 'finance:performanceRanking:edit', '#',
  'SYSTEM', NOW(), '预留绩效排名编辑权限'
WHERE NOT EXISTS (
  SELECT 1 FROM sys_menu
  WHERE parent_id = @performance_menu_id
    AND perms = 'finance:performanceRanking:edit'
);

-- leiyongyu 的全部角色获得页面显示、查询和编辑权限。
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
