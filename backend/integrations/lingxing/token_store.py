from __future__ import annotations

from datetime import datetime

import pymysql

from backend.database import db_connection


def load_token() -> dict | None:
    try:
        with db_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT * FROM lingxing_token WHERE id = 1")
                return cursor.fetchone()
    except pymysql.err.ProgrammingError as exc:
        if exc.args and exc.args[0] == 1146:
            return None
        raise


def save_token(
    access_token: str,
    refresh_token: str | None,
    expires_at: datetime | None,
) -> None:
    with db_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO lingxing_token (id, access_token, refresh_token, expires_at)
                VALUES (1, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    access_token = VALUES(access_token),
                    refresh_token = VALUES(refresh_token),
                    expires_at = VALUES(expires_at)
                """,
                (access_token, refresh_token, expires_at),
            )
        connection.commit()


def clear_token() -> None:
    with db_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute("DELETE FROM lingxing_token WHERE id = 1")
        connection.commit()
