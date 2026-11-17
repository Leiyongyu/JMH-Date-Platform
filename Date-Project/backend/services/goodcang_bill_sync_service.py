"""eBay 月度利润表数据拉取（二）：谷仓账单费用明细（海外仓尾程 / 仓储），按自然月。

- 谷仓每半个月出一张账单（1～14 日、15～月底），某月 = 账单截止时间落在该月的账单（2026-10 两张）。
- 只取 eBay 业务账户（GOODCANG_BILL_ACCOUNTS，默认 ACG1064502）。
- 账单列表 finance/billing_list → 下载 finance/billing_export（多张一次下载，返回 zip；该接口限流严格，只请求一次）。
- 解析账单里各费用明细页，一行一笔费用，金额取「本期费用小计」：
    入库费用明细 → 入库费用；仓租费用明细 → 仓储费；订单费用明细 → 出库费用；退货费用明细 → 退货费用；
    增值及附加服务费用明细 → 业务类型（标准增值 / 异常服务）；理赔及返还费用明细 → 理赔及返还（负数）。
  平台：订单费用明细取账单的「平台」列，其余明细为 EBAY（与财务手工表一致）。
  2026-10 与手工表「海外仓尾程原表」逐项核对：29,873 行，各费用类型、各币种金额完全一致。
- 理赔单没有 SKU 列，错发货的 SKU 写在备注里（「错发货明细：JMH-20049-0056*1」），从备注里取。
- 整月替换；任何一步失败不写库，保留上一次的数据。
"""
from __future__ import annotations

import base64
import io
import logging
import re
import zipfile
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any
from uuid import uuid4
from zoneinfo import ZoneInfo

from backend.config import settings
from backend.integrations.goodcang.client import GoodcangClient
from backend.repositories import ebay_monthly_profit_repository as repo
from backend.services.amazon_profit_sync_service import previous_natural_month

LOG = logging.getLogger(__name__)
TASK_CODE = "goodcang_bill_monthly_sync"
TASK_NAME = "eBay月度利润表-谷仓账单拉取"
SHEET_TYPES = {"入库费用明细": "入库费用", "仓租费用明细": "仓储费", "订单费用明细": "出库费用",
               "退货费用明细": "退货费用", "理赔及返还费用明细": "理赔及返还"}
VAS_SHEET = "增值及附加服务费用明细"
SKU_IN_REMARK = re.compile(r"JMH-[A-Za-z0-9-]+\*\d+")
MAX_PAGES = 50


class GoodcangBillSyncError(RuntimeError):
    def __init__(self, stage: str, message: str, metrics: dict[str, Any] | None = None):
        super().__init__(message)
        self.stage = stage
        self.metrics = metrics or {}


def _month(value: str | None) -> str:
    text = str(value or "").strip()
    if not text:
        return previous_natural_month()
    datetime.strptime(text, "%Y-%m")
    return text


def _bounds(month: str) -> tuple[str, str]:
    year, number = (int(part) for part in month.split("-"))
    last = date(year + number // 12, number % 12 + 1, 1) - timedelta(days=1)
    return f"{month}-01 00:00:00", f"{last.isoformat()} 23:59:59"


def _accounts() -> list[str]:
    return [item.strip() for item in (settings.goodcang_bill_accounts or "").split(",") if item.strip()]


def _text(value: Any, limit: int = 255) -> str | None:
    if value is None:
        return None
    text = str(value).strip()[:limit]
    return text or None


def _dec(value: Any) -> Decimal | None:
    if value in (None, ""):
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


# ------------------------------------------------------------ 解析（纯函数）
def parse_bill(content: bytes, bill: dict[str, Any], month: str) -> list[dict[str, Any]]:
    """一张账单 xlsx → 费用行。"""
    from openpyxl import load_workbook

    workbook = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    rows: list[dict[str, Any]] = []
    for sheet in workbook.worksheets:
        if sheet.title not in SHEET_TYPES and sheet.title != VAS_SHEET:
            continue
        sheet.reset_dimensions()  # 谷仓导出的维度信息不准，不重置只能读到第一行
        iterator = sheet.iter_rows(values_only=True)
        header = next(iterator, None)
        if not header:
            continue
        index = {str(name).strip(): position for position, name in enumerate(header) if name is not None}

        def get(row, *names):
            for name in names:
                position = index.get(name)
                if position is not None and position < len(row) and row[position] not in (None, ""):
                    return row[position]
            return None

        for row_no, values in enumerate(iterator, 2):
            if not any(value not in (None, "") for value in values):
                continue
            amount = _dec(get(values, "本期费用小计"))
            if amount is None:
                continue
            fee_type = SHEET_TYPES.get(sheet.title) or _text(get(values, "业务类型"))
            platform = (_text(get(values, "平台")) or "EBAY") if sheet.title == "订单费用明细" else "EBAY"
            remark = _text(get(values, "备注"))
            sku = _text(get(values, "SKU"))
            if not sku and remark:
                found = SKU_IN_REMARK.search(remark)
                sku = found.group(0) if found else None
            charge_time = get(values, "计费时间")
            rows.append({
                "stat_month": month, "bill_number": bill["bill_number"], "sheet_name": sheet.title,
                "row_no": row_no, "account_code": bill.get("account_code"),
                "bill_from": bill.get("bill_from_time"), "bill_to": bill.get("bill_to_time"),
                "fee_type": fee_type, "fee_detail": _text(get(values, "费用明细")),
                "business_type": _text(get(values, "业务类型")), "business_no": _text(get(values, "业务单号")),
                "related_no": _text(get(values, "关联单号")),
                "tracking_no": _text(get(values, "跟踪号", "海柜号/跟踪号")),
                "warehouse_code": _text(get(values, "仓库代码")), "sku": sku, "platform": platform,
                "currency": _text(get(values, "币种")), "amount": amount,
                "charge_time": _text(charge_time)[:19] if charge_time else None, "remark": remark[:500] if remark else None,
            })
    workbook.close()
    return rows


def unpack(data: bytes, bills: list[dict[str, Any]]) -> dict[str, bytes]:
    """下载内容 → {账单号: xlsx}。单张时直接是 xlsx（本身也是 zip 格式，靠 [Content_Types].xml 区分）。"""
    archive = zipfile.ZipFile(io.BytesIO(data))
    names = archive.namelist()
    if "[Content_Types].xml" in names:
        return {bills[0]["bill_number"]: data}
    files = {}
    for name in names:
        for bill in bills:
            if name.split("/")[-1].startswith(bill["bill_number"]):
                files[bill["bill_number"]] = archive.read(name)
    return files


# ------------------------------------------------------------ 拉取
def list_month_bills(client: GoodcangClient, month: str) -> list[dict[str, Any]]:
    begin, end = _bounds(month)
    accounts = set(_accounts())
    bills, page = [], 1
    while page <= MAX_PAGES:
        result = client.fetch_bill_page(begin, end, page)
        if result.get("code") not in (0, "0"):
            raise GoodcangBillSyncError("账单列表", f"谷仓账单列表返回失败：{str(result.get('message'))[:200]}")
        data = result.get("data") or {}
        items = data.get("list") or []
        bills += [item for item in items if not accounts or item.get("account_code") in accounts]
        if len(items) < 200 or page * 200 >= int(data.get("total") or 0):
            break
        page += 1
    return sorted(bills, key=lambda item: item.get("bill_to_time") or "")


def sync_goodcang_bills(stat_month: str | None = None, *, client: GoodcangClient | None = None) -> dict[str, Any]:
    month = _month(stat_month)
    owned = client is None
    client = client or GoodcangClient()
    try:
        bills = list_month_bills(client, month)
        if not bills:
            raise GoodcangBillSyncError("账单列表", f"{month} 没有账户 {','.join(_accounts())} 的谷仓账单，未写库")
        result = client.export_bills([bill["bill_number"] for bill in bills])
    finally:
        if owned:
            client.http.close()
    if result.get("code") not in (0, "0") or not result.get("data"):
        raise GoodcangBillSyncError("账单下载", f"谷仓账单下载返回失败：{str(result.get('message'))[:200]}")
    files = unpack(base64.b64decode(result["data"]), bills)
    missing = [bill["bill_number"] for bill in bills if bill["bill_number"] not in files]
    if missing:
        raise GoodcangBillSyncError("账单下载", "下载内容缺少账单：" + "、".join(missing))
    rows = []
    for bill in bills:
        rows.extend(parse_bill(files[bill["bill_number"]], bill, month))
    if not rows:
        raise GoodcangBillSyncError("账单解析", "账单里没有解析到任何费用明细，未写库")
    batch_id = uuid4().hex
    pulled_at = datetime.now(ZoneInfo("Asia/Shanghai")).replace(tzinfo=None)
    written = repo.replace_bill_rows(month, rows, batch_id=batch_id, pulled_at=pulled_at)
    totals: dict[str, Decimal] = {}
    for row in rows:
        key = f"{row['fee_type']}|{row['currency']}"
        totals[key] = totals.get(key, Decimal(0)) + row["amount"]
    return {"stat_month": month, "sync_batch_id": batch_id, "pulled_at": pulled_at.strftime("%Y-%m-%d %H:%M:%S"),
            "bills": [bill["bill_number"] for bill in bills], "extract_rows": len(rows), "ods_rows": written,
            "totals": {key: str(value) for key, value in sorted(totals.items())}}
