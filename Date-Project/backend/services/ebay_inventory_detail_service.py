"""eBay库存明细：库存为主，页面与导出共享一次取数及Decimal计算。"""
from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import PurePosixPath
from typing import Any

from backend.repositories import ebay_inventory_detail_repository as repository
from backend.repositories import ebay_inventory_price_repository as price_repository
from backend.repositories import ebay_inventory_pivot_repository as history_repository
from backend.repositories import inventory_report_etl_repository as owner_repository
from backend.services.ebay_inventory_grade_rule import calculate_grade
from backend.services.ebay_inventory_workbook import normalize_site
from backend.services.ebay_inventory_price_parser import parse_prices
from backend.services.inventory_report_etl_service import (
    _ebay_assignment, _ebay_product_sku_map, _ebay_rule_map,
)

ZERO = Decimal("0")
TOTAL_DURATION_MONTHS = Decimal("4.03")
MIDDLE_SITE_SUFFIXES = {"德国": "DE", "美国": "US", "英国": "UK"}
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
    "profit_rate", "max_monthly_sales",
}


def _text(value) -> str:
    return str(value or "").strip()


def sku_middle_code(sku: str) -> str | None:
    """取连字符分隔后的第二段数字，作为文本保留前导零。"""
    parts = _text(sku).split("-")
    code = parts[1].strip() if len(parts) > 1 else ""
    return code if code and all("0" <= char <= "9" for char in code) else None


def sku_middle_site_code(site: str, middle_code: str | None) -> str | None:
    """仅供展示的中间码+站点标识，不替代现有分组或价格匹配键。"""
    middle = "" if middle_code is None else str(middle_code).strip()
    suffix = MIDDLE_SITE_SUFFIXES.get(_text(site))
    if not suffix or not middle or not all("0" <= char <= "9" for char in middle):
        return None
    return middle + suffix


def _product_key(site, sku):
    """Invalid middle codes stay separate; never merge all missing codes together."""
    middle = sku_middle_code(sku)
    return (_text(site), "MIDDLE", middle) if middle is not None else (_text(site), "SKU", _text(sku).upper())


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
    """上传价按文本中间码取MIN，跨站点共用人民币，不回退产品档案。"""
    raw = source.get("imported_unit_price")
    if raw is None or raw == "":
        return None, "上传单价未匹配到有效中间码，请导入产品单价后刷新；不回退产品管理价格"
    try:
        price = _decimal(raw)
    except ValueError:
        return None, "上传单价不是有效数值，单价与货值暂不计算"
    if price < ZERO:
        return None, "上传单价为负数，单价与货值暂不计算"
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
    if (source.get("age_source_products") or 0) > 1 and sku_middle_code(source["sku"]) is None:
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


def max_monthly_sales_candidates(items, window_end) -> list[dict[str, Any]]:
    """把本次观测到的30天滚动销量整理成高水位候选，低于已存值的由SQL丢弃。

    观测窗口就是页面「近30天销量」用的那个：[统计日-30, 统计日)，不含当天。
    每次重新计算只看当前这一个窗口；统计日之前错过的窗口由回填SQL补齐
    （deploy/ebay-inventory-detail/04_回填历史最大月销.sql）。
    """
    candidates = []
    for item in items:
        observed = _decimal(item.get("sales_qty_30d"))
        if observed <= ZERO:
            continue
        site, key_type, key = _product_key(item["site"], item["sku"])
        candidates.append({
            "site": site, "product_key_type": key_type, "product_key": key,
            "max_monthly_sales": observed, "peak_window_end": window_end,
        })
    return candidates


def _max_sales_floor_map(floor_rows) -> dict[tuple, Decimal]:
    """高水位按站点+合并键归集，键与 _product_key 同构。"""
    result: dict[tuple, Decimal] = {}
    for row in floor_rows or []:
        key = (_text(row.get("site")), _text(row.get("product_key_type")).upper(),
               _text(row.get("product_key")))
        if not key[0] or key[1] not in {"MIDDLE", "SKU"} or not key[2]:
            continue
        value = _decimal(row.get("max_monthly_sales"))
        if key not in result or value > result[key]:
            result[key] = value
    return result


def _profit_rate(profit: Decimal, paid_amount: Decimal) -> Decimal | None:
    """销售额为0时除不出比率，返回None；页面显示--，等级也不给评级。"""
    return None if paid_amount == ZERO else profit / paid_amount


def _build_items(source_rows, rent_rows, rates, metadata, owner_rules, sku_map,
                 max_floor_rows=None):
    """先按原SKU计算，再按站点+中间码汇总；筛选和分页必须在汇总之后。"""
    sales_floor = _max_sales_floor_map(max_floor_rows)
    aliases = defaultdict(set)
    for row in source_rows:
        aliases[(_text(row["site"]), rent_sku_key(row["sku"]))].add(_text(row["sku"]).upper())
    # Alias SKUs belonging to ONE merged product can share an age/rent key.
    # Rent is counted once per source match key by _merge_product_items below.
    collisions = {key for key, values in aliases.items()
                  if len({_product_key(key[0], sku) for sku in values}) > 1}
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
        three_month_profit = _decimal(source.get("three_month_profit_cny"))
        three_month_paid = _decimal(source.get("three_month_paid_amount_cny"))
        profit_rate = _profit_rate(three_month_profit, three_month_paid)
        item = {
            "site": site, "sku": sku, "brand": sku.split("-", 1)[0].upper(),
            "sku_middle_code": sku_middle_code(sku),
            "product_name": _text(source.get("product_name")) or None,
            "three_month_profit_cny": three_month_profit,
            "three_month_paid_amount_cny": three_month_paid,
            "profit_rate": profit_rate,
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
    items = _merge_product_items(items)
    for item in items:
        # 历史最大月销 = MAX(本次观测, 高水位)，只升不降。
        # 本次观测就是「近30天销量」那个滚动窗口 [统计日-30, 统计日)，不按自然月
        # 切分；更早的窗口不在本次取数范围内，只存在于高水位表里，两者取大。
        # 等级必须在取完下限之后再算，否则会按偏低的销量评级。
        observed = _decimal(item.get("sales_qty_30d"))
        floor = sales_floor.get(_product_key(item["site"], item["sku"]))
        if floor is not None and floor > observed:
            item["max_monthly_sales"] = floor
            item["max_monthly_sales_source"] = "HISTORY_HIGH_WATER"
        else:
            item["max_monthly_sales"] = observed
            item["max_monthly_sales_source"] = "ORDERS"
        item["grade"] = calculate_grade(item["max_monthly_sales"], item["profit_rate"])
    missing_prices = sum(item["price_warning"] is not None for item in items)
    if missing_prices:
        warnings.append(f"{missing_prices}条库存记录未匹配有效上传单价；缺失货值不计入汇总，可悬浮查看原因")
    missing_ages = sum(item["age_warning"] is not None for item in items)
    if missing_ages:
        warnings.append(f"{missing_ages}条库存记录的部分或全部库龄未匹配、冲突或异常；已匹配部分取最大值，可悬浮查看原因")
    return items, warnings


def _merge_product_items(items):
    """Aggregate unrounded full-SKU values, never sum ratios, prices or rounded purchases."""
    groups = defaultdict(list)
    seen = set()
    for item in items:
        key = (_text(item["site"]), _text(item["sku"]).upper())
        if key in seen:
            raise ValueError("库存源数据存在重复站点+完整SKU，未合并或保存")
        seen.add(key)
        groups[_product_key(*key)].append(item)
    result = []
    for _, members in sorted(groups.items()):
        # Stable representative: prefer the shorter original SKU over suffix aliases.
        members = sorted(members, key=lambda item: (len(item["sku"]), item["sku"].upper(), item["sku"]))
        row = dict(members[0])
        row["sku_aliases"] = [item["sku"] for item in members]
        row["merged_sku_count"] = len(members)
        row["missing_price_sku_count"] = sum(item["unit_price_tax"] is None for item in members)
        row["missing_rent_key_count"] = len({item["rent_match_key"] for item in members
                                             if item["warehouse_rent_30d_cny"] is None})
        row["brand_aliases"] = sorted({item["brand"] for item in members if item.get("brand")})
        row["merge_warning"] = None
        if len(members) == 1:
            result.append(row)
            continue

        notes = []
        for field in QUANTITY_FIELDS + ("sales_qty_3m", "three_month_profit_cny",
                                        "three_month_paid_amount_cny"):
            row[field] = sum((item[field] for item in members), ZERO)
        # 利润率按合并后的总利润/总销售额重算，不能对各SKU的比率取平均。
        row["profit_rate"] = _profit_rate(row["three_month_profit_cny"],
                                          row["three_month_paid_amount_cny"])
        sales, sales_3m = row["sales_qty_30d"], row["sales_qty_3m"]
        row["average_daily_sales_30d"] = sales / Decimal(30)
        row["average_monthly_sales_3m"] = sales_3m / Decimal(3)
        row["in_stock_sales_ratio"] = row["overseas_sellable_quantity"] / sales if sales else ZERO
        row["total_stock_sales_ratio"] = row["overseas_total_quantity"] / sales if sales else ZERO
        row["total_stock_sales_ratio_months"] = row["cycle_total_quantity"] * Decimal(3) / sales_3m if sales_3m else ZERO
        row["total_duration_months"] = TOTAL_DURATION_MONTHS
        row["purchase_quantity"] = (sales_3m * TOTAL_DURATION_MONTHS / Decimal(3) - row["cycle_total_quantity"]).quantize(
            Decimal("1"), rounding=ROUND_HALF_UP)
        for field in ("overseas_max_age_days", "last_sold_at"):
            values = [item[field] for item in members if item.get(field) is not None]
            row[field] = max(values) if values else None
        row["product_name"] = next((item["product_name"] for item in members if item.get("product_name")), None)
        owners = {_text(item.get("owner")) or "未分配" for item in members}
        if len(owners) > 1:
            row["owner"], row["owner_match_source"] = "未分配", "MERGED_CONFLICT"
            notes.append("合并SKU的负责人不同：" + "、".join(sorted(owners)) + "，归入未分配以免任意转移货值")

        # All members share the same middle code and uploaded minimum price.
        # Do not retain the old catalogue/inventory-weighted pricing policy.
        prices = [item["unit_price_tax"] for item in members if item["unit_price_tax"] is not None]
        row["unit_price_tax"] = min(prices) if prices else None
        row["missing_price_sku_count"] = 0 if prices else len(members)
        row["overseas_sellable_value"] = row["unit_price_tax"] * row["overseas_sellable_quantity"] if prices else None
        row["overseas_total_value"] = row["unit_price_tax"] * row["overseas_total_quantity"] if prices else None
        row["price_warning"] = None if prices else members[0].get("price_warning")
        age_notes = sorted({item["age_warning"] for item in members if item.get("age_warning")})
        age_prefix = "合并库龄取已匹配SKU的最大值；" if row["overseas_max_age_days"] is not None and age_notes else ""
        row["age_warning"] = age_prefix + "；".join(age_notes) or None

        rent_by_key = {}
        for item in members:
            rent_by_key.setdefault(item["rent_match_key"], item["warehouse_rent_30d_cny"])
        row["rent_match_keys"] = sorted(rent_by_key)
        rent_values = [value for value in rent_by_key.values() if value is not None]
        row["warehouse_rent_30d_cny"] = sum(rent_values, ZERO) if rent_values else None
        rent_notes = sorted({item["rent_warning"] for item in members if item.get("rent_warning")})
        if row["missing_rent_key_count"] and rent_values:
            rent_notes.append("合并仓租仅汇总可计算的不同匹配键，缺失金额未计入")
        row["rent_warning"] = "；".join(rent_notes) or None
        row["merge_warning"] = "；".join(notes) or None
        result.append(row)
    return result


def _round_item(item: dict) -> dict:
    result = {}
    for key, value in item.items():
        if isinstance(value, Decimal):
            # Round displayed averages only at output; ratios and sorting use full precision.
            places = "0.01" if key.endswith("_cny") or key in PRICE_FIELDS or key in {"average_daily_sales_30d", "average_monthly_sales_3m"} else "0.000001"
            if item.get("history_origin") != "EXCEL_IMPORT":
                value = value.quantize(Decimal(places), rounding=ROUND_HALF_UP)
            # 数量保持精确数值文本，避免返回过长尾数或把0变空。
            value = format(value, "f").rstrip("0").rstrip(".") if "." in format(value, "f") else str(value)
            result[key] = "0" if value in {"-0", ""} else value
        else:
            result[key] = value
    if "sku" in item and item.get("history_origin") != "EXCEL_IMPORT":
        # Display-only enrichment also supports old frozen rows. Derive solely
        # from that row, never query current sources or write the historical JSON.
        middle = item.get("sku_middle_code") if "sku_middle_code" in item else sku_middle_code(item.get("sku"))
        result.setdefault("sku_middle_code", middle)
        result["sku_middle_site_code"] = sku_middle_site_code(item.get("site"), middle)
    return result


def load_calculated_inventory():
    """Unfiltered, unrounded Decimal rows shared by the live view and daily history."""
    source_rows, metadata, rent_rows, rates, max_floor_rows = repository.read_snapshot()
    owner_month = datetime.now(CHINA).strftime("%Y-%m")
    raw_rules = owner_repository.owner_rules(owner_month, "ebay") if source_rows else []
    rules = _ebay_rule_map(raw_rules)
    sku_map = _ebay_product_sku_map(owner_month, include_next=False) if source_rows else {}
    items, warnings = _build_items(source_rows, rent_rows, rates, metadata, rules, sku_map,
                                   max_floor_rows)
    # 观测窗口右端即取数用的统计日；候选写库时要记下它是哪一天的窗口。
    sales_candidates = max_monthly_sales_candidates(
        items, metadata.get("sales_date_to_exclusive"))
    if "inventory_batch_id" in metadata and not metadata["inventory_batch_id"]:
        warnings.append("没有可用的成功周报库存快照，请先执行仓位库存明细周报任务；不回退旧库存表")
    if source_rows and not raw_rules:
        warnings.append(f"{owner_month}没有eBay负责人规则，未匹配行显示未分配，不回退到其他月份")
    metadata = {**metadata, "owner_rule_month": owner_month,
                "grouping_policy": "site_middle_code_v1", "source_sku_count": len(source_rows),
                "product_group_count": len(items)}
    return items, metadata, warnings, sales_candidates


def _filter_values(value, label, *, uppercase=False, numeric=False):
    """CSV filters: OR within a field, AND across fields; retain leading zeroes."""
    text = _text(value)
    if len(text) > 2048:
        raise ValueError(f"{label}筛选不能超过2048个字符")
    values = {part.strip() for part in text.split(",") if part.strip()}
    if len(values) > 100:
        raise ValueError(f"{label}最多选择100项")
    if numeric and any(not all("0" <= char <= "9" for char in part) for part in values):
        raise ValueError("SKU筛选请输入数字中间码，多个中间码使用英文逗号分隔，例如10053,20017")
    return {part.upper() for part in values} if uppercase else values


def _row_middle_codes(row):
    # Old/imported snapshots may lack the display field. Extract for matching only;
    # do not recalculate, regroup or mutate frozen history rows.
    code = _text(row.get("sku_middle_code"))
    if code and all("0" <= char <= "9" for char in code):
        return {code}
    return {code for value in (row.get("sku_aliases") or [row.get("sku")])
            if (code := sku_middle_code(value)) is not None}


def list_inventory(*, site=None, sku=None, brand=None, grade=None, page=1, page_size=50,
                   sort_field=None, sort_order=None, paginate=True, selected_keys=None, stat_date=None):
    sku_filter = _filter_values(sku, "中间码", numeric=True)
    brand_filter = _filter_values(brand, "品牌", uppercase=True)
    grade_filter = _filter_values(grade, "等级")
    if stat_date:
        if stat_date != "latest":
            try:
                if date.fromisoformat(stat_date).isoformat() != stat_date:
                    raise ValueError()
            except (ValueError, TypeError) as exc:
                raise ValueError("统计日期必须为YYYY-MM-DD") from exc
        items, metadata, warnings = history_repository.read_inventory_day(stat_date)
    else:
        # Retain the internal live calculation path; the page explicitly requests history.
        items, metadata, warnings, _ = load_calculated_inventory()
    sites = sorted({_text(row["site"]) for row in items})
    brands = sorted({value for row in items for value in row.get("brand_aliases", [row["brand"]]) if value})
    grades = sorted({_text(row.get("grade")) for row in items if row.get("grade")})
    site_filter = normalize_site(site) if site else ""
    items = [row for row in items
             if (not site_filter or row["site"] == site_filter)
             and (not sku_filter or sku_filter.intersection(_row_middle_codes(row)))
             and (not brand_filter or brand_filter.intersection(
                 _text(value).upper() for value in (row.get("brand_aliases") or [row.get("brand")])))
             and (not grade_filter or _text(row.get("grade")) in grade_filter)]
    if selected_keys:
        def selection_key(row):
            return (normalize_site(row["site"]), _text(row.get("sku")).upper(), _text(row.get("record_key")))
        requested = {selection_key(key) for key in selected_keys}
        actual = {selection_key(row) for row in items}
        if not requested.issubset(actual):
            raise ValueError("部分已选数据已变化或不在当前筛选结果中，请刷新后重新选择导出")
        items = [row for row in items if selection_key(row) in requested]
    field = sort_field or "sales_qty_30d"
    if field not in SORT_FIELDS:
        raise ValueError("不支持该排序字段")
    descending = _text(sort_order).lower() not in {"asc", "ascending"}
    # 二级键保证同值分页稳定，空值在两种方向都置底。
    items.sort(key=lambda row: (row["site"], _text(row["sku"]), _text(row.get("record_key"))))
    populated = [row for row in items if row.get(field) is not None]
    missing = [row for row in items if row.get(field) is None]
    populated.sort(key=lambda row: row[field], reverse=descending)
    items = populated + missing
    count = len(items)
    summary = {field: sum((row[field] for row in items if row.get(field) is not None), ZERO) for field in (
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
                         "row_scope": "指定统计日期冻结明细" if stat_date else "最新成功周报批次中七个eBay仓库的站点+中间码汇总；无有效中间码保留完整SKU"},
            "summary": _round_item(summary)}


def import_prices(content: bytes, filename: str, operator: str | None = None):
    result = parse_prices(content, filename)
    filename = PurePosixPath(filename.replace("\\", "/")).name[:255]
    rows = result.pop("rows")
    imported = price_repository.replace_prices(rows, _text(operator)[:64] or "SYSTEM", filename)
    return {"imported_rows": imported, **result,
            "message": "按SKU+价格去重，替换本次涉及SKU的价格集合，其他SKU保留；同中间码取最低人民币价。请点击刷新重新计算今日快照。"}
