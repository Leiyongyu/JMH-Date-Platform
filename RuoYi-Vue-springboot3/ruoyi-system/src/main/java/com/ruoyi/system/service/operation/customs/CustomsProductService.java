package com.ruoyi.system.service.operation.customs;

import com.ruoyi.system.domain.operation.customs.CustomsFbaShipmentOption;
import com.ruoyi.system.domain.operation.customs.CustomsFbaShipmentSkuOption;
import com.ruoyi.system.domain.operation.customs.CustomsDeclarationItem;
import com.ruoyi.system.domain.operation.customs.CustomsDeclarationGenerateLog;
import com.ruoyi.system.domain.operation.customs.CustomsDeclarationRequest;
import com.ruoyi.system.domain.operation.customs.CustomsProduct;
import com.ruoyi.system.domain.operation.customs.CustomsStockOrderOption;
import com.ruoyi.common.utils.SecurityUtils;
import com.ruoyi.common.utils.html.EscapeUtil;
import com.ruoyi.system.domain.operation.customs.CustomsInventoryItem;
import com.ruoyi.system.mapper.operation.customs.CustomsInventoryMapper;
import com.ruoyi.system.mapper.operation.customs.CustomsDeclarationGenerateLogMapper;
import com.ruoyi.system.mapper.operation.customs.CustomsProductMapper;
import java.io.InputStream;
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.ArrayList;
import java.util.Collections;
import java.util.HashMap;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.UUID;
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
import org.springframework.transaction.support.TransactionTemplate;
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
    private final CustomsDeclarationGenerateLogMapper generateLogMapper;
    private final TransactionTemplate transactionTemplate;

    public CustomsProductService(CustomsProductMapper productMapper,
                                 CustomsInventoryMapper customsInventoryMapper,
                                 CustomsDeclarationGenerateLogMapper generateLogMapper,
                                 TransactionTemplate transactionTemplate)
    {
        this.productMapper = productMapper;
        this.customsInventoryMapper = customsInventoryMapper;
        this.generateLogMapper = generateLogMapper;
        this.transactionTemplate = transactionTemplate;
    }

    public List<CustomsProduct> search(String keyword)
    {
        String value = trim(keyword);
        if (value.isEmpty()) return List.of();
        // Resolve to standard SKU first
        Map<String, String> mapping = resolveStandardSkus(List.of(value));
        String standardSku = mapping.get(value);
        // Search by original keyword, normalized key, and standard SKU
        Set<String> seenKeys = new HashSet<>();
        List<CustomsProduct> results = new ArrayList<>();
        addSearchResults(results, seenKeys, value);
        String normalized = normalizeSkuKey(value);
        if (!normalized.equals(value) && !normalized.isEmpty()) addSearchResults(results, seenKeys, normalized);
        if (standardSku != null && !standardSku.equals(value) && !standardSku.equals(normalized))
            addSearchResults(results, seenKeys, standardSku);
        return results;
    }

    private void addSearchResults(List<CustomsProduct> results, Set<String> seenKeys, String term)
    {
        for (CustomsProduct p : productMapper.search(term, 20))
        {
            String key = productKey(p);
            if (!key.isEmpty() && seenKeys.add(key)) results.add(p);
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
        List<CustomsFbaShipmentOption> shipments = productMapper.searchFbaShipments(trim(keyword), size);
        if (shipments == null || shipments.isEmpty()) return shipments;
        List<String> shipmentIds = shipments.stream()
                .map(CustomsFbaShipmentOption::getShipmentId)
                .filter(id -> !trim(id).isEmpty())
                .distinct()
                .collect(Collectors.toList());
        Map<String, List<CustomsFbaShipmentSkuOption>> itemMap = productMapper.selectFbaShipmentSkuOptions(shipmentIds)
                .stream()
                .collect(Collectors.groupingBy(CustomsFbaShipmentSkuOption::getShipmentId, LinkedHashMap::new, Collectors.toList()));
        for (CustomsFbaShipmentOption shipment : shipments)
        {
            shipment.setItems(itemMap.getOrDefault(shipment.getShipmentId(), Collections.emptyList()));
        }
        return shipments;
    }

    public Map<String, Object> linkStockOrders(List<String> orderNos)
    {
        List<String> orders = normalizeSkus(orderNos);
        if (orders.isEmpty()) throw new IllegalArgumentException("请选择需要关联的备货单");
        List<CustomsDeclarationItem> products = productMapper.selectProductsByStockOrders(orders);
        // 只有匹配到出入库清单的 SKU 才会被批次价格覆盖；纯历史记录保持历史单价。
        applyBatchPrices(new ArrayList<CustomsProduct>(products));
        List<String> missingSkus = productMapper.selectMissingSkusByStockOrders(orders);
        List<String> missingInventorySkus = productMapper.selectMissingInventorySkusByStockOrders(orders);
        return buildLinkResult(products, missingSkus, missingInventorySkus, "EBAY");
    }

    public Map<String, Object> linkFbaShipments(List<String> shipmentIds)
    {
        List<String> shipments = normalizeSkus(shipmentIds);
        if (shipments.isEmpty()) throw new IllegalArgumentException("请选择需要关联的FBA货件");
        List<CustomsDeclarationItem> products = productMapper.selectProductsByFbaShipments(shipments);
        applyFbaTax(products, shipments);
        // 含税/库存商品沿用采购数量 + 剩余库存倒推批次价；历史兜底记录不受影响。
        applyBatchPrices(new ArrayList<CustomsProduct>(products));
        List<String> missingSkus = productMapper.selectMissingSkusByFbaShipments(shipments);
        List<String> missingInventorySkus = productMapper.selectMissingInventorySkusByFbaShipments(shipments);
        return buildLinkResult(products, missingSkus, missingInventorySkus, "FBA");
    }

    private void applyFbaTax(List<CustomsDeclarationItem> products, List<String> shipments)
    {
        if (products == null || products.isEmpty()) return;
        Map<String, Integer> taxMap = productMapper.selectFbaShipmentSkuOptions(shipments)
                .stream()
                .filter(item -> !trim(item.getShipmentId()).isEmpty() && !trim(item.getSku()).isEmpty())
                .filter(item -> item.getIsTax() != null)
                .collect(Collectors.toMap(
                        item -> trim(item.getShipmentId()) + "|" + normalizeSkuKey(item.getSku()),
                        CustomsFbaShipmentSkuOption::getIsTax,
                        (left, right) -> left != null ? left : right,
                        LinkedHashMap::new));
        for (CustomsDeclarationItem product : products)
        {
            Integer isTax = taxMap.get(trim(product.getSourceOrderNo()) + "|" + normalizeSkuKey(defaultValue(product.getRawSku(), product.getSku())));
            if (isTax != null) product.setIsTax(isTax);
        }
    }

    private Map<String, Object> buildLinkResult(List<? extends CustomsProduct> products,
                                                List<String> missingSkus,
                                                List<String> missingInventorySkus,
                                                String sourceType)
    {
        List<CustomsDeclarationItem> items = new ArrayList<>();
        Map<String, CustomsDeclarationItem> merged = new LinkedHashMap<>();
        Set<String> missingHistorySkus = new LinkedHashSet<>();
        Set<String> visibleSkuKeys = new LinkedHashSet<>();

        for (CustomsProduct product : products)
        {
            CustomsDeclarationItem item = copyToItem(product);
            visibleSkuKeys.add(normalizeSkuKey(defaultValue(trim(item.getRawSku()), trim(item.getSku()))));
            if ("INVENTORY".equalsIgnoreCase(trim(product.getSourceType())))
            {
                missingHistorySkus.add(defaultValue(trim(item.getRawSku()), trim(item.getSku())));
            }
            item.setQuantity(Math.max(1, item.getQuantity() == null ? 1 : item.getQuantity()));
            item.setBoxCount(Math.max(1, item.getBoxCount() == null ? 1 : item.getBoxCount()));

            if (product.getIsTax() != null && product.getIsTax() == 1)
            {
                String key = normalizeSkuKey(product.getSku()) + "|" + trim(product.getSourceLocation());
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

        for (String sku : missingSkus == null ? List.<String>of() : missingSkus)
        {
            String value = trim(sku);
            String key = normalizeSkuKey(value);
            if (value.isEmpty() || !visibleSkuKeys.add(key)) continue;
            CustomsDeclarationItem item = new CustomsDeclarationItem();
            item.setSku(value);
            item.setRawSku(value);
            item.setQuantity(1);
            item.setBoxCount(1);
            item.setUnit("");
            item.setCurrency("");
            item.setDeclarationSourceType(sourceType);
            item.setMatchStatus("MISSING_PRODUCT");
            items.add(item);
        }

        Map<String, Object> result = new LinkedHashMap<>();
        result.put("products", items);
        result.put("missingSkus", missingSkus == null ? List.of() : missingSkus);
        result.put("missingInventorySkus", missingInventorySkus == null ? List.of() : missingInventorySkus);
        result.put("missingHistorySkus", new ArrayList<>(missingHistorySkus));
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
                .map(s -> skuMapping.getOrDefault(s, s))
                .distinct()
                .collect(Collectors.toList());

        List<CustomsProduct> products = querySkus.isEmpty() ? List.of() : productMapper.selectBySkus(querySkus);
        Map<String, CustomsProduct> found = new HashMap<>();
        Map<String, CustomsProduct> foundByKey = new LinkedHashMap<>();
        for (CustomsProduct product : products)
        {
            found.putIfAbsent(product.getSku(), product);
            foundByKey.putIfAbsent(normalizeSkuKey(product.getSku()), product);
        }

        // Build a reverse mapping: rawSku → standardSku (from inventory), for missing detection
        List<CustomsDeclarationItem> matched = new ArrayList<>();
        List<String> missing = new ArrayList<>();
        for (String sku : requestedSkus)
        {
            String standardSku = skuMapping.get(sku);
            String lookupSku = standardSku == null ? sku : standardSku;
            CustomsProduct product = found.get(lookupSku);
            if (product == null) product = foundByKey.get(normalizeSkuKey(sku));
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
                .map(s -> skuMapping.getOrDefault(s, s))
                .distinct()
                .collect(Collectors.toList());

        Map<String, CustomsProduct> found = new HashMap<>();
        Map<String, CustomsProduct> foundByKey = new LinkedHashMap<>();
        List<CustomsProduct> skuProducts = querySkus.isEmpty() ? List.<CustomsProduct>of() : productMapper.selectBySkus(querySkus);
        for (CustomsProduct product : skuProducts)
        {
            found.putIfAbsent(product.getSku(), product);
            foundByKey.putIfAbsent(normalizeSkuKey(product.getSku()), product);
        }

        List<CustomsDeclarationItem> matched = new ArrayList<>();
        List<String> missing = new ArrayList<>();
        for (SkuRequest request : requests)
        {
            String standardSku = skuMapping.get(request.sku());
            String lookupSku = standardSku == null ? request.sku() : standardSku;
            CustomsProduct product = found.get(lookupSku);
            if (product == null) product = foundByKey.get(normalizeSkuKey(request.sku()));
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
            String sheetName = sheet.getSheetName();
            String fileName = file.getOriginalFilename();
            String username = currentUsername();
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
                    product.setSourceType("IMPORT");
                    product.setSourceFileName(fileName);
                    product.setSourceSheet(sheetName);
                    product.setSourceRowNo(i + 1);
                    product.setUpdatedBy(username);
                    parsed.add(product);
                }
                catch (Exception e)
                {
                    errors.add("第" + (i + 1) + "行 " + sku + "：" + e.getMessage());
                }
            }
        }
        if (parsed.isEmpty() && errors.isEmpty()) throw new IllegalArgumentException("未读取到可导入的商品数据");

        // 历史报关资料按文件中的完整 SKU 保存，不要求 SKU 必须存在于出入库清单。
        List<CustomsProduct> resolved = parsed;

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

        // Batch-check existing rows by full SKU + product_code.
        Set<String> existingKeys = new HashSet<>();
        for (CustomsProduct p : productMapper.selectExistingBySkuSource(resolved))
        {
            existingKeys.add(productKey(p));
        }

        int inserted = 0;
        int updated = 0;
        try
        {
            // 历史报关价格是已经申报的当前值，重复导入直接覆盖，不参与库存批次价格计算。
            batchUpsert(resolved);
            for (CustomsProduct product : resolved)
            {
                if (existingKeys.contains(productKey(product))) updated++;
                else inserted++;
            }
        }
        catch (Exception e)
        {
            errors.add("批量写入失败：" + e.getMessage());
            TransactionAspectSupport.currentTransactionStatus().setRollbackOnly();
            throw new IllegalStateException("批量写入失败：" + e.getMessage(), e);
        }
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("inserted", inserted);
        result.put("updated", updated);
        result.put("failed", errors.size());
        result.put("errors", errors);
        return result;
    }

    public Map<String, Object> importHistories(List<MultipartFile> files) throws Exception
    {
        if (files == null || files.isEmpty()) throw new IllegalArgumentException("请选择历史报关单文件");
        int inserted = 0;
        int updated = 0;
        int failed = 0;
        List<String> errors = new ArrayList<>();
        for (MultipartFile file : files)
        {
            try
            {
                Map<String, Object> one = transactionTemplate.execute(status ->
                {
                    try
                    {
                        return importHistory(file);
                    }
                    catch (Exception e)
                    {
                        throw new IllegalStateException(e);
                    }
                });
                if (one == null) one = Map.of();
                inserted += number(one.get("inserted"));
                updated += number(one.get("updated"));
                failed += number(one.get("failed"));
                Object fileErrors = one.get("errors");
                if (fileErrors instanceof List<?> list)
                    for (Object error : list) errors.add(file.getOriginalFilename() + "：" + error);
            }
            catch (Exception e)
            {
                failed++;
                Throwable cause = e.getCause() == null ? e : e.getCause();
                errors.add((file == null ? "未知文件" : file.getOriginalFilename()) + "：" + cause.getMessage());
            }
        }
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("fileCount", files.size());
        result.put("inserted", inserted);
        result.put("updated", updated);
        result.put("failed", failed);
        result.put("errors", errors);
        return result;
    }

    private int number(Object value)
    {
        return value instanceof Number number ? number.intValue() : 0;
    }

    private String currentUsername()
    {
        try { return SecurityUtils.getUsername(); }
        catch (Exception ignored) { return null; }
    }

    private String productKey(CustomsProduct product)
    {
        if (product == null) return "";
        return trim(product.getSku()) + "|" + trim(product.getProductCode());
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
        // 页面“保存商品”保存当前确认值到历史报关表，不重新计算库存批次价格。
        if (overwrite) batchUpsert(values);
        else batchInsert(values);
        return values.size();
    }

    private List<CustomsProduct> normalizeSaveProducts(List<CustomsProduct> products)
    {
        if (products == null || products.isEmpty()) throw new IllegalArgumentException("请选择需要保存的商品");
        // First validate and sanitize
        for (CustomsProduct product : products)
        {
            validateProduct(product);
            sanitizeProduct(product);
            product.setSourceType("MANUAL");
            product.setSourceFileName(null);
            product.setSourceSheet(null);
            product.setSourceRowNo(null);
            product.setUpdatedBy(currentUsername());
            product.setSku(product.getSku().trim());
            product.setProductCode(trim(product.getProductCode()));
            product.setSourceLocation(trim(product.getSourceLocation()));
            product.setOriginCountry(defaultValue(product.getOriginCountry(), "中国"));
        }

        Map<String, CustomsProduct> unique = new LinkedHashMap<>();
        for (CustomsProduct product : products)
        {
            // 保存时保留页面完整 SKU；库存清单只能在出入库清单页面维护。
            unique.put(product.getSku() + "|" + trim(product.getProductCode()), product);
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
        item.setProductCode(product.getProductCode());
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
            item.setDeclarationSourceType(declarationItem.getDeclarationSourceType());
            item.setSourceLineId(declarationItem.getSourceLineId());
            item.setRawSku(declarationItem.getRawSku());
            item.setWarehouseBucket(declarationItem.getWarehouseBucket());
            item.setWarehouseName(declarationItem.getWarehouseName());
            item.setMatchStatus(declarationItem.getMatchStatus());
            item.setOrderTotalCbm(declarationItem.getOrderTotalCbm());
        }
        return item;
    }

    @Transactional(rollbackFor = Exception.class)
    public String recordDeclarationGenerate(CustomsDeclarationRequest request)
    {
        if (request == null || request.getItems() == null || request.getItems().isEmpty()) return null;
        String declarationNo = "CD" + java.time.LocalDateTime.now()
                .format(java.time.format.DateTimeFormatter.ofPattern("yyyyMMddHHmmss"))
                + "-" + UUID.randomUUID().toString().substring(0, 8);
        String username = currentUsername();
        List<CustomsDeclarationGenerateLog> logs = new ArrayList<>();
        int index = 0;
        for (CustomsDeclarationItem item : request.getItems())
        {
            index++;
            String sku = trim(item.getSku());
            if (sku.isEmpty()) continue;
            CustomsDeclarationGenerateLog log = new CustomsDeclarationGenerateLog();
            String sourceType = defaultValue(item.getDeclarationSourceType(), "MANUAL");
            String sourceOrderNo = defaultValue(item.getSourceOrderNo(), declarationNo);
            String sourceLineId = defaultValue(item.getSourceLineId(), "LINE-" + index);
            String bucket = defaultValue(item.getWarehouseBucket(), "UNKNOWN");
            log.setDeclarationNo(declarationNo);
            log.setSourceType(sourceType);
            log.setSourceOrderNo(sourceOrderNo);
            log.setSourceLineId(sourceLineId);
            log.setRawSku(defaultValue(item.getRawSku(), sku));
            log.setStandardSku(sku);
            log.setProductCode(trim(item.getProductCode()));
            log.setSourceLocation(trim(item.getSourceLocation()));
            log.setWarehouseBucket(bucket);
            log.setWarehouseName(defaultValue(item.getWarehouseName(), bucketName(bucket)));
            log.setQuantity(BigDecimal.valueOf(Math.max(0, item.getQuantity() == null ? 0 : item.getQuantity())));
            log.setMatchStatus(defaultValue(item.getMatchStatus(),
                    "UNKNOWN".equalsIgnoreCase(bucket) ? "UNKNOWN_WAREHOUSE" : "MATCHED"));
            log.setRemark("报关单导出生成");
            log.setCreatedBy(username);
            logs.add(log);
        }
        if (!logs.isEmpty())
        {
            for (int from = 0; from < logs.size(); from += 500)
            {
                int to = Math.min(from + 500, logs.size());
                generateLogMapper.batchUpsert(logs.subList(from, to));
            }
        }
        return declarationNo;
    }

    private String bucketName(String bucket)
    {
        return switch (bucket == null ? "" : bucket)
        {
            case "CZ" -> "捷克仓";
            case "UK" -> "英国仓";
            case "US_GC" -> "美国谷仓";
            case "DE" -> "德国仓";
            case "FBA_DE" -> "FBA(DE)";
            case "FBA_UK" -> "FBA(UK)";
            case "FBA_US" -> "FBA(US)";
            case "FBA_FR" -> "FBA(FR)";
            default -> "未知仓";
        };
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
        if (product.getProductCode() != null) product.setProductCode(EscapeUtil.clean(product.getProductCode()));
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
            CellType cachedType = cell.getCachedFormulaResultType();
            if (cachedType == CellType.STRING) return trim(cell.getStringCellValue());
            if (cachedType == CellType.NUMERIC)
                return BigDecimal.valueOf(cell.getNumericCellValue()).stripTrailingZeros().toPlainString();
            if (cachedType == CellType.BOOLEAN) return Boolean.toString(cell.getBooleanCellValue());
            return "";
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

    // ==================== 批次单价计算 ====================

    /**
     * 根据出入库明细的采购数量和含税单价，按剩余库存倒推当前批次单价。
     * <p>
     * 数量段和单价段右对齐（单价段可能少于数量段，左侧无价格的历史批次忽略）。
     * 从最后一笔采购累计，累计量 ≥ 剩余库存时取该批次单价。
     *
     * @param qtyStr   采购数量，如 "20+66+30+50+50+30"
     * @param priceStr 含税单价，如 "1375/1265/1210/1089"
     * @param remaining 剩余库存
     * @return 批次单价，无法计算则返回 null
     */
    static BigDecimal calculateBatchUnitPrice(String qtyStr, String priceStr, BigDecimal remaining)
    {
        if (qtyStr == null || qtyStr.isEmpty()) return null;
        if (priceStr == null || priceStr.isEmpty()) return null;
        if (remaining == null || remaining.compareTo(BigDecimal.ZERO) <= 0) return null;

        String[] qtyParts = qtyStr.split("\\+");
        String[] priceParts = priceStr.split("/");
        if (qtyParts.length == 0 || priceParts.length == 0) return null;

        // 解析数量（右对齐：price[0] 对应 qty[offset]）
        BigDecimal[] quantities = new BigDecimal[qtyParts.length];
        for (int i = 0; i < qtyParts.length; i++)
        {
            try { quantities[i] = new BigDecimal(qtyParts[i].trim()); }
            catch (NumberFormatException e) { return null; }
        }

        // 解析单价
        BigDecimal[] prices = new BigDecimal[priceParts.length];
        for (int i = 0; i < priceParts.length; i++)
        {
            try { prices[i] = new BigDecimal(priceParts[i].trim()); }
            catch (NumberFormatException e) { return null; }
        }

        int offset = quantities.length - prices.length; // 左侧无对应单价的数量段数
        if (offset < 0) offset = 0; // 防御：单价段数多于数量段

        BigDecimal cumQty = BigDecimal.ZERO;
        // 从最后一批往前累计，BigDecimal 累加和比较，避免 int 截断小数
        for (int i = quantities.length - 1; i >= offset; i--)
        {
            cumQty = cumQty.add(quantities[i]);
            if (cumQty.compareTo(remaining) >= 0)
                return prices[i - offset];
        }
        // 剩余库存大于所有有价批次，取最早单价
        if (prices.length > 0) return prices[0];
        return null;
    }

    /**
     * 为产品列表按 SKU 匹配出入库明细，计算并设置批次单价。
     * 匹配不到 inventory 的保持原价不变。
     */
    private void applyBatchPrices(List<CustomsProduct> products)
    {
        if (products == null || products.isEmpty()) return;
        List<String> skus = products.stream().map(CustomsProduct::getSku)
                .filter(s -> s != null && !s.isEmpty()).distinct().collect(Collectors.toList());
        if (skus.isEmpty()) return;

        List<CustomsInventoryItem> inventoryItems = customsInventoryMapper.selectBySkus(skus);
        Map<String, CustomsInventoryItem> invMap = new HashMap<>();
        for (CustomsInventoryItem item : inventoryItems)
            if (item.getSku() != null) invMap.put(item.getSku(), item);

        for (CustomsProduct product : products)
        {
            CustomsInventoryItem inv = invMap.get(product.getSku());
            if (inv == null) continue;
            BigDecimal batchPrice = calculateBatchUnitPrice(
                    inv.getPurchaseQuantity(), inv.getTaxIncludedPrice(), inv.getRemainingStock());
            if (batchPrice != null) product.setUnitPriceUsd(batchPrice);
        }
    }

    private record SkuRequest(String sku, int quantity) {}
}
