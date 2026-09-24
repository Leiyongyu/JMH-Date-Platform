-- ============================================================================
-- 首页「商品分析」全部建表 + 订单上传接口的表结构变更
--
-- 在 Python 业务库 date-project 执行。**整份可重复执行**：
-- 建表一律 CREATE TABLE IF NOT EXISTS，加列/加索引用动态SQL判断存在与否，
-- 重复跑不会报 1050/1060/1061，也不会动任何已有数据。
--
-- Java 库 jmh_data_platform 的 Quartz 任务不在这份里（跨库容易连错），见：
--   deploy/ebay-store-listing/02_每月5号05点Quartz任务.sql   在售刊登每月同步
--   deploy/feishu-bad-transaction/01_每周三18点Quartz任务.sql  飞书不良交易刊登
--
-- ----------------------------------------------------------------------------
-- 首页商品分析的四张卡片各自读什么
-- ----------------------------------------------------------------------------
-- AMAZON·在售商品 负责人在售SKU数
--     ods_lingxing_amz_listing_latest / _state，Java库 shop_list，
--     dwd_performance_owner_rule                          ← 本脚本不建，只检查
-- EBAY·在售商品 负责人在售SKU数
--     Java库 ebay_product_listing，dwd_performance_owner_rule  ← 同上
-- AMAZON·人民币价格结构
--     上面那套 + dim_lingxing_currency_month
--     + dws_listing_cny_price_report / _tier               ← 同上
-- EBAY·美元价格结构（含「产品结构」弹窗）
--     ods_ebay_store_listing_latest / _state               ← 本脚本建
--     dwd_ebay_listing_sku                                 ← 本脚本建
--     dws_ebay_listing_price_tier / _state                 ← 本脚本建
--     dwd_ebay_sku_analysis_order（销量，本脚本加账号列）
--     dws_ebay_sku_unit_price（不良交易量）                 ← 本脚本不建，只检查
--
-- 本脚本负责的就是 eBay 那条线：在售刊登三层 + 订单的店铺维度。
-- 其余表属于早就上线的功能，缺了说明那个功能没部署，第0步会点出来。
-- ============================================================================

USE `date-project`;
SET NAMES utf8mb4 COLLATE utf8mb4_unicode_ci;
SET @db = DATABASE();


-- ============================================================================
-- 第0步【只读】前置检查：首页商品分析依赖的表，哪些在、哪些缺
--
-- 「本脚本会建」的行现在缺是正常的，往下执行就有了。
-- 「需先部署」的行缺了，说明对应功能没上线，去跑它自己的迁移，别在这里补。
-- ============================================================================
SELECT t.表 AS 表名, t.归属,
       IF(c.TABLE_NAME IS NULL, '✗ 缺失', '✓ 已存在') AS 状态,
       IFNULL(c.TABLE_ROWS, 0) AS 估算行数
FROM (
    SELECT 'ods_ebay_store_listing_latest' AS 表, '本脚本会建｜在售刊登贴源' AS 归属 UNION ALL
    SELECT 'ods_ebay_store_listing_state',  '本脚本会建｜在售刊登同步状态' UNION ALL
    SELECT 'dwd_ebay_listing_sku',          '本脚本会建｜刊登SKU清洗层' UNION ALL
    SELECT 'dws_ebay_listing_price_tier',   '本脚本会建｜美元价与档位' UNION ALL
    SELECT 'dws_ebay_listing_price_state',  '本脚本会建｜每月加工状态' UNION ALL
    SELECT 'ods_ebay_sku_analysis_order_raw','需先部署｜订单上传（SKU分析菜单）' UNION ALL
    SELECT 'dwd_ebay_sku_analysis_order',   '需先部署｜订单清洗层，本脚本给它加账号列' UNION ALL
    SELECT 'dws_ebay_sku_unit_price',       '需先部署｜飞书不良交易量' UNION ALL
    SELECT 'ods_feishu_bad_transaction_listing','需先部署｜飞书不良交易刊登贴源' UNION ALL
    SELECT 'dim_lingxing_currency_month',   '需先部署｜月度汇率，换美元要用' UNION ALL
    SELECT 'ods_lingxing_amz_listing_latest','需先部署｜AMZ在售刊登' UNION ALL
    SELECT 'ods_lingxing_amz_listing_state','需先部署｜AMZ同步状态' UNION ALL
    SELECT 'dws_listing_cny_price_report',  '需先部署｜AMZ人民币价格结构' UNION ALL
    SELECT 'dws_listing_cny_price_tier',    '需先部署｜AMZ人民币档位明细' UNION ALL
    SELECT 'dwd_performance_owner_rule',    '需先部署｜负责人规则' UNION ALL
    SELECT 'scheduler_task',                '需先部署｜Python任务白名单'
) t
LEFT JOIN information_schema.TABLES c
       ON c.TABLE_SCHEMA = @db AND c.TABLE_NAME = t.表
ORDER BY FIELD(LEFT(t.归属, 4), '本脚本', '需先部署'), t.表;


-- ============================================================================
-- 第1步 ODS：eBay 在售刊登贴源表（按月累积）
--
-- 每月5日从官方 Trading 接口拉一次，一行=一条在售刊登，接口给什么存什么。
-- 已存在就跳过，不会动里面的数据。
-- ============================================================================
CREATE TABLE IF NOT EXISTS ods_ebay_store_listing_latest (
 id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '原始记录主键',
 stat_month CHAR(7) NOT NULL COMMENT '留档月份YYYY-MM，取自pulled_at的北京时间月份，不是接口月份',
 seller_user_id VARCHAR(128) NOT NULL COMMENT 'eBay身份接口返回的稳定账号ID',
 seller_account VARCHAR(128) NOT NULL COMMENT 'eBay卖家账号用户名，用于区分店铺',
 item_id VARCHAR(64) NOT NULL COMMENT 'eBay商品刊登ItemID；同账号内唯一，不按SKU去重',
 sku TEXT NULL COMMENT '刊登SKU原值，缺失为NULL，多变体见variations_json',
 title TEXT NULL COMMENT '刊登商品标题',
 site VARCHAR(16) NULL COMMENT '从商品ViewItemURL域名识别站点，非账号注册站点；无法识别为空',
 current_price VARCHAR(128) NULL COMMENT 'CurrentPrice原始十进制文本，不换汇不丢精度',
 currency VARCHAR(16) NULL COMMENT 'CurrentPrice的currencyID原币种',
 buy_it_now_price VARCHAR(128) NULL COMMENT 'BuyItNowPrice原始十进制文本',
 buy_it_now_currency VARCHAR(16) NULL COMMENT 'BuyItNowPrice原币种',
 quantity BIGINT UNSIGNED NULL COMMENT '接口Quantity原值，非推算库存',
 quantity_available BIGINT UNSIGNED NULL COMMENT '接口QuantityAvailable可用数量',
 quantity_sold BIGINT UNSIGNED NULL COMMENT '接口QuantitySold累计已售数量，缺失不补零',
 watch_count BIGINT UNSIGNED NULL COMMENT '接口WatchCount关注数量',
 listing_type VARCHAR(128) NULL COMMENT '刊登类型，如FixedPriceItem',
 listing_duration VARCHAR(64) NULL COMMENT '刊登时长，如GTC',
 time_left VARCHAR(128) NULL COMMENT '接口TimeLeft原始时长字符串',
 start_time VARCHAR(128) NULL COMMENT 'ListingDetails.StartTime原值，保留UTC标记',
 view_item_url TEXT NULL COMMENT '商品刊登查看链接',
 image_url TEXT NULL COMMENT 'PictureDetails.GalleryURL主图链接',
 variations_json JSON NULL COMMENT '多规格变体数组，每项含sku/price/quantity/quantity_sold；无变体为NULL。统计多规格刊登必须按本列逐变体计，不能用父级sku/current_price',
 sync_batch_id VARCHAR(64) NOT NULL COMMENT '完整成功发布的同步批次ID',
 pulled_at DATETIME NOT NULL COMMENT '本批拉取开始时间，北京时间',
 PRIMARY KEY(id),
 UNIQUE KEY uk_month_seller_item(stat_month,seller_user_id,item_id),
 KEY idx_month(stat_month),
 KEY idx_seller_month(seller_user_id,stat_month),
 KEY idx_account_sku(seller_account,sku(128))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin
  COMMENT='ODS-eBay官方Trading在售商品，按月累积；每账号每月一份，键(月份,账号,ItemID)';

CREATE TABLE IF NOT EXISTS ods_ebay_store_listing_state (
 stat_month CHAR(7) NOT NULL COMMENT '留档月份YYYY-MM',
 seller_user_id VARCHAR(128) NOT NULL COMMENT 'eBay稳定账号ID',
 seller_account VARCHAR(128) NOT NULL COMMENT '本次认证成功的卖家用户名',
 row_count BIGINT UNSIGNED NOT NULL COMMENT '该账号当月成功发布的条数，明确空店为0',
 sync_batch_id VARCHAR(64) NOT NULL COMMENT '同步批次ID，与商品原始表同事务提交',
 pulled_at DATETIME NOT NULL COMMENT '拉取开始时间，北京时间',
 published_at DATETIME NOT NULL COMMENT '拉取完成后发布开始时间，北京时间',
 PRIMARY KEY(stat_month,seller_user_id),
 KEY idx_month(stat_month)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin
  COMMENT='ODS-eBay店铺每月同步状态，每账号每月一行；row_count=0代表当月确实空店，缺行代表当月没同步';


-- ============================================================================
-- 第2步 DWD：刊登明细清洗层
--
-- 一行 = 一个「可以分档的刊登SKU」。相对 ODS 做四件事：
--   拆多规格变体（不拆会把N个SKU塌缩成1个，且价格分档会错）
--   丢掉没SKU/没站点/价格不是正数的行，并在 state 表里计数
--   价格从文本转 DECIMAL，站点与币种统一大写
--   SKU 去首尾空白
-- 这一层**不换汇、不分档**：留一份原币的干净明细，能直接和 eBay 后台逐条对。
-- ============================================================================
CREATE TABLE IF NOT EXISTS dwd_ebay_listing_sku (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '主键',
  stat_month CHAR(7) NOT NULL COMMENT '统计月份YYYY-MM，与ODS同值',
  seller_user_id VARCHAR(128) NOT NULL COMMENT 'eBay稳定账号ID',
  seller_account VARCHAR(128) NOT NULL COMMENT '店铺（卖家账号用户名）',
  item_id VARCHAR(64) NOT NULL COMMENT '刊登ItemID',
  variation_no INT UNSIGNED NOT NULL DEFAULT 0 COMMENT '0=无变体的父级行；1..n=该刊登下第n个变体，按数组顺序',
  sku VARCHAR(255) NOT NULL COMMENT '去首尾空白后的SKU；父级行取父级SKU，变体行取变体SKU',
  site VARCHAR(16) NOT NULL COMMENT '站点代码，大写；从ViewItemURL域名识别',
  currency VARCHAR(16) NOT NULL COMMENT '原币种，大写',
  price_original DECIMAL(20,6) NOT NULL COMMENT '原币挂牌价，由ODS文本转数值；必为正数',
  quantity BIGINT UNSIGNED NULL COMMENT '该SKU的接口数量，仅参考',
  quantity_sold BIGINT UNSIGNED NULL COMMENT '该SKU累计已售数量，仅参考',
  is_variation TINYINT NOT NULL DEFAULT 0 COMMENT '1=来自变体数组，0=来自父级行',
  etl_batch_id VARCHAR(64) NOT NULL COMMENT '本次清洗批次ID',
  computed_at DATETIME NOT NULL COMMENT '本行清洗时间',
  PRIMARY KEY(id),
  UNIQUE KEY uk_dwd_listing_sku(stat_month,seller_user_id,item_id,variation_no),
  KEY idx_dwd_month_sku(stat_month,sku),
  KEY idx_dwd_month_shop(stat_month,seller_account),
  KEY idx_dwd_month_currency(stat_month,currency)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='DWD-eBay在售刊登SKU明细：已拆变体、已清洗，原币不换汇不分档';


-- ============================================================================
-- 第3步 DWS：换汇 + 分档汇总层
--
-- 一行 = 月 × 店铺 × 站点 × SKU。在 DWD 之上做两件事：
--   换汇：美元价 = 原币价 × rate_org(原币) ÷ rate_org(USD)，两个汇率都取
--        「不晚于统计月份、且有正值」的最新一个月；USD 原币直接短路不换。
--   分档：七档左闭右开 [0,5) [5,20) [20,50) [50,100) [100,200) [200,500) [500,∞)
--
-- 同一店铺同一站点同一SKU挂多条刊登时取最低价、只留一行，listing_count
-- 记下合并了几条。每条都算的话，铺得多的SKU会在档位占比里被重复计。
-- ============================================================================
CREATE TABLE IF NOT EXISTS dws_ebay_listing_price_tier (
  stat_month CHAR(7) NOT NULL COMMENT '统计月份YYYY-MM',
  seller_user_id VARCHAR(128) NOT NULL COMMENT 'eBay稳定账号ID',
  seller_account VARCHAR(128) NOT NULL COMMENT '店铺（卖家账号用户名）',
  site VARCHAR(16) NOT NULL COMMENT '站点代码',
  sku VARCHAR(255) NOT NULL COMMENT 'SKU',
  currency VARCHAR(16) NOT NULL COMMENT '最低价那条刊登的原币种',
  price_original DECIMAL(20,6) NOT NULL COMMENT '该组合内最低的原币价',
  price_usd DECIMAL(24,8) NOT NULL COMMENT '换算后的美元价；分档前不四舍五入，本列是展示用的截断值',
  tier_no TINYINT UNSIGNED NOT NULL COMMENT '价格档位1~7，与页面USD_LABELS同序',
  rate_month CHAR(7) NOT NULL COMMENT '实际取用的原币汇率月份；与stat_month不同即发生了回退',
  rate_org DECIMAL(20,8) NOT NULL COMMENT '原币的rate_org（1原币=多少人民币）；美元原币短路时记1',
  usd_rate_month CHAR(7) NOT NULL COMMENT '实际取用的美元汇率月份',
  usd_rate_org DECIMAL(20,8) NOT NULL COMMENT '美元的rate_org；美元原币短路时记1',
  listing_count INT UNSIGNED NOT NULL DEFAULT 1 COMMENT '该组合合并了几条刊登SKU',
  computed_at DATETIME NOT NULL COMMENT '本行计算时间',
  PRIMARY KEY(stat_month,seller_user_id,site,sku),
  KEY idx_dws_month_shop(stat_month,seller_account),
  KEY idx_dws_month_tier(stat_month,tier_no),
  KEY idx_dws_month_sku(stat_month,sku)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='DWS-eBay刊登美元价与价格档位，按月×店铺×站点×SKU；同组合多刊登取最低价';

-- 每月一行的加工状态：页面用它显示「这份报表算的是哪个月、用的哪个月汇率」，
-- 也用它判断源数据更新了要不要提示重算。清洗丢掉多少行也记在这里——
-- 丢行必须看得见。
CREATE TABLE IF NOT EXISTS dws_ebay_listing_price_state (
  stat_month CHAR(7) NOT NULL COMMENT '统计月份YYYY-MM',
  ods_rows BIGINT UNSIGNED NOT NULL DEFAULT 0 COMMENT '该月ODS刊登条数',
  dwd_rows BIGINT UNSIGNED NOT NULL DEFAULT 0 COMMENT '拆变体清洗后的刊登SKU行数',
  dws_rows BIGINT UNSIGNED NOT NULL DEFAULT 0 COMMENT '换汇分档后的店铺站点SKU行数',
  dropped_no_sku BIGINT UNSIGNED NOT NULL DEFAULT 0 COMMENT '清洗丢弃：SKU为空',
  dropped_no_site BIGINT UNSIGNED NOT NULL DEFAULT 0 COMMENT '清洗丢弃：站点为空',
  dropped_bad_price BIGINT UNSIGNED NOT NULL DEFAULT 0 COMMENT '清洗丢弃：价格非正数或不是数值',
  dropped_no_rate BIGINT UNSIGNED NOT NULL DEFAULT 0 COMMENT '换汇丢弃：该币种没有任何可用rate_org',
  missing_currencies VARCHAR(500) NOT NULL DEFAULT '' COMMENT '缺汇率的币种，逗号分隔；为空表示齐全',
  shop_count INT UNSIGNED NOT NULL DEFAULT 0 COMMENT '该月店铺数',
  sku_count INT UNSIGNED NOT NULL DEFAULT 0 COMMENT '该月去重SKU数',
  rate_month CHAR(7) NOT NULL DEFAULT '' COMMENT '美元汇率实际取用的月份',
  etl_batch_id VARCHAR(64) NOT NULL COMMENT '本次加工批次ID',
  source_pulled_at DATETIME NULL COMMENT '该月ODS最新的拉取时间，用于判断源数据有没有更新',
  computed_at DATETIME NOT NULL COMMENT '本次加工时间',
  PRIMARY KEY(stat_month)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='DWS-eBay刊登价格分层每月加工状态，含清洗丢弃行数与所用汇率月份';


-- ============================================================================
-- 第4步 订单上传接口：加「平台账号」列
--
-- 数字酋长订单模板从 2026-09-24 起在最前面多了一列「平台账号」，值就是
-- eBay 卖家账号本身（aplus-shop、oyeah-motor…），与上面 DWS 的
-- seller_account 完全相等，等值join即可，**不需要映射表**。
--
--   ods_ebay_sku_analysis_order_raw.source_platform_account   Excel原值
--   dwd_ebay_sku_analysis_order.seller_account                去首尾空白
--
-- 空串的含义是「这批订单是旧模板上传的」，不是「没有店铺」。要让历史月份
-- 也能按店铺筛，得用新模板把那些月份重传一遍。
--
-- 当天先按「店铺名称」接过一版，跑过那一版的机器上有 source_shop_name /
-- shop_name 两个旧列名，这里**改名**而不是新增：两个列名指的是同一件事，
-- 留着旧列只会多一份永远是空的数据，以后谁都说不清该读哪个。
--
-- 四段都是「存在才执行」，表不在就整段跳过（去 SKU 分析菜单传一次订单，
-- Python 会自己把订单那几张表建出来）。重复跑不报错。
-- ============================================================================

SET @has_ods = EXISTS(SELECT 1 FROM information_schema.TABLES
                      WHERE TABLE_SCHEMA=@db AND TABLE_NAME='ods_ebay_sku_analysis_order_raw');
SET @has_dwd = EXISTS(SELECT 1 FROM information_schema.TABLES
                      WHERE TABLE_SCHEMA=@db AND TABLE_NAME='dwd_ebay_sku_analysis_order');

-- 4.1 ODS：有旧列就改名，没有就加，已经是新列名就什么都不做
SET @sql = IF(NOT @has_ods, 'DO 0',
  IF(EXISTS(SELECT 1 FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA=@db AND TABLE_NAME='ods_ebay_sku_analysis_order_raw'
              AND COLUMN_NAME='source_shop_name'),
    'ALTER TABLE ods_ebay_sku_analysis_order_raw RENAME COLUMN source_shop_name TO source_platform_account',
    IF(EXISTS(SELECT 1 FROM information_schema.COLUMNS
              WHERE TABLE_SCHEMA=@db AND TABLE_NAME='ods_ebay_sku_analysis_order_raw'
                AND COLUMN_NAME='source_platform_account'),
      'DO 0',
      'ALTER TABLE ods_ebay_sku_analysis_order_raw ADD COLUMN source_platform_account VARCHAR(191) DEFAULT NULL COMMENT ''Excel第一列原始平台账号，2026-09-24起模板新增'' AFTER source_row')));
PREPARE s FROM @sql; EXECUTE s; DEALLOCATE PREPARE s;

-- 4.2 DWD：同上
SET @sql = IF(NOT @has_dwd, 'DO 0',
  IF(EXISTS(SELECT 1 FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA=@db AND TABLE_NAME='dwd_ebay_sku_analysis_order'
              AND COLUMN_NAME='shop_name'),
    'ALTER TABLE dwd_ebay_sku_analysis_order RENAME COLUMN shop_name TO seller_account',
    IF(EXISTS(SELECT 1 FROM information_schema.COLUMNS
              WHERE TABLE_SCHEMA=@db AND TABLE_NAME='dwd_ebay_sku_analysis_order'
                AND COLUMN_NAME='seller_account'),
      'DO 0',
      'ALTER TABLE dwd_ebay_sku_analysis_order ADD COLUMN seller_account VARCHAR(191) NOT NULL DEFAULT '''' COMMENT ''eBay卖家账号，取上传源数据的平台账号；与dws_ebay_listing_price_tier.seller_account同义；空串=该批次源文件没有这一列'' AFTER site_name')));
PREPARE s FROM @sql; EXECUTE s; DEALLOCATE PREPARE s;

-- 4.3 注释刷一遍（RENAME COLUMN 不会带新注释过来）
SET @sql = IF(NOT @has_ods, 'DO 0',
  'ALTER TABLE ods_ebay_sku_analysis_order_raw MODIFY COLUMN source_platform_account VARCHAR(191) DEFAULT NULL COMMENT ''Excel第一列原始平台账号，2026-09-24起模板新增''');
PREPARE s FROM @sql; EXECUTE s; DEALLOCATE PREPARE s;

SET @sql = IF(NOT @has_dwd, 'DO 0',
  'ALTER TABLE dwd_ebay_sku_analysis_order MODIFY COLUMN seller_account VARCHAR(191) NOT NULL DEFAULT '''' COMMENT ''eBay卖家账号，取上传源数据的平台账号；与dws_ebay_listing_price_tier.seller_account同义；空串=该批次源文件没有这一列''');
PREPARE s FROM @sql; EXECUTE s; DEALLOCATE PREPARE s;

-- 4.4 索引：有旧名就改名，没有就建
SET @sql = IF(NOT @has_dwd, 'DO 0',
  IF(EXISTS(SELECT 1 FROM information_schema.STATISTICS
            WHERE TABLE_SCHEMA=@db AND TABLE_NAME='dwd_ebay_sku_analysis_order'
              AND INDEX_NAME='idx_esa_dwd_shop_time'),
    'ALTER TABLE dwd_ebay_sku_analysis_order RENAME INDEX idx_esa_dwd_shop_time TO idx_esa_dwd_account_time',
    IF(EXISTS(SELECT 1 FROM information_schema.STATISTICS
              WHERE TABLE_SCHEMA=@db AND TABLE_NAME='dwd_ebay_sku_analysis_order'
                AND INDEX_NAME='idx_esa_dwd_account_time'),
      'DO 0',
      'ALTER TABLE dwd_ebay_sku_analysis_order ADD KEY idx_esa_dwd_account_time (seller_account, payment_time)')));
PREPARE s FROM @sql; EXECUTE s; DEALLOCATE PREPARE s;

-- 4.5 已入库的批次：ODS里有账号就回填到DWD。
--     只有用新模板传过的批次才填得上；旧批次两边都是空的，回填不动。
SET @sql = IF(NOT (@has_ods AND @has_dwd), 'DO 0',
  'UPDATE dwd_ebay_sku_analysis_order d
     INNER JOIN ods_ebay_sku_analysis_order_raw o
             ON o.import_batch_id = d.import_batch_id AND o.source_row = d.source_row
      SET d.seller_account = TRIM(o.source_platform_account)
    WHERE d.seller_account = ''''
      AND o.source_platform_account IS NOT NULL AND TRIM(o.source_platform_account) <> ''''');
PREPARE s FROM @sql; EXECUTE s; DEALLOCATE PREPARE s;


-- ============================================================================
-- 第5步 Python 侧任务登记（每月5日05:00 拉在售刊登）
--
-- Quartz 才是唯一计时器，这张表只是 Python 端的任务白名单。
-- ============================================================================
INSERT INTO scheduler_task(task_code,task_name,cron_expression,enabled,description)
VALUES('ebay_store_listing_sync','eBay店铺商品信息每月同步','0 0 5 5 * ?',1,
 '每月5日北京时间05:00，Quartz唯一计时；官方GetMyeBaySelling在售列表；配置账号完整拉取校验后按月覆盖，失败保留旧数据。拉完由价格结构页的刷新按钮走ODS->DWD->DWS重算。')
ON DUPLICATE KEY UPDATE task_name=VALUES(task_name),cron_expression=VALUES(cron_expression),
                        enabled=VALUES(enabled),description=VALUES(description);


-- ============================================================================
-- 第6步【只读】验收
-- ============================================================================

-- 6.1 五张表都该在了
SELECT TABLE_NAME AS 表, TABLE_ROWS AS 估算行数,
       ROUND((DATA_LENGTH+INDEX_LENGTH)/1024/1024, 1) AS 占用MB
FROM information_schema.TABLES
WHERE TABLE_SCHEMA=@db
  AND TABLE_NAME IN ('ods_ebay_store_listing_latest','ods_ebay_store_listing_state',
                     'dwd_ebay_listing_sku','dws_ebay_listing_price_tier',
                     'dws_ebay_listing_price_state')
ORDER BY TABLE_NAME;

-- 6.2 订单表的账号列与索引（三行都该有值）
SELECT 'ods.source_platform_account' AS 对象,
       IF(EXISTS(SELECT 1 FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=@db
                 AND TABLE_NAME='ods_ebay_sku_analysis_order_raw'
                 AND COLUMN_NAME='source_platform_account'), '✓', '✗ 缺失') AS 状态
UNION ALL
SELECT 'dwd.seller_account',
       IF(EXISTS(SELECT 1 FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=@db
                 AND TABLE_NAME='dwd_ebay_sku_analysis_order'
                 AND COLUMN_NAME='seller_account'), '✓', '✗ 缺失')
UNION ALL
SELECT 'dwd.idx_esa_dwd_account_time',
       IF(EXISTS(SELECT 1 FROM information_schema.STATISTICS WHERE TABLE_SCHEMA=@db
                 AND TABLE_NAME='dwd_ebay_sku_analysis_order'
                 AND INDEX_NAME='idx_esa_dwd_account_time'), '✓', '✗ 缺失')
UNION ALL
SELECT '旧列 dwd.shop_name 应已消失',
       IF(EXISTS(SELECT 1 FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=@db
                 AND TABLE_NAME='dwd_ebay_sku_analysis_order'
                 AND COLUMN_NAME='shop_name'), '✗ 还在，请检查', '✓');

-- 6.3 订单按月看账号覆盖：有账号的行=0 的月份，就是还没用新模板传过的
SELECT DATE_FORMAT(payment_time,'%Y-%m') AS 月份,
       COUNT(*) AS 行数,
       SUM(seller_account <> '') AS 有账号的行,
       COUNT(DISTINCT NULLIF(seller_account,'')) AS 账号数,
       ROUND(SUM(seller_account <> '')*100/COUNT(*), 1) AS 覆盖率
FROM dwd_ebay_sku_analysis_order
GROUP BY 1 ORDER BY 1;

-- 6.4 任务登记
SELECT task_code AS 任务, task_name, cron_expression, enabled
FROM scheduler_task
WHERE task_code IN ('ebay_store_listing_sync','feishu_bad_transaction_sync','ebay_token_health_check')
ORDER BY task_code;


-- ============================================================================
-- 执行完还要做什么
-- ============================================================================
-- 1. Java 库 jmh_data_platform 跑
--      deploy/ebay-store-listing/02_每月5号05点Quartz任务.sql
-- 2. 重启 Python、重新打包重启 Java、npm run build:prod
-- 3. 首页「EBAY · 美元价格结构」点一次刷新
--      → 跑 ODS→DWD→DWS，并重算飞书那张不良交易量表；不拉取任何外部接口
--      → 此时 dwd_ebay_listing_sku / dws_ebay_listing_price_tier 才会有数据
--    ODS 是空的（第一次部署、或以前删过表）就先等每月5日的同步，
--    或者在定时任务里手动跑一次「eBay店铺商品信息每月同步」。
-- 4. SKU 分析菜单用新模板重传订单；想让历史月份也能按店铺筛，
--    把那些月份一起重传（看 6.3 哪些月份覆盖率是0）
-- 5. 逐项核对：deploy/ebay-store-listing/05_核对价格分层与产品结构_只读.sql
-- ============================================================================
