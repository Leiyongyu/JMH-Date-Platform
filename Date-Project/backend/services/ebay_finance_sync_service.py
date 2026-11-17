"""eBay 月度利润表数据拉取（一）：eBay Finances 交易流水，按店铺、按自然月（美国太平洋时间）。

口径与卖家后台「Transaction report」逐条一致（2026-10 全部 35 家有授权的店铺逐店核对：条数、净额相同）：
- 所有店铺都注册在美国站、按美元放款，后台报告的月份按太平洋时间（PDT/PST）切，这里同样按太平洋时间取整月。
- 一条交易可能含多个商品行（多件订单）：拆成每个商品行一行，SKU / 标题 / 数量取 Fulfillment 订单接口，
  成交费按行项目的 marketplaceFees；各行净额按行折算后合计严格等于这条交易的净额（尾差放在最后一行）。
- 交易类型 → 报表口径（与后台报告的 Type 对照，2026-10 逐条核实）：
    SALE → 订单；REFUND + 退货/取消/退款单号 → 退款；REFUND + 案件号(CASE_ID) → 索赔；
    REFUND + 付款纠纷号 → 付款纠纷；DISPUTE（冻结）、带关联单号的 CREDIT（解冻）→ 冻结；
    没有关联单号的 CREDIT → 索赔（平台补款）；NON_SALE_CHARGE 按费用类型分广告费 / 刊登费；
    SHIPPING_LABEL → 运单；ADJUSTMENT → 调整；其他 → 其他。
- 金额：net_amount 是放款币种（美元）的带符号净额；gross / 各项费用是交易币种的带符号金额，
  fx_rate 是交易币种 → 放款币种的折算率（eBay 实际使用的），报表按「交易币种 × fx_rate × 中行美元价」折人民币。
  人民币不在这里算：中行汇率由财务在页面录入，可以在拉取后补录或修改。
- 每次拉取按店铺整月替换；某家店拉取失败不影响其他店，失败店保留上一次的数据并记入结果。
- 只发 GET，不改动 eBay 上的任何东西。
"""
from __future__ import annotations

import logging
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, time, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any, Iterable, Sequence
from uuid import uuid4
from zoneinfo import ZoneInfo

from backend.agent import ebay_live as live
from backend.repositories import ebay_monthly_profit_repository as repo
from backend.services.amazon_profit_sync_service import previous_natural_month

LOG = logging.getLogger(__name__)
TASK_CODE = "ebay_finance_monthly_sync"
TASK_NAME = "eBay月度利润表-交易流水拉取"
PT = ZoneInfo("America/Los_Angeles")
ZERO = Decimal("0")
TX_PATH = "/sell/finances/v1/transaction"
ORDER_PATH = "/sell/fulfillment/v1/order"
TX_PAGE = 1000
ORDER_BATCH = 50
MAX_TX_PER_STORE = 200_000
WORKERS = 4

# 广告费：与手工表同一规则——描述里含 ads / value fee / promoted（推广刊登、站外推广、成交费类）；
# 其余非销售费用（刊登费、副标题、跨国费、店铺订阅费等）归刊登 / 副标题。描述为空时按费用类型兜底。
AD_MEMO_WORDS = ("ads", "value fee", "promoted")
AD_FEE_TYPES = frozenset({"AD_FEE", "PREMIUM_AD_FEES", "FINAL_VALUE_FEE", "FINAL_VALUE_FEE_FIXED_PER_ORDER"})
# 订单 / 退款行上的费用列（与后台报告一致）。
FVF_FEES = {"FINAL_VALUE_FEE_FIXED_PER_ORDER": "fvf_fixed", "FINAL_VALUE_FEE": "fvf_variable",
            "REGULATORY_OPERATING_FEE": "regulatory_fee", "INTERNATIONAL_FEE": "international_fee"}
PENALTY_FEES = {"HIGH_ITEM_NOT_AS_DESCRIBED_FEE": "inad_fee", "BELOW_STANDARD_FEE": "below_standard_fee"}
FEE_COLUMNS = ("fvf_fixed", "fvf_variable", "regulatory_fee", "international_fee", "inad_fee",
               "below_standard_fee", "other_line_fee")
CATEGORIES = ("ORDER", "REFUND", "CLAIM", "PAYMENT_DISPUTE", "HOLD", "AD_FEE", "LISTING_FEE",
              "SHIPPING_LABEL", "ADJUSTMENT", "OTHER")
REFUND_REFS = {"RETURN_ID", "CANCELLATION_ID", "REFUND_ID"}


class EbayFinanceSyncError(RuntimeError):
    def __init__(self, stage: str, message: str, metrics: dict[str, Any] | None = None):
        super().__init__(message)
        self.stage = stage
        self.metrics = metrics or {}


# ------------------------------------------------------------ 小工具
def month_window(month: str) -> tuple[datetime, datetime]:
    """太平洋时间整月 → UTC 起止（含首不含尾）。夏令时切换由时区库处理。"""
    year, number = (int(part) for part in month.split("-"))
    start = datetime.combine(date(year, number, 1), time(0), PT)
    end = datetime.combine(date(year + number // 12, number % 12 + 1, 1), time(0), PT)
    return start.astimezone(timezone.utc), end.astimezone(timezone.utc)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.") + f"{value.microsecond // 1000:03d}Z"


def _dec(value: Any) -> Decimal:
    if value in (None, ""):
        return ZERO
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return ZERO


def _money(node: dict | None) -> tuple[Decimal, str | None]:
    if not isinstance(node, dict):
        return ZERO, None
    return _dec(node.get("value")), node.get("currency")


def _parse_time(text: str | None) -> datetime | None:
    if not text:
        return None
    try:
        return datetime.fromisoformat(str(text).replace("Z", "+00:00"))
    except ValueError:
        return None


def _refs(tx: dict) -> dict[str, list[str]]:
    out: dict[str, list[str]] = defaultdict(list)
    for item in tx.get("references") or []:
        if item.get("referenceType") and item.get("referenceId"):
            out[item["referenceType"]].append(str(item["referenceId"]))
    return out


def classify(tx: dict) -> str:
    """交易 → 报表口径（见模块说明）。"""
    kind = tx.get("transactionType")
    refs = set(_refs(tx))
    if kind == "SALE":
        return "ORDER"
    if kind == "REFUND":
        if "CASE_ID" in refs:
            return "CLAIM"
        if "PAYMENTS_DISPUTE_ID" in refs:
            return "PAYMENT_DISPUTE"
        return "REFUND"
    if kind == "DISPUTE":
        return "HOLD"
    if kind == "CREDIT":
        return "HOLD" if refs else "CLAIM"
    if kind == "NON_SALE_CHARGE":
        memo = str(tx.get("transactionMemo") or "").lower()
        if memo:
            return "AD_FEE" if any(word in memo for word in AD_MEMO_WORDS) else "LISTING_FEE"
        return "AD_FEE" if tx.get("feeType") in AD_FEE_TYPES else "LISTING_FEE"
    if kind == "SHIPPING_LABEL":
        return "SHIPPING_LABEL"
    if kind == "ADJUSTMENT":
        return "ADJUSTMENT"
    return "OTHER"


def _fx(tx: dict) -> tuple[Decimal, str]:
    """交易币种 → 放款币种折算率与交易币种。没有折算（同币种）时为 1。"""
    amount, payout_currency = _money(tx.get("amount"))
    node = tx.get("amount") or {}
    converted = _dec(node.get("convertedFromValue"))
    tx_currency = node.get("convertedFromCurrency") or payout_currency
    if converted and amount:
        return (amount / converted), tx_currency
    return Decimal(1), tx_currency


# ------------------------------------------------------------ 规范化（纯函数）
def normalize(store_name: str, tx: dict, orders: dict[str, dict], item_skus: dict[str, str],
              month: str) -> list[dict[str, Any]]:
    """一条交易 → 一或多行（多件订单按商品行拆开）。金额带符号：收入为正、支出为负。"""
    sign = Decimal(1) if tx.get("bookingEntry") == "CREDIT" else Decimal(-1)
    net_payout, payout_currency = _money(tx.get("amount"))
    net_payout *= sign
    fx, tx_currency = _fx(tx)
    converted = _dec((tx.get("amount") or {}).get("convertedFromValue"))
    # 交易币种净额：接口给了原币金额就直接用（精确），同币种时等于放款净额。
    net_tx = sign * converted if converted else net_payout
    category = classify(tx)
    refs = _refs(tx)
    created = _parse_time(tx.get("transactionDate"))
    order_id = tx.get("orderId")
    order = orders.get(order_id) if order_id else None
    order_lines = {str(li.get("lineItemId")): li for li in (order or {}).get("lineItems") or []}
    item_ids = refs.get("ITEM_ID") or []
    base = {
        "stat_month": month, "store_name": store_name, "transaction_id": str(tx.get("transactionId")),
        "transaction_type": tx.get("transactionType"), "transaction_status": tx.get("transactionStatus"),
        "booking_entry": tx.get("bookingEntry"), "category": category,
        "transaction_time_utc": created.astimezone(timezone.utc).replace(tzinfo=None) if created else None,
        "transaction_date_pt": created.astimezone(PT).date() if created else None,
        "order_id": order_id, "payout_id": tx.get("payoutId"), "fee_type": tx.get("feeType"),
        "memo": (str(tx.get("transactionMemo"))[:500] if tx.get("transactionMemo") else None),
        "reference_text": ";".join(f"{k}:{v}" for k, values in sorted(refs.items()) for v in values)[:500] or None,
        "payout_currency": payout_currency, "tx_currency": tx_currency, "fx_rate": fx,
        "ebay_tax": ZERO,
    }
    lines = (tx.get("orderLineItems") or []) if category in ("ORDER", "REFUND", "CLAIM", "PAYMENT_DISPUTE") else []
    out: list[dict[str, Any]] = []
    if lines:
        tax_total, _ = _money(tx.get("ebayCollectedTaxAmount"))
        bases = [_money(li.get("feeBasisAmount"))[0] for li in lines]
        basis_sum = sum(bases, ZERO)
        for index, li in enumerate(lines, 1):
            fees = {column: ZERO for column in FEE_COLUMNS}
            for fee in li.get("marketplaceFees") or []:
                value, _ = _money(fee.get("amount"))
                column = FVF_FEES.get(fee.get("feeType")) or PENALTY_FEES.get(fee.get("feeType")) or "other_line_fee"
                fees[column] += value
            detail = order_lines.get(str(li.get("lineItemId"))) or {}
            sku = (str(detail.get("sku"))[:200] if detail.get("sku") else None)
            item_id = detail.get("legacyItemId") or (item_ids[0] if item_ids else None)
            row = {**base, "line_no": index, "line_item_id": li.get("lineItemId"),
                   "item_id": item_id, "sku": sku or (item_skus.get(str(item_id)) if item_id else None),
                   "title": (str(detail.get("title"))[:500] if detail.get("title") else None),
                   "quantity": detail.get("quantity"),
                   **{column: -sign * value for column, value in fees.items()},
                   "ebay_tax": sign * tax_total if index == 1 else ZERO}
            out.append(row)
        # 毛额（商品小计 + 运费，不含 eBay 代收税）= 净额 − 费用；按行项目的计费基数分到各行，尾差放最后一行。
        fees_total = sum((row[c] for row in out for c in FEE_COLUMNS), ZERO)
        gross_total = net_tx - fees_total
        allocated_gross, allocated_net = ZERO, ZERO
        for index, row in enumerate(out):
            last = index == len(out) - 1
            share = (bases[index] / basis_sum) if basis_sum else Decimal(1) / len(out)
            gross = (gross_total - allocated_gross) if last else (gross_total * share).quantize(
                Decimal("0.0001"), rounding=ROUND_HALF_UP)
            allocated_gross += gross
            row["gross_amount"] = gross
            line_net = ((gross + sum((row[c] for c in FEE_COLUMNS), ZERO)) * fx).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP)
            row["net_amount"] = (net_payout - allocated_net) if last else line_net
            allocated_net += row["net_amount"]
    else:
        fee_total, _ = _money(tx.get("totalFeeAmount"))
        gross_tx = net_tx - (-sign * fee_total)
        line = next(iter(order_lines.values()), {}) if order_lines else {}
        item_id = item_ids[0] if item_ids else line.get("legacyItemId")
        sku = line.get("sku") or (item_skus.get(str(item_id)) if item_id else None)
        out.append({**base, "line_no": 1, "line_item_id": None, "item_id": item_id, "sku": sku or None,
                    "title": (str(line.get("title"))[:500] if line.get("title") else None), "quantity": None,
                    "gross_amount": gross_tx.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP),
                    **{column: ZERO for column in FEE_COLUMNS},
                    "other_line_fee": (-sign * fee_total), "net_amount": net_payout})
    return out


# ------------------------------------------------------------ 拉取
def fetch_store(store: live.StoreTarget, month: str) -> dict[str, Any]:
    """一家店当月的交易 + 订单详情。只读。"""
    reader = live.StoreReader(store)
    marketplace = reader.registration_marketplace()
    start, end = month_window(month)
    flt = f"transactionDate:[{_iso(start)}..{_iso(end - timedelta(milliseconds=1))}]"
    txs, offset = [], 0
    while True:
        page = reader.get(TX_PATH, {"filter": flt, "limit": TX_PAGE, "offset": offset},
                          host="apiz", marketplace=marketplace)
        items = page.get("transactions") or []
        txs += items
        offset += len(items)
        if not items or offset >= int(page.get("total") or 0):
            break
        if len(txs) > MAX_TX_PER_STORE:
            raise EbayFinanceSyncError("拉取交易", f"{store.name} 当月交易超过 {MAX_TX_PER_STORE} 条，未截断，请核实")
    order_ids = sorted({t.get("orderId") for t in txs if t.get("orderId")})
    orders: dict[str, dict] = {}
    for index in range(0, len(order_ids), ORDER_BATCH):
        batch = order_ids[index:index + ORDER_BATCH]
        data = reader.get(ORDER_PATH, {"orderIds": ",".join(batch)})
        for order in data.get("orders") or []:
            orders[str(order.get("orderId"))] = order
    return {"marketplace": marketplace, "transactions": txs, "orders": orders}


def normalize_store(store_name: str, fetched: dict[str, Any], item_skus: dict[str, str],
                    month: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for tx in fetched["transactions"]:
        rows.extend(normalize(store_name, tx, fetched["orders"], item_skus, month))
    return rows


def _month(value: str | None) -> str:
    text = str(value or "").strip()
    if not text:
        return previous_natural_month()
    datetime.strptime(text, "%Y-%m")
    return text


def sync_ebay_finance(stat_month: str | None = None, *, stores: Sequence[live.StoreTarget] | None = None) -> dict[str, Any]:
    """拉取并按店铺整月替换。返回与调度结果一致的统计。"""
    month = _month(stat_month)
    batch_id = uuid4().hex
    pulled_at = datetime.now(ZoneInfo("Asia/Shanghai")).replace(tzinfo=None)
    targets = list(stores or live.store_targets())
    if not targets:
        raise EbayFinanceSyncError("店铺列表", "没有可用的 eBay 店铺凭证")
    item_skus = repo.listing_item_skus()
    results, failures = {}, {}

    def one(store):
        try:
            return store, fetch_store(store, month), None
        except (live.EbayReadError, EbayFinanceSyncError) as exc:
            return store, None, f"{getattr(exc, 'kind', 'ERROR')} {exc}"[:300]

    with ThreadPoolExecutor(WORKERS) as pool:
        for store, fetched, error in pool.map(one, targets):
            if error:
                failures[store.name] = error
                LOG.warning("eBay交易拉取失败 store=%s %s", store.name, error)
                continue
            results[store.name] = normalize_store(store.name, fetched, item_skus, month)
    if not results:
        raise EbayFinanceSyncError("拉取交易", "全部店铺拉取失败：" + "；".join(f"{k} {v}" for k, v in failures.items())[:800])
    written = repo.replace_finance_rows(month, results, batch_id=batch_id, pulled_at=pulled_at)
    categories: dict[str, int] = defaultdict(int)
    for rows in results.values():
        for row in rows:
            categories[row["category"]] += 1
    return {
        "stat_month": month, "sync_batch_id": batch_id,
        "pulled_at": pulled_at.strftime("%Y-%m-%d %H:%M:%S"),
        "extract_rows": sum(len(rows) for rows in results.values()), "ods_rows": written,
        "store_count": len(results), "failed_stores": failures,
        "missing_sku_rows": sum(1 for rows in results.values() for row in rows
                                if not row.get("sku") and row["category"] in ("ORDER", "REFUND", "CLAIM")),
        "category_rows": dict(categories),
    }
