"""Latest Goodcang inventory × clearance landed unit cost, by owner and site."""
from collections import Counter, defaultdict
from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP
from uuid import uuid4

from backend.repositories import inventory_report_etl_repository as owners
from backend.repositories import ebay_inventory_age_ratio_repository as repository
from backend.repositories.performance_repository import named_lock
from backend.services.clearance_service import _ebay_inventory_age_rows, _optional_num
from backend.services.ebay_inventory_detail_service import CHINA, rent_site
from backend.services.inventory_report_etl_service import (
    _ebay_assignment, _ebay_product_sku_map, _ebay_rule_map,
)

BUCKETS = ("under_90", "days_90_120", "days_120_180", "over_180")
ZERO = Decimal("0")


def product_middle_code(sku):
    # SKU = brand-core-supplier-other... . Keep exactly core + supplier,
    # including letters/leading zeros; never merge different suppliers.
    parts = [part.strip() for part in str(sku or "").strip().upper().split("-")]
    return "-".join(parts[1:3]) if len(parts) >= 3 and all(parts[:3]) else None


def match_middle_code(inventory, products, rules, sku_map):
    """Match core+supplier, prefer suffix-free SKUs, then highest landed cost.

    Purchase and transport costs always come from the same candidate SKU.
    Equal maximum costs may share a price, but conflicting owners stay explicit.
    """
    index = defaultdict(list)
    for product in products:
        code = product_middle_code(product["sku"])
        if code:
            index[code].append(product)
    matches = {}
    result = []
    for item in inventory:
        code = product_middle_code(item["source_product_sku"])
        warehouse = str(item.get("warehouse_code") or "").strip().upper()
        country = "US" if warehouse in {"USEA", "USWE"} else warehouse if warehouse in {"UK", "DE", "CZ"} else None
        key = (code, country)
        if key not in matches:
            candidates = index.get(code, [])
            # All fourth-and-later segments are variants, not only YXR/RXY:
            # e.g. YXQ, GWC, YXQ-2 also fall back to the three-segment base SKU.
            normal = [p for p in candidates if len(p["sku"].strip().split("-")) == 3]
            candidates = normal or candidates
            branded = [p for p in candidates if not p["sku"].strip().upper().startswith("JMH-")]
            candidates = sorted(branded or candidates, key=lambda p: p["sku"])
            evaluations = []
            for p in candidates:
                step = _optional_num(p.get("step_price"))
                purchase = step if step is not None and step > ZERO else _optional_num(p.get("cg_price"))
                head = _optional_num(p.get("transport_costs", {}).get(country))
                owner, _ = _ebay_assignment(p["sku"], rules, sku_map)
                evaluations.append((p, purchase, head, owner))
            valid = [entry for entry in evaluations
                     if entry[1] is not None and entry[2] is not None
                     and entry[1].is_finite() and entry[2].is_finite()
                     and entry[1] >= ZERO and entry[2] >= ZERO]
            highest = max((entry[1] + entry[2] for entry in valid), default=None)
            winners = [entry for entry in valid if entry[1] + entry[2] == highest]
            owner_names = {entry[3] for entry in winners}
            reason = ("INVALID_MIDDLE_CODE" if not code else "PRODUCT_NOT_FOUND" if not candidates
                      else "COST_NOT_FOUND" if not valid
                      else "OWNER_AMBIGUOUS" if len(owner_names) > 1 else None)
            matched = winners[0][0] if winners and not reason else {}
            details = [{"sku": p["sku"], "purchase_price": str(purchase) if purchase is not None else None,
                        "first_leg_cost": str(head) if head is not None else None, "owner": owner}
                       for p, purchase, head, owner in evaluations]
            matches[key] = {
                "sku_middle": code or "", "sku": matched.get("sku"),
                "cg_price": matched.get("cg_price"), "step_price": matched.get("step_price"),
                "first_leg_cost": matched.get("transport_costs", {}).get(country),
                "source_product_batch_id": matched.get("source_product_batch_id"),
                "candidate_count": 1 if matched else 0, "non_jmh_count": 0,
                "transport_country_code": country, "middle_match_error": reason,
                "candidate_details": details,
                "matched_owner": (next(iter(owner_names)) if len(owner_names) == 1
                                  else "未分配" if owner_names else None),
            }
        result.append({**item, **matches[key]})
    return result


def clean_matched_rows(month, now, source):
    rows, _ = _ebay_inventory_age_rows(month, str(uuid4()), now.replace(tzinfo=None), source)
    for row, matched in zip(rows, source):
        row["matched_owner"] = matched["matched_owner"]
        row["candidate_details"] = matched["candidate_details"]
        if matched["middle_match_error"]:
            row["match_status"] = matched["middle_match_error"]
    return rows


def age_bucket(age):
    if age is None or age < 0:
        return None
    return BUCKETS[0] if age < 90 else BUCKETS[1] if age < 120 else BUCKETS[2] if age <= 180 else BUCKETS[3]


def _number(value):
    result = Decimal(str(value))
    if not result.is_finite():
        raise ValueError("库龄货值源数据含非有限数值，未保存快照")
    return result


def _amount(value):
    return format(value.quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP), "f")


def aggregate(rows, rules, sku_map, stat_date):
    grouped = {"owners": {}, "sites": {}}
    errors, excluded = Counter(), []
    valued_rows = 0
    for row in rows:
        # Prefer the unambiguously matched product; otherwise resolve the original
        # warehouse SKU using the same JMH mapping and fixed brands as performance.
        owner = row.get("matched_owner")
        if owner is None:
            owner, _ = _ebay_assignment(row.get("sku") or row["source_product_sku"], rules, sku_map)
        site = rent_site(row["warehouse_code"]) or "未识别站点"
        groups = []
        for dimension, key in (("owners", owner), ("sites", site)):
            group = grouped[dimension].setdefault(key, {
                "stat_date": stat_date, "name": key, "source_rows": 0,
                "valued_rows": 0, "excluded_rows": 0,
                **{bucket + "_value": ZERO for bucket in BUCKETS},
            })
            group["source_rows"] += 1
            groups.append(group)
        bucket = age_bucket(row.get("warehouse_age_days"))
        reason = row["match_status"] if row["match_status"] != "MATCHED" else None
        quantity = _number(row["inventory_quantity"])
        # Quantity metrics use every source inventory row, independently of
        # product/cost matching. Keep the existing valuation/owner rules below.
        site_group = grouped["sites"][site]
        site_group["total_quantity"] = site_group.get("total_quantity", ZERO) + quantity
        site_group["over_180_quantity"] = site_group.get("over_180_quantity", ZERO) + (
            quantity if bucket == "over_180" else ZERO)
        unit = row.get("unit_landed_cost")
        if not reason and (unit is None or _number(unit) < 0 or quantity < 0):
            reason = "INVALID_COST_OR_QUANTITY"
        if not reason and bucket is None:
            reason = "INVALID_AGE"
        if reason:
            errors[reason] += 1
            excluded.append({"sku": row["source_product_sku"], "warehouse": row["warehouse_code"],
                             "owner": owner, "reason": reason,
                             "middle_code": row.get("sku_middle"),
                             "candidates": row.get("candidate_details", [])})
            for group in groups:
                group["excluded_rows"] += 1
            continue
        value = quantity * _number(unit)
        valued_rows += 1
        for group in groups:
            group[bucket + "_value"] += value
            group["valued_rows"] += 1

    result = {}
    for dimension, groups in grouped.items():
        items = []
        for _, group in sorted(groups.items()):
            # Quantize each bucket first so the stored total always reconciles.
            amounts = {bucket: Decimal(_amount(group[bucket + "_value"])) for bucket in BUCKETS}
            total = sum(amounts.values(), ZERO)
            for bucket in BUCKETS:
                group[bucket + "_value"] = _amount(amounts[bucket]) if group["valued_rows"] else None
                group[bucket + "_ratio"] = _amount(amounts[bucket] / total) if total else None
            group["total_value"] = _amount(total) if group["valued_rows"] else None
            if dimension == "sites":
                total_quantity = group["total_quantity"]
                over_quantity = group["over_180_quantity"]
                group["total_quantity"] = _amount(total_quantity)
                group["over_180_quantity"] = _amount(over_quantity)
                group["over_180_quantity_ratio"] = _amount(over_quantity / total_quantity) if total_quantity else None
            items.append(group)
        result[dimension] = items
    return {**result, "source_rows": len(rows), "valued_rows": valued_rows,
            "excluded_rows": len(excluded), "exclusion_reasons": dict(errors), "excluded_details": excluded}


def capture_snapshot():
    with named_lock("inventory:ebay-age-ratio") as acquired:
        if not acquired:
            raise ValueError("海外仓库龄占比正在刷新，请稍后重试")
        report = build_snapshot()
        repository.save_snapshot(report)
        return report


def build_snapshot(now=None):
    """Calculate only; unified refresh publishes this alongside inventory in one transaction."""
    now = now or datetime.now(CHINA)
    month, day = now.strftime("%Y-%m"), now.date().isoformat()
    inventory, products = repository.load_source(month)
    source = inventory
    if not source:
        raise ValueError("谷仓最新库龄表没有数据，请先执行谷仓-eBay库存库龄每周刷新")
    batches = {r["source_goodcang_batch_id"] for r in source}
    if len(batches) != 1 or not next(iter(batches)):
        raise ValueError("谷仓最新库龄数据批次不完整，未保存统计")
    raw_rules = owners.owner_rules(month, "ebay")
    rules = _ebay_rule_map(raw_rules)
    if not rules:
        raise ValueError(f"缺少{month}的eBay负责人规则，请先在绩效排名导入当月规则")
    sku_map = _ebay_product_sku_map(month, include_next=False)
    matched = match_middle_code(inventory, products, rules, sku_map)
    rows = clean_matched_rows(month, now, matched)
    report = aggregate(rows, rules, sku_map, day)
    if not report["valued_rows"]:
        raise ValueError("没有可计算货值的库龄明细，请检查当月采购成本、头程成本及库龄；旧快照未覆盖")
    warnings = []
    if report["excluded_rows"]:
        warnings.append(f'{report["excluded_rows"]}条明细缺成本、产品匹配不唯一或库龄无效，未计入货值及占比；当前金额为可计算部分。')
    if any(row["name"] == "未分配" for row in report["owners"]):
        warnings.append("部分SKU未匹配负责人，保留在“未分配”中，未丢弃其货值。")
    if any(row["name"] == "未识别站点" for row in report["sites"]):
        warnings.append("存在未识别仓库，已归入“未识别站点”。")
    if any(row["pull_month"] != month for row in source):
        warnings.append("谷仓最新源数据不是当月拉取；统计日期是重新计算日期，请留意源数据拉取时间。")
    source_times = [r["source_pulled_at"] for r in source if r.get("source_pulled_at")]
    report.update(stat_date=day, generated_at=now.strftime("%Y-%m-%d %H:%M:%S"),
                  owner_month=month, cost_month=month, source_batch_id=next(iter(batches)),
                  source_pulled_at=max(source_times).isoformat(sep=" ") if source_times else None,
                  source_months=sorted({r["pull_month"] for r in source}), warnings=warnings,
                  product_batch_ids=sorted({r["source_product_batch_id"] for r in rows if r.get("source_product_batch_id")}),
                  calculation_version="core-supplier-max-landed-cost-v4",
                  site_calculation_version="site-inventory-over180-v1")
    return report


def read_range(start_date, end_date):
    if not start_date or not end_date:
        raise ValueError("请同时提供开始日期和结束日期")
    for value in (start_date, end_date):
        try:
            if date.fromisoformat(value).isoformat() != value:
                raise ValueError()
        except (TypeError, ValueError):
            raise ValueError("统计日期必须为YYYY-MM-DD") from None
    if start_date > end_date:
        raise ValueError("开始日期不能晚于结束日期")
    return repository.read_range(start_date, end_date)


def read_snapshot(stat_date=None):
    if stat_date and stat_date != "latest":
        try:
            if date.fromisoformat(stat_date).isoformat() != stat_date:
                raise ValueError()
        except (TypeError, ValueError):
            raise ValueError("统计日期必须为YYYY-MM-DD") from None
    return repository.read_snapshot(stat_date)
