-- Python业务库 date-project：eBay SKU 美元单价表（按月）。
--
-- 来源：ods_feishu_bad_transaction_listing（飞书「不良交易刊登」，每周三更新）。
-- 口径：每个统计月份取该月**最大的登记日期**那一批，按 店铺+SKU 聚合，
--       单价 = SUM(总交易额) / SUM(总交易量)。
--
-- 为什么按店铺分：同一个SKU在不同店铺售价不同。实测 FRD-70361-4-0734 在
-- 三个店铺分别是 23.32 / 19.99 / 26.00 美元，19.99 和 23.32 分属「5-20」
-- 和「20-50」两个档，不分店铺就会算错。
--
-- 为什么不换汇：这张源表的金额本来就是美元，再乘汇率是错的。
--
-- 覆盖策略：主键含 stat_month，同月重复计算直接覆盖。源表每周三更新一次，
-- 所以同一个月内会被覆盖 4~5 次，始终是该月最新那一批的口径。
--
-- 口径提醒（页面上也要写）：源表只收录**有不良交易的刊登**，不是全部在售。
-- 实测最新一批 291 个SKU / 35 个店铺，而 eBay 在售表有 2016 个SKU / 37 个店铺。
-- 所以这张表算出来的价格结构是「有不良交易的刊登」的价格结构，
-- 不良交易率的分母也只含这些刊登的交易（实测 15~18%，不能与 eBay 官方面板对数）。

USE `date-project`;
SET NAMES utf8mb4 COLLATE utf8mb4_unicode_ci;

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
