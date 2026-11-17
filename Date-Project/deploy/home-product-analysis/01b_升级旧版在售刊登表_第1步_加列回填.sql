-- ============================================================================
-- 【只有旧库需要】把 2026-09-18 版的在售刊登表升级成按月累积的结构 · 第1步
--
-- 在 Python 业务库 date-project 执行。可重复执行。
--
-- ----------------------------------------------------------------------------
-- 为什么需要这一步
-- ----------------------------------------------------------------------------
-- 01 对已存在的表只做 CREATE TABLE IF NOT EXISTS，不会升级旧表结构。
-- 2026-09-18 建的那版表是「每次同步整表覆盖、只留最新一份」，没有 stat_month；
-- 变体数组埋在 normalized_json 里，没有单独的 variations_json。
-- 新代码按月累积、按 variations_json 拆变体，所以旧表必须先升级。
--
-- 旧表还有五个 NOT NULL 且无默认值的列：raw_xml、response_meta_json、
-- normalized_json、source_page、api_total。新版同步代码不再写这些列，
-- 留着它们的话**下一次同步会直接报 1364 字段没有默认值**，所以第2步必须删掉。
--
-- ----------------------------------------------------------------------------
-- 这一步做什么（全部是"只增不减"，随时可以停下）
-- ----------------------------------------------------------------------------
--   1. 加 stat_month、variations_json 两列
--   2. 从 pulled_at 回填月份，从 normalized_json 抽出变体数组
--   3. 给 state 表加 stat_month 并回填
--   4. 【闸门】核对变体一条没丢
--
-- 旧列一个都不删、唯一键一个都不动，所以这一步失败了直接重跑即可。
-- 删列和换唯一键在 01c，**必须等这里的闸门全是 0 才能执行**。
--
-- ⚠️ 执行前确认已有数据库备份。
-- ============================================================================

USE `date-project`;
SET NAMES utf8mb4 COLLATE utf8mb4_unicode_ci;
SET @db = DATABASE();
SET SESSION group_concat_max_len = 65535;


-- ============================================================================
-- 第0步【只读】判断这台机器要不要跑本脚本
--
-- 「结论」那一列：
--   需要升级       → 继续往下执行
--   已是新结构     → 本脚本无事可做，直接跳到 01c 看一眼（它也会跳过），或直接跑 03
--   表不存在       → 先跑 01，它会按新结构建出来，然后跳过 01b/01c
-- ============================================================================
SELECT VERSION() AS MySQL版本;

SELECT
  IF(NOT EXISTS(SELECT 1 FROM information_schema.TABLES
                WHERE TABLE_SCHEMA=@db AND TABLE_NAME='ods_ebay_store_listing_latest'),
     '表不存在 → 先跑 01 建表，本脚本与 01c 都不用执行',
     IF(EXISTS(SELECT 1 FROM information_schema.COLUMNS
               WHERE TABLE_SCHEMA=@db AND TABLE_NAME='ods_ebay_store_listing_latest'
                 AND COLUMN_NAME='normalized_json'),
        '需要升级 → 执行本脚本，闸门通过后再执行 01c',
        IF(EXISTS(SELECT 1 FROM information_schema.COLUMNS
                  WHERE TABLE_SCHEMA=@db AND TABLE_NAME='ods_ebay_store_listing_latest'
                    AND COLUMN_NAME='stat_month'),
           '已是新结构 → 本脚本无事可做',
           '结构异常 → 既没有 normalized_json 也没有 stat_month，停下来人工确认')
     )) AS 结论;

-- 现有列一览，对照着看
SELECT GROUP_CONCAT(COLUMN_NAME ORDER BY ORDINAL_POSITION) AS 现有列
FROM information_schema.COLUMNS
WHERE TABLE_SCHEMA=@db AND TABLE_NAME='ods_ebay_store_listing_latest';


-- ============================================================================
-- 第1步【只读】记下改造前的底数，第4步闸门要拿它比对
--
-- 把这三个数记下来：行数、带变体的刊登数、变体总数。
-- （开发机实测：18076 行 / 43 个带变体 / 141 个变体。部署机的数会不一样。）
--
-- 「单条最多几个变体」若 > 20，**停下来告诉我**：下面回填用的 JSON_REMOVE
-- 只铺了 20 个槽位，超过的变体身上会残留 raw_xml，白占空间。
-- ============================================================================
-- 已经升级过的库里没有 normalized_json，这段要改从 variations_json 取，
-- 否则重复执行会 1054。整份脚本必须任何时候都能重跑。
SET @has_norm = EXISTS(SELECT 1 FROM information_schema.COLUMNS
                       WHERE TABLE_SCHEMA=@db AND TABLE_NAME='ods_ebay_store_listing_latest'
                         AND COLUMN_NAME='normalized_json');
SET @src = IF(@has_norm, 'JSON_EXTRACT(normalized_json,''$.variations'')', 'variations_json');
SET @sql = CONCAT(
  'SELECT COUNT(*) AS 行数,',
  ' COUNT(DISTINCT seller_user_id) AS 账号数,',
  ' DATE_FORMAT(MIN(pulled_at),''%Y-%m-%d'') AS 最早拉取,',
  ' DATE_FORMAT(MAX(pulled_at),''%Y-%m-%d'') AS 最晚拉取,',
  ' COUNT(DISTINCT DATE_FORMAT(pulled_at,''%Y-%m'')) AS 涉及月份数,',
  ' SUM(JSON_LENGTH(', @src, ')>0) AS 带变体的刊登数,',
  ' SUM(COALESCE(JSON_LENGTH(', @src, '),0)) AS 变体总数,',
  ' MAX(COALESCE(JSON_LENGTH(', @src, '),0)) AS 单条最多几个变体,',
  ' ''', IF(@has_norm,'旧结构，需要升级','已升级，本脚本后续会全部跳过'), ''' AS 结构',
  ' FROM ods_ebay_store_listing_latest');
PREPARE s FROM @sql; EXECUTE s; DEALLOCATE PREPARE s;


-- ============================================================================
-- 第2步 加列（已经有了就跳过）
-- ============================================================================
SET @sql = IF(EXISTS(SELECT 1 FROM information_schema.COLUMNS
                     WHERE TABLE_SCHEMA=@db AND TABLE_NAME='ods_ebay_store_listing_latest'
                       AND COLUMN_NAME='stat_month'),
  'DO 0',
  'ALTER TABLE ods_ebay_store_listing_latest ADD COLUMN stat_month CHAR(7) NULL COMMENT ''留档月份YYYY-MM，取自pulled_at的北京时间月份，不是接口月份'' AFTER id');
PREPARE s FROM @sql; EXECUTE s; DEALLOCATE PREPARE s;

SET @sql = IF(EXISTS(SELECT 1 FROM information_schema.COLUMNS
                     WHERE TABLE_SCHEMA=@db AND TABLE_NAME='ods_ebay_store_listing_latest'
                       AND COLUMN_NAME='variations_json'),
  'DO 0',
  'ALTER TABLE ods_ebay_store_listing_latest ADD COLUMN variations_json JSON NULL COMMENT ''多规格变体数组，每项含sku/price/quantity/quantity_sold，已剥除变体raw_xml；无变体为NULL。统计多规格刊登必须按本列逐变体计，不能用父级sku/current_price'' AFTER image_url');
PREPARE s FROM @sql; EXECUTE s; DEALLOCATE PREPARE s;

SET @sql = IF(EXISTS(SELECT 1 FROM information_schema.COLUMNS
                     WHERE TABLE_SCHEMA=@db AND TABLE_NAME='ods_ebay_store_listing_state'
                       AND COLUMN_NAME='stat_month'),
  'DO 0',
  'ALTER TABLE ods_ebay_store_listing_state ADD COLUMN stat_month CHAR(7) NULL COMMENT ''留档月份YYYY-MM'' FIRST');
PREPARE s FROM @sql; EXECUTE s; DEALLOCATE PREPARE s;


-- ============================================================================
-- 第3步 回填
--
-- 月份取自 pulled_at 而不是当前日期：这批数据本来就属于它被拉下来的那个月。
--
-- 变体只留数组本身，并逐个剥掉变体自己的 raw_xml。JSON_REMOVE 会忽略不存在的
-- 路径，所以铺 20 个槽位对只有 5 个变体的行也安全；超过 20 个的由第1步揪出来。
-- 无变体存 NULL 而不是空数组，统计时好直接判空。
--
-- 只回填还没填的行，重复执行不会重算已经填好的。
-- ============================================================================
SET @sql = IF(NOT EXISTS(SELECT 1 FROM information_schema.COLUMNS
                         WHERE TABLE_SCHEMA=@db AND TABLE_NAME='ods_ebay_store_listing_latest'
                           AND COLUMN_NAME='normalized_json'),
  'DO 0',
  'UPDATE ods_ebay_store_listing_latest
      SET stat_month = DATE_FORMAT(pulled_at,''%Y-%m''),
          variations_json = CASE WHEN JSON_LENGTH(JSON_EXTRACT(normalized_json,''$.variations'')) > 0
              THEN JSON_REMOVE(JSON_EXTRACT(normalized_json,''$.variations''),
                   ''$[0].raw_xml'',''$[1].raw_xml'',''$[2].raw_xml'',''$[3].raw_xml'',''$[4].raw_xml'',
                   ''$[5].raw_xml'',''$[6].raw_xml'',''$[7].raw_xml'',''$[8].raw_xml'',''$[9].raw_xml'',
                   ''$[10].raw_xml'',''$[11].raw_xml'',''$[12].raw_xml'',''$[13].raw_xml'',''$[14].raw_xml'',
                   ''$[15].raw_xml'',''$[16].raw_xml'',''$[17].raw_xml'',''$[18].raw_xml'',''$[19].raw_xml'')
              ELSE NULL END
    WHERE stat_month IS NULL');
PREPARE s FROM @sql; EXECUTE s; DEALLOCATE PREPARE s;

UPDATE ods_ebay_store_listing_state
SET stat_month = DATE_FORMAT(pulled_at,'%Y-%m')
WHERE stat_month IS NULL;


-- ============================================================================
-- 第4步【闸门 · 只读】五个数必须全是 0
--
-- ⚠️ 只要有一个不是 0：**停下来，不要执行 01c**，把这张结果表发回来。
--    此时旧列 normalized_json 还原封不动，重跑本脚本或人工修正都来得及。
--    一旦跑了 01c 删掉 normalized_json，变体就只能从备份里恢复了。
--
-- 逐列含义：
--   变体数对不上   回填出来的变体个数 ≠ 原 normalized_json 里的个数
--   还带rawxml     变体身上的 raw_xml 没剥干净（多半是变体超过20个）
--   空数组占位     有变体却存成了 []，应当是 NULL
--   月份没填上     stat_month 还是 NULL
--   state月份没填  状态表的 stat_month 还是 NULL
-- ============================================================================
-- 旧列已经删掉时「变体数对不上」没法比，那一列返回 0 并注明；
-- 其余三项与旧列无关，照常检查。
SET @sql = CONCAT(
  'SELECT ',
  IF(@has_norm,
     'SUM(COALESCE(JSON_LENGTH(JSON_EXTRACT(normalized_json,''$.variations'')),0)'
     ' <> COALESCE(JSON_LENGTH(variations_json),0))',
     '0'), ' AS 变体数对不上_应为0,',
  ' SUM(JSON_SEARCH(variations_json,''one'',''%'',NULL,''$[*].raw_xml'') IS NOT NULL)'
  ' AS 还带rawxml_应为0,',
  ' SUM(variations_json IS NOT NULL AND JSON_LENGTH(variations_json)=0)'
  ' AS 空数组占位_应为0,',
  ' SUM(stat_month IS NULL) AS 月份没填上_应为0,',
  ' ''', IF(@has_norm,'已与旧列逐行比对','旧列已删，变体数无法再比对（升级时已比过）'), ''' AS 比对说明',
  ' FROM ods_ebay_store_listing_latest');
PREPARE s FROM @sql; EXECUTE s; DEALLOCATE PREPARE s;

SELECT SUM(stat_month IS NULL) AS state月份没填上_应为0 FROM ods_ebay_store_listing_state;


-- ============================================================================
-- 第5步【只读】回填结果概览，和第1步的底数对一下
--
-- 「带变体的刊登数」「变体总数」必须与第1步完全相同。
-- 月份通常只有一个（旧表是整表覆盖式的，只留最新一份）。
-- ============================================================================
SELECT stat_month AS 月份, COUNT(*) AS 行数,
       COUNT(DISTINCT seller_user_id) AS 账号数,
       SUM(variations_json IS NOT NULL) AS 带变体的刊登数,
       SUM(COALESCE(JSON_LENGTH(variations_json),0)) AS 变体总数
FROM ods_ebay_store_listing_latest
GROUP BY stat_month ORDER BY stat_month;

-- 同一个(月份,账号,ItemID)有没有重复？01c 要把它建成唯一键，有重复会建不上。
-- 预期：返回空结果。有行返回就停下来，把结果发回来。
SELECT stat_month, seller_user_id, item_id, COUNT(*) AS 条数
FROM ods_ebay_store_listing_latest
GROUP BY stat_month, seller_user_id, item_id HAVING COUNT(*) > 1
LIMIT 20;

-- state 表同理：01c 要把 (月份,账号) 建成主键
SELECT stat_month, seller_user_id, COUNT(*) AS 条数
FROM ods_ebay_store_listing_state
GROUP BY stat_month, seller_user_id HAVING COUNT(*) > 1
LIMIT 20;


-- ============================================================================
-- 确认第4步五个数全是 0、第5步两段都返回空结果之后，再执行
--   01c_升级旧版在售刊登表_第2步_删旧列换唯一键.sql
-- ============================================================================
