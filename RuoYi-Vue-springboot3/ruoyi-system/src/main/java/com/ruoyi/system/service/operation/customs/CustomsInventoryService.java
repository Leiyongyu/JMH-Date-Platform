package com.ruoyi.system.service.operation.customs;

import com.ruoyi.common.utils.SecurityUtils;
import com.ruoyi.system.domain.operation.customs.CustomsDeclarationGenerateLog;
import com.ruoyi.system.domain.operation.customs.CustomsInventoryItem;
import com.ruoyi.system.mapper.operation.customs.CustomsDeclarationGenerateLogMapper;
import com.ruoyi.system.mapper.operation.customs.CustomsInventoryMapper;
import jakarta.servlet.http.HttpServletResponse;
import java.io.InputStream;
import java.math.BigDecimal;
import java.net.URLEncoder;
import java.text.ParseException;
import java.text.SimpleDateFormat;
import java.util.ArrayList;
import java.util.Date;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.stream.Collectors;
import java.nio.charset.StandardCharsets;
import java.util.regex.Matcher;
import java.util.regex.Pattern;
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
    private static final Pattern HS_PATTERN = Pattern.compile("^(\\d{6,13})\\s*(.*)$");
    private static final String[] FIELD_NAMES = {
            "productCode", "productName", "sku", "purchaseQuantity", "unit", "taxIncludedPrice",
            "purchaseDate", "inboundDate", "inboundQuantity", "inboundRemark", "outboundDate",
            "czechWarehouseQty", "ukWarehouseQty", "usWarehouseQty", "deWarehouseQty",
            "fbaDeQty", "fbaUkQty", "fbaUsQty", "fbaFrQty", "remainingStock",
            "remark", "customsUnit", "declarationElements"
    };
    private final CustomsInventoryMapper inventoryMapper;
    private final CustomsDeclarationGenerateLogMapper generateLogMapper;

    public CustomsInventoryService(CustomsInventoryMapper inventoryMapper,
                                   CustomsDeclarationGenerateLogMapper generateLogMapper)
    {
        this.inventoryMapper = inventoryMapper;
        this.generateLogMapper = generateLogMapper;
    }

    public List<CustomsInventoryItem> list(String keyword)
    {
        List<CustomsInventoryItem> rows = inventoryMapper.selectList(trim(keyword));
        enrichDeclarationUsage(rows);
        return rows;
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
        normalizeDateFields(item);
        applyRemainingStock(item);
        applyHsFields(item);
        initializeAutoStock(item);
        inventoryMapper.insert(item);
        return item;
    }

    @Transactional(rollbackFor = Exception.class)
    public CustomsInventoryItem update(CustomsInventoryItem item)
    {
        if (item == null || item.getId() == null) throw new IllegalArgumentException("编辑记录ID不能为空");
        CustomsInventoryItem old = inventoryMapper.selectById(item.getId());
        if (old == null) throw new IllegalArgumentException("出入库记录不存在");
        validateItem(item);
        normalizeDateFields(item);
        applyRemainingStock(item);
        applyHsFields(item);
        checkFieldPermissions(old, item);
        inventoryMapper.update(item);
        return item;
    }

    private void enrichDeclarationUsage(List<CustomsInventoryItem> rows)
    {
        if (rows == null || rows.isEmpty()) return;
        List<Map<String, String>> keys = rows.stream()
                .filter(row -> !trim(row.getSku()).isEmpty())
                .map(row -> {
                    Map<String, String> key = new LinkedHashMap<>();
                    key.put("sku", trim(row.getSku()));
                    key.put("productCode", trim(row.getProductCode()));
                    return key;
                })
                .distinct()
                .collect(Collectors.toList());
        if (keys.isEmpty()) return;

        Map<String, CustomsInventoryItem> rowMap = new LinkedHashMap<>();
        for (CustomsInventoryItem row : rows)
        {
            rowMap.put(rowKey(row.getSku(), row.getProductCode()), row);
            row.setDeclaredCzechWarehouseQty(BigDecimal.ZERO);
            row.setDeclaredUkWarehouseQty(BigDecimal.ZERO);
            row.setDeclaredUsWarehouseQty(BigDecimal.ZERO);
            row.setDeclaredDeWarehouseQty(BigDecimal.ZERO);
            row.setDeclaredFbaDeQty(BigDecimal.ZERO);
            row.setDeclaredFbaUkQty(BigDecimal.ZERO);
            row.setDeclaredFbaUsQty(BigDecimal.ZERO);
            row.setDeclaredFbaFrQty(BigDecimal.ZERO);
            row.setDeclaredUnknownWarehouseQty(BigDecimal.ZERO);
            row.setDeclaredTotalQty(BigDecimal.ZERO);
            row.setDeclarationLogs(new LinkedHashMap<>());
        }

        for (Map<String, Object> summary : generateLogMapper.selectBucketSummary(keys))
        {
            CustomsInventoryItem row = rowMap.get(rowKey(value(summary.get("standardSku")), value(summary.get("productCode"))));
            if (row == null) continue;
            String bucket = value(summary.get("warehouseBucket"));
            BigDecimal quantity = decimalValue(summary.get("quantity"));
            applyDeclaredQuantity(row, bucket, quantity);
        }

        for (CustomsDeclarationGenerateLog log : generateLogMapper.selectRecentLogs(keys))
        {
            CustomsInventoryItem row = rowMap.get(rowKey(log.getStandardSku(), log.getProductCode()));
            if (row == null) continue;
            String bucket = defaultValue(log.getWarehouseBucket(), "UNKNOWN");
            row.getDeclarationLogs().computeIfAbsent(bucket, k -> new ArrayList<>()).add(log);
        }

        for (CustomsInventoryItem row : rows)
        {
            BigDecimal total = sum(row.getDeclaredCzechWarehouseQty(), row.getDeclaredUkWarehouseQty(),
                    row.getDeclaredUsWarehouseQty(), row.getDeclaredDeWarehouseQty(), row.getDeclaredFbaDeQty(),
                    row.getDeclaredFbaUkQty(), row.getDeclaredFbaUsQty(), row.getDeclaredFbaFrQty(),
                    row.getDeclaredUnknownWarehouseQty());
            row.setDeclaredTotalQty(total);
            row.setAvailableRemainingStock(autoBase(row.getAutoRemainingStock(), row.getRemainingStock()).subtract(total));
        }
    }

    private void initializeAutoStock(CustomsInventoryItem item)
    {
        item.setAutoCzechWarehouseQty(nvl(item.getAutoCzechWarehouseQty(), item.getCzechWarehouseQty()));
        item.setAutoUkWarehouseQty(nvl(item.getAutoUkWarehouseQty(), item.getUkWarehouseQty()));
        item.setAutoUsWarehouseQty(nvl(item.getAutoUsWarehouseQty(), item.getUsWarehouseQty()));
        item.setAutoDeWarehouseQty(nvl(item.getAutoDeWarehouseQty(), item.getDeWarehouseQty()));
        item.setAutoFbaDeQty(nvl(item.getAutoFbaDeQty(), item.getFbaDeQty()));
        item.setAutoFbaUkQty(nvl(item.getAutoFbaUkQty(), item.getFbaUkQty()));
        item.setAutoFbaUsQty(nvl(item.getAutoFbaUsQty(), item.getFbaUsQty()));
        item.setAutoFbaFrQty(nvl(item.getAutoFbaFrQty(), item.getFbaFrQty()));
        item.setAutoRemainingStock(nvl(item.getAutoRemainingStock(), item.getRemainingStock()));
    }

    private void normalizeDateFields(CustomsInventoryItem item)
    {
        item.setPurchaseDate(normalizeSingleDate(item.getPurchaseDate()));
        item.setInboundDate(normalizeSingleDate(item.getInboundDate()));
        item.setOutboundDate(normalizeLooseDateText(item.getOutboundDate()));
    }

    private void applyRemainingStock(CustomsInventoryItem item)
    {
        item.setRemainingStock(calculateRemainingStock(item));
    }

    private BigDecimal calculateRemainingStock(CustomsInventoryItem item)
    {
        return nvl(item.getInboundQuantity())
                .subtract(nvl(item.getCzechWarehouseQty()))
                .subtract(nvl(item.getUkWarehouseQty()))
                .subtract(nvl(item.getUsWarehouseQty()))
                .subtract(nvl(item.getDeWarehouseQty()))
                .subtract(nvl(item.getFbaDeQty()))
                .subtract(nvl(item.getFbaUkQty()))
                .subtract(nvl(item.getFbaUsQty()))
                .subtract(nvl(item.getFbaFrQty()));
    }

    private void applyDeclaredQuantity(CustomsInventoryItem row, String bucket, BigDecimal quantity)
    {
        BigDecimal value = nvl(quantity);
        switch (bucket)
        {
            case "CZ" -> row.setDeclaredCzechWarehouseQty(nvl(row.getDeclaredCzechWarehouseQty()).add(value));
            case "UK" -> row.setDeclaredUkWarehouseQty(nvl(row.getDeclaredUkWarehouseQty()).add(value));
            case "US_GC" -> row.setDeclaredUsWarehouseQty(nvl(row.getDeclaredUsWarehouseQty()).add(value));
            case "DE" -> row.setDeclaredDeWarehouseQty(nvl(row.getDeclaredDeWarehouseQty()).add(value));
            case "FBA_DE" -> row.setDeclaredFbaDeQty(nvl(row.getDeclaredFbaDeQty()).add(value));
            case "FBA_UK" -> row.setDeclaredFbaUkQty(nvl(row.getDeclaredFbaUkQty()).add(value));
            case "FBA_US" -> row.setDeclaredFbaUsQty(nvl(row.getDeclaredFbaUsQty()).add(value));
            case "FBA_FR" -> row.setDeclaredFbaFrQty(nvl(row.getDeclaredFbaFrQty()).add(value));
            default -> row.setDeclaredUnknownWarehouseQty(nvl(row.getDeclaredUnknownWarehouseQty()).add(value));
        }
    }

    private String rowKey(String sku, String productCode)
    {
        return trim(sku) + "|" + trim(productCode);
    }

    private BigDecimal decimalValue(Object value)
    {
        if (value instanceof BigDecimal decimal) return decimal;
        if (value instanceof Number number) return BigDecimal.valueOf(number.doubleValue());
        try { return new BigDecimal(value(value)); }
        catch (Exception ignored) { return BigDecimal.ZERO; }
    }

    private BigDecimal nvl(BigDecimal value)
    {
        return value == null ? BigDecimal.ZERO : value;
    }

    private BigDecimal nvl(BigDecimal value, BigDecimal fallback)
    {
        return value == null ? fallback : value;
    }

    private BigDecimal autoBase(BigDecimal autoValue, BigDecimal manualFallback)
    {
        return autoValue == null ? nvl(manualFallback) : autoValue;
    }

    private BigDecimal sum(BigDecimal... values)
    {
        BigDecimal total = BigDecimal.ZERO;
        for (BigDecimal value : values) total = total.add(nvl(value));
        return total;
    }

    private String value(Object value)
    {
        return value == null ? "" : value.toString();
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
                    CustomsInventoryItem item = parseRow(row, defaultValue(productCode, lastProductCode));
                    normalizeDateFields(item);
                    applyRemainingStock(item);
                    initializeAutoStock(item);
                    parsed.add(item);
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
        item.setRemark(cellString(row.getCell(20)));
        item.setCustomsUnit(cellString(row.getCell(21)));
        item.setDeclarationElements(cellString(row.getCell(22)));
        applyHsFields(item);
        return item;
    }

    private void applyHsFields(CustomsInventoryItem item)
    {
        String elements = trim(item.getDeclarationElements());
        Matcher matcher = HS_PATTERN.matcher(elements);
        if (matcher.find())
        {
            item.setHsCode(matcher.group(1));
            item.setHsDescription(trim(matcher.group(2)));
        }
        else
        {
            item.setHsCode("");
            item.setHsDescription(elements);
        }
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
        if (isDateCell(cell))
        {
            Date date = DateUtil.getJavaDate(cellNumericValue(cell));
            return new SimpleDateFormat("yyyy-MM-dd").format(date);
        }
        return normalizeLooseDateText(cellString(cell));
    }

    private String normalizeSingleDate(String value)
    {
        String text = trim(value);
        if (text.isEmpty()) return "";
        Date date = parseDate(text);
        return date == null ? text : new SimpleDateFormat("yyyy-MM-dd").format(date);
    }

    private String normalizeLooseDateText(String value)
    {
        String text = trim(value);
        if (text.isEmpty()) return "";
        String[] parts = text.split("[\\r\\n,，;；]+");
        List<String> normalized = new ArrayList<>();
        for (String part : parts)
        {
            String item = trim(part);
            if (item.isEmpty()) continue;
            normalized.add(normalizeSingleDate(item));
        }
        return normalized.isEmpty() ? text : String.join("，", normalized);
    }

    private Date parseDate(String value)
    {
        String text = trim(value).replace('.', '-').replace('/', '-');
        String[] patterns = {"yyyy-MM-dd", "yyyy-M-d", "yyyyMMdd"};
        for (String pattern : patterns)
        {
            try
            {
                SimpleDateFormat format = new SimpleDateFormat(pattern);
                format.setLenient(false);
                return format.parse(text);
            }
            catch (ParseException ignored) { }
        }
        return null;
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
        CellType type = cell.getCellType();
        if (type == CellType.FORMULA)
        {
            try { type = cell.getCachedFormulaResultType(); }
            catch (Exception ignored) { return ""; }
        }
        if (type == CellType.NUMERIC)
            return BigDecimal.valueOf(cellNumericValue(cell)).stripTrailingZeros().toPlainString();
        if (type == CellType.STRING) return trim(cell.getStringCellValue());
        if (type == CellType.BOOLEAN) return Boolean.toString(cell.getBooleanCellValue());
        return trim(cell.toString());
    }

    private boolean isDateCell(Cell cell)
    {
        if (cell == null) return false;
        try
        {
            CellType type = cell.getCellType() == CellType.FORMULA ? cell.getCachedFormulaResultType() : cell.getCellType();
            return type == CellType.NUMERIC && DateUtil.isValidExcelDate(cellNumericValue(cell));
        }
        catch (Exception ignored) { return false; }
    }

    private double cellNumericValue(Cell cell)
    {
        return cell.getNumericCellValue();
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
