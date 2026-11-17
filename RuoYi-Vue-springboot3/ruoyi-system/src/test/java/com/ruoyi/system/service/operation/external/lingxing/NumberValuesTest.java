package com.ruoyi.system.service.operation.external.lingxing;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;

import com.ruoyi.common.utils.NumberValues;
import java.math.BigDecimal;
import org.junit.jupiter.api.Test;

class NumberValuesTest
{
    @Test
    void parsesDecimalAndThousandsFormattedQuantities()
    {
        // 这两种格式过去会被 Integer.parseInt 静默解析成 0。
        assertEquals(12, NumberValues.toInteger("12.0", 0, "quantity"));
        assertEquals(1234, NumberValues.toInteger("1,234", 0, "quantity"));
        assertEquals(7, NumberValues.toInteger(new BigDecimal("7.00"), 0, "quantity"));
        assertEquals(5, NumberValues.toInteger(" 5 ", 0, "quantity"));
    }

    @Test
    void blankAndInvalidFallBack()
    {
        assertNull(NumberValues.toInteger(null, null, "quantity"));
        assertEquals(0, NumberValues.toInteger("", 0, "quantity"));
        assertEquals(0, NumberValues.toInteger("N/A", 0, "quantity"));
        assertNull(NumberValues.toInteger("abc", null, "quantity"));
    }
}
