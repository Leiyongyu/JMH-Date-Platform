"""Frozen owner/site history. Never joins live inventory or owner rules on reads."""
from __future__ import annotations

import json
from datetime import date, datetime
from decimal import Decimal

from backend.database import db_connection

HEADER = "ebay_inventory_pivot_snapshot"
DETAIL = "ebay_inventory_pivot_owner"
INVENTORY_DETAIL = "ebay_inventory_detail_history"
METRICS = (
    "sku_count", "overseas_sellable_quantity", "overseas_total_quantity", "sales_qty_30d",
    "in_stock_sales_ratio", "total_stock_sales_ratio", "overseas_sellable_value",
    "overseas_total_value", "warehouse_rent_30d_cny", "missing_price_count", "missing_rent_count",
)
SORT_FIELDS = {"stat_date", "owner", "site", *METRICS}
MAX_EXPORT_ROWS = 50000


def _json_default(value):
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    raise TypeError(type(value).__name__)


def replace_day(header: dict, groups: list[dict], inventory_items: list[dict]) -> int:
    """Replace this date only; a failed insert rolls back header and all old rows."""
    columns = ("snapshot_id", "owner", "site", *METRICS)
    with db_connection() as connection:
        try:
            connection.begin()
            with connection.cursor() as cursor:
                cursor.execute(f"""
                    INSERT INTO {HEADER}
                      (stat_date,stat_month,generated_at,inventory_batch_id,inventory_snapshot_date,
                       inventory_pulled_at,trigger_type,item_count,group_count,metadata_json)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    ON DUPLICATE KEY UPDATE stat_month=VALUES(stat_month),
                      generated_at=VALUES(generated_at),inventory_batch_id=VALUES(inventory_batch_id),
                      inventory_snapshot_date=VALUES(inventory_snapshot_date),
                      inventory_pulled_at=VALUES(inventory_pulled_at),trigger_type=VALUES(trigger_type),
                      item_count=VALUES(item_count),group_count=VALUES(group_count),metadata_json=VALUES(metadata_json)
                """, (
                    header["stat_date"], header["stat_month"], header["generated_at"],
                    header["inventory_batch_id"], header.get("inventory_snapshot_date"),
                    header.get("inventory_pulled_at"), header["trigger_type"], header["item_count"],
                    len(groups), json.dumps(header["metadata"], default=_json_default, ensure_ascii=False),
                ))
                cursor.execute(f"SELECT id FROM {HEADER} WHERE stat_date=%s FOR UPDATE", (header["stat_date"],))
                snapshot_id = cursor.fetchone()["id"]
                cursor.execute(f"DELETE FROM {DETAIL} WHERE snapshot_id=%s", (snapshot_id,))
                params = [(snapshot_id, row["owner"], row["site"], *(row[key] for key in METRICS)) for row in groups]
                query = f"INSERT INTO {DETAIL} ({','.join(columns)}) VALUES ({','.join(['%s'] * len(columns))})"
                for offset in range(0, len(params), 500):
                    cursor.executemany(query, params[offset:offset + 500])
                # Full detail and owner totals publish atomically under the same date header.
                cursor.execute(f"DELETE FROM {INVENTORY_DETAIL} WHERE snapshot_id=%s", (snapshot_id,))
                detail_params = [
                    (snapshot_id, row["site"], row["sku"],
                     json.dumps({"values": row, "decimal_fields": [
                         key for key, value in row.items() if isinstance(value, Decimal)
                     ]}, default=_json_default, ensure_ascii=False, allow_nan=False))
                    for row in inventory_items
                ]
                for offset in range(0, len(detail_params), 500):
                    cursor.executemany(
                        f"INSERT INTO {INVENTORY_DETAIL} (snapshot_id,site,sku,item_json) VALUES (%s,%s,%s,%s)",
                        detail_params[offset:offset + 500],
                    )
            connection.commit()
            return snapshot_id
        except Exception:
            connection.rollback()
            raise


def read_inventory_day(stat_date):
    """One repeatable-read snapshot for available dates, header and complete frozen detail."""
    with db_connection() as connection:
        try:
            with connection.cursor() as cursor:
                cursor.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
                connection.begin()
                cursor.execute(f"""SELECT s.stat_date FROM {HEADER} s
                    WHERE EXISTS (SELECT 1 FROM {INVENTORY_DETAIL} d WHERE d.snapshot_id=s.id)
                    ORDER BY s.stat_date DESC""")
                dates = [row["stat_date"].isoformat() for row in cursor.fetchall()]
                selected = dates[0] if stat_date == "latest" and dates else (
                    None if stat_date == "latest" else str(stat_date))
                cursor.execute(f"SELECT * FROM {HEADER} WHERE stat_date=%s", (selected,))
                header = cursor.fetchone()
                items = []
                if header:
                    cursor.execute(f"SELECT item_json FROM {INVENTORY_DETAIL} WHERE snapshot_id=%s ORDER BY site,sku,id",
                                   (header["id"],))
                    for row in cursor.fetchall():
                        saved = json.loads(row["item_json"]) if isinstance(row["item_json"], str) else row["item_json"]
                        item = saved["values"]
                        for key in saved["decimal_fields"]:
                            item[key] = Decimal(item[key])
                        item["stat_date"] = selected
                        items.append(item)
                metadata = {}
                if header and items:
                    raw = header["metadata_json"]
                    metadata = json.loads(raw) if isinstance(raw, str) else dict(raw)
                    metadata.update(snapshot_id=header["id"], generated_at=header["generated_at"].isoformat())
                metadata.update(stat_date=selected, available_dates=dates, is_history=True)
            connection.commit()
        except Exception:
            connection.rollback()
            raise
    return items, metadata, metadata.get("warnings", [])


def insert_import_days(days: dict, file_hash: str, filename: str, operator: str) -> dict:
    """Atomic insert-only import; caller holds the shared inventory:ebay-pivot lock."""
    dates = sorted(days)
    now = datetime.now()
    imported_rows = imported_dates = skipped_dates = 0
    with db_connection() as connection:
        try:
            connection.begin()
            with connection.cursor() as cursor:
                marks = ",".join(["%s"] * len(dates))
                cursor.execute(f"SELECT id,stat_date,trigger_type,item_count,metadata_json FROM {HEADER} "
                               f"WHERE stat_date IN ({marks}) FOR UPDATE", tuple(dates))
                existing = {row["stat_date"]: row for row in cursor.fetchall()}
                conflicts = []
                for day, saved in existing.items():
                    raw = saved["metadata_json"]
                    metadata = json.loads(raw) if isinstance(raw, str) else raw
                    if (saved["trigger_type"] != "EXCEL_IMPORT"
                            or metadata.get("import_file_sha256") != file_hash
                            or saved["item_count"] != len(days[day])):
                        conflicts.append(day.isoformat())
                    else:
                        cursor.execute(f"SELECT COUNT(*) total FROM {INVENTORY_DETAIL} WHERE snapshot_id=%s",
                                       (saved["id"],))
                        if cursor.fetchone()["total"] != len(days[day]):
                            conflicts.append(day.isoformat())
                if conflicts:
                    raise ValueError("以下统计日期已存在其他或不完整批次，整份未导入、未覆盖：" + "、".join(sorted(conflicts)))
                for day in dates:
                    if day in existing:
                        skipped_dates += 1
                        continue
                    items = days[day]
                    metadata = {"history_origin": "EXCEL_IMPORT", "import_file_sha256": file_hash,
                                "import_filename": filename, "import_operator": operator,
                                "grouping_policy": "original_excel_rows", "warnings": []}
                    cursor.execute(f"""INSERT INTO {HEADER}
                        (stat_date,stat_month,generated_at,inventory_batch_id,trigger_type,item_count,group_count,metadata_json)
                        VALUES (%s,%s,%s,%s,'EXCEL_IMPORT',%s,0,%s)""",
                        (day, day.strftime("%Y-%m"), now, file_hash, len(items),
                         json.dumps(metadata, ensure_ascii=False)))
                    snapshot_id = cursor.lastrowid
                    query = (f"INSERT INTO {INVENTORY_DETAIL} (snapshot_id,site,sku,record_key,item_json) "
                             "VALUES (%s,%s,%s,%s,%s)")
                    for offset in range(0, len(items), 500):
                        params = [(snapshot_id, item["site"], item["sku"] or "", item["record_key"],
                                   json.dumps({"values": item, "decimal_fields": [
                                       key for key, value in item.items() if isinstance(value, Decimal)
                                   ]}, default=_json_default, ensure_ascii=False, allow_nan=False))
                                  for item in items[offset:offset + 500]]
                        cursor.executemany(query, params)
                    imported_rows += len(items)
                    imported_dates += 1
            connection.commit()
        except Exception:
            connection.rollback()
            raise
    return {"imported_rows": imported_rows, "imported_dates": imported_dates,
            "skipped_existing_dates": skipped_dates, "already_imported": not imported_dates}


def read_history(*, start_date=None, end_date=None, owner=None, site=None,
                 page=1, page_size=50, sort_field="stat_date", sort_order="desc", paginate=True):
    if sort_field not in SORT_FIELDS:
        raise ValueError("不支持该历史透视排序字段")
    conditions, params = [], []
    for value, clause in (
        (start_date, "s.stat_date >= %s"), (end_date, "s.stat_date <= %s"),
        (owner, "d.owner = %s"), (site, "d.site = %s"),
    ):
        if value is not None:
            conditions.append(clause)
            params.append(value)
    where = " WHERE " + " AND ".join(conditions) if conditions else ""
    joined = f" FROM {DETAIL} d JOIN {HEADER} s ON s.id=d.snapshot_id"
    # Page complete (snapshot date, owner) groups, never their individual sites.
    # The date is unique on the header, so snapshot_id identifies the same group.
    header_fields = (
        "stat_date", "stat_month", "generated_at", "inventory_snapshot_date",
        "inventory_pulled_at", "inventory_batch_id",
    )
    header_columns = ",".join("s." + key for key in header_fields)
    group_columns = "s.id," + header_columns + ",d.owner"
    metric_expressions = []
    ratio_quantities = {
        "in_stock_sales_ratio": "overseas_sellable_quantity",
        "total_stock_sales_ratio": "overseas_total_quantity",
    }
    for key in METRICS:
        if key in ratio_quantities:
            numerator = ratio_quantities[key]
            expression = (f"CASE WHEN SUM(d.sales_qty_30d)=0 THEN 0 "
                          f"ELSE ROUND(SUM(d.{numerator})/SUM(d.sales_qty_30d),6) END")
        else:
            # SUM ignores missing amounts and preserves NULL when all are missing.
            expression = f"SUM(d.{key})"
        metric_expressions.append(expression + " AS " + key)
    grouped = ("SELECT s.id AS snapshot_id," + header_columns + ",d.owner,"
               "'负责人汇总' AS site,'OWNER_TOTAL' AS row_type,"
               "COUNT(*) AS site_count,MIN(d.site) AS sort_site,"
               + ",".join(metric_expressions) + joined + where + " GROUP BY " + group_columns)
    field = "g.sort_site" if sort_field == "site" else "g." + sort_field
    direction = "ASC" if sort_order in {"asc", "ascending"} else "DESC"
    order = f" ORDER BY {field} IS NULL, {field} {direction},g.stat_date DESC,g.owner"
    with db_connection() as connection:
        try:
            with connection.cursor() as cursor:
                cursor.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
                connection.begin()
                count_groups = ("SELECT d.snapshot_id,d.owner,COUNT(*) site_count" + joined + where
                                + " GROUP BY d.snapshot_id,d.owner")
                cursor.execute("SELECT COUNT(*) total,COALESCE(SUM(g.site_count),0) detail_count,"
                               "COUNT(DISTINCT g.snapshot_id) snapshot_count FROM ("
                               + count_groups + ") g", tuple(params))
                counts = cursor.fetchone()
                if not paginate and counts["detail_count"] + counts["total"] > MAX_EXPORT_ROWS:
                    raise ValueError("历史透视导出超过50000行，请缩小统计日期范围")
                query = "SELECT g.* FROM (" + grouped + ") g" + order
                page_params = list(params)
                if paginate:
                    query += " LIMIT %s OFFSET %s"
                    page_params.extend((page_size, (page - 1) * page_size))
                cursor.execute(query, tuple(page_params))
                owner_totals = list(cursor.fetchall())
                items = []
                if owner_totals:
                    detail_where, detail_params = where, list(params)
                    if paginate:
                        keys = [(row["snapshot_id"], row["owner"]) for row in owner_totals]
                        detail_where += " AND " if detail_where else " WHERE "
                        detail_where += "(d.snapshot_id,d.owner) IN (" + ",".join(["(%s,%s)"] * len(keys)) + ")"
                        detail_params.extend(value for key in keys for value in key)
                    detail_query = ("SELECT s.id AS snapshot_id," + header_columns
                                    + ",d.owner,d.site,'DETAIL' AS row_type,"
                                    + ",".join("d." + key for key in METRICS) + joined + detail_where
                                    + " ORDER BY s.stat_date DESC,d.owner,d.site")
                    cursor.execute(detail_query, tuple(detail_params))
                    items = list(cursor.fetchall())
                for row in owner_totals:
                    row.pop("sort_site", None)
                cursor.execute(f"SELECT DISTINCT owner FROM {DETAIL} ORDER BY owner")
                owners = [row["owner"] for row in cursor.fetchall()]
                cursor.execute(f"SELECT DISTINCT site FROM {DETAIL} ORDER BY site")
                sites = [row["site"] for row in cursor.fetchall()]
                cursor.execute(f"SELECT stat_date FROM {HEADER} ORDER BY stat_date DESC")
                dates = [row["stat_date"].isoformat() for row in cursor.fetchall()]
            connection.commit()
        except Exception:
            connection.rollback()
            raise
    return {"items": items, "owner_totals": owner_totals,
            "pagination": {"page": page, "page_size": page_size, "total": counts["total"]},
            "options": {"owners": owners, "sites": sites, "dates": dates},
            "metadata": {"snapshot_count": counts["snapshot_count"],
                         "detail_count": int(counts["detail_count"]),
                         "owner_total_count": counts["total"], "pagination_unit": "owner_date"}}
