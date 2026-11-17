-- ============================================================================
-- 02_仓位库存明细周报建表.sql
-- 目标库：date-project
-- 用途  ：脚本中心「仓位库存明细周报」组件的数据底座
-- 特性  ：幂等（CREATE TABLE IF NOT EXISTS），可重复执行
--         新建表及兼容补列/扩列/唯一索引升级，不删除业务数据
-- 生成  ：2026-09-09
--
-- 【设计原则】
--   按要求「数据源所有字段都保存，用的时候只取需要的字段」：
--   三个领星接口返回什么就存什么，一列一字段，另加 raw_json 兜底。
--   Excel 只是这些表的一个视图，后续再要别的字段直接查表，不用重新定规则拉取。
--
-- 【为什么不复用现有表（实测依据）】
--   1) jmh_data_platform.warehouse_inventory_detail
--      表结构看着有 28 列，但实测 4,449 行中：
--        fnsku / product_total / product_bad_num / product_qc_num /
--        average_age / stock_cost / stock_cost_total / transit_head_cost  全 NULL
--        good_lock_num / purchase_price / price / stock_price 等          全是建表默认 0
--      同步代码只写 9 列，其余是预留空列；且只覆盖 7 个仓，AMZ 仓一个没有。
--      该表正被 eBay 补货快照和跟价表读取，改写入会牵动它们。
--   2) date-project.ods_lingxing_ctu_inventory_detail
--      有 raw_json，但只覆盖 8 个中转仓、且是按月（pull_month）语义，
--      周频写入会打乱现有库龄成本链路。
--   3) inventoryBinDetails（仓位库存明细）全项目从未接入，无表可用。
--
-- 【实测数据量，用于容量预估】
--   库存明细 inventoryDetails      全量 8,571 行 / 16 个仓 / 4,353 个 product_id
--   仓位库存 inventoryBinDetails   全量 26,310 行
--   产品详情 batchGetProductInfo   4,353 个 product_id，100 个一批共 44 批
--   单周新增约 39,000 行，一年约 200 万行，单表可控。
-- ============================================================================

USE `date-project`;

-- ---------------------------------------------------------------------------
-- 表1：仓库库存明细周快照
-- 接口：erp/sc/routing/data/local_inventory/inventoryDetails
-- 实测该接口顶层返回 28 个字段，此处全部落列，另存 raw_json。
--
-- 唯一键为什么带 seller_id：
--   实测全量 8,571 行中，(wid, product_id) 有 36 组重复，
--   同一 SKU 同一仓因 seller_id 不同返回多条，共享同一份物理库存。
--   例：wid=18678 product_id=398670
--       seller_id=0     product_total=20
--       seller_id=12655 product_total=0
--   ODS 层原样保留全部行，导出时再按 (wid, product_id) 取最大值去重
--   （与 AmzWarehouseInventorySyncService 已有口径一致：取最大，不求和）。
--
-- 注意 purchase_price：实测非零率仅 16.6%，且非零行与 product_total 非零行
--   完全重合（754/754）——有库存才有采购单价，零库存行为 0 是正常的，不是缺数。
-- ---------------------------------------------------------------------------
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

-- ---------------------------------------------------------------------------
-- 表2：库龄分档周快照（竖表）
-- 来源：表1 的 stock_age_list 拆解
--
-- 为什么用竖表不写死列：
--   分档名是按仓库配置的。实测当前 16 个仓统一为
--     0-29天库龄 / 30-89天库龄 / 90-120天库龄 / 121天以上库龄（7,493 行唯一一种），
--   但接口文档两个示例分别是
--     0-15/16-30/31-90/91天以上
--     0-15/16-45/61-120/121-150/151-180/181-210/366天以上
--   说明领星侧改配置就会变。写死列名以后一定会出事，竖表可以自适应。
--   导出时按 bucket_name 动态透视成列。
-- ---------------------------------------------------------------------------
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

-- ---------------------------------------------------------------------------
-- 表3：仓位库存明细周快照
-- 接口：erp/sc/routing/data/local_inventory/inventoryBinDetails
-- 实测返回 16 个字段，全部落列。
--
-- 粒度提醒：本表 1 行 = (仓库, 仓位, 产品)，比表1 细 3 倍多
--   （wid=18674：表1 741 行，本表 3,415 行）。
--   导出时必须先按 (wid, product_id) 汇总 lock_num / valid_num 再挂回表1，
--   否则一个 SKU 会炸成多行。
--
-- 覆盖度提醒：仓位是本地仓/中转仓的概念。
--   实测谷仓 4 个海外仓的仓位数据分别只有 4 / 19 / 19 / 7 行，
--   所以那 2,913 行在 Excel 里「锁定量(仓位)/未锁定量」为空是正常的。
-- ---------------------------------------------------------------------------
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
  `total` DECIMAL(24,6) NULL COMMENT '总量',
  `lock_num` DECIMAL(24,6) NULL COMMENT '锁定量；接口字段名 lockNum',
  `valid_num` DECIMAL(24,6) NULL COMMENT '未锁定量；接口字段名 validNum',
  `third_inventory` JSON NULL COMMENT '第三方库存原值；本接口只有8个数值，无对账数组，且实测几乎全为0',
  `raw_json` JSON NULL COMMENT '整条记录原值，字段兜底',
  `pulled_at` DATETIME NOT NULL COMMENT '实际拉取时间',
  `create_time` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '记录创建时间',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_bin_week` (`snapshot_date`,`sync_batch_id`,`wid`,`whb_id`,`product_id`),
  KEY `idx_bin_week_date_wid_pid` (`snapshot_date`,`wid`,`product_id`),
  KEY `idx_bin_week_date_sku` (`snapshot_date`,`sku`),
  KEY `idx_bin_week_batch` (`sync_batch_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='ODS-领星仓位库存明细周快照（接口16字段全存）';

-- 兼容已执行过本脚本早期版本的环境：早期版本漏建了 product_name 列。
-- CREATE TABLE IF NOT EXISTS 对已存在的表不会补列，所以这里单独补一次。
SET @sql := IF(
  (SELECT COUNT(*) FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA='date-project'
      AND TABLE_NAME='ods_lingxing_inventory_bin_detail_weekly'
      AND COLUMN_NAME='product_name') = 0,
  'ALTER TABLE `ods_lingxing_inventory_bin_detail_weekly` ADD COLUMN `product_name` VARCHAR(500) NULL COMMENT ''产品名称；接口文档未列出的实际返回字段，可作为产品详情缺失时的兜底'' AFTER `sku`',
  'SELECT ''ods_lingxing_inventory_bin_detail_weekly.product_name 已存在，跳过'' AS `提示`');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

-- ---------------------------------------------------------------------------
-- 表4：本地产品详情周快照
-- 接口：erp/sc/routing/data/local_inventory/batchGetProductInfo
-- 实测返回 58 个顶层字段。常用标量平铺成列，
-- supplier_quote / picture_list / declaration / clearance / custom_fields
-- 等嵌套结构只进 raw_json，避免为了「全字段」把表撑成几百列。
--
-- 关联提醒：本接口返回的主键字段名是 id，等于库存明细的 product_id。
--   实测按 productIds 请求 100 个返回 100 个，id→sku 与库存明细
--   product_id→sku 映射 0 条不一致。
--
-- 数据可用性提醒（全量统计 1,198 个 product_id，非抽样）：
--   cg_package_*（包装规格）      96.6%
--   cg_product_gross_weight       96.2%
--   cg_product_*（产品规格）      91.7%
--   cg_product_net_weight         88.1%
--   cg_price                      67.8%
--   cg_box_weight（外箱实重）      5.9%   ← 稀疏
--   cg_box_*（外箱规格）           5.5%   ← 稀疏
--   cg_box_pcs（单箱数量）         0.7%
--   category_name                  0.0%   ← 领星侧完全未维护
--   注意 cg_price 是产品档案的当前采购成本，与库存明细的 purchase_price
--   （该批库存的实际加权进价）不是一回事，有库存的 200 行里 87 行数值不同。
--   Excel 的「采购单价」和「库存金额」都用 purchase_price，保持自洽。
-- ---------------------------------------------------------------------------
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

-- 兼容已执行过本脚本早期版本的环境：早期版本 model 建成了 VARCHAR(200)，
-- 实测全量 4,353 个 SKU 中最长 222 字符，会写入失败（Data too long）。
SET @sql := IF(
  (SELECT CHARACTER_MAXIMUM_LENGTH FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA='date-project'
      AND TABLE_NAME='ods_lingxing_product_info_weekly'
      AND COLUMN_NAME='model') < 1000,
  'ALTER TABLE `ods_lingxing_product_info_weekly` MODIFY COLUMN `model` VARCHAR(1000) NULL COMMENT ''产品型号；实测是逗号分隔的OE号列表，全量4353个SKU最长222字符，留4.5倍余量''',
  'SELECT ''ods_lingxing_product_info_weekly.model 宽度已足够，跳过'' AS `提示`');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

-- ---------------------------------------------------------------------------
-- 表5：周报导出文件留底登记
-- 部署机上已生成的文件永不删除，本表只登记不清理。
-- 页面按 snapshot_date 倒序列出历史文件供下载。
-- ---------------------------------------------------------------------------
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
  `status` VARCHAR(20) NOT NULL DEFAULT 'SUCCESS' COMMENT 'RUNNING / SUCCESS / FAILED / INTERRUPTED',
  `error_message` TEXT NULL COMMENT '失败原因',
  `trigger_type` VARCHAR(20) NOT NULL DEFAULT 'job' COMMENT 'job=定时触发 manual=页面手动',
  `generated_at` DATETIME NOT NULL COMMENT '文件生成完成时间',
  `create_time` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '记录创建时间',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_export_file` (`export_code`,`snapshot_date`,`file_name`),
  KEY `idx_export_code_date` (`export_code`,`snapshot_date`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='周报导出文件留底登记；部署机文件永不删除';

SELECT '02 建表脚本执行完毕' AS `结果`;

-- 同日重跑保留各批次；仅调整唯一索引，不删除表或数据。
SET @weekly_ddl := IF((SELECT GROUP_CONCAT(COLUMN_NAME ORDER BY SEQ_IN_INDEX) FROM information_schema.STATISTICS WHERE TABLE_SCHEMA='date-project' AND TABLE_NAME='ods_lingxing_inventory_detail_weekly' AND INDEX_NAME='uk_inv_week') = 'snapshot_date,sync_batch_id,wid,product_id,seller_id', 'SELECT 1', 'ALTER TABLE `ods_lingxing_inventory_detail_weekly` DROP INDEX `uk_inv_week`, ADD UNIQUE KEY `uk_inv_week` (`snapshot_date`,`sync_batch_id`,`wid`,`product_id`,`seller_id`)');
PREPARE weekly_stmt FROM @weekly_ddl; EXECUTE weekly_stmt; DEALLOCATE PREPARE weekly_stmt;
SET @weekly_ddl := IF((SELECT GROUP_CONCAT(COLUMN_NAME ORDER BY SEQ_IN_INDEX) FROM information_schema.STATISTICS WHERE TABLE_SCHEMA='date-project' AND TABLE_NAME='ods_lingxing_inventory_age_bucket_weekly' AND INDEX_NAME='uk_age_week') = 'snapshot_date,sync_batch_id,wid,product_id,seller_id,bucket_index', 'SELECT 1', 'ALTER TABLE `ods_lingxing_inventory_age_bucket_weekly` DROP INDEX `uk_age_week`, ADD UNIQUE KEY `uk_age_week` (`snapshot_date`,`sync_batch_id`,`wid`,`product_id`,`seller_id`,`bucket_index`)');
PREPARE weekly_stmt FROM @weekly_ddl; EXECUTE weekly_stmt; DEALLOCATE PREPARE weekly_stmt;
-- 已执行10的环境保留新业务键，重跑旧初始化脚本不得将其降级。首次部署需继续执行10/11。
SET @weekly_ddl := IF((SELECT GROUP_CONCAT(COLUMN_NAME ORDER BY SEQ_IN_INDEX) FROM information_schema.STATISTICS WHERE TABLE_SCHEMA='date-project' AND TABLE_NAME='ods_lingxing_inventory_bin_detail_weekly' AND INDEX_NAME='uk_bin_week') IN ('snapshot_date,sync_batch_id,wid,whb_id,product_id','snapshot_date,sync_batch_id,wid,whb_id,product_id,bin_identity_key'), 'SELECT 1', 'ALTER TABLE `ods_lingxing_inventory_bin_detail_weekly` DROP INDEX `uk_bin_week`, ADD UNIQUE KEY `uk_bin_week` (`snapshot_date`,`sync_batch_id`,`wid`,`whb_id`,`product_id`)');
PREPARE weekly_stmt FROM @weekly_ddl; EXECUTE weekly_stmt; DEALLOCATE PREPARE weekly_stmt;
SET @weekly_ddl := IF((SELECT GROUP_CONCAT(COLUMN_NAME ORDER BY SEQ_IN_INDEX) FROM information_schema.STATISTICS WHERE TABLE_SCHEMA='date-project' AND TABLE_NAME='ods_lingxing_product_info_weekly' AND INDEX_NAME='uk_prod_week') = 'snapshot_date,sync_batch_id,product_id', 'SELECT 1', 'ALTER TABLE `ods_lingxing_product_info_weekly` DROP INDEX `uk_prod_week`, ADD UNIQUE KEY `uk_prod_week` (`snapshot_date`,`sync_batch_id`,`product_id`)');
PREPARE weekly_stmt FROM @weekly_ddl; EXECUTE weekly_stmt; DEALLOCATE PREPARE weekly_stmt;
