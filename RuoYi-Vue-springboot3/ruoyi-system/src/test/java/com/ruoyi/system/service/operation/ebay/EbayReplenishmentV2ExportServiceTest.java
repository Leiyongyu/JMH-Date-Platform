package com.ruoyi.system.service.operation.ebay;

import com.ruoyi.common.exception.ServiceException;
import java.io.ByteArrayInputStream;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import org.apache.poi.ss.usermodel.CellType;
import org.apache.poi.ss.usermodel.DataFormatter;
import org.apache.poi.xssf.usermodel.XSSFWorkbook;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class EbayReplenishmentV2ExportServiceTest
{
    private Map<String, Object> payload()
    {
        Map<String, Object> item = new LinkedHashMap<>();
        item.put("site", "德国");
        item.put("sku", "00001234567890123456");
        item.put("product_name", "=HYPERLINK(\"https://example.invalid\")");
        item.put("sales_qty_7d", "0");
        item.put("profit_rate", "0.125");
        item.put("sales_type", "BRUSH");
        item.put("warehouse_rent_amount_cny", "12.3456");
        item.put("chengdu_qc_outbound_days", 0);
        item.put("safety_stock_quantity", 12);
        item.put("safety_stock_quantity_2", 31);
        item.put("monthly_metrics", List.of(Map.of("month", "2026-08",
                "sales_qty", "10", "quality_return_qty", "0", "quality_return_rate", "0")));
        return new LinkedHashMap<>(Map.of("items", List.of(item), "pagination", Map.of("total", 1),
                "latest_complete_month", "2026-08", "months", List.of("2026-08", "2026-07", "2026-06")));
    }

    @Test
    void writes34ColumnsWithNumbersBlanksAndSeparateMonthlyDetails() throws Exception
    {
        byte[] bytes = new EbayReplenishmentV2ExportService().buildExcel(payload(), Map.of());
        try (var workbook = new XSSFWorkbook(new ByteArrayInputStream(bytes)))
        {
            assertEquals(3, workbook.getNumberOfSheets());
            var sheet = workbook.getSheet("补货2.0");
            assertEquals(34, sheet.getRow(0).getLastCellNum());
            assertEquals(1, sheet.getLastRowNum());
            assertEquals("建议补货量2", sheet.getRow(0).getCell(33).getStringCellValue());
            assertEquals("00001234567890123456", sheet.getRow(1).getCell(1).getStringCellValue());
            assertEquals(CellType.STRING, sheet.getRow(1).getCell(2).getCellType());
            assertEquals(CellType.NUMERIC, sheet.getRow(1).getCell(3).getCellType());
            var formatter = new DataFormatter(Locale.US);
            assertEquals("0", formatter.formatCellValue(sheet.getRow(1).getCell(3)));
            assertEquals("12.50%", formatter.formatCellValue(sheet.getRow(1).getCell(8)));
            assertEquals("--", sheet.getRow(1).getCell(15).getStringCellValue());
            assertEquals("刷单", sheet.getRow(1).getCell(22).getStringCellValue());
            assertEquals(12.3456, sheet.getRow(1).getCell(12).getNumericCellValue(), 0.000001);
            assertEquals(0, sheet.getRow(1).getCell(28).getNumericCellValue());
            assertEquals(12, sheet.getRow(1).getCell(30).getNumericCellValue());
            assertEquals(31, sheet.getRow(1).getCell(32).getNumericCellValue());
            var monthly = workbook.getSheet("三个月明细");
            assertEquals("2026-08", monthly.getRow(1).getCell(2).getStringCellValue());
            assertEquals("--", monthly.getRow(1).getCell(6).getStringCellValue());
            assertEquals("--", monthly.getRow(1).getCell(7).getStringCellValue());
        }
    }

    @Test
    void rejectsIncompletePageInsteadOfSilentlyExportingIt()
    {
        var data = payload();
        data.put("pagination", Map.of("total", 510));
        var error = assertThrows(ServiceException.class,
                () -> new EbayReplenishmentV2ExportService().buildExcel(data, Map.of()));
        assertTrue(error.getMessage().contains("记录数与总数不一致"));
    }

    @Test
    void rejectsEmptyDataBeforeWritingAnExcel()
    {
        var data = payload();
        data.put("items", List.of());
        assertThrows(ServiceException.class,
                () -> new EbayReplenishmentV2ExportService().buildExcel(data, Map.of()));
    }
}
