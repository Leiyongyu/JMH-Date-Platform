package com.ruoyi.system.service.operation.compute;

import java.math.BigDecimal;
import java.math.RoundingMode;

/**
 * 库存计算工具类：SKU提取、站点映射、安全除法、产品等级计算。
 * 从旧项目 InventoryUtils 移植。
 */
public final class InventoryUtils
{
    private InventoryUtils() {}

    /**
     * 安全除法 a / b，b 为 0 返回 0
     */
    public static BigDecimal safeDivide(int a, int b)
    {
        if (b == 0) return BigDecimal.ZERO;
        return BigDecimal.valueOf(a).divide(BigDecimal.valueOf(b), 4, RoundingMode.HALF_UP);
    }

    /**
     * 仓库名称 → 站点中文标签
     */
    public static String whNameToSite(String name)
    {
        if (name == null) return "";
        String n = name.trim();
        // 美国仓
        if (n.contains("美国") || n.contains("US") || n.contains("美西") || n.contains("美东")
                || n.contains("洛杉矶") || n.contains("新泽西") || n.contains("达拉斯")
                || n.contains("芝加哥") || n.contains("亚特兰大"))
            return "美国";
        // 英国仓
        if (n.contains("英国") || n.contains("UK") || n.contains("伦敦") || n.contains("曼彻斯特"))
            return "英国";
        // 德国仓
        if (n.contains("德国") || n.contains("DE") || n.contains("法兰克福") || n.contains("柏林"))
            return "德国";
        return "";
    }

    /**
     * 货币代码 → 站点标签
     */
    public static String currencyToSite(String currency)
    {
        if (currency == null) return "";
        switch (currency.toUpperCase())
        {
            case "USD": return "美国";
            case "GBP": return "英国";
            case "EUR": return "德国";
            default: return "";
        }
    }

    /**
     * 提取中间码: 取 SKU 去掉品牌前缀后的部分。
     * 例: "BMW-30087-A" → "BMW-30087"
     *     "2PC-BMW-30087" → "2PC-BMW-30087" (保留前三段)
     *     "4PC-DAS-10254" → "4PC-DAS-10254" (PC前缀保留前三段)
     */
    public static String extractMiddleCode(String sku)
    {
        if (sku == null || sku.isEmpty()) return "";
        String s = sku.trim();
        String[] parts = s.split("-");
        // 所有数字+PC 前缀 (2PC, 4PC, PC 等) 保留前三段
        if (parts.length >= 3 && parts[0].matches("\\d*PC"))
        {
            return parts[0] + "-" + parts[1] + "-" + parts[2];
        }
        if (parts.length >= 2)
        {
            return parts[0] + "-" + parts[1];
        }
        return s;
    }

    /**
     * 补货页用：提取中间码（先去掉PC前缀再取中间码）
     * 例: "2PC-BMW-30087" → 去PC → "BMW-30087" → 中间码 "BMW-30087"
     */
    public static String extractMiddleCodeForInventory(String sku)
    {
        String s = stripPcPrefix(sku);
        return extractMiddleCode(s);
    }

    /**
     * 提取基础 SKU（取前两段，2PC-xxx-yyy 保留前三段）
     */
    public static String extractBaseSku(String sku)
    {
        return extractMiddleCode(sku);
    }

    /**
     * 提取库存分组 key: 去掉 PC 前缀后提取 baseSku
     * 使 2PC-BMW-30087 和 BMW-30087 归入同一商品分组
     */
    public static String extractInventoryGroupKey(String sku)
    {
        String s = stripPcPrefix(sku);
        return extractBaseSku(s);
    }

    /**
     * 去掉 PC 前缀 (2PC-, 4PC-, PC- 等，匹配 \d*PC- 模式)
     */
    public static String stripPcPrefix(String sku)
    {
        if (sku == null || sku.isEmpty()) return "";
        String s = sku.trim();
        // 匹配 数字+PC- 或 纯PC- 前缀: "2PC-DAS-10254" → "DAS-10254", "PC-xxx" → "xxx"
        if (s.matches("^\\d*PC-.*"))
        {
            int idx = s.indexOf('-');
            if (idx > 0 && idx < s.length() - 1)
                return s.substring(idx + 1);
        }
        return s;
    }

    /**
     * 提取品牌前缀（SKU 第一个 '-' 前的部分）
     */
    public static String extractBrandPrefix(String sku)
    {
        if (sku == null || sku.isEmpty()) return "";
        String s = stripPcPrefix(sku);
        int i = s.indexOf('-');
        return i > 0 ? s.substring(0, i) : s;
    }

    /**
     * SKU 产品等级：A~E，基于近30天销量和利润率
     */
    public static String calcProductLevel(int sales, double profitRate)
    {
        if (sales >= 100 && profitRate >= 0.30) return "A";
        if (sales >= 50 && profitRate >= 0.20) return "B";
        if (sales >= 20 && profitRate >= 0.10) return "C";
        if (sales >= 5) return "D";
        return "E";
    }

    /**
     * 根据品牌前缀匹配负责人
     */
    public static String matchOwner(String sku, java.util.Map<String, String> ownerByBrand)
    {
        if (sku == null || sku.isEmpty() || ownerByBrand == null || ownerByBrand.isEmpty()) return "";
        String brand = extractBrandPrefix(sku).toUpperCase();
        String owner = ownerByBrand.get(brand);
        if (owner != null && !owner.isEmpty()) return owner;
        // 尝试用完整 SKU 前缀匹配（包含前两段）
        String base = extractBaseSku(sku).toUpperCase();
        return ownerByBrand.getOrDefault(base, "");
    }
}
