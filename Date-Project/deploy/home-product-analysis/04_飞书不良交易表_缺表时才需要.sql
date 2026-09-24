-- ============================================================================
-- 【缺表时才需要】飞书「不良交易刊登」两张表
--
-- 在 Python 业务库 date-project 执行。可重复执行，建表一律 IF NOT EXISTS。
--
-- 01 的第0步检查里，若 ods_feishu_bad_transaction_listing 或
-- dws_ebay_sku_unit_price 显示「✗ 缺失」，执行本脚本补上；都在就不用跑。
--
-- 这两张表只供「产品结构」弹窗里的**不良交易率**那张图。缺了它们：
--   · 美元价格结构卡片照常工作（价格档来自在售刊登，与这两张表无关）
--   · 产品结构的销售数量占比图照常工作
--   · 只有不良交易率那张图会是空的
--   · 且每周三 18:00 的「飞书不良交易刊登每周同步」会因为表不存在而失败
--
--   ods_feishu_bad_transaction_listing   飞书原样落库，按 record_id 增量
--   dws_ebay_sku_unit_price              按月×店铺×SKU 汇总出的成交量与不良量
--
-- 建完表还要在 Python 服务的 .env 里配好 FEISHU_APP_ID / FEISHU_APP_SECRET，
-- 否则同步任务跑起来会报「请先配置」。配置项本身不在这份 SQL 的范围内。
-- ============================================================================

USE `date-project`;
SET NAMES utf8mb4 COLLATE utf8mb4_unicode_ci;


-- ============================================================================
-- 第1步 飞书不良交易刊登贴源表
-- ============================================================================
CREATE TABLE IF NOT EXISTS ods_feishu_bad_transaction_listing (
  -- 必须是二进制排序规则：飞书的 record_id 大小写敏感，实测存在
  -- rec277zuUdLAHp 与 rec277zuUdLahP 这种只差大小写的两条记录。
  -- 用本库默认的 utf8mb4_unicode_ci 会让它们在主键上撞车，
  -- 后写的那条变成 UPDATE 前一条，静默少行且每次同步来回翻。
  record_id            VARCHAR(32) COLLATE utf8mb4_bin NOT NULL
                       COMMENT '飞书记录ID，表内唯一且稳定，作为增量更新的主键；大小写敏感',
  reg_date             DATE         NULL     COMMENT '飞书字段「登记日期」；批次标识，每周三一批。实测全表有419条为空',
  shop                 VARCHAR(128) NULL     COMMENT '飞书字段「店铺」',
  evaluate_date        VARCHAR(32)  NULL     COMMENT '飞书字段「评估日期」；飞书侧是文本不是日期，原样存',
  item_id              VARCHAR(32)  NULL     COMMENT '飞书字段「物品编号」；eBay ItemID',
  title                VARCHAR(255) NULL     COMMENT '飞书字段「刊登标题」；实测最长80字符',
  listing_status       VARCHAR(8)   NULL     COMMENT '飞书字段「刊登状态：Y=在线，N=已下线」；单选',
  sku                  VARCHAR(64)  NULL     COMMENT '飞书字段「SKU」',
  total_amount         VARCHAR(32)  NULL     COMMENT '飞书字段「总交易额」；飞书侧是文本，算数时CAST',
  total_qty            VARCHAR(16)  NULL     COMMENT '飞书字段「总交易量」；飞书侧是文本',
  defect_qty           VARCHAR(16)  NULL     COMMENT '飞书字段「不良交易量」；飞书侧是文本',
  inr_qty              VARCHAR(16)  NULL     COMMENT '飞书字段「物品未收到纠纷数量」；飞书侧是文本',
  snad_qty             VARCHAR(16)  NULL     COMMENT '飞书字段「物品与描述不符退货数量」；飞书侧是文本',
  neutral_negative_qty VARCHAR(16)  NULL     COMMENT '飞书字段「中差评数量」；飞书侧是文本',
  low_dsr_qty          VARCHAR(16)  NULL     COMMENT '飞书字段「物品描述评分低分数量」；飞书侧是文本',
  oos_cancel_qty       VARCHAR(16)  NULL     COMMENT '飞书字段「因缺货而取消的交易数量」；飞书侧是文本',
  defect_rate          VARCHAR(16)  NULL     COMMENT '飞书字段「不良交易率」；飞书侧是文本，算数时CAST',
  parent_json          JSON         NULL     COMMENT '飞书字段「父记录」，关联类型原样存；全表仅79条有值',
  spare_date_1         DATE         NULL     COMMENT '飞书字段「字段 1」；日期型占位列，全表仅4条有值',
  spare_date_2         DATE         NULL     COMMENT '飞书字段「字段 2」；日期型占位列，全表仅4条有值',
  spare_date_3         DATE         NULL     COMMENT '飞书字段「字段 3」；日期型占位列，全表仅4条有值',
  spare_text_4         VARCHAR(64)  NULL     COMMENT '飞书字段「字段 4」；文本占位列，全表仅2条有值',
  spare_text_5         VARCHAR(64)  NULL     COMMENT '飞书字段「字段 5」；文本占位列，全表仅2条有值',
  spare_text_6         VARCHAR(64)  NULL     COMMENT '飞书字段「字段 6」；文本占位列，全表仅1条有值',
  spare_text_7         VARCHAR(64)  NULL     COMMENT '飞书字段「字段 7」；文本占位列，全表仅1条有值',
  spare_text_8         VARCHAR(64)  NULL     COMMENT '飞书字段「字段 8」；文本占位列，全表仅4条有值',
  feishu_created_at    DATETIME     NULL     COMMENT '飞书记录创建时间，取自接口automatic_fields，北京时间',
  feishu_updated_at    DATETIME     NULL     COMMENT '飞书记录最后更新时间，同上；表里没有可见的更新时间字段，判断有没有变只能靠它',
  content_hash         CHAR(64)     NOT NULL COMMENT '业务字段的SHA256指纹；与库里一致就跳过写入，用来区分"更新"和"没变"',
  first_synced_at      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '本行首次同步进来的时间',
  last_synced_at       DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '最后一次被同步看到的时间；即使内容没变也会更新',
  last_changed_at      DATETIME     NULL     COMMENT '最后一次内容真正发生变化的时间；内容没变时不动',
  PRIMARY KEY (record_id),
  -- 按批次查是主要用法：某一周的不良交易刊登。
  KEY idx_reg_date (reg_date),
  KEY idx_shop_reg (shop, reg_date),
  KEY idx_sku (sku),
  KEY idx_item (item_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='飞书多维表格「不良交易刊登」本地副本；按飞书record_id增量upsert，每周三更新一批';


-- ============================================================================
-- 已经按旧定义建过表的话，补执行这一条把主键改成大小写敏感。
-- 改完必须重跑一次全量回填，把之前被大小写撞掉的行补回来。
-- 表是新建的（CREATE TABLE IF NOT EXISTS 刚生效）则本条无副作用。
-- ============================================================================
ALTER TABLE ods_feishu_bad_transaction_listing
  MODIFY COLUMN record_id VARCHAR(32) COLLATE utf8mb4_bin NOT NULL
    COMMENT '飞书记录ID，表内唯一且稳定，作为增量更新的主键；大小写敏感';


-- 同步任务登记。cron 每周三 18:00（北京时间），业务方周三更新完之后再拉。
-- 真正的触发由 Java 侧 Quartz 负责（见 deploy/feishu-bad-transaction/），
-- 这里登记的是 Python 侧的任务目录，两边的 cron 要保持一致。
INSERT INTO scheduler_task(task_code,task_name,cron_expression,enabled,description)
VALUES('feishu_bad_transaction_sync','飞书不良交易刊登每周同步','0 0 18 ? * WED',1,
 '每周三北京时间18:00。默认只拉飞书视图vewohlM1T4那一批（当周约370条），'
 '按record_id增量upsert，内容未变的行不写。全量回填用 scripts/feishu_bad_transaction_backfill.py。')
ON DUPLICATE KEY UPDATE task_name=VALUES(task_name),cron_expression=VALUES(cron_expression),
                        description=VALUES(description);


-- ============================================================================
-- 只读验证（首次同步之后执行）
-- ============================================================================

-- 总量与批次分布；预期每个登记日期 350~490 条
SELECT COUNT(*) AS 总行数, COUNT(DISTINCT reg_date) AS 批次数,
       MIN(reg_date) AS 最早批次, MAX(reg_date) AS 最晚批次,
       SUM(reg_date IS NULL) AS 无登记日期的行
FROM ods_feishu_bad_transaction_listing;

SELECT reg_date AS 登记日期, COUNT(*) AS 行数, COUNT(DISTINCT shop) AS 店铺数,
       MAX(last_synced_at) AS 最后同步
FROM ods_feishu_bad_transaction_listing
GROUP BY reg_date ORDER BY reg_date DESC LIMIT 10;

-- 主键没重复（应无结果）
SELECT record_id, COUNT(*) FROM ods_feishu_bad_transaction_listing
GROUP BY record_id HAVING COUNT(*) > 1 LIMIT 5;

-- 文本列里存的数字能不能算：抽最新一批看不良交易率分布
SELECT reg_date AS 登记日期, COUNT(*) AS 行数,
       ROUND(AVG(CAST(NULLIF(defect_rate,'') AS DECIMAL(10,6))),4) AS 平均不良交易率,
       SUM(CAST(NULLIF(defect_qty,'') AS UNSIGNED)) AS 不良交易量合计
FROM ods_feishu_bad_transaction_listing
WHERE reg_date = (SELECT MAX(reg_date) FROM ods_feishu_bad_transaction_listing)
GROUP BY reg_date;

-- ============================================================================
-- 第2步 按月×店铺×SKU 的汇总表
-- ============================================================================
CREATE TABLE IF NOT EXISTS dws_ebay_sku_unit_price (
  stat_month     CHAR(7)        NOT NULL COMMENT '统计月份YYYY-MM，取自来源批次登记日期的年月',
  shop           VARCHAR(128)   NOT NULL COMMENT '店铺，取自源表「店铺」；同一SKU不同店铺单价不同，必须分开',
  sku            VARCHAR(64)    NOT NULL COMMENT 'SKU，取自源表「SKU」',
  reg_date       DATE           NOT NULL COMMENT '来源批次：该统计月份内最大的登记日期',
  listing_count  INT UNSIGNED   NOT NULL COMMENT '该店铺该SKU在这一批里有几个刊登（物品编号）；>1时按合计额除合计量',
  total_amount   DECIMAL(20,6)  NOT NULL COMMENT '汇总总交易额，美元，源表本身就是美元不换汇',
  total_qty      DECIMAL(20,6)  NOT NULL COMMENT '汇总总交易量',
  defect_qty     DECIMAL(20,6)  NOT NULL COMMENT '汇总不良交易量，用于产品结构的不良交易率',
  unit_price     DECIMAL(20,6)  NOT NULL COMMENT '单价=总交易额/总交易量，美元；总交易量为0的不入表',
  tier_no        TINYINT UNSIGNED NOT NULL COMMENT '美元七档序号1至7：界限5/20/50/100/200/500，区间左闭右开',
  computed_at    DATETIME       NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '本行计算时间',
  PRIMARY KEY (stat_month, shop, sku),
  -- 价格结构按店铺+档位统计SKU占比；产品结构按月+档位汇总不良交易率。
  KEY idx_month_tier (stat_month, tier_no),
  KEY idx_month_shop (stat_month, shop),
  KEY idx_sku (sku)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='eBay SKU美元单价（按月×店铺×SKU），由飞书不良交易刊登表的成交额/成交量算出；金额已是美元不换汇';


-- ============================================================================
-- 只读验证（首次计算之后执行）
-- ============================================================================

-- 覆盖了哪些月份，每月多少店铺/SKU
SELECT stat_month AS 统计月份, MAX(reg_date) AS 来源批次, COUNT(*) AS 店铺SKU数,
       COUNT(DISTINCT shop) AS 店铺数, COUNT(DISTINCT sku) AS 去重SKU数,
       MAX(computed_at) AS 计算时间
FROM dws_ebay_sku_unit_price GROUP BY stat_month ORDER BY stat_month DESC;

-- 同一SKU在不同店铺确实是不同单价（示例）
SELECT stat_month AS 统计月份, sku, shop AS 店铺, total_amount AS 总交易额,
       total_qty AS 总交易量, unit_price AS 单价, tier_no AS 档位
FROM dws_ebay_sku_unit_price
WHERE sku = 'FRD-70361-4-0734' ORDER BY stat_month DESC, shop;

-- 最新月份的档位分布（价格结构图的数据）
SELECT tier_no AS 档位, COUNT(*) AS 店铺SKU数,
       ROUND(MIN(unit_price),2) AS 最低单价, ROUND(MAX(unit_price),2) AS 最高单价
FROM dws_ebay_sku_unit_price
WHERE stat_month = (SELECT MAX(stat_month) FROM dws_ebay_sku_unit_price)
GROUP BY tier_no ORDER BY tier_no;

-- 各月各档位的不良交易率（产品结构图的数据）
SELECT stat_month AS 统计月份, tier_no AS 档位,
       SUM(total_qty) AS 总交易量, SUM(defect_qty) AS 不良交易量,
       ROUND(SUM(defect_qty)/NULLIF(SUM(total_qty),0),4) AS 不良交易率
FROM dws_ebay_sku_unit_price
GROUP BY stat_month, tier_no ORDER BY stat_month DESC, tier_no LIMIT 21;

-- ============================================================================
-- 第3步【只读】验收
--
-- 两张表都该在。行数为 0 是正常的——要等每周三的同步任务拉数据，
-- 或者在首页「EBAY · 美元价格结构」点一次刷新（刷新会重算汇总表，
-- 但贴源表仍需同步任务去拉）。
-- ============================================================================
SELECT TABLE_NAME AS 表, TABLE_ROWS AS 估算行数, TABLE_COMMENT AS 说明
FROM information_schema.TABLES
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME IN ('ods_feishu_bad_transaction_listing','dws_ebay_sku_unit_price')
ORDER BY TABLE_NAME;

SELECT task_code AS 任务, task_name, cron_expression, enabled
FROM scheduler_task WHERE task_code = 'feishu_bad_transaction_sync';
