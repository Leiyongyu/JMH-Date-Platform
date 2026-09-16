"""Owner/site pivot captured after weekly publication, preserving actual generation dates."""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP

from backend.repositories import ebay_inventory_pivot_repository as repository
from backend.repositories.performance_repository import named_lock
from backend.services.ebay_inventory_detail_service import CHINA, load_calculated_inventory

QUANTITIES = ("overseas_sellable_quantity", "overseas_total_quantity", "sales_qty_30d")
AMOUNTS = ("overseas_sellable_value", "overseas_total_value", "warehouse_rent_30d_cny")
ZERO = Decimal(0)


def aggregate_inventory(items):
    """Sum present Decimal amounts, skip missing values; an entirely missing amount stays None."""
    groups = {}
    seen = set()
    for item in items:
        owner = str(item.get("owner") or "未分配").strip() or "未分配"
        site, sku = str(item.get("site") or "").strip(), str(item.get("sku") or "").strip()
        if not site or not sku or (site, sku) in seen:
            raise ValueError("库存明细存在重复或空站点/SKU，未保存历史透视")
        seen.add((site, sku))
        key = (owner, site)
        group = groups.setdefault(key, {
            "owner": owner, "site": site, "sku_count": 0,
            **{field: ZERO for field in QUANTITIES},
            **{field: None for field in AMOUNTS},
            "missing_price_count": 0, "missing_rent_count": 0,
        })
        group["sku_count"] += 1
        for field in QUANTITIES:
            value = item.get(field)
            if value is None:
                raise ValueError("库存明细数量缺失，未保存历史透视")
            group[field] += Decimal(str(value))
        for field in AMOUNTS:
            value = item.get(field)
            if value is not None:
                # Missing money does not remove this SKU's stock, sales or SKU count.
                # None remains only if no SKU supplies this specific amount; 0 is valid.
                group[field] = (group[field] if group[field] is not None else ZERO) + Decimal(str(value))
        group["missing_price_count"] += int(any(item.get(field) is None for field in AMOUNTS[:2]))
        group["missing_rent_count"] += int(item.get("warehouse_rent_30d_cny") is None)
    result = []
    for _, group in sorted(groups.items()):
        sales = group["sales_qty_30d"]
        group["in_stock_sales_ratio"] = group["overseas_sellable_quantity"] / sales if sales else ZERO
        group["total_stock_sales_ratio"] = group["overseas_total_quantity"] / sales if sales else ZERO
        for field in QUANTITIES + AMOUNTS + ("in_stock_sales_ratio", "total_stock_sales_ratio"):
            value = group[field]
            if value is not None:
                if not value.is_finite():
                    raise ValueError("历史透视含非有限数值，未保存")
                group[field] = value.quantize(Decimal("0.01" if field in AMOUNTS else "0.000001"), rounding=ROUND_HALF_UP)
        result.append(group)
    return result


def capture_snapshot(expected_inventory_batch: str | None = None, trigger_type="MANUAL"):
    # One lock spans read+aggregate+replace, preventing older captures finishing last.
    with named_lock("inventory:ebay-pivot") as acquired:
        if not acquired:
            raise ValueError("历史透视正在生成，请稍后重试")
        items, metadata, warnings = load_calculated_inventory()
        batch = metadata.get("inventory_batch_id")
        if not batch or not items:
            raise ValueError("没有可用的成功库存快照，不生成空白历史")
        if expected_inventory_batch and expected_inventory_batch != batch:
            raise ValueError("库存批次已变化，未将其他批次误记为本次任务历史")
        groups = aggregate_inventory(items)
        generated = datetime.now(CHINA)
        stat_date = generated.date()
        snapshot_id = repository.replace_day({
            "stat_date": stat_date, "stat_month": stat_date.strftime("%Y-%m"),
            "generated_at": generated.replace(tzinfo=None), "inventory_batch_id": batch,
            "inventory_snapshot_date": metadata.get("inventory_snapshot_date"),
            "inventory_pulled_at": metadata.get("inventory_pulled_at"),
            "trigger_type": str(trigger_type)[:32], "item_count": len(items),
            "metadata": {**metadata, "warnings": warnings, "amount_aggregation_policy": "sum_present_v1"},
        }, groups)
        return {"stat_date": stat_date.isoformat(), "snapshot_id": snapshot_id,
                "group_count": len(groups), "item_count": len(items), "inventory_batch_id": batch}


def _date_filter(value):
    if value is None or value == "":
        return None
    try:
        text = str(value)
        parsed = date.fromisoformat(text)
        if parsed.isoformat() != text:
            raise ValueError()
        return parsed
    except ValueError as exc:
        raise ValueError("统计日期必须为YYYY-MM-DD") from exc


def _insert_owner_totals(data):
    """Order complete owner/date groups and append one total, never sum a paged fragment."""
    totals = data.pop("owner_totals", None)
    if totals is None:
        return data  # Compatibility with callers supplying older already-flat results.
    groups = {}
    for row in data["items"]:
        key = (row["stat_date"], row["owner"])
        groups.setdefault(key, []).append({**row, "row_type": "DETAIL"})
    items, seen = [], set()
    for total in totals:
        key = (total["stat_date"], total["owner"])
        if key in seen or key not in groups:
            raise ValueError("负责人汇总与站点明细不一致，请刷新后重试")
        seen.add(key)
        details = sorted(groups[key], key=lambda row: row["site"])
        if total.get("site_count") is not None and int(total["site_count"]) != len(details):
            raise ValueError("负责人汇总的站点不完整，请刷新后重试")
        items.extend(details)
        items.append({**total, "site": "负责人汇总", "row_type": "OWNER_TOTAL"})
    if seen != set(groups):
        raise ValueError("部分站点明细缺少负责人汇总，请刷新后重试")
    data["items"] = items
    return data


def list_pivot(*, start_date=None, end_date=None, owner=None, site=None, page=1, page_size=50,
               sort_field=None, sort_order=None, paginate=True):
    start, end = _date_filter(start_date), _date_filter(end_date)
    if start and end and start > end:
        raise ValueError("开始日期不能晚于结束日期")
    data = repository.read_history(
        start_date=start, end_date=end, owner=str(owner).strip() if owner and str(owner).strip() else None,
        site=str(site).strip() if site and str(site).strip() else None,
        page=max(1, int(page)), page_size=max(1, min(200, int(page_size))),
        sort_field=sort_field or "stat_date", sort_order=str(sort_order or "desc").lower(),
        paginate=paginate,
    )
    data = _insert_owner_totals(data)
    # Decimal text avoids binary conversion; dates/timestamps remain explicit ISO values.
    data["items"] = [{key: format(value, "f") if isinstance(value, Decimal)
                      else value.isoformat() if isinstance(value, (date, datetime)) else value
                      for key, value in row.items()} for row in data["items"]]
    return data
