"""报关单 PDF 与报关资料 Excel 商品的匹配和合并。"""
import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from modules.tax_refund.repository import get_current_excel_items_map
from modules.tax_refund.repository import get_existing_export_identities, get_next_sequence_start


class ExportMatchError(ValueError):
    """上传顺序、匹配键或申报参数不满足入库要求。"""


def normalize_item_no(value):
    text = str(value or '').strip()
    match = re.match(r'0*(\d+)', text)
    return str(int(match.group(1))) if match else text


def _decimal(value):
    if value in (None, ''):
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None


def _month_from(value):
    if isinstance(value, (date, datetime)):
        return value.strftime('%Y%m')
    text = re.sub(r'\D', '', str(value or ''))
    return text[:6] if len(text) >= 6 else ''


def _validate_declaration_identity(records, declaration_month, declaration_batch):
    month = re.sub(r'\D', '', str(declaration_month or ''))
    if not month and records:
        month = _month_from(records[0].get('declaration_date'))
    if not re.fullmatch(r'\d{6}', month):
        raise ExportMatchError('无法确定6位申报年月，请在上传时填写，例如202601')
    raw_batch = str(declaration_batch or '').strip()
    if not raw_batch:
        return month, None
    batch = raw_batch.zfill(3)
    if not re.fullmatch(r'\d{3}', batch):
        raise ExportMatchError('申报批次必须是3位数字，例如001')
    return month, batch


def _parse_optional_export_date(value):
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value or '').strip()
    if not text:
        return None
    for date_format in ('%Y-%m-%d', '%Y%m%d'):
        try:
            return datetime.strptime(text, date_format).date()
        except ValueError:
            continue
    raise ExportMatchError('出口日期格式不正确，请使用YYYY-MM-DD')


def _comparison_warnings(pdf_record, excel_item):
    warnings = []
    pdf_code = re.sub(r'\D', '', str(pdf_record.get('export_product_code') or ''))
    excel_code = re.sub(r'\D', '', str(excel_item.get('commodity_code') or ''))
    if pdf_code and excel_code and pdf_code != excel_code:
        warnings.append(f'商品编码不一致(PDF={pdf_code}, Excel={excel_code})')

    pdf_qty = _decimal(pdf_record.get('export_quantity'))
    excel_qty = _decimal(excel_item.get('transaction_quantity'))
    if pdf_qty is not None and excel_qty is not None and abs(pdf_qty - excel_qty) > Decimal('0.000001'):
        warnings.append(f'成交数量不一致(PDF={pdf_qty}, Excel={excel_qty})')

    pdf_amount = _decimal(pdf_record.get('fob_amount'))
    excel_amount = _decimal(excel_item.get('total_price'))
    if pdf_amount is not None and excel_amount is not None and abs(pdf_amount - excel_amount) > Decimal('0.03'):
        warnings.append(f'总价不一致(PDF={pdf_amount}, Excel={excel_amount})')
    if excel_item.get('parse_status') == 'ERROR':
        warnings.append(f'报关资料解析异常: {excel_item.get("parse_message") or "未知原因"}')
    return warnings


def match_and_enrich_export_records(records, declaration_month=None, declaration_batch=None,
                                    export_date=None):
    """
    按合同协议号 + 标准化项号匹配当前报关资料，并以报关资料商品字段覆盖 PDF OCR 字段。
    返回 (合并记录, 统计信息)。任何缺失匹配都会阻止入库。
    """
    if not records:
        raise ExportMatchError('报关单没有解析到商品记录')
    contract_no = str(records[0].get('contract_no') or '').strip().upper()
    if not contract_no:
        raise ExportMatchError('报关单未识别到合同协议号，无法匹配报关资料')

    source_map, duplicates = get_current_excel_items_map(contract_no)
    if not source_map:
        raise ExportMatchError(
            f'合同 {contract_no} 尚未上传报关资料 Excel，请先导入 customs_declaration_excel_item')
    if duplicates:
        raise ExportMatchError(
            f'合同 {contract_no} 的当前报关资料存在重复项号: {", ".join(duplicates)}')

    missing = []
    for record in records:
        item_no = normalize_item_no(record.get('customs_item_no'))
        if item_no not in source_map:
            missing.append(item_no or '?')
    if missing:
        raise ExportMatchError(
            f'合同 {contract_no} 缺少报关资料项号: {", ".join(missing)}；请先上传完整报关资料')

    month, batch = _validate_declaration_identity(records, declaration_month, declaration_batch)
    selected_export_date = _parse_optional_export_date(export_date)
    next_sequence = get_next_sequence_start(month, batch) if batch else None
    existing_identities = get_existing_export_identities(
        records[0].get('customs_declaration_no'))
    enriched = []
    warning_count = 0
    allocated_count = 0
    reused_identity_count = 0
    for pdf_record in records:
        item_no = normalize_item_no(pdf_record.get('customs_item_no'))
        source = source_map[item_no]
        warnings = _comparison_warnings(pdf_record, source)
        warning_count += len(warnings)
        existing_identity = existing_identities.get(item_no)
        can_reuse_identity = (
            existing_identity
            and existing_identity.get('declaration_month') == month
            and existing_identity.get('declaration_batch') == batch
            and existing_identity.get('sequence_no')
        )
        if can_reuse_identity:
            sequence = str(existing_identity['sequence_no']).zfill(8)
            relation_no = existing_identity.get('relation_no') or (f'{month}{batch}{sequence}' if batch else None)
            reused_identity_count += 1
        elif batch:
            sequence = str(next_sequence + allocated_count).zfill(8)
            relation_no = f'{month}{batch}{sequence}'
            allocated_count += 1
        else:
            # 无批次时仍生成序号（按报关单项号顺序），关联号留空
            sequence = str(allocated_count + 1).zfill(8)
            relation_no = None
            allocated_count += 1
        record = dict(pdf_record)
        record.update({
            'customs_excel_item_id': source['id'],
            'customs_item_no': item_no,
            'contract_no': source['contract_agreement_no'],
            'export_date': selected_export_date or pdf_record.get('export_date'),
            'export_invoice_no': source.get('export_invoice_no') or record.get('export_invoice_no'),
            'export_product_code': source.get('commodity_code') or record.get('export_product_code'),
            'export_product_name': source.get('product_name') or record.get('export_product_name'),
            'sku_original': source.get('sku') or record.get('sku_original'),
            'sku_normalized': source.get('sku') or record.get('sku_normalized'),
            'unit': source.get('transaction_unit') or record.get('unit'),
            'export_quantity': source.get('transaction_quantity'),
            'statutory_quantity': source.get('statutory_quantity'),
            'statutory_unit': source.get('statutory_unit'),
            'unit_price': source.get('unit_price'),
            'fob_amount': source.get('total_price'),
            'currency_code': source.get('currency_code') or record.get('currency_code') or 'USD',
            'declaration_month': month,
            'declaration_batch': batch,
            'sequence_no': sequence,
            'relation_no': relation_no,
            'declared_product_code': None,
            'tax_business_type': None,
            'customs_match_status': 'MATCHED',
            'customs_match_message': '; '.join(warnings) or None,
        })
        enriched.append(record)
    return enriched, {
        'contract_no': contract_no,
        'matched_count': len(enriched),
        'warning_count': warning_count,
        'declaration_month': month,
        'declaration_batch': batch,
        'export_date': (
            selected_export_date or records[0].get('export_date')
        ).isoformat() if (selected_export_date or records[0].get('export_date')) else None,
        'reused_identity_count': reused_identity_count,
    }
