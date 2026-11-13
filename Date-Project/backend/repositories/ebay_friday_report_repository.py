"""eBay「周五数据」：读上游快照（eBay 在售刊登、谷仓库存、负责人规则、SKU 来源），写 / 读当周报表快照。"""
from __future__ import annotations

import json
from typing import Any, Iterable, Sequence

from pymysql.err import ProgrammingError

from backend.database import db_connection
from backend.repositories import ebay_replenishment_v2_repository as replenishment_repo

RUN_TABLE = "ebay_friday_report_run"
LISTING_TABLE = "ebay_friday_report_listing"
STOCK_TABLE = "ebay_friday_report_stock"
STORE_TABLE = "ebay_store_main_site"
MIGRATION_MESSAGE = "周五数据表未部署，请执行 migrations/20261113_ebay_friday_report.sql"
LISTING_COLUMNS = (
    "report_date", "item_id", "sku", "store_name", "online_qty", "sold_qty", "listing_site", "start_time",
    "brand", "mid_code", "site", "principal_name", "is_used", "overseas_stock", "plan_site", "site_match",
)
STOCK_COLUMNS = (
    "report_date", "row_no", "product_sku", "product_type", "product_barcode", "compliance_status",
    "product_title", "warehouse_code", "warehouse_desc", "warning_qty", "onway", "total_onway",
    "transfer_onway", "freeze", "sellable", "reserved", "shipped", "unsellable", "unsellable_reserved",
    "unsellable_shipped", "site", "sku", "mid_code", "brand", "is_used", "no_link", "principal_name",
    "store_items_json",
)


def missing_table(error: Exception) -> bool:
    return isinstance(error, ProgrammingError) and error.args[0] == 1146 and any(
        name in str(error).lower() for name in (RUN_TABLE, LISTING_TABLE, STOCK_TABLE, STORE_TABLE))


def _query(sql: str, params: Iterable[Any] = ()) -> list[dict[str, Any]]:
    with db_connection() as connection, connection.cursor() as cursor:
        cursor.execute(sql, tuple(params))
        return list(cursor.fetchall())


# ------------------------------------------------------------------ 上游


def latest_listings() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """最新一个月份批次的 eBay 在售刊登（eBay 同步按月份整批覆盖）。"""
    head = _query("SELECT stat_month,MAX(pulled_at) pulled_at,COUNT(*) n FROM ods_ebay_store_listing_latest "
                  "WHERE stat_month=(SELECT MAX(stat_month) FROM ods_ebay_store_listing_latest) GROUP BY stat_month")
    if not head:
        return [], {}
    rows = _query("SELECT item_id,sku,seller_account,site,quantity_available,quantity_sold,start_time "
                  "FROM ods_ebay_store_listing_latest WHERE stat_month=%s", (head[0]["stat_month"],))
    return rows, head[0]


def goodcang_stock() -> tuple[list[dict[str, Any]], Any]:
    """谷仓区域仓库存里良品可售 > 0 的行（与表格「海外仓库存」同口径）。"""
    rows = _query("SELECT warehouse_code,warehouse_desc,product_sku,product_title,sellable,reserved,onway,"
                  "transfer_onway,total_onway,unsellable,pi_freeze,pi_warning_qty,product_type,raw_json,pulled_at "
                  "FROM ods_goodcang_product_inventory_latest WHERE sellable>0 "
                  # 与原表一致：英国、德国、新泽西、加州在前，其余（捷克等）排最后。
                  "ORDER BY FIELD(warehouse_code,'UK','DE','USEA','USWE')=0,"
                  "FIELD(warehouse_code,'UK','DE','USEA','USWE'),warehouse_code,product_sku")
    pulled = _query("SELECT MAX(pulled_at) p FROM ods_goodcang_product_inventory_latest")
    return rows, (pulled[0]["p"] if pulled else None)


def ebay_owner_rules(month: str) -> list[dict[str, Any]]:
    return _query("SELECT match_key,principal_name,rule_type FROM dwd_performance_owner_rule "
                  "WHERE platform='ebay' AND rule_type='EBAY_BRAND' AND stat_month=%s ORDER BY group_code,match_key",
                  (month,))


def brand_sku_sources() -> list[str]:
    """系统里带品牌前缀的 SKU：eBay 刊登、领星本地仓库存、eBay 订单。用来推「中间码 → 品牌」。"""
    source_db = replenishment_repo._source_database()
    skus: list[str] = []
    for sql in ("SELECT DISTINCT UPPER(TRIM(sku)) sku FROM ods_ebay_store_listing_latest WHERE sku<>''",
                f"SELECT DISTINCT UPPER(TRIM(sku)) sku FROM `{source_db}`.warehouse_inventory_detail WHERE sku<>''",
                "SELECT DISTINCT UPPER(TRIM(inventory_sku)) sku FROM dwd_ebay_sku_analysis_order "
                "WHERE inventory_sku<>''"):
        try:
            skus.extend(row["sku"] for row in _query(sql) if row["sku"])
        except ProgrammingError as exc:
            if exc.args[0] != 1146:
                raise
    return skus


# ------------------------------------------------------------------ 店铺主站点


def stores() -> list[dict[str, Any]]:
    return _query(f"SELECT store_key,store_name,main_site,second_site,note,company,sort_order,updated_by,updated_at "
                  f"FROM `{STORE_TABLE}` ORDER BY FIELD(main_site,'DE','UK','US'),sort_order,store_name")


def upsert_store(row: dict[str, Any]) -> None:
    with db_connection() as connection, connection.cursor() as cursor:
        cursor.execute(
            f"INSERT INTO `{STORE_TABLE}` (store_key,store_name,main_site,second_site,note,sort_order,updated_by) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s) ON DUPLICATE KEY UPDATE store_name=VALUES(store_name),"
            "main_site=VALUES(main_site),second_site=VALUES(second_site),note=VALUES(note),"
            "sort_order=VALUES(sort_order),updated_by=VALUES(updated_by)",
            (row["store_key"], row["store_name"], row["main_site"], row.get("second_site"), row.get("note"),
             int(row.get("sort_order") or 0), row.get("updated_by")))
        connection.commit()


def delete_store(store_key: str) -> int:
    with db_connection() as connection, connection.cursor() as cursor:
        cursor.execute(f"DELETE FROM `{STORE_TABLE}` WHERE store_key=%s", (store_key,))
        connection.commit()
        return cursor.rowcount


# ------------------------------------------------------------------ 报表快照


def _db_value(value: Any) -> Any:
    """JSON 列（店铺列）是 dict，pymysql 不能直接绑定 dict，写库前转成 JSON 文本。"""
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    return value


def replace_report(run: dict[str, Any], listings: Sequence[dict[str, Any]], stocks: Sequence[dict[str, Any]]) -> None:
    """同一事务整表替换两张表与生成记录：只保留最新一期，不留历史（2026-11-13 用户确认只看当天这一份）。

    失败回滚，页面始终看到完整的上一份。
    """
    report_date = run["report_date"]
    with db_connection() as connection:
        connection.begin()
        try:
            with connection.cursor() as cursor:
                for table in (LISTING_TABLE, STOCK_TABLE, RUN_TABLE):
                    cursor.execute(f"DELETE FROM `{table}`")
                for table, columns, rows in ((LISTING_TABLE, LISTING_COLUMNS, listings),
                                             (STOCK_TABLE, STOCK_COLUMNS, stocks)):
                    sql = (f"INSERT INTO `{table}` ({','.join(columns)}) "
                           f"VALUES ({','.join(['%s'] * len(columns))})")
                    values = [tuple(_db_value(row.get(column)) for column in columns) for row in rows]
                    for offset in range(0, len(values), 1000):
                        cursor.executemany(sql, values[offset:offset + 1000])
                cursor.execute(
                    f"INSERT INTO `{RUN_TABLE}` (report_date,generated_at,listing_month,listing_pulled_at,"
                    "goodcang_pulled_at,owner_rule_month,listing_rows,stock_rows,store_columns_json,summary_json,"
                    "generated_by) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                    (report_date, run["generated_at"], run.get("listing_month"), run.get("listing_pulled_at"),
                     run.get("goodcang_pulled_at"), run.get("owner_rule_month"), len(listings), len(stocks),
                     json.dumps(run.get("store_columns") or [], ensure_ascii=False),
                     json.dumps(run.get("summary") or {}, ensure_ascii=False, default=str), run.get("generated_by")))
            connection.commit()
        except Exception:
            connection.rollback()
            raise


def runs(limit: int = 26) -> list[dict[str, Any]]:
    return _query(f"SELECT report_date,generated_at,listing_month,listing_pulled_at,goodcang_pulled_at,"
                  f"owner_rule_month,listing_rows,stock_rows,generated_by FROM `{RUN_TABLE}` "
                  "ORDER BY report_date DESC LIMIT %s", (int(limit),))


def run(report_date) -> dict[str, Any] | None:
    rows = _query(f"SELECT * FROM `{RUN_TABLE}` WHERE report_date=%s", (report_date,))
    if not rows:
        return None
    row = rows[0]
    for key in ("store_columns_json", "summary_json"):
        value = row.get(key)
        row[key] = json.loads(value) if isinstance(value, (str, bytes)) else (value or ([] if "columns" in key else {}))
    return row


def page(table: str, where: str, params: list[Any], order: str, limit: int | None, offset: int) -> tuple[list, int]:
    with db_connection() as connection, connection.cursor() as cursor:
        cursor.execute(f"SELECT COUNT(*) n FROM `{table}` WHERE {where}", params)
        total = int(cursor.fetchone()["n"])
        sql = f"SELECT * FROM `{table}` WHERE {where} ORDER BY {order}"
        if limit is not None:
            sql += " LIMIT %s OFFSET %s"
            cursor.execute(sql, [*params, limit, offset])
        else:
            cursor.execute(sql, params)
        return list(cursor.fetchall()), total


def options(table: str, report_date, column: str) -> list[str]:
    rows = _query(f"SELECT DISTINCT {column} v FROM `{table}` WHERE report_date=%s AND {column} IS NOT NULL "
                  f"AND {column}<>'' ORDER BY {column}", (report_date,))
    return [row["v"] for row in rows]
