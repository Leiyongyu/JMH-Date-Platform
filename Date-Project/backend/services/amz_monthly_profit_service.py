"""AMZ 月度利润表（财务中心）：照财务手工表「AMZ利润报表-结算」的「店铺利润-CNY」「小组利润-CNY」两张表出数。

口径（与手工表一致，2026-09 逐行核对过）：
- 数据：领星利润报表-MSKU（结算、按月、人民币），见 amz_monthly_profit_sync_service。
- 剔除与归属：与月度库存、AMZ利润报表同一套规则（amz_profit_report_service._classify）——
  剔除关停店铺（斯露星、斯鑫雅、水金余等）；智贸云、优贝诺只保留 MSKU 含 zmy/dsq 的；
  组别取店铺名前缀（EU/US1/US2/US3），店铺名取中间段，不属于这四个部门的（如信博嘉立）不进报表。
- 店铺利润：按 组别 + 店铺名 汇总；最终毛利 = 毛利润 − FBA途损抵扣（途损抵扣本身为负数，即加回途损成本）。
- 小组利润：按组别汇总；US3 按月度库存的部门规则拆成 MJ（新志楠、富琳顿）与 ZXY（其余），小组行跟在
  US3 后面，US3 = MJ + ZXY。手工补充费用只能记在末级行（EU / US1 / US2 / MJ / ZXY）上，记到哪一列就加到
  哪一列，并计入最终毛利；「补充费用」列放不属于任何现有费用列的金额。
- 比率：毛利率 = 最终毛利 ÷（销售额＋买家运费＋促销折扣＋FBA库存赔偿＋其他收入＋收入退款额＋费用退款额）；
  各费用占比 = 费用 ÷（销售额＋买家运费＋促销折扣＋FBA库存赔偿＋其他收入）；退款率、退货率 = 数量 ÷ 销量。
  分母为 0 时返回 None（页面显示 --），不当 0。
"""
from __future__ import annotations

import logging
import re
from collections import defaultdict
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from io import BytesIO
from typing import Any, Sequence

from backend.repositories import amz_monthly_profit_repository as repo
from backend.repositories import inventory_report_etl_repository as inventory_repo
from backend.services import amz_profit_report_service as profit_report
from backend.services import inventory_report_etl_service as inventory

LOG = logging.getLogger(__name__)
ZERO = Decimal("0")
MONEY = Decimal("0.01")
RATE = Decimal("0.000001")
MONTH = re.compile(r"^20\d{2}-(0[1-9]|1[0-2])$")
GROUP_ORDER = ("EU", "US1", "US2", "US3")
MAX_ADJUSTMENT = Decimal("100000000")

# 领星自定义费用名 → 报表列。站外推广费走 customOrderFee（custom_order_fee），手工表的利润表里不单列。
CUSTOM_FEES = (
    ("store_tax_fee", "店铺税务相关"), ("warehouse_fee", "仓库费用"), ("store_operation_fee", "店铺运营费"),
    ("slow_moving_fee", "滞销库存费用"), ("tax_risk_fee", "税务风险金"), ("store_rent_fee", "店租费（法人补贴等）"),
)
CUSTOM_FEE_BY_NAME = {name: key for key, name in CUSTOM_FEES}
# 手工补充费用可以记到的列。
ADJUSTMENT_ITEMS = (*CUSTOM_FEES, ("supplement_fee", "补充费用"))
ADJUSTMENT_LABELS = dict(ADJUSTMENT_ITEMS)

SUM_FIELDS = (
    "sales_qty", "refunds_qty", "returns_qty", "sales_amount", "shipping_credits", "promotional_rebates",
    "fba_inventory_credit", "other_in_amount", "sales_refunds", "fee_refunds", "platform_fee",
    "fba_delivery_fee", "other_transaction_fees", "ads_cost", "promotion_fee", "storage_fee",
    "inbound_convenience_fee", "adjustment_fee", "platform_other_fee",
    *(key for key, _ in CUSTOM_FEES), "purchase_cost", "first_leg_cost", "gross_profit", "transit_loss",
)
QTY_KEYS = {"sales_qty", "refunds_qty", "returns_qty"}
MARGIN_BASE = ("sales_amount", "shipping_credits", "promotional_rebates", "fba_inventory_credit",
               "other_in_amount", "sales_refunds", "fee_refunds")
SHARE_BASE = ("sales_amount", "shipping_credits", "promotional_rebates", "fba_inventory_credit", "other_in_amount")
SHARES = (("platform_fee_ratio", "platform_fee"), ("fba_delivery_fee_ratio", "fba_delivery_fee"),
          ("ads_cost_ratio", "ads_cost"), ("storage_fee_ratio", "storage_fee"),
          ("purchase_cost_ratio", "purchase_cost"), ("first_leg_cost_ratio", "first_leg_cost"))

# 表头与手工表一致（店铺利润-CNY / 小组利润-CNY）。kind：qty / money / rate。
_COMMON_HEAD = (
    ("sales_qty", "销量", "qty"), ("refunds_qty", "退款量", "qty"), ("returns_qty", "退货量", "qty"),
    ("sales_amount", "销售额", "money"), ("shipping_credits", "买家运费", "money"),
    ("promotional_rebates", "促销折扣", "money"), ("fba_inventory_credit", "FBA库存赔偿", "money"),
    ("other_in_amount", "其他收入", "money"), ("sales_refunds", "收入退款额", "money"),
    ("fee_refunds", "费用退款额", "money"), ("platform_fee", "平台费", "money"),
    ("fba_delivery_fee", "FBA发货费", "money"), ("other_transaction_fees", "其他订单费用", "money"),
    ("ads_cost", "广告费", "money"), ("promotion_fee", "推广费", "money"), ("storage_fee", "FBA仓储费", "money"),
    ("inbound_convenience_fee", "入库配置费", "money"), ("adjustment_fee", "调整费用", "money"),
    ("platform_other_fee", "平台其他费", "money"),
    *((key, label, "money") for key, label in CUSTOM_FEES),
)
_RATIOS_HEAD = (
    ("gross_margin", "毛利率", "rate"), ("refund_rate", "退款率", "rate"), ("return_rate", "退货率", "rate"),
    ("platform_fee_ratio", "平台费占比", "rate"), ("fba_delivery_fee_ratio", "FBA发货费占比", "rate"),
    ("ads_cost_ratio", "广告费占比", "rate"), ("storage_fee_ratio", "FBA仓储费占比", "rate"),
    ("purchase_cost_ratio", "采购成本占比", "rate"), ("first_leg_cost_ratio", "头程成本占比", "rate"),
)
STORE_COLUMNS = (
    *_COMMON_HEAD, ("purchase_cost", "采购成本", "money"), ("first_leg_cost", "头程成本", "money"),
    ("gross_profit", "毛利润", "money"), ("transit_loss", "FBA途损", "money"),
    ("final_profit", "最终毛利", "money"), *_RATIOS_HEAD,
)
GROUP_COLUMNS = (
    *_COMMON_HEAD, ("supplement_fee", "补充费用", "money"), ("purchase_cost", "采购成本", "money"),
    ("first_leg_cost", "头程成本", "money"), ("transit_loss", "FBA途损抵扣", "money"),
    ("final_profit", "最终毛利", "money"), *_RATIOS_HEAD,
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
    except InvalidOperation:
        return ZERO


def _empty() -> dict[str, Decimal]:
    return {key: ZERO for key in (*SUM_FIELDS, "supplement_fee")}


def _period_label(month: str) -> str:
    year, number = (int(part) for part in month.split("-"))
    last = (date(year + number // 12, number % 12 + 1, 1) - date(year, number, 1)).days
    return f"{month}-01~{month}-{last:02d}"


def _ratio(numerator: Decimal, denominator: Decimal) -> Decimal | None:
    if not denominator:
        return None
    return (numerator / denominator).quantize(RATE, rounding=ROUND_HALF_UP)


def _finish(sums: dict[str, Decimal]) -> dict[str, Any]:
    """汇总值 → 一行输出：最终毛利、各比率；金额保留两位。"""
    final = sums["gross_profit"] - sums["transit_loss"] + sums.get("adjustments_total", ZERO)
    margin_base = sum((sums[key] for key in MARGIN_BASE), ZERO)
    share_base = sum((sums[key] for key in SHARE_BASE), ZERO)
    out: dict[str, Any] = {}
    for key, value in sums.items():
        if key == "adjustments_total":
            continue
        out[key] = int(value) if key in QTY_KEYS else value.quantize(MONEY, rounding=ROUND_HALF_UP)
    out["final_profit"] = final.quantize(MONEY, rounding=ROUND_HALF_UP)
    out["gross_margin"] = _ratio(final, margin_base)
    out["refund_rate"] = _ratio(sums["refunds_qty"], sums["sales_qty"])
    out["return_rate"] = _ratio(sums["returns_qty"], sums["sales_qty"])
    for ratio_key, field in SHARES:
        out[ratio_key] = _ratio(sums[field], share_base)
    return out


def _add(target: dict[str, Decimal], source: dict[str, Decimal]) -> None:
    for key, value in source.items():
        target[key] = target.get(key, ZERO) + value


# ------------------------------------------------------------ 组别与小组
# 与月度库存同一套部门划分（inventory.DEPARTMENTS）：US3 按店铺拆成 MJ（新志楠、富琳顿）与 ZXY（其余）。
# 部门 → (组别, 小组)。小组行跟在组别行后面，组别行 = 各小组之和。
DEPARTMENT_ROWS = {
    "AMZ-EU": ("EU", None), "AMZ-US1": ("US1", None), "AMZ-US2": ("US2", None),
    "AMZ-US2-MJ": ("US3", "MJ"), "AMZ-US1-ZXY": ("US3", "ZXY"),
}
SUBTEAMS = {"US3": ("MJ", "ZXY")}
# 可以记补充费用的末级行（没有小组的组别，或小组）。
LEAF_CODES = ("EU", "US1", "US2", "MJ", "ZXY")


# ------------------------------------------------------------ 报表
def build_report(month: str, rows: Sequence[dict[str, Any]], *, shops: dict[str, str],
                 rules: Any, adjustments: Sequence[dict[str, Any]]) -> dict[str, Any]:
    """纯计算：MSKU 月度行 + 补充费用 → 店铺利润、小组利润两张表。"""
    excluded: dict[str, int] = defaultdict(int)
    unknown_fees: dict[str, Decimal] = defaultdict(Decimal)
    stores: dict[tuple[str, str], dict[str, Decimal]] = defaultdict(_empty)
    leaf_of_store: dict[tuple[str, str], str] = {}
    for row in rows:
        key = profit_report._classify(row, "STORE", shops, rules, excluded)
        if key is None:
            continue
        mapped = DEPARTMENT_ROWS.get(key[0])
        if mapped is None:
            excluded["unmatched_department"] += 1
            continue
        group, team = mapped
        store_key = (group, key[1])
        leaf_of_store[store_key] = team or group
        sums = stores[store_key]
        for field in SUM_FIELDS:
            if field in CUSTOM_FEE_BY_NAME.values():
                continue
            sums[field] += _num(row.get(field))
        for name, value in (row.get("other_fees") or {}).items():
            column = CUSTOM_FEE_BY_NAME.get(name)
            if column:
                sums[column] += _num(value)
            else:
                unknown_fees[name] += _num(value)

    def order(item):
        (group, store), _ = item
        team = leaf_of_store[(group, store)]
        teams = SUBTEAMS.get(group, ())
        return (GROUP_ORDER.index(group), teams.index(team) if team in teams else -1, store)

    store_rows = [{"group_code": group, "subteam_code": None if leaf_of_store[(group, store)] == group
                   else leaf_of_store[(group, store)], "store_name": store, **_finish(dict(sums))}
                  for (group, store), sums in sorted(stores.items(), key=order)]
    store_total = _empty()
    for sums in stores.values():
        _add(store_total, sums)

    # 小组利润：店铺落到末级行，加补充费用；有小组的组别行 = 各小组之和。
    leaf_sums: dict[str, dict[str, Decimal]] = defaultdict(_empty)
    for store_key, sums in stores.items():
        _add(leaf_sums[leaf_of_store[store_key]], sums)
    applied = 0
    for item in adjustments:
        code, fee = str(item.get("row_code")), str(item.get("fee_item"))
        if code not in LEAF_CODES or fee not in ADJUSTMENT_LABELS:
            continue
        amount = _num(item.get("amount"))
        target = leaf_sums[code]
        target[fee] = target.get(fee, ZERO) + amount
        target["adjustments_total"] = target.get("adjustments_total", ZERO) + amount
        applied += 1
    group_rows, total = [], _empty()
    for group in GROUP_ORDER:
        teams = SUBTEAMS.get(group, ())
        if teams:
            present = [team for team in teams if team in leaf_sums]
            if not present:
                continue
            group_sums = _empty()
            for team in present:
                _add(group_sums, leaf_sums[team])
            team_rows = [{"row_code": team, "group_code": group, "row_type": "SUBTEAM",
                          **_finish(dict(leaf_sums[team]))} for team in present]
        else:
            if group not in leaf_sums:
                continue
            group_sums, team_rows = leaf_sums[group], []
        _add(total, group_sums)
        group_rows.append({"row_code": group, "group_code": group, "row_type": "GROUP", **_finish(dict(group_sums))})
        group_rows.extend(team_rows)
    notices = []
    if unknown_fees:
        notices.append("领星有未单列的自定义费用（已计入毛利润）：" + "、".join(
            f"{name} {value.quantize(MONEY)}" for name, value in sorted(unknown_fees.items())))
    return {
        "stat_month": month,
        "period": _period_label(month),
        "currency_code": "CNY",
        "store_rows": store_rows,
        "store_total": {"row_code": "TOTAL", **_finish(dict(store_total))},
        "group_rows": group_rows,
        "group_total": {"row_code": "TOTAL", **_finish(dict(total))},
        "excluded": dict(excluded),
        "adjustment_count": applied,
        "notices": notices,
    }


def list_months(limit: int = 36) -> list[dict[str, Any]]:
    return [{"stat_month": row["stat_month"], "msku_rows": int(row["msku_rows"] or 0),
             "pulled_at": _text_time(row.get("pulled_at")), "sync_batch_id": row.get("sync_batch_id")}
            for row in repo.months(limit)]


def _text_time(value: Any) -> str | None:
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M:%S")
    return str(value) if value else None


def get_report(month: str) -> dict[str, Any]:
    month = _month(month)
    rows = repo.msku_rows(month)
    if not rows:
        raise ValueError(f"{month} 还没有拉取领星利润报表数据，请先在定时任务里执行「AMZ月度利润表数据拉取」")
    meta = next((item for item in repo.months(120) if item["stat_month"] == month), {})
    rules = inventory._amazon_rule_maps(inventory_repo.owner_rules(month, "amazon"))
    report = build_report(month, rows, shops=inventory_repo.amazon_shop_map(), rules=rules,
                          adjustments=repo.adjustments(month))
    report["pulled_at"] = _text_time(meta.get("pulled_at"))
    report["reconcile_notice"] = _reconcile_notice(month, rows)
    report["leaf_codes"] = list(LEAF_CODES)
    report["adjustment_items"] = [{"key": key, "label": label} for key, label in ADJUSTMENT_ITEMS]
    report["store_columns"] = [{"key": key, "label": label, "kind": kind} for key, label, kind in STORE_COLUMNS]
    report["group_columns"] = [{"key": key, "label": label, "kind": kind} for key, label, kind in GROUP_COLUMNS]
    if report["reconcile_notice"]:
        report["notices"].insert(0, report["reconcile_notice"])
    return report


def _reconcile_notice(month: str, rows: Sequence[dict[str, Any]]) -> str | None:
    """店铺接口 vs MSKU 加总：销量或销售额对不上的店铺数（拉取不完整时提示）。"""
    seller = repo.seller_rows(month)
    if not seller:
        return None
    msku: dict[str, list[Decimal]] = defaultdict(lambda: [ZERO, ZERO])
    for row in rows:
        msku[str(row["sid"])][0] += _num(row["sales_qty"])
        msku[str(row["sid"])][1] += _num(row["sales_amount"])
    bad = [row.get("store_name") or row["sid"] for row in seller
           if msku[str(row["sid"])][0] != _num(row["sales_qty"])
           or abs(msku[str(row["sid"])][1] - _num(row["sales_amount"])) > 1]
    if not bad:
        return None
    return f"有 {len(bad)} 家店 MSKU 加总与领星店铺报表不一致（{'、'.join(map(str, bad[:5]))}{'…' if len(bad) > 5 else ''}），可能拉取不完整，建议重新拉取"


# ------------------------------------------------------------ 补充费用
def _adjustment_payload(month: str, payload: dict[str, Any], operator: str | None) -> dict[str, Any]:
    code = str(payload.get("row_code") or "").strip()
    fee = str(payload.get("fee_item") or "").strip()
    if code not in LEAF_CODES:
        raise ValueError(f"只能记在末级行上：{'、'.join(LEAF_CODES)}（US3 请记到 MJ 或 ZXY）")
    if fee not in ADJUSTMENT_LABELS:
        raise ValueError("费用列无效")
    try:
        amount = Decimal(str(payload.get("amount"))).quantize(MONEY, rounding=ROUND_HALF_UP)
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
    return {"id": repo.insert_adjustment(_adjustment_payload(month, payload, operator))}


def update_adjustment(adjustment_id: int, payload: dict[str, Any], operator: str | None) -> dict[str, Any]:
    current = repo.adjustment(adjustment_id)
    if not current:
        raise ValueError("补充费用不存在或已删除")
    row = _adjustment_payload(current["stat_month"], payload, operator)
    repo.update_adjustment(adjustment_id, row)
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
    header_font = Font(bold=True, color="FFFFFF")
    header_fill = PatternFill("solid", fgColor="24486D")
    total_font = Font(bold=True)
    formats = {"money": "#,##0.00", "rate": "0.00%", "qty": "#,##0"}

    def sheet(ws, keys_head, rows, total, label_columns):
        head = ["日期", *[label for label, _ in label_columns], *[label for _, label, _ in keys_head]]
        ws.append(head)
        for cell in ws[1]:
            cell.font, cell.fill = header_font, header_fill
            cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        for row in [*rows, total]:
            is_total = row is total
            values = [report["period"] if not is_total else "总计",
                      *[("" if is_total else row.get(key)) for _, key in label_columns]]
            for key, _, kind in keys_head:
                value = row.get(key)
                values.append(float(value) if isinstance(value, Decimal) else value)
            ws.append(values)
            for index, (_, _, kind) in enumerate(keys_head, start=len(label_columns) + 2):
                ws.cell(ws.max_row, index).number_format = formats[kind]
            if is_total:
                for cell in ws[ws.max_row]:
                    cell.font = total_font
        ws.freeze_panes = ws.cell(2, len(label_columns) + 2)
        for index in range(1, len(head) + 1):
            ws.column_dimensions[ws.cell(1, index).column_letter].width = 13
        ws.column_dimensions["A"].width = 22

    first = workbook.active
    first.title = "店铺利润-CNY"
    sheet(first, STORE_COLUMNS, report["store_rows"], report["store_total"],
          (("组别", "group_code"), ("店铺名", "store_name")))
    second = workbook.create_sheet("小组利润-CNY")
    sheet(second, GROUP_COLUMNS, report["group_rows"], report["group_total"], (("组别", "row_code"),))
    notes = workbook.create_sheet("说明")
    for line in (
        f"统计月份：{report['period']}（结算口径，人民币，领星利润报表按月汇总）",
        f"数据拉取时间：{report.get('pulled_at') or '--'}（领星月结后数据仍可能调整，以拉取时快照为准）",
        "剔除：关停店铺；智贸云、优贝诺只保留 MSKU 含 zmy/dsq 的；非 EU/US1/US2/US3 部门的店铺",
        "最终毛利 = 毛利润 − FBA途损抵扣 + 手工补充费用",
        "毛利率 = 最终毛利 ÷（销售额+买家运费+促销折扣+FBA库存赔偿+其他收入+收入退款额+费用退款额）",
        "各费用占比 = 费用 ÷（销售额+买家运费+促销折扣+FBA库存赔偿+其他收入）",
        *report["notices"],
    ):
        notes.append([line])
    notes.column_dimensions["A"].width = 120
    output = BytesIO()
    workbook.save(output)
    return f"AMZ月度利润表-{report['stat_month']}.xlsx", output.getvalue()
