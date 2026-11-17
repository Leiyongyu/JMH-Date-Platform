"""财务中心「项目利润总表」：照财务手工表《项目利润总表》的「小组项目利润表」「店铺维度-项目利润表」两张表出数。

口径（2026-09 与手工表逐主体逐项核对过）：
- AMZ 数据：财务每月从领星后台手动导出「利润报表-MSKU」（结算、按月、币种选人民币）在页面上传，按 AMZ_FILE_COLUMNS
  把文件列加总成原来的字段（2026-09 与领星接口逐行核对 29 个字段全部一致）。不再用接口拉取的
  ods_lingxing_profit_report_msku_month：接口的成本明细（移除、途损等分项）有缺段，手动导出是全的；那张表仍归
  AMZ 月度利润表使用。手工表的「AMZ收入-店铺(分站点)-汇总」就是这份数据按 主体 + 站点 汇总。
- 主体与组别：店铺名「EU-主体01-DE」前缀是组别（EU/US1/US2/US3）、中间段是主体；没有组别前缀的（主体03）按
  ENTITY_GROUPS 归组。与 AMZ 月度利润表不同，关停店铺也照手工表计入。
- 主体05、主体27只算 MSKU 含 zmy/dsq 的（与月度库存同一条规则）；主体03只算 XBJL 开头的 MSKU（手工表口径，
  见 OWN_MSKU_PREFIXES，只用于本表）。被剔除 MSKU 的「维护的店铺运营费」仍按手工表记在该主体上（并计入毛利）。
- 店铺维度各列与手工表 SUMIFS 的列一一对应，见 STORE_COLUMNS；其中「退款额合计」是领星口径
  （收入退款额 + 费用退款额 + 买家运费 + 促销折扣 + 其他收入），「平台支出合计」含净税费。
- 小组表 AMZ 列由店铺维度按组加总；eBay 列来自上传的财务 eBay 利润明细表（「汇总」sheet 的当月小计行、
  「eaby分析」的广告费、交易报告的订单数），上传后可手工改；超库龄、主体税费、人力、分摊、房租等
  各组手填。FBA 移除、FBA 途损抵扣、其他店铺运营费（店租 / 税务风险金 / 滞销库存费用，加回）由上传的领星文件
  按组自动算（见 store_sums）；eBay 的谷仓销毁、积分抵扣取 eBay 利润明细表「汇总」，没有就为空。
  行与公式照手工表：变动成本小计 = 采购 + 途损抵扣 + 头程 + 店铺运营费（移除、超库龄、主体税费只展示）；
  项目毛利 = 平台收入 + 平台支出 + 变动成本小计；净利润 = 项目组净利润 + 手动分摊 + 其他费用 + 固定成本合计。
"""
from __future__ import annotations

import io
import logging
import re
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Iterable

from backend.repositories import project_profit_repository as repo
from backend.services import inventory_report_etl_service as inventory

LOG = logging.getLogger(__name__)
CHINA = timezone(timedelta(hours=8))
ZERO = Decimal("0")
MONTH = re.compile(r"^20\d{2}-(0[1-9]|1[0-2])$")
MAX_FILE_BYTES = 50 * 1024 * 1024
MAX_AMOUNT = Decimal("1000000000")
MIGRATION_MESSAGE = repo.MIGRATION_MESSAGE

GROUPS = ("EBAY", "EU", "US1", "US2", "US3")
AMZ_GROUPS = GROUPS[1:]
GROUP_LABELS = {"EBAY": "eBay", "EU": "EU", "US1": "US1", "US2": "US2", "US3": "US3", "TOTAL": "合计"}
UNGROUPED = "未分组"
# 店铺名没有组别前缀的主体（关停店铺），按手工表归组。
ENTITY_GROUPS = {"主体03": "EU"}
# 手工表只计本公司 MSKU 的主体：店铺里其他 MSKU（未配对、他人商品）只保留店铺运营费。2026-09 核对：
# 主体03-DE 的 57-YSGX-X294、XZ-G5MI-KAAM 不在手工表里，按此剔除后 EU 与手工表一致。
OWN_MSKU_PREFIXES = {"主体03": "XBJL"}
# 手工表店铺维度的主体顺序；不在表里的新主体排在本组最后。
ENTITY_ORDER = (
    "主体01", "主体02", "员工18", "主体03", "主体04", "主体05", "主体06", "主体07",
    "主体08", "主体09", "主体10", "员工19", "主体11", "主体12", "主体13", "主体14", "主体15", "主体16", "主体17",
    "主体18", "主体19", "主体20", "主体21", "主体22",
    "主体23", "员工20", "主体24", "主体25", "主体26", "主体27", "主体28",
)

# ------------------------------------------------------------------ 店铺维度
STORE_COLUMNS = (
    ("sales_amount", "销售额统计", ("sales_amount",)),
    ("fba_inventory_credit", "FBA库存赔偿", ("fba_inventory_credit",)),
    ("refund_total", "退款额合计",
     ("sales_refunds", "fee_refunds", "shipping_credits", "promotional_rebates", "other_in_amount")),
    ("platform_income", "平台收入合计",
     ("sales_amount", "fba_inventory_credit", "shipping_credits", "promotional_rebates", "cash_on_delivery",
      "other_in_amount", "sales_refunds", "fee_refunds")),
    ("platform_fee", "平台佣金", ("platform_fee",)),
    ("fba_delivery", "FBA发货费+FBA国际物流", ("fba_delivery_fee", "international_inbound_fee")),
    ("ads", "广告费+推广费", ("ads_cost", "promotion_fee")),
    ("storage", "FBA仓储费+入库配置费", ("storage_fee", "inbound_convenience_fee")),
    ("other_expense", "其他支出", ("other_transaction_fees", "adjustment_fee", "platform_other_fee")),
    ("platform_expense", "平台支出合计",
     ("platform_fee", "fba_delivery_fee", "other_transaction_fees", "ads_cost", "promotion_fee", "storage_fee",
      "inbound_convenience_fee", "international_inbound_fee", "adjustment_fee", "platform_other_fee",
      "sales_tax", "sales_tax_refund", "market_tax", "market_tax_refund")),
    ("platform_receipt", "平台收款额", ()),
    ("purchase_cost", "销售采购成本", ("purchase_cost",)),
    ("first_leg_cost", "头程运费成本", ("first_leg_cost",)),
    ("store_operation", "维护的店铺运营费", ("_custom_fees",)),
    ("gross_profit", "毛利（不含店铺运营费等）", ("gross_profit",)),
    ("sales_qty", "销量", ("sales_qty",)),
)
STORE_KEYS = tuple(key for key, _label, _fields in STORE_COLUMNS)
STORE_LABELS = {key: label for key, label, _fields in STORE_COLUMNS}
QTY_KEYS = {"sales_qty", "refunds_qty"}
# 领星自定义费用里属于「其他店铺运营费（虚拟维护税金、滞销利息、店租）」的几项：已含在店铺运营费里扣过，
# 小组表在净利润前按正数加回（手工表的「（+）」）。2026-09 与手工表核对一致。
OTHER_STORE_FEE_NAMES = ("店租费（法人补贴等）", "税务风险金", "滞销库存费用")
# 「超库龄费用」（只展示）= 领星自定义费用「滞销库存费用」按组汇总，文件里的负数照记。
AGED_FEE_NAME = "滞销库存费用"
# 主体05、主体27两家店里非本公司 MSKU 的店铺运营费互记到对方主体：(组别, 主体)。
FEE_PARTNERS = {"主体05": ("US3", "主体27"), "主体27": ("EU", "主体05")}


def _num(value: Any) -> Decimal:
    if value in (None, ""):
        return ZERO
    try:
        return Decimal(str(value).replace(",", "").strip())
    except (InvalidOperation, ValueError):
        return ZERO


def _month(value: str | None) -> str:
    text = str(value or "").strip()
    if not MONTH.match(text):
        raise ValueError("请选择正确的月份")
    return text


def _custom_fees(row: dict[str, Any]) -> Decimal:
    fees = row.get("other_fees") or {}
    return sum((_num(value) for value in fees.values()), ZERO) if isinstance(fees, dict) else ZERO


def entity_of(store_name: Any) -> tuple[str, str]:
    """店铺名 → (组别, 主体)。「EU-主体01-DE」→ (EU, 主体01)；「主体03-DE」→ (EU, 主体03)。"""
    parts = [part.strip() for part in str(store_name or "").split("-")]
    if len(parts) >= 2 and parts[0].upper() in AMZ_GROUPS:
        return parts[0].upper(), parts[1] or "未知店铺"
    entity = parts[0] or "未知店铺"
    return ENTITY_GROUPS.get(entity, UNGROUPED), entity


def _excluded(entity: str, store_name: str, msku: str) -> bool:
    prefix = OWN_MSKU_PREFIXES.get(entity)
    if prefix:
        return not msku.strip().upper().startswith(prefix)
    return inventory._exclude_special_store_msku(store_name, msku)


def _other_store_fees(row: dict[str, Any]) -> Decimal:
    fees = row.get("other_fees") or {}
    if not isinstance(fees, dict):
        return ZERO
    return sum((_num(fees.get(name)) for name in OTHER_STORE_FEE_NAMES), ZERO)


def store_sums(rows: Iterable[dict[str, Any]]) -> dict[tuple[str, str], dict[str, Decimal]]:
    """按 (组别, 主体) 汇总店铺维度各列，另带小组表用的几项：
    refunds_qty（退款率）、removal_cost（FBA 移除，文件里的负数照记）、transit_credit（FBA 途损抵扣，
    文件里途损成本合计取反，即抵扣为正）、other_store_fee（其他店铺运营费加回，自定义费用三项取反）、
    aged_fee（超库龄费用 = 自定义费用「滞销库存费用」）。自定义费用类的照店铺运营费口径，被剔除 MSKU 的也计入。"""
    sums: dict[tuple[str, str], dict[str, Decimal]] = defaultdict(lambda: defaultdict(lambda: ZERO))
    for row in rows:
        key = entity_of(row.get("store_name"))
        target = sums[key]
        fees = _custom_fees(row)
        target["other_store_fee"] -= _other_store_fees(row)
        other_fees = row.get("other_fees")
        target["aged_fee"] += _num(other_fees.get(AGED_FEE_NAME)) if isinstance(other_fees, dict) else ZERO
        if _excluded(key[1], str(row.get("store_name") or ""), str(row.get("msku") or "")):
            # 主体05 / 主体27 / 主体03 非本公司 MSKU：手工表只保留其店铺运营费（计入毛利）。
            # 主体05、主体27两家店互卖对方的货：非本公司 MSKU 的店铺运营费记到对方主体（照 2026-10 手工表）。
            owner = sums[FEE_PARTNERS[key[1]]] if key[1] in FEE_PARTNERS else target
            owner["store_operation"] += fees
            owner["gross_profit"] += fees
            continue
        file_expense = row.get("platform_expense")
        for key_name, _label, fields in STORE_COLUMNS:
            if key_name == "platform_expense" and file_expense is not None:
                target[key_name] += _num(file_expense)  # 领星文件自带的「平台支出」合计
                continue
            for field in fields:
                target[key_name] += fees if field == "_custom_fees" else _num(row.get(field))
        target["refunds_qty"] += _num(row.get("refunds_qty"))
        target["removal_cost"] += _num(row.get("removal_cost"))
        target["transit_credit"] -= _num(row.get("transit_loss"))
    for target in sums.values():
        target["platform_receipt"] = target["platform_income"] + target["platform_expense"]
    return sums


def _entity_sort(item: tuple[tuple[str, str], Any]) -> tuple:
    (group, entity), _value = item
    group_rank = AMZ_GROUPS.index(group) if group in AMZ_GROUPS else len(AMZ_GROUPS)
    rank = ENTITY_ORDER.index(entity) if entity in ENTITY_ORDER else len(ENTITY_ORDER)
    return group_rank, rank, entity


# ------------------------------------------------------------------ 小组项目利润表
# kind：amz = AMZ 列由店铺维度汇总、eBay 列来自上传（可改）；manual = 各组手填；formula = 按公式算；
#       ratio = 比率行。unit：money / qty / rate。memo=True 表示只展示、不进合计公式（照手工表）。
def _row(code, label, category, kind, unit="money", **extra):
    return {"code": code, "label": label, "category": category, "kind": kind, "unit": unit, **extra}


STATEMENT = (
    _row("platform_income", "平台收入", "收入", "amz", amz_key="platform_income"),
    _row("normal_orders", "正常订单", "收入", "amz", amz_key="sales_amount", ebay=False),
    _row("refund_orders", "退款订单", "收入", "amz", amz_key="refund_total", ebay=False),
    _row("compensation", "赔偿合计", "收入", "amz", amz_key="fba_inventory_credit", ebay=False),
    _row("platform_expense", "平台支出", "直接成本（变动成本）", "amz", amz_key="platform_expense"),
    _row("ads", "广告费及推广费（亚马逊&eBay）", "直接成本（变动成本）", "amz", amz_key="ads", indent=True),
    _row("fba_logistics", "FBA仓储物流 / eBay谷仓（尾程+中转代发）", "直接成本（变动成本）", "amz",
         amz_key=("fba_delivery", "storage"), indent=True),
    _row("platform_fee", "平台费", "直接成本（变动成本）", "amz", amz_key="platform_fee", indent=True, ebay=False),
    _row("other_platform_expense", "其他平台支出", "直接成本（变动成本）", "amz", amz_key="other_expense",
         indent=True, ebay=False),
    _row("purchase_cost", "采购成本", "直接成本（变动成本）", "amz", amz_key="purchase_cost"),
    _row("removal_destroy", "FBA移除 / 谷仓销毁", "直接成本（变动成本）", "amz", amz_key="removal_cost", memo=True),
    # 下面两行照「总表」：按组手填，只展示，不进变动成本小计。
    _row("goods_loss", "货损、清货 / 借货", "直接成本（变动成本）", "manual", memo=True),
    _row("other_income", "其他收入（沃尔玛 + 多渠道）", "直接成本（变动成本）", "manual", memo=True),
    _row("transit_credit", "FBA途损抵扣 / eBay积分抵扣（+）", "直接成本（变动成本）", "amz",
         amz_key="transit_credit"),
    _row("aged_fee", "超库龄费用", "直接成本（变动成本）", "amz", amz_key="aged_fee", memo=True),
    _row("first_leg", "头程运费", "直接成本（变动成本）", "amz", amz_key="first_leg_cost"),
    _row("store_operation", "店铺运营费（直评、紫鸟续费等）", "直接成本（变动成本）", "amz", amz_key="store_operation"),
    _row("entity_tax", "店铺主体税费（真实缴费）", "直接成本（变动成本）", "manual", memo=True, indent=True),
    _row("variable_subtotal", "变动成本小计", "直接成本（变动成本）", "formula", strong=True),
    _row("project_gross", "项目毛利", "项目毛利", "formula", strong=True),
    _row("gross_margin", "毛利率", "项目毛利", "ratio", unit="rate"),
    _row("labor_cost", "项目人力成本", "项目人力成本", "manual"),
    _row("group_net", "项目组净利润", "项目组净利润", "formula", strong=True),
    _row("order_qty", "订单销量", "经营数据", "amz", unit="qty", amz_key="sales_qty", override=True),
    _row("headcount", "人员数量", "经营数据", "manual", unit="qty"),
    _row("manual_allocation", "其他店铺运营费（虚拟维护税金、滞销利息、店租）（+）", "手动分摊费用", "amz",
         amz_key="other_store_fee"),
    _row("other_fee", "其他费用", "手动分摊费用", "formula"),
    _row("software_allocation", "项目软件费用分摊", "手动分摊费用", "manual", indent=True),
    _row("other_fee_extra", "其他费用补充（不含软件分摊）", "手动分摊费用", "manual", indent=True),
    _row("supply_chain_labor", "供应链人力成本", "间接成本（固定成本）", "manual"),
    _row("admin_labor", "综合管理部人力成本", "间接成本（固定成本）", "manual"),
    _row("west_rent", "西区房租", "间接成本（固定成本）", "manual"),
    _row("east_rent", "东区房租、物业水电+经营开支分摊", "间接成本（固定成本）", "manual"),
    _row("fixed_subtotal", "固定成本合计", "间接成本（固定成本）", "formula", strong=True),
    _row("net_profit", "净利润", "净利润", "formula", strong=True),
    _row("net_margin", "净利润率", "净利润", "ratio", unit="rate"),
    _row("refund_rate", "退款率（退款量 / 销量）", "监控指标", "amz", unit="rate", override=True),
    _row("ads_ratio", "广告推广支出占比", "监控指标", "ratio", unit="rate", target="5%", limit=Decimal("0.05")),
    _row("purchase_ratio", "采购成本占比（产品成本费率）", "监控指标", "ratio", unit="rate",
         target="亚马逊40%，eBay45%"),
    _row("first_leg_ratio", "头程占比", "监控指标", "ratio", unit="rate", target="5%", limit=Decimal("0.05")),
    _row("logistics_ratio", "海外仓储物流占比", "监控指标", "ratio", unit="rate", target="18%", limit=Decimal("0.18")),
    _row("store_op_ratio", "店铺运营费占比", "监控指标", "ratio", unit="rate", target="4%", limit=Decimal("0.04")),
    _row("labor_ratio", "项目人力成本占比", "监控指标", "ratio", unit="rate", target=">12% 黄色预警，>15% 红色预警"),
    _row("gross_margin_check", "项目毛利率", "监控指标", "ratio", unit="rate", target="<10% 红色预警，<12% 黄色预警"),
    _row("expense_ratio", "费用率（所有变动费用占比）", "监控指标", "ratio", unit="rate"),
    _row("per_capita", "人均效能（平台收入 / 项目人数）", "监控指标", "ratio", unit="money", target="<35万/人 红色预警"),
    _row("per_capita_gross", "人均毛利（项目毛利 / 项目人数）", "监控指标", "ratio", unit="money",
         target="<5万/人 黄色预警"),
    _row("rent_ratio", "房租物业水电、经营开支分摊占比", "监控指标", "ratio", unit="rate"),
    _row("monthly_cost", "每月经营成本开支合计（变动 + 固定费用）- 回款监控红线", "回款监控", "formula", strong=True),
    _row("collection", "回款", "回款监控", "manual"),
    _row("collection_rate", "回款率", "回款监控", "ratio", unit="rate"),
    _row("monthly_target", "月度毛利目标", "月度完成情况", "manual"),
    _row("monthly_rate", "月度完成率", "月度完成情况", "ratio", unit="rate"),
    _row("annual_target", "年度毛利目标", "年度完成情况", "manual"),
    _row("annual_rate", "年度完成率（当年累计毛利 / 年度目标）", "年度完成情况", "ratio", unit="rate"),
)
ROW_BY_CODE = {row["code"]: row for row in STATEMENT}
MANUAL_CODES = tuple(row["code"] for row in STATEMENT if row["kind"] == "manual")
OVERRIDE_CODES = tuple(row["code"] for row in STATEMENT if row.get("override"))
# eBay 列从上传文件读出的项目（上传后可手工改）。
EBAY_UPLOAD_CODES = ("platform_income", "platform_expense", "ads", "fba_logistics", "purchase_cost",
                     "removal_destroy", "transit_credit", "aged_fee", "first_leg", "store_operation",
                     "order_qty", "refund_rate", "manual_allocation")
EBAY_EDITABLE = tuple(dict.fromkeys((*EBAY_UPLOAD_CODES, *MANUAL_CODES)))
AMZ_EDITABLE = tuple(dict.fromkeys((*MANUAL_CODES, *OVERRIDE_CODES)))


def editable(group: str, code: str) -> bool:
    return code in (EBAY_EDITABLE if group == "EBAY" else AMZ_EDITABLE if group in AMZ_GROUPS else ())


def _div(numerator: Decimal | None, denominator: Decimal | None) -> Decimal | None:
    if numerator is None or not denominator:
        return None
    return numerator / denominator


def _column(values: dict[str, Decimal | None]) -> dict[str, Decimal | None]:
    """一列（一个组或合计）：已有基础项 → 补齐公式行与比率行。"""
    v = {code: values.get(code) for code in ROW_BY_CODE}
    if all(value is None for value in v.values()):
        return v  # 这一列什么数据都没有：公式行也显示 --，不算出一串 0
    z = lambda code: v.get(code) or ZERO  # noqa: E731
    v["variable_subtotal"] = z("purchase_cost") + z("transit_credit") + z("first_leg") + z("store_operation")
    v["project_gross"] = z("platform_income") + z("platform_expense") + v["variable_subtotal"]
    v["group_net"] = v["project_gross"] + z("labor_cost")
    v["other_fee"] = z("software_allocation") + z("other_fee_extra")
    v["fixed_subtotal"] = z("supply_chain_labor") + z("admin_labor") + z("west_rent") + z("east_rent")
    v["net_profit"] = v["group_net"] + z("manual_allocation") + v["other_fee"] + v["fixed_subtotal"]
    income = v.get("platform_income")
    v["gross_margin"] = v["gross_margin_check"] = _div(v["project_gross"], income)
    v["net_margin"] = _div(v["net_profit"], income)
    v["ads_ratio"] = _div(v.get("ads"), income)
    v["purchase_ratio"] = _div(v.get("purchase_cost"), income)
    v["first_leg_ratio"] = _div(v.get("first_leg"), income)
    v["logistics_ratio"] = _div(v.get("fba_logistics"), income)
    v["store_op_ratio"] = _div(v.get("store_operation"), income)
    v["labor_ratio"] = _div(v.get("labor_cost"), v["project_gross"]) if v.get("labor_cost") is not None else None
    v["expense_ratio"] = _div(z("platform_expense") + v["variable_subtotal"], income)
    v["per_capita"] = _div(income, v.get("headcount"))
    v["per_capita_gross"] = _div(v["project_gross"], v.get("headcount"))
    rent = [v.get(code) for code in ("west_rent", "east_rent") if v.get(code) is not None]
    v["rent_ratio"] = _div(sum(rent, ZERO), income) if rent else None
    v["monthly_cost"] = (v["variable_subtotal"] + v["fixed_subtotal"] + z("labor_cost") + z("manual_allocation")
                         + v["other_fee"])
    v["collection_rate"] = _div(v.get("collection"), income)
    v["monthly_rate"] = _div(v["project_gross"], v.get("monthly_target"))
    # annual_rate 要用到往月毛利，在 build_statement 里补。
    return v


def _level(code: str, group: str, value: Decimal | None) -> str | None:
    """预警色：red / yellow；照手工表各指标的标准。"""
    if value is None:
        return None
    row = ROW_BY_CODE[code]
    if row.get("limit") is not None:
        return "red" if abs(value) > row["limit"] else None
    if code == "purchase_ratio":
        return "red" if abs(value) > (Decimal("0.45") if group == "EBAY" else Decimal("0.40")) else None
    if code == "labor_ratio":
        return "red" if abs(value) > Decimal("0.15") else "yellow" if abs(value) > Decimal("0.12") else None
    if code == "gross_margin_check":
        return "red" if value < Decimal("0.10") else "yellow" if value < Decimal("0.12") else None
    if code == "per_capita":
        return "red" if value < Decimal("350000") else None
    if code == "per_capita_gross":
        return "yellow" if value < Decimal("50000") else None
    return None


def _out(value: Decimal | None, unit: str) -> float | None:
    if value is None:
        return None
    return round(float(value), 6 if unit == "rate" else 2)


def build_statement(sums: dict[tuple[str, str], dict[str, Decimal]],
                    items: Iterable[dict[str, Any]],
                    prior_gross: dict[str, Decimal] | None = None,
                    annual_targets: dict[str, Decimal] | None = None) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """prior_gross：当年 1 月到上月各组项目毛利之和；annual_targets：本月没填时沿用的当年年度目标。"""
    stored: dict[tuple[str, str], dict[str, Any]] = {
        (str(item["group_code"]), str(item["item_code"])): item for item in items}
    group_sums: dict[str, dict[str, Decimal]] = defaultdict(lambda: defaultdict(lambda: ZERO))
    for (group, _entity), values in sums.items():
        if group in AMZ_GROUPS:
            for key, value in values.items():
                group_sums[group][key] += value
    base: dict[str, dict[str, Decimal | None]] = {}
    sources: dict[str, dict[str, str]] = defaultdict(dict)
    for group in GROUPS:
        values: dict[str, Decimal | None] = {}
        for row in STATEMENT:
            code = row["code"]
            item = stored.get((group, code))
            # 该组本月没有领星数据时不填 0，页面显示 --（规范：不用 0 冒充没有数据）。
            if row["kind"] == "amz" and group in AMZ_GROUPS and group in group_sums:
                key = row.get("amz_key")
                if code == "refund_rate":
                    values[code] = _div(group_sums[group]["refunds_qty"], group_sums[group]["sales_qty"])
                elif isinstance(key, tuple):
                    values[code] = sum((group_sums[group][part] for part in key), ZERO)
                else:
                    values[code] = group_sums[group][key]
                sources[group][code] = "AUTO"
            if item is not None and editable(group, code):
                values[code] = _num(item["amount"])
                sources[group][code] = str(item.get("source") or "MANUAL")
        if values.get("annual_target") is None and (annual_targets or {}).get(group) is not None:
            values["annual_target"] = annual_targets[group]
            sources[group]["annual_target"] = "CARRY"
        base[group] = values
    columns = {group: _column(base[group]) for group in GROUPS}
    total_base: dict[str, Decimal | None] = {}
    for row in STATEMENT:
        code = row["code"]
        if row["kind"] in ("amz", "manual") and code != "refund_rate":
            present = [base[group].get(code) for group in GROUPS if base[group].get(code) is not None]
            total_base[code] = sum(present, ZERO) if present else None
    qty = {group: base[group].get("order_qty") for group in GROUPS}
    weighted = [(base[group].get("refund_rate"), qty[group]) for group in GROUPS
                if base[group].get("refund_rate") is not None and qty[group]]
    total_base["refund_rate"] = (sum((rate * count for rate, count in weighted), ZERO)
                                 / sum((count for _rate, count in weighted), ZERO)) if weighted else None
    columns["TOTAL"] = _column(total_base)
    prior = prior_gross or {}
    for group in (*GROUPS, "TOTAL"):
        current = columns[group].get("project_gross")
        before = (sum((prior.get(g, ZERO) for g in GROUPS), ZERO) if group == "TOTAL" else prior.get(group, ZERO))
        ytd = None if current is None and not before else (current or ZERO) + before
        columns[group]["annual_rate"] = _div(ytd, columns[group].get("annual_target"))
    statement = []
    for row in STATEMENT:
        code, unit = row["code"], row["unit"]
        values = {group: _out(columns[group].get(code), unit) for group in (*GROUPS, "TOTAL")}
        levels = {group: _level(code, group, columns[group].get(code)) for group in (*GROUPS, "TOTAL")}
        statement.append({
            "code": code, "label": row["label"], "category": row["category"], "kind": row["kind"], "unit": unit,
            "memo": bool(row.get("memo")), "indent": bool(row.get("indent")), "strong": bool(row.get("strong")),
            "target": row.get("target"), "values": values,
            "levels": {group: level for group, level in levels.items() if level},
            "sources": {group: sources[group].get(code) for group in GROUPS if sources[group].get(code)},
            "editable": [group for group in GROUPS if editable(group, code)],
        })
    return statement, columns


def build_stores(sums: dict[tuple[str, str], dict[str, Decimal]]) -> dict[str, Any]:
    rows, subtotals = [], {}
    total: dict[str, Decimal] = defaultdict(lambda: ZERO)
    for (group, entity), values in sorted(sums.items(), key=_entity_sort):
        rows.append({"group_code": group, "entity": entity, "row_type": "ENTITY",
                     **{key: _out(values.get(key, ZERO), "qty" if key in QTY_KEYS else "money")
                        for key in STORE_KEYS}})
        bucket = subtotals.setdefault(group, defaultdict(lambda: ZERO))
        for key in STORE_KEYS:
            bucket[key] += values.get(key, ZERO)
            total[key] += values.get(key, ZERO)
    result = []
    for group in (*AMZ_GROUPS, UNGROUPED):
        group_rows = [row for row in rows if row["group_code"] == group]
        if not group_rows:
            continue
        result.extend(group_rows)
        result.append({"group_code": group, "entity": f"{group} 小计", "row_type": "GROUP",
                       **{key: _out(subtotals[group][key], "money") for key in STORE_KEYS}})
    return {"columns": [{"key": key, "label": label} for key, label, _fields in STORE_COLUMNS],
            "rows": result,
            "total": {"group_code": "TOTAL", "entity": "合计", "row_type": "TOTAL",
                      **{key: _out(total[key], "money") for key in STORE_KEYS}}}


# ------------------------------------------------------------------ 查询
def _text_time(value: Any) -> str | None:
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M:%S")
    return str(value) if value else None


def list_months(limit: int = 36) -> list[str]:
    return repo.months(limit)


# 往月各组项目毛利（年度完成率用）：按 领星上传时间 + 手工项 / eBay 上传的最后修改时间 缓存，数据变了才重算。
_GROSS_CACHE: dict[str, tuple[tuple, dict[str, Decimal]]] = {}


def _month_gross(month: str, items: list[dict[str, Any]]) -> dict[str, Decimal]:
    amz = repo.amz_upload(month)
    signature = (_text_time((amz or {}).get("uploaded_at")), len(items),
                 max((_text_time(item.get("updated_at")) or "" for item in items), default=""))
    cached = _GROSS_CACHE.get(month)
    if cached and cached[0] == signature:
        return cached[1]
    _statement, columns = build_statement(store_sums(repo.msku_rows(month)), items)
    gross = {group: columns[group]["project_gross"] for group in GROUPS
             if columns[group].get("project_gross") is not None}
    _GROSS_CACHE[month] = (signature, gross)
    return gross


def _year_context(month: str) -> tuple[dict[str, Decimal], dict[str, Decimal]]:
    """当年 1 月到上月：各组项目毛利之和、最近一次填的年度毛利目标。"""
    year = month[:4]
    prior: dict[str, Decimal] = defaultdict(lambda: ZERO)
    targets: dict[str, Decimal] = {}
    for previous in sorted(m for m in repo.months(120) if m[:4] == year and m < month):
        items = repo.items(previous)
        for group, value in _month_gross(previous, items).items():
            prior[group] += value
        for item in items:
            if item.get("item_code") == "annual_target" and item.get("amount") is not None:
                targets[str(item["group_code"])] = _num(item["amount"])
    return dict(prior), targets


def get_report(month: str) -> dict[str, Any]:
    month = _month(month)
    rows = repo.msku_rows(month)
    sums = store_sums(rows)
    items = repo.items(month)
    prior_gross, annual_targets = _year_context(month)
    statement, _columns = build_statement(sums, items, prior_gross, annual_targets)
    amz = repo.amz_upload(month)
    upload = repo.upload(month)
    notices = []
    if not rows:
        notices.append(f"{month} 还没上传领星利润报表-MSKU，AMZ 各列为空")
    ungrouped = sorted({entity for (group, entity) in sums if group == UNGROUPED})
    if ungrouped:
        notices.append("以下主体识别不出组别，未计入小组表：" + "、".join(ungrouped))
    if upload is None:
        notices.append("本月还没上传 eBay 利润明细表，eBay 列只有手工录入的项目")
    filled = {(str(item["group_code"]), str(item["item_code"])) for item in items}
    missing = [GROUP_LABELS[group] for group in GROUPS if (group, "labor_cost") not in filled]
    if missing:
        notices.append("项目人力成本未录入：" + "、".join(missing))
    return {
        "stat_month": month,
        "groups": [{"code": group, "label": GROUP_LABELS[group]} for group in (*GROUPS, "TOTAL")],
        "statement": statement,
        "stores": build_stores(sums),
        "amz_upload": None if amz is None else {
            "file_name": amz.get("file_name"), "uploaded_by": amz.get("uploaded_by"), "msku_rows": int(amz.get("n") or 0),
            "uploaded_at": _text_time(amz.get("uploaded_at")), "check": amz.get("check") or {}},
        "ebay_upload": None if upload is None else {
            "file_name": upload.get("file_name"), "uploaded_by": upload.get("uploaded_by"),
            "uploaded_at": _text_time(upload.get("uploaded_at")), "check": upload.get("check") or {}},
        "notices": notices,
    }


# ------------------------------------------------------------------ 手工项
def save_items(payload: dict[str, Any], operator: str | None) -> dict[str, Any]:
    month = _month(payload.get("stat_month"))
    values = []
    for item in payload.get("items") or []:
        group = str(item.get("group_code") or "").strip().upper()
        code = str(item.get("item_code") or "").strip()
        if not editable(group, code):
            raise ValueError(f"{GROUP_LABELS.get(group, group)}「{ROW_BY_CODE.get(code, {}).get('label', code)}」不能手工录入")
        raw = item.get("amount")
        if raw in (None, ""):
            values.append((group, code, None))
            continue
        try:
            amount = Decimal(str(raw).replace(",", "").strip())
        except (InvalidOperation, ValueError) as exc:
            raise ValueError(f"「{ROW_BY_CODE[code]['label']}」金额格式不正确") from exc
        if not amount.is_finite() or abs(amount) >= MAX_AMOUNT:
            raise ValueError(f"「{ROW_BY_CODE[code]['label']}」金额超出范围")
        values.append((group, code, amount))
    if not values:
        raise ValueError("没有要保存的项目")
    changed = repo.save_items(month, values, operator, "MANUAL")
    LOG.info("项目利润总表手工项保存 month=%s items=%s operator=%s", month, len(values), operator)
    return {"stat_month": month, "saved": len(values), "changed": changed}


# ------------------------------------------------------------------ eBay 利润明细表上传
SUMMARY_SHEET = "汇总"
ANALYSIS_SHEET = "eaby分析"
TRANSACTION_SHEET = "eaby交易报告-核算-去除发放款项"
SUMMARY_REQUIRED = {
    "income": "平台收入-总(RMB)", "net": "平台净收入", "purchase": "销售采购成本(RMB)", "first_leg": "头程成本(RMB)",
    "last_mile": "海外仓-尾程(RMB)", "storage": "海外仓-仓储(RMB)", "store_op": "店铺运营费用-(紫鸟等)",
    "gross": "毛利(RMB)",
}
SUMMARY_OPTIONAL = {
    "net_project": "平台净收入-项目(电热毯)", "purchase_freight": "采购运费(RMB)", "duty": "头程关税成本(RMB)",
    "project_cost": "销售产品成本-项目", "warehouse_project": "海外仓费用-项目", "adjust_borrow": "调整项(借货/清货)",
    "adjust_discount": "调整项(成都仓折扣)", "aged_capital": "资金占用费-超龄货值", "packing": "包装耗材费",
    "brush_credit": "刷单SKU采购成本抵扣", "points": "积分抵扣", "tax_risk": "税务风险金", "destroy": "GU仓销毁",
    "expense_total": "平台支出(RMB)-总",
}


def _norm(value: Any) -> str:
    text = str(value or "").strip().lower().replace("（", "(").replace("）", ")").replace(" ", "")
    return text


def _sheet(workbook, name: str):
    wanted = _norm(name)
    for sheet in workbook.worksheets:
        if _norm(sheet.title) == wanted:
            return sheet
    return None


def parse_ebay_workbook(content: bytes, month: str) -> tuple[dict[str, Decimal | None], dict[str, Any]]:
    """读财务 eBay 利润明细表：返回 eBay 列各项目的值与核对信息。"""
    import openpyxl

    try:
        workbook = openpyxl.load_workbook(io.BytesIO(content), data_only=True, read_only=True)
    except Exception as exc:
        raise ValueError("读取文件失败，请上传财务的《利润明细表yyyymm-ebay》.xlsx") from exc
    try:
        summary = _sheet(workbook, SUMMARY_SHEET)
        if summary is None:
            raise ValueError("文件里没有「汇总」sheet，请确认上传的是财务的 eBay 利润明细表")
        rows = summary.iter_rows(values_only=True)
        header = [_norm(value) for value in (next(rows, None) or ())]
        index = {key: header.index(_norm(name)) for key, name in {**SUMMARY_REQUIRED, **SUMMARY_OPTIONAL}.items()
                 if _norm(name) in header}
        missing = [name for key, name in SUMMARY_REQUIRED.items() if key not in index]
        if missing:
            raise ValueError("「汇总」sheet 缺少列：" + "、".join(missing))
        wanted = month.replace("-", "")
        subtotal, months_seen = None, set()
        for row in rows:
            label = str(row[0] if row else "").strip()
            matched = re.match(r"^(20\d{4})\s*小计$", label)
            if matched:
                months_seen.add(matched.group(1))
                if matched.group(1) == wanted:
                    subtotal = row
        if subtotal is None:
            seen = "、".join(f"{m[:4]}-{m[4:]}" for m in sorted(months_seen)) or "无"
            raise ValueError(f"「汇总」sheet 里没有 {month} 的小计行（文件里的月份：{seen}），请确认月份")
        # 小计行是 SUM 公式，明细全空时算出 0：0 也当作「没有」。
        present = {key for key, i in index.items() if i < len(subtotal) and _num(subtotal[i]) != 0}
        g = {key: _num(subtotal[i]) if i < len(subtotal) else ZERO for key, i in index.items()}
        g.update({key: ZERO for key in SUMMARY_OPTIONAL if key not in g})
        # 口径照 2026-10 财务手工表：
        #   平台支出 = 汇总「平台支出(RMB)-总」+ 谷仓尾程 + 仓储（+ 海外仓费用-项目）；没有该列时退回「净收入 − 收入」；
        #   采购成本含 GU仓销毁；店铺运营费不含 资金占用费-超龄货值 与 GU仓销毁。
        logistics = g["last_mile"] + g["storage"] + g["warehouse_project"]
        net_expense = g["net"] - g["income"] + g["net_project"]
        expense = g["expense_total"] if "expense_total" in index else net_expense
        values: dict[str, Decimal | None] = {
            "platform_income": g["income"],
            "platform_expense": expense + logistics,
            "fba_logistics": logistics,
            "purchase_cost": (g["purchase"] + g["purchase_freight"] + g["project_cost"] + g["brush_credit"]
                              + g["destroy"]),
            "first_leg": g["first_leg"] + g["duty"],
            # 积分抵扣、GU仓销毁：文件里有这一列且有值才填，没有就为空（页面显示 --）。
            "transit_credit": g["points"] if "points" in present else None,
            "removal_destroy": g["destroy"] if "destroy" in present else None,
            "aged_fee": g["aged_capital"],
            "store_operation": (g["store_op"] + g["adjust_borrow"] + g["adjust_discount"] + g["packing"]
                                + g["tax_risk"]),
            # 其他店铺运营费（+）= 资金占用费-超龄货值 + 税务风险金，取反加回；两项都没有时为空。
            # 2026-09：−(−1,859.25 − 25,096.59) = 26,955.84；2026-10：27,188.64，均与手工表一致。
            "manual_allocation": (-(g["aged_capital"] + g["tax_risk"])
                                  if present & {"aged_capital", "tax_risk"} else None),
            "ads": None, "order_qty": None, "refund_rate": None,
        }
        check: dict[str, Any] = {"income": float(g["income"]), "net_income": float(g["net"]),
                                 "gross_profit": float(g["gross"])}
        analysis = _sheet(workbook, ANALYSIS_SHEET)
        if analysis is not None:
            arows = list(analysis.iter_rows(min_row=1, max_row=40, values_only=True))
            head = next((i for i, row in enumerate(arows) if row and _norm("广告费") in [_norm(v) for v in row]), None)
            if head is not None:
                ads_col = [_norm(v) for v in arows[head]].index(_norm("广告费"))
                for row in arows[head + 1:]:
                    if row and _norm(row[0]) == "ebay" and str(row[1] or "").strip() == wanted:
                        values["ads"] = _num(row[ads_col])
                        break
        transactions = _sheet(workbook, TRANSACTION_SHEET)
        if transactions is not None:
            trows = transactions.iter_rows(values_only=True)
            head = [_norm(v) for v in (next(trows, None) or ())]
            if "类型" in head and "数量" in head:
                type_col, qty_col = head.index("类型"), head.index("数量")
                orders = refunds = 0
                quantity = ZERO
                for row in trows:
                    if not row or type_col >= len(row):
                        continue
                    kind = _norm(row[type_col])
                    if kind in ("order", "订单"):
                        orders += 1
                        quantity += _num(row[qty_col] if qty_col < len(row) else None)
                    elif kind in ("refund", "退款"):
                        refunds += 1
                values["order_qty"] = quantity
                values["refund_rate"] = Decimal(refunds) / Decimal(orders) if orders else None
                check.update({"order_rows": orders, "refund_rows": refunds})
    finally:
        workbook.close()
    gross = (values["platform_income"] + values["platform_expense"] + values["purchase_cost"]
             + (values["transit_credit"] or ZERO) + values["first_leg"] + values["store_operation"])
    check["computed_gross_profit"] = float(gross)
    # 与汇总「毛利」的差额里，有两部分是口径不同造成的（照手工表）：平台支出取「平台支出-总」而非「净收入 − 收入」，
    # 店铺运营费不扣资金占用费。gross_diff 只留去掉这两部分后仍对不上的数，应为 0。
    method = (expense - net_expense) - g["aged_capital"]
    check["method_diff"] = round(float(method), 2)
    check["method_parts"] = {"platform_expense": round(float(expense - net_expense), 2),
                             "aged_capital": round(float(-g["aged_capital"]), 2)}
    check["gross_diff"] = round(float(gross - g["gross"] - method), 2)
    return values, check


def import_ebay(content: bytes, filename: str, month: str, operator: str | None) -> dict[str, Any]:
    month = _month(month)
    if not content:
        raise ValueError("请选择 eBay 利润明细表")
    if len(content) > MAX_FILE_BYTES:
        raise ValueError("文件不能超过 50MB")
    values, check = parse_ebay_workbook(content, month)
    items = [("EBAY", code, values.get(code)) for code in EBAY_UPLOAD_CODES]
    repo.save_upload(month, items, filename, operator, datetime.now(CHINA).replace(tzinfo=None), check)
    LOG.info("项目利润总表 eBay 上传 month=%s file=%s gross_diff=%s", month, filename, check.get("gross_diff"))
    return {"stat_month": month, "file_name": filename, "check": check,
            "missing": [ROW_BY_CODE[code]["label"] for code in EBAY_UPLOAD_CODES if values.get(code) is None]}


# ------------------------------------------------------------------ 领星利润报表-MSKU 上传
# 文件是领星后台「利润报表 → MSKU」按月导出：第 1 行分组表头（向右延续），第 2 行字段名，第 3 行起每行一个 店铺+MSKU。
# 目标字段 → 文件列：(分组, 字段名) 取单列；(分组, None) 取整组（除 AMZ_GROUP_EXCLUDE 里的数量 / 单列项）；
# (None, 字段名) 按字段名取（名字全表唯一）。2026-09 与领星接口逐行核对一致。
AMZ_FILE_COLUMNS: dict[str, tuple[tuple[str | None, str | None], ...]] = {
    "sales_qty": (("平台收入", "FBA销量"), ("平台收入", "FBM销量")),
    "refunds_qty": (("平台收入", "退款量"),),
    "returns_qty": (("平台收入", "退货量（可售）"), ("平台收入", "退货量（不可售）")),
    "sales_amount": (("平台收入", "FBA销售额"), ("平台收入", "FBM销售额")),
    "shipping_credits": (("平台收入", "买家运费"),),
    "promotional_rebates": (("平台收入", "促销折扣"),),
    "fba_inventory_credit": (("平台收入", "FBA库存赔偿"),),
    "cash_on_delivery": (("平台收入", "COD"),),
    "other_in_amount": (("平台收入-其他收入", None),),
    "sales_refunds": (("平台收入-收入退款额", None),),
    "fee_refunds": (("平台收入-费用退款额", None),),
    "platform_fee": (("平台支出", "平台费"),),
    "fba_delivery_fee": tuple(("平台支出", name) for name in (
        "FBA发货费(FBA)", "FBA发货费(容量预留费)", "亚马逊物流客户退货费", "FBA发货费(多渠道)", "MCF返佣费用")),
    "other_transaction_fees": (("平台支出", "其他订单费用"),),
    "ads_cost": (("平台支出-广告费", None),),
    "promotion_fee": (("平台支出-推广费", None),),
    "storage_fee": (("平台支出-FBA仓储费", None),),
    "inbound_convenience_fee": (("平台支出-FBA仓储费", "入库配置费（原合仓费）"),),
    "international_inbound_fee": (("平台支出-FBA国际物流货运费", None),),
    "adjustment_fee": (("平台支出", "调整费用"),),
    "platform_other_fee": (("平台支出-平台其他费", None),),
    "custom_order_fee": (("自定义费用", "站外推广费"),),
    "sales_tax": (("税费-销售税", None),),
    "sales_tax_refund": (("税费-销售税退款额", None),),
    "market_tax": (("税费", "市场税"),),
    "market_tax_refund": (("税费", "市场税退款额"),),
    "purchase_cost": (("商品成本", "采购成本"),),
    "first_leg_cost": (("商品成本", "头程成本"),),
    "other_cost": (("商品成本", "其他成本"),),
    "gross_profit": (("利润", "毛利润"),),
    # 领星自带的「平台支出」合计列：不含销售税 / 市场税净额与 FBA发货费(多渠道)；小组表、店铺维度的平台支出取这一列
    # （照 2026-10 手工表）。
    "platform_expense": (("平台支出", "平台支出"),),
    # FBA 移除 = 移除采购 + 移除物流（不含其他成本）；FBA 途损 = 途损补回 + 发货途损的采购 / 物流 / 其他。
    "removal_cost": tuple((None, name) for name in ("FBA移除采购成本", "FBA移除物流成本")),
    "transit_loss": tuple((None, name) for name in (
        "FBA途损补回采购成本", "FBA途损补回物流成本", "FBA途损补回其他成本",
        "FBA发货途损采购成本", "FBA发货途损物流成本", "FBA发货途损其他成本")),
}
AMZ_GROUP_EXCLUDE = {"平台支出-FBA仓储费": ("销毁量", "移除量", "入库配置费（原合仓费）")}
AMZ_QTY_FIELDS = ("sales_qty", "refunds_qty", "returns_qty")
AMZ_CUSTOM_GROUP = "自定义费用"
AMZ_CUSTOM_EXCLUDE = ("站外推广费",)  # 走 custom_order_fee，与接口 customOrderFee 一致
AMZ_INCOME_PARTS = ("sales_amount", "fba_inventory_credit", "shipping_credits", "promotional_rebates",
                    "cash_on_delivery", "other_in_amount", "sales_refunds", "fee_refunds")
AMZ_KEY_COLUMNS = {"month": "日期", "store": "店铺", "msku": "MSKU", "sku": "SKU", "name": "品名", "currency": "币种"}
AMZ_CURRENCY = "CNY"
AMZ_MAX_ROWS = 100000
AMZ_TOLERANCE = Decimal("0.05")


def _amz_cell(value: Any, where: str) -> Decimal:
    if value is None or isinstance(value, bool):
        return ZERO
    if isinstance(value, (int, float, Decimal)):
        return Decimal(str(value))
    text = str(value).replace(",", "").strip()
    if text in ("", "-", "--"):
        return ZERO
    try:
        return Decimal(text)
    except InvalidOperation:
        raise ValueError(f"{where} 不是数字：{value}") from None


def _amz_header(rows) -> tuple[list[str], list[str]]:
    """找字段名那一行（含 店铺 / MSKU / 币种），它的上一行是分组表头（合并单元格，向右延续）。"""
    previous: tuple = ()
    for index, row in enumerate(rows):
        names = [str(cell).strip() if cell is not None else "" for cell in row]
        if {"店铺", "MSKU", "币种"} <= set(names):
            groups, current = [], ""
            padded = list(previous) + [None] * max(0, len(names) - len(previous))
            for cell in padded[:len(names)]:
                current = str(cell).strip() if cell not in (None, "") else current
                groups.append(current)
            return groups, names
        previous = row
        if index >= 5:
            break
    raise ValueError("没找到表头（店铺 / MSKU / 币种），请上传领星「利润报表-MSKU」导出的原始文件")


def _amz_index(groups: list[str], names: list[str]) -> dict[str, Any]:
    norm_names = [_norm(name) for name in names]
    norm_groups = [_norm(group) for group in groups]
    fields: dict[str, list[int]] = {}
    missing: list[str] = []
    for field, sources in AMZ_FILE_COLUMNS.items():
        columns: list[int] = []
        for group, name in sources:
            if name is None:
                skip = {_norm(item) for item in AMZ_GROUP_EXCLUDE.get(group, ())}
                hits = [j for j, g in enumerate(norm_groups) if g == _norm(group) and norm_names[j] not in skip]
                if not hits:
                    missing.append(f"{group}（整组）")
            else:
                hits = [j for j, n in enumerate(norm_names)
                        if n == _norm(name) and (group is None or norm_groups[j] == _norm(group))]
                if len(hits) != 1:
                    missing.append(f"{group} / {name}" if group else name)
                    continue
            columns.extend(hits)
        fields[field] = columns
    keys = {}
    for key, name in AMZ_KEY_COLUMNS.items():
        hits = [j for j, n in enumerate(norm_names) if n == _norm(name)]
        if hits:
            keys[key] = hits[0]
        else:
            missing.append(name)
    income = [j for j, (g, n) in enumerate(zip(norm_groups, norm_names))
              if g == _norm("平台收入") and n == _norm("平台收入")]
    if len(income) != 1:
        missing.append("平台收入 / 平台收入")
    if missing:
        raise ValueError("文件缺少列：" + "、".join(missing[:10]) + "，请上传领星「利润报表-MSKU」导出的原始文件")
    skip_custom = {_norm(item) for item in AMZ_CUSTOM_EXCLUDE}
    custom = {j: names[j] for j, (g, n) in enumerate(zip(norm_groups, norm_names))
              if g == _norm(AMZ_CUSTOM_GROUP) and n not in skip_custom}
    return {"fields": fields, "keys": keys, "income": income[0], "custom": custom}


def parse_lingxing_msku_workbook(content: bytes, month: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """读领星「利润报表-MSKU」手动导出：返回按 店铺+MSKU 的行（字段同原领星月表）与核对信息。"""
    import openpyxl

    try:
        workbook = openpyxl.load_workbook(io.BytesIO(content), data_only=True, read_only=True)
    except Exception as exc:
        raise ValueError("读取文件失败，请上传领星「利润报表-MSKU」导出的 .xlsx 文件") from exc
    merged: dict[tuple[str, str], dict[str, Any]] = {}
    periods: set[str] = set()
    currencies: set[str] = set()
    income_bad: list[int] = []
    try:
        rows = workbook.worksheets[0].iter_rows(values_only=True)
        groups, names = _amz_header(rows)
        index = _amz_index(groups, names)
        fields, keys = index["fields"], index["keys"]
        line = 2
        for row in rows:
            line += 1
            cells = list(row) + [None] * max(0, len(names) - len(row))
            store = str(cells[keys["store"]] or "").strip()
            if not store:
                continue
            msku = str(cells[keys["msku"]] or "").strip() or "-"
            periods.add(str(cells[keys["month"]] or "").strip())
            currencies.add(str(cells[keys["currency"]] or "").strip().upper())
            values = {field: sum((_amz_cell(cells[j], f"第{line}行「{names[j]}」") for j in columns), ZERO)
                      for field, columns in fields.items()}
            fees = {}
            for j, fee_name in index["custom"].items():
                amount = _amz_cell(cells[j], f"第{line}行「{fee_name}」")
                if amount:
                    fees[fee_name] = amount
            income = sum((values[key] for key in AMZ_INCOME_PARTS), ZERO)
            if abs(income - _amz_cell(cells[index["income"]], f"第{line}行「平台收入」")) > AMZ_TOLERANCE:
                income_bad.append(line)
            key = (store, msku)
            target = merged.get(key)
            if target is None:
                if len(merged) >= AMZ_MAX_ROWS:
                    raise ValueError(f"文件超过 {AMZ_MAX_ROWS} 行")
                merged[key] = {"store_name": store[:128], "msku": msku[:200],
                               "local_sku": str(cells[keys["sku"]] or "").strip()[:200] or None,
                               "local_name": str(cells[keys["name"]] or "").strip()[:500] or None,
                               "currency_code": AMZ_CURRENCY, **values, "other_fees": fees}
                continue
            for field, value in values.items():
                target[field] += value
            for fee_name, amount in fees.items():
                target["other_fees"][fee_name] = target["other_fees"].get(fee_name, ZERO) + amount
    finally:
        workbook.close()
    if not merged:
        raise ValueError("文件里没有数据行")
    wrong = sorted(periods - {month, f"{month}~{month}"})
    if wrong:
        raise ValueError(f"文件日期是 {'、'.join(wrong[:3])}，与所选月份 {month} 不一致；导出时请按月选择 {month}")
    other = sorted(currencies - {AMZ_CURRENCY})
    if other:
        raise ValueError(f"文件币种为 {'、'.join(other[:6])}，请在领星导出时把币种选为「人民币（CNY）」后重新导出")
    if income_bad:
        raise ValueError(f"有 {len(income_bad)} 行按公式算的平台收入与文件「平台收入」列不一致（如第 {income_bad[0]} 行），"
                         "领星导出格式可能有变化，请联系管理员")
    result = list(merged.values())
    for row in result:
        for field in AMZ_QTY_FIELDS:
            row[field] = int(row[field])
        row["other_fees"] = {name: str(value) for name, value in row["other_fees"].items()}

    def total(field: str) -> float:
        return round(float(sum((_num(row[field]) for row in result), ZERO)), 2)

    check = {"rows": len(result), "stores": len({row["store_name"] for row in result}),
             "sales_qty": int(total("sales_qty")), "sales_amount": total("sales_amount"),
             "platform_income": round(float(sum((_num(row[key]) for row in result for key in AMZ_INCOME_PARTS),
                                                ZERO)), 2),
             "purchase_cost": total("purchase_cost"), "gross_profit": total("gross_profit"),
             "removal_cost": total("removal_cost"), "transit_loss": total("transit_loss")}
    return result, check


def import_amz(content: bytes, filename: str, month: str, operator: str | None) -> dict[str, Any]:
    month = _month(month)
    if not content:
        raise ValueError("请选择领星利润报表-MSKU 文件")
    if len(content) > MAX_FILE_BYTES:
        raise ValueError("文件不能超过 50MB")
    rows, check = parse_lingxing_msku_workbook(content, month)
    stored = repo.save_amz_upload(month, rows, filename, operator, datetime.now(CHINA).replace(tzinfo=None), check)
    LOG.info("项目利润总表 领星利润报表上传 month=%s file=%s rows=%s replaced=%s", month, filename, len(rows),
             stored.get("deleted_rows"))
    return {"stat_month": month, "file_name": filename, "check": check, **stored}


# ------------------------------------------------------------------ 导出
def export_report(month: str) -> tuple[str, bytes]:
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill

    report = get_report(month)
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "小组项目利润表"
    head = ["类别", "项目", *[group["label"] for group in report["groups"]], "标准"]
    sheet.append([f"{report['stat_month']} 小组项目利润表（人民币）"])
    sheet.append(head)
    for row in report["statement"]:
        values = [row["values"].get(group["code"]) for group in report["groups"]]
        sheet.append([row["category"], ("    " if row["indent"] else "") + row["label"], *values, row.get("target")])
        line = sheet.max_row
        fmt = "0.00%" if row["unit"] == "rate" else "#,##0" if row["unit"] == "qty" else "#,##0.00"
        for column in range(3, 3 + len(values)):
            sheet.cell(line, column).number_format = fmt
        if row["strong"]:
            for column in range(1, len(head) + 1):
                sheet.cell(line, column).font = Font(bold=True)
    stores = workbook.create_sheet("店铺维度利润表")
    columns = report["stores"]["columns"]
    stores.append([f"{report['stat_month']} 店铺维度利润表（人民币，AMZ）"])
    stores.append(["组别", "主体", *[column["label"] for column in columns]])
    fill = PatternFill("solid", fgColor="EEF3F8")
    for row in [*report["stores"]["rows"], report["stores"]["total"]]:
        stores.append([row["group_code"], row["entity"], *[row.get(column["key"]) for column in columns]])
        line = stores.max_row
        for column in range(3, 3 + len(columns)):
            stores.cell(line, column).number_format = "#,##0.00"
        if row["row_type"] != "ENTITY":
            for column in range(1, 3 + len(columns)):
                stores.cell(line, column).font = Font(bold=True)
                stores.cell(line, column).fill = fill
    for ws in (sheet, stores):
        ws["A1"].font = Font(bold=True, size=12)
        for cell in ws[2]:
            cell.font = Font(bold=True)
            cell.alignment = Alignment(horizontal="center", wrap_text=True)
        ws.freeze_panes = "C3"
        ws.column_dimensions["A"].width = 16
        ws.column_dimensions["B"].width = 34 if ws is sheet else 14
    buffer = io.BytesIO()
    workbook.save(buffer)
    return f"项目利润总表-{report['stat_month']}.xlsx", buffer.getvalue()
