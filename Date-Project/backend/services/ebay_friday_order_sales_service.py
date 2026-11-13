"""eBay「周五数据 / 订单售出统计」：手动上传数字酋长「Order-交易级别」导出，按负责人出透视。

还原运营原来手工做的《订单售出数统计》的「透视」sheet（2026-11-13 用户确认口径）：
  - 只取平台为 eBay、库存SKU 不为空的行；作废 / 退款的订单照原表一起算；
  - 品牌 / 中间码：库存SKU 第一段 / 第二段（先去掉 2PC- / 4PC- 多件装前缀；JMH 开头的按中间码推品牌）；
  - 站点：币种 USD → US，EUR → DE，其他 → UK；
  - 美金收入 = 收入 × 订单汇率 ÷ 领星当月美元汇率（rate_org，按付款月份取，当月未出时回退到最近已出的月份；
    原表写死 6.70341，用户改为领星当月汇率）；
  - 负责人：当月 eBay 品牌负责人规则（飞书负责人映射表，与系统其他报表一致）；
  - 透视：每个负责人「中间码 + 站点」去重个数、美金收入合计、购买数量合计；总计行的去重数按全部订单重新去重。
只保留最新一次上传，不留历史；透视在读取时现算，负责人规则或汇率更新后自动跟上。
"""
from __future__ import annotations

import json
import logging
from collections import defaultdict
from datetime import datetime
from decimal import Decimal, InvalidOperation
from io import BytesIO
from typing import Any

from backend.database import db_connection
from backend.services import ebay_friday_report_service as friday
from backend.services.ebay_replenishment_periods import reference_today
from backend.services.inventory_report_etl_service import _ebay_assignment, _ebay_rule_map

LOG = logging.getLogger(__name__)
UPLOAD_TABLE = "ebay_friday_order_upload"
LINE_TABLE = "ebay_friday_order_line"
MIGRATION_MESSAGE = "订单售出统计表未部署，请执行 migrations/20261113_ebay_friday_order_sales.sql"
MAX_FILE_BYTES = 20 * 1024 * 1024
REQUIRED_HEADERS = ("平台订单号", "发货状态", "付款时间", "平台", "币种", "库存SKU", "购买数量", "汇率", "收入")
LINE_COLUMNS = ("row_no", "order_no", "ship_status", "pay_time", "currency", "order_rate", "income", "quantity",
                "stock_sku", "brand", "mid_code", "site")
UNASSIGNED = "未分配"


def _decimal(value: Any) -> Decimal | None:
    if value in (None, ""):
        return None
    try:
        number = Decimal(str(value).strip().replace(",", ""))
    except InvalidOperation:
        return None
    return number if number.is_finite() else None


def _datetime(value: Any):
    if isinstance(value, datetime):
        return value
    text = str(value or "").strip()
    if not text:
        return None
    for pattern in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d", "%Y/%m/%d %H:%M:%S", "%Y/%m/%d"):
        try:
            return datetime.strptime(text, pattern)
        except ValueError:
            continue
    return None


def currency_site(currency: Any) -> str:
    code = str(currency or "").strip().upper()
    if code == "USD":
        return "US"
    if code == "EUR":
        return "DE"
    return "UK"


# ------------------------------------------------------------------ 解析上传


def parse(content: bytes, brands: dict[str, str]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """读数字酋长订单导出（第一个 sheet，第一行表头）-> 订单行 + 统计。"""
    from openpyxl import load_workbook

    try:
        workbook = load_workbook(BytesIO(content), read_only=True, data_only=True)
    except Exception as exc:
        raise ValueError("无法读取文件，请上传数字酋长导出的 .xlsx 订单表") from exc
    sheet = workbook.worksheets[0]
    rows = sheet.iter_rows(values_only=True)
    header = [str(v or "").strip() for v in next(rows, ())]
    missing = [name for name in REQUIRED_HEADERS if name not in header]
    if missing:
        raise ValueError(f"文件缺少列：{'、'.join(missing)}；请上传数字酋长「Order-交易级别」导出")
    index = {name: header.index(name) for name in REQUIRED_HEADERS}
    lines, excluded, source_rows = [], defaultdict(int), 0
    pay_times = []
    for values in rows:
        if not values or all(v in (None, "") for v in values):
            continue
        source_rows += 1
        get = lambda name: values[index[name]] if index[name] < len(values) else None  # noqa: E731
        if str(get("平台") or "").strip().lower() != "ebay":
            excluded[f"非 eBay 平台（{str(get('平台') or '空').strip()}）"] += 1
            continue
        sku = str(get("库存SKU") or "").strip().upper()
        if not sku:
            excluded["库存SKU 为空"] += 1
            continue
        brand, mid = friday.brand_mid(sku)
        if brand == "JMH" and mid:
            brand = brands.get(mid, brand)
        pay_time = _datetime(get("付款时间"))
        if pay_time:
            pay_times.append(pay_time)
        lines.append({
            "row_no": len(lines) + 1,
            "order_no": str(get("平台订单号") or "").strip(),
            "ship_status": str(get("发货状态") or "").strip() or None,
            "pay_time": pay_time,
            "currency": str(get("币种") or "").strip().upper() or None,
            "order_rate": _decimal(get("汇率")),
            "income": _decimal(get("收入")),
            "quantity": int(_decimal(get("购买数量")) or 0),
            "stock_sku": sku, "brand": brand, "mid_code": mid, "site": currency_site(get("币种")),
        })
    workbook.close()
    if not lines:
        raise ValueError("文件里没有 eBay 平台且有库存SKU 的订单行")
    stats = {"source_rows": source_rows, "used_rows": len(lines), "excluded": dict(excluded),
             "pay_time_from": min(pay_times) if pay_times else None, "pay_time_to": max(pay_times) if pay_times else None}
    return lines, stats


def import_orders(content: bytes, filename: str, operator: str | None) -> dict[str, Any]:
    if len(content) > MAX_FILE_BYTES:
        raise ValueError("订单文件不能超过20MB")
    brands = friday.mid_brand_map(friday.repo.brand_sku_sources())
    lines, stats = parse(content, brands)
    with db_connection() as connection:
        connection.begin()
        try:
            with connection.cursor() as cursor:
                cursor.execute(f"DELETE FROM `{LINE_TABLE}`")
                cursor.execute(f"DELETE FROM `{UPLOAD_TABLE}`")
                sql = f"INSERT INTO `{LINE_TABLE}` ({','.join(LINE_COLUMNS)}) VALUES ({','.join(['%s'] * len(LINE_COLUMNS))})"
                values = [tuple(line[c] for c in LINE_COLUMNS) for line in lines]
                for offset in range(0, len(values), 1000):
                    cursor.executemany(sql, values[offset:offset + 1000])
                cursor.execute(
                    f"INSERT INTO `{UPLOAD_TABLE}` (id,file_name,uploaded_by,uploaded_at,pay_time_from,pay_time_to,"
                    "source_rows,used_rows,excluded_json) VALUES (1,%s,%s,%s,%s,%s,%s,%s,%s)",
                    (str(filename or "订单导出.xlsx")[:255], operator, datetime.now(friday.CHINA).replace(tzinfo=None),
                     stats["pay_time_from"], stats["pay_time_to"], stats["source_rows"], stats["used_rows"],
                     json.dumps(stats["excluded"], ensure_ascii=False)))
            connection.commit()
        except Exception:
            connection.rollback()
            raise
    LOG.info("eBay周五数据订单售出上传 file=%s rows=%s used=%s", filename, stats["source_rows"], stats["used_rows"])
    return {"file_name": filename, "source_rows": stats["source_rows"], "used_rows": stats["used_rows"],
            "excluded": stats["excluded"]}


# ------------------------------------------------------------------ 透视


def usd_rates() -> dict[str, Decimal]:
    with db_connection() as connection, connection.cursor() as cursor:
        cursor.execute("SELECT rate_month,rate_org FROM dim_lingxing_currency_month "
                       "WHERE currency_code='USD' AND rate_org>0 ORDER BY rate_month")
        return {str(row["rate_month"]): Decimal(str(row["rate_org"])) for row in cursor.fetchall()}


def rate_for(month: str, rates: dict[str, Decimal]) -> tuple[str, Decimal] | None:
    """付款月份的美元汇率；当月未出时回退到不晚于该月的最近已出月份。"""
    candidates = [m for m in rates if m <= month]
    if not candidates:
        return None
    chosen = max(candidates)
    return chosen, rates[chosen]


def pivot(lines: list[dict[str, Any]], owner_rules, rates: dict[str, Decimal]) -> dict[str, Any]:
    rules = _ebay_rule_map(owner_rules)
    groups: dict[str, dict[str, Any]] = defaultdict(lambda: {"keys": set(), "usd": Decimal(0), "qty": 0, "lines": 0})
    all_keys, used_months, missing_rate = set(), {}, 0
    for line in lines:
        sku = line["stock_sku"]
        if line.get("brand") and sku.startswith("JMH") and line["brand"] != "JMH":
            sku = sku.replace("JMH", line["brand"], 1)
        principal = _ebay_assignment(sku, rules)[0] or UNASSIGNED
        month = (line["pay_time"] or datetime.now()).strftime("%Y-%m")
        found = rate_for(month, rates)
        group = groups[principal]
        key = f"{line.get('mid_code') or ''}{line.get('site') or ''}"
        group["keys"].add(key)
        all_keys.add(key)
        group["qty"] += int(line.get("quantity") or 0)
        group["lines"] += 1
        income, order_rate = line.get("income"), line.get("order_rate")
        if found is None:
            missing_rate += 1
        elif income is not None and order_rate is not None:
            used_months[month] = found
            group["usd"] += Decimal(str(income)) * Decimal(str(order_rate)) / found[1]
    rows = [{"principal_name": name, "distinct_mid_site": len(g["keys"]), "usd_income": str(g["usd"].quantize(Decimal("0.01"))),
             "quantity": g["qty"], "order_lines": g["lines"]}
            for name, g in sorted(groups.items(), key=lambda item: (item[0] == UNASSIGNED, item[0]))]
    total = {"principal_name": "总计", "distinct_mid_site": len(all_keys),
             "usd_income": str(sum((g["usd"] for g in groups.values()), Decimal(0)).quantize(Decimal("0.01"))),
             "quantity": sum(r["quantity"] for r in rows), "order_lines": sum(r["order_lines"] for r in rows)}
    return {"rows": rows, "total": total, "missing_rate_lines": missing_rate,
            "usd_rate_months": {m: {"rate_month": v[0], "rate": str(v[1])} for m, v in sorted(used_months.items())}}


def _load():
    with db_connection() as connection, connection.cursor() as cursor:
        cursor.execute(f"SELECT * FROM `{UPLOAD_TABLE}` WHERE id=1")
        upload = cursor.fetchone()
        if not upload:
            return None, []
        cursor.execute(f"SELECT * FROM `{LINE_TABLE}` ORDER BY row_no")
        return upload, list(cursor.fetchall())


def summary() -> dict[str, Any]:
    try:
        upload, lines = _load()
    except Exception as exc:
        if friday.repo.missing_table(exc) or (getattr(exc, "args", None) and exc.args[0] == 1146):
            raise ValueError(MIGRATION_MESSAGE) from exc
        raise
    if not upload:
        return {"upload": None, "rows": [], "total": None}
    month = reference_today().strftime("%Y-%m")
    result = pivot(lines, friday.repo.ebay_owner_rules(month), usd_rates())
    excluded = upload.get("excluded_json")
    meta = {
        "file_name": upload["file_name"], "uploaded_by": upload.get("uploaded_by"),
        "uploaded_at": str(upload["uploaded_at"]),
        "pay_time_from": str(upload["pay_time_from"]) if upload.get("pay_time_from") else None,
        "pay_time_to": str(upload["pay_time_to"]) if upload.get("pay_time_to") else None,
        "source_rows": upload["source_rows"], "used_rows": upload["used_rows"],
        "excluded": json.loads(excluded) if isinstance(excluded, (str, bytes)) else (excluded or {}),
        "owner_rule_month": month,
    }
    return {"upload": meta, **result}
