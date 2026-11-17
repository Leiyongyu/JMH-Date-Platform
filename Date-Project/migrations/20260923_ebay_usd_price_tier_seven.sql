-- Python业务库 date-project：eBay美元价格结构由5档改为7档。
--
-- 只改表和列的注释，不动表结构、不动数据：
--   tier_no 本来就是 TINYINT UNSIGNED，没有 CHECK 约束，存 1~7 无需改类型；
--   主键 (platform,node_id,tier_no) 天然容纳新增的第6、7档。
--
-- 旧的5档数据不需要手工清理：summary_json 里的 version 由 3 升到 4，
-- read_report 读到版本不符会直接返回「统计口径已更新，请重新统计」，
-- 页面点一次刷新按钮即按7档整表重建（rebuild 是先删后插）。
--
-- 新档位（左闭右开）：
--   1: [0,5)   2: [5,20)   3: [20,50)   4: [50,100)
--   5: [100,200)   6: [200,500)   7: [500,+∞)
-- 与旧5档不同，7档全部左闭右开，不再有「上界归本档」的特例。
-- 人民币报表 dws_listing_price_tier 不受影响，仍是5档、1690归第四档。

USE `date-project`;
SET NAMES utf8mb4 COLLATE utf8mb4_unicode_ci;

ALTER TABLE dws_ebay_usd_price_tier
  MODIFY COLUMN tier_no TINYINT UNSIGNED NOT NULL
    COMMENT '美元七档1至7，界限5/20/50/100/200/500，区间左闭右开',
  COMMENT='eBay美元七档SKU统计；原价USD直用，其他币种按当月rate_org交叉换算';

ALTER TABLE dws_ebay_usd_price_report
  COMMENT='eBay美元七档价格结构发布状态';


-- 只读验证：应显示「美元七档1至7…」
SELECT COLUMN_NAME AS 列, COLUMN_COMMENT AS 注释
FROM information_schema.COLUMNS
WHERE TABLE_SCHEMA = 'date-project'
  AND TABLE_NAME = 'dws_ebay_usd_price_tier'
  AND COLUMN_NAME = 'tier_no';

-- 只读验证：旧报表的口径版本，应为 3（尚未重新统计）或 4（已按7档重建）
SELECT JSON_UNQUOTE(JSON_EXTRACT(summary_json, '$.version'))         AS 口径版本,
       JSON_UNQUOTE(JSON_EXTRACT(summary_json, '$.target_currency')) AS 统计币种,
       generated_at                                                  AS 生成时间
FROM dws_ebay_usd_price_report WHERE platform = 'ebay';

-- 只读验证：当前落库的档位序号分布。重新统计前是 1~5，之后应为 1~7。
SELECT tier_no AS 档位, COUNT(*) AS 节点数
FROM dws_ebay_usd_price_tier WHERE platform = 'ebay'
GROUP BY tier_no ORDER BY tier_no;
