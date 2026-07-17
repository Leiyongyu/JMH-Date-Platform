"""银行回款主记录 (forex_receipt)"""
from models.base import get_conn


def upsert_receipt(data):
    """按 receipt_business_key 插入或更新"""
    conn = get_conn()
    cursor = conn.cursor(dictionary=True)
    cursor.execute(
        'SELECT id FROM forex_receipt WHERE receipt_business_key = %s',
        (data['receipt_business_key'],))
    existing = cursor.fetchone()
    if existing:
        sets = []
        params = []
        fields = ['core_transaction_no', 'receipt_total_usd',
                  'actual_exchange_rate', 'actual_exchange_rate_raw',
                  'settlement_receipt_rmb', 'receipt_date', 'difference_usd',
                  'business_entity', 'source_sheet_name', 'import_batch_id']
        for f in fields:
            if f in data:
                sets.append(f'{f} = %s')
                params.append(data[f])
        params.append(existing['id'])
        cursor.execute(f'UPDATE forex_receipt SET {", ".join(sets)} WHERE id = %s', params)
        conn.commit()
        rid = existing['id']
        is_new = False
    else:
        sql = '''INSERT INTO forex_receipt (
            receipt_business_key, core_transaction_no,
            receipt_total_usd, actual_exchange_rate, actual_exchange_rate_raw,
            settlement_receipt_rmb, receipt_date, difference_usd,
            business_entity, source_sheet_name, import_batch_id
        ) VALUES (
            %(receipt_business_key)s, %(core_transaction_no)s,
            %(receipt_total_usd)s, %(actual_exchange_rate)s, %(actual_exchange_rate_raw)s,
            %(settlement_receipt_rmb)s, %(receipt_date)s, %(difference_usd)s,
            %(business_entity)s, %(source_sheet_name)s, %(import_batch_id)s
        )'''
        cursor.execute(sql, data)
        conn.commit()
        rid = cursor.lastrowid
        is_new = True
    cursor.close(); conn.close()
    return rid, is_new


def get_receipts_by_business_key(business_key):
    conn = get_conn()
    cursor = conn.cursor(dictionary=True)
    cursor.execute(
        'SELECT * FROM forex_receipt WHERE receipt_business_key = %s AND is_deleted = 0',
        (business_key,))
    row = cursor.fetchone()
    cursor.close(); conn.close()
    return row


def count_receipts(core_tx_no=None):
    conn = get_conn()
    cursor = conn.cursor()
    if core_tx_no:
        cursor.execute(
            'SELECT COUNT(*) FROM forex_receipt WHERE core_transaction_no = %s AND is_deleted = 0',
            (core_tx_no,))
    else:
        cursor.execute('SELECT COUNT(*) FROM forex_receipt WHERE is_deleted = 0')
    cnt = cursor.fetchone()[0]
    cursor.close(); conn.close()
    return cnt
