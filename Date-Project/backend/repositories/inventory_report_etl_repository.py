from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from backend.config import settings
from backend.database import db_connection


DETAIL_TABLES = {
    "fba": "dwd_inventory_report_fba_detail",
    "overseas": "dwd_inventory_report_overseas_detail",
    "local": "dwd_inventory_report_local_detail",
}

FBA_FIELDS = (
    "stat_month", "source_id", "source_child_index", "sync_batch_id", "sid", "store_name",
    "group_code", "department_code", "principal_name",
    "principal_match_source", "ware_house_name", "msku", "asin", "fnsku",
    "local_sku", "local_name", "country_code", "end_inventory_qty",
    "end_inventory_total_cost", "end_in_transit_qty",
    "end_in_transit_total_cost",
)

WAREHOUSE_FIELDS = (
    "stat_month", "source_id", "source_child_index", "sync_batch_id", "sys_wid",
    "ware_house_name", "seller_name", "product_name", "sku", "fnsku",
    "spu", "brand", "platform_code", "group_code", "department_code",
    "principal_name", "principal_match_source", "end_in_transit_qty",
    "end_in_transit_total_cost", "end_inventory_qty",
    "end_inventory_total_cost",
)

OVERSEAS_FIELDS = (
    "stat_month", "source_id", "source_child_index", "sync_batch_id", "sys_wid",
    "ware_house_name", "seller_name", "product_name", "sku", "fnsku",
    "spu", "api_sku", "brand", "platform_code", "group_code",
    "department_code", "principal_name", "principal_match_source",
    "end_in_transit_qty", "end_in_transit_total_cost", "end_inventory_qty",
    "end_inventory_total_cost",
)

DIMENSION_FIELDS = (
    "stat_month", "source_type", "platform_code", "dimension_type",
    "dimension_value", "department_code", "source_rows",
    "end_in_transit_qty", "end_in_transit_total_cost", "end_inventory_qty",
    "end_inventory_total_cost",
)

DEPARTMENT_FIELDS = (
    "stat_month", "department_code", "department_name", "display_order",
    "is_total", "local_end_in_transit_qty",
    "local_end_in_transit_total_cost", "local_end_inventory_qty",
    "local_end_inventory_total_cost", "overseas_end_in_transit_qty",
    "overseas_end_in_transit_total_cost", "overseas_end_inventory_qty",
    "overseas_end_inventory_total_cost", "fba_end_inventory_qty",
    "fba_end_inventory_total_cost", "fba_end_in_transit_qty",
    "fba_end_in_transit_total_cost",
)


def source_rows(stat_month: str) -> dict[str, list[dict[str, Any]]]:
    queries = {
        "fba": """
            SELECT id,stat_month,sync_batch_id,sid,ware_house_name,msku,asin,
                   fnsku,local_sku,local_name,country_code,end_count,
                   end_total_amount,transferring_out_count,
                   transferring_out_total_amount,end_on_way_count,
                   end_on_way_total_amount,child_data
            FROM ods_lingxing_fba_monthly_inventory_detail
            WHERE stat_month=%s ORDER BY id
        """,
        "overseas": """
            SELECT id,stat_month,sync_batch_id,sys_wid,ware_house_name,
                   seller_name,product_name,sku,fnsku,spu,api_sku,brand,
                   allocation_in_transit_count,allocation_in_transit_cost,
                   day_end_count,day_end_cost,child_list
            FROM ods_lingxing_overseas_monthly_inventory_detail
            WHERE stat_month=%s ORDER BY id
        """,
        "local": """
            SELECT id,stat_month,sync_batch_id,sys_wid,ware_house_name,
                   seller_name,product_name,sku,fnsku,spu,brand,
                   allocation_in_transit_count,allocation_in_transit_cost,
                   day_end_count,day_end_cost,child_list
            FROM ods_lingxing_local_monthly_inventory_detail
            WHERE stat_month=%s ORDER BY id
        """,
    }
    result: dict[str, list[dict[str, Any]]] = {}
    with db_connection() as connection, connection.cursor() as cursor:
        for source_type, query in queries.items():
            cursor.execute(query, (stat_month,))
            result[source_type] = list(cursor.fetchall())
    return result


def amazon_shop_map() -> dict[str, str]:
    database = _source_database()
    with db_connection() as connection, connection.cursor() as cursor:
        cursor.execute(
            f"""
            SELECT CAST(sid AS CHAR) AS sid, store_name
            FROM `{database}`.`shop_list`
            WHERE platform_code='10001' AND sid IS NOT NULL
            """
        )
        return {
            str(row["sid"]): str(row.get("store_name") or "").strip()
            for row in cursor.fetchall()
        }


def owner_rules(stat_month: str, platform: str) -> list[dict[str, Any]]:
    with db_connection() as connection, connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT group_code,rule_type,match_key,principal_name
            FROM dwd_performance_owner_rule
            WHERE stat_month=%s AND platform=%s
            ORDER BY group_code,rule_type,match_key
            """,
            (stat_month, platform),
        )
        return list(cursor.fetchall())


def replace_clean_month(
    stat_month: str,
    fba_rows: list[dict[str, Any]],
    overseas_rows: list[dict[str, Any]],
    local_rows: list[dict[str, Any]],
    dimension_rows: list[dict[str, Any]],
    department_rows: list[dict[str, Any]],
) -> dict[str, int]:
    payloads = (
        ("dwd_inventory_report_fba_detail", FBA_FIELDS, fba_rows),
        ("dwd_inventory_report_overseas_detail", OVERSEAS_FIELDS, overseas_rows),
        ("dwd_inventory_report_local_detail", WAREHOUSE_FIELDS, local_rows),
        ("dws_inventory_report_dimension_summary", DIMENSION_FIELDS, dimension_rows),
        ("dws_inventory_report_department_summary", DEPARTMENT_FIELDS, department_rows),
    )
    deleted_rows = 0
    with db_connection() as connection:
        try:
            with connection.cursor() as cursor:
                for table, fields, rows in payloads:
                    cursor.execute(
                        f"SELECT COUNT(*) AS total FROM `{table}` WHERE stat_month=%s",
                        (stat_month,),
                    )
                    deleted_rows += int(cursor.fetchone()["total"] or 0)
                    cursor.execute(
                        f"DELETE FROM `{table}` WHERE stat_month=%s",
                        (stat_month,),
                    )
                    _insert_rows(cursor, table, fields, rows)
            connection.commit()
        except Exception:
            connection.rollback()
            raise
    return {
        "deleted_rows": deleted_rows,
        "fba_detail_rows": len(fba_rows),
        "overseas_detail_rows": len(overseas_rows),
        "local_detail_rows": len(local_rows),
        "dimension_summary_rows": len(dimension_rows),
        "department_summary_rows": len(department_rows),
        "inserted_rows": sum(len(rows) for _, _, rows in payloads),
    }


def months(limit: int = 24) -> list[dict[str, Any]]:
    with db_connection() as connection, connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT stat_month,MAX(updated_at) AS updated_at,
                   COUNT(*) AS department_rows
            FROM dws_inventory_report_department_summary
            GROUP BY stat_month
            ORDER BY stat_month DESC
            LIMIT %s
            """,
            (max(1, min(limit, 120)),),
        )
        return list(cursor.fetchall())


def department_summary(stat_month: str | None = None) -> dict[str, Any]:
    with db_connection() as connection, connection.cursor() as cursor:
        month = stat_month
        if not month:
            cursor.execute(
                "SELECT MAX(stat_month) AS stat_month "
                "FROM dws_inventory_report_department_summary"
            )
            month = cursor.fetchone()["stat_month"]
        if not month:
            return {"stat_month": None, "items": []}
        cursor.execute(
            """
            SELECT * FROM dws_inventory_report_department_summary
            WHERE stat_month=%s ORDER BY display_order,id
            """,
            (month,),
        )
        return {"stat_month": month, "items": list(cursor.fetchall())}


def detail_rows(
    source_type: str,
    stat_month: str | None,
    department_code: str | None,
    principal_name: str | None,
    keyword: str | None,
    page: int,
    page_size: int,
) -> dict[str, Any]:
    source = source_type.lower()
    if source not in DETAIL_TABLES:
        raise ValueError("source_type必须是fba、overseas或local")
    table = DETAIL_TABLES[source]
    page = max(1, page)
    page_size = max(1, min(page_size, 500))
    with db_connection() as connection, connection.cursor() as cursor:
        month = stat_month
        if not month:
            cursor.execute(f"SELECT MAX(stat_month) AS stat_month FROM `{table}`")
            month = cursor.fetchone()["stat_month"]
        if not month:
            return {
                "source_type": source,
                "stat_month": None,
                "items": [],
                "pagination": {"page": page, "page_size": page_size, "total": 0},
            }
        where = ["stat_month=%s"]
        params: list[Any] = [month]
        if department_code:
            where.append("department_code=%s")
            params.append(department_code)
        if principal_name:
            where.append("principal_name LIKE %s")
            params.append(f"%{principal_name.strip()}%")
        if keyword and keyword.strip():
            value = f"%{keyword.strip()}%"
            if source == "fba":
                where.append(
                    "(store_name LIKE %s OR ware_house_name LIKE %s OR "
                    "msku LIKE %s OR local_sku LIKE %s OR asin LIKE %s)"
                )
                params.extend([value] * 5)
            else:
                where.append(
                    "(seller_name LIKE %s OR ware_house_name LIKE %s OR "
                    "sku LIKE %s OR fnsku LIKE %s OR product_name LIKE %s)"
                )
                params.extend([value] * 5)
        where_sql = " AND ".join(where)
        cursor.execute(
            f"SELECT COUNT(*) AS total FROM `{table}` WHERE {where_sql}",
            tuple(params),
        )
        total = int(cursor.fetchone()["total"] or 0)
        cursor.execute(
            f"SELECT * FROM `{table}` WHERE {where_sql} "
            "ORDER BY department_code,principal_name,id LIMIT %s OFFSET %s",
            (*params, page_size, (page - 1) * page_size),
        )
        return {
            "source_type": source,
            "stat_month": month,
            "items": list(cursor.fetchall()),
            "pagination": {"page": page, "page_size": page_size, "total": total},
        }


def _insert_rows(
    cursor, table: str, fields: tuple[str, ...], rows: list[dict[str, Any]]
) -> None:
    if not rows:
        return
    columns = ",".join(f"`{field}`" for field in fields)
    values = ",".join(f"%({field})s" for field in fields)
    statement = f"INSERT INTO `{table}` ({columns}) VALUES ({values})"
    for batch in _chunks(rows, 300):
        cursor.executemany(statement, batch)


def _chunks(rows: list[dict[str, Any]], size: int) -> Iterable[list[dict[str, Any]]]:
    for start in range(0, len(rows), size):
        yield rows[start : start + size]


def _source_database() -> str:
    return (settings.shop_source_database.strip() or "jmh_data_platform").replace(
        "`", "``"
    )
