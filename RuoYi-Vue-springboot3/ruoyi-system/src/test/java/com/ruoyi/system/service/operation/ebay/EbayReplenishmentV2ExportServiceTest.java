package com.ruoyi.system.service.operation.ebay;

import com.ruoyi.common.exception.ServiceException;
import com.ruoyi.system.mapper.operation.ebay.EbayReplenishmentV2LeadTimeMapper;
import java.io.ByteArrayInputStream;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Set;
import java.util.HashSet;
import java.util.Arrays;
import java.util.stream.Collectors;
import org.apache.poi.ss.usermodel.CellType;
import org.apache.poi.ss.usermodel.DataFormatter;
import org.apache.poi.xssf.usermodel.XSSFWorkbook;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

class EbayReplenishmentV2ExportServiceTest
{
    private static final Set<String> ALL_PERMISSIONS = Set.of("*:*:*");

    private static Set<String> columns(String... keys)
    {
        return Arrays.stream(keys).map(key -> EbayReplenishmentV2ExportService.COLUMN_PERMISSION_PREFIX + key)
                .collect(Collectors.toSet());
    }

    private static List<String> headers(org.apache.poi.ss.usermodel.Sheet sheet)
    {
        return java.util.stream.IntStream.range(0, sheet.getRow(0).getLastCellNum())
                .mapToObj(index -> sheet.getRow(0).getCell(index).getStringCellValue()).toList();
    }

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
        item.put("operations_note", "运营的完整备注超过五字");
        item.put("development_note", "开发完整备注");
        item.put("operations_confirmed", true);
        item.put("monthly_metrics", List.of(Map.of("month", "2026-08",
                "sales_qty", "10", "quality_return_qty", "0", "quality_return_rate", "0")));
        return new LinkedHashMap<>(Map.of("items", List.of(item), "pagination", Map.of("total", 1),
                "latest_complete_month", "2026-08", "months", List.of("2026-08", "2026-07", "2026-06")));
    }

    @Test
    void writes37ColumnsWithNumbersBlanksAndSeparateMonthlyDetails() throws Exception
    {
        byte[] bytes = new EbayReplenishmentV2ExportService().buildExcel(payload(), Map.of(), ALL_PERMISSIONS);
        try (var workbook = new XSSFWorkbook(new ByteArrayInputStream(bytes)))
        {
            assertEquals(3, workbook.getNumberOfSheets());
            var sheet = workbook.getSheet("补货2.0");
            assertEquals(37, sheet.getRow(0).getLastCellNum());
            assertEquals(1, sheet.getLastRowNum());
            assertEquals("建议补货量2", sheet.getRow(0).getCell(33).getStringCellValue());
            assertEquals("运营", sheet.getRow(0).getCell(34).getStringCellValue());
            assertEquals("开发", sheet.getRow(0).getCell(35).getStringCellValue());
            assertEquals("运营的完整备注超过五字", sheet.getRow(1).getCell(34).getStringCellValue());
            assertEquals("已确认", sheet.getRow(1).getCell(36).getStringCellValue());
            assertEquals("00001234567890123456", sheet.getRow(1).getCell(1).getStringCellValue());
            assertEquals(CellType.STRING, sheet.getRow(1).getCell(2).getCellType());
            assertEquals(CellType.NUMERIC, sheet.getRow(1).getCell(3).getCellType());
            var formatter = new DataFormatter(Locale.US);
            assertEquals("开发完整备注", formatter.formatCellValue(sheet.getRow(1).getCell(35)));
            assertEquals("0", formatter.formatCellValue(sheet.getRow(1).getCell(3)));
            assertEquals("12.50%", formatter.formatCellValue(sheet.getRow(1).getCell(8)));
            assertEquals("--", sheet.getRow(1).getCell(15).getStringCellValue());
            assertEquals("刷单", sheet.getRow(1).getCell(22).getStringCellValue());
            assertEquals(12.3456, sheet.getRow(1).getCell(12).getNumericCellValue(), 0.000001);
            assertEquals(0, sheet.getRow(1).getCell(28).getNumericCellValue());
            assertEquals(12, sheet.getRow(1).getCell(30).getNumericCellValue());
            assertEquals(31, sheet.getRow(1).getCell(32).getNumericCellValue());
            var monthly = workbook.getSheet("90天分段明细");
            assertEquals("2026-08", monthly.getRow(1).getCell(2).getStringCellValue());
            assertEquals("--", monthly.getRow(1).getCell(6).getStringCellValue());
            assertEquals("--", monthly.getRow(1).getCell(7).getStringCellValue());
        }
    }

    @Test
    void exportsEffectiveSiteLeadTimeFromTheSameEnrichmentAsTheList() throws Exception
    {
        var mapper = mock(EbayReplenishmentV2LeadTimeMapper.class);
        when(mapper.selectByKeys(anyList())).thenReturn(List.of());
        var data = payload();
        new EbayReplenishmentV2LeadTimeService(mapper).enrich(data);
        byte[] bytes = new EbayReplenishmentV2ExportService().buildExcel(data, Map.of(), ALL_PERMISSIONS);
        try (var workbook = new XSSFWorkbook(new ByteArrayInputStream(bytes)))
        {
            assertEquals(67, workbook.getSheet("补货2.0").getRow(1).getCell(29).getNumericCellValue());
        }
    }

    @Test
    void rejectsIncompletePageInsteadOfSilentlyExportingIt()
    {
        var data = payload();
        data.put("pagination", Map.of("total", 510));
        var error = assertThrows(ServiceException.class,
                () -> new EbayReplenishmentV2ExportService().buildExcel(data, Map.of(), ALL_PERMISSIONS));
        assertTrue(error.getMessage().contains("记录数与总数不一致"));
    }

    @Test
    void rejectsEmptyDataBeforeWritingAnExcel()
    {
        var data = payload();
        data.put("items", List.of());
        assertThrows(ServiceException.class,
                () -> new EbayReplenishmentV2ExportService().buildExcel(data, Map.of(), ALL_PERMISSIONS));
    }

    @Test
    void restrictsBothSheetsAndNeverSerializesDeniedValues() throws Exception
    {
        var data = payload();
        var item = (Map<String, Object>) ((List<?>) data.get("items")).get(0);
        item.put("gross_profit_amount", "DENIED_MAIN_PROFIT");
        item.put("monthly_metrics", List.of(Map.of("month", "DENIED_DATE", "sales_qty", 10,
                "gross_profit_amount", "DENIED_DETAIL_PROFIT", "quality_return_qty", "DENIED_QUALITY")));
        byte[] bytes = new EbayReplenishmentV2ExportService().buildExcel(data, Map.of(),
                columns("site", "sku", "sales_qty", "operations_note"));
        try (var workbook = new XSSFWorkbook(new ByteArrayInputStream(bytes)))
        {
            assertEquals(List.of("站点", "SKU", "销量", "运营"), headers(workbook.getSheet("补货2.0")));
            assertEquals(List.of("站点", "SKU", "销量"), headers(workbook.getSheet("90天分段明细")));
            assertEquals("运营的完整备注超过五字", workbook.getSheet("补货2.0").getRow(1).getCell(3).getStringCellValue());
            for (var sheet : workbook) for (var row : sheet) for (var cell : row)
            {
                String value = new DataFormatter().formatCellValue(cell);
                assertFalse(value.contains("DENIED_"));
                assertFalse(value.contains("开发完整备注"));
            }
        }
        // 导出过滤不能修改列表原数据。
        assertEquals("DENIED_MAIN_PROFIT", item.get("gross_profit_amount"));
        assertEquals("开发完整备注", item.get("development_note"));
    }

    @Test
    void unionsRolesWithoutGrantingUnselectedColumns() throws Exception
    {
        var permissions = new HashSet<>(columns("site", "operations_note"));
        permissions.addAll(columns("sku", "development_note"));
        byte[] bytes = new EbayReplenishmentV2ExportService().buildExcel(payload(), Map.of(), permissions);
        try (var workbook = new XSSFWorkbook(new ByteArrayInputStream(bytes)))
        {
            assertEquals(List.of("站点", "SKU", "运营", "开发"), headers(workbook.getSheet("补货2.0")));
            assertNull(workbook.getSheet("90天分段明细"));
            assertEquals(2, workbook.getNumberOfSheets());
        }
    }

    @Test
    void allowsOnlyDetailColumnsWithoutLeakingMainTable() throws Exception
    {
        byte[] bytes = new EbayReplenishmentV2ExportService().buildExcel(payload(), Map.of(),
                columns("month", "quality_return_qty"));
        try (var workbook = new XSSFWorkbook(new ByteArrayInputStream(bytes)))
        {
            assertNull(workbook.getSheet("补货2.0"));
            assertEquals(List.of("日期区间", "产品质量问题退货量"), headers(workbook.getSheet("90天分段明细")));
            assertEquals(0, workbook.getSheet("90天分段明细").getPaneInformation().getVerticalSplitPosition());
        }
    }

    @Test
    void singleColumnWorkbookHasNoHiddenUnauthorizedColumns() throws Exception
    {
        byte[] bytes = new EbayReplenishmentV2ExportService().buildExcel(payload(), Map.of(), columns("development_note"));
        try (var workbook = new XSSFWorkbook(new ByteArrayInputStream(bytes)))
        {
            var sheet = workbook.getSheet("补货2.0");
            assertEquals(List.of("开发"), headers(sheet));
            assertEquals(1, sheet.getRow(1).getLastCellNum());
            assertEquals("开发完整备注", sheet.getRow(1).getCell(0).getStringCellValue());
            assertFalse(sheet.isColumnHidden(0));
            assertEquals(0, sheet.getPaneInformation().getVerticalSplitPosition());
        }
    }

    @Test
    void failsClosedForMissingUnknownOrPageOnlyPermissions()
    {
        var service = new EbayReplenishmentV2ExportService();
        for (Set<String> permissions : List.of(Set.<String>of(), columns("not_a_column"),
                Set.of("operations:ebayReplenishmentV2:list", "operations:ebayReplenishmentV2:purchase")))
        {
            var error = assertThrows(ServiceException.class, () -> service.buildExcel(payload(), Map.of(), permissions));
            assertTrue(error.getMessage().contains("导出字段权限"));
            assertEquals(403, error.getCode());
        }
        assertThrows(ServiceException.class, () -> service.checkExportPermission(null));
    }
}
