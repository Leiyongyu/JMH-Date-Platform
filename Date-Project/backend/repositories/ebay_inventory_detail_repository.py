"""eBay 库存明细的批量取数，不修改补货 2.0 数据。等级改为按规则计算，无导入。"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

from pymysql.err import ProgrammingError

from backend.config import settings
from backend.database import db_connection

MAX_ROWS = 50_000
_PRICE_TABLE = "ebay_inventory_detail_price"
_MAX_MONTHLY_SALES_TABLE = "dws_ebay_inventory_max_monthly_sales"
_PRICE_MISSING = "Ebay库存明细单价表尚未部署，请先执行20260916_ebay_inventory_detail_price.sql"
_MAX_MONTHLY_SALES_MISSING = (
    "历史最大月销高水位表尚未部署，请先执行"
    "20260922_ebay_inventory_max_monthly_sales.sql"
)
_BATCH_SIZE = 500


def _weekly_snapshot_cte() -> str:
    # Select by source pull time, never Excel regeneration time. Deleted exports
    # still prove that the batch completed; RUNNING/FAILED exports do not.
    return """
        inventory_snapshot AS (
            SELECT i.sync_batch_id,i.snapshot_date,MAX(i.pulled_at) inventory_pulled_at
            FROM ods_lingxing_inventory_detail_weekly i
            WHERE EXISTS (
                SELECT 1 FROM ops_weekly_export_file f
                WHERE f.export_code='weekly_inventory_bin'
                  AND f.sync_batch_id=i.sync_batch_id AND f.snapshot_date=i.snapshot_date
                  AND f.status IN ('SUCCESS','DELETE_PENDING','DELETED')
            )
            GROUP BY i.sync_batch_id,i.snapshot_date
            ORDER BY inventory_pulled_at DESC,i.snapshot_date DESC,i.sync_batch_id DESC
            LIMIT 1
        )
    """


def _weekly_inventory_ctes() -> str:
    """Only this page switches sources; replenishment/shared inventory stays unchanged.

    Match the weekly export's whole-row representative (largest product_total,
    then seller_id). Do not sum multiple sellers' copies of physical stock or
    take independent maxima that would fabricate a row from different sellers.
    """
    return f"""
        {_weekly_snapshot_cte()},
        inventory_ranked AS (
            SELECT i.*,
                   ROW_NUMBER() OVER (
                       PARTITION BY i.wid,i.product_id
                       ORDER BY (i.product_total IS NOT NULL) DESC,i.product_total DESC,
                                i.seller_id DESC,i.id DESC
                   ) inventory_rank
            FROM ods_lingxing_inventory_detail_weekly i
            JOIN inventory_snapshot b
              ON b.sync_batch_id=i.sync_batch_id AND b.snapshot_date=i.snapshot_date
            WHERE i.wid IN (18674,18675,18676,18699,18700,18701,18702)
        ),
        inventory_source AS (
            SELECT CASE WHEN wid IN (18674,18699) THEN '德国'
                        WHEN wid IN (18675,18702) THEN '英国'
                        WHEN wid IN (18676,18700,18701) THEN '美国' END site,
                   TRIM(sku) sku,
                   CASE WHEN wid IN (18674,18675,18676)
                        THEN COALESCE(quantity_receive,0) ELSE 0 END chengdu_in_transit_quantity,
                   CASE WHEN wid IN (18674,18675,18676)
                        THEN COALESCE(product_valid_num,0) ELSE 0 END chengdu_sellable_quantity,
                   CASE WHEN wid IN (18699,18700,18701,18702)
                        THEN COALESCE(product_onway,0) ELSE 0 END overseas_in_transit_quantity,
                   CASE WHEN wid IN (18699,18700,18701,18702)
                        THEN COALESCE(product_valid_num,0) ELSE 0 END overseas_sellable_quantity,
                   COALESCE(product_total,0) pending_outbound_quantity
            FROM inventory_ranked
            WHERE inventory_rank=1 AND sku IS NOT NULL AND TRIM(sku)<>''
        ),
        inventory_summary AS (
            SELECT site,sku,
                   SUM(chengdu_in_transit_quantity) chengdu_in_transit_quantity,
                   SUM(chengdu_sellable_quantity) chengdu_sellable_quantity,
                   SUM(overseas_in_transit_quantity) overseas_in_transit_quantity,
                   SUM(overseas_sellable_quantity) overseas_sellable_quantity,
                   SUM(pending_outbound_quantity) pending_outbound_quantity
            FROM inventory_source GROUP BY site,sku
        )
    """


def _product_price_table() -> str:
    # Uploaded prices are local, incremental configuration, not Lingxing snapshots.
    return _PRICE_TABLE


def _inventory_age_table() -> str:
    database = (settings.shop_source_database.strip() or "jmh_data_platform").replace("`", "``")
    return f"`{database}`.ods_goodcang_inventory_age_latest"


def _bounded_rows(cursor, label: str) -> list[dict[str, Any]]:
    rows = list(cursor.fetchall())
    if len(rows) > MAX_ROWS:
        raise ValueError(f"{label}超过{MAX_ROWS}行，请先优化查询范围；未截断数据")
    return rows


def _three_month_sales_window(reference_date: date | None = None) -> tuple[date, date]:
    """与补货2.0同口径：前三个完整自然月，固定三个月，不使用订单最新日。"""
    current = reference_date or datetime.now(timezone(timedelta(hours=8))).date()
    end = current.replace(day=1)
    start_index = end.year * 12 + end.month - 1 - 3
    return date(start_index // 12, start_index % 12 + 1, 1), end


def _recent_sales_window(reference_date: date | None = None) -> tuple[date, date]:
    """北京时间当天零点为开区间上界，取此前30个完整日期。"""
    end = reference_date or datetime.now(timezone(timedelta(hours=8))).date()
    return end - timedelta(days=30), end


def _source_rows(cursor, sales_window: tuple[date, date] | None = None,
                 recent_window: tuple[date, date] | None = None) -> list[dict[str, Any]]:
    # 库存作为行全集。近30天截至北京时间昨天，月均销量取前三个完整自然月。
    price_table = _product_price_table()
    age_table = _inventory_age_table()
    reference_date = datetime.now(timezone(timedelta(hours=8))).date()
    sales_window = sales_window or _three_month_sales_window(reference_date)
    recent_window = recent_window or _recent_sales_window(reference_date)
    # Match Python's second-segment strip, including tabs/newlines, not just SQL spaces.
    middle_sql = "REGEXP_REPLACE(SUBSTRING_INDEX(SUBSTRING_INDEX(inventory.sku,'-',2),'-',-1), '^[[:space:]]+|[[:space:]]+$', '')"
    query = f"""
        WITH {_weekly_inventory_ctes()},
        recent_sales AS (
            SELECT source.site_name,source.inventory_sku,
                   SUM(source.purchase_quantity) sales_qty_30d
            FROM dwd_ebay_sku_analysis_order source
            WHERE source.payment_time >= %s AND source.payment_time < %s
              AND COALESCE(source.shipping_status,'') NOT LIKE '%%已作废%%'
            GROUP BY source.site_name,source.inventory_sku
        ),
        complete_month_sales AS (
            -- 利润率沿用补货2.0的算式：三月利润/(三月销售额-已退款退款额)。
            -- 差别是本页按既有约定排除已作废订单，补货2.0不排除，因此同一SKU
            -- 两页的利润率可能有小幅差异，属业务选定口径，不是计算错误。
            SELECT source.site_name,source.inventory_sku,
                   SUM(source.purchase_quantity) sales_qty_3m,
                   SUM(source.order_profit_cny) three_month_profit_cny,
                   SUM(source.paid_amount_cny)
                     -SUM(CASE WHEN source.shipping_status LIKE '%%已退款%%'
                               THEN source.refund_amount_cny ELSE 0 END)
                     three_month_paid_amount_cny
            FROM dwd_ebay_sku_analysis_order source
            WHERE source.payment_time >= %s AND source.payment_time < %s
              AND COALESCE(source.shipping_status,'') NOT LIKE '%%已作废%%'
            GROUP BY source.site_name,source.inventory_sku
        ),
        product_names AS (
            SELECT TRIM(sku) sku,MAX(TRIM(product_name)) product_name
            FROM ods_lingxing_product_info_weekly
            WHERE sync_batch_id=(
                SELECT sync_batch_id FROM ods_lingxing_product_info_weekly
                ORDER BY pulled_at DESC,id DESC LIMIT 1
            )
              AND sku IS NOT NULL AND TRIM(sku)<>''
              AND product_name IS NOT NULL AND TRIM(product_name)<>''
            GROUP BY TRIM(sku)
            HAVING COUNT(DISTINCT TRIM(product_name))=1
        ),
        age_source AS (
            -- Weekly latest-only snapshot; never read/overwrite monthly clearance history.
            SELECT CASE WHEN UPPER(TRIM(warehouse_code)) IN ('DE','CZ','IT') THEN '德国'
                        WHEN UPPER(TRIM(warehouse_code))='UK' THEN '英国'
                        WHEN UPPER(TRIM(warehouse_code))='FR' THEN '法国'
                        WHEN UPPER(TRIM(warehouse_code)) LIKE 'US%%' THEN '美国' END site,
                   UPPER(TRIM(product_sku)) product_sku,
                   UPPER(CASE WHEN LOCATE('-',TRIM(product_sku))>0
                              THEN SUBSTRING(TRIM(product_sku),LOCATE('-',TRIM(product_sku))+1)
                              ELSE TRIM(product_sku) END) sku_suffix,
                   warehouse_age,
                   TRIM(JSON_UNQUOTE(JSON_EXTRACT(raw_json,'$.warehouse_age'))) raw_age
            FROM {age_table}
            WHERE product_sku IS NOT NULL AND TRIM(product_sku)<>''
        ),
        age_groups AS (
            -- Legacy ingestion defaulted unparseable ages to 0. Check the raw value
            -- too so missing/invalid ages cannot masquerade as real zero-day stock.
            SELECT site,sku_suffix,
                   MAX(CASE WHEN raw_age REGEXP '^[0-9]{{1,10}}$' AND warehouse_age>=0
                                  AND CAST(raw_age AS DECIMAL(30,0))=warehouse_age
                            THEN warehouse_age END) age_days,
                   COUNT(*) age_source_rows,COUNT(DISTINCT product_sku) age_source_products,
                   SUM(CASE WHEN raw_age REGEXP '^[0-9]{{1,10}}$' AND warehouse_age>=0
                                  AND CAST(raw_age AS DECIMAL(30,0))=warehouse_age
                            THEN 0 ELSE 1 END) age_invalid_rows
            FROM age_source
            WHERE site IS NOT NULL AND sku_suffix<>''
            GROUP BY site,sku_suffix
        ),
        product_prices AS (
            -- One price per textual middle code across sites; zero is a valid minimum.
            -- Aggregate before joining so repeated SKU/price pairs never multiply inventory.
            SELECT middle_code,MIN(unit_price) imported_unit_price,COUNT(*) price_source_rows
            FROM {price_table}
            WHERE middle_code IS NOT NULL AND middle_code<>''
            GROUP BY middle_code
        )
        SELECT inventory.site,inventory.sku,
               COALESCE(NULLIF(TRIM((
                   SELECT source.product_name_cn
                   FROM dwd_ebay_sku_analysis_order source
                   WHERE source.site_name = CONVERT(inventory.site USING utf8mb4) COLLATE utf8mb4_unicode_ci
                     AND source.inventory_sku = CONVERT(inventory.sku USING utf8mb4) COLLATE utf8mb4_unicode_ci
                   ORDER BY source.payment_time DESC,source.id DESC LIMIT 1
               )),''),products.product_name) product_name,
               (
                   SELECT DATE_FORMAT(MAX(source.payment_time),'%%Y-%%m-%%d')
                   FROM dwd_ebay_sku_analysis_order source
                   WHERE source.site_name = CONVERT(inventory.site USING utf8mb4) COLLATE utf8mb4_unicode_ci
                     AND source.inventory_sku = CONVERT(inventory.sku USING utf8mb4) COLLATE utf8mb4_unicode_ci
                     AND COALESCE(source.shipping_status,'') NOT LIKE '%%已作废%%'
               ) last_sold_at,
               CAST(inventory.chengdu_in_transit_quantity AS DECIMAL(30,6)) chengdu_in_transit_quantity,
               CAST(inventory.chengdu_sellable_quantity AS DECIMAL(30,6)) chengdu_sellable_quantity,
               CAST(inventory.overseas_in_transit_quantity AS DECIMAL(30,6)) overseas_in_transit_quantity,
               CAST(inventory.overseas_sellable_quantity AS DECIMAL(30,6)) overseas_sellable_quantity,
               CAST(inventory.pending_outbound_quantity AS DECIMAL(30,6)) pending_outbound_quantity,
               COALESCE(recent.sales_qty_30d,0) sales_qty_30d,
               COALESCE(monthly.sales_qty_3m,0) sales_qty_3m,
               COALESCE(monthly.three_month_profit_cny,0) three_month_profit_cny,
               COALESCE(monthly.three_month_paid_amount_cny,0) three_month_paid_amount_cny,
               prices.imported_unit_price,prices.price_source_rows,
               ages.age_days,ages.age_source_rows,ages.age_source_products,ages.age_invalid_rows
        FROM inventory_summary inventory
        LEFT JOIN recent_sales recent
          ON CONVERT(recent.site_name USING utf8mb4) COLLATE utf8mb4_unicode_ci
           = CONVERT(inventory.site USING utf8mb4) COLLATE utf8mb4_unicode_ci
         AND CONVERT(recent.inventory_sku USING utf8mb4) COLLATE utf8mb4_unicode_ci
           = CONVERT(inventory.sku USING utf8mb4) COLLATE utf8mb4_unicode_ci
        LEFT JOIN complete_month_sales monthly
          ON CONVERT(monthly.site_name USING utf8mb4) COLLATE utf8mb4_unicode_ci
           = CONVERT(inventory.site USING utf8mb4) COLLATE utf8mb4_unicode_ci
         AND CONVERT(monthly.inventory_sku USING utf8mb4) COLLATE utf8mb4_unicode_ci
           = CONVERT(inventory.sku USING utf8mb4) COLLATE utf8mb4_unicode_ci
        LEFT JOIN product_names products
          ON CONVERT(products.sku USING utf8mb4) COLLATE utf8mb4_unicode_ci
           = CONVERT(inventory.sku USING utf8mb4) COLLATE utf8mb4_unicode_ci
        LEFT JOIN product_prices prices
          ON LOCATE('-',inventory.sku)>0
         AND {middle_sql} REGEXP '^[0-9]+$'
         AND CONVERT(prices.middle_code USING utf8mb4) COLLATE utf8mb4_unicode_ci
           = CONVERT({middle_sql} USING utf8mb4) COLLATE utf8mb4_unicode_ci
        LEFT JOIN age_groups ages
          ON CONVERT(ages.site USING utf8mb4) COLLATE utf8mb4_unicode_ci
           = CONVERT(inventory.site USING utf8mb4) COLLATE utf8mb4_unicode_ci
         AND CONVERT(ages.sku_suffix USING utf8mb4) COLLATE utf8mb4_unicode_ci
           = CONVERT(UPPER(CASE WHEN LOCATE('-',TRIM(inventory.sku))>0
                                THEN SUBSTRING(TRIM(inventory.sku),LOCATE('-',TRIM(inventory.sku))+1)
                                ELSE TRIM(inventory.sku) END) USING utf8mb4) COLLATE utf8mb4_unicode_ci
        ORDER BY inventory.site,inventory.sku
        LIMIT {MAX_ROWS + 1}
    """
    try:
        cursor.execute(query, (*recent_window, *sales_window))
    except ProgrammingError as exc:
        if exc.args and exc.args[0] == 1146 and _PRICE_TABLE in str(exc):
            raise ValueError(_PRICE_MISSING) from exc
        raise
    return _bounded_rows(cursor, "库存明细")


def source_rows() -> list[dict[str, Any]]:
    with db_connection() as connection, connection.cursor() as cursor:
        return _source_rows(cursor)


def _monthly_sales_rows(cursor, month_end_exclusive: date | None = None) -> list[dict[str, Any]]:
    """历史各完整自然月的销量，供"历史最大月销"取最大值。

    只取当前库存里还存在的站点+SKU，行数不随历史订单总量增长；当月尚未结束
    不计入，作废订单不计，与本页其他销量口径一致。按站点+完整SKU返回明细，
    合并到中间码这一步交给服务层的 _product_key，避免在SQL里再写一套合并键。
    """
    end = month_end_exclusive or datetime.now(timezone(timedelta(hours=8))).date().replace(day=1)
    query = f"""
        WITH {_weekly_inventory_ctes()}
        SELECT inventory.site,inventory.sku,
               DATE_FORMAT(source.payment_time,'%%Y-%%m') stat_month,
               SUM(source.purchase_quantity) sales_qty
        FROM inventory_summary inventory
        JOIN dwd_ebay_sku_analysis_order source
          ON CONVERT(source.site_name USING utf8mb4) COLLATE utf8mb4_unicode_ci
           = CONVERT(inventory.site USING utf8mb4) COLLATE utf8mb4_unicode_ci
         AND CONVERT(source.inventory_sku USING utf8mb4) COLLATE utf8mb4_unicode_ci
           = CONVERT(inventory.sku USING utf8mb4) COLLATE utf8mb4_unicode_ci
        WHERE source.payment_time < %s
          AND COALESCE(source.shipping_status,'') NOT LIKE '%%已作废%%'
        GROUP BY inventory.site,inventory.sku,DATE_FORMAT(source.payment_time,'%%Y-%%m')
        LIMIT {MAX_ROWS + 1}
    """
    cursor.execute(query, (end,))
    return _bounded_rows(cursor, "库存明细历史月销量")


def monthly_sales_rows() -> list[dict[str, Any]]:
    with db_connection() as connection, connection.cursor() as cursor:
        return _monthly_sales_rows(cursor)


def _max_monthly_sales_rows(cursor) -> list[dict[str, Any]]:
    """历史最大月销高水位；表缺失时按空处理，页面退化为只用订单表现有月份。"""
    try:
        cursor.execute(
            f"SELECT site,product_key_type,product_key,max_monthly_sales,peak_month"
            f" FROM {_MAX_MONTHLY_SALES_TABLE} LIMIT {MAX_ROWS + 1}"
        )
    except ProgrammingError as exc:
        if exc.args and exc.args[0] == 1146 and _MAX_MONTHLY_SALES_TABLE in str(exc):
            return []
        raise
    return _bounded_rows(cursor, "历史最大月销高水位")


def max_monthly_sales_rows() -> list[dict[str, Any]]:
    with db_connection() as connection, connection.cursor() as cursor:
        return _max_monthly_sales_rows(cursor)


def raise_max_monthly_sales(rows: list[dict[str, Any]]) -> int:
    """只升不降地合并高水位：低于或等于已存值的候选不写，峰值月份随值一起变。

    没有候选行时不建连接。表缺失直接抛错，避免"重新计算"静默不落库。
    """
    if not rows:
        return 0
    if len(rows) > MAX_ROWS:
        raise ValueError(f"历史最大月销高水位超过{MAX_ROWS}行，未写入")
    query = f"""
        INSERT INTO {_MAX_MONTHLY_SALES_TABLE}
            (site,product_key_type,product_key,max_monthly_sales,peak_month,value_source)
        VALUES (%(site)s,%(product_key_type)s,%(product_key)s,%(max_monthly_sales)s,
                %(peak_month)s,'CALCULATED')
        ON DUPLICATE KEY UPDATE
            peak_month=IF(VALUES(max_monthly_sales)>max_monthly_sales,
                          VALUES(peak_month),peak_month),
            value_source=IF(VALUES(max_monthly_sales)>max_monthly_sales,
                            'CALCULATED',value_source),
            max_monthly_sales=GREATEST(max_monthly_sales,VALUES(max_monthly_sales))
    """
    with db_connection() as connection:
        try:
            connection.begin()
            with connection.cursor() as cursor:
                for offset in range(0, len(rows), _BATCH_SIZE):
                    cursor.executemany(query, rows[offset:offset + _BATCH_SIZE])
            connection.commit()
        except Exception as exc:
            connection.rollback()
            if isinstance(exc, ProgrammingError) and exc.args and exc.args[0] == 1146 \
                    and _MAX_MONTHLY_SALES_TABLE in str(exc):
                raise ValueError(_MAX_MONTHLY_SALES_MISSING) from exc
            raise
    return len(rows)


def _source_metadata(cursor) -> dict[str, Any]:
    cursor.execute(f"""
        WITH {_weekly_snapshot_cte()}
        SELECT (SELECT DATE(MAX(payment_time)) FROM dwd_ebay_sku_analysis_order
                WHERE COALESCE(shipping_status,'') NOT LIKE '%已作废%') sales_source_latest_date,
               MAX(sync_batch_id) inventory_batch_id,MAX(snapshot_date) inventory_snapshot_date,
               MAX(inventory_pulled_at) inventory_pulled_at
        FROM inventory_snapshot
    """)
    metadata = dict(cursor.fetchone())
    cursor.execute("""
        SELECT COUNT(*) rent_row_count,
               MIN(request_date_from) rent_date_from,
               MAX(request_date_to) rent_date_to,
               MAX(pulled_at) rent_pulled_at,
               DATE_FORMAT(MAX(pulled_at),'%Y-%m') rent_pull_month,
               MAX(sync_batch_id) rent_batch_id,
               COUNT(DISTINCT sync_batch_id) rent_batch_count
        FROM ods_goodcang_wh_inventory_storage_detail
    """)
    metadata.update(cursor.fetchone())
    if metadata["rent_batch_count"] > 1:
        raise ValueError("谷仓仓租明细含多个批次，无法确定统一拉取月份，请先完成全量覆盖同步")
    price_table = _product_price_table()
    try:
        cursor.execute(f"""
            SELECT MAX(updated_at) price_imported_at,COUNT(*) price_row_count,
                   COUNT(DISTINCT middle_code) price_middle_code_count
            FROM {price_table}
        """)
    except ProgrammingError as exc:
        if exc.args and exc.args[0] == 1146 and _PRICE_TABLE in str(exc):
            raise ValueError(_PRICE_MISSING) from exc
        raise
    metadata.update(cursor.fetchone())
    metadata["price_source"] = "uploaded_middle_code_min_v1"
    age_table = _inventory_age_table()
    cursor.execute(f"""
        SELECT MAX(snapshot_month) age_snapshot_month,MAX(pulled_at) age_pulled_at,
               COUNT(*) age_row_count,COUNT(DISTINCT sync_batch_id) age_batch_count
        FROM {age_table}
    """)
    metadata.update(cursor.fetchone())
    return metadata


def source_metadata() -> dict[str, Any]:
    with db_connection() as connection, connection.cursor() as cursor:
        return _source_metadata(cursor)


def _rent_rows(cursor) -> list[dict[str, Any]]:
    # ODS 已按近 30 天最新批次全量覆盖，无须再次用今日滑窗删除旧批次中的
    # 边缘日期。先保留仓库、完整 SKU、原币，站点及去前缀冲突由服务层判断。
    cursor.execute(f"""
        SELECT TRIM(warehouse_code) warehouse_code,TRIM(product_sku) product_sku,
               UPPER(TRIM(bill_currency_code)) bill_currency_code,
               SUM(warehouse_rent_amount) warehouse_rent_amount,
               SUM(CASE WHEN warehouse_rent_amount IS NULL THEN 1 ELSE 0 END) missing_amount_rows,
               COUNT(*) source_rows
        FROM ods_goodcang_wh_inventory_storage_detail
        GROUP BY TRIM(warehouse_code),TRIM(product_sku),UPPER(TRIM(bill_currency_code))
        ORDER BY warehouse_code,product_sku,bill_currency_code
        LIMIT {MAX_ROWS + 1}
    """)
    return _bounded_rows(cursor, "仓租分组")


def rent_rows() -> list[dict[str, Any]]:
    with db_connection() as connection, connection.cursor() as cursor:
        return _rent_rows(cursor)


def _rates(cursor, month: str | None) -> dict[str, Decimal]:
    if not month:
        return {}
    cursor.execute("""
        SELECT currency_code,my_rate FROM dim_lingxing_currency_month
        WHERE rate_month=%s
    """, (month,))
    result = {}
    for row in cursor.fetchall():
        code = str(row.get("currency_code") or "").strip().upper()
        if not code:
            continue
        try:
            rate = Decimal(str(row["my_rate"]))
        except (InvalidOperation, TypeError, ValueError) as exc:
            raise ValueError(f"{month}月{code}汇率无效，请先修正月度汇率") from exc
        if not rate.is_finite() or rate <= 0:
            raise ValueError(f"{month}月{code}汇率必须是正数，请先修正月度汇率")
        result[code] = rate
    return result


def rates(month: str | None) -> dict[str, Decimal]:
    """只读取指定月份的企业汇率，无旧月份、固定值或零值兜底。"""
    with db_connection() as connection, connection.cursor() as cursor:
        return _rates(cursor, month)


def read_snapshot() -> tuple[list[dict[str, Any]], dict[str, Any], list[dict[str, Any]],
                             dict[str, Decimal], list[dict[str, Any]], list[dict[str, Any]]]:
    """同一一致性读事务内取数，避免采购价/仓租/库龄替换期间混用新旧批次。"""
    reference_date = datetime.now(timezone(timedelta(hours=8))).date()
    sales_window = _three_month_sales_window(reference_date)
    recent_window = _recent_sales_window(reference_date)
    with db_connection() as connection:
        try:
            with connection.cursor() as cursor:
                cursor.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
                connection.begin()
                metadata = _source_metadata(cursor)
                metadata.update(monthly_sales_date_from=sales_window[0],
                                monthly_sales_date_to_exclusive=sales_window[1],
                                sales_date_from=recent_window[0],
                                sales_date_to_exclusive=recent_window[1],
                                sales_anchor_date=recent_window[1] - timedelta(days=1),
                                sales_policy="calendar_30d_exclude_today_void_v1")
                items = _source_rows(cursor, sales_window=sales_window, recent_window=recent_window)
                # 与库存明细同一事务内读取，否则历史月销可能对应另一批库存快照。
                monthly = _monthly_sales_rows(cursor, month_end_exclusive=sales_window[1])
                # 高水位与月度明细同事务读取；两者形状不同，分别返回不合并。
                max_floor = _max_monthly_sales_rows(cursor)
                rent = _rent_rows(cursor)
                fx = _rates(cursor, metadata.get("rent_pull_month"))
            connection.commit()
            return items, metadata, rent, fx, monthly, max_floor
        except Exception:
            connection.rollback()
            raise
