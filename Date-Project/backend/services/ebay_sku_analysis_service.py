from __future__ import annotations

import json
import re
from datetime import datetime
from decimal import Decimal
from io import BytesIO
from pathlib import Path
from uuid import uuid4

import pandas as pd

from backend.database import db_connection

REQUIRED_COLUMNS = {
    "平台订单号", "付款时间", "平台", "币种", "应收货款(订单级别)",
    "应收运费", "平台费用", "客户ID", "收件人国家", "库存SKU",
    "购买数量", "销售员", "汇率", "国家中文", "国家英文", "发货状态",
}
MONTH_PATTERN = re.compile(r"^20\d{2}-(0[1-9]|1[0-2])$")


def import_orders(content: bytes, file_name: str, operator: str | None = None) -> dict:
    _ensure_tables()
    batch_id = str(uuid4())
    workbook = pd.ExcelFile(BytesIO(content))
    sheet = "Worksheet" if "Worksheet" in workbook.sheet_names else workbook.sheet_names[0]
    frame = pd.read_excel(workbook, sheet_name=sheet, dtype=object)
    missing = REQUIRED_COLUMNS - {str(value).strip() for value in frame.columns}
    if missing:
        raise ValueError(f"数字酋长订单文件缺少列: {', '.join(sorted(missing))}")
    frame = frame.copy()
    frame["_source_row"] = range(2, len(frame) + 2)
    frame["_payment_time"] = pd.to_datetime(frame["付款时间"], errors="coerce")
    frame["_sku"] = frame["库存SKU"].map(_text).str.upper()
    frame["_order_no"] = frame["平台订单号"].map(_text)
    frame["_quantity"] = pd.to_numeric(frame["购买数量"], errors="coerce").fillna(0).clip(lower=0)
    frame["_goods"] = pd.to_numeric(frame["应收货款(订单级别)"], errors="coerce").fillna(0)
    frame["_shipping"] = pd.to_numeric(frame["应收运费"], errors="coerce").fillna(0)
    frame["_fee"] = pd.to_numeric(frame["平台费用"], errors="coerce").fillna(0)
    frame["_exchange"] = pd.to_numeric(frame["汇率"], errors="coerce").fillna(0)
    valid = frame[
        frame["_payment_time"].notna() & frame["_sku"].ne("") &
        frame["_order_no"].ne("") & frame["平台"].map(_text).str.lower().eq("ebay")
    ].copy()
    if valid.empty:
        raise ValueError("文件中没有有效的eBay付款订单数据")
    valid["_stat_month"] = valid["_payment_time"].dt.strftime("%Y-%m")
    valid["_payment_date"] = valid["_payment_time"].dt.date
    order_keys = ["_order_no", "_payment_date"]
    quantity_total = valid.groupby(order_keys)["_quantity"].transform("sum")
    row_count = valid.groupby(order_keys)["_order_no"].transform("count")
    valid["_weight"] = valid["_quantity"].where(quantity_total > 0, 1) / quantity_total.where(quantity_total > 0, row_count)
    order_goods = valid.groupby(order_keys)["_goods"].transform("max")
    order_shipping = valid.groupby(order_keys)["_shipping"].transform("max")
    order_fee = valid.groupby(order_keys)["_fee"].transform("max")
    order_exchange = valid.groupby(order_keys)["_exchange"].transform("max")
    valid["_paid_original"] = (order_goods + order_shipping) * valid["_weight"]
    valid["_shipping_original"] = order_shipping * valid["_weight"]
    valid["_fee_original"] = order_fee * valid["_weight"]
    valid["_paid_cny"] = valid["_paid_original"] * order_exchange
    valid["_shipping_cny"] = valid["_shipping_original"] * order_exchange
    valid["_fee_cny"] = valid["_fee_original"] * order_exchange
    refunded = valid["发货状态"].map(_text).str.contains("已退款", na=False)
    valid["_refund_quantity"] = valid["_quantity"].where(refunded, 0)
    valid["_refund_amount"] = valid["_paid_original"].where(refunded, 0)
    months = sorted(valid["_stat_month"].unique().tolist())
    rows = [_row(record, batch_id, file_name, sheet) for _, record in valid.iterrows()]
    with db_connection() as connection:
        with connection.cursor() as cursor:
            replacement_keys = sorted({(row["platform_order_no"], row["payment_time"].date()) for row in rows})
            for key_group in _chunks(replacement_keys, 500):
                placeholders = ",".join(["(%s,%s)"] * len(key_group))
                delete_params = [value for key in key_group for value in key]
                for table in ("ods_ebay_sku_analysis_order_raw", "dwd_ebay_sku_analysis_order"):
                    cursor.execute(
                        f"DELETE FROM {table} WHERE (platform_order_no,DATE(payment_time)) IN ({placeholders})",
                        delete_params)
            cursor.executemany(
                """INSERT INTO ods_ebay_sku_analysis_order_raw
                (import_batch_id,stat_month,source_file_name,source_sheet,source_row,platform_order_no,payment_time,
                 inventory_sku,purchase_quantity,paid_amount_cny,shipping_amount_cny,platform_fee_cny,currency_code,
                 exchange_rate,customer_id,site_code,site_name,country_name,seller_account,shipping_status,
                 paid_amount_original,shipping_amount_original,refund_quantity,refund_amount_original,raw_json)
                VALUES (%(import_batch_id)s,%(stat_month)s,%(source_file_name)s,%(source_sheet)s,%(source_row)s,
                 %(platform_order_no)s,%(payment_time)s,%(inventory_sku)s,%(purchase_quantity)s,%(paid_amount_cny)s,
                 %(shipping_amount_cny)s,%(platform_fee_cny)s,%(currency_code)s,%(exchange_rate)s,%(customer_id)s,
                 %(site_code)s,%(site_name)s,%(country_name)s,%(seller_account)s,%(shipping_status)s,
                 %(paid_amount_original)s,%(shipping_amount_original)s,%(refund_quantity)s,%(refund_amount_original)s,
                 %(raw_json)s)""", rows)
            cursor.executemany(
                """INSERT INTO dwd_ebay_sku_analysis_order
                (stat_month,payment_time,platform_order_no,inventory_sku,purchase_quantity,paid_amount_cny,
                 shipping_amount_cny,platform_fee_cny,paid_amount_original,shipping_amount_original,
                 refund_quantity,refund_amount_original,shipping_status,currency_code,customer_id,site_code,
                 site_name,country_name,seller_account,import_batch_id,source_row)
                VALUES (%(stat_month)s,%(payment_time)s,%(platform_order_no)s,%(inventory_sku)s,%(purchase_quantity)s,
                 %(paid_amount_cny)s,%(shipping_amount_cny)s,%(platform_fee_cny)s,%(paid_amount_original)s,
                 %(shipping_amount_original)s,%(refund_quantity)s,%(refund_amount_original)s,%(shipping_status)s,
                 %(currency_code)s,%(customer_id)s,%(site_code)s,%(site_name)s,%(country_name)s,%(seller_account)s,
                 %(import_batch_id)s,%(source_row)s)""", rows)
            cursor.execute(
                """INSERT INTO ebay_sku_analysis_import_batch
                (import_batch_id,source_file_name,imported_months,total_rows,valid_rows,skipped_rows,operator_name,status,complete_time)
                VALUES (%s,%s,%s,%s,%s,%s,%s,'COMPLETED',NOW())""",
                (batch_id, file_name, ",".join(months), len(frame), len(rows), len(frame)-len(rows), operator))
        connection.commit()
    return {"import_batch_id": batch_id, "months": months, "total_rows": len(frame),
            "valid_rows": len(rows), "skipped_rows": len(frame)-len(rows),
            "replaced_order_count": len(replacement_keys)}


def date_bounds() -> dict:
    _ensure_tables()
    with db_connection() as connection, connection.cursor() as cursor:
        cursor.execute("SELECT MIN(DATE(payment_time)) min_date,MAX(DATE(payment_time)) max_date FROM dwd_ebay_sku_analysis_order")
        row = cursor.fetchone() or {}
        return {"min_date": str(row.get("min_date") or ""), "max_date": str(row.get("max_date") or "")}


def list_summary(start_date: str | None, end_date: str | None, sku: str | None,
                 site: str | None, chart_metric: str | None, chart_order: str | None,
                 page: int, page_size: int) -> dict:
    _ensure_tables()
    bounds = date_bounds()
    if not bounds["min_date"]:
        return {"items": [], "chart": [], "summary": _empty_summary(), "pagination": {"page": 1, "page_size": page_size, "total": 0}, "date_bounds": bounds}
    start = start_date or bounds["min_date"]
    end = end_date or bounds["max_date"]
    try:
        start_value = datetime.strptime(start, "%Y-%m-%d").date()
        end_value = datetime.strptime(end, "%Y-%m-%d").date()
    except ValueError as exc:
        raise ValueError("日期必须为YYYY-MM-DD格式") from exc
    if start_value > end_value:
        raise ValueError("开始日期不能晚于结束日期")
    clauses = ["DATE(o.payment_time) BETWEEN %s AND %s"]
    params: list[object] = [start_value, end_value]
    if sku:
        clauses.append("o.inventory_sku LIKE %s"); params.append(f"%{sku.strip().upper()}%")
    if site:
        clauses.append("o.site_name=%s"); params.append(site)
    where = " AND ".join(clauses)
    listing = """SELECT site_name,UPPER(msku) inventory_sku,
        SUBSTRING_INDEX(GROUP_CONCAT(picture_url ORDER BY listing_start_time DESC,id DESC SEPARATOR '|||'),'|||',1) picture_url,
        MIN(listing_start_time) listing_start_time,MAX(listing_start_time) latest_listing_start_time
        FROM jmh_data_platform.ebay_product_listing
        WHERE listing_status_name='在售' AND msku IS NOT NULL AND msku<>''
        GROUP BY site_name,UPPER(msku)"""
    grouped = f"""SELECT o.inventory_sku,o.site_name,l.picture_url,
        l.listing_start_time,l.latest_listing_start_time,
        ROUND(SUM(o.paid_amount_cny)-SUM(CASE WHEN o.shipping_status LIKE '%%已退款%%' THEN o.paid_amount_cny ELSE 0 END),2) paid_amount,ROUND(SUM(o.purchase_quantity),0) sold_quantity,
        COUNT(DISTINCT o.platform_order_no) paid_order_count,COUNT(DISTINCT o.customer_id) buyer_count,
        ROUND((SUM(o.paid_amount_cny)-SUM(CASE WHEN o.shipping_status LIKE '%%已退款%%' THEN o.paid_amount_cny ELSE 0 END))/NULLIF(COUNT(DISTINCT o.customer_id),0),2) average_order_value,
        ROUND(SUM(o.refund_quantity),0) refund_count,
        ROUND(SUM(CASE WHEN o.shipping_status LIKE '%%已退款%%' THEN o.paid_amount_cny ELSE 0 END),2) refund_amount,
        ROUND(SUM(o.refund_quantity)/NULLIF(SUM(o.purchase_quantity),0),6) return_rate,
        ROUND(SUM(o.shipping_amount_cny),2) shipping_amount,'CNY' currency_code
        FROM dwd_ebay_sku_analysis_order o LEFT JOIN ({listing}) l
          ON l.site_name=o.site_name AND l.inventory_sku=o.inventory_sku
        WHERE {where}
        GROUP BY o.inventory_sku,o.site_name,l.picture_url,l.listing_start_time,l.latest_listing_start_time"""
    chart_columns = {
        "paid_amount": "paid_amount", "sold_quantity": "sold_quantity",
        "paid_order_count": "paid_order_count", "average_order_value": "average_order_value",
        "buyer_count": "buyer_count", "refund_count": "refund_count",
        "refund_amount": "refund_amount", "return_rate": "return_rate", "shipping_amount": "shipping_amount",
    }
    chart_column = chart_columns.get(chart_metric or "paid_amount", "paid_amount")
    chart_direction = "ASC" if (chart_order or "desc").lower() == "asc" else "DESC"
    page = max(page, 1); page_size = min(max(page_size, 1), 200)
    with db_connection() as connection, connection.cursor() as cursor:
        cursor.execute(f"SELECT COUNT(*) total FROM ({grouped}) x", params); total = int(cursor.fetchone()["total"])
        cursor.execute(grouped + " ORDER BY paid_amount DESC,inventory_sku LIMIT %s OFFSET %s", params + [page_size, (page-1)*page_size])
        items = [_json_row(row) for row in cursor.fetchall()]
        cursor.execute(grouped + f" ORDER BY {chart_column} {chart_direction},inventory_sku ASC LIMIT 20", params); chart = [_json_row(row) for row in cursor.fetchall()]
        cursor.execute(f"""SELECT ROUND(SUM(o.paid_amount_cny)-SUM(CASE WHEN o.shipping_status LIKE '%%已退款%%' THEN o.paid_amount_cny ELSE 0 END),2) paid_amount,ROUND(SUM(o.purchase_quantity),0) sold_quantity,
            COUNT(DISTINCT o.platform_order_no) paid_order_count,COUNT(DISTINCT o.inventory_sku) sku_count,
            COUNT(DISTINCT o.customer_id) buyer_count,ROUND(SUM(o.shipping_amount_cny),2) shipping_amount,
            ROUND(SUM(o.refund_quantity),0) refund_count,
            ROUND(SUM(CASE WHEN o.shipping_status LIKE '%%已退款%%' THEN o.paid_amount_cny ELSE 0 END),2) refund_amount,
            ROUND(SUM(o.refund_quantity)/NULLIF(SUM(o.purchase_quantity),0),6) return_rate
            FROM dwd_ebay_sku_analysis_order o WHERE {where}""", params)
        summary = _json_row(cursor.fetchone())
        cursor.execute("SELECT DISTINCT site_name FROM dwd_ebay_sku_analysis_order ORDER BY site_name")
        sites = [row["site_name"] for row in cursor.fetchall()]
    return {"items": items, "chart": chart, "summary": summary, "sites": sites,
            "date_bounds": bounds, "start_date": start, "end_date": end,
            "pagination": {"page": page, "page_size": page_size, "total": total}}

def _row(record, batch_id, file_name, sheet):
    country_en = _text(record.get("国家英文"))
    country_cn = _text(record.get("国家中文")) or _text(record.get("收件人国家"))
    raw = {str(key): _json_value(value) for key, value in record.items() if not str(key).startswith("_")}
    return {"import_batch_id": batch_id, "stat_month": record["_stat_month"], "source_file_name": file_name,
            "source_sheet": sheet, "source_row": int(record["_source_row"]), "platform_order_no": record["_order_no"],
            "payment_time": record["_payment_time"].to_pydatetime(), "inventory_sku": record["_sku"],
            "purchase_quantity": _decimal(record["_quantity"]), "paid_amount_cny": _decimal(record["_paid_cny"]),
            "shipping_amount_cny": _decimal(record["_shipping_cny"]), "platform_fee_cny": _decimal(record["_fee_cny"]),
            "paid_amount_original": _decimal(record["_paid_original"]), "shipping_amount_original": _decimal(record["_shipping_original"]),
            "refund_quantity": _decimal(record["_refund_quantity"]), "refund_amount_original": _decimal(record["_refund_amount"]),
            "shipping_status": _text(record.get("发货状态")), "currency_code": _text(record.get("币种")),
            "exchange_rate": _decimal(record["_exchange"]), "customer_id": _text(record.get("客户ID")) or None,
            "site_code": _site(country_en), "site_name": _site_name(country_cn, record.get("币种")),
            "country_name": country_cn or None, "seller_account": _text(record.get("销售员")) or "未提供账号",
            "raw_json": json.dumps(raw, ensure_ascii=False)}


def _ensure_tables():
    path = Path(__file__).parents[2] / "migrations" / "20260825_ebay_sku_analysis_tables.sql"
    statements = [item.strip() for item in path.read_text(encoding="utf-8").split(";") if item.strip()]
    missing_columns = {
        "ods_ebay_sku_analysis_order_raw": {
            "site_name": "VARCHAR(100) NOT NULL DEFAULT '其他' COMMENT '中文站点名称' AFTER site_code",
            "shipping_status": "VARCHAR(64) DEFAULT NULL COMMENT '发货状态' AFTER seller_account",
            "paid_amount_original": "DECIMAL(20,6) NOT NULL DEFAULT 0 COMMENT '已支付金额原币' AFTER shipping_status",
            "shipping_amount_original": "DECIMAL(20,6) NOT NULL DEFAULT 0 COMMENT '应收运费原币' AFTER paid_amount_original",
            "refund_quantity": "DECIMAL(18,4) NOT NULL DEFAULT 0 COMMENT '已退款购买数量' AFTER shipping_amount_original",
            "refund_amount_original": "DECIMAL(20,6) NOT NULL DEFAULT 0 COMMENT '退款金额原币' AFTER refund_quantity",
        },
        "dwd_ebay_sku_analysis_order": {
            "paid_amount_original": "DECIMAL(20,6) NOT NULL DEFAULT 0 COMMENT '已支付金额原币' AFTER platform_fee_cny",
            "shipping_amount_original": "DECIMAL(20,6) NOT NULL DEFAULT 0 COMMENT '应收运费原币' AFTER paid_amount_original",
            "refund_quantity": "DECIMAL(18,4) NOT NULL DEFAULT 0 COMMENT '已退款购买数量' AFTER shipping_amount_original",
            "refund_amount_original": "DECIMAL(20,6) NOT NULL DEFAULT 0 COMMENT '退款金额原币' AFTER refund_quantity",
            "shipping_status": "VARCHAR(64) DEFAULT NULL COMMENT '发货状态' AFTER refund_amount_original",
            "currency_code": "VARCHAR(16) DEFAULT NULL COMMENT '币种' AFTER shipping_status",
            "site_name": "VARCHAR(100) NOT NULL DEFAULT '其他' COMMENT '中文站点名称' AFTER site_code",
        },
    }
    with db_connection() as connection, connection.cursor() as cursor:
        for statement in statements:
            cursor.execute(statement)
        for table_name, columns in missing_columns.items():
            cursor.execute(f"SHOW COLUMNS FROM `{table_name}`")
            existing = {row["Field"] for row in cursor.fetchall()}
            for column_name, definition in columns.items():
                if column_name not in existing:
                    cursor.execute(f"ALTER TABLE `{table_name}` ADD COLUMN `{column_name}` {definition}")
        connection.commit()


def _site_name(country: str, currency) -> str:
    value = country.strip()
    if value in {"美国", "英国", "德国", "法国"}: return value
    return {"USD": "美国", "GBP": "英国", "EUR": "德国"}.get(_text(currency).upper(), value or "其他")


def _site(country: str) -> str:
    value = country.lower()
    if value == "united states": return "US"
    if value == "united kingdom": return "UK"
    if value == "germany": return "DE"
    return "OTHER"


def _text(value) -> str:
    return "" if value is None or pd.isna(value) else str(value).strip()


def _decimal(value) -> Decimal:
    return Decimal(str(0 if value is None or pd.isna(value) else value)).quantize(Decimal("0.000001"))


def _json_value(value):
    if value is None or pd.isna(value): return None
    if isinstance(value, (datetime, pd.Timestamp)): return value.isoformat()
    return value.item() if hasattr(value, "item") else value


def _json_row(row):
    return {key: (value.isoformat(sep=" ") if isinstance(value, datetime) else str(value) if isinstance(value, Decimal) else value)
            for key, value in (row or {}).items()}


def _empty_summary():
    return {"paid_amount": "0", "sold_quantity": "0", "paid_order_count": 0, "sku_count": 0, "buyer_count": 0, "shipping_amount": "0"}


def _chunks(values, size: int):
    for index in range(0, len(values), size):
        yield values[index:index + size]
