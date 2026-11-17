"""Column ↔ LingXing field maps for the AMZ profit report source tables.

Settlement figures come from 利润统计 (seller/msku list, camelCase); order
figures from 订单利润 OrderProfit (snake_case). Both are pulled in USD.
"""
from __future__ import annotations

# (table column, API field, kind) — kind "qty" is summed as an integer.
SETTLEMENT_METRICS: tuple[tuple[str, str, str], ...] = (
    ("total_sales_quantity", "totalSalesQuantity", "qty"),
    ("refunds_quantity", "refundsQuantity", "qty"),
    ("fba_returns_quantity", "fbaReturnsQuantity", "qty"),
    ("total_ads_sales_quantity", "totalAdsSalesQuantity", "qty"),
    ("total_sales_amount", "totalSalesAmount", "amount"),
    ("total_sales_amount_with_tax", "totalSalesAmountWithTax", "amount"),
    ("shipping_credits", "shippingCredits", "amount"),
    ("promotional_rebates", "promotionalRebates", "amount"),
    ("fba_inventory_credit", "fbaInventoryCredit", "amount"),
    ("cash_on_delivery", "cashOnDelivery", "amount"),
    ("other_in_amount", "otherInAmount", "amount"),
    ("total_sales_refunds", "totalSalesRefunds", "amount"),
    ("total_fee_refunds", "totalFeeRefunds", "amount"),
    ("platform_fee", "platformFee", "amount"),
    ("fba_delivery_fee", "fbaDeliveryFee", "amount"),
    ("other_transaction_fees", "otherTransactionFees", "amount"),
    ("total_ads_cost", "totalAdsCost", "amount"),
    ("total_ads_sales", "totalAdsSales", "amount"),
    ("promotion_fee", "promotionFee", "amount"),
    ("total_storage_fee", "totalStorageFee", "amount"),
    ("fba_inbound_convenience_fee", "sharedFbaInboundConvenienceFee", "amount"),
    # LingXing spells this field "Integerernational".
    ("fba_international_inbound_fee", "sharedFbaIntegerernationalInboundFee", "amount"),
    ("adjustments", "adjustments", "amount"),
    ("total_platform_other_fee", "totalPlatformOtherFee", "amount"),
    ("total_sales_tax", "totalSalesTax", "amount"),
    ("sales_tax_refund", "salesTaxRefund", "amount"),
    ("sales_tax_withheld", "salesTaxWithheld", "amount"),
    ("refund_tax_withheld", "refundTaxWithheld", "amount"),
    ("custom_order_fee", "customOrderFee", "amount"),
    ("cg_price", "cgPrice", "amount"),
    ("cg_transport_costs", "cgTransportCosts", "amount"),
    ("cg_other_costs_total", "cgOtherCostsTotal", "amount"),
    ("total_cost", "totalCost", "amount"),
    ("gross_profit", "grossProfit", "amount"),
    ("gross_profit_with_tax", "grossProfitWithTax", "amount"),
)

ORDER_METRICS: tuple[tuple[str, str, str], ...] = (
    ("volume", "volume", "qty"),
    ("refund_quantity", "refund_quantity", "qty"),
    ("return_quantity", "return_quantity", "qty"),
    ("ad_volume", "ad_volume", "qty"),
    ("amount", "amount", "amount"),
    ("tax_amount", "tax_amount", "amount"),
    ("net_amount", "net_amount", "amount"),
    ("gross_profit", "gross_profit", "amount"),
    ("refund_amount", "refund_amount", "amount"),
    ("shipping_cost", "shipping_cost", "amount"),
    ("promotion_discount", "promotion_discount", "amount"),
    ("selling_fee", "selling_fee", "amount"),
    ("fulfillment_fee", "fulfillment_fee", "amount"),
    ("other_order_fee", "other_order_fee", "amount"),
    ("spend", "spend", "amount"),
    ("ad_sales_amount", "ad_sales_amount", "amount"),
    ("total_stock_fee", "total_stock_fee", "amount"),
    ("promotion_fee", "promotion_fee", "amount"),
    ("purchase_costs", "purchase_costs", "amount"),
    ("logistics_costs", "logistics_costs", "amount"),
    ("other_costs", "other_costs", "amount"),
    ("total_costs", "total_costs", "amount"),
)

SETTLEMENT_COLUMNS = tuple(column for column, _field, _kind in SETTLEMENT_METRICS)
ORDER_COLUMNS = tuple(column for column, _field, _kind in ORDER_METRICS)
