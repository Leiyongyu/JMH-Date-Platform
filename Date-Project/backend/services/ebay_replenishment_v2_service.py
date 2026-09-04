from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any

from backend.database import db_connection
from backend.repositories import ebay_replenishment_v2_repository as repository
from backend.services import ebay_sku_analysis_service as sku_analysis_service


_SORT_COLUMNS = {
    "site": "site",
    "sku": "sku",
    "product_name": "product_name",
    "productName": "product_name",
    "sales_qty": "sales_qty_m1",
    "salesQty": "sales_qty_m1",
    "sales_qty_7d": "sales_qty_7d",
    "salesQty7d": "sales_qty_7d",
    "sales_qty_15d": "sales_qty_15d",
    "salesQty15d": "sales_qty_15d",
    "sales_qty_30d": "sales_qty_30d",
    "salesQty30d": "sales_qty_30d",
    "gross_profit_amount": "gross_profit_amount_m1",
    "grossProfitAmount": "gross_profit_amount_m1",
    "profit_rate": (
        "(gross_profit_amount_m1+gross_profit_amount_m2+gross_profit_amount_m3)/"
        "NULLIF((paid_amount_m1+paid_amount_m2+paid_amount_m3),0)"
    ),
    "profitRate": (
        "(gross_profit_amount_m1+gross_profit_amount_m2+gross_profit_amount_m3)/"
        "NULLIF((paid_amount_m1+paid_amount_m2+paid_amount_m3),0)"
    ),
    "return_qty": "return_qty_m1",
    "returnQty": "return_qty_m1",
    "return_rate": (
        "(return_qty_m1+return_qty_m2+return_qty_m3)/"
        "NULLIF((sales_qty_m1+sales_qty_m2+sales_qty_m3),0)"
    ),
    "returnRate": (
        "(return_qty_m1+return_qty_m2+return_qty_m3)/"
        "NULLIF((sales_qty_m1+sales_qty_m2+sales_qty_m3),0)"
    ),
    "return_amount": "return_amount_m1",
    "returnAmount": "return_amount_m1",
}


# 与原 eBay 补货计算链路 application.yml 中 lingxing.inventory-wids 保持一致。
# 匹配库存时仅对站点标签和完整 SKU 做等值匹配，不再截取 SKU 后缀。
_INVENTORY_SITE_BY_WID = {
    18674: "德国",  # 成都 eBay-DE 中转仓
    18675: "英国",  # 成都 eBay-UK 中转仓
    18676: "美国",  # 成都 eBay-US 中转仓
    18699: "德国",  # 谷仓德国仓
    18700: "美国",  # 谷仓美国新泽西仓
    18701: "美国",  # 谷仓美国加州仓
    18702: "英国",  # 谷仓英国仓
}
_CHENGDU_WIDS = (18674, 18675, 18676)
_OVERSEAS_WIDS = (18699, 18700, 18701, 18702)
_INVENTORY_WIDS_SQL = ",".join(str(wid) for wid in _INVENTORY_SITE_BY_WID)
_CHENGDU_WIDS_SQL = ",".join(str(wid) for wid in _CHENGDU_WIDS)
_OVERSEAS_WIDS_SQL = ",".join(str(wid) for wid in _OVERSEAS_WIDS)
_INVENTORY_SITE_CASE_SQL = " ".join(
    f"WHEN {wid} THEN '{site}'" for wid, site in _INVENTORY_SITE_BY_WID.items()
)


def list_replenishment(
    site: str | None = None,
    sku: str | None = None,
    product_name: str | None = None,
    product_level: str | None = None,
    product_nature: str | None = None,
    page: int = 1,
    page_size: int = 50,
    sort_field: str | None = None,
    sort_order: str | None = None,
) -> dict[str, Any]:
    """Return the latest three complete natural months by site and SKU.

    All measures deliberately keep the existing SKU-analysis payment-month
    definitions.  The latest complete month is also exposed as each row's
    primary value; the complete three-month series is returned in
    ``monthly_metrics`` for the UI hover card.
    """

    sku_analysis_service._ensure_tables()
    months = _complete_months()
    page = max(_positive_int(page, 1), 1)
    page_size = min(max(_positive_int(page_size, 50), 1), 200)
    forecast_sort_requested = (sort_field or "") in {
        "forecast_sales_quantity_2",
        "forecastSalesQuantity2",
    }
    sort_column = _SORT_COLUMNS.get(
        sort_field or "sales_qty_30d", "sales_qty_30d"
    )
    sort_direction = (
        "ASC"
        if str(sort_order or "desc").lower() in {"asc", "ascending"}
        else "DESC"
    )
    # 产品等级和产品性质均在组装阶段算出，SQL 里不存在这两列，
    # 因此带任一派生筛选时不能用 SQL 分页：先取全量、算完再筛选并分页，
    # 否则每页会少于 page_size、总数也会是筛选前的值。
    level_filter = (product_level or "").strip().upper() or None
    nature_filter = (product_nature or "").strip() or None
    paginate_in_sql = (
        level_filter is None
        and nature_filter is None
        and not forecast_sort_requested
    )

    range_start = months[-1]["start_date"]
    range_end = months[0]["end_date"]
    where_sql, filter_params = _filters(site, sku, product_name)
    limit_sql = "LIMIT %s OFFSET %s" if paginate_in_sql else ""
    month_params = [month["month"] for month in months for _ in range(5)]
    query = f"""
        WITH period_rows AS (
            SELECT id,site_name,inventory_sku,payment_time,purchase_quantity,
                   paid_amount_cny,order_profit_cny,refund_quantity,refund_amount_cny,
                   shipping_status
            FROM dwd_ebay_sku_analysis_order
            WHERE payment_time >= %s AND payment_time < %s
        ),
        anchor AS (
            SELECT COALESCE(DATE(MAX(payment_time)),CURDATE()) anchor_date
            FROM dwd_ebay_sku_analysis_order
        ),
        recent_windows AS (
            SELECT recent.site_name,recent.inventory_sku,
                   SUM(CASE WHEN recent.payment_time
                            >= DATE_SUB(anchor.anchor_date,INTERVAL 6 DAY)
                            THEN recent.purchase_quantity ELSE 0 END) sales_qty_7d,
                   SUM(CASE WHEN recent.payment_time
                            >= DATE_SUB(anchor.anchor_date,INTERVAL 14 DAY)
                            THEN recent.purchase_quantity ELSE 0 END) sales_qty_15d,
                   SUM(recent.purchase_quantity) sales_qty_30d
            FROM dwd_ebay_sku_analysis_order recent
            CROSS JOIN anchor
            WHERE recent.payment_time
                  >= DATE_SUB(anchor.anchor_date,INTERVAL 29 DAY)
              AND recent.payment_time
                  < DATE_ADD(anchor.anchor_date,INTERVAL 1 DAY)
            GROUP BY recent.site_name,recent.inventory_sku
        ),
        period_keys AS (
            SELECT DISTINCT site_name,inventory_sku FROM period_rows
        ),
        latest_source AS (
            SELECT site_name,inventory_sku,product_name_cn
            FROM (
                SELECT source.site_name,source.inventory_sku,source.product_name_cn,
                       ROW_NUMBER() OVER (
                           PARTITION BY source.site_name,source.inventory_sku
                           ORDER BY source.payment_time DESC,source.id DESC
                       ) latest_rank
                FROM dwd_ebay_sku_analysis_order source
                INNER JOIN period_keys period_key
                    ON period_key.site_name=source.site_name
                   AND period_key.inventory_sku=source.inventory_sku
            ) ranked_source
            WHERE latest_rank=1
        ),
        monthly AS (
            SELECT site_name,inventory_sku,
                   DATE_FORMAT(payment_time,'%%Y-%%m') stat_month,
                   SUM(purchase_quantity) sales_qty,
                   SUM(order_profit_cny) gross_profit_amount,
                   SUM(paid_amount_cny)
                     -SUM(CASE WHEN shipping_status LIKE '%%已退款%%'
                               THEN refund_amount_cny ELSE 0 END) paid_amount,
                   SUM(refund_quantity) return_qty,
                   SUM(CASE WHEN shipping_status LIKE '%%已退款%%'
                            THEN refund_amount_cny ELSE 0 END) return_amount
            FROM period_rows
            GROUP BY site_name,inventory_sku,DATE_FORMAT(payment_time,'%%Y-%%m')
        ),
        base AS (
            SELECT monthly.site_name site,
                   monthly.inventory_sku sku,
                   latest_source.product_name_cn product_name,
                   COALESCE(SUM(CASE WHEN monthly.stat_month=%s THEN monthly.sales_qty ELSE 0 END),0) sales_qty_m1,
                   COALESCE(SUM(CASE WHEN monthly.stat_month=%s THEN monthly.gross_profit_amount ELSE 0 END),0) gross_profit_amount_m1,
                   COALESCE(SUM(CASE WHEN monthly.stat_month=%s THEN monthly.paid_amount ELSE 0 END),0) paid_amount_m1,
                   COALESCE(SUM(CASE WHEN monthly.stat_month=%s THEN monthly.return_qty ELSE 0 END),0) return_qty_m1,
                   COALESCE(SUM(CASE WHEN monthly.stat_month=%s THEN monthly.return_amount ELSE 0 END),0) return_amount_m1,
                   COALESCE(SUM(CASE WHEN monthly.stat_month=%s THEN monthly.sales_qty ELSE 0 END),0) sales_qty_m2,
                   COALESCE(SUM(CASE WHEN monthly.stat_month=%s THEN monthly.gross_profit_amount ELSE 0 END),0) gross_profit_amount_m2,
                   COALESCE(SUM(CASE WHEN monthly.stat_month=%s THEN monthly.paid_amount ELSE 0 END),0) paid_amount_m2,
                   COALESCE(SUM(CASE WHEN monthly.stat_month=%s THEN monthly.return_qty ELSE 0 END),0) return_qty_m2,
                   COALESCE(SUM(CASE WHEN monthly.stat_month=%s THEN monthly.return_amount ELSE 0 END),0) return_amount_m2,
                   COALESCE(SUM(CASE WHEN monthly.stat_month=%s THEN monthly.sales_qty ELSE 0 END),0) sales_qty_m3,
                   COALESCE(SUM(CASE WHEN monthly.stat_month=%s THEN monthly.gross_profit_amount ELSE 0 END),0) gross_profit_amount_m3,
                   COALESCE(SUM(CASE WHEN monthly.stat_month=%s THEN monthly.paid_amount ELSE 0 END),0) paid_amount_m3,
                   COALESCE(SUM(CASE WHEN monthly.stat_month=%s THEN monthly.return_qty ELSE 0 END),0) return_qty_m3,
                   COALESCE(SUM(CASE WHEN monthly.stat_month=%s THEN monthly.return_amount ELSE 0 END),0) return_amount_m3
            FROM monthly
            LEFT JOIN latest_source
              ON latest_source.site_name=monthly.site_name
             AND latest_source.inventory_sku=monthly.inventory_sku
            GROUP BY monthly.site_name,monthly.inventory_sku,
                     latest_source.product_name_cn
        ),
        inventory_source AS (
            SELECT CASE source.wid {_INVENTORY_SITE_CASE_SQL} END site,
                   TRIM(source.sku) sku,
                   CASE WHEN source.wid IN ({_CHENGDU_WIDS_SQL})
                        THEN COALESCE(source.quantity_receive,0) ELSE 0 END
                       chengdu_in_transit_quantity,
                   CASE WHEN source.wid IN ({_CHENGDU_WIDS_SQL})
                        THEN COALESCE(source.product_valid_num,0) ELSE 0 END
                       chengdu_sellable_quantity,
                   CASE WHEN source.wid IN ({_OVERSEAS_WIDS_SQL})
                        THEN COALESCE(source.product_onway,0) ELSE 0 END
                       overseas_in_transit_quantity,
                   CASE WHEN source.wid IN ({_OVERSEAS_WIDS_SQL})
                        THEN COALESCE(source.product_valid_num,0) ELSE 0 END
                       overseas_sellable_quantity
            FROM jmh_data_platform.warehouse_inventory_detail source
            WHERE source.wid IN ({_INVENTORY_WIDS_SQL})
              AND source.sku IS NOT NULL AND TRIM(source.sku)<>''
        ),
        inventory_summary AS (
            SELECT site,sku,
                   SUM(chengdu_in_transit_quantity) chengdu_in_transit_quantity,
                   SUM(chengdu_sellable_quantity) chengdu_sellable_quantity,
                   SUM(overseas_in_transit_quantity) overseas_in_transit_quantity,
                   SUM(overseas_sellable_quantity) overseas_sellable_quantity
            FROM inventory_source
            GROUP BY site,sku
        )
        SELECT base.*,
               COALESCE(inventory_summary.chengdu_in_transit_quantity,0)
                   chengdu_in_transit_quantity,
               COALESCE(inventory_summary.chengdu_sellable_quantity,0)
                   chengdu_sellable_quantity,
               COALESCE(inventory_summary.overseas_in_transit_quantity,0)
                   overseas_in_transit_quantity,
               COALESCE(inventory_summary.overseas_sellable_quantity,0)
                   overseas_sellable_quantity,
               COALESCE(recent_windows.sales_qty_7d,0) sales_qty_7d,
               COALESCE(recent_windows.sales_qty_15d,0) sales_qty_15d,
               COALESCE(recent_windows.sales_qty_30d,0) sales_qty_30d,
               COUNT(*) OVER() total_count
        FROM base
        LEFT JOIN recent_windows
          ON recent_windows.site_name=base.site
         AND recent_windows.inventory_sku=base.sku
        LEFT JOIN inventory_summary
          ON CONVERT(inventory_summary.site USING utf8mb4) COLLATE utf8mb4_unicode_ci
             =CONVERT(base.site USING utf8mb4) COLLATE utf8mb4_unicode_ci
         AND CONVERT(inventory_summary.sku USING utf8mb4) COLLATE utf8mb4_unicode_ci
             =CONVERT(base.sku USING utf8mb4) COLLATE utf8mb4_unicode_ci
        {where_sql}
        ORDER BY {sort_column} {sort_direction},site ASC,sku ASC
        {limit_sql}
    """
    params: list[Any] = [range_start, range_end, *month_params, *filter_params]
    if paginate_in_sql:
        params.extend([page_size, (page - 1) * page_size])

    with db_connection() as connection, connection.cursor() as cursor:
        cursor.execute(query, params)
        rows = cursor.fetchall()
        total = int(rows[0].get("total_count") or 0) if rows else 0
        if not rows and page > 1:
            total = _count_filtered(
                cursor, range_start, range_end, where_sql, filter_params
            )
        cursor.execute(
            """SELECT DISTINCT site_name
               FROM dwd_ebay_sku_analysis_order
               WHERE payment_time >= %s AND payment_time < %s
                 AND site_name IS NOT NULL AND site_name<>''
               ORDER BY site_name""",
            (range_start, range_end),
        )
        sites = [row["site_name"] for row in cursor.fetchall()]

    lead_time_days = repository.lead_time_days_by_sku() if rows else {}
    formula_configs = repository.formula_by_level() if rows else {}
    first_listing_dates = repository.first_listing_date_by_sku() if rows else {}
    inventory_ages = repository.overseas_inventory_age_by_sku() if rows else {}
    forecast_formula = repository.forecast_formula_by_group() if rows else {}
    items = _assemble_items(
        rows,
        months,
        lead_time_days=lead_time_days,
        formula_configs=formula_configs,
        first_listing_dates=first_listing_dates,
        inventory_ages=inventory_ages,
        forecast_formula=forecast_formula,
    )
    if level_filter is not None or nature_filter is not None:
        items = [
            item
            for item in items
            if (
                level_filter is None
                or str(item.get("product_level") or "").strip().upper()
                == level_filter
            )
            and (
                nature_filter is None
                or str(item.get("product_nature") or "").strip()
                == nature_filter
            )
        ]
    if forecast_sort_requested:
        items = _sort_forecast_sales_2(items, sort_direction)
    if not paginate_in_sql:
        total = len(items)
        offset = (page - 1) * page_size
        items = items[offset:offset + page_size]
    return {
        "items": items,
        "months": [month["month"] for month in months],
        "latest_complete_month": months[0]["month"],
        "sites": sites,
        "pagination": {"page": page, "page_size": page_size, "total": total},
    }


def _count_filtered(cursor, range_start, range_end, where_sql, filter_params) -> int:
    query = f"""
        WITH period_keys AS (
            SELECT DISTINCT site_name,inventory_sku
            FROM dwd_ebay_sku_analysis_order
            WHERE payment_time >= %s AND payment_time < %s
        ),
        latest_source AS (
            SELECT site_name,inventory_sku,product_name_cn
            FROM (
                SELECT source.site_name,source.inventory_sku,source.product_name_cn,
                       ROW_NUMBER() OVER (
                           PARTITION BY source.site_name,source.inventory_sku
                           ORDER BY source.payment_time DESC,source.id DESC
                       ) latest_rank
                FROM dwd_ebay_sku_analysis_order source
                INNER JOIN period_keys period_key
                    ON period_key.site_name=source.site_name
                   AND period_key.inventory_sku=source.inventory_sku
            ) ranked_source
            WHERE latest_rank=1
        ),
        base AS (
            SELECT period_key.site_name site,period_key.inventory_sku sku,
                   latest_source.product_name_cn product_name
            FROM period_keys period_key
            LEFT JOIN latest_source
              ON latest_source.site_name=period_key.site_name
             AND latest_source.inventory_sku=period_key.inventory_sku
        )
        SELECT COUNT(*) total FROM base {where_sql}
    """
    cursor.execute(query, [range_start, range_end, *filter_params])
    row = cursor.fetchone() or {}
    return int(row.get("total") or 0)


def _filters(
    site: str | None, sku: str | None, product_name: str | None
) -> tuple[str, list[Any]]:
    clauses: list[str] = []
    params: list[Any] = []
    if site and site.strip():
        clauses.append("base.site=%s")
        params.append(site.strip())
    if sku and sku.strip():
        clauses.append("base.sku LIKE %s")
        params.append(f"%{sku.strip().upper()}%")
    if product_name and product_name.strip():
        clauses.append("COALESCE(base.product_name,'') LIKE %s")
        params.append(f"%{product_name.strip()}%")
    return ("WHERE " + " AND ".join(clauses), params) if clauses else ("", params)


def _complete_months(reference_date: date | None = None) -> list[dict[str, Any]]:
    current = reference_date or date.today()
    current_month_start = date(current.year, current.month, 1)
    months: list[dict[str, Any]] = []
    end_date = current_month_start
    for _ in range(3):
        start_date = _previous_month_start(end_date)
        months.append(
            {
                "month": start_date.strftime("%Y-%m"),
                "start_date": start_date,
                "end_date": end_date,
            }
        )
        end_date = start_date
    return months


def _previous_month_start(value: date) -> date:
    if value.month == 1:
        return date(value.year - 1, 12, 1)
    return date(value.year, value.month - 1, 1)


def _assemble_items(
    rows: list[dict[str, Any]],
    months: list[dict[str, Any]],
    lead_time_days: dict[tuple[str, str], Decimal] | None = None,
    formula_configs: dict[str, dict[str, Decimal]] | None = None,
    first_listing_dates: dict[tuple[str, str], Any] | None = None,
    inventory_ages: dict[tuple[str, str], Decimal] | None = None,
    forecast_formula: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    lead_time_days = lead_time_days or {}
    formula_configs = formula_configs or {}
    first_listing_dates = first_listing_dates or {}
    inventory_ages = inventory_ages or {}
    forecast_formula = forecast_formula or {}
    today = date.today()
    result: list[dict[str, Any]] = []
    for row in rows:
        monthly_metrics = []
        for index, month in enumerate(months, start=1):
            raw_sales_qty = row.get(f"sales_qty_m{index}")
            raw_gross_profit_amount = row.get(f"gross_profit_amount_m{index}")
            raw_return_qty = row.get(f"return_qty_m{index}")
            sales_qty = _quantity_text(raw_sales_qty)
            gross_profit_amount = _money_text(
                raw_gross_profit_amount
            )
            return_qty = _quantity_text(raw_return_qty)
            monthly_metrics.append(
                {
                    "month": month["month"],
                    "sales_qty": sales_qty,
                    "gross_profit_amount": gross_profit_amount,
                    "return_qty": return_qty,
                    "return_amount": _money_text(row.get(f"return_amount_m{index}")),
                }
            )
        latest = monthly_metrics[0]
        raw_forecast_sales_quantity = _average_metric_decimal(
            monthly_metrics, "sales_qty"
        )
        forecast_sales_quantity = _average_metric(monthly_metrics, "sales_qty")
        forecast_gross_profit_amount = _average_metric(
            monthly_metrics, "gross_profit_amount"
        )
        forecast_return_quantity = _average_metric(monthly_metrics, "return_qty")
        forecast_return_amount = _average_metric(monthly_metrics, "return_amount")
        sell_through_ratio = _ratio_decimal(
            raw_forecast_sales_quantity, row.get("overseas_sellable_quantity")
        )
        three_month_profit = sum(
            (_decimal(row.get(f"gross_profit_amount_m{index}")) for index in range(1, 4)),
            Decimal("0"),
        )
        three_month_paid_amount = sum(
            (_decimal(row.get(f"paid_amount_m{index}")) for index in range(1, 4)),
            Decimal("0"),
        )
        three_month_return_qty = sum(
            (_decimal(row.get(f"return_qty_m{index}")) for index in range(1, 4)),
            Decimal("0"),
        )
        three_month_sales_qty = sum(
            (_decimal(row.get(f"sales_qty_m{index}")) for index in range(1, 4)),
            Decimal("0"),
        )
        profit_rate = _ratio_decimal(three_month_profit, three_month_paid_amount)
        return_rate = _ratio_decimal(three_month_return_qty, three_month_sales_qty)
        product_level = _product_level(return_rate, profit_rate, sell_through_ratio)
        product_nature = _product_nature(
            first_listing_dates.get(
                (
                    str(row.get("sku") or "").strip(),
                    str(row.get("site") or "其他").strip(),
                )
            ),
            today,
        )
        overseas_inventory_age = inventory_ages.get(
            (
                str(row.get("site") or "其他").strip(),
                str(row.get("sku") or "").strip(),
            )
        )
        forecast_sales_quantity_2 = _forecast_sales_2(
            product_nature=product_nature,
            sales_7d=_decimal(row.get("sales_qty_7d")),
            sales_15d=_decimal(row.get("sales_qty_15d")),
            sales_30d=_decimal(row.get("sales_qty_30d")),
            age_days=overseas_inventory_age,
            config=forecast_formula,
        )
        safety_stock_quantity, suggested_replenishment_quantity = (
            _replenishment_quantities(
                site=str(row.get("site") or "其他").strip(),
                sku=str(row.get("sku") or "").strip(),
                average_monthly_sales=raw_forecast_sales_quantity,
                product_level=product_level,
                inventory_total=sum(
                    (
                        _decimal(row.get("chengdu_in_transit_quantity")),
                        _decimal(row.get("chengdu_sellable_quantity")),
                        _decimal(row.get("overseas_in_transit_quantity")),
                        _decimal(row.get("overseas_sellable_quantity")),
                    ),
                    Decimal("0"),
                ),
                lead_time_days=lead_time_days,
                formula_configs=formula_configs,
            )
        )
        result.append(
            {
                "site": row.get("site") or "其他",
                "sku": row.get("sku") or "",
                "product_name": row.get("product_name") or "",
                "sales_qty_7d": _quantity_text(row.get("sales_qty_7d")),
                "sales_qty_15d": _quantity_text(row.get("sales_qty_15d")),
                "sales_qty_30d": _quantity_text(row.get("sales_qty_30d")),
                "sales_qty": latest["sales_qty"],
                "gross_profit_amount": latest["gross_profit_amount"],
                "profit_rate": _ratio_decimal_text(profit_rate),
                "return_qty": latest["return_qty"],
                "return_amount": latest["return_amount"],
                "return_rate": _ratio_decimal_text(return_rate),
                "forecast_sales_quantity": forecast_sales_quantity,
                "overseas_inventory_age_days": (
                    _quantity_text(overseas_inventory_age)
                    if overseas_inventory_age is not None
                    else None
                ),
                "forecast_sales_quantity_2": _forecast_quantity_text(
                    forecast_sales_quantity_2
                ),
                "forecast_gross_profit_amount": forecast_gross_profit_amount,
                "forecast_return_quantity": forecast_return_quantity,
                "forecast_return_amount": forecast_return_amount,
                "sell_through_ratio": _ratio_decimal_text(sell_through_ratio),
                "product_level": product_level,
                "product_nature": product_nature,
                "chengdu_in_transit_quantity": _quantity_text(
                    row.get("chengdu_in_transit_quantity")
                ),
                "chengdu_sellable_quantity": _quantity_text(
                    row.get("chengdu_sellable_quantity")
                ),
                "overseas_in_transit_quantity": _quantity_text(
                    row.get("overseas_in_transit_quantity")
                ),
                "overseas_sellable_quantity": _quantity_text(
                    row.get("overseas_sellable_quantity")
                ),
                "safety_stock_quantity": safety_stock_quantity,
                "suggested_replenishment_quantity": suggested_replenishment_quantity,
                "monthly_metrics": monthly_metrics,
            }
        )
    return result


def _ratio_decimal(numerator: Any, denominator: Any) -> Decimal | None:
    denominator_value = _decimal(denominator)
    if denominator_value == 0:
        return None
    return _decimal(numerator) / denominator_value


def _ratio_text(numerator: Any, denominator: Any) -> str | None:
    return _ratio_decimal_text(_ratio_decimal(numerator, denominator))


def _ratio_decimal_text(value: Decimal | None) -> str | None:
    if value is None:
        return None
    return format(
        value.quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP), "f"
    )


def _product_level(
    return_rate: Decimal | None,
    profit_rate: Decimal | None,
    monthly_turnover_rate: Decimal | None,
) -> str | None:
    """按用户给定的 1→9 优先级计算产品等级，所有比率均用小数值。"""

    if return_rate is None:
        return None
    if return_rate > Decimal("0.06"):
        return "C"
    if profit_rate is None:
        return None
    if return_rate >= Decimal("0.03"):
        # 长尾产品统一按 B 级展示与计算，不再单独输出「长尾产品-B」标签。
        return "C" if profit_rate < Decimal("0.18") else "B"
    if monthly_turnover_rate is None:
        return None
    if profit_rate < Decimal("0.12"):
        return "C" if monthly_turnover_rate <= Decimal("0.12") else "B"
    if profit_rate < Decimal("0.22"):
        return "B" if monthly_turnover_rate < Decimal("0.12") else "A"
    return "B" if monthly_turnover_rate < Decimal("0.15") else "S"


_NEW_PRODUCT_MAX_DAYS = 90


def _product_nature(first_listing_date: Any, today: date) -> str | None:
    """刊登超过90天为老品，90天以内（含90天）为新品。"""

    if first_listing_date is None:
        return None
    if isinstance(first_listing_date, datetime):
        listing_date = first_listing_date.date()
    elif isinstance(first_listing_date, date):
        listing_date = first_listing_date
    else:
        try:
            listing_date = date.fromisoformat(str(first_listing_date).strip()[:10])
        except (TypeError, ValueError):
            return None
    return (
        "老品"
        if (today - listing_date).days > _NEW_PRODUCT_MAX_DAYS
        else "新品"
    )


def _forecast_sales_2(
    *,
    product_nature: str | None,
    sales_7d: Decimal,
    sales_15d: Decimal,
    sales_30d: Decimal,
    age_days: Decimal | None,
    config: dict[str, Any],
) -> Decimal | None:
    """新品按最老批次库龄折算，老品按日均分档加权；封顶值由MISC配置控制。"""

    if product_nature not in {"新品", "老品"}:
        return None
    misc = config.get("MISC")
    if not isinstance(misc, dict):
        return None
    month_days = misc.get("month_days")
    new_age_cap = misc.get("new_age_cap")
    fallback_ratio = misc.get("old_fallback_ratio")
    if (
        month_days is None
        or _decimal(month_days) <= 0
        or new_age_cap is None
        or _decimal(new_age_cap) <= 0
        or fallback_ratio is None
        or _decimal(fallback_ratio) < 0
    ):
        return None

    month_days_value = _decimal(month_days)
    fallback = sales_30d * _decimal(fallback_ratio)
    if product_nature == "新品":
        if age_days is None or _decimal(age_days) <= 0:
            return fallback
        divisor = min(_decimal(age_days), _decimal(new_age_cap))
        return sales_30d * month_days_value / divisor

    rate_7d = sales_7d / Decimal("7")
    rate_15d = sales_15d / Decimal("15")
    rate_30d = sales_30d / Decimal("30")
    if sales_7d > 0:
        tier = _match_tier(config.get("OLD_7D"), rate_7d, rate_30d)
        if tier is None:
            return None
        weights = (
            tier.get("weight_7d"),
            tier.get("weight_15d"),
            tier.get("weight_30d"),
        )
        if any(weight is None for weight in weights):
            return None
        weighted = (
            rate_7d * _decimal(weights[0])
            + rate_15d * _decimal(weights[1])
            + rate_30d * _decimal(weights[2])
        )
    elif sales_15d > 0:
        tier = _match_tier(config.get("OLD_15D"), rate_15d, rate_30d)
        if tier is None:
            return None
        weights = (tier.get("weight_15d"), tier.get("weight_30d"))
        if any(weight is None for weight in weights):
            return None
        weighted = (
            rate_15d * _decimal(weights[0])
            + rate_30d * _decimal(weights[1])
        )
    else:
        # 规则12包含近30天也为0的规则13，此时自然返回0。
        return fallback
    return weighted * month_days_value


def _match_tier(
    tiers: Any, rate: Decimal, rate_30d: Decimal
) -> dict[str, Any] | None:
    """按档位升序取第一个满足下限的档，NULL阈值为无条件兜底。"""

    if not isinstance(tiers, list) or not tiers:
        return None
    for tier in tiers:
        threshold = tier.get("threshold_ratio")
        if threshold is None or rate >= _decimal(threshold) * rate_30d:
            return tier
    return None


def _sort_forecast_sales_2(
    items: list[dict[str, Any]], direction: str
) -> list[dict[str, Any]]:
    """预估销量2是派生值，需在组装后内存排序；空值始终排在末尾。"""

    available = [
        item
        for item in items
        if item.get("forecast_sales_quantity_2") is not None
    ]
    missing = [
        item
        for item in items
        if item.get("forecast_sales_quantity_2") is None
    ]
    available.sort(
        key=lambda item: (
            str(item.get("site") or ""),
            str(item.get("sku") or ""),
        )
    )
    available.sort(
        key=lambda item: _decimal(item.get("forecast_sales_quantity_2")),
        reverse=direction == "DESC",
    )
    return available + missing


def _replenishment_quantities(
    *,
    site: str,
    sku: str,
    average_monthly_sales: Decimal,
    product_level: str | None,
    inventory_total: Decimal,
    lead_time_days: dict[tuple[str, str], Decimal],
    formula_configs: dict[str, dict[str, Decimal]],
) -> tuple[str | None, str | None]:
    """按全局配置实时计算安全库存和建议补货量。"""

    key = (site, sku)
    if key not in lead_time_days:
        return None, None
    normalized_level = product_level
    if normalized_level not in {"S", "A", "B", "C"}:
        return None, None
    config = formula_configs.get(normalized_level)
    if config is None:
        return None, None
    safety_coefficient = config.get("safety_coefficient")
    suggest_coefficient = config.get("suggest_coefficient")
    if safety_coefficient is None or suggest_coefficient is None:
        return None, None

    total_days = _decimal(lead_time_days[key])
    safety_stock = (
        average_monthly_sales
        * total_days
        * _decimal(safety_coefficient)
        / Decimal("30")
    ).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    suggested = (
        average_monthly_sales
        * total_days
        * _decimal(suggest_coefficient)
        / Decimal("30")
        - inventory_total
    )
    suggested = max(suggested, Decimal("0")).quantize(
        Decimal("1"), rounding=ROUND_HALF_UP
    )
    return format(safety_stock, "f"), format(suggested, "f")


def list_formula_configs() -> list[dict[str, Any]]:
    return [_formula_response(row) for row in repository.list_formula_rows()]


def save_formula_configs(
    rows: list[dict[str, Any]], operator: str | None = None
) -> list[dict[str, Any]]:
    expected_levels = {"S", "A", "B", "C"}
    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in rows:
        level = str(row.get("product_level") or "").strip().upper()
        if level not in expected_levels or level in seen:
            raise ValueError("公式配置必须且只能包含 S、A、B、C 四个级别")
        seen.add(level)
        remark = str(row.get("remark") or "").strip()
        if len(remark) > 500:
            raise ValueError(f"{level}级备注不能超过500个字符")
        normalized.append(
            {
                "product_level": level,
                "safety_coefficient": _non_negative_decimal(
                    row.get("safety_coefficient"), f"{level}级安全系数"
                ),
                "suggest_coefficient": _non_negative_decimal(
                    row.get("suggest_coefficient"), f"{level}级补货系数"
                ),
                "remark": remark or None,
            }
        )
    if seen != expected_levels:
        raise ValueError("公式配置必须且只能包含 S、A、B、C 四个级别")
    safe_operator = str(operator or "SYSTEM").strip()[:64] or "SYSTEM"
    repository.save_formula_rows(normalized, safe_operator)
    return list_formula_configs()


def _formula_response(row: dict[str, Any]) -> dict[str, Any]:
    return {
        **row,
        "safety_coefficient": format(
            _decimal(row.get("safety_coefficient")), "f"
        ),
        "suggest_coefficient": format(
            _decimal(row.get("suggest_coefficient")), "f"
        ),
    }


def list_forecast_formula_configs() -> list[dict[str, Any]]:
    return [
        _forecast_formula_response(row)
        for row in repository.list_forecast_formula_rows()
    ]


def save_forecast_formula_configs(
    rows: list[dict[str, Any]], operator: str | None = None
) -> list[dict[str, Any]]:
    expected_keys = {
        *(("OLD_7D", tier) for tier in range(1, 6)),
        *(("OLD_15D", tier) for tier in range(1, 6)),
        ("MISC", 1),
    }
    normalized: list[dict[str, Any]] = []
    seen: set[tuple[str, int]] = set()
    for row in rows:
        group = str(row.get("rule_group") or "").strip().upper()
        tier = _positive_int(row.get("tier"), 0)
        key = (group, tier)
        if key not in expected_keys or key in seen:
            raise ValueError("预估销量2公式必须且只能包含两个五档规则组和一条全局配置")
        seen.add(key)
        remark = str(row.get("remark") or "").strip()
        if len(remark) > 255:
            raise ValueError(f"{group}第{tier}档备注不能超过255个字符")
        item: dict[str, Any] = {
            "rule_group": group,
            "tier": tier,
            "threshold_ratio": None,
            "weight_7d": None,
            "weight_15d": None,
            "weight_30d": None,
            "month_days": None,
            "new_age_cap": None,
            "old_fallback_ratio": None,
            "remark": remark or None,
        }
        if group == "OLD_7D":
            if tier < 5:
                item["threshold_ratio"] = _required_non_negative_decimal(
                    row.get("threshold_ratio"), f"老品近7天第{tier}档阈值"
                )
            elif row.get("threshold_ratio") not in {None, ""}:
                raise ValueError("老品近7天第5档必须是无阈值兜底档")
            item["weight_7d"] = _required_non_negative_decimal(
                row.get("weight_7d"), f"老品近7天第{tier}档7天权重"
            )
            item["weight_15d"] = _required_non_negative_decimal(
                row.get("weight_15d"), f"老品近7天第{tier}档15天权重"
            )
            item["weight_30d"] = _required_non_negative_decimal(
                row.get("weight_30d"), f"老品近7天第{tier}档30天权重"
            )
        elif group == "OLD_15D":
            if tier < 5:
                item["threshold_ratio"] = _required_non_negative_decimal(
                    row.get("threshold_ratio"), f"老品近15天第{tier}档阈值"
                )
            elif row.get("threshold_ratio") not in {None, ""}:
                raise ValueError("老品近15天第5档必须是无阈值兜底档")
            item["weight_15d"] = _required_non_negative_decimal(
                row.get("weight_15d"), f"老品近15天第{tier}档15天权重"
            )
            item["weight_30d"] = _required_non_negative_decimal(
                row.get("weight_30d"), f"老品近15天第{tier}档30天权重"
            )
        else:
            item["month_days"] = _required_positive_decimal(
                row.get("month_days"), "月销折算天数"
            )
            item["new_age_cap"] = _required_positive_decimal(
                row.get("new_age_cap"), "新品库龄封顶天数"
            )
            item["old_fallback_ratio"] = _required_non_negative_decimal(
                row.get("old_fallback_ratio"), "无近期销量回退系数"
            )
        normalized.append(item)
    if seen != expected_keys:
        raise ValueError("预估销量2公式必须且只能包含两个五档规则组和一条全局配置")
    safe_operator = str(operator or "SYSTEM").strip()[:64] or "SYSTEM"
    repository.save_forecast_formula_rows(normalized, safe_operator)
    return list_forecast_formula_configs()


def _forecast_formula_response(row: dict[str, Any]) -> dict[str, Any]:
    decimal_fields = (
        "threshold_ratio",
        "weight_7d",
        "weight_15d",
        "weight_30d",
        "month_days",
        "new_age_cap",
        "old_fallback_ratio",
    )
    return {
        **row,
        **{
            field: (
                format(_decimal(row.get(field)), "f")
                if row.get(field) is not None
                else None
            )
            for field in decimal_fields
        },
    }


def _non_negative_decimal(value: Any, label: str) -> Decimal:
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError(f"{label}必须是有效数字") from exc
    if not result.is_finite() or result < 0:
        raise ValueError(f"{label}必须大于或等于0")
    return result.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)


def _required_non_negative_decimal(value: Any, label: str) -> Decimal:
    if value is None or value == "":
        raise ValueError(f"{label}不能为空")
    return _non_negative_decimal(value, label)


def _required_positive_decimal(value: Any, label: str) -> Decimal:
    result = _required_non_negative_decimal(value, label)
    if result <= 0:
        raise ValueError(f"{label}必须大于0")
    return result


def _average_metric(monthly_metrics: list[dict[str, str]], key: str) -> str:
    average = _average_metric_decimal(monthly_metrics, key).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )
    return format(average, "f")


def _average_metric_decimal(
    monthly_metrics: list[dict[str, Any]], key: str
) -> Decimal:
    total = sum(
        (_decimal(metric.get(key)) for metric in monthly_metrics), Decimal("0")
    )
    return total / Decimal("3")


def _quantity_text(value: Any) -> str:
    decimal_value = _decimal(value)
    if decimal_value == 0:
        return "0"
    return format(decimal_value.normalize(), "f")


def _forecast_quantity_text(value: Decimal | None) -> str | None:
    if value is None:
        return None
    return format(
        value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP), "f"
    )


def _money_text(value: Any) -> str:
    return format(_decimal(value).quantize(Decimal("0.01")), "f")


def _decimal(value: Any) -> Decimal:
    try:
        return Decimal(str(value or 0))
    except (InvalidOperation, ValueError, TypeError):
        return Decimal("0")


def _positive_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default
