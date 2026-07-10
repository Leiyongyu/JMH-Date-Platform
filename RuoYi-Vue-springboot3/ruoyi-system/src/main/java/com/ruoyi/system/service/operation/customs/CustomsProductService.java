package com.ruoyi.system.service.operation.customs;

import com.ruoyi.system.domain.operation.customs.CustomsFbaShipmentOption;
import com.ruoyi.system.domain.operation.customs.CustomsDeclarationItem;
import com.ruoyi.system.domain.operation.customs.CustomsProduct;
import com.ruoyi.system.domain.operation.customs.CustomsStockOrderOption;
import com.ruoyi.common.utils.html.EscapeUtil;
import com.ruoyi.system.mapper.operation.customs.CustomsInventoryMapper;
import com.ruoyi.system.mapper.operation.customs.CustomsProductMapper;
import java.io.InputStream;
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.ArrayList;
import java.util.Collections;
import java.util.HashMap;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.regex.Matcher;
import java.util.regex.Pattern;
import java.util.stream.Collectors;
import org.apache.poi.ss.usermodel.Cell;
import org.apache.poi.ss.usermodel.CellType;
import org.apache.poi.ss.usermodel.Row;
import org.apache.poi.ss.usermodel.Sheet;
import org.apache.poi.ss.usermodel.Workbook;
import org.apache.poi.xssf.usermodel.XSSFWorkbook;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.interceptor.TransactionAspectSupport;
import org.springframework.web.multipart.MultipartFile;

@Service
public class CustomsProductService
{
    private static final long MAX_FILE_SIZE = 20L * 1024 * 1024;
    private static final int MAX_ROWS = 50000;
    private static final Pattern WEIGHT_PATTERN =
            Pattern.compile("(\\d+)\\s*([\\u4e00-\\u9fa5]+)\\s*/\\s*([\\d.]+)\\s*([\\u4e00-\\u9fa5]+)");
    private static final Pattern HS_PATTERN = Pattern.compile("^(\\d{4}\\s?\\d{2,6})");

    private final CustomsProductMapper productMapper;
    private final CustomsInventoryMapper customsInventoryMapper;

    public CustomsProductService(CustomsProductMapper productMapper, CustomsInventoryMapper customsInventoryMapper)
    {
        this.productMapper = productMapper;
        this.customsInventoryMapper = customsInventoryMapper;
    }

    public List<CustomsProduct> search(String keyword)
    {
        String value = trim(keyword);
        if (value.isEmpty()) return List.of();
        // Resolve to standard SKU first
        Map<String, String> mapping = resolveStandardSkus(List.of(value));
        String standardSku = mapping.get(value);
        // Search by original keyword, normalized key, and standard SKU
        Set<String> seenSkus = new HashSet<>();
        List<CustomsProduct> results = new ArrayList<>();
        addSearchResults(results, seenSkus, value);
        String normalized = normalizeSkuKey(value);
        if (!normalized.equals(value) && !normalized.isEmpty()) addSearchResults(results, seenSkus, normalized);
        if (standardSku != null && !standardSku.equals(value) && !standardSku.equals(normalized))
            addSearchResults(results, seenSkus, standardSku);
        return results;
    }

    private void addSearchResults(List<CustomsProduct> results, Set<String> seenSkus, String term)
    {
        for (CustomsProduct p : productMapper.search(term, 20))
        {
            if (p.getSku() != null && seenSkus.add(p.getSku())) results.add(p);
        }
    }

    public List<CustomsStockOrderOption> searchStockOrders(String keyword, Integer limit)
    {
        int size = limit == null ? 50 : Math.max(1, Math.min(limit, 200));
        return productMapper.searchStockOrders(trim(keyword), size);
    }

    public List<CustomsFbaShipmentOption> searchFbaShipments(String keyword, Integer limit)
    {
        int size = limit == null ? 50 : Math.max(1, Math.min(limit, 200));
        return productMapper.searchFbaShipments(trim(keyword), size);
    }

    public Map<String, Object> linkStockOrders(List<String> orderNos)
    {
        List<String> orders = normalizeSkus(orderNos);
        if (orders.isEmpty()) throw new IllegalArgumentException("请选择需要关联的备货单");
        List<CustomsDeclarationItem> products = productMapper.selectProductsByStockOrders(orders);
        List<String> missingSkus = productMapper.selectMissingSkusByStockOrders(orders);
        return buildLinkResult(products, missingSkus);
    }

    public Map<String, Object> linkFbaShipments(List<String> shipmentIds)
    {
        List<String> shipments = normalizeSkus(shipmentIds);
        if (shipments.isEmpty()) throw new IllegalArgumentException("请选择需要关联的FBA货件");
        List<CustomsProduct> products = productMapper.selectProductsByFbaShipments(shipments);
        List<String> missingSkus = productMapper.selectMissingSkusByFbaShipments(shipments);
        return buildLinkResult(products, missingSkus);
    }

    private Map<String, Object> buildLinkResult(List<? extends CustomsProduct> products, List<String> missingSkus)
    {
        List<CustomsDeclarationItem> items = new ArrayList<>();
        Map<String, CustomsDeclarationItem> merged = new LinkedHashMap<>();

        for (CustomsProduct product : products)
        {
            CustomsDeclarationItem item = copyToItem(product);
            item.setQuantity(Math.max(1, item.getQuantity() == null ? 1 : item.getQuantity()));
            item.setBoxCount(Math.max(1, item.getBoxCount() == null ? 1 : item.getBoxCount()));

            if (product.getIsTax() != null && product.getIsTax() == 1)
            {
                String key = trim(product.getSku()) + "|"
                        + trim(product.getSourceLocation()) + "|"
                        + trim(product.getBoxNo()) + "|"
                        + trim(product.getDestinationCountry());
                CustomsDeclarationItem existing = merged.get(key);
                if (existing != null)
                {
                    existing.setQuantity(existing.getQuantity() + item.getQuantity());
                    existing.setBoxCount(Math.max(
                            existing.getBoxCount() == null ? 1 : existing.getBoxCount(),
                            item.getBoxCount() == null ? 1 : item.getBoxCount()));
                }
                else
                {
                    merged.put(key, item);
                    items.add(item);
                }
            }
            else
            {
                items.add(item);
            }
        }

        Map<String, Object> result = new LinkedHashMap<>();
        result.put("products", items);
        result.put("missingSkus", missingSkus == null ? List.of() : missingSkus);
        return result;
    }

    public Map<String, Object> batchQuery(List<String> sourceSkus, Map<String, Integer> quantities)
    {
        List<String> requestedSkus = new ArrayList<>();
        if (sourceSkus != null)
            for (String sku : sourceSkus) if (!trim(sku).isEmpty()) requestedSkus.add(sku.trim());
        List<String> uniqueSkus = normalizeSkus(requestedSkus);

        // Resolve raw SKUs to standard customs_inventory_list SKUs — no fallback to raw
        Map<String, String> skuMapping = resolveStandardSkus(uniqueSkus);
        List<String> querySkus = uniqueSkus.stream()
                .map(skuMapping::get)
                .filter(s -> s != null)
                .distinct()
                .collect(Collectors.toList());

        List<CustomsProduct> products = querySkus.isEmpty() ? List.of() : productMapper.selectBySkus(querySkus);
        Map<String, CustomsProduct> found = new HashMap<>();
        for (CustomsProduct product : products) found.put(product.getSku(), product);

        // Build a reverse mapping: rawSku → standardSku (from inventory), for missing detection
        List<CustomsDeclarationItem> matched = new ArrayList<>();
        List<String> missing = new ArrayList<>();
        for (String sku : requestedSkus)
        {
            String standardSku = skuMapping.get(sku);
            if (standardSku == null)
            {
                missing.add(sku);
                continue;
            }
            CustomsProduct product = found.get(standardSku);
            if (product == null)
            {
                missing.add(sku);
                continue;
            }
            CustomsDeclarationItem item = copyToItem(product);
            item.setQuantity(Math.max(1, quantities == null ? 1 : quantities.getOrDefault(sku, 1)));
            matched.add(item);
        }
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("products", matched);
        result.put("missingSkus", missing);
        return result;
    }

    public Map<String, Object> importSkuFile(MultipartFile file) throws Exception
    {
        checkFile(file);
        List<SkuRequest> requests = new ArrayList<>();
        try (InputStream input = file.getInputStream(); Workbook workbook = new XSSFWorkbook(input))
        {
            Sheet sheet = workbook.getSheetAt(0);
            int last = Math.min(sheet.getLastRowNum(), MAX_ROWS - 1);
            for (int i = 0; i <= last; i++)
            {
                Row row = sheet.getRow(i);
                if (row == null) continue;
                String sku = cellString(row.getCell(0));
                if (sku.isEmpty() || "sku".equalsIgnoreCase(sku)) continue;
                int qty = integerValue(row.getCell(1), 1);
                requests.add(new SkuRequest(sku, qty));
            }
        }
        if (requests.isEmpty()) throw new IllegalArgumentException("未读取到SKU");

        List<String> uniqueSkus = normalizeSkus(requests.stream().map(SkuRequest::sku).toList());

        // Resolve raw SKUs to standard customs_inventory_list SKUs — no fallback to raw
        Map<String, String> skuMapping = resolveStandardSkus(uniqueSkus);
        List<String> querySkus = uniqueSkus.stream()
                .map(skuMapping::get)
                .filter(s -> s != null)
                .distinct()
                .collect(Collectors.toList());

        Map<String, CustomsProduct> found = new HashMap<>();
        List<CustomsProduct> skuProducts = querySkus.isEmpty() ? List.<CustomsProduct>of() : productMapper.selectBySkus(querySkus);
        for (CustomsProduct product : skuProducts) found.put(product.getSku(), product);

        List<CustomsDeclarationItem> matched = new ArrayList<>();
        List<String> missing = new ArrayList<>();
        for (SkuRequest request : requests)
        {
            String standardSku = skuMapping.get(request.sku());
            if (standardSku == null)
            {
                missing.add(request.sku());
                continue;
            }
            CustomsProduct product = found.get(standardSku);
            if (product == null)
            {
                missing.add(request.sku());
                continue;
            }
            CustomsDeclarationItem item = copyToItem(product);
            item.setQuantity(request.quantity());
            matched.add(item);
        }
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("products", matched);
        result.put("missingSkus", missing);
        return result;
    }

    @Transactional(rollbackFor = Exception.class)
    public Map<String, Object> importHistory(MultipartFile file) throws Exception
    {
        checkFile(file);
        List<CustomsProduct> parsed = new ArrayList<>();
        List<String> errors = new ArrayList<>();
        try (InputStream input = file.getInputStream(); Workbook workbook = new XSSFWorkbook(input))
        {
            Sheet sheet = findCustomsSheet(workbook);
            int last = Math.min(sheet.getLastRowNum(), MAX_ROWS - 1);
            for (int i = 10; i <= last; i++)
            {
                Row row = sheet.getRow(i);
                if (row == null) continue;
                String sku = cellString(row.getCell(3));
                if (sku.isEmpty()) continue;
                try
                {
                    CustomsProduct product = parseHistoryRow(row, sku);
                    sanitizeProduct(product);
                    parsed.add(product);
                }
                catch (Exception e)
                {
                    errors.add("第" + (i + 1) + "行 " + sku + "：" + e.getMessage());
                }
            }
        }
        if (parsed.isEmpty() && errors.isEmpty()) throw new IllegalArgumentException("未读取到可导入的商品数据");

        // Normalize SKUs against customs_inventory_list
        List<CustomsProduct> validProducts = new ArrayList<>();
        {
            List<String> rawSkus = parsed.stream().map(CustomsProduct::getSku).distinct().collect(Collectors.toList());
            Map<String, String> skuMapping = resolveStandardSkus(rawSkus);
            for (CustomsProduct product : parsed)
            {
                String standardSku = skuMapping.getOrDefault(product.getSku(), null);
                if (standardSku == null)
                {
                    errors.add(product.getSku() + "：未在库存清单中找到匹配的标准SKU");
                }
                else
                {
                    product.setSku(standardSku);
                    validProducts.add(product);
                }
            }
        }
        // Use only products that could be resolved
        List<CustomsProduct> resolved = validProducts;

        // All rows failed — return errors without touching the DB
        if (resolved.isEmpty())
        {
            Map<String, Object> result = new LinkedHashMap<>();
            result.put("inserted", 0);
            result.put("updated", 0);
            result.put("failed", errors.size());
            result.put("errors", errors);
            return result;
        }

        // Batch-check existing SKUs (1 DB call instead of N)
        Set<String> existingSkus = new HashSet<>();
        List<String> allSkus = resolved.stream().map(CustomsProduct::getSku).distinct().collect(Collectors.toList());
        if (!allSkus.isEmpty())
        {
            for (CustomsProduct p : productMapper.selectBySkus(allSkus))
            {
                existingSkus.add(p.getSku());
            }
        }

        int inserted = 0;
        int updated = 0;
        try
        {
            // Batch upsert (already internally split into 500-size chunks)
            batchUpsert(resolved);
            for (CustomsProduct product : resolved)
            {
                if (existingSkus.contains(product.getSku())) updated++;
                else inserted++;
            }
        }
        catch (Exception e)
        {
            errors.add("批量写入失败：" + e.getMessage());
            TransactionAspectSupport.currentTransactionStatus().setRollbackOnly();
        }
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("inserted", inserted);
        result.put("updated", updated);
        result.put("failed", errors.size());
        result.put("errors", errors);
        return result;
    }

    public List<CustomsProduct> findExistingProducts(List<CustomsProduct> products)
    {
        List<CustomsProduct> values = normalizeSaveProducts(products);
        if (values.isEmpty()) return List.of();
        return productMapper.selectExistingBySkuSource(values);
    }

    @Transactional(rollbackFor = Exception.class)
    public int saveProducts(List<CustomsProduct> products, boolean overwrite)
    {
        List<CustomsProduct> values = normalizeSaveProducts(products);
        if (!overwrite)
        {
            List<CustomsProduct> existing = productMapper.selectExistingBySkuSource(values);
            if (!existing.isEmpty()) throw new IllegalArgumentException("商品资料已存在，请确认覆盖后再保存");
        }
        if (overwrite) batchUpsert(values);
        else batchInsert(values);
        return values.size();
    }

    private List<CustomsProduct> normalizeSaveProducts(List<CustomsProduct> products)
    {
        if (products == null || products.isEmpty()) throw new IllegalArgumentException("请选择需要保存的商品");
        // First validate and sanitize
        List<String> rawSkus = new ArrayList<>();
        for (CustomsProduct product : products)
        {
            validateProduct(product);
            sanitizeProduct(product);
            product.setSku(product.getSku().trim());
            product.setSourceLocation(trim(product.getSourceLocation()));
            product.setOriginCountry(defaultValue(product.getOriginCountry(), "中国"));
            rawSkus.add(product.getSku());
        }

        // Resolve SKUs to standard customs_inventory_list SKUs
        Map<String, String> skuMapping = resolveStandardSkus(rawSkus);
        Map<String, CustomsProduct> unique = new LinkedHashMap<>();
        for (CustomsProduct product : products)
        {
            String standardSku = skuMapping.getOrDefault(product.getSku(), null);
            if (standardSku == null)
                throw new IllegalArgumentException(product.getSku() + "：未在库存清单中找到匹配的标准SKU");
            product.setSku(standardSku);
            unique.put(product.getSku(), product);
        }
        return new ArrayList<>(unique.values());
    }

    private void batchUpsert(List<CustomsProduct> products)
    {
        if (products == null || products.isEmpty()) return;
        for (int from = 0; from < products.size(); from += 500)
        {
            int to = Math.min(from + 500, products.size());
            productMapper.batchUpsert(products.subList(from, to));
        }
    }

    private void batchInsert(List<CustomsProduct> products)
    {
        if (products == null || products.isEmpty()) return;
        for (int from = 0; from < products.size(); from += 500)
        {
            int to = Math.min(from + 500, products.size());
            productMapper.batchInsert(products.subList(from, to));
        }
    }

    private CustomsProduct parseHistoryRow(Row row, String sku)
    {
        CustomsProduct product = new CustomsProduct();
        product.setSku(sku);
        String hsText = cellString(row.getCell(1));
        Matcher hsMatcher = HS_PATTERN.matcher(hsText);
        if (hsMatcher.find())
        {
            product.setHsCode(hsMatcher.group(1).replace(" ", ""));
            product.setHsDescription(hsText.substring(hsMatcher.end()).trim());
        }
        else
        {
            product.setHsCode("");
            product.setHsDescription(hsText);
        }
        product.setDescriptionCn(cellString(row.getCell(2)));
        product.setModel(defaultValue(cellString(row.getCell(4)), "通用型"));

        String weightText = cellString(row.getCell(5));
        Matcher weightMatcher = WEIGHT_PATTERN.matcher(weightText);
        if (weightMatcher.find())
        {
            int quantity = Integer.parseInt(weightMatcher.group(1));
            product.setUnit(weightMatcher.group(2));
            BigDecimal totalWeight = new BigDecimal(weightMatcher.group(3));
            product.setSingleWeight(quantity > 0
                    ? totalWeight.divide(BigDecimal.valueOf(quantity), 4, RoundingMode.HALF_UP) : BigDecimal.ZERO);
        }
        else
        {
            product.setUnit("个");
        }

        String[] priceParts = cellString(row.getCell(6)).split("/");
        product.setUnitPriceUsd(decimal(priceParts.length > 0 ? priceParts[0] : "0"));
        product.setCurrency(priceParts.length >= 3 ? defaultValue(priceParts[2].trim(), "USD") : "USD");
        product.setOriginCountry(cellString(row.getCell(7)));
        product.setDestinationCountry(cellString(row.getCell(8)));
        product.setSourceLocation(cellString(row.getCell(10)));
        product.setExemption(cellString(row.getCell(12)));
        return product;
    }

    private Sheet findCustomsSheet(Workbook workbook)
    {
        for (int i = 0; i < workbook.getNumberOfSheets(); i++)
        {
            String name = workbook.getSheetName(i);
            if (name.contains("报") || name.contains("関")) return workbook.getSheetAt(i);
        }
        return workbook.getNumberOfSheets() >= 4 ? workbook.getSheetAt(3) : workbook.getSheetAt(0);
    }

    private CustomsDeclarationItem copyToItem(CustomsProduct product)
    {
        CustomsDeclarationItem item = new CustomsDeclarationItem();
        item.setId(product.getId());
        item.setSku(product.getSku());
        item.setDescriptionCn(product.getDescriptionCn());
        item.setModel(product.getModel());
        item.setUnit(product.getUnit());
        item.setUnitPriceUsd(product.getUnitPriceUsd());
        item.setCurrency(product.getCurrency());
        item.setSingleWeight(product.getSingleWeight());
        item.setPackingNetWeight(product.getPackingNetWeight());
        item.setPackingGrossWeight(product.getPackingGrossWeight());
        item.setPackingCbm(product.getPackingCbm());
        item.setBoxLength(product.getBoxLength());
        item.setBoxWidth(product.getBoxWidth());
        item.setBoxHeight(product.getBoxHeight());
        item.setHsCode(product.getHsCode());
        item.setHsDescription(product.getHsDescription());
        item.setOriginCountry(product.getOriginCountry());
        item.setDestinationCountry(product.getDestinationCountry());
        item.setSourceLocation(product.getSourceLocation());
        item.setExemption(product.getExemption());
        item.setBoxNo(product.getBoxNo());
        item.setIsTax(product.getIsTax());
        if (product instanceof CustomsDeclarationItem declarationItem)
        {
            item.setQuantity(declarationItem.getQuantity());
            item.setBoxCount(declarationItem.getBoxCount());
            item.setSourceOrderNo(declarationItem.getSourceOrderNo());
            item.setOrderTotalCbm(declarationItem.getOrderTotalCbm());
        }
        return item;
    }

    private List<String> normalizeSkus(List<String> values)
    {
        if (values == null) return List.of();
        Set<String> unique = new java.util.LinkedHashSet<>();
        for (String value : values) if (!trim(value).isEmpty()) unique.add(value.trim());
        return new ArrayList<>(unique);
    }

    private void validateProduct(CustomsProduct product)
    {
        if (product == null || trim(product.getSku()).isEmpty()) throw new IllegalArgumentException("SKU不能为空");
        if (trim(product.getDescriptionCn()).isEmpty()) throw new IllegalArgumentException(product.getSku() + " 商品名称不能为空");
        if (product.getUnitPriceUsd() != null && product.getUnitPriceUsd().signum() < 0)
            throw new IllegalArgumentException(product.getSku() + " 单价不能小于0");
        if (product.getSingleWeight() != null && product.getSingleWeight().signum() < 0)
            throw new IllegalArgumentException(product.getSku() + " 单重不能小于0");
    }

    /** Sanitize free-text fields against XSS before persisting. */
    private void sanitizeProduct(CustomsProduct product)
    {
        if (product.getDescriptionCn() != null) product.setDescriptionCn(EscapeUtil.clean(product.getDescriptionCn()));
        if (product.getHsDescription() != null) product.setHsDescription(EscapeUtil.clean(product.getHsDescription()));
        if (product.getModel() != null) product.setModel(EscapeUtil.clean(product.getModel()));
        if (product.getExemption() != null) product.setExemption(EscapeUtil.clean(product.getExemption()));
        if (product.getSourceLocation() != null) product.setSourceLocation(EscapeUtil.clean(product.getSourceLocation()));
        if (product.getUnit() != null) product.setUnit(EscapeUtil.clean(product.getUnit()));
    }

    private void checkFile(MultipartFile file)
    {
        if (file == null || file.isEmpty()) throw new IllegalArgumentException("上传文件不能为空");
        if (file.getSize() > MAX_FILE_SIZE) throw new IllegalArgumentException("上传文件不能超过20MB");
        String name = file.getOriginalFilename();
        if (name == null || !name.toLowerCase().endsWith(".xlsx"))
            throw new IllegalArgumentException("仅支持xlsx文件");
    }

    private String cellString(Cell cell)
    {
        if (cell == null) return "";
        if (cell.getCellType() == CellType.NUMERIC)
            return BigDecimal.valueOf(cell.getNumericCellValue()).stripTrailingZeros().toPlainString();
        if (cell.getCellType() == CellType.BOOLEAN) return Boolean.toString(cell.getBooleanCellValue());
        if (cell.getCellType() == CellType.FORMULA)
        {
            try { return BigDecimal.valueOf(cell.getNumericCellValue()).stripTrailingZeros().toPlainString(); }
            catch (Exception ignored) { return trim(cell.getCellFormula()); }
        }
        return trim(cell.toString());
    }

    private int integerValue(Cell cell, int defaultValue)
    {
        try { return new BigDecimal(cellString(cell)).intValue(); }
        catch (Exception ignored) { return defaultValue; }
    }

    private BigDecimal decimal(String value)
    {
        try { return new BigDecimal(trim(value)); }
        catch (Exception ignored) { return BigDecimal.ZERO; }
    }

    private String defaultValue(String value, String defaultValue)
    {
        return trim(value).isEmpty() ? defaultValue : value.trim();
    }

    private String trim(String value)
    {
        return value == null ? "" : value.trim();
    }

    /** Normalize a raw SKU (possibly with brand prefix) to a key for matching against customs_inventory_list. */
    private String normalizeSkuKey(String rawSku)
    {
        if (rawSku == null || rawSku.isEmpty()) return "";
        String s = rawSku.trim();
        int firstDash = s.indexOf('-');
        if (firstDash < 0) return s;
        String prefix = s.substring(0, firstDash);
        // PC 前缀原样保留
        if (prefix.toUpperCase().contains("PC")) return s;
        // 从第一个包含数字的段开始；该段去掉前导非数字字符；后续段全部保留
        String[] parts = s.split("-");
        for (int i = 0; i < parts.length; i++)
        {
            if (parts[i].matches(".*\\d+.*"))
            {
                String first = parts[i].replaceAll("^[^0-9]+", "");
                if (first.isEmpty()) continue;
                StringBuilder sb = new StringBuilder(first);
                for (int j = i + 1; j < parts.length; j++) sb.append("-").append(parts[j]);
                return sb.toString();
            }
        }
        return s;
    }

    /** Resolve raw SKUs to standard customs_inventory_list SKUs. Returns rawSku → standardSku map (null if not found). */
    private Map<String, String> resolveStandardSkus(List<String> rawSkus)
    {
        if (rawSkus == null || rawSkus.isEmpty()) return Collections.emptyMap();
        List<String> keys = rawSkus.stream()
                .map(this::normalizeSkuKey)
                .filter(k -> !k.isEmpty())
                .distinct()
                .collect(Collectors.toList());
        if (keys.isEmpty()) return Collections.emptyMap();

        // SQL returns best-match inventory SKU per matchKey (ROW_NUMBER priority-ordered)
        List<Map<String, String>> rows = customsInventoryMapper.selectSkusByNormalizedKeys(keys);
        Map<String, String> keyToSku = new LinkedHashMap<>();
        for (Map<String, String> row : rows)
        {
            String invSku = row.get("standardSku");
            String matchKey = row.get("matchKey");
            if (invSku != null && matchKey != null) keyToSku.putIfAbsent(matchKey, invSku);
        }

        Map<String, String> result = new LinkedHashMap<>();
        for (String raw : rawSkus)
        {
            String key = normalizeSkuKey(raw);
            result.put(raw, keyToSku.getOrDefault(key, null));
        }
        return result;
    }

    private record SkuRequest(String sku, int quantity) {}
}
