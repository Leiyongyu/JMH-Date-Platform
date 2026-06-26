package com.ruoyi.system.service.operation.customs;

import com.ruoyi.system.domain.operation.customs.CustomsDeclarationHeader;
import com.ruoyi.system.domain.operation.customs.CustomsDeclarationItem;
import com.ruoyi.system.domain.operation.customs.CustomsDeclarationRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.io.InputStream;
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.util.List;
import org.apache.poi.ss.usermodel.BorderStyle;
import org.apache.poi.ss.usermodel.Cell;
import org.apache.poi.ss.usermodel.CellStyle;
import org.apache.poi.ss.usermodel.Row;
import org.apache.poi.ss.usermodel.Sheet;
import org.apache.poi.ss.usermodel.Workbook;
import org.apache.poi.ss.util.CellRangeAddress;
import org.apache.poi.xssf.usermodel.XSSFWorkbook;
import org.springframework.core.io.ClassPathResource;
import org.springframework.stereotype.Service;

@Service
public class CustomsDeclarationExportService
{
    private static final String TEMPLATE = "templates/customs/customs-declaration-template.xlsx";
    private static final int DATA_START_ROW = 10;
    private static final int TEMPLATE_ITEM_ROWS = 25;
    private static final int TEMPLATE_FOOTER_ROW = DATA_START_ROW + TEMPLATE_ITEM_ROWS;
    private static final int TEMPLATE_LAST_ROW = 37;
    private static final int MAX_ITEMS = 1000;

    public void export(CustomsDeclarationRequest request, HttpServletResponse response) throws Exception
    {
        validateAndCalculate(request);
        ClassPathResource resource = new ClassPathResource(TEMPLATE);
        try (InputStream input = resource.getInputStream(); Workbook workbook = new XSSFWorkbook(input))
        {
            while (workbook.getNumberOfSheets() > 1)
                workbook.removeSheetAt(workbook.getNumberOfSheets() - 1);
            Sheet sheet = workbook.getSheetAt(0);
            fillHeader(sheet, request.getHeader(), request.getItems().size());
            int footerStartRow = prepareRows(sheet, request.getItems().size());
            fillItems(sheet, request.getItems());
            workbook.setPrintArea(workbook.getSheetIndex(sheet), 0, 12, 0,
                    footerStartRow + (TEMPLATE_LAST_ROW - TEMPLATE_FOOTER_ROW));

            String filename = "报关单_" + LocalDate.now().format(DateTimeFormatter.ofPattern("yyMMdd")) + ".xlsx";
            response.setContentType("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet");
            response.setCharacterEncoding(StandardCharsets.UTF_8.name());
            response.setHeader("Content-Disposition", "attachment; filename*=UTF-8''"
                    + URLEncoder.encode(filename, StandardCharsets.UTF_8).replace("+", "%20"));
            workbook.write(response.getOutputStream());
        }
    }

    /**
     * 正式模板预留 25 条商品行，第 36-38 行为固定页脚。
     * 根据实际商品数量移动页脚，避免导出残留模板示例数据。
     */
    private int prepareRows(Sheet sheet, int itemCount)
    {
        int difference = itemCount - TEMPLATE_ITEM_ROWS;
        if (difference < 0)
        {
            int firstUnusedRow = DATA_START_ROW + itemCount;
            for (int i = sheet.getNumMergedRegions() - 1; i >= 0; i--)
            {
                CellRangeAddress region = sheet.getMergedRegion(i);
                if (region.getFirstRow() >= firstUnusedRow && region.getLastRow() < TEMPLATE_FOOTER_ROW)
                    sheet.removeMergedRegion(i);
            }
        }
        if (difference != 0)
        {
            sheet.shiftRows(TEMPLATE_FOOTER_ROW, TEMPLATE_LAST_ROW, difference, true, false);
        }

        int footerStartRow = TEMPLATE_FOOTER_ROW + difference;
        Row styleRow = sheet.getRow(DATA_START_ROW);
        for (int rowIndex = DATA_START_ROW; rowIndex < footerStartRow; rowIndex++)
        {
            Row row = sheet.getRow(rowIndex);
            if (row == null) row = sheet.createRow(rowIndex);
            if (styleRow != null) row.setHeight(styleRow.getHeight());
            for (int column = 0; column < 13; column++)
            {
                Cell cell = row.getCell(column);
                if (cell == null) cell = row.createCell(column);
                cell.setBlank();
            }
        }
        return footerStartRow;
    }

    private void validateAndCalculate(CustomsDeclarationRequest request)
    {
        if (request == null || request.getItems() == null || request.getItems().isEmpty())
            throw new IllegalArgumentException("请至少添加一个商品");
        if (request.getItems().size() > MAX_ITEMS) throw new IllegalArgumentException("单次最多导出1000个商品");
        for (CustomsDeclarationItem item : request.getItems())
        {
            if (blank(item.getSku())) throw new IllegalArgumentException("SKU不能为空");
            if (item.getQuantity() == null) item.setQuantity(1);
            if (blank(item.getCurrency())) item.setCurrency("USD");

            BigDecimal quantity = BigDecimal.valueOf(item.getQuantity());
            BigDecimal price = item.getUnitPriceUsd() == null ? BigDecimal.ZERO : item.getUnitPriceUsd();
            BigDecimal weight = item.getSingleWeight() == null ? BigDecimal.ZERO : item.getSingleWeight();
            item.setTotalPrice(price.multiply(quantity).setScale(2, RoundingMode.HALF_UP));
            item.setTotalWeight(weight.multiply(quantity).setScale(4, RoundingMode.HALF_UP));
        }
    }

    private void fillHeader(Sheet sheet, CustomsDeclarationHeader h, int itemCount)
    {
        if (h == null) h = new CustomsDeclarationHeader();
        set(sheet, 1, 1, h.getPreEntry());
        set(sheet, 1, 3, h.getCustomsNo());
        set(sheet, 2, 1, h.getConsignor());
        set(sheet, 2, 3, h.getCustomsArea());
        set(sheet, 2, 6, h.getExportDate());
        set(sheet, 2, 8, h.getDeclareDate());
        set(sheet, 2, 11, h.getRecordNo());
        set(sheet, 3, 1, h.getConsignee());
        set(sheet, 3, 3, h.getTransportMode());
        set(sheet, 3, 6, h.getTransportName());
        set(sheet, 3, 8, h.getBillNo());
        set(sheet, 4, 1, h.getProducer());
        set(sheet, 4, 3, h.getSupervision());
        set(sheet, 4, 6, h.getTaxNature());
        set(sheet, 4, 8, h.getLicenseNo());
        set(sheet, 5, 1, h.getContractNo());
        set(sheet, 5, 3, h.getTradeCountry());
        set(sheet, 5, 6, h.getDestCountry());
        set(sheet, 5, 8, h.getDestPort());
        set(sheet, 5, 11, h.getEntryPort());
        set(sheet, 6, 1, h.getPackType());
        set(sheet, 6, 2, "件数  " + (h.getPackQty() == null ? itemCount : h.getPackQty()));
        set(sheet, 6, 3, blank(h.getGrossWt()) ? "" : "毛重（千克）" + h.getGrossWt());
        set(sheet, 6, 5, blank(h.getNetWt()) ? "" : "净重（千克）" + h.getNetWt());
        set(sheet, 6, 6, blank(h.getTradeTerm()) ? "" : "成交方式 " + h.getTradeTerm());
        set(sheet, 6, 8, h.getFreight());
        set(sheet, 6, 10, h.getInsurance());
        set(sheet, 6, 12, h.getOtherFee());
        set(sheet, 7, 1, h.getDocs());
        set(sheet, 8, 1, h.getMarks());
    }

    private void fillItems(Sheet sheet, List<CustomsDeclarationItem> items)
    {
        Row styleRow = sheet.getRow(DATA_START_ROW);
        CellStyle[] styles = new CellStyle[13];
        for (int c = 0; c < styles.length; c++)
            if (styleRow != null && styleRow.getCell(c) != null) styles[c] = styleRow.getCell(c).getCellStyle();

        for (int i = 0; i < items.size(); i++)
        {
            int rowIndex = DATA_START_ROW + i;
            Row row = sheet.getRow(rowIndex);
            if (row == null) row = sheet.createRow(rowIndex);
            if (styleRow != null) row.setHeight(styleRow.getHeight());
            for (int c = 0; c < 13; c++)
            {
                Cell cell = row.getCell(c);
                if (cell == null) cell = row.createCell(c);
                if (styles[c] != null) cell.setCellStyle(styles[c]);
                else applyBorder(cell);
            }
            removeOverlappingMerge(sheet, rowIndex, 8, 9);
            removeOverlappingMerge(sheet, rowIndex, 10, 11);
            sheet.addMergedRegion(new CellRangeAddress(rowIndex, rowIndex, 8, 9));
            sheet.addMergedRegion(new CellRangeAddress(rowIndex, rowIndex, 10, 11));

            CustomsDeclarationItem item = items.get(i);
            row.getCell(0).setCellValue(i + 1);
            row.getCell(1).setCellValue((value(item.getHsCode()) + " " + value(item.getHsDescription())).trim());
            row.getCell(2).setCellValue(value(item.getDescriptionCn()));
            row.getCell(3).setCellValue(value(item.getSku()));
            row.getCell(4).setCellValue(defaultValue(item.getModel(), "通用型"));
            String qtyWeight = item.getQuantity() + defaultValue(item.getUnit(), "个");
            if (item.getTotalWeight() != null && item.getTotalWeight().signum() > 0)
                qtyWeight += "/" + item.getTotalWeight().stripTrailingZeros().toPlainString() + "千克";
            row.getCell(5).setCellValue(qtyWeight);
            row.getCell(6).setCellValue(decimalText(item.getUnitPriceUsd()) + "/"
                    + decimalText(item.getTotalPrice()) + "/" + value(item.getCurrency()));
            row.getCell(7).setCellValue(value(item.getOriginCountry()));
            row.getCell(8).setCellValue(value(item.getDestinationCountry()));
            row.getCell(10).setCellValue(value(item.getSourceLocation()));
            row.getCell(12).setCellValue(value(item.getExemption()));
        }
    }

    private void set(Sheet sheet, int row, int column, String value)
    {
        Row targetRow = sheet.getRow(row);
        if (targetRow == null) targetRow = sheet.createRow(row);
        Cell cell = targetRow.getCell(column);
        if (cell == null) cell = targetRow.createCell(column);
        cell.setCellValue(value(value));
    }

    private void removeOverlappingMerge(Sheet sheet, int row, int firstColumn, int lastColumn)
    {
        for (int i = sheet.getNumMergedRegions() - 1; i >= 0; i--)
        {
            CellRangeAddress region = sheet.getMergedRegion(i);
            if (region.getFirstRow() == row && region.getLastRow() == row
                    && region.getFirstColumn() <= lastColumn && region.getLastColumn() >= firstColumn)
                sheet.removeMergedRegion(i);
        }
    }

    private void applyBorder(Cell cell)
    {
        CellStyle style = cell.getSheet().getWorkbook().createCellStyle();
        style.setBorderTop(BorderStyle.THIN);
        style.setBorderBottom(BorderStyle.THIN);
        style.setBorderLeft(BorderStyle.THIN);
        style.setBorderRight(BorderStyle.THIN);
        cell.setCellStyle(style);
    }

    private String decimalText(BigDecimal value)
    {
        return value == null ? "0" : value.stripTrailingZeros().toPlainString();
    }

    private String defaultValue(String value, String defaultValue)
    {
        return blank(value) ? defaultValue : value;
    }

    private String value(String value) { return value == null ? "" : value; }
    private boolean blank(String value) { return value == null || value.trim().isEmpty(); }
}
