from __future__ import annotations

import re
from datetime import datetime
from typing import Any
from uuid import uuid4

from backend.database import db_connection, init_database
from backend.services.inventory_service import ensure_fifo_allocations


CUSTOMS_NO_PATTERN = re.compile(r"^\d{18}$")
MONTH_PATTERN = re.compile(r"^\d{6}$")
BATCH_PATTERN = re.compile(r"^\d{1,3}$")


class CustomsAllocationErrors(ValueError):
    def __init__(self, errors: list[dict[str, Any]]):
        self.errors = errors
        super().__init__("\n".join(str(item["error"]) for item in errors))


def normalize_assignment(
    declaration_month: str, declaration_batch: str
) -> tuple[str, str]:
    month = str(declaration_month or "").strip()
    batch_input = str(declaration_batch or "").strip()
    if not MONTH_PATTERN.fullmatch(month):
        raise ValueError("申报年月必须是6位数字，格式为YYYYMM")
    try:
        datetime.strptime(month, "%Y%m")
    except ValueError as exc:
        raise ValueError("申报年月不是有效月份，请按YYYYMM填写") from exc
    if not BATCH_PATTERN.fullmatch(batch_input):
        raise ValueError("申报批次必须是1至3位数字，例如001或3")
    batch_number = int(batch_input)
    if batch_number < 1:
        raise ValueError("申报批次必须大于000")
    batch = str(batch_number).zfill(3)
    if month == "202512" and batch == "002":
        raise ValueError("申报年月202512按现有业务规则需要跳过002批次")
    return month, batch


def list_customs_declaration_options() -> list[dict[str, Any]]:
    """列出回款表中的18位报关单，并标记其报关资料是否完整、是否可生成。"""
    init_database()
    with db_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT r.customs_declaration_no, r.contract_no, r.export_date, "
                "MIN(c.invoice_no) AS invoice_no, COUNT(DISTINCT c.id) AS item_count, "
                "MAX(c.document_total_usd) AS document_total_usd, "
                "COUNT(DISTINCT e.id) AS generated_count, "
                "(SELECT COUNT(DISTINCT r2.contract_no) "
                " FROM foreign_exchange_receipts r2 "
                " WHERE r2.customs_declaration_no = r.customs_declaration_no"
                ") AS contract_count "
                "FROM foreign_exchange_receipts r "
                "LEFT JOIN customs_declaration_items c "
                "ON c.customs_declaration_no = r.customs_declaration_no "
                "AND c.customs_match_status = 'MATCHED' "
                "LEFT JOIN tax_refund_export_details e "
                "ON LEFT(e.customs_declaration_no, 18) = r.customs_declaration_no "
                "AND e.uploaded_file_name LIKE '报关资料生成:%%' "
                "WHERE r.customs_declaration_no REGEXP '^[0-9]{18}$' "
                "GROUP BY r.customs_declaration_no, r.contract_no, r.export_date "
                "ORDER BY r.export_date DESC, r.customs_declaration_no DESC"
            )
            rows = cursor.fetchall()
    for row in rows:
        if row.get("export_date"):
            row["export_date"] = row["export_date"].isoformat()
        row["item_count"] = int(row["item_count"])
        row["generated_count"] = int(row["generated_count"])
        row["contract_count"] = int(row["contract_count"])
        row["has_customs_data"] = row["item_count"] > 0
        row["ambiguous_contract"] = row["contract_count"] > 1
        row["selectable"] = row["has_customs_data"] and not row["ambiguous_contract"]
        row["converted"] = row["generated_count"] > 0
        row["customs_match_status"] = (
            "MATCHED" if row["has_customs_data"] else "UNMATCHED"
        )
    return rows


def item_number(row: dict[str, Any]) -> int:
    try:
        value = int(str(row.get("item_no") or "").strip())
    except ValueError as exc:
        raise ValueError(f"商品项号不是有效数字：{row.get('item_no')}") from exc
    if value < 1 or value > 999:
        raise ValueError(f"商品项号{value}无法补足为三位报关单商品项号")
    return value


def build_export_records(
    customs_rows: list[dict[str, Any]],
    customs_no: str,
    export_date,
    declaration_month: str,
    declaration_batch: str,
    existing_sequences: dict[str, str],
    next_sequence: int,
) -> list[dict[str, Any]]:
    month, batch = normalize_assignment(declaration_month, declaration_batch)
    if not customs_rows:
        raise ValueError("该报关单合同未找到报关商品明细")

    upload_batch_id = str(uuid4())
    export_records: list[dict[str, Any]] = []
    seen_items: set[int] = set()
    for row in customs_rows:
        item = item_number(row)
        if item in seen_items:
            raise ValueError(f"报关单合同内存在重复商品项号：{item}")
        seen_items.add(item)
        export_customs_no = f"{customs_no}{item:03d}"
        sequence_no = existing_sequences.get(export_customs_no)
        if not sequence_no:
            sequence_no = str(next_sequence).zfill(8)
            next_sequence += 1
        correlation_no = f"{month}{batch}{sequence_no}"

        quantity = row.get("quantity_value")
        unit = str(row.get("quantity_unit") or "").strip()
        total_price = row.get("total_price")
        currency = str(row.get("currency") or "").strip().upper()
        if quantity is None or not unit:
            raise ValueError(f"商品项号{item}的数量及单位未正确拆分")
        if total_price is None or currency != "USD":
            raise ValueError(f"商品项号{item}的总价或币制无效，只接受USD总价")
        if not row.get("invoice_no") or not row.get("product_code") or not row.get(
            "product_name"
        ):
            raise ValueError(f"商品项号{item}缺少发票号、商品代码或商品名称")

        export_records.append(
            {
                "declaration_month": month,
                "declaration_batch": batch,
                "sequence_no": sequence_no,
                "correlation_no": correlation_no,
                "contract_no": row.get("contract_no"),
                "export_invoice_no": row["invoice_no"],
                "customs_declaration_no": export_customs_no,
                "agent_export_certificate_no": None,
                "export_date": export_date,
                "export_product_code": row["product_code"],
                "export_product_name": row["product_name"],
                "measurement_unit": unit,
                "export_quantity": quantity,
                "fob_value_usd": total_price,
                "declared_product_code": None,
                "tax_refund_business_type": None,
                "remark": None,
                "upload_batch_id": upload_batch_id,
                "uploaded_file_name": f"报关资料生成:{row['uploaded_file_name']}",
                "source_hash": row["source_hash"],
                "source_sheet": row["source_sheet"],
                "source_row": row["source_row"],
                "_inventory_sku": row.get("specification"),
            }
        )
    return export_records


def convert_customs_declaration_to_export_details(
    customs_declaration_no: str,
    declaration_month: str,
    declaration_batch: str,
) -> dict[str, Any]:
    customs_no = str(customs_declaration_no or "").strip()
    if not CUSTOMS_NO_PATTERN.fullmatch(customs_no):
        raise ValueError("请选择一个有效的18位报关单号")
    month, batch = normalize_assignment(declaration_month, declaration_batch)
    init_database()

    with db_connection() as connection:
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT contract_no, export_date FROM foreign_exchange_receipts "
                    "WHERE customs_declaration_no = %s",
                    (customs_no,),
                )
                receipt_rows = cursor.fetchall()
                contracts = {str(row["contract_no"]).strip() for row in receipt_rows}
                dates = {row["export_date"] for row in receipt_rows if row["export_date"]}
                if len(contracts) != 1:
                    raise ValueError(f"报关单{customs_no}无法确定唯一合同协议号")
                if len(dates) > 1:
                    raise ValueError(f"报关单{customs_no}对应多个出口日期")
                contract_no = next(iter(contracts))
                export_date = next(iter(dates), None)

                cursor.execute(
                    "SELECT * FROM customs_declaration_items "
                    "WHERE customs_declaration_no = %s "
                    "AND customs_match_status = 'MATCHED' "
                    "ORDER BY CAST(item_no AS UNSIGNED), id",
                    (customs_no,),
                )
                customs_rows = cursor.fetchall()
                if not customs_rows:
                    raise ValueError(
                        f"报关单{customs_no}没有唯一匹配的报关Excel；"
                        "请核对该文件商品总价是否等于回款表报关合同金额"
                    )
                cursor.execute(
                    "SELECT id, customs_declaration_no, declaration_month, "
                    "declaration_batch, sequence_no "
                    "FROM tax_refund_export_details "
                    "WHERE LEFT(customs_declaration_no, 18) = %s "
                    "AND uploaded_file_name LIKE '报关资料生成:%%' FOR UPDATE",
                    (customs_no,),
                )
                existing_rows = cursor.fetchall()
                existing_by_customs = {
                    row["customs_declaration_no"]: row for row in existing_rows
                }
                existing_sequences = {
                    row["customs_declaration_no"]: row["sequence_no"]
                    for row in existing_rows
                    if row["declaration_month"] == month
                    and row["declaration_batch"] == batch
                }
                cursor.execute(
                    "SELECT MAX(CAST(sequence_no AS UNSIGNED)) AS max_sequence "
                    "FROM tax_refund_export_details "
                    "WHERE declaration_month = %s AND declaration_batch = %s",
                    (month, batch),
                )
                next_sequence = int(cursor.fetchone()["max_sequence"] or 0) + 1
                records = build_export_records(
                    customs_rows,
                    customs_no,
                    export_date,
                    month,
                    batch,
                    existing_sequences,
                    next_sequence,
                )
                incoming_customs_numbers = {
                    record["customs_declaration_no"] for record in records
                }
                stale = set(existing_by_customs) - incoming_customs_numbers
                if stale:
                    raise ValueError(
                        "该报关单以前生成过、但本次报关Excel已缺少商品项："
                        + "、".join(sorted(stale))
                        + "；为避免误删库存扣减，请先核对源文件"
                    )

                columns = [key for key in records[0] if not key.startswith("_")]
                quoted_columns = ", ".join(f"`{column}`" for column in columns)
                value_placeholders = ", ".join(["%s"] * len(columns))
                update_sql = ", ".join(f"`{column}` = %s" for column in columns)
                export_ids: list[int] = []
                inserted_rows = 0
                updated_rows = 0
                for record in records:
                    current = existing_by_customs.get(record["customs_declaration_no"])
                    values = tuple(record[column] for column in columns)
                    if current:
                        cursor.execute(
                            f"UPDATE tax_refund_export_details SET {update_sql} WHERE id = %s",
                            (*values, current["id"]),
                        )
                        cursor.execute(
                            "UPDATE purchase_inventory_allocations SET correlation_no = %s "
                            "WHERE export_detail_id = %s",
                            (record["correlation_no"], current["id"]),
                        )
                        export_ids.append(int(current["id"]))
                        updated_rows += 1
                    else:
                        cursor.execute(
                            f"INSERT INTO tax_refund_export_details ({quoted_columns}) "
                            f"VALUES ({value_placeholders})",
                            values,
                        )
                        export_ids.append(int(cursor.lastrowid))
                        inserted_rows += 1

                id_placeholders = ", ".join(["%s"] * len(export_ids))
                cursor.execute(
                    "SELECT * FROM tax_refund_export_details "
                    f"WHERE id IN ({id_placeholders}) ORDER BY sequence_no FOR UPDATE",
                    export_ids,
                )
                fifo_exports = cursor.fetchall()
                sku_by_customs = {
                    record["customs_declaration_no"]: record["_inventory_sku"]
                    for record in records
                }
                for export_row in fifo_exports:
                    export_row["inventory_sku"] = sku_by_customs[
                        export_row["customs_declaration_no"]
                    ]
                allocation_stats = ensure_fifo_allocations(
                    cursor, fifo_exports, str(uuid4()), collect_errors=True
                )
                if allocation_stats["errors"]:
                    raise CustomsAllocationErrors(allocation_stats["errors"])
            connection.commit()
        except Exception:
            connection.rollback()
            raise

    return {
        "customs_declaration_no": customs_no,
        "contract_no": contract_no,
        "export_date": export_date,
        "declaration_month": month,
        "declaration_batch": batch,
        "processed_rows": len(records),
        "inserted_rows": inserted_rows,
        "updated_rows": updated_rows,
        **allocation_stats,
        "table": "tax_refund_export_details",
    }


def convert_customs_declarations_to_export_details(
    customs_declaration_numbers: list[str],
    declaration_month: str,
    declaration_batch: str,
) -> dict[str, Any]:
    numbers = list(
        dict.fromkeys(
            str(value or "").strip() for value in customs_declaration_numbers
        )
    )
    if not numbers:
        raise ValueError("请至少选择一张报关单")
    invalid = [value for value in numbers if not CUSTOMS_NO_PATTERN.fullmatch(value)]
    if invalid:
        raise ValueError(f"存在无效18位报关单号：{invalid[0]}")
    month, batch = normalize_assignment(declaration_month, declaration_batch)
    results: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    for number in numbers:
        try:
            results.append(
                convert_customs_declaration_to_export_details(number, month, batch)
            )
        except ValueError as exc:
            allocation_errors = getattr(exc, "errors", None)
            if allocation_errors:
                errors.extend(allocation_errors)
                continue
            with db_connection() as connection:
                with connection.cursor() as cursor:
                    cursor.execute(
                        "SELECT GROUP_CONCAT(DISTINCT contract_no ORDER BY contract_no "
                        "SEPARATOR '、') AS contract_no "
                        "FROM customs_declaration_items "
                        "WHERE customs_declaration_no=%s",
                        (number,),
                    )
                    context = cursor.fetchone() or {}
            errors.append(
                {
                    "customs_declaration_no": number,
                    "contract_no": context.get("contract_no") or "",
                    "error": str(exc),
                }
            )
    failed_numbers = {
        str(error.get("customs_declaration_no") or "") for error in errors
    }
    return {
        "customs_declaration_count": len(numbers),
        "successful_customs_declaration_count": len(results),
        "failed_customs_declaration_count": len(failed_numbers),
        "error_count": len(errors),
        "customs_declaration_numbers": numbers,
        "declaration_month": month,
        "declaration_batch": batch,
        "processed_rows": sum(result["processed_rows"] for result in results),
        "inserted_rows": sum(result["inserted_rows"] for result in results),
        "updated_rows": sum(result["updated_rows"] for result in results),
        "new_inventory_allocation_rows": sum(
            result["new_inventory_allocation_rows"] for result in results
        ),
        "new_inventory_allocated_quantity": sum(
            result["new_inventory_allocated_quantity"] for result in results
        ),
        "files": results,
        "errors": errors,
        "table": "tax_refund_export_details",
    }
