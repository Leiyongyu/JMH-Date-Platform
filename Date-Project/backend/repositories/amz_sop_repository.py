from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from backend.database import db_connection
from backend.repositories.performance_repository import shop_table_sql


def shop_map() -> dict[str, str]:
    with db_connection() as connection:
        with connection.cursor() as cursor:
            table = shop_table_sql(cursor)
            cursor.execute(
                f"""
                SELECT CAST(sid AS CHAR) AS sid, store_name
                FROM {table}
                WHERE sid IS NOT NULL AND sid <> ''
                  AND platform_code = '10001'
                """
            )
            return {
                str(row["sid"]): str(row.get("store_name") or "").strip()
                for row in cursor.fetchall()
            }


def sales_date_bounds() -> tuple[date | None, date | None]:
    with db_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT MIN(period_start) AS min_date, MAX(period_end) AS max_date "
                "FROM dwd_amz_sop_sales_daily"
            )
            row = cursor.fetchone() or {}
            return row.get("min_date"), row.get("max_date")


def source_table_status() -> dict[str, bool]:
    """Return whether both incremental source tables already contain data."""
    with db_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    EXISTS(SELECT 1 FROM ods_amz_sop_sales_daily LIMIT 1) AS sales_ready,
                    EXISTS(SELECT 1 FROM ods_amz_sop_after_sales LIMIT 1) AS after_sales_ready
                """
            )
            row = cursor.fetchone() or {}
            return {
                "sales_ready": bool(row.get("sales_ready")),
                "after_sales_ready": bool(row.get("after_sales_ready")),
            }


def replace_sales_period(
    period_start: date,
    period_end: date,
    ods_rows: list[dict[str, Any]],
    dwd_rows: list[dict[str, Any]],
) -> dict[str, int]:
    with db_connection() as connection:
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT COUNT(*) AS total FROM ods_amz_sop_sales_daily "
                    "WHERE period_start=%s AND period_end=%s",
                    (period_start, period_end),
                )
                old_ods = int(cursor.fetchone()["total"])
                cursor.execute(
                    "SELECT COUNT(*) AS total FROM dwd_amz_sop_sales_daily "
                    "WHERE period_start=%s AND period_end=%s",
                    (period_start, period_end),
                )
                old_dwd = int(cursor.fetchone()["total"])
                cursor.execute(
                    "DELETE FROM ods_amz_sop_sales_daily "
                    "WHERE period_start=%s AND period_end=%s",
                    (period_start, period_end),
                )
                cursor.execute(
                    "DELETE FROM dwd_amz_sop_sales_daily "
                    "WHERE period_start=%s AND period_end=%s",
                    (period_start, period_end),
                )
                if ods_rows:
                    cursor.executemany(
                        """
                        INSERT INTO ods_amz_sop_sales_daily (
                            period_start,period_end,sid,store_name,data_source,seller_sku,local_sku,asin,
                            currency_code,volume,gross_profit,amount,refund_amount,
                            source_hash,sync_batch_id,pulled_at
                        ) VALUES (
                            %(period_start)s,%(period_end)s,%(sid)s,%(store_name)s,%(data_source)s,%(seller_sku)s,
                            %(local_sku)s,%(asin)s,%(currency_code)s,%(volume)s,%(gross_profit)s,
                            %(amount)s,%(refund_amount)s,%(source_hash)s,
                            %(sync_batch_id)s,%(pulled_at)s
                        )
                        """,
                        ods_rows,
                    )
                if dwd_rows:
                    cursor.executemany(
                        """
                        INSERT INTO dwd_amz_sop_sales_daily (
                            period_start,period_end,sid,store_name,data_source,business_sku,seller_sku,asin,
                            currency_code,volume,gross_profit,amount,refund_amount,
                            sync_batch_id
                        ) VALUES (
                            %(period_start)s,%(period_end)s,%(sid)s,%(store_name)s,%(data_source)s,%(business_sku)s,
                            %(seller_sku)s,%(asin)s,%(currency_code)s,%(volume)s,%(gross_profit)s,
                            %(amount)s,%(refund_amount)s,%(sync_batch_id)s
                        )
                        """,
                        dwd_rows,
                    )
            connection.commit()
            return {
                "old_ods_rows": old_ods,
                "old_dwd_rows": old_dwd,
                "ods_rows": len(ods_rows),
                "dwd_rows": len(dwd_rows),
            }
        except Exception:
            connection.rollback()
            raise


def replace_after_sales_orders(
    rows: list[dict[str, Any]], order_ids: list[str]
) -> int:
    """Replace every returned Amazon order as one complete item-list snapshot."""
    normalized_order_ids = sorted({str(value).strip() for value in order_ids if str(value).strip()})
    if not normalized_order_ids:
        return 0
    with db_connection() as connection:
        try:
            with connection.cursor() as cursor:
                for index in range(0, len(normalized_order_ids), 500):
                    chunk = normalized_order_ids[index:index + 500]
                    placeholders = ",".join(["%s"] * len(chunk))
                    cursor.execute(
                        f"DELETE FROM ods_amz_sop_after_sales "
                        f"WHERE amazon_order_id IN ({placeholders})",
                        chunk,
                    )
                if rows:
                    cursor.executemany(
                        """
                        INSERT INTO ods_amz_sop_after_sales (
                            source_key,amazon_order_id,sid,store_name,data_source,local_sku,msku,
                            asin,after_type,after_quantity,after_reason,return_status,
                            inventory_attributes,buyers_note,after_time,data_update_time,
                            item_identifier,md5_v2,source_hash,
                            sync_batch_id,pulled_at
                        ) VALUES (
                            %(source_key)s,%(amazon_order_id)s,%(sid)s,%(store_name)s,%(data_source)s,
                            %(local_sku)s,%(msku)s,%(asin)s,%(after_type)s,%(after_quantity)s,
                            %(after_reason)s,%(return_status)s,%(inventory_attributes)s,%(buyers_note)s,
                            %(after_time)s,%(data_update_time)s,
                            %(item_identifier)s,%(md5_v2)s,%(source_hash)s,
                            %(sync_batch_id)s,%(pulled_at)s
                        )
                        """,
                        rows,
                    )
            connection.commit()
            return len(rows)
        except Exception:
            connection.rollback()
            raise


def after_sales_rows(start_date: date, end_date: date) -> list[dict[str, Any]]:
    with db_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT * FROM ods_amz_sop_after_sales
                WHERE after_time >= %s AND after_time < DATE_ADD(%s, INTERVAL 1 DAY)
                ORDER BY amazon_order_id, COALESCE(local_sku,msku), after_time, id
                """,
                (start_date, end_date),
            )
            return list(cursor.fetchall())


def category_rules() -> list[dict[str, Any]]:
    with db_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT big_category,small_category,responsible_party,
                       classification_description,priority,rule_version
                FROM dim_amz_sop_after_sales_category
                WHERE enabled=1
                ORDER BY priority,id
                """
            )
            return list(cursor.fetchall())


def cached_classifications(hashes: list[str]) -> dict[str, dict[str, Any]]:
    if not hashes:
        return {}
    result: dict[str, dict[str, Any]] = {}
    with db_connection() as connection:
        with connection.cursor() as cursor:
            for index in range(0, len(hashes), 500):
                chunk = hashes[index:index + 500]
                placeholders = ",".join(["%s"] * len(chunk))
                cursor.execute(
                    f"SELECT * FROM dim_amz_sop_classification_cache "
                    f"WHERE classification_hash IN ({placeholders})",
                    chunk,
                )
                result.update({row["classification_hash"]: row for row in cursor.fetchall()})
    return result


def upsert_classification_cache(rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    with db_connection() as connection:
        with connection.cursor() as cursor:
            cursor.executemany(
                """
                INSERT INTO dim_amz_sop_classification_cache (
                    classification_hash,after_reason,return_status,inventory_attributes,buyers_note,
                    after_reason_zh,return_status_zh,inventory_attributes_zh,buyers_note_zh,
                    big_category,small_category,confidence,classify_method,model_name,
                    rule_version,evidence,response_json
                ) VALUES (
                    %(classification_hash)s,%(after_reason)s,%(return_status)s,
                    %(inventory_attributes)s,%(buyers_note)s,%(after_reason_zh)s,
                    %(return_status_zh)s,%(inventory_attributes_zh)s,%(buyers_note_zh)s,
                    %(big_category)s,%(small_category)s,%(confidence)s,%(classify_method)s,
                    %(model_name)s,%(rule_version)s,%(evidence)s,%(response_json)s
                )
                ON DUPLICATE KEY UPDATE
                    after_reason_zh=VALUES(after_reason_zh),return_status_zh=VALUES(return_status_zh),
                    inventory_attributes_zh=VALUES(inventory_attributes_zh),buyers_note_zh=VALUES(buyers_note_zh),
                    big_category=VALUES(big_category),small_category=VALUES(small_category),
                    confidence=VALUES(confidence),classify_method=VALUES(classify_method),
                    model_name=VALUES(model_name),rule_version=VALUES(rule_version),
                    evidence=VALUES(evidence),response_json=VALUES(response_json)
                """,
                rows,
            )
        connection.commit()


def replace_dwd_and_summary(
    start_date: date,
    end_date: date,
    dwd_rows: list[dict[str, Any]],
    summary_rows: list[dict[str, Any]],
) -> None:
    with db_connection() as connection:
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "DELETE FROM dwd_amz_sop_after_sales "
                    "WHERE after_time >= %s AND after_time < DATE_ADD(%s, INTERVAL 1 DAY)",
                    (start_date, end_date),
                )
                if dwd_rows:
                    cursor.executemany(
                        """
                        INSERT INTO dwd_amz_sop_after_sales (
                            source_key,amazon_order_id,sid,store_name,data_source,business_sku,msku,
                            asin,after_type,coexist_flag,after_quantity,after_reason,return_status,
                            inventory_attributes,buyers_note,after_reason_zh,return_status_zh,
                            inventory_attributes_zh,buyers_note_zh,after_sales_note,big_category,
                            small_category,classify_method,confidence,merged_from_source_key,
                            after_time,data_update_time,sync_batch_id
                        ) VALUES (
                            %(source_key)s,%(amazon_order_id)s,%(sid)s,%(store_name)s,%(data_source)s,
                            %(business_sku)s,%(msku)s,%(asin)s,%(after_type)s,%(coexist_flag)s,
                            %(after_quantity)s,%(after_reason)s,%(return_status)s,
                            %(inventory_attributes)s,%(buyers_note)s,%(after_reason_zh)s,
                            %(return_status_zh)s,%(inventory_attributes_zh)s,%(buyers_note_zh)s,
                            %(after_sales_note)s,%(big_category)s,%(small_category)s,
                            %(classify_method)s,%(confidence)s,%(merged_from_source_key)s,
                            %(after_time)s,%(data_update_time)s,%(sync_batch_id)s
                        )
                        """,
                        dwd_rows,
                    )
                cursor.execute(
                    "DELETE FROM dws_amz_sop_after_sales_summary "
                    "WHERE period_start <= %s AND period_end >= %s",
                    (end_date, start_date),
                )
                _insert_summary_rows(cursor, summary_rows)
            connection.commit()
        except Exception:
            connection.rollback()
            raise


def replace_summary_period(
    start_date: date,
    end_date: date,
    summary_rows: list[dict[str, Any]],
) -> None:
    """Replace one on-demand summary range without touching classified details."""
    with db_connection() as connection:
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "DELETE FROM dws_amz_sop_after_sales_summary "
                    "WHERE period_start=%s AND period_end=%s",
                    (start_date, end_date),
                )
                _insert_summary_rows(cursor, summary_rows)
            connection.commit()
        except Exception:
            connection.rollback()
            raise


def _insert_summary_rows(cursor, summary_rows: list[dict[str, Any]]) -> None:
    if not summary_rows:
        return
    cursor.executemany(
        """
        INSERT INTO dws_amz_sop_after_sales_summary (
            period_start,period_end,big_category,small_category,business_sku,
            order_count,order_numbers,source_after_quantity_text,
            source_sales_volume_text,after_quantity,sales_volume,after_sales_rate,
            sync_batch_id,generated_at
        ) VALUES (
            %(period_start)s,%(period_end)s,%(big_category)s,%(small_category)s,
            %(business_sku)s,%(order_count)s,%(order_numbers)s,
            %(source_after_quantity_text)s,%(source_sales_volume_text)s,
            %(after_quantity)s,%(sales_volume)s,%(after_sales_rate)s,
            %(sync_batch_id)s,%(generated_at)s
        )
        """,
        summary_rows,
    )


def sales_volume_by_sku_source(
    start_date: date, end_date: date, batch_id: str
) -> dict[tuple[str, str], Decimal]:
    with db_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT business_sku,data_source,SUM(volume) AS volume
                FROM dwd_amz_sop_sales_daily
                WHERE period_start=%s AND period_end=%s AND sync_batch_id=%s
                GROUP BY business_sku,data_source
                """,
                (start_date, end_date, batch_id),
            )
            return {
                (row["business_sku"], row["data_source"]): Decimal(str(row["volume"] or 0))
                for row in cursor.fetchall()
            }


def latest_sales_batch_for_period(
    start_date: date, end_date: date
) -> str | None:
    """Return an existing exact-range sales snapshot for a local summary rebuild."""
    with db_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT sync_batch_id
                FROM dwd_amz_sop_sales_daily
                WHERE period_start=%s AND period_end=%s
                ORDER BY update_time DESC,id DESC LIMIT 1
                """,
                (start_date, end_date),
            )
            row = cursor.fetchone()
            return str(row["sync_batch_id"]) if row else None


def processed_after_sales_rows(
    start_date: date, end_date: date
) -> list[dict[str, Any]]:
    with db_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT * FROM dwd_amz_sop_after_sales
                WHERE after_time >= %s
                  AND after_time < DATE_ADD(%s, INTERVAL 1 DAY)
                ORDER BY amazon_order_id,business_sku,after_time,id
                """,
                (start_date, end_date),
            )
            return list(cursor.fetchall())


def summary_period_exists(
    start_date: date, end_date: date, metric_version: str | None = None
) -> bool:
    version_sql = " AND sync_batch_id LIKE %s" if metric_version else ""
    params: list[Any] = [start_date, end_date]
    if metric_version:
        params.append(f"{metric_version}-%")
    with db_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT EXISTS(
                    SELECT 1 FROM dws_amz_sop_after_sales_summary
                    WHERE period_start=%s AND period_end=%s{version_sql} LIMIT 1
                ) AS ready
                """,
                params,
            )
            return bool((cursor.fetchone() or {}).get("ready"))


def latest_period() -> tuple[date, date] | None:
    with db_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT period_start,period_end
                FROM dws_amz_sop_after_sales_summary
                ORDER BY period_end DESC,period_start DESC LIMIT 1
                """
            )
            row = cursor.fetchone()
            return (row["period_start"], row["period_end"]) if row else None


def periods(limit: int = 24) -> list[dict[str, Any]]:
    with db_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT period_start,period_end,MAX(generated_at) AS generated_at,
                       COUNT(*) AS row_count,SUM(after_quantity) AS after_quantity
                FROM dws_amz_sop_after_sales_summary
                GROUP BY period_start,period_end
                ORDER BY period_end DESC,period_start DESC LIMIT %s
                """,
                (max(1, min(limit, 100)),),
            )
            return list(cursor.fetchall())


def summary_page(
    start_date: date | None,
    end_date: date | None,
    big_category: str | None,
    small_category: str | None,
    sku: str | None,
    page: int,
    page_size: int,
) -> dict[str, Any]:
    if not start_date or not end_date:
        latest = latest_period()
        if not latest:
            return {"period_start": None, "period_end": None, "items": [], "total": 0}
        start_date, end_date = latest
    where = ["period_start=%s", "period_end=%s"]
    params: list[Any] = [start_date, end_date]
    if big_category:
        where.append("big_category=%s")
        params.append(big_category)
    if small_category:
        where.append("small_category LIKE %s")
        params.append(f"%{small_category.strip()}%")
    if sku:
        where.append("business_sku LIKE %s")
        params.append(f"%{sku.strip()}%")
    where_sql = " AND ".join(where)
    offset = (max(page, 1) - 1) * page_size
    with db_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                f"SELECT COUNT(*) AS total FROM dws_amz_sop_after_sales_summary WHERE {where_sql}",
                params,
            )
            total = int(cursor.fetchone()["total"])
            cursor.execute(
                f"""
                SELECT * FROM dws_amz_sop_after_sales_summary
                WHERE {where_sql}
                ORDER BY after_quantity DESC, business_sku, small_category
                LIMIT %s OFFSET %s
                """,
                [*params, page_size, offset],
            )
            items = list(cursor.fetchall())
            cursor.execute(
                f"""
                SELECT COALESCE(SUM(after_quantity),0) AS after_quantity,
                       COUNT(DISTINCT business_sku) AS sku_count,
                       COUNT(DISTINCT big_category) AS category_count
                FROM dws_amz_sop_after_sales_summary WHERE {where_sql}
                """,
                params,
            )
            totals = cursor.fetchone()
    return {
        "period_start": start_date,
        "period_end": end_date,
        "items": items,
        "total": total,
        "summary": totals,
    }


def summary_all(start_date: date, end_date: date) -> list[dict[str, Any]]:
    with db_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT * FROM dws_amz_sop_after_sales_summary
                WHERE period_start=%s AND period_end=%s
                ORDER BY FIELD(big_category,'补偿','客户自身原因','物流商问题','不适配',
                    '产品质量问题','国内物流部','其他','供应商加强包装','海外仓问题','退货已损坏'),
                    after_quantity DESC,business_sku
                """,
                (start_date, end_date),
            )
            return list(cursor.fetchall())


def summary_filtered(
    start_date: date,
    end_date: date,
    big_category: str | None,
    small_category: str | None,
    sku: str | None,
    selected_ids: list[int] | None = None,
    selected_skus: list[str] | None = None,
) -> list[dict[str, Any]]:
    where = ["period_start=%s", "period_end=%s"]
    params: list[Any] = [start_date, end_date]
    if big_category:
        where.append("big_category=%s")
        params.append(big_category)
    if small_category:
        where.append("small_category LIKE %s")
        params.append(f"%{small_category.strip()}%")
    if sku:
        where.append("business_sku LIKE %s")
        params.append(f"%{sku.strip()}%")
    if selected_ids:
        where.append(f"id IN ({','.join(['%s'] * len(selected_ids))})")
        params.extend(selected_ids)
    if selected_skus:
        where.append(f"business_sku IN ({','.join(['%s'] * len(selected_skus))})")
        params.extend(selected_skus)
    with db_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT * FROM dws_amz_sop_after_sales_summary
                WHERE {' AND '.join(where)}
                ORDER BY after_quantity DESC,business_sku,small_category
                """,
                params,
            )
            return list(cursor.fetchall())
