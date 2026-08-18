from __future__ import annotations

from collections.abc import Iterable
from decimal import Decimal
from typing import Any

from backend.config import settings
from backend.database import db_connection


ZERO = Decimal("0")


DETAIL_TABLES = {
    "fba": "dwd_inventory_report_fba_detail",
    "overseas": "dwd_inventory_report_overseas_detail",
    "local": "dwd_inventory_report_local_detail",
    "ebay_sales": "dwd_inventory_report_ebay_sales_detail",
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

AMZ_SALES_FIELDS = (
    "stat_month", "source_id", "sid", "store_name",
    "group_code", "department_code", "principal_name",
    "principal_match_source", "msku", "local_sku", "asin", "item_name",
    "currency_code", "amount", "volume",
)

EBAY_SALES_SOURCE_FIELDS = (
    "stat_month", "sku", "brand_code", "image_url", "multi_variant",
    "product_sales_amount", "receivable_shipping_amount", "amount",
    "source_file_name", "source_sheet", "source_row", "import_batch_id",
    "imported_by",
)

PURCHASE_ORDER_TRANSIT_FIELDS = (
    "stat_month", "purchase_order_no", "purchase_warehouse",
    "purchase_warehouse_detail", "sku", "store_name", "unit_price",
    "pending_arrival_qty", "sku_pending_total_cost", "product_dimension",
    "platform_code", "group_code", "department_code", "source_file_name",
    "source_sheet", "source_row", "import_batch_id", "imported_by",
)

EBAY_SALES_FIELDS = (
    "stat_month", "source_id", "sku", "brand_code", "image_url",
    "multi_variant", "department_code", "principal_name",
    "principal_match_source", "product_sales_amount",
    "receivable_shipping_amount", "amount",
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
    "fba_end_in_transit_total_cost", "next_month_opening_inventory_qty",
    "actual_achievement_amount", "target_achievement_rate",
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
        "order_profit": """
            SELECT id,stat_month,sid,msku,local_sku,asin,
                   item_name,currency_code,amount,volume
            FROM ods_lingxing_inventory_report_amz_order_profit
            WHERE stat_month=%s ORDER BY id
        """,
        "ebay_sales": """
            SELECT id,stat_month,sku,brand_code,image_url,multi_variant,
                   product_sales_amount,receivable_shipping_amount,amount
            FROM ods_inventory_report_ebay_sales
            WHERE stat_month=%s ORDER BY id
        """,
        "purchase_order_transit": """
            SELECT id,stat_month,purchase_order_no,purchase_warehouse,
                   purchase_warehouse_detail,sku,store_name,unit_price,
                   pending_arrival_qty,sku_pending_total_cost,product_dimension,
                   platform_code,group_code,department_code,source_file_name,
                   source_sheet,source_row,import_batch_id,imported_by,imported_at
            FROM ods_inventory_report_purchase_order_transit
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


def replace_ebay_sales_source_month(
    stat_month: str,
    rows: list[dict[str, Any]],
) -> dict[str, int]:
    table = "ods_inventory_report_ebay_sales"
    with db_connection() as connection:
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    f"SELECT COUNT(*) AS total FROM `{table}` WHERE stat_month=%s",
                    (stat_month,),
                )
                deleted_rows = int(cursor.fetchone()["total"] or 0)
                cursor.execute(
                    f"DELETE FROM `{table}` WHERE stat_month=%s",
                    (stat_month,),
                )
                _insert_rows(cursor, table, EBAY_SALES_SOURCE_FIELDS, rows)
            connection.commit()
        except Exception:
            connection.rollback()
            raise
    return {"deleted_rows": deleted_rows, "inserted_rows": len(rows)}


def replace_purchase_order_transit(
    stat_month: str,
    rows: list[dict[str, Any]],
) -> dict[str, int]:
    """全表替换采购单在途源数据，并同步已存在的部门汇总快照。"""
    table = "ods_inventory_report_purchase_order_transit"
    with db_connection() as connection:
        try:
            with connection.cursor() as cursor:
                cursor.execute(f"SELECT COUNT(*) AS total FROM `{table}`")
                deleted_rows = int(cursor.fetchone()["total"] or 0)
                cursor.execute(f"DELETE FROM `{table}`")
                _insert_rows(cursor, table, PURCHASE_ORDER_TRANSIT_FIELDS, rows)
                updated_rows = _apply_purchase_order_transit_to_summary(
                    cursor, stat_month
                )
            connection.commit()
        except Exception:
            connection.rollback()
            raise
    return {
        "deleted_rows": deleted_rows,
        "inserted_rows": len(rows),
        "updated_summary_rows": updated_rows,
    }


def _apply_purchase_order_transit_to_summary(cursor, stat_month: str) -> int:
    cursor.execute(
        """
        UPDATE dws_inventory_report_department_summary d
        LEFT JOIN (
            SELECT stat_month,department_code,
                   COALESCE(SUM(pending_arrival_qty),0) AS total_qty,
                   COALESCE(SUM(sku_pending_total_cost),0) AS total_cost
            FROM ods_inventory_report_purchase_order_transit
            WHERE stat_month=%s
            GROUP BY stat_month,department_code
        ) p ON p.stat_month=d.stat_month
           AND p.department_code=d.department_code
        SET d.local_end_in_transit_qty=COALESCE(p.total_qty,0),
            d.local_end_in_transit_total_cost=COALESCE(p.total_cost,0),
            d.updated_at=NOW()
        WHERE d.stat_month=%s AND d.is_total=0
        """,
        (stat_month, stat_month),
    )
    detail_rows = max(0, int(cursor.rowcount or 0))
    cursor.execute(
        """
        UPDATE dws_inventory_report_department_summary d
        JOIN (
            SELECT stat_month,
                   COALESCE(SUM(local_end_in_transit_qty),0) AS total_qty,
                   COALESCE(SUM(local_end_in_transit_total_cost),0) AS total_cost
            FROM dws_inventory_report_department_summary
            WHERE stat_month=%s AND is_total=0
            GROUP BY stat_month
        ) totals ON totals.stat_month=d.stat_month
        SET d.local_end_in_transit_qty=totals.total_qty,
            d.local_end_in_transit_total_cost=totals.total_cost,
            d.updated_at=NOW()
        WHERE d.stat_month=%s AND d.is_total=1
        """,
        (stat_month, stat_month),
    )
    return detail_rows + max(0, int(cursor.rowcount or 0))


def replace_clean_month(
    stat_month: str,
    fba_rows: list[dict[str, Any]],
    overseas_rows: list[dict[str, Any]],
    local_rows: list[dict[str, Any]],
    amz_sales_rows: list[dict[str, Any]],
    ebay_sales_rows: list[dict[str, Any]],
    dimension_rows: list[dict[str, Any]],
    department_rows: list[dict[str, Any]],
) -> dict[str, int]:
    payloads = (
        ("dwd_inventory_report_fba_detail", FBA_FIELDS, fba_rows),
        ("dwd_inventory_report_overseas_detail", OVERSEAS_FIELDS, overseas_rows),
        ("dwd_inventory_report_local_detail", WAREHOUSE_FIELDS, local_rows),
        ("dwd_inventory_report_amz_sales_detail", AMZ_SALES_FIELDS, amz_sales_rows),
        ("dwd_inventory_report_ebay_sales_detail", EBAY_SALES_FIELDS, ebay_sales_rows),
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
        "amz_sales_detail_rows": len(amz_sales_rows),
        "ebay_sales_detail_rows": len(ebay_sales_rows),
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


def opening_inventory_by_department(
    stat_month: str,
) -> dict[str, Decimal | None]:
    """读取已回填的次月月初库存，避免重新计算汇总时丢失快照。"""
    with db_connection() as connection, connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT department_code,next_month_opening_inventory_qty
            FROM dws_inventory_report_department_summary
            WHERE stat_month=%s
            """,
            (stat_month,),
        )
        return {
            str(row["department_code"]): row[
                "next_month_opening_inventory_qty"
            ]
            for row in cursor.fetchall()
        }


def fill_next_month_opening_inventory(stat_month: str) -> dict[str, int]:
    """使用本月海外仓与FBA仓期末库存数量，回填次月月初库存快照。"""
    with db_connection() as connection:
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT
                        SUM(CASE WHEN is_total=0 THEN 1 ELSE 0 END)
                            AS source_rows,
                        SUM(CASE WHEN is_total=1 THEN 1 ELSE 0 END)
                            AS total_rows
                    FROM dws_inventory_report_department_summary
                    WHERE stat_month=%s
                    """,
                    (stat_month,),
                )
                counts = cursor.fetchone()
                source_rows = int(counts["source_rows"] or 0)
                total_rows = int(counts["total_rows"] or 0)
                if source_rows == 0:
                    raise ValueError(
                        f"{stat_month} 没有可用的月度库存部门汇总数据"
                    )
                cursor.execute(
                    """
                    UPDATE dws_inventory_report_department_summary
                    SET next_month_opening_inventory_qty=
                            COALESCE(overseas_end_inventory_qty,0)
                            + COALESCE(fba_end_inventory_qty,0),
                        updated_at=NOW()
                    WHERE stat_month=%s AND is_total=0
                    """,
                    (stat_month,),
                )
                cursor.execute(
                    """
                    UPDATE dws_inventory_report_department_summary d
                    JOIN (
                        SELECT stat_month,
                               SUM(next_month_opening_inventory_qty) AS total_qty
                        FROM dws_inventory_report_department_summary
                        WHERE stat_month=%s AND is_total=0
                        GROUP BY stat_month
                    ) totals ON totals.stat_month=d.stat_month
                    SET d.next_month_opening_inventory_qty=totals.total_qty,
                        d.updated_at=NOW()
                    WHERE d.stat_month=%s AND d.is_total=1
                    """,
                    (stat_month, stat_month),
                )
            connection.commit()
        except Exception:
            connection.rollback()
            raise
    return {
        "source_rows": source_rows,
        "updated_rows": source_rows + total_rows,
    }


def inventory_age_group_costs(pull_month: str) -> dict[str, dict[str, Any]]:
    with db_connection() as connection, connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT group_code,inventory_91_180_cost,inventory_181_plus_cost
            FROM dws_amz_fba_inventory_age_group
            WHERE pull_month=%s
            UNION ALL
            SELECT 'EBAY-1' AS group_code,
                   COALESCE(SUM(CASE WHEN inventory_age_bucket='91_180'
                                    THEN inventory_age_cost ELSE 0 END),0)
                       AS inventory_91_180_cost,
                   COALESCE(SUM(CASE WHEN inventory_age_bucket='181_PLUS'
                                    THEN inventory_age_cost ELSE 0 END),0)
                       AS inventory_181_plus_cost
            FROM dwd_ebay_inventory_age_cost_snapshot
            WHERE pull_month=%s
            HAVING COUNT(*)>0
            """,
            (pull_month, pull_month),
        )
        return {
            str(row["group_code"]): row
            for row in cursor.fetchall()
        }


def order_profit_rows(stat_month: str) -> list[dict[str, Any]]:
    """Return the AMZ order-profit snapshot used to calculate monthly volume."""
    with db_connection() as connection, connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT id,stat_month,sid,msku,local_sku,asin,item_name,
                   currency_code,amount,volume
            FROM ods_lingxing_inventory_report_amz_order_profit
            WHERE stat_month=%s
            ORDER BY id
            """,
            (stat_month,),
        )
        return list(cursor.fetchall())


def ebay_sales_source_rows(stat_month: str) -> list[dict[str, Any]]:
    """Return one business month's uploaded eBay actual-achievement source."""
    with db_connection() as connection, connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT id,stat_month,sku,brand_code,image_url,multi_variant,
                   product_sales_amount,receivable_shipping_amount,amount
            FROM ods_inventory_report_ebay_sales
            WHERE stat_month=%s
            ORDER BY id
            """,
            (stat_month,),
        )
        return list(cursor.fetchall())


def replace_amz_sales_detail_month(
    stat_month: str,
    rows: list[dict[str, Any]],
) -> dict[str, int]:
    """Replace only the AMZ sales DWD partition used by month-end volume."""
    table = "dwd_inventory_report_amz_sales_detail"
    with db_connection() as connection:
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    f"SELECT COUNT(*) AS total FROM `{table}` WHERE stat_month=%s",
                    (stat_month,),
                )
                deleted_rows = int(cursor.fetchone()["total"] or 0)
                cursor.execute(
                    f"DELETE FROM `{table}` WHERE stat_month=%s",
                    (stat_month,),
                )
                _insert_rows(cursor, table, AMZ_SALES_FIELDS, rows)
            connection.commit()
        except Exception:
            connection.rollback()
            raise
    return {"deleted_rows": deleted_rows, "inserted_rows": len(rows)}


def replace_ebay_sales_detail_month(
    stat_month: str,
    rows: list[dict[str, Any]],
) -> dict[str, int]:
    """Replace one business month's uploaded eBay actual-achievement DWD."""
    table = "dwd_inventory_report_ebay_sales_detail"
    with db_connection() as connection:
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    f"SELECT COUNT(*) AS total FROM `{table}` WHERE stat_month=%s",
                    (stat_month,),
                )
                deleted_rows = int(cursor.fetchone()["total"] or 0)
                cursor.execute(
                    f"DELETE FROM `{table}` WHERE stat_month=%s",
                    (stat_month,),
                )
                _insert_rows(cursor, table, EBAY_SALES_FIELDS, rows)
            connection.commit()
        except Exception:
            connection.rollback()
            raise
    return {"deleted_rows": deleted_rows, "inserted_rows": len(rows)}


def amz_sales_volume_by_department(
    stat_month: str,
) -> dict[str, Decimal] | None:
    """Aggregate cleaned AMZ volume; None means the month has no DWD source."""
    with db_connection() as connection, connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT COUNT(*) AS source_rows
            FROM dwd_inventory_report_amz_sales_detail
            WHERE stat_month=%s
            """,
            (stat_month,),
        )
        if int(cursor.fetchone()["source_rows"] or 0) == 0:
            return None
        cursor.execute(
            """
            SELECT department_code,COALESCE(SUM(volume),0) AS sales_volume
            FROM dwd_inventory_report_amz_sales_detail
            WHERE stat_month=%s AND department_code IS NOT NULL
            GROUP BY department_code
            """,
            (stat_month,),
        )
        return {
            str(row["department_code"]): row.get("sales_volume") or ZERO
            for row in cursor.fetchall()
        }


def amz_sales_amount_by_department(
    stat_month: str,
) -> dict[str, Decimal] | None:
    """Aggregate current business month's AMZ actual achievement by department."""
    with db_connection() as connection, connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT COUNT(*) AS source_rows
            FROM dwd_inventory_report_amz_sales_detail
            WHERE stat_month=%s
            """,
            (stat_month,),
        )
        if int(cursor.fetchone()["source_rows"] or 0) == 0:
            return None
        cursor.execute(
            """
            SELECT department_code,COALESCE(SUM(amount),0) AS sales_amount
            FROM dwd_inventory_report_amz_sales_detail
            WHERE stat_month=%s AND department_code IS NOT NULL
            GROUP BY department_code
            """,
            (stat_month,),
        )
        return {
            str(row["department_code"]): row.get("sales_amount") or ZERO
            for row in cursor.fetchall()
        }


def ebay_sales_amount(stat_month: str) -> Decimal | None:
    """Return current business month's uploaded eBay actual achievement."""
    with db_connection() as connection, connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT COUNT(*) AS source_rows,
                   COALESCE(SUM(amount),0) AS sales_amount
            FROM dwd_inventory_report_ebay_sales_detail
            WHERE stat_month=%s
            """,
            (stat_month,),
        )
        row = cursor.fetchone()
        if not row or int(row.get("source_rows") or 0) == 0:
            return None
        return row.get("sales_amount") or ZERO


def ebay_sales_volume(stat_month: str) -> Decimal | None:
    """Sum eBay quantity by payment time; no source rows is represented by None."""
    database = _source_database()
    with db_connection() as connection, connection.cursor() as cursor:
        cursor.execute(
            f"""
            SELECT COUNT(*) AS source_rows,
                   COALESCE(SUM(COALESCE(quantity,0)),0) AS sales_volume
            FROM `{database}`.`ebay_sales`
            WHERE payment_time >= STR_TO_DATE(CONCAT(%s,'-01'), '%%Y-%%m-%%d')
              AND payment_time < DATE_ADD(
                    STR_TO_DATE(CONCAT(%s,'-01'), '%%Y-%%m-%%d'),
                    INTERVAL 1 MONTH
                  )
            """,
            (stat_month, stat_month),
        )
        row = cursor.fetchone()
        if not row or int(row.get("source_rows") or 0) == 0:
            return None
        return row.get("sales_volume") or 0


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
        raise ValueError("source_type必须是fba、overseas、local或ebay_sales")
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
            elif source in {"overseas", "local"}:
                where.append(
                    "(seller_name LIKE %s OR ware_house_name LIKE %s OR "
                    "sku LIKE %s OR fnsku LIKE %s OR product_name LIKE %s)"
                )
                params.extend([value] * 5)
            else:
                where.append(
                    "(sku LIKE %s OR brand_code LIKE %s OR "
                    "principal_name LIKE %s)"
                )
                params.extend([value] * 3)
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
