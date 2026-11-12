"""eBay 价格分析 BI 的业务层：刷表（状态判定）与看板取数。

状态**只在刷表时算一次并落库**，所有查询读 status 这一列 —— KPI、散点、缺口榜、
明细表因此必然同一口径，前端也就不需要（也不允许）自己再推导一遍。

口径要点（与设计文档第 3、6 节一致）：
- 覆盖天数 = 谷仓海外仓可售 ÷ 近 7 日日均销量；近 7 日无销量时留 NULL，不写 0 也不写极大值
- price_usd = 原币售价 × my_rate(原币) ÷ my_rate(USD)；汇率按币种回退到快照月及以前最近已出的
  月份（月度汇率月底才出），完全没有汇率时留 NULL，不补 0
- 未关联到库存的刊登保留为「未匹配」，库存列与 stock_gap 留 NULL，不计入缺口与超卖
"""
from __future__ import annotations

import logging
import re
from datetime import date, datetime, timezone
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
MAX_PAGE_SIZE = 200
MAX_EXPORT_ROWS = repo.MAX_ROWS
EXCEL_CONTENT_TYPE = (
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
)

# 严重度排序：SKU 汇总视图里一组刊登取哪个状态。
# 「未匹配」排在「滞销」前面：不知道库存比卖得慢更需要先处理。
_SEVERITY = {
    STATUS_OVERSELL: 1, STATUS_OUT_OF_STOCK: 2, STATUS_REPLENISH: 3,
    STATUS_UNMATCHED: 4, STATUS_SLOW_MOVING: 5, STATUS_HEALTHY: 6,
}
_PRICE_OK = re.compile(r"^[0-9]+(\.[0-9]+)?$")
_ILLEGAL_XML = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")

# 导出列。Java 侧按 sys_menu 的 exportColumn:* 过滤后把允许的 key 传进来，
# 不传就导全部；未知 key 直接忽略，不报错也不漏别的列。
EXPORT_COLUMNS = (
    ("seller_account", "店铺"), ("site_name", "站点"), ("item_id", "ItemID"),
    ("sku", "SKU"), ("mid_code", "中间码"), ("owner_name", "负责人"), ("title", "标题"),
    ("listing_start_time", "上架时间"),
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


def listing_start_time(value: Any) -> datetime | None:
    """接口 ListingDetails/StartTime 是 UTC（如 2026-11-10T02:09:54.000Z），落库转成北京时间。

    eBay 在售接口不返回改价时间，页面「上架时间」即刊登创建时间；格式不认识时留 NULL。
    """
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(CHINA).replace(tzinfo=None, microsecond=0)


def owner_resolver(rule_month: str | None, sku_month: str | None):
    """SKU -> eBay 负责人，口径与绩效 / 月度库存一致（按品牌规则，固定品牌优先，没规则计「未分配」）。

    rule_month 为空（库里还没有任何 eBay 规则）时一律返回 None，页面显示 --，不猜。
    """
    if not rule_month:
        return lambda sku: None
    from backend.repositories import inventory_report_etl_repository as owner_repo
    from backend.services.inventory_report_etl_service import _ebay_assignment, _ebay_rule_map
    rules = _ebay_rule_map(owner_repo.owner_rules(rule_month, "ebay"))
    sku_map = owner_repo.ebay_product_sku_map(sku_month or rule_month)
    cache: dict[str, str | None] = {}

    def resolve(sku: str | None) -> str | None:
        if not sku:
            return None
        if sku not in cache:
            cache[sku] = _ebay_assignment(sku, rules, sku_map)[0] or None
        return cache[sku]
    return resolve


def listing_price(value: Any) -> Decimal | None:
    """ODS 存的是接口原文。只认纯十进制正数，非法或 0 留 None，不补 0。"""
    text = str(value or "").strip()
    if not _PRICE_OK.fullmatch(text):
        return None
    price = Decimal(text)
    return price if price > 0 else None


def price_usd(price: Decimal | None, currency: str | None,
              rates: dict[str, Decimal]) -> Decimal | None:
    """原币价 -> 美元价。本币或目标币汇率缺失一律返回 None，绝不补 0。

    用哪个月的汇率由 repository.rate_lookup 决定（按币种回退到最近已出月份），这里只做换算。
    """
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


# ---------------------------------------------------------------- 未匹配原因
# 分类按 2026-11-10 真实数据校准（本机 17258 条刊登里 761 条未匹配，谷仓用调研时的全量）：
# 组合装 238、带后缀且去掉后哪里都没有 266（其中 -SY 239）、套装 235、仓里确实没有 13、
# 后缀去掉后本站有 5、只有别的站点有 3、站点没仓 1。候选里的「刊登未填 SKU」实测 0 条，
# 不单列：空 SKU 落「仓里没有」，文案写明没填 SKU。
# 判定顺序自上而下、命中即止；只在刷表时做（要查谷仓与成都全部 SKU），不放进查询。
REASON_SITE_UNMAPPED = "SITE_UNMAPPED"
REASON_SKU_BUNDLE = "SKU_BUNDLE"
REASON_SKU_COMBO = "SKU_COMBO"
REASON_SKU_SUFFIX = "SKU_SUFFIX"
REASON_OTHER_SITE_ONLY = "OTHER_SITE_ONLY"
REASON_SUFFIX_NOT_STOCKED = "SUFFIX_NOT_STOCKED"
REASON_NOT_IN_WAREHOUSE = "NOT_IN_WAREHOUSE"
UNMATCHED_REASONS = (
    REASON_SITE_UNMAPPED, REASON_SKU_BUNDLE, REASON_SKU_COMBO, REASON_SKU_SUFFIX,
    REASON_OTHER_SITE_ONLY, REASON_SUFFIX_NOT_STOCKED, REASON_NOT_IN_WAREHOUSE,
)
# 站点 → 看板纳入的谷仓区域仓；不在这里的仓（CZ 等）只用来提示「别的仓有」。
SITE_WAREHOUSES = {"DE": ("DE",), "UK": ("UK",), "US": ("USEA", "USWE")}
_WAREHOUSE_ORDER = ("DE", "UK", "USEA", "USWE", "CZ", "IT", "FRVI", "ES", "USCE")
_COMBO_PREFIX = re.compile(r"^(\d+)\s*PCS?\s*-\s*(.+)$", re.I)      # 2PC-DAS-10757-0557
_COMBO_TIMES = re.compile(r"^(.+?)\s*\*\s*(\d+)$")                    # POR-180010-0205*2
_SUFFIX = re.compile(r"^(.*\d)-([A-Z][A-Z0-9]*)$", re.I)              # YP-50699955-SY
_TEXT_LIMIT = 255


def _site_name(site: str) -> str:
    return repo.SITE_NAME_BY_SITE.get(site, site)


def _found_here(sku: str, site: str, index: dict[str, Any]) -> list[str]:
    """本站点哪里有这个 SKU：谷仓按去前缀 key，成都按完整 SKU。"""
    key = repo.inventory_key(sku)
    goodcang = index.get("goodcang") or {}
    codes = [code for code in SITE_WAREHOUSES.get(site, ()) if key and key in goodcang.get(code, ())]
    places = [f"谷仓 {'、'.join(codes)}"] if codes else []
    if sku.strip().upper() in (index.get("chengdu") or {}).get(_site_name(site), ()):
        places.append("成都仓")
    return places


def _found_elsewhere(sku: str, site: str, index: dict[str, Any]) -> list[str]:
    """本站点以外哪里有：别的谷仓区域仓（含 CZ 等）、别的站点的成都仓。"""
    key = repo.inventory_key(sku)
    goodcang = index.get("goodcang") or {}
    own = SITE_WAREHOUSES.get(site, ())
    codes = sorted((code for code, keys in goodcang.items() if code not in own and key in keys),
                   key=lambda code: (_WAREHOUSE_ORDER.index(code)
                                     if code in _WAREHOUSE_ORDER else len(_WAREHOUSE_ORDER), code))
    places = [f"谷仓 {'、'.join(codes)}"] if key and codes else []
    chengdu = index.get("chengdu") or {}
    for other, name in repo.SITE_NAME_BY_SITE.items():
        if other != site and sku.strip().upper() in chengdu.get(name, ()):
            places.append(f"成都仓（{other} 站）")
    return places


def _combo(sku: str, site: str, index: dict[str, Any]) -> tuple[str, str] | None:
    """组合装 / 多件装：2PC- 前缀、*N 结尾，或中间夹件数段（GM-40419-10-1224 = 40419-1224 的 10 件装）。"""
    match = _COMBO_PREFIX.match(sku)
    if match:
        return f"{match.group(1)} 件装", match.group(2).strip()
    match = _COMBO_TIMES.match(sku)
    if match:
        return f"{match.group(2)} 件装", match.group(1).strip()
    parts = sku.split("-")
    # 中间段是小数字时才可能是件数；JMH-30020-2-0018 这类本身就是合法四段 SKU，
    # 所以只有去掉这段后确实在仓里找得到，才认作多件装。
    for position in range(2, len(parts) - 1):
        segment = parts[position].strip()
        if segment.isdigit() and 1 < int(segment) <= 50:
            single = "-".join(parts[:position] + parts[position + 1:])
            if _found_here(single, site, index) or _found_elsewhere(single, site, index):
                return f"{segment} 件装", single
    return None


def _join(places: list[str]) -> str:
    """「谷仓 DE、成都仓」；以仓库代码结尾时补一个空格，免得和后面的「有」粘在一起。"""
    text = "、".join(places)
    return text + " " if text and text[-1].isascii() else text


def unmatched_reason(sku: str | None, site: str | None,
                     index: dict[str, Any] | None) -> tuple[str, str]:
    """未匹配刊登 -> (原因代码, 页面文案)。文案要让人看了就知道下一步该做什么。"""
    index = index or {}
    site = str(site or "").strip().upper()
    text = str(sku or "").strip()
    if site not in SITE_WAREHOUSES:
        return REASON_SITE_UNMAPPED, f"{site or '未知'} 站没有对应仓库，看板不关联库存"
    if not text:
        return REASON_NOT_IN_WAREHOUSE, "刊登没有填写 SKU，无法到仓库查找"
    if "+" in text:
        count = len([part for part in text.split("+") if part.strip()])
        return REASON_SKU_BUNDLE, (f"套装 SKU：用「+」拼了 {count} 个商品，"
                                   "仓库按单个商品登记，需要拆开对应")
    combo = _combo(text, site, index)
    if combo:
        label, single = combo
        here = _found_here(single, site, index)
        if here:
            return REASON_SKU_COMBO, f"组合装（{label}），单件 SKU {single} 在{_join(here)}有，库存需按单件折算"
        elsewhere = _found_elsewhere(single, site, index)
        if elsewhere:
            return REASON_SKU_COMBO, (f"组合装（{label}），单件 SKU {single} 本站点仓库没有，"
                                      f"{_join(elsewhere)}有")
        return REASON_SKU_COMBO, f"组合装（{label}），单件 SKU {single} 在谷仓和成都都找不到"
    suffix = _SUFFIX.match(text)
    if suffix:
        base, tag = suffix.group(1), suffix.group(2).upper()
        here = _found_here(base, site, index)
        if here:
            return REASON_SKU_SUFFIX, f"SKU 带后缀「-{tag}」，去掉后 {base} 在{_join(here)}有"
    elsewhere = _found_elsewhere(text, site, index)
    if elsewhere:
        return REASON_OTHER_SITE_ONLY, f"{site} 站仓库没有此商品，{_join(elsewhere)}有"
    if suffix:
        elsewhere = _found_elsewhere(base, site, index)
        if elsewhere:
            return REASON_OTHER_SITE_ONLY, (f"SKU 带后缀「-{tag}」，去掉后 {base} {site} 站仓库也没有，"
                                            f"{_join(elsewhere)}有")
        return REASON_SUFFIX_NOT_STOCKED, f"SKU 带后缀「-{tag}」，去掉后缀在谷仓和成都也都找不到此商品"
    return REASON_NOT_IN_WAREHOUSE, "谷仓和成都都没有此 SKU"


def _reason_fields(matched: bool, sku: str | None, site: str | None,
                   index: dict[str, Any] | None) -> dict[str, str | None]:
    if matched:
        return {"unmatched_reason": None, "unmatched_reason_text": None}
    code, text = unmatched_reason(sku, site, index)
    return {"unmatched_reason": code, "unmatched_reason_text": text[:_TEXT_LIMIT]}


def build_row(source: dict[str, Any], *, stat_date: date, rates: dict[str, Decimal],
              batch_id: str, refreshed_at: datetime,
              index: dict[str, Any] | None = None, owner_of=None) -> dict[str, Any]:
    """一条源记录 -> 一条落库行。未关联到库存的行照样返回，库存列留 NULL，并写明未匹配原因。"""
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
        **_reason_fields(matched, sku, site, index),
        "sales_qty_7d": sales_7d,
        "sales_qty_30d": sales_30d,
        "cover_days": days,
        "stock_gap": gap,
        "purchase_cost_cny": _decimal(source.get("purchase_cost_cny")),
        "status": resolve_status(
            inventory_matched=matched, ebay_quantity_available=available,
            overseas_sellable=overseas, chengdu_sellable=chengdu,
            cover_days_value=days, sales_qty_30d=sales_30d),
        "owner_name": owner_of(sku) if owner_of else None,
        "listing_start_time": listing_start_time(source.get("start_time")),
        "sync_batch_id": batch_id,
        "refreshed_at": refreshed_at,
    }


def build_rows(source: dict[str, Any], *, batch_id: str,
               refreshed_at: datetime) -> list[dict[str, Any]]:
    batch = source.get("batch") or {}
    if not batch:
        return []
    index = source.get("inventory_index") or {}
    owner_of = owner_resolver(source.get("owner_rule_month"), batch.get("stat_month"))
    return [build_row(row, stat_date=batch["stat_date"], rates=source.get("rates") or {},
                      batch_id=batch_id, refreshed_at=refreshed_at, index=index,
                      owner_of=owner_of)
            for row in source.get("rows") or []]


def _decimal(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None
    return result.quantize(Decimal("0.000001")) if result.is_finite() else None


# ---------------------------------------------------------------- 失败提示
def failure_reason(exc: BaseException) -> str:
    """接口、导出、刷表共用的失败原因：数据库错误带出具体缺的表/列或错误码，其余只给异常类型。"""
    return repo.describe_db_error(exc) or f"内部错误（{type(exc).__name__}），请检查服务日志"


def _db_step(stage: str, action, *args):
    """刷表里访问数据库的一步：数据库错误改写成可读原因（保留原异常作为 cause），其余原样抛出。"""
    try:
        return action(*args)
    except Exception as exc:
        reason = repo.describe_db_error(exc)
        if reason is None:
            raise
        raise RuntimeError(f"eBay价格分析刷表{stage}失败：{reason}") from exc


# ---------------------------------------------------------------- 刷表
def refresh_price_analysis() -> dict[str, Any]:
    """拉最新刊登批次 -> 算状态 -> 整表事务替换。写库操作，只由定时任务通道调用。"""
    # 失败直接抛给定时任务通道（scheduler_task_run 记失败），不在这里吞掉。
    batch_id = str(uuid4())
    refreshed_at = datetime.now(CHINA).replace(tzinfo=None)
    source = _db_step("读取源数据", repo.read_source)
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
    written = _db_step("写入看板表", repo.replace_rows, rows)
    result = {
        "status": "success", "sync_batch_id": batch_id,
        "stat_date": _text(batch["stat_date"]), "rows": written["rows"],
        "deleted_rows": written["deleted_rows"], "accounts": _account_rows(rows),
        "matched_rows": sum(row["inventory_matched"] for row in rows),
        "missing_price_usd": sum(row["price_usd"] is None for row in rows),
        "status_counts": _counter(row["status"] for row in rows),
        "unmatched_reason_counts": _counter(row["unmatched_reason"] for row in rows
                                            if row["unmatched_reason"]),
        "goodcang_rows": goodcang["rows"],
        "owner_rule_month": source.get("owner_rule_month"),
        # 币种 → 实际折算用的汇率月份（当月未出时按币种回退到最近已出月份）
        "rate_months": dict(sorted((source.get("rate_months") or {}).items())),
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
              mid_code_filter: str | None = None, site_oversell: bool | None = None,
              out_of_stock_listed: bool | None = None,
              unmatched: bool | None = None) -> dict[str, Any]:
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
        "site_oversell": bool(site_oversell),
        "out_of_stock_listed": bool(out_of_stock_listed),
        "unmatched": bool(unmatched),
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
        "owner_name": row.get("owner_name"),
        "listing_start_time": _text(row.get("listing_start_time")),
        # 跨店对比：同站点同 SKU 所有店铺（查询时派生，不受店铺筛选影响）
        "site_store_count": _int(row.get("site_store_count")),
        "site_ebay_available_total": _int(row.get("site_ebay_available_total")),
        "site_price_usd_min": _number(row.get("site_price_usd_min")),
        "site_price_usd_max": _number(row.get("site_price_usd_max")),
        "price_vs_site_min_pct": _number(row.get("price_vs_site_min_pct"), 4),
        "site_oversell": bool(_int(row.get("site_oversell"))),
        "out_of_stock_listed": bool(_int(row.get("out_of_stock_listed"))),
        "unmatched_reason": row.get("unmatched_reason"),
        "unmatched_reason_text": row.get("unmatched_reason_text"),
    }


_CROSS_STORE_KEYS = ("site_store_count", "site_ebay_available_total", "site_price_usd_min",
                     "site_price_usd_max", "price_vs_site_min_pct")


def _summary_row(row: dict[str, Any]) -> dict[str, Any]:
    result = _detail_row(row)
    for key in ("seller_account", "item_id", "listing_start_time", *_CROSS_STORE_KEYS):
        result.pop(key, None)
    result["status"] = _worst_status(row.get("statuses"))
    result["listing_count"] = _int(row.get("listing_count")) or 0
    result["store_count"] = _int(row.get("store_count")) or 0
    result["price_usd_min"] = _number(row.get("price_usd_min"))
    result["price_usd_max"] = _number(row.get("price_usd_max"))
    return result


def _snapshot() -> dict[str, Any]:
    """列表接口顶层的快照日期与刷新时间（页头用）。"""
    current = repo.meta()
    return {"stat_date": _text(current.get("stat_date")),
            "refreshed_at": _text(current.get("refreshed_at"))}


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
           sort_order: str = "desc", site_oversell: bool | None = None,
           out_of_stock_listed: bool | None = None,
           unmatched: bool | None = None) -> dict[str, Any]:
    if mode not in ("detail", "summary"):
        raise ValueError("mode 只能是 detail 或 summary")
    page = max(1, int(page))
    page_size = max(1, min(MAX_PAGE_SIZE, int(page_size)))
    criteria = _criteria(stat_date=stat_date, sites=sites, accounts=accounts,
                         status=status, keyword=keyword, sku=sku,
                         mid_code_filter=mid_code_filter, site_oversell=site_oversell,
                         out_of_stock_listed=out_of_stock_listed, unmatched=unmatched)
    total = (repo.summary_count(criteria) if mode == "summary"
             else repo.detail_count(criteria))
    rows = _rows(criteria, mode=mode, sort_by=sort_by, sort_order=sort_order,
                 offset=(page - 1) * page_size, limit=page_size)
    return {**_snapshot(), "total": total, "page": page, "page_size": page_size,
            "mode": mode, "rows": rows}


def stores(*, sites: str | None = None, accounts: str | None = None) -> dict[str, Any]:
    """店铺汇总：一行一个 店铺+站点，不分页（店铺几十个）。"""
    criteria = _criteria(sites=sites, accounts=accounts)
    return {**_snapshot(), "rows": [{
        "seller_account": row.get("seller_account"),
        "site": row.get("site"),
        "site_name": row.get("site_name"),
        "listing_count": _int(row.get("listing_count")) or 0,
        "sku_count": _int(row.get("sku_count")) or 0,
        "ebay_available": _int(row.get("ebay_available")) or 0,
        "out_of_stock_listed": _int(row.get("out_of_stock_listed")) or 0,
        "site_oversell_sku_count": _int(row.get("site_oversell_sku_count")) or 0,
        "unmatched_count": _int(row.get("unmatched_count")) or 0,
    } for row in repo.store_rows(criteria)]}


def sku_listings(*, sku: str | None) -> dict[str, Any]:
    """某个完整 SKU 在所有店铺、所有站点的刊登，以及每个站点的库存与跨店合计。

    库存按站点共享：每个站点一行、取 MAX；eBay 可售按店铺相加。SKU 不存在返回空数组。
    """
    text = str(sku or "").strip()
    if not text:
        raise ValueError("sku 必填")
    if len(text) > 255:
        raise ValueError("sku 不能超过255个字符")
    listings = repo.sku_listings(text)
    first = listings[0] if listings else {}
    return {
        "sku": text, "title": first.get("title"), "image_url": first.get("image_url"),
        **_snapshot(),
        "listings": [{
            "seller_account": row.get("seller_account"),
            "site": row.get("site"),
            "site_name": row.get("site_name"),
            "item_id": row.get("item_id"),
            "view_item_url": row.get("view_item_url"),
            "currency": row.get("currency"),
            "current_price": _number(row.get("current_price")),
            "price_usd": _number(row.get("price_usd")),
            "ebay_quantity_available": _int(row.get("ebay_quantity_available")),
            "status": row.get("status"),
            "out_of_stock_listed": bool(_int(row.get("out_of_stock_listed"))),
            "unmatched_reason": row.get("unmatched_reason"),
            "unmatched_reason_text": row.get("unmatched_reason_text"),
            "owner_name": row.get("owner_name"),
            "listing_start_time": _text(row.get("listing_start_time")),
        } for row in listings],
        "sites": [{
            "site": row.get("site"),
            "site_name": row.get("site_name"),
            "overseas_sellable": _int(row.get("site_overseas_sellable")),
            "overseas_in_transit": _int(row.get("site_overseas_in_transit")),
            "chengdu_sellable": _int(row.get("site_chengdu_sellable")),
            "pending_outbound": _int(row.get("site_pending_outbound")),
            "ebay_available_total": _int(row.get("site_ebay_available_total")) or 0,
            "store_count": _int(row.get("site_store_count")) or 0,
            "site_oversell": bool(_int(row.get("site_oversell"))),
        } for row in (repo.sku_sites(text) if listings else [])],
    }


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
                                       "keyword", "sku", "mid_code_filter",
                                       "site_oversell", "out_of_stock_listed",
                                       "unmatched")})
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
