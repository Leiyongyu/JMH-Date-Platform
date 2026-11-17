package com.ruoyi.common.utils;

import java.math.BigDecimal;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

/**
 * 外部接口返回值的数值解析。
 *
 * 领星等接口的数量字段可能以 "12"、"12.0"、"1,234" 形式返回；直接 Integer.parseInt
 * 会把后两种静默解析成默认值 0，导致库存、件数等被算错且无人察觉。这里统一按
 * BigDecimal 解析，真正无法解析时记 WARN 日志再返回调用方给定的默认值。
 */
public final class NumberValues
{
    private static final Logger LOG = LoggerFactory.getLogger(NumberValues.class);

    private NumberValues()
    {
    }

    public static Integer toInteger(Object value, Integer fallback, String field)
    {
        if (value == null) return fallback;
        if (value instanceof Number number) return number.intValue();
        String text = value.toString().trim().replace(",", "");
        if (text.isEmpty()) return fallback;
        try
        {
            return new BigDecimal(text).intValue();
        }
        catch (NumberFormatException e)
        {
            LOG.warn("数值字段解析失败，按默认值 {} 处理 field={} value={}", fallback, field, value);
            return fallback;
        }
    }
}
