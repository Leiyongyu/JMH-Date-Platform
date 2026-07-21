"""退税模块数据访问层。封装 SQL，不暴露连接细节给 service。

已实现：报关资料、出口明细、进货库存、外汇应收 的 CRUD。
以下函数桥接到旧 models/（后续逐步迁移到此文件）：
  - 任务管理：create_task, get_task, list_tasks, mark_task_*, update_task_progress
  - 批次管理：check_duplicate_file, create_import_batch, update_import_batch
  - 统计查询：count_allocations, count_receipts
  - 退税源数据：get_refund_exports, get_refund_forex_rows, get_refund_purchases
"""
from __future__ import annotations

from decimal import Decimal
from typing import Any

from infrastructure.database import get_conn
from modules.tax_refund.customs_numbers import customs_base_number, customs_item_number

# ── 桥接：尚未迁移到新 repository 的函数 ──
from models.api_task import (  # noqa: F401
    create_task,
    get_task,
    list_tasks,
    mark_task_failed,
    mark_task_running,
    mark_task_success,
    update_task_progress,
)
from models.excel_item import (  # noqa: F401
    get_excel_items_by_contract,
    insert_excel_item,
)
from models.forex_allocation import count_allocations  # noqa: F401
from models.forex_receipt import count_receipts  # noqa: F401
from models.import_batch import (  # noqa: F401
    check_duplicate_file,
    create_import_batch,
    update_import_batch,
)
from models.refund_source import (  # noqa: F401
    get_refund_exports,
    get_refund_forex_rows,
    get_refund_purchases,
)


# ── 报关资料商品 ──

def get_current_excel_items_map(contract_no: str) -> tuple[dict[str, dict], list[str]]:
    """取得一个合同当前有效的报关资料商品，以标准化项号为键。返回 (map, duplicates)。"""
    conn = get_conn()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("""
            SELECT * FROM customs_declaration_excel_item
            WHERE contract_agreement_no = %s AND is_current = 1 AND is_deleted = 0
            ORDER BY CAST(product_sequence_normalized AS UNSIGNED), id
        """, (contract_no,))
        rows = cursor.fetchall()
    finally:
        cursor.close()
        conn.close()

    result: dict[str, dict] = {}
    duplicates: set[str] = set()
    for row in rows:
        key = str(row['product_sequence_normalized']).lstrip('0') or '0'
        if key in result:
            duplicates.add(key)
        result[key] = row
    return result, sorted(
        duplicates,
        key=lambda v: (0, int(v)) if v.isdigit() else (1, v),
    )


def set_excel_items_old_version(contract_no: str, file_hash: str) -> int:
    conn = get_conn()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            UPDATE customs_declaration_excel_item
            SET is_current = 0, updated_at = NOW(3)
            WHERE contract_agreement_no = %s AND is_current = 1 AND is_deleted = 0
              AND source_file_hash != %s
        """, (contract_no, file_hash))
        affected = cursor.rowcount
        conn.commit()
    finally:
        cursor.close()
        conn.close()
    return affected


def upsert_excel_item(data: dict) -> tuple[int, bool]:
    conn = get_conn()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("""
            SELECT id FROM customs_declaration_excel_item
            WHERE contract_agreement_no = %s AND product_sequence_normalized = %s
              AND is_current = 1 AND is_deleted = 0
        """, (data['contract_agreement_no'], data['product_sequence_normalized']))
        existing = cursor.fetchone()

        if existing:
            update_fields = [
                'product_sequence_no', 'export_invoice_no', 'commodity_code', 'product_name', 'sku',
                'specification_model', 'transaction_quantity', 'transaction_unit',
                'statutory_quantity', 'statutory_unit', 'unit_price', 'total_price', 'currency_code',
                'format_version', 'source_file_name', 'source_file_hash',
                'source_row_no', 'import_batch_id', 'parse_status', 'parse_message', 'updated_by',
            ]
            sets = [f'{f} = %s' for f in update_fields if f in data and data[f] is not None]
            params = [data[f] for f in update_fields if f in data and data[f] is not None]
            params.append(existing['id'])
            cursor.execute(
                f"UPDATE customs_declaration_excel_item SET {', '.join(sets)} WHERE id = %s", params)
            conn.commit()
            return existing['id'], False
        else:
            sql = """
                INSERT INTO customs_declaration_excel_item (
                    contract_agreement_no, product_sequence_no, product_sequence_normalized,
                    export_invoice_no, commodity_code, product_name, sku, specification_model,
                    transaction_quantity, transaction_unit, statutory_quantity, statutory_unit,
                    unit_price, total_price, currency_code,
                    format_version, source_file_name, source_file_hash,
                    source_row_no, import_batch_id, parse_status, parse_message, created_by
                ) VALUES (
                    %(contract_agreement_no)s, %(product_sequence_no)s, %(product_sequence_normalized)s,
                    %(export_invoice_no)s, %(commodity_code)s, %(product_name)s, %(sku)s, %(specification_model)s,
                    %(transaction_quantity)s, %(transaction_unit)s, %(statutory_quantity)s, %(statutory_unit)s,
                    %(unit_price)s, %(total_price)s, %(currency_code)s,
                    %(format_version)s, %(source_file_name)s, %(source_file_hash)s,
                    %(source_row_no)s, %(import_batch_id)s, %(parse_status)s, %(parse_message)s, %(created_by)s
                )
            """
            cursor.execute(sql, data)
            conn.commit()
            return cursor.lastrowid, True
    finally:
        cursor.close()
        conn.close()


# ── 出口明细 ──

EXPORT_WRITE_FIELDS = (
    'customs_excel_item_id', 'customs_declaration_no', 'customs_item_no',
    'declaration_date', 'export_date', 'contract_no', 'overseas_consignee',
    'export_invoice_no', 'agency_certificate_no', 'export_product_code',
    'export_product_name', 'product_specification', 'sku_original', 'sku_normalized',
    'unit', 'export_quantity', 'statutory_quantity', 'statutory_unit', 'unit_price',
    'fob_amount', 'currency_code', 'declaration_month', 'declaration_batch',
    'sequence_no', 'relation_no', 'declared_product_code', 'tax_business_type',
    'remark', 'customs_match_status', 'customs_match_message', 'source_file_name',
    'source_file_hash', 'source_page_no', 'parse_confidence', 'parse_status',
    'import_batch_id', 'created_by',
)


def upsert_export_detail(data: dict) -> tuple[int, bool]:
    # export_detail 从入库开始即保存21位编号：18位报关单号 + 3位商品项号。
    full_customs_no = customs_item_number(
        data.get('customs_declaration_no'), data.get('customs_item_no'))
    data['customs_declaration_no'] = full_customs_no
    base_customs_no = full_customs_no[:18]
    conn = get_conn()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "SELECT id FROM export_detail WHERE LEFT(customs_declaration_no, 18) = %s "
            "AND CAST(customs_item_no AS UNSIGNED) = %s AND is_deleted = 0 "
            "ORDER BY (customs_declaration_no = %s) DESC, id LIMIT 1",
            (base_customs_no, int(full_customs_no[-3:]), full_customs_no))
        existing_id = cursor.fetchone()
        existing_id = existing_id[0] if existing_id else None

        values = {field: data.get(field) for field in EXPORT_WRITE_FIELDS}
        if existing_id:
            update_fields = tuple(
                f for f in EXPORT_WRITE_FIELDS
                if f not in ('customs_item_no', 'created_by'))
            assignments = ', '.join(f'{f} = %({f})s' for f in update_fields)
            values['id'] = existing_id
            cursor.execute(
                f"UPDATE export_detail SET {assignments}, updated_by = %(created_by)s WHERE id = %(id)s",
                values)
            export_id = existing_id
            is_new = False
        else:
            columns = ', '.join(EXPORT_WRITE_FIELDS)
            placeholders = ', '.join(f'%({f})s' for f in EXPORT_WRITE_FIELDS)
            cursor.execute(
                f"INSERT INTO export_detail ({columns}) VALUES ({placeholders})", values)
            export_id = cursor.lastrowid
            is_new = True

        excel_item_id = data.get('customs_excel_item_id')
        if excel_item_id:
            cursor.execute("""
                UPDATE customs_declaration_excel_item
                SET customs_declaration_no = %s, pdf_match_status = 'MATCHED',
                    pdf_import_batch_id = %s, pdf_source_page_no = %s,
                    matched_at = NOW(3), updated_by = %s
                WHERE id = %s
            """, (data.get('customs_declaration_no'), data.get('import_batch_id'),
                  data.get('source_page_no'), data.get('created_by'), excel_item_id))
        conn.commit()
        return export_id, is_new
    except Exception:
        conn.rollback()
        raise
    finally:
        cursor.close()
        conn.close()


def get_existing_export_identities(customs_declaration_no: str) -> dict:
    base_customs_no = customs_base_number(customs_declaration_no)
    conn = get_conn()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("""
            SELECT customs_item_no, declaration_month, declaration_batch, sequence_no, relation_no
            FROM export_detail
            WHERE LEFT(customs_declaration_no, 18) = %s AND is_deleted = 0
        """, (base_customs_no,))
        rows = cursor.fetchall()
    finally:
        cursor.close()
        conn.close()
    return {str(row['customs_item_no']).lstrip('0') or '0': row for row in rows}


def get_next_sequence_start(declaration_month: str, declaration_batch: str) -> int:
    conn = get_conn()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT COALESCE(MAX(CAST(sequence_no AS UNSIGNED)), 0)
            FROM export_detail
            WHERE declaration_month = %s AND declaration_batch = %s AND is_deleted = 0
        """, (declaration_month, declaration_batch))
        return int(cursor.fetchone()[0]) + 1
    finally:
        cursor.close()
        conn.close()


def get_all_exports(page=1, per_page=50, **filters) -> tuple[list[dict], int]:
    clauses = ['is_deleted = 0']
    params: list[Any] = []
    for key in ('contract_no', 'declaration_month',
                'declaration_batch', 'relation_no', 'customs_match_status'):
        if filters.get(key):
            clauses.append(f'{key} = %s')
            params.append(filters[key])
    if filters.get('customs_declaration_no'):
        clauses.append('customs_declaration_no LIKE %s')
        params.append(filters['customs_declaration_no'].strip() + '%')

    where = ' AND '.join(clauses)
    offset = (page - 1) * per_page
    conn = get_conn()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(
            f"SELECT * FROM export_detail WHERE {where} ORDER BY id DESC LIMIT %s OFFSET %s",
            (*params, per_page, offset))
        rows = cursor.fetchall()
        cursor.execute(f"SELECT COUNT(*) AS cnt FROM export_detail WHERE {where}", params)
        total = cursor.fetchone()['cnt']
    finally:
        cursor.close()
        conn.close()
    return rows, total


def get_exports_for_excel(ids: list[int] | None = None) -> list[dict]:
    clauses = ['is_deleted = 0']
    params: list[Any] = []
    if ids is not None:
        clauses.append(f"id IN ({','.join(['%s'] * len(ids))})")
        params.extend(ids)
    conn = get_conn()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(
            f"SELECT * FROM export_detail WHERE {' AND '.join(clauses)} "
            "ORDER BY customs_declaration_no, CAST(customs_item_no AS UNSIGNED), id",
            params,
        )
        return cursor.fetchall()
    finally:
        cursor.close()
        conn.close()


# ── 进货库存 ──

def insert_purchase_inventory(data: dict) -> int:
    conn = get_conn()
    cursor = conn.cursor(dictionary=True)
    try:
        conn.start_transaction()
        cursor.execute(
            """
            SELECT id, invoice_date, supplier_tax_no, sku_normalized, unit,
                   purchased_quantity, allocated_quantity, reserved_quantity
            FROM purchase_inventory
            WHERE invoice_no=%s AND invoice_item_no=%s AND is_deleted=0
            FOR UPDATE
            """,
            (data['invoice_no'], data['invoice_item_no']),
        )
        existing = cursor.fetchone()
        if existing and (
            Decimal(str(existing.get('allocated_quantity') or 0)) > 0
            or Decimal(str(existing.get('reserved_quantity') or 0)) > 0
        ):
            immutable_fields = (
                'invoice_date', 'supplier_tax_no', 'sku_normalized', 'unit',
                'purchased_quantity',
            )
            changed = []
            for field in immutable_fields:
                old = existing.get(field)
                new = data.get(field)
                if field == 'purchased_quantity':
                    equal = Decimal(str(old or 0)) == Decimal(str(new or 0))
                else:
                    equal = str(old or '').strip() == str(new or '').strip()
                if not equal:
                    changed.append(field)
            if changed:
                raise ValueError(
                    f"发票 {data['invoice_no']} 第{data['invoice_item_no']}行已有库存扣减或预占，"
                    f"禁止覆盖关键字段: {', '.join(changed)}"
                )
            cursor.execute(
                """
                UPDATE purchase_inventory
                SET source_file_name=%s, source_file_hash=%s, source_page_no=%s,
                    parse_confidence=%s, parse_status=%s, import_batch_id=%s,
                    updated_by=%s
                WHERE id=%s
                """,
                (
                    data.get('source_file_name'), data.get('source_file_hash'),
                    data.get('source_page_no'), data.get('parse_confidence'),
                    data.get('parse_status'), data.get('import_batch_id'),
                    data.get('created_by'), existing['id'],
                ),
            )
            conn.commit()
            return int(existing['id'])

        sql = """
            INSERT INTO purchase_inventory (
                invoice_no, invoice_date, invoice_item_no,
                supplier_name, supplier_tax_no, buyer_name, buyer_tax_no,
                tax_type, product_name, product_specification,
                sku_original, sku_normalized, unit,
                purchased_quantity, allocated_quantity, reserved_quantity, remaining_quantity,
                unit_price, taxable_amount, tax_rate, refund_rate,
                tax_amount, refundable_tax_amount, inventory_status,
                declaration_month, declaration_batch, sequence_no, relation_no, remark,
                source_file_name, source_file_hash, source_page_no,
                parse_confidence, parse_status, import_batch_id, created_by
            ) VALUES (
                %(invoice_no)s, %(invoice_date)s, %(invoice_item_no)s,
                %(supplier_name)s, %(supplier_tax_no)s, %(buyer_name)s, %(buyer_tax_no)s,
                %(tax_type)s, %(product_name)s, %(product_specification)s,
                %(sku_original)s, %(sku_normalized)s, %(unit)s,
                %(purchased_quantity)s, 0, 0, %(purchased_quantity)s,
                %(unit_price)s, %(taxable_amount)s, %(tax_rate)s, %(refund_rate)s,
                %(tax_amount)s, %(refundable_tax_amount)s, 'AVAILABLE',
                %(declaration_month)s, %(declaration_batch)s, %(sequence_no)s, %(relation_no)s, %(remark)s,
                %(source_file_name)s, %(source_file_hash)s, %(source_page_no)s,
                %(parse_confidence)s, %(parse_status)s, %(import_batch_id)s, %(created_by)s
            )
            ON DUPLICATE KEY UPDATE
                invoice_date = VALUES(invoice_date),
                supplier_name = VALUES(supplier_name), supplier_tax_no = VALUES(supplier_tax_no),
                buyer_name = VALUES(buyer_name), buyer_tax_no = VALUES(buyer_tax_no),
                tax_type = VALUES(tax_type),
                product_name = VALUES(product_name), product_specification = VALUES(product_specification),
                sku_original = VALUES(sku_original), sku_normalized = VALUES(sku_normalized),
                unit = VALUES(unit), purchased_quantity = VALUES(purchased_quantity),
                remaining_quantity = VALUES(purchased_quantity) - allocated_quantity - reserved_quantity,
                inventory_status = CASE
                    WHEN allocated_quantity = 0 AND reserved_quantity = 0 THEN 'AVAILABLE'
                    ELSE inventory_status END,
                unit_price = VALUES(unit_price), taxable_amount = VALUES(taxable_amount),
                tax_rate = VALUES(tax_rate), refund_rate = VALUES(refund_rate),
                tax_amount = VALUES(tax_amount),
                refundable_tax_amount = VALUES(refundable_tax_amount),
                declaration_month = VALUES(declaration_month),
                declaration_batch = VALUES(declaration_batch),
                sequence_no = VALUES(sequence_no),
                relation_no = VALUES(relation_no), remark = VALUES(remark),
                source_file_name = VALUES(source_file_name), source_file_hash = VALUES(source_file_hash),
                source_page_no = VALUES(source_page_no), parse_confidence = VALUES(parse_confidence),
                parse_status = VALUES(parse_status), import_batch_id = VALUES(import_batch_id),
                updated_by = VALUES(created_by)
        """
        cursor.execute(sql, data)
        conn.commit()
        return int(cursor.lastrowid or (existing['id'] if existing else 0))
    except Exception:
        conn.rollback()
        raise
    finally:
        cursor.close()
        conn.close()


def get_all_inventory(page=1, per_page=50, **filters) -> tuple[list[dict], int]:
    clauses = ['is_deleted = 0']
    params: list[Any] = []
    for key, col in [
        ('invoice_no', 'invoice_no'),
        ('supplier_tax_no', 'supplier_tax_no'),
        ('buyer_tax_no', 'buyer_tax_no'),
        ('sku_normalized', 'sku_normalized'),
        ('inventory_status', 'inventory_status'),
    ]:
        if filters.get(key):
            clauses.append(f'{col} = %s')
            params.append(str(filters[key]).strip())
    if filters.get('invoice_date_from'):
        clauses.append('invoice_date >= %s')
        params.append(filters['invoice_date_from'])
    if filters.get('invoice_date_to'):
        clauses.append('invoice_date <= %s')
        params.append(filters['invoice_date_to'])

    where = ' AND '.join(clauses)
    offset = (page - 1) * per_page
    conn = get_conn()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(
            f"SELECT * FROM purchase_inventory WHERE {where} ORDER BY invoice_date DESC, id DESC "
            "LIMIT %s OFFSET %s",
            params + [per_page, offset])
        rows = cursor.fetchall()
        cursor.execute(f"SELECT COUNT(*) as cnt FROM purchase_inventory WHERE {where}", params)
        total = cursor.fetchone()['cnt']
    finally:
        cursor.close()
        conn.close()
    return rows, total


def get_inventory_for_excel(ids: list[int] | None = None) -> list[dict]:
    clauses = ['is_deleted = 0']
    params: list[Any] = []
    if ids is not None:
        clauses.append(f"id IN ({','.join(['%s'] * len(ids))})")
        params.extend(ids)
    conn = get_conn()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(
            f"SELECT * FROM purchase_inventory WHERE {' AND '.join(clauses)} "
            "ORDER BY invoice_date, invoice_no, invoice_item_no, id",
            params,
        )
        return cursor.fetchall()
    finally:
        cursor.close()
        conn.close()


# ── 外汇 ──

def list_receivables(page=1, per_page=50, **filters) -> tuple[list[dict], int]:
    where = ['r.is_deleted = 0']
    params: list[Any] = []
    if filters.get('customs_no'):
        where.append('r.customs_no_match_key = %s')
        params.append(filters['customs_no'][:18])
    if filters.get('contract_no'):
        where.append('r.contract_no = %s')
        params.append(filters['contract_no'])
    if filters.get('business_entity'):
        where.append('r.business_entity = %s')
        params.append(filters['business_entity'])
    if filters.get('source_type'):
        where.append('r.source_type = %s')
        params.append(filters['source_type'])
    if filters.get('export_date_from'):
        where.append('r.export_date >= %s')
        params.append(filters['export_date_from'])
    if filters.get('export_date_to'):
        where.append('r.export_date <= %s')
        params.append(filters['export_date_to'])

    where_clause = ' AND '.join(where)
    offset = (page - 1) * per_page
    conn = get_conn()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(
            f"SELECT r.*, COALESCE(SUM(a.allocated_amount_usd), 0) AS received_amount_usd, "
            f"rec.core_transaction_no, rec.receipt_date, rec.receipt_total_usd, rec.actual_exchange_rate, "
            f"rec.settlement_receipt_rmb, rec.difference_usd "
            f"FROM forex_export_receivable r "
            f"LEFT JOIN forex_receipt_allocation a ON a.receivable_id = r.id "
            f"LEFT JOIN forex_receipt rec ON rec.id = a.receipt_id AND rec.is_deleted = 0 "
            f"WHERE {where_clause} GROUP BY r.id, rec.id "
            f"ORDER BY r.id DESC LIMIT %s OFFSET %s",
            params + [per_page, offset])
        rows = cursor.fetchall()
        cursor.execute(f"SELECT COUNT(*) as cnt FROM forex_export_receivable r WHERE {where_clause}", params)
        total = cursor.fetchone()['cnt']
    finally:
        cursor.close()
        conn.close()
    return rows, total


def get_receivables_for_excel(ids: list[int] | None = None) -> list[dict]:
    clauses = ['r.is_deleted = 0']
    params: list[Any] = []
    if ids is not None:
        clauses.append(f"r.id IN ({','.join(['%s'] * len(ids))})")
        params.extend(ids)
    conn = get_conn()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(
            f"SELECT r.*, COALESCE(SUM(a.allocated_amount_usd), 0) AS received_amount_usd, "
            f"rec.core_transaction_no, rec.receipt_date, rec.receipt_total_usd, "
            f"rec.actual_exchange_rate, rec.settlement_receipt_rmb, rec.difference_usd "
            f"FROM forex_export_receivable r "
            f"LEFT JOIN forex_receipt_allocation a ON a.receivable_id = r.id "
            f"LEFT JOIN forex_receipt rec ON rec.id = a.receipt_id AND rec.is_deleted = 0 "
            f"WHERE {' AND '.join(clauses)} GROUP BY r.id, rec.id "
            "ORDER BY r.export_date, r.id, rec.receipt_date, rec.id",
            params,
        )
        return cursor.fetchall()
    finally:
        cursor.close()
        conn.close()
