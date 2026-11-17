from __future__ import annotations

from typing import Any

from backend.database import db_connection


TABLES = (
    "tax_refund_export_details",
    "tax_refund_purchase_details",
    "foreign_exchange_receipts",
    "customs_declaration_items",
    "purchase_invoice_summary",
    "purchase_invoice_inventory",
    "purchase_inventory_allocations",
)


def database_status() -> dict[str, Any]:
    counts = {}
    with db_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT DATABASE() AS db, VERSION() AS version")
            server = cursor.fetchone()
            for table in TABLES:
                cursor.execute(f"SELECT COUNT(*) AS count FROM `{table}`")
                counts[table] = cursor.fetchone()["count"]
    return {"database": server["db"], "mysql_version": server["version"], "counts": counts}


def list_purchase_inventory(
    page: int = 1,
    page_size: int = 50,
    keyword: str = "",
    available_only: bool = False,
) -> dict[str, Any]:
    page = max(1, int(page))
    page_size = min(200, max(10, int(page_size)))
    keyword = str(keyword or "").strip()
    conditions: list[str] = []
    parameters: list[Any] = []
    if keyword:
        like_value = f"%{keyword}%"
        conditions.append(
            "("
            "normalized_sku LIKE %s OR specification LIKE %s OR invoice_no LIKE %s "
            "OR seller_name LIKE %s OR seller_tax_id LIKE %s OR project_name LIKE %s"
            ")"
        )
        parameters.extend([like_value] * 6)
    if available_only:
        conditions.append("available_quantity > 0")
    where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""

    with db_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT COUNT(*) AS total, "
                "COALESCE(SUM(original_quantity), 0) AS original_quantity, "
                "COALESCE(SUM(available_quantity), 0) AS available_quantity "
                f"FROM purchase_invoice_inventory {where_clause}",
                parameters,
            )
            summary = cursor.fetchone()
            total = int(summary["total"])
            total_pages = max(1, (total + page_size - 1) // page_size)
            page = min(page, total_pages)
            offset = (page - 1) * page_size
            cursor.execute(
                "SELECT id, invoice_no, invoice_date, seller_name, seller_tax_id, "
                "item_sequence, project_name, specification, normalized_sku, "
                "inventory_match_type, unit, "
                "original_quantity, available_quantity, unit_price, original_amount, "
                "available_amount, tax_rate, original_tax_amount, available_tax_amount "
                f"FROM purchase_invoice_inventory {where_clause} "
                "ORDER BY invoice_date, invoice_no, item_sequence "
                "LIMIT %s OFFSET %s",
                [*parameters, page_size, offset],
            )
            items = list(cursor.fetchall())

    return {
        "items": items,
        "page": page,
        "page_size": page_size,
        "total": total,
        "total_pages": total_pages,
        "summary": {
            "original_quantity": summary["original_quantity"],
            "available_quantity": summary["available_quantity"],
        },
    }
