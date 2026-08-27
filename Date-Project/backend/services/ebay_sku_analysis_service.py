from __future__ import annotations

import re
from datetime import datetime
from decimal import Decimal
from io import BytesIO
from pathlib import Path
from threading import Lock
from uuid import uuid4

import pandas as pd

from backend.database import db_connection

SOURCE_COLUMN_MAP = {
    "国家中文": "country_name",
    "平台订单号": "platform_order_no",
    "发货状态": "shipping_status",
    "下单时间": "order_time",
    "付款时间": "payment_time",
    "退款时间": "refund_time",
    "币种": "currency_code",
    "应收货款(订单级别)": "goods_receivable_original",
    "应收运费": "shipping_receivable_original",
    "税费($)": "tax_usd",
    "平台费用": "platform_fee_original",
    "平台产品单价": "platform_product_unit_price",
    "产品单价": "product_unit_price",
    "退款金额": "source_refund_amount",
    "税费(￥)": "tax_cny",
    "广告费(￥)": "advertising_fee_cny",
    "实际尾程运费(￥)": "last_mile_shipping_cny",
    "平台费用明细": "platform_fee_detail",
    "头程运费(￥)": "first_mile_shipping_cny",
    "采购成本(¥)": "purchase_cost_cny",
    "汇率": "exchange_rate",
    "客户ID": "customer_id",
    "图片链接": "picture_url",
    "产品名称(中)": "product_name_cn",
    "平台SKU": "platform_sku",
    "库存SKU": "inventory_sku",
    "SKU状态": "sku_status",
    "Listing链接": "listing_url",
    "可用库存": "available_inventory",
    "订单利润(￥)": "order_profit_cny",
    "订单总金额": "order_total_amount_original",
    "购买数量": "purchase_quantity",
    "平台SKU数量": "platform_sku_quantity",
    "订单备注": "order_remark",
}
CNY_SOURCE_COLUMN_MAP = {
    "goods_receivable_cny": "应收货款(订单级别)",
    "shipping_receivable_cny": "应收运费",
    "tax_usd_cny": "税费($)",
    "platform_product_unit_price_cny": "平台产品单价",
    "product_unit_price_cny": "产品单价",
    "source_refund_amount_cny": "退款金额",
}
PROFIT_SOURCE_COLUMN_MAP = {
    "账号": "account_name",
    "站点": "source_site_name",
    "订单号": "platform_order_no",
    "Listing ID": "listing_id",
    "图片": "picture_url",
    "SKU": "source_sku",
    "平台SKU": "platform_sku",
    "库存SKU": "inventory_sku",
    "数量": "quantity",
    "单价": "unit_price_cny",
    "产品名称": "product_name",
    "产品名称.1": "product_name_secondary",
    "成本": "cost_cny",
    "订单金额": "order_amount_cny",
    "售出数": "sold_quantity",
    "订单数": "order_count",
    "税费": "tax_cny",
    "下单时间": "order_time",
    "付款时间": "payment_time",
    "退款时间": "refund_time",
    "状态": "order_status",
    "财务状态": "financial_status",
    "利润": "profit_cny",
    "利润率": "source_profit_rate",
    "商品销售额": "product_sales_amount_cny",
    "应收运费": "shipping_receivable_cny",
    "平台费用": "platform_fee_cny",
    "采购成本": "purchase_cost_cny",
    "头程运费": "first_mile_shipping_cny",
    "海关税费": "customs_tax_cny",
    "尾程运费": "last_mile_shipping_cny",
    "退款金额": "refund_amount_cny",
    "广告费": "advertising_fee_cny",
    "平台其他费": "other_platform_fee_cny",
    "退款金额(下单时间)": "refund_amount_by_order_time_cny",
    "采购成本(手动)": "manual_purchase_cost_cny",
    "头程成本": "first_mile_cost_cny",
}
PROFIT_REQUIRED_COLUMNS = set(PROFIT_SOURCE_COLUMN_MAP)
PROFIT_DATETIME_SOURCE_FIELDS = {"order_time", "payment_time", "refund_time"}
PROFIT_DECIMAL_SOURCE_FIELDS = {
    "quantity", "unit_price_cny", "cost_cny", "order_amount_cny", "sold_quantity",
    "order_count", "tax_cny", "profit_cny", "source_profit_rate", "product_sales_amount_cny",
    "shipping_receivable_cny", "platform_fee_cny", "purchase_cost_cny", "first_mile_shipping_cny",
    "customs_tax_cny", "last_mile_shipping_cny", "refund_amount_cny", "advertising_fee_cny",
    "other_platform_fee_cny", "refund_amount_by_order_time_cny", "manual_purchase_cost_cny",
    "first_mile_cost_cny",
}
REQUIRED_COLUMNS = set(SOURCE_COLUMN_MAP)
DATETIME_SOURCE_FIELDS = {"order_time", "payment_time", "refund_time"}
DECIMAL_SOURCE_FIELDS = {
    "goods_receivable_original", "shipping_receivable_original", "tax_usd",
    "platform_fee_original", "platform_product_unit_price", "product_unit_price",
    "source_refund_amount", "tax_cny", "advertising_fee_cny", "last_mile_shipping_cny",
    "first_mile_shipping_cny", "purchase_cost_cny", "exchange_rate", "available_inventory",
    "order_profit_cny", "order_total_amount_original", "purchase_quantity", "platform_sku_quantity",
}
MONTH_PATTERN = re.compile(r"^20\d{2}-(0[1-9]|1[0-2])$")
_TABLES_READY = False
_TABLES_LOCK = Lock()


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
    inventory_sku = frame["库存SKU"].map(_text).str.upper()
    platform_sku = frame["平台SKU"].map(_text).str.upper()
    frame["_sku"] = inventory_sku.where(inventory_sku.ne(""), platform_sku)
    frame["_platform_sku"] = platform_sku.where(platform_sku.ne(""), frame["_sku"])
    frame["_order_no"] = frame["平台订单号"].map(_text)
    frame["_quantity"] = pd.to_numeric(frame["购买数量"], errors="coerce").fillna(0).clip(lower=0)
    frame["_goods"] = pd.to_numeric(frame["应收货款(订单级别)"], errors="coerce").fillna(0)
    frame["_shipping"] = pd.to_numeric(frame["应收运费"], errors="coerce").fillna(0)
    frame["_fee"] = pd.to_numeric(frame["平台费用"], errors="coerce").fillna(0)
    frame["_refund"] = pd.to_numeric(frame["退款金额"], errors="coerce").fillna(0)
    frame["_exchange"] = pd.to_numeric(frame["汇率"], errors="coerce").fillna(0)
    replaceable = frame[
        frame["_payment_time"].notna() & frame["_sku"].ne("") &
        frame["_order_no"].ne("")
    ].copy()
    valid = replaceable[~replaceable["_sku"].str.startswith("AMZ", na=False)].copy()
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
    order_refund = valid.groupby(order_keys)["_refund"].transform("max")
    order_exchange = valid.groupby(order_keys)["_exchange"].transform("max")
    valid["_paid_original"] = (order_goods + order_shipping) * valid["_weight"]
    valid["_shipping_original"] = order_shipping * valid["_weight"]
    valid["_fee_original"] = order_fee * valid["_weight"]
    valid["_paid_cny"] = valid["_paid_original"] * order_exchange
    valid["_shipping_cny"] = valid["_shipping_original"] * order_exchange
    valid["_fee_cny"] = valid["_fee_original"] * order_exchange
    shipping_status = valid["发货状态"].map(_text)
    refunded = shipping_status.str.contains("已退款", na=False)
    returned_or_voided = shipping_status.str.contains("已退款|已作废", regex=True, na=False)
    valid["_refund_quantity"] = valid["_quantity"].where(returned_or_voided, 0)
    valid["_refunded_quantity"] = valid["_quantity"].where(refunded, 0)
    refund_quantity_total = valid.groupby(order_keys)["_refunded_quantity"].transform("sum")
    valid["_refund_marker"] = refunded.astype(int)
    refund_row_count = valid.groupby(order_keys)["_refund_marker"].transform("sum")
    valid["_refund_weight"] = 0.0
    quantity_mask = refunded & refund_quantity_total.gt(0)
    valid.loc[quantity_mask, "_refund_weight"] = (
        valid.loc[quantity_mask, "_refunded_quantity"] / refund_quantity_total.loc[quantity_mask]
    )
    row_mask = refunded & ~refund_quantity_total.gt(0) & refund_row_count.gt(0)
    valid.loc[row_mask, "_refund_weight"] = 1 / refund_row_count.loc[row_mask]
    valid["_refund_amount"] = order_refund * valid["_refund_weight"]
    valid["_refund_cny"] = valid["_refund_amount"] * order_exchange
    months = sorted(valid["_stat_month"].unique().tolist())
    rows = [_row(record, batch_id, file_name, sheet) for _, record in valid.iterrows()]
    replacement_keys = sorted({
        (record["_order_no"], record["_payment_time"].date())
        for _, record in replaceable.iterrows()
    })
    ods_columns = [
        "import_batch_id", "stat_month", "source_file_name", "source_sheet", "source_row",
        *SOURCE_COLUMN_MAP.values(), *CNY_SOURCE_COLUMN_MAP.keys(),
    ]
    ods_column_sql = ",".join(ods_columns)
    ods_value_sql = ",".join(f"%({column})s" for column in ods_columns)
    with db_connection() as connection:
        with connection.cursor() as cursor:
            for key_group in _chunks(replacement_keys, 500):
                placeholders = ",".join(["(%s,%s)"] * len(key_group))
                delete_params = [value for key in key_group for value in key]
                for table in ("ods_ebay_sku_analysis_order_raw", "dwd_ebay_sku_analysis_order"):
                    cursor.execute(
                        f"DELETE FROM {table} WHERE (platform_order_no,DATE(payment_time)) IN ({placeholders})",
                        delete_params)
            cursor.executemany(
                f"INSERT INTO ods_ebay_sku_analysis_order_raw "
                f"({ods_column_sql}) VALUES ({ods_value_sql})",
                rows,
            )
            cursor.executemany(
                """INSERT INTO dwd_ebay_sku_analysis_order
                (stat_month,payment_time,platform_order_no,inventory_sku,purchase_quantity,paid_amount_cny,
                 shipping_amount_cny,platform_fee_cny,paid_amount_original,shipping_amount_original,
                 refund_quantity,refund_amount_original,refund_amount_cny,shipping_status,currency_code,customer_id,site_code,
                 site_name,country_name,picture_url,product_name_cn,listing_url,import_batch_id,source_row)
                VALUES (%(stat_month)s,%(payment_time)s,%(platform_order_no)s,%(inventory_sku)s,%(purchase_quantity)s,
                 %(paid_amount_cny)s,%(shipping_amount_cny)s,%(platform_fee_cny)s,%(paid_amount_original)s,
                 %(shipping_amount_original)s,%(refund_quantity)s,%(refund_amount_original)s,%(refund_amount_cny)s,
                 %(shipping_status)s,
                 %(currency_code)s,%(customer_id)s,%(site_code)s,%(site_name)s,%(country_name)s,
                 %(picture_url)s,%(product_name_cn)s,%(listing_url)s,%(import_batch_id)s,%(source_row)s)""", rows)
            _rebuild_profit_daily(cursor, sorted({record["_payment_time"].date() for _, record in valid.iterrows()}))
            cursor.execute(
                """INSERT INTO ebay_sku_analysis_import_batch
                (import_batch_id,source_file_name,imported_months,total_rows,valid_rows,skipped_rows,operator_name,status,complete_time)
                VALUES (%s,%s,%s,%s,%s,%s,%s,'COMPLETED',NOW())""",
                (batch_id, file_name, ",".join(months), len(frame), len(rows), len(frame)-len(rows), operator))
        connection.commit()
    return {"import_batch_id": batch_id, "months": months, "total_rows": len(frame),
            "valid_rows": len(rows), "skipped_rows": len(frame)-len(rows),
            "replaced_order_count": len(replacement_keys)}


def import_profit_orders(content: bytes, file_name: str, operator: str | None = None) -> dict:
    _ensure_tables()
    batch_id = str(uuid4())
    workbook = pd.ExcelFile(BytesIO(content))
    sheet = workbook.sheet_names[0]
    frame = pd.read_excel(workbook, sheet_name=sheet, dtype=object)
    missing = PROFIT_REQUIRED_COLUMNS - {str(value).strip() for value in frame.columns}
    if missing:
        raise ValueError(f"订单利润表缺少列: {', '.join(sorted(missing))}")
    frame = frame.copy()
    frame["_source_row"] = range(2, len(frame) + 2)
    frame["_payment_time"] = pd.to_datetime(frame["付款时间"], errors="coerce")
    frame["_source_site"] = frame["站点"].map(_identifier)
    frame["_site_name"] = frame["_source_site"].map(_profit_site_name)
    inventory_sku = frame["库存SKU"].map(_identifier).str.upper()
    platform_sku = frame["平台SKU"].map(_identifier).str.upper()
    frame["_sku"] = inventory_sku.where(inventory_sku.ne(""), platform_sku)
    frame["_platform_sku"] = platform_sku.where(platform_sku.ne(""), frame["_sku"])
    frame["_order_no"] = frame["订单号"].map(_identifier)
    ebay_rows = frame[
        frame["_source_site"].str.startswith("eBay", na=False)
        & ~frame["_source_site"].str.contains("Walmart", case=False, na=False)
    ].copy()
    valid = ebay_rows[
        ebay_rows["_payment_time"].notna()
        & ebay_rows["_order_no"].ne("")
        & ebay_rows["_sku"].ne("")
        & ~ebay_rows["_sku"].str.contains("AMZ", case=False, regex=False, na=False)
    ].copy()
    if valid.empty:
        raise ValueError("订单利润表中没有可匹配的eBay付款订单数据")
    valid["_stat_month"] = valid["_payment_time"].dt.strftime("%Y-%m")
    rows = [_profit_row(record, batch_id, file_name, sheet) for _, record in valid.iterrows()]
    replacement_keys = sorted({
        (record["_payment_time"].date(), record["_order_no"], record["_sku"])
        for _, record in valid.iterrows()
    })
    ods_columns = [
        "import_batch_id", "stat_month", "source_file_name", "source_sheet", "source_row",
        *PROFIT_SOURCE_COLUMN_MAP.values(), "site_name",
    ]
    with db_connection() as connection:
        with connection.cursor() as cursor:
            for key_group in _chunks(replacement_keys, 500):
                placeholders = ",".join(["(%s,%s,%s)"] * len(key_group))
                delete_params = [value for key in key_group for value in key]
                for table in ("ods_ebay_sku_analysis_profit_raw", "dwd_ebay_sku_analysis_profit"):
                    cursor.execute(
                        f"DELETE FROM {table} "
                        f"WHERE (DATE(payment_time),platform_order_no,inventory_sku) IN ({placeholders})",
                        delete_params,
                    )
            cursor.executemany(
                f"INSERT INTO ods_ebay_sku_analysis_profit_raw "
                f"({','.join(ods_columns)}) VALUES ({','.join(f'%({column})s' for column in ods_columns)})",
                rows,
            )
            cursor.executemany(
                """INSERT INTO dwd_ebay_sku_analysis_profit
                (stat_month,payment_date,payment_time,platform_order_no,inventory_sku,platform_sku,
                 source_site_name,site_name,profit_cny,product_sales_amount_cny,shipping_receivable_cny,
                 refund_amount_cny,net_revenue_cny,import_batch_id,source_row)
                VALUES (%(stat_month)s,%(payment_date)s,%(payment_time)s,%(platform_order_no)s,
                 %(inventory_sku)s,%(platform_sku)s,%(source_site_name)s,%(site_name)s,%(profit_cny)s,
                 %(product_sales_amount_cny)s,%(shipping_receivable_cny)s,%(refund_amount_cny)s,
                 %(net_revenue_cny)s,%(import_batch_id)s,%(source_row)s)""",
                rows,
            )
            _rebuild_profit_daily(cursor, sorted({record["_payment_time"].date() for _, record in valid.iterrows()}))
            cursor.execute(
                """INSERT INTO ebay_sku_analysis_profit_import_batch
                (import_batch_id,source_file_name,imported_months,total_rows,valid_rows,skipped_rows,
                 excluded_walmart_rows,excluded_amz_rows,operator_name,status,complete_time)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,'COMPLETED',NOW())""",
                (
                    batch_id, file_name, ",".join(sorted(valid["_stat_month"].unique().tolist())),
                    len(frame), len(rows), len(frame) - len(rows),
                    int(frame["_source_site"].str.contains("Walmart", case=False, na=False).sum()),
                    int(ebay_rows["_sku"].str.contains("AMZ", case=False, regex=False, na=False).sum()),
                    operator,
                ),
            )
        connection.commit()
    return {
        "import_batch_id": batch_id,
        "months": sorted(valid["_stat_month"].unique().tolist()),
        "total_rows": len(frame),
        "valid_rows": len(rows),
        "skipped_rows": len(frame) - len(rows),
        "excluded_walmart_rows": int(frame["_source_site"].str.contains("Walmart", case=False, na=False).sum()),
        "excluded_amz_rows": int(ebay_rows["_sku"].str.contains("AMZ", case=False, regex=False, na=False).sum()),
        "replaced_key_count": len(replacement_keys),
    }


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
    selected_days = (end_value - start_value).days + 1
    clauses = ["DATE(o.payment_time) BETWEEN %s AND %s"]
    params: list[object] = [start_value, end_value]
    if sku:
        clauses.append("o.inventory_sku LIKE %s"); params.append(f"%{sku.strip().upper()}%")
    if site:
        clauses.append("o.site_name=%s"); params.append(site)
    where = " AND ".join(clauses)
    profit_clauses = ["p.payment_date BETWEEN %s AND %s"]
    profit_params: list[object] = [start_value, end_value]
    if sku:
        profit_clauses.append("p.inventory_sku LIKE %s"); profit_params.append(f"%{sku.strip().upper()}%")
    if site:
        profit_clauses.append("p.site_name=%s"); profit_params.append(site)
    profit_where = " AND ".join(profit_clauses)
    latest_source = """SELECT site_name,inventory_sku,picture_url,product_name_cn,listing_url
        FROM (
          SELECT site_name,inventory_sku,picture_url,product_name_cn,listing_url,
            ROW_NUMBER() OVER (
              PARTITION BY inventory_sku
              ORDER BY payment_time DESC,id DESC
            ) latest_rank
          FROM dwd_ebay_sku_analysis_order
        ) ranked_source
        WHERE latest_rank=1"""
    listing = """SELECT site_name,UPPER(msku) inventory_sku,
        MIN(listing_start_time) listing_start_time,MAX(listing_start_time) latest_listing_start_time
        FROM jmh_data_platform.ebay_product_listing
        WHERE listing_status_name='在售' AND msku IS NOT NULL AND msku<>''
        GROUP BY site_name,UPPER(msku)"""
    velocity = """SELECT inventory_sku,
        ROUND(SUM(CASE WHEN payment_time>=DATE_SUB(CURDATE(),INTERVAL 7 DAY)
          AND payment_time<CURDATE() THEN purchase_quantity ELSE 0 END)/7,4) sales_velocity_7d,
        ROUND(SUM(CASE WHEN payment_time>=DATE_SUB(CURDATE(),INTERVAL 14 DAY)
          AND payment_time<CURDATE() THEN purchase_quantity ELSE 0 END)/14,4) sales_velocity_14d,
        ROUND(SUM(CASE WHEN payment_time>=DATE_SUB(CURDATE(),INTERVAL 30 DAY)
          AND payment_time<CURDATE() THEN purchase_quantity ELSE 0 END)/30,4) sales_velocity_30d
        FROM dwd_ebay_sku_analysis_order
        WHERE payment_time>=DATE_SUB(CURDATE(),INTERVAL 30 DAY)
          AND payment_time<CURDATE()
        GROUP BY inventory_sku"""
    profit_summary = f"""SELECT p.inventory_sku,SUM(p.profit_cny) profit_amount,
          SUM(p.net_revenue_cny) profit_base_amount
        FROM dws_ebay_sku_analysis_profit_daily p
        WHERE {profit_where}
        GROUP BY p.inventory_sku"""
    grouped = f"""SELECT o.inventory_sku,s.site_name,s.picture_url,s.product_name_cn,s.listing_url,
        l.listing_start_time,l.latest_listing_start_time,
        ROUND(SUM(o.paid_amount_cny)-SUM(CASE WHEN o.shipping_status LIKE '%%已退款%%' THEN o.refund_amount_cny ELSE 0 END),2) paid_amount,ROUND(SUM(o.purchase_quantity),0) sold_quantity,
        ROUND(SUM(o.purchase_quantity)/{selected_days},4) sales_velocity_total,
        COALESCE(v.sales_velocity_7d,0) sales_velocity_7d,
        COALESCE(v.sales_velocity_14d,0) sales_velocity_14d,
        COALESCE(v.sales_velocity_30d,0) sales_velocity_30d,
        COUNT(DISTINCT o.platform_order_no) paid_order_count,COUNT(DISTINCT o.customer_id) buyer_count,
        ROUND((SUM(o.paid_amount_cny)-SUM(CASE WHEN o.shipping_status LIKE '%%已退款%%' THEN o.refund_amount_cny ELSE 0 END))/NULLIF(COUNT(DISTINCT o.customer_id),0),2) average_order_value,
        ROUND(SUM(o.refund_quantity),0) refund_count,
        ROUND(SUM(CASE WHEN o.shipping_status LIKE '%%已退款%%' THEN o.refund_amount_cny ELSE 0 END),2) refund_amount,
        ROUND(SUM(o.refund_quantity)/NULLIF(SUM(o.purchase_quantity),0),6) return_rate,
        ROUND(SUM(o.shipping_amount_cny),2) shipping_amount,
        ROUND(COALESCE(p.profit_amount,0),2) profit_amount,
        ROUND(COALESCE(p.profit_amount,0)/NULLIF(p.profit_base_amount,0),6) profit_rate,'CNY' currency_code
        FROM dwd_ebay_sku_analysis_order o
        LEFT JOIN ({latest_source}) s
          ON s.inventory_sku=o.inventory_sku
        LEFT JOIN ({listing}) l
          ON l.site_name=s.site_name AND l.inventory_sku=o.inventory_sku
        LEFT JOIN ({velocity}) v
          ON v.inventory_sku=o.inventory_sku
        LEFT JOIN ({profit_summary}) p
          ON p.inventory_sku=o.inventory_sku
        WHERE {where}
        GROUP BY o.inventory_sku,s.site_name,s.picture_url,s.product_name_cn,s.listing_url,
          l.listing_start_time,l.latest_listing_start_time,
          v.sales_velocity_7d,v.sales_velocity_14d,v.sales_velocity_30d,
          p.profit_amount,p.profit_base_amount"""
    chart_columns = {
        "paid_amount": "paid_amount", "sold_quantity": "sold_quantity",
        "paid_order_count": "paid_order_count", "average_order_value": "average_order_value",
        "buyer_count": "buyer_count", "refund_count": "refund_count",
        "refund_amount": "refund_amount", "return_rate": "return_rate", "shipping_amount": "shipping_amount",
        "profit_amount": "profit_amount", "profit_rate": "profit_rate",
    }
    chart_column = chart_columns.get(chart_metric or "paid_amount", "paid_amount")
    chart_direction = "ASC" if (chart_order or "desc").lower() == "asc" else "DESC"
    page = max(page, 1); page_size = min(max(page_size, 1), 200)
    grouped_params = profit_params + params
    with db_connection() as connection, connection.cursor() as cursor:
        cursor.execute(f"SELECT COUNT(*) total FROM ({grouped}) x", grouped_params); total = int(cursor.fetchone()["total"])
        cursor.execute(grouped + " ORDER BY paid_amount DESC,inventory_sku LIMIT %s OFFSET %s", grouped_params + [page_size, (page-1)*page_size])
        items = [_json_row(row) for row in cursor.fetchall()]
        cursor.execute(grouped + f" ORDER BY {chart_column} {chart_direction},inventory_sku ASC LIMIT 20", grouped_params); chart = [_json_row(row) for row in cursor.fetchall()]
        cursor.execute(f"""SELECT ROUND(SUM(o.paid_amount_cny)-SUM(CASE WHEN o.shipping_status LIKE '%%已退款%%' THEN o.refund_amount_cny ELSE 0 END),2) paid_amount,ROUND(SUM(o.purchase_quantity),0) sold_quantity,
            COUNT(DISTINCT o.platform_order_no) paid_order_count,COUNT(DISTINCT o.inventory_sku) sku_count,
            COUNT(DISTINCT o.customer_id) buyer_count,ROUND(SUM(o.shipping_amount_cny),2) shipping_amount,
            ROUND(SUM(o.refund_quantity),0) refund_count,
            ROUND(SUM(CASE WHEN o.shipping_status LIKE '%%已退款%%' THEN o.refund_amount_cny ELSE 0 END),2) refund_amount,
            ROUND(SUM(o.refund_quantity)/NULLIF(SUM(o.purchase_quantity),0),6) return_rate
            FROM dwd_ebay_sku_analysis_order o WHERE {where}""", params)
        summary = _json_row(cursor.fetchone())
        cursor.execute("SELECT DISTINCT site_name FROM dwd_ebay_sku_analysis_order ORDER BY site_name")
        sites = [row["site_name"] for row in cursor.fetchall()]
    return {"items": items, "chart": chart, "summary": summary, "sites": sites,
            "date_bounds": bounds, "start_date": start, "end_date": end,
            "pagination": {"page": page, "page_size": page_size, "total": total}}

def _row(record, batch_id, file_name, sheet):
    country_cn = _text(record.get("国家中文")) or _text(record.get("收件人国家"))
    source = _source_fields(record)
    return {**source, "import_batch_id": batch_id, "stat_month": record["_stat_month"], "source_file_name": file_name,
            "source_sheet": sheet, "source_row": int(record["_source_row"]), "platform_order_no": record["_order_no"],
            "payment_time": record["_payment_time"].to_pydatetime(), "inventory_sku": record["_sku"],
            "platform_sku": record["_platform_sku"],
            "purchase_quantity": _decimal(record["_quantity"]), "paid_amount_cny": _decimal(record["_paid_cny"]),
            "shipping_amount_cny": _decimal(record["_shipping_cny"]), "platform_fee_cny": _decimal(record["_fee_cny"]),
            "paid_amount_original": _decimal(record["_paid_original"]), "shipping_amount_original": _decimal(record["_shipping_original"]),
            "refund_quantity": _decimal(record["_refund_quantity"]), "refund_amount_original": _decimal(record["_refund_amount"]),
            "refund_amount_cny": _decimal(record["_refund_cny"]),
            "shipping_status": _text(record.get("发货状态")), "currency_code": _text(record.get("币种")),
            "exchange_rate": _decimal(record["_exchange"]), "customer_id": _text(record.get("客户ID")) or None,
            "site_code": _site(country_cn), "site_name": _site_name(country_cn, record.get("币种")),
            "country_name": country_cn or None}


def _source_fields(record) -> dict:
    result = {}
    for excel_column, database_column in SOURCE_COLUMN_MAP.items():
        value = record.get(excel_column)
        if database_column == "payment_time":
            result[database_column] = record["_payment_time"].to_pydatetime()
        elif database_column in DATETIME_SOURCE_FIELDS:
            parsed = pd.to_datetime(value, errors="coerce")
            result[database_column] = None if pd.isna(parsed) else parsed.to_pydatetime()
        elif database_column in DECIMAL_SOURCE_FIELDS:
            result[database_column] = _decimal(pd.to_numeric(value, errors="coerce"))
        else:
            result[database_column] = _text(value) or None
    exchange_rate = pd.to_numeric(record.get("汇率"), errors="coerce")
    exchange_rate = 0 if pd.isna(exchange_rate) else exchange_rate
    for database_column, excel_column in CNY_SOURCE_COLUMN_MAP.items():
        original_value = pd.to_numeric(record.get(excel_column), errors="coerce")
        original_value = 0 if pd.isna(original_value) else original_value
        result[database_column] = _decimal(original_value * exchange_rate)
    return result


def _profit_row(record, batch_id: str, file_name: str, sheet: str) -> dict:
    source = _profit_source_fields(record)
    product_sales = pd.to_numeric(record.get("商品销售额"), errors="coerce")
    shipping = pd.to_numeric(record.get("应收运费"), errors="coerce")
    refund = pd.to_numeric(record.get("退款金额"), errors="coerce")
    product_sales = 0 if pd.isna(product_sales) else product_sales
    shipping = 0 if pd.isna(shipping) else shipping
    refund = 0 if pd.isna(refund) else refund
    return {
        **source,
        "import_batch_id": batch_id,
        "stat_month": record["_stat_month"],
        "source_file_name": file_name,
        "source_sheet": sheet,
        "source_row": int(record["_source_row"]),
        "payment_date": record["_payment_time"].date(),
        "payment_time": record["_payment_time"].to_pydatetime(),
        "platform_order_no": record["_order_no"],
        "inventory_sku": record["_sku"],
        "platform_sku": record["_platform_sku"] or None,
        "source_site_name": record["_source_site"],
        "site_name": record["_site_name"],
        "profit_cny": _decimal(pd.to_numeric(record.get("利润"), errors="coerce")),
        "net_revenue_cny": _decimal(product_sales + shipping - refund),
    }


def _rebuild_profit_daily(cursor, payment_dates) -> None:
    dates = sorted(set(payment_dates))
    if not dates:
        return
    placeholders = ",".join(["%s"] * len(dates))
    cursor.execute(
        f"DELETE FROM dws_ebay_sku_analysis_profit_daily WHERE payment_date IN ({placeholders})",
        dates,
    )
    cursor.execute(
        f"""INSERT INTO dws_ebay_sku_analysis_profit_daily
        (payment_date,stat_month,site_name,inventory_sku,profit_cny,product_sales_amount_cny,
         shipping_receivable_cny,refund_amount_cny,net_revenue_cny,source_row_count,update_time)
        SELECT p.payment_date,DATE_FORMAT(p.payment_date,'%%Y-%%m'),p.site_name,p.inventory_sku,
          SUM(p.profit_cny),SUM(p.product_sales_amount_cny),SUM(p.shipping_receivable_cny),
          SUM(p.refund_amount_cny),SUM(p.net_revenue_cny),COUNT(*),NOW()
        FROM dwd_ebay_sku_analysis_profit p
        WHERE p.payment_date IN ({placeholders})
          AND EXISTS (
            SELECT 1 FROM dwd_ebay_sku_analysis_order matched
            WHERE DATE(matched.payment_time)=p.payment_date
              AND matched.platform_order_no=p.platform_order_no
              AND matched.inventory_sku=p.inventory_sku
          )
        GROUP BY p.payment_date,p.site_name,p.inventory_sku""",
        dates,
    )


def _profit_source_fields(record) -> dict:
    result = {}
    for excel_column, database_column in PROFIT_SOURCE_COLUMN_MAP.items():
        value = record.get(excel_column)
        if database_column == "payment_time":
            result[database_column] = record["_payment_time"].to_pydatetime()
        elif database_column in PROFIT_DATETIME_SOURCE_FIELDS:
            parsed = pd.to_datetime(value, errors="coerce")
            result[database_column] = None if pd.isna(parsed) else parsed.to_pydatetime()
        elif database_column in PROFIT_DECIMAL_SOURCE_FIELDS:
            result[database_column] = _decimal(pd.to_numeric(value, errors="coerce"))
        elif database_column in {"platform_order_no", "platform_sku", "inventory_sku", "source_sku"}:
            result[database_column] = _identifier(value) or None
        else:
            result[database_column] = _text(value) or None
    return result


def _ensure_tables():
    global _TABLES_READY
    if _TABLES_READY:
        return
    with _TABLES_LOCK:
        if _TABLES_READY:
            return
        _initialize_tables()
        _TABLES_READY = True


def _initialize_tables():
    path = Path(__file__).parents[2] / "migrations" / "20260825_ebay_sku_analysis_tables.sql"
    statements = [item.strip() for item in path.read_text(encoding="utf-8").split(";") if item.strip()]
    missing_columns = {
        "ods_ebay_sku_analysis_order_raw": {
            "goods_receivable_cny": "DECIMAL(20,6) NOT NULL DEFAULT 0 COMMENT '应收货款（订单级别，人民币）' AFTER goods_receivable_original",
            "shipping_receivable_cny": "DECIMAL(20,6) NOT NULL DEFAULT 0 COMMENT '应收运费（人民币）' AFTER shipping_receivable_original",
            "tax_usd_cny": "DECIMAL(20,6) NOT NULL DEFAULT 0 COMMENT '税费（美元字段换算人民币）' AFTER tax_usd",
            "platform_product_unit_price_cny": "DECIMAL(20,6) NOT NULL DEFAULT 0 COMMENT '平台产品单价（人民币）' AFTER platform_product_unit_price",
            "product_unit_price_cny": "DECIMAL(20,6) NOT NULL DEFAULT 0 COMMENT '产品单价（人民币）' AFTER product_unit_price",
            "source_refund_amount_cny": "DECIMAL(20,6) NOT NULL DEFAULT 0 COMMENT '退款金额（人民币）' AFTER source_refund_amount",
        },
        "dwd_ebay_sku_analysis_order": {
            "paid_amount_original": "DECIMAL(20,6) NOT NULL DEFAULT 0 COMMENT '已支付金额原币' AFTER platform_fee_cny",
            "shipping_amount_original": "DECIMAL(20,6) NOT NULL DEFAULT 0 COMMENT '应收运费原币' AFTER paid_amount_original",
            "refund_quantity": "DECIMAL(18,4) NOT NULL DEFAULT 0 COMMENT '退货数量，状态包含已退款或已作废' AFTER shipping_amount_original",
            "refund_amount_original": "DECIMAL(20,6) NOT NULL DEFAULT 0 COMMENT '退款金额原币' AFTER refund_quantity",
            "refund_amount_cny": "DECIMAL(20,6) NOT NULL DEFAULT 0 COMMENT '退款金额人民币' AFTER refund_amount_original",
            "shipping_status": "VARCHAR(64) DEFAULT NULL COMMENT '发货状态' AFTER refund_amount_original",
            "currency_code": "VARCHAR(16) DEFAULT NULL COMMENT '币种' AFTER shipping_status",
            "site_name": "VARCHAR(100) NOT NULL DEFAULT '其他' COMMENT '中文站点名称' AFTER site_code",
            "picture_url": "TEXT DEFAULT NULL COMMENT '图片链接，取上传源数据' AFTER country_name",
            "product_name_cn": "VARCHAR(500) DEFAULT NULL COMMENT '产品名称（中文），取上传源数据' AFTER picture_url",
            "listing_url": "TEXT DEFAULT NULL COMMENT 'Listing链接，取上传源数据' AFTER product_name_cn",
        },
        "dwd_ebay_sku_analysis_profit": {
            "product_sales_amount_cny": "DECIMAL(20,6) NOT NULL DEFAULT 0 COMMENT '商品销售额人民币' AFTER profit_cny",
            "shipping_receivable_cny": "DECIMAL(20,6) NOT NULL DEFAULT 0 COMMENT '应收运费人民币' AFTER product_sales_amount_cny",
            "refund_amount_cny": "DECIMAL(20,6) NOT NULL DEFAULT 0 COMMENT '退款金额人民币' AFTER shipping_receivable_cny",
            "net_revenue_cny": "DECIMAL(20,6) NOT NULL DEFAULT 0 COMMENT '利润率分母，商品销售额加应收运费减退款金额' AFTER refund_amount_cny",
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
    value = country.strip().lower()
    return {
        "美国": "US", "united states": "US",
        "英国": "UK", "united kingdom": "UK",
        "德国": "DE", "germany": "DE",
        "法国": "FR", "france": "FR",
        "意大利": "IT", "italy": "IT",
        "西班牙": "ES", "spain": "ES",
        "澳大利亚": "AU", "australia": "AU",
        "加拿大": "CA", "canada": "CA",
    }.get(value, "OTHER")


def _profit_site_name(source_site: str) -> str:
    value = _identifier(source_site)
    if not value.lower().startswith("ebay"):
        return ""
    if "汽配" in value or "美国" in value:
        return "美国"
    matched = re.search(r"eBay(.+?)站", value, flags=re.IGNORECASE)
    return matched.group(1).strip() if matched else value


def _identifier(value) -> str:
    text = _text(value)
    return "" if text.lower() in {"", "-", "--", "nan", "none", "null"} else text


def _text(value) -> str:
    return "" if value is None or pd.isna(value) else str(value).strip()


def _decimal(value) -> Decimal:
    return Decimal(str(0 if value is None or pd.isna(value) else value)).quantize(Decimal("0.000001"))


def _json_row(row):
    return {key: (value.isoformat(sep=" ") if isinstance(value, datetime) else str(value) if isinstance(value, Decimal) else value)
            for key, value in (row or {}).items()}


def _empty_summary():
    return {"paid_amount": "0", "sold_quantity": "0", "paid_order_count": 0, "sku_count": 0, "buyer_count": 0, "shipping_amount": "0"}


def _chunks(values, size: int):
    for index in range(0, len(values), size):
        yield values[index:index + size]
