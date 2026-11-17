"""Storage for the eBay price tool's 中间码+站点 → OE号 mapping."""
from __future__ import annotations

from typing import Any

from backend.database import db_connection


TABLE = "dim_ebay_sku_oe_site"
CHUNK = 500


def list_mappings() -> list[dict[str, Any]]:
    with db_connection() as connection, connection.cursor() as cursor:
        cursor.execute(
            f"SELECT site_key,middle_code,site,oe_no,update_by,update_time FROM `{TABLE}` ORDER BY site_key"
        )
        return list(cursor.fetchall())


def upsert_mappings(rows: list[dict[str, str]], operator: str) -> dict[str, int]:
    """Insert new keys and overwrite the OE of existing ones; keys absent from
    ``rows`` are left alone. Returns created / updated / unchanged counts."""
    if not rows:
        return {"created": 0, "updated": 0, "unchanged": 0}
    with db_connection() as connection:
        try:
            with connection.cursor() as cursor:
                existing: dict[str, str] = {}
                keys = [row["site_key"] for row in rows]
                for start in range(0, len(keys), CHUNK):
                    part = keys[start:start + CHUNK]
                    cursor.execute(
                        f"SELECT site_key,oe_no FROM `{TABLE}` WHERE site_key IN ({','.join(['%s'] * len(part))})",
                        part,
                    )
                    existing.update({r["site_key"]: r["oe_no"] for r in cursor.fetchall()})
                changed = [
                    {**row, "operator": operator}
                    for row in rows if existing.get(row["site_key"]) != row["oe_no"]
                ]
                if changed:
                    cursor.executemany(
                        f"""
                        INSERT INTO `{TABLE}` (site_key,middle_code,site,oe_no,create_by,update_by)
                        VALUES (%(site_key)s,%(middle_code)s,%(site)s,%(oe_no)s,%(operator)s,%(operator)s)
                        ON DUPLICATE KEY UPDATE
                            update_by=VALUES(update_by),
                            middle_code=VALUES(middle_code),
                            site=VALUES(site),
                            oe_no=VALUES(oe_no)
                        """,
                        changed,
                    )
            connection.commit()
        except Exception:
            connection.rollback()
            raise
    created = sum(1 for row in rows if row["site_key"] not in existing)
    updated = sum(1 for row in changed if row["site_key"] in existing)
    return {"created": created, "updated": updated, "unchanged": len(rows) - created - updated}


def insert_mapping(row: dict[str, str], operator: str) -> bool:
    """False when the key already exists."""
    with db_connection() as connection:
        try:
            with connection.cursor() as cursor:
                cursor.execute(f"SELECT 1 FROM `{TABLE}` WHERE site_key=%s FOR UPDATE", (row["site_key"],))
                if cursor.fetchone():
                    connection.rollback()
                    return False
                cursor.execute(
                    f"INSERT INTO `{TABLE}` (site_key,middle_code,site,oe_no,create_by,update_by) "
                    "VALUES (%s,%s,%s,%s,%s,%s)",
                    (row["site_key"], row["middle_code"], row["site"], row["oe_no"], operator, operator),
                )
            connection.commit()
        except Exception:
            connection.rollback()
            raise
    return True


def update_mapping(original_key: str, row: dict[str, str], operator: str) -> str:
    """Returns "ok", "missing" (original key gone) or "duplicate" (new key taken)."""
    with db_connection() as connection:
        try:
            with connection.cursor() as cursor:
                cursor.execute(f"SELECT 1 FROM `{TABLE}` WHERE site_key=%s FOR UPDATE", (original_key,))
                if not cursor.fetchone():
                    connection.rollback()
                    return "missing"
                if row["site_key"] != original_key:
                    cursor.execute(f"SELECT 1 FROM `{TABLE}` WHERE site_key=%s FOR UPDATE", (row["site_key"],))
                    if cursor.fetchone():
                        connection.rollback()
                        return "duplicate"
                cursor.execute(
                    f"UPDATE `{TABLE}` SET site_key=%s,middle_code=%s,site=%s,oe_no=%s,update_by=%s "
                    "WHERE site_key=%s",
                    (row["site_key"], row["middle_code"], row["site"], row["oe_no"], operator, original_key),
                )
            connection.commit()
        except Exception:
            connection.rollback()
            raise
    return "ok"


def delete_mapping(site_key: str) -> bool:
    with db_connection() as connection:
        try:
            with connection.cursor() as cursor:
                deleted = cursor.execute(f"DELETE FROM `{TABLE}` WHERE site_key=%s", (site_key,))
            connection.commit()
        except Exception:
            connection.rollback()
            raise
    return bool(deleted)
