"""eBay 价格分析 BI 的业务层：刷表（状态判定）与看板取数。

状态**只在刷表时算一次并落库**，所有查询读 status 这一列 —— KPI、散点、缺口榜、
明细表因此必然同一口径，前端也就不需要（也不允许）自己再推导一遍。

口径要点（与设计文档第 3、6 节一致）：
- 覆盖天数 = 谷仓海外仓可售 ÷ 近 7 日日均销量；近 7 日无销量时留 NULL，不写 0 也不写极大值
- price_usd = 原币售价 × my_rate(原币) ÷ my_rate(USD)；汇率缺失留 NULL，不补 0
- 未关联到库存的刊登保留为「未匹配」，库存列与 stock_gap 留 NULL，不计入缺口与超卖
"""
from __future__ import annotations

import logging
import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from io import BytesIO
from typing import Any, Iterable, Sequence
from uuid import uuid4
from zoneinfo import ZoneInfo

from backend.repositories import ebay_price_analysis_repository as repo

LOG = logging.getLogger(__name__)
CHINA = ZoneInfo("Asia/Shanghai")

TASK_CODE = "ebay_price_analysis_refresh"
TASK_NAME = "eBay价格分析刷表"

STATUS_UNMATCHED = "未匹配"
STATUS_OVERSELL = "超卖风险"
STATUS_OUT_OF_STOCK = "断货"
STATUS_REPLENISH = "待补货"
STATUS_SLOW_MOVING = "滞销"
STATUS_HEALTHY = "健康"
STATUSES = (STATUS_UNMATCHED, STATUS_OVERSELL, STATUS_OUT_OF_STOCK, STATUS_REPLENISH,
            STATUS_SLOW_MOVING, STATUS_HEALTHY)

# 待补货的门槛天数。改这里会同时改状态列和「待补货」清单，不会只改一半。
COVER_DAYS_THRESHOLD = Decimal("15")
# cover_days 落库是 DECIMAL(10,2)：销量是 DECIMAL(18,4)，理论上会出现 0.0001 这种
# 日均，算出来的天数能顶爆列宽。封顶而不是改列宽，页面上这已经是「足够久」。
COVER_DAYS_MAX = Decimal("99999999.99")
SCATTER_LIMIT = 2000
MAX_PAGE_SIZE = 200
MAX_EXPORT_ROWS = repo.MAX_ROWS
EXCEL_CONTENT_TYPE = (
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
)

# 严重度排序，同时用于三处：风险清单的 impact、SKU 聚合后取哪个状态、明细表默认排序。
# 「未匹配」排在「滞销」前面：不知道库存比卖得慢更需要先处理。
_SEVERITY = {
    STATUS_OVERSELL: 1, STATUS_OUT_OF_STOCK: 2, STATUS_REPLENISH: 3,
    STATUS_UNMATCHED: 4, STATUS_SLOW_MOVING: 5, STATUS_HEALTHY: 6,
}
RISKS = (
    ("oversell", STATUS_OVERSELL, "eBay 可售超过谷仓+成都可用"),
    ("out_of_stock", STATUS_OUT_OF_STOCK, "谷仓可售为 0 但 eBay 仍在售"),
    ("replenish", STATUS_REPLENISH, f"覆盖天数不足 {COVER_DAYS_THRESHOLD} 天"),
    ("unmatched", STATUS_UNMATCHED, "按站点+去掉品牌前缀的SKU 未关联到谷仓或成都库存"),
    ("slow_moving", STATUS_SLOW_MOVING, "近 30 日无销量但谷仓仍有可售"),
)

_PRICE_OK = re.compile(r"^[0-9]+(\.[0-9]+)?$")
_ILLEGAL_XML = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")

# 导出列。Java 侧按 sys_menu 的 exportColumn:* 过滤后把允许的 key 传进来，
# 不传就导全部；未知 key 直接忽略，不报错也不漏别的列。
EXPORT_COLUMNS = (
    ("seller_account", "店铺"), ("site_name", "站点"), ("item_id", "ItemID"),
    ("sku", "SKU"), ("mid_code", "中间码"), ("title", "标题"),
    ("currency", "币种"), ("current_price", "原币售价"), ("price_usd", "美元价"),
    ("ebay_quantity_available", "eBay可售"), ("ebay_quantity_sold", "eBay已售"),
    ("overseas_sellable", "谷仓可售"), ("overseas_in_transit", "海外在途"),
    ("chengdu_sellable", "成都可售"), ("pending_outbound", "待出库"),
    ("sales_qty_7d", "近7日销量"), ("sales_qty_30d", "近30日销量"),
    ("cover_days", "覆盖天数"), ("stock_gap", "库存缺口"),
    ("purchase_cost_cny", "采购成本(¥)"), ("status", "状态"),
    ("view_item_url", "刊登链接"), ("stat_date", "快照日期"),
)


# ---------------------------------------------------------------- 纯计算
def brand_code(sku: str | None) -> str | None:
    """SKU 第 1 段。TYT-90245-0772 -> TYT。"""
    head = str(sku or "").strip().split("-")[0].strip()
    return head or None


def mid_code(sku: str | None) -> str | None:
    """SKU 前 2 段，品牌-中间码。TYT-90245-0772 -> TYT-90245；不足两段返回 None。"""
    parts = [part.strip() for part in str(sku or "").strip().split("-")]
    if len(parts) < 2 or not parts[0] or not parts[1]:
        return None
    return f"{parts[0]}-{parts[1]}"


def quantity(value: Any) -> int | None:
    """数量列统一成整数；缺失保持 None，不补 0。"""
    if value is None or value == "":
        return None
    try:
        return int(Decimal(str(value)).to_integral_value(rounding="ROUND_HALF_UP"))
    except (InvalidOperation, TypeError, ValueError):
        return None


def listing_price(value: Any) -> Decimal | None:
    """ODS 存的是接口原文。只认纯十进制正数，非法或 0 留 None，不补 0。"""
    text = str(value or "").strip()
    if not _PRICE_OK.fullmatch(text):
        return None
    price = Decimal(text)
    return price if price > 0 else None


def price_usd(price: Decimal | None, currency: str | None,
              rates: dict[str, Decimal]) -> Decimal | None:
    """原币价 -> 美元价。本币或目标币汇率缺失一律返回 None，绝不补 0 或用旧月汇率。"""
    if price is None:
        return None
    code = str(currency or "").strip().upper()
    if code == "USD":
        return price
    own, usd = rates.get(code), rates.get("USD")
    if not own or not usd:
        return None
    return (price * own / usd).quantize(Decimal("0.000001"))


def cover_days(overseas_sellable: int | None, sales_qty_7d: int | None) -> Decimal | None:
    """覆盖天数 = 海外可售 ÷ 近 7 日日均销量。

    近 7 日日均为 0（含无销量、无订单数据）时返回 None —— 写 0 会把「卖不动但有货」
    误判成「马上要断」，写极大值又会在图上压扁所有真实值。
    """
    if overseas_sellable is None or not sales_qty_7d:
        return None
    daily = Decimal(sales_qty_7d) / Decimal(7)
    if daily <= 0:
        return None
    days = (Decimal(overseas_sellable) / daily).quantize(Decimal("0.01"))
    return min(days, COVER_DAYS_MAX)


def resolve_status(*, inventory_matched: bool, ebay_quantity_available: int | None,
                   overseas_sellable: int | None, chengdu_sellable: int | None,
                   cover_days_value: Decimal | None,
                   sales_qty_30d: int | None) -> str:
    """自上而下，命中即止。与设计文档第 3 节末的表格逐行对应。

    可售量缺失（接口没给）时不做大小比较：拿 None 当 0 会凭空判出超卖或断货。
    """
    if not inventory_matched:
        return STATUS_UNMATCHED
    available = ebay_quantity_available
    overseas = overseas_sellable or 0
    chengdu = chengdu_sellable or 0
    if available is not None and available > overseas + chengdu:
        return STATUS_OVERSELL
    if overseas == 0 and (available or 0) > 0:
        return STATUS_OUT_OF_STOCK
    if cover_days_value is not None and cover_days_value < COVER_DAYS_THRESHOLD:
        return STATUS_REPLENISH
    if not sales_qty_30d and overseas > 0:
        return STATUS_SLOW_MOVING
    return STATUS_HEALTHY


def build_row(source: dict[str, Any], *, stat_date: date, rates: dict[str, Decimal],
              batch_id: str, refreshed_at: datetime) -> dict[str, Any]:
    """一条源记录 -> 一条落库行。未关联到库存的行照样返回，库存列留 NULL。"""
    sku = (str(source.get("sku")).strip() if source.get("sku") else None) or None
    matched = source.get("overseas_sellable") is not None
    overseas = quantity(source.get("overseas_sellable")) if matched else None
    chengdu = quantity(source.get("chengdu_sellable")) if matched else None
    available = quantity(source.get("ebay_quantity_available"))
    sales_7d = quantity(source.get("sales_qty_7d")) or 0
    sales_30d = quantity(source.get("sales_qty_30d")) or 0
    days = cover_days(overseas, sales_7d)
    price = listing_price(source.get("current_price"))
    site = str(source.get("site") or "").strip().upper() or None
    gap = None
    if matched and available is not None:
        gap = (overseas or 0) - available
    return {
        "stat_date": stat_date,
        "seller_account": source["seller_account"],
        "site": site,
        "site_name": repo.SITE_NAME_BY_SITE.get(site or ""),
        "item_id": source["item_id"],
        "sku": sku,
        "brand_code": brand_code(sku),
        "mid_code": mid_code(sku),
        "title": source.get("title"),
        "image_url": source.get("image_url"),
        "view_item_url": source.get("view_item_url"),
        "currency": (str(source.get("currency")).strip().upper()
                     if source.get("currency") else None),
        "current_price": price,
        "price_usd": price_usd(price, source.get("currency"), rates),
        "ebay_quantity": quantity(source.get("ebay_quantity")),
        "ebay_quantity_available": available,
        "ebay_quantity_sold": quantity(source.get("ebay_quantity_sold")),
        "watch_count": quantity(source.get("watch_count")),
        "overseas_sellable": overseas,
        "overseas_in_transit": quantity(source.get("overseas_in_transit")) if matched else None,
        "chengdu_sellable": chengdu,
        "pending_outbound": quantity(source.get("pending_outbound")) if matched else None,
        "inventory_matched": 1 if matched else 0,
        "sales_qty_7d": sales_7d,
        "sales_qty_30d": sales_30d,
        "cover_days": days,
        "stock_gap": gap,
        "purchase_cost_cny": _decimal(source.get("purchase_cost_cny")),
        "status": resolve_status(
            inventory_matched=matched, ebay_quantity_available=available,
            overseas_sellable=overseas, chengdu_sellable=chengdu,
            cover_days_value=days, sales_qty_30d=sales_30d),
        "sync_batch_id": batch_id,
        "refreshed_at": refreshed_at,
    }


def build_rows(source: dict[str, Any], *, batch_id: str,
               refreshed_at: datetime) -> list[dict[str, Any]]:
    batch = source.get("batch") or {}
    if not batch:
        return []
    return [build_row(row, stat_date=batch["stat_date"], rates=source.get("rates") or {},
                      batch_id=batch_id, refreshed_at=refreshed_at)
            for row in source.get("rows") or []]


def _decimal(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None
    return result.quantize(Decimal("0.000001")) if result.is_finite() else None


# ---------------------------------------------------------------- 刷表
def refresh_price_analysis() -> dict[str, Any]:
    """拉最新刊登批次 -> 算状态 -> 整表事务替换。写库操作，只由定时任务通道调用。"""
    # 失败直接抛给定时任务通道（scheduler_task_run 记失败），不在这里吞掉。
    batch_id = str(uuid4())
    refreshed_at = datetime.now(CHINA).replace(tzinfo=None)
    source = repo.read_source()
    batch = source.get("batch") or {}
    if not batch:
        raise ValueError("ods_ebay_store_listing_latest 没有任何在售刊登，未刷表")
    # 谷仓同步失败时 Java 仍会继续刷表（用上一份谷仓快照）；但表不存在或为空时不能刷，
    # 否则正常看板会被整表覆盖成「海外仓全部未匹配」。抛错即不写表，DWS 保持上一次结果。
    goodcang = source.get("goodcang") or {}
    if not goodcang.get("exists"):
        raise ValueError(f"{repo.GOODCANG_TABLE} 不存在，请先执行 20261110_goodcang_product_inventory.sql；"
                         "未刷表，看板保持上一次结果")
    if not goodcang.get("rows"):
        raise ValueError("谷仓库存快照为空（DE/UK/USEA/USWE 合计 0 行），未刷表，看板保持上一次结果")
    rows = build_rows(source, batch_id=batch_id, refreshed_at=refreshed_at)
    written = repo.replace_rows(rows)
    result = {
        "status": "success", "sync_batch_id": batch_id,
        "stat_date": _text(batch["stat_date"]), "rows": written["rows"],
        "deleted_rows": written["deleted_rows"], "accounts": _account_rows(rows),
        "matched_rows": sum(row["inventory_matched"] for row in rows),
        "missing_price_usd": sum(row["price_usd"] is None for row in rows),
        "status_counts": _counter(row["status"] for row in rows),
        "goodcang_rows": goodcang["rows"],
    }
    LOG.info("eBay价格分析刷表完成 batch=%s rows=%s", batch_id, written["rows"])
    return result


def _account_rows(rows: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    counts: dict[str, int] = {}
    for row in rows:
        counts[row["seller_account"]] = counts.get(row["seller_account"], 0) + 1
    return [{"seller_account": account, "rows": count}
            for account, count in sorted(counts.items())]


def _counter(values: Iterable[str]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for value in values:
        counts[value] = counts.get(value, 0) + 1
    return counts


# ---------------------------------------------------------------- 查询
def _csv(value: str | None, *, limit: int = 60, item_length: int = 128) -> list[str]:
    items: list[str] = []
    for part in str(value or "").split(","):
        text = part.strip()
        if not text:
            continue
        if len(text) > item_length:
            raise ValueError("筛选项长度超限")
        if text not in items:
            items.append(text)
    if len(items) > limit:
        raise ValueError(f"筛选项不能超过{limit}个")
    return items


def _criteria(*, stat_date: str | None = None, sites: str | None = None,
              accounts: str | None = None, status: str | None = None,
              keyword: str | None = None, sku: str | None = None,
              mid_code_filter: str | None = None) -> dict[str, Any]:
    statuses = _csv(status, limit=len(STATUSES), item_length=16)
    unknown = [item for item in statuses if item not in STATUSES]
    if unknown:
        raise ValueError("状态取值无效：" + "、".join(unknown))
    text = str(keyword or "").strip()
    if len(text) > 128:
        raise ValueError("搜索关键词不能超过128个字符")
    return {
        "stat_date": _parse_date(stat_date),
        "sites": [site.upper() for site in _csv(sites, limit=10, item_length=16)],
        "accounts": _csv(accounts, limit=60),
        "statuses": statuses,
        "keyword": text,
        "sku": (str(sku).strip() or None) if sku else None,
        "mid_code": (str(mid_code_filter).strip() or None) if mid_code_filter else None,
    }


def _parse_date(value: str | None) -> date | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.strptime(text, "%Y-%m-%d").date()
    except ValueError as exc:
        raise ValueError("快照日期格式应为 YYYY-MM-DD") from exc


def _text(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M:%S")
    if isinstance(value, date):
        return value.strftime("%Y-%m-%d")
    return str(value)


def _number(value: Any, places: int = 2) -> float | None:
    """图表与表格用的数值。None 保持 None，不补 0。"""
    if value is None or value == "":
        return None
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None
    if not result.is_finite():
        return None
    return float(result.quantize(Decimal(1).scaleb(-places)))


def _int(value: Any) -> int | None:
    return quantity(value)


def _worst_status(statuses: Any) -> str | None:
    """SKU 聚合后的状态：取这一组里最严重的那个，不新造状态值。"""
    items = [item.strip() for item in str(statuses or "").split(",") if item.strip()]
    known = [item for item in items if item in _SEVERITY]
    if not known:
        return None
    return min(known, key=lambda item: _SEVERITY[item])


def _median(values: list[Decimal]) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return _number(ordered[middle])
    return _number((ordered[middle - 1] + ordered[middle]) / 2)


def _kpis(summary: dict[str, Any]) -> list[dict[str, Any]]:
    counts = summary.get("status_counts") or {}
    overseas = _int(summary.get("overseas_sellable"))
    matched_available = _int(summary.get("matched_ebay_available"))
    gap = None
    if overseas is not None or matched_available is not None:
        gap = (overseas or 0) - (matched_available or 0)
    return [
        {"key": "listing_count", "label": "在售刊登",
         "value": _int(summary.get("listing_count")) or 0, "unit": "条"},
        {"key": "sku_count", "label": "在售SKU",
         "value": _int(summary.get("sku_count")) or 0, "unit": "个"},
        {"key": "ebay_available", "label": "eBay可售",
         "value": _int(summary.get("ebay_available")) or 0, "unit": "件"},
        {"key": "overseas_sellable", "label": "谷仓可售",
         "value": overseas or 0, "unit": "件"},
        {"key": "stock_gap", "label": "库存缺口", "value": gap or 0, "unit": "件"},
        {"key": "oversell_count", "label": "超卖风险",
         "value": int(counts.get(STATUS_OVERSELL, 0)), "unit": "条"},
        {"key": "unmatched_count", "label": "未匹配",
         "value": int(counts.get(STATUS_UNMATCHED, 0)), "unit": "条"},
        {"key": "avg_price_usd", "label": "均价",
         "value": _number(summary.get("avg_price_usd")), "unit": "USD"},
    ]


def _point(row: dict[str, Any]) -> dict[str, Any]:
    price_rows = _int(row.get("price_rows")) or 0
    average = (Decimal(str(row["price_sum"])) / price_rows
               if price_rows and row.get("price_sum") is not None else None)
    return {
        "sku": row.get("group_key"),
        "mid_code": row.get("mid_code"),
        "price_usd": _number(average),
        "overseas_sellable": _int(row.get("overseas_sellable")),
        "ebay_available": _int(row.get("ebay_available")),
        "status": _worst_status(row.get("statuses")),
    }


def _sample(points: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], bool]:
    """点数超限时按价格顺序等距抽样：保留整个价格区间的形状，不只留头部。"""
    if len(points) <= SCATTER_LIMIT:
        return points, False
    step = len(points) / SCATTER_LIMIT
    sampled = [points[min(len(points) - 1, int(index * step))]
               for index in range(SCATTER_LIMIT)]
    return sampled, True


def overview(*, stat_date: str | None = None, sites: str | None = None,
             accounts: str | None = None, status: str | None = None,
             keyword: str | None = None, dimension: str = "sku") -> dict[str, Any]:
    if dimension not in ("sku", "mid"):
        raise ValueError("dimension 只能是 sku 或 mid")
    criteria = _criteria(stat_date=stat_date, sites=sites, accounts=accounts,
                         status=status, keyword=keyword)
    meta = repo.meta()
    summary = repo.summary(criteria)
    points = [_point(row) for row in repo.dimension_points(criteria, dimension)]
    # 中位数取全量点，不取抽样后的点：抽样只影响画多少个点，不该影响参考线。
    median = {
        "price_usd": _median([Decimal(str(point["price_usd"])) for point in points
                              if point["price_usd"] is not None]),
        "overseas_sellable": _median([Decimal(str(point["overseas_sellable"]))
                                      for point in points
                                      if point["overseas_sellable"] is not None]),
    }
    gap_rows = [point for point in points if point["overseas_sellable"] is not None]
    for point in gap_rows:
        point["stock_gap"] = (point["overseas_sellable"] or 0) - (point["ebay_available"] or 0)
    top = sorted(gap_rows, key=lambda point: (-abs(point["stock_gap"]),
                                              str(point["sku"] or "")))[:10]
    points.sort(key=lambda point: (point["price_usd"] is None, point["price_usd"] or 0,
                                   str(point["sku"] or "")))
    scatter, sampled = _sample(points)
    counts = summary.get("status_counts") or {}
    return {
        "stat_date": _text(meta.get("stat_date")),
        "refreshed_at": _text(meta.get("refreshed_at")),
        "dimension": dimension,
        "kpis": _kpis(summary),
        "store_compare": [{
            "seller_account": row["seller_account"], "site": row["site"],
            "ebay_available": _int(row.get("ebay_available")) or 0,
            "overseas_sellable": _int(row.get("overseas_sellable")) or 0,
            "listing_count": _int(row.get("listing_count")) or 0,
        } for row in repo.store_compare(criteria)],
        "scatter": [{key: value for key, value in point.items() if key != "stock_gap"}
                    for point in scatter],
        "scatter_median": median,
        "scatter_sampled": sampled,
        "scatter_total": len(points),
        "stock_gap_top": [{
            "sku": point["sku"], "mid_code": point["mid_code"],
            "stock_gap": point["stock_gap"],
            "overseas_sellable": point["overseas_sellable"],
            "ebay_available": point["ebay_available"],
        } for point in top],
        "risks": [{
            "key": key, "label": label, "count": int(counts.get(label, 0)),
            "impact": _SEVERITY[label], "hint": hint, "filter": {"status": label},
        } for key, label, hint in RISKS],
    }


def _detail_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "seller_account": row.get("seller_account"),
        "site": row.get("site"),
        "site_name": row.get("site_name"),
        "item_id": row.get("item_id"),
        "sku": row.get("sku"),
        "mid_code": row.get("mid_code"),
        "title": row.get("title"),
        "image_url": row.get("image_url"),
        "view_item_url": row.get("view_item_url"),
        "currency": row.get("currency"),
        "current_price": _number(row.get("current_price")),
        "price_usd": _number(row.get("price_usd")),
        "ebay_quantity_available": _int(row.get("ebay_quantity_available")),
        "ebay_quantity_sold": _int(row.get("ebay_quantity_sold")),
        "overseas_sellable": _int(row.get("overseas_sellable")),
        "overseas_in_transit": _int(row.get("overseas_in_transit")),
        "chengdu_sellable": _int(row.get("chengdu_sellable")),
        "pending_outbound": _int(row.get("pending_outbound")),
        "sales_qty_7d": _int(row.get("sales_qty_7d")),
        "sales_qty_30d": _int(row.get("sales_qty_30d")),
        "cover_days": _number(row.get("cover_days")),
        "stock_gap": _int(row.get("stock_gap")),
        "purchase_cost_cny": _number(row.get("purchase_cost_cny")),
        "status": row.get("status"),
        "stat_date": _text(row.get("stat_date")),
    }


def _summary_row(row: dict[str, Any]) -> dict[str, Any]:
    result = _detail_row(row)
    result.pop("seller_account", None)
    result.pop("item_id", None)
    result["status"] = _worst_status(row.get("statuses"))
    result["listing_count"] = _int(row.get("listing_count")) or 0
    result["store_count"] = _int(row.get("store_count")) or 0
    return result


def _rows(criteria: dict[str, Any], *, mode: str, sort_by: str | None, sort_order: str,
          offset: int | None, limit: int | None) -> list[dict[str, Any]]:
    if mode == "summary":
        return [_summary_row(row) for row in repo.summary_rows(
            criteria, sort_by=sort_by, sort_order=sort_order, offset=offset, limit=limit)]
    return [_detail_row(row) for row in repo.detail_rows(
        criteria, sort_by=sort_by, sort_order=sort_order, offset=offset, limit=limit)]


def detail(*, stat_date: str | None = None, sites: str | None = None,
           accounts: str | None = None, status: str | None = None,
           keyword: str | None = None, sku: str | None = None,
           mid_code_filter: str | None = None, mode: str = "detail", page: int = 1,
           page_size: int = 50, sort_by: str | None = None,
           sort_order: str = "desc") -> dict[str, Any]:
    if mode not in ("detail", "summary"):
        raise ValueError("mode 只能是 detail 或 summary")
    page = max(1, int(page))
    page_size = max(1, min(MAX_PAGE_SIZE, int(page_size)))
    criteria = _criteria(stat_date=stat_date, sites=sites, accounts=accounts,
                         status=status, keyword=keyword, sku=sku,
                         mid_code_filter=mid_code_filter)
    total = (repo.summary_count(criteria) if mode == "summary"
             else repo.detail_count(criteria))
    rows = _rows(criteria, mode=mode, sort_by=sort_by, sort_order=sort_order,
                 offset=(page - 1) * page_size, limit=page_size)
    return {"total": total, "page": page, "page_size": page_size, "mode": mode,
            "rows": rows}


def export(*, columns: str | None = None, mode: str = "detail", **filters) -> tuple[str, bytes]:
    """按当前筛选导出 xlsx。列权限由 Java 侧按 exportColumn:* 过滤后传进来。"""
    if mode not in ("detail", "summary"):
        raise ValueError("mode 只能是 detail 或 summary")
    allowed = set(_csv(columns, limit=len(EXPORT_COLUMNS), item_length=64))
    chosen = [item for item in EXPORT_COLUMNS if not allowed or item[0] in allowed]
    if not chosen:
        raise ValueError("没有可导出的列，请检查导出列权限配置")
    criteria = _criteria(**{key: value for key, value in filters.items()
                            if key in ("stat_date", "sites", "accounts", "status",
                                       "keyword", "sku", "mid_code_filter")})
    rows = _rows(criteria, mode=mode, sort_by=filters.get("sort_by"),
                 sort_order=filters.get("sort_order") or "desc", offset=None, limit=None)
    if not rows:
        raise ValueError("当前筛选条件下没有可导出的数据")
    return _workbook(rows, chosen, mode)


def _workbook(rows: Sequence[dict[str, Any]], columns: Sequence[tuple[str, str]],
              mode: str) -> tuple[str, bytes]:
    from openpyxl import Workbook
    from openpyxl.cell import WriteOnlyCell
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter

    workbook = Workbook(write_only=True)
    sheet = workbook.create_sheet("eBay价格分析")
    header = []
    for index, (_, label) in enumerate(columns, 1):
        sheet.column_dimensions[get_column_letter(index)].width = 20
        cell = WriteOnlyCell(sheet, label)
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor="24486D")
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        header.append(cell)
    sheet.append(header)
    for row in rows:
        cells = []
        for key, _ in columns:
            value = row.get(key)
            cell = WriteOnlyCell(sheet)
            if value is None:
                # 缺失统一显示「--」，不写 0：导出件要和页面一个口径。
                cell.value = "--"
                cell.data_type = "s"
            elif isinstance(value, (int, float)):
                cell.value = value
            else:
                cell.value = _ILLEGAL_XML.sub("", str(value))
                cell.data_type = "s"
            cells.append(cell)
        sheet.append(cells)
    output = BytesIO()
    workbook.save(output)
    workbook.close()
    suffix = "汇总" if mode == "summary" else "明细"
    name = f"eBay价格分析{suffix}-{datetime.now(CHINA):%Y%m%d%H%M%S}.xlsx"
    return name, output.getvalue()
