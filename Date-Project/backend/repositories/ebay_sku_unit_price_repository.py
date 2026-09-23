"""eBay SKU 美元单价表：由飞书不良交易刊登表算出，按月×店铺×SKU。

单价 = 该月最大登记日期那一批里，按店铺+SKU 汇总的 总交易额 / 总交易量。
源表金额本来就是美元，不换汇。
"""
from __future__ import annotations

from datetime import datetime

from backend.database import db_connection
from backend.services import listing_price_tier_service as engine

TABLE = "dws_ebay_sku_unit_price"
SOURCE_TABLE = "ods_feishu_bad_transaction_listing"
_BATCH_SIZE = 500

# 一个统计月份里源表有4~5批（每周三一批）。三条规则，缺一不可：
#
# 1. SKU全集取整月的并集，不是只取最后一批。实测2026-09四批合起来有1062个
#    店铺SKU，只看最后一批只有435个，会丢掉627个。
#
# 2. 交易量与不良量在同一个店铺SKU上跨批次取 MAX，绝不相加。源表给的是评估
#    窗口内的累计数，同一个SKU每批都会重报一次：BMW-30034-0046 三批分别是
#    6、7、7，相加得20，实际只有7。
#
# 3. 单价取该店铺SKU**自己**最大登记日期那一批的 金额÷数量。不能拿整月最大量
#    去配另一批的金额——那是两批的数字，比值没有意义。
#    （数字并非单调递增：BMW-30213-0071 的不良量走过 1→2→1，是滚动窗口；
#     实测372个多批次店铺SKU里有80个的最大量不在最后一批。）
#
# 同一批次内同一店铺SKU的多个刊登（不同物品编号）仍然相加——那是不同刊登的
# 成交，本来就该合并。所以是"批次内求和、批次间取最大"。
_AGGREGATE_SQL = f"""
    WITH per_batch AS (
        -- 源表里的店铺名带首尾空白，个别还夹着换行（实测有 ' allteile-motor'、
        -- '  superturbo-store'，以及一个以换行开头的）。不清掉会把同一个店铺
        -- 拆成两个。ODS 保持原样，只在这里归一。
        -- 用 CHAR(10)/CHAR(13) 而不是转义字面量：这段SQL是Python的f-string，
        -- 写反斜杠n会在拼串时变成真的换行，把上面的注释截断。
        SELECT DATE_FORMAT(b.reg_date,'%%Y-%%m') AS stat_month,
               TRIM(BOTH FROM REPLACE(REPLACE(b.shop, CHAR(10), ' '), CHAR(13), ' ')) AS shop,
               TRIM(b.sku) AS sku, b.reg_date,
               COUNT(*) AS listing_count,
               SUM(CAST(NULLIF(TRIM(b.total_amount),'') AS DECIMAL(20,6))) AS total_amount,
               SUM(CAST(NULLIF(TRIM(b.total_qty),'')    AS DECIMAL(20,6))) AS total_qty,
               SUM(CAST(NULLIF(TRIM(b.defect_qty),'')   AS DECIMAL(20,6))) AS defect_qty
        FROM {SOURCE_TABLE} b
        WHERE b.reg_date IS NOT NULL
          AND b.shop IS NOT NULL AND TRIM(b.shop) <> ''
          AND b.sku  IS NOT NULL AND TRIM(b.sku)  <> ''
        GROUP BY 1, 2, 3, b.reg_date
    ),
    ranked AS (
        SELECT p.*, ROW_NUMBER() OVER (PARTITION BY p.stat_month, p.shop, p.sku
                                       ORDER BY p.reg_date DESC) AS rn,
               MAX(p.total_qty)  OVER (PARTITION BY p.stat_month, p.shop, p.sku) AS peak_qty,
               MAX(p.defect_qty) OVER (PARTITION BY p.stat_month, p.shop, p.sku) AS peak_defect
        FROM per_batch p
    )
    SELECT stat_month, shop, sku, reg_date, listing_count,
           total_amount AS price_amount, total_qty AS price_qty,
           peak_qty  AS total_qty,
           peak_defect AS defect_qty
    FROM ranked WHERE rn = 1
"""


def aggregate(cursor, months=None):
    """按月×店铺×SKU 聚合出单价；总交易量非正的行丢弃并计数。

    months 为 None 时算全部月份（首次建表/回填）；给了就只算这些月份（每周刷新）。
    """
    sql, args = _AGGREGATE_SQL, ()
    if months:
        placeholders = ",".join(["%s"] * len(months))
        sql = f"{_AGGREGATE_SQL} AND stat_month IN ({placeholders})"
        args = tuple(months)
    cursor.execute(sql, args)
    rows, skipped = [], 0
    for row in cursor.fetchall():
        # 单价用该店铺SKU自己最大登记日期那一批的金额与数量，两者同批才可比。
        amount, qty = row["price_amount"], row["price_qty"]
        # 总交易量为0或缺失就算不出单价；丢掉并计数，不拿0或NULL冒充价格。
        if qty is None or qty <= 0 or amount is None or amount < 0:
            skipped += 1
            continue
        price = amount / qty
        rows.append({
            "stat_month": row["stat_month"], "shop": row["shop"], "sku": row["sku"],
            "reg_date": row["reg_date"], "listing_count": row["listing_count"],
            "total_amount": amount,
            # 交易量与不良量取整月最大，不是单价那一批的值：同一SKU跨批次重报，
            # 相加会翻倍，取最后一批又会漏掉峰值出现在中间批次的情况。
            "total_qty": row["total_qty"] or 0, "defect_qty": row["defect_qty"] or 0,
            "unit_price": price,
            # 档位逻辑只此一处，与页面分档共用同一套阈值。
            "tier_no": engine.tier_index(price, "USD") + 1,
        })
    return rows, skipped


def refresh(months=None):
    """重算并覆盖这些月份的单价。整批一个事务，失败全回滚。

    同月重复计算直接覆盖：源表每周三更新，一个月内会被刷新4~5次。
    该月算不出来的旧行会被删掉，不留上一批的残影。
    """
    columns = ("stat_month", "shop", "sku", "reg_date", "listing_count",
               "total_amount", "total_qty", "defect_qty", "unit_price", "tier_no")
    insert_sql = (f"INSERT INTO {TABLE} (" + ",".join(f"`{c}`" for c in columns)
                  + ",computed_at) VALUES (" + ",".join(["%s"] * len(columns)) + ",%s) "
                  + "ON DUPLICATE KEY UPDATE "
                  + ",".join(f"`{c}`=VALUES(`{c}`)" for c in columns[3:])
                  + ",computed_at=VALUES(computed_at)")
    computed_at = datetime.now().replace(microsecond=0)
    with db_connection() as connection:
        try:
            connection.begin()
            with connection.cursor() as cursor:
                rows, skipped = aggregate(cursor, months)
                touched = sorted({row["stat_month"] for row in rows})
                for offset in range(0, len(rows), _BATCH_SIZE):
                    chunk = rows[offset:offset + _BATCH_SIZE]
                    cursor.executemany(insert_sql, [
                        tuple(row[c] for c in columns) + (computed_at,) for row in chunk])
                removed = _drop_stale(cursor, touched, {(r["stat_month"], r["shop"], r["sku"]) for r in rows})
            connection.commit()
        except Exception:
            connection.rollback()
            raise
    return {"months": touched, "rows": len(rows), "skipped_rows": skipped, "removed_rows": removed}


def _drop_stale(cursor, months, seen):
    """本次算过的月份里，库里有但这次算不出来的行删掉。没算的月份一行不碰。"""
    removed = 0
    for month in months:
        cursor.execute(f"SELECT shop,sku FROM {TABLE} WHERE stat_month=%s", (month,))
        stale = [(r["shop"], r["sku"]) for r in cursor.fetchall()
                 if (month, r["shop"], r["sku"]) not in seen]
        for offset in range(0, len(stale), _BATCH_SIZE):
            chunk = stale[offset:offset + _BATCH_SIZE]
            clause = " OR ".join(["(shop=%s AND sku=%s)"] * len(chunk))
            args = [month] + [value for pair in chunk for value in pair]
            cursor.execute(f"DELETE FROM {TABLE} WHERE stat_month=%s AND ({clause})", args)
            removed += cursor.rowcount
    return removed


def latest_month(cursor):
    cursor.execute(f"SELECT MAX(stat_month) AS m FROM {TABLE}")
    row = cursor.fetchone()
    return (row or {}).get("m") or ""


def unit_prices(cursor, stat_month):
    """某个月的全部单价行，供价格分层使用。"""
    cursor.execute(
        f"SELECT stat_month,shop,sku,unit_price,total_qty,defect_qty,listing_count,reg_date "
        f"FROM {TABLE} WHERE stat_month=%s ORDER BY shop,sku", (stat_month,))
    return list(cursor.fetchall())


def defect_rate_by_tier(year=None):
    """产品结构：各月各档位的不良交易率，不分店铺。

    分子分母都来自不良交易刊登表，所以这是「被标记刊登内部」的不良率，
    与 eBay 官方面板的口径不同，页面上要注明。
    """
    sql = (f"SELECT stat_month,tier_no,COUNT(*) AS sku_count,"
           f"SUM(total_qty) AS total_qty,SUM(defect_qty) AS defect_qty "
           f"FROM {TABLE} ")
    args = ()
    if year:
        sql += "WHERE stat_month LIKE %s "
        args = (f"{year}-%",)
    sql += "GROUP BY stat_month,tier_no ORDER BY stat_month,tier_no"
    with db_connection() as connection, connection.cursor() as cursor:
        cursor.execute(sql, args)
        rows = list(cursor.fetchall())
        cursor.execute(f"SELECT DISTINCT LEFT(stat_month,4) AS y FROM {TABLE} ORDER BY y DESC")
        years = [r["y"] for r in cursor.fetchall()]
    return rows, years


def months(cursor=None):
    """单价表里有哪些统计月份，新到旧。页面的月份筛选器用它。"""
    def query(cur):
        cur.execute(f"SELECT DISTINCT stat_month FROM {TABLE} ORDER BY stat_month DESC")
        return [r["stat_month"] for r in cur.fetchall()]
    if cursor is not None:
        return query(cursor)
    with db_connection() as connection, connection.cursor() as cur:
        return query(cur)


def tier_breakdown(stat_month="", shop=""):
    """某个月每个店铺每个档位的SKU数，直接从单价表聚合。

    不读已发布的快照：单价表本身就是按月存的，任意历史月份都能当场算出来，
    再维护一份按月的快照只会多一处可能不一致的地方。
    """
    with db_connection() as connection, connection.cursor() as cursor:
        available = months(cursor)
        month = stat_month.strip() or (available[0] if available else "")
        if not month:
            return dict(stat_month="", months=[], shops=[], reg_date="", items=[],
                        distinct_sku_count=0)
        args = [month]
        clause = "stat_month=%s"
        if shop.strip():
            clause += " AND shop=%s"
            args.append(shop.strip())
        cursor.execute(f"SELECT DISTINCT shop FROM {TABLE} WHERE stat_month=%s ORDER BY shop", (month,))
        shops = [r["shop"] for r in cursor.fetchall()]
        cursor.execute(f"SELECT MAX(reg_date) AS d FROM {TABLE} WHERE stat_month=%s", (month,))
        reg_date = (cursor.fetchone() or {}).get("d")
        cursor.execute(
            f"SELECT shop,tier_no,COUNT(*) AS sku_count,SUM(total_qty) AS total_qty,"
            f"SUM(defect_qty) AS defect_qty FROM {TABLE} WHERE {clause} "
            f"GROUP BY shop,tier_no ORDER BY shop,tier_no", args)
        items = list(cursor.fetchall())
        # 行数是「店铺SKU」组合数：同一个SKU铺在N个店铺就算N行。页面上要同时
        # 显示去重SKU数，否则「435 SKU」会被读成有435个不同的商品（实际291个）。
        cursor.execute(f"SELECT COUNT(DISTINCT sku) AS n FROM {TABLE} WHERE {clause}", args)
        distinct_skus = int((cursor.fetchone() or {}).get("n") or 0)
        return dict(stat_month=month, months=available, shops=shops,
                    reg_date=str(reg_date or ""), items=items, distinct_sku_count=distinct_skus)
