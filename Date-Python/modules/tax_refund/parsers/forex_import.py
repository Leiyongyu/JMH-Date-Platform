"""Sheet1 外汇回款导入：解析、预览和单事务入库。"""
from collections import defaultdict

from infrastructure.database import get_conn
from modules.tax_refund.parsers.forex_normalizer import (
    _to_decimal,
    is_abnormal_date,
    make_receipt_business_key,
    normalize_date,
    normalize_exchange_rate,
)
from modules.tax_refund.parsers.forex_excel import parse_forex_workbook


def _first_value(records, field):
    for record in records:
        value = record.get(field)
        if value not in (None, ''):
            return value
    return None


def _existing_values(table, column, values):
    values = list(dict.fromkeys(value for value in values if value))
    if not values:
        return set()
    conn = get_conn()
    cursor = conn.cursor()
    try:
        placeholders = ','.join(['%s'] * len(values))
        cursor.execute(
            f'SELECT {column} FROM {table} WHERE {column} IN ({placeholders})',
            values,
        )
        return {row[0] for row in cursor.fetchall()}
    finally:
        cursor.close()
        conn.close()


def _build_receipt_groups(records):
    grouped = defaultdict(list)
    for record in records:
        if not record.get('skip_import') and record.get('receipt_group_key'):
            grouped[record['receipt_group_key']].append(record)

    result = []
    for group_key, group_records in grouped.items():
        core_tx = _first_value(group_records, 'core_transaction_no')
        receipt_date = _first_value(group_records, 'receipt_date_normalized')
        receipt_total = _first_value(group_records, 'receipt_total_amount_usd')
        settlement_rmb = _first_value(group_records, 'settlement_rmb')
        difference_usd = _first_value(group_records, 'difference_usd')
        business_entity = _first_value(group_records, 'business_entity')
        business_key = make_receipt_business_key(
            core_tx, business_entity, receipt_date, receipt_total,
            settlement_rmb,
        )
        result.append({
            'group_key': group_key,
            'receipt_business_key': business_key,
            'core_transaction_no': core_tx,
            'receipt_total_usd': receipt_total,
            'actual_exchange_rate': _first_value(group_records, 'actual_exchange_rate'),
            'actual_exchange_rate_raw': _first_value(group_records, 'actual_exchange_rate_raw'),
            'settlement_receipt_rmb': settlement_rmb,
            'receipt_date': receipt_date,
            'difference_usd': difference_usd,
            'business_entity': business_entity,
            'source_sheet_name': 'Sheet1',
            'customs_count': len(group_records),
        })
    return result


def preview_forex_import(file_path, file_hash):
    """只解析 Sheet1 并生成可确认的预览数据。"""
    _, sheet_results = parse_forex_workbook(file_path, file_hash)
    sheet_result = sheet_results[0]
    records = sheet_result['rows']
    errors = list(sheet_result.get('errors', []))

    for row in records:
        row['export_date_normalized'] = normalize_date(row.get('export_date'))
        row['receipt_date_normalized'] = normalize_date(row.get('receipt_date'))
        row['monthly_exchange_rate'] = normalize_exchange_rate(row.get('monthly_exchange_rate_raw'))
        row['actual_exchange_rate'] = normalize_exchange_rate(row.get('actual_exchange_rate_raw'))
        row['customs_contract_usd'] = _to_decimal(row.get('customs_contract_usd'))
        row['export_amount_usd'] = _to_decimal(row.get('export_amount_usd'))
        row['allocation_amount_usd'] = _to_decimal(row.get('allocation_amount_usd'))
        row['amount_usd'] = row['allocation_amount_usd']  # 兼容原预览字段
        row['receipt_total_amount_usd'] = _to_decimal(row.get('receipt_total_usd'))
        row['received_amount_usd'] = row['receipt_total_amount_usd']
        row['settlement_rmb'] = _to_decimal(row.get('settlement_receipt_rmb'))
        row['difference_usd'] = _to_decimal(row.get('difference_usd'))

        if is_abnormal_date(row.get('export_date')):
            errors.append({
                'sheet': 'Sheet1', 'row': row['source_row_no'],
                'message': f'异常出口日期: {row["export_date"]}',
            })
        if is_abnormal_date(row.get('receipt_date')):
            errors.append({
                'sheet': 'Sheet1', 'row': row['source_row_no'],
                'message': f'异常收汇日期: {row["receipt_date"]}',
            })
        if row.get('receipt_group_key') and row.get('allocation_amount_usd') is None:
            errors.append({
                'sheet': 'Sheet1', 'row': row['source_row_no'],
                'message': '回款分配金额为空，本行只保存应收记录，不生成回款分配',
            })

    receipt_groups = _build_receipt_groups(records)
    valid_records = [row for row in records if not row.get('skip_import')]
    existing_receivables = _existing_values(
        'forex_export_receivable', 'customs_no_match_key',
        [row['customs_no_match_key'] for row in valid_records],
    )
    existing_receipts = _existing_values(
        'forex_receipt', 'receipt_business_key',
        [group['receipt_business_key'] for group in receipt_groups],
    )

    unique_receivable_keys = {row['customs_no_match_key'] for row in valid_records}
    unique_receipt_keys = {group['receipt_business_key'] for group in receipt_groups}
    allocation_count = sum(
        1 for row in valid_records
        if row.get('receipt_group_key') and row.get('allocation_amount_usd') is not None
    )
    stats = {
        'new_count': len(unique_receivable_keys - existing_receivables),
        'update_count': len(unique_receivable_keys & existing_receivables),
        'receipt_count': len(unique_receipt_keys),
        'new_receipt_count': len(unique_receipt_keys - existing_receipts),
        'update_receipt_count': len(unique_receipt_keys & existing_receipts),
        'receipt_new': len(unique_receipt_keys - existing_receipts),
        'receipt_upd': len(unique_receipt_keys & existing_receipts),
        'allocation_count': allocation_count,
        'error_count': len(errors),
    }

    return {
        'records': records,
        'receipt_groups': receipt_groups,
        'sheets': {
            'Sheet1': {
                'rows': len(records),
                'merged_areas': len({group['group_key'] for group in receipt_groups}),
            },
        },
        'errors': errors,
        'stats': stats,
    }


def _upsert_receipt(cursor, group, batch_id):
    cursor.execute(
        'SELECT id FROM forex_receipt WHERE receipt_business_key = %s',
        (group['receipt_business_key'],),
    )
    existing = cursor.fetchone()
    params = (
        group['group_key'], group.get('core_transaction_no'), group.get('receipt_total_usd'),
        group.get('actual_exchange_rate'), group.get('actual_exchange_rate_raw'),
        group.get('settlement_receipt_rmb'), group.get('receipt_date'),
        group.get('difference_usd'), group.get('business_entity'),
        group.get('source_sheet_name'), batch_id,
    )
    if existing:
        cursor.execute('''
            UPDATE forex_receipt SET
                core_transaction_no=%s, receipt_total_usd=%s,
                actual_exchange_rate=%s, actual_exchange_rate_raw=%s,
                settlement_receipt_rmb=%s, receipt_date=%s, difference_usd=%s,
                business_entity=%s, source_sheet_name=%s, import_batch_id=%s
            WHERE id=%s
        ''', params[1:] + (existing[0],))
        return existing[0], False

    cursor.execute('''
        INSERT INTO forex_receipt (
            receipt_business_key, core_transaction_no,
            receipt_total_usd, actual_exchange_rate, actual_exchange_rate_raw,
            settlement_receipt_rmb, receipt_date, difference_usd,
            business_entity, source_sheet_name, import_batch_id
        ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
    ''', (group['receipt_business_key'],) + params[1:])
    return cursor.lastrowid, True


def _upsert_receivable(cursor, record, batch_id, file_name):
    cursor.execute(
        'SELECT id FROM forex_export_receivable WHERE customs_no_match_key = %s',
        (record['customs_no_match_key'],),
    )
    existing = cursor.fetchone()
    values = (
        record['customs_declaration_no'], record.get('contract_no'), record.get('business_entity'),
        record.get('export_date_normalized'), record.get('customs_port'),
        record.get('customs_contract_usd'), record.get('export_amount_usd'),
        record.get('monthly_exchange_rate'), record.get('monthly_exchange_rate_raw'),
        'EXCEL_IMPORT', file_name, 'Sheet1',
        record.get('source_row_no'), batch_id,
    )
    if existing:
        cursor.execute('''
            UPDATE forex_export_receivable SET
                customs_declaration_no=%s,
                contract_no=COALESCE(%s, contract_no),
                business_entity=COALESCE(%s, business_entity),
                export_date=COALESCE(%s, export_date),
                customs_port=COALESCE(%s, customs_port),
                customs_contract_usd=COALESCE(%s, customs_contract_usd),
                export_amount_usd=COALESCE(%s, export_amount_usd),
                monthly_exchange_rate=COALESCE(%s, monthly_exchange_rate),
                monthly_exchange_rate_raw=COALESCE(%s, monthly_exchange_rate_raw),
                source_type=%s, source_file_name=%s, source_sheet_name=%s,
                source_row_no=%s, import_batch_id=%s
            WHERE id=%s
        ''', values + (existing[0],))
        return existing[0], False

    cursor.execute('''
        INSERT INTO forex_export_receivable (
            customs_no_match_key, customs_declaration_no, contract_no, business_entity,
            export_date, customs_port, customs_contract_usd, export_amount_usd,
            monthly_exchange_rate, monthly_exchange_rate_raw,
            source_type, source_file_name, source_sheet_name, source_row_no, import_batch_id
        ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
    ''', (record['customs_no_match_key'],) + values)
    return cursor.lastrowid, True


def confirm_forex_import(preview_data, file_path, file_hash, batch_id, file_name):
    """以一个数据库事务写入应收、回款和分配三张表。"""
    del file_path, file_hash  # 预览数据已包含本次确认所需字段
    conn = get_conn()
    cursor = conn.cursor()
    conn.start_transaction()
    try:
        groups = preview_data.get('receipt_groups') or _build_receipt_groups(preview_data['records'])
        receipt_ids_by_group = {}
        receipt_ids_by_business = {}
        new_receipt = upd_receipt = 0
        for group in groups:
            business_key = group['receipt_business_key']
            if business_key in receipt_ids_by_business:
                receipt_id = receipt_ids_by_business[business_key]
            else:
                receipt_id, is_new = _upsert_receipt(cursor, group, batch_id)
                receipt_ids_by_business[business_key] = receipt_id
                new_receipt += int(is_new)
                upd_receipt += int(not is_new)
            receipt_ids_by_group[group['group_key']] = receipt_id

        new_receivable = upd_receivable = 0
        new_allocation = upd_allocation = 0
        for record in preview_data['records']:
            if record.get('skip_import'):
                continue
            receivable_id, is_new = _upsert_receivable(cursor, record, batch_id, file_name)
            new_receivable += int(is_new)
            upd_receivable += int(not is_new)

            receipt_id = receipt_ids_by_group.get(record.get('receipt_group_key'))
            allocation_amount = _to_decimal(record.get('allocation_amount_usd'))
            if not receipt_id or allocation_amount is None:
                continue
            cursor.execute('''
                SELECT id FROM forex_receipt_allocation
                WHERE receipt_id=%s AND receivable_id=%s
            ''', (receipt_id, receivable_id))
            existing = cursor.fetchone()
            if existing:
                cursor.execute('''
                    UPDATE forex_receipt_allocation SET
                        allocated_amount_usd=%s, source_sheet_name='Sheet1',
                        source_row_no=%s, import_batch_id=%s
                    WHERE id=%s
                ''', (allocation_amount, record['source_row_no'], batch_id, existing[0]))
                upd_allocation += 1
            else:
                cursor.execute('''
                    INSERT INTO forex_receipt_allocation (
                        receipt_id, receivable_id, allocated_amount_usd,
                        source_sheet_name, source_row_no, import_batch_id
                    ) VALUES (%s,%s,%s,'Sheet1',%s,%s)
                ''', (receipt_id, receivable_id, allocation_amount,
                      record['source_row_no'], batch_id))
                new_allocation += 1

        conn.commit()
        return {
            'new_receivable': new_receivable,
            'upd_receivable': upd_receivable,
            'new_receipt': new_receipt,
            'upd_receipt': upd_receipt,
            'new_allocation': new_allocation,
            'upd_allocation': upd_allocation,
        }
    except Exception:
        conn.rollback()
        raise
    finally:
        cursor.close()
        conn.close()
