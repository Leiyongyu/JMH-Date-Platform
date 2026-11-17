from __future__ import annotations

from collections import Counter
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from backend.database import db_connection, init_database
from backend.parsers.customs_declaration_parser import parse_customs_declaration_workbook
from backend.parsers.purchase_invoice_summary_parser import (
    parse_purchase_invoice_summary_workbook,
)
from backend.parsers.receipt_parser import parse_receipts_workbook
from backend.services.inventory_service import sync_invoice_inventory


def normalized_key(
    record: dict[str, Any], key_columns: tuple[str, ...]
) -> tuple[str, ...]:
    return tuple(
        str(record.get(column) or "").strip().upper() for column in key_columns
    )


def upsert_records(
    cursor,
    table: str,
    records: list[dict[str, Any]],
    key_columns: tuple[str, ...],
) -> tuple[int, int]:
    if not records:
        return 0, 0
    quoted_keys = ", ".join(f"`{column}`" for column in key_columns)
    cursor.execute(f"SELECT {quoted_keys} FROM `{table}`")
    existing_keys = {
        normalized_key(row, key_columns) for row in cursor.fetchall()
    }
    inserted_rows = sum(
        normalized_key(record, key_columns) not in existing_keys for record in records
    )
    updated_rows = len(records) - inserted_rows

    columns = list(records[0])
    quoted_columns = ", ".join(f"`{column}`" for column in columns)
    placeholders = ", ".join(["%s"] * len(columns))
    update_columns = [column for column in columns if column not in key_columns]
    updates = ", ".join(
        f"`{column}` = VALUES(`{column}`)" for column in update_columns
    )
    sql = (
        f"INSERT INTO `{table}` ({quoted_columns}) VALUES ({placeholders}) "
        f"ON DUPLICATE KEY UPDATE {updates}"
    )
    cursor.executemany(
        sql, [tuple(record[column] for column in columns) for record in records]
    )
    return inserted_rows, updated_rows


CENT = Decimal("0.01")


def amount_key(value: Any) -> Decimal | None:
    if value is None:
        return None
    return Decimal(str(value)).quantize(CENT, rounding=ROUND_HALF_UP)


def reconcile_customs_documents(
    cursor, contract_numbers: list[str] | None = None
) -> dict[str, int]:
    """
    将每份报关Excel绑定到唯一18位报关单。

    同一合同允许多份Excel；只有“合同号+报关商品总价”在文件和回款两侧
    都能形成一对一关系时才自动匹配，避免把整套商品复制给同合同的多张报关单。
    """
    contracts = sorted(
        {
            str(value or "").strip()
            for value in (contract_numbers or [])
            if str(value or "").strip()
        }
    )
    where_sql = ""
    params: tuple[Any, ...] = ()
    if contracts:
        placeholders = ", ".join(["%s"] * len(contracts))
        where_sql = f" WHERE contract_no IN ({placeholders})"
        params = tuple(contracts)

    cursor.execute(
        "SELECT source_document_key, contract_no, "
        "MAX(document_total_usd) AS document_total_usd "
        "FROM customs_declaration_items"
        f"{where_sql} "
        "GROUP BY source_document_key, contract_no",
        params,
    )
    documents = list(cursor.fetchall())
    if not documents:
        return {
            "matched_documents": 0,
            "ambiguous_documents": 0,
            "unmatched_documents": 0,
            "matched_customs_rows": 0,
        }

    document_contracts = sorted({row["contract_no"] for row in documents})
    placeholders = ", ".join(["%s"] * len(document_contracts))
    cursor.execute(
        "SELECT contract_no, customs_declaration_no, export_date, "
        "declared_contract_amount_usd "
        "FROM foreign_exchange_receipts "
        f"WHERE contract_no IN ({placeholders}) "
        "AND customs_declaration_no REGEXP '^[0-9]{18}$'",
        tuple(document_contracts),
    )
    receipts = list(cursor.fetchall())

    receipt_by_identity = {
        (str(row["contract_no"]).strip(), str(row["customs_declaration_no"]).strip()): row
        for row in receipts
    }
    candidates_by_document: dict[str, list[tuple[str, str]]] = {}
    for document in documents:
        contract = str(document["contract_no"]).strip()
        total = amount_key(document["document_total_usd"])
        candidates_by_document[document["source_document_key"]] = [
            identity
            for identity, receipt in receipt_by_identity.items()
            if identity[0] == contract
            and total is not None
            and amount_key(receipt["declared_contract_amount_usd"]) == total
        ]

    candidate_usage = Counter(
        identity
        for candidates in candidates_by_document.values()
        for identity in candidates
    )
    results: dict[str, tuple[str, dict[str, Any] | None]] = {}
    for document in documents:
        key = document["source_document_key"]
        candidates = candidates_by_document[key]
        if len(candidates) == 1 and candidate_usage[candidates[0]] == 1:
            results[key] = ("MATCHED", receipt_by_identity[candidates[0]])
        elif candidates:
            results[key] = ("AMBIGUOUS", None)
        else:
            results[key] = ("UNMATCHED", None)

    document_keys = [row["source_document_key"] for row in documents]
    key_placeholders = ", ".join(["%s"] * len(document_keys))
    cursor.execute(
        "UPDATE customs_declaration_items "
        "SET customs_declaration_no=NULL, export_date=NULL, "
        "customs_match_status='UNMATCHED' "
        f"WHERE source_document_key IN ({key_placeholders})",
        tuple(document_keys),
    )

    matched_customs_rows = 0
    for key, (status, receipt) in results.items():
        if receipt is None:
            cursor.execute(
                "UPDATE customs_declaration_items SET customs_match_status=%s "
                "WHERE source_document_key=%s",
                (status, key),
            )
            continue
        cursor.execute(
            "UPDATE customs_declaration_items "
            "SET customs_match_status='MATCHED', customs_declaration_no=%s, "
            "export_date=%s WHERE source_document_key=%s",
            (receipt["customs_declaration_no"], receipt["export_date"], key),
        )
        matched_customs_rows += int(cursor.rowcount)

    status_counts = Counter(status for status, _ in results.values())
    return {
        "matched_documents": status_counts["MATCHED"],
        "ambiguous_documents": status_counts["AMBIGUOUS"],
        "unmatched_documents": status_counts["UNMATCHED"],
        "matched_customs_rows": matched_customs_rows,
    }


def replace_customs_declaration_records(
    records: list[dict[str, Any]], metadata: dict[str, Any]
) -> dict[str, Any]:
    init_database()
    key_columns = ("source_document_key", "item_no")
    deduplicated = {
        normalized_key(record, key_columns): record for record in records
    }
    records = list(deduplicated.values())
    contract_no = records[0]["contract_no"]
    document_key = records[0]["source_document_key"]

    with db_connection() as connection:
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT item_no, customs_declaration_no, declaration_date, "
                    "declaration_month, declaration_batch, sequence_no, correlation_no "
                    "FROM customs_declaration_items WHERE source_document_key = %s",
                    (document_key,),
                )
                existing_records = cursor.fetchall()
                existing_by_item = {
                    str(row["item_no"]).strip(): row for row in existing_records
                }
                preserved_fields = (
                    "declaration_date",
                    "declaration_month",
                    "declaration_batch",
                    "sequence_no",
                    "correlation_no",
                )
                for record in records:
                    existing = existing_by_item.get(str(record["item_no"]).strip(), {})
                    for field in preserved_fields:
                        record[field] = existing.get(field)

                cursor.execute(
                    "DELETE FROM customs_declaration_items "
                    "WHERE source_document_key = %s",
                    (document_key,),
                )
                columns = list(records[0])
                quoted_columns = ", ".join(f"`{column}`" for column in columns)
                placeholders = ", ".join(["%s"] * len(columns))
                cursor.executemany(
                    f"INSERT INTO customs_declaration_items ({quoted_columns}) "
                    f"VALUES ({placeholders})",
                    [
                        tuple(record[column] for column in columns)
                        for record in records
                    ],
                )
                reconciliation = reconcile_customs_documents(
                    cursor, [contract_no]
                )
                cursor.execute(
                    "SELECT customs_match_status, customs_declaration_no, export_date "
                    "FROM customs_declaration_items "
                    "WHERE source_document_key=%s LIMIT 1",
                    (document_key,),
                )
                match = cursor.fetchone()
            connection.commit()
        except Exception:
            connection.rollback()
            raise

    existing_rows = len(existing_records)
    return {
        **metadata,
        "table": "customs_declaration_items",
        "processed_rows": len(records),
        "inserted_rows": len(records) if existing_rows == 0 else 0,
        "updated_rows": len(records) if existing_rows > 0 else 0,
        "replaced_rows": existing_rows,
        "source_document_key": document_key,
        "document_total_usd": metadata["document_total_usd"],
        "customs_match_status": match["customs_match_status"],
        "customs_declaration_no": match["customs_declaration_no"],
        "export_date": match["export_date"],
        "export_date_source": (
            "foreign_exchange_receipts"
            if match["customs_match_status"] == "MATCHED"
            else None
        ),
        **reconciliation,
    }


def import_customs_declaration_excel(
    content: bytes, file_name: str
) -> dict[str, Any]:
    try:
        records, metadata = parse_customs_declaration_workbook(content, file_name)
    except ValueError as exc:
        raise ValueError(f"文件“{file_name}”解析失败：{exc}") from exc
    return replace_customs_declaration_records(records, metadata)


def import_customs_declaration_excel_batch(
    files: list[tuple[bytes, str]],
) -> dict[str, Any]:
    if not files:
        raise ValueError("请至少选择一个报关单Excel")

    parsed_files: list[tuple[list[dict[str, Any]], dict[str, Any]]] = []
    seen_documents: set[str] = set()
    for content, file_name in files:
        try:
            records, metadata = parse_customs_declaration_workbook(content, file_name)
        except ValueError as exc:
            raise ValueError(f"文件“{file_name}”解析失败：{exc}") from exc
        except Exception as exc:
            raise ValueError(
                f"文件“{file_name}”读取异常：{type(exc).__name__}: {exc}"
            ) from exc
        document_key = str(metadata["source_document_key"])
        if document_key in seen_documents:
            raise ValueError(
                f"文件“{file_name}”与本批次其他文件的报关资料标识重复"
            )
        seen_documents.add(document_key)
        parsed_files.append((records, metadata))

    results = [
        replace_customs_declaration_records(records, metadata)
        for records, metadata in parsed_files
    ]
    return {
        "file_count": len(results),
        "processed_rows": sum(result["processed_rows"] for result in results),
        "inserted_rows": sum(result["inserted_rows"] for result in results),
        "updated_rows": sum(result["updated_rows"] for result in results),
        "replaced_rows": sum(result["replaced_rows"] for result in results),
        "files": results,
        "table": "customs_declaration_items",
    }


def backfill_customs_export_dates(cursor, contract_numbers: list[str]) -> int:
    return reconcile_customs_documents(
        cursor, contract_numbers
    )["matched_customs_rows"]


def import_foreign_exchange_receipts(
    content: bytes, file_name: str
) -> dict[str, Any]:
    records, metadata = parse_receipts_workbook(content, file_name)
    key_columns = ("contract_no", "customs_declaration_no")
    deduplicated = {
        normalized_key(record, key_columns): record for record in records
    }
    records = list(deduplicated.values())
    init_database()

    with db_connection() as connection:
        try:
            with connection.cursor() as cursor:
                inserted_rows, updated_rows = upsert_records(
                    cursor,
                    "foreign_exchange_receipts",
                    records,
                    key_columns,
                )
                matched_customs_rows = backfill_customs_export_dates(
                    cursor, [record["contract_no"] for record in records]
                )
            connection.commit()
        except Exception:
            connection.rollback()
            raise

    return {
        **metadata,
        "table": "foreign_exchange_receipts",
        "processed_rows": len(records),
        "inserted_rows": inserted_rows,
        "updated_rows": updated_rows,
        "matched_customs_rows": matched_customs_rows,
    }


def import_purchase_invoice_summary(
    content: bytes, file_name: str
) -> dict[str, Any]:
    records, metadata = parse_purchase_invoice_summary_workbook(content, file_name)
    invoice_identities = sorted(
        {str(record["invoice_identity"]) for record in records}
    )
    init_database()

    with db_connection() as connection:
        try:
            with connection.cursor() as cursor:
                inventory_totals = {
                    "inventory_rows": 0,
                    "inventory_inserted_rows": 0,
                    "inventory_updated_rows": 0,
                }
                records_by_invoice: dict[str, list[dict[str, Any]]] = {}
                for record in records:
                    records_by_invoice.setdefault(
                        str(record["invoice_identity"]), []
                    ).append(record)
                for identity, invoice_records in records_by_invoice.items():
                    eligible_inventory_rows = []
                    for record in invoice_records:
                        resolved_sku = str(record.get("resolved_sku") or "").strip()
                        project_name = str(
                            record.get("goods_or_service_name") or ""
                        ).strip()
                        inventory_match_value = resolved_sku or project_name
                        inventory_match_type = (
                            "SKU" if resolved_sku else "PRODUCT_NAME"
                        )
                        if (
                            not inventory_match_value
                            or not str(record.get("unit") or "").strip()
                            or record.get("quantity") is None
                            or record["quantity"] <= 0
                        ):
                            continue
                        invoice_datetime = record.get("invoice_datetime")
                        eligible_inventory_rows.append(
                            {
                                "invoice_no": identity,
                                "invoice_date": (
                                    invoice_datetime.date()
                                    if invoice_datetime is not None
                                    else None
                                ),
                                "seller_name": record.get("seller_name") or "",
                                "seller_tax_id": record.get("seller_tax_id") or "",
                                "item_sequence": record["invoice_line_no"],
                                "project_name": project_name,
                                "specification": inventory_match_value,
                                "inventory_match_type": inventory_match_type,
                                "unit": record["unit"],
                                "quantity": record["quantity"],
                                "unit_price": record.get("unit_price"),
                                "amount": record.get("amount"),
                                "tax_rate": record.get("tax_rate") or "",
                                "tax_amount": record.get("tax_amount"),
                                "source_hash": record["source_hash"],
                            }
                        )
                    inventory_result = sync_invoice_inventory(
                        cursor, eligible_inventory_rows, identity
                    )
                    for key in inventory_totals:
                        inventory_totals[key] += inventory_result[key]

                placeholders = ", ".join(["%s"] * len(invoice_identities))
                cursor.execute(
                    "SELECT COUNT(*) AS count FROM purchase_invoice_summary "
                    f"WHERE invoice_identity IN ({placeholders})",
                    invoice_identities,
                )
                replaced_rows = int(cursor.fetchone()["count"])
                cursor.execute(
                    "DELETE FROM purchase_invoice_summary "
                    f"WHERE invoice_identity IN ({placeholders})",
                    invoice_identities,
                )
                columns = list(records[0])
                quoted_columns = ", ".join(f"`{column}`" for column in columns)
                placeholders = ", ".join(["%s"] * len(columns))
                cursor.executemany(
                    f"INSERT INTO purchase_invoice_summary ({quoted_columns}) "
                    f"VALUES ({placeholders})",
                    [
                        tuple(record[column] for column in columns)
                        for record in records
                    ],
                )
            connection.commit()
        except Exception:
            connection.rollback()
            raise

    return {
        **metadata,
        "table": "purchase_invoice_summary",
        "processed_rows": len(records),
        "inserted_rows": len(records),
        "updated_rows": 0,
        "replaced_rows": replaced_rows,
        "upserted_invoice_count": len(invoice_identities),
        **inventory_totals,
    }
