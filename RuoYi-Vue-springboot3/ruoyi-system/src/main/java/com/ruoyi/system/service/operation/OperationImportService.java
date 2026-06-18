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
    @Autowired private EbayPriceTrackingConfigMapper trackingConfigMapper;
    @Autowired private GoodcangProductInfoMapper productInfoMapper;

    // ========== 导入销量 ==========
    public OperationImportTask importEbaySales(MultipartFile file, String operator) throws Exception
    {
        OperationImportTask task = createTask(file.getOriginalFilename(), "EBAY_SALES", operator);
        try (InputStream is = file.getInputStream(); Workbook wb = new XSSFWorkbook(is))
        {
            Sheet sheet = wb.getSheetAt(0);
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
                    m.put("platformOrderNo", getCellStr(row, 0));
                    m.put("currency", getCellStr(row, 1));
                    m.put("sku", getCellStr(row, 2));
                    m.put("quantity", getCellInt(row, 3));
                    m.put("paymentTime", getCellDate(row, 4));
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
                int rows = Math.min(sheet.getLastRowNum(), MAX_ROWS);
                task.setTotalRows(task.getTotalRows() + rows);
                for (int i = 1; i <= rows; i++)
                {
                    Row row = sheet.getRow(i);
                    if (row == null || isEmptyRow(row)) continue;
                    try
                    {
                        String sku = getCellStr(row, 0);
                        String mid = InventoryUtils.extractMiddleCodeForInventory(sku);
                        if (mid.isEmpty()) continue;
                        BigDecimal rate = getCellDecimal(row, 1);
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
            int total = Math.min(sheet.getLastRowNum(), MAX_ROWS);
            task.setTotalRows(total);
            int success = 0;
            // 按 site + middleCode 更新
            Map<String, BigDecimal> updates = new LinkedHashMap<>();
            for (int i = 1; i <= total; i++)
            {
                Row row = sheet.getRow(i);
                if (row == null || isEmptyRow(row)) continue;
                try
                {
                    String sku = getCellStr(row, 0);
                    String site = mapSite(getCellStr(row, 1));
                    BigDecimal rate = getCellDecimal(row, 2);
                    if (sku == null || site == null || rate == null) continue;
                    String mid = InventoryUtils.extractMiddleCodeForInventory(sku);
                    if (mid.isEmpty()) continue;
                    updates.put(site + "|" + mid, rate);
                } catch (Exception ignored) {}
            }
            for (Map.Entry<String, BigDecimal> e : updates.entrySet())
            {
                String[] parts = e.getKey().split("\\|");
                if (parts.length == 2) { dedupMapper.updateReturnRate(parts[0], parts[1], e.getValue()); success++; }
            }
            task.setSuccessRows(success);
            task.setStatus("SUCCESS");
        }
        finishTask(task);
        return task;
    }

    // ========== 导入最低价 → ebay_price_tracking_config ==========
    public OperationImportTask importLowestPrice(MultipartFile file, String operator) throws Exception
    {
        OperationImportTask task = createTask(file.getOriginalFilename(), "LOWEST_PRICE", operator);
        try (InputStream is = file.getInputStream(); Workbook wb = new XSSFWorkbook(is))
        {
            Sheet sheet = wb.getSheetAt(0);
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
                    String sku = getCellStr(row, 0);
                    String site = getCellStr(row, 1);
                    BigDecimal price = getCellDecimal(row, 2);
                    String itemNo = getCellStr(row, 3);
                    if (sku == null || site == null || price == null) continue;
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
                    EbayPriceTrackingConfig cfg = getOrCreateConfig(parts[0], parts[1]);
                    cfg.setOurLowestPrice(e.getValue().price);
                    saveConfig(cfg);
                    success++;
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
            int total = Math.min(sheet.getLastRowNum(), MAX_ROWS);
            task.setTotalRows(total);
            int success = 0;
            for (int i = 1; i <= total; i++)
            {
                Row row = sheet.getRow(i);
                if (row == null || isEmptyRow(row)) continue;
                try
                {
                    String middleCode = getCellStr(row, 0);
                    BigDecimal price = getCellDecimal(row, 1);
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

    private EbayPriceTrackingConfig getOrCreateConfig(String site, String sku)
    {
        EbayPriceTrackingConfig c = trackingConfigMapper.selectBySiteSku(site, sku);
        if (c == null) { c = new EbayPriceTrackingConfig(); c.setSite(site); c.setSku(sku); }
        return c;
    }

    private void saveConfig(EbayPriceTrackingConfig c)
    {
        if (c.getId() != null) trackingConfigMapper.updateWithVersion(c);
        else trackingConfigMapper.insert(c);
    }

    private String mapSite(String name)
    {
        if (name == null) return null;
        String n = name.trim();
        if (n.contains("美国") || n.equalsIgnoreCase("US") || n.equalsIgnoreCase("USA")) return "美国";
        if (n.contains("英国") || n.equalsIgnoreCase("UK") || n.equalsIgnoreCase("GB")) return "英国";
        if (n.contains("德国") || n.equalsIgnoreCase("DE") || n.equalsIgnoreCase("GER")) return "德国";
        return null;
    }

    // -- Excel 工具 --
    private String getCellStr(Row row, int col) { Cell c = row.getCell(col); if (c == null) return null; c.setCellType(CellType.STRING); String v = c.getStringCellValue().trim(); return v.isEmpty() ? null : v; }
    private Integer getCellInt(Row row, int col) { Cell c = row.getCell(col); if (c == null) return 0; try { return (int) c.getNumericCellValue(); } catch (Exception e) { try { return Integer.parseInt(getCellStr(row, col)); } catch (Exception e2) { return 0; } } }
    private BigDecimal getCellDecimal(Row row, int col) { Cell c = row.getCell(col); if (c == null) return null; try { return BigDecimal.valueOf(c.getNumericCellValue()); } catch (Exception e) { try { return new BigDecimal(getCellStr(row, col)); } catch (Exception e2) { return null; } } }
    private String getCellDate(Row row, int col)
    {
        Cell c = row.getCell(col); if (c == null) return null;
        try { return new SimpleDateFormat("yyyy-MM-dd HH:mm:ss").format(c.getDateCellValue()); }
        catch (Exception e) { String s = getCellStr(row, col); return s != null ? s : null; }
    }
    private boolean isEmptyRow(Row row) { for (int i = 0; i < 5; i++) if (row.getCell(i) != null && getCellStr(row, i) != null) return false; return true; }

    private static class PriceRecord { BigDecimal price; String itemNo; PriceRecord(BigDecimal p, String i) { price = p; itemNo = i; } }
}
