package com.ruoyi.system.service.operation.ebay;

import com.ruoyi.common.exception.ServiceException;
import com.ruoyi.system.domain.operation.ebay.EbayWarehouseRentAggregate;
import com.ruoyi.system.domain.operation.ebay.EbayWarehouseRentDetail;
import com.ruoyi.system.mapper.operation.ebay.EbayWarehouseRentMapper;
import java.io.InputStream;
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.UUID;
import org.apache.poi.openxml4j.opc.OPCPackage;
import org.apache.poi.ss.usermodel.DataFormatter;
import org.apache.poi.ss.util.CellReference;
import org.apache.poi.util.XMLHelper;
import org.apache.poi.xssf.eventusermodel.ReadOnlySharedStringsTable;
import org.apache.poi.xssf.eventusermodel.XSSFReader;
import org.apache.poi.xssf.eventusermodel.XSSFSheetXMLHandler;
import org.apache.poi.xssf.model.SharedStrings;
import org.apache.poi.xssf.model.StylesTable;
import org.apache.poi.xssf.usermodel.XSSFComment;
import org.springframework.stereotype.Service;
import org.springframework.util.StringUtils;
import org.springframework.web.multipart.MultipartFile;
import org.xml.sax.Attributes;
import org.xml.sax.InputSource;
import org.xml.sax.XMLReader;
import org.xml.sax.helpers.DefaultHandler;

/** eBay补货2.0仓租明细导入、汇总与列表回填。 */
@Service
public class EbayWarehouseRentService
{
    private static final long MAX_FILE_SIZE = 20L * 1024L * 1024L;
    private static final int MAX_DATA_ROWS = 200_000;
    private static final int MAX_REPORTED_ERRORS = 20;
    private static final String TARGET_SHEET = "仓租明细";

    private static final List<String> EXPECTED_HEADERS = List.of(
            "单号", "仓库", "商品编码", "谷仓商品条码", "产品名称",
            "参考编号", "计费时间", "上架时间", "尺寸（长*宽*高）",
            "数量", "体积(m3)", "商品重量(KG)", "仓租金额(不含税)",
            "计费币种", "库龄(天)", "货型", "计费类型",
            "存储物理形态", "旺季附加费(不含税)",
            "超库龄附加费(不含税)", "超尺寸附加费(不含税)",
            "总金额(不含税)");

    private static final Map<String, String> WAREHOUSE_SITE_MAP = Map.of(
            "DE", "德国",
            "CZ", "德国",
            "IT", "德国",
            "UK", "英国",
            "USEW", "美国",
            "USWE", "美国",
            "USEA", "美国");

    private static final Map<String, BigDecimal> EXCHANGE_RATES = Map.of(
            "USD", new BigDecimal("6.7828"),
            "EUR", new BigDecimal("7.8344"),
            "GBP", new BigDecimal("9.1530"));

    private final EbayWarehouseRentMapper mapper;
    private final EbayWarehouseRentReplaceService replaceService;

    public EbayWarehouseRentService(
            EbayWarehouseRentMapper mapper,
            EbayWarehouseRentReplaceService replaceService)
    {
        this.mapper = mapper;
        this.replaceService = replaceService;
    }

    /** 先完整解析校验，再按本次单号增量覆盖明细并重建全量汇总。 */
    public Map<String, Object> importFile(MultipartFile file, String operator)
    {
        validateFile(file);
        String sourceFileName = safeFileName(file.getOriginalFilename());
        String importedBy = safeOperator(operator);
        ParseResult parsed;
        try
        {
            parsed = parse(file);
        }
        catch (ServiceException e)
        {
            throw e;
        }
        catch (Exception e)
        {
            throw new ServiceException("仓租明细解析失败：" + rootMessage(e));
        }

        String batchId = UUID.randomUUID().toString().replace("-", "");
        for (EbayWarehouseRentDetail item : parsed.items())
        {
            item.setImportBatchId(batchId);
            item.setSourceFileName(sourceFileName);
            item.setSourceSheetName(TARGET_SHEET);
            item.setImportedBy(importedBy);
        }
        EbayWarehouseRentReplaceService.ReplaceResult replaced =
                replaceService.replace(parsed.items());

        Map<String, Object> result = new LinkedHashMap<>();
        result.put("sourceFileName", sourceFileName);
        result.put("sourceRowCount", parsed.sourceRowCount());
        result.put("detailRowCount", replaced.detailRowCount());
        result.put("coveredDocumentCount", replaced.replacedOrderCount());
        result.put("aggregateRowCount", replaced.aggregateRowCount());
        result.put("warehouseRentAmountCny", parsed.totalAmountCny()
                .setScale(2, RoundingMode.HALF_UP).toPlainString());
        result.put("importBatchId", batchId);
        return result;
    }

    /** 将当前页仓租按站点和完整SKU批量回填，避免逐行查询。 */
    public Object enrich(Object data)
    {
        if (!(data instanceof Map<?, ?> dataMap)) return data;
        Object itemsValue = dataMap.get("items");
        if (!(itemsValue instanceof List<?> items) || items.isEmpty()) return data;

        Map<SiteSkuKey, EbayWarehouseRentAggregate> requested =
                new LinkedHashMap<>();
        for (Object value : items)
        {
            if (!(value instanceof Map<?, ?> item)) continue;
            String site = itemSite(item);
            String sku = itemSku(item);
            if (site == null || sku == null) continue;
            addKey(requested, site, sku);
            addKey(requested, site, stripBrandPrefix(sku));
        }
        if (requested.isEmpty()) return data;

        Map<SiteSkuKey, BigDecimal> amounts = new LinkedHashMap<>();
        for (EbayWarehouseRentAggregate config
                : mapper.selectByKeys(List.copyOf(requested.values())))
        {
            amounts.put(new SiteSkuKey(config.getSite(), config.getSku()),
                    config.getWarehouseRentAmountCny());
        }
        for (Object value : items)
        {
            if (!(value instanceof Map<?, ?> rawItem)) continue;
            Map<String, Object> item = mutableMap(rawItem);
            String site = itemSite(item);
            String sku = itemSku(item);
            BigDecimal amount = null;
            if (site != null && sku != null)
            {
                amount = amounts.get(new SiteSkuKey(site, sku));
                if (amount == null)
                {
                    String core = stripBrandPrefix(sku);
                    if (core != null)
                    {
                        amount = amounts.get(new SiteSkuKey(site, core));
                    }
                }
            }
            item.put("warehouse_rent_amount_cny", amount);
        }
        return data;
    }

    private static String itemSite(Map<?, ?> item)
    {
        String site = text(item.get("site"));
        return site != null ? site : text(item.get("site_name"));
    }

    private static String itemSku(Map<?, ?> item)
    {
        String sku = text(item.get("sku"));
        return sku != null ? sku : text(item.get("inventory_sku"));
    }

    private static void addKey(
            Map<SiteSkuKey, EbayWarehouseRentAggregate> requested,
            String site, String sku)
    {
        if (sku == null) return;
        SiteSkuKey key = new SiteSkuKey(site, sku);
        requested.computeIfAbsent(key, ignored -> key.toDomain());
    }

    /**
     * 页面SKU带品牌前缀（BMW-30001-0001），仓租文件的商品编码是 JMH-30001-0001，
     * 导入时已由 normalizeSku 剥成 30001-0001。两边只差首段前缀，去掉后即可对上。
     * 先走精确匹配，匹配不上再用去前缀的结果兜底，避免影响本就同名的SKU。
     */
    private static String stripBrandPrefix(String sku)
    {
        if (sku == null) return null;
        int index = sku.indexOf('-');
        if (index < 0 || index + 1 >= sku.length()) return null;
        return text(sku.substring(index + 1));
    }

    private ParseResult parse(MultipartFile file) throws Exception
    {
        try (InputStream input = file.getInputStream();
             OPCPackage pkg = OPCPackage.open(input))
        {
            XSSFReader reader = new XSSFReader(pkg);
            StylesTable styles = reader.getStylesTable();
            SharedStrings strings = new ReadOnlySharedStringsTable(pkg);
            XSSFReader.SheetIterator sheets =
                    (XSSFReader.SheetIterator) reader.getSheetsData();
            boolean found = false;
            WarehouseRentSheetHandler handler = null;
            while (sheets.hasNext())
            {
                try (InputStream sheetInput = sheets.next())
                {
                    if (!TARGET_SHEET.equals(sheets.getSheetName())) continue;
                    found = true;
                    Map<Integer, String> rawTotalAmounts =
                            parseRawTotalAmounts(sheetInput);
                    handler = new WarehouseRentSheetHandler(rawTotalAmounts);
                    try (InputStream formattedSheetInput =
                                 sheets.getSheetPart().getInputStream())
                    {
                        XMLReader parser = XMLHelper.newXMLReader();
                        parser.setContentHandler(new XSSFSheetXMLHandler(
                                styles, strings, handler,
                                new DataFormatter(Locale.CHINA), false));
                        parser.parse(new InputSource(formattedSheetInput));
                    }
                    break;
                }
            }
            if (!found || handler == null)
            {
                throw new ServiceException("Excel中缺少“仓租明细”工作表");
            }
            return handler.result();
        }
    }

    /** 金额计算读取单元格底层数值，避免显示格式逐行舍入造成累计误差。 */
    private Map<Integer, String> parseRawTotalAmounts(InputStream input)
            throws Exception
    {
        RawTotalAmountSheetHandler handler =
                new RawTotalAmountSheetHandler();
        XMLReader parser = XMLHelper.newXMLReader();
        parser.setContentHandler(handler);
        parser.parse(new InputSource(input));
        return handler.values();
    }

    private void validateFile(MultipartFile file)
    {
        if (file == null || file.isEmpty())
        {
            throw new ServiceException("请选择需要上传的仓租明细文件");
        }
        if (file.getSize() > MAX_FILE_SIZE)
        {
            throw new ServiceException("仓租明细文件不能超过20MB");
        }
        String fileName = text(file.getOriginalFilename());
        if (fileName == null || !fileName.toLowerCase(Locale.ROOT).endsWith(".xlsx"))
        {
            throw new ServiceException("仓租明细只支持.xlsx格式");
        }
    }

    private static String normalizeSku(String productCode)
    {
        String value = text(productCode);
        if (value == null) return null;
        String stripped = text(value.replaceFirst("(?i)^JMH-", ""));
        return stripped == null ? null : stripped.toUpperCase(Locale.ROOT);
    }

    private static BigDecimal parseAmount(String value)
    {
        String normalized = text(value);
        if (normalized == null) return null;
        try
        {
            return new BigDecimal(normalized.replace(",", ""));
        }
        catch (NumberFormatException e)
        {
            return null;
        }
    }

    private static String safeFileName(String value)
    {
        String result = text(value);
        if (result == null) return "仓租明细.xlsx";
        result = result.replace('\\', '/');
        int separator = result.lastIndexOf('/');
        if (separator >= 0) result = result.substring(separator + 1);
        return result.length() <= 255 ? result : result.substring(0, 255);
    }

    private static String safeOperator(String value)
    {
        String result = text(value);
        if (result == null) return "SYSTEM";
        return result.length() <= 64 ? result : result.substring(0, 64);
    }

    private static String text(Object value)
    {
        if (value == null) return null;
        String result = String.valueOf(value).trim();
        return StringUtils.hasText(result) ? result : null;
    }

    private String rootMessage(Throwable error)
    {
        Throwable current = error;
        while (current.getCause() != null) current = current.getCause();
        String message = text(current.getMessage());
        return message == null ? current.getClass().getSimpleName() : message;
    }

    @SuppressWarnings("unchecked")
    private Map<String, Object> mutableMap(Map<?, ?> value)
    {
        return (Map<String, Object>) value;
    }

    private record SiteSkuKey(String site, String sku)
    {
        private SiteSkuKey
        {
            site = site == null ? null : site.trim();
            sku = sku == null ? null : sku.trim().toUpperCase(Locale.ROOT);
        }

        private EbayWarehouseRentAggregate toDomain()
        {
            EbayWarehouseRentAggregate result = new EbayWarehouseRentAggregate();
            result.setSite(site);
            result.setSku(sku);
            return result;
        }
    }

    private record ParseResult(
            List<EbayWarehouseRentDetail> items,
            int sourceRowCount,
            BigDecimal totalAmountCny)
    {
    }

    /** 只截取V列的底层v值，22个源字段仍由DataFormatter按显示文本保存。 */
    private static final class RawTotalAmountSheetHandler
            extends DefaultHandler
    {
        private final Map<Integer, String> values = new HashMap<>();
        private final StringBuilder buffer = new StringBuilder();
        private int currentRow = -1;
        private boolean targetCell;
        private boolean readingValue;

        @Override
        public void startElement(
                String uri,
                String localName,
                String qName,
                Attributes attributes)
        {
            String element = elementName(localName, qName);
            if ("c".equals(element))
            {
                String reference = attributes.getValue("r");
                if (reference == null) return;
                CellReference cell = new CellReference(reference);
                targetCell = cell.getCol() == 21;
                currentRow = targetCell ? cell.getRow() : -1;
            }
            else if (targetCell && "v".equals(element))
            {
                readingValue = true;
                buffer.setLength(0);
            }
        }

        @Override
        public void characters(char[] ch, int start, int length)
        {
            if (readingValue) buffer.append(ch, start, length);
        }

        @Override
        public void endElement(String uri, String localName, String qName)
        {
            String element = elementName(localName, qName);
            if (readingValue && "v".equals(element))
            {
                values.put(currentRow, buffer.toString());
                readingValue = false;
            }
            else if ("c".equals(element))
            {
                targetCell = false;
                currentRow = -1;
            }
        }

        private Map<Integer, String> values()
        {
            return values;
        }

        private String elementName(String localName, String qName)
        {
            return StringUtils.hasText(localName) ? localName : qName;
        }
    }

    private static final class WarehouseRentSheetHandler
            implements XSSFSheetXMLHandler.SheetContentsHandler
    {
        private final String[] headers = new String[EXPECTED_HEADERS.size()];
        private final String[] sourceValues =
                new String[EXPECTED_HEADERS.size()];
        private final List<EbayWarehouseRentDetail> details =
                new ArrayList<>();
        private final List<String> errors = new ArrayList<>();
        private int errorCount;
        private int currentRow;
        private boolean headerValid;
        private boolean rowHasAnyValue;
        private BigDecimal totalAmountCny = BigDecimal.ZERO;
        private final Map<Integer, String> rawTotalAmounts;

        private WarehouseRentSheetHandler(
                Map<Integer, String> rawTotalAmounts)
        {
            this.rawTotalAmounts = rawTotalAmounts;
        }

        @Override
        public void startRow(int rowNum)
        {
            currentRow = rowNum;
            Arrays.fill(sourceValues, null);
            rowHasAnyValue = false;
            if (rowNum > MAX_DATA_ROWS)
            {
                throw new ServiceException("仓租明细最多支持" + MAX_DATA_ROWS + "行数据");
            }
        }

        @Override
        public void endRow(int rowNum)
        {
            if (rowNum == 0)
            {
                validateHeaders();
                return;
            }
            if (!headerValid) return;
            if (!rowHasAnyValue)
            {
                return;
            }

            int excelRow = rowNum + 1;
            String orderNo = text(sourceValues[0]);
            String warehouseCode = text(sourceValues[1]);
            String productCode = text(sourceValues[2]);
            String currency = text(sourceValues[13]);
            String totalAmount = text(rawTotalAmounts.get(rowNum));
            if (totalAmount == null) totalAmount = text(sourceValues[21]);
            String normalizedWarehouse = warehouseCode == null
                    ? null : warehouseCode.toUpperCase(Locale.ROOT);
            String site = WAREHOUSE_SITE_MAP.get(normalizedWarehouse);
            String sku = normalizeSku(productCode);
            String normalizedCurrency = currency == null
                    ? null : currency.toUpperCase(Locale.ROOT);
            BigDecimal rate = EXCHANGE_RATES.get(normalizedCurrency);
            BigDecimal sourceAmount = parseAmount(totalAmount);

            boolean valid = true;
            if (orderNo == null)
            {
                addError(excelRow, "单号不能为空");
                valid = false;
            }
            if (site == null)
            {
                addError(excelRow, "仓库“" + display(warehouseCode) + "”没有站点映射");
                valid = false;
            }
            if (sku == null)
            {
                addError(excelRow, "商品编码不能为空");
                valid = false;
            }
            if (rate == null)
            {
                addError(excelRow, "计费币种“" + display(currency) + "”不支持");
                valid = false;
            }
            if (sourceAmount == null)
            {
                addError(excelRow, "总金额(不含税)不是有效数字");
                valid = false;
            }
            if (!valid) return;

            BigDecimal cnyAmount = sourceAmount.multiply(rate)
                    .setScale(4, RoundingMode.HALF_UP);
            details.add(buildDetail(
                    orderNo, site, sku, rate, cnyAmount, excelRow));
            totalAmountCny = totalAmountCny.add(cnyAmount);
        }

        @Override
        public void cell(
                String cellReference,
                String formattedValue,
                XSSFComment comment)
        {
            if (cellReference == null) return;
            int column = new CellReference(cellReference).getCol();
            String value = sourceText(formattedValue);
            if (text(value) != null) rowHasAnyValue = true;
            if (currentRow == 0)
            {
                if (column < headers.length) headers[column] = text(value);
                else if (text(value) != null)
                    addError(1, "模板存在多余列：" + cellReference);
                return;
            }
            if (column < sourceValues.length) sourceValues[column] = value;
        }

        private EbayWarehouseRentDetail buildDetail(
                String orderNo,
                String site,
                String sku,
                BigDecimal exchangeRate,
                BigDecimal amountCny,
                int excelRow)
        {
            EbayWarehouseRentDetail item = new EbayWarehouseRentDetail();
            item.setOrderNo(orderNo);
            item.setWarehouseCode(sourceValues[1]);
            item.setProductCode(sourceValues[2]);
            item.setGoodsBarcode(sourceValues[3]);
            item.setProductName(sourceValues[4]);
            item.setReferenceNo(sourceValues[5]);
            item.setBillingTimeText(sourceValues[6]);
            item.setListingTimeText(sourceValues[7]);
            item.setDimensionsText(sourceValues[8]);
            item.setQuantityText(sourceValues[9]);
            item.setVolumeM3Text(sourceValues[10]);
            item.setProductWeightKgText(sourceValues[11]);
            item.setWarehouseRentExclTaxText(sourceValues[12]);
            item.setBillingCurrency(sourceValues[13]);
            item.setInventoryAgeDaysText(sourceValues[14]);
            item.setGoodsType(sourceValues[15]);
            item.setBillingType(sourceValues[16]);
            item.setStoragePhysicalForm(sourceValues[17]);
            item.setPeakSeasonSurchargeExclTaxText(sourceValues[18]);
            item.setOverAgeSurchargeExclTaxText(sourceValues[19]);
            item.setOversizedSurchargeExclTaxText(sourceValues[20]);
            item.setTotalAmountExclTaxText(sourceValues[21]);
            item.setSite(site);
            item.setSku(sku);
            item.setExchangeRate(exchangeRate);
            item.setWarehouseRentAmountCny(amountCny);
            item.setSourceRowNum(excelRow);
            return item;
        }

        private void validateHeaders()
        {
            boolean valid = true;
            for (int index = 0; index < EXPECTED_HEADERS.size(); index++)
            {
                String expected = EXPECTED_HEADERS.get(index);
                if (!expected.equals(headers[index]))
                {
                    addError(1, "第" + (index + 1) + "列应为“" + expected
                            + "”，实际为“" + display(headers[index]) + "”");
                    valid = false;
                }
            }
            headerValid = valid && errorCount == 0;
        }

        private void addError(int excelRow, String message)
        {
            errorCount++;
            if (errors.size() < MAX_REPORTED_ERRORS)
            {
                errors.add("第" + excelRow + "行：" + message);
            }
        }

        private ParseResult result()
        {
            if (errorCount > 0)
            {
                String suffix = errorCount > errors.size()
                        ? "；另有" + (errorCount - errors.size()) + "个错误未展示" : "";
                throw new ServiceException(
                        "仓租明细校验失败（共" + errorCount + "个错误）："
                        + String.join("；", errors) + suffix);
            }
            if (!headerValid)
            {
                throw new ServiceException("仓租明细模板表头不正确");
            }
            if (details.isEmpty())
            {
                throw new ServiceException("仓租明细没有可导入的数据");
            }
            return new ParseResult(
                    List.copyOf(details), details.size(), totalAmountCny);
        }

        private String sourceText(String value)
        {
            return value != null && StringUtils.hasText(value) ? value : null;
        }

        private String display(String value)
        {
            return value == null ? "空" : value;
        }
    }
}
