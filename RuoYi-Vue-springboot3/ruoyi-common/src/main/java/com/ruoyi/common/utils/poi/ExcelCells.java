package com.ruoyi.common.utils.poi;

import java.math.BigDecimal;
import java.security.MessageDigest;
import java.util.HexFormat;
import org.apache.poi.ss.usermodel.Cell;
import org.apache.poi.ss.usermodel.CellType;
import org.apache.poi.ss.usermodel.DataFormatter;
import org.apache.poi.ss.usermodel.FormulaEvaluator;

/**
 * 业务 Excel 导入共用的单元格取值工具。
 *
 * 两种取值方式语义不同：
 * formatted 按单元格显示格式取文本（与用户在 Excel 中看到的一致，公式会被计算）；
 * plain 取原始值，数字去掉多余小数位，公式只读缓存结果、不读公式本身。
 */
public final class ExcelCells
{
    private ExcelCells()
    {
    }

    /** 按显示格式取文本；空单元格返回空串。 */
    public static String formatted(Cell cell, DataFormatter formatter, FormulaEvaluator evaluator)
    {
        if (cell == null) return "";
        String text = formatter.formatCellValue(cell, evaluator);
        return text == null ? "" : text.trim();
    }

    /**
     * 取原始值文本：数字 1.50 → "1.5"，布尔 → "true"/"false"。
     * 公式单元格只读缓存结果；缓存为错误值或无法读取时返回空串，而不是返回公式文本。
     */
    public static String plain(Cell cell)
    {
        if (cell == null) return "";
        try
        {
            CellType type = cell.getCellType();
            if (type == CellType.FORMULA)
            {
                type = cell.getCachedFormulaResultType();
                if (type != CellType.STRING && type != CellType.NUMERIC && type != CellType.BOOLEAN)
                    return "";
            }
            if (type == CellType.NUMERIC)
                return BigDecimal.valueOf(cell.getNumericCellValue()).stripTrailingZeros().toPlainString();
            if (type == CellType.BOOLEAN) return Boolean.toString(cell.getBooleanCellValue());
            if (type == CellType.STRING) return trim(cell.getStringCellValue());
            return trim(cell.toString());
        }
        catch (RuntimeException e)
        {
            return "";
        }
    }

    /** 上传文件内容摘要，用于导入批次去重。 */
    public static String sha256Hex(byte[] bytes)
    {
        try
        {
            return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(bytes));
        }
        catch (Exception e)
        {
            throw new IllegalStateException("计算文件摘要失败", e);
        }
    }

    private static String trim(String value)
    {
        return value == null ? "" : value.trim();
    }
}
