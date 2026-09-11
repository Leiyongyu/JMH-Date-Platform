from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any

from backend.database import db_connection
from backend.repositories import ebay_replenishment_v2_repository as repository
from backend.services import ebay_sku_analysis_service as sku_analysis_service
from backend.services import ebay_level_rule_service as level_service
from backend.services import ebay_replenishment_sales_type_service as sales_type_service
from backend.repositories import ebay_replenishment_sales_type_repository as sales_type_repository
from backend.services.ebay_forecast_rule_engine import (
    PreparedRules,
    calculate_forecast as _forecast_sales_2,
    prepare_rules,
)


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


from backend.services.ebay_inventory_shared import inventory_ctes


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
    sales_type: str | None = None,
    *,
    paginate: bool = True,
) -> dict[str, Any]:
    """Return the latest three complete natural months by site and SKU.

    All measures deliberately keep the existing SKU-analysis payment-month
    definitions.  The latest complete month is also exposed as each row's
    primary value; the complete three-month series is returned in
    ``monthly_metrics`` for the UI hover card.
    """

    sales_type_filter = sales_type_service.normalize_filter(sales_type)
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
        paginate
        and level_filter is None
        and nature_filter is None
        and not forecast_sort_requested
    )

    range_start = months[-1]["start_date"]
    range_end = months[0]["end_date"]
    where_sql, filter_params = _filters(site, sku, product_name)
    sales_type_join = sales_type_repository.join_sql()
    sales_type_select = "COALESCE(sales_type.sales_type,'NORMAL') AS sales_type"
    sales_type_available = True
    if sales_type_filter:
        where_sql += (" AND " if where_sql else "WHERE ") + "COALESCE(sales_type.sales_type,'NORMAL')=%s"
        filter_params.append(sales_type_filter)
    # 站点和 SKU 都是订单源表原生字段，可在 CTE 聚合前安全下推。
    # 商品名称取自最新一条历史订单，只能保留在外层，避免改变原有语义。
    source_where_sql, source_filter_params = _source_filters(site, sku)
    recent_where_sql, recent_filter_params = _source_filters(
        site, sku, alias="recent"
    )
    limit_sql = "LIMIT %s OFFSET %s" if paginate_in_sql else ""
    month_params = [month["month"] for month in months for _ in range(7)]
    query = f"""
        WITH period_rows AS (
            SELECT id,site_name,inventory_sku,payment_time,purchase_quantity,
                   paid_amount_cny,order_profit_cny,refund_quantity,refund_amount_cny,
                   shipping_status,
                   CASE WHEN TRIM(assignment.big_category)='产品质量问题'
                        THEN refund_quantity ELSE 0 END quality_return_qty,
                   CASE WHEN assignment.platform_order_no IS NULL
                        THEN refund_quantity ELSE 0 END unclassified_return_qty
            FROM dwd_ebay_sku_analysis_order
            -- 按中间分类匹配，包含其全部小类；订单号主键一对一关联，不扩增订单行。
            LEFT JOIN ebay_sku_analysis_return_classification assignment
              ON assignment.platform_order_no=dwd_ebay_sku_analysis_order.platform_order_no
            WHERE payment_time >= %s AND payment_time < %s
            {source_where_sql}
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
              {recent_where_sql}
            GROUP BY recent.site_name,recent.inventory_sku
        ),
        period_keys AS (
            SELECT DISTINCT site_name,inventory_sku FROM period_rows
        ),
        latest_source AS (
            SELECT period_key.site_name,period_key.inventory_sku,
                   (
                       SELECT source.product_name_cn
                       FROM dwd_ebay_sku_analysis_order source
                       WHERE source.site_name=period_key.site_name
                         AND source.inventory_sku=period_key.inventory_sku
                       ORDER BY source.payment_time DESC,source.id DESC
                       LIMIT 1
                   ) product_name_cn
            FROM period_keys period_key
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
                            THEN refund_amount_cny ELSE 0 END) return_amount,
                   SUM(quality_return_qty) quality_return_qty,
                   SUM(unclassified_return_qty) unclassified_return_qty
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
                   COALESCE(SUM(CASE WHEN monthly.stat_month=%s THEN monthly.quality_return_qty ELSE 0 END),0) quality_return_qty_m1,
                   COALESCE(SUM(CASE WHEN monthly.stat_month=%s THEN monthly.unclassified_return_qty ELSE 0 END),0) unclassified_return_qty_m1,
                   COALESCE(SUM(CASE WHEN monthly.stat_month=%s THEN monthly.sales_qty ELSE 0 END),0) sales_qty_m2,
                   COALESCE(SUM(CASE WHEN monthly.stat_month=%s THEN monthly.gross_profit_amount ELSE 0 END),0) gross_profit_amount_m2,
                   COALESCE(SUM(CASE WHEN monthly.stat_month=%s THEN monthly.paid_amount ELSE 0 END),0) paid_amount_m2,
                   COALESCE(SUM(CASE WHEN monthly.stat_month=%s THEN monthly.return_qty ELSE 0 END),0) return_qty_m2,
                   COALESCE(SUM(CASE WHEN monthly.stat_month=%s THEN monthly.return_amount ELSE 0 END),0) return_amount_m2,
                   COALESCE(SUM(CASE WHEN monthly.stat_month=%s THEN monthly.quality_return_qty ELSE 0 END),0) quality_return_qty_m2,
                   COALESCE(SUM(CASE WHEN monthly.stat_month=%s THEN monthly.unclassified_return_qty ELSE 0 END),0) unclassified_return_qty_m2,
                   COALESCE(SUM(CASE WHEN monthly.stat_month=%s THEN monthly.sales_qty ELSE 0 END),0) sales_qty_m3,
                   COALESCE(SUM(CASE WHEN monthly.stat_month=%s THEN monthly.gross_profit_amount ELSE 0 END),0) gross_profit_amount_m3,
                   COALESCE(SUM(CASE WHEN monthly.stat_month=%s THEN monthly.paid_amount ELSE 0 END),0) paid_amount_m3,
                   COALESCE(SUM(CASE WHEN monthly.stat_month=%s THEN monthly.return_qty ELSE 0 END),0) return_qty_m3,
                   COALESCE(SUM(CASE WHEN monthly.stat_month=%s THEN monthly.return_amount ELSE 0 END),0) return_amount_m3,
                   COALESCE(SUM(CASE WHEN monthly.stat_month=%s THEN monthly.quality_return_qty ELSE 0 END),0) quality_return_qty_m3,
                   COALESCE(SUM(CASE WHEN monthly.stat_month=%s THEN monthly.unclassified_return_qty ELSE 0 END),0) unclassified_return_qty_m3
            FROM monthly
            LEFT JOIN latest_source
              ON latest_source.site_name=monthly.site_name
             AND latest_source.inventory_sku=monthly.inventory_sku
            GROUP BY monthly.site_name,monthly.inventory_sku,
                     latest_source.product_name_cn
        ),
        {inventory_ctes()}
        SELECT base.*,
               {sales_type_select},
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
        {sales_type_join}
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
    params: list[Any] = [
        range_start,
        range_end,
        *source_filter_params,
        *recent_filter_params,
        *month_params,
        *filter_params,
    ]
    if paginate_in_sql:
        params.extend([page_size, (page - 1) * page_size])

    with db_connection() as connection, connection.cursor() as cursor:
        try:
            cursor.execute(query, params)
        except Exception as exc:
            if not sales_type_repository.missing_table(exc):
                raise
            if sales_type_filter:
                raise ValueError(sales_type_repository.MIGRATION_MESSAGE) from exc
            # 缺部署表时保留旧列表，明确返回不可编辑状态，不把丢失配置伪装成正常。
            query = query.replace(sales_type_join, "").replace(sales_type_select, "NULL AS sales_type")
            sales_type_join = ""
            sales_type_available = False
            cursor.execute(query, params)
        rows = cursor.fetchall()
        total = int(rows[0].get("total_count") or 0) if rows else 0
        if paginate and not rows and page > 1:
            total = _count_filtered(
                cursor,
                range_start,
                range_end,
                source_where_sql,
                source_filter_params,
                where_sql,
                filter_params,
                sales_type_join,
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
    forecast_rules = prepare_rules(repository.forecast_rules()) if rows else PreparedRules()
    level_rules = level_service.prepare_levels(repository.list_level_rules(allow_missing=True)) if rows else None
    items = _assemble_items(
        rows,
        months,
        lead_time_days=lead_time_days,
        formula_configs=formula_configs,
        first_listing_dates=first_listing_dates,
        inventory_ages=inventory_ages,
        forecast_rules=forecast_rules,
        level_rules=level_rules,
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
        if paginate:
            offset = (page - 1) * page_size
            items = items[offset:offset + page_size]
    return {
        "items": items,
        "sales_type_available": sales_type_available,
        "months": [month["month"] for month in months],
        "latest_complete_month": months[0]["month"],
        "sites": sites,
        "pagination": {
            "page": page if paginate else 1,
            "page_size": page_size if paginate else total,
            "total": total,
        },
    }


def _count_filtered(
    cursor,
    range_start,
    range_end,
    source_where_sql,
    source_filter_params,
    where_sql,
    filter_params,
    sales_type_join="",
) -> int:
    query = f"""
        WITH period_keys AS (
            SELECT DISTINCT site_name,inventory_sku
            FROM dwd_ebay_sku_analysis_order
            WHERE payment_time >= %s AND payment_time < %s
            {source_where_sql}
        ),
        latest_source AS (
            SELECT period_key.site_name,period_key.inventory_sku,
                   (
                       SELECT source.product_name_cn
                       FROM dwd_ebay_sku_analysis_order source
                       WHERE source.site_name=period_key.site_name
                         AND source.inventory_sku=period_key.inventory_sku
                       ORDER BY source.payment_time DESC,source.id DESC
                       LIMIT 1
                   ) product_name_cn
            FROM period_keys period_key
        ),
        base AS (
            SELECT period_key.site_name site,period_key.inventory_sku sku,
                   latest_source.product_name_cn product_name
            FROM period_keys period_key
            LEFT JOIN latest_source
              ON latest_source.site_name=period_key.site_name
             AND latest_source.inventory_sku=period_key.inventory_sku
        )
        SELECT COUNT(*) total FROM base {sales_type_join} {where_sql}
    """
    cursor.execute(
        query,
        [range_start, range_end, *source_filter_params, *filter_params],
    )
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


def _source_filters(
    site: str | None, sku: str | None, alias: str | None = None
) -> tuple[str, list[Any]]:
    """生成可安全下推到订单源表的站点/SKU条件；保留现有模糊搜索语义。"""

    prefix = f"{alias}." if alias else ""
    clauses: list[str] = []
    params: list[Any] = []
    if site and site.strip():
        clauses.append(f"{prefix}site_name=%s")
        params.append(site.strip())
    if sku and sku.strip():
        clauses.append(f"{prefix}inventory_sku LIKE %s")
        params.append(f"%{sku.strip().upper()}%")
    return (" AND " + " AND ".join(clauses), params) if clauses else ("", params)


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
    forecast_rules: PreparedRules | None = None,
    level_rules=None,
) -> list[dict[str, Any]]:
    lead_time_days = lead_time_days or {}
    formula_configs = formula_configs or {}
    first_listing_dates = first_listing_dates or {}
    inventory_ages = inventory_ages or {}
    forecast_rules = forecast_rules or PreparedRules()
    today = date.today()
    result: list[dict[str, Any]] = []
    for row in rows:
        monthly_metrics = []
        for index, month in enumerate(months, start=1):
            raw_sales_qty = row.get(f"sales_qty_m{index}")
            raw_gross_profit_amount = row.get(f"gross_profit_amount_m{index}")
            raw_return_qty = row.get(f"return_qty_m{index}")
            raw_quality_return_qty = row.get(f"quality_return_qty_m{index}")
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
                    "quality_return_qty": _quantity_text(raw_quality_return_qty),
                    "quality_return_rate": _ratio_text(raw_quality_return_qty, raw_sales_qty),
                    "unclassified_return_qty": _quantity_text(row.get(f"unclassified_return_qty_m{index}")),
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
        sell_through_ratio = _sell_through_ratio(
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
        # 独立观察指标，不替换总退货率，也不参与产品等级和补货量计算。
        quality_return_qty = sum(
            (_decimal(row.get(f"quality_return_qty_m{index}")) for index in range(1, 4)),
            Decimal("0"),
        )
        quality_return_summary = {
            "return_qty": _quantity_text(three_month_return_qty),
            "quality_return_qty": _quantity_text(quality_return_qty),
            "quality_return_rate": _ratio_text(quality_return_qty, three_month_sales_qty),
            "unclassified_return_qty": _quantity_text(sum(
                (_decimal(row.get(f"unclassified_return_qty_m{index}")) for index in range(1, 4)),
                Decimal("0"),
            )),
        }
        product_level = _product_level(return_rate, profit_rate, sell_through_ratio, level_rules)
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
            rules=forecast_rules,
            round_result=False,
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
        safety_stock_quantity_2, suggested_replenishment_quantity_2 = (None, None)
        if forecast_sales_quantity_2 is not None:
            safety_stock_quantity_2, suggested_replenishment_quantity_2 = _replenishment_quantities(
                site=str(row.get("site") or "其他").strip(), sku=str(row.get("sku") or "").strip(),
                average_monthly_sales=forecast_sales_quantity_2, product_level=product_level,
                inventory_total=sum((_decimal(row.get(key)) for key in (
                    "chengdu_in_transit_quantity", "chengdu_sellable_quantity",
                    "overseas_in_transit_quantity", "overseas_sellable_quantity")), Decimal(0)),
                lead_time_days=lead_time_days, formula_configs=formula_configs,
            )
        result.append(
            {
                "site": row.get("site") or "其他",
                "sku": row.get("sku") or "",
                "sales_type": row.get("sales_type"),
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
                "safety_stock_quantity_2": safety_stock_quantity_2,
                "suggested_replenishment_quantity_2": suggested_replenishment_quantity_2,
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
                "quality_return_summary": quality_return_summary,
            }
        )
    return result


def _sell_through_ratio(forecast: Any, overseas_sellable: Any) -> Decimal | None:
    """仅动销比将零海外可售按1作分母；不修改库存原值或其他比率。"""
    if overseas_sellable is None:
        return None
    try:
        denominator = Decimal(str(overseas_sellable))
    except (InvalidOperation, ValueError, TypeError):
        return None
    if not denominator.is_finite():
        return None
    return _ratio_decimal(forecast, Decimal("1") if denominator == 0 else denominator)


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


def _product_level(return_rate, profit_rate, monthly_turnover_rate, level_rules=None):
    """按数据库启用规则顺序匹配；缺配置不回退硬编码。"""
    return level_service.calculate_level(return_rate, profit_rate, monthly_turnover_rate, level_rules)


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


def _non_negative_decimal(value: Any, label: str) -> Decimal:
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError(f"{label}必须是有效数字") from exc
    if not result.is_finite() or result < 0:
        raise ValueError(f"{label}必须大于或等于0")
    return result.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)


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
