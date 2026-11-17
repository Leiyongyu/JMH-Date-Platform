package com.ruoyi.system.service.operation.external.lingxing;

import static org.junit.jupiter.api.Assertions.*;
import java.math.BigDecimal;
import java.util.Map;
import org.junit.jupiter.api.Test;

class AmzOrderProfitAmountParserTest
{
    @Test
    void preservesDecimalAmountWithoutPercentMultiplication()
    {
        assertEquals(new BigDecimal("12345.678901"),
                AmzOrderProfitAmountParser.grossProfitCny(Map.of("currency_code", "CNY", "gross_profit", "12345.678901")));
        assertEquals(new BigDecimal("-19.123456"),
                AmzOrderProfitAmountParser.grossProfitCny(Map.of("currency_code", "CNY", "gross_profit", "-19.123456")));
        assertEquals(BigDecimal.ZERO,
                AmzOrderProfitAmountParser.grossProfitCny(Map.of("currency_code", "CNY", "gross_profit", "0")));
    }

    @Test
    void absentValueIsNotZero()
    {
        assertNull(AmzOrderProfitAmountParser.grossProfitCny(Map.of("currency_code", "CNY")));
        assertNull(AmzOrderProfitAmountParser.grossProfitCny(Map.of("currency_code", "CNY", "gross_profit", " ")));
    }

    @Test
    void rejectsWrongOrUnknownCurrencyAndInvalidAmounts()
    {
        assertThrows(IllegalStateException.class, () -> AmzOrderProfitAmountParser.grossProfitCny(
                Map.of("currency_code", "USD", "gross_profit", "15")));
        assertThrows(IllegalStateException.class, () -> AmzOrderProfitAmountParser.grossProfitCny(
                Map.of("gross_profit", "15")));
        assertThrows(IllegalStateException.class, () -> AmzOrderProfitAmountParser.grossProfitCny(
                Map.of("currency_code", "CNY", "gross_profit", "NaN")));
    }
}
