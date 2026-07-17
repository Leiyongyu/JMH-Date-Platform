"""出口明细表 (export_detail) 数据访问。"""
from models.base import get_conn


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


def _existing_id(cursor, data):
    cursor.execute(
        'SELECT id FROM export_detail WHERE customs_declaration_no = %s '
        'AND customs_item_no = %s AND is_deleted = 0',
        (data['customs_declaration_no'], data['customs_item_no']))
    row = cursor.fetchone()
    return row[0] if row else None


def insert_export_detail(data, skip_existing=True):
    """兼容旧调用；新匹配流程应使用 upsert_export_detail。"""
    conn = get_conn()
    cursor = conn.cursor()
    existing_id = _existing_id(cursor, data)
    if existing_id and skip_existing:
        cursor.close(); conn.close()
        return existing_id, False
    cursor.close(); conn.close()
    return upsert_export_detail(data)


def upsert_export_detail(data):
    """按海关编号+商品项号新增或覆盖，并回写报关资料匹配状态。"""
    conn = get_conn()
    cursor = conn.cursor()
    try:
        existing_id = _existing_id(cursor, data)
        values = {field: data.get(field) for field in EXPORT_WRITE_FIELDS}
        if existing_id:
            update_fields = tuple(field for field in EXPORT_WRITE_FIELDS
                                  if field not in ('customs_declaration_no', 'customs_item_no', 'created_by'))
            assignments = ', '.join(f'{field} = %({field})s' for field in update_fields)
            values['id'] = existing_id
            cursor.execute(
                f'UPDATE export_detail SET {assignments}, updated_by = %(created_by)s WHERE id = %(id)s',
                values)
            export_id = existing_id
            is_new = False
        else:
            columns = ', '.join(EXPORT_WRITE_FIELDS)
            placeholders = ', '.join(f'%({field})s' for field in EXPORT_WRITE_FIELDS)
            cursor.execute(
                f'INSERT INTO export_detail ({columns}) VALUES ({placeholders})', values)
            export_id = cursor.lastrowid
            is_new = True

        excel_item_id = data.get('customs_excel_item_id')
        if excel_item_id:
            cursor.execute('''
                UPDATE customs_declaration_excel_item
                SET customs_declaration_no = %s,
                    pdf_match_status = 'MATCHED',
                    pdf_import_batch_id = %s,
                    pdf_source_page_no = %s,
                    matched_at = NOW(3),
                    updated_by = %s
                WHERE id = %s
            ''', (
                data.get('customs_declaration_no'), data.get('import_batch_id'),
                data.get('source_page_no'), data.get('created_by'), excel_item_id,
            ))
        conn.commit()
        return export_id, is_new
    except Exception:
        conn.rollback()
        raise
    finally:
        cursor.close(); conn.close()


def get_next_sequence_start(declaration_month, declaration_batch):
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT COALESCE(MAX(CAST(sequence_no AS UNSIGNED)), 0)
        FROM export_detail
        WHERE declaration_month = %s AND declaration_batch = %s AND is_deleted = 0
    ''', (declaration_month, declaration_batch))
    value = int(cursor.fetchone()[0]) + 1
    cursor.close(); conn.close()
    return value


def get_existing_export_identities(customs_declaration_no):
    """按项号取得同一报关单已入库的申报身份，供重复上传时稳定复用。"""
    conn = get_conn()
    cursor = conn.cursor(dictionary=True)
    cursor.execute('''
        SELECT customs_item_no, declaration_month, declaration_batch, sequence_no, relation_no
        FROM export_detail
        WHERE customs_declaration_no = %s AND is_deleted = 0
    ''', (customs_declaration_no,))
    rows = cursor.fetchall()
    cursor.close(); conn.close()
    return {
        str(row['customs_item_no']).lstrip('0') or '0': row
        for row in rows
    }


def get_export_by_batch(batch_id):
    conn = get_conn()
    cursor = conn.cursor(dictionary=True)
    cursor.execute(
        'SELECT * FROM export_detail WHERE import_batch_id = %s AND is_deleted = 0 ORDER BY id',
        (batch_id,))
    rows = cursor.fetchall()
    cursor.close(); conn.close()
    return rows


def _export_filters(contract_no=None, customs_declaration_no=None, declaration_month=None,
                    declaration_batch=None, relation_no=None, customs_match_status=None):
    clauses = ['is_deleted = 0']
    params = []
    if contract_no:
        clauses.append('contract_no = %s')
        params.append(contract_no)
    if customs_declaration_no:
        clauses.append('customs_declaration_no LIKE %s')
        params.append(customs_declaration_no.strip() + '%')
    if declaration_month:
        clauses.append('declaration_month = %s')
        params.append(declaration_month)
    if declaration_batch:
        clauses.append('declaration_batch = %s')
        params.append(declaration_batch)
    if relation_no:
        clauses.append('relation_no = %s')
        params.append(relation_no)
    if customs_match_status:
        clauses.append('customs_match_status = %s')
        params.append(customs_match_status)
    return ' AND '.join(clauses), params


def get_all_exports(page=1, per_page=50, contract_no=None, declaration_month=None,
                    declaration_batch=None, customs_match_status=None):
    conn = get_conn()
    cursor = conn.cursor(dictionary=True)
    where, params = _export_filters(
        contract_no, declaration_month, declaration_batch, customs_match_status)
    offset = (page - 1) * per_page
    cursor.execute(
        f'SELECT * FROM export_detail WHERE {where} ORDER BY id DESC LIMIT %s OFFSET %s',
        (*params, per_page, offset))
    rows = cursor.fetchall()
    cursor.execute(f'SELECT COUNT(*) AS cnt FROM export_detail WHERE {where}', params)
    total = cursor.fetchone()['cnt']
    cursor.close(); conn.close()
    return rows, total


def get_exports_for_report(contract_no=None, declaration_month=None, declaration_batch=None):
    conn = get_conn()
    cursor = conn.cursor(dictionary=True)
    where, params = _export_filters(contract_no, declaration_month, declaration_batch, 'MATCHED')
    cursor.execute(f'''
        SELECT * FROM export_detail
        WHERE {where}
        ORDER BY declaration_month, declaration_batch,
                 CAST(sequence_no AS UNSIGNED), customs_declaration_no,
                 CAST(customs_item_no AS UNSIGNED)
    ''', params)
    rows = cursor.fetchall()
    cursor.close(); conn.close()
    return rows


def check_customs_exists(customs_no, item_no):
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute(
        'SELECT id FROM export_detail WHERE customs_declaration_no = %s '
        'AND customs_item_no = %s AND is_deleted = 0',
        (customs_no, item_no))
    row = cursor.fetchone()
    cursor.close(); conn.close()
    return row is not None
