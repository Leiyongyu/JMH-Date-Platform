"""退税领域任务处理器；执行统一交给 infrastructure.task_queue。"""

from modules.tax_refund.repository import update_task_progress
from modules.tax_refund.repository import insert_excel_item, set_excel_items_old_version
from modules.tax_refund.repository import upsert_export_detail
from modules.tax_refund.repository import count_allocations
from modules.tax_refund.repository import count_receipts
from modules.tax_refund.repository import (
    check_duplicate_file,
    create_import_batch,
    update_import_batch,
)
from modules.tax_refund.repository import insert_purchase_inventory
from modules.tax_refund.parsers.customs_pdf import parse_customs_pdf_full
from modules.tax_refund.parsers.customs_excel import parse_customs_excel
from modules.tax_refund.parsers.export_matcher import match_and_enrich_export_records
from modules.tax_refund.parsers.forex_import import confirm_forex_import, preview_forex_import
from modules.tax_refund.parsers.invoice_pdf import parse_invoice_pdf_full
from modules.tax_refund.workflow import RefundWorkflow, WorkflowOptions
from modules.tax_refund.inventory_service import reverse_generation
from infrastructure.task_queue import get_task_queue, register_handler


TASK_CUSTOMS_MATERIAL = 'CUSTOMS_MATERIAL_IMPORT'
TASK_CUSTOMS_DECLARATION = 'CUSTOMS_DECLARATION_IMPORT'
TASK_PURCHASE_INVOICE = 'PURCHASE_INVOICE_IMPORT'
TASK_FOREX = 'FOREX_IMPORT'
TASK_REFUND_PACKAGE = 'REFUND_PACKAGE_GENERATE'
TASK_REFUND_REVERSE = 'REFUND_PACKAGE_REVERSE'

TASK_TYPES = {
    TASK_CUSTOMS_MATERIAL,
    TASK_CUSTOMS_DECLARATION,
    TASK_PURCHASE_INVOICE,
    TASK_FOREX,
    TASK_REFUND_PACKAGE,
    TASK_REFUND_REVERSE,
}

FILE_TASK_EXTENSIONS = {
    TASK_CUSTOMS_MATERIAL: '.xlsx',
    TASK_CUSTOMS_DECLARATION: '.pdf',
    TASK_PURCHASE_INVOICE: '.pdf',
    TASK_FOREX: '.xlsx',
}

def submit_task(task_id):
    """兼容现有路由；所有任务统一进入可靠任务队列。"""
    get_task_queue().enqueue(task_id)


def _file_context(task, import_type):
    path = task.get('stored_file_path')
    if not path:
        raise ValueError('任务缺少已保存的源文件')
    payload = task.get('request_payload') or {}
    batch_id = create_import_batch(
        import_type,
        task.get('original_file_name') or '',
        path,
        task.get('file_sha256') or '',
        int(payload.get('file_size') or 0),
        task.get('created_by') or 'ERP',
    )
    return path, payload, batch_id


@register_handler(TASK_CUSTOMS_MATERIAL)
def _import_customs_material(task_id, task):
    path, payload, batch_id = _file_context(task, 'CUSTOMS_EXCEL')
    contract_no, format_version, items, error = parse_customs_excel(path)
    if error or not items:
        message = error or '未解析到商品数据'
        update_import_batch(batch_id, parse_status='FAILED', error_message=message)
        raise ValueError(message)
    update_task_progress(task_id, 0, len(items))
    archived = set_excel_items_old_version(contract_no, task.get('file_sha256'))
    success = 0
    errors = []
    for index, item in enumerate(items, start=1):
        item['import_batch_id'] = batch_id
        item['created_by'] = task.get('created_by') or 'ERP'
        item['updated_by'] = task.get('created_by') or 'ERP'
        try:
            insert_excel_item(item)
            success += 1
        except Exception as exc:
            errors.append({'row': item.get('source_row_no'), 'message': str(exc)})
        update_task_progress(task_id, index, len(items))
    status = 'SUCCESS' if not errors else 'PARTIAL_SUCCESS'
    update_import_batch(
        batch_id, parse_status=status, total_count=len(items),
        success_count=success, error_count=len(errors),
        error_message='; '.join(error['message'] for error in errors[:10]) or None,
    )
    return {
        'import_batch_id': batch_id,
        'contract_no': contract_no,
        'format': format_version,
        'total_count': len(items),
        'success_count': success,
        'error_count': len(errors),
        'old_archived': archived,
        'errors': errors,
    }, ('SUCCESS' if not errors else 'PARTIAL')


@register_handler(TASK_CUSTOMS_DECLARATION)
def _import_customs_declaration(task_id, task):
    path, payload, batch_id = _file_context(task, 'CUSTOMS_PDF')
    records, stats = parse_customs_pdf_full(path, task.get('file_sha256'), batch_id,
                                           task.get('created_by') or 'ERP')
    if stats.get('error_message') or not records:
        message = stats.get('error_message') or '报关单没有解析到商品记录'
        update_import_batch(batch_id, parse_status='FAILED', error_message=message)
        raise ValueError(message)
    records, match_stats = match_and_enrich_export_records(
        records,
        declaration_month=payload.get('declaration_month'),
        declaration_batch=payload.get('declaration_batch'),
        export_date=payload.get('export_date'),
    )
    update_task_progress(task_id, 0, len(records))
    new_count = update_count = 0
    for index, record in enumerate(records, start=1):
        _, is_new = upsert_export_detail(record)
        new_count += int(is_new)
        update_count += int(not is_new)
        update_task_progress(task_id, index, len(records))
    update_import_batch(
        batch_id, parse_status='SUCCESS', total_count=len(records),
        success_count=len(records), error_count=0,
    )
    return {
        'import_batch_id': batch_id,
        'customs_declaration_no': records[0].get('customs_declaration_no'),
        'total_count': len(records),
        'new_count': new_count,
        'update_count': update_count,
        'match': match_stats,
    }, 'SUCCESS'


@register_handler(TASK_PURCHASE_INVOICE)
def _import_purchase_invoice(task_id, task):
    path, payload, batch_id = _file_context(task, 'INVOICE_PDF')
    decl_month = str(payload.get('declaration_month') or '').strip() or None
    decl_batch = str(payload.get('declaration_batch') or '').strip().zfill(3) if payload.get('declaration_batch') else None
    records, stats = parse_invoice_pdf_full(
        path, task.get('file_sha256'), batch_id, task.get('created_by') or 'ERP',
        declaration_month=decl_month, declaration_batch=decl_batch)
    if stats.get('error_message') or not records:
        message = stats.get('error_message') or '发票没有解析到商品记录'
        update_import_batch(batch_id, parse_status='FAILED', error_message=message)
        raise ValueError(message)

    update_task_progress(task_id, 0, len(records))
    success = 0
    errors = []
    for index, record in enumerate(records, start=1):
        try:
            record['declaration_month'] = decl_month
            record['declaration_batch'] = decl_batch
            record['sequence_no'] = str(index).zfill(8)
            record['relation_no'] = f'{decl_month}{decl_batch}{str(index).zfill(8)}' if (decl_month and decl_batch) else None
            insert_purchase_inventory(record)
            success += 1
        except Exception as exc:
            errors.append({'invoice_item_no': record.get('invoice_item_no'), 'message': str(exc)})
        update_task_progress(task_id, index, len(records))
    status = 'SUCCESS' if not errors else 'PARTIAL'
    update_import_batch(
        batch_id, parse_status=status, total_count=len(records),
        success_count=success, error_count=len(errors),
        error_message='; '.join(error['message'] for error in errors[:10]) or None,
    )
    return {
        'import_batch_id': batch_id,
        'total_count': len(records),
        'success_count': success,
        'error_count': len(errors),
        'errors': errors,
    }, status


@register_handler(TASK_FOREX)
def _import_forex(task_id, task):
    duplicate = check_duplicate_file(task.get('file_sha256'), 'FOREX_EXCEL')
    if duplicate and duplicate[1] == 'SUCCESS':
        return {
            'import_batch_id': duplicate[0],
            'duplicate': True,
            'message': '相同文件已成功导入，本次未重复写入',
        }, 'SUCCESS'
    path, payload, batch_id = _file_context(task, 'FOREX_EXCEL')
    preview = preview_forex_import(path, task.get('file_sha256'))
    update_task_progress(task_id, 0, len(preview['records']))
    result = confirm_forex_import(
        preview, path, task.get('file_sha256'), batch_id,
        task.get('original_file_name') or '',
    )
    update_task_progress(task_id, len(preview['records']), len(preview['records']))
    update_import_batch(
        batch_id, parse_status='SUCCESS', total_count=len(preview['records']),
        success_count=result['new_receivable'] + result['upd_receivable'],
        error_count=preview.get('stats', {}).get('error_count', 0),
    )
    return {
        'import_batch_id': batch_id,
        'total_count': len(preview['records']),
        'validation_error_count': preview.get('stats', {}).get('error_count', 0),
        **result,
        'receipt_total': count_receipts(),
        'allocation_total': count_allocations(),
    }, 'SUCCESS'


@register_handler(TASK_REFUND_PACKAGE)
def _generate_refund_package(task_id, task):
    payload = task.get('request_payload') or {}
    options = WorkflowOptions(
        output_parent_dir=str(payload.get('output_parent_dir') or '').strip(),
        declaration_month=str(payload.get('declaration_month') or '202512').strip(),
        overwrite=_as_bool(payload.get('overwrite', False)),
        payer_name=str(
            payload.get('payer_name') or 'Hong Kong Cammy Yeson Limited').strip(),
        export_ids=payload.get('export_ids'),
        task_id=task_id,
        idempotency_key=task.get('idempotency_key'),
        operator_id=str(task.get('operator_id') or task.get('created_by') or 'ERP'),
        operator_name=str(task.get('operator_name') or task.get('created_by') or 'ERP'),
    )
    update_task_progress(task_id, 0, 1)
    result = RefundWorkflow().run(options)
    if not result.success:
        raise ValueError('; '.join(result.errors) or '退税汇总生成失败')
    update_task_progress(task_id, 1, 1)
    return result.to_dict(), 'SUCCESS'


@register_handler(TASK_REFUND_REVERSE)
def _reverse_refund_package(task_id, task):
    payload = task.get('request_payload') or {}
    update_task_progress(task_id, 0, 1)
    result = reverse_generation(
        generation_id=int(payload['generation_id']),
        operator_id=str(task.get('operator_id') or task.get('created_by') or 'ERP'),
        operator_name=str(task.get('operator_name') or task.get('created_by') or 'ERP'),
        reason=str(payload.get('reason') or '').strip(),
        reverse_task_id=task_id,
    )
    update_task_progress(task_id, 1, 1)
    return result, 'SUCCESS'


def _as_bool(value):
    """兼容 JSON 布尔值和 multipart 表单字符串。"""
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in ('1', 'true', 'yes', 'y', 'on')
