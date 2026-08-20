from __future__ import annotations

import json
from collections.abc import Iterable
from contextlib import contextmanager
from datetime import datetime
from decimal import Decimal
from typing import Any

from pymysql.connections import Connection

from backend.config import settings
from backend.database import db_connection


RANKING_TABLES = {
    "amazon": "dws_amz_performance_ranking",
    "ebay": "dws_ebay_performance_ranking",
    "combined": "dws_combined_performance_ranking",
}


@contextmanager
def performance_connection():
    with db_connection() as connection:
        yield connection


@contextmanager
def named_lock(lock_name: str):
    """Hold a MySQL advisory lock for the lifetime of one connection."""
    with db_connection() as connection:
        acquired = False
        with connection.cursor() as cursor:
            cursor.execute("SELECT GET_LOCK(%s, 0) AS acquired", (lock_name,))
            row = cursor.fetchone()
            acquired = bool(row and int(row["acquired"] or 0) == 1)
        try:
            yield acquired
        finally:
            if acquired:
                with connection.cursor() as cursor:
                    cursor.execute("SELECT RELEASE_LOCK(%s)", (lock_name,))


def latest_ranking_month(platform: str) -> str | None:
    table = _ranking_table(platform)
    with db_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(f"SELECT MAX(stat_month) AS stat_month FROM {table}")
            row = cursor.fetchone()
    return row["stat_month"] if row else None


def list_rankings(
    platform: str,
    stat_month: str | None,
    principal_name: str | None,
    order_by: str,
    order: str,
    page: int,
    page_size: int,
) -> dict[str, Any]:
    table = _ranking_table(platform)
    month = stat_month or latest_ranking_month(platform)
    if not month:
        return {"stat_month": None, "items": [], "total": 0}

    order_column = "gross_profit" if order_by == "gross_profit" else "net_sales_amount"
    direction = "ASC" if order.lower() == "asc" else "DESC"
    where = ["stat_month = %s"]
    params: list[Any] = [month]
    if principal_name:
        where.append("principal_name LIKE %s")
        params.append(f"%{principal_name}%")
    where_sql = " AND ".join(where)
    offset = (page - 1) * page_size

    with db_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(f"SELECT COUNT(*) AS total FROM {table} WHERE {where_sql}", params)
            total = int(cursor.fetchone()["total"])
            cursor.execute(
                f"""
                SELECT *
                FROM {table}
                WHERE {where_sql}
                ORDER BY {order_column} {direction}, id ASC
                LIMIT %s OFFSET %s
                """,
                [*params, page_size, offset],
            )
            rows = cursor.fetchall()
    return {"stat_month": month, "items": rows, "total": total}


def months_status(limit: int = 12) -> list[dict[str, Any]]:
    with db_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT stat_month FROM dwd_amz_monthly_order_profit
                UNION
                SELECT stat_month FROM dwd_ebay_monthly_profit
                UNION
                SELECT stat_month FROM dws_combined_performance_ranking
                ORDER BY stat_month DESC
                LIMIT %s
                """,
                (limit,),
            )
            months = [row["stat_month"] for row in cursor.fetchall()]
            result = []
            for month in months:
                result.append(
                    {
                        "stat_month": month,
                        "amazon_ready": _exists(cursor, "dws_amz_performance_ranking", month),
                        "ebay_ready": _exists(cursor, "dws_ebay_performance_ranking", month),
                        "combined_ready": _exists(cursor, "dws_combined_performance_ranking", month),
                        "partial": _combined_partial(cursor, month),
                        "last_refreshed_at": _last_refresh_time(cursor, month),
                    }
                )
    return result


def get_amz_profit_rows(connection: Connection, stat_month: str) -> list[dict]:
    with connection.cursor() as cursor:
        table_name = _shop_table_name(cursor)
        cursor.execute(
            f"""
            SELECT p.*, s.store_name
            FROM dwd_amz_monthly_order_profit p
            LEFT JOIN {table_name} s ON CAST(s.sid AS CHAR) = CAST(p.sid AS CHAR)
            WHERE p.stat_month = %s
            """,
            (stat_month,),
        )
        return list(cursor.fetchall())


def count_amz_profit_rows(connection: Connection, stat_month: str) -> int:
    return _count(connection, "dwd_amz_monthly_order_profit", stat_month)


def count_ebay_profit_rows(connection: Connection, stat_month: str) -> int:
    return _count(connection, "dwd_ebay_monthly_profit", stat_month)


def get_owner_rules(connection: Connection, platform: str, stat_month: str) -> dict[tuple[str, str, str], str]:
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT group_code, rule_type, match_key, principal_name
            FROM dwd_performance_owner_rule
            WHERE platform = %s AND stat_month = %s
            """,
            (platform, stat_month),
        )
        rows = cursor.fetchall()
    return {
        (
            (row["group_code"] or "").upper(),
            (row["rule_type"] or "").upper(),
            row["match_key"] or "",
        ): normalize_principal(row["principal_name"])
        for row in rows
    }


def replace_amz_ranking(connection: Connection, stat_month: str, rows: list[dict]) -> None:
    with connection.cursor() as cursor:
        cursor.execute("DELETE FROM dws_amz_performance_ranking WHERE stat_month = %s", (stat_month,))
        if rows:
            cursor.executemany(
                """
                INSERT INTO dws_amz_performance_ranking (
                    stat_month, principal_name, gross_profit, amount, refund_amount,
                    net_sales_amount, source_rows, matched_rows, unmatched_rows, missing_shop_rows
                ) VALUES (
                    %(stat_month)s, %(principal_name)s, %(gross_profit)s, %(amount)s,
                    %(refund_amount)s, %(net_sales_amount)s, %(source_rows)s,
                    %(matched_rows)s, %(unmatched_rows)s, %(missing_shop_rows)s
                )
                """,
                rows,
            )


def refresh_ebay_ranking_sql(connection: Connection, stat_month: str) -> dict[str, int]:
    with connection.cursor() as cursor:
        source_rows = _count_with_cursor(cursor, "dwd_ebay_monthly_profit", stat_month)
        cursor.execute("DELETE FROM dws_ebay_performance_ranking WHERE stat_month = %s", (stat_month,))
        cursor.execute(
            """
            INSERT INTO dws_ebay_performance_ranking (
                stat_month, principal_name, gross_profit, sales_amount, refund_amount,
                net_sales_amount, source_rows, matched_rows, unmatched_rows
            )
            SELECT
                ranked.stat_month,
                ranked.principal_name,
                SUM(ranked.gross_profit),
                SUM(ranked.sales_amount),
                SUM(ranked.refund_amount),
                SUM(ranked.net_sales_amount),
                COUNT(*),
                SUM(ranked.matched_flag),
                SUM(ranked.unmatched_flag)
            FROM (
                SELECT
                    p.stat_month,
                    p.gross_profit,
                    p.sales_amount,
                    p.refund_amount,
                    p.net_sales_amount,
                    CASE
                        WHEN p.brand_code IN ('FLL', 'LEJ') THEN '方黎力'
                        WHEN p.brand_code = 'CL' THEN '陈丽'
                        WHEN r.principal_name IS NULL OR TRIM(r.principal_name) IN ('', '待定', '待到') THEN '未分配'
                        ELSE TRIM(r.principal_name)
                    END AS principal_name,
                    CASE
                        WHEN p.brand_code IN ('FLL', 'LEJ', 'CL') THEN 1
                        WHEN r.principal_name IS NOT NULL AND TRIM(r.principal_name) NOT IN ('', '待定', '待到') THEN 1
                        ELSE 0
                    END AS matched_flag,
                    CASE
                        WHEN p.brand_code IN ('FLL', 'LEJ', 'CL') THEN 0
                        WHEN r.principal_name IS NULL OR TRIM(r.principal_name) IN ('', '待定', '待到') THEN 1
                        ELSE 0
                    END AS unmatched_flag
                FROM dwd_ebay_monthly_profit p
                LEFT JOIN dwd_performance_owner_rule r
                    ON r.platform = 'ebay'
                    AND r.stat_month = p.stat_month
                    AND r.rule_type = 'EBAY_BRAND'
                    AND r.match_key = p.brand_code
                WHERE p.stat_month = %s
            ) ranked
            GROUP BY ranked.stat_month, ranked.principal_name
            """,
            (stat_month,),
        )
        ranking_rows = cursor.rowcount
    return {"source_rows": source_rows, "ranking_rows": ranking_rows}


def refresh_combined_ranking_sql(connection: Connection, stat_month: str, partial: bool) -> int:
    with connection.cursor() as cursor:
        cursor.execute("DELETE FROM dws_combined_performance_ranking WHERE stat_month = %s", (stat_month,))
        cursor.execute(
            """
            INSERT INTO dws_combined_performance_ranking (
                stat_month, principal_name, gross_profit, net_sales_amount,
                amz_gross_profit, amz_net_sales_amount, ebay_gross_profit,
                ebay_net_sales_amount, partial
            )
            SELECT
                stat_month,
                principal_name,
                SUM(gross_profit),
                SUM(net_sales_amount),
                SUM(amz_gross_profit),
                SUM(amz_net_sales_amount),
                SUM(ebay_gross_profit),
                SUM(ebay_net_sales_amount),
                %s
            FROM (
                SELECT stat_month, principal_name, gross_profit, net_sales_amount,
                       gross_profit AS amz_gross_profit, net_sales_amount AS amz_net_sales_amount,
                       0 AS ebay_gross_profit, 0 AS ebay_net_sales_amount
                FROM dws_amz_performance_ranking
                WHERE stat_month = %s
                UNION ALL
                SELECT stat_month, principal_name, gross_profit, net_sales_amount,
                       0 AS amz_gross_profit, 0 AS amz_net_sales_amount,
                       gross_profit AS ebay_gross_profit, net_sales_amount AS ebay_net_sales_amount
                FROM dws_ebay_performance_ranking
                WHERE stat_month = %s
            ) t
            GROUP BY stat_month, principal_name
            """,
            (1 if partial else 0, stat_month, stat_month),
        )
        return cursor.rowcount


def upsert_refresh_run(connection: Connection, payload: dict[str, Any]) -> None:
    with connection.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO performance_refresh_run (
                refresh_id, stat_month, platform, status, partial, source_rows,
                matched_rows, unmatched_rows, missing_shop_rows, amz_profit_rows,
                ebay_profit_rows, amz_ranking_rows, ebay_ranking_rows,
                combined_ranking_rows, trigger_source, request_id, error_message,
                started_at, completed_at
            ) VALUES (
                %(refresh_id)s, %(stat_month)s, %(platform)s, %(status)s, %(partial)s,
                %(source_rows)s, %(matched_rows)s, %(unmatched_rows)s,
                %(missing_shop_rows)s, %(amz_profit_rows)s, %(ebay_profit_rows)s,
                %(amz_ranking_rows)s, %(ebay_ranking_rows)s, %(combined_ranking_rows)s,
                %(trigger_source)s, %(request_id)s, %(error_message)s,
                %(started_at)s, %(completed_at)s
            )
            ON DUPLICATE KEY UPDATE
                status = VALUES(status),
                partial = VALUES(partial),
                source_rows = VALUES(source_rows),
                matched_rows = VALUES(matched_rows),
                unmatched_rows = VALUES(unmatched_rows),
                missing_shop_rows = VALUES(missing_shop_rows),
                amz_profit_rows = VALUES(amz_profit_rows),
                ebay_profit_rows = VALUES(ebay_profit_rows),
                amz_ranking_rows = VALUES(amz_ranking_rows),
                ebay_ranking_rows = VALUES(ebay_ranking_rows),
                combined_ranking_rows = VALUES(combined_ranking_rows),
                error_message = VALUES(error_message),
                completed_at = VALUES(completed_at)
            """,
            payload,
        )


def insert_import_batch(connection: Connection, payload: dict[str, Any]) -> None:
    with connection.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO performance_import_batch (
                batch_id, import_type, platform, stat_month, source_file_name,
                file_hash, idempotency_key, status, total_rows, inserted_rows,
                updated_rows, skipped_rows, operator, request_id, error_message,
                started_at, completed_at
            ) VALUES (
                %(batch_id)s, %(import_type)s, %(platform)s, %(stat_month)s,
                %(source_file_name)s, %(file_hash)s, %(idempotency_key)s,
                %(status)s, %(total_rows)s, %(inserted_rows)s, %(updated_rows)s,
                %(skipped_rows)s, %(operator)s, %(request_id)s,
                %(error_message)s, %(started_at)s, %(completed_at)s
            )
            ON DUPLICATE KEY UPDATE
                batch_id = VALUES(batch_id),
                source_file_name = VALUES(source_file_name),
                idempotency_key = VALUES(idempotency_key),
                status = VALUES(status),
                total_rows = VALUES(total_rows),
                inserted_rows = VALUES(inserted_rows),
                updated_rows = VALUES(updated_rows),
                skipped_rows = VALUES(skipped_rows),
                operator = VALUES(operator),
                request_id = VALUES(request_id),
                error_message = VALUES(error_message),
                started_at = VALUES(started_at),
                completed_at = VALUES(completed_at)
            """,
            payload,
        )


def replace_ebay_profit_month(
    connection: Connection,
    stat_month: str,
    rows: list[dict[str, Any]],
    raw_rows: list[dict[str, Any]],
) -> None:
    with connection.cursor() as cursor:
        cursor.execute("DELETE FROM ods_ebay_monthly_profit_raw WHERE stat_month = %s", (stat_month,))
        cursor.execute("DELETE FROM dwd_ebay_monthly_profit WHERE stat_month = %s", (stat_month,))
        if raw_rows:
            cursor.executemany(
                """
                INSERT INTO ods_ebay_monthly_profit_raw (
                    stat_month, source_file_name, source_sheet, source_row,
                    sku, brand_code, image_url, multi_variant, gross_profit,
                    product_sales_amount, receivable_shipping_amount,
                    sales_amount, refund_amount, net_sales_amount, import_batch_id
                ) VALUES (
                    %(stat_month)s, %(source_file_name)s, %(source_sheet)s,
                    %(source_row)s, %(sku)s, %(brand_code)s, %(image_url)s,
                    %(multi_variant)s, %(gross_profit)s, %(product_sales_amount)s,
                    %(receivable_shipping_amount)s, %(sales_amount)s,
                    %(refund_amount)s, %(net_sales_amount)s, %(import_batch_id)s
                )
                """,
                raw_rows,
            )
        if rows:
            cursor.executemany(
                """
                INSERT INTO dwd_ebay_monthly_profit (
                    stat_month, sku, brand_code, image_url, multi_variant,
                    gross_profit, product_sales_amount, receivable_shipping_amount,
                    sales_amount, refund_amount, net_sales_amount, source_file_name,
                    source_sheet, source_row, import_batch_id
                ) VALUES (
                    %(stat_month)s, %(sku)s, %(brand_code)s, %(image_url)s,
                    %(multi_variant)s, %(gross_profit)s, %(product_sales_amount)s,
                    %(receivable_shipping_amount)s, %(sales_amount)s,
                    %(refund_amount)s, %(net_sales_amount)s, %(source_file_name)s,
                    %(source_sheet)s, %(source_row)s, %(import_batch_id)s
                )
                """,
                rows,
            )


def upsert_owner_rules(
    connection: Connection,
    rules: list[dict[str, Any]],
    raw_rows: list[dict[str, Any]],
) -> None:
    with connection.cursor() as cursor:
        if raw_rows:
            cursor.executemany(
                """
                INSERT INTO ods_performance_owner_rule_raw (
                    platform, stat_month, source_file_name, source_sheet, source_row,
                    group_code, rule_type, match_key, principal_name, import_batch_id
                ) VALUES (
                    %(platform)s, %(stat_month)s, %(source_file_name)s,
                    %(source_sheet)s, %(source_row)s,
                    %(group_code)s, %(rule_type)s, %(match_key)s, %(principal_name)s,
                    %(import_batch_id)s
                )
                ON DUPLICATE KEY UPDATE
                    principal_name = VALUES(principal_name),
                    source_file_name = VALUES(source_file_name),
                    source_sheet = VALUES(source_sheet),
                    source_row = VALUES(source_row),
                    import_batch_id = VALUES(import_batch_id)
                """,
                raw_rows,
            )
        if rules:
            cursor.executemany(
                """
                INSERT INTO dwd_performance_owner_rule (
                    platform, stat_month, group_code, rule_type, match_key,
                    principal_name, source_file_name, source_sheet, source_row,
                    import_batch_id
                ) VALUES (
                    %(platform)s, %(stat_month)s, %(group_code)s, %(rule_type)s,
                    %(match_key)s, %(principal_name)s, %(source_file_name)s,
                    %(source_sheet)s, %(source_row)s, %(import_batch_id)s
                )
                ON DUPLICATE KEY UPDATE
                    principal_name = VALUES(principal_name),
                    source_file_name = VALUES(source_file_name),
                    source_sheet = VALUES(source_sheet),
                    source_row = VALUES(source_row),
                    import_batch_id = VALUES(import_batch_id),
                    update_time = CURRENT_TIMESTAMP
                """,
                rules,
            )


def owner_rule_summary(platform: str, stat_month: str) -> list[dict[str, Any]]:
    with db_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT group_code, rule_type, COUNT(*) AS rule_count,
                       MAX(update_time) AS last_updated_at
                FROM dwd_performance_owner_rule
                WHERE platform = %s AND stat_month = %s
                GROUP BY group_code, rule_type
                ORDER BY group_code, rule_type
                """,
                (platform, stat_month),
            )
            return list(cursor.fetchall())


def append_amz_profit_raw(
    connection: Connection,
    raw_rows: list[dict[str, Any]],
) -> None:
    with connection.cursor() as cursor:
        if raw_rows:
            cursor.executemany(
                """
                INSERT INTO ods_lingxing_amz_order_profit_raw (
                    stat_month, sid, seller_sku, local_sku, asin, country,
                    currency_code, gross_profit, amount, refund_amount,
                    net_sales_amount, principal_names, sync_batch_id, sync_time
                ) VALUES (
                    %(stat_month)s, %(sid)s, %(seller_sku)s, %(local_sku)s,
                    %(asin)s, %(country)s, %(currency_code)s, %(gross_profit)s,
                    %(amount)s, %(refund_amount)s, %(net_sales_amount)s,
                    %(principal_names)s, %(sync_batch_id)s, %(sync_time)s
                )
                """,
                raw_rows,
            )


def replace_amz_profit_month(
    connection: Connection,
    stat_month: str,
    rows: list[dict[str, Any]],
) -> dict[str, int]:
    """Replace one complete DWD month and return exact key-level changes."""
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT sid, seller_sku
            FROM dwd_amz_monthly_order_profit
            WHERE stat_month = %s
            """,
            (stat_month,),
        )
        old_keys = {
            (str(row["sid"]), str(row["seller_sku"]))
            for row in cursor.fetchall()
        }
        new_keys = {
            (str(row["sid"]), str(row["seller_sku"]))
            for row in rows
        }
        cursor.execute(
            "DELETE FROM dwd_amz_monthly_order_profit WHERE stat_month = %s",
            (stat_month,),
        )
        if rows:
            cursor.executemany(
                """
                INSERT INTO dwd_amz_monthly_order_profit (
                    stat_month, sid, seller_sku, local_sku, asin, country, currency_code,
                    gross_profit, amount, refund_amount, net_sales_amount, principal_names,
                    sync_batch_id, sync_time
                ) VALUES (
                    %(stat_month)s, %(sid)s, %(seller_sku)s, %(local_sku)s, %(asin)s,
                    %(country)s, %(currency_code)s, %(gross_profit)s, %(amount)s,
                    %(refund_amount)s, %(net_sales_amount)s, %(principal_names)s,
                    %(sync_batch_id)s, %(sync_time)s
                )
                """,
                rows,
            )
    return {
        "inserted_rows": len(new_keys - old_keys),
        "updated_rows": len(new_keys & old_keys),
        "deleted_rows": len(old_keys - new_keys),
        "dwd_rows": len(new_keys),
    }


def amazon_shop_sids() -> list[str]:
    with db_connection() as connection:
        with connection.cursor() as cursor:
            table_name = _shop_table_name(cursor)
            cursor.execute(
                f"""
                SELECT DISTINCT CAST(sid AS CHAR) AS sid
                FROM {table_name}
                WHERE sid IS NOT NULL AND sid <> ''
                  AND (platform_code = '10001' OR platform_code IS NULL OR platform_code = '')
                """
            )
            return [str(row["sid"]) for row in cursor.fetchall() if row.get("sid")]


def shop_table_sql(cursor) -> str:
    return _shop_table_name(cursor)


def scheduler_tasks() -> list[dict[str, Any]]:
    with db_connection() as connection:
        _ensure_default_scheduler_task(connection)
        connection.commit()
        with connection.cursor() as cursor:
            cursor.execute("SELECT * FROM scheduler_task ORDER BY task_code")
            return list(cursor.fetchall())


def scheduler_runs(task_code: str, limit: int = 50) -> list[dict[str, Any]]:
    with db_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT * FROM scheduler_task_run
                WHERE task_code = %s
                ORDER BY started_at DESC
                LIMIT %s
                """,
                (task_code, limit),
            )
            return list(cursor.fetchall())


def update_scheduler_task_enabled(task_code: str, enabled: bool) -> None:
    with db_connection() as connection:
        _ensure_default_scheduler_task(connection)
        with connection.cursor() as cursor:
            cursor.execute(
                "UPDATE scheduler_task SET enabled = %s WHERE task_code = %s",
                (1 if enabled else 0, task_code),
            )
        connection.commit()


def insert_scheduler_run(connection: Connection, payload: dict[str, Any]) -> None:
    with connection.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO scheduler_task_run (
                run_id, task_code, status, stat_month, trigger_type, source_rows,
                sync_batch_id, extract_rows, ods_rows, inserted_rows, updated_rows,
                deleted_rows, skipped_rows, amz_ranking_rows,
                combined_ranking_rows, etl_stage, error_message, request_id,
                started_at, completed_at
            ) VALUES (
                %(run_id)s, %(task_code)s, %(status)s, %(stat_month)s,
                %(trigger_type)s, %(source_rows)s, %(sync_batch_id)s,
                %(extract_rows)s, %(ods_rows)s, %(inserted_rows)s,
                %(updated_rows)s, %(deleted_rows)s, %(skipped_rows)s,
                %(amz_ranking_rows)s, %(combined_ranking_rows)s,
                %(etl_stage)s, %(error_message)s, %(request_id)s,
                %(started_at)s, %(completed_at)s
            )
            ON DUPLICATE KEY UPDATE
                status = VALUES(status),
                stat_month = VALUES(stat_month),
                source_rows = VALUES(source_rows),
                sync_batch_id = VALUES(sync_batch_id),
                extract_rows = VALUES(extract_rows),
                ods_rows = VALUES(ods_rows),
                inserted_rows = VALUES(inserted_rows),
                updated_rows = VALUES(updated_rows),
                deleted_rows = VALUES(deleted_rows),
                skipped_rows = VALUES(skipped_rows),
                amz_ranking_rows = VALUES(amz_ranking_rows),
                combined_ranking_rows = VALUES(combined_ranking_rows),
                etl_stage = VALUES(etl_stage),
                error_message = VALUES(error_message),
                completed_at = VALUES(completed_at)
            """,
            payload,
        )


def _ensure_default_scheduler_task(connection: Connection) -> None:
    with connection.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO scheduler_task (
                task_code, task_name, cron_expression, enabled, description
            ) VALUES (
                'amz_monthly_order_profit_sync',
                'Amazon月度完整订单利润同步',
                '0 0 22 4 * ?',
                1,
                '每月4日22:00拉取上一个完整自然月的领星Amazon订单利润'
            )
            ON DUPLICATE KEY UPDATE
                task_name = VALUES(task_name),
                cron_expression = VALUES(cron_expression),
                description = VALUES(description)
            """
        )
        cursor.execute(
            """
            INSERT INTO scheduler_task (
                task_code, task_name, cron_expression, enabled, description
            ) VALUES (
                'monthly_inventory_report_opening_inventory_fill',
                '月度库存次月月初库存填充',
                '0 0 23 2 * ?',
                1,
                '每月2日23:00将上月海外仓与FBA仓期末库存数量之和回填为次月月初库存数量'
            )
            ON DUPLICATE KEY UPDATE
                task_name = VALUES(task_name),
                cron_expression = VALUES(cron_expression),
                description = VALUES(description)
            """
        )
        cursor.execute(
            """
            INSERT INTO scheduler_task (
                task_code, task_name, cron_expression, enabled, description
            ) VALUES (
                'monthly_inventory_report_sales_volume_sync',
                '月度库存实际达成及销量填充',
                '0 0 6 2 * ?',
                1,
                '每月2日06:00拉取上个完整自然月Amazon订单利润amount和volume，覆盖ODS并重建实际达成及销量DWD；eBay销量由ebay_sales按payment_time实时汇总'
            )
            ON DUPLICATE KEY UPDATE
                task_name = VALUES(task_name),
                cron_expression = VALUES(cron_expression),
                description = VALUES(description)
            """
        )
        cursor.execute(
            """
            INSERT INTO scheduler_task (
                task_code, task_name, cron_expression, enabled, description
            ) VALUES (
                'monthly_inventory_report_source_sync',
                '月度库存统计表数据拉取',
                '0 0 6 1 * ?',
                1,
                '每月1日拉取上月FBA、海外仓、本地仓数据，每月2日06:00拉取上月Amazon实际达成和销量，每月2日23:00回填次月月初库存'
            )
            ON DUPLICATE KEY UPDATE
                task_name = VALUES(task_name),
                cron_expression = VALUES(cron_expression),
                description = VALUES(description)
            """
        )
        cursor.execute(
            """
            INSERT INTO scheduler_task (
                task_code, task_name, cron_expression, enabled, description
            ) VALUES (
                'amz_sop_after_sales_chain',
                'AMZ-SOP售后链路',
                '0 30 22 ? * SUN',
                1,
                '每周日22:30执行；源表为空拉取最近365天，否则增量刷新最近7天；完成清洗、AI分类及售后率汇总'
            )
            ON DUPLICATE KEY UPDATE
                task_name = VALUES(task_name),
                cron_expression = VALUES(cron_expression),
                description = VALUES(description)
            """
        )
        cursor.execute(
            """
            INSERT INTO scheduler_task (
                task_code, task_name, cron_expression, enabled, description
            ) VALUES (
                'amz_fba_inventory_snapshot_sync',
                'AMZ FBA与eBay海外仓库存库龄月度快照',
                '0 30 22 1 * ?',
                1,
                '每月1日22:30由Java先刷新谷仓eBay库龄和领星产品成本，再拉取当前月FBA库存并重建滞销清货汇总'
            )
            ON DUPLICATE KEY UPDATE
                task_name = VALUES(task_name),
                cron_expression = VALUES(cron_expression),
                description = VALUES(description)
            """
        )


def normalize_principal(value: Any) -> str:
    text = str(value or "").replace("\u3000", " ").replace("\xa0", " ").strip()
    return "未分配" if text in {"", "待定", "待到"} else text


def decimal_zero() -> Decimal:
    return Decimal("0")


def json_dumps(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, default=str)


def _ranking_table(platform: str) -> str:
    try:
        return RANKING_TABLES[platform]
    except KeyError as exc:
        raise ValueError(f"不支持的平台: {platform}") from exc


def _exists(cursor, table: str, stat_month: str) -> bool:
    cursor.execute(f"SELECT 1 FROM {table} WHERE stat_month = %s LIMIT 1", (stat_month,))
    return cursor.fetchone() is not None


def _combined_partial(cursor, stat_month: str) -> bool:
    cursor.execute(
        "SELECT MAX(partial) AS partial FROM dws_combined_performance_ranking WHERE stat_month = %s",
        (stat_month,),
    )
    row = cursor.fetchone()
    return bool(row and row["partial"])


def _last_refresh_time(cursor, stat_month: str):
    cursor.execute(
        """
        SELECT MAX(completed_at) AS completed_at
        FROM performance_refresh_run
        WHERE stat_month = %s AND status = 'completed'
        """,
        (stat_month,),
    )
    row = cursor.fetchone()
    return row["completed_at"] if row else None


def _count(connection: Connection, table: str, stat_month: str) -> int:
    with connection.cursor() as cursor:
        return _count_with_cursor(cursor, table, stat_month)


def _count_with_cursor(cursor, table: str, stat_month: str) -> int:
    cursor.execute(f"SELECT COUNT(*) AS total FROM {table} WHERE stat_month = %s", (stat_month,))
    return int(cursor.fetchone()["total"])


def _shop_table_name(cursor) -> str:
    if _table_exists(cursor, None, "shop_list"):
        return "shop_list"
    source_database = settings.shop_source_database.strip()
    if source_database and _table_exists(cursor, source_database, "shop_list"):
        escaped = source_database.replace("`", "``")
        return f"`{escaped}`.shop_list"
    raise ValueError(
        "未找到店铺表 shop_list；请在当前库创建 shop_list，或设置 SHOP_SOURCE_DATABASE 指向包含 shop_list 的库"
    )


def _table_exists(cursor, database: str | None, table: str) -> bool:
    if database:
        cursor.execute(
            """
            SELECT 1
            FROM information_schema.TABLES
            WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s
            LIMIT 1
            """,
            (database, table),
        )
    else:
        cursor.execute(
            """
            SELECT 1
            FROM information_schema.TABLES
            WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s
            LIMIT 1
            """,
            (table,),
        )
    return cursor.fetchone() is not None
