"""报关资料Excel商品表 (customs_declaration_excel_item)"""
from models.base import get_conn


def upsert_excel_item(data):
    # Keep direct/model-level callers compatible with records created before
    # the invoice-number parser was added.
    data = {**data, 'export_invoice_no': data.get('export_invoice_no')}
    """
    按 (合同协议号 + 标准化项号) 增量更新：存在则覆盖，不存在则新增。
    返回 (id, is_new)
    """
    conn = get_conn()
    cursor = conn.cursor(dictionary=True)

    # 查是否存在当前有效记录
    cursor.execute('''
        SELECT id FROM customs_declaration_excel_item
        WHERE contract_agreement_no = %s AND product_sequence_normalized = %s
          AND is_current = 1 AND is_deleted = 0
    ''', (data['contract_agreement_no'], data['product_sequence_normalized']))
    existing = cursor.fetchone()

    if existing:
        # 覆盖更新
        sets = []
        params = []
        update_fields = [
            'product_sequence_no', 'export_invoice_no', 'commodity_code', 'product_name', 'sku',
            'specification_model',
            'transaction_quantity', 'transaction_unit', 'statutory_quantity', 'statutory_unit',
            'unit_price', 'total_price', 'currency_code',
            'format_version', 'source_file_name', 'source_file_hash',
            'source_row_no', 'import_batch_id', 'parse_status', 'parse_message', 'updated_by'
        ]
        for f in update_fields:
            if f in data and data[f] is not None:
                sets.append(f'{f} = %s')
                params.append(data[f])
        params.append(existing['id'])
        cursor.execute(f'UPDATE customs_declaration_excel_item SET {", ".join(sets)} WHERE id = %s', params)
        conn.commit()
        cursor.close(); conn.close()
        return existing['id'], False
    else:
        # 新增
        sql = '''
            INSERT INTO customs_declaration_excel_item (
                contract_agreement_no, product_sequence_no, product_sequence_normalized, export_invoice_no,
                commodity_code, product_name, sku, specification_model,
                transaction_quantity, transaction_unit,
                statutory_quantity, statutory_unit,
                unit_price, total_price, currency_code,
                format_version, source_file_name, source_file_hash,
                source_row_no, import_batch_id,
                parse_status, parse_message, created_by
            ) VALUES (
                %(contract_agreement_no)s, %(product_sequence_no)s, %(product_sequence_normalized)s, %(export_invoice_no)s,
                %(commodity_code)s, %(product_name)s, %(sku)s, %(specification_model)s,
                %(transaction_quantity)s, %(transaction_unit)s,
                %(statutory_quantity)s, %(statutory_unit)s,
                %(unit_price)s, %(total_price)s, %(currency_code)s,
                %(format_version)s, %(source_file_name)s, %(source_file_hash)s,
                %(source_row_no)s, %(import_batch_id)s,
                %(parse_status)s, %(parse_message)s, %(created_by)s
            )
        '''
        cursor.execute(sql, data)
        conn.commit()
        last_id = cursor.lastrowid
        cursor.close(); conn.close()
        return last_id, True


# 保留旧函数名兼容
insert_excel_item = upsert_excel_item


def set_excel_items_old_version(contract_no, file_hash):
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute('''
        UPDATE customs_declaration_excel_item
        SET is_current = 0, updated_at = NOW(3)
        WHERE contract_agreement_no = %s AND is_current = 1 AND is_deleted = 0
          AND source_file_hash != %s
    ''', (contract_no, file_hash))
    affected = cursor.rowcount
    conn.commit()
    cursor.close(); conn.close()
    return affected


def get_excel_items_by_contract(contract_no, current_only=True):
    conn = get_conn()
    cursor = conn.cursor(dictionary=True)
    if current_only:
        cursor.execute('''
            SELECT * FROM customs_declaration_excel_item
            WHERE contract_agreement_no = %s AND is_current = 1 AND is_deleted = 0
            ORDER BY CAST(product_sequence_normalized AS UNSIGNED), product_sequence_normalized
        ''', (contract_no,))
    else:
        cursor.execute('''
            SELECT * FROM customs_declaration_excel_item
            WHERE contract_agreement_no = %s AND is_deleted = 0
            ORDER BY is_current DESC, CAST(product_sequence_normalized AS UNSIGNED)
        ''', (contract_no,))
    rows = cursor.fetchall()
    cursor.close(); conn.close()
    return rows


def get_all_excel_items(page=1, per_page=50):
    conn = get_conn()
    cursor = conn.cursor(dictionary=True)
    offset = (page - 1) * per_page
    cursor.execute('''
        SELECT * FROM customs_declaration_excel_item
        WHERE is_deleted = 0
        ORDER BY id DESC LIMIT %s OFFSET %s
    ''', (per_page, offset))
    rows = cursor.fetchall()
    cursor.execute('SELECT COUNT(*) as cnt FROM customs_declaration_excel_item WHERE is_deleted = 0')
    total = cursor.fetchone()['cnt']
    cursor.close(); conn.close()
    return rows, total


def check_excel_item_exists(contract_no, seq_normalized):
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT id FROM customs_declaration_excel_item
        WHERE contract_agreement_no = %s AND product_sequence_normalized = %s
          AND is_current = 1 AND is_deleted = 0
    ''', (contract_no, seq_normalized))
    row = cursor.fetchone()
    cursor.close(); conn.close()
    return row is not None


def get_current_excel_items_map(contract_no):
    """取得一个合同当前有效的报关资料商品，以标准化项号为键。"""
    conn = get_conn()
    cursor = conn.cursor(dictionary=True)
    cursor.execute('''
        SELECT * FROM customs_declaration_excel_item
        WHERE contract_agreement_no = %s AND is_current = 1 AND is_deleted = 0
        ORDER BY CAST(product_sequence_normalized AS UNSIGNED), id
    ''', (contract_no,))
    rows = cursor.fetchall()
    cursor.close(); conn.close()
    result = {}
    duplicates = set()
    for row in rows:
        key = str(row['product_sequence_normalized']).lstrip('0') or '0'
        if key in result:
            duplicates.add(key)
        result[key] = row
    return result, sorted(
        duplicates,
        key=lambda value: (0, int(value)) if value.isdigit() else (1, value),
    )
