"""报关单应收记录 (forex_export_receivable)"""
from models.base import get_conn


def upsert_receivable(data):
    """按 customs_no_match_key 插入或更新"""
    conn = get_conn()
    cursor = conn.cursor(dictionary=True)
    cursor.execute(
        'SELECT id FROM forex_export_receivable WHERE customs_no_match_key = %s',
        (data['customs_no_match_key'],))
    existing = cursor.fetchone()
    if existing:
        sets = []
        params = []
        fields = ['customs_declaration_no', 'contract_no', 'business_entity',
                  'export_date', 'customs_port', 'customs_contract_usd',
                  'export_amount_usd', 'monthly_exchange_rate', 'monthly_exchange_rate_raw',
                  'source_type', 'source_file_name', 'source_sheet_name',
                  'source_row_no', 'import_batch_id']
        for f in fields:
            if f in data:
                sets.append(f'{f} = %s')
                params.append(data[f])
        params.append(existing['id'])
        cursor.execute(
            f'UPDATE forex_export_receivable SET {", ".join(sets)} WHERE id = %s', params)
        conn.commit()
        rid = existing['id']
        is_new = False
    else:
        sql = '''INSERT INTO forex_export_receivable (
            customs_no_match_key, customs_declaration_no, contract_no, business_entity,
            export_date, customs_port, customs_contract_usd, export_amount_usd,
            monthly_exchange_rate, monthly_exchange_rate_raw,
            source_type, source_file_name, source_sheet_name, source_row_no, import_batch_id
        ) VALUES (
            %(customs_no_match_key)s, %(customs_declaration_no)s, %(contract_no)s, %(business_entity)s,
            %(export_date)s, %(customs_port)s, %(customs_contract_usd)s, %(export_amount_usd)s,
            %(monthly_exchange_rate)s, %(monthly_exchange_rate_raw)s,
            %(source_type)s, %(source_file_name)s, %(source_sheet_name)s, %(source_row_no)s, %(import_batch_id)s
        )'''
        cursor.execute(sql, data)
        conn.commit()
        rid = cursor.lastrowid
        is_new = True
    cursor.close(); conn.close()
    return rid, is_new


def get_receivable_by_customs(match_key):
    conn = get_conn()
    cursor = conn.cursor(dictionary=True)
    cursor.execute(
        'SELECT * FROM forex_export_receivable WHERE customs_no_match_key = %s AND is_deleted = 0',
        (match_key,))
    row = cursor.fetchone()
    cursor.close(); conn.close()
    return row


def list_receivables(page=1, per_page=50, customs_no=None, contract_no=None,
                     business_entity=None, source_type=None, export_date_from=None,
                     export_date_to=None):
    conn = get_conn()
    cursor = conn.cursor(dictionary=True)
    where = ['r.is_deleted = 0']
    params = []
    if customs_no:
        where.append('r.customs_no_match_key = %s')
        params.append(customs_no[:18])
    if contract_no:
        where.append('r.contract_no = %s')
        params.append(contract_no)
    if business_entity:
        where.append('r.business_entity = %s')
        params.append(business_entity)
    if source_type:
        where.append('r.source_type = %s')
        params.append(source_type)
    if export_date_from:
        where.append('r.export_date >= %s')
        params.append(export_date_from)
    if export_date_to:
        where.append('r.export_date <= %s')
        params.append(export_date_to)
    where_clause = ' AND '.join(where)
    offset = (page - 1) * per_page
    cursor.execute(
        f'SELECT r.*, COALESCE(SUM(a.allocated_amount_usd), 0) AS received_amount_usd '
        f'FROM forex_export_receivable r '
        f'LEFT JOIN forex_receipt_allocation a ON a.receivable_id = r.id '
        f'WHERE {where_clause} GROUP BY r.id '
        f'ORDER BY r.export_date DESC, r.id DESC LIMIT %s OFFSET %s',
        params + [per_page, offset])
    rows = cursor.fetchall()
    cursor.execute(
        f'SELECT COUNT(*) as cnt FROM forex_export_receivable r WHERE {where_clause}', params)
    total = cursor.fetchone()['cnt']
    cursor.close(); conn.close()
    return rows, total
