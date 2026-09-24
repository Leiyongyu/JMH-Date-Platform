"""eBay 在售刊登价格分层：ODS -> DWD -> DWS 三层加工。

    ods_ebay_store_listing_latest   每月5日从 Trading 接口拉回来的在售刊登（原样）
         │ build_dwd  拆变体、去空SKU/空站点、价格转数值、站点与币种标准化
         ▼
    dwd_ebay_listing_sku            一行 = 一个可分档的「刊登SKU」，仍是原币
         │ build_dws  按 dim_lingxing_currency_month.rate_org 换美元，落七档
         ▼
    dws_ebay_listing_price_tier     一行 = 月×店铺×站点×SKU 的美元价与档位

分层不是为了好看：出了问题要能一层层往回对。DWD 只有清洗、没有汇率，
所以"是不是拆错了变体"可以直接拿它和 eBay 后台逐条比；DWS 存了每行实际
用的 rate_org 和汇率月份，所以"为什么这个SKU落在这一档"也能当场算回去。

换汇口径：美元价 = 原币价 × rate_org(原币) ÷ rate_org(USD)。
两个汇率都取「不晚于统计月份、且该字段有正值」的最新一个月——九月的刊登
用九月的汇率，不用今天的汇率；当月还没同步汇率时才回退到上一个有值的月份。
USD 原币直接短路，一步汇率都不经过。
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from fractions import Fraction
from uuid import uuid4

from backend.database import db_connection
from backend.services import listing_price_tier_service as engine

ODS_TABLE = "ods_ebay_store_listing_latest"
ODS_STATE_TABLE = "ods_ebay_store_listing_state"
DWD_TABLE = "dwd_ebay_listing_sku"
DWS_TABLE = "dws_ebay_listing_price_tier"
STATE_TABLE = "dws_ebay_listing_price_state"
RATE_TABLE = "dim_lingxing_currency_month"
RATE_FIELD = "rate_org"
_BATCH_SIZE = 1000

# 价格文本必须是纯十进制正数才认。ODS 存的是接口原文，不做转换也不补零，
# 所以这里是第一道也是唯一一道数值校验。
_PRICE_OK = r"^[0-9]+(\.[0-9]+)?$"

# 两个来源合成一份「候选行」：没有变体的刊登用父级那行，有变体的按变体逐个展开。
# 过滤条件和丢弃计数都基于同一段 SQL，不各写一份——两边写法一旦分叉，
# 「丢了多少行」报的就不是实际丢的那些行。
#
# 各列显式 COLLATE：ODS 是 utf8mb4_bin，JSON_TABLE 取出来的是另一套排序规则，
# UNION ALL 不指定会直接报 1271 混合排序规则。
_CANDIDATES_CTE = f"""
WITH candidates AS (
    SELECT l.stat_month, l.seller_user_id, l.seller_account, l.item_id,
           0 AS variation_no,
           CAST(l.sku AS CHAR(255)) COLLATE utf8mb4_unicode_ci      AS raw_sku,
           CAST(l.site AS CHAR(16)) COLLATE utf8mb4_unicode_ci      AS raw_site,
           CAST(l.currency AS CHAR(16)) COLLATE utf8mb4_unicode_ci  AS raw_currency,
           CAST(l.current_price AS CHAR(64)) COLLATE utf8mb4_unicode_ci AS raw_price,
           CAST(l.quantity AS SIGNED) AS quantity,
           CAST(l.quantity_sold AS SIGNED) AS quantity_sold,
           0 AS is_variation
    FROM {ODS_TABLE} l
    WHERE l.stat_month = %s AND l.variations_json IS NULL
    UNION ALL
    -- 多规格刊登：父级那行的 sku/current_price 只是第一个变体的值，
    -- 拿它代表整条刊登会把 N 个SKU塌缩成 1 个，且价格分档会错。
    SELECT l.stat_month, l.seller_user_id, l.seller_account, l.item_id,
           jt.variation_no,
           CAST(jt.sku AS CHAR(255)) COLLATE utf8mb4_unicode_ci     AS raw_sku,
           CAST(l.site AS CHAR(16)) COLLATE utf8mb4_unicode_ci      AS raw_site,
           CAST(COALESCE(jt.currency, l.currency) AS CHAR(16)) COLLATE utf8mb4_unicode_ci AS raw_currency,
           CAST(jt.price_value AS CHAR(64)) COLLATE utf8mb4_unicode_ci AS raw_price,
           jt.quantity, jt.quantity_sold,
           1 AS is_variation
    FROM {ODS_TABLE} l,
         JSON_TABLE(l.variations_json, '$[*]' COLUMNS(
             variation_no FOR ORDINALITY,
             sku          VARCHAR(255) PATH '$.sku',
             price_value  VARCHAR(64)  PATH '$.price.value',
             currency     VARCHAR(16)  PATH '$.price.currency',
             quantity     BIGINT       PATH '$.quantity',
             quantity_sold BIGINT      PATH '$.quantity_sold')) jt
    WHERE l.stat_month = %s AND l.variations_json IS NOT NULL
)
"""

# 干净行的判定。三个条件互相独立，所以下面的丢弃计数可以分别归因。
_CLEAN_WHERE = (
    "raw_sku IS NOT NULL AND TRIM(raw_sku) <> '' "
    "AND raw_site IS NOT NULL AND TRIM(raw_site) <> '' "
    "AND raw_currency IS NOT NULL AND TRIM(raw_currency) <> '' "
    f"AND raw_price REGEXP '{_PRICE_OK}' "
    "AND CAST(TRIM(raw_price) AS DECIMAL(20,6)) > 0"
)

_DWD_COLUMNS = ("stat_month", "seller_user_id", "seller_account", "item_id", "variation_no",
                "sku", "site", "currency", "price_original", "quantity", "quantity_sold",
                "is_variation", "etl_batch_id", "computed_at")

# MySQL 只接受 INSERT INTO t (列) WITH cte AS (...) SELECT，
# 不接受把 WITH 写在 INSERT 前面（那是 PostgreSQL 的写法，这里会直接1064）。
_INSERT_DWD = f"""
INSERT INTO {DWD_TABLE} ({','.join(_DWD_COLUMNS)})
{_CANDIDATES_CTE}
SELECT stat_month, seller_user_id, seller_account, item_id, variation_no,
       TRIM(raw_sku), UPPER(TRIM(raw_site)), UPPER(TRIM(raw_currency)),
       CAST(TRIM(raw_price) AS DECIMAL(20,6)),
       quantity, quantity_sold, is_variation, %s, %s
FROM candidates
WHERE {_CLEAN_WHERE}
"""

# 丢弃归因：一行可能同时缺SKU又缺站点，各自计各自的，所以三个数相加
# 可能大于实际丢弃行数。要的是"哪类问题有多少"，不是互斥分桶。
_COUNT_CANDIDATES = f"""
{_CANDIDATES_CTE}
SELECT COUNT(*) AS total,
       SUM(raw_sku IS NULL OR TRIM(raw_sku) = '')            AS no_sku,
       SUM(raw_site IS NULL OR TRIM(raw_site) = '')          AS no_site,
       SUM(raw_currency IS NULL OR TRIM(raw_currency) = ''
           OR raw_price NOT REGEXP '{_PRICE_OK}'
           OR CAST(TRIM(COALESCE(raw_price,'0')) AS DECIMAL(20,6)) <= 0) AS bad_price
FROM candidates
"""


def ods_months(cursor):
    """ODS 里有哪些留档月份，旧到新。"""
    cursor.execute(f"SELECT DISTINCT stat_month FROM {ODS_TABLE} ORDER BY stat_month")
    return [row["stat_month"] for row in cursor.fetchall()]


def rates_for(cursor, stat_month):
    """该统计月份每个币种应当使用的 rate_org 及其实际来源月份。

    每个币种各自回退：当月没同步汇率时退到该币种最近一个有正值的月份，
    不取未来月份——预先录入的下月汇率此刻尚未生效。
    (rate_month,currency_code) 唯一，同币种同月不会有第二行。
    """
    cursor.execute(
        f"""SELECT c.currency_code, c.rate_month, c.{RATE_FIELD} AS rate
            FROM {RATE_TABLE} c
            WHERE c.rate_month <= %s AND c.{RATE_FIELD} IS NOT NULL AND c.{RATE_FIELD} > 0
              AND c.rate_month = (SELECT MAX(x.rate_month) FROM {RATE_TABLE} x
                                  WHERE x.currency_code = c.currency_code
                                    AND x.rate_month <= %s
                                    AND x.{RATE_FIELD} IS NOT NULL AND x.{RATE_FIELD} > 0)""",
        (stat_month, stat_month))
    return {str(row["currency_code"]).strip().upper():
            (Decimal(str(row["rate"])), row["rate_month"]) for row in cursor.fetchall()}


def build_dwd(cursor, stat_month, batch_id, computed_at):
    """ODS -> DWD：拆变体、清洗。先删该月旧行，再整月重建。

    只动这一个月：别的月份的清洗结果一行不碰，补跑某个月不会牵连其他月。
    """
    cursor.execute(f"SELECT COUNT(*) AS n, MAX(pulled_at) AS pulled_at "
                   f"FROM {ODS_TABLE} WHERE stat_month=%s", (stat_month,))
    source = cursor.fetchone() or {}
    cursor.execute(_COUNT_CANDIDATES, (stat_month, stat_month))
    audit = cursor.fetchone() or {}
    cursor.execute(f"DELETE FROM {DWD_TABLE} WHERE stat_month=%s", (stat_month,))
    cursor.execute(_INSERT_DWD, (stat_month, stat_month, batch_id, computed_at))
    written = cursor.rowcount
    expected = int(audit.get("total") or 0)
    dropped = {key: int(audit.get(key) or 0) for key in ("no_sku", "no_site", "bad_price")}
    # 写进去多少必须能对上：候选总数减去被过滤掉的，剩下的就该是写入行数。
    # 对不上多半是唯一键把两行合成了一行（同一刊登的两个变体SKU只差大小写），
    # 那属于静默少行，当场拦住而不是等人来对数。
    cursor.execute(f"SELECT COUNT(*) AS n FROM {DWD_TABLE} WHERE stat_month=%s", (stat_month,))
    stored = int((cursor.fetchone() or {}).get("n") or 0)
    if stored != written:
        raise ValueError(f"{stat_month} 清洗层写入行数校验失败：本次写{written}行，"
                         f"库里只有{stored}行；多半是(月份,账号,ItemID,变体序号)撞了唯一键。已回滚。")
    return dict(ods_rows=int(source.get("n") or 0), candidate_rows=expected,
                dwd_rows=written, source_pulled_at=source.get("pulled_at"),
                dropped_no_sku=dropped["no_sku"], dropped_no_site=dropped["no_site"],
                dropped_bad_price=dropped["bad_price"])


def _usd_price(price, currency, rates):
    """原币价 -> 美元价；拿不到汇率返回 None。

    用精确分数而不是先算成小数：原币÷美元几乎必然是无限循环小数，
    提前四舍五入会让刚好压在档位边界上的价格翻档。
    """
    if currency == "USD":
        return Fraction(price), (Decimal(1), ""), (Decimal(1), "")
    usd = rates.get("USD")
    own = rates.get(currency)
    if not usd or not own:
        return None, own, usd
    return Fraction(price) * Fraction(own[0]) / Fraction(usd[0]), own, usd


def build_dws(cursor, stat_month, batch_id, computed_at):
    """DWD -> DWS：换汇、分档，并按 月×店铺×站点×SKU 取最低价合并。

    同一店铺同一站点同一SKU挂多条刊登时只留最低价那条（实测2026-09有1021组）。
    每条都留的话，铺得多的SKU在档位占比里会被重复计。
    """
    rates = rates_for(cursor, stat_month)
    cursor.execute(
        f"SELECT seller_user_id,seller_account,site,sku,currency,price_original "
        f"FROM {DWD_TABLE} WHERE stat_month=%s", (stat_month,))
    best, missing, dropped = {}, set(), 0
    for row in cursor.fetchall():
        currency = str(row["currency"] or "").strip().upper()
        price = Decimal(str(row["price_original"]))
        usd, own, usd_rate = _usd_price(price, currency, rates)
        if usd is None:
            dropped += 1
            if not rates.get(currency):
                missing.add(currency or "未知")
            if not rates.get("USD"):
                missing.add("USD")
            continue
        key = (row["seller_user_id"], row["site"], row["sku"])
        current = best.get(key)
        if current is None or usd < current["usd"]:
            best[key] = dict(
                seller_account=row["seller_account"], usd=usd, currency=currency,
                price_original=price, rate=own[0], rate_month=own[1] or stat_month,
                usd_rate=usd_rate[0], usd_rate_month=usd_rate[1] or stat_month,
                listing_count=(current or {}).get("listing_count", 0) + 1)
        else:
            current["listing_count"] += 1
    columns = ("stat_month", "seller_user_id", "seller_account", "site", "sku", "currency",
               "price_original", "price_usd", "tier_no", "rate_month", "rate_org",
               "usd_rate_month", "usd_rate_org", "listing_count", "computed_at")
    values = []
    for (user_id, site, sku), item in best.items():
        usd = item["usd"]
        values.append((
            stat_month, user_id, item["seller_account"], site, sku, item["currency"],
            item["price_original"],
            # 展示用的美元价截断到8位；分档用的是上面那个精确分数，不受这里影响。
            Decimal(usd.numerator) / Decimal(usd.denominator),
            # 档位只此一处实现，与页面、与飞书单价表共用同一套阈值。
            engine.tier_index(usd, "USD") + 1,
            item["rate_month"], item["rate"], item["usd_rate_month"], item["usd_rate"],
            item["listing_count"], computed_at))
    cursor.execute(f"DELETE FROM {DWS_TABLE} WHERE stat_month=%s", (stat_month,))
    insert = (f"INSERT INTO {DWS_TABLE} ({','.join(columns)}) VALUES ("
              + ",".join(["%s"] * len(columns)) + ")")
    for offset in range(0, len(values), _BATCH_SIZE):
        cursor.executemany(insert, values[offset:offset + _BATCH_SIZE])
    cursor.execute(f"SELECT COUNT(*) AS rows_,COUNT(DISTINCT seller_account) AS shops,"
                   f"COUNT(DISTINCT sku) AS skus FROM {DWS_TABLE} WHERE stat_month=%s",
                   (stat_month,))
    stored = cursor.fetchone() or {}
    if int(stored.get("rows_") or 0) != len(values):
        raise ValueError(f"{stat_month} 汇总层写入行数校验失败：本次{len(values)}行，"
                         f"库里{stored.get('rows_')}行。已回滚。")
    return dict(dws_rows=len(values), dropped_no_rate=dropped,
                missing_currencies=sorted(missing),
                shop_count=int(stored.get("shops") or 0),
                sku_count=int(stored.get("skus") or 0),
                rate_month=(rates.get("USD") or (None, ""))[1] or "")


_STATE_COLUMNS = ("stat_month", "ods_rows", "dwd_rows", "dws_rows", "dropped_no_sku",
                  "dropped_no_site", "dropped_bad_price", "dropped_no_rate",
                  "missing_currencies", "shop_count", "sku_count", "rate_month",
                  "etl_batch_id", "source_pulled_at", "computed_at")


def _write_state(cursor, stat_month, metrics, batch_id, computed_at):
    row = (stat_month, metrics["ods_rows"], metrics["dwd_rows"], metrics["dws_rows"],
           metrics["dropped_no_sku"], metrics["dropped_no_site"], metrics["dropped_bad_price"],
           metrics["dropped_no_rate"], ",".join(metrics["missing_currencies"]),
           metrics["shop_count"], metrics["sku_count"], metrics["rate_month"],
           batch_id, metrics["source_pulled_at"], computed_at)
    cursor.execute(
        f"INSERT INTO {STATE_TABLE} ({','.join(_STATE_COLUMNS)}) VALUES ("
        + ",".join(["%s"] * len(_STATE_COLUMNS)) + ") ON DUPLICATE KEY UPDATE "
        + ",".join(f"{c}=VALUES({c})" for c in _STATE_COLUMNS[1:]), row)


def refresh(months=None):
    """重算这些月份的 DWD 与 DWS。整批一个事务，失败全回滚。

    months 为 None 时算 ODS 里的全部月份。不拉取任何外部接口——
    拉取是每月5日的定时任务干的事，这里只是把已经拉回来的数据重新加工一遍。
    """
    batch_id, computed_at = str(uuid4()), datetime.now().replace(microsecond=0)
    results = []
    with db_connection() as connection:
        try:
            connection.begin()
            with connection.cursor() as cursor:
                targets = list(months) if months else ods_months(cursor)
                for month in targets:
                    metrics = build_dwd(cursor, month, batch_id, computed_at)
                    metrics.update(build_dws(cursor, month, batch_id, computed_at))
                    _write_state(cursor, month, metrics, batch_id, computed_at)
                    results.append(dict(metrics, stat_month=month))
                removed = _drop_orphan_months(cursor, targets) if months is None else 0
            connection.commit()
        except Exception:
            connection.rollback()
            raise
    return dict(batch_id=batch_id, months=[r["stat_month"] for r in results],
                details=results, removed_rows=removed,
                ods_rows=sum(r["ods_rows"] for r in results),
                dwd_rows=sum(r["dwd_rows"] for r in results),
                dws_rows=sum(r["dws_rows"] for r in results),
                missing_currencies=sorted({c for r in results for c in r["missing_currencies"]}))


def _drop_orphan_months(cursor, kept):
    """整表重算时，ODS 里已经不存在的月份从 DWD/DWS/state 里一并清掉。

    按月重建只覆盖算过的月份，管不到「整个月份的源数据被删了」这种情况，
    不清的话月份选择器里会一直挂着一个查不出数的月份。
    """
    removed = 0
    for table in (DWD_TABLE, DWS_TABLE, STATE_TABLE):
        if kept:
            placeholders = ",".join(["%s"] * len(kept))
            cursor.execute(f"DELETE FROM {table} WHERE stat_month NOT IN ({placeholders})", kept)
        else:
            cursor.execute(f"DELETE FROM {table}")
        removed += cursor.rowcount
    return removed


# ----------------------------------------------------------------- 读取接口

def months(cursor=None):
    """DWS 里有哪些统计月份，新到旧。页面的月份筛选器用它。"""
    def query(cur):
        cur.execute(f"SELECT DISTINCT stat_month FROM {DWS_TABLE} ORDER BY stat_month DESC")
        return [r["stat_month"] for r in cur.fetchall()]
    if cursor is not None:
        return query(cursor)
    with db_connection() as connection, connection.cursor() as cur:
        return query(cur)


def state(cursor, stat_month):
    cursor.execute(f"SELECT * FROM {STATE_TABLE} WHERE stat_month=%s", (stat_month,))
    return cursor.fetchone() or {}


def tier_breakdown(stat_month="", shop=""):
    """某个月每个店铺、每个站点、每个档位的SKU数，直接从 DWS 聚合。

    店铺行不是站点行的简单相加：同一个SKU在DE和UK各挂一条，站点各计一次，
    店铺层面按SKU去重只算一个。页面上两层都要显示，所以两层分别查。
    """
    with db_connection() as connection, connection.cursor() as cursor:
        available = months(cursor)
        month = stat_month.strip() or (available[0] if available else "")
        if not month:
            return dict(stat_month="", months=[], shops=[], shop_rows=[], site_rows=[],
                        distinct_sku_count=0, state={})
        args = [month]
        clause = "stat_month=%s"
        if shop.strip():
            clause += " AND seller_account=%s"
            args.append(shop.strip())
        cursor.execute(f"SELECT DISTINCT seller_account FROM {DWS_TABLE} "
                       f"WHERE stat_month=%s ORDER BY seller_account", (month,))
        shops = [r["seller_account"] for r in cursor.fetchall()]
        # 店铺层：同一SKU在多个站点只算一次，取该店铺内最低档位那一档。
        # 不去重的话店铺SKU数会被站点数放大，和页面上写的"去重SKU"对不上。
        cursor.execute(
            f"""SELECT seller_account, tier_no, COUNT(*) AS sku_count
                FROM (SELECT seller_account, sku, MIN(tier_no) AS tier_no
                      FROM {DWS_TABLE} WHERE {clause}
                      GROUP BY seller_account, sku) t
                GROUP BY seller_account, tier_no ORDER BY seller_account, tier_no""", args)
        shop_rows = list(cursor.fetchall())
        cursor.execute(
            f"""SELECT seller_account, site, tier_no, COUNT(*) AS sku_count,
                       GROUP_CONCAT(DISTINCT currency ORDER BY currency) AS currencies
                FROM {DWS_TABLE} WHERE {clause}
                GROUP BY seller_account, site, tier_no
                ORDER BY seller_account, site, tier_no""", args)
        site_rows = list(cursor.fetchall())
        cursor.execute(f"SELECT COUNT(DISTINCT sku) AS n FROM {DWS_TABLE} WHERE {clause}", args)
        distinct = int((cursor.fetchone() or {}).get("n") or 0)
        rates, rate_months = rates_used(cursor, month)
        current = state(cursor, month)
        # 源表又拉过一次而分层还没重算时，页面要提示"请重新统计"，
        # 否则看到的是上一批刊登的价格结构，却没有任何迹象。
        stale = current.get("source_pulled_at") != source_pulled_at(cursor, month)
        return dict(stat_month=month, months=available, shops=shops, shop_rows=shop_rows,
                    site_rows=site_rows, distinct_sku_count=distinct,
                    state=current, rates=rates, rate_months=rate_months, stale=stale)


def sku_tiers(cursor, stat_month, shops=None):
    """某月每个SKU的档位，不分站点；产品结构的两张图用它。

    同一SKU在不同店铺/站点售价不同时取**最低价**那一档，与分层报表的
    店铺行用的是同一条规则。取平均会让一个站点的清仓价把整体拉低一档，
    取最高又会被某个站点的高价单挑起来，最低价至少是个确定的、
    页面上说得清的口径。

    shops 给了就只看这几家店的挂牌价——筛店铺时销量也只算这几家，
    两边得用同一批店，不然会拿甲店的价格给乙店的销量分档。
    """
    sql = (f"SELECT sku, MIN(price_usd) AS price_usd, MIN(tier_no) AS tier_no,"
           f"       COUNT(*) AS shop_site_count "
           f"FROM {DWS_TABLE} WHERE stat_month=%s")
    args = [stat_month]
    if shops:
        sql += f" AND seller_account IN ({','.join(['%s'] * len(shops))})"
        args += list(shops)
    cursor.execute(sql + " GROUP BY sku", args)
    return {row["sku"]: row for row in cursor.fetchall()}


def sku_tier_lookup(cursor, wanted_months, shops=None):
    """给一串统计月份，各自返回「SKU -> 档位」。

    某个月没有刊登快照时退回到**不晚于该月的最近一个有快照的月份**，
    再没有就退回到最早的那个月。在售刊登是每月5日拉一次，2026-09之前的
    月份没有快照，不回退的话产品结构两张图就只剩一个月。
    价格不会一夜之间跨档，拿相邻月份的挂牌价给历史销量分档是可接受的近似；
    返回值里带上实际用的月份，页面要注明"这一列用的是哪个月的价格"。
    """
    available = months(cursor)          # 新到旧
    if not available:
        return {}, {}
    ordered = sorted(available)
    cache, used = {}, {}
    for month in wanted_months:
        if month in ordered:
            source = month
        else:
            earlier = [m for m in ordered if m <= month]
            source = earlier[-1] if earlier else ordered[0]
        used[month] = source
        if source not in cache:
            cache[source] = sku_tiers(cursor, source, shops)
    return {month: cache[source] for month, source in used.items()}, used


# ------------------------------------------------- 产品结构两张图的事实数据
#
# 两张图的档位都来自上面的 DWS（在售刊登的挂牌价换美元），事实数据各有各的表：
#   销量   dwd_ebay_sku_analysis_order      订单Excel的清洗层，按付款时间归月
#   不良量 dws_ebay_sku_unit_price          飞书「不良交易刊登」算出来的月度量
# 飞书那张表只收录有不良交易的刊登，SKU远不全（实测2026-09只有372个SKU，
# 而在售刊登有2023个），所以它只用来提供不良量，不再用来定价格档。

ORDER_TABLE = "dwd_ebay_sku_analysis_order"
DEFECT_TABLE = "dws_ebay_sku_unit_price"

_SALES_BY_SKU = f"""
    SELECT DATE_FORMAT(o.payment_time,'%%Y-%%m') AS stat_month,
           TRIM(o.inventory_sku) AS sku,
           SUM(o.purchase_quantity)                AS qty,
           SUM(o.refund_quantity)                  AS refund_qty,
           COUNT(*)                                AS order_rows,
           COUNT(DISTINCT o.platform_order_no)     AS order_count
    FROM {ORDER_TABLE} o
    WHERE o.payment_time IS NOT NULL
      AND o.inventory_sku IS NOT NULL AND TRIM(o.inventory_sku) <> ''
      {{year_clause}}
    GROUP BY 1, 2
"""


def sales_by_sku(cursor, year=None, shops=None):
    """各月各SKU的销量与订单数；不分站点，shops 为空则看全 eBay 合计。

    销量是毛销量（purchase_quantity），不扣退货——与 eBay 补货2.0 同口径，
    退货量单列一列，需要看净销量时自己减。

    平台账号列是 2026-09-24 才随数字酋长模板加上的。在那之前上传的批次
    seller_account 是空串，按店铺筛时这些行一条都出不来——不是漏算，是源文件
    当时就没有这一列，得用新模板把那些月份重传。sales_shop_coverage
    专门把这件事量出来给页面提示。
    """
    conditions = ""
    args = []
    if year:
        conditions += " AND o.payment_time >= %s AND o.payment_time < %s"
        args += [f"{int(year)}-01-01", f"{int(year) + 1}-01-01"]
    if shops:
        conditions += f" AND o.seller_account IN ({','.join(['%s'] * len(shops))})"
        args += list(shops)
    cursor.execute(_SALES_BY_SKU.format(year_clause=conditions), tuple(args))
    return list(cursor.fetchall())


def sales_shop_coverage(cursor, year=None):
    """各月订单里有多少销量带得上店铺名。页面按店铺筛时要据此提示。"""
    sql = (f"SELECT DATE_FORMAT(o.payment_time,'%%Y-%%m') AS stat_month,"
           f"       SUM(o.purchase_quantity) AS total_qty,"
           f"       SUM(IF(TRIM(IFNULL(o.seller_account,''))<>'', o.purchase_quantity, 0)) AS shop_qty "
           f"FROM {ORDER_TABLE} o WHERE o.payment_time IS NOT NULL")
    args = ()
    if year:
        sql += " AND o.payment_time >= %s AND o.payment_time < %s"
        args = (f"{int(year)}-01-01", f"{int(year) + 1}-01-01")
    cursor.execute(sql + " GROUP BY 1 ORDER BY 1", args)
    return list(cursor.fetchall())


def defect_by_sku(cursor, year=None, shops=None):
    """各月各SKU的总交易量与不良交易量，来自飞书不良交易刊登表。

    源表是按 月×店铺×SKU 存的，不筛店铺时把店铺维度抹掉聚到SKU级；
    筛了就只算这几家店。注意传进来的 shops 必须已经是**飞书那套店铺名**，
    调用方用 shop_directory 换算过——这张表里是「帝蓝泰江-eBay-Oyeah Motor」，
    不是 eBay 卖家账号 oyeah-motor，直接拿账号名来筛一行都匹配不上。
    """
    sql = (f"SELECT stat_month, sku, SUM(total_qty) AS total_qty, "
           f"SUM(defect_qty) AS defect_qty FROM {DEFECT_TABLE} WHERE 1=1 ")
    args = []
    if year:
        sql += "AND stat_month LIKE %s "
        args.append(f"{year}-%")
    if shops:
        sql += f"AND shop IN ({','.join(['%s'] * len(shops))}) "
        args += list(shops)
    sql += "GROUP BY stat_month, sku"
    cursor.execute(sql, tuple(args))
    return list(cursor.fetchall())


def structure_years(cursor):
    """产品结构的年份选择器：销量、不良量、刊登快照三边年份的并集，新到旧。"""
    years = set()
    for sql in (f"SELECT DISTINCT DATE_FORMAT(payment_time,'%Y') AS y FROM {ORDER_TABLE} "
                f"WHERE payment_time IS NOT NULL",
                f"SELECT DISTINCT LEFT(stat_month,4) AS y FROM {DEFECT_TABLE}",
                f"SELECT DISTINCT LEFT(stat_month,4) AS y FROM {DWS_TABLE}"):
        cursor.execute(sql)
        years.update(str(r["y"]) for r in cursor.fetchall() if r["y"])
    return sorted(years, reverse=True)


def rates_used(cursor, stat_month):
    """该月实际用到的汇率：币种 -> (rate_org, 汇率月份)。页脚的悬浮说明用它。

    直接从 DWS 里读每行记下的值，而不是重新查一遍汇率表——报表说的必须是
    这份数据当时用的那个汇率，不能是"现在查出来的"那个。
    """
    cursor.execute(
        f"""SELECT currency, MAX(rate_org) AS rate_org, MAX(rate_month) AS rate_month,
                   MAX(usd_rate_org) AS usd_rate_org, MAX(usd_rate_month) AS usd_rate_month
            FROM {DWS_TABLE} WHERE stat_month=%s GROUP BY currency ORDER BY currency""",
        (stat_month,))
    rows = list(cursor.fetchall())
    rates, rate_months = {}, {}
    for row in rows:
        currency = str(row["currency"])
        if currency == "USD":
            # 美元不经过汇率，写1并注明，免得有人拿这行去验算。
            rates[currency] = "1（原币即美元，不换汇）"
            rate_months[currency] = ""
            continue
        rates[currency] = str(row["rate_org"])
        rate_months[currency] = row["rate_month"]
        if row["usd_rate_org"] is not None:
            rates.setdefault("USD(分母)", str(row["usd_rate_org"]))
            rate_months.setdefault("USD(分母)", row["usd_rate_month"])
    return rates, rate_months


def source_pulled_at(cursor, stat_month):
    """该月 ODS 最新的拉取时间。和 state 里记的一比就知道源数据有没有更新过。"""
    cursor.execute(f"SELECT MAX(pulled_at) AS t FROM {ODS_TABLE} WHERE stat_month=%s",
                   (stat_month,))
    return (cursor.fetchone() or {}).get("t")


# ------------------------------------------------------------ 店铺名三边归一
#
# 同一家店在三张表里写法都不一样，改不动源头，只能在读取侧归一：
#   在售刊登（档位）  seller_account   oyeah-motor
#   订单（销量）      seller_account   oyeah-motor        ← 模板里的「平台账号」
#   飞书（不良量）    shop             帝蓝泰江-eBay-Oyeah Motor
#
# 订单那一列给的就是 eBay 卖家账号，和在售刊登一字不差，本可以直接等值join，
# 所以**不需要映射表**——真正需要推导的只有飞书那一侧。仍然让订单也走归一键，
# 是为了三边用同一条规则：源头哪天把大小写或连字符改了，不会出现
# 「订单对上了、飞书没对上」这种一半一半的结果。
#
# 比对键只留字母数字并统一小写，抹平大小写、连字符、下划线、空格的差异；
# 飞书那套带公司前缀，所以用「后缀匹配」而不是相等。规则本身只此一处，
# 与飞书表内部的改名归一共用 _match_key。
#
# 实测 2026-09：订单文件39个账号，其中37个与在售刊登完全相等；飞书40个店名
# 与这37个账号 1:1 全部对上、0歧义。剩下 kelan（没配 eBay 授权凭证）与
# Vco8TviLRZK（22行，像个token不像账号）各自单独列出来，不硬塞给别人。

def _suffix_match(key, candidates):
    """candidates 里键以 key 结尾（或反之）且唯一的那一个；有歧义就不认。

    宁可让一家店单独列着，也不能把两家店合成一家——合错了在图上看不出来。
    """
    hit = [name for name, other in candidates.items()
           if other and (other.endswith(key) or key.endswith(other))]
    return hit[0] if len(hit) == 1 else ""


def shop_directory(cursor):
    """产品结构的店铺选择器：三张表的店铺并成一份名单。

    返回 [{value, label, seller_account, feishu_shop, order_shop, has_sales,
           has_defect, has_tier}]，按名称排序。value 就是 label，页面传回来
    什么就按什么找——真正的匹配靠下面算好的三个字段，不在SQL里做归一，
    免得把索引废掉。
    """
    from backend.repositories.ebay_sku_unit_price_repository import _match_key

    def distinct(sql):
        cursor.execute(sql)
        return sorted({str(r["v"]).strip() for r in cursor.fetchall() if str(r["v"] or "").strip()})

    accounts = distinct(f"SELECT DISTINCT seller_account AS v FROM {DWS_TABLE}")
    order_shops = distinct(f"SELECT DISTINCT seller_account AS v FROM {ORDER_TABLE}")
    feishu_shops = distinct(f"SELECT DISTINCT shop AS v FROM {DEFECT_TABLE}")
    order_keys = {name: _match_key(name) for name in order_shops}
    feishu_keys = {name: _match_key(name) for name in feishu_shops}

    entries = []
    # 认领制：卖家账号优先成组，被它认领走的订单名/飞书名不再单独起一组。
    # 不能按「各自名字的归一键」去重——飞书名带公司前缀，它的键和卖家账号的键
    # 本来就不相等，用 setdefault 会让同一家店出现两次（实测选项数 40 虚增到 77）。
    claimed_order, claimed_feishu = set(), set()
    for account in accounts:
        key = _match_key(account)
        order_shop = _suffix_match(key, order_keys)
        feishu_shop = _suffix_match(key, feishu_keys)
        claimed_order.add(order_shop)
        claimed_feishu.add(feishu_shop)
        entries.append(dict(value=account, label=account, seller_account=account,
                            order_shop=order_shop, feishu_shop=feishu_shop))
    # 没有 eBay 授权凭证的店（订单里在卖、飞书里有记录，但拉不到在售刊登）
    # 也要能选到，否则它们的销量和不良量只有"全部"模式下才看得见。
    for name in order_shops:
        if name in claimed_order:
            continue
        feishu_shop = _suffix_match(_match_key(name), feishu_keys)
        claimed_feishu.add(feishu_shop)
        entries.append(dict(value=name, label=name, seller_account="",
                            order_shop=name, feishu_shop=feishu_shop))
    for name in feishu_shops:
        if name in claimed_feishu:
            continue
        entries.append(dict(value=name, label=name, seller_account="",
                            order_shop="", feishu_shop=name))
    for entry in entries:
        entry["has_tier"] = bool(entry["seller_account"])
        entry["has_sales"] = bool(entry["order_shop"])
        entry["has_defect"] = bool(entry["feishu_shop"])
    return sorted(entries, key=lambda e: e["label"].lower())


def resolve_shops(cursor, selected):
    """页面选的店铺名 -> 三张表各自该用的名字。

    选了库里没有的名字直接报错，不当成"全部"——默默返回全量会让人以为
    筛生效了，看到的却是全站数字。
    """
    from backend.repositories.ebay_sku_unit_price_repository import _match_key

    names = [str(name).strip() for name in (selected or []) if str(name or "").strip()]
    if not names:
        return dict(labels=[], accounts=[], order_shops=[], feishu_shops=[], unknown=[])
    directory = {_match_key(entry["value"]): entry for entry in shop_directory(cursor)}
    picked, unknown = [], []
    for name in names:
        entry = directory.get(_match_key(name))
        (picked.append(entry) if entry else unknown.append(name))
    if unknown:
        raise ValueError(f"选择的店铺不在可选范围内：{'、'.join(unknown)}")
    return dict(
        labels=[e["label"] for e in picked],
        accounts=[e["seller_account"] for e in picked if e["seller_account"]],
        order_shops=[e["order_shop"] for e in picked if e["order_shop"]],
        feishu_shops=[e["feishu_shop"] for e in picked if e["feishu_shop"]])
