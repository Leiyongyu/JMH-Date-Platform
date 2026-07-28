package com.ruoyi.system.service.finance;

import com.ruoyi.system.domain.operation.external.AmzPerformanceOwnerRule;
import com.ruoyi.system.mapper.operation.external.AmzPerformanceOwnerRuleMapper;
import java.time.YearMonth;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Set;
import java.util.regex.Matcher;
import java.util.regex.Pattern;
import org.apache.poi.ss.usermodel.DataFormatter;
import org.apache.poi.ss.usermodel.Row;
import org.apache.poi.ss.usermodel.Sheet;
import org.apache.poi.ss.usermodel.Workbook;
import org.apache.poi.ss.usermodel.WorkbookFactory;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.util.StringUtils;
import org.springframework.web.multipart.MultipartFile;

/** 负责人划分工作簿全组别、全月份增量导入。 */
@Service
public class PerformanceOwnerRuleImportService
{
    private static final int BATCH_SIZE = 300;
    private static final long MAX_FILE_SIZE = 10L * 1024L * 1024L;
    private static final Pattern OWNER_MONTH_HEADER =
            Pattern.compile("^(\\d{4})(\\d{2})负责人$");

    private final AmzPerformanceOwnerRuleMapper mapper;

    public PerformanceOwnerRuleImportService(AmzPerformanceOwnerRuleMapper mapper)
    {
        this.mapper = mapper;
    }

    @Transactional(rollbackFor = Exception.class)
    public Map<String, Object> importFile(MultipartFile file, String operator) throws Exception
    {
        checkFile(file);
        String sourceFileName = normalize(file.getOriginalFilename());
        List<AmzPerformanceOwnerRule> rows = new ArrayList<>();
        Set<String> importedSheets = new LinkedHashSet<>();
        Set<String> importedMonths = new LinkedHashSet<>();

        try (Workbook workbook = WorkbookFactory.create(file.getInputStream()))
        {
            parseSheet(workbook, "EU-品牌", "EU", "BRAND",
                    sourceFileName, operator, rows, importedMonths);
            importedSheets.add("EU-品牌");
            parseSheet(workbook, "EU-OTH", "EU", "OTH_CODE",
                    sourceFileName, operator, rows, importedMonths);
            importedSheets.add("EU-OTH");
            parseSheet(workbook, "US1", "US1", "STORE",
                    sourceFileName, operator, rows, importedMonths);
            importedSheets.add("US1");
            parseSheet(workbook, "US2", "US2", "STORE",
                    sourceFileName, operator, rows, importedMonths);
            importedSheets.add("US2");
        }

        if (rows.isEmpty())
            throw new IllegalArgumentException("四个负责人工作表中没有可导入的数据");

        int affectedRows = 0;
        for (int i = 0; i < rows.size(); i += BATCH_SIZE)
        {
            affectedRows += mapper.upsertBatch(rows.subList(i, Math.min(i + BATCH_SIZE, rows.size())));
        }

        Map<String, Object> result = new LinkedHashMap<>();
        result.put("importedRows", rows.size());
        result.put("affectedRows", affectedRows);
        result.put("sheets", importedSheets);
        result.put("groups", List.of("EU", "US1", "US2"));
        result.put("months", importedMonths);
        result.put("monthCount", importedMonths.size());
        return result;
    }

    public List<Map<String, Object>> summary(String statMonth)
    {
        return mapper.selectSummaryByMonth(normalizeMonth(statMonth));
    }

    private void parseSheet(
            Workbook workbook,
            String sheetName,
            String groupCode,
            String ruleType,
            String sourceFileName,
            String operator,
            List<AmzPerformanceOwnerRule> output,
            Set<String> importedMonths)
    {
        Sheet sheet = workbook.getSheet(sheetName);
        if (sheet == null)
            throw new IllegalArgumentException("Excel中缺少工作表：" + sheetName);

        DataFormatter formatter = new DataFormatter(Locale.CHINA);
        Row header = sheet.getRow(sheet.getFirstRowNum());
        if (header == null)
            throw new IllegalArgumentException("工作表“" + sheetName + "”表头为空");

        String keyHeader = sheetName.equals("EU-品牌") ? "品牌"
                : sheetName.equals("EU-OTH") ? "中间码-OTH" : "店铺名";
        int keyColumn = findColumn(header, keyHeader, formatter);
        if (keyColumn < 0)
            throw new IllegalArgumentException("工作表“" + sheetName
                    + "”缺少匹配键列：" + keyHeader);

        Map<Integer, String> ownerMonthColumns = findOwnerMonthColumns(header, formatter);
        if (ownerMonthColumns.isEmpty())
            throw new IllegalArgumentException("工作表“" + sheetName
                    + "”未找到“YYYYMM负责人”格式的月份列");

        Map<String, Integer> sourceRows = new LinkedHashMap<>();
        for (int i = sheet.getFirstRowNum() + 1; i <= sheet.getLastRowNum(); i++)
        {
            Row row = sheet.getRow(i);
            if (row == null) continue;
            String matchKey = normalize(formatter.formatCellValue(row.getCell(keyColumn)));

            for (Map.Entry<Integer, String> ownerColumn : ownerMonthColumns.entrySet())
            {
                String principalName = normalize(
                        formatter.formatCellValue(row.getCell(ownerColumn.getKey())));
                if ("待定".equals(principalName) || "待到".equals(principalName))
                    principalName = "未分配";
                if (!StringUtils.hasText(principalName)) continue;
                if (!StringUtils.hasText(matchKey))
                    throw new IllegalArgumentException("工作表“" + sheetName + "”第"
                            + (i + 1) + "行匹配键为空");

                String normalizedKey = matchKey;
                if ("BRAND".equals(ruleType) || "OTH_CODE".equals(ruleType))
                    normalizedKey = normalizedKey.toUpperCase(Locale.ROOT);

                String statMonth = ownerColumn.getValue();
                String duplicateKey = statMonth + "|" + groupCode + "|"
                        + ruleType + "|" + normalizedKey;
                Integer previousRow = sourceRows.putIfAbsent(duplicateKey, i + 1);
                if (previousRow != null)
                    throw new IllegalArgumentException("工作表“" + sheetName + "”第"
                            + previousRow + "行和第" + (i + 1)
                            + "行存在重复匹配键：" + normalizedKey);

                AmzPerformanceOwnerRule rule = new AmzPerformanceOwnerRule();
                rule.setStatMonth(statMonth);
                rule.setGroupCode(groupCode);
                rule.setRuleType(ruleType);
                rule.setMatchKey(normalizedKey);
                rule.setPrincipalName(principalName);
                rule.setSourceFileName(sourceFileName);
                rule.setSourceSheet(sheetName);
                rule.setSourceRow(i + 1);
                rule.setImportedBy(normalize(operator));
                output.add(rule);
                importedMonths.add(statMonth);
            }
        }
    }

    private Map<Integer, String> findOwnerMonthColumns(Row header, DataFormatter formatter)
    {
        Map<Integer, String> columns = new LinkedHashMap<>();
        for (int i = 0; i < header.getLastCellNum(); i++)
        {
            String value = normalize(formatter.formatCellValue(header.getCell(i)));
            Matcher matcher = OWNER_MONTH_HEADER.matcher(value);
            if (!matcher.matches()) continue;
            try
            {
                String statMonth = YearMonth.of(
                        Integer.parseInt(matcher.group(1)),
                        Integer.parseInt(matcher.group(2))).toString();
                columns.put(i, statMonth);
            }
            catch (Exception e)
            {
                throw new IllegalArgumentException("负责人月份列格式错误：" + value);
            }
        }
        return columns;
    }

    private int findColumn(Row header, String expected, DataFormatter formatter)
    {
        String target = normalize(expected);
        for (int i = 0; i < header.getLastCellNum(); i++)
        {
            if (target.equalsIgnoreCase(normalize(formatter.formatCellValue(header.getCell(i)))))
                return i;
        }
        return -1;
    }

    private void checkFile(MultipartFile file)
    {
        if (file == null || file.isEmpty())
            throw new IllegalArgumentException("请选择负责人划分Excel文件");
        if (file.getSize() > MAX_FILE_SIZE)
            throw new IllegalArgumentException("Excel文件不能超过10MB");
        String name = normalize(file.getOriginalFilename()).toLowerCase(Locale.ROOT);
        if (!name.endsWith(".xlsx") && !name.endsWith(".xls"))
            throw new IllegalArgumentException("只支持.xlsx或.xls格式");
    }

    private String normalizeMonth(String statMonth)
    {
        String value = normalize(statMonth);
        try
        {
            return YearMonth.parse(value).toString();
        }
        catch (Exception e)
        {
            throw new IllegalArgumentException("统计月份格式必须为YYYY-MM");
        }
    }

    private String normalize(String value)
    {
        return value == null ? "" : value.replace('\u00A0', ' ')
                .replace('\u3000', ' ').trim();
    }
}
