package com.ruoyi.system.service.finance;

import com.ruoyi.system.domain.operation.external.EbayPerformanceOwnerRule;
import com.ruoyi.system.domain.operation.external.EbayPerformanceProfit;
import com.ruoyi.system.mapper.operation.external.EbayPerformanceOwnerRuleMapper;
import com.ruoyi.system.mapper.operation.external.EbayPerformanceProfitMapper;
import java.math.BigDecimal;
import java.math.RoundingMode;
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
import org.apache.poi.ss.usermodel.Cell;
import org.apache.poi.ss.usermodel.CellType;
import org.apache.poi.ss.usermodel.DataFormatter;
import org.apache.poi.ss.usermodel.Row;
import org.apache.poi.ss.usermodel.Sheet;
import org.apache.poi.ss.usermodel.Workbook;
import org.apache.poi.ss.usermodel.WorkbookFactory;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.util.StringUtils;
import org.springframework.web.multipart.MultipartFile;

/** eBay 月度绩效利润及品牌负责人 Excel 导入。 */
@Service
public class EbayPerformanceImportService
{
    private static final int BATCH_SIZE = 300;
    private static final long MAX_FILE_SIZE = 20L * 1024L * 1024L;
    private static final Pattern FILE_MONTH =
            Pattern.compile("(?<!\\d)(20\\d{2})(0[1-9]|1[0-2])(?!\\d)");
    private static final Pattern OWNER_MONTH_HEADER =
            Pattern.compile("^(\\d{4})(\\d{2})负责人$");
    private static final Pattern PACK_QUANTITY_PREFIX =
            Pattern.compile("^\\d+PC$", Pattern.CASE_INSENSITIVE);

    private final EbayPerformanceProfitMapper profitMapper;
    private final EbayPerformanceOwnerRuleMapper ownerRuleMapper;

    public EbayPerformanceImportService(
            EbayPerformanceProfitMapper profitMapper,
            EbayPerformanceOwnerRuleMapper ownerRuleMapper)
    {
        this.profitMapper = profitMapper;
        this.ownerRuleMapper = ownerRuleMapper;
    }

    /**
     * 月度利润文件是整月全量文件。同月再次导入时整月覆盖，
     * 以保留文件中可能出现的重复 SKU 行及其完整金额。
     */
    @Transactional(rollbackFor = Exception.class)
    public Map<String, Object> importProfit(MultipartFile file, String operator) throws Exception
    {
        checkFile(file, "eBay月度利润表");
        String sourceFileName = normalize(file.getOriginalFilename());
        String statMonth = extractMonth(sourceFileName);
        List<EbayPerformanceProfit> rows = new ArrayList<>();
        BigDecimal grossProfitTotal = BigDecimal.ZERO;
        BigDecimal productSalesTotal = BigDecimal.ZERO;
        BigDecimal receivableShippingTotal = BigDecimal.ZERO;
        BigDecimal salesTotal = BigDecimal.ZERO;
        BigDecimal refundTotal = BigDecimal.ZERO;

        try (Workbook workbook = WorkbookFactory.create(file.getInputStream()))
        {
            Sheet sheet = findSheet(workbook, "sheet1");
            DataFormatter formatter = new DataFormatter(Locale.CHINA);
            Row header = sheet.getRow(sheet.getFirstRowNum());
            if (header == null)
                throw new IllegalArgumentException("工作表“sheet1”表头为空");

            int skuColumn = requiredColumn(header, "SKU", formatter, sheet.getSheetName());
            int imageColumn = requiredColumn(header, "图片", formatter, sheet.getSheetName());
            int multiVariantColumn = requiredColumn(
                    header, "是否多属性", formatter, sheet.getSheetName());
            int grossProfitColumn = requiredColumn(
                    header, "利润", formatter, sheet.getSheetName());
            int productSalesColumn = requiredColumn(
                    header, "商品销售额", formatter, sheet.getSheetName());
            int receivableShippingColumn = requiredColumn(
                    header, "应收运费", formatter, sheet.getSheetName());
            int refundColumn = requiredColumn(
                    header, "退款金额", formatter, sheet.getSheetName());

            for (int i = sheet.getFirstRowNum() + 1; i <= sheet.getLastRowNum(); i++)
            {
                Row row = sheet.getRow(i);
                if (row == null) continue;
                String sku = normalize(formatter.formatCellValue(row.getCell(skuColumn)));
                BigDecimal grossProfit = decimal(
                        row.getCell(grossProfitColumn), formatter, i + 1, "利润");
                BigDecimal productSalesAmount = decimal(
                        row.getCell(productSalesColumn), formatter, i + 1, "商品销售额");
                BigDecimal receivableShippingAmount = decimal(
                        row.getCell(receivableShippingColumn), formatter, i + 1, "应收运费");
                BigDecimal salesAmount =
                        productSalesAmount.add(receivableShippingAmount);
                BigDecimal refundAmount = decimal(
                        row.getCell(refundColumn), formatter, i + 1, "退款金额");

                if (!StringUtils.hasText(sku)
                        && grossProfit.signum() == 0
                        && productSalesAmount.signum() == 0
                        && receivableShippingAmount.signum() == 0
                        && refundAmount.signum() == 0)
                    continue;
                if (!StringUtils.hasText(sku))
                    sku = "[SKU 未填写]";

                EbayPerformanceProfit profit = new EbayPerformanceProfit();
                profit.setStatMonth(statMonth);
                profit.setSku(sku);
                profit.setBrandCode(extractBrand(sku));
                profit.setImageUrl(normalize(
                        formatter.formatCellValue(row.getCell(imageColumn))));
                profit.setMultiVariant(normalize(
                        formatter.formatCellValue(row.getCell(multiVariantColumn))));
                profit.setGrossProfit(grossProfit);
                profit.setProductSalesAmount(productSalesAmount);
                profit.setReceivableShippingAmount(receivableShippingAmount);
                profit.setSalesAmount(salesAmount);
                profit.setRefundAmount(refundAmount);
                profit.setNetSalesAmount(salesAmount.subtract(refundAmount));
                profit.setSourceFileName(sourceFileName);
                profit.setSourceSheet(sheet.getSheetName());
                profit.setSourceRow(i + 1);
                profit.setImportedBy(normalize(operator));
                rows.add(profit);

                grossProfitTotal = grossProfitTotal.add(grossProfit);
                productSalesTotal = productSalesTotal.add(productSalesAmount);
                receivableShippingTotal =
                        receivableShippingTotal.add(receivableShippingAmount);
                salesTotal = salesTotal.add(salesAmount);
                refundTotal = refundTotal.add(refundAmount);
            }
        }

        if (rows.isEmpty())
            throw new IllegalArgumentException("eBay月度利润表中没有可导入的数据");

        profitMapper.deleteByStatMonth(statMonth);
        int insertedRows = 0;
        for (int i = 0; i < rows.size(); i += BATCH_SIZE)
        {
            insertedRows += profitMapper.insertBatch(
                    rows.subList(i, Math.min(i + BATCH_SIZE, rows.size())));
        }

        Map<String, Object> result = new LinkedHashMap<>();
        result.put("statMonth", statMonth);
        result.put("totalRows", rows.size());
        result.put("insertedRows", insertedRows);
        result.put("grossProfit", grossProfitTotal);
        result.put("productSalesAmount", productSalesTotal);
        result.put("receivableShippingAmount", receivableShippingTotal);
        result.put("salesAmount", salesTotal);
        result.put("refundAmount", refundTotal);
        result.put("netSalesAmount", salesTotal.subtract(refundTotal));
        return result;
    }

    /** 负责人表按月份和品牌增量覆盖，其余月份及品牌规则保留。 */
    @Transactional(rollbackFor = Exception.class)
    public Map<String, Object> importOwnerRules(
            MultipartFile file, String operator) throws Exception
    {
        checkFile(file, "eBay负责人配置");
        String sourceFileName = normalize(file.getOriginalFilename());
        List<EbayPerformanceOwnerRule> rows = new ArrayList<>();
        Set<String> importedMonths = new LinkedHashSet<>();
        Map<String, Integer> sourceRows = new LinkedHashMap<>();
        String sourceSheet;

        try (Workbook workbook = WorkbookFactory.create(file.getInputStream()))
        {
            Sheet sheet = findSheet(workbook, "Sheet1");
            sourceSheet = sheet.getSheetName();
            DataFormatter formatter = new DataFormatter(Locale.CHINA);
            Row header = sheet.getRow(sheet.getFirstRowNum());
            if (header == null)
                throw new IllegalArgumentException("工作表“Sheet1”表头为空");
            int brandColumn = requiredColumn(
                    header, "品牌", formatter, sheet.getSheetName());
            Map<Integer, String> monthColumns = findOwnerMonthColumns(header, formatter);
            if (monthColumns.isEmpty())
                throw new IllegalArgumentException(
                        "工作表“Sheet1”未找到“YYYYMM负责人”格式的月份列");

            for (int i = sheet.getFirstRowNum() + 1; i <= sheet.getLastRowNum(); i++)
            {
                Row row = sheet.getRow(i);
                if (row == null) continue;
                String brandCode = normalize(
                        formatter.formatCellValue(row.getCell(brandColumn)))
                        .toUpperCase(Locale.ROOT);

                for (Map.Entry<Integer, String> monthColumn : monthColumns.entrySet())
                {
                    String principalName = normalize(
                            formatter.formatCellValue(row.getCell(monthColumn.getKey())));
                    if (!StringUtils.hasText(principalName)) continue;
                    if (!StringUtils.hasText(brandCode))
                        throw new IllegalArgumentException("工作表“Sheet1”第"
                                + (i + 1) + "行品牌为空");
                    if ("待定".equals(principalName) || "待到".equals(principalName))
                        principalName = "未分配";

                    String statMonth = monthColumn.getValue();
                    String duplicateKey = statMonth + "|" + brandCode;
                    Integer previousRow = sourceRows.putIfAbsent(duplicateKey, i + 1);
                    if (previousRow != null)
                        throw new IllegalArgumentException("工作表“Sheet1”第"
                                + previousRow + "行和第" + (i + 1)
                                + "行品牌重复：" + brandCode);

                    EbayPerformanceOwnerRule rule = new EbayPerformanceOwnerRule();
                    rule.setStatMonth(statMonth);
                    rule.setBrandCode(brandCode);
                    rule.setPrincipalName(principalName);
                    rule.setSourceFileName(sourceFileName);
                    rule.setSourceSheet(sourceSheet);
                    rule.setSourceRow(i + 1);
                    rule.setImportedBy(normalize(operator));
                    rows.add(rule);
                    importedMonths.add(statMonth);
                }
            }
        }

        if (rows.isEmpty())
            throw new IllegalArgumentException("eBay负责人配置中没有可导入的数据");

        int affectedRows = 0;
        for (int i = 0; i < rows.size(); i += BATCH_SIZE)
        {
            affectedRows += ownerRuleMapper.upsertBatch(
                    rows.subList(i, Math.min(i + BATCH_SIZE, rows.size())));
        }

        Map<String, Object> result = new LinkedHashMap<>();
        result.put("importedRows", rows.size());
        result.put("affectedRows", affectedRows);
        result.put("sheet", sourceSheet);
        result.put("months", importedMonths);
        result.put("monthCount", importedMonths.size());
        return result;
    }

    public List<Map<String, Object>> ownerRuleSummary(String statMonth)
    {
        return ownerRuleMapper.selectSummaryByMonth(normalizeMonth(statMonth));
    }

    private Map<Integer, String> findOwnerMonthColumns(
            Row header, DataFormatter formatter)
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

    private int requiredColumn(
            Row header, String expected, DataFormatter formatter, String sheetName)
    {
        for (int i = 0; i < header.getLastCellNum(); i++)
        {
            if (expected.equalsIgnoreCase(normalize(
                    formatter.formatCellValue(header.getCell(i)))))
                return i;
        }
        throw new IllegalArgumentException(
                "工作表“" + sheetName + "”缺少列：" + expected);
    }

    private Sheet findSheet(Workbook workbook, String expectedName)
    {
        for (int i = 0; i < workbook.getNumberOfSheets(); i++)
        {
            Sheet sheet = workbook.getSheetAt(i);
            if (expectedName.equalsIgnoreCase(normalize(sheet.getSheetName())))
                return sheet;
        }
        throw new IllegalArgumentException("Excel中缺少工作表：" + expectedName);
    }

    private String extractMonth(String fileName)
    {
        Matcher matcher = FILE_MONTH.matcher(fileName);
        if (!matcher.find())
            throw new IllegalArgumentException(
                    "利润表文件名必须包含年月，例如：ebay-202606-利润表.xlsx");
        return YearMonth.of(
                Integer.parseInt(matcher.group(1)),
                Integer.parseInt(matcher.group(2))).toString();
    }

    private String extractBrand(String sku)
    {
        String[] parts = sku.split("-", 3);
        String brand = parts[0];
        if (parts.length > 1 && PACK_QUANTITY_PREFIX.matcher(brand).matches())
            brand = parts[1];
        return normalize(brand).toUpperCase(Locale.ROOT);
    }

    private BigDecimal decimal(
            Cell cell,
            DataFormatter formatter,
            int rowNumber,
            String columnName)
    {
        if (cell == null) return BigDecimal.ZERO;
        CellType cellType = cell.getCellType();
        if (cellType == CellType.NUMERIC
                || (cellType == CellType.FORMULA
                    && cell.getCachedFormulaResultType() == CellType.NUMERIC))
            return BigDecimal.valueOf(cell.getNumericCellValue())
                    .setScale(6, RoundingMode.HALF_UP);

        String rawValue = formatter.formatCellValue(cell);
        String value = normalize(rawValue);
        if (!StringUtils.hasText(value) || "-".equals(value))
            return BigDecimal.ZERO;
        boolean negativeParentheses = value.startsWith("(") && value.endsWith(")");
        if (negativeParentheses)
            value = value.substring(1, value.length() - 1);
        value = value.replace(",", "")
                .replace("￥", "")
                .replace("¥", "")
                .replace("$", "")
                .replace(" ", "");
        try
        {
            BigDecimal number = new BigDecimal(value);
            return (negativeParentheses ? number.negate() : number)
                    .setScale(6, RoundingMode.HALF_UP);
        }
        catch (Exception e)
        {
            throw new IllegalArgumentException("第" + rowNumber + "行“"
                    + columnName + "”不是有效数字：" + rawValue);
        }
    }

    private void checkFile(MultipartFile file, String label)
    {
        if (file == null || file.isEmpty())
            throw new IllegalArgumentException("请选择" + label + "Excel文件");
        if (file.getSize() > MAX_FILE_SIZE)
            throw new IllegalArgumentException("Excel文件不能超过20MB");
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
