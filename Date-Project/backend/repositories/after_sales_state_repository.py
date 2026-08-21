from __future__ import annotations

from contextlib import contextmanager
from datetime import date
from typing import Iterator

from backend.database import db_connection


def _missing_state_table(exc: Exception) -> bool:
    return bool(getattr(exc, "args", ()) and exc.args[0] == 1146)


def previous_month_finalized(platform: str, month_start: date) -> bool:
    try:
        with db_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT is_finalized FROM etl_after_sales_month_state "
                    "WHERE platform=%s AND stat_month=DATE_FORMAT(%s,'%%Y-%%m')",
                    (platform.upper(), month_start),
                )
                row = cursor.fetchone()
                return bool(row and row.get("is_finalized"))
    except Exception as exc:
        if _missing_state_table(exc):
            return False
        raise


def has_any_month(platform: str) -> bool:
    try:
        with db_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT 1 FROM etl_after_sales_month_state "
                    "WHERE platform=%s LIMIT 1",
                    (platform.upper(),),
                )
                return cursor.fetchone() is not None
    except Exception as exc:
        if _missing_state_table(exc):
            return False
        raise


def refresh_month(
    platform: str,
    month_start: date,
    month_end: date,
    sales_row_count: int,
    after_sales_row_count: int,
    finalized: bool,
    batch_id: str,
) -> None:
    try:
        with db_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO etl_after_sales_month_state (
                        platform,stat_month,month_start,month_end,sales_row_count,
                        after_sales_row_count,is_finalized,source_version,
                        sync_batch_id,synced_at
                    ) VALUES (%s,DATE_FORMAT(%s,'%%Y-%%m'),%s,%s,%s,%s,%s,1,%s,NOW())
                    ON DUPLICATE KEY UPDATE
                        month_start=VALUES(month_start),month_end=VALUES(month_end),
                        sales_row_count=VALUES(sales_row_count),
                        after_sales_row_count=VALUES(after_sales_row_count),
                        is_finalized=VALUES(is_finalized),
                        source_version=source_version+1,
                        sync_batch_id=VALUES(sync_batch_id),synced_at=NOW()
                    """,
                    (
                        platform.upper(), month_start, month_start, month_end,
                        sales_row_count, after_sales_row_count, int(finalized), batch_id,
                    ),
                )
                cursor.execute(
                    "DELETE FROM etl_after_sales_range_state "
                    "WHERE platform=%s AND period_start<=%s AND period_end>=%s",
                    (platform.upper(), month_end, month_start),
                )
            connection.commit()
    except Exception as exc:
        if not _missing_state_table(exc):
            raise


def month_counts(platform: str, month_start: date, month_end: date) -> tuple[int, int]:
    with db_connection() as connection:
        with connection.cursor() as cursor:
            if platform.upper() == "AMZ":
                cursor.execute(
                    "SELECT (SELECT COUNT(*) FROM dwd_amz_sop_sales_daily "
                    "WHERE period_start=%s) sales_rows,"
                    "(SELECT COUNT(*) FROM dwd_amz_sop_after_sales WHERE after_time>=%s "
                    "AND after_time<DATE_ADD(%s,INTERVAL 1 DAY)) after_rows",
                    (month_start, month_start, month_end),
                )
            else:
                cursor.execute(
                    "SELECT ((SELECT COUNT(*) FROM dwd_ebay_sop_sales_monthly "
                    "WHERE month_start=%s)+(SELECT COUNT(*) FROM dwd_ebay_sop_sales_daily "
                    "WHERE sale_date BETWEEN %s AND %s)) sales_rows,"
                    "(SELECT COUNT(*) FROM dwd_ebay_sop_after_sales WHERE after_time>=%s "
                    "AND after_time<DATE_ADD(%s,INTERVAL 1 DAY)) after_rows",
                    (month_start, month_start, month_end, month_start, month_end),
                )
            row = cursor.fetchone() or {}
            return int(row.get("sales_rows") or 0), int(row.get("after_rows") or 0)


def periods(platform: str, limit: int = 24) -> list[dict]:
    try:
        with db_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT month_start AS period_start,month_end AS period_end,"
                    "sales_row_count,after_sales_row_count,is_finalized,synced_at "
                    "FROM etl_after_sales_month_state WHERE platform=%s "
                    "AND sales_row_count>0 ORDER BY month_start DESC LIMIT %s",
                    (platform.upper(), max(1, min(limit, 100))),
                )
                return list(cursor.fetchall())
    except Exception as exc:
        if _missing_state_table(exc):
            return []
        raise


def range_source_version(platform: str, start_date: date, end_date: date) -> int:
    try:
        with db_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT COALESCE(SUM(source_version),0) version "
                    "FROM etl_after_sales_month_state WHERE platform=%s "
                    "AND month_start>=%s AND month_end<=%s",
                    (platform.upper(), start_date, end_date),
                )
                return int((cursor.fetchone() or {}).get("version") or 0)
    except Exception as exc:
        if _missing_state_table(exc):
            return 0
        raise


def range_ready(platform: str, start_date: date, end_date: date, version: str) -> bool:
    source_version = range_source_version(platform, start_date, end_date)
    try:
        with db_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT 1 FROM etl_after_sales_range_state WHERE platform=%s "
                    "AND period_start=%s AND period_end=%s AND calculation_version=%s "
                    "AND source_version=%s LIMIT 1",
                    (platform.upper(), start_date, end_date, version, source_version),
                )
                return cursor.fetchone() is not None
    except Exception as exc:
        if _missing_state_table(exc):
            return False
        raise


def mark_range_ready(
    platform: str, start_date: date, end_date: date, version: str, row_count: int
) -> None:
    source_version = range_source_version(platform, start_date, end_date)
    try:
        with db_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO etl_after_sales_range_state (
                        platform,period_start,period_end,calculation_version,
                        source_version,summary_row_count,generated_at
                    ) VALUES (%s,%s,%s,%s,%s,%s,NOW())
                    ON DUPLICATE KEY UPDATE source_version=VALUES(source_version),
                        summary_row_count=VALUES(summary_row_count),generated_at=NOW()
                    """,
                    (platform.upper(), start_date, end_date, version, source_version, row_count),
                )
            connection.commit()
    except Exception as exc:
        if not _missing_state_table(exc):
            raise


@contextmanager
def range_lock(platform: str, start_date: date, end_date: date) -> Iterator[None]:
    name = f"jmh:after-sales:{platform.lower()}:{start_date}:{end_date}"
    with db_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT GET_LOCK(%s,60) acquired", (name,))
            if (cursor.fetchone() or {}).get("acquired") != 1:
                raise TimeoutError("该月份区间正在计算，请稍后重试")
        try:
            yield
        finally:
            with connection.cursor() as cursor:
                cursor.execute("SELECT RELEASE_LOCK(%s)", (name,))
