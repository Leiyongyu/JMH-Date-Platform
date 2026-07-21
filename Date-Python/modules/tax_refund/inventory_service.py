"""退税库存的事务预占、确认、释放、冲销和审计查询。"""
from __future__ import annotations

import json
from decimal import Decimal
from typing import Any

from infrastructure.database import get_conn


class InventoryAllocationError(RuntimeError):
    """库存分配冲突或业务校验失败。"""


def _decimal(value: Any) -> Decimal:
    return Decimal(str(value or 0))


def _json_load(value: Any) -> Any:
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value
    return value


def _placeholders(values: list[Any]) -> str:
    if not values:
        raise InventoryAllocationError("库存分配缺少出口明细")
    return ",".join(["%s"] * len(values))


def get_generation_by_task(task_id: int) -> dict | None:
    conn = get_conn()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("SELECT * FROM refund_generation WHERE api_task_id=%s", (task_id,))
        row = cursor.fetchone()
        if row:
            row["result_payload"] = _json_load(row.get("result_payload"))
        return row
    finally:
        cursor.close()
        conn.close()


def reserve_plan(
    *, task_id: int, idempotency_key: str | None, declaration_month: str,
    operator_id: str, operator_name: str, target_dir: str, staging_dir: str,
    plan: list[dict[str, Any]],
) -> int:
    """在一个短事务内锁定出口和库存行，并按计划转为预占。"""
    allocations = [row for group in plan for row in group["purchases"]]
    export_rows = [row for group in plan for row in group["exports"]]
    export_ids = list(dict.fromkeys(int(row["id"]) for row in export_rows))
    if not allocations:
        raise InventoryAllocationError("没有可预占的进货库存")

    conn = get_conn()
    cursor = conn.cursor(dictionary=True)
    try:
        conn.start_transaction()
        cursor.execute(
            """
            INSERT INTO refund_generation (
                api_task_id, idempotency_key, declaration_month,
                output_directory, staging_directory, generation_status,
                generated_by_id, generated_by_name
            ) VALUES (%s,%s,%s,%s,%s,'PREPARING',%s,%s)
            ON DUPLICATE KEY UPDATE id=LAST_INSERT_ID(id)
            """,
            (
                task_id, idempotency_key, declaration_month, target_dir, staging_dir,
                operator_id, operator_name,
            ),
        )
        generation_id = int(cursor.lastrowid)
        cursor.execute(
            "SELECT api_task_id, generation_status FROM refund_generation WHERE id=%s FOR UPDATE",
            (generation_id,),
        )
        generation = cursor.fetchone()
        if int(generation["api_task_id"]) != task_id:
            raise InventoryAllocationError("幂等键已被另一个退税任务使用")
        if generation["generation_status"] not in ("PREPARING", "FAILED"):
            raise InventoryAllocationError(
                f"任务已有不可重复预占的生成记录: {generation['generation_status']}"
            )

        cursor.execute(
            f"""
            SELECT id, inventory_allocation_status
            FROM export_detail
            WHERE id IN ({_placeholders(export_ids)}) AND is_deleted=0
            FOR UPDATE
            """,
            tuple(export_ids),
        )
        locked_exports = {int(row["id"]): row for row in cursor.fetchall()}
        if len(locked_exports) != len(export_ids):
            raise InventoryAllocationError("部分出口明细不存在或已删除")
        conflicts = [
            row_id for row_id, row in locked_exports.items()
            if row["inventory_allocation_status"] in ("RESERVED", "ALLOCATED")
        ]
        if conflicts:
            raise InventoryAllocationError(f"出口明细已被其他退税任务占用: {conflicts}")

        for allocation in allocations:
            lot_id = int(allocation["lot_id"])
            export_id = int(allocation["export_id"])
            quantity = _decimal(allocation.get("allocated_quantity") or allocation.get("数量"))
            if quantity <= 0:
                raise InventoryAllocationError(f"库存 {lot_id} 的预占数量必须大于0")

            cursor.execute(
                "SELECT * FROM purchase_inventory WHERE id=%s AND is_deleted=0 FOR UPDATE",
                (lot_id,),
            )
            lot = cursor.fetchone()
            if not lot:
                raise InventoryAllocationError(f"进货库存不存在: {lot_id}")
            if lot["inventory_status"] in ("LOCKED", "CANCELLED"):
                raise InventoryAllocationError(f"进货库存不可用: {lot_id}")

            remaining_before = _decimal(lot["remaining_quantity"])
            if remaining_before < quantity:
                raise InventoryAllocationError(
                    f"库存发生并发变化，请重试：{lot['invoice_no']} 行{lot['invoice_item_no']} "
                    f"需要{quantity}，当前仅剩{remaining_before}"
                )

            sku = str(lot.get("sku_normalized") or "").strip()
            supplier = str(lot.get("supplier_tax_no") or "").strip()
            if allocation.get("match_mode") != "RELATION" and sku and supplier:
                cursor.execute(
                    """
                    SELECT id FROM purchase_inventory
                    WHERE sku_normalized=%s AND supplier_tax_no=%s
                      AND is_deleted=0 AND remaining_quantity>0
                      AND inventory_status NOT IN ('LOCKED','CANCELLED')
                    ORDER BY invoice_date, invoice_no, invoice_item_no, id
                    LIMIT 1 FOR UPDATE
                    """,
                    (sku, supplier),
                )
                first_lot = cursor.fetchone()
                if not first_lot or int(first_lot["id"]) != lot_id:
                    raise InventoryAllocationError(
                        f"SKU {sku} 的FIFO顺序已变化，请重新生成任务"
                    )

            remaining_after = remaining_before - quantity
            reserved_after = _decimal(lot.get("reserved_quantity")) + quantity
            allocated_now = _decimal(lot.get("allocated_quantity"))
            if remaining_after == 0 and reserved_after > 0:
                inventory_status = "RESERVED"
            elif allocated_now > 0 or reserved_after > 0:
                inventory_status = "PARTIAL"
            else:
                inventory_status = "AVAILABLE"
            cursor.execute(
                """
                UPDATE purchase_inventory
                SET reserved_quantity=reserved_quantity+%s,
                    remaining_quantity=remaining_quantity-%s,
                    inventory_status=%s, last_allocation_task_id=%s,
                    version=version+1, updated_by=%s
                WHERE id=%s AND remaining_quantity>=%s
                """,
                (
                    quantity, quantity, inventory_status, task_id,
                    operator_id, lot_id, quantity,
                ),
            )
            if cursor.rowcount != 1:
                raise InventoryAllocationError(f"库存 {lot_id} 预占失败，请重试")

            export_snapshot = next(row for row in export_rows if int(row["id"]) == export_id)
            cursor.execute(
                """
                INSERT INTO refund_inventory_allocation (
                    generation_id, api_task_id, entry_type, allocation_status,
                    export_detail_id, customs_declaration_no, customs_item_no,
                    purchase_inventory_id, invoice_no, invoice_item_no, invoice_date,
                    supplier_tax_no, sku_original, sku_normalized, relation_no,
                    quantity_before, allocated_quantity, quantity_after,
                    operated_by_id, operated_by_name
                ) VALUES (
                    %s,%s,'ALLOCATION','RESERVED',%s,%s,%s,
                    %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s
                )
                """,
                (
                    generation_id, task_id, export_id,
                    export_snapshot.get("customs_declaration_no") or "",
                    export_snapshot.get("customs_item_no") or "",
                    lot_id, lot["invoice_no"], lot["invoice_item_no"], lot["invoice_date"],
                    lot["supplier_tax_no"], lot.get("sku_original"), lot.get("sku_normalized"),
                    allocation.get("关联号"), remaining_before, quantity, remaining_after,
                    operator_id, operator_name,
                ),
            )

        cursor.execute(
            f"""
            UPDATE export_detail
            SET inventory_allocation_status='RESERVED',
                latest_refund_generation_id=%s, updated_by=%s
            WHERE id IN ({_placeholders(export_ids)})
            """,
            (generation_id, operator_id, *export_ids),
        )
        cursor.execute(
            """
            UPDATE refund_generation
            SET generation_status='RESERVED', output_directory=%s,
                staging_directory=%s, error_message=NULL
            WHERE id=%s
            """,
            (target_dir, staging_dir, generation_id),
        )
        conn.commit()
        return generation_id
    except Exception:
        conn.rollback()
        raise
    finally:
        cursor.close()
        conn.close()


def confirm_generation(
    generation_id: int, result_payload: dict[str, Any], operator_id: str,
) -> None:
    """文件已在临时目录生成后，将预占正式转为已分配。"""
    conn = get_conn()
    cursor = conn.cursor(dictionary=True)
    try:
        conn.start_transaction()
        cursor.execute(
            "SELECT * FROM refund_generation WHERE id=%s FOR UPDATE", (generation_id,)
        )
        generation = cursor.fetchone()
        if not generation:
            raise InventoryAllocationError("退税生成批次不存在")
        if generation["generation_status"] == "FILE_PENDING":
            conn.commit()
            return
        if generation["generation_status"] != "RESERVED":
            raise InventoryAllocationError(
                f"生成批次状态不允许确认: {generation['generation_status']}"
            )
        cursor.execute(
            """
            SELECT * FROM refund_inventory_allocation
            WHERE generation_id=%s AND entry_type='ALLOCATION'
              AND allocation_status='RESERVED'
            ORDER BY id FOR UPDATE
            """,
            (generation_id,),
        )
        allocations = cursor.fetchall()
        if not allocations:
            raise InventoryAllocationError("生成批次没有预占流水")

        export_values: dict[int, dict[str, Any]] = {}
        for allocation in allocations:
            quantity = _decimal(allocation["allocated_quantity"])
            cursor.execute(
                "SELECT * FROM purchase_inventory WHERE id=%s FOR UPDATE",
                (allocation["purchase_inventory_id"],),
            )
            lot = cursor.fetchone()
            if not lot or _decimal(lot.get("reserved_quantity")) < quantity:
                raise InventoryAllocationError("预占库存数据不一致，无法确认扣减")
            reserved_after = _decimal(lot["reserved_quantity"]) - quantity
            allocated_after = _decimal(lot["allocated_quantity"]) + quantity
            remaining = _decimal(lot["remaining_quantity"])
            status = "EXHAUSTED" if remaining == 0 and reserved_after == 0 else "PARTIAL"
            cursor.execute(
                """
                UPDATE purchase_inventory
                SET reserved_quantity=reserved_quantity-%s,
                    allocated_quantity=allocated_quantity+%s,
                    inventory_status=%s, last_allocated_at=NOW(3),
                    last_allocation_task_id=%s, version=version+1,
                    updated_by=%s
                WHERE id=%s AND reserved_quantity>=%s
                """,
                (
                    quantity, quantity, status, generation["api_task_id"], operator_id,
                    allocation["purchase_inventory_id"], quantity,
                ),
            )
            export_values[int(allocation["export_detail_id"])] = {
                "relation_no": allocation.get("relation_no")
            }

        cursor.execute(
            """
            UPDATE refund_inventory_allocation
            SET allocation_status='COMMITTED'
            WHERE generation_id=%s AND entry_type='ALLOCATION'
              AND allocation_status='RESERVED'
            """,
            (generation_id,),
        )
        for export_id, values in export_values.items():
            relation = values["relation_no"] or ""
            declaration_batch = relation[6:9] if len(relation) >= 9 else None
            sequence_no = relation[9:17] if len(relation) >= 17 else None
            cursor.execute(
                """
                UPDATE export_detail
                SET inventory_allocation_status='ALLOCATED',
                    declaration_status='ALLOCATED', declaration_month=%s,
                    declaration_batch=%s, sequence_no=%s, relation_no=%s,
                    inventory_allocated_at=NOW(3), updated_by=%s
                WHERE id=%s AND latest_refund_generation_id=%s
                """,
                (
                    generation["declaration_month"], declaration_batch, sequence_no,
                    relation or None, operator_id, export_id, generation_id,
                ),
            )
        cursor.execute(
            """
            UPDATE refund_generation
            SET generation_status='FILE_PENDING', generated_at=NOW(3),
                committed_at=NOW(3), result_payload=%s, error_message=NULL
            WHERE id=%s
            """,
            (json.dumps(result_payload, ensure_ascii=False, default=str), generation_id),
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        cursor.close()
        conn.close()


def mark_generation_published(generation_id: int, output_directory: str) -> None:
    conn = get_conn()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            UPDATE refund_generation
            SET generation_status='COMMITTED', output_directory=%s,
                staging_directory=NULL, error_message=NULL
            WHERE id=%s AND generation_status IN ('FILE_PENDING','COMMITTED')
            """,
            (output_directory, generation_id),
        )
        conn.commit()
    finally:
        cursor.close()
        conn.close()


def release_generation(generation_id: int, error_message: str) -> None:
    """生成失败时释放所有仍处于 RESERVED 的库存，不删除审计流水。"""
    conn = get_conn()
    cursor = conn.cursor(dictionary=True)
    try:
        conn.start_transaction()
        cursor.execute(
            "SELECT * FROM refund_generation WHERE id=%s FOR UPDATE", (generation_id,)
        )
        generation = cursor.fetchone()
        if not generation or generation["generation_status"] not in ("PREPARING", "RESERVED"):
            conn.commit()
            return
        cursor.execute(
            """
            SELECT * FROM refund_inventory_allocation
            WHERE generation_id=%s AND entry_type='ALLOCATION'
              AND allocation_status='RESERVED'
            ORDER BY id FOR UPDATE
            """,
            (generation_id,),
        )
        allocations = cursor.fetchall()
        export_ids = set()
        for allocation in allocations:
            export_ids.add(int(allocation["export_detail_id"]))
            quantity = _decimal(allocation["allocated_quantity"])
            cursor.execute(
                "SELECT * FROM purchase_inventory WHERE id=%s FOR UPDATE",
                (allocation["purchase_inventory_id"],),
            )
            lot = cursor.fetchone()
            if not lot or _decimal(lot["reserved_quantity"]) < quantity:
                raise InventoryAllocationError("释放预占时发现库存数据不一致")
            reserved_after = _decimal(lot["reserved_quantity"]) - quantity
            allocated = _decimal(lot["allocated_quantity"])
            status = "AVAILABLE" if allocated == 0 and reserved_after == 0 else "PARTIAL"
            cursor.execute(
                """
                UPDATE purchase_inventory
                SET reserved_quantity=reserved_quantity-%s,
                    remaining_quantity=remaining_quantity+%s,
                    inventory_status=%s, version=version+1
                WHERE id=%s AND reserved_quantity>=%s
                """,
                (quantity, quantity, status, allocation["purchase_inventory_id"], quantity),
            )
        cursor.execute(
            """
            UPDATE refund_inventory_allocation SET allocation_status='RELEASED'
            WHERE generation_id=%s AND entry_type='ALLOCATION'
              AND allocation_status='RESERVED'
            """,
            (generation_id,),
        )
        if export_ids:
            cursor.execute(
                f"""
                UPDATE export_detail
                SET inventory_allocation_status='UNALLOCATED',
                    latest_refund_generation_id=NULL
                WHERE latest_refund_generation_id=%s
                  AND id IN ({_placeholders(list(export_ids))})
                """,
                (generation_id, *export_ids),
            )
        cursor.execute(
            """
            UPDATE refund_generation
            SET generation_status='FAILED', error_message=%s
            WHERE id=%s
            """,
            (str(error_message)[:10000], generation_id),
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        cursor.close()
        conn.close()


def reverse_generation(
    generation_id: int, operator_id: str, operator_name: str, reason: str,
    reverse_task_id: int,
) -> dict[str, Any]:
    """冲销已确认批次；原流水保留，新增 REVERSAL 流水。"""
    if not reason.strip():
        raise InventoryAllocationError("冲销原因不能为空")
    conn = get_conn()
    cursor = conn.cursor(dictionary=True)
    try:
        conn.start_transaction()
        cursor.execute(
            "SELECT * FROM refund_generation WHERE id=%s FOR UPDATE", (generation_id,)
        )
        generation = cursor.fetchone()
        if not generation:
            raise InventoryAllocationError("退税生成批次不存在")
        if generation["generation_status"] == "REVERSED":
            conn.commit()
            return {"generation_id": generation_id, "status": "REVERSED", "duplicate": True}
        if generation["generation_status"] != "COMMITTED":
            raise InventoryAllocationError(
                f"只有COMMITTED批次可以冲销，当前为{generation['generation_status']}"
            )
        cursor.execute(
            """
            SELECT * FROM refund_inventory_allocation
            WHERE generation_id=%s AND entry_type='ALLOCATION'
              AND allocation_status='COMMITTED'
            ORDER BY id FOR UPDATE
            """,
            (generation_id,),
        )
        allocations = cursor.fetchall()
        export_ids = set()
        reversed_quantity = Decimal("0")
        for allocation in allocations:
            export_ids.add(int(allocation["export_detail_id"]))
            quantity = _decimal(allocation["allocated_quantity"])
            cursor.execute(
                "SELECT * FROM purchase_inventory WHERE id=%s FOR UPDATE",
                (allocation["purchase_inventory_id"],),
            )
            lot = cursor.fetchone()
            if not lot or _decimal(lot["allocated_quantity"]) < quantity:
                raise InventoryAllocationError("冲销时发现库存已分配数量不一致")
            before = _decimal(lot["remaining_quantity"])
            after = before + quantity
            allocated_after = _decimal(lot["allocated_quantity"]) - quantity
            reserved = _decimal(lot["reserved_quantity"])
            status = "AVAILABLE" if allocated_after == 0 and reserved == 0 else "PARTIAL"
            cursor.execute(
                """
                UPDATE purchase_inventory
                SET allocated_quantity=allocated_quantity-%s,
                    remaining_quantity=remaining_quantity+%s,
                    inventory_status=%s, version=version+1,
                    last_allocation_task_id=%s, updated_by=%s
                WHERE id=%s AND allocated_quantity>=%s
                """,
                (
                    quantity, quantity, status, reverse_task_id, operator_id,
                    allocation["purchase_inventory_id"], quantity,
                ),
            )
            cursor.execute(
                """
                INSERT INTO refund_inventory_allocation (
                    generation_id, api_task_id, entry_type, allocation_status,
                    reversal_of_id, export_detail_id, customs_declaration_no,
                    customs_item_no, purchase_inventory_id, invoice_no,
                    invoice_item_no, invoice_date, supplier_tax_no, sku_original,
                    sku_normalized, relation_no, quantity_before,
                    allocated_quantity, quantity_after, operated_by_id, operated_by_name
                ) VALUES (
                    %s,%s,'REVERSAL','COMMITTED',%s,%s,%s,%s,%s,%s,
                    %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s
                )
                """,
                (
                    generation_id, reverse_task_id, allocation["id"],
                    allocation["export_detail_id"], allocation["customs_declaration_no"],
                    allocation["customs_item_no"], allocation["purchase_inventory_id"],
                    allocation["invoice_no"], allocation["invoice_item_no"],
                    allocation["invoice_date"], allocation["supplier_tax_no"],
                    allocation.get("sku_original"), allocation.get("sku_normalized"),
                    allocation.get("relation_no"), before, quantity, after,
                    operator_id, operator_name,
                ),
            )
            reversed_quantity += quantity
        if export_ids:
            cursor.execute(
                f"""
                UPDATE export_detail
                SET inventory_allocation_status='UNALLOCATED',
                    declaration_status='PENDING', declaration_month=NULL,
                    declaration_batch=NULL, sequence_no=NULL, relation_no=NULL,
                    latest_refund_generation_id=NULL, inventory_allocated_at=NULL,
                    updated_by=%s
                WHERE latest_refund_generation_id=%s
                  AND id IN ({_placeholders(list(export_ids))})
                """,
                (operator_id, generation_id, *export_ids),
            )
        cursor.execute(
            """
            UPDATE refund_generation
            SET generation_status='REVERSED', reversed_at=NOW(3),
                reversed_by_id=%s, reversed_by_name=%s, reversal_reason=%s
            WHERE id=%s
            """,
            (operator_id, operator_name, reason.strip(), generation_id),
        )
        conn.commit()
        return {
            "generation_id": generation_id,
            "status": "REVERSED",
            "allocation_count": len(allocations),
            "reversed_quantity": str(reversed_quantity),
        }
    except Exception:
        conn.rollback()
        raise
    finally:
        cursor.close()
        conn.close()


def list_generations(page: int = 1, page_size: int = 20, **filters) -> tuple[list[dict], int]:
    clauses = ["1=1"]
    params: list[Any] = []
    for key, column in (
        ("status", "generation_status"), ("operator_id", "generated_by_id"),
        ("declaration_month", "declaration_month"),
    ):
        if filters.get(key):
            clauses.append(f"{column}=%s")
            params.append(str(filters[key]).strip())
    where = " AND ".join(clauses)
    conn = get_conn()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(
            f"SELECT * FROM refund_generation WHERE {where} ORDER BY id DESC LIMIT %s OFFSET %s",
            (*params, page_size, (page - 1) * page_size),
        )
        rows = cursor.fetchall()
        for row in rows:
            row["result_payload"] = _json_load(row.get("result_payload"))
        cursor.execute(f"SELECT COUNT(*) AS cnt FROM refund_generation WHERE {where}", params)
        return rows, int(cursor.fetchone()["cnt"])
    finally:
        cursor.close()
        conn.close()


def list_allocations(page: int = 1, page_size: int = 50, **filters) -> tuple[list[dict], int]:
    clauses = ["1=1"]
    params: list[Any] = []
    for key, column in (
        ("generation_id", "generation_id"), ("invoice_no", "invoice_no"),
        ("sku_normalized", "sku_normalized"),
        ("customs_declaration_no", "customs_declaration_no"),
        ("operator_id", "operated_by_id"), ("entry_type", "entry_type"),
        ("status", "allocation_status"),
    ):
        if filters.get(key) not in (None, ""):
            clauses.append(f"{column}=%s")
            params.append(filters[key])
    where = " AND ".join(clauses)
    conn = get_conn()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(
            f"""
            SELECT * FROM refund_inventory_allocation
            WHERE {where} ORDER BY id DESC LIMIT %s OFFSET %s
            """,
            (*params, page_size, (page - 1) * page_size),
        )
        rows = cursor.fetchall()
        cursor.execute(
            f"SELECT COUNT(*) AS cnt FROM refund_inventory_allocation WHERE {where}", params
        )
        return rows, int(cursor.fetchone()["cnt"])
    finally:
        cursor.close()
        conn.close()
