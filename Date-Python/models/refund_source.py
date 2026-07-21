"""退税汇总生成所需的数据库只读查询。"""

from models.base import get_conn


def get_refund_purchases():
    conn = get_conn()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("""
            SELECT id, invoice_no, invoice_date, invoice_item_no,
                   supplier_name, supplier_tax_no, tax_type,
                   product_name, sku_normalized, unit,
                   purchased_quantity, remaining_quantity,
                   taxable_amount, tax_amount, tax_rate, refund_rate,
                   refundable_tax_amount,
                   declaration_month, declaration_batch, sequence_no, relation_no,
                   remark
            FROM purchase_inventory
            WHERE is_deleted = 0
              AND inventory_status NOT IN ('LOCKED', 'CANCELLED')
              AND remaining_quantity > 0
            ORDER BY invoice_date, invoice_no, invoice_item_no, id
        """)
        return cursor.fetchall()
    finally:
        cursor.close()
        conn.close()


def get_refund_exports():
    conn = get_conn()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("""
            SELECT id, customs_declaration_no, customs_item_no,
                   declaration_date, export_date, contract_no,
                   export_invoice_no, agency_certificate_no,
                   export_product_code, export_product_name,
                   sku_normalized, unit, export_quantity, fob_amount,
                   currency_code, declaration_month, declaration_batch,
                   sequence_no, relation_no, declared_product_code,
                   tax_business_type, remark
            FROM export_detail
            WHERE is_deleted = 0 AND customs_match_status = 'MATCHED'
              AND inventory_allocation_status IN ('UNALLOCATED','REVERSED')
            ORDER BY customs_declaration_no,
                     CAST(customs_item_no AS UNSIGNED), id
        """)
        return cursor.fetchall()
    finally:
        cursor.close()
        conn.close()


def get_refund_forex_rows():
    conn = get_conn()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("""
            SELECT fr.customs_no_match_key, fr.customs_declaration_no,
                   fr.contract_no, fr.monthly_exchange_rate,
                   r.core_transaction_no, r.receipt_date,
                   r.settlement_receipt_rmb, r.receipt_total_usd,
                   r.actual_exchange_rate,
                   a.allocated_amount_usd
            FROM forex_export_receivable fr
            LEFT JOIN forex_receipt_allocation a ON a.receivable_id = fr.id
            LEFT JOIN forex_receipt r
              ON r.id = a.receipt_id AND r.is_deleted = 0
            WHERE fr.is_deleted = 0
            ORDER BY fr.id, r.receipt_date, r.id
        """)
        return cursor.fetchall()
    finally:
        cursor.close()
        conn.close()
