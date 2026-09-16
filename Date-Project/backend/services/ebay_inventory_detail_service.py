"""eBay库存明细：库存为主，页面与导出共享一次取数及Decimal计算。"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import PurePosixPath
from typing import Any

from backend.repositories import ebay_inventory_detail_repository as repository
from backend.repositories import inventory_report_etl_repository as owner_repository
from backend.services.ebay_inventory_grade_parser import normalize_site, parse_grades
from backend.services.inventory_report_etl_service import (
    _ebay_assignment, _ebay_product_sku_map, _ebay_rule_map,
)

ZERO = Decimal("0")
TOTAL_DURATION_MONTHS = Decimal("4.03")
CHINA = timezone(timedelta(hours=8))
PLACEHOLDER_FIELDS: tuple[str, ...] = ()
PRICE_FIELDS = ("unit_price_tax", "overseas_sellable_value", "overseas_total_value")
QUANTITY_FIELDS = (
    "overseas_in_transit_quantity", "overseas_sellable_quantity",
    "overseas_total_quantity", "chengdu_in_transit_quantity", "chengdu_sellable_quantity",
    "cycle_total_quantity", "sales_qty_30d", "pending_outbound_quantity", "procurement_plan_quantity",
)
SORT_FIELDS = set(PLACEHOLDER_FIELDS + QUANTITY_FIELDS + PRICE_FIELDS) | {
    "site", "sku", "brand", "product_name", "grade", "owner", "average_daily_sales_30d", "average_monthly_sales_3m",
    "in_stock_sales_ratio", "total_stock_sales_ratio", "total_stock_sales_ratio_months", "warehouse_rent_30d_cny",
    "overseas_max_age_days", "purchase_quantity", "total_duration_months", "last_sold_at",
}


def _text(value) -> str:
    return str(value or "").strip()


def _decimal(value) -> Decimal:
    if value is None or value == "":
        return ZERO
    try:
        result = value if isinstance(value, Decimal) else Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError("库存源数据含无效数值，请检查数据源") from exc
    if not result.is_finite():
        raise ValueError("库存源数据含非有限数值，请检查数据源")
    return result


def rent_sku_key(sku: str) -> str:
    """仅移除首段前缀；保留多件装或规格尾缀，禁止反复截断。"""
    value = _text(sku).upper()
    return value.split("-", 1)[1] if "-" in value else value


def _product_price(source, metadata) -> tuple[Decimal | None, str | None]:
    """cg_price为人民币原值；完整SKU、无站点维度，不换汇/加税/库存加权。"""
    if (metadata.get("price_batch_count") or 0) > 1:
        return None, "最新产品采购价月份含多个批次，单价与货值暂不计算"
    if (source.get("price_source_rows") or 0) > 1:
        return None, "最新产品档案存在重复完整SKU，单价与货值暂不计算"
    raw = source.get("cg_price")
    if raw is None or raw == "":
        return None, "最新产品档案未匹配到完整SKU或cg_price为空，不回退历史价"
    try:
        price = _decimal(raw)
    except ValueError:
        return None, "产品cg_price不是有效数值，单价与货值暂不计算"
    if price < ZERO:
        return None, "产品cg_price为负数，单价与货值暂不计算"
    # 0 is a real source value, not missing data. Round only after valuation.
    return price, None


def rent_site(warehouse: str) -> str | None:
    code = _text(warehouse).upper()
    if code in {"DE", "CZ", "IT"}:
        return "德国"
    if code == "UK":
        return "英国"
    if code == "FR":
        return "法国"
    if code.startswith("US"):
        return "美国"
    return None


def _inventory_age(source, metadata, aliases, collisions) -> tuple[Decimal | None, str | None]:
    """周更新的谷仓最新快照、同站点同尾码最大库龄；不读月报成本快照。"""
    if (metadata.get("age_batch_count") or 0) > 1:
        return None, "谷仓最新库龄表含多个批次，最高库龄暂不计算"
    if not source.get("age_source_rows"):
        if not metadata.get("age_snapshot_month"):
            return None, "没有谷仓最新库龄快照，请先执行谷仓库龄每周刷新任务"
        return None, "谷仓最新库龄快照未匹配到本站点的商品编码，不回退月度快照"
    key = (_text(source["site"]), rent_sku_key(source["sku"]))
    if key in collisions:
        return None, "同站点去前缀后匹配多个库存SKU：" + "、".join(sorted(aliases[key]))
    if (source.get("age_source_products") or 0) > 1:
        return None, "谷仓同站点同尾码存在多个完整商品编码，无法唯一匹配最高库龄"
    if source.get("age_invalid_rows"):
        return None, "谷仓部分批次缺少有效库龄，无法确定最大天数，未按0补齐"
    raw = source.get("age_days")
    if raw is None or raw == "":
        return None, "谷仓未返回有效库龄天数"
    try:
        days = _decimal(raw)
    except ValueError:
        return None, "谷仓库龄天数不是有效数值"
    if days < ZERO or days != days.to_integral_value():
        return None, "谷仓库龄天数必须是非负整数"
    # 0 is valid. This is the captured age, not captured age + elapsed days.
    return days, None


def _rent_totals(rent_rows, rates, rate_month):
    totals = defaultdict(lambda: ZERO)
    errors = {}
    unknown_warehouses = set()
    missing_currencies = set()
    for row in rent_rows:
        site = rent_site(row.get("warehouse_code"))
        if site is None:
            unknown_warehouses.add(_text(row.get("warehouse_code")) or "空仓库")
            continue
        suffix = rent_sku_key(row.get("product_sku"))
        if not suffix:
            continue
        key = (site, suffix)
        code = _text(row.get("bill_currency_code")).upper()
        raw_rate = rates.get(code)
        if raw_rate is None or _decimal(raw_rate) <= ZERO:
            errors[key] = f"缺少{rate_month or '拉取月份'}的{code or '计费币种'}汇率"
            missing_currencies.add(code or "空币种")
            continue
        if int(row.get("missing_amount_rows") or 0) > 0 or row.get("warehouse_rent_amount") is None:
            errors[key] = "部分谷仓明细缺少仓租金额，未按0补齐"
            continue
        # 先按仓库/原SKU/币种聚合，再按本批拉取月份my_rate折人民币。
        # 不把汇率先转float或强制两位，金额在最后输出时统一舍入。
        totals[key] += _decimal(row["warehouse_rent_amount"]) * _decimal(raw_rate)
    warnings = []
    if unknown_warehouses:
        warnings.append("仓租存在未映射站点的仓库：" + "、".join(sorted(unknown_warehouses)))
    if missing_currencies:
        warnings.append(f"{rate_month or '拉取月份'}缺少汇率：" + "、".join(sorted(missing_currencies)) + "，相关仓租显示--")
    return totals, errors, warnings


def _build_items(source_rows, rent_rows, rates, metadata, owner_rules, sku_map):
    """全部库存键参与碰撞检测；筛选不得掩盖另一个同尾码SKU。"""
    aliases = defaultdict(set)
    for row in source_rows:
        aliases[(_text(row["site"]), rent_sku_key(row["sku"]))].add(_text(row["sku"]).upper())
    collisions = {key for key, values in aliases.items() if len(values) > 1}
    rate_month = metadata.get("rent_pull_month")
    rents, rent_errors, warnings = _rent_totals(rent_rows, rates, rate_month)
    if collisions:
        warnings.append(f"发现{len(collisions)}组同站点同尾码的不同SKU，冲突行仓租显示--，避免重复计费")
    has_rent = bool(metadata.get("rent_row_count"))
    if not has_rent:
        warnings.append("当前没有谷仓仓租明细快照，仓租显示--；请先执行仓租同步任务")
    items = []
    for source in source_rows:
        site, sku = _text(source["site"]), _text(source["sku"])
        overseas_transit = _decimal(source.get("overseas_in_transit_quantity"))
        overseas_available = _decimal(source.get("overseas_sellable_quantity"))
        chengdu_transit = _decimal(source.get("chengdu_in_transit_quantity"))
        chengdu_available = _decimal(source.get("chengdu_sellable_quantity"))
        overseas_total = overseas_transit + overseas_available
        # Confirmed business mapping: product_total is the page's pending outbound
        # quantity; keep the upstream schema label unchanged.
        pending_outbound = _decimal(source.get("pending_outbound_quantity"))
        procurement_plan = ZERO  # Business default for every SKU; no source/config yet.
        cycle_total = overseas_total + chengdu_transit + chengdu_available + pending_outbound + procurement_plan
        sales = _decimal(source.get("sales_qty_30d"))
        three_month_sales = _decimal(source.get("sales_qty_3m"))
        # Business constant for this page only, not replenishment lead times.
        duration = TOTAL_DURATION_MONTHS
        # Algebraically monthly average * duration - cycle stock. Multiply before
        # dividing by 3; use the unrounded average, then HALF_UP once to an integer.
        # Keep negative results; do not clamp to zero or use ceiling rounding.
        purchase_quantity = (three_month_sales * duration / Decimal(3) - cycle_total).quantize(
            Decimal("1"), rounding=ROUND_HALF_UP
        )
        price, price_warning = _product_price(source, metadata)
        inventory_age, age_warning = _inventory_age(source, metadata, aliases, collisions)
        owner, owner_source = _ebay_assignment(sku, owner_rules, sku_map)
        match_key = (site, rent_sku_key(sku))
        rent_warning = None
        if match_key in collisions:
            rent_warning = "同站点去前缀后匹配多个SKU：" + "、".join(sorted(aliases[match_key]))
        elif match_key in rent_errors:
            rent_warning = rent_errors[match_key]
        elif not has_rent:
            rent_warning = "没有谷仓仓租明细快照"
        rent_amount = None if rent_warning else rents.get(match_key, ZERO)
        item = {
            "site": site, "sku": sku, "brand": sku.split("-", 1)[0].upper(),
            "product_name": _text(source.get("product_name")) or None,
            "grade": _text(source.get("grade")) or None,
            "overseas_in_transit_quantity": overseas_transit,
            "overseas_sellable_quantity": overseas_available,
            "overseas_total_quantity": overseas_total,
            "chengdu_in_transit_quantity": chengdu_transit,
            "chengdu_sellable_quantity": chengdu_available,
            "pending_outbound_quantity": pending_outbound,
            "procurement_plan_quantity": procurement_plan,
            "cycle_total_quantity": cycle_total,
            "overseas_max_age_days": inventory_age,
            "age_warning": age_warning,
            "sales_qty_30d": sales,
            "average_daily_sales_30d": sales / Decimal(30),
            "in_stock_sales_ratio": overseas_available / sales if sales else ZERO,
            "total_stock_sales_ratio": overseas_total / sales if sales else ZERO,
            "sales_qty_3m": three_month_sales,
            "average_monthly_sales_3m": three_month_sales / Decimal(3),
            # 等价于周期总库存/(三月总销量/3)，避免先舍入均销量。返回原比值，
            # 页面与Excel只设置百分比格式；缺销量/零分母沿用其他库销比返回0。
            "total_stock_sales_ratio_months": cycle_total * Decimal(3) / three_month_sales if three_month_sales else ZERO,
            "unit_price_tax": price,
            "overseas_sellable_value": price * overseas_available if price is not None else None,
            "overseas_total_value": price * overseas_total if price is not None else None,
            "price_warning": price_warning,
            "owner": owner, "owner_match_source": owner_source,
            "warehouse_rent_30d_cny": rent_amount,
            "rent_match_key": match_key[1], "rent_warning": rent_warning,
            "rent_rate_month": rate_month,
            **{field: None for field in PLACEHOLDER_FIELDS},
            "total_duration_months": duration,
            "purchase_quantity": purchase_quantity,
            "last_sold_at": _text(source.get("last_sold_at")) or None,
        }
        items.append(item)
    missing_prices = sum(item["price_warning"] is not None for item in items)
    if missing_prices:
        warnings.append(f"{missing_prices}条库存记录的产品采购价缺失或异常，单价及货值显示--；可悬浮查看原因")
    missing_ages = sum(item["age_warning"] is not None for item in items)
    if missing_ages:
        warnings.append(f"{missing_ages}条库存记录的库龄未匹配、冲突或异常，海外最高库龄显示--；可悬浮查看原因")
    return items, warnings


def _round_item(item: dict) -> dict:
    result = {}
    for key, value in item.items():
        if isinstance(value, Decimal):
            # Round displayed averages only at output; ratios and sorting use full precision.
            places = "0.01" if key.endswith("_cny") or key in PRICE_FIELDS or key in {"average_daily_sales_30d", "average_monthly_sales_3m"} else "0.000001"
            value = value.quantize(Decimal(places), rounding=ROUND_HALF_UP)
            # 数量保持精确数值文本，避免返回过长尾数或把0变空。
            value = format(value, "f").rstrip("0").rstrip(".") if "." in format(value, "f") else str(value)
            result[key] = "0" if value in {"-0", ""} else value
        else:
            result[key] = value
    return result


def load_calculated_inventory():
    """Unfiltered, unrounded Decimal rows shared by the live view and daily history."""
    source_rows, metadata, rent_rows, rates = repository.read_snapshot()
    owner_month = datetime.now(CHINA).strftime("%Y-%m")
    raw_rules = owner_repository.owner_rules(owner_month, "ebay") if source_rows else []
    rules = _ebay_rule_map(raw_rules)
    sku_map = _ebay_product_sku_map(owner_month, include_next=False) if source_rows else {}
    items, warnings = _build_items(source_rows, rent_rows, rates, metadata, rules, sku_map)
    if "inventory_batch_id" in metadata and not metadata["inventory_batch_id"]:
        warnings.append("没有可用的成功周报库存快照，请先执行仓位库存明细周报任务；不回退旧库存表")
    if source_rows and not raw_rules:
        warnings.append(f"{owner_month}没有eBay负责人规则，未匹配行显示未分配，不回退到其他月份")
    metadata = {**metadata, "owner_rule_month": owner_month}
    return items, metadata, warnings


def list_inventory(*, site=None, sku=None, brand=None, grade=None, page=1, page_size=50,
                   sort_field=None, sort_order=None, paginate=True, selected_keys=None):
    items, metadata, warnings = load_calculated_inventory()
    sites = sorted({_text(row["site"]) for row in items})
    brands = sorted({row["brand"] for row in items})
    grades = sorted({row["grade"] for row in items if row.get("grade")})
    site_filter = normalize_site(site) if site else ""
    sku_filter, brand_filter, grade_filter = _text(sku).upper(), _text(brand).upper(), _text(grade)
    items = [row for row in items
             if (not site_filter or row["site"] == site_filter)
             and (not sku_filter or sku_filter in row["sku"].upper())
             and (not brand_filter or row["brand"] == brand_filter)
             and (not grade_filter or row["grade"] == grade_filter)]
    if selected_keys:
        requested = {(normalize_site(key["site"]), _text(key["sku"]).upper()) for key in selected_keys}
        actual = {(row["site"], row["sku"].upper()) for row in items}
        if not requested.issubset(actual):
            raise ValueError("部分已选数据已变化或不在当前筛选结果中，请刷新后重新选择导出")
        items = [row for row in items if (row["site"], row["sku"].upper()) in requested]
    field = sort_field or "sales_qty_30d"
    if field not in SORT_FIELDS:
        raise ValueError("不支持该排序字段")
    descending = _text(sort_order).lower() not in {"asc", "ascending"}
    # 二级键保证同值分页稳定，空值在两种方向都置底。
    items.sort(key=lambda row: (row["site"], row["sku"]))
    populated = [row for row in items if row.get(field) is not None]
    missing = [row for row in items if row.get(field) is None]
    populated.sort(key=lambda row: row[field], reverse=descending)
    items = populated + missing
    count = len(items)
    summary = {field: sum((row[field] for row in items), ZERO) for field in (
        "overseas_total_quantity", "cycle_total_quantity", "sales_qty_30d")}
    summary["warehouse_rent_30d_cny"] = (
        sum((row["warehouse_rent_30d_cny"] for row in items), ZERO)
        if all(row["warehouse_rent_30d_cny"] is not None for row in items) else None)
    page = max(1, int(page))
    page_size = min(200, max(1, int(page_size)))
    page_items = items[(page - 1) * page_size:page * page_size] if paginate else items
    return {"items": [_round_item(row) for row in page_items],
            "pagination": {"page": page, "page_size": page_size, "total": count},
            "sites": sites, "brands": brands, "grades": grades,
            "metadata": {**metadata,
                         "rent_rate_month": metadata.get("rent_pull_month"), "warnings": warnings,
                         "row_scope": "最新成功周报批次中七个eBay仓库的站点+完整SKU库存记录"},
            "summary": _round_item(summary)}


def import_grades(content: bytes, filename: str, operator: str | None = None):
    result = parse_grades(content, filename)
    filename = PurePosixPath(filename.replace("\\", "/")).name[:255]
    rows = result.pop("rows")
    imported = repository.upsert_grades(rows, _text(operator)[:64] or "SYSTEM", filename)
    return {"imported_rows": imported, **result,
            "message": "按站点+完整SKU更新有效等级；错误行和文件未包含的SKU保留原等级"}
