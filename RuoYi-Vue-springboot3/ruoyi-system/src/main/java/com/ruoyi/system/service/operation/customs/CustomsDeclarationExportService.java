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
import java.util.HashSet;
import java.util.List;
import java.util.Set;
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
    private static final int MAX_ITEMS = 1000;

    private static final int CONTRACT_START_ROW = 15;
    private static final int CONTRACT_FOOTER_ROW = 16;
    private static final int INVOICE_START_ROW = 10;
    private static final int PACKING_START_ROW = 9;
    private static final int CUSTOMS_START_ROW = 10;
    private static final int CUSTOMS_FOOTER_ROW = 11;

    public void export(CustomsDeclarationRequest request, HttpServletResponse response) throws Exception
    {
        validateAndCalculate(request);
        ClassPathResource resource = new ClassPathResource(TEMPLATE);
        try (InputStream input = resource.getInputStream(); Workbook workbook = new XSSFWorkbook(input))
        {
            Sheet contract = requiredSheet(workbook, "合同");
            Sheet invoice = requiredSheet(workbook, "INVOICE");
            Sheet packing = requiredSheet(workbook, "Packing List ");
            Sheet customs = requiredSheet(workbook, "报关单");

            CustomsDeclarationHeader header = request.getHeader() == null ? new CustomsDeclarationHeader() : request.getHeader();
            fillContractHeader(contract, header);
            fillCustomsHeader(customs, header, request.getItems().size());

            int contractTotalRow = prepareContractRows(contract, request.getItems().size());
            fillContractItems(contract, request.getItems(), contractTotalRow);

            int invoiceTotalRow = INVOICE_START_ROW + request.getItems().size();
            fillInvoiceItems(invoice, request.getItems().size(), invoiceTotalRow);

            int packingTotalRow = PACKING_START_ROW + request.getItems().size();
            fillPackingItems(packing, request.getItems(), packingTotalRow, header);

            int customsFooterRow = prepareRows(customs, CUSTOMS_START_ROW, CUSTOMS_FOOTER_ROW,
                    customs.getLastRowNum(), request.getItems().size(), 13);
            fillCustomsItems(customs, request.getItems());

            setPrintAreas(workbook, contract, invoice, packing, customs, contractTotalRow, invoiceTotalRow,
                    packingTotalRow, customsFooterRow);
            workbook.setForceFormulaRecalculation(true);
            workbook.getCreationHelper().createFormulaEvaluator().evaluateAll();

            String filename = "报关单_" + LocalDate.now().format(DateTimeFormatter.ofPattern("yyMMdd")) + ".xlsx";
            response.setContentType("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet");
            response.setCharacterEncoding(StandardCharsets.UTF_8.name());
            response.setHeader("Content-Disposition", "attachment; filename*=UTF-8''"
                    + URLEncoder.encode(filename, StandardCharsets.UTF_8).replace("+", "%20"));
            workbook.write(response.getOutputStream());
        }
    }

    private Sheet requiredSheet(Workbook workbook, String name)
    {
        Sheet sheet = workbook.getSheet(name);
        if (sheet == null) throw new IllegalStateException("报关资料模板缺少工作表：" + name);
        return sheet;
    }

    private int prepareRows(Sheet sheet, int dataStartRow, int footerStartRow, int templateLastRow,
                            int itemCount, int columnCount)
    {
        int footerShiftRows = itemCount;
        Row styleRow = sheet.getRow(dataStartRow);
        CellStyle[] styles = copyStyles(styleRow, columnCount);
        short rowHeight = styleRow == null ? sheet.getDefaultRowHeight() : styleRow.getHeight();

        if (templateLastRow >= footerStartRow)
            sheet.shiftRows(footerStartRow, templateLastRow, footerShiftRows, true, false);

        int footerRow = footerStartRow + footerShiftRows;
        for (int rowIndex = dataStartRow; rowIndex < footerRow; rowIndex++)
        {
            Row row = sheet.getRow(rowIndex);
            if (row == null) row = sheet.createRow(rowIndex);
            row.setHeight(rowHeight);
            for (int column = 0; column < columnCount; column++)
            {
                Cell cell = row.getCell(column);
                if (cell == null) cell = row.createCell(column);
                if (styles[column] != null) cell.setCellStyle(styles[column]);
                else applyBorder(cell);
                cell.setBlank();
            }
        }
        return footerRow;
    }

    private int prepareContractRows(Sheet sheet, int itemCount)
    {
        Row styleRow = sheet.getRow(CONTRACT_START_ROW);
        CellStyle[] styles = copyStyles(styleRow, 9);
        short rowHeight = styleRow == null ? sheet.getDefaultRowHeight() : styleRow.getHeight();
        int totalRow = CONTRACT_START_ROW + itemCount;
        int footerShiftRows = itemCount + 3;

        sheet.shiftRows(CONTRACT_FOOTER_ROW, sheet.getLastRowNum(), footerShiftRows, true, false);
        for (int rowIndex = CONTRACT_START_ROW; rowIndex < CONTRACT_FOOTER_ROW + footerShiftRows; rowIndex++)
        {
            Row row = sheet.getRow(rowIndex);
            if (row == null) row = sheet.createRow(rowIndex);
            row.setHeight(rowHeight);
            for (int column = 0; column < 9; column++)
            {
                Cell cell = row.getCell(column);
                if (cell == null) cell = row.createCell(column);
                if (styles[column] != null) cell.setCellStyle(styles[column]);
                else applyBorder(cell);
                cell.setBlank();
            }
        }
        return totalRow;
    }

    private CellStyle[] copyStyles(Row sourceRow, int columnCount)
    {
        CellStyle[] styles = new CellStyle[columnCount];
        if (sourceRow == null) return styles;
        for (int column = 0; column < styles.length; column++)
        {
            Cell cell = sourceRow.getCell(column);
            if (cell != null) styles[column] = cell.getCellStyle();
        }
        return styles;
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

    private void fillContractHeader(Sheet sheet, CustomsDeclarationHeader h)
    {
        if (!blank(h.getContractNo())) set(sheet, 4, 6, h.getContractNo());
        if (!blank(h.getExportDate())) set(sheet, 5, 6, h.getExportDate());
        if (!blank(h.getConsignee()))
        {
            set(sheet, 12, 0, h.getConsignee());
        }
        if (!blank(h.getTransportMode())) set(sheet, 8, 6, h.getTransportMode());
        setFormula(sheet, 10, 6, "H" + (CONTRACT_START_ROW + 2));
    }

    private void fillCustomsHeader(Sheet sheet, CustomsDeclarationHeader h, int itemCount)
    {
        set(sheet, 1, 0, "预录入编号：" + value(h.getPreEntry()));
        set(sheet, 1, 2, "海关编号：" + value(h.getCustomsNo()));
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
        if (blank(h.getContractNo())) setFormula(sheet, 5, 1, "'合同'!G5");
        else set(sheet, 5, 1, h.getContractNo());
        set(sheet, 5, 3, h.getTradeCountry());
        set(sheet, 5, 6, h.getDestCountry());
        set(sheet, 5, 8, h.getDestPort());
        set(sheet, 5, 11, h.getEntryPort());
        set(sheet, 6, 1, h.getPackType());
        set(sheet, 6, 2, "件数  " + (h.getPackQty() == null ? itemCount : h.getPackQty()));
        set(sheet, 6, 3, blank(h.getGrossWt()) ? "" : "毛重（千克）" + h.getGrossWt());
        set(sheet, 6, 5, blank(h.getNetWt()) ? "" : "净重  （千克）" + h.getNetWt());
        set(sheet, 6, 6, blank(h.getTradeTerm()) ? "" : "成交方式   " + h.getTradeTerm());
        set(sheet, 6, 8, h.getFreight());
        set(sheet, 6, 10, h.getInsurance());
        set(sheet, 6, 12, h.getOtherFee());
        set(sheet, 7, 1, h.getDocs());
        set(sheet, 8, 1, h.getMarks());
    }

    private void fillContractItems(Sheet sheet, List<CustomsDeclarationItem> items, int totalRow)
    {
        for (int i = 0; i < items.size(); i++)
        {
            CustomsDeclarationItem item = items.get(i);
            int rowIndex = CONTRACT_START_ROW + i;
            int excelRow = rowIndex + 1;
            setNumber(sheet, rowIndex, 0, i + 1);
            set(sheet, rowIndex, 1, item.getDescriptionCn());
            set(sheet, rowIndex, 2, item.getSku());
            set(sheet, rowIndex, 3, defaultValue(item.getModel(), "无型号"));
            set(sheet, rowIndex, 4, defaultValue(item.getUnit(), "PIECE"));
            setNumber(sheet, rowIndex, 5, item.getQuantity());
            setNumber(sheet, rowIndex, 6, item.getUnitPriceUsd());
            setFormula(sheet, rowIndex, 7, "ROUND(F" + excelRow + "*G" + excelRow + ",2)");
            set(sheet, rowIndex, 8, defaultValue(item.getCurrency(), "USD"));
        }
        setFormula(sheet, 10, 6, "H" + (totalRow + 1));
        setFormula(sheet, totalRow, 5, "SUM(F" + (CONTRACT_START_ROW + 1) + ":F" + totalRow + ")");
        set(sheet, totalRow, 6, "PIECES");
        setFormula(sheet, totalRow, 7, "SUM(H" + (CONTRACT_START_ROW + 1) + ":H" + totalRow + ")");
    }

    private void fillInvoiceItems(Sheet sheet, int itemCount, int totalRow)
    {
        Row styleRow = sheet.getRow(INVOICE_START_ROW - 1);
        CellStyle[] styles = copyStyles(styleRow, 8);
        for (int i = 0; i < itemCount; i++)
        {
            int rowIndex = INVOICE_START_ROW + i;
            int excelRow = rowIndex + 1;
            Row row = getRow(sheet, rowIndex);
            for (int c = 0; c < 8; c++) applyStyle(row, c, styles[c]);
            setNumber(sheet, rowIndex, 0, i + 1);
            setFormula(sheet, rowIndex, 1, "'合同'!B" + (CONTRACT_START_ROW + i + 1));
            setFormula(sheet, rowIndex, 2, "'合同'!C" + (CONTRACT_START_ROW + i + 1));
            setFormula(sheet, rowIndex, 3, "'合同'!D" + (CONTRACT_START_ROW + i + 1));
            setFormula(sheet, rowIndex, 4, "'合同'!E" + (CONTRACT_START_ROW + i + 1));
            setFormula(sheet, rowIndex, 5, "'合同'!F" + (CONTRACT_START_ROW + i + 1));
            setFormula(sheet, rowIndex, 6, "'合同'!G" + (CONTRACT_START_ROW + i + 1));
            setFormula(sheet, rowIndex, 7, "'合同'!H" + (CONTRACT_START_ROW + i + 1));
        }
        Row total = getRow(sheet, totalRow);
        for (int c = 0; c < 8; c++) applyStyle(total, c, styles[c]);
        setFormula(sheet, totalRow, 5, "SUM(F" + (INVOICE_START_ROW + 1) + ":F" + totalRow + ")");
        set(sheet, totalRow, 6, "PIECES");
        setFormula(sheet, totalRow, 7, "SUM(H" + (INVOICE_START_ROW + 1) + ":H" + totalRow + ")");
    }

    private void fillPackingItems(Sheet sheet, List<CustomsDeclarationItem> items, int totalRow, CustomsDeclarationHeader h)
    {
        Row styleRow = sheet.getRow(PACKING_START_ROW - 1);
        CellStyle[] styles = copyStyles(styleRow, 12);
        Set<String> exportedBoxes = new HashSet<>();
        for (int i = 0; i < items.size(); i++)
        {
            CustomsDeclarationItem item = items.get(i);
            int rowIndex = PACKING_START_ROW + i;
            Row row = getRow(sheet, rowIndex);
            for (int c = 0; c < 12; c++) applyStyle(row, c, styles[c]);
            setNumber(sheet, rowIndex, 0, i + 1);
            setFormula(sheet, rowIndex, 1, "'INVOICE'!B" + (INVOICE_START_ROW + i + 1));
            setFormula(sheet, rowIndex, 2, "'INVOICE'!C" + (INVOICE_START_ROW + i + 1));
            setFormula(sheet, rowIndex, 3, "'INVOICE'!D" + (INVOICE_START_ROW + i + 1));
            setFormula(sheet, rowIndex, 4, "'INVOICE'!E" + (INVOICE_START_ROW + i + 1));
            setFormula(sheet, rowIndex, 5, "'INVOICE'!F" + (INVOICE_START_ROW + i + 1));
            setNumber(sheet, rowIndex, 6, firstNonNull(item.getPackingNetWeight(), item.getTotalWeight()));
            if (exportedBoxes.add(packingBoxKey(item, i)))
            {
                int boxCount = item.getBoxCount() == null || item.getBoxCount() < 1 ? 1 : item.getBoxCount();
                setNumber(sheet, rowIndex, 7, multiply(firstNonNull(item.getPackingGrossWeight(), item.getTotalWeight()), boxCount));
                setNumber(sheet, rowIndex, 8, multiply(item.getPackingCbm(), boxCount));
            }
            else
            {
                getCell(sheet, rowIndex, 7).setBlank();
                getCell(sheet, rowIndex, 8).setBlank();
            }
            setNumber(sheet, rowIndex, 9, item.getBoxLength());
            setNumber(sheet, rowIndex, 10, item.getBoxWidth());
            setNumber(sheet, rowIndex, 11, item.getBoxHeight());
        }
        mergeSharedPackingBoxColumns(sheet, items);
        Row total = getRow(sheet, totalRow);
        for (int c = 0; c < 12; c++) applyStyle(total, c, styles[c]);
        merge(sheet, totalRow, 0, 1);
        merge(sheet, totalRow, 4, 5);
        merge(sheet, totalRow, 8, 11);
        set(sheet, totalRow, 0, "CTN NO:1-" + (h.getPackQty() == null ? items.size() : h.getPackQty()));
        set(sheet, totalRow, 3, "TOTAL:");
        setFormula(sheet, totalRow, 4, "SUM(F" + (PACKING_START_ROW + 1) + ":F" + totalRow + ")&\"PCS\"");
        setFormula(sheet, totalRow, 6, "SUM(G" + (PACKING_START_ROW + 1) + ":G" + totalRow + ")");
        setFormula(sheet, totalRow, 7, "SUM(H" + (PACKING_START_ROW + 1) + ":H" + totalRow + ")");
        BigDecimal totalCbm = packingTotalCbm(items);
        if (totalCbm != null)
        {
            set(sheet, totalRow, 8, formatCbm(totalCbm) + "CBM");
        }
        else
        {
            setFormula(sheet, totalRow, 8, "SUM(I" + (PACKING_START_ROW + 1) + ":I" + totalRow + ")&\"CBM\"");
        }
    }

    private String packingBoxKey(CustomsDeclarationItem item, int index)
    {
        if (!blank(item.getBoxNo()))
        {
            return defaultValue(item.getSourceOrderNo(), "MANUAL") + "|" + item.getBoxNo();
        }
        return "ROW|" + index;
    }

    private void mergeSharedPackingBoxColumns(Sheet sheet, List<CustomsDeclarationItem> items)
    {
        int start = 0;
        while (start < items.size())
        {
            String key = packingBoxKey(items.get(start), start);
            int end = start;
            while (end + 1 < items.size() && key.equals(packingBoxKey(items.get(end + 1), end + 1)))
            {
                end++;
            }
            if (end > start && !key.startsWith("ROW|"))
            {
                int firstRow = PACKING_START_ROW + start;
                int lastRow = PACKING_START_ROW + end;
                for (int column = 7; column <= 11; column++)
                {
                    mergeVertical(sheet, firstRow, lastRow, column);
                }
            }
            start = end + 1;
        }
    }

    private BigDecimal multiply(BigDecimal value, int count)
    {
        if (value == null) return null;
        return value.multiply(BigDecimal.valueOf(count)).setScale(6, RoundingMode.HALF_UP).stripTrailingZeros();
    }

    private BigDecimal packingTotalCbm(List<CustomsDeclarationItem> items)
    {
        BigDecimal total = BigDecimal.ZERO;
        Set<String> exportedOrders = new HashSet<>();
        Set<String> exportedBoxes = new HashSet<>();
        boolean hasCbm = false;
        for (int i = 0; i < items.size(); i++)
        {
            CustomsDeclarationItem item = items.get(i);
            if (!blank(item.getSourceOrderNo()) && item.getOrderTotalCbm() != null)
            {
                if (exportedOrders.add(item.getSourceOrderNo()))
                {
                    total = total.add(item.getOrderTotalCbm());
                    hasCbm = true;
                }
                continue;
            }
            if (item.getPackingCbm() != null && exportedBoxes.add(packingBoxKey(item, i)))
            {
                int boxCount = item.getBoxCount() == null || item.getBoxCount() < 1 ? 1 : item.getBoxCount();
                total = total.add(multiply(item.getPackingCbm(), boxCount));
                hasCbm = true;
            }
        }
        return hasCbm ? total : null;
    }

    private String formatCbm(BigDecimal value)
    {
        return value.setScale(2, RoundingMode.HALF_UP).stripTrailingZeros().toPlainString();
    }

    private void fillCustomsItems(Sheet sheet, List<CustomsDeclarationItem> items)
    {
        for (int i = 0; i < items.size(); i++)
        {
            CustomsDeclarationItem item = items.get(i);
            int rowIndex = CUSTOMS_START_ROW + i;
            int contractExcelRow = CONTRACT_START_ROW + i + 1;
            int packingExcelRow = PACKING_START_ROW + i + 1;
            Row row = getRow(sheet, rowIndex);
            for (int c = 0; c < 13; c++)
            {
                Cell cell = row.getCell(c);
                if (cell == null) cell = row.createCell(c);
                if (cell.getCellStyle() == null) applyBorder(cell);
            }
            merge(sheet, rowIndex, 8, 9);
            merge(sheet, rowIndex, 10, 11);

            setNumber(sheet, rowIndex, 0, i + 1);
            set(sheet, rowIndex, 1, (value(item.getHsCode()) + " " + value(item.getHsDescription())).trim());
            setFormula(sheet, rowIndex, 2, "'Packing List '!B" + packingExcelRow);
            setFormula(sheet, rowIndex, 3, "'Packing List '!C" + packingExcelRow);
            setFormula(sheet, rowIndex, 4, "'Packing List '!D" + packingExcelRow);
            set(sheet, rowIndex, 5, quantityWeightText(item));
            setFormula(sheet, rowIndex, 6, "'合同'!G" + contractExcelRow + "&\"/\"&'合同'!H" + contractExcelRow + "&\"/\"&\"" + defaultValue(item.getCurrency(), "USD") + "\"");
            set(sheet, rowIndex, 7, item.getOriginCountry());
            set(sheet, rowIndex, 8, item.getDestinationCountry());
            set(sheet, rowIndex, 10, item.getSourceLocation());
            set(sheet, rowIndex, 12, defaultValue(item.getExemption(), "照章"));
        }
    }

    private void setPrintAreas(Workbook workbook, Sheet contract, Sheet invoice, Sheet packing, Sheet customs,
                               int contractTotalRow, int invoiceTotalRow, int packingTotalRow, int customsFooterRow)
    {
        workbook.setPrintArea(workbook.getSheetIndex(contract), 0, 8, 0, Math.max(contractTotalRow + 12, contract.getLastRowNum()));
        workbook.setPrintArea(workbook.getSheetIndex(invoice), 0, 7, 0, invoiceTotalRow);
        workbook.setPrintArea(workbook.getSheetIndex(packing), 0, 11, 0, packingTotalRow);
        workbook.setPrintArea(workbook.getSheetIndex(customs), 0, 12, 0, customsFooterRow + 2);
    }

    private String quantityWeightText(CustomsDeclarationItem item)
    {
        String text = item.getQuantity() + defaultValue(item.getUnit(), "个");
        if (item.getTotalWeight() != null && item.getTotalWeight().signum() > 0)
            text += "/" + item.getTotalWeight().stripTrailingZeros().toPlainString() + "千克";
        return text;
    }

    private Row getRow(Sheet sheet, int rowIndex)
    {
        Row row = sheet.getRow(rowIndex);
        if (row == null) row = sheet.createRow(rowIndex);
        return row;
    }

    private void applyStyle(Row row, int column, CellStyle style)
    {
        Cell cell = row.getCell(column);
        if (cell == null) cell = row.createCell(column);
        if (style != null) cell.setCellStyle(style);
        else applyBorder(cell);
    }

    private void set(Sheet sheet, int row, int column, String value)
    {
        Cell cell = getCell(sheet, row, column);
        cell.setCellValue(value(value));
    }

    private void setNumber(Sheet sheet, int row, int column, Number value)
    {
        Cell cell = getCell(sheet, row, column);
        if (value == null) cell.setBlank();
        else cell.setCellValue(value.doubleValue());
    }

    private void setNumber(Sheet sheet, int row, int column, BigDecimal value)
    {
        Cell cell = getCell(sheet, row, column);
        if (value == null) cell.setBlank();
        else cell.setCellValue(value.doubleValue());
    }

    private BigDecimal firstNonNull(BigDecimal first, BigDecimal fallback)
    {
        return first == null ? fallback : first;
    }

    private void setFormula(Sheet sheet, int row, int column, String formula)
    {
        Cell cell = getCell(sheet, row, column);
        cell.setCellFormula(formula);
    }

    private Cell getCell(Sheet sheet, int row, int column)
    {
        Row targetRow = getRow(sheet, row);
        Cell cell = targetRow.getCell(column);
        if (cell == null) cell = targetRow.createCell(column);
        return cell;
    }

    private void merge(Sheet sheet, int rowIndex, int firstColumn, int lastColumn)
    {
        for (int i = sheet.getNumMergedRegions() - 1; i >= 0; i--)
        {
            CellRangeAddress region = sheet.getMergedRegion(i);
            if (region.getFirstRow() == rowIndex && region.getLastRow() == rowIndex
                    && region.getFirstColumn() <= lastColumn && region.getLastColumn() >= firstColumn)
                sheet.removeMergedRegion(i);
        }
        sheet.addMergedRegion(new CellRangeAddress(rowIndex, rowIndex, firstColumn, lastColumn));
    }

    private void mergeVertical(Sheet sheet, int firstRow, int lastRow, int column)
    {
        for (int i = sheet.getNumMergedRegions() - 1; i >= 0; i--)
        {
            CellRangeAddress region = sheet.getMergedRegion(i);
            if (region.getFirstColumn() <= column && region.getLastColumn() >= column
                    && region.getFirstRow() <= lastRow && region.getLastRow() >= firstRow)
                sheet.removeMergedRegion(i);
        }
        sheet.addMergedRegion(new CellRangeAddress(firstRow, lastRow, column, column));
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

    private String defaultValue(String value, String defaultValue)
    {
        return blank(value) ? defaultValue : value;
    }

    private String value(String value) { return value == null ? "" : value; }
    private boolean blank(String value) { return value == null || value.trim().isEmpty(); }
}
