"""FastAPI 实现的 ERP RESTful + 任务型 API。"""

from datetime import date, datetime
from decimal import Decimal
import math
import os
import hashlib
from urllib.parse import quote, unquote

from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import ValidationError

from modules.tax_refund.repository import create_task, get_task, list_tasks
from modules.tax_refund.repository import get_excel_items_by_contract
from modules.tax_refund.repository import get_all_exports, get_exports_for_excel
from modules.tax_refund.repository import list_receivables
from modules.tax_refund.repository import get_all_inventory, get_inventory_for_excel
from modules.tax_refund.repository import get_receivables_for_excel
from modules.tax_refund.inventory_service import list_allocations, list_generations
from modules.tax_refund.schemas import (
    ErrorResponse, ExcelExportRequest, RefundPackageReverseTaskRequest,
    RefundPackageTaskRequest, TaskAcceptedResponse,
)
from modules.tax_refund.parsers.export_report import build_export_detail_workbook
from modules.tax_refund.parsers.purchase_report import build_purchase_detail_workbook
from modules.tax_refund.parsers.forex_report import build_forex_summary_workbook
from modules.tax_refund.task_handlers import (
    FILE_TASK_EXTENSIONS,
    TASK_REFUND_PACKAGE,
    TASK_REFUND_REVERSE,
    TASK_TYPES,
    submit_task,
)
from infrastructure.file_storage import compute_sha256, save_upload_stream
from modules.finance.ebay_finance import router as ebay_finance_router


router = APIRouter(prefix='/api/v1', tags=['ERP v1'])
router.include_router(ebay_finance_router)


def serialize(value):
    if isinstance(value, dict):
        return {key: serialize(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [serialize(item) for item in value]
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    return value


def success(data, status_code=200, meta=None, headers=None):
    body = {'success': True, 'data': serialize(data)}
    if meta is not None:
        body['meta'] = meta
    return JSONResponse(body, status_code=status_code, headers=headers)


def error(message, status_code=400, code='BAD_REQUEST', details=None):
    error_body = {'code': code, 'message': message}
    if details is not None:
        error_body['details'] = serialize(details)
    return JSONResponse(
        {'success': False, 'error': error_body}, status_code=status_code)


def page_meta(page, page_size, total):
    return {
        'page': page,
        'page_size': page_size,
        'total': total,
        'total_pages': math.ceil(total / page_size) if total else 0,
    }


def excel_response(content, chinese_name: str, ascii_name: str):
    encoded_name = quote(chinese_name)
    return StreamingResponse(
        content,
        media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        headers={
            'Content-Disposition': (
                f'attachment; filename="{ascii_name}"; '
                f"filename*=UTF-8''{encoded_name}"
            ),
            'Cache-Control': 'no-store',
        },
    )


def export_ids_or_error(request: ExcelExportRequest):
    ids = request.normalized_ids
    if request.ids is not None and not ids:
        return None, error('ids不能为空数组；导出全部请传null或省略ids', 422, 'EMPTY_EXPORT_SELECTION')
    return ids, None


async def _task_payload(request):
    content_type = request.headers.get('content-type', '').lower()
    if content_type.startswith('application/json'):
        try:
            payload = await request.json()
        except Exception:
            return None, None, error('JSON 请求体格式错误', 400, 'INVALID_JSON')
        if not isinstance(payload, dict):
            return None, None, error('JSON 请求体必须是对象', 422, 'INVALID_PAYLOAD')
        return dict(payload), None, None

    form = await request.form()
    uploads = form.getlist('file')  # 支持多文件
    payload = {
        key: value for key, value in form.items()
        if key != 'file' and isinstance(value, str)
    }
    return payload, uploads, None


async def _close_upload(upload):
    if upload is not None and hasattr(upload, 'close'):
        await upload.close()


@router.post(
    '/tasks',
    status_code=202,
    response_model=TaskAcceptedResponse,
    responses={
        400: {'model': ErrorResponse},
        413: {'model': ErrorResponse},
        422: {'model': ErrorResponse},
        500: {'model': ErrorResponse},
    },
    openapi_extra={
        'requestBody': {
            'required': True,
            'content': {
                'application/json': {
                    'schema': {
                        'oneOf': [
                            RefundPackageTaskRequest.model_json_schema(),
                            RefundPackageReverseTaskRequest.model_json_schema(),
                        ]
                    },
                },
                'multipart/form-data': {
                    'schema': {
                        'type': 'object',
                        'required': ['task_type', 'file'],
                        'properties': {
                            'task_type': {
                                'type': 'string',
                                'enum': sorted(FILE_TASK_EXTENSIONS),
                            },
                            'file': {'type': 'string', 'format': 'binary'},
                            'declaration_month': {'type': 'string'},
                            'declaration_batch': {'type': 'string'},
                            'export_date': {'type': 'string', 'format': 'date'},
                            'created_by': {'type': 'string'},
                        },
                    },
                },
            },
        },
    },
    summary='创建导入或退税资料生成任务',
)
async def create_api_task(request: Request):
    payload, upload, payload_error = await _task_payload(request)
    if payload_error:
        return payload_error

    task_type = str(payload.pop('task_type', '') or '').strip().upper()
    if task_type not in TASK_TYPES:
        for u in (upload if isinstance(upload, list) else [upload] if upload else []):
            await _close_upload(u)
        return error(
            'task_type 不受支持', 422, 'UNSUPPORTED_TASK_TYPE',
            {'supported': sorted(TASK_TYPES)},
        )

    legacy_user = payload.pop('created_by', None)
    operator_id = str(
        request.headers.get('X-ERP-User-Id')
        or request.headers.get('X-ERP-User') or legacy_user or 'ERP'
    ).strip()[:64]
    # HTTP 请求头不能可靠承载原始中文；ERP/测试页使用 UTF-8 百分号编码。
    operator_name = unquote(str(
        request.headers.get('X-ERP-User-Name') or operator_id
    )).strip()[:100]
    created_by = operator_id
    raw_idempotency_key = str(request.headers.get('Idempotency-Key') or '').strip()
    original_name = stored_path = file_hash = None

    if task_type in (TASK_REFUND_PACKAGE, TASK_REFUND_REVERSE):
        if not request.headers.get('X-ERP-User-Id') or not request.headers.get('X-ERP-User-Name'):
            return error(
                '退税生成和冲销必须由ERP传递操作人ID及姓名',
                422,
                'ERP_OPERATOR_REQUIRED',
                {'required_headers': ['X-ERP-User-Id', 'X-ERP-User-Name']},
            )

    if task_type in FILE_TASK_EXTENSIONS:
        expected = FILE_TASK_EXTENSIONS[task_type]
        uploads_list = upload if isinstance(upload, list) else ([upload] if upload else [])
        if not uploads_list:
            return error('文件型任务必须提供 file', 422, 'FILE_REQUIRED')

        task_ids = []
        for single_upload in uploads_list:
            try:
                filename = getattr(single_upload, 'filename', None)
                if not filename:
                    continue
                if os.path.splitext(filename)[1].lower() != expected:
                    continue
                try:
                    stored_path, original_name, file_size = save_upload_stream(
                        filename, single_upload.file)
                finally:
                    await _close_upload(single_upload)
                file_hash = compute_sha256(stored_path)
                p = dict(payload)
                p['file_size'] = file_size
                task_id = create_task(
                    task_type=task_type,
                    request_payload=p,
                    original_file_name=original_name,
                    stored_file_path=stored_path,
                    file_sha256=file_hash,
                    created_by=created_by,
                    operator_id=operator_id,
                    operator_name=operator_name,
                    idempotency_key=(
                        hashlib.sha256(
                            f'{task_type}:{raw_idempotency_key}:{file_hash}'.encode('utf-8')
                        ).hexdigest()
                        if raw_idempotency_key else None
                    ),
                )
                submit_task(task_id)
                task_ids.append(task_id)
            except Exception:
                pass

        if not task_ids:
            return error('没有成功创建任何任务', 422, 'NO_VALID_FILES')
        location = f'/api/v1/tasks/{task_ids[-1]}'
        return success(
            {
                'task_ids': task_ids,
                'count': len(task_ids),
                'task_type': task_type,
                'task_status': 'PENDING',
                'status_url': location,
            },
            status_code=202,
            headers={'Location': location},
        )
    elif task_type in (TASK_REFUND_PACKAGE, TASK_REFUND_REVERSE):
        try:
            schema = (
                RefundPackageTaskRequest
                if task_type == TASK_REFUND_PACKAGE
                else RefundPackageReverseTaskRequest
            )
            validated = schema.model_validate({
                'task_type': task_type,
                **payload,
            })
        except ValidationError as exc:
            return error(
                '退税资料生成参数不合法', 422, 'INVALID_TASK_PAYLOAD',
                exc.errors(include_url=False),
            )
        payload = validated.model_dump(exclude={'task_type', 'created_by'})

        task_id = create_task(
            task_type=task_type,
            request_payload=payload,
            created_by=created_by,
            operator_id=operator_id,
            operator_name=operator_name,
            idempotency_key=(
                hashlib.sha256(
                    f'{task_type}:{raw_idempotency_key}'.encode('utf-8')
                ).hexdigest()
                if raw_idempotency_key else None
            ),
        )
        submit_task(task_id)
        location = f'/api/v1/tasks/{task_id}'
        return success(
            {
                'id': task_id,
                'task_type': task_type,
                'task_status': 'PENDING',
                'status_url': location,
            },
            status_code=202,
            headers={'Location': location},
        )


@router.get('/tasks/{task_id}', summary='查询任务状态和结果')
def get_api_task(task_id: int):
    task = get_task(task_id)
    if not task:
        return error('任务不存在', 404, 'TASK_NOT_FOUND')
    return success(task)


@router.get('/tasks', summary='分页查询任务历史')
def get_api_tasks(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    task_type: str | None = None,
    task_status: str | None = None,
):
    rows, total = list_tasks(page, page_size, task_type, task_status)
    return success(rows, meta=page_meta(page, page_size, total))


@router.get('/customs-material-items', summary='查询报关资料商品')
def get_customs_material_items(contract_no: str = Query(min_length=1)):
    return success(get_excel_items_by_contract(contract_no.strip()))


@router.get('/export-details', summary='分页查询完整出口明细')
def get_export_details(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    contract_no: str | None = None,
    customs_declaration_no: str | None = None,
    declaration_month: str | None = None,
    declaration_batch: str | None = None,
    relation_no: str | None = None,
    customs_match_status: str | None = None,
):
    rows, total = get_all_exports(
        page=page,
        per_page=page_size,
        contract_no=contract_no,
        customs_declaration_no=customs_declaration_no,
        declaration_month=declaration_month,
        declaration_batch=declaration_batch,
        relation_no=relation_no,
        customs_match_status=customs_match_status,
    )
    return success(rows, meta=page_meta(page, page_size, total))


@router.post('/export-details/export', summary='导出选中或全部出口明细Excel')
def export_details_excel(request: ExcelExportRequest):
    ids, selection_error = export_ids_or_error(request)
    if selection_error:
        return selection_error
    rows = get_exports_for_excel(ids)
    stamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    return excel_response(
        build_export_detail_workbook(rows),
        f'出口明细_{stamp}.xlsx',
        f'export_details_{stamp}.xlsx',
    )


@router.get('/purchase-inventory', summary='分页查询进货库存')
def get_purchase_inventory(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    invoice_no: str | None = None,
    invoice_date_from: str | None = None,
    invoice_date_to: str | None = None,
    supplier_tax_no: str | None = None,
    buyer_tax_no: str | None = None,
    sku_normalized: str | None = None,
    inventory_status: str | None = None,
):
    rows, total = get_all_inventory(
        page=page,
        per_page=page_size,
        invoice_no=invoice_no,
        invoice_date_from=invoice_date_from,
        invoice_date_to=invoice_date_to,
        supplier_tax_no=supplier_tax_no,
        buyer_tax_no=buyer_tax_no,
        sku_normalized=sku_normalized,
        inventory_status=inventory_status,
    )
    return success(rows, meta=page_meta(page, page_size, total))


@router.post('/purchase-inventory/export', summary='导出选中或全部进货明细Excel')
def export_purchase_inventory_excel(request: ExcelExportRequest):
    ids, selection_error = export_ids_or_error(request)
    if selection_error:
        return selection_error
    rows = get_inventory_for_excel(ids)
    stamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    return excel_response(
        build_purchase_detail_workbook(rows),
        f'进货明细_{stamp}.xlsx',
        f'purchase_details_{stamp}.xlsx',
    )


@router.get('/refund-generations', summary='分页查询退税文件生成批次')
def get_refund_generations(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: str | None = None,
    operator_id: str | None = None,
    declaration_month: str | None = None,
):
    rows, total = list_generations(
        page, page_size, status=status, operator_id=operator_id,
        declaration_month=declaration_month,
    )
    return success(rows, meta=page_meta(page, page_size, total))


@router.get('/inventory-allocations', summary='分页查询库存扣减和冲销流水')
def get_inventory_allocations(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    generation_id: int | None = None,
    invoice_no: str | None = None,
    sku_normalized: str | None = None,
    customs_declaration_no: str | None = None,
    operator_id: str | None = None,
    entry_type: str | None = None,
    status: str | None = None,
):
    rows, total = list_allocations(
        page, page_size, generation_id=generation_id, invoice_no=invoice_no,
        sku_normalized=sku_normalized,
        customs_declaration_no=customs_declaration_no,
        operator_id=operator_id, entry_type=entry_type, status=status,
    )
    return success(rows, meta=page_meta(page, page_size, total))


@router.get('/forex-receivables', summary='分页查询外汇应收')
def get_forex_receivables(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    customs_no: str | None = None,
    contract_no: str | None = None,
    business_entity: str | None = None,
    source_type: str | None = None,
    export_date_from: str | None = None,
    export_date_to: str | None = None,
):
    rows, total = list_receivables(
        page=page,
        per_page=page_size,
        customs_no=customs_no,
        contract_no=contract_no,
        business_entity=business_entity,
        source_type=source_type,
        export_date_from=export_date_from,
        export_date_to=export_date_to,
    )
    return success(rows, meta=page_meta(page, page_size, total))


@router.post('/forex-receivables/export', summary='导出选中或全部回款汇总Excel')
def export_forex_receivables_excel(request: ExcelExportRequest):
    ids, selection_error = export_ids_or_error(request)
    if selection_error:
        return selection_error
    rows = get_receivables_for_excel(ids)
    stamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    return excel_response(
        build_forex_summary_workbook(rows),
        f'回款汇总_{stamp}.xlsx',
        f'forex_receivables_{stamp}.xlsx',
    )
