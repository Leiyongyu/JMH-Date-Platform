package com.ruoyi.system.service.operation.customs;

import static org.junit.jupiter.api.Assertions.assertEquals;

import com.ruoyi.common.utils.poi.ExcelCells;
import java.nio.charset.StandardCharsets;
import org.apache.poi.ss.usermodel.DataFormatter;
import org.apache.poi.ss.usermodel.Row;
import org.apache.poi.xssf.usermodel.XSSFWorkbook;
import org.junit.jupiter.api.Test;

class ExcelCellsTest
{
    @Test
    void plainReadsRawValuesAndNeverReturnsFormulaText() throws Exception
    {
        try (XSSFWorkbook workbook = new XSSFWorkbook())
        {
            Row row = workbook.createSheet().createRow(0);
            row.createCell(0).setCellValue(1.50);
            row.createCell(1).setCellValue("  SKU-1 ");
            row.createCell(2).setCellValue(true);
            row.createCell(3).setCellFormula("1/0");
            row.createCell(4).setCellFormula("A1*2");
            workbook.getCreationHelper().createFormulaEvaluator().evaluateAll();

            assertEquals("1.5", ExcelCells.plain(row.getCell(0)));
            assertEquals("SKU-1", ExcelCells.plain(row.getCell(1)));
            assertEquals("true", ExcelCells.plain(row.getCell(2)));
            assertEquals("", ExcelCells.plain(row.getCell(3)));
            assertEquals("3", ExcelCells.plain(row.getCell(4)));
            assertEquals("", ExcelCells.plain(row.getCell(9)));
        }
    }

    @Test
    void formattedFollowsDisplayFormat() throws Exception
    {
        try (XSSFWorkbook workbook = new XSSFWorkbook())
        {
            Row row = workbook.createSheet().createRow(0);
            row.createCell(0).setCellFormula("2+3");
            assertEquals("5", ExcelCells.formatted(row.getCell(0), new DataFormatter(),
                    workbook.getCreationHelper().createFormulaEvaluator()));
            assertEquals("", ExcelCells.formatted(null, new DataFormatter(), null));
        }
    }

    @Test
    void sha256HexIsStable()
    {
        assertEquals("ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad",
                ExcelCells.sha256Hex("abc".getBytes(StandardCharsets.UTF_8)));
    }
}
