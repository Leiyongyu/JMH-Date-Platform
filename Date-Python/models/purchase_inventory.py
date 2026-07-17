"""进货库存表 (purchase_inventory)"""
from models.base import get_conn


def insert_purchase_inventory(data):
    conn = get_conn()
    cursor = conn.cursor()
    sql = '''
        INSERT INTO purchase_inventory (
            invoice_no, invoice_date, invoice_item_no,
            supplier_name, supplier_tax_no, buyer_name, buyer_tax_no,
            tax_type, product_name, product_specification,
            sku_original, sku_normalized, unit,
            purchased_quantity, allocated_quantity, remaining_quantity,
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
            %(purchased_quantity)s, 0, %(purchased_quantity)s,
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
            remaining_quantity = VALUES(purchased_quantity) - allocated_quantity,
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
    '''
    cursor.execute(sql, data)
    conn.commit()
    last_id = cursor.lastrowid
    cursor.close(); conn.close()
    return last_id


def get_inventory_by_batch(batch_id):
    conn = get_conn()
    cursor = conn.cursor(dictionary=True)
    cursor.execute(
        'SELECT * FROM purchase_inventory WHERE import_batch_id = %s AND is_deleted = 0 ORDER BY id', (batch_id,))
    rows = cursor.fetchall()
    cursor.close(); conn.close()
    return rows


def get_all_inventory(page=1, per_page=50, invoice_no=None, invoice_date_from=None,
                      invoice_date_to=None, supplier_tax_no=None, buyer_tax_no=None,
                      sku_normalized=None, inventory_status=None):
    conn = get_conn()
    cursor = conn.cursor(dictionary=True)
    clauses = ['is_deleted = 0']
    params = []
    if invoice_no:
        clauses.append('invoice_no = %s')
        params.append(invoice_no.strip())
    if invoice_date_from:
        clauses.append('invoice_date >= %s')
        params.append(invoice_date_from)
    if invoice_date_to:
        clauses.append('invoice_date <= %s')
        params.append(invoice_date_to)
    if supplier_tax_no:
        clauses.append('supplier_tax_no = %s')
        params.append(supplier_tax_no.strip())
    if buyer_tax_no:
        clauses.append('buyer_tax_no = %s')
        params.append(buyer_tax_no.strip())
    if sku_normalized:
        clauses.append('sku_normalized = %s')
        params.append(sku_normalized.strip())
    if inventory_status:
        clauses.append('inventory_status = %s')
        params.append(inventory_status.strip())

    where = ' AND '.join(clauses)
    offset = (page - 1) * per_page
    cursor.execute(
        f'SELECT * FROM purchase_inventory WHERE {where} ORDER BY invoice_date DESC, id DESC LIMIT %s OFFSET %s',
        params + [per_page, offset])
    rows = cursor.fetchall()
    cursor.execute(f'SELECT COUNT(*) as cnt FROM purchase_inventory WHERE {where}', params)
    total = cursor.fetchone()['cnt']
    cursor.close(); conn.close()
    return rows, total


def get_inventory_for_report(invoice_no=None, supplier_tax_no=None):
    conn = get_conn()
    cursor = conn.cursor(dictionary=True)
    clauses = ['is_deleted = 0']
    params = []
    if invoice_no:
        clauses.append('invoice_no = %s')
        params.append(invoice_no)
    if supplier_tax_no:
        clauses.append('supplier_tax_no = %s')
        params.append(supplier_tax_no)
    cursor.execute(f'''
        SELECT * FROM purchase_inventory
        WHERE {' AND '.join(clauses)}
        ORDER BY invoice_date, invoice_no, invoice_item_no
    ''', params)
    rows = cursor.fetchall()
    cursor.close(); conn.close()
    return rows
