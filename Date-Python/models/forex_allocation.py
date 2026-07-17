"""回款与报关单分配关系 (forex_receipt_allocation)"""
from models.base import get_conn


def upsert_allocation(data):
    """按 (receipt_id, receivable_id) 插入或更新"""
    conn = get_conn()
    cursor = conn.cursor(dictionary=True)
    cursor.execute(
        'SELECT id FROM forex_receipt_allocation WHERE receipt_id = %s AND receivable_id = %s',
        (data['receipt_id'], data['receivable_id']))
    existing = cursor.fetchone()
    if existing:
        cursor.execute(
            'UPDATE forex_receipt_allocation SET allocated_amount_usd = %s, '
            'source_sheet_name = %s, source_row_no = %s, import_batch_id = %s WHERE id = %s',
            (data['allocated_amount_usd'], data.get('source_sheet_name'),
             data.get('source_row_no'), data.get('import_batch_id'), existing['id']))
        conn.commit()
        aid = existing['id']
        is_new = False
    else:
        sql = '''INSERT INTO forex_receipt_allocation (
            receipt_id, receivable_id, allocated_amount_usd,
            source_sheet_name, source_row_no, import_batch_id
        ) VALUES (
            %(receipt_id)s, %(receivable_id)s, %(allocated_amount_usd)s,
            %(source_sheet_name)s, %(source_row_no)s, %(import_batch_id)s
        )'''
        cursor.execute(sql, data)
        conn.commit()
        aid = cursor.lastrowid
        is_new = True
    cursor.close(); conn.close()
    return aid, is_new


def get_allocations_by_receipt(receipt_id):
    conn = get_conn()
    cursor = conn.cursor(dictionary=True)
    cursor.execute(
        'SELECT a.*, r.customs_declaration_no, r.customs_no_match_key '
        'FROM forex_receipt_allocation a '
        'JOIN forex_export_receivable r ON r.id = a.receivable_id '
        'WHERE a.receipt_id = %s', (receipt_id,))
    rows = cursor.fetchall()
    cursor.close(); conn.close()
    return rows


def count_allocations():
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute('SELECT COUNT(*) FROM forex_receipt_allocation')
    cnt = cursor.fetchone()[0]
    cursor.close(); conn.close()
    return cnt
