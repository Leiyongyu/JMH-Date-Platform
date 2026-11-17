"""eBay 月度利润表（财务中心）：照财务手工表「利润明细表-ebay」的「汇总」「ebay个人」出数，并按店铺拆开。

数据（都按月）：
- 交易流水：eBay Finances 接口（ebay_finance_sync_service），与后台「Transaction report」逐条一致。
- 采购成本、头程运费：「SKU分析」导入的数字酋长订单文件，按平台订单号对上交易里的订单。
- 海外仓尾程、仓储：谷仓账单（goodcang_bill_sync_service）。仓储按人分摊用谷仓仓租明细（每周同步）。
- 超龄货值（海外 91～180 天、180 天以上）、成都仓 30 天以上：与滞销清货同一套库龄快照，按站点、按负责人。
- 汇率：财务录入的中行折算价月均值；其余手工数（店铺运营费、积分抵扣、GU仓销毁、借货清货等）走补充费用。

口径（与手工表公式一致）：
- 每条交易折人民币：交易币种金额 × eBay 实际折算率 × 中行美元价，各列逐行四舍五入到分（同 Excel ROUND）。
  平台收入 = 销售总额（商品小计+运费）+ 退款 + 赔偿；平台支出 = 成交费 + 罚款 + 广告费 + 刊登/副标题 + 其他费用；
  平台净收入 = 各交易净额之和（含税费差，所以 ≠ 收入 + 支出）。
- 站点：按交易币种，USD → US，EUR → DE，GBP → UK；US 一组，其余为 EU。负责人按 SKU 品牌规则（当月），
  没有 SKU 或品牌未分配的金额按各人平台收入占比分摊。
- 资金占用费 = −（海外 91～180 天货值 × 12% + 180 天以上 × 24% + 成都仓 30 天以上 × 12%）× 30 / 360；
  税务风险金 = −平台收入 × 1%。
- 店铺运营费、GU仓销毁按总额录入：站点 US 1/2、DE 1/4、UK 1/4（GU仓销毁三站各 1/3），个人平均分。
- 仓储（个人）：仓租明细按 SKU 归人，账单仓储费与明细的差额平均分给每个人（与手工表一致）。
- 比率分母为 0 时返回 None（页面 --）。
"""
from __future__ import annotations

import logging
import re
from collections import defaultdict
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from io import BytesIO
from typing import Any, Callable, Sequence

from backend.config import settings
from backend.repositories import ebay_monthly_profit_repository as repo
from backend.repositories import inventory_report_etl_repository as owner_repo
from backend.services.inventory_report_etl_service import _ebay_assignment, _ebay_rule_map

LOG = logging.getLogger(__name__)
ZERO = Decimal("0")
CENT = Decimal("0.01")
RATE = Decimal("0.000001")
MONTH = re.compile(r"^20\d{2}-(0[1-9]|1[0-2])$")
UNASSIGNED = "未分配"
MAX_ADJUSTMENT = Decimal("100000000")
SITES = ("US", "DE", "UK")
SITE_BY_CURRENCY = {"USD": "US", "EUR": "DE", "GBP": "UK"}
SITE_GROUP = {"US": "US", "DE": "EU", "UK": "EU"}
TAX_RISK_RATE = Decimal("0.01")
CAPITAL_RATES = (("over_90_180", Decimal("0.12")), ("over_180", Decimal("0.24")), ("ctu_30", Decimal("0.12")))
# 总额录入的项目怎么分到站点（个人一律平均分）。
SITE_SPLITS = {"store_operation": {"US": Decimal("0.5"), "DE": Decimal("0.25"), "UK": Decimal("0.25")},
               "gu_destruction": {site: Decimal(1) / 3 for site in SITES}}

# 补充费用：key → (名称, 可记的行)。行：SITE = US/DE/UK，ALL = 总额（按规则分），OWNER = 负责人。
ADJUSTMENT_ITEMS = (
    ("store_operation", "店铺运营费用（紫鸟等）", ("ALL",)),
    ("gu_destruction", "GU仓销毁", ("ALL",)),
    ("points", "积分抵扣", ("SITE", "OWNER")),
    ("purchase_freight", "采购运费", ("SITE",)),
    ("first_leg_duty", "头程关税", ("SITE",)),
    ("loan_clear", "调整项（借货/清货）", ("SITE",)),
    ("ctu_discount", "调整项（成都仓折扣）", ("SITE",)),
    ("packaging", "包装耗材费", ("SITE",)),
    ("brushing", "刷单SKU采购成本抵扣", ("SITE",)),
    ("supplement", "其他补充费用", ("SITE", "OWNER")),
)
ADJUSTMENT_LABELS = {key: label for key, label, _ in ADJUSTMENT_ITEMS}
ADJUSTMENT_SCOPES = {key: scopes for key, _, scopes in ADJUSTMENT_ITEMS}

PLATFORM_KEYS = ("sales", "refund", "claim", "fvf", "penalty", "ads", "listing", "other_fee", "net")
INCOME_KEYS = ("sales", "refund", "claim")
EXPENSE_KEYS = ("fvf", "penalty", "ads", "listing", "other_fee")

SITE_COLUMNS = (
    ("platform_income", "平台收入", "money"), ("platform_expense", "平台支出", "money"),
    ("platform_net", "平台净收入", "money"), ("purchase_cost", "销售采购成本", "money"),
    ("purchase_freight", "采购运费", "money"), ("first_leg_cost", "头程成本", "money"),
    ("first_leg_duty", "头程关税", "money"), ("tail_fee", "海外仓-尾程", "money"),
    ("storage_fee", "海外仓-仓储", "money"), ("store_operation", "店铺运营费用", "money"),
    ("loan_clear", "调整项（借货/清货）", "money"), ("ctu_discount", "调整项（成都仓折扣）", "money"),
    ("capital_cost", "资金占用费-超龄货值", "money"), ("packaging", "包装耗材费", "money"),
    ("brushing", "刷单抵扣", "money"), ("points", "积分抵扣", "money"), ("tax_risk", "税务风险金", "money"),
    ("gu_destruction", "GU仓销毁", "money"), ("supplement", "其他补充", "money"),
    ("gross_profit", "毛利", "money"), ("gross_margin", "毛利率", "rate"),
    ("ctu_30", "成都仓30天+货值", "money"), ("over_180", "超龄货值（180天+）", "money"),
    ("over_90_180", "超龄货值（91-180天）", "money"),
)
OWNER_COLUMNS = (
    ("platform_income", "平台收入", "money"), ("platform_expense", "平台支出", "money"),
    ("platform_payback", "平台回款额", "money"), ("platform_net", "实际平台回款额", "money"),
    ("purchase_cost", "销售产品成本", "money"), ("first_leg_cost", "头程成本", "money"),
    ("storage_fee", "仓储费", "money"), ("tail_fee", "海外仓物流成本（除仓租）", "money"),
    ("store_operation", "店铺运营费用", "money"), ("other_cost", "其他费用", "money"),
    ("points", "积分抵扣", "money"), ("gu_destruction", "GU仓销毁", "money"), ("supplement", "其他补充", "money"),
    ("gross_profit", "毛利", "money"), ("gross_margin", "毛利率", "rate"),
    ("net_ratio", "实际回款额占比", "rate"), ("purchase_ratio", "销售产品成本占比", "rate"),
    ("first_leg_ratio", "头程成本占比", "rate"), ("tail_ratio", "海外仓物流成本占比", "rate"),
    ("storage_ratio", "仓储费占比", "rate"),
    ("refund", "退款", "money"), ("refund_ratio", "退款占比", "rate"),
    ("claim", "赔偿", "money"), ("claim_ratio", "赔偿占比", "rate"),
    ("fvf", "成交费", "money"), ("fvf_ratio", "成交费占比", "rate"),
    ("penalty", "罚款", "money"), ("penalty_ratio", "罚款占比", "rate"),
    ("ads", "广告费", "money"), ("ads_ratio", "广告费占比", "rate"),
    ("listing", "刊登/副标题", "money"), ("other_fee", "其他平台费用", "money"),
    ("over_90_180", "91-180天成本", "money"), ("over_180", "180天+成本", "money"), ("ctu_30", "成都仓30天+成本", "money"),
)
STORE_COLUMNS = (
    ("platform_income", "平台收入", "money"), ("platform_expense", "平台支出", "money"),
    ("platform_net", "平台净收入", "money"), ("purchase_cost", "采购成本", "money"),
    ("first_leg_cost", "头程成本", "money"), ("tail_fee", "海外仓尾程", "money"),
    ("gross_profit", "店铺毛利（未含仓储及分摊项）", "money"), ("gross_margin", "毛利率", "rate"),
    ("sales", "销售总额", "money"), ("refund", "退款", "money"), ("claim", "赔偿", "money"),
    ("fvf", "成交费", "money"), ("penalty", "罚款", "money"), ("ads", "广告费", "money"),
    ("listing", "刊登/副标题", "money"), ("other_fee", "其他费用", "money"), ("order_count", "订单数", "qty"),
)


# ------------------------------------------------------------ 小工具
def _month(value: str | None) -> str:
    text = str(value or "").strip()
    if not MONTH.match(text):
        raise ValueError("月份格式应为 YYYY-MM")
    return text


def _num(value: Any) -> Decimal:
    if value is None or value == "":
        return ZERO
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return ZERO


def _round(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def _ratio(numerator: Decimal, denominator: Decimal) -> Decimal | None:
    if not denominator:
        return None
    return (numerator / denominator).quantize(RATE, rounding=ROUND_HALF_UP)


def _base_sku(value: Any) -> str | None:
    """「JMH-30477-0740*1」「A;B」→ 第一个 SKU，去掉数量后缀。"""
    if not value:
        return None
    text = str(value).replace(",", ";").split(";")[0].split("*")[0].strip().upper()
    return text or None


def _text_time(value: Any) -> str | None:
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M:%S")
    return str(value) if value else None


# ------------------------------------------------------------ 交易折人民币（逐行，同 Excel ROUND）
def transaction_amounts(row: dict[str, Any], usd_rate: Decimal) -> dict[str, Decimal]:
    fx = _num(row.get("fx_rate")) or Decimal(1)
    factor = fx * usd_rate
    gross = _num(row.get("gross_amount"))
    category = row.get("category")
    out = {key: ZERO for key in PLATFORM_KEYS}
    out["net"] = _num(row.get("net_amount")) * usd_rate
    if category == "ORDER":
        out["sales"] = _round(gross * factor)
    elif category == "REFUND":
        out["refund"] = _round(gross * factor)
    elif category == "CLAIM":
        out["claim"] = _round(gross * factor)
    elif category == "AD_FEE":
        out["ads"] = _round(gross * factor)
    elif category == "LISTING_FEE":
        out["listing"] = _round(gross * factor)
    else:
        out["other_fee"] = _round(gross * factor)
    out["fvf"] = _round(sum((_num(row.get(key)) for key in
                             ("fvf_fixed", "fvf_variable", "regulatory_fee", "international_fee")), ZERO) * factor)
    out["penalty"] = _round((_num(row.get("inad_fee")) + _num(row.get("below_standard_fee"))) * factor)
    return out


def _site_of(currency: Any) -> tuple[str, str | None]:
    site = SITE_BY_CURRENCY.get(str(currency or "").upper())
    return (SITE_GROUP[site], site) if site else ("EU", None)


# ------------------------------------------------------------ 报表（纯计算）
def _empty() -> dict[str, Decimal]:
    return defaultdict(Decimal)


def build_report(month: str, rows: Sequence[dict[str, Any]], *, rates: dict[str, Decimal],
                 owner_of: Callable[[str | None], str | None], costs: dict[str, tuple[Any, Any]],
                 bills: Sequence[dict[str, Any]], storage: Sequence[dict[str, Any]],
                 age: dict[str, Any], adjustments: Sequence[dict[str, Any]],
                 owners: Sequence[str]) -> dict[str, Any]:
    notices: list[str] = []
    usd = _num(rates.get("USD"))
    site: dict[str, dict[str, Decimal]] = defaultdict(_empty)
    owner: dict[str, dict[str, Decimal]] = defaultdict(_empty)
    store: dict[str, dict[str, Decimal]] = defaultdict(_empty)
    order_place: dict[str, tuple[str, str | None, str, str]] = {}

    def owner_key(sku):
        name = owner_of(_base_sku(sku)) if sku else None
        return name if name and name != UNASSIGNED else ""

    # 调整类交易（如卖家共同出资优惠券）只有美元金额、看不出站点：按店铺当月销售额最多的站点归属（同手工表）。
    main_site = _store_main_sites(rows, usd)

    # 1. 交易
    for row in rows:
        amounts = transaction_amounts(row, usd)
        group, site_code = _site_of(row.get("tx_currency"))
        if row.get("category") == "ADJUSTMENT" and main_site.get(row["store_name"]):
            site_code = main_site[row["store_name"]]
            group = SITE_GROUP[site_code]
        who = owner_key(row.get("sku"))
        targets = _targets(site, group, site_code) + [owner[who], store[row["store_name"]]]
        for target in targets:
            for key, value in amounts.items():
                target[key] += value
        if row.get("category") == "ORDER" and row.get("order_id") and row["order_id"] not in order_place:
            order_place[row["order_id"]] = (group, site_code, who, row["store_name"])

    # 2. 采购成本、头程（按订单）
    missing_cost = 0
    for order_id, (group, site_code, who, store_name) in order_place.items():
        cost = costs.get(order_id)
        if cost is None:
            missing_cost += 1
            continue
        purchase, first_leg = -_num(cost[0]), -_num(cost[1])
        for target in _targets(site, group, site_code) + [owner[who], store[store_name]]:
            target["purchase_cost"] += purchase
            target["first_leg_cost"] += first_leg
            target["order_count"] += 1
    if order_place and missing_cost:
        notices.append(f"{missing_cost} / {len(order_place)} 个订单在「SKU分析」导入的订单文件里没有采购成本（按 0 计）")

    # 3. 谷仓账单：尾程、仓储
    store_of_order = {order_id: place[3] for order_id, place in order_place.items()}
    missing_rates = set()
    storage_total = ZERO
    for bill in bills:
        if not str(bill.get("platform") or "").upper().startswith("EBAY"):
            continue
        currency = str(bill.get("currency") or "").upper()
        rate = _num(rates.get(currency))
        if not rate:
            missing_rates.add(currency)
            continue
        value = -_num(bill.get("amount")) * rate
        group, site_code = _site_of(currency)
        key = "storage_fee" if bill.get("fee_type") == "仓储费" else "tail_fee"
        for target in _targets(site, group, site_code):
            target[key] += value
        if key == "storage_fee":
            storage_total += value
            continue
        owner[owner_key(bill.get("sku"))]["tail_fee"] += value
        store_name = store_of_order.get(str(bill.get("related_no") or ""))
        if store_name:
            store[store_name]["tail_fee"] += value

    # 4. 仓储按人：仓租明细按 SKU 归人，账单与明细的差额平均分
    assigned = defaultdict(Decimal)
    for item in storage:
        rate = _num(rates.get(str(item.get("currency") or "").upper()))
        if not rate:
            missing_rates.add(str(item.get("currency") or "").upper())
            continue
        who = owner_key(item.get("product_sku"))
        if who:
            assigned[who] -= _num(item.get("amount")) * rate
    if missing_rates:
        notices.append("缺少中行汇率：" + "、".join(sorted(code for code in missing_rates if code)) + "，这些币种的谷仓费用未计入")

    # 5. 人员名单：当月规则里的负责人 + 实际出现的人
    people = [name for name in owners if name and name != UNASSIGNED]
    people += sorted(name for name in owner if name and name not in people)
    if not storage:
        notices.append("当月没有谷仓仓租明细，个人仓储费按人平均分")
    remainder = storage_total - sum(assigned.values(), ZERO)
    for name in people:
        owner[name]["storage_fee"] += assigned.get(name, ZERO) + (remainder / len(people) if people else ZERO)

    # 6. 未归属金额按平台收入占比分给每个人
    blank = owner.pop("", None)
    if blank:
        income_of = {name: sum((owner[name][key] for key in INCOME_KEYS), ZERO) for name in people}
        total_income = sum(income_of.values(), ZERO)
        for name in people:
            share = (income_of[name] / total_income) if total_income else (Decimal(1) / len(people))
            for key, value in blank.items():
                if key == "order_count":
                    continue
                owner[name][key] += value * share
        unassigned_income = sum((blank[key] for key in INCOME_KEYS), ZERO)
        if unassigned_income:
            notices.append(f"没有 SKU 或品牌未分配的平台收入 {_round(unassigned_income)} 元，已按各人收入占比分摊")

    # 7. 库龄与成都仓（自动）
    for code in SITES:
        for key in ("over_90_180", "over_180", "ctu_30"):
            site[code][key] += _num(age.get("site", {}).get(code, {}).get(key))
    for name in people:
        for key in ("over_90_180", "over_180", "ctu_30"):
            owner[name][key] += _num(age.get("owner", {}).get(name, {}).get(key))
    notices.extend(age.get("notices") or [])

    # 8. 补充费用
    applied = 0
    for item in adjustments:
        fee, code, amount = str(item.get("fee_item")), str(item.get("row_code")), _num(item.get("amount"))
        if fee not in ADJUSTMENT_LABELS:
            continue
        if code == "ALL" and "ALL" in ADJUSTMENT_SCOPES[fee]:
            for site_code, share in SITE_SPLITS[fee].items():
                site[site_code][fee] += amount * share
            for name in people:
                owner[name][fee] += amount / len(people) if people else ZERO
        elif code in SITES and "SITE" in ADJUSTMENT_SCOPES[fee]:
            site[code][fee] += amount
        elif code in people and "OWNER" in ADJUSTMENT_SCOPES[fee]:
            owner[code][fee] += amount
        else:
            continue
        applied += 1
    # 总额项与站点项分别加到 EU
    for code in ("DE", "UK"):
        for item in ADJUSTMENT_ITEMS:
            site["EU"][item[0]] += site[code][item[0]]
        for key in ("over_90_180", "over_180", "ctu_30"):
            site["EU"][key] += site[code][key]

    # 9. 出行
    site_rows = [_site_row(code, site[code]) for code in ("US", "EU", "DE", "UK")]
    site_total = _site_row("TOTAL", _sum(site["US"], site["EU"]))
    owner_rows = [_owner_row(name, owner[name]) for name in people]
    owner_total = _owner_row("TOTAL", _sum(*(owner[name] for name in people)))
    store_rows = sorted((_store_row(name, values) for name, values in store.items()),
                        key=lambda item: -(item["platform_income"] or ZERO))
    store_total = _store_row("TOTAL", _sum(*store.values()))
    return {"stat_month": month, "currency_code": "CNY", "site_rows": site_rows, "site_total": site_total,
            "owner_rows": owner_rows, "owner_total": owner_total, "store_rows": store_rows,
            "store_total": store_total, "adjustment_count": applied, "notices": notices,
            "store_count": len(store), "order_count": len(order_place), "transaction_rows": len(rows)}


def _targets(site: dict, group: str, site_code: str | None) -> list[dict[str, Decimal]]:
    """组别行 + 站点行；美国的组别与站点同为 US，只加一次。"""
    keys = [group] + ([site_code] if site_code and site_code != group else [])
    return [site[key] for key in keys]


def _store_main_sites(rows: Sequence[dict[str, Any]], usd: Decimal) -> dict[str, str]:
    sales: dict[str, dict[str, Decimal]] = defaultdict(lambda: defaultdict(Decimal))
    for row in rows:
        if row.get("category") == "ORDER":
            _, code = _site_of(row.get("tx_currency"))
            if code:
                sales[row["store_name"]][code] += _num(row.get("net_amount"))
    return {name: max(values, key=values.get) for name, values in sales.items() if values}


def _sum(*parts: dict[str, Decimal]) -> dict[str, Decimal]:
    total = _empty()
    for part in parts:
        for key, value in part.items():
            total[key] += value
    return total


def _platform(values: dict[str, Decimal]) -> dict[str, Decimal]:
    income = sum((values[key] for key in INCOME_KEYS), ZERO)
    expense = sum((values[key] for key in EXPENSE_KEYS), ZERO)
    return {"platform_income": income, "platform_expense": expense, "platform_net": values["net"]}


def _capital_cost(values: dict[str, Decimal]) -> Decimal:
    return -sum((values[key] * rate for key, rate in CAPITAL_RATES), ZERO) * 30 / 360


def _money_out(row: dict[str, Any], kinds: Sequence[tuple[str, str, str]]) -> dict[str, Any]:
    for key, _label, kind in kinds:
        value = row.get(key)
        if kind == "money" and isinstance(value, Decimal):
            row[key] = _round(value)
        elif kind == "qty" and isinstance(value, Decimal):
            row[key] = int(value)
    return row


def _site_row(code: str, values: dict[str, Decimal]) -> dict[str, Any]:
    platform = _platform(values)
    row: dict[str, Any] = {"row_code": code, **platform}
    for key in ("purchase_cost", "purchase_freight", "first_leg_cost", "first_leg_duty", "tail_fee", "storage_fee",
                "store_operation", "loan_clear", "ctu_discount", "packaging", "brushing", "points",
                "gu_destruction", "supplement", "ctu_30", "over_180", "over_90_180"):
        row[key] = values[key]
    row["capital_cost"] = _capital_cost(values)
    row["tax_risk"] = -platform["platform_income"] * TAX_RISK_RATE
    profit = platform["platform_net"] + sum((row[key] for key in (
        "purchase_cost", "purchase_freight", "first_leg_cost", "first_leg_duty", "tail_fee", "storage_fee",
        "store_operation", "loan_clear", "ctu_discount", "capital_cost", "packaging", "brushing", "points",
        "tax_risk", "gu_destruction", "supplement")), ZERO)
    row["gross_profit"] = profit
    row["gross_margin"] = _ratio(profit, platform["platform_income"])
    return _money_out(row, SITE_COLUMNS)


def _owner_row(name: str, values: dict[str, Decimal]) -> dict[str, Any]:
    platform = _platform(values)
    income = platform["platform_income"]
    row: dict[str, Any] = {"row_code": name, **platform,
                           "platform_payback": platform["platform_income"] + platform["platform_expense"]}
    for key in ("purchase_cost", "first_leg_cost", "storage_fee", "tail_fee", "store_operation", "points",
                "gu_destruction", "supplement", "refund", "claim", "fvf", "penalty", "ads", "listing", "other_fee",
                "over_90_180", "over_180", "ctu_30"):
        row[key] = values[key]
    row["other_cost"] = -income * TAX_RISK_RATE + _capital_cost(values)
    profit = platform["platform_net"] + sum((row[key] for key in (
        "purchase_cost", "first_leg_cost", "storage_fee", "tail_fee", "store_operation", "other_cost", "points",
        "gu_destruction", "supplement")), ZERO)
    row["gross_profit"] = profit
    row["gross_margin"] = _ratio(profit, income)
    for ratio, key in (("net_ratio", "platform_net"), ("purchase_ratio", "purchase_cost"),
                       ("first_leg_ratio", "first_leg_cost"), ("tail_ratio", "tail_fee"),
                       ("storage_ratio", "storage_fee"), ("claim_ratio", "claim"), ("fvf_ratio", "fvf"),
                       ("penalty_ratio", "penalty"), ("ads_ratio", "ads")):
        row[ratio] = _ratio(row[key], income)
    row["refund_ratio"] = _ratio(row["refund"], income + row["refund"])
    return _money_out(row, OWNER_COLUMNS)


def _store_row(name: str, values: dict[str, Decimal]) -> dict[str, Any]:
    platform = _platform(values)
    row: dict[str, Any] = {"row_code": name, "store_name": name, **platform}
    for key in ("purchase_cost", "first_leg_cost", "tail_fee", "sales", "refund", "claim", "fvf", "penalty",
                "ads", "listing", "other_fee", "order_count"):
        row[key] = values[key]
    profit = platform["platform_net"] + row["purchase_cost"] + row["first_leg_cost"] + row["tail_fee"]
    row["gross_profit"] = profit
    row["gross_margin"] = _ratio(profit, platform["platform_income"])
    return _money_out(row, STORE_COLUMNS)


# ------------------------------------------------------------ 库龄（复用滞销清货）
def _next_month(month: str) -> str:
    year, number = (int(part) for part in month.split("-"))
    return f"{year + 1}-01" if number == 12 else f"{year}-{number + 1:02d}"


def inventory_age(month: str) -> dict[str, Any]:
    """按站点、按负责人的海外 91～180 天、180 天以上库龄成本，以及成都仓 30 天以上成本。

    取「次月初」拍的那份库龄快照（反映当月底的库存）：2026-10 报表用 pull_month=2026-11，
    与财务手工表 202610 的超龄货值、成都仓 30 天以上逐项一致（部署机核对）。
    """
    pull_month = _next_month(month)
    from backend.repositories import clearance_repository as clearance_repo
    from backend.services import clearance_drilldown_service as clearance

    over_180_buckets = ("181_270", "271_365", "365_plus")
    out: dict[str, Any] = {"site": defaultdict(dict), "owner": defaultdict(dict), "notices": []}
    try:
        if pull_month not in {row["pull_month"] for row in clearance_repo.months(36)}:
            out["notices"].append(f"还没有 {pull_month} 初的库龄快照（滞销清货），超龄货值与成都仓 30 天以上按 0 计")
            return out
        sites = clearance_repo.list_site_dimensions(pull_month)
        for item in sites.get("items") or []:
            code = item.get("dimension_name") or item.get("dimension_key")
            if code in SITES:
                out["site"][code]["over_90_180"] = _num(item.get("inventory_91_180_cost"))
                out["site"][code]["over_180"] = sum((_num(item.get(f"inventory_{b}_cost")) for b in over_180_buckets), ZERO)
        owners = clearance.list_dimensions(pull_month, "EBAY-1", dimension="OWNER")
        ctu_total = ZERO
        for item in owners.get("items") or []:
            name = item.get("dimension_name")
            out["owner"][name]["over_90_180"] = _num(item.get("inventory_91_180_cost"))
            out["owner"][name]["over_180"] = sum((_num(item.get(f"inventory_{b}_cost")) for b in over_180_buckets), ZERO)
            out["owner"][name]["ctu_30"] = _num(item.get("ctu_over_30_cost"))
            ctu_total += _num(item.get("ctu_over_30_cost"))
        for code in SITES:  # 成都仓没有站点信息，按站点平均（与手工表一致）
            out["site"][code]["ctu_30"] = ctu_total / 3
    except Exception:  # 库龄是辅助列，取不到时不影响利润主表
        LOG.exception("eBay月度利润表读取库龄失败 pull_month=%s", pull_month)
        out["notices"].append(f"{pull_month} 库龄数据读取失败，超龄货值与成都仓 30 天以上按 0 计")
    return out


# ------------------------------------------------------------ 查询
def list_months(limit: int = 36) -> list[dict[str, Any]]:
    bills = {row["stat_month"]: row for row in repo.bill_months(limit)}
    return [{"stat_month": row["stat_month"], "transaction_rows": int(row["rows_"] or 0),
             "store_count": int(row["stores"] or 0), "pulled_at": _text_time(row.get("pulled_at")),
             "bill_rows": int((bills.get(row["stat_month"]) or {}).get("rows_") or 0)}
            for row in repo.finance_months(limit)]


def _previous_month(month: str) -> str:
    year, number = (int(part) for part in month.split("-"))
    return f"{year - 1}-12" if number == 1 else f"{year}-{number - 1:02d}"


def _owner_resolver(month: str):
    rules = _ebay_rule_map(owner_repo.owner_rules(month, "ebay"))
    # 领星产品资料按月快照，月初当月快照可能还没出：退回上一个月（JMH 仓库 SKU 还原品牌用）。
    sku_map = owner_repo.ebay_product_sku_map(month) or owner_repo.ebay_product_sku_map(_previous_month(month)) or {}
    cache: dict[str, str | None] = {}

    def resolve(sku):
        if not sku:
            return None
        if sku not in cache:
            cache[sku] = _ebay_assignment(sku, rules, sku_map)[0] or None
        return cache[sku]
    owners = sorted({value for value in rules.values() if value and value != UNASSIGNED})
    return resolve, owners


def excluded_store_names() -> set[str]:
    return {name.strip() for name in (settings.ebay_profit_excluded_stores or "").split(",") if name.strip()}


def get_report(month: str) -> dict[str, Any]:
    month = _month(month)
    all_rows = repo.finance_rows(month)
    if not all_rows:
        raise ValueError(f"{month} 还没有拉取 eBay 交易流水，请先在定时任务里执行「{'eBay月度利润表-交易流水拉取'}」")
    rates = {code: _num(value) for code, value in repo.rates(month).items()}
    if not rates.get("USD"):
        raise ValueError(f"请先录入 {month} 的中行折算价（至少 USD、EUR、GBP），再查看利润表")
    excluded_stores = excluded_store_names()
    rows = [row for row in all_rows if row["store_name"] not in excluded_stores]
    resolve, owners = _owner_resolver(month)
    bills = repo.bill_rows(month)
    report = build_report(month, rows, rates=rates, owner_of=resolve, costs=repo.order_costs(month),
                          bills=bills, storage=repo.storage_rows(month), age=inventory_age(month),
                          adjustments=repo.adjustments(month), owners=owners)
    if not bills:
        report["notices"].insert(0, f"{month} 还没有拉取谷仓账单，海外仓尾程、仓储按 0 计")
    skipped = len(all_rows) - len(rows)
    if skipped:
        names = sorted({row["store_name"] for row in all_rows if row["store_name"] in excluded_stores})
        report["notices"].append(f"已排除 AMZ 组店铺 {'、'.join(names)} 的 {skipped} 行交易（另计在 AMZ 利润里）")
    if not repo.order_cost_month_rows(month):
        report["notices"].insert(0, f"「SKU分析」还没有导入 {month} 的订单文件，采购成本、头程运费按 0 计")
    meta = next((item for item in repo.finance_months(120) if item["stat_month"] == month), {})
    report["pulled_at"] = _text_time(meta.get("pulled_at"))
    report["rates"] = {code: str(value) for code, value in sorted(rates.items())}
    report["owners"] = [row["row_code"] for row in report["owner_rows"]]
    report["adjustment_items"] = [{"key": key, "label": label, "scopes": list(scopes)}
                                  for key, label, scopes in ADJUSTMENT_ITEMS]
    report["site_columns"] = [{"key": k, "label": l, "kind": t} for k, l, t in SITE_COLUMNS]
    report["owner_columns"] = [{"key": k, "label": l, "kind": t} for k, l, t in OWNER_COLUMNS]
    report["store_columns"] = [{"key": k, "label": l, "kind": t} for k, l, t in STORE_COLUMNS]
    return report


# ------------------------------------------------------------ 汇率
def get_rates(month: str) -> list[dict[str, Any]]:
    month = _month(month)
    return [{**row, "rate": str(row["rate"]), "updated_at": _text_time(row.get("updated_at"))}
            for row in repo.rate_rows(month)]


def save_rates(month: str, values: dict[str, Any], operator: str | None) -> dict[str, Any]:
    month = _month(month)
    clean: dict[str, Decimal] = {}
    for code, raw in (values or {}).items():
        currency = str(code or "").strip().upper()
        if not re.match(r"^[A-Z]{3}$", currency):
            raise ValueError(f"币种代码无效：{code}")
        if raw in (None, ""):
            continue
        try:
            rate = Decimal(str(raw)).quantize(RATE, rounding=ROUND_HALF_UP)
        except (InvalidOperation, ValueError):
            raise ValueError(f"{currency} 汇率格式不正确") from None
        if not Decimal("0.001") <= rate <= Decimal("1000"):
            raise ValueError(f"{currency} 汇率应在 0.001～1000 之间")
        clean[currency] = rate
    if not clean:
        raise ValueError("请至少填写一个币种的汇率")
    return {"saved": repo.upsert_rates(month, clean, (operator or "")[:64] or None)}


# ------------------------------------------------------------ 补充费用
def _adjustment_payload(month: str, payload: dict[str, Any], operator: str | None,
                        owners: Sequence[str]) -> dict[str, Any]:
    fee = str(payload.get("fee_item") or "").strip()
    code = str(payload.get("row_code") or "").strip()
    if fee not in ADJUSTMENT_LABELS:
        raise ValueError("费用项无效")
    scopes = ADJUSTMENT_SCOPES[fee]
    valid = ((code == "ALL" and "ALL" in scopes) or (code in SITES and "SITE" in scopes)
             or (code in owners and "OWNER" in scopes))
    if not valid:
        where = "、".join({"ALL": "总额", "SITE": "站点 US/DE/UK", "OWNER": "负责人"}[s] for s in scopes)
        raise ValueError(f"「{ADJUSTMENT_LABELS[fee]}」只能记在：{where}")
    try:
        amount = Decimal(str(payload.get("amount"))).quantize(CENT, rounding=ROUND_HALF_UP)
    except (InvalidOperation, TypeError, ValueError):
        raise ValueError("金额格式不正确") from None
    if not amount or abs(amount) >= MAX_ADJUSTMENT:
        raise ValueError("金额不能为 0，且绝对值须小于 1 亿")
    remark = str(payload.get("remark") or "").strip()
    if len(remark) > 255:
        raise ValueError("备注不能超过 255 个字符")
    return {"stat_month": month, "row_code": code, "fee_item": fee, "amount": amount,
            "remark": remark or None, "operator": (operator or "")[:64] or None}


def list_adjustments(month: str) -> list[dict[str, Any]]:
    month = _month(month)
    return [{**row, "amount": str(row["amount"]), "fee_label": ADJUSTMENT_LABELS.get(row["fee_item"], row["fee_item"]),
             "created_at": _text_time(row.get("created_at")), "updated_at": _text_time(row.get("updated_at"))}
            for row in repo.adjustments(month)]


def create_adjustment(payload: dict[str, Any], operator: str | None) -> dict[str, Any]:
    month = _month(payload.get("stat_month"))
    _, owners = _owner_resolver(month)
    return {"id": repo.insert_adjustment(_adjustment_payload(month, payload, operator, owners))}


def update_adjustment(adjustment_id: int, payload: dict[str, Any], operator: str | None) -> dict[str, Any]:
    current = repo.adjustment(adjustment_id)
    if not current:
        raise ValueError("补充费用不存在或已删除")
    _, owners = _owner_resolver(current["stat_month"])
    repo.update_adjustment(adjustment_id, _adjustment_payload(current["stat_month"], payload, operator, owners))
    return {"id": adjustment_id}


def delete_adjustment(adjustment_id: int) -> dict[str, Any]:
    if not repo.delete_adjustment(adjustment_id):
        raise ValueError("补充费用不存在或已删除")
    return {"id": adjustment_id}


# ------------------------------------------------------------ 导出
def export_report(month: str) -> tuple[str, bytes]:
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill

    report = get_report(month)
    workbook = Workbook()
    header_font, header_fill = Font(bold=True, color="FFFFFF"), PatternFill("solid", fgColor="24486D")
    formats = {"money": "#,##0.00", "rate": "0.00%", "qty": "#,##0"}
    labels = {"US": "US", "EU": "EU", "DE": "EU-DE", "UK": "EU-UK", "TOTAL": "合计"}

    def sheet(ws, columns, rows, total, first):
        head = ["月份", first, *[label for _, label, _ in columns]]
        ws.append(head)
        for cell in ws[1]:
            cell.font, cell.fill = header_font, header_fill
            cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        for row in [*rows, total]:
            name = labels.get(row["row_code"], row["row_code"]) if first == "站点" else (
                "合计" if row is total else row["row_code"])
            values = [report["stat_month"], name]
            for key, _label, _kind in columns:
                value = row.get(key)
                values.append(float(value) if isinstance(value, Decimal) else value)
            ws.append(values)
            for index, (_, _, kind) in enumerate(columns, start=3):
                ws.cell(ws.max_row, index).number_format = formats[kind]
            if row is total:
                for cell in ws[ws.max_row]:
                    cell.font = Font(bold=True)
        ws.freeze_panes = "C2"
        for index in range(1, len(head) + 1):
            ws.column_dimensions[ws.cell(1, index).column_letter].width = 14
        ws.column_dimensions["B"].width = 26

    first = workbook.active
    first.title = "站点汇总"
    sheet(first, SITE_COLUMNS, report["site_rows"], report["site_total"], "站点")
    sheet(workbook.create_sheet("个人利润"), OWNER_COLUMNS, report["owner_rows"], report["owner_total"], "负责人")
    sheet(workbook.create_sheet("店铺利润"), STORE_COLUMNS, report["store_rows"], report["store_total"], "店铺")
    notes = workbook.create_sheet("说明")
    for line in (
        f"统计月份：{report['stat_month']}（eBay 交易按美国太平洋时间切月，与卖家后台交易报告一致），人民币",
        f"交易拉取时间：{report.get('pulled_at') or '--'}；中行汇率：" + "、".join(f"{k} {v}" for k, v in report["rates"].items()),
        "平台收入 = 销售总额 + 退款 + 赔偿；平台支出 = 成交费 + 罚款 + 广告费 + 刊登/副标题 + 其他费用；平台净收入 = 交易净额合计",
        "资金占用费 = −（91-180天货值×12% + 180天+×24% + 成都仓30天+×12%）×30/360；税务风险金 = −平台收入×1%",
        "毛利 = 平台净收入 + 采购 + 头程 + 尾程 + 仓储 + 店铺运营 + 各调整项 + 资金占用费 + 积分抵扣 + 税务风险金 + GU仓销毁 + 补充",
        "没有 SKU 或品牌未分配的金额，个人表按各人平台收入占比分摊；店铺表未含仓储及店铺运营等分摊项",
        *report["notices"],
    ):
        notes.append([line])
    notes.column_dimensions["A"].width = 130
    output = BytesIO()
    workbook.save(output)
    return f"eBay月度利润表-{report['stat_month']}.xlsx", output.getvalue()
