from __future__ import annotations

from typing import Any

from backend.database import db_connection


def upsert_monthly_rates(rows: list[dict[str, Any]]) -> int:
    if not rows:
        return 0
    with db_connection() as connection:
        try:
            with connection.cursor() as cursor:
                cursor.executemany(
                    """
                    INSERT INTO dim_lingxing_currency_month (
                        rate_month, currency_code, my_rate, rate_org,
                        sync_batch_id, synced_at
                    ) VALUES (
                        %(rate_month)s, %(currency_code)s, %(my_rate)s,
                        %(rate_org)s, %(sync_batch_id)s, %(synced_at)s
                    )
                    ON DUPLICATE KEY UPDATE
                        my_rate=VALUES(my_rate),
                        rate_org=VALUES(rate_org),
                        sync_batch_id=VALUES(sync_batch_id),
                        synced_at=VALUES(synced_at)
                    """,
                    rows,
                )
            connection.commit()
        except Exception:
            connection.rollback()
            raise
    return len(rows)
