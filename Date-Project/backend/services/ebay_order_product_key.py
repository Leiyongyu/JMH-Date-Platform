"""eBay订单产品键：站点独立，过滤AMZ/数字PC前缀，归并二手后缀。

只在读取汇总时使用，不覆盖订单原始inventory_sku；其他后缀保持完整。
"""
import re

EXCLUDED_PREFIX = re.compile(r"^(?:AMZ|[0-9]+PC)", re.IGNORECASE)
USED_SUFFIX = re.compile(r"-(?:YXR|RXY)$", re.IGNORECASE)


def product_sku(value: str | None) -> str:
    """返回归并后的完整产品SKU；仅剥离末尾一个明确的二手标记。"""
    return USED_SUFFIX.sub("", str(value or "").strip().upper())


def is_used_sku(value: str | None) -> bool:
    return bool(USED_SUFFIX.search(str(value or "").strip()))


def product_key(site: str | None, sku: str | None) -> tuple[str, str] | None:
    raw = str(sku or "").strip().upper()
    site = str(site or "").strip()
    normalized = product_sku(raw)
    if not site or not normalized or EXCLUDED_PREFIX.match(raw):
        return None
    return site, normalized


def product_sku_sql(column: str) -> str:
    """column只能由代码传入SQL列名，不能传入用户输入。"""
    raw = f"UPPER(TRIM({column}))"
    return f"CASE WHEN RIGHT({raw},4) IN ('-YXR','-RXY') THEN LEFT({raw},CHAR_LENGTH({raw})-4) ELSE {raw} END"


def product_orders_cte() -> str:
    """所有订单指标先共用此键再聚合；保留原始SKU和二手标识供后续使用。"""
    sku = product_sku_sql("orders.inventory_sku")
    return f"""product_orders AS (
        SELECT orders.id,TRIM(orders.site_name) site_name,
               {sku} inventory_sku,
               orders.inventory_sku original_inventory_sku,
               RIGHT(UPPER(TRIM(orders.inventory_sku)),4) IN ('-YXR','-RXY') is_used_product,
               orders.payment_time,orders.platform_order_no,orders.product_name_cn,
               orders.purchase_quantity,orders.paid_amount_cny,orders.order_profit_cny,
               orders.refund_quantity,orders.refund_amount_cny,orders.shipping_status
        FROM dwd_ebay_sku_analysis_order orders
        WHERE UPPER(TRIM(orders.inventory_sku)) NOT REGEXP '^(AMZ|[0-9]+PC)'
          AND ({sku}) <> ''
          AND orders.site_name IS NOT NULL AND TRIM(orders.site_name) <> ''
    )"""


def latest_product_source_ctes() -> str:
    """规范化键无法直接使用原SKU索引，按产品排序一次，避免逐产品扫描历史订单。"""
    return """latest_ranked AS (
        SELECT site_name,inventory_sku,product_name_cn,
               ROW_NUMBER() OVER (
                   PARTITION BY site_name,inventory_sku
                   ORDER BY payment_time DESC,id DESC
               ) source_rank
        FROM product_orders
    ), latest_source AS (
        SELECT period_key.site_name,period_key.inventory_sku,source.product_name_cn
        FROM period_keys period_key
        LEFT JOIN latest_ranked source
          ON source.site_name=period_key.site_name
         AND source.inventory_sku=period_key.inventory_sku
         AND source.source_rank=1
    )"""
