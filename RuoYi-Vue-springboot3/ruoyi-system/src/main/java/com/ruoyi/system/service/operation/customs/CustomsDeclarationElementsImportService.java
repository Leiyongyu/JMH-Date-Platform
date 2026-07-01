package com.ruoyi.system.service.operation.customs;

import com.ruoyi.system.mapper.operation.customs.CustomsInventoryMapper;
import java.util.*;
import java.util.regex.Matcher;
import java.util.regex.Pattern;
import org.apache.poi.ss.usermodel.*;
import org.apache.poi.xssf.usermodel.XSSFWorkbook;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.multipart.MultipartFile;

@Service
public class CustomsDeclarationElementsImportService
{
    private static final Logger LOG = LoggerFactory.getLogger(CustomsDeclarationElementsImportService.class);
    private static final String SHEET_NAME = "报关单";
    private static final Pattern DECLARATION_SKU_PATTERN = Pattern.compile("申报要素备注栏备注[:：]\\s*([A-Za-z0-9]+[-A-Za-z0-9]*)");
    private static final Pattern SKU_PATTERN = Pattern.compile("\\b[A-Za-z0-9]+(?:-[A-Za-z0-9]+)+\\b");

    private final CustomsInventoryMapper mapper;

    public CustomsDeclarationElementsImportService(CustomsInventoryMapper mapper) { this.mapper = mapper; }

    @Transactional
    public Map<String, Object> importDeclarationElements(MultipartFile file) throws Exception
    {
        // 1. 校验文件
        if (file == null || file.isEmpty()) throw new IllegalArgumentException("文件不能为空");
        String filename = file.getOriginalFilename();
        if (filename == null || !filename.toLowerCase().endsWith(".xlsx"))
            throw new IllegalArgumentException("仅支持 .xlsx 文件");

        Map<String, Object> result = new HashMap<>();

        try (Workbook wb = new XSSFWorkbook(file.getInputStream()))
        {
            FormulaEvaluator evaluator = wb.getCreationHelper().createFormulaEvaluator();
            // 2. 找到"报关单" sheet
            Sheet sheet = wb.getSheet(SHEET_NAME);
            if (sheet == null)
            {
                result.put("readRows", 0); result.put("insertedRows", 0); result.put("updatedRows", 0);
                result.put("skippedRows", 0); result.put("failedRows", 0);
                result.put("errors", Collections.singletonList("未找到名为'" + SHEET_NAME + "'的工作表"));
                return result;
            }

            // 3. 表头在第10行（0-indexed=9）
            int headerRowIdx = 9;
            Row headerRow = sheet.getRow(headerRowIdx);
            if (headerRow == null) throw new IllegalArgumentException("第10行表头为空");
            int skuCol = -1, declCol = -1, nameCol = -1, srcCol = -1, unitCol = -1, priceCol = -1;
            for (int c = 0; c < headerRow.getLastCellNum(); c++)
            {
                String v = getCellStr(headerRow, c, evaluator);
                if (v == null) continue;
                if (v.contains("商品编码")) declCol = c;
                else if (v.contains("商品名称")) nameCol = c;
                else if (v.contains("SKU")) skuCol = c;
                else if (v.contains("境内货源地")) srcCol = c;
                else if (v.contains("数量及单位") || v.contains("数量/单位")) unitCol = c;
                else if (v.contains("单价") && (v.contains("总价") || v.contains("币制"))) priceCol = c;
            }
            if (skuCol == -1) throw new IllegalArgumentException("未找到 SKU 列");
            if (declCol == -1) throw new IllegalArgumentException("未找到 商品编码 列");

            // 4. 读取数据行
            Map<String, String[]> dataMap = new LinkedHashMap<>(); // key: sku|sourceLocation → [declElements, sourceLocation, sku, customsUnit, taxPrice, productName]
            int readRows = 0, skippedRows = 0;
            for (int r = headerRowIdx + 1; r <= sheet.getLastRowNum(); r++)
            {
                Row row = sheet.getRow(r);
                if (row == null) { skippedRows++; continue; }
                String decl = getCellStr(row, declCol, evaluator);
                if (decl == null || decl.trim().isEmpty()) { skippedRows++; continue; }
                decl = decl.trim();
                String sku = getCellStr(row, skuCol, evaluator);
                if (isBlankSku(sku)) sku = extractSkuFromDeclaration(decl);
                if (sku == null || sku.trim().isEmpty()) { skippedRows++; continue; }
                sku = sku.trim();
                String src = getCellStr(row, srcCol, evaluator);
                String srcLoc = (src != null) ? src.trim() : "";
                String productName = "";
                if (nameCol >= 0) {
                    String name = getCellStr(row, nameCol, evaluator);
                    productName = name == null ? "" : name.trim();
                }

                // 解析单位: "3个/9.4千克" → 取/前, 去掉数字和空格 → "个"
                String customsUnit = "";
                if (unitCol >= 0) {
                    String unitRaw = getCellStr(row, unitCol, evaluator);
                    if (unitRaw != null && unitRaw.contains("/")) {
                        customsUnit = unitRaw.split("/")[0].replaceAll("[0-9.\\s]", "").trim();
                    }
                }

                // 解析单价: "42.74/128.22/USD" → 取第一个值
                String taxPrice = "";
                if (priceCol >= 0) {
                    String priceRaw = getCellStr(row, priceCol, evaluator);
                    if (priceRaw != null && priceRaw.contains("/")) {
                        taxPrice = priceRaw.split("/")[0].trim();
                    }
                }

                readRows++;
                dataMap.put(sku + "|" + srcLoc, new String[]{decl, srcLoc, sku, customsUnit, taxPrice, productName});
            }
            if (dataMap.isEmpty()) throw new IllegalArgumentException("Excel 中没有可导入数据");

            // 5. 查询已存在记录（全格式匹配 + 短格式兼容）
            List<Map<String, Object>> keys = new ArrayList<>();
            Set<String> seenSkus = new HashSet<>();
            for (String key : dataMap.keySet())
            {
                String sku = key.split("\\|")[0];
                if (seenSkus.add(sku)) {
                    Map<String, Object> m = new HashMap<>();
                    m.put("sku", sku);
                    keys.add(m);
                }
            }
            List<Map<String, Object>> existing = mapper.selectExistingSkuSource(keys);
            Set<String> existingSkuSources = new HashSet<>();
            Map<String, String> shortSourceToFull = new HashMap<>(); // 短格式+货源地→全格式映射
            for (Map<String, Object> e : existing)
            {
                String dbSku = e.get("sku").toString();
                String dbSource = e.get("sourceLocation") == null ? "" : e.get("sourceLocation").toString().trim();
                existingSkuSources.add(buildKey(dbSku, dbSource));
                // 提取短格式: JMH170044-0741 → 170044-0741, DAS-10623-0557 → 10623-0557
                String shortSku = dbSku.replaceFirst("^[A-Z]+-?", "");
                if (!shortSku.equals(dbSku)) shortSourceToFull.put(buildKey(shortSku, dbSource), dbSku);
            }

            // 6. 分类：更新 vs 新增
            List<Map<String, Object>> toUpdate = new ArrayList<>();
            List<Map<String, Object>> toInsert = new ArrayList<>();
            int failedRows = 0;
            List<String> errors = new ArrayList<>();

            for (Map.Entry<String, String[]> entry : dataMap.entrySet())
            {
                String[] parts = entry.getKey().split("\\|", 2);
                String[] vals = entry.getValue();
                String declElements = vals[0];
                String srcLoc = parts.length > 1 ? parts[1] : "";
                String sku = parts[0];

                // 全格式匹配或短格式匹配
                String matchedSku = sku;
                boolean exists = existingSkuSources.contains(buildKey(sku, srcLoc));
                if (!exists) {
                    String shortForm = sku.replaceFirst("^[A-Z]+-?", "");
                    String fullSku = shortSourceToFull.get(buildKey(shortForm, srcLoc));
                    if (fullSku != null) {
                        matchedSku = fullSku;
                        exists = true;
                    }
                }

                Map<String, Object> row = new HashMap<>();
                row.put("sku", matchedSku);
                row.put("sourceLocation", srcLoc);
                row.put("declarationElements", declElements);
                row.put("customsUnit", vals[3]);
                row.put("taxIncludedPrice", vals[4]);
                row.put("productName", vals[5]);
                if (exists)
                {
                    toUpdate.add(row);
                }
                else
                {
                    toInsert.add(row);
                }
            }

            // 7. 执行更新
            int updatedRows = 0, insertedRows = 0;
            for (Map<String, Object> item : toUpdate) {
                int rowCount = mapper.updateDeclarationElements(item);
                if (rowCount == 0) {
                    LOG.warn("更新申报要素未匹配: sku={}", item.get("sku"));
                }
                updatedRows += rowCount;
            }
            if (!toInsert.isEmpty()) insertedRows = mapper.batchInsertDeclarationRows(toInsert);

            result.put("readRows", readRows);
            result.put("insertedRows", insertedRows);
            result.put("updatedRows", updatedRows);
            result.put("skippedRows", skippedRows);
            result.put("failedRows", failedRows);
            result.put("errors", errors.subList(0, Math.min(50, errors.size())));
            LOG.info("申报要素导入完成: 读取{} 新增{} 更新{} 跳过{}", readRows, insertedRows, updatedRows, skippedRows);
        }
        return result;
    }

    private String getCellStr(Row row, int col)
    {
        return getCellStr(row, col, null);
    }

    private String getCellStr(Row row, int col, FormulaEvaluator evaluator)
    {
        if (col < 0) return null;
        Cell cell = row.getCell(col);
        if (cell == null) return null;
        DataFormatter fmt = new DataFormatter();
        try {
            return evaluator == null ? fmt.formatCellValue(cell).trim() : fmt.formatCellValue(cell, evaluator).trim();
        } catch (Exception e) {
            return fmt.formatCellValue(cell).trim();
        }
    }

    private boolean isBlankSku(String sku)
    {
        if (sku == null || sku.trim().isEmpty()) return true;
        String v = sku.trim();
        return v.startsWith("=") || v.contains("Packing List") || v.contains("合同!");
    }

    private String extractSkuFromDeclaration(String declarationElements)
    {
        if (declarationElements == null) return null;
        Matcher remarkMatcher = DECLARATION_SKU_PATTERN.matcher(declarationElements);
        if (remarkMatcher.find()) return remarkMatcher.group(1).trim();
        Matcher skuMatcher = SKU_PATTERN.matcher(declarationElements);
        String lastMatch = null;
        while (skuMatcher.find()) lastMatch = skuMatcher.group().trim();
        return lastMatch;
    }

    private String buildKey(String sku, String sourceLocation)
    {
        return (sku == null ? "" : sku.trim()) + "|" + (sourceLocation == null ? "" : sourceLocation.trim());
    }
}
