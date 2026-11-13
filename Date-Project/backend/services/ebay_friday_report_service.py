"""eBay「周五数据」：每周五早上生成两张表（运营中心 / eBay / 数据报表 / 周五数据），只保留最新一期，不留历史。

还原的是运营原来手工做的《有货无货检查》Excel，数据全部取系统已有的快照，不再人工导出：

有货无货（每条在线 listing 一行，来源 ods_ebay_store_listing_latest 最新月份批次）
  站点        eBay 站点 UK → UK；US（含 eBay 汽配）→ US；其他 → DE（与 Excel 公式一致）
  品牌/中间码  SKU 第一段 / 第二段
  负责人      当月 eBay 品牌负责人规则（与 Excel「运营分品」一致）
  二手SKU     SKU 除第一段外任一段带 YXR / RXY / YXQ / QXY（含 YXR+BMW、YXR/XY）
  品牌/中间码  先去掉多件装前缀 2PC- / 4PC-
  海外仓实际库存  谷仓良品可售按「中间码 + 站点 + 是否二手」汇总（Excel 的 SUMIFS 口径，2026-11-13 用户确认）
  规划站点    店铺主站点（ebay_store_main_site，页面可维护）
  判断        站点 = 规划站点 为 T，否则 F

海外仓库存（谷仓区域仓良品可售 > 0 的每一行，来源 ods_goodcang_product_inventory_latest）
  站点        仓库代码 UK → UK；USCE / USEA / USWE → US；其他 → DE（与 Excel 公式一致）
  SKU         谷仓 SKU 的 JMH 换成品牌；品牌由「中间码 → 品牌」得出，这个对应关系从系统里带品牌前缀的
              SKU（eBay 刊登、领星本地仓库存、eBay 订单）推出，同一中间码多个品牌时取 SKU 最多的那个
  店铺列      每个店铺一列：同站点、同 SKU 的 listing 的 Item 号；listing 所在店铺的主站点 ≠ 站点时
              写成「Item号:历史售出」，提示这条链接挂在不该挂的店铺上
  海外仓有货无在线链接  所有店铺都没有这个 SKU 的同站点 listing 时标「无链接」
"""
from __future__ import annotations

import json
import logging
import re
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from io import BytesIO
from typing import Any

from backend.repositories import ebay_friday_report_repository as repo
from backend.services.ebay_replenishment_periods import reference_today
from backend.services.inventory_report_etl_service import _ebay_assignment, _ebay_rule_map

LOG = logging.getLogger(__name__)
TASK_CODE = "ebay_friday_report_generate"
TASK_NAME = "eBay周五数据生成"
CHINA = timezone(timedelta(hours=8))
SITES = ("DE", "UK", "US")
USED_SUFFIXES = frozenset({"YXR", "RXY", "YXQ", "QXY"})
# 多件装前缀：2PC-OTH-230681-1247 的品牌是 OTH、中间码 230681（与原表一致）。
PACK_PREFIX = re.compile(r"^\d+PC$")
NO_LINK = "无链接"
PRODUCT_TYPES = {"0": "常规商品", "1": "组合商品"}


class EbayFridayReportError(RuntimeError):
    """带 stage / metrics，调度器据此还原失败运行记录。"""

    def __init__(self, stage: str, message: str, metrics: dict[str, Any] | None = None):
        super().__init__(message)
        self.stage = stage
        self.metrics = dict(metrics or {})


# ------------------------------------------------------------------ 规则


def store_key(name: Any) -> str:
    """店铺匹配键：只留小写字母和数字（autoteilefastship = autoteile-fast-ship）。"""
    return re.sub(r"[^a-z0-9]", "", str(name or "").lower())


def listing_site(site: Any) -> str:
    code = str(site or "").strip().upper()
    if code in ("UK", "GB", "英国"):
        return "UK"
    if code in ("US", "EBAYMOTORS", "MOTORS", "美国", "EBAY汽配"):
        return "US"
    return "DE"


def warehouse_site(code: Any) -> str:
    code = str(code or "").strip().upper()
    if code == "UK":
        return "UK"
    if code in ("USCE", "USEA", "USWE"):
        return "US"
    return "DE"


def sku_parts(sku: Any) -> list[str]:
    return [part for part in str(sku or "").strip().upper().split("-") if part]


def brand_mid(sku: Any) -> tuple[str | None, str | None]:
    """SKU 的品牌（第一段）与中间码（第二段）；开头的多件装前缀（2PC- / 4PC-）先去掉。"""
    parts = sku_parts(sku)
    if parts and PACK_PREFIX.match(parts[0]):
        parts = parts[1:]
    return (parts[0] if parts else None), (parts[1] if len(parts) >= 2 else None)


def is_used(sku: Any) -> bool:
    """二手：除第一段外任一段带 YXR / RXY / YXQ / QXY（含 YXR+BMW、YXR/XY 这类拼写）。"""
    return any(token in USED_SUFFIXES for part in sku_parts(sku)[1:] for token in re.split(r"[+/]", part))


def _int(value: Any) -> int:
    try:
        return int(Decimal(str(value).strip()))
    except (InvalidOperation, ValueError, TypeError):
        return 0


def _beijing(value: Any):
    """eBay 的 StartTime 是 UTC（2026-07-23T09:51:46.000Z），换成北京时间展示。"""
    text = str(value or "").strip()
    if not text:
        return None
    try:
        moment = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(CHINA).replace(tzinfo=None)


def mid_brand_map(skus) -> dict[str, str]:
    counts: dict[str, Counter] = defaultdict(Counter)
    for sku in set(skus):
        brand, mid = brand_mid(sku)
        if brand and mid and brand != "JMH":
            counts[mid][brand] += 1
    return {mid: sorted(brands.items(), key=lambda item: (-item[1], item[0]))[0][0] for mid, brands in counts.items()}


def store_columns(store_rows) -> list[dict[str, Any]]:
    return [{"key": row["store_key"], "name": row["store_name"], "main_site": row["main_site"]} for row in store_rows]


# ------------------------------------------------------------------ 生成


def build(listing_rows, stock_rows, store_rows, owner_rules, sku_sources, report_date):
    """纯计算：上游快照 -> 两张表的行。"""
    rules = _ebay_rule_map(owner_rules)
    main_site = {row["store_key"]: row["main_site"] for row in store_rows}
    display = {row["store_key"]: row["store_name"] for row in store_rows}

    stocks, sellable_by_mid = [], defaultdict(int)
    brands = mid_brand_map(sku_sources)
    for index, row in enumerate(stock_rows, 1):
        raw = row.get("raw_json") or {}
        if isinstance(raw, (str, bytes)):
            raw = json.loads(raw)
        product_sku = str(row.get("product_sku") or "").strip().upper()
        mid = brand_mid(product_sku)[1]
        brand = brands.get(mid) if mid else None
        sku = product_sku.replace("JMH", brand, 1) if brand and product_sku.startswith("JMH") else product_sku
        site = warehouse_site(row.get("warehouse_code"))
        used = is_used(product_sku)
        sellable = _int(row.get("sellable"))
        if mid:
            sellable_by_mid[(mid, site, used)] += sellable
        principal = _ebay_assignment(sku, rules)[0] if brand else None
        stocks.append({
            "report_date": report_date, "row_no": index, "product_sku": product_sku,
            "product_type": PRODUCT_TYPES.get(str(row.get("product_type")), str(row.get("product_type") or "")),
            "product_barcode": raw.get("product_barcode"),
            "compliance_status": raw.get("product_freeze_status_text"),
            "product_title": row.get("product_title"),
            "warehouse_code": row.get("warehouse_code"), "warehouse_desc": row.get("warehouse_desc"),
            "warning_qty": _int(row.get("pi_warning_qty")), "onway": _int(row.get("onway")),
            "total_onway": _int(row.get("total_onway")), "transfer_onway": _int(row.get("transfer_onway")),
            "freeze": _int(row.get("pi_freeze")), "sellable": sellable, "reserved": _int(row.get("reserved")),
            "shipped": _int(raw.get("shipped")), "unsellable": _int(row.get("unsellable")),
            "unsellable_reserved": _int(raw.get("pi_unsellable_reserved")),
            "unsellable_shipped": _int(raw.get("pi_unsellable_shipped")),
            "site": site, "sku": sku, "mid_code": mid, "brand": brand, "is_used": int(used),
            "principal_name": principal, "_stores": defaultdict(list),
        })

    listings = []
    by_sku_site: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in listing_rows:
        item_id = str(row.get("item_id") or "").strip()
        if not item_id:
            continue
        sku = str(row.get("sku") or "").strip()
        brand, mid = brand_mid(sku)
        site = listing_site(row.get("site"))
        used = is_used(sku)
        key = store_key(row.get("seller_account"))
        plan = main_site.get(key)
        record = {
            "report_date": report_date, "item_id": item_id, "sku": sku,
            "store_name": display.get(key, str(row.get("seller_account") or "")),
            "online_qty": _int(row.get("quantity_available")),
            # eBay 对从没卖出过的刊登不返回 QuantitySold，按 0（与数字酋长导出逐条比对 99% 一致）。
            "sold_qty": _int(row.get("quantity_sold")),
            "listing_site": row.get("site"), "start_time": _beijing(row.get("start_time")),
            "brand": brand, "mid_code": mid, "site": site,
            "principal_name": _ebay_assignment(sku, rules)[0] if sku else None,
            "is_used": int(used), "overseas_stock": sellable_by_mid.get((mid, site, used), 0) if mid else 0,
            "plan_site": plan, "site_match": None if plan is None else int(plan == site),
            "_store_key": key,
        }
        listings.append(record)
        by_sku_site[(sku.upper(), site)].append(record)

    for stock in stocks:
        matched = sorted(by_sku_site.get((stock["sku"], stock["site"]), []),
                         key=lambda r: (r["start_time"] or datetime.min), reverse=True)
        for listing in matched:
            text = listing["item_id"] if listing["site_match"] != 0 else f"{listing['item_id']}:{listing['sold_qty']}"
            stock["_stores"][listing["_store_key"]].append(text)
        stock["no_link"] = int(not matched)
        # 多个 Item 用顿号连接，与原表一致。
        stock["store_items_json"] = {key: "、".join(items) for key, items in stock.pop("_stores").items()}
    for listing in listings:
        listing.pop("_store_key")
    return listings, stocks


def summarize(listings, stocks) -> dict[str, Any]:
    return {
        "listing_count": len(listings),
        "site_mismatch": sum(1 for r in listings if r["site_match"] == 0),
        "no_plan_site": sum(1 for r in listings if r["site_match"] is None),
        "online_without_stock": sum(1 for r in listings if r["online_qty"] > 0 and r["overseas_stock"] <= 0),
        "stock_rows": len(stocks),
        "stock_sellable": sum(r["sellable"] for r in stocks),
        "stock_no_link": sum(1 for r in stocks if r["no_link"]),
        "stock_no_brand": sum(1 for r in stocks if not r["brand"]),
        "store_unknown": sorted({r["store_name"] for r in listings if r["plan_site"] is None}),
    }


def generate(report_date=None, operator: str = "scheduler") -> dict[str, Any]:
    report_date = report_date or reference_today()
    metrics = {"extract_rows": 0, "ods_rows": 0, "sync_batch_id": f"friday:{report_date}"}
    try:
        listing_rows, listing_head = repo.latest_listings()
        stock_rows, goodcang_pulled = repo.goodcang_stock()
        store_rows = repo.stores()
    except Exception as exc:
        if repo.missing_table(exc):
            raise EbayFridayReportError("EXTRACT", repo.MIGRATION_MESSAGE, metrics) from exc
        raise
    if not listing_rows:
        raise EbayFridayReportError("EXTRACT", "系统里还没有 eBay 在售刊登，请先执行 eBay 在售刊登同步", metrics)
    if not stock_rows:
        raise EbayFridayReportError("EXTRACT", "谷仓库存快照为空，请先执行谷仓区域仓库存同步", metrics)
    month = report_date.strftime("%Y-%m")
    listings, stocks = build(listing_rows, stock_rows, store_rows, repo.ebay_owner_rules(month),
                             repo.brand_sku_sources(), report_date)
    metrics.update(extract_rows=len(listing_rows) + len(stock_rows))
    summary = summarize(listings, stocks)
    run = {
        "report_date": report_date, "generated_at": datetime.now(CHINA).replace(tzinfo=None),
        "listing_month": listing_head.get("stat_month"), "listing_pulled_at": listing_head.get("pulled_at"),
        "goodcang_pulled_at": goodcang_pulled, "owner_rule_month": month,
        "store_columns": store_columns(store_rows), "summary": summary, "generated_by": operator,
    }
    try:
        repo.replace_report(run, listings, stocks)
    except Exception as exc:
        raise EbayFridayReportError("LOAD", f"写入周五数据失败，已回滚：{exc}", metrics) from exc
    LOG.info("eBay周五数据生成 date=%s listing=%s stock=%s", report_date, len(listings), len(stocks))
    return {"task_code": TASK_CODE, "report_date": str(report_date), **summary,
            "store_unknown": summary["store_unknown"][:20],
            "extract_rows": metrics["extract_rows"], "ods_rows": len(listings) + len(stocks),
            "inserted_rows": len(listings) + len(stocks), "sync_batch_id": metrics["sync_batch_id"]}


# ------------------------------------------------------------------ 查询


def _date(value: str | None):
    if not value:
        latest = repo.runs(1)
        if not latest:
            return None
        return latest[0]["report_date"]
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError as exc:
        raise ValueError("报表日期格式应为 YYYY-MM-DD") from exc


def overview(report_date: str | None = None) -> dict[str, Any]:
    day = _date(report_date)
    if day is None:
        return {"report_date": None, "stores": repo.stores()}
    run = repo.run(day)
    if run is None:
        raise ValueError(f"{day} 没有周五数据；只保留最新一期，请刷新页面")
    return {
        "report_date": str(day), "run": {k: v for k, v in run.items() if not k.endswith("_json")},
        "summary": run["summary_json"], "store_columns": run["store_columns_json"], "stores": repo.stores(),
        "options": {
            "stores": repo.options(repo.LISTING_TABLE, day, "store_name"),
            "principals": repo.options(repo.LISTING_TABLE, day, "principal_name"),
            "brands": repo.options(repo.STOCK_TABLE, day, "brand"),
        },
    }


LISTING_SORTS = {"online_qty": "online_qty", "sold_qty": "sold_qty", "overseas_stock": "overseas_stock",
                 "start_time": "start_time", "sku": "sku", "store_name": "store_name"}
STOCK_SORTS = {"sellable": "sellable", "onway": "onway", "sku": "sku", "warehouse_code": "warehouse_code"}


def _filters(day, params: dict[str, Any], kind: str) -> tuple[str, list[Any]]:
    clauses, values = ["report_date=%s"], [day]
    keyword = str(params.get("keyword") or "").strip()
    if keyword:
        if kind == "listing":
            clauses.append("(sku LIKE %s OR item_id LIKE %s)")
            values += [f"%{keyword}%", f"%{keyword}%"]
        else:
            clauses.append("(sku LIKE %s OR product_sku LIKE %s)")
            values += [f"%{keyword}%", f"%{keyword}%"]
    for field in ("site", "principal_name") + (("store_name",) if kind == "listing" else ("brand",)):
        value = str(params.get(field) or "").strip()
        if value:
            clauses.append(f"{field}=%s")
            values.append(value)
    flag = str(params.get("flag") or "").strip()
    if kind == "listing":
        if flag == "mismatch":
            clauses.append("site_match=0")
        elif flag == "no_plan":
            clauses.append("site_match IS NULL")
        elif flag == "no_stock":
            clauses.append("online_qty>0 AND overseas_stock<=0")
        elif flag == "used":
            clauses.append("is_used=1")
    else:
        if flag == "no_link":
            clauses.append("no_link=1")
        elif flag == "no_brand":
            clauses.append("(brand IS NULL OR brand='')")
        elif flag == "used":
            clauses.append("is_used=1")
    return " AND ".join(clauses), values


def _order(params, sorts, default):
    field = sorts.get(str(params.get("sort_field") or ""))
    if not field:
        return default
    direction = "ASC" if str(params.get("sort_order") or "").lower() in ("asc", "ascending") else "DESC"
    return f"{field} {direction},{default}"


def listing_page(params: dict[str, Any]) -> dict[str, Any]:
    day = _date(params.get("report_date"))
    if day is None:
        return {"items": [], "total": 0}
    where, values = _filters(day, params, "listing")
    page, size = max(int(params.get("page") or 1), 1), min(max(int(params.get("page_size") or 50), 1), 200)
    rows, total = repo.page(repo.LISTING_TABLE, where, values,
                            _order(params, LISTING_SORTS, "site_match IS NULL,site_match,start_time DESC,item_id"),
                            size, (page - 1) * size)
    return {"items": [_listing_out(r) for r in rows], "total": total}


def stock_page(params: dict[str, Any]) -> dict[str, Any]:
    day = _date(params.get("report_date"))
    if day is None:
        return {"items": [], "total": 0}
    where, values = _filters(day, params, "stock")
    page, size = max(int(params.get("page") or 1), 1), min(max(int(params.get("page_size") or 50), 1), 200)
    rows, total = repo.page(repo.STOCK_TABLE, where, values, _order(params, STOCK_SORTS, "row_no"),
                            size, (page - 1) * size)
    return {"items": [_stock_out(r) for r in rows], "total": total}


def _listing_out(row):
    row = dict(row)
    row["report_date"] = str(row["report_date"])
    row["start_time"] = row["start_time"].strftime("%Y-%m-%d %H:%M:%S") if row.get("start_time") else None
    row["is_used"] = bool(row["is_used"])
    row["judge"] = None if row["site_match"] is None else ("T" if row["site_match"] else "F")
    return row


def _stock_out(row):
    row = dict(row)
    row["report_date"] = str(row["report_date"])
    value = row.pop("store_items_json", None)
    row["store_items"] = json.loads(value) if isinstance(value, (str, bytes)) else (value or {})
    row["is_used"] = bool(row["is_used"])
    row["no_link"] = bool(row["no_link"])
    return row


# ------------------------------------------------------------------ 店铺主站点


def save_store(payload: dict[str, Any], operator: str | None) -> dict[str, Any]:
    name = str(payload.get("store_name") or "").strip()
    key = store_key(name)
    main = str(payload.get("main_site") or "").strip().upper()
    second = str(payload.get("second_site") or "").strip().upper() or None
    if not key:
        raise ValueError("请填写店铺名")
    if main not in SITES or (second and second not in SITES):
        raise ValueError("主站点 / 第二站点只能是 DE、UK、US")
    original = store_key(payload.get("original_key") or "")
    if original and original != key:
        repo.delete_store(original)
    repo.upsert_store({"store_key": key, "store_name": name, "main_site": main, "second_site": second,
                       "note": str(payload.get("note") or "").strip()[:255] or None,
                       "sort_order": payload.get("sort_order") or 0, "updated_by": operator})
    return {"store_key": key, "note": "已保存；下次生成周五数据时按新的主站点判断"}


def delete_store(key: str) -> dict[str, Any]:
    if not repo.delete_store(store_key(key)):
        raise ValueError("店铺不存在")
    return {"deleted": True}


# ------------------------------------------------------------------ 导出


LISTING_HEADERS = (
    ("Item Number", "item_id"), ("SKU", "sku"), ("eBay账号", "store_name"), ("在线库存", "online_qty"),
    ("历史售出", "sold_qty"), ("eBay站点", "listing_site"), ("上架时间", "start_time"), ("品牌", "brand"),
    ("中间码", "mid_code"), ("站点", "site"), ("负责人", "principal_name"), ("二手SKU(是/否)", "is_used"),
    ("海外仓实际库存", "overseas_stock"), ("规划站点", "plan_site"), ("判断", "judge"),
)
STOCK_HEADERS = (
    ("商品编码", "product_sku"), ("商品类型", "product_type"), ("谷仓商品条码", "product_barcode"),
    ("商品合规状态", "compliance_status"), ("商品中文名称", "product_title"), ("仓库（区域）代码", "warehouse_code"),
    ("仓库（区域）名称", "warehouse_desc"), ("预警库存(良品)", "warning_qty"), ("海外在途", "onway"),
    ("总在途", "total_onway"), ("中转在途", "transfer_onway"), ("冻结", "freeze"), ("良品可售", "sellable"),
    ("良品待出库/预占", "reserved"), ("良品已出库", "shipped"), ("不良品可售", "unsellable"),
    ("不良品待出库/预占", "unsellable_reserved"), ("不良品已出库", "unsellable_shipped"), ("站点", "site"),
    ("SKU", "sku"), ("中间码", "mid_code"), ("品牌", "brand"), ("是否二手", "is_used"),
    ("海外仓有货无在线链接", "no_link"), ("负责人", "principal_name"),
)


def _cell(key, value):
    if key == "is_used":
        return "是" if value else "否"
    if key == "no_link":
        return NO_LINK if value else ""
    return value


def export(report_date: str | None) -> tuple[str, bytes]:
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter

    data = overview(report_date)
    day = data.get("report_date")
    if not day:
        raise ValueError("还没有生成周五数据")
    workbook = Workbook()
    header_fill = PatternFill("solid", fgColor="F7F9FC")
    bold = Font(bold=True, color="24334A")

    sheet = workbook.active
    sheet.title = "有货无货"
    sheet.append([title for title, _ in LISTING_HEADERS])
    where, values = _filters(datetime.strptime(day, "%Y-%m-%d").date(), {}, "listing")
    rows, _ = repo.page(repo.LISTING_TABLE, where, values, "site_match IS NULL,site_match,start_time DESC,item_id",
                        None, 0)
    for row in map(_listing_out, rows):
        sheet.append([_cell(key, row.get(key)) for _, key in LISTING_HEADERS])

    stock_sheet = workbook.create_sheet("海外仓库存")
    stores = data.get("store_columns") or []
    stock_sheet.append([""] * len(STOCK_HEADERS) + [store["main_site"] for store in stores])
    stock_sheet.append([title for title, _ in STOCK_HEADERS] + [store["name"] for store in stores])
    where, values = _filters(datetime.strptime(day, "%Y-%m-%d").date(), {}, "stock")
    rows, _ = repo.page(repo.STOCK_TABLE, where, values, "row_no", None, 0)
    for row in map(_stock_out, rows):
        stock_sheet.append([_cell(key, row.get(key)) for _, key in STOCK_HEADERS]
                           + [row["store_items"].get(store["key"], "") for store in stores])

    sheets = [(sheet, (1,)), (stock_sheet, (1, 2))]
    # 订单售出统计（透视）：有上传时附在最后一张 sheet；没上传或表未部署时不影响前两张。
    from backend.services import ebay_friday_order_sales_service as order_sales
    try:
        orders = order_sales.summary()
    except ValueError:
        orders = {"upload": None}
    if orders.get("upload"):
        order_sheet = workbook.create_sheet("订单售出统计")
        order_sheet.append(["负责人", "非重复计数项:中间码+站点", "求和项:美金收入", "求和项:购买数量"])
        for row in [*orders["rows"], orders["total"]]:
            order_sheet.append([row["principal_name"], row["distinct_mid_site"], float(row["usd_income"]), row["quantity"]])
        sheets.append((order_sheet, (1,)))
    for ws, header_rows in sheets:
        for r in header_rows:
            for cell in ws[r]:
                cell.font, cell.fill = bold, header_fill
                cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        ws.freeze_panes = ws.cell(row=header_rows[-1] + 1, column=3)
        for index in range(1, ws.max_column + 1):
            ws.column_dimensions[get_column_letter(index)].width = 16
    buffer = BytesIO()
    workbook.save(buffer)
    return f"周五数据-{day}.xlsx", buffer.getvalue()
