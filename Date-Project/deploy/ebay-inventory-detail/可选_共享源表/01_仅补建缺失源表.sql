-- 仅补建缺失共享源表；不迁移已有结构、不导入数据、不注册定时任务。
-- 从当前仓库CREATE TABLE语句提取；参见每表来源。不执行原文件中的其他语句。
SET NAMES utf8mb4;

-- 来源：Date-Project/backend/schema.sql
USE `date-project`;
CREATE TABLE IF NOT EXISTS `ods_lingxing_inventory_detail_weekly` (
  `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '主键',
  `snapshot_date` DATE NOT NULL COMMENT '快照日期，取任务执行当天；接口只返回实时库存，不支持补拉历史',
  `sync_batch_id` VARCHAR(64) NOT NULL COMMENT '同步批次ID',
  `wid` INT NOT NULL COMMENT '领星仓库ID',
  `product_id` BIGINT NOT NULL COMMENT '本地产品ID；三个接口的关联主键',
  `seller_id` VARCHAR(64) NOT NULL DEFAULT '0' COMMENT '店铺ID；同仓同SKU可能因店铺返回多条',
  `sku` VARCHAR(255) NULL COMMENT 'SKU',
  `fnsku` VARCHAR(64) NULL COMMENT 'FNSKU',
  `product_total` DECIMAL(24,6) NULL COMMENT '实际库存总量',
  `product_valid_num` DECIMAL(24,6) NULL COMMENT '可用量',
  `expect_valid_num` DECIMAL(24,6) NULL COMMENT '期望可用',
  `product_bad_num` DECIMAL(24,6) NULL COMMENT '次品量',
  `product_qc_num` DECIMAL(24,6) NULL COMMENT '待检待上架量',
  `product_lock_num` DECIMAL(24,6) NULL COMMENT '锁定量',
  `good_lock_num` DECIMAL(24,6) NULL COMMENT '良品锁定量',
  `bad_lock_num` DECIMAL(24,6) NULL COMMENT '次品锁定量',
  `storage_distribute_num` DECIMAL(24,6) NULL COMMENT 'FBA发货单待配货量',
  `quantity_receive` DECIMAL(24,6) NULL COMMENT '待到货量',
  `expect_pending_num` DECIMAL(24,6) NULL COMMENT '期望待到货量',
  `product_onway` DECIMAL(24,6) NULL COMMENT '调拨在途',
  `available_inventory_box_qty` DECIMAL(24,6) NULL COMMENT '可用箱库存量',
  `average_age` INT NULL COMMENT '平均库龄天数',
  `stock_cost_total` DECIMAL(24,6) NULL COMMENT '库存成本',
  `stock_cost` DECIMAL(24,6) NULL COMMENT '单位库存成本',
  `stock_price` DECIMAL(24,6) NULL COMMENT '单位库存成本',
  `purchase_price` DECIMAL(24,6) NULL COMMENT '采购单价；该批库存的实际加权进价，仅有库存时非零',
  `price` DECIMAL(24,6) NULL COMMENT '单位费用',
  `head_stock_price` DECIMAL(24,6) NULL COMMENT '单位头程',
  `transit_head_cost` DECIMAL(24,6) NULL COMMENT '调拨在途头程成本',
  `stock_age_list` JSON NULL COMMENT '库龄分档数组原值；同时拆解进库龄竖表',
  `third_inventory` JSON NULL COMMENT '海外仓第三方库存原值；含8个数值和third_inventory_data对账数组',
  `raw_json` JSON NULL COMMENT '整条记录原值，字段兜底',
  `pulled_at` DATETIME NOT NULL COMMENT '实际拉取时间',
  `create_time` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '记录创建时间',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_inv_week` (`snapshot_date`,`sync_batch_id`,`wid`,`product_id`,`seller_id`),
  KEY `idx_inv_week_date_wid` (`snapshot_date`,`wid`),
  KEY `idx_inv_week_date_pid` (`snapshot_date`,`product_id`),
  KEY `idx_inv_week_date_sku` (`snapshot_date`,`sku`),
  KEY `idx_inv_week_batch` (`sync_batch_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='ODS-领星仓库库存明细周快照（接口28字段全存）';

-- 来源：Date-Project/backend/schema.sql
USE `date-project`;
CREATE TABLE IF NOT EXISTS `ods_lingxing_inventory_age_bucket_weekly` (
  `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '主键',
  `snapshot_date` DATE NOT NULL COMMENT '快照日期',
  `sync_batch_id` VARCHAR(64) NOT NULL COMMENT '同步批次ID',
  `wid` INT NOT NULL COMMENT '领星仓库ID',
  `product_id` BIGINT NOT NULL COMMENT '本地产品ID',
  `seller_id` VARCHAR(64) NOT NULL DEFAULT '0' COMMENT '店铺ID；与表1保持同一粒度',
  `bucket_index` TINYINT NOT NULL COMMENT '接口返回的原始顺序，0起；用于稳定排列',
  `bucket_name` VARCHAR(64) NOT NULL COMMENT '分档名，如 0-29天库龄',
  `qty` DECIMAL(24,6) NULL COMMENT '该分档数量',
  `create_time` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '记录创建时间',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_age_week` (`snapshot_date`,`sync_batch_id`,`wid`,`product_id`,`seller_id`,`bucket_index`),
  KEY `idx_age_week_date_pid` (`snapshot_date`,`wid`,`product_id`),
  KEY `idx_age_week_date_name` (`snapshot_date`,`bucket_name`),
  KEY `idx_age_week_batch` (`sync_batch_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='ODS-库存库龄分档周快照（竖表，分档名自适应）';

-- 来源：Date-Project/backend/schema.sql
USE `date-project`;
CREATE TABLE IF NOT EXISTS `ods_lingxing_inventory_bin_detail_weekly` (
  `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '主键',
  `snapshot_date` DATE NOT NULL COMMENT '快照日期',
  `sync_batch_id` VARCHAR(64) NOT NULL COMMENT '同步批次ID',
  `wid` INT NOT NULL COMMENT '领星仓库ID',
  `wh_name` VARCHAR(200) NULL COMMENT '仓库名称；本接口直接返回，库存明细接口不返回',
  `whb_id` BIGINT NOT NULL COMMENT '仓位ID',
  `whb_name` VARCHAR(200) NULL COMMENT '仓位名称',
  `whb_type` INT NULL COMMENT '仓位类型；实测有 1/2/4/5/7/9，比接口文档的1-6多出7和9，不要按文档做枚举校验',
  `whb_type_name` VARCHAR(64) NULL COMMENT '仓位类型名称：待检暂存/可用暂存/拣货暂存/可用/可用在途暂存/上架暂存',
  `product_id` BIGINT NOT NULL COMMENT '本地产品ID；与表1按 (wid, product_id) 关联，实测命中率100%',
  `sku` VARCHAR(255) NULL COMMENT 'SKU',
  `product_name` VARCHAR(500) NULL COMMENT '产品名称；接口文档未列出的实际返回字段，可作为产品详情缺失时的兜底',
  `msku` VARCHAR(255) NULL COMMENT 'MSKU；接口文档未列出的实际返回字段',
  `store_id` VARCHAR(64) NULL COMMENT '店铺ID；接口文档写的是seller_id，实际返回键名为store_id',
  `fnsku` VARCHAR(64) NULL COMMENT 'FNSKU',
  `bin_identity_key` VARBINARY(1600) GENERATED ALWAYS AS (CONCAT(
    CHAR_LENGTH(COALESCE(NULLIF(TRIM(`store_id`),''),'0')),':',COALESCE(NULLIF(TRIM(`store_id`),''),'0'),
    CHAR_LENGTH(COALESCE(`msku`,'')),':',COALESCE(`msku`,''),
    CHAR_LENGTH(COALESCE(`fnsku`,'')),':',COALESCE(`fnsku`,''))) STORED
    COMMENT 'weekly-bin-identity-v1: store_id,msku,fnsku; byte-exact length framing',
  `total` DECIMAL(24,6) NULL COMMENT '总量',
  `lock_num` DECIMAL(24,6) NULL COMMENT '锁定量；接口字段名 lockNum',
  `valid_num` DECIMAL(24,6) NULL COMMENT '未锁定量；接口字段名 validNum',
  `third_inventory` JSON NULL COMMENT '第三方库存原值；本接口只有8个数值，无对账数组，且实测几乎全为0',
  `raw_json` JSON NULL COMMENT '整条记录原值，字段兜底',
  `pulled_at` DATETIME NOT NULL COMMENT '实际拉取时间',
  `create_time` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '记录创建时间',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_bin_week` (`snapshot_date`,`sync_batch_id`,`wid`,`whb_id`,`product_id`,`bin_identity_key`),
  KEY `idx_bin_week_date_wid_pid` (`snapshot_date`,`wid`,`product_id`),
  KEY `idx_bin_week_date_sku` (`snapshot_date`,`sku`),
  KEY `idx_bin_week_batch` (`sync_batch_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='ODS-领星仓位库存明细周快照（接口16字段全存）';

-- 来源：Date-Project/backend/schema.sql
USE `date-project`;
CREATE TABLE IF NOT EXISTS `ods_lingxing_product_info_weekly` (
  `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '主键',
  `snapshot_date` DATE NOT NULL COMMENT '快照日期',
  `sync_batch_id` VARCHAR(64) NOT NULL COMMENT '同步批次ID',
  `product_id` BIGINT NOT NULL COMMENT '本地产品ID；接口字段名是 id',
  `sku` VARCHAR(255) NULL COMMENT '产品SKU',
  `product_name` VARCHAR(500) NULL COMMENT '产品名称；库存明细接口不返回，只能从这里取',
  `model` VARCHAR(1000) NULL COMMENT '产品型号；实测是逗号分隔的OE号列表，全量4353个SKU最长222字符，留4.5倍余量',
  `unit` VARCHAR(32) NULL COMMENT '商品单位',
  `status` TINYINT NULL COMMENT '状态：0停售 1在售 2开发中 3清仓',
  `is_combo` TINYINT NULL COMMENT '是否组合产品：0否 1是',
  `brand_name` VARCHAR(200) NULL COMMENT '品牌名称',
  `category_name` VARCHAR(200) NULL COMMENT '分类名称；实测0%有值，领星侧完全未维护',
  `category_full_name` VARCHAR(500) NULL COMMENT '分类全路径；接口文档未列出的实际返回字段',
  `product_developer` VARCHAR(100) NULL COMMENT '开发者',
  `cg_opt_username` VARCHAR(100) NULL COMMENT '采购员',
  `cg_delivery` INT NULL COMMENT '采购交期',
  `cg_price` DECIMAL(24,6) NULL COMMENT '产品档案采购成本；与库存明细purchase_price不同源',
  `cg_product_length` DECIMAL(16,4) NULL COMMENT '产品规格长CM',
  `cg_product_width` DECIMAL(16,4) NULL COMMENT '产品规格宽CM',
  `cg_product_height` DECIMAL(16,4) NULL COMMENT '产品规格高CM',
  `cg_package_length` DECIMAL(16,4) NULL COMMENT '包装规格长CM',
  `cg_package_width` DECIMAL(16,4) NULL COMMENT '包装规格宽CM',
  `cg_package_height` DECIMAL(16,4) NULL COMMENT '包装规格高CM',
  `cg_box_length` DECIMAL(16,4) NULL COMMENT '外箱规格长CM；实测仅5.5%有值，多数SKU领星未维护',
  `cg_box_width` DECIMAL(16,4) NULL COMMENT '外箱规格宽CM；实测仅5.5%有值',
  `cg_box_height` DECIMAL(16,4) NULL COMMENT '外箱规格高CM；实测仅5.5%有值',
  `cg_box_weight` DECIMAL(16,4) NULL COMMENT '外箱实重KG；实测仅5.9%有值',
  `cg_box_pcs` INT NULL COMMENT '单箱数量；实测仅0.7%有值',
  `cg_product_net_weight` DECIMAL(16,4) NULL COMMENT '产品净重G',
  `cg_product_gross_weight` DECIMAL(16,4) NULL COMMENT '产品毛重G',
  `cg_product_material` VARCHAR(200) NULL COMMENT '采购材质',
  `currency` VARCHAR(16) NULL COMMENT '官方汇率code',
  `bg_customs_export_name` VARCHAR(255) NULL COMMENT '中文报关名',
  `bg_customs_import_name` VARCHAR(255) NULL COMMENT '英文报关名',
  `bg_export_hs_code` VARCHAR(64) NULL COMMENT '中国HSCode',
  `bg_import_hs_code` VARCHAR(64) NULL COMMENT '进口国HSCode',
  `raw_json` JSON NULL COMMENT '接口58字段整条原值；供应商报价/图片/报关/清关/自定义字段等嵌套结构只存这里',
  `pulled_at` DATETIME NOT NULL COMMENT '实际拉取时间',
  `create_time` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '记录创建时间',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_prod_week` (`snapshot_date`,`sync_batch_id`,`product_id`),
  KEY `idx_prod_week_sku` (`snapshot_date`,`sku`),
  KEY `idx_prod_week_batch` (`sync_batch_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='ODS-领星本地产品详情周快照（常用列平铺，嵌套结构进raw_json）';

-- 来源：Date-Project/backend/schema.sql
USE `date-project`;
CREATE TABLE IF NOT EXISTS `ops_weekly_export_file` (
  `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '主键',
  `export_code` VARCHAR(64) NOT NULL COMMENT '导出类型编码；本次为 weekly_inventory_bin',
  `snapshot_date` DATE NOT NULL COMMENT '数据快照日期',
  `sync_batch_id` VARCHAR(64) NOT NULL COMMENT '同步批次ID，可回溯到四张ODS表',
  `file_name` VARCHAR(255) NOT NULL COMMENT '文件名',
  `file_path` VARCHAR(500) NOT NULL COMMENT '服务器绝对路径',
  `file_size` BIGINT NULL COMMENT '文件字节数',
  `row_count` INT NULL COMMENT '数据行数（不含表头）',
  `column_count` INT NULL COMMENT '列数',
  `status` VARCHAR(20) NOT NULL DEFAULT 'SUCCESS' COMMENT 'RUNNING / SUCCESS / FAILED / INTERRUPTED / DELETE_PENDING / DELETED',
  `error_message` TEXT NULL COMMENT '失败原因',
  `trigger_type` VARCHAR(20) NOT NULL DEFAULT 'job' COMMENT 'job=定时触发 manual=页面手动',
  `generated_at` DATETIME NOT NULL COMMENT '文件生成完成时间',
  `create_time` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '记录创建时间',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_export_file` (`export_code`,`snapshot_date`,`file_name`),
  KEY `idx_export_code_date` (`export_code`,`snapshot_date`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='周报导出文件登记；可手动永久删除Excel，保留登记记录与库存快照';

-- 来源：Date-Project/backend/schema.sql
USE `date-project`;
CREATE TABLE IF NOT EXISTS `ods_goodcang_wh_inventory_storage` (
  `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '主键；不作为业务关联键',
  `currency_code` VARCHAR(16) NULL COMMENT '计费货币；接口原值',
  `isdb_volume` DECIMAL(30,12) NULL COMMENT '体积m3；不换算',
  `is_amount` DECIMAL(30,12) NULL COMMENT '计费总金额含税；计费货币原币',
  `is_date` VARCHAR(32) NULL COMMENT '发生时间；接口字符串原值',
  `is_settlement_amount` DECIMAL(30,12) NULL COMMENT '结算总金额含税；结算货币原币',
  `note` TEXT NULL COMMENT '备注；接口原值',
  `settlement_currency_code` VARCHAR(16) NULL COMMENT '结算货币；接口原值',
  `warehouse_code` VARCHAR(64) NULL COMMENT '仓库代码；关联字段',
  `wis_code` VARCHAR(64) NULL COMMENT '仓租单号；用于后续关联仓租明细',
  `wp_settlement_cycle` VARCHAR(64) NULL COMMENT '结算周期；接口原值',
  `request_date_from` DATETIME NOT NULL COMMENT '本次查询开始时间；北京时间',
  `request_date_to` DATETIME NOT NULL COMMENT '本次查询截止时间；北京时间',
  `source_page` INT UNSIGNED NOT NULL COMMENT '来源页码，从1开始',
  `source_row_no` INT UNSIGNED NOT NULL COMMENT '页内行号，从1开始',
  `api_count` INT UNSIGNED NOT NULL COMMENT '接口总数量',
  `sync_batch_id` VARCHAR(64) NOT NULL COMMENT '当前同步请求标识，仅留最新数据，不保留历史批次',
  `pulled_at` DATETIME NOT NULL COMMENT '本次同步起始时刻，也是窗口截止时刻',
  `raw_json` JSON NOT NULL COMMENT '原始数据行全部字段；数值精度不降级float',
  PRIMARY KEY (`id`),
  KEY `idx_gc_storage_wis` (`wis_code`),
  KEY `idx_gc_storage_warehouse_date` (`warehouse_code`, `is_date`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='ODS-谷仓仓租概要近30天；完整拉取成功后全表事务替换，不保留历史';

-- 来源：Date-Project/backend/schema.sql
USE `date-project`;
CREATE TABLE IF NOT EXISTS `ods_goodcang_wh_inventory_storage_detail` (
  `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '主键；不作为业务关联键',
  `wis_code` VARCHAR(64) NULL COMMENT '仓租单号；接口原值',
  `reference_no` VARCHAR(255) NULL COMMENT '参考编号；保留前导零',
  `warehouse_code` VARCHAR(64) NULL COMMENT '仓库代码；接口原值',
  `product_sku` VARCHAR(255) NULL COMMENT '商品编码；接口原值',
  `product_barcode` VARCHAR(255) NULL COMMENT '产品代码；接口原值',
  `product_name` VARCHAR(1000) NULL COMMENT '产品名称；接口原值',
  `quantity` BIGINT NULL COMMENT '数量；接口原值，缺失不补零',
  `length` DECIMAL(30,12) NULL COMMENT '产品长cm；接口原值',
  `width` DECIMAL(30,12) NULL COMMENT '产品宽cm；接口原值',
  `height` DECIMAL(30,12) NULL COMMENT '产品高cm；接口原值',
  `volume` DECIMAL(30,12) NULL COMMENT '体积m3；接口原值',
  `cargo_type` VARCHAR(64) NULL COMMENT '货型；接口原值',
  `day` BIGINT NULL COMMENT '库龄天数；接口原值，缺失不补零',
  `bill_amount` DECIMAL(30,12) NULL COMMENT '总金额不含税；计费币种原币，不换算',
  `settlement_amount` DECIMAL(30,12) NULL COMMENT '结算金额不含税；结算币种原币，不换算',
  `warehouse_rent_amount` DECIMAL(30,12) NULL COMMENT '仓租金额不含税；接口原币金额，不换算',
  `bill_currency_code` VARCHAR(16) NULL COMMENT '计费币种；接口原值',
  `settlement_currency_code` VARCHAR(16) NULL COMMENT '结算币种；接口原值',
  `charge_date` VARCHAR(32) NULL COMMENT '计费时间；接口字符串原值',
  `putaway_date` VARCHAR(32) NULL COMMENT '上架时间；接口字符串原值',
  `request_wis_code` VARCHAR(64) NOT NULL COMMENT '实际请求仓租单号；与响应wis_code分开保留用于追溯',
  `request_date_from` DATETIME NOT NULL COMMENT '概要查询开始时间；北京时间，非明细接口请求参数',
  `request_date_to` DATETIME NOT NULL COMMENT '概要查询截止时间；北京时间，非明细接口请求参数',
  `source_page` INT UNSIGNED NOT NULL COMMENT '当前仓租单的来源页码，从1开始',
  `source_row_no` INT UNSIGNED NOT NULL COMMENT '页内行号，从1开始',
  `api_count` INT UNSIGNED NOT NULL COMMENT '当前仓租单明细接口总数量',
  `sync_batch_id` VARCHAR(64) NOT NULL COMMENT '与概要一致的当前同步标识；不保留历史批次',
  `pulled_at` DATETIME NOT NULL COMMENT '本次链式同步起始时刻，也是概要窗口截止时刻',
  `raw_json` JSON NOT NULL COMMENT '原始明细行全部字段；数值精度不降级float',
  PRIMARY KEY (`id`),
  KEY `idx_gc_storage_detail_wis` (`wis_code`),
  KEY `idx_gc_storage_detail_request` (`request_wis_code`),
  KEY `idx_gc_storage_detail_sku_date` (`warehouse_code`, `product_sku`, `charge_date`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='ODS-谷仓近30天仓租单全部明细；概要及逐单明细完整拉取后同事务全表替换，不保留历史';

-- 来源：Date-Project/backend/schema.sql
USE `date-project`;
CREATE TABLE IF NOT EXISTS dim_lingxing_currency_month (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '主键',
    rate_month CHAR(7) NOT NULL COMMENT '汇率月份YYYY-MM；领星date字段',
    currency_code VARCHAR(16) NOT NULL COMMENT '币种代码；领星code字段',
    my_rate DECIMAL(20,6) NOT NULL COMMENT '我的汇率；领星my_rate，系统优先使用',
    rate_org DECIMAL(20,6) NULL COMMENT '官方汇率；领星rate_org，仅留档',
    sync_batch_id VARCHAR(64) NULL COMMENT '同步批次ID',
    synced_at DATETIME NULL COMMENT '同步时间',
    create_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '记录创建时间',
    update_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '记录更新时间',
    PRIMARY KEY (id),
    UNIQUE KEY uk_currency_month (rate_month, currency_code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='DIM-领星月度汇率';

-- 来源：Date-Project/backend/schema.sql
USE `date-project`;
CREATE TABLE IF NOT EXISTS dwd_performance_owner_rule (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '主键',
    platform VARCHAR(20) NOT NULL COMMENT '平台：amazon/ebay',
    stat_month CHAR(7) NOT NULL COMMENT '统计月份YYYY-MM',
    group_code VARCHAR(16) NOT NULL DEFAULT '' COMMENT '组别：EU/US1/US2，eBay为空',
    rule_type VARCHAR(32) NOT NULL COMMENT '规则类型：BRAND/OTH_CODE/STORE/EBAY_BRAND',
    match_key VARCHAR(200) NOT NULL COMMENT '匹配键',
    principal_name VARCHAR(100) NOT NULL COMMENT '负责人',
    source_file_name VARCHAR(255) NULL COMMENT '来源文件名',
    source_sheet VARCHAR(64) NULL COMMENT '来源Sheet',
    source_row INT NULL COMMENT '来源行',
    import_batch_id VARCHAR(64) NULL COMMENT '导入批次ID',
    create_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    update_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '修改时间',
    PRIMARY KEY (id),
    UNIQUE KEY uk_dwd_perf_rule (platform, stat_month, group_code, rule_type, match_key),
    KEY idx_dwd_perf_rule_owner (platform, stat_month, principal_name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='DWD-绩效负责人月度匹配规则';

-- 来源：Date-Project/migrations/20260825_ebay_sku_analysis_tables.sql
USE `date-project`;
CREATE TABLE IF NOT EXISTS dwd_ebay_sku_analysis_order (
  id BIGINT NOT NULL AUTO_INCREMENT COMMENT '主键ID', stat_month CHAR(7) NOT NULL COMMENT '统计月份，格式YYYY-MM', payment_time DATETIME NOT NULL COMMENT '付款时间', refund_time DATETIME DEFAULT NULL COMMENT '退款时间',
  platform_order_no VARCHAR(128) NOT NULL COMMENT '平台订单号', inventory_sku VARCHAR(128) NOT NULL COMMENT '标准库存SKU', purchase_quantity DECIMAL(18,4) NOT NULL DEFAULT 0 COMMENT '购买数量',
  paid_amount_cny DECIMAL(20,6) NOT NULL DEFAULT 0 COMMENT '已支付金额人民币', shipping_amount_cny DECIMAL(20,6) NOT NULL DEFAULT 0 COMMENT '运费人民币',
  platform_fee_cny DECIMAL(20,6) NOT NULL DEFAULT 0 COMMENT '平台费用人民币', order_profit_cny DECIMAL(20,6) NOT NULL DEFAULT 0 COMMENT '订单利润（人民币，来自订单上传文件）', paid_amount_original DECIMAL(20,6) NOT NULL DEFAULT 0 COMMENT '应收货款加应收运费原币（按订单SKU分摊）', shipping_amount_original DECIMAL(20,6) NOT NULL DEFAULT 0 COMMENT '应收运费原币', refund_quantity DECIMAL(18,4) NOT NULL DEFAULT 0 COMMENT '退货数量，状态包含已退款或已作废', refund_amount_original DECIMAL(20,6) NOT NULL DEFAULT 0 COMMENT '退款金额原币（按退款行分摊）', refund_amount_cny DECIMAL(20,6) NOT NULL DEFAULT 0 COMMENT '退款金额人民币', shipping_status VARCHAR(64) DEFAULT NULL COMMENT '发货状态', currency_code VARCHAR(16) DEFAULT NULL COMMENT '币种', customer_id VARCHAR(255) DEFAULT NULL COMMENT '客户ID', site_code VARCHAR(32) NOT NULL COMMENT '标准站点代码', site_name VARCHAR(100) NOT NULL DEFAULT '其他' COMMENT '中文站点名称',
  country_name VARCHAR(128) DEFAULT NULL COMMENT '国家名称',
  picture_url TEXT DEFAULT NULL COMMENT '图片链接，取上传源数据',
  product_name_cn VARCHAR(500) DEFAULT NULL COMMENT '产品名称（中文），取上传源数据',
  listing_url TEXT DEFAULT NULL COMMENT 'Listing链接，取上传源数据',
  order_remark TEXT DEFAULT NULL COMMENT '原始订单备注，作为退款原因展示',
  import_batch_id VARCHAR(64) NOT NULL COMMENT '导入批次ID',
  source_row INT NOT NULL COMMENT '来源Excel行号', create_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间', PRIMARY KEY (id),
  UNIQUE KEY uk_esa_dwd_month_row (stat_month, import_batch_id, source_row), KEY idx_esa_dwd_order_date (platform_order_no,payment_time), KEY idx_esa_dwd_time (payment_time), KEY idx_esa_dwd_sku (inventory_sku), KEY idx_esa_dwd_site (site_code), KEY idx_esa_dwd_site_sku_time (site_name,inventory_sku,payment_time), KEY idx_esa_dwd_return_time (refund_time,site_name,inventory_sku)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='DWD-eBay SKU分析订单清洗明细';

-- 来源：RuoYi-Vue-springboot3/sql/20260916_goodcang_inventory_age_weekly.sql
USE `jmh_data_platform`;
CREATE TABLE IF NOT EXISTS `ods_goodcang_inventory_age_latest` (
    `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '自增主键',
    `snapshot_month` CHAR(7) NOT NULL COMMENT '本批拉取归属年月；仅作元数据，不保存月历史',
    `warehouse_code` VARCHAR(30) NOT NULL DEFAULT '' COMMENT '谷仓仓库代码',
    `product_sku` VARCHAR(255) NOT NULL DEFAULT '' COMMENT '谷仓商品编码',
    `iba_quantity` BIGINT NOT NULL DEFAULT 0 COMMENT '在库库存数量',
    `iba_fifo_time` VARCHAR(32) NULL COMMENT '上架时间，保留原始格式',
    `iba_warning_age` INT NULL COMMENT '预警库龄',
    `product_title` VARCHAR(500) NULL COMMENT '商品中文名称',
    `product_title_en` VARCHAR(500) NULL COMMENT '商品英文名称',
    `warehouse_desc` VARCHAR(255) NULL COMMENT '谷仓仓库名称',
    `warehouse_age` INT NULL COMMENT '谷仓返回的库龄天数',
    `expiration_date` VARCHAR(32) NULL COMMENT '过期日期，保留原始格式',
    `source_page` INT NOT NULL COMMENT '来源页码',
    `source_row_no` INT NOT NULL COMMENT '接口页内行号',
    `api_code` INT NULL COMMENT '业务状态码',
    `api_message` VARCHAR(500) NULL COMMENT '返回消息',
    `api_total` BIGINT NULL COMMENT '总记录数',
    `sync_batch_id` VARCHAR(64) NOT NULL COMMENT '最新成功同步批次ID',
    `raw_json` JSON NOT NULL COMMENT '完整谷仓库龄原始JSON',
    `pulled_at` DATETIME NOT NULL COMMENT '真实拉取时间；迁移初始化不改此时间',
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    UNIQUE KEY `uk_gc_age_latest_page_row` (`source_page`,`source_row_no`),
    KEY `idx_gc_age_latest_warehouse_sku` (`warehouse_code`,`product_sku`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='谷仓eBay库存库龄最新单批快照；每周一06:00全量事务覆盖；与月快照隔离';

-- 来源：RuoYi-Vue-springboot3/sql/20260818_goodcang_inventory_age_lingxing_product_procurement.sql
USE `jmh_data_platform`;
CREATE TABLE IF NOT EXISTS `ods_lingxing_product_procurement_monthly` (
    `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '自增主键',
    `snapshot_month` CHAR(7) NOT NULL COMMENT '快照归属年月，格式YYYY-MM',
    `sku` VARCHAR(255) NOT NULL COMMENT '领星本地产品SKU',
    `cg_price` DECIMAL(24,6) NULL COMMENT '采购成本，来源data.cg_price',
    `sync_batch_id` VARCHAR(64) NOT NULL COMMENT '本次同步批次ID',
    `pulled_at` DATETIME NOT NULL COMMENT '接口拉取时间',
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '记录创建时间',
    `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '记录更新时间',
    PRIMARY KEY (`id`),
    UNIQUE KEY `uk_lx_product_procurement_month_sku` (`snapshot_month`,`sku`),
    KEY `idx_lx_product_procurement_sku` (`sku`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='领星产品管理采购成本月度ODS快照';
