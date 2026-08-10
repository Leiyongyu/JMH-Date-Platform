package com.ruoyi.system.service.operation.ebay;

import java.io.InputStream;
import java.util.ArrayList;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Set;
import org.apache.poi.ss.usermodel.Cell;
import org.apache.poi.ss.usermodel.DataFormatter;
import org.apache.poi.ss.usermodel.FormulaEvaluator;
import org.apache.poi.ss.usermodel.Row;
import org.apache.poi.ss.usermodel.Sheet;
import org.apache.poi.ss.usermodel.Workbook;
import org.apache.poi.ss.usermodel.WorkbookFactory;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.multipart.MultipartFile;
import com.ruoyi.common.exception.ServiceException;
import com.ruoyi.system.domain.operation.ebay.EbaySkuOeMapping;
import com.ruoyi.system.mapper.operation.EbaySkuOeMappingMapper;

/**
 * SKU-OE 对照表导入：只覆盖本次文件中出现的 SKU。
 */
@Service
public class EbaySkuOeImportService
{
    private static final int SQL_BATCH_SIZE = 500;
    private static final int MAX_FILE_NAME_LENGTH = 255;

    private final EbaySkuOeMappingMapper mapper;

    public EbaySkuOeImportService(EbaySkuOeMappingMapper mapper)
    {
        this.mapper = mapper;
    }

    @Transactional(rollbackFor = Exception.class)
    public Map<String, Object> importMappings(MultipartFile file)
    {
        checkFile(file);
        ParsedWorkbook parsed = parse(file);
        if (parsed.skuToOes.isEmpty())
        {
            throw new ServiceException("未读取到有效的 sku、oe 对照数据");
        }

        List<String> skus = new ArrayList<>();
        parsed.skuToOes.values().forEach(entry -> skus.add(entry.sku));
        Set<String> existing = new HashSet<>();
        for (List<String> chunk : chunks(skus, SQL_BATCH_SIZE))
        {
            for (String sku : mapper.selectExistingSkus(chunk))
            {
                existing.add(key(sku));
            }
        }
        for (List<String> chunk : chunks(skus, SQL_BATCH_SIZE))
        {
            mapper.deleteBySkus(chunk);
        }

        String sourceFileName = truncate(file.getOriginalFilename(), MAX_FILE_NAME_LENGTH);
        List<EbaySkuOeMapping> rows = new ArrayList<>();
        for (SkuOes entry : parsed.skuToOes.values())
        {
            int index = 1;
            for (String oe : entry.oes)
            {
                EbaySkuOeMapping mapping = new EbaySkuOeMapping();
                mapping.setSku(entry.sku);
                mapping.setOe(oe);
                mapping.setOeIndex(index++);
                mapping.setSourceFileName(sourceFileName);
                rows.add(mapping);
            }
        }
        for (List<EbaySkuOeMapping> chunk : chunks(rows, SQL_BATCH_SIZE))
        {
            mapper.batchInsert(chunk);
        }

        int updated = 0;
        for (String sku : skus)
        {
            if (existing.contains(key(sku)))
            {
                updated++;
            }
        }
        LinkedHashMap<String, Object> result = new LinkedHashMap<>();
        result.put("totalRows", parsed.totalRows);
        result.put("affectedSkus", skus.size());
        result.put("createdSkus", skus.size() - updated);
        result.put("updatedSkus", updated);
        result.put("insertedMappings", rows.size());
        result.put("skippedRows", parsed.skippedRows);
        return result;
    }

    private ParsedWorkbook parse(MultipartFile file)
    {
        try (InputStream input = file.getInputStream(); Workbook workbook = WorkbookFactory.create(input))
        {
            if (workbook.getNumberOfSheets() == 0)
            {
                throw new ServiceException("Excel 文件没有工作表");
            }
            Sheet sheet = workbook.getSheetAt(0);
            Row header = sheet.getRow(sheet.getFirstRowNum());
            if (header == null)
            {
                throw new ServiceException("Excel 文件为空");
            }
            DataFormatter formatter = new DataFormatter(Locale.ROOT);
            FormulaEvaluator evaluator = workbook.getCreationHelper().createFormulaEvaluator();
            int skuColumn = -1;
            int oeColumn = -1;
            for (Cell cell : header)
            {
                String name = normalizeHeader(formatter.formatCellValue(cell, evaluator));
                if ("sku".equals(name))
                {
                    skuColumn = cell.getColumnIndex();
                }
                else if ("oe".equals(name))
                {
                    oeColumn = cell.getColumnIndex();
                }
            }
            if (skuColumn < 0 || oeColumn < 0)
            {
                throw new ServiceException("Excel 表头必须包含 sku 和 oe 两列");
            }

            LinkedHashMap<String, SkuOes> values = new LinkedHashMap<>();
            int totalRows = 0;
            int skippedRows = 0;
            for (int rowIndex = header.getRowNum() + 1; rowIndex <= sheet.getLastRowNum(); rowIndex++)
            {
                totalRows++;
                Row row = sheet.getRow(rowIndex);
                String sku = cellText(row, skuColumn, formatter, evaluator);
                String oeText = cellText(row, oeColumn, formatter, evaluator);
                List<String> oes = splitValues(oeText);
                if (sku.isBlank() || oes.isEmpty())
                {
                    skippedRows++;
                    continue;
                }
                SkuOes entry = values.computeIfAbsent(key(sku), ignored -> new SkuOes(sku));
                entry.addAll(oes);
            }
            return new ParsedWorkbook(values, totalRows, skippedRows);
        }
        catch (ServiceException e)
        {
            throw e;
        }
        catch (Exception e)
        {
            throw new ServiceException("SKU-OE 对照表解析失败: " + e.getMessage());
        }
    }

    private static void checkFile(MultipartFile file)
    {
        if (file == null || file.isEmpty())
        {
            throw new ServiceException("请选择要导入的 Excel 文件");
        }
        String name = file.getOriginalFilename() == null ? "" : file.getOriginalFilename().toLowerCase(Locale.ROOT);
        if (!name.endsWith(".xlsx") && !name.endsWith(".xlsm"))
        {
            throw new ServiceException("仅支持 .xlsx 或 .xlsm 文件");
        }
    }

    private static String cellText(Row row, int column, DataFormatter formatter, FormulaEvaluator evaluator)
    {
        if (row == null)
        {
            return "";
        }
        Cell cell = row.getCell(column);
        return cell == null ? "" : formatter.formatCellValue(cell, evaluator).trim();
    }

    private static String normalizeHeader(String value)
    {
        return value == null ? "" : value.toLowerCase(Locale.ROOT).replaceAll("[\\s_]", "");
    }

    static List<String> splitValues(String value)
    {
        LinkedHashMap<String, String> unique = new LinkedHashMap<>();
        if (value != null)
        {
            for (String part : value.split("[\\r\\n,，]+"))
            {
                String normalized = part.trim();
                if (!normalized.isEmpty())
                {
                    unique.putIfAbsent(key(normalized), normalized);
                }
            }
        }
        return new ArrayList<>(unique.values());
    }

    private static String key(String value)
    {
        return value == null ? "" : value.trim().toUpperCase(Locale.ROOT);
    }

    private static String truncate(String value, int maxLength)
    {
        if (value == null || value.length() <= maxLength)
        {
            return value;
        }
        return value.substring(0, maxLength);
    }

    private static <T> List<List<T>> chunks(List<T> values, int size)
    {
        List<List<T>> chunks = new ArrayList<>();
        for (int start = 0; start < values.size(); start += size)
        {
            chunks.add(values.subList(start, Math.min(start + size, values.size())));
        }
        return chunks;
    }

    private static final class SkuOes
    {
        private final String sku;
        private final List<String> oes = new ArrayList<>();
        private final Set<String> oeKeys = new LinkedHashSet<>();

        private SkuOes(String sku)
        {
            this.sku = sku;
        }

        private void addAll(List<String> values)
        {
            for (String value : values)
            {
                if (oeKeys.add(key(value)))
                {
                    oes.add(value);
                }
            }
        }
    }

    private static final class ParsedWorkbook
    {
        private final LinkedHashMap<String, SkuOes> skuToOes;
        private final int totalRows;
        private final int skippedRows;

        private ParsedWorkbook(LinkedHashMap<String, SkuOes> skuToOes, int totalRows, int skippedRows)
        {
            this.skuToOes = skuToOes;
            this.totalRows = totalRows;
            this.skippedRows = skippedRows;
        }
    }
}
