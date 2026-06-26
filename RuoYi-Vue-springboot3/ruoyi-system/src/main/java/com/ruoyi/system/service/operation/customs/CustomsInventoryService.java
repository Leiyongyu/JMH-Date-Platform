package com.ruoyi.system.service.operation.customs;

import com.ruoyi.common.utils.SecurityUtils;
import com.ruoyi.system.domain.operation.customs.CustomsInventoryItem;
import com.ruoyi.system.mapper.operation.customs.CustomsInventoryMapper;
import jakarta.servlet.http.HttpServletResponse;
import java.io.InputStream;
import java.math.BigDecimal;
import java.net.URLEncoder;
import java.text.SimpleDateFormat;
import java.util.ArrayList;
import java.util.Date;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.nio.charset.StandardCharsets;
import org.apache.poi.ss.usermodel.Cell;
import org.apache.poi.ss.usermodel.CellType;
import org.apache.poi.ss.usermodel.CellStyle;
import org.apache.poi.ss.usermodel.Font;
import org.apache.poi.ss.usermodel.DateUtil;
import org.apache.poi.ss.usermodel.Row;
import org.apache.poi.ss.usermodel.Sheet;
import org.apache.poi.ss.usermodel.Workbook;
import org.apache.poi.xssf.usermodel.XSSFWorkbook;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.multipart.MultipartFile;

@Service
public class CustomsInventoryService
{
    private static final long MAX_FILE_SIZE = 30L * 1024 * 1024;
    private static final int MAX_ROWS = 60000;
    private static final String IMPORT_SHEET_NAME = "工作表1";
    private static final String[] FIELD_NAMES = {
            "productCode", "productName", "sku", "purchaseQuantity", "unit", "taxIncludedPrice",
            "purchaseDate", "inboundDate", "inboundQuantity", "inboundRemark", "outboundDate",
            "czechWarehouseQty", "ukWarehouseQty", "usWarehouseQty", "deWarehouseQty",
            "fbaDeQty", "fbaUkQty", "fbaUsQty", "fbaFrQty", "remainingStock",
            "remark", "customsUnit", "declarationElements"
    };
    private final CustomsInventoryMapper inventoryMapper;

    public CustomsInventoryService(CustomsInventoryMapper inventoryMapper)
    {
        this.inventoryMapper = inventoryMapper;
    }

    public List<CustomsInventoryItem> list(String keyword)
    {
        return inventoryMapper.selectList(trim(keyword));
    }

    public List<CustomsInventoryItem> productOptions(String productCode, String productName, String sku, String unit)
    {
        return inventoryMapper.selectProductOptions(
                trim(productCode),
                trim(productName),
                trim(sku),
                trim(unit),
                30);
    }

    public List<String> editableFields()
    {
        List<String> fields = new ArrayList<>();
        for (String field : FIELD_NAMES)
        {
            if (SecurityUtils.hasPermi("customs:inventory:field:" + field)) fields.add(field);
        }
        return fields;
    }

    @Transactional(rollbackFor = Exception.class)
    public CustomsInventoryItem add(CustomsInventoryItem item)
    {
        validateItem(item);
        inventoryMapper.insert(item);
        return item;
    }

    @Transactional(rollbackFor = Exception.class)
    public CustomsInventoryItem update(CustomsInventoryItem item)
    {
        if (item == null || item.getId() == null) throw new IllegalArgumentException("编辑记录ID不能为空");
        CustomsInventoryItem old = inventoryMapper.selectById(item.getId());
        if (old == null) throw new IllegalArgumentException("出入库记录不存在");
        checkFieldPermissions(old, item);
        validateItem(item);
        inventoryMapper.update(item);
        return item;
    }

    public void export(List<Long> ids, HttpServletResponse response) throws Exception
    {
        List<CustomsInventoryItem> rows = (ids == null || ids.isEmpty()) ? inventoryMapper.selectList("")
                : inventoryMapper.selectByIds(ids);
        try (Workbook workbook = new XSSFWorkbook())
        {
            Sheet sheet = workbook.createSheet("出入库清单");
            String[] headers = {
                    "编码", "产品名称", "SKU", "采购数量", "单位", "含税单价", "采购日期", "入库日期",
                    "入库数量", "入库备注", "出库日期", "捷克仓", "英国仓", "美国谷仓", "德国仓",
                    "FBA(DE)", "FBA(UK)", "FBA(US)", "FBA(FR)", "剩余库存", "备注",
                    "报关计量单位", "申报要素"
            };
            CellStyle headerStyle = workbook.createCellStyle();
            Font headerFont = workbook.createFont();
            headerFont.setBold(true);
            headerStyle.setFont(headerFont);

            Row header = sheet.createRow(0);
            for (int i = 0; i < headers.length; i++)
            {
                Cell cell = header.createCell(i);
                cell.setCellValue(headers[i]);
                cell.setCellStyle(headerStyle);
            }

            int rowIndex = 1;
            for (CustomsInventoryItem item : rows)
            {
                Row row = sheet.createRow(rowIndex++);
                int col = 0;
                row.createCell(col++).setCellValue(text(item.getProductCode()));
                row.createCell(col++).setCellValue(text(item.getProductName()));
                row.createCell(col++).setCellValue(text(item.getSku()));
                row.createCell(col++).setCellValue(text(item.getPurchaseQuantity()));
                row.createCell(col++).setCellValue(text(item.getUnit()));
                row.createCell(col++).setCellValue(text(item.getTaxIncludedPrice()));
                row.createCell(col++).setCellValue(text(item.getPurchaseDate()));
                row.createCell(col++).setCellValue(text(item.getInboundDate()));
                setDecimal(row.createCell(col++), item.getInboundQuantity());
                row.createCell(col++).setCellValue(text(item.getInboundRemark()));
                row.createCell(col++).setCellValue(text(item.getOutboundDate()));
                setDecimal(row.createCell(col++), item.getCzechWarehouseQty());
                setDecimal(row.createCell(col++), item.getUkWarehouseQty());
                setDecimal(row.createCell(col++), item.getUsWarehouseQty());
                setDecimal(row.createCell(col++), item.getDeWarehouseQty());
                setDecimal(row.createCell(col++), item.getFbaDeQty());
                setDecimal(row.createCell(col++), item.getFbaUkQty());
                setDecimal(row.createCell(col++), item.getFbaUsQty());
                setDecimal(row.createCell(col++), item.getFbaFrQty());
                setDecimal(row.createCell(col++), item.getRemainingStock());
                row.createCell(col++).setCellValue(text(item.getRemark()));
                row.createCell(col++).setCellValue(text(item.getCustomsUnit()));
                row.createCell(col).setCellValue(text(item.getDeclarationElements()));
            }
            for (int i = 0; i < headers.length; i++) sheet.autoSizeColumn(i);

            String fileName = URLEncoder.encode("出入库清单.xlsx", StandardCharsets.UTF_8).replaceAll("\\+", "%20");
            response.setContentType("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet");
            response.setCharacterEncoding("utf-8");
            response.setHeader("Content-Disposition", "attachment; filename*=UTF-8''" + fileName);
            workbook.write(response.getOutputStream());
        }
    }

    @Transactional(rollbackFor = Exception.class)
    public Map<String, Object> importFile(MultipartFile file) throws Exception
    {
        checkFile(file);
        List<CustomsInventoryItem> parsed = new ArrayList<>();
        List<String> errors = new ArrayList<>();

        try (InputStream input = file.getInputStream(); Workbook workbook = new XSSFWorkbook(input))
        {
            Sheet sheet = workbook.getSheet(IMPORT_SHEET_NAME);
            if (sheet == null) throw new IllegalArgumentException("未找到工作表：" + IMPORT_SHEET_NAME);

            int last = Math.min(sheet.getLastRowNum(), MAX_ROWS - 1);
            String lastProductCode = "";
            for (int rowIndex = 4; rowIndex <= last; rowIndex++)
            {
                Row row = sheet.getRow(rowIndex);
                if (row == null) continue;
                String sku = cellString(row.getCell(2));
                String productName = cellString(row.getCell(1));
                if (sku.isEmpty() && productName.isEmpty()) continue;
                try
                {
                    String productCode = cellString(row.getCell(0));
                    if (!productCode.isEmpty()) lastProductCode = productCode;
                    parsed.add(parseRow(row, defaultValue(productCode, lastProductCode)));
                }
                catch (Exception e)
                {
                    errors.add(sheet.getSheetName() + " 第" + (rowIndex + 1) + "行：" + e.getMessage());
                }
            }
        }

        if (parsed.isEmpty() && errors.isEmpty()) throw new IllegalArgumentException("未读取到出入库清单数据");

        int saved = 0;
        inventoryMapper.deleteAll();
        for (int from = 0; from < parsed.size(); from += 500)
        {
            int to = Math.min(from + 500, parsed.size());
            saved += inventoryMapper.batchInsert(parsed.subList(from, to));
        }

        Map<String, Object> result = new LinkedHashMap<>();
        result.put("parsed", parsed.size());
        result.put("saved", saved);
        result.put("failed", errors.size());
        result.put("errors", errors);
        return result;
    }

    private CustomsInventoryItem parseRow(Row row, String productCode)
    {
        CustomsInventoryItem item = new CustomsInventoryItem();
        item.setProductCode(productCode);
        item.setProductName(cellString(row.getCell(1)));
        item.setSku(cellString(row.getCell(2)));
        item.setPurchaseQuantity(cellString(row.getCell(3)));
        item.setUnit(cellString(row.getCell(4)));
        item.setTaxIncludedPrice(cellString(row.getCell(5)));
        item.setPurchaseDate(dateOrText(row.getCell(6)));
        item.setInboundDate(dateOrText(row.getCell(7)));
        item.setInboundQuantity(decimal(row.getCell(8)));
        item.setInboundRemark(cellString(row.getCell(9)));
        item.setOutboundDate(dateOrText(row.getCell(10)));
        item.setCzechWarehouseQty(decimal(row.getCell(11)));
        item.setUkWarehouseQty(decimal(row.getCell(12)));
        item.setUsWarehouseQty(decimal(row.getCell(13)));
        item.setDeWarehouseQty(decimal(row.getCell(14)));
        item.setFbaDeQty(decimal(row.getCell(15)));
        item.setFbaUkQty(decimal(row.getCell(16)));
        item.setFbaUsQty(decimal(row.getCell(17)));
        item.setFbaFrQty(decimal(row.getCell(18)));
        item.setRemainingStock(decimal(row.getCell(19)));
        item.setRemark(cellString(row.getCell(20)));
        item.setCustomsUnit(cellString(row.getCell(21)));
        item.setDeclarationElements(cellString(row.getCell(22)));
        return item;
    }

    private void checkFile(MultipartFile file)
    {
        if (file == null || file.isEmpty()) throw new IllegalArgumentException("上传文件不能为空");
        if (file.getSize() > MAX_FILE_SIZE) throw new IllegalArgumentException("上传文件不能超过30MB");
        String name = file.getOriginalFilename();
        if (name == null || !name.toLowerCase().endsWith(".xlsx"))
            throw new IllegalArgumentException("仅支持xlsx文件");
    }

    private void validateItem(CustomsInventoryItem item)
    {
        if (item == null) throw new IllegalArgumentException("新增记录不能为空");
        if (trim(item.getSku()).isEmpty() && trim(item.getProductName()).isEmpty())
            throw new IllegalArgumentException("SKU和产品名称至少填写一项");
    }

    private void checkFieldPermissions(CustomsInventoryItem oldItem, CustomsInventoryItem newItem)
    {
        requireFieldPerm(changed(oldItem.getProductCode(), newItem.getProductCode()), "productCode", "编码");
        requireFieldPerm(changed(oldItem.getProductName(), newItem.getProductName()), "productName", "产品名称");
        requireFieldPerm(changed(oldItem.getSku(), newItem.getSku()), "sku", "SKU");
        requireFieldPerm(changed(oldItem.getPurchaseQuantity(), newItem.getPurchaseQuantity()), "purchaseQuantity", "采购数量");
        requireFieldPerm(changed(oldItem.getUnit(), newItem.getUnit()), "unit", "单位");
        requireFieldPerm(changed(oldItem.getTaxIncludedPrice(), newItem.getTaxIncludedPrice()), "taxIncludedPrice", "含税单价");
        requireFieldPerm(changed(oldItem.getPurchaseDate(), newItem.getPurchaseDate()), "purchaseDate", "采购日期");
        requireFieldPerm(changed(oldItem.getInboundDate(), newItem.getInboundDate()), "inboundDate", "入库日期");
        requireFieldPerm(changed(oldItem.getInboundQuantity(), newItem.getInboundQuantity()), "inboundQuantity", "入库数量");
        requireFieldPerm(changed(oldItem.getInboundRemark(), newItem.getInboundRemark()), "inboundRemark", "入库备注");
        requireFieldPerm(changed(oldItem.getOutboundDate(), newItem.getOutboundDate()), "outboundDate", "出库日期");
        requireFieldPerm(changed(oldItem.getCzechWarehouseQty(), newItem.getCzechWarehouseQty()), "czechWarehouseQty", "捷克仓");
        requireFieldPerm(changed(oldItem.getUkWarehouseQty(), newItem.getUkWarehouseQty()), "ukWarehouseQty", "英国仓");
        requireFieldPerm(changed(oldItem.getUsWarehouseQty(), newItem.getUsWarehouseQty()), "usWarehouseQty", "美国谷仓");
        requireFieldPerm(changed(oldItem.getDeWarehouseQty(), newItem.getDeWarehouseQty()), "deWarehouseQty", "德国仓");
        requireFieldPerm(changed(oldItem.getFbaDeQty(), newItem.getFbaDeQty()), "fbaDeQty", "FBA(DE)");
        requireFieldPerm(changed(oldItem.getFbaUkQty(), newItem.getFbaUkQty()), "fbaUkQty", "FBA(UK)");
        requireFieldPerm(changed(oldItem.getFbaUsQty(), newItem.getFbaUsQty()), "fbaUsQty", "FBA(US)");
        requireFieldPerm(changed(oldItem.getFbaFrQty(), newItem.getFbaFrQty()), "fbaFrQty", "FBA(FR)");
        requireFieldPerm(changed(oldItem.getRemainingStock(), newItem.getRemainingStock()), "remainingStock", "剩余库存");
        requireFieldPerm(changed(oldItem.getRemark(), newItem.getRemark()), "remark", "备注");
        requireFieldPerm(changed(oldItem.getCustomsUnit(), newItem.getCustomsUnit()), "customsUnit", "报关计量单位");
        requireFieldPerm(changed(oldItem.getDeclarationElements(), newItem.getDeclarationElements()), "declarationElements", "申报要素");
    }

    private void requireFieldPerm(boolean changed, String field, String name)
    {
        if (changed && !SecurityUtils.hasPermi("customs:inventory:field:" + field))
            throw new IllegalArgumentException("没有编辑字段权限：" + name);
    }

    private boolean changed(Object oldValue, Object newValue)
    {
        return !Objects.equals(normalize(oldValue), normalize(newValue));
    }

    private Object normalize(Object value)
    {
        if (value instanceof String) return trim((String) value);
        if (value instanceof BigDecimal) return ((BigDecimal) value).stripTrailingZeros();
        return value;
    }

    private void setDecimal(Cell cell, BigDecimal value)
    {
        if (value != null) cell.setCellValue(value.doubleValue());
    }

    private String text(String value)
    {
        return value == null ? "" : value;
    }

    private String dateOrText(Cell cell)
    {
        if (cell == null) return "";
        if (cell.getCellType() == CellType.NUMERIC && DateUtil.isValidExcelDate(cell.getNumericCellValue()))
        {
            Date date = DateUtil.getJavaDate(cell.getNumericCellValue());
            return new SimpleDateFormat("yyyy/M/d").format(date);
        }
        return cellString(cell);
    }

    private BigDecimal decimal(Cell cell)
    {
        String value = cellString(cell).replace(",", "");
        if (value.isEmpty()) return null;
        try { return new BigDecimal(value); }
        catch (Exception ignored) { return null; }
    }

    private String cellString(Cell cell)
    {
        if (cell == null) return "";
        if (cell.getCellType() == CellType.NUMERIC)
            return BigDecimal.valueOf(cell.getNumericCellValue()).stripTrailingZeros().toPlainString();
        if (cell.getCellType() == CellType.BOOLEAN) return Boolean.toString(cell.getBooleanCellValue());
        if (cell.getCellType() == CellType.FORMULA)
        {
            try { return BigDecimal.valueOf(cell.getNumericCellValue()).stripTrailingZeros().toPlainString(); }
            catch (Exception ignored) { return trim(cell.getCellFormula()); }
        }
        return trim(cell.toString());
    }

    private String defaultValue(String value, String defaultValue)
    {
        return trim(value).isEmpty() ? defaultValue : trim(value);
    }

    private String trim(String value)
    {
        return value == null ? "" : value.trim();
    }
}
