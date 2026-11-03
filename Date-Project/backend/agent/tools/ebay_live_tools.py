"""eBay 实时只读工具（移植自 eBay 客服 AI Agent 的数据助手，汇总逻辑在本文件，取数在 backend.agent.ebay_live）。

- 数据按店铺返回，无法拆到负责人，因此只对 eBay 数据范围为「全部数据」的账号开放，另需对应页面权限；
- 按店铺并发取数；取不到数的店铺在 notes 里逐个列出原因，不当作 0；
- 金额保持 eBay 返回的原币/结算币种，不换汇，多币种分行列出；
- 日期按北京时间理解，订单、财务、售后最多查 31 天，流量最多 90 天。
"""
from __future__ import annotations

from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, time, timedelta
from typing import Any, Callable, Literal
from zoneinfo import ZoneInfo

from pydantic import BaseModel, Field, model_validator

from backend.agent.context import SCOPE_EBAY, AgentContext, ToolPermissionError
from backend.agent.ebay_live import (
    EbayReadError, StoreReader, StoreTarget, amount, cached, currency, iso, pick_stores, store_targets,
)
from backend.agent.tools.base import Tool, ToolResult

BEIJING = ZoneInfo("Asia/Shanghai")
STORE_WORKERS = 6
MAX_ORDERS_PER_STORE = 3000
MAX_DAYS = 31
TRAFFIC_MAX_DAYS = 90
LIVE_TIMEOUT_SEC = 180
PERM_SALES = "finance:salesDashboard:list"
PERM_RETURNS = "operations:ebayReturnOverview:list"
SCOPE_NOTE = "eBay 实时数据按店铺返回，无法按负责人拆分，只对 eBay 数据范围为「全部数据」的账号开放"
# 用户在输入框下方勾选「eBay实时」后，本次提问才提供这些工具
EBAY_SOURCE = "ebay"


def allowed(context: AgentContext) -> bool:
    return context.access.scope(SCOPE_EBAY) is None


def require_all_ebay(context: AgentContext) -> None:
    if EBAY_SOURCE not in context.sources:
        raise ToolPermissionError("本次提问没有勾选「eBay实时」，只能查询本系统数据")
    if not allowed(context):
        raise ToolPermissionError(SCOPE_NOTE)


# ---------------------------------------------------------------- 参数

class LiveArgs(BaseModel):
    store: str | None = Field(None, max_length=60, description="店铺名称或账号关键词（包含匹配）；不填查全部店铺")
    start_date: date | None = Field(None, description="开始日期（北京时间，含），默认 7 天前")
    end_date: date | None = Field(None, description="结束日期（北京时间，含），默认今天")

    @model_validator(mode="after")
    def _order(self):
        if self.start_date and self.end_date and self.start_date > self.end_date:
            raise ValueError("开始日期不能晚于结束日期")
        return self


class OrdersArgs(LiveArgs):
    group_by: Literal["store", "day", "marketplace", "sku", "none"] = Field(
        "store", description="分组：store 店铺 / day 日期 / marketplace 站点 / sku SKU / none 合计")
    sku: str | None = Field(None, max_length=60, description="只统计包含该文字的 SKU")
    top: int = Field(30, ge=1, le=200, description="group_by=sku 时返回前几名")


class AfterSalesArgs(LiveArgs):
    include_details: bool = Field(False, description="是否返回逐条明细（最多 200 条）")


class TrafficArgs(LiveArgs):
    marketplaces: list[Literal["EBAY_DE", "EBAY_GB", "EBAY_US", "EBAY_FR", "EBAY_IT", "EBAY_ES", "EBAY_AU",
                               "EBAY_CA", "EBAY_AT"]] = Field(
        default_factory=lambda: ["EBAY_DE", "EBAY_GB", "EBAY_US"],
        max_length=5, description="要统计的站点，默认德国、英国、美国（每个站点每店一次调用，按店铺有额度）")
    group_by: Literal["store", "day", "marketplace"] = "store"


class StoreOnlyArgs(BaseModel):
    store: str | None = Field(None, max_length=60, description="店铺名称或账号关键词；不填查全部店铺")


# ---------------------------------------------------------------- 公共

class Window:
    def __init__(self, start: date, end: date):
        self.start, self.end = start, end
        self.start_utc = datetime.combine(start, time.min, BEIJING)
        end_at = datetime.combine(end + timedelta(days=1), time.min, BEIJING) - timedelta(seconds=1)
        self.end_utc = min(end_at, datetime.now(BEIJING) - timedelta(minutes=2))
        self.label = f"{start:%Y-%m-%d} 至 {end:%Y-%m-%d}（北京时间）"


def window(args: LiveArgs, context: AgentContext, *, max_days: int = MAX_DAYS, end_offset: int = 0) -> Window:
    today = datetime.now(BEIJING).date()
    end = min(args.end_date or today - timedelta(days=end_offset), today - timedelta(days=end_offset))
    start = args.start_date or end - timedelta(days=6)
    if (end - start).days + 1 > max_days:
        raise ValueError(f"单次最多查询 {max_days} 天，请缩小日期范围")
    return Window(start, end)


def run_stores(keyword: str | None, fn: Callable[[StoreReader], Any]) -> tuple[list[StoreTarget], dict, dict]:
    """按店铺并发执行 fn；返回（目标店铺, {key: 结果}, {key: 失败原因}）。"""
    stores = pick_stores(store_targets(), keyword)
    if not stores:
        raise ValueError(f"没有找到名称或账号包含「{keyword}」的 eBay 店铺" if keyword else "没有配置可用的 eBay 店铺凭证")

    def one(store: StoreTarget):
        try:
            return store.key, fn(StoreReader(store)), None
        except EbayReadError as exc:
            return store.key, None, exc.reason
        except Exception as exc:  # noqa: BLE001 —— 单店出错不影响其他店铺
            return store.key, None, f"{type(exc).__name__}"

    with ThreadPoolExecutor(max_workers=STORE_WORKERS) as pool:
        outcomes = list(pool.map(one, stores))
    results = {key: value for key, value, error in outcomes if error is None}
    failed = {key: error for key, _value, error in outcomes if error is not None}
    return stores, results, failed


def failure_notes(stores: list[StoreTarget], failed: dict[str, str]) -> list[str]:
    if not failed:
        return []
    names = {s.key: s.name for s in stores}
    items = [f"{names[k]}（{v}）" for k, v in list(failed.items())[:10]]
    more = f" 等 {len(failed)} 个店铺" if len(failed) > 10 else ""
    return [f"以下店铺没取到数据，未计入结果：{'；'.join(items)}{more}"]


def r2(value: float) -> float:
    return round(value + 0.0, 2)


def paged(reader: StoreReader, path: str, list_key: str, params: dict, *, limit: int, max_rows: int,
          **kwargs) -> tuple[list[dict], bool]:
    rows, offset = [], 0
    while True:
        data = reader.get(path, {**params, "limit": limit, "offset": offset}, **kwargs)
        page = data.get(list_key) or []
        rows += page
        offset += len(page)
        if not page or offset >= int(data.get("total") or 0):
            return rows, False
        if len(rows) >= max_rows:
            return rows, True


# ---------------------------------------------------------------- 订单与销量

def _orders(reader: StoreReader, win: Window) -> dict:
    def load():
        raw, truncated = paged(reader, "/sell/fulfillment/v1/order", "orders",
                               {"filter": f"creationdate:[{iso(win.start_utc)}..{iso(win.end_utc)}]"},
                               limit=200, max_rows=MAX_ORDERS_PER_STORE)
        return {"orders": raw, "truncated": truncated}
    return cached((reader.store.key, "orders", win.start, win.end), load)


def ebay_orders_summary(context: AgentContext, args: OrdersArgs) -> ToolResult:
    require_all_ebay(context)
    win = window(args, context)
    stores, results, failed = run_stores(args.store, lambda r: _orders(r, win))
    names = {s.key: s.name for s in stores}
    sku_filter = (args.sku or "").casefold()
    buckets: dict[tuple, dict] = defaultdict(lambda: {"orders": set(), "units": 0, "amount": 0.0, "title": ""})
    cancelled, truncated = 0, []
    for key, res in results.items():
        if res["truncated"]:
            truncated.append(names[key])
        for o in res["orders"]:
            if (o.get("cancelStatus") or {}).get("cancelState") == "CANCELED":
                cancelled += 1
                continue
            lines = o.get("lineItems") or []
            if sku_filter:
                lines = [li for li in lines if sku_filter in (li.get("sku") or "").casefold()]
                if not lines:
                    continue
            created = datetime.fromisoformat(o["creationDate"].replace("Z", "+00:00")).astimezone(BEIJING)
            marketplace = (lines[0].get("listingMarketplaceId") if lines else None) or "UNKNOWN"
            for li in lines:
                if args.group_by == "sku":
                    group = li.get("sku") or "（无SKU）"
                else:
                    group = {"store": names[key], "day": f"{created:%Y-%m-%d}", "marketplace": marketplace,
                             "none": "合计"}[args.group_by]
                total = li.get("total") or {}
                bucket = buckets[(group, currency(total) or "")]
                bucket["orders"].add(o.get("orderId"))
                bucket["units"] += int(li.get("quantity") or 0)
                bucket["amount"] += amount(total)
                bucket["title"] = bucket["title"] or (li.get("title") or "")[:80]
    label = {"store": "店铺", "day": "日期", "marketplace": "站点", "sku": "SKU", "none": "范围"}[args.group_by]
    rows = [{"group": g, "currency": c, "orders": len(b["orders"]), "units": b["units"], "amount": r2(b["amount"]),
             **({"title": b["title"]} if args.group_by == "sku" else {})}
            for (g, c), b in buckets.items()]
    if args.group_by == "day":
        rows.sort(key=lambda r: (r["group"], r["currency"]))
    else:
        rows.sort(key=lambda r: -r["units" if args.group_by == "sku" else "orders"])
    if args.group_by == "sku":
        rows = rows[:args.top]
    columns = [("group", label)] + ([("title", "商品标题")] if args.group_by == "sku" else []) + [
        ("orders", "订单数"), ("units", "件数"), ("amount", "销售额（原币）"), ("currency", "币种")]
    by_currency: dict[str, float] = defaultdict(float)
    for row in rows if args.group_by != "sku" else []:
        by_currency[row["currency"]] += row["amount"]
    all_orders = {oid for b in buckets.values() for oid in b["orders"]}
    summary = {"店铺数": len(results), "订单数": len(all_orders), "件数": sum(b["units"] for b in buckets.values()),
               **{f"销售额（{c}）": r2(v) for c, v in by_currency.items() if c}}
    notes = [f"按下单时间统计（北京时间），已排除取消订单 {cancelled} 单；销售额为订单行金额（买家所付商品+运费，原币，"
             "不含 eBay 代收的税），未扣成交费和广告费，净收入请查财务汇总。",
             "这是 eBay 实时数据，月度业绩口径请以销售看板 / 绩效排名为准。"]
    if truncated:
        notes.append(f"以下店铺订单超过 {MAX_ORDERS_PER_STORE} 单，只统计了前 {MAX_ORDERS_PER_STORE} 单：{'、'.join(truncated)}")
    return ToolResult(title=f"eBay 实时订单（按{label}）", summary=summary, columns=columns, rows=rows,
                      source="eBay Fulfillment API（实时）", period=win.label,
                      notes=notes + failure_notes(stores, failed))


# ---------------------------------------------------------------- 财务

FIN_COLUMNS = [("sales_net", "销售入账（已扣成交费）"), ("fees", "成交费"), ("ad_fees", "广告费"),
               ("other_fees", "其他费用"), ("refunds", "退款"), ("disputes", "纠纷扣款"), ("labels", "运费标签"),
               ("credits", "其他入账"), ("net", "净额"), ("payouts", "已放款"), ("balance", "当前余额"),
               ("on_hold", "其中冻结")]


def _finance(reader: StoreReader, win: Window) -> dict:
    def load():
        marketplace = reader.registration_marketplace()
        tx, truncated = paged(reader, "/sell/finances/v1/transaction", "transactions",
                              {"filter": f"transactionDate:[{iso(win.start_utc)}..{iso(win.end_utc)}]"},
                              limit=1000, max_rows=MAX_ORDERS_PER_STORE * 3, host="apiz", marketplace=marketplace)
        payouts = reader.get("/sell/finances/v1/payout", {
            "filter": f"payoutDate:[{iso(win.start_utc)}..{iso(win.end_utc)}]", "limit": 200},
            host="apiz", marketplace=marketplace).get("payouts") or []
        funds = reader.get("/sell/finances/v1/seller_funds_summary", host="apiz", marketplace=marketplace)
        return {"tx": tx, "truncated": truncated, "payouts": payouts, "funds": funds}
    return cached((reader.store.key, "finance", win.start, win.end), load)


def ebay_finance_summary(context: AgentContext, args: LiveArgs) -> ToolResult:
    require_all_ebay(context)
    win = window(args, context)
    stores, results, failed = run_stores(args.store, lambda r: _finance(r, win))
    names = {s.key: s.name for s in stores}
    rows, totals = [], defaultdict(lambda: defaultdict(float))
    for key, res in results.items():
        per: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
        for t in res["tx"]:
            node = t.get("amount") or {}
            cur = currency(node) or ""
            value = amount(node) * (-1 if t.get("bookingEntry") == "DEBIT" else 1)
            rate = float(node.get("exchangeRate") or 1) if node.get("convertedFromCurrency") else 1.0
            kind = t.get("transactionType")
            m = per[cur]
            if kind == "SALE":
                m["sales_net"] += value
                m["fees"] -= amount(t.get("totalFeeAmount")) * rate
            elif kind == "NON_SALE_CHARGE":
                m["ad_fees" if t.get("feeType") == "AD_FEE" else "other_fees"] += value
            elif kind == "REFUND":
                m["refunds"] += value
            elif kind == "DISPUTE":
                m["disputes"] += value
            elif kind == "SHIPPING_LABEL":
                m["labels"] += value
            elif kind not in ("WITHDRAWAL", "TRANSFER", "PAYOUT"):
                m["credits"] += value
            if kind not in ("WITHDRAWAL", "TRANSFER", "PAYOUT"):
                m["net"] += value
        for p in res["payouts"]:
            if p.get("payoutStatus") in ("SUCCEEDED", "INITIATED"):
                per[currency(p.get("amount")) or ""]["payouts"] += amount(p.get("amount"))
        funds = res["funds"] or {}
        fund_cur = currency(funds.get("totalFunds")) or ""
        per[fund_cur]["balance"] += amount(funds.get("totalFunds"))
        per[fund_cur]["on_hold"] += amount(funds.get("fundsOnHold"))
        for cur, m in per.items():
            rows.append({"store": names[key], "currency": cur, **{k: r2(m[k]) for k, _ in FIN_COLUMNS}})
            for k, _ in FIN_COLUMNS:
                totals[cur][k] += m[k]
    rows.sort(key=lambda r: -r["net"])
    summary: dict[str, Any] = {"店铺数": len(results)}
    for cur, m in totals.items():
        for k in ("sales_net", "fees", "ad_fees", "refunds", "net", "payouts", "balance"):
            summary[f"{dict(FIN_COLUMNS)[k]}（{cur}）"] = r2(m[k])
    truncated = [names[k] for k, r in results.items() if r["truncated"]]
    notes = ["金额为 eBay 财务接口的结算币种（eBay 已按交易当时汇率折算）；成交费按交易汇率由原币折算。",
             "净额 = 期间内全部入账与扣款之和（不含放款本身）；当前余额、冻结为查询时点的数值，与所选日期无关。"]
    if truncated:
        notes.append(f"以下店铺交易笔数过多，只统计了前 {MAX_ORDERS_PER_STORE * 3} 笔：{'、'.join(truncated)}")
    return ToolResult(title="eBay 财务汇总", summary=summary,
                      columns=[("store", "店铺"), *FIN_COLUMNS, ("currency", "币种")], rows=rows,
                      source="eBay Finances API（实时）", period=win.label, notes=notes + failure_notes(stores, failed))


# ---------------------------------------------------------------- 退货与纠纷

AFTER_SALES_KINDS = ("退货", "未收到货", "个案", "付款纠纷")
CLOSED = ("CLOSED", "CS_CLOSED")


def _value(node: Any) -> Any:
    return node.get("value") if isinstance(node, dict) else node


def _post_order(reader: StoreReader, path: str, params: dict, marketplace: str, max_pages: int = 10) -> list[dict]:
    rows = []
    for page in range(1, max_pages + 1):
        data = reader.get(path, {**params, "limit": 200, "offset": page}, iaf=True, marketplace=marketplace)
        members = data.get("members") or []
        rows += members
        total_pages = int(((data.get("paginationOutput") or {}).get("totalPages")) or 1)
        if not members or page >= total_pages:
            break
    return rows


def _after_sales(reader: StoreReader, win: Window) -> list[dict]:
    def load():
        marketplace = reader.registration_marketplace()
        start, end = iso(win.start_utc), iso(win.end_utc)
        rows = []
        for r in _post_order(reader, "/post-order/v2/return/search", {
                "creation_date_range_from": start, "creation_date_range_to": end, "role": "SELLER"}, marketplace):
            info = r.get("creationInfo") or {}
            refund = (r.get("buyerTotalRefund") or {}).get("estimatedRefundAmount")
            rows.append({"kind": "退货", "id": r.get("returnId"), "order_id": r.get("orderId"),
                         "created": _value(info.get("creationDate")), "status": r.get("status") or r.get("state"),
                         "reason": info.get("reason"),
                         "open": bool((r.get("sellerResponseDue") or {}).get("activityDue")),
                         "amount": amount(refund), "currency": currency(refund)})
        for q in _post_order(reader, "/post-order/v2/inquiry/search", {
                "inquiry_creation_date_range_from": start, "inquiry_creation_date_range_to": end}, marketplace):
            status = q.get("inquiryStatusEnum") or q.get("status") or ""
            rows.append({"kind": "未收到货", "id": q.get("inquiryId"), "order_id": q.get("orderId"),
                         "created": _value(q.get("creationDate")), "status": status, "reason": None,
                         "open": status.upper() not in CLOSED,
                         "amount": amount(q.get("claimAmount")), "currency": currency(q.get("claimAmount"))})
        for c in _post_order(reader, "/post-order/v2/casemanagement/search", {
                "case_creation_date_range_from": start, "case_creation_date_range_to": end}, marketplace):
            status = c.get("caseStatusEnum") or ""
            rows.append({"kind": "个案", "id": str(c.get("caseId")), "order_id": None,
                         "created": _value(c.get("creationDate")), "status": status, "reason": c.get("caseType"),
                         "open": status not in CLOSED,
                         "amount": amount(c.get("claimAmount")), "currency": currency(c.get("claimAmount"))})
        try:
            disputes = reader.get("/sell/fulfillment/v1/payment_dispute_summary", {
                "open_date_from": start, "open_date_to": end, "limit": 200}, host="apiz")
            for p in disputes.get("paymentDisputeSummaries") or []:
                rows.append({"kind": "付款纠纷", "id": p.get("paymentDisputeId"), "order_id": p.get("orderId"),
                             "created": p.get("openDate"), "status": p.get("paymentDisputeStatus"),
                             "reason": p.get("reason"),
                             "open": p.get("paymentDisputeStatus") in ("OPEN", "ACTION_NEEDED"),
                             "amount": amount(p.get("amount")), "currency": currency(p.get("amount"))})
        except EbayReadError as exc:
            if exc.kind not in ("NO_SCOPE", "NOT_FOUND", "DENIED"):
                raise
        return rows
    return cached((reader.store.key, "after_sales", win.start, win.end), load)


def _day(value: str | None) -> str:
    if not value:
        return ""
    try:
        return f"{datetime.fromisoformat(value.replace('Z', '+00:00')).astimezone(BEIJING):%Y-%m-%d}"
    except ValueError:
        return value[:10]


def ebay_after_sales(context: AgentContext, args: AfterSalesArgs) -> ToolResult:
    require_all_ebay(context)
    win = window(args, context)
    stores, results, failed = run_stores(args.store, lambda r: _after_sales(r, win))
    names = {s.key: s.name for s in stores}
    if args.include_details:
        rows = [{"store": names[k], "kind": r["kind"], "id": r["id"], "order_id": r["order_id"] or "",
                 "created": _day(r["created"]), "status": r["status"] or "", "reason": r["reason"] or "",
                 "amount": r2(r["amount"]), "currency": r["currency"] or ""}
                for k, items in results.items() for r in items]
        rows.sort(key=lambda r: r["created"], reverse=True)
        rows = rows[:200]
        columns = [("store", "店铺"), ("kind", "类型"), ("id", "编号"), ("order_id", "订单号"), ("created", "创建日期"),
                   ("status", "状态"), ("reason", "原因"), ("amount", "涉及金额"), ("currency", "币种")]
    else:
        rows = []
        for k, items in results.items():
            counts = defaultdict(int)
            for r in items:
                counts[r["kind"]] += 1
                counts["open"] += 1 if r["open"] else 0
            rows.append({"store": names[k], **{kind: counts[kind] for kind in AFTER_SALES_KINDS}, "open": counts["open"]})
        rows.sort(key=lambda r: -sum(r[kind] for kind in AFTER_SALES_KINDS))
        columns = [("store", "店铺"), *[(kind, kind) for kind in AFTER_SALES_KINDS], ("open", "待处理")]
    everything = [r for items in results.values() for r in items]
    # 总数和待处理数分开给出，避免把「退货总数」当成「待处理退货」
    summary = {"店铺数": len(results),
               **{f"{kind}（总数）": sum(1 for r in everything if r["kind"] == kind) for kind in AFTER_SALES_KINDS},
               **{f"{kind}（待处理）": sum(1 for r in everything if r["kind"] == kind and r["open"])
                  for kind in AFTER_SALES_KINDS},
               "待处理合计": sum(1 for r in everything if r["open"])}
    return ToolResult(title="eBay 退货与纠纷" + ("明细" if args.include_details else ""), summary=summary,
                      columns=columns, rows=rows, source="eBay Post-Order / Fulfillment API（实时）", period=win.label,
                      notes=["按创建时间统计；待处理 = eBay 显示仍需卖家操作或尚未关闭的。"]
                      + failure_notes(stores, failed))


# ---------------------------------------------------------------- 卖家等级

LEVEL_TEXT = {"TOP_RATED": "优秀", "ABOVE_STANDARD": "合格", "BELOW_STANDARD": "不合格"}
PROGRAMS = (("PROGRAM_US", "美国"), ("PROGRAM_UK", "英国"), ("PROGRAM_DE", "德国"), ("PROGRAM_GLOBAL", "全球"))


def _metric(value: Any) -> float | None:
    value = _value(value)
    try:
        return float(value) if value is not None and not isinstance(value, bool) else None
    except (TypeError, ValueError):
        return None


def _standards(reader: StoreReader) -> list[dict]:
    def load():
        data = reader.get("/sell/analytics/v1/seller_standards_profile")
        rows = []
        for profile in data.get("standardsProfiles") or []:
            if (profile.get("cycle") or {}).get("cycleType") != "CURRENT":
                continue
            metrics = {m.get("metricKey"): m.get("value") for m in profile.get("metrics") or []}
            rows.append({"program": profile.get("program"), "level": profile.get("standardsLevel"),
                         "defect_rate": _metric(metrics.get("DEFECTIVE_TRANSACTION_RATE")),
                         "late_rate": _metric(metrics.get("SHIPPING_MISS_RATE")),
                         "cases_rate": _metric(metrics.get("CLAIMS_SAF_RATE"))})
        return rows
    return cached((reader.store.key, "standards"), load)


def ebay_seller_standards(context: AgentContext, args: StoreOnlyArgs) -> ToolResult:
    require_all_ebay(context)
    stores, results, failed = run_stores(args.store, _standards)
    names = {s.key: s.name for s in stores}
    rows = []
    for key, profiles in results.items():
        by = {p["program"]: p for p in profiles}

        def worst(field: str) -> float | None:
            values = [p[field] for p in profiles if p[field] is not None]
            return max(values) if values else None
        rows.append({"store": names[key],
                     **{code: LEVEL_TEXT.get((by.get(code) or {}).get("level"), "") for code, _ in PROGRAMS},
                     "defect_rate": worst("defect_rate"), "late_rate": worst("late_rate"),
                     "cases_rate": worst("cases_rate"),
                     "below": "是" if any(p["level"] == "BELOW_STANDARD" for p in profiles) else ""})
    rows.sort(key=lambda r: (r["below"] != "是", -(r["defect_rate"] or 0)))
    below = [r["store"] for r in rows if r["below"] == "是"]
    return ToolResult(
        title="eBay 卖家等级（当前考核周期）", summary={"店铺数": len(results), "有站点不合格的店铺数": len(below)},
        columns=[("store", "店铺"), *[(code, f"{label}等级") for code, label in PROGRAMS],
                 ("defect_rate", "不良交易率%（最高）"), ("late_rate", "延迟发货率%（最高）"),
                 ("cases_rate", "未解决个案率%（最高）"), ("below", "有不合格")],
        rows=rows, source="eBay Analytics API（实时）", period="当前考核周期",
        notes=["卖家等级按 eBay 当前考核周期计算，与日期无关；比率为百分数，取各考核站点中最高的一个。"]
        + failure_notes(stores, failed))


# ---------------------------------------------------------------- 流量

TRAFFIC_METRICS = "LISTING_IMPRESSION_TOTAL,LISTING_VIEWS_TOTAL,TRANSACTION"


def _traffic(reader: StoreReader, marketplaces: list[str], start: str, end: str) -> list[dict]:
    def load():
        rows = []
        for marketplace in marketplaces:
            try:
                data = reader.get("/sell/analytics/v1/traffic_report", {
                    "dimension": "DAY", "metric": TRAFFIC_METRICS,
                    "filter": f"marketplace_ids:{{{marketplace}}},date_range:[{start}..{end}]"}, retry_429=False)
            except EbayReadError as exc:
                if exc.kind == "NOT_FOUND" or exc.status in (400, 409):
                    continue  # 该站点没有刊登
                raise
            keys = [m.get("key") for m in (data.get("header") or {}).get("metrics") or []]
            for record in data.get("records") or []:
                values = {k: (v or {}).get("value") for k, v in zip(keys, record.get("metricValues") or [])}
                day = ((record.get("dimensionValues") or [{}])[0]).get("value") or ""
                rows.append({"marketplace": marketplace, "day": f"{day[:4]}-{day[4:6]}-{day[6:8]}",
                             "impressions": int(values.get("LISTING_IMPRESSION_TOTAL") or 0),
                             "views": int(values.get("LISTING_VIEWS_TOTAL") or 0),
                             "transactions": int(values.get("TRANSACTION") or 0)})
        return rows
    # 流量报表按天更新、按店铺有较低额度，缓存 6 小时
    return cached((reader.store.key, "traffic", tuple(marketplaces), start, end), load, ttl=6 * 3600)


def ebay_traffic(context: AgentContext, args: TrafficArgs) -> ToolResult:
    require_all_ebay(context)
    win = window(args, context, max_days=TRAFFIC_MAX_DAYS, end_offset=1)
    start, end = f"{win.start:%Y%m%d}", f"{win.end:%Y%m%d}"
    stores, results, failed = run_stores(args.store, lambda r: _traffic(r, list(args.marketplaces), start, end))
    names = {s.key: s.name for s in stores}
    agg: dict[str, dict[str, int]] = defaultdict(lambda: {"impressions": 0, "views": 0, "transactions": 0})
    for key, items in results.items():
        for r in items:
            group = {"store": names[key], "day": r["day"], "marketplace": r["marketplace"]}[args.group_by]
            for field in ("impressions", "views", "transactions"):
                agg[group][field] += r[field]

    def ratios(v: dict[str, int]) -> dict[str, Any]:
        return {**v, "view_rate": round(v["views"] / v["impressions"], 4) if v["impressions"] else None,
                "conversion": round(v["transactions"] / v["views"], 4) if v["views"] else None}
    rows = [{"group": g, **ratios(v)} for g, v in agg.items()]
    rows.sort(key=lambda r: r["group"] if args.group_by == "day" else -r["impressions"])
    total = ratios({f: sum(v[f] for v in agg.values()) for f in ("impressions", "views", "transactions")})
    label = {"store": "店铺", "day": "日期", "marketplace": "站点"}[args.group_by]
    return ToolResult(
        title=f"eBay 刊登流量（按{label}）",
        summary={"店铺数": len(results), "曝光": total["impressions"], "浏览": total["views"],
                 "成交": total["transactions"], "浏览率": total["view_rate"], "成交转化率": total["conversion"]},
        columns=[("group", label), ("impressions", "曝光"), ("views", "浏览"), ("view_rate", "浏览率"),
                 ("transactions", "成交"), ("conversion", "成交转化率")],
        rows=rows, source="eBay Analytics 流量报表（实时，缓存 6 小时）",
        period=f"{win.start:%Y-%m-%d} 至 {win.end:%Y-%m-%d}；站点 {'、'.join(args.marketplaces)}",
        notes=["浏览率 = 浏览 ÷ 曝光，成交转化率 = 成交 ÷ 浏览（小数）；流量数据按天更新，截止到昨天。",
               "流量报表每个站点每店一次调用，eBay 按店铺限额，额度用完的店铺会列在下方。"]
        + failure_notes(stores, failed))


# ---------------------------------------------------------------- 广告活动

def _campaigns(reader: StoreReader) -> list[dict]:
    def load():
        raw, _ = paged(reader, "/sell/marketing/v1/ad_campaign", "campaigns", {}, limit=100, max_rows=500)
        rows = []
        for c in raw:
            funding = c.get("fundingStrategy") or {}
            rows.append({"name": c.get("campaignName") or "", "status": c.get("campaignStatus") or "",
                         "marketplace": c.get("marketplaceId") or "", "model": funding.get("fundingModel") or "",
                         "rate": float(funding["bidPercentage"]) if funding.get("bidPercentage") else None,
                         "start": (c.get("startDate") or "")[:10], "end": (c.get("endDate") or "")[:10]})
        return rows
    return cached((reader.store.key, "campaigns"), load)


def ebay_campaigns(context: AgentContext, args: StoreOnlyArgs) -> ToolResult:
    require_all_ebay(context)
    stores, results, failed = run_stores(args.store, _campaigns)
    names = {s.key: s.name for s in stores}
    rows = [{"store": names[k], **c} for k, items in results.items() for c in items]
    rows.sort(key=lambda r: (r["status"] != "RUNNING", r["store"]))
    running = [r for r in rows if r["status"] == "RUNNING"]
    rates = [r["rate"] for r in running if r["rate"] is not None]
    return ToolResult(
        title="eBay 广告推广活动",
        summary={"店铺数": len(results), "活动数": len(rows), "进行中": len(running),
                 "进行中平均广告费率%": round(sum(rates) / len(rates), 2) if rates else None},
        columns=[("store", "店铺"), ("name", "活动名称"), ("status", "状态"), ("marketplace", "站点"),
                 ("model", "计费方式"), ("rate", "广告费率%"), ("start", "开始"), ("end", "结束")],
        rows=rows, source="eBay Marketing API（实时）", period="查询时点",
        notes=["只列出活动设置，不含点击和归因销售；期间实际广告费请查 eBay 财务汇总里的「广告费」。"]
        + failure_notes(stores, failed))


def _live(name: str, description: str, args_model, handler, permission: str, title: str) -> Tool:
    return Tool(name, description, args_model, handler, permission=permission, title=title,
                data_scope_all=SCOPE_EBAY, timeout_sec=LIVE_TIMEOUT_SEC, requires_source=EBAY_SOURCE)


EBAY_LIVE_TOOLS = [
    _live("ebay_orders_summary", "查询 eBay 实时订单：指定日期（默认近7天，最多31天）的订单数、件数、销售额（原币），"
          "可按店铺/日期/站点/SKU 分组。用于「今天、本周、最近几天」这类实时问题；月度业绩用销售看板或绩效排名。",
          OrdersArgs, ebay_orders_summary, PERM_SALES, "查询eBay实时订单"),
    _live("ebay_finance_summary", "查询 eBay 财务汇总：期间内销售入账、成交费、广告费、退款、纠纷扣款、净额、已放款，"
          "以及当前余额和冻结金额（按店铺，结算币种）。", LiveArgs, ebay_finance_summary, PERM_SALES, "查询eBay财务"),
    _live("ebay_after_sales", "查询 eBay 退货、未收到货、个案、付款纠纷的数量与待处理数（按店铺，实时），可返回明细。",
          AfterSalesArgs, ebay_after_sales, PERM_RETURNS, "查询eBay退货纠纷"),
    _live("ebay_seller_standards", "查询 eBay 卖家等级：各考核站点等级、不良交易率、延迟发货率、未解决个案率（当前考核周期）。",
          StoreOnlyArgs, ebay_seller_standards, PERM_RETURNS, "查询eBay卖家等级"),
    _live("ebay_traffic", "查询 eBay 刊登流量：曝光、浏览、成交及转化率（截止昨天，最多90天），可按店铺/日期/站点分组。"
          "按店铺有调用额度，尽量指定店铺或站点。", TrafficArgs, ebay_traffic, PERM_SALES, "查询eBay流量"),
    _live("ebay_campaigns", "查询 eBay 广告推广活动的设置：状态、站点、计费方式、广告费率。",
          StoreOnlyArgs, ebay_campaigns, PERM_SALES, "查询eBay广告活动"),
]
