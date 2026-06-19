package com.ruoyi.system.service.operation;

import java.io.InputStream;
import java.math.BigDecimal;
import java.text.SimpleDateFormat;
import java.util.*;

import org.apache.poi.ss.usermodel.*;
import org.apache.poi.xssf.usermodel.XSSFWorkbook;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.multipart.MultipartFile;

import com.ruoyi.system.domain.operation.OperationImportTask;
import com.ruoyi.system.domain.operation.external.*;
import com.ruoyi.system.mapper.operation.OperationImportTaskMapper;
import com.ruoyi.system.mapper.operation.external.*;
import com.ruoyi.system.service.operation.compute.InventoryUtils;

@Service
public class OperationImportService
{
    private static final Logger log = LoggerFactory.getLogger(OperationImportService.class);
    private static final int MAX_ROWS = 50000;
    private static final long MAX_FILE_SIZE = 20 * 1024 * 1024; // 20MB

    @Autowired private OperationImportTaskMapper taskMapper;
    @Autowired private EbaySalesMapper ebaySalesMapper;
    @Autowired private EbayProductDedupMapper dedupMapper;
    @Autowired private GoodcangProductInfoMapper productInfoMapper;

    // ========== 导入销量 ==========
    public OperationImportTask importEbaySales(MultipartFile file, String operator) throws Exception
    {
        OperationImportTask task = createTask(file.getOriginalFilename(), "EBAY_SALES", operator);
        try (InputStream is = file.getInputStream(); Workbook wb = new XSSFWorkbook(is))
        {
            Sheet sheet = wb.getSheetAt(0);
            Row headerRow = sheet.getRow(0);
            int[] idx = findColumnIndexes(headerRow, "平台订单号", "币种", "库存SKU", "购买数量", "付款时间");
            int colOrderNo = idx[0], colCurrency = idx[1], colSku = idx[2], colQty = idx[3], colPayTime = idx[4];
            if (colOrderNo < 0 || colCurrency < 0 || colSku < 0 || colQty < 0 || colPayTime < 0)
            {
                task.setStatus("FAILED");
                task.setFailRows(1);
                finishTask(task);
                throw new IllegalArgumentException("销量导入文件缺少必要表头：平台订单号、币种、库存SKU、购买数量、付款时间");
            }
            int total = Math.min(sheet.getLastRowNum(), MAX_ROWS);
            task.setTotalRows(total);
            int success = 0;
            List<Map<String, Object>> batch = new ArrayList<>();
            List<String> errors = new ArrayList<>();

            for (int i = 1; i <= total; i++)
            {
                Row row = sheet.getRow(i);
                if (row == null || isEmptyRow(row)) continue;
                try
                {
                    Map<String, Object> m = new LinkedHashMap<>();
                    m.put("platformOrderNo", getCellStr(row, colOrderNo));
                    m.put("currency", getCellStr(row, colCurrency));
                    m.put("sku", getCellStr(row, colSku));
                    m.put("quantity", getCellInt(row, colQty));
                    m.put("paymentTime", getCellDate(row, colPayTime));
                    if (m.get("platformOrderNo") == null || m.get("sku") == null) { errors.add("行" + (i+1) + ": 订单号或SKU为空"); continue; }
                    batch.add(m);
                    if (batch.size() >= 500) { ebaySalesMapper.batchUpsert(batch); success += batch.size(); batch.clear(); }
                }
                catch (Exception e) { errors.add("行" + (i+1) + ": " + e.getMessage()); }
            }
            if (!batch.isEmpty()) { ebaySalesMapper.batchUpsert(batch); success += batch.size(); }
            task.setSuccessRows(success);
            task.setFailRows(errors.size());
            task.setStatus(errors.isEmpty() ? "SUCCESS" : "PARTIAL");
        }
        finishTask(task);
        return task;
    }

    // ========== 导入利润率 ==========
    public OperationImportTask importProfitRate(MultipartFile file, String operator) throws Exception
    {
        OperationImportTask task = createTask(file.getOriginalFilename(), "PROFIT_RATE", operator);
        try (InputStream is = file.getInputStream(); Workbook wb = new XSSFWorkbook(is))
        {
            int total = wb.getNumberOfSheets();
            int success = 0;
            for (int s = 0; s < total; s++)
            {
                Sheet sheet = wb.getSheetAt(s);
                String sheetName = sheet.getSheetName().trim();
                String site = mapSite(sheetName);
                if (site == null) { log.warn("未知站点: {}", sheetName); continue; }
                Row headerRow = sheet.getRow(0);
                int colSku = findColumnIndex(headerRow, 0, "SKU", "产品代码");
                int colRate = findColumnIndex(headerRow, 1, "Profit", "利润率");
                int rows = Math.min(sheet.getLastRowNum(), MAX_ROWS);
                task.setTotalRows(task.getTotalRows() + rows);
                for (int i = 1; i <= rows; i++)
                {
                    Row row = sheet.getRow(i);
                    if (row == null || isEmptyRow(row)) continue;
                    try
                    {
                        String sku = getCellStr(row, colSku);
                        String mid = InventoryUtils.extractMiddleCodeForInventory(sku);
                        if (mid.isEmpty() && sku != null) mid = sku.trim();
                        if (mid.isEmpty()) continue;
                        BigDecimal rate = getCellDecimal(row, colRate);
                        if (rate == null) continue;
                        dedupMapper.updateProfitRate(site, mid, rate);
                        success++;
                    } catch (Exception ignored) {}
                }
            }
            task.setSuccessRows(success);
            task.setStatus("SUCCESS");
        }
        finishTask(task);
        return task;
    }

    // ========== 导入退货率 ==========
    public OperationImportTask importReturnRate(MultipartFile file, String operator) throws Exception
    {
        OperationImportTask task = createTask(file.getOriginalFilename(), "RETURN_RATE", operator);
        try (InputStream is = file.getInputStream(); Workbook wb = new XSSFWorkbook(is))
        {
            Sheet sheet = wb.getSheetAt(0);
            Row headerRow = sheet.getRow(0);
            int colSku = findColumnIndex(headerRow, 0, "SKU", "产品SKU");
            int colRate = findColumnIndex(headerRow, 4, "各平台售后率");
            int total = Math.min(sheet.getLastRowNum(), MAX_ROWS);
            task.setTotalRows(total);
            int success = 0;
            Map<String, BigDecimal> updates = new LinkedHashMap<>();
            for (int i = 1; i <= total; i++)
            {
                Row row = sheet.getRow(i);
                if (row == null || isEmptyRow(row)) continue;
                try
                {
                    String sku = getCellStr(row, colSku);
                    BigDecimal rate = getCellDecimal(row, colRate);
                    if (sku == null || rate == null) continue;
                    String mid = InventoryUtils.extractMiddleCodeForInventory(sku);
                    if (mid.isEmpty()) mid = sku.trim();
                    if (mid.isEmpty()) continue;
                    updates.putIfAbsent(mid, rate);
                } catch (Exception ignored) {}
            }
            for (Map.Entry<String, BigDecimal> e : updates.entrySet())
            {
                int rows = dedupMapper.updateReturnRateByMiddleCode(e.getKey(), e.getValue());
                if (rows > 0) success++;
            }
            task.setSuccessRows(success);
            task.setStatus("SUCCESS");
        }
        finishTask(task);
        return task;
    }

    // ========== 导入最低价 → ebay_product_dedup ==========
    public OperationImportTask importLowestPrice(MultipartFile file, String operator) throws Exception
    {
        OperationImportTask task = createTask(file.getOriginalFilename(), "LOWEST_PRICE", operator);
        try (InputStream is = file.getInputStream(); Workbook wb = new XSSFWorkbook(is))
        {
            Sheet sheet = wb.getSheetAt(0);
            Row headerRow = sheet.getRow(0);
            int colSku = findColumnIndex(headerRow, 0, "SKU");
            int colSite = findColumnIndex(headerRow, 1, "站点", "Site");
            int colPrice = findColumnIndex(headerRow, 2, "价格", "Price");
            int colItemNo = findColumnIndex(headerRow, -1, "Item Number");
            int total = Math.min(sheet.getLastRowNum(), MAX_ROWS);
            task.setTotalRows(total);
            int success = 0;
            // 按 (site, sku) 仅保留最低价
            Map<String, PriceRecord> best = new LinkedHashMap<>();
            for (int i = 1; i <= total; i++)
            {
                Row row = sheet.getRow(i);
                if (row == null || isEmptyRow(row)) continue;
                try
                {
                    String sku = InventoryUtils.extractBaseSku(getCellStr(row, colSku));
                    String site = mapSite(getCellStr(row, colSite));
                    BigDecimal price = getCellDecimal(row, colPrice);
                    String itemNo = colItemNo >= 0 ? getCellStr(row, colItemNo) : null;
                    if (sku == null || sku.isEmpty() || site == null || price == null) continue;
                    String key = site + "|" + sku;
                    PriceRecord pr = best.get(key);
                    if (pr == null || price.compareTo(pr.price) < 0) best.put(key, new PriceRecord(price, itemNo));
                } catch (Exception ignored) {}
            }
            for (Map.Entry<String, PriceRecord> e : best.entrySet())
            {
                String[] parts = e.getKey().split("\\|");
                if (parts.length == 2)
                {
                    int rows = dedupMapper.updateLowestPrice(parts[0], parts[1], e.getValue().price, e.getValue().itemNo);
                    if (rows > 0) success++;
                }
            }
            task.setSuccessRows(success);
            task.setStatus("SUCCESS");
        }
        finishTask(task);
        return task;
    }

    // ========== 导入商品单价 → goodcang_product_info ==========
    public OperationImportTask importProductPrice(MultipartFile file, String operator) throws Exception
    {
        OperationImportTask task = createTask(file.getOriginalFilename(), "PRODUCT_PRICE", operator);
        try (InputStream is = file.getInputStream(); Workbook wb = new XSSFWorkbook(is))
        {
            Sheet sheet = wb.getSheetAt(0);
            Row headerRow = sheet.getRow(0);
            int colSku = findColumnIndex(headerRow, 0, "sku", "SKU");
            int colPrice = findColumnIndex(headerRow, 1, "price", "Price", "单价");
            int total = Math.min(sheet.getLastRowNum(), MAX_ROWS);
            task.setTotalRows(total);
            int success = 0;
            for (int i = 1; i <= total; i++)
            {
                Row row = sheet.getRow(i);
                if (row == null || isEmptyRow(row)) continue;
                try
                {
                    String middleCode = getCellStr(row, colSku);
                    BigDecimal price = getCellDecimal(row, colPrice);
                    if (middleCode == null || price == null) continue;
                    productInfoMapper.updatePrice(middleCode, price);
                    success++;
                } catch (Exception ignored) {}
            }
            task.setSuccessRows(success);
            task.setStatus("SUCCESS");
        }
        finishTask(task);
        return task;
    }

    // ========== 工具方法 ==========
    private OperationImportTask createTask(String fileName, String type, String operator)
    {
        OperationImportTask t = new OperationImportTask();
        t.setFileName(fileName); t.setTaskType(type); t.setOperator(operator);
        t.setStatus("RUNNING"); t.setTotalRows(0); t.setSuccessRows(0); t.setFailRows(0);
        taskMapper.insert(t);
        return t;
    }

    private void finishTask(OperationImportTask t)
    {
        t.setEndTime(new Date());
        if (!"PARTIAL".equals(t.getStatus()) && !"FAILED".equals(t.getStatus())) t.setStatus("SUCCESS");
        taskMapper.update(t);
        log.info("导入完成: type={}, success={}, fail={}", t.getTaskType(), t.getSuccessRows(), t.getFailRows());
    }

    private String mapSite(String name)
    {
        if (name == null) return null;
        String n = name.trim();
        if (n.contains("美国") || n.equalsIgnoreCase("US") || n.equalsIgnoreCase("USA") || n.equalsIgnoreCase("United States")) return "美国";
        if (n.contains("英国") || n.equalsIgnoreCase("UK") || n.equalsIgnoreCase("GB") || n.equalsIgnoreCase("United Kingdom")) return "英国";
        if (n.contains("德国") || n.equalsIgnoreCase("DE") || n.equalsIgnoreCase("GER") || n.equalsIgnoreCase("Germany")) return "德国";
        return null;
    }

    // -- Excel 工具 --
    private int[] findColumnIndexes(Row headerRow, String... headers)
    {
        int[] indexes = new int[headers.length];
        Arrays.fill(indexes, -1);
        if (headerRow == null) return indexes;
        for (Cell cell : headerRow)
        {
            String value = getCellStr(cell);
            if (value == null) continue;
            for (int i = 0; i < headers.length; i++)
            {
                if (value.equals(headers[i])) indexes[i] = cell.getColumnIndex();
            }
        }
        return indexes;
    }

    private int findColumnIndex(Row headerRow, int defaultIndex, String... headers)
    {
        if (headerRow == null) return defaultIndex;
        for (Cell cell : headerRow)
        {
            String value = getCellStr(cell);
            if (value == null) continue;
            for (String header : headers)
            {
                if (value.equalsIgnoreCase(header) || value.contains(header)) return cell.getColumnIndex();
            }
        }
        return defaultIndex;
    }

    private String getCellStr(Row row, int col) { return row == null || col < 0 ? null : getCellStr(row.getCell(col)); }
    private String getCellStr(Cell c)
    {
        if (c == null) return null;
        try
        {
            switch (c.getCellType())
            {
                case STRING:
                    String s = c.getStringCellValue();
                    return s == null || s.trim().isEmpty() ? null : s.trim();
                case NUMERIC:
                    if (DateUtil.isCellDateFormatted(c)) return new SimpleDateFormat("yyyy-MM-dd HH:mm:ss").format(c.getDateCellValue());
                    double d = c.getNumericCellValue();
                    if (d == Math.floor(d) && !Double.isInfinite(d)) return String.valueOf((long) d);
                    return String.valueOf(d);
                case BOOLEAN:
                    return String.valueOf(c.getBooleanCellValue());
                case FORMULA:
                    try { return String.valueOf(c.getNumericCellValue()); }
                    catch (Exception e) { String v = c.getStringCellValue(); return v == null || v.trim().isEmpty() ? null : v.trim(); }
                default:
                    return null;
            }
        }
        catch (Exception e) { return null; }
    }
    private Integer getCellInt(Row row, int col) { if (row == null || col < 0) return 0; Cell c = row.getCell(col); if (c == null) return 0; try { return (int) c.getNumericCellValue(); } catch (Exception e) { try { return Integer.parseInt(getCellStr(row, col)); } catch (Exception e2) { return 0; } } }
    private BigDecimal getCellDecimal(Row row, int col)
    {
        if (row == null || col < 0) return null;
        Cell c = row.getCell(col); if (c == null) return null;
        try { return BigDecimal.valueOf(c.getNumericCellValue()); }
        catch (Exception e)
        {
            try
            {
                String s = getCellStr(row, col);
                if (s == null) return null;
                boolean percent = s.endsWith("%");
                s = s.replace(",", "").replace("%", "").trim();
                if (s.isEmpty()) return null;
                BigDecimal val = new BigDecimal(s);
                return percent ? val.divide(BigDecimal.valueOf(100), 6, java.math.RoundingMode.HALF_UP) : val;
            }
            catch (Exception e2) { return null; }
        }
    }
    private String getCellDate(Row row, int col)
    {
        Cell c = row.getCell(col); if (c == null) return null;
        try
        {
            if (c.getCellType() == CellType.NUMERIC && DateUtil.isCellDateFormatted(c))
                return new SimpleDateFormat("yyyy-MM-dd HH:mm:ss").format(c.getDateCellValue());
            String s = getCellStr(c);
            if (s == null) return null;
            if (s.matches("\\d{4}-\\d{2}-\\d{2}(\\s+\\d{2}:\\d{2}:\\d{2})?"))
                return s.length() == 10 ? s + " 00:00:00" : s;
            if (s.matches("\\d{4}/\\d{1,2}/\\d{1,2}(\\s+\\d{1,2}:\\d{1,2}(:\\d{1,2})?)?"))
            {
                String normalized = s.replace('/', '-');
                return normalized.length() == 10 ? normalized + " 00:00:00" : normalized;
            }
            return null;
        }
        catch (Exception e) { return null; }
    }
    private boolean isEmptyRow(Row row) { for (int i = 0; i < 5; i++) if (row.getCell(i) != null && getCellStr(row, i) != null) return false; return true; }

    private static class PriceRecord { BigDecimal price; String itemNo; PriceRecord(BigDecimal p, String i) { price = p; itemNo = i; } }
}
