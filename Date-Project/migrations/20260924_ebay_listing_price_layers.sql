-- Python业务库 date-project：恢复 eBay 在售刊登拉取，并把「清洗 / 换汇 / 分档」
-- 拆成 ODS -> DWD -> DWS 三层，各层一张表、各自可单独核对。
--
-- ============================================================================
-- 为什么要分层（顺带回答"为什么有的表叫 dwd"）
-- ============================================================================
-- 本项目的表名前缀就是数仓分层，不是随手起的：
--   ods_  贴源层：外部系统给什么就存什么，不做任何加工，只加批次/时间戳。
--   dwd_  明细层：一行一个业务事实，做清洗、拆开、标准化，但不做汇总。
--   dws_  汇总层：按分析口径加工好的结果（换汇、分档、按月×店铺汇总）。
--   dim_  维表：汇率、站点、分类这类被别人join的基准数据。
--
-- 所以 dwd_ebay_sku_analysis_order 并不是"从eBay拉来的源数据"——它是
-- 订单Excel的**清洗层**，它的贴源层是 ods_ebay_sku_analysis_order_raw
-- （Excel原样入库，含来源文件名/工作表/行号）。两张表一直都在。
--
-- 而从 eBay Trading 接口拉回来的在售刊登，贴源表一直叫
-- ods_ebay_store_listing_latest，前缀本来就是 ods。之前缺的不是 ods，
-- 是它后面的 dwd 和 dws：清洗（拆变体、去空SKU、价格转数值）和换汇分档
-- 全写在 Python 里、只留一份聚合结果，中间过程落不了地、也没法单独核对。
-- 本次把这两层补上。
--
-- ============================================================================
-- 这条链路长什么样
-- ============================================================================
--   ods_ebay_store_listing_latest     每月5日拉一次，一行=一条在售刊登（原样）
--        │  拆变体、去空SKU、价格转DECIMAL、站点/币种标准化
--        ▼
--   dwd_ebay_listing_sku              一行=一个可分档的「刊登SKU」
--        │  按 dim_lingxing_currency_month.rate_org 换成美元、落七档
--        ▼
--   dws_ebay_listing_price_tier       一行=月×店铺×站点×SKU 的美元价与档位
--        │  页面按 月/店铺 现场聚合
--        ▼
--   「EBAY · 美元价格结构」卡片 / 产品结构三图
--
-- 换汇口径：美元价 = 原币价 × rate_org(原币) ÷ rate_org(USD)，两个汇率都取
-- 「不晚于统计月份、且有正值」的最新一个月。USD 原币直接短路不换。
--
-- 执行：可重复执行，不删任何已有数据。

USE `date-project`;
SET NAMES utf8mb4 COLLATE utf8mb4_unicode_ci;


-- ============================================================================
-- 第1步 ODS：在售刊登贴源表（按月累积）
--
-- 机器上已经有这两张表就什么都不做。只有跑过 20260923_drop_ebay_store_listing.sql
-- 把表删掉的机器才会在这里重建——重建出来是空的，历史月份拉不回来，
-- 要等下一次每月同步才会有数据。
-- ============================================================================
CREATE TABLE IF NOT EXISTS ods_ebay_store_listing_latest (
 id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '原始记录主键',
 stat_month CHAR(7) NOT NULL COMMENT '留档月份YYYY-MM，取自pulled_at的北京时间月份，不是接口月份',
 seller_user_id VARCHAR(128) NOT NULL COMMENT 'eBay身份接口返回的稳定账号ID，覆盖范围及联合唯一键',
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
-- 一行 = 一个「可以分档的刊登SKU」。相对 ODS 做四件事，做完就不再有脏数据：
--   1. 拆变体。多规格刊登的父级行只有一个 sku 和一个价格，变体各有各的
--      SKU与价格。不拆会把多规格塌缩成一个SKU、且价格取错（实测43条刊登
--      带141个变体）。无变体的刊登退回用父级那行，variation_no=0。
--   2. 丢掉没有SKU、没有站点、价格不是正数的行，并在 state 表里计数——
--      丢多少必须看得见，不能悄悄少。
--   3. 价格从文本转 DECIMAL(20,6)，站点与币种统一大写去空白。
--   4. SKU 去首尾空白。
--
-- 这一层**不换汇、不分档**：留一份"原币的干净明细"，出了问题能直接和
-- eBay 后台逐条对，不用先把汇率的影响剥掉。
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
--   1. 换汇：美元价 = 原币价 × rate_org(原币) ÷ rate_org(USD)。
--      两个汇率都取 dim_lingxing_currency_month 里「不晚于统计月份、且该字段
--      有正值」的最新一个月，所以九月的刊登用九月的汇率、不用今天的汇率。
--      USD 原币直接短路，不经过任何汇率。
--   2. 分档：七档左闭右开 [0,5) [5,20) [20,50) [50,100) [100,200) [200,500) [500,∞)。
--
-- 同一店铺同一站点同一SKU挂了多条刊登时取**最低价**、只留一行
-- （实测2026-09有1021组这种情况），listing_count 记下合并了几条。
-- 不取最低价而是每条都算的话，铺得多的SKU会在占比里被重复计。
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
  rate_org DECIMAL(20,8) NOT NULL COMMENT '原币的rate_org（1原币=多少人民币）',
  usd_rate_month CHAR(7) NOT NULL COMMENT '实际取用的美元汇率月份',
  usd_rate_org DECIMAL(20,8) NOT NULL COMMENT '美元的rate_org',
  listing_count INT UNSIGNED NOT NULL DEFAULT 1 COMMENT '该组合合并了几条刊登SKU',
  computed_at DATETIME NOT NULL COMMENT '本行计算时间',
  PRIMARY KEY(stat_month,seller_user_id,site,sku),
  KEY idx_dws_month_shop(stat_month,seller_account),
  KEY idx_dws_month_tier(stat_month,tier_no),
  KEY idx_dws_month_sku(stat_month,sku)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='DWS-eBay刊登美元价与价格档位，按月×店铺×站点×SKU；同组合多刊登取最低价';

-- 每月一行的加工状态：页面用它显示"这份报表算的是哪个月、用的哪个月汇率"，
-- 也用它判断源数据变了要不要提示重算。清洗丢掉多少行也记在这里，
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
-- 第4步 Python 侧任务登记（每月5日05:00 拉取在售刊登）
--
-- Quartz 才是唯一计时器，这张表只是 Python 端的任务白名单。
-- Java 库 jmh_data_platform 里的 sys_job 见
-- deploy/ebay-store-listing/02_每月5号05点Quartz任务.sql。
-- ============================================================================
INSERT INTO scheduler_task(task_code,task_name,cron_expression,enabled,description)
VALUES('ebay_store_listing_sync','eBay店铺商品信息每月同步','0 0 5 5 * ?',1,
 '每月5日北京时间05:00，Quartz唯一计时；官方GetMyeBaySelling在售列表；配置账号完整拉取校验后按月覆盖，失败保留旧数据。拉完由价格结构页的刷新按钮走ODS->DWD->DWS重算。')
ON DUPLICATE KEY UPDATE task_name=VALUES(task_name),cron_expression=VALUES(cron_expression),
                        enabled=VALUES(enabled),description=VALUES(description);


-- ============================================================================
-- 第5步【只读】确认
-- ============================================================================
SELECT TABLE_NAME AS 表, TABLE_COMMENT AS 说明
FROM information_schema.TABLES
WHERE TABLE_SCHEMA='date-project'
  AND TABLE_NAME IN ('ods_ebay_store_listing_latest','ods_ebay_store_listing_state',
                     'dwd_ebay_listing_sku','dws_ebay_listing_price_tier',
                     'dws_ebay_listing_price_state')
ORDER BY TABLE_NAME;

SELECT task_code AS 任务, task_name, cron_expression, enabled
FROM scheduler_task WHERE task_code='ebay_store_listing_sync';
