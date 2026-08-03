from __future__ import annotations

import re
from decimal import Decimal, ROUND_HALF_UP
from typing import Any


ZERO = Decimal("0")
CENT = Decimal("0.01")


def decimal_value(value: Any) -> Decimal:
    if value is None:
        return ZERO
    return Decimal(str(value))


def normalize_sku(value: Any) -> str:
    return re.sub(r"\s+", "", str(value or "")).upper()


def normalize_product_name(value: Any) -> str:
    """报关品名可能按“中文换行英文”保存，通用库存只用第一行中文品名匹配。"""
    lines = [line.strip() for line in str(value or "").splitlines() if line.strip()]
    return normalize_sku(lines[0] if lines else "")


def is_placeholder_sku(value: Any) -> bool:
    return normalize_sku(value) in {
        "无型号", "無型號", "无规格", "無規格", "N/A", "NA", "NONE", "-", "—",
    }


def compatible_inventory_skus(value: Any) -> tuple[str, ...]:
    """兼容采购备注中SKU有无JMH前缀及JMH后的连接符差异。"""
    sku = normalize_sku(value)
    match = re.fullmatch(r"(?:JMH-?)?(\d{5,6}-\d{4})", sku)
    if not match:
        return (sku,) if sku else ()
    body = match.group(1)
    return (f"JMH{body}", f"JMH-{body}", body)


def normalized_unit(value: Any) -> str:
    return re.sub(r"\s+", "", str(value or "")).upper()


def compatible_inventory_units(value: Any) -> tuple[str, ...]:
    """返回FIFO可互换的计数单位；数据库和导出仍保留各自原始单位。"""
    unit = normalized_unit(value)
    if unit in {"个", "只"}:
        return ("个", "只")
    return (unit,)


def tax_rate_percent(value: Any) -> Decimal:
    text = str(value or "").strip()
    if text.endswith("%"):
        try:
            return Decimal(text[:-1])
        except Exception:
            return ZERO
    return ZERO


def sync_invoice_inventory(
    cursor, records: list[dict[str, Any]], invoice_no: str | None = None
) -> dict[str, int]:
    """在采购汇总上传事务内按发票同步可用SKU库存；已消耗数量永不恢复。"""
    invoice_no = str(invoice_no or (records[0]["invoice_no"] if records else "")).strip()
    if not invoice_no:
        raise ValueError("同步采购发票库存时缺少发票号码")
    cursor.execute(
        "SELECT * FROM purchase_invoice_inventory WHERE invoice_no = %s FOR UPDATE",
        (invoice_no,),
    )
    existing = {int(row["item_sequence"]): row for row in cursor.fetchall()}
    incoming_sequences: set[int] = set()
    inserted = 0
    updated = 0

    for record in records:
        sequence = int(record["item_sequence"])
        incoming_sequences.add(sequence)
        specification = str(record.get("specification") or "").strip()
        inventory_match_type = str(
            record.get("inventory_match_type") or "SKU"
        ).strip().upper()
        sku = (
            normalize_product_name(specification)
            if inventory_match_type == "PRODUCT_NAME"
            else normalize_sku(specification)
        )
        unit = str(record.get("unit") or "").strip()
        quantity = decimal_value(record.get("quantity"))
        amount = decimal_value(record.get("amount")).quantize(CENT)
        tax_amount = decimal_value(record.get("tax_amount")).quantize(CENT)
        if not sku or not specification:
            raise ValueError(f"发票商品序号{sequence}缺少规格型号，无法建立SKU库存")
        if inventory_match_type not in {"SKU", "PRODUCT_NAME"}:
            raise ValueError(
                f"发票商品序号{sequence}库存匹配类型无效：{inventory_match_type}"
            )
        if not unit:
            raise ValueError(f"发票商品序号{sequence}缺少单位，无法建立库存")
        if quantity <= ZERO:
            raise ValueError(f"发票商品序号{sequence}数量必须大于0")

        current = existing.get(sequence)
        if current:
            consumed_quantity = decimal_value(current["original_quantity"]) - decimal_value(
                current["available_quantity"]
            )
            consumed_amount = decimal_value(current["original_amount"]) - decimal_value(
                current["available_amount"]
            )
            consumed_tax = decimal_value(current["original_tax_amount"]) - decimal_value(
                current["available_tax_amount"]
            )
            if consumed_quantity > ZERO:
                immutable_changed = (
                    current["normalized_sku"] != sku
                    or current["inventory_match_type"] != inventory_match_type
                    or compatible_inventory_units(current["unit"])
                    != compatible_inventory_units(unit)
                    or current["invoice_date"] != record["invoice_date"]
                    or current["seller_tax_id"] != record["seller_tax_id"]
                )
                if immutable_changed:
                    raise ValueError(
                        f"发票{invoice_no}商品序号{sequence}已有库存扣减，不能修改SKU、单位、日期或销售方"
                    )
            if quantity < consumed_quantity or amount < consumed_amount or tax_amount < consumed_tax:
                raise ValueError(
                    f"发票{invoice_no}商品序号{sequence}的新数量或金额小于已扣减值，不能覆盖"
                )
            cursor.execute(
                "UPDATE purchase_invoice_inventory SET invoice_date=%s, seller_name=%s, "
                "seller_tax_id=%s, project_name=%s, specification=%s, normalized_sku=%s, unit=%s, "
                "inventory_match_type=%s, "
                "original_quantity=%s, available_quantity=%s, unit_price=%s, original_amount=%s, "
                "available_amount=%s, tax_rate=%s, original_tax_amount=%s, available_tax_amount=%s, "
                "source_hash=%s WHERE id=%s",
                (
                    record["invoice_date"], record["seller_name"], record["seller_tax_id"],
                    record["project_name"], specification, sku, unit,
                    inventory_match_type, quantity,
                    quantity - consumed_quantity, record.get("unit_price"), amount,
                    amount - consumed_amount, record["tax_rate"], tax_amount,
                    tax_amount - consumed_tax, record["source_hash"], current["id"],
                ),
            )
            updated += 1
        else:
            cursor.execute(
                "INSERT INTO purchase_invoice_inventory "
                "(invoice_no, invoice_date, seller_name, seller_tax_id, item_sequence, project_name, "
                "specification, normalized_sku, inventory_match_type, unit, "
                "original_quantity, available_quantity, "
                "unit_price, original_amount, available_amount, tax_rate, original_tax_amount, "
                "available_tax_amount, source_hash) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (
                    invoice_no, record["invoice_date"], record["seller_name"], record["seller_tax_id"],
                    sequence, record["project_name"], specification, sku,
                    inventory_match_type, unit, quantity, quantity,
                    record.get("unit_price"), amount, amount, record["tax_rate"], tax_amount,
                    tax_amount, record["source_hash"],
                ),
            )
            inserted += 1

    removed_sequences = set(existing) - incoming_sequences
    for sequence in removed_sequences:
        current = existing[sequence]
        consumed = decimal_value(current["original_quantity"]) - decimal_value(
            current["available_quantity"]
        )
        if consumed > ZERO:
            raise ValueError(
                f"发票{invoice_no}商品序号{sequence}已有库存扣减，重新上传时不能删除该商品"
            )
        cursor.execute("DELETE FROM purchase_invoice_inventory WHERE id = %s", (current["id"],))

    return {
        "inventory_rows": len(records),
        "inventory_inserted_rows": inserted,
        "inventory_updated_rows": updated,
    }


def allocated_money(available_money: Decimal, take: Decimal, available_quantity: Decimal) -> Decimal:
    if take == available_quantity:
        return available_money
    return (available_money * take / available_quantity).quantize(CENT, rounding=ROUND_HALF_UP)


def purchase_detail_from_allocation(
    export_row: dict[str, Any], allocation: dict[str, Any], generation_id: str
) -> dict[str, Any]:
    levy_rate = tax_rate_percent(allocation["tax_rate"])
    inventory_id = int(allocation["inventory_id"])
    allocation_id = int(allocation["allocation_id"])
    sequence = int(allocation["allocation_sequence"])
    sku = allocation["specification"]
    match_label = (
        "通用品名"
        if allocation.get("inventory_match_type") == "PRODUCT_NAME"
        else "精确SKU"
    )
    return {
        "detail_key": f"FIFO:{export_row['id']}:{inventory_id}",
        "source_type": "FIFO_INVOICE",
        "inventory_allocation_id": allocation_id,
        "allocation_sequence": sequence,
        "declaration_month": export_row["declaration_month"],
        "declaration_batch": export_row["declaration_batch"],
        "sequence_no": export_row["sequence_no"],
        "correlation_no": export_row["correlation_no"],
        "contract_no": export_row.get("contract_no"),
        "tax_type": "V|增值税",
        "refundable_tax_amount": allocation["allocated_tax_amount"],
        "supplier_tax_id": allocation["seller_tax_id"],
        "purchase_voucher_no": allocation["invoice_no"],
        "invoice_date": allocation["invoice_date"],
        "export_product_code": export_row["export_product_code"],
        "export_product_name": export_row["export_product_name"],
        "measurement_unit": export_row["measurement_unit"],
        "quantity": allocation["allocated_quantity"],
        "taxable_amount": allocation["allocated_amount"],
        "levy_rate_percent": levy_rate,
        "refund_rate_percent": levy_rate,
        "remark": (
            f"FIFO库存分配；发票商品序号{allocation['item_sequence']}；"
            f"{match_label} {sku}"
        ),
        "upload_batch_id": generation_id,
        "uploaded_file_name": "FIFO库存分配",
        "source_hash": allocation["source_hash"],
        "source_sheet": "采购发票汇总",
        "source_row": int(allocation["item_sequence"]),
    }


def insert_purchase_detail(cursor, record: dict[str, Any]) -> None:
    columns = list(record)
    quoted_columns = ", ".join(f"`{column}`" for column in columns)
    placeholders = ", ".join(["%s"] * len(columns))
    updates = ", ".join(
        f"`{column}` = VALUES(`{column}`)"
        for column in columns
        if column != "detail_key"
    )
    cursor.execute(
        f"INSERT INTO tax_refund_purchase_details ({quoted_columns}) VALUES ({placeholders}) "
        f"ON DUPLICATE KEY UPDATE {updates}",
        tuple(record[column] for column in columns),
    )


def _ensure_fifo_allocations_strict(
    cursor, export_rows: list[dict[str, Any]], generation_id: str
) -> dict[str, Any]:
    """对没有手工进货明细的报关来源出口行执行SKU+单位FIFO分配。"""
    newly_allocated_quantity = ZERO
    new_allocation_rows = 0
    for export_row in sorted(export_rows, key=lambda row: row["correlation_no"]):
        raw_sku = export_row.get("inventory_sku")
        compatible_skus = (
            () if is_placeholder_sku(raw_sku) else compatible_inventory_skus(raw_sku)
        )
        product_name = normalize_product_name(export_row.get("export_product_name"))
        unit = str(export_row.get("measurement_unit") or "").strip()
        demand = decimal_value(export_row.get("export_quantity"))
        if not compatible_skus and not product_name:
            raise ValueError(
                f"关联号{export_row['correlation_no']}缺少可用的商品规格型号和品名，"
                "无法匹配发票库存"
            )
        if not unit or demand <= ZERO:
            raise ValueError(
                f"关联号{export_row['correlation_no']}的单位或出口数量无效，无法扣减库存"
            )

        cursor.execute(
            "SELECT a.id AS allocation_id, a.inventory_id, a.allocation_sequence, "
            "a.allocated_quantity, a.allocated_amount, a.allocated_tax_amount, "
            "i.invoice_no, i.invoice_date, i.seller_name, i.seller_tax_id, i.item_sequence, "
            "i.project_name, i.specification, i.inventory_match_type, "
            "i.unit, i.tax_rate, i.source_hash "
            "FROM purchase_inventory_allocations a "
            "JOIN purchase_invoice_inventory i ON i.id = a.inventory_id "
            "WHERE a.export_detail_id = %s ORDER BY a.allocation_sequence FOR UPDATE",
            (export_row["id"],),
        )
        allocations = list(cursor.fetchall())
        allocated_total = sum(
            (decimal_value(row["allocated_quantity"]) for row in allocations), ZERO
        )
        if allocated_total > demand:
            raise ValueError(
                f"关联号{export_row['correlation_no']}已扣库存{allocated_total}，大于当前出口数量{demand}"
            )
        remaining = demand - allocated_total
        next_sequence = len(allocations) + 1

        if remaining > ZERO:
            compatible_units = compatible_inventory_units(unit)
            unit_placeholders = ", ".join(["%s"] * len(compatible_units))
            exact_inventory_rows: list[dict[str, Any]] = []
            if compatible_skus:
                sku_placeholders = ", ".join(["%s"] * len(compatible_skus))
                sku_priority_placeholders = ", ".join(
                    ["%s"] * len(compatible_skus)
                )
                cursor.execute(
                    "SELECT * FROM purchase_invoice_inventory "
                    "WHERE inventory_match_type='SKU' "
                    f"AND normalized_sku IN ({sku_placeholders}) "
                    f"AND unit IN ({unit_placeholders}) "
                    "AND available_quantity > 0 "
                    f"ORDER BY FIELD(normalized_sku, {sku_priority_placeholders}), "
                    "invoice_date, invoice_no, item_sequence FOR UPDATE",
                    (*compatible_skus, *compatible_units, *compatible_skus),
                )
                exact_inventory_rows = list(cursor.fetchall())
            generic_inventory_rows: list[dict[str, Any]] = []
            if product_name:
                cursor.execute(
                    "SELECT * FROM purchase_invoice_inventory "
                    "WHERE inventory_match_type='PRODUCT_NAME' "
                    f"AND normalized_sku=%s AND unit IN ({unit_placeholders}) "
                    "AND available_quantity>0 "
                    "ORDER BY invoice_date, invoice_no, item_sequence FOR UPDATE",
                    (product_name, *compatible_units),
                )
                generic_inventory_rows = list(cursor.fetchall())
            inventory_rows = [*exact_inventory_rows, *generic_inventory_rows]
            exact_available = sum(
                (
                    decimal_value(row["available_quantity"])
                    for row in exact_inventory_rows
                ),
                ZERO,
            )
            generic_available = sum(
                (
                    decimal_value(row["available_quantity"])
                    for row in generic_inventory_rows
                ),
                ZERO,
            )
            available_total = sum(
                (decimal_value(row["available_quantity"]) for row in inventory_rows), ZERO
            )
            if available_total < remaining:
                raise ValueError(
                    f"SKU {export_row['inventory_sku']} / 单位{unit}库存不足："
                    f"需要{remaining}，精确SKU可用{exact_available}，"
                    f"同品名“{export_row.get('export_product_name') or ''}”"
                    f"通用库存可用{generic_available}"
                )
            for inventory in inventory_rows:
                if remaining <= ZERO:
                    break
                available_quantity = decimal_value(inventory["available_quantity"])
                take = min(remaining, available_quantity)
                amount = allocated_money(
                    decimal_value(inventory["available_amount"]), take, available_quantity
                )
                tax_amount = allocated_money(
                    decimal_value(inventory["available_tax_amount"]), take, available_quantity
                )
                cursor.execute(
                    "UPDATE purchase_invoice_inventory SET available_quantity = available_quantity - %s, "
                    "available_amount = available_amount - %s, "
                    "available_tax_amount = available_tax_amount - %s WHERE id = %s",
                    (take, amount, tax_amount, inventory["id"]),
                )
                cursor.execute(
                    "INSERT INTO purchase_inventory_allocations "
                    "(generation_id, export_detail_id, correlation_no, inventory_id, "
                    "allocation_sequence, allocated_quantity, allocated_amount, allocated_tax_amount) "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                    (
                        generation_id, export_row["id"], export_row["correlation_no"],
                        inventory["id"], next_sequence, take, amount, tax_amount,
                    ),
                )
                allocation = {
                    "allocation_id": cursor.lastrowid,
                    "inventory_id": inventory["id"],
                    "allocation_sequence": next_sequence,
                    "allocated_quantity": take,
                    "allocated_amount": amount,
                    "allocated_tax_amount": tax_amount,
                    **{
                        key: inventory[key]
                        for key in (
                            "invoice_no", "invoice_date", "seller_name", "seller_tax_id",
                            "item_sequence", "project_name", "specification",
                            "inventory_match_type", "unit",
                            "tax_rate", "source_hash",
                        )
                    },
                }
                allocations.append(allocation)
                remaining -= take
                next_sequence += 1
                new_allocation_rows += 1
                newly_allocated_quantity += take

        for allocation in allocations:
            insert_purchase_detail(
                cursor,
                purchase_detail_from_allocation(export_row, allocation, generation_id),
            )

    return {
        "new_inventory_allocation_rows": new_allocation_rows,
        "new_inventory_allocated_quantity": newly_allocated_quantity,
    }


def ensure_fifo_allocations(
    cursor,
    export_rows: list[dict[str, Any]],
    generation_id: str,
    collect_errors: bool = False,
) -> dict[str, Any]:
    """FIFO分配；批量转换时可逐商品回滚并收集全部业务错误。"""
    if not collect_errors:
        return _ensure_fifo_allocations_strict(cursor, export_rows, generation_id)

    new_allocation_rows = 0
    newly_allocated_quantity = ZERO
    errors: list[dict[str, Any]] = []
    for position, export_row in enumerate(
        sorted(export_rows, key=lambda row: row["correlation_no"]), start=1
    ):
        savepoint = f"fifo_item_{position}"
        cursor.execute(f"SAVEPOINT {savepoint}")
        try:
            result = _ensure_fifo_allocations_strict(
                cursor, [export_row], generation_id
            )
            new_allocation_rows += int(result["new_inventory_allocation_rows"])
            newly_allocated_quantity += decimal_value(
                result["new_inventory_allocated_quantity"]
            )
        except ValueError as exc:
            cursor.execute(f"ROLLBACK TO SAVEPOINT {savepoint}")
            full_customs_no = str(
                export_row.get("customs_declaration_no") or ""
            ).strip()
            errors.append(
                {
                    "customs_declaration_no": full_customs_no[:18],
                    "contract_no": str(export_row.get("contract_no") or ""),
                    "item_no": full_customs_no[-3:] if len(full_customs_no) >= 21 else "",
                    "sku": str(export_row.get("inventory_sku") or ""),
                    "product_name": str(
                        export_row.get("export_product_name") or ""
                    ).splitlines()[0],
                    "quantity": str(export_row.get("export_quantity") or ""),
                    "unit": str(export_row.get("measurement_unit") or ""),
                    "error": str(exc),
                }
            )
        finally:
            cursor.execute(f"RELEASE SAVEPOINT {savepoint}")

    return {
        "new_inventory_allocation_rows": new_allocation_rows,
        "new_inventory_allocated_quantity": newly_allocated_quantity,
        "errors": errors,
    }
