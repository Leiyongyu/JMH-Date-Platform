"""eBay 价格分析 BI 的取数与落库：两个 ODS 关联出一张 DWS，查询只读那一列状态。

    ods_ebay_store_listing_latest          在售刊登（售价、可售量、已售量）
    ods_lingxing_inventory_detail_weekly   领星周快照（海外仓/成都中转仓可售、在途、锁定）
    dwd_ebay_sku_analysis_order            近 7/30 日销量
    ods_ebay_sku_analysis_order_raw        真实采购成本
    dim_lingxing_currency_month            月度汇率（my_rate）
                 │  定时任务 ebay_price_analysis_refresh（整表事务替换，不留历史批次）
                 ▼
    dws_ebay_price_analysis                一行 = 一条在售刊登

关联口径：站点 + **完整 SKU**。DE→德国、UK→英国、US→美国，其余站点（实测只有 1 条 FR）
落在「未匹配」。实测命中率 DE 95.1% / UK 97.1% / US 81.8%，降级到「品牌-中间码」
只提升到 97.7% / 98.6% / 85.5%，不值得损失精度，中间码只作聚合与下钻维度。

未关联到库存的刊登**必须保留**（inventory_matched=0、状态「未匹配」）：US 站有近两成
关联不上，静默丢掉会让库存缺口和超卖判断失真。这类行的库存列、cover_days、stock_gap
一律留 NULL，不写 0 —— 0 会被当成「有数据且为零」，进而被算进缺口和超卖。

库存批次的选法与 ebay_inventory_detail_repository 一致：只认跑出过成功周报导出的
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
ORDER_TABLE = "dwd_ebay_sku_analysis_order"
ORDER_RAW_TABLE = "ods_ebay_sku_analysis_order_raw"
RATE_TABLE = "dim_lingxing_currency_month"
EXPORT_FILE_TABLE = "ops_weekly_export_file"

# 海外仓与成都中转仓的仓库ID，以及各自的站点归属，与库存明细页同一套。
OVERSEAS_WIDS = (18699, 18700, 18701, 18702)
CHENGDU_WIDS = (18674, 18675, 18676)
SITE_NAME_BY_SITE = {"DE": "德国", "UK": "英国", "US": "美国"}

MAX_ROWS = 60_000
_BATCH_SIZE = 500

COLUMNS = (
    "stat_date", "seller_account", "site", "site_name", "item_id", "sku", "brand_code",
    "mid_code", "title", "image_url", "view_item_url", "currency", "current_price",
    "price_usd", "ebay_quantity", "ebay_quantity_available", "ebay_quantity_sold",
    "watch_count", "overseas_sellable", "overseas_in_transit", "chengdu_sellable",
    "pending_outbound", "inventory_matched", "sales_qty_7d", "sales_qty_30d",
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
}

# 汇总视图的可排序列：聚合后才有的列（店铺数、刊登数）也在内。
SUMMARY_SORTABLE = {
    "sku", "mid_code", "brand_code", "site", "site_name", "ebay_quantity_available",
    "overseas_sellable", "overseas_in_transit", "chengdu_sellable", "pending_outbound",
    "sales_qty_7d", "sales_qty_30d", "cover_days", "stock_gap", "price_usd",
    "current_price", "purchase_cost_cny", "listing_count", "store_count",
}

_DETAIL_COLUMNS = (
    "seller_account", "site", "site_name", "item_id", "sku", "mid_code", "brand_code",
    "title", "image_url", "view_item_url", "currency", "current_price", "price_usd",
    "ebay_quantity", "ebay_quantity_available", "ebay_quantity_sold", "watch_count",
    "overseas_sellable", "overseas_in_transit", "chengdu_sellable", "pending_outbound",
    "inventory_matched", "sales_qty_7d", "sales_qty_30d", "cover_days", "stock_gap",
    "purchase_cost_cny", "status", "stat_date",
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


def _inventory_ctes() -> str:
    wids = ",".join(str(wid) for wid in (*CHENGDU_WIDS, *OVERSEAS_WIDS))
    overseas = ",".join(str(wid) for wid in OVERSEAS_WIDS)
    chengdu = ",".join(str(wid) for wid in CHENGDU_WIDS)
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
            WHERE i.wid IN ({wids})
        ),
        inventory_source AS (
            SELECT CASE WHEN wid IN (18674,18699) THEN '德国'
                        WHEN wid IN (18675,18702) THEN '英国'
                        WHEN wid IN (18676,18700,18701) THEN '美国' END site_name,
                   TRIM(sku) sku,
                   CASE WHEN wid IN ({chengdu}) THEN COALESCE(product_valid_num,0)
                        ELSE 0 END chengdu_sellable,
                   CASE WHEN wid IN ({overseas}) THEN COALESCE(product_valid_num,0)
                        ELSE 0 END overseas_sellable,
                   CASE WHEN wid IN ({overseas}) THEN COALESCE(product_onway,0)
                        ELSE 0 END overseas_in_transit,
                   COALESCE(product_lock_num,0) pending_outbound
            FROM inventory_ranked
            WHERE inventory_rank=1 AND sku IS NOT NULL AND TRIM(sku)<>''
        ),
        inventory_summary AS (
            SELECT site_name,sku,
                   SUM(chengdu_sellable) chengdu_sellable,
                   SUM(overseas_sellable) overseas_sellable,
                   SUM(overseas_in_transit) overseas_in_transit,
                   SUM(pending_outbound) pending_outbound
            FROM inventory_source GROUP BY site_name,sku
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


def rates(cursor, rate_month: str) -> dict[str, Decimal]:
    """指定月份的企业汇率（my_rate，人民币/1单位外币）。不回退到其他月份。

    缺这个月的汇率就是缺：价格分析把 price_usd 留 NULL，不拿旧月份汇率冒充当月。
    """
    cursor.execute(
        f"SELECT currency_code,my_rate FROM {RATE_TABLE} WHERE rate_month=%s",
        (rate_month,),
    )
    result: dict[str, Decimal] = {}
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
    return result


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
               inventory.overseas_sellable,inventory.overseas_in_transit,
               inventory.chengdu_sellable,inventory.pending_outbound,
               sales7.qty sales_qty_7d,sales30.qty sales_qty_30d,
               cost.unit_cost purchase_cost_cny
        FROM listing
        LEFT JOIN inventory_summary inventory
          ON {_collate('inventory.site_name')} = {site_name}
         AND {_collate('inventory.sku')} = {sku}
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
                stat_date = batch["stat_date"]
                rows = _source_rows(cursor, batch["stat_month"], stat_date)
                month_rates = rates(cursor, stat_date.strftime("%Y-%m"))
            connection.commit()
            return {"batch": batch, "rows": rows, "rates": month_rates,
                    "windows": sales_windows(stat_date)}
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


def _filters(criteria: dict[str, Any]) -> tuple[str, list[Any]]:
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
    keyword = str(criteria.get("keyword") or "").strip()
    if keyword:
        like = f"%{keyword}%"
        clauses.append("(sku LIKE %s OR title LIKE %s OR mid_code LIKE %s OR item_id=%s)")
        params.extend([like, like, like, keyword])
    return (" WHERE " + " AND ".join(clauses) if clauses else ""), params


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


def summary(criteria: dict[str, Any]) -> dict[str, Any]:
    """KPI 的三段取数：刊登行汇总、按 站点+SKU 去重后的库存、各状态条数。

    库存是「站点+SKU」粒度，同一个 SKU 挂了 N 条刊登就会在 N 行里重复出现；
    直接 SUM 会把谷仓可售放大 N 倍，所以去重后再加。
    """
    where, params = _filters(criteria)
    listing = _query(f"""
        SELECT COUNT(*) listing_count,COUNT(DISTINCT sku) sku_count,
               SUM(ebay_quantity_available) ebay_available,
               SUM(CASE WHEN inventory_matched=1 THEN ebay_quantity_available END)
                   matched_ebay_available,
               AVG(price_usd) avg_price_usd,
               SUM(price_usd IS NULL) missing_price_usd
        FROM {TABLE}{where}
    """, params)[0]
    matched_where = where + (" AND " if where else " WHERE ") + "inventory_matched=1"
    inventory = _query(f"""
        SELECT SUM(overseas_sellable) overseas_sellable,
               SUM(chengdu_sellable) chengdu_sellable,
               SUM(overseas_in_transit) overseas_in_transit
        FROM (SELECT site,sku,MAX(overseas_sellable) overseas_sellable,
                     MAX(chengdu_sellable) chengdu_sellable,
                     MAX(overseas_in_transit) overseas_in_transit
              FROM {TABLE}{matched_where} GROUP BY site,sku) distinct_sku
    """, params)[0]
    statuses = _query(
        f"SELECT status,COUNT(*) n FROM {TABLE}{where} GROUP BY status", params)
    return {**listing, **inventory,
            "status_counts": {row["status"]: int(row["n"]) for row in statuses}}


def store_compare(criteria: dict[str, Any]) -> list[dict[str, Any]]:
    """店铺 × 站点的 eBay 可售与谷仓可售。先按 SKU 去重再汇总到店铺。

    两个店铺卖同一个 SKU 时，两边各看到同一份谷仓库存 —— 这是店铺对比本身的含义，
    不是重复计数，页面口径说明里写明。
    """
    where, params = _filters(criteria)
    return _query(f"""
        SELECT seller_account,site,SUM(ebay_available) ebay_available,
               SUM(listing_count) listing_count,SUM(overseas_sellable) overseas_sellable
        FROM (SELECT seller_account,site,sku,
                     SUM(ebay_quantity_available) ebay_available,COUNT(*) listing_count,
                     MAX(CASE WHEN inventory_matched=1 THEN overseas_sellable END)
                         overseas_sellable
              FROM {TABLE}{where} GROUP BY seller_account,site,sku) by_sku
        GROUP BY seller_account,site
        ORDER BY ebay_available DESC,seller_account
        LIMIT 200
    """, params)


def dimension_points(criteria: dict[str, Any], dimension: str) -> list[dict[str, Any]]:
    """散点与缺口榜的共同底数：按完整 SKU 或 品牌-中间码 聚合，跨店合计。

    库存同样先按 站点+SKU 去重再相加；状态在服务层按严重度取最严重的那个。
    """
    key = "mid_code" if dimension == "mid" else "sku"
    where, params = _filters(criteria)
    joiner = " AND " if where else " WHERE "
    rows = _query(f"""
        SELECT grouped.group_key,MAX(grouped.mid_code) mid_code,
               SUM(grouped.ebay_available) ebay_available,
               SUM(grouped.overseas_sellable) overseas_sellable,
               SUM(grouped.listing_count) listing_count,
               SUM(grouped.matched_listing_count) matched_listing_count,
               SUM(grouped.price_sum) price_sum,SUM(grouped.price_rows) price_rows,
               SUM(grouped.sales_qty_30d) sales_qty_30d,
               GROUP_CONCAT(DISTINCT grouped.statuses) statuses
        FROM (SELECT {key} group_key,MAX(mid_code) mid_code,
                     SUM(ebay_quantity_available) ebay_available,
                     MAX(CASE WHEN inventory_matched=1 THEN overseas_sellable END)
                         overseas_sellable,
                     COUNT(*) listing_count,
                     SUM(inventory_matched=1) matched_listing_count,
                     SUM(price_usd) price_sum,SUM(price_usd IS NOT NULL) price_rows,
                     MAX(sales_qty_30d) sales_qty_30d,
                     GROUP_CONCAT(DISTINCT status) statuses
              FROM {TABLE}{where}{joiner}{key} IS NOT NULL
              GROUP BY {key},site) grouped
        GROUP BY grouped.group_key
        LIMIT {MAX_ROWS + 1}
    """, params)
    if len(rows) > MAX_ROWS:
        raise ValueError(f"聚合维度超过{MAX_ROWS}组，未截断数据；请先收窄筛选条件")
    return rows


def detail_rows(criteria: dict[str, Any], *, sort_by: str | None = None,
                sort_order: str = "desc", offset: int | None = None,
                limit: int | None = None) -> list[dict[str, Any]]:
    where, params = _filters(criteria)
    column = sort_by if sort_by in SORTABLE else "stock_gap"
    direction = "ASC" if str(sort_order).lower() == "asc" else "DESC"
    bound = (f" LIMIT {int(limit)} OFFSET {int(offset or 0)}" if limit is not None
             else f" LIMIT {MAX_ROWS + 1}")
    # 排序列可能为 NULL（未匹配行的库存列、缺汇率的美元价）：NULL 一律排在最后，
    # 不让它们顶在第一页冒充极值。seller_account+item_id 兜底保证分页稳定。
    rows = _query(
        f"SELECT {','.join(_DETAIL_COLUMNS)} FROM {TABLE}{where} "
        f"ORDER BY ({column} IS NULL) ASC,{column} {direction},seller_account,item_id"
        f"{bound}", params)
    if limit is None and len(rows) > MAX_ROWS:
        raise ValueError(f"导出行数超过{MAX_ROWS}行，未截断数据；请先收窄筛选条件")
    return rows


def detail_count(criteria: dict[str, Any]) -> int:
    where, params = _filters(criteria)
    return int(_query(f"SELECT COUNT(*) n FROM {TABLE}{where}", params)[0]["n"])


def summary_rows(criteria: dict[str, Any], *, sort_by: str | None = None,
                 sort_order: str = "desc", offset: int | None = None,
                 limit: int | None = None) -> list[dict[str, Any]]:
    """明细表的「按 SKU 汇总」视图：一行一个 站点+完整SKU，跨店合并。

    库存列取 MAX 而不是 SUM：同一 站点+SKU 的每条刊登上挂的是同一份库存。
    """
    where, params = _filters(criteria)
    column = sort_by if sort_by in SUMMARY_SORTABLE else "stock_gap"
    direction = "ASC" if str(sort_order).lower() == "asc" else "DESC"
    bound = (f" LIMIT {int(limit)} OFFSET {int(offset or 0)}" if limit is not None
             else f" LIMIT {MAX_ROWS + 1}")
    joiner = " AND " if where else " WHERE "
    rows = _query(f"""
        SELECT site,site_name,sku,MAX(mid_code) mid_code,MAX(brand_code) brand_code,
               MAX(title) title,MAX(image_url) image_url,MAX(view_item_url) view_item_url,
               MAX(currency) currency,MIN(current_price) current_price,
               AVG(price_usd) price_usd,
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
               COUNT(*) listing_count,COUNT(DISTINCT seller_account) store_count,
               MAX(stat_date) stat_date
        FROM {TABLE}{where}{joiner}sku IS NOT NULL
        GROUP BY site,site_name,sku
        ORDER BY ({column} IS NULL) ASC,{column} {direction},site,sku
        {bound}
    """, params)
    if limit is None and len(rows) > MAX_ROWS:
        raise ValueError(f"导出行数超过{MAX_ROWS}行，未截断数据；请先收窄筛选条件")
    return rows


def summary_count(criteria: dict[str, Any]) -> int:
    where, params = _filters(criteria)
    joiner = " AND " if where else " WHERE "
    return int(_query(
        f"SELECT COUNT(DISTINCT site,sku) n FROM {TABLE}{where}{joiner}sku IS NOT NULL",
        params)[0]["n"])
