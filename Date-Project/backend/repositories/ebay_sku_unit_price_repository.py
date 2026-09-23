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

# 每个统计月份只认该月最大的那个登记日期：源表每周三更新，一个月里有4~5批，
# 要的是最新那批的口径，不是把整月几批混在一起加总。
_AGGREGATE_SQL = f"""
    WITH latest AS (
        SELECT DATE_FORMAT(reg_date,'%%Y-%%m') AS stat_month, MAX(reg_date) AS reg_date
        FROM {SOURCE_TABLE} WHERE reg_date IS NOT NULL
        GROUP BY DATE_FORMAT(reg_date,'%%Y-%%m')
    )
    SELECT l.stat_month, b.shop, b.sku, l.reg_date,
           COUNT(*) AS listing_count,
           SUM(CAST(NULLIF(TRIM(b.total_amount),'') AS DECIMAL(20,6))) AS total_amount,
           SUM(CAST(NULLIF(TRIM(b.total_qty),'')    AS DECIMAL(20,6))) AS total_qty,
           SUM(CAST(NULLIF(TRIM(b.defect_qty),'')   AS DECIMAL(20,6))) AS defect_qty
    FROM {SOURCE_TABLE} b
    JOIN latest l ON l.stat_month = DATE_FORMAT(b.reg_date,'%%Y-%%m') AND l.reg_date = b.reg_date
    WHERE b.shop IS NOT NULL AND TRIM(b.shop) <> ''
      AND b.sku  IS NOT NULL AND TRIM(b.sku)  <> ''
    GROUP BY l.stat_month, b.shop, b.sku, l.reg_date
"""


def aggregate(cursor, months=None):
    """按月×店铺×SKU 聚合出单价；总交易量非正的行丢弃并计数。

    months 为 None 时算全部月份（首次建表/回填）；给了就只算这些月份（每周刷新）。
    """
    sql, args = _AGGREGATE_SQL, ()
    if months:
        placeholders = ",".join(["%s"] * len(months))
        sql = f"{_AGGREGATE_SQL} HAVING l.stat_month IN ({placeholders})"
        args = tuple(months)
    cursor.execute(sql, args)
    rows, skipped = [], 0
    for row in cursor.fetchall():
        amount, qty = row["total_amount"], row["total_qty"]
        # 总交易量为0或缺失就算不出单价；丢掉并计数，不拿0或NULL冒充价格。
        if qty is None or qty <= 0 or amount is None or amount < 0:
            skipped += 1
            continue
        price = amount / qty
        rows.append({
            "stat_month": row["stat_month"], "shop": row["shop"], "sku": row["sku"],
            "reg_date": row["reg_date"], "listing_count": row["listing_count"],
            "total_amount": amount, "total_qty": qty, "defect_qty": row["defect_qty"] or 0,
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
