package com.ruoyi.system.service.operation;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.ruoyi.system.domain.operation.OperationImportTask;
import com.ruoyi.system.mapper.operation.OperationImportTaskMapper;
import com.ruoyi.system.mapper.operation.external.EbayProductDedupMapper;
import com.ruoyi.system.mapper.operation.external.EbaySalesMapper;
import com.ruoyi.system.mapper.operation.external.GoodcangProductInfoMapper;
import com.ruoyi.system.service.operation.compute.InventoryUtils;
import java.io.InputStream;
import java.math.BigDecimal;
import java.text.SimpleDateFormat;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Date;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import org.apache.poi.ss.usermodel.Cell;
import org.apache.poi.ss.usermodel.CellType;
import org.apache.poi.ss.usermodel.DateUtil;
import org.apache.poi.ss.usermodel.Row;
import org.apache.poi.ss.usermodel.Sheet;
import org.apache.poi.ss.usermodel.Workbook;
import org.apache.poi.xssf.usermodel.XSSFWorkbook;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Service;
import org.springframework.web.multipart.MultipartFile;

@Service
public class OperationImportService
{
    private static final Logger log = LoggerFactory.getLogger(OperationImportService.class);
    private static final int MAX_ROWS = 50000;
    private static final int MAX_FAILURE_DETAILS = 500;
    private static final long MAX_FILE_SIZE = 20 * 1024 * 1024;

    @Autowired private OperationImportTaskMapper taskMapper;
    @Autowired private EbaySalesMapper ebaySalesMapper;
    @Autowired private EbayProductDedupMapper dedupMapper;
    @Autowired private GoodcangProductInfoMapper productInfoMapper;
    @Autowired private ObjectMapper objectMapper;

    public OperationImportTask importEbaySales(MultipartFile file, String operator) throws Exception
    {
        OperationImportTask task = createTask(fileName(file), "EBAY_SALES", operator);
        List<ImportFailure> failures = new ArrayList<>();
        try (InputStream is = openCheckedFile(file); Workbook wb = new XSSFWorkbook(is))
        {
            Sheet sheet = wb.getSheetAt(0);
            Row headerRow = sheet.getRow(0);
            int[] idx = findColumnIndexes(headerRow, "平台订单号", "币种", "库存SKU", "购买数量", "付款时间");
            int colOrderNo = idx[0], colCurrency = idx[1], colSku = idx[2], colQty = idx[3], colPayTime = idx[4];
            if (colOrderNo < 0 || colCurrency < 0 || colSku < 0 || colQty < 0 || colPayTime < 0)
            {
                addFailure(failures, 1, "", "销量导入文件缺少必要表头：平台订单号、币种、库存SKU、购买数量、付款时间");
                return failTask(task, failures.get(0).getReason(), failures);
            }

            int total = Math.min(sheet.getLastRowNum(), MAX_ROWS);
            task.setTotalRows(total);
            int success = 0;
            List<Map<String, Object>> batch = new ArrayList<>();

            for (int i = 1; i <= total; i++)
            {
                Row row = sheet.getRow(i);
                if (row == null || isEmptyRow(row)) continue;
                try
                {
                    String orderNo = getCellStr(row, colOrderNo);
                    String sku = getCellStr(row, colSku);
                    if (isBlank(orderNo) || isBlank(sku))
                    {
                        addFailure(failures, i + 1, sku, "订单号或SKU为空");
                        continue;
                    }
                    Map<String, Object> m = new LinkedHashMap<>();
                    m.put("platformOrderNo", orderNo);
                    m.put("currency", getCellStr(row, colCurrency));
                    m.put("sku", sku);
                    m.put("quantity", getCellInt(row, colQty));
                    m.put("paymentTime", getCellDate(row, colPayTime));
                    batch.add(m);
                    if (batch.size() >= 500)
                    {
                        ebaySalesMapper.batchUpsert(batch);
                        success += batch.size();
                        batch.clear();
                    }
                }
                catch (Exception e)
                {
                    addFailure(failures, i + 1, "", e.getMessage());
                }
            }
            if (!batch.isEmpty())
            {
                ebaySalesMapper.batchUpsert(batch);
                success += batch.size();
            }
            task.setSuccessRows(success);
            completeTask(task, failures);
            return task;
        }
        catch (Exception e)
        {
            if (failures.isEmpty()) addFailure(failures, null, "", e.getMessage());
            return failTask(task, e.getMessage(), failures);
        }
    }

    public OperationImportTask importProfitRate(MultipartFile file, String operator) throws Exception
    {
        OperationImportTask task = createTask(fileName(file), "PROFIT_RATE", operator);
        List<ImportFailure> failures = new ArrayList<>();
        try (InputStream is = openCheckedFile(file); Workbook wb = new XSSFWorkbook(is))
        {
            int success = 0;
            for (int s = 0; s < wb.getNumberOfSheets(); s++)
            {
                Sheet sheet = wb.getSheetAt(s);
                String site = mapSite(sheet.getSheetName());
                if (site == null)
                {
                    addFailure(failures, 1, sheet.getSheetName(), "未知站点 sheet，已跳过");
                    continue;
                }
                Row headerRow = sheet.getRow(0);
                int colSku = findColumnIndex(headerRow, 0, "SKU", "产品代码");
                int colRate = findColumnIndex(headerRow, 1, "Profit", "利润率");
                int rows = Math.min(sheet.getLastRowNum(), MAX_ROWS);
                task.setTotalRows(nvl(task.getTotalRows()) + rows);
                for (int i = 1; i <= rows; i++)
                {
                    Row row = sheet.getRow(i);
                    if (row == null || isEmptyRow(row)) continue;
                    try
                    {
                        String sku = getCellStr(row, colSku);
                        String mid = InventoryUtils.extractMiddleCodeForInventory(sku);
                        if (mid.isEmpty() && sku != null) mid = sku.trim();
                        BigDecimal rate = getCellDecimal(row, colRate);
                        if (mid.isEmpty())
                        {
                            addFailure(failures, i + 1, sku, "SKU为空或无法解析中间码");
                            continue;
                        }
                        if (rate == null)
                        {
                            addFailure(failures, i + 1, sku, "利润率为空或格式不正确");
                            continue;
                        }
                        int rowsUpdated = dedupMapper.updateProfitRate(site, mid, rate);
                        if (rowsUpdated > 0) success++;
                        else addFailure(failures, i + 1, sku, "未匹配到eBay商品记录");
                    }
                    catch (Exception e)
                    {
                        addFailure(failures, i + 1, "", e.getMessage());
                    }
                }
            }
            task.setSuccessRows(success);
            completeTask(task, failures);
            return task;
        }
        catch (Exception e)
        {
            if (failures.isEmpty()) addFailure(failures, null, "", e.getMessage());
            return failTask(task, e.getMessage(), failures);
        }
    }

    public OperationImportTask importReturnRate(MultipartFile file, String operator) throws Exception
    {
        OperationImportTask task = createTask(fileName(file), "RETURN_RATE", operator);
        List<ImportFailure> failures = new ArrayList<>();
        try (InputStream is = openCheckedFile(file); Workbook wb = new XSSFWorkbook(is))
        {
            Sheet sheet = wb.getSheetAt(0);
            Row headerRow = sheet.getRow(0);
            int colSku = findColumnIndex(headerRow, 0, "SKU", "产品SKU");
            int colSource = findColumnIndex(headerRow, -1, "数据来源");
            int colRate = findColumnIndex(headerRow, 4, "各平台售后率");
            int total = Math.min(sheet.getLastRowNum(), MAX_ROWS);
            task.setTotalRows(total);
            Map<String, BigDecimal> updates = new LinkedHashMap<>();
            String lastSku = null;

            for (int i = 1; i <= total; i++)
            {
                Row row = sheet.getRow(i);
                if (row == null || isEmptyRow(row)) continue;
                try
                {
                    String sku = getCellStr(row, colSku);
                    if (!isBlank(sku)) lastSku = sku;
                    else sku = lastSku;
                    if (colSource >= 0)
                    {
                        String source = getCellStr(row, colSource);
                        if (source == null || !"ebay".equalsIgnoreCase(source.trim())) continue;
                    }
                    BigDecimal rate = getCellDecimal(row, colRate);
                    if (isBlank(sku))
                    {
                        addFailure(failures, i + 1, "", "SKU为空");
                        continue;
                    }
                    if (rate == null)
                    {
                        addFailure(failures, i + 1, sku, "退货率为空或格式不正确");
                        continue;
                    }
                    String mid = InventoryUtils.extractMiddleCodeForInventory(sku);
                    if (mid.isEmpty()) mid = sku.trim();
                    updates.putIfAbsent(mid, rate);
                }
                catch (Exception e)
                {
                    addFailure(failures, i + 1, "", e.getMessage());
                }
            }

            int success = 0;
            for (Map.Entry<String, BigDecimal> e : updates.entrySet())
            {
                int rows = dedupMapper.updateReturnRateByMiddleCode(e.getKey(), e.getValue());
                if (rows > 0) success++;
                else addFailure(failures, null, e.getKey(), "未匹配到eBay商品记录");
            }
            task.setSuccessRows(success);
            completeTask(task, failures);
            return task;
        }
        catch (Exception e)
        {
            if (failures.isEmpty()) addFailure(failures, null, "", e.getMessage());
            return failTask(task, e.getMessage(), failures);
        }
    }

    public OperationImportTask importLowestPrice(MultipartFile file, String operator) throws Exception
    {
        OperationImportTask task = createTask(fileName(file), "LOWEST_PRICE", operator);
        List<ImportFailure> failures = new ArrayList<>();
        try (InputStream is = openCheckedFile(file); Workbook wb = new XSSFWorkbook(is))
        {
            Sheet sheet = wb.getSheetAt(0);
            Row headerRow = sheet.getRow(0);
            int colSku = findColumnIndex(headerRow, 0, "SKU");
            int colSite = findColumnIndex(headerRow, 1, "站点", "Site");
            int colPrice = findColumnIndex(headerRow, 2, "价格", "Price");
            int colItemNo = findColumnIndex(headerRow, -1, "Item Number");
            int total = Math.min(sheet.getLastRowNum(), MAX_ROWS);
            task.setTotalRows(total);
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
                    if (isBlank(sku) || site == null || price == null)
                    {
                        addFailure(failures, i + 1, sku, "SKU、站点或价格为空/格式不正确");
                        continue;
                    }
                    String key = site + "|" + sku;
                    PriceRecord pr = best.get(key);
                    if (pr == null || price.compareTo(pr.price) < 0) best.put(key, new PriceRecord(price, itemNo));
                }
                catch (Exception e)
                {
                    addFailure(failures, i + 1, "", e.getMessage());
                }
            }

            int success = 0;
            for (Map.Entry<String, PriceRecord> e : best.entrySet())
            {
                String[] parts = e.getKey().split("\\|", 2);
                int rows = dedupMapper.updateLowestPrice(parts[0], parts[1], e.getValue().price, e.getValue().itemNo);
                if (rows > 0) success++;
                else addFailure(failures, null, e.getKey(), "未匹配到eBay商品记录");
            }
            task.setSuccessRows(success);
            completeTask(task, failures);
            return task;
        }
        catch (Exception e)
        {
            if (failures.isEmpty()) addFailure(failures, null, "", e.getMessage());
            return failTask(task, e.getMessage(), failures);
        }
    }

    public OperationImportTask importProductPrice(MultipartFile file, String operator) throws Exception
    {
        OperationImportTask task = createTask(fileName(file), "PRODUCT_PRICE", operator);
        List<ImportFailure> failures = new ArrayList<>();
        try (InputStream is = openCheckedFile(file); Workbook wb = new XSSFWorkbook(is))
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
                    if (isBlank(middleCode) || price == null)
                    {
                        addFailure(failures, i + 1, middleCode, "中间码或单价为空/格式不正确");
                        continue;
                    }
                    int rows = productInfoMapper.updatePrice(middleCode, price);
                    if (rows > 0) success++;
                    else addFailure(failures, i + 1, middleCode, "未匹配到谷仓商品记录");
                }
                catch (Exception e)
                {
                    addFailure(failures, i + 1, "", e.getMessage());
                }
            }
            task.setSuccessRows(success);
            completeTask(task, failures);
            return task;
        }
        catch (Exception e)
        {
            if (failures.isEmpty()) addFailure(failures, null, "", e.getMessage());
            return failTask(task, e.getMessage(), failures);
        }
    }

    private OperationImportTask createTask(String fileName, String type, String operator)
    {
        OperationImportTask t = new OperationImportTask();
        t.setFileName(fileName);
        t.setTaskType(type);
        t.setOperator(operator);
        t.setStatus("RUNNING");
        t.setTotalRows(0);
        t.setSuccessRows(0);
        t.setFailRows(0);
        taskMapper.insert(t);
        return t;
    }

    private void completeTask(OperationImportTask task, List<ImportFailure> failures)
    {
        int failCount = failures != null ? failures.size() : 0;
        task.setFailRows(failCount);
        task.setStatus(failCount == 0 ? "SUCCESS" : (nvl(task.getSuccessRows()) > 0 ? "PARTIAL" : "FAILED"));
        task.setFailDetailJson(toJson(failures));
        finishTask(task);
    }

    private OperationImportTask failTask(OperationImportTask task, String message, List<ImportFailure> failures)
    {
        task.setSuccessRows(nvl(task.getSuccessRows()));
        task.setFailRows(failures != null && !failures.isEmpty() ? failures.size() : 1);
        task.setStatus("FAILED");
        task.setFailDetailJson(toJson(failures));
        task.setErrorFilePath(message);
        finishTask(task);
        return task;
    }

    private void finishTask(OperationImportTask t)
    {
        t.setEndTime(new Date());
        if (!"PARTIAL".equals(t.getStatus()) && !"FAILED".equals(t.getStatus())) t.setStatus("SUCCESS");
        taskMapper.update(t);
        log.info("导入完成: type={}, success={}, fail={}", t.getTaskType(), t.getSuccessRows(), t.getFailRows());
    }

    private InputStream openCheckedFile(MultipartFile file) throws Exception
    {
        if (file == null || file.isEmpty()) throw new IllegalArgumentException("上传文件不能为空");
        if (file.getSize() > MAX_FILE_SIZE) throw new IllegalArgumentException("上传文件不能超过20MB");
        return file.getInputStream();
    }

    private String fileName(MultipartFile file)
    {
        return file != null ? file.getOriginalFilename() : "";
    }

    private void addFailure(List<ImportFailure> failures, Integer rowNumber, String key, String reason)
    {
        if (failures.size() >= MAX_FAILURE_DETAILS) return;
        failures.add(new ImportFailure(rowNumber, key, reason));
    }

    private String toJson(List<ImportFailure> failures)
    {
        if (failures == null || failures.isEmpty()) return null;
        try { return objectMapper.writeValueAsString(failures); }
        catch (JsonProcessingException e) { return null; }
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
                    return isBlank(s) ? null : s.trim();
                case NUMERIC:
                    if (DateUtil.isCellDateFormatted(c)) return new SimpleDateFormat("yyyy-MM-dd HH:mm:ss").format(c.getDateCellValue());
                    double d = c.getNumericCellValue();
                    if (d == Math.floor(d) && !Double.isInfinite(d)) return String.valueOf((long) d);
                    return String.valueOf(d);
                case BOOLEAN:
                    return String.valueOf(c.getBooleanCellValue());
                case FORMULA:
                    try { return String.valueOf(c.getNumericCellValue()); }
                    catch (Exception e) { String v = c.getStringCellValue(); return isBlank(v) ? null : v.trim(); }
                default:
                    return null;
            }
        }
        catch (Exception e) { return null; }
    }

    private Integer getCellInt(Row row, int col)
    {
        if (row == null || col < 0) return 0;
        Cell c = row.getCell(col);
        if (c == null) return 0;
        try { return (int) c.getNumericCellValue(); }
        catch (Exception e) {
            try { return Integer.parseInt(getCellStr(row, col)); }
            catch (Exception e2) { return 0; }
        }
    }

    private BigDecimal getCellDecimal(Row row, int col)
    {
        if (row == null || col < 0) return null;
        Cell c = row.getCell(col);
        if (c == null) return null;
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
        if (row == null || col < 0) return null;
        Cell c = row.getCell(col);
        if (c == null) return null;
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

    private boolean isEmptyRow(Row row)
    {
        for (int i = 0; i < 5; i++) if (row.getCell(i) != null && getCellStr(row, i) != null) return false;
        return true;
    }

    private boolean isBlank(String text)
    {
        return text == null || text.trim().isEmpty();
    }

    private int nvl(Integer value)
    {
        return value != null ? value : 0;
    }

    private static class PriceRecord
    {
        BigDecimal price;
        String itemNo;
        PriceRecord(BigDecimal price, String itemNo) { this.price = price; this.itemNo = itemNo; }
    }

    public static class ImportFailure
    {
        private Integer rowNumber;
        private String key;
        private String reason;

        public ImportFailure() {}

        public ImportFailure(Integer rowNumber, String key, String reason)
        {
            this.rowNumber = rowNumber;
            this.key = key;
            this.reason = reason;
        }

        public Integer getRowNumber() { return rowNumber; }
        public void setRowNumber(Integer rowNumber) { this.rowNumber = rowNumber; }
        public String getKey() { return key; }
        public void setKey(String key) { this.key = key; }
        public String getReason() { return reason; }
        public void setReason(String reason) { this.reason = reason; }
    }
}
