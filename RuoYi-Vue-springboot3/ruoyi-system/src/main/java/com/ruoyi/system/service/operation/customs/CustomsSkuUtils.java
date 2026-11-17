package com.ruoyi.system.service.operation.customs;

import java.util.Locale;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * 报关 SKU 规则。
 * <p>
 * 匹配键和报关编码是两个不同概念：匹配键使用括号前的仓库 SKU，
 * 报关文件才使用括号内的客户/原厂编码。
 */
public final class CustomsSkuUtils
{
    private static final Pattern DECLARATION_SKU_PATTERN =
            Pattern.compile("[\\(（]\\s*([^\\(（\\)）]+?)\\s*[\\)）]");

    private CustomsSkuUtils()
    {
    }

    /**
     * 生成库存匹配键。括号及其后的报关编码不参与匹配，再沿用原有去品牌前缀规则。
     */
    public static String normalizeMatchKey(String rawSku)
    {
        if (rawSku == null || rawSku.isEmpty()) return "";
        String sku = rawSku.trim();
        int parenthesis = firstParenthesis(sku);
        if (parenthesis > 0)
        {
            sku = sku.substring(0, parenthesis).trim();
        }
        int firstDash = sku.indexOf('-');
        if (firstDash < 0) return sku;
        String prefix = sku.substring(0, firstDash);
        // PC 前缀原样保留，仅忽略括号后的报关编码。
        if (prefix.toUpperCase(Locale.ROOT).contains("PC")) return sku;
        String[] parts = sku.split("-");
        for (int i = 0; i < parts.length; i++)
        {
            if (parts[i].matches(".*\\d+.*"))
            {
                String first = parts[i].replaceAll("^[^0-9]+", "");
                if (first.isEmpty()) continue;
                StringBuilder result = new StringBuilder(first);
                for (int j = i + 1; j < parts.length; j++) result.append("-").append(parts[j]);
                return result.toString();
            }
        }
        return sku;
    }

    /**
     * 生成报关文件中的 SKU。有完整括号时取括号内容，否则保留原 SKU。
     */
    public static String declarationSku(String rawSku)
    {
        if (rawSku == null) return "";
        String sku = rawSku.trim();
        Matcher matcher = DECLARATION_SKU_PATTERN.matcher(sku);
        if (matcher.find())
        {
            String declarationSku = matcher.group(1).trim();
            if (!declarationSku.isEmpty()) return declarationSku;
        }
        return sku;
    }

    private static int firstParenthesis(String value)
    {
        int halfWidth = value.indexOf('(');
        int fullWidth = value.indexOf('（');
        if (halfWidth < 0) return fullWidth;
        if (fullWidth < 0) return halfWidth;
        return Math.min(halfWidth, fullWidth);
    }
}
