"""eBay 价格分析 BI 的取数与落库：在售刊登关联库存、销量、成本，出一张 DWS，查询只读那一列状态。

    ods_ebay_store_listing_latest          在售刊登（售价、可售量、已售量）
    ods_goodcang_product_inventory_latest  谷仓区域仓库存（海外仓可售、海外在途、待出库）
    ods_lingxing_inventory_detail_weekly   领星周快照（只取成都中转仓可售、锁定）
    dwd_ebay_sku_analysis_order            近 7/30 日销量
    ods_ebay_sku_analysis_order_raw        真实采购成本
    dim_lingxing_currency_month            月度汇率（my_rate）
                 │  定时任务 ebay_price_analysis_refresh（整表事务替换，不留历史批次）
                 ▼
    dws_ebay_price_analysis                一行 = 一条在售刊登

库存关联口径：
- 海外仓（谷仓）：站点 + **去掉 SKU 第一段后的其余部分完整比对**（inventory_key）。
  谷仓 SKU 统一是 JMH- 前缀，listing 是品牌前缀，去掉第一段后编码体系一致。
  区域仓 → 站点：DE→德国、UK→英国、USEA + USWE→美国（两仓合计）；CZ 等不纳入。
- 成都中转仓（领星 wid 18674/18675/18676）：站点 + **完整 SKU**，与原口径一致。
- 谷仓或成都任一关联上即算匹配；其余站点（实测只有 1 条 FR）落在「未匹配」。

未关联到库存的刊登**必须保留**（inventory_matched=0、状态「未匹配」），并在刷表时写明原因
（unmatched_reason / unmatched_reason_text，判定见 service.unmatched_reason）：静默丢掉会让
库存缺口和超卖判断失真。这类行的库存列、cover_days、stock_gap 一律留 NULL，不写 0 ——
0 会被当成「有数据且为零」，进而被算进缺口和超卖。

成都仓的领星批次选法与 ebay_inventory_detail_repository 一致：只认跑出过成功周报导出的
那批快照（同一 snapshot_date 下还躺着 INTERRUPTED / FAILED 的批次），再按
(wid, product_id) 取整行代表，不把多个 seller 的同一份实物库存相加。
"""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any, Iterable, Sequence

from backend.database import db_connection

TABLE = "dws_ebay_price_analysis"
LISTING_TABLE = "ods_ebay_store_listing_latest"
INVENTORY_TABLE = "ods_lingxing_inventory_detail_weekly"
GOODCANG_TABLE = "ods_goodcang_product_inventory_latest"
ORDER_TABLE = "dwd_ebay_sku_analysis_order"
ORDER_RAW_TABLE = "ods_ebay_sku_analysis_order_raw"
RATE_TABLE = "dim_lingxing_currency_month"
EXPORT_FILE_TABLE = "ops_weekly_export_file"

# 海外仓取谷仓区域仓库存：区域仓 → 站点；美东、美西合计为美国，CZ 等没有站点归属的仓不纳入。
GOODCANG_SITE_BY_WAREHOUSE = {"DE": "德国", "UK": "英国", "USEA": "美国", "USWE": "美国"}
# 成都中转仓仍取领星周快照，仓库ID与站点归属与库存明细页同一套。
CHENGDU_WIDS = (18674, 18675, 18676)
SITE_NAME_BY_SITE = {"DE": "德国", "UK": "英国", "US": "美国"}

MAX_ROWS = 60_000
_BATCH_SIZE = 500

COLUMNS = (
    "stat_date", "seller_account", "site", "site_name", "item_id", "sku", "brand_code",
    "mid_code", "title", "image_url", "view_item_url", "currency", "current_price",
    "price_usd", "ebay_quantity", "ebay_quantity_available", "ebay_quantity_sold",
    "watch_count", "overseas_sellable", "overseas_in_transit", "chengdu_sellable",
    "pending_outbound", "inventory_matched", "unmatched_reason", "unmatched_reason_text",
    "sales_qty_7d", "sales_qty_30d",
    "cover_days", "stock_gap", "purchase_cost_cny", "status", "sync_batch_id",
    "refreshed_at",
)

# 明细视图可排序列白名单。不在表里的列一律拒绝，不拼接客户端字符串。
SORTABLE = {
    "seller_account", "site", "site_name", "sku", "mid_code", "brand_code", "currency",
    "current_price", "price_usd", "ebay_quantity", "ebay_quantity_available",
    "ebay_quantity_sold", "watch_count", "overseas_sellable", "overseas_in_transit",
    "chengdu_sellable", "pending_outbound", "sales_qty_7d", "sales_qty_30d",
    "cover_days", "stock_gap", "purchase_cost_cny", "status", "item_id",
    "site_store_count", "site_ebay_available_total", "site_price_usd_min",
    "site_price_usd_max", "price_vs_site_min_pct", "site_oversell",
}

# 汇总视图的可排序列：聚合后才有的列（店铺数、刊登数）也在内。
SUMMARY_SORTABLE = {
    "sku", "mid_code", "brand_code", "site", "site_name", "ebay_quantity_available",
    "overseas_sellable", "overseas_in_transit", "chengdu_sellable", "pending_outbound",
    "sales_qty_7d", "sales_qty_30d", "cover_days", "stock_gap", "price_usd",
    "current_price", "purchase_cost_cny", "listing_count", "store_count",
    "price_usd_min", "price_usd_max", "site_oversell",
}

_DETAIL_COLUMNS = (
    "seller_account", "site", "site_name", "item_id", "sku", "mid_code", "brand_code",
    "title", "image_url", "view_item_url", "currency", "current_price", "price_usd",
    "ebay_quantity", "ebay_quantity_available", "ebay_quantity_sold", "watch_count",
    "overseas_sellable", "overseas_in_transit", "chengdu_sellable", "pending_outbound",
    "inventory_matched", "unmatched_reason", "unmatched_reason_text",
    "sales_qty_7d", "sales_qty_30d", "cover_days", "stock_gap",
    "purchase_cost_cny", "status", "stat_date",
    # 以下为查询时派生的跨店对比列（见 _listing_view），不在 DWS 表里。
    "site_store_count", "site_ebay_available_total", "site_price_usd_min",
    "site_price_usd_max", "price_vs_site_min_pct", "site_oversell", "out_of_stock_listed",
)


def _collate(expression: str) -> str:
    """跨表比较字符串：ODS 刊登表是 utf8mb4_bin，库存与订单表是 utf8mb4_unicode_ci。

    不显式统一排序规则，列对列的比较会直接报 1267 混合排序规则。
    """
    return f"CONVERT({expression} USING utf8mb4) COLLATE utf8mb4_unicode_ci"


def _site_name_sql(site_expression: str) -> str:
    whens = " ".join(
        f"WHEN '{site}' THEN '{name}'" for site, name in SITE_NAME_BY_SITE.items()
    )
    return f"CASE {site_expression} {whens} END"


def inventory_key(sku: Any) -> str | None:
    """海外仓关联键：去掉 SKU 第一段（品牌前缀，谷仓侧为 JMH），其余部分完整保留。

    谷仓有两段 SKU（JMH-10022）和四段以上 SKU（JMH-30020-2-0018、JMH-10437-0774-YXR），
    所以不能只取「中间码-尾号」两段，否则会把不同商品错配到一起。
    与 _inventory_key_sql 同一规则：listing 与谷仓两边都按它取 key。
    """
    text = str(sku or "").strip().upper()
    if "-" not in text:
        return None
    return text.split("-", 1)[1].strip() or None


def _inventory_key_sql(expression: str) -> str:
    """inventory_key 的 SQL 版本，两边（listing / 谷仓）用同一段表达式取 key。"""
    text = f"UPPER(TRIM(CAST({expression} AS CHAR(255))))"
    return (f"NULLIF(TRIM(CASE WHEN LOCATE('-',{text})>0 "
            f"THEN SUBSTRING({text},LOCATE('-',{text})+1) END),'')")


def _inventory_ctes() -> str:
    """海外仓取谷仓区域仓库存（站点 + 去前缀 key），成都中转仓仍取领星周快照（站点 + 完整 SKU）。"""
    chengdu = ",".join(str(wid) for wid in CHENGDU_WIDS)
    warehouses = ",".join(f"'{code}'" for code in GOODCANG_SITE_BY_WAREHOUSE)
    site_case = " ".join(f"WHEN '{code}' THEN '{name}'"
                         for code, name in GOODCANG_SITE_BY_WAREHOUSE.items())
    gc_key = _inventory_key_sql("g.product_sku")
    return f"""
        inventory_snapshot AS (
            SELECT i.sync_batch_id,i.snapshot_date,MAX(i.pulled_at) inventory_pulled_at
            FROM {INVENTORY_TABLE} i
            WHERE EXISTS (
                SELECT 1 FROM {EXPORT_FILE_TABLE} f
                WHERE f.export_code='weekly_inventory_bin'
                  AND f.sync_batch_id=i.sync_batch_id AND f.snapshot_date=i.snapshot_date
                  AND f.status IN ('SUCCESS','DELETE_PENDING','DELETED')
            )
            GROUP BY i.sync_batch_id,i.snapshot_date
            ORDER BY i.snapshot_date DESC,inventory_pulled_at DESC,i.sync_batch_id DESC
            LIMIT 1
        ),
        inventory_ranked AS (
            SELECT i.*,
                   ROW_NUMBER() OVER (
                       PARTITION BY i.wid,i.product_id
                       ORDER BY (i.product_total IS NOT NULL) DESC,i.product_total DESC,
                                i.seller_id DESC,i.id DESC
                   ) inventory_rank
            FROM {INVENTORY_TABLE} i
            JOIN inventory_snapshot b
              ON b.sync_batch_id=i.sync_batch_id AND b.snapshot_date=i.snapshot_date
            WHERE i.wid IN ({chengdu})
        ),
        chengdu_inventory AS (
            SELECT CASE wid WHEN 18674 THEN '德国' WHEN 18675 THEN '英国'
                            WHEN 18676 THEN '美国' END site_name,
                   TRIM(sku) sku,
                   SUM(COALESCE(product_valid_num,0)) chengdu_sellable,
                   SUM(COALESCE(product_lock_num,0)) chengdu_pending_outbound
            FROM inventory_ranked
            WHERE inventory_rank=1 AND sku IS NOT NULL AND TRIM(sku)<>''
            GROUP BY wid,TRIM(sku)
        ),
        overseas_inventory AS (
            -- 美东 USEA + 美西 USWE 合计为美国；CZ 等没有站点归属的仓不纳入。
            SELECT CASE g.warehouse_code {site_case} END site_name,
                   {gc_key} sku_key,
                   SUM(COALESCE(g.sellable,0)) overseas_sellable,
                   SUM(COALESCE(g.onway,0)) overseas_in_transit,
                   SUM(COALESCE(g.reserved,0)) overseas_pending_outbound
            FROM {GOODCANG_TABLE} g
            WHERE g.warehouse_code IN ({warehouses})
            GROUP BY CASE g.warehouse_code {site_case} END,{gc_key}
            HAVING sku_key IS NOT NULL
        )
    """


def _listing_cte(stat_month: str | None) -> str:
    """最新一批在售刊登。ODS 按月累积，所以先定位 pulled_at 最新的那个留档月份。"""
    selector = (
        "SELECT %s AS stat_month" if stat_month
        else f"SELECT stat_month FROM {LISTING_TABLE} "
             "GROUP BY stat_month ORDER BY MAX(pulled_at) DESC,stat_month DESC LIMIT 1"
    )
    site = "UPPER(TRIM(CAST(l.site AS CHAR(16))))"
    return f"""
        listing_batch AS ({selector}),
        listing AS (
            SELECT l.seller_account,l.item_id,
                   NULLIF(TRIM(CAST(l.sku AS CHAR(255))),'') sku,
                   NULLIF({site},'') site,
                   {_site_name_sql(site)} site_name,
                   l.title,l.image_url,l.view_item_url,
                   NULLIF(UPPER(TRIM(CAST(l.currency AS CHAR(16)))),'') currency,
                   CAST(l.current_price AS CHAR(64)) current_price,
                   CAST(l.quantity AS SIGNED) ebay_quantity,
                   CAST(l.quantity_available AS SIGNED) ebay_quantity_available,
                   CAST(l.quantity_sold AS SIGNED) ebay_quantity_sold,
                   CAST(l.watch_count AS SIGNED) watch_count,
                   l.pulled_at
            FROM {LISTING_TABLE} l
            JOIN listing_batch b ON b.stat_month=l.stat_month
        )
    """


def latest_listing_batch(cursor, stat_month: str | None = None) -> dict[str, Any]:
    """最新刊登批次的留档月份、拉取时间、行数与店铺数；没有任何刊登时返回空 dict。"""
    cursor.execute(
        f"WITH {_listing_cte(stat_month)} "
        "SELECT (SELECT stat_month FROM listing_batch) stat_month,"
        "MAX(pulled_at) pulled_at,COUNT(*) listing_rows,"
        "COUNT(DISTINCT seller_account) account_count FROM listing",
        (stat_month,) if stat_month else (),
    )
    row = cursor.fetchone() or {}
    if not row.get("pulled_at"):
        return {}
    pulled_at = row["pulled_at"]
    return {
        "stat_month": row["stat_month"],
        "pulled_at": pulled_at,
        "stat_date": pulled_at.date(),
        "listing_rows": int(row.get("listing_rows") or 0),
        "account_count": int(row.get("account_count") or 0),
    }


def rate_lookup(cursor, rate_month: str) -> tuple[dict[str, Decimal], dict[str, str]]:
    """企业汇率（my_rate，人民币/1单位外币）：**每个币种**各取 rate_month 及以前最近一个有效月份。

    返回 (币种 → 汇率, 币种 → 实际用的月份)。

    为什么回退：领星月度企业汇率要到月底才定，而价格分析每周一刷表，一个月里大部分时间
    当月汇率都还没出；只认当月会让绝大多数刊登的 price_usd 为 NULL，跨店比价基本用不了。
    为什么按币种各自回退：各币种出汇率的月份并不整齐（本机 2026-08 只有 1 个币种），
    统一取一个月份会把其他币种整体丢掉。完全没有可用汇率的币种仍然缺，price_usd 留 NULL。
    实际用到的月份写进刷表结果的 rate_months，事后可查是按哪个月折算的。
    """
    cursor.execute(
        f"""SELECT r.currency_code,r.my_rate,r.rate_month
            FROM {RATE_TABLE} r
            JOIN (SELECT UPPER(TRIM(currency_code)) code,MAX(rate_month) rate_month
                  FROM {RATE_TABLE}
                  WHERE rate_month<=%s AND my_rate>0
                  GROUP BY UPPER(TRIM(currency_code))) latest
              ON UPPER(TRIM(r.currency_code))=latest.code AND r.rate_month=latest.rate_month
            WHERE r.my_rate>0""",
        (rate_month,),
    )
    result: dict[str, Decimal] = {}
    months: dict[str, str] = {}
    for row in cursor.fetchall():
        code = str(row.get("currency_code") or "").strip().upper()
        if not code:
            continue
        try:
            rate = Decimal(str(row["my_rate"]))
        except (InvalidOperation, TypeError, ValueError):
            continue
        if rate.is_finite() and rate > 0:
            result[code] = rate
            months[code] = str(row.get("rate_month") or "")
    return result, months


def rates(cursor, rate_month: str) -> dict[str, Decimal]:
    """只要汇率不要月份时用；回退规则见 rate_lookup。"""
    return rate_lookup(cursor, rate_month)[0]


def sales_windows(stat_date: date) -> dict[str, tuple[date, date]]:
    """销量窗口锚在快照日期上，不锚今天：看板展示的是那一天的在售状态。

    左闭右开，右界就是快照日期，所以取的是快照日之前 7 / 30 个完整自然日。
    """
    return {
        "sales_7d": (stat_date - timedelta(days=7), stat_date),
        "sales_30d": (stat_date - timedelta(days=30), stat_date),
    }


def _source_rows(cursor, stat_month: str, stat_date: date) -> list[dict[str, Any]]:
    windows = sales_windows(stat_date)
    site_name = _collate("listing.site_name")
    sku = _collate("listing.sku")
    query = f"""
        WITH {_inventory_ctes()},
        {_listing_cte(stat_month)},
        sales_7d AS (
            SELECT site_name,inventory_sku,SUM(purchase_quantity) qty
            FROM {ORDER_TABLE}
            WHERE payment_time>=%s AND payment_time<%s
              AND COALESCE(shipping_status,'') NOT LIKE '%%已作废%%'
            GROUP BY site_name,inventory_sku
        ),
        sales_30d AS (
            SELECT site_name,inventory_sku,SUM(purchase_quantity) qty
            FROM {ORDER_TABLE}
            WHERE payment_time>=%s AND payment_time<%s
              AND COALESCE(shipping_status,'') NOT LIKE '%%已作废%%'
            GROUP BY site_name,inventory_sku
        ),
        purchase_cost AS (
            -- 真实采购成本取最近一笔该站点该SKU的订单行，换算成单件；不用售价估算。
            SELECT site_name,inventory_sku,purchase_cost_cny/purchase_quantity unit_cost
            FROM (
                SELECT source_site_name site_name,inventory_sku,
                       purchase_cost_cny,purchase_quantity,
                       ROW_NUMBER() OVER (PARTITION BY source_site_name,inventory_sku
                                          ORDER BY payment_time DESC,id DESC) rn
                FROM {ORDER_RAW_TABLE}
                WHERE purchase_cost_cny>0 AND purchase_quantity>0
                  AND COALESCE(shipping_status,'') NOT LIKE '%%已作废%%'
            ) latest
            WHERE rn=1
        )
        SELECT listing.seller_account,listing.item_id,listing.sku,listing.site,
               listing.site_name,listing.title,listing.image_url,listing.view_item_url,
               listing.currency,listing.current_price,listing.ebay_quantity,
               listing.ebay_quantity_available,listing.ebay_quantity_sold,
               listing.watch_count,
               -- 谷仓或成都任一关联上即算匹配；两边都没关联上时库存列留 NULL（build_row 据此判「未匹配」）。
               CASE WHEN overseas.site_name IS NULL AND chengdu.site_name IS NULL THEN NULL
                    ELSE COALESCE(overseas.overseas_sellable,0) END overseas_sellable,
               CASE WHEN overseas.site_name IS NULL AND chengdu.site_name IS NULL THEN NULL
                    ELSE COALESCE(overseas.overseas_in_transit,0) END overseas_in_transit,
               CASE WHEN overseas.site_name IS NULL AND chengdu.site_name IS NULL THEN NULL
                    ELSE COALESCE(chengdu.chengdu_sellable,0) END chengdu_sellable,
               CASE WHEN overseas.site_name IS NULL AND chengdu.site_name IS NULL THEN NULL
                    ELSE COALESCE(overseas.overseas_pending_outbound,0)
                         + COALESCE(chengdu.chengdu_pending_outbound,0) END pending_outbound,
               sales7.qty sales_qty_7d,sales30.qty sales_qty_30d,
               cost.unit_cost purchase_cost_cny
        FROM listing
        LEFT JOIN overseas_inventory overseas
          ON {_collate('overseas.site_name')} = {site_name}
         AND {_collate('overseas.sku_key')} = {_collate(_inventory_key_sql('listing.sku'))}
        LEFT JOIN chengdu_inventory chengdu
          ON {_collate('chengdu.site_name')} = {site_name}
         AND {_collate('chengdu.sku')} = {sku}
        LEFT JOIN sales_7d sales7
          ON {_collate('sales7.site_name')} = {site_name}
         AND {_collate('sales7.inventory_sku')} = {sku}
        LEFT JOIN sales_30d sales30
          ON {_collate('sales30.site_name')} = {site_name}
         AND {_collate('sales30.inventory_sku')} = {sku}
        LEFT JOIN purchase_cost cost
          ON {_collate('cost.site_name')} = {site_name}
         AND {_collate('cost.inventory_sku')} = {sku}
        ORDER BY listing.seller_account,listing.item_id
        LIMIT {MAX_ROWS + 1}
    """
    params = (
        *((stat_month,) if stat_month else ()),
        *windows["sales_7d"], *windows["sales_30d"],
    )
    cursor.execute(query, params)
    rows = list(cursor.fetchall())
    if len(rows) > MAX_ROWS:
        raise ValueError(f"在售刊登超过{MAX_ROWS}行，未截断数据；请先确认刊登同步范围")
    return rows


def goodcang_snapshot(cursor) -> dict[str, Any]:
    """谷仓库存表是否存在、纳入看板的四个仓合计多少行。只读。

    刷表据此拦截：表不存在（迁移未执行）或四个仓 0 行（首次同步失败）时，算下去会把正常看板
    整表覆盖成「海外仓全部未匹配」，还看起来像刷成功了。
    """
    cursor.execute(
        "SELECT COUNT(*) AS n FROM information_schema.TABLES "
        "WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME=%s",
        (GOODCANG_TABLE,),
    )
    if not int((cursor.fetchone() or {}).get("n") or 0):
        return {"exists": False, "rows": 0}
    warehouses = ",".join(["%s"] * len(GOODCANG_SITE_BY_WAREHOUSE))
    cursor.execute(
        f"SELECT COUNT(*) AS n FROM {GOODCANG_TABLE} WHERE warehouse_code IN ({warehouses})",
        tuple(GOODCANG_SITE_BY_WAREHOUSE),
    )
    return {"exists": True, "rows": int((cursor.fetchone() or {}).get("n") or 0)}


def inventory_index(cursor) -> dict[str, Any]:
    """判未匹配原因用的库存索引，只在刷表时取一次：

    - goodcang：区域仓 → 该仓全部去前缀 key（含 CZ 等不纳入看板的仓，用来提示「别的仓有」）
    - chengdu：站点名 → 成都中转仓完整 SKU（大写）
    """
    cursor.execute(f"SELECT warehouse_code,product_sku FROM {GOODCANG_TABLE}")
    goodcang: dict[str, set[str]] = {}
    for row in cursor.fetchall():
        key = inventory_key(row.get("product_sku"))
        code = str(row.get("warehouse_code") or "").strip().upper()
        if key and code:
            goodcang.setdefault(code, set()).add(key)
    cursor.execute(f"WITH {_inventory_ctes()} SELECT site_name,sku FROM chengdu_inventory")
    chengdu: dict[str, set[str]] = {}
    for row in cursor.fetchall():
        if row.get("site_name") and row.get("sku"):
            chengdu.setdefault(row["site_name"], set()).add(str(row["sku"]).strip().upper())
    return {"goodcang": goodcang, "chengdu": chengdu}


def read_source(stat_month: str | None = None) -> dict[str, Any]:
    """同一一致性读事务里取刊登、库存、销量、成本与汇率，避免混用替换前后的批次。"""
    with db_connection() as connection:
        try:
            with connection.cursor() as cursor:
                cursor.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
                connection.begin()
                batch = latest_listing_batch(cursor, stat_month)
                if not batch:
                    connection.commit()
                    return {"batch": {}, "rows": [], "rates": {}, "windows": {}}
                goodcang = goodcang_snapshot(cursor)
                if not goodcang["exists"] or not goodcang["rows"]:
                    # 谷仓表缺失时源查询本身会报错；空表时算出来全是未匹配。都不取源数据，由 service 拒绝刷表。
                    connection.commit()
                    return {"batch": batch, "rows": [], "rates": {}, "windows": {},
                            "goodcang": goodcang}
                stat_date = batch["stat_date"]
                rows = _source_rows(cursor, batch["stat_month"], stat_date)
                month_rates, rate_months = rate_lookup(cursor, stat_date.strftime("%Y-%m"))
                index = inventory_index(cursor)
            connection.commit()
            return {"batch": batch, "rows": rows, "rates": month_rates,
                    "rate_months": rate_months, "inventory_index": index,
                    "windows": sales_windows(stat_date), "goodcang": goodcang}
        except Exception:
            connection.rollback()
            raise


def replace_rows(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    """整表事务替换，不留历史批次（与 ods_ebay_store_listing_latest 的发布方式一致）。

    先删后插在同一个事务里，写完立刻按行数复核：对不上多半是
    (店铺,ItemID) 撞了唯一键把两行合成一行，那属于静默少行，当场回滚。
    """
    if len(rows) > MAX_ROWS:
        raise ValueError(f"价格分析结果超过{MAX_ROWS}行，未写入")
    names = ",".join(f"`{column}`" for column in COLUMNS)
    placeholders = ",".join(f"%({column})s" for column in COLUMNS)
    insert = f"INSERT INTO {TABLE} ({names}) VALUES ({placeholders})"
    with db_connection() as connection:
        try:
            connection.begin()
            with connection.cursor() as cursor:
                cursor.execute(f"DELETE FROM {TABLE}")
                deleted = cursor.rowcount
                for offset in range(0, len(rows), _BATCH_SIZE):
                    cursor.executemany(insert, rows[offset:offset + _BATCH_SIZE])
                cursor.execute(f"SELECT COUNT(*) n FROM {TABLE}")
                stored = int((cursor.fetchone() or {}).get("n") or 0)
                if stored != len(rows):
                    raise ValueError(
                        f"价格分析写入行数校验失败：本次{len(rows)}行，库里{stored}行；"
                        "多半是(店铺,ItemID)撞了唯一键。已回滚。"
                    )
            connection.commit()
            return {"rows": len(rows), "deleted_rows": deleted}
        except Exception:
            connection.rollback()
            raise


def _filters(criteria: dict[str, Any], *, flags: bool = True) -> tuple[str, list[Any]]:
    clauses: list[str] = []
    params: list[Any] = []
    if criteria.get("stat_date"):
        clauses.append("stat_date=%s")
        params.append(criteria["stat_date"])
    for column, key in (("site", "sites"), ("seller_account", "accounts"),
                        ("status", "statuses")):
        values = [value for value in (criteria.get(key) or []) if value]
        if values:
            clauses.append(f"{column} IN (" + ",".join(["%s"] * len(values)) + ")")
            params.extend(values)
    for column, key in (("mid_code", "mid_code"), ("sku", "sku")):
        if criteria.get(key):
            clauses.append(f"{column}=%s")
            params.append(criteria[key])
    if criteria.get("unmatched"):
        clauses.append("inventory_matched=0")
    keyword = str(criteria.get("keyword") or "").strip()
    if keyword:
        like = f"%{keyword}%"
        clauses.append("(sku LIKE %s OR title LIKE %s OR mid_code LIKE %s OR item_id=%s)")
        params.extend([like, like, like, keyword])
    if flags:
        clauses.extend(_flag_clauses(criteria))
    return (" WHERE " + " AND ".join(clauses) if clauses else ""), params


def _flag_clauses(criteria: dict[str, Any]) -> list[str]:
    """多店超卖 / 断货在售两个标记筛选；列是 _listing_view 派生的 0/1。"""
    return [f"{flag}=1" for flag in ("site_oversell", "out_of_stock_listed") if criteria.get(flag)]


# ------------------------------------------------------------ 跨店对比（查询时派生）
# 库存口径：谷仓、成都库存按「站点 + SKU」共享 —— 同站点同 SKU 的多个店铺挂的是同一份库存，
# 聚合时一律取 MAX，绝不相加；eBay 可售是每个店铺各自的，可以相加。
# 多店超卖 = 同站点所有店铺 eBay 可售合计 > 该站点谷仓可售 + 成都可售（只对已匹配库存的 SKU 判定）。
# 这一段是唯一定义：明细、SKU 汇总、店铺汇总、SKU 跨店详情都从它取，不各写一份。
_SITE_OVERSEAS = "MAX(CASE WHEN inventory_matched=1 THEN overseas_sellable END)"
_SITE_CHENGDU = "MAX(CASE WHEN inventory_matched=1 THEN chengdu_sellable END)"
SITE_AGGREGATES_SQL = f"""
    COUNT(DISTINCT seller_account) site_store_count,
    SUM(ebay_quantity_available) site_ebay_available_total,
    MIN(price_usd) site_price_usd_min,
    MAX(price_usd) site_price_usd_max,
    {_SITE_OVERSEAS} site_overseas_sellable,
    {_SITE_CHENGDU} site_chengdu_sellable,
    MAX(CASE WHEN inventory_matched=1 THEN overseas_in_transit END) site_overseas_in_transit,
    MAX(CASE WHEN inventory_matched=1 THEN pending_outbound END) site_pending_outbound,
    CASE WHEN MAX(inventory_matched)=1
          AND COALESCE(SUM(ebay_quantity_available),0)
              > COALESCE({_SITE_OVERSEAS},0)+COALESCE({_SITE_CHENGDU},0)
         THEN 1 ELSE 0 END site_oversell"""


def out_of_stock_listed_sql(alias: str = "") -> str:
    """断货在售（每条刊登）：已匹配库存，谷仓可售 + 成都可售 = 0，但 eBay 可售 > 0。

    唯一定义：明细、SKU 汇总、店铺汇总、sku-listings 都用它。alias 是表别名前缀，如 "d."。
    """
    return (f"CASE WHEN {alias}inventory_matched=1"
            f" AND COALESCE({alias}overseas_sellable,0)+COALESCE({alias}chengdu_sellable,0)=0"
            f" AND COALESCE({alias}ebay_quantity_available,0)>0 THEN 1 ELSE 0 END")


def site_sku_sql(source: str = TABLE, where: str = "") -> str:
    """同站点同 SKU 的跨店聚合。source 可换成同结构的派生表（测试用字面量行喂进来，只读）。"""
    joiner = " AND " if where else " WHERE "
    return (f"SELECT site,sku,{SITE_AGGREGATES_SQL} FROM {source}{where}{joiner}sku IS NOT NULL "
            "GROUP BY site,sku")


def _listing_view(criteria: dict[str, Any], source: str = TABLE) -> tuple[str, list[Any]]:
    """一行一条刊登 + 同站点同 SKU 的跨店对比列。返回带 {columns} 占位的 SQL 与参数。

    跨店聚合算在**全部店铺**上，只受快照日期约束：按店铺筛选时，对比的仍是该站点所有店铺。
    """
    where, params = "", []
    if criteria.get("stat_date"):
        where, params = " WHERE stat_date=%s", [criteria["stat_date"]]
    view = f"""
        WITH site_sku AS ({site_sku_sql(source, where)})
        SELECT {{columns}} FROM (
            SELECT d.*,
                   s.site_store_count,s.site_ebay_available_total,
                   s.site_price_usd_min,s.site_price_usd_max,
                   CASE WHEN d.price_usd IS NULL OR s.site_price_usd_min IS NULL
                             OR s.site_price_usd_min=0 THEN NULL
                        ELSE (d.price_usd-s.site_price_usd_min)/s.site_price_usd_min
                   END price_vs_site_min_pct,
                   CASE WHEN d.inventory_matched=1 THEN COALESCE(s.site_oversell,0) ELSE 0 END
                       site_oversell,
                   {out_of_stock_listed_sql("d.")} out_of_stock_listed
            FROM {source} d
            LEFT JOIN site_sku s ON s.site<=>d.site AND s.sku=d.sku
        ) v"""
    return view, params


def _query(sql: str, params: Iterable[Any]) -> list[dict[str, Any]]:
    with db_connection() as connection, connection.cursor() as cursor:
        cursor.execute(sql, tuple(params))
        return list(cursor.fetchall())


def meta() -> dict[str, Any]:
    """表里现有快照的日期、刷新时间与行数；表空时各项为 None。"""
    rows = _query(
        f"SELECT MAX(stat_date) stat_date,MAX(refreshed_at) refreshed_at,"
        f"MAX(sync_batch_id) sync_batch_id,COUNT(*) rows_ FROM {TABLE}", ())
    row = rows[0] if rows else {}
    return {"stat_date": row.get("stat_date"), "refreshed_at": row.get("refreshed_at"),
            "sync_batch_id": row.get("sync_batch_id"), "rows": int(row.get("rows_") or 0)}


def detail_rows(criteria: dict[str, Any], *, sort_by: str | None = None,
                sort_order: str = "desc", offset: int | None = None,
                limit: int | None = None) -> list[dict[str, Any]]:
    view, view_params = _listing_view(criteria)
    where, params = _filters(criteria)
    column = sort_by if sort_by in SORTABLE else "stock_gap"
    direction = "ASC" if str(sort_order).lower() == "asc" else "DESC"
    bound = (f" LIMIT {int(limit)} OFFSET {int(offset or 0)}" if limit is not None
             else f" LIMIT {MAX_ROWS + 1}")
    # 排序列可能为 NULL（未匹配行的库存列、缺汇率的美元价）：NULL 一律排在最后，
    # 不让它们顶在第一页冒充极值。seller_account+item_id 兜底保证分页稳定。
    rows = _query(
        view.format(columns=",".join(_DETAIL_COLUMNS)) + f"{where} "
        f"ORDER BY ({column} IS NULL) ASC,{column} {direction},seller_account,item_id"
        f"{bound}", [*view_params, *params])
    if limit is None and len(rows) > MAX_ROWS:
        raise ValueError(f"导出行数超过{MAX_ROWS}行，未截断数据；请先收窄筛选条件")
    return rows


def detail_count(criteria: dict[str, Any]) -> int:
    view, view_params = _listing_view(criteria)
    where, params = _filters(criteria)
    return int(_query(view.format(columns="COUNT(*) n") + where,
                      [*view_params, *params])[0]["n"])


def _summary_grouped(criteria: dict[str, Any], select: str) -> tuple[str, list[Any]]:
    """按 站点+SKU 分组的子查询。行级筛选在分组前，两个标记筛选在分组后（标记是 站点+SKU 级的）。"""
    view, view_params = _listing_view(criteria)
    where, params = _filters(criteria, flags=False)
    joiner = " AND " if where else " WHERE "
    grouped = (view.format(columns=select) + f"{where}{joiner}sku IS NOT NULL "
               "GROUP BY site,site_name,sku")
    flags = _flag_clauses(criteria)
    outer = (" WHERE " + " AND ".join(flags)) if flags else ""
    return f"SELECT * FROM ({grouped}) g{outer}", [*view_params, *params]


_SUMMARY_SELECT = """
        site,site_name,sku,MAX(mid_code) mid_code,MAX(brand_code) brand_code,
        MAX(title) title,MAX(image_url) image_url,MAX(view_item_url) view_item_url,
        MAX(currency) currency,MIN(current_price) current_price,
        AVG(price_usd) price_usd,
        MAX(site_price_usd_min) price_usd_min,MAX(site_price_usd_max) price_usd_max,
        SUM(ebay_quantity_available) ebay_quantity_available,
        MAX(overseas_sellable) overseas_sellable,
        MAX(overseas_in_transit) overseas_in_transit,
        MAX(chengdu_sellable) chengdu_sellable,
        MAX(pending_outbound) pending_outbound,
        MAX(sales_qty_7d) sales_qty_7d,MAX(sales_qty_30d) sales_qty_30d,
        MAX(cover_days) cover_days,
        MAX(CASE WHEN inventory_matched=1 THEN overseas_sellable END)
            -SUM(ebay_quantity_available) stock_gap,
        MAX(purchase_cost_cny) purchase_cost_cny,
        GROUP_CONCAT(DISTINCT status) statuses,
        COUNT(*) listing_count,MAX(site_store_count) store_count,
        MAX(site_oversell) site_oversell,MAX(out_of_stock_listed) out_of_stock_listed,
        MAX(unmatched_reason) unmatched_reason,MAX(unmatched_reason_text) unmatched_reason_text,
        MAX(stat_date) stat_date"""


def summary_rows(criteria: dict[str, Any], *, sort_by: str | None = None,
                 sort_order: str = "desc", offset: int | None = None,
                 limit: int | None = None) -> list[dict[str, Any]]:
    """明细表的「按 SKU 汇总」视图：一行一个 站点+完整SKU，跨店合并。

    库存列取 MAX 而不是 SUM：同一 站点+SKU 的每条刊登上挂的是同一份库存。
    跨店对比列（store_count、price_usd_min / max、site_oversell）取自 site_sku，按该站点
    全部店铺算，不受店铺、状态、关键词筛选影响，与明细里的同站点对比同一口径；
    其余汇总列（刊登数、eBay 可售合计、均价等）按筛选后的刊登算。
    """
    column = sort_by if sort_by in SUMMARY_SORTABLE else "stock_gap"
    direction = "ASC" if str(sort_order).lower() == "asc" else "DESC"
    bound = (f" LIMIT {int(limit)} OFFSET {int(offset or 0)}" if limit is not None
             else f" LIMIT {MAX_ROWS + 1}")
    sql, params = _summary_grouped(criteria, _SUMMARY_SELECT)
    rows = _query(f"{sql} ORDER BY ({column} IS NULL) ASC,{column} {direction},site,sku{bound}",
                  params)
    if limit is None and len(rows) > MAX_ROWS:
        raise ValueError(f"导出行数超过{MAX_ROWS}行，未截断数据；请先收窄筛选条件")
    return rows


def summary_count(criteria: dict[str, Any]) -> int:
    sql, params = _summary_grouped(
        criteria, "site,sku,MAX(site_oversell) site_oversell,"
                  "MAX(out_of_stock_listed) out_of_stock_listed")
    return int(_query(f"SELECT COUNT(*) n FROM ({sql}) c", params)[0]["n"])


STORE_SELECT = """
        seller_account,site,MAX(site_name) site_name,
        COUNT(*) listing_count,COUNT(DISTINCT sku) sku_count,
        COALESCE(SUM(ebay_quantity_available),0) ebay_available,
        SUM(out_of_stock_listed) out_of_stock_listed,
        COUNT(DISTINCT CASE WHEN site_oversell=1 THEN sku END) site_oversell_sku_count,
        SUM(inventory_matched=0) unmatched_count"""


def store_rows(criteria: dict[str, Any]) -> list[dict[str, Any]]:
    """店铺汇总：一行一个 店铺+站点。只受站点、店铺筛选；多店超卖按该站点全部店铺判定。"""
    view, view_params = _listing_view(criteria)
    where, params = _filters({key: criteria.get(key)
                              for key in ("stat_date", "sites", "accounts")})
    return _query(view.format(columns=STORE_SELECT)
                  + f"{where} GROUP BY seller_account,site ORDER BY seller_account,site LIMIT 1000",
                  [*view_params, *params])


def sku_listings(sku: str) -> list[dict[str, Any]]:
    """某个完整 SKU 在所有店铺、所有站点的刊登。按 站点、美元价 排序，缺价排最后。"""
    return _query(
        "SELECT seller_account,site,site_name,item_id,view_item_url,currency,current_price,"
        "price_usd,ebay_quantity_available,status,title,image_url,"
        "unmatched_reason,unmatched_reason_text,"
        f"{out_of_stock_listed_sql()} out_of_stock_listed FROM {TABLE} WHERE sku=%s "
        "ORDER BY site,(price_usd IS NULL) ASC,price_usd,seller_account,item_id "
        f"LIMIT {MAX_ROWS + 1}", (sku,))


def sku_sites(sku: str) -> list[dict[str, Any]]:
    """某个 SKU 每个站点的库存与跨店合计：库存取 MAX（站点共享一份），eBay 可售相加。"""
    return _query(f"SELECT site,MAX(site_name) site_name,{SITE_AGGREGATES_SQL} FROM {TABLE} "
                  "WHERE sku=%s GROUP BY site ORDER BY site", (sku,))
