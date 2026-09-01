"""SKU-OE 映射数据库操作。"""

from __future__ import annotations

from backend.database import db_connection


def list_all() -> list[dict]:
    """返回全部 SKU-OE 映射，按 SKU 排序。"""
    with db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT sku, oe, middle_code "
                "FROM ebay_price_sku_oe_mapping "
                "ORDER BY sku, oe"
            )
            return cur.fetchall()


def get_by_skus(skus: list[str]) -> dict[str, str]:
    """根据 SKU 列表批量查询，返回 {sku: oe} 映射（取第一个 OE）。"""
    if not skus:
        return {}
    with db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT sku, oe FROM ebay_price_sku_oe_mapping "
                "WHERE sku IN (%s)" % ",".join(["%s"] * len(skus)),
                skus,
            )
            rows = cur.fetchall()
    result: dict[str, str] = {}
    for row in rows:
        result.setdefault(row["sku"], row["oe"])
    return result


def get_middle_code_map() -> dict[str, str]:
    """返回 {middle_code_upper: oe} 映射（仅手动指定的中间码）。"""
    with db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT middle_code, oe FROM ebay_price_sku_oe_mapping "
                "WHERE middle_code IS NOT NULL AND middle_code != ''"
            )
            rows = cur.fetchall()
    return {row["middle_code"].upper(): row["oe"] for row in rows}


def add(sku: str, oe: str, middle_code: str | None) -> dict:
    with db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id FROM ebay_price_sku_oe_mapping "
                "WHERE sku=%s AND oe=%s",
                (sku, oe),
            )
            if cur.fetchone():
                conn.rollback()
                raise ValueError(f"SKU '{sku}' + OE '{oe}' 已存在")
            cur.execute(
                "INSERT INTO ebay_price_sku_oe_mapping (sku, oe, middle_code) "
                "VALUES (%s, %s, %s)",
                (sku, oe, middle_code or None),
            )
            conn.commit()
    return {"sku": sku, "oe": oe, "middleCode": middle_code or ""}


def update(sku: str, oe: str, middle_code: str | None) -> dict:
    with db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE ebay_price_sku_oe_mapping "
                "SET oe=%s, middle_code=%s "
                "WHERE sku=%s",
                (oe, middle_code or None, sku),
            )
            if cur.rowcount == 0:
                conn.rollback()
                raise ValueError(f"SKU '{sku}' 不存在")
            conn.commit()
    return {"sku": sku, "oe": oe, "middleCode": middle_code or ""}


def delete(sku: str) -> None:
    with db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM ebay_price_sku_oe_mapping WHERE sku=%s", (sku,)
            )
            if cur.rowcount == 0:
                conn.rollback()
                raise ValueError(f"SKU '{sku}' 不存在")
            conn.commit()


def batch_upsert(rows: list[dict], source_file: str = "") -> dict:
    """批量导入：新增的插入，已有的覆盖 OE。返回统计信息。"""
    if not rows:
        return {"imported": 0, "created": 0, "updated": 0}
    with db_connection() as conn:
        with conn.cursor() as cur:
            skus = [r["sku"] for r in rows]
            cur.execute(
                "SELECT DISTINCT sku FROM ebay_price_sku_oe_mapping "
                "WHERE sku IN (%s)" % ",".join(["%s"] * len(skus)),
                skus,
            )
            existing = {r["sku"] for r in cur.fetchall()}

            created = updated = 0
            for r in rows:
                mc = r.get("middle_code")
                if r["sku"] in existing:
                    cur.execute(
                        "UPDATE ebay_price_sku_oe_mapping "
                        "SET oe=%s, middle_code=%s "
                        "WHERE sku=%s AND oe=%s",
                        (r["oe"], mc or None, r["sku"], r["oe"]),
                    )
                    if cur.rowcount == 0:
                        cur.execute(
                            "INSERT INTO ebay_price_sku_oe_mapping "
                            "(sku, oe, middle_code) VALUES (%s, %s, %s)",
                            (r["sku"], r["oe"], mc or None),
                        )
                    updated += 1
                else:
                    cur.execute(
                        "INSERT INTO ebay_price_sku_oe_mapping "
                        "(sku, oe, middle_code) VALUES (%s, %s, %s)",
                        (r["sku"], r["oe"], mc or None),
                    )
                    created += 1
            conn.commit()
    return {"imported": len(rows), "created": created, "updated": updated}
