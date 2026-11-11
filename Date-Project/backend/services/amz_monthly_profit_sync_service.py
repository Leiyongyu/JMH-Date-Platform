"""AMZ 月度利润表数据拉取：领星「利润报表」MSKU + 店铺，结算口径、按月汇总、人民币。

- 两个接口都传 monthlyQuery=true、summaryEnabled=true、currencyCode=CNY：领星直接按它自己的汇率折成人民币，
  与在领星页面导出的「AMZ利润报表-结算」逐店一致（2026-09 实测 98 家店销量、销售额分毫不差）。
  不用系统月度汇率自己换算 —— 领星的折算率与系统「我的汇率」不同，换算后对不上导出件。
- FBA 途损抵扣：MSKU 记录里采购 / 头程 / 其他三类成本明细（cgPriceDetails 等），按业务类型编码
  226（FBA发货途损）+ 11（FBA途损补回）的金额加总。
- 店铺接口只用来核对：MSKU 按店铺加总与店铺接口的销量、销售额对不上时记在结果里（警告，不阻断）。
- 领星月结后数据还会调整（尤其途损），所以每次拉取整月替换，并记下 pulled_at：报表就是那一刻的快照。
- 分页、限流间隔、重试沿用 AMZ 利润报表同步的 _Api。
"""
from __future__ import annotations

import json
import logging
import time
from collections import defaultdict
from datetime import datetime
from decimal import Decimal
from typing import Any, Callable, Iterable
from uuid import uuid4

from backend.integrations.lingxing.client import LingXingClient
from backend.repositories import amz_monthly_profit_repository as repo
from backend.services.amazon_profit_sync_service import previous_natural_month
from backend.services.amz_profit_report_sync_service import _Api, _decimal, _text

LOG = logging.getLogger(__name__)
TASK_CODE = "amz_monthly_profit_sync"
TASK_NAME = "AMZ月度利润表数据拉取"
MSKU_PATH = "bd/profit/report/open/report/msku/list"
SELLER_PATH = "bd/profit/report/open/report/seller/list"
CURRENCY = "CNY"
# 每条 MSKU 记录带三段成本明细，单页太大会拖慢接口；1000 条一页，一个月十几页。
MSKU_PAGE_SIZE = 1000
SELLER_PAGE_SIZE = 1000
INTERVAL_SECONDS = 0.2
TRANSIT_CODES = ("226", "11")  # FBA发货途损、FBA途损补回
COST_DETAIL_FIELDS = ("cgPriceDetails", "cgTransportCostsDetails", "cgOtherCostsDetails")
RECONCILE_TOLERANCE = Decimal("1")
QTY_FIELDS = (("sales_qty", "totalSalesQuantity"), ("refunds_qty", "refundsQuantity"),
              ("returns_qty", "fbaReturnsQuantity"))
MONEY_FIELDS = (
    ("sales_amount", "totalSalesAmount"), ("shipping_credits", "shippingCredits"),
    ("promotional_rebates", "promotionalRebates"), ("fba_inventory_credit", "fbaInventoryCredit"),
    ("cash_on_delivery", "cashOnDelivery"), ("other_in_amount", "otherInAmount"),
    ("sales_refunds", "totalSalesRefunds"), ("fee_refunds", "totalFeeRefunds"),
    ("platform_fee", "platformFee"), ("fba_delivery_fee", "totalFbaDeliveryFee"),
    ("other_transaction_fees", "otherTransactionFees"), ("ads_cost", "totalAdsCost"),
    ("promotion_fee", "promotionFee"), ("storage_fee", "totalStorageFee"),
    ("inbound_convenience_fee", "sharedFbaInboundConvenienceFee"),
    ("international_inbound_fee", "sharedFbaIntegerernationalInboundFee"),
    ("adjustment_fee", "adjustments"), ("platform_other_fee", "totalPlatformOtherFee"),
    ("custom_order_fee", "customOrderFee"), ("sales_tax", "totalSalesTax"),
    ("sales_tax_refund", "salesTaxRefund"), ("market_tax", "salesTaxWithheld"),
    ("market_tax_refund", "refundTaxWithheld"), ("purchase_cost", "cgPriceTotal"),
    ("first_leg_cost", "cgTransportCostsTotal"), ("other_cost", "cgOtherCostsTotal"),
    ("gross_profit", "grossProfit"),
)


class AmzMonthlyProfitSyncError(RuntimeError):
    """带 stage / metrics，调度器据此还原失败运行记录。"""

    def __init__(self, stage: str, message: str, metrics: dict[str, Any]):
        super().__init__(message)
        self.stage = stage
        self.metrics = dict(metrics)


def _month(value: str | None) -> str:
    text = str(value or "").strip() or previous_natural_month()
    datetime.strptime(text, "%Y-%m")
    return text


def _body(month: str) -> dict[str, Any]:
    return {"monthlyQuery": True, "summaryEnabled": True, "startDate": month, "endDate": month,
            "currencyCode": CURRENCY}


def _detail_items(value: Any) -> Iterable[dict[str, Any]]:
    """成本明细：开放接口是 JSON 数组字符串，MCP 返回的是多段 JSON 用 ",," 拼接；两种都认。"""
    if value is None or value == "":
        return
    if isinstance(value, dict):
        yield value
        return
    if isinstance(value, list):
        for item in value:
            yield from _detail_items(item)
        return
    for chunk in str(value).split(",,"):
        chunk = chunk.strip()
        if not chunk:
            continue
        try:
            parsed = json.loads(chunk)
        except ValueError:
            continue
        yield from _detail_items(parsed)


def transit_loss(record: dict[str, Any]) -> Decimal:
    """FBA 途损抵扣 = 三类成本明细里 226（发货途损）与 11（途损补回）的金额之和。"""
    total = Decimal("0")
    for field in COST_DETAIL_FIELDS:
        for item in _detail_items(record.get(field)):
            for code in TRANSIT_CODES:
                entry = item.get(code)
                if isinstance(entry, dict):
                    total += _decimal(entry.get("amount"))
    return total


def custom_fees(record: dict[str, Any]) -> dict[str, str]:
    """otherFeeStr（领星里录入的自定义费用）按费用名汇总，金额保留原值字符串。"""
    sums: dict[str, Decimal] = defaultdict(Decimal)
    for item in record.get("otherFeeStr") or []:
        if isinstance(item, dict) and _text(item.get("otherFeeName")):
            sums[_text(item.get("otherFeeName"))] += _decimal(item.get("feeAllocation"))
    return {name: str(value) for name, value in sums.items()}


def msku_row(record: dict[str, Any], common: dict[str, Any]) -> dict[str, Any]:
    sid, msku = _text(record.get("sid")), _text(record.get("msku")) or "-"
    if not sid:
        raise ValueError("领星利润报表-MSKU 记录缺少 sid")
    row = {**common, "sid": sid, "msku": msku, "store_name": _text(record.get("storeName")) or None,
           "local_sku": _text(record.get("localSku")) or None,
           "local_name": (_text(record.get("localName")) or None),
           "currency_code": _text(record.get("currencyCode")) or CURRENCY}
    if row["currency_code"] != CURRENCY:
        raise ValueError(f"领星利润报表-MSKU 返回币种 {row['currency_code']}，应为 {CURRENCY}")
    row.update({column: int(_decimal(record.get(field))) for column, field in QTY_FIELDS})
    row.update({column: _decimal(record.get(field)) for column, field in MONEY_FIELDS})
    row["transit_loss"] = transit_loss(record)
    row["other_fees"] = custom_fees(record)
    if row["local_name"] and len(row["local_name"]) > 500:
        row["local_name"] = row["local_name"][:500]
    return row


def seller_row(record: dict[str, Any], common: dict[str, Any]) -> dict[str, Any]:
    return {**common, "sid": _text(record.get("sid")), "store_name": _text(record.get("storeName")) or None,
            "country_code": _text(record.get("countryCode")) or None,
            "currency_code": _text(record.get("currencyCode")) or CURRENCY,
            "sales_qty": int(_decimal(record.get("totalSalesQuantity"))),
            "sales_amount": _decimal(record.get("totalSalesAmount")),
            "gross_profit": _decimal(record.get("grossProfit"))}


def merge_msku(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """同一 (店铺, MSKU) 出现多条时合并（接口分页偶有重复键），数值相加。"""
    merged: dict[tuple[str, str], dict[str, Any]] = {}
    for row in rows:
        key = (row["sid"], row["msku"])
        if key not in merged:
            merged[key] = row
            continue
        target = merged[key]
        for column, _ in (*QTY_FIELDS, *MONEY_FIELDS):
            target[column] += row[column]
        target["transit_loss"] += row["transit_loss"]
        fees = defaultdict(Decimal, {k: Decimal(v) for k, v in target["other_fees"].items()})
        for name, value in row["other_fees"].items():
            fees[name] += Decimal(value)
        target["other_fees"] = {k: str(v) for k, v in fees.items()}
    return list(merged.values())


def reconcile(msku: list[dict[str, Any]], seller: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """MSKU 按店铺加总 vs 店铺接口：销量、销售额对不上的店铺（警告）。"""
    totals: dict[str, dict[str, Decimal]] = defaultdict(lambda: defaultdict(Decimal))
    names: dict[str, str] = {}
    for row in msku:
        totals[row["sid"]]["msku_qty"] += row["sales_qty"]
        totals[row["sid"]]["msku_amount"] += row["sales_amount"]
        names[row["sid"]] = row.get("store_name") or names.get(row["sid"], "")
    for row in seller:
        totals[row["sid"]]["seller_qty"] += row["sales_qty"]
        totals[row["sid"]]["seller_amount"] += row["sales_amount"]
        names[row["sid"]] = row.get("store_name") or names.get(row["sid"], "")
    diffs = []
    for sid, value in sorted(totals.items()):
        if (value["msku_qty"] != value["seller_qty"]
                or abs(value["msku_amount"] - value["seller_amount"]) > RECONCILE_TOLERANCE):
            diffs.append({"sid": sid, "store_name": names.get(sid), "msku_qty": int(value["msku_qty"]),
                          "seller_qty": int(value["seller_qty"]), "msku_amount": str(value["msku_amount"]),
                          "seller_amount": str(value["seller_amount"])})
    return diffs


def sync_amz_monthly_profit(
    stat_month: str | None = None,
    *,
    client: LingXingClient | None = None,
    sleep: Callable[[float], None] = time.sleep,
    replace: Callable[..., dict[str, int]] | None = None,
) -> dict[str, Any]:
    month = _month(stat_month)
    replace = replace or repo.replace_month
    batch_id = str(uuid4())
    pulled_at = datetime.now().replace(microsecond=0)
    common = {"stat_month": month, "sync_batch_id": batch_id, "pulled_at": pulled_at}
    metrics: dict[str, Any] = {"stat_month": month, "sync_batch_id": batch_id, "currency_code": CURRENCY,
                               "pulled_at": pulled_at.strftime("%Y-%m-%d %H:%M:%S"),
                               "extract_rows": 0, "ods_rows": 0}
    stage = "EXTRACT_SELLER"
    started = time.monotonic()
    try:
        api = _Api(client or LingXingClient(), sleep)
        LOG.info("AMZ月度利润拉取开始 month=%s batch=%s", month, batch_id)
        seller = [seller_row(record, common)
                  for page in api._pages(SELLER_PATH, _body(month), SELLER_PAGE_SIZE, INTERVAL_SECONDS)
                  for record in page]
        metrics["seller_records"] = len(seller)
        stage = "EXTRACT_MSKU"
        records, raw_rows = 0, []
        for page in api._pages(MSKU_PATH, _body(month), MSKU_PAGE_SIZE, INTERVAL_SECONDS):
            records += len(page)
            raw_rows.extend(msku_row(record, common) for record in page)
            LOG.info("AMZ月度利润拉取 month=%s MSKU 累计%s条 已用时%.0f秒", month, records,
                     time.monotonic() - started)
        msku = merge_msku(raw_rows)
        metrics.update(msku_records=records, extract_rows=records + len(seller))
        stage = "TRANSFORM"
        if not msku or not seller:
            missing = "、".join(name for name, rows in (("利润报表-MSKU", msku), ("利润报表-店铺", seller)) if not rows)
            raise ValueError(f"{month} 领星未返回{missing}数据，为防止覆盖已有月份，本次未写入")
        metrics["reconcile_diff_stores"] = reconcile(msku, seller)
        metrics["transit_loss_total"] = str(sum((row["transit_loss"] for row in msku), Decimal("0")))
        stage = "LOAD"
        stored = replace(month, msku, seller)
    except AmzMonthlyProfitSyncError:
        raise
    except Exception as exc:
        LOG.warning("AMZ月度利润拉取失败 month=%s 阶段=%s 原因=%s", month, stage, str(exc)[:300])
        raise AmzMonthlyProfitSyncError(
            stage, f"AMZ月度利润表数据拉取失败（{stage}），原有月份数据保持不变：{exc}", metrics) from exc
    LOG.info("AMZ月度利润拉取完成 month=%s MSKU=%s 店铺=%s 核对差异店铺=%s 耗时%.0f秒", month,
             stored["msku_rows"], stored["seller_rows"], len(metrics["reconcile_diff_stores"]),
             time.monotonic() - started)
    return {**metrics, **stored, "ods_rows": stored["msku_rows"] + stored["seller_rows"],
            "inserted_rows": stored["msku_rows"] + stored["seller_rows"], "status": "completed"}
