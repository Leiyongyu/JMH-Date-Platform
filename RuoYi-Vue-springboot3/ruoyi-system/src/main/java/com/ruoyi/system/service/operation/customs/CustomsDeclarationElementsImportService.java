package com.ruoyi.system.service.operation.customs;

import com.ruoyi.system.mapper.operation.customs.CustomsInventoryMapper;
import java.util.*;
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
            int skuCol = -1, declCol = -1, srcCol = -1, unitCol = -1, priceCol = -1;
            for (int c = 0; c < headerRow.getLastCellNum(); c++)
            {
                String v = getCellStr(headerRow, c);
                if (v == null) continue;
                if (v.contains("商品编码")) declCol = c;
                else if (v.contains("SKU")) skuCol = c;
                else if (v.contains("境内货源地")) srcCol = c;
                else if (v.contains("数量及单位") || v.contains("数量/单位")) unitCol = c;
                else if (v.contains("单价") && (v.contains("总价") || v.contains("币制"))) priceCol = c;
            }
            if (skuCol == -1) throw new IllegalArgumentException("未找到 SKU 列");
            if (declCol == -1) throw new IllegalArgumentException("未找到 商品编码 列");

            // 4. 读取数据行
            Map<String, String[]> dataMap = new LinkedHashMap<>(); // key: sku|sourceLocation → [declElements, sourceLocation]
            int readRows = 0, skippedRows = 0;
            for (int r = headerRowIdx + 1; r <= sheet.getLastRowNum(); r++)
            {
                Row row = sheet.getRow(r);
                if (row == null) { skippedRows++; continue; }
                String sku = getCellStr(row, skuCol);
                if (sku == null || sku.trim().isEmpty()) { skippedRows++; continue; }
                sku = sku.trim();
                String decl = getCellStr(row, declCol);
                if (decl == null || decl.trim().isEmpty()) { skippedRows++; continue; }
                decl = decl.trim();
                String src = getCellStr(row, srcCol);
                String srcLoc = (src != null) ? src.trim() : "";

                // 解析单位: "3个/9.4千克" → 取/前, 去掉数字和空格 → "个"
                String customsUnit = "";
                if (unitCol >= 0) {
                    String unitRaw = getCellStr(row, unitCol);
                    if (unitRaw != null && unitRaw.contains("/")) {
                        customsUnit = unitRaw.split("/")[0].replaceAll("[0-9.\\s]", "").trim();
                    }
                }

                // 解析单价: "42.74/128.22/USD" → 取第一个值
                String taxPrice = "";
                if (priceCol >= 0) {
                    String priceRaw = getCellStr(row, priceCol);
                    if (priceRaw != null && priceRaw.contains("/")) {
                        taxPrice = priceRaw.split("/")[0].trim();
                    }
                }

                readRows++;
                dataMap.put(sku + "|" + srcLoc, new String[]{decl, srcLoc, sku, customsUnit, taxPrice});
            }
            if (dataMap.isEmpty()) throw new IllegalArgumentException("Excel 中没有可导入数据");

            // 5. 查询已存在记录
            List<Map<String, Object>> keys = new ArrayList<>();
            for (Map.Entry<String, String[]> entry : dataMap.entrySet())
            {
                String[] parts = entry.getKey().split("\\|", 2);
                Map<String, Object> m = new HashMap<>();
                m.put("sku", parts[0]);
                m.put("sourceLocation", parts.length > 1 ? parts[1] : "");
                keys.add(m);
            }
            List<Map<String, Object>> existing = mapper.selectExistingSkuSource(keys);
            Set<String> existingSet = new HashSet<>();
            for (Map<String, Object> e : existing)
            {
                String src = e.get("sourceLocation") != null ? e.get("sourceLocation").toString() : "";
                existingSet.add(e.get("sku").toString() + "|" + src);
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

                Map<String, Object> row = new HashMap<>();
                row.put("sku", sku);
                row.put("sourceLocation", srcLoc);
                row.put("declarationElements", declElements);
                // vals[3] = customsUnit, vals[4] = taxPrice
                row.put("customsUnit", vals[3]);
                row.put("taxIncludedPrice", vals[4]);

                if (existingSet.contains(entry.getKey()))
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
            if (!toUpdate.isEmpty()) updatedRows = mapper.batchUpdateDeclarationElements(toUpdate);
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
        if (col < 0) return null;
        Cell cell = row.getCell(col);
        if (cell == null) return null;
        DataFormatter fmt = new DataFormatter();
        return fmt.formatCellValue(cell).trim();
    }
}
