package com.ruoyi.system.service.operation.external.lingxing;

import java.math.BigDecimal;
import java.util.Map;

/** OrderProfit毛利润直接取领星人民币原值，不通过利润率反推，不经double转换。 */
final class AmzOrderProfitAmountParser
{
    private AmzOrderProfitAmountParser() {}

    static BigDecimal grossProfitCny(Map<String, Object> item)
    {
        Object value = item.get("gross_profit");
        if (value == null || value.toString().isBlank()) return null;
        String currency = String.valueOf(item.getOrDefault("currency_code", "")).trim();
        if (!"CNY".equalsIgnoreCase(currency))
            throw new IllegalStateException("领星OrderProfit毛利润币种不是CNY或缺失，拒绝按人民币存储");
        try
        {
            return new BigDecimal(value.toString().trim());
        }
        catch (NumberFormatException e)
        {
            throw new IllegalStateException("领星OrderProfit的gross_profit不是有效金额", e);
        }
    }
}
