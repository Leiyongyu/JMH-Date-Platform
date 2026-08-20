from __future__ import annotations

from contextlib import contextmanager
from datetime import date
from decimal import Decimal
from typing import Any

from backend.database import db_connection


RAW_ORDER_COLUMNS = (
    "source_key", "data_kind", "source_file", "source_sheet", "source_row_no",
    "platform_order_no", "shipping_status", "package_status", "exception_status",
    "logistics_channel", "tracking_no", "payment_time", "marked_ship_time",
    "platform_name", "currency_code", "receivable_goods", "receivable_shipping",
    "platform_fee", "insurance_amount", "transfer_fee", "paypal_receipt", "customer_id",
    "recipient", "customer_email", "recipient_phone1", "recipient_phone2",
    "recipient_country", "recipient_state", "recipient_city", "recipient_postal_code",
    "recipient_address1", "recipient_address2", "recipient_address3",
    "recipient_alt_address", "recipient_house_no", "inventory_sku", "sku_status",
    "purchase_quantity", "allocated_quantity", "paypal_transaction_no", "salesperson",
    "exchange_rate", "original_currency_income", "country_cn", "country_en",
    "import_batch_id",
)

HISTORY_COLUMNS = (
    "source_key", "order_no", "payment_time", "refund_time", "product_title",
    "after_quantity", "product_sku", "small_category", "big_category", "data_source",
    "platform_name", "after_sales_note", "source_file", "source_sheet", "source_row_no",
    "import_batch_id",
)

HISTORY_SALES_COLUMNS = (
    "source_key", "sale_month", "data_source", "product_sku", "sales_quantity",
    "source_file", "source_sheet", "source_row_no", "import_batch_id",
)

AFTER_SALES_COLUMNS = (
    "source_key", "source_kind", "order_no", "payment_time", "after_time",
    "product_title", "after_quantity", "business_sku", "after_type", "big_category",
    "small_category", "data_source", "platform_name", "after_sales_note",
    "classify_method", "confidence", "import_batch_id",
)


@contextmanager
def import_lock(data_kind: str, timeout_seconds: int = 60):
    """Serialize imports of the same kind across processes."""
    lock_name = f"jmh:ebay-sop:{data_kind.lower()}"
    with db_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT GET_LOCK(%s,%s) AS acquired", (lock_name, timeout_seconds))
            acquired = (cursor.fetchone() or {}).get("acquired")
        if acquired != 1:
            raise TimeoutError(f"eBay {data_kind} 导入任务正在执行，请稍后重试")
        try:
            yield
        finally:
            with connection.cursor() as cursor:
                cursor.execute("SELECT RELEASE_LOCK(%s)", (lock_name,))


def existing_order_numbers(data_kind: str, order_numbers: set[str]) -> set[str]:
    values = sorted(value for value in order_numbers if value)
    if not values:
        return set()
    result: set[str] = set()
    with db_connection() as connection:
        with connection.cursor() as cursor:
            for offset in range(0, len(values), 500):
                chunk = values[offset:offset + 500]
                placeholders = ",".join(["%s"] * len(chunk))
                cursor.execute(
                    f"SELECT DISTINCT platform_order_no FROM ods_ebay_sop_order_raw "
                    f"WHERE data_kind=%s AND platform_order_no IN ({placeholders})",
                    (data_kind, *chunk),
                )
                result.update(
                    str(row["platform_order_no"])
                    for row in cursor.fetchall()
                    if row.get("platform_order_no")
                )
                if data_kind == "AFTER_SALES":
                    cursor.execute(
                        f"SELECT DISTINCT order_no FROM ods_ebay_sop_after_sales_history "
                        f"WHERE order_no IN ({placeholders})",
                        tuple(chunk),
                    )
                    result.update(
                        str(row["order_no"])
                        for row in cursor.fetchall()
                        if row.get("order_no")
                    )
    return result


def start_import_batch(row: dict[str, Any]) -> None:
    with db_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO etl_ebay_sop_import_batch (
                    batch_id,import_type,file_name,file_sha256,operator,status,started_at
                ) VALUES (%s,%s,%s,%s,%s,'PROCESSING',NOW())
                """,
                (
                    row["batch_id"], row["import_type"], row["file_name"],
                    row["file_sha256"], row.get("operator"),
                ),
            )
        connection.commit()


def finish_import_batch(
    batch_id: str,
    status: str,
    total_rows: int = 0,
    raw_rows: int = 0,
    dwd_rows: int = 0,
    skipped_rows: int = 0,
    error_message: str | None = None,
) -> None:
    with db_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE etl_ebay_sop_import_batch
                SET status=%s,total_rows=%s,raw_rows=%s,dwd_rows=%s,skipped_rows=%s,
                    error_message=%s,completed_at=NOW()
                WHERE batch_id=%s
                """,
                (status, total_rows, raw_rows, dwd_rows, skipped_rows, error_message, batch_id),
            )
        connection.commit()


def upsert_raw_orders(rows: list[dict[str, Any]]) -> int:
    if not rows:
        return 0
    with db_connection() as connection:
        with connection.cursor() as cursor:
            _upsert_raw_orders(cursor, rows)
        connection.commit()
    return len(rows)


def _upsert_raw_orders(cursor, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    columns = ",".join(RAW_ORDER_COLUMNS)
    values = ",".join(f"%({column})s" for column in RAW_ORDER_COLUMNS)
    updates = ",".join(
        f"{column}=VALUES({column})"
        for column in RAW_ORDER_COLUMNS
        if column not in {"source_key", "data_kind"}
    )
    cursor.executemany(
        f"INSERT INTO ods_ebay_sop_order_raw ({columns}) VALUES ({values}) "
        f"ON DUPLICATE KEY UPDATE {updates}",
        rows,
    )


def upsert_history_rows(rows: list[dict[str, Any]]) -> int:
    if not rows:
        return 0
    columns = ",".join(HISTORY_COLUMNS)
    values = ",".join(f"%({column})s" for column in HISTORY_COLUMNS)
    updates = ",".join(
        f"{column}=VALUES({column})" for column in HISTORY_COLUMNS if column != "source_key"
    )
    with db_connection() as connection:
        with connection.cursor() as cursor:
            cursor.executemany(
                f"INSERT INTO ods_ebay_sop_after_sales_history ({columns}) VALUES ({values}) "
                f"ON DUPLICATE KEY UPDATE {updates}",
                rows,
            )
        connection.commit()
    return len(rows)


def upsert_history_sales_raw(rows: list[dict[str, Any]]) -> int:
    if not rows:
        return 0
    columns = ",".join(HISTORY_SALES_COLUMNS)
    values = ",".join(f"%({column})s" for column in HISTORY_SALES_COLUMNS)
    updates = ",".join(
        f"{column}=VALUES({column})"
        for column in HISTORY_SALES_COLUMNS if column != "source_key"
    )
    with db_connection() as connection:
        with connection.cursor() as cursor:
            cursor.executemany(
                f"INSERT INTO ods_ebay_sop_sales_history ({columns}) VALUES ({values}) "
                f"ON DUPLICATE KEY UPDATE {updates}",
                rows,
            )
        connection.commit()
    return len(rows)


def replace_history_sales(rows: list[dict[str, Any]]) -> int:
    with db_connection() as connection:
        try:
            with connection.cursor() as cursor:
                cursor.execute("DELETE FROM dwd_ebay_sop_sales_monthly")
                if rows:
                    cursor.executemany(
                        """
                        INSERT INTO dwd_ebay_sop_sales_monthly (
                            month_start,month_end,data_source,business_sku,
                            sales_quantity,import_batch_id
                        ) VALUES (
                            %(month_start)s,%(month_end)s,%(data_source)s,
                            %(business_sku)s,%(sales_quantity)s,%(import_batch_id)s
                        )
                        """,
                        rows,
                    )
            connection.commit()
        except Exception:
            connection.rollback()
            raise
    return len(rows)


def replace_history_data(
    after_sales_raw_rows: list[dict[str, Any]],
    sales_raw_rows: list[dict[str, Any]],
    after_sales_dwd_rows: list[dict[str, Any]],
    sales_dwd_rows: list[dict[str, Any]],
) -> tuple[int, int, int, int]:
    """Replace only months present in a standard history/monthly workbook."""
    after_months = sorted({
        row["after_time"].strftime("%Y-%m")
        for row in after_sales_dwd_rows if row.get("after_time")
    })
    sales_months = sorted({
        row["month_start"].strftime("%Y-%m")
        for row in sales_dwd_rows if row.get("month_start")
    })
    affected_months = sorted(set(after_months) | set(sales_months))
    with db_connection() as connection:
        try:
            with connection.cursor() as cursor:
                if after_months:
                    placeholders = ",".join(["%s"] * len(after_months))
                    cursor.execute(
                        "DELETE FROM ods_ebay_sop_after_sales_history "
                        f"WHERE DATE_FORMAT(refund_time,'%%Y-%%m') IN ({placeholders})",
                        after_months,
                    )
                    cursor.execute(
                        "DELETE FROM dwd_ebay_sop_after_sales "
                        f"WHERE source_kind='HISTORY' AND "
                        f"DATE_FORMAT(after_time,'%%Y-%%m') IN ({placeholders})",
                        after_months,
                    )
                if sales_months:
                    placeholders = ",".join(["%s"] * len(sales_months))
                    cursor.execute(
                        "DELETE FROM ods_ebay_sop_sales_history "
                        f"WHERE sale_month IN ({placeholders})",
                        sales_months,
                    )
                    cursor.execute(
                        "DELETE FROM dwd_ebay_sop_sales_monthly "
                        f"WHERE DATE_FORMAT(month_start,'%%Y-%%m') IN ({placeholders})",
                        sales_months,
                    )
                if affected_months:
                    first_month = min(affected_months)
                    last_month = max(affected_months)
                    cursor.execute(
                        "DELETE FROM dws_ebay_sop_after_sales_summary "
                        "WHERE period_end >= STR_TO_DATE(CONCAT(%s,'-01'),'%%Y-%%m-%%d') "
                        "AND period_start <= LAST_DAY(STR_TO_DATE(CONCAT(%s,'-01'),'%%Y-%%m-%%d'))",
                        (first_month, last_month),
                    )

                if after_sales_raw_rows:
                    columns = ",".join(HISTORY_COLUMNS)
                    values = ",".join(f"%({column})s" for column in HISTORY_COLUMNS)
                    updates = ",".join(
                        f"{column}=VALUES({column})"
                        for column in HISTORY_COLUMNS if column != "source_key"
                    )
                    cursor.executemany(
                        f"INSERT INTO ods_ebay_sop_after_sales_history ({columns}) "
                        f"VALUES ({values}) ON DUPLICATE KEY UPDATE {updates}",
                        after_sales_raw_rows,
                    )
                if sales_raw_rows:
                    columns = ",".join(HISTORY_SALES_COLUMNS)
                    values = ",".join(
                        f"%({column})s" for column in HISTORY_SALES_COLUMNS
                    )
                    updates = ",".join(
                        f"{column}=VALUES({column})"
                        for column in HISTORY_SALES_COLUMNS if column != "source_key"
                    )
                    cursor.executemany(
                        f"INSERT INTO ods_ebay_sop_sales_history ({columns}) "
                        f"VALUES ({values}) ON DUPLICATE KEY UPDATE {updates}",
                        sales_raw_rows,
                    )
                if after_sales_dwd_rows:
                    columns = ",".join(AFTER_SALES_COLUMNS)
                    values = ",".join(
                        f"%({column})s" for column in AFTER_SALES_COLUMNS
                    )
                    cursor.executemany(
                        f"INSERT INTO dwd_ebay_sop_after_sales ({columns}) "
                        f"VALUES ({values})",
                        after_sales_dwd_rows,
                    )
                if sales_dwd_rows:
                    cursor.executemany(
                        """
                        INSERT INTO dwd_ebay_sop_sales_monthly (
                            month_start,month_end,data_source,business_sku,
                            sales_quantity,import_batch_id
                        ) VALUES (
                            %(month_start)s,%(month_end)s,%(data_source)s,
                            %(business_sku)s,%(sales_quantity)s,%(import_batch_id)s
                        )
                        """,
                        sales_dwd_rows,
                    )
            connection.commit()
        except Exception:
            connection.rollback()
            raise
    return (
        len(after_sales_raw_rows),
        len(sales_raw_rows),
        len(after_sales_dwd_rows),
        len(sales_dwd_rows),
    )


def replace_sales_range(
    start_date: date, end_date: date, rows: list[dict[str, Any]]
) -> int:
    with db_connection() as connection:
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "DELETE FROM dwd_ebay_sop_sales_daily WHERE sale_date BETWEEN %s AND %s",
                    (start_date, end_date),
                )
                if rows:
                    cursor.executemany(
                        """
                        INSERT INTO dwd_ebay_sop_sales_daily (
                            sale_date,data_source,business_sku,currency_code,sales_quantity,
                            unit_price_total,sales_amount,order_count,import_batch_id
                        ) VALUES (
                            %(sale_date)s,%(data_source)s,%(business_sku)s,%(currency_code)s,
                            %(sales_quantity)s,%(unit_price_total)s,%(sales_amount)s,
                            %(order_count)s,%(import_batch_id)s
                        )
                        """,
                        rows,
                    )
            connection.commit()
        except Exception:
            connection.rollback()
            raise
    return len(rows)


def append_sales_orders(
    raw_rows: list[dict[str, Any]], rows: list[dict[str, Any]]
) -> tuple[int, int]:
    """Atomically append aggregates produced only from previously unseen orders."""
    with db_connection() as connection:
        try:
            with connection.cursor() as cursor:
                _upsert_raw_orders(cursor, raw_rows)
                if rows:
                    cursor.executemany(
                        """
                        INSERT INTO dwd_ebay_sop_sales_daily (
                            sale_date,data_source,business_sku,currency_code,sales_quantity,
                            unit_price_total,sales_amount,order_count,import_batch_id
                        ) VALUES (
                            %(sale_date)s,%(data_source)s,%(business_sku)s,%(currency_code)s,
                            %(sales_quantity)s,%(unit_price_total)s,%(sales_amount)s,
                            %(order_count)s,%(import_batch_id)s
                        )
                        ON DUPLICATE KEY UPDATE
                            sales_quantity=sales_quantity+VALUES(sales_quantity),
                            unit_price_total=unit_price_total+VALUES(unit_price_total),
                            sales_amount=sales_amount+VALUES(sales_amount),
                            order_count=order_count+VALUES(order_count),
                            import_batch_id=VALUES(import_batch_id)
                        """,
                        rows,
                    )
            connection.commit()
        except Exception:
            connection.rollback()
            raise
    return len(raw_rows), len(rows)


def upsert_after_sales(rows: list[dict[str, Any]]) -> int:
    if not rows:
        return 0
    with db_connection() as connection:
        with connection.cursor() as cursor:
            _upsert_after_sales(cursor, rows)
        connection.commit()
    return len(rows)


def _upsert_after_sales(cursor, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    columns = ",".join(AFTER_SALES_COLUMNS)
    values = ",".join(f"%({column})s" for column in AFTER_SALES_COLUMNS)
    updates = ",".join(
        f"{column}=VALUES({column})" for column in AFTER_SALES_COLUMNS if column != "source_key"
    )
    cursor.executemany(
        f"INSERT INTO dwd_ebay_sop_after_sales ({columns}) VALUES ({values}) "
        f"ON DUPLICATE KEY UPDATE {updates}",
        rows,
    )


def append_after_sales_orders(
    raw_rows: list[dict[str, Any]], rows: list[dict[str, Any]]
) -> tuple[int, int]:
    with db_connection() as connection:
        try:
            with connection.cursor() as cursor:
                _upsert_raw_orders(cursor, raw_rows)
                _upsert_after_sales(cursor, rows)
            connection.commit()
        except Exception:
            connection.rollback()
            raise
    return len(raw_rows), len(rows)


def coverage() -> tuple[date | None, date | None]:
    with db_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    (SELECT MIN(value_date) FROM (
                        SELECT MIN(sale_date) AS value_date FROM dwd_ebay_sop_sales_daily
                        UNION ALL
                        SELECT MIN(month_start) AS value_date FROM dwd_ebay_sop_sales_monthly
                    ) sales_min_values) AS sales_min,
                    (SELECT MAX(value_date) FROM (
                        SELECT MAX(sale_date) AS value_date FROM dwd_ebay_sop_sales_daily
                        UNION ALL
                        SELECT MAX(month_end) AS value_date FROM dwd_ebay_sop_sales_monthly
                    ) sales_max_values) AS sales_max,
                    (SELECT MIN(month_start) FROM dwd_ebay_sop_sales_monthly) AS monthly_min,
                    (SELECT MAX(month_end) FROM dwd_ebay_sop_sales_monthly) AS monthly_max,
                    (SELECT MIN(DATE(after_time)) FROM dwd_ebay_sop_after_sales) AS after_min,
                    (SELECT MAX(DATE(after_time)) FROM dwd_ebay_sop_after_sales) AS after_max
                """
            )
            row = cursor.fetchone() or {}
    after_min = row.get("after_min")
    after_max = row.get("after_max")
    monthly_min = row.get("monthly_min")
    monthly_max = row.get("monthly_max")
    # 历史销量只有整月汇总，售后表的首末日期只是当月第一/最后一笔
    # 售后发生日，不能据此把可查询范围裁成半个月，否则默认查询会触发
    # “历史月份必须选完整月”的校验。
    if after_min and monthly_min and (after_min.year, after_min.month) == (
        monthly_min.year, monthly_min.month
    ):
        after_min = monthly_min
    if after_max and monthly_max and (after_max.year, after_max.month) == (
        monthly_max.year, monthly_max.month
    ):
        after_max = monthly_max
    minimums = [value for value in (row.get("sales_min"), after_min) if value]
    maximums = [value for value in (row.get("sales_max"), after_max) if value]
    return (max(minimums) if minimums else None, min(maximums) if maximums else None)


def periods(limit: int = 24) -> list[dict[str, Any]]:
    start, end = coverage()
    if not start or not end or start > end:
        return []
    result = []
    cursor_date = date(end.year, end.month, 1)
    while cursor_date >= date(start.year, start.month, 1) and len(result) < max(1, min(limit, 100)):
        next_month = date(cursor_date.year + (cursor_date.month == 12), cursor_date.month % 12 + 1, 1)
        period_start = max(start, cursor_date)
        period_end = min(end, date.fromordinal(next_month.toordinal() - 1))
        result.append({"period_start": period_start, "period_end": period_end})
        cursor_date = date(cursor_date.year - (cursor_date.month == 1), (cursor_date.month - 2) % 12 + 1, 1)
    return result


def sales_by_sku_source(
    start_date: date, end_date: date
) -> dict[tuple[str, str], Decimal]:
    with db_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT business_sku,data_source,SUM(sales_quantity) AS quantity
                FROM (
                    SELECT business_sku,data_source,sales_quantity
                    FROM dwd_ebay_sop_sales_daily
                    WHERE sale_date BETWEEN %s AND %s
                    UNION ALL
                    SELECT monthly.business_sku,monthly.data_source,monthly.sales_quantity
                    FROM dwd_ebay_sop_sales_monthly monthly
                    WHERE monthly.month_start >= %s
                      AND monthly.month_end <= %s
                      AND NOT EXISTS (
                          SELECT 1 FROM dwd_ebay_sop_sales_daily daily
                          WHERE daily.sale_date BETWEEN monthly.month_start AND monthly.month_end
                      )
                ) effective_sales
                GROUP BY business_sku,data_source
                """,
                (start_date, end_date, start_date, end_date),
            )
            return {
                (str(row["business_sku"]), str(row["data_source"])):
                    Decimal(str(row.get("quantity") or 0))
                for row in cursor.fetchall()
            }


def sales_total(start_date: date, end_date: date) -> Decimal:
    return sum(sales_by_sku_source(start_date, end_date).values(), Decimal("0"))


def has_partial_monthly_history(start_date: date, end_date: date) -> bool:
    with db_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT 1
                FROM dwd_ebay_sop_sales_monthly monthly
                WHERE monthly.month_end >= %s
                  AND monthly.month_start <= %s
                  AND NOT (
                      monthly.month_start >= %s AND monthly.month_end <= %s
                  )
                  AND NOT EXISTS (
                      SELECT 1 FROM dwd_ebay_sop_sales_daily daily
                      WHERE daily.sale_date BETWEEN monthly.month_start AND monthly.month_end
                  )
                LIMIT 1
                """,
                (start_date, end_date, start_date, end_date),
            )
            return cursor.fetchone() is not None


def after_sales_rows(start_date: date, end_date: date) -> list[dict[str, Any]]:
    with db_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT * FROM dwd_ebay_sop_after_sales
                WHERE after_time >= %s AND after_time < DATE_ADD(%s, INTERVAL 1 DAY)
                ORDER BY order_no,business_sku,after_time,id
                """,
                (start_date, end_date),
            )
            return list(cursor.fetchall())


def replace_summary_period(
    start_date: date, end_date: date, rows: list[dict[str, Any]]
) -> None:
    with db_connection() as connection:
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "DELETE FROM dws_ebay_sop_after_sales_summary "
                    "WHERE period_start=%s AND period_end=%s",
                    (start_date, end_date),
                )
                if rows:
                    cursor.executemany(
                        """
                        INSERT INTO dws_ebay_sop_after_sales_summary (
                            period_start,period_end,big_category,small_category,business_sku,
                            order_count,order_numbers,source_after_quantity_text,
                            source_sales_volume_text,after_quantity,sales_volume,
                            after_sales_rate,calculation_version,generated_at
                        ) VALUES (
                            %(period_start)s,%(period_end)s,%(big_category)s,%(small_category)s,
                            %(business_sku)s,%(order_count)s,%(order_numbers)s,
                            %(source_after_quantity_text)s,%(source_sales_volume_text)s,
                            %(after_quantity)s,%(sales_volume)s,%(after_sales_rate)s,
                            %(calculation_version)s,%(generated_at)s
                        )
                        """,
                        rows,
                    )
            connection.commit()
        except Exception:
            connection.rollback()
            raise


def summary_filtered(
    start_date: date,
    end_date: date,
    big_category: str | None = None,
    small_category: str | None = None,
    sku: str | None = None,
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
    if selected_skus:
        where.append(f"business_sku IN ({','.join(['%s'] * len(selected_skus))})")
        params.extend(selected_skus)
    with db_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT * FROM dws_ebay_sop_after_sales_summary
                WHERE {' AND '.join(where)}
                ORDER BY after_quantity DESC,business_sku,small_category
                """,
                params,
            )
            return list(cursor.fetchall())
